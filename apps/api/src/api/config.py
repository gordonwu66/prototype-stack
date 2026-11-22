import os
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Tests set API_ENV_FILE="" so a developer's .env (API keys, the dev database) never
        # applies to them.
        env_file=os.environ.get("API_ENV_FILE", ".env") or None,
        extra="ignore",
        # Empty values count as unset, so placeholders like `DB_HOST=` in .env are harmless.
        env_ignore_empty=True,
    )

    cors_origins: list[str] = ["http://localhost:3000"]
    chat_system_prompt: str | None = None

    # A provider's models are offered only when its credentials/endpoint are set.
    anthropic_api_key: SecretStr | None = None
    anthropic_models: list[str] = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]

    openai_api_key: SecretStr | None = None
    openai_models: list[str] = ["gpt-6.1-sol", "gpt-6.1-terra"]

    # Any OpenAI-compatible server hosting open-weight models: Ollama, vLLM, LM Studio,
    # llama.cpp, or a hosted one (Together, Groq, Fireworks, OpenRouter).
    openweight_base_url: str | None = None
    openweight_api_key: SecretStr | None = None
    openweight_models: list[str] = ["gpt-oss:20b", "qwen3:8b", "llama3.3", "deepseek-r1:8b"]

    # Embeddings for semantic search: any OpenAI-compatible /embeddings endpoint. Defaults to
    # OpenAI with OPENAI_API_KEY; without a key, search runs on BM25 alone.
    embedding_model: str = "text-embedding-3-large"
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None

    # Postgres. Without DB_HOST, chat history stays in process memory and is lost on restart.
    db_host: str | None = None
    db_port: int = 5432
    db_name: str = "prototype"
    # The API's role: reads and writes rows, never changes the schema.
    db_user: str = "app"
    db_password: SecretStr | None = None
    # Alembic's role, which owns the schema. Falls back to DB_USER / DB_PASSWORD.
    db_migration_user: str | None = None
    db_migration_password: SecretStr | None = None
    db_sslmode: Literal["disable", "require", "verify-full"] = "verify-full"
    # CA bundle for verify-full; a relative path is resolved against apps/api.
    db_ssl_root_cert: str = "certs/rds-global-bundle.pem"

    # Sign in to RDS with short-lived IAM tokens instead of passwords. Credentials come from
    # AWS_PROFILE, else the access keys below, else boto3's default chain (an ECS task role).
    db_iam_auth: bool = False
    aws_region: str | None = None
    aws_profile: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None

    def db_login(self, *, migration: bool = False) -> tuple[str, str | None]:
        """The (user, password) to connect as; the password is None under IAM auth."""
        if migration and self.db_migration_user:
            user, password = self.db_migration_user, self.db_migration_password
        else:
            user, password = self.db_user, self.db_password
        if self.db_iam_auth:
            return user, None
        return user, password.get_secret_value() if password else None


settings = Settings()
