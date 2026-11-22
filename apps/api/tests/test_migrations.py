import pytest
from alembic import command

from api.db.engine import alembic_config, database


def test_models_match_migrations() -> None:
    """Fails when models.py changed without a migration (`pnpm db:revision "<message>"`)."""
    if not database.configured:
        pytest.skip("Postgres not configured; run `pnpm test:api:db`")
    command.check(alembic_config())
