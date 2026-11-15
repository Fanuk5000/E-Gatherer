import logging
from collections.abc import Collection
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repository import DatabaseRepository
from src.parsers.base import BaseParser
from src.parsers.schemas import ExchangeRateItem

logger = logging.getLogger(__name__)

NBU_EXCHANGE_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
DEFAULT_TARGET_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "PLN", "GBP")


class NbuCurrencyParser(BaseParser[list[dict[str, Any]], ExchangeRateItem]):
    """Fetches official daily UAH exchange rates from the NBU JSON API."""

    def __init__(
        self,
        target_currencies: Collection[str] = DEFAULT_TARGET_CURRENCIES,
        url: str = NBU_EXCHANGE_URL,
        timeout: float = 15.0,
    ) -> None:
        self.target_currencies = frozenset(c.upper() for c in target_currencies)
        self.url = url
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "nbu_exchange_rates"

    async def fetch(self) -> list[dict[str, Any]]:
        """Fetches official daily NBU exchange rates JSON payload."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(self.url)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, list):
            raise TypeError(
                f"Expected JSON list from NBU API, got {type(payload).__name__}"
            )

        return payload

    def parse(self, raw_data: list[dict[str, Any]]) -> list[ExchangeRateItem]:
        """Filters target currencies, skips reference rates, and validates types."""
        items: list[ExchangeRateItem] = []

        for entry in raw_data:
            code = str(entry.get("cc", "")).upper()
            if code not in self.target_currencies:
                continue

            title = str(entry.get("txt", ""))
            if "довідковий" in title.lower():
                logger.debug("Skipping intraday reference rate entry: %s", title)
                continue

            raw_rate = entry.get("rate")
            raw_date = entry.get("exchangedate")
            if raw_rate is None or not raw_date:
                logger.warning("Incomplete NBU entry skipped for %s: %s", code, entry)
                continue

            items.append(
                ExchangeRateItem(
                    currency_code=code,
                    rate_to_uah=Decimal(str(raw_rate)),
                    exchange_date=datetime.strptime(str(raw_date), "%d.%m.%Y").date(),
                )
            )

        return items

    async def save(self, items: list[ExchangeRateItem], session: AsyncSession) -> int:
        """Upserts validated exchange rates into pricing.exchange_rates."""
        repo = DatabaseRepository(session)
        for item in items:
            await repo.upsert_exchange_rate(
                currency_code=item.currency_code,
                rate_to_uah=item.rate_to_uah,
                exchange_date=item.exchange_date,
            )
        return len(items)
