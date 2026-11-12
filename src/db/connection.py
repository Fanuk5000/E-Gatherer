from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.db.models import Base
from src.db.settings import db_settings
from src.db.sql_views import ANALYTICAL_VIEWS_DDL

# Pool tuned for low-RAM (4GB) server & 5400 RPM HDD
engine: AsyncEngine = create_async_engine(
    db_settings.async_url,
    echo=db_settings.echo,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Creates database schema, tables, indexes, and analytical views."""
    async with engine.begin() as connection:
        # Create all tables defined in models.py
        await connection.run_sync(Base.metadata.create_all)

        # Create/refresh analytical SQL views for Grafana
        for view_ddl in ANALYTICAL_VIEWS_DDL:
            await connection.execute(text(view_ddl))


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession]:
    """Provides transactional async database session context."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Closes all active database connection pools gracefully."""
    await engine.dispose()
