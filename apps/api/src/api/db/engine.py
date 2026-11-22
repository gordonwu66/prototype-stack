import ssl
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from api.config import Settings, settings

API_DIR = Path(__file__).resolve().parents[3]  # apps/api


def database_url(s: Settings, *, migration: bool = False) -> URL:
    user, password = s.db_login(migration=migration)
    return URL.create(
        "postgresql+asyncpg",
        username=user,
        password=password,
        host=s.db_host,
        port=s.db_port,
        database=s.db_name,
    )


def ssl_context(s: Settings) -> ssl.SSLContext | bool:
    if s.db_sslmode == "disable":
        return False
    if s.db_sslmode == "require":
        # Encrypted but unverified, like libpq's sslmode=require.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    cafile = API_DIR / s.db_ssl_root_cert
    if not cafile.is_file():
        raise RuntimeError(
            f"DB_SSLMODE=verify-full needs the RDS CA bundle at {cafile}. "
            "Download it (see infra/rds/README.md) or point DB_SSL_ROOT_CERT at it."
        )
    return ssl.create_default_context(cafile=cafile)


def iam_token_factory(s: Settings) -> Callable[[str], str]:
    """Returns user -> a 15-minute RDS auth token, signed locally with the app's AWS identity."""
    import boto3

    if not s.aws_region:
        raise RuntimeError("DB_IAM_AUTH needs AWS_REGION")
    session = boto3.Session(
        profile_name=s.aws_profile,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=(
            s.aws_secret_access_key.get_secret_value() if s.aws_secret_access_key else None
        ),
        region_name=s.aws_region,
    )
    rds = session.client("rds")

    def token(user: str) -> str:
        return rds.generate_db_auth_token(
            DBHostname=s.db_host, Port=s.db_port, DBUsername=user, Region=s.aws_region
        )

    return token


def create_engine(s: Settings, *, migration: bool = False) -> AsyncEngine:
    if not s.db_host:
        raise RuntimeError("DB_HOST is not set")
    if s.db_iam_auth and s.db_sslmode == "disable":
        raise RuntimeError("RDS IAM authentication requires TLS; set DB_SSLMODE=verify-full")
    engine = create_async_engine(
        database_url(s, migration=migration),
        connect_args={"ssl": ssl_context(s)},
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
    )
    if s.db_iam_auth:
        token = iam_token_factory(s)
        user, _ = s.db_login(migration=migration)

        # Tokens expire after 15 minutes, so sign a fresh one for every new connection.
        @event.listens_for(engine.sync_engine, "do_connect")
        def _use_iam_token(dialect: Any, conn_rec: Any, cargs: Any, cparams: dict) -> None:
            cparams["password"] = token(user)

    return engine


class Database:
    """The API's connection pool, shared by chat and search. Started and stopped by the app."""

    def __init__(self, s: Settings) -> None:
        self.settings = s
        self._engine: AsyncEngine | None = None
        self._sessions: async_sessionmaker[AsyncSession] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.db_host)

    async def start(self) -> None:
        if not self.configured or self._engine:
            return
        # Created here rather than at import, so connections belong to the serving event loop.
        engine = create_engine(self.settings)
        try:
            await check_schema(engine)
        except BaseException:
            await engine.dispose()
            raise
        self._engine = engine
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
        self._engine = self._sessions = None

    @property
    def sessions(self) -> async_sessionmaker[AsyncSession]:
        if self._sessions is None:
            raise RuntimeError("The database is not configured or not started")
        return self._sessions


database = Database(settings)


@cache
def alembic_config() -> Config:
    return Config(str(API_DIR / "alembic.ini"))


async def check_schema(engine: AsyncEngine) -> None:
    """Fails fast when the database isn't reachable or isn't migrated to this code's head."""
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    url = engine.url
    try:
        async with engine.connect() as conn:
            current = await conn.run_sync(
                lambda c: MigrationContext.configure(c).get_current_revision()
            )
    except Exception as exc:
        raise RuntimeError(
            f"Can't connect to Postgres at {url.host}:{url.port}/{url.database} "
            f"as {url.username}: {exc}"
        ) from exc
    if current != head:
        raise RuntimeError(
            f"The database schema is at revision {current or '(none)'}, but this code expects "
            f"{head}. Run `pnpm db:migrate`."
        )
