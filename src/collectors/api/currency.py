import argparse
import asyncio
import logging
from collections.abc import Collection
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.base import BaseParser
from src.collectors.schemas import ExchangeRateItem
from src.db.connection import close_db, init_db
from src.db.repository import DatabaseRepository

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
        if isinstance(target_currencies, str):
            target_currencies = (target_currencies,)
        self.__target_currencies = frozenset(c.upper() for c in target_currencies)
        self.__url = url
        self.__timeout = timeout

    @property
    def name(self) -> str:
        return "nbu_exchange_rates"

    async def fetch(self) -> list[dict[str, Any]]:
        """Fetches official daily NBU exchange rates JSON payload."""
        async with httpx.AsyncClient(timeout=self.__timeout) as client:
            response = await client.get(self.__url)
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
            if code not in self.__target_currencies:
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


async def _main(save_to_db: bool, currencies: tuple[str, ...]) -> None:
    parser = NbuCurrencyParser(target_currencies=currencies)
    if save_to_db:
        await init_db()
        try:
            saved = await parser.run()
            print(f"Saved {saved} exchange rates to PostgreSQL.")
        finally:
            await close_db()
        return

    raw_data = await parser.fetch()
    items = parser.parse(raw_data)
    print(f"Fetched {len(items)} NBU exchange rate(s):")
    for item in items:
        print(f"  - {item.currency_code} -> {item.rate_to_uah} UAH ({item.exchange_date})")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="Run NBU currency API collector.")
    arg_parser.add_argument(
        "--currencies",
        nargs="+",
        default=list(DEFAULT_TARGET_CURRENCIES),
        help="Target currency codes (default: USD EUR PLN GBP).",
    )
    arg_parser.add_argument(
        "--save",
        action="store_true",
        help="Persist exchange rates via BaseParser.run() into PostgreSQL.",
    )
    cli_args = arg_parser.parse_args()
    asyncio.run(
        _main(save_to_db=cli_args.save, currencies=tuple(cli_args.currencies))
    )
