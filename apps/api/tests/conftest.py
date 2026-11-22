import os

# Never run tests with the developer's .env (API keys, the dev RDS database). Without DB_*
# variables the app uses the in-memory chat store; `pnpm test:api:db` sets them to point at
# the throwaway Postgres from infra/docker-compose.yml, so the same tests cover Postgres.
os.environ["API_ENV_FILE"] = ""

import pytest  # noqa: E402
from alembic import command  # noqa: E402

from api.config import settings  # noqa: E402
from api.db.engine import alembic_config  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    if settings.db_host:
        command.upgrade(alembic_config(), "head")
