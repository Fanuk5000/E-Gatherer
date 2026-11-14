import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DatabaseSettings:
    """PostgreSQL connection settings loaded from environment variables."""

    user: str = os.getenv("POSTGRES_USER", "postgres")  # DSN user
    password: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    db: str = os.getenv("POSTGRES_DB", "egatherer")
    host: str = os.getenv("POSTGRES_HOST", "localhost")
    port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    echo: bool = os.getenv("POSTGRES_ECHO", "false").lower() in ("true", "1", "yes")

    @property
    def async_url(self) -> str:
        override = os.getenv("DATABASE_URL")
        if override:
            return override
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


db_settings = DatabaseSettings()
