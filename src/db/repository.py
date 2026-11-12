from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ExchangeRate, PriceHistory, ScrapeLog


class DatabaseRepository:
    """Handles transactional database persistence for scraped data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_exchange_rate(
        self,
        currency_code: str,
        rate_to_uah: Decimal,
        exchange_date: date,
    ) -> None:
        """Inserts or updates daily NBU exchange rate."""
        stmt = (
            insert(ExchangeRate)
            .values(
                currency_code=currency_code,
                rate_to_uah=rate_to_uah,
                exchange_date=exchange_date,
            )
            .on_conflict_do_update(
                constraint="uq_currency_exchange_date",
                set_={"rate_to_uah": rate_to_uah},
            )
        )
        await self.session.execute(stmt)

    async def get_latest_usd_rate(self) -> Decimal | None:
        """Fetches the latest recorded USD to UAH exchange rate."""
        stmt = (
            select(ExchangeRate.rate_to_uah)
            .where(ExchangeRate.currency_code == "USD")
            .order_by(ExchangeRate.exchange_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_price(
        self,
        store_product_id: int,
        price_uah: Decimal,
        usd_rate: Decimal | None = None,
        recorded_at: datetime | None = None,
    ) -> PriceHistory:
        """Appends raw time-series price record and computes USD equivalent."""
        price_usd = None
        if usd_rate and usd_rate > 0:
            price_usd = round(price_uah / usd_rate, 2)

        record = PriceHistory(
            store_product_id=store_product_id,
            price_uah=price_uah,
            price_usd_computed=price_usd,
            recorded_at=recorded_at or datetime.now(),
        )
        self.session.add(record)
        return record

    async def log_scrape_event(
        self,
        scraper_name: str,
        status: str,
        items_scraped: int,
        started_at: datetime,
        error_message: str | None = None,
    ) -> ScrapeLog:
        """Logs scraper execution result into audit trail."""
        log = ScrapeLog(
            scraper_name=scraper_name,
            status=status,
            items_scraped=items_scraped,
            error_message=error_message,
            started_at=started_at,
            finished_at=datetime.now(),
        )
        self.session.add(log)
        return log
