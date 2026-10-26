"""Application settings, read from environment variables (and `.env` when present)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    # `.env` also carries keys for the frontend and later work packages.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- PostgreSQL ---
    postgres_user: str = "support"
    postgres_password: str = "change-me"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "support"
    postgres_test_db: str = "support_test"

    # --- Qdrant ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "kb_chunks"

    # --- Embeddings / retrieval ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    # Downloaded at image build time (Dockerfile); outside /app so the dev bind mount keeps it.
    embedding_cache_dir: str = "/opt/fastembed"
    # Semantic results scoring below this are dropped (docs/PLAN.md §9); tuned in WP7.
    retrieval_score_threshold: float = 0.5

    # --- Auth ---
    # Required: the app refuses to start rather than sign tokens with a known default key.
    jwt_secret: str
    jwt_expire_minutes: int = 480
    jwt_algorithm: str = "HS256"

    # --- Knowledge base ---
    max_upload_mb: int = 10
    # Where the Acme Cloud sample documents are mounted (docker-compose.yml).
    sample_kb_dir: str = "/sample_kb"

    # --- App ---
    log_level: str = "INFO"
    # Comma-separated list, e.g. "http://localhost:5173,http://127.0.0.1:5173"
    cors_origins: str = "http://localhost:5173"

    def _url(self, db_name: str) -> str:
        # URL.create escapes special characters in the password.
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=db_name,
        ).render_as_string(hide_password=False)

    @property
    def database_url(self) -> str:
        return self._url(self.postgres_db)

    @property
    def test_database_url(self) -> str:
        return self._url(self.postgres_test_db)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
