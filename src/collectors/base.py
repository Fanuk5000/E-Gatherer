import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.connection import get_session
from src.db.repository import DatabaseRepository

RawT = TypeVar("RawT")
ParsedT = TypeVar("ParsedT")

logger = logging.getLogger(__name__)


class BaseParser[RawT, ParsedT](ABC):
    """Abstract base class defining library-agnostic ETL parser contract."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique parser identifier recorded in etl.scrape_logs."""

    @abstractmethod
    async def fetch(self) -> RawT:
        """Retrieves raw payload from target source (httpx, Playwright, etc.)."""

    @abstractmethod
    def parse(self, raw_data: RawT) -> list[ParsedT]:
        """Transforms and validates raw payload into immutable dataclass items."""

    @abstractmethod
    async def save(self, items: list[ParsedT], session: AsyncSession) -> int:
        """Persists parsed items inside active DB transaction and returns saved count."""

    async def run(self) -> int:
        """Template method orchestrating fetch -> parse -> save with audit logging."""
        started_at = datetime.now(
            UTC
        )  # used bare UTC cause grafana autoconverts to user timezone
        logger.info("Starting parser '%s'...", self.name)

        try:
            raw_data = await self.fetch()
            items = self.parse(raw_data)
            logger.info("Parser '%s' extracted %d items.", self.name, len(items))

            async with get_session() as session:
                saved_count = await self.save(items, session)
                repo = DatabaseRepository(session)
                await repo.log_scrape_event(
                    scraper_name=self.name,
                    status="SUCCESS",
                    items_scraped=saved_count,
                    started_at=started_at,
                )

            logger.info("Parser '%s' finished: %d items saved.", self.name, saved_count)
            return saved_count

        except Exception as exc:
            logger.exception("Parser '%s' failed:", self.name)
            try:
                async with get_session() as err_session:
                    repo = DatabaseRepository(err_session)
                    await repo.log_scrape_event(
                        scraper_name=self.name,
                        status="FAILED",
                        items_scraped=0,
                        started_at=started_at,
                        error_message=str(exc),
                    )
            except Exception:
                logger.exception("Failed to record error log for '%s'.", self.name)
            raise
