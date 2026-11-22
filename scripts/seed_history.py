import argparse
import asyncio
import logging
import random
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func, select

from src.collectors.api.currency import DEFAULT_TARGET_CURRENCIES, NbuCurrencyParser
from src.collectors.schemas import ExchangeRateItem
from src.db.connection import close_db, get_session, init_db
from src.db.models import ExchangeRate, PriceHistory
from src.db.repository import DatabaseRepository
from src.logger_config import setup_logging

NBU_EXCHANGE_BASE_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
KYIV_TZ = ZoneInfo("Europe/Kyiv")

logger = logging.getLogger(__name__)


def missing_backfill_dates(
    target_dates: Sequence[date],
    existing_dates: set[date],
) -> list[date]:
    """Returns sorted target dates not already present in existing_dates."""
    return sorted(d for d in target_dates if d not in existing_dates)


def generate_historical_prices(
    base_price: Decimal,
    dates: Sequence[date],
    rng: random.Random,
    max_daily_pct: float = 0.02,
) -> dict[date, Decimal]:
    """Generates realistic daily prices walking backward from base_price."""
    ordered = sorted(dates, reverse=True)
    generated: dict[date, Decimal] = {}
    current = base_price

    for day in ordered:
        factor = Decimal(str(1.0 + rng.uniform(-max_daily_pct, max_daily_pct)))
        current = max(Decimal("0.01"), (current * factor).quantize(Decimal("0.01")))
        generated[day] = current

    return generated


async def _fetch_day_rates(
    client: httpx.AsyncClient,
    parser: NbuCurrencyParser,
    semaphore: asyncio.Semaphore,
    target_date: date,
) -> list[ExchangeRateItem]:
    url = f"{NBU_EXCHANGE_BASE_URL}?date={target_date:%Y%m%d}&json"
    async with semaphore:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        raise TypeError(
            f"Expected JSON list from NBU API for {target_date}, got {type(payload).__name__}"
        )
    return parser.parse(payload)


async def fetch_nbu_rates_for_dates(
    dates: Sequence[date],
    currencies: Collection[str] = DEFAULT_TARGET_CURRENCIES,
    concurrency: int = 4,
    timeout: float = 15.0,
) -> list[ExchangeRateItem]:
    """Fetches real historical NBU exchange rates for each date in dates."""
    parser = NbuCurrencyParser(target_currencies=currencies)
    semaphore = asyncio.Semaphore(concurrency)
    collected: dict[tuple[str, date], ExchangeRateItem] = {}

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            _fetch_day_rates(client, parser, semaphore, target_date)
            for target_date in dates
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for target_date, result in zip(dates, results, strict=True):
        if isinstance(result, BaseException):
            logger.warning("Failed to fetch NBU rates for %s: %s", target_date, result)
            continue
        for item in result:
            collected[(item.currency_code, item.exchange_date)] = item

    return list(collected.values())


def _nearest_usd_rate(
    target_date: date,
    usd_by_date: dict[date, Decimal],
    fallback_rate: Decimal | None,
) -> Decimal | None:
    if target_date in usd_by_date:
        return usd_by_date[target_date]
    if not usd_by_date:
        return fallback_rate
    nearest = min(usd_by_date, key=lambda d: abs((d - target_date).days))
    return usd_by_date[nearest]


async def seed_history(days: int = 30, seed: int = 42) -> tuple[int, int]:
    """Backfills real historical NBU rates and daily product price history."""
    if days < 1:
        raise ValueError("days must be >= 1")

    today = datetime.now(KYIV_TZ).date()
    history_dates = [today - timedelta(days=offset) for offset in range(days, 0, -1)]
    nbu_dates = [*history_dates, today]

    logger.info("Fetching real NBU exchange rates for %d day(s)...", len(nbu_dates))
    nbu_items = await fetch_nbu_rates_for_dates(nbu_dates)

    rng = random.Random(seed)
    inserted_prices = 0

    await init_db()
    try:
        async with get_session() as session:
            repo = DatabaseRepository(session)
            for item in nbu_items:
                await repo.upsert_exchange_rate(
                    currency_code=item.currency_code,
                    rate_to_uah=item.rate_to_uah,
                    exchange_date=item.exchange_date,
                )

            usd_rows = (
                await session.execute(
                    select(ExchangeRate.exchange_date, ExchangeRate.rate_to_uah).where(
                        ExchangeRate.currency_code == "USD"
                    )
                )
            ).all()
            usd_by_date = {row[0]: row[1] for row in usd_rows}
            fallback_usd = await repo.get_latest_usd_rate()

            latest_stmt = (
                select(PriceHistory.store_product_id, PriceHistory.price_uah)
                .distinct(PriceHistory.store_product_id)
                .order_by(
                    PriceHistory.store_product_id,
                    PriceHistory.recorded_at.desc(),
                    PriceHistory.id.desc(),
                )
            )
            latest_products = (await session.execute(latest_stmt)).all()
            if not latest_products:
                logger.warning(
                    "No scraped products in pricing.price_history yet. "
                    "Run 'make scrape-save' or 'make run-container-once' first."
                )
                return len(nbu_items), 0

            existing_stmt = select(
                PriceHistory.store_product_id,
                func.date(PriceHistory.recorded_at),
            ).distinct()
            existing_by_product: dict[int, set[date]] = defaultdict(set)
            for sp_id, existing_day in (await session.execute(existing_stmt)).all():
                existing_by_product[sp_id].add(existing_day)

            for store_product_id, base_price in latest_products:
                needed_dates = missing_backfill_dates(
                    history_dates, existing_by_product[store_product_id]
                )
                if not needed_dates:
                    continue

                generated = generate_historical_prices(base_price, needed_dates, rng)
                for day in needed_dates:
                    usd_rate = _nearest_usd_rate(day, usd_by_date, fallback_usd)
                    # Noon UTC keeps calendar date identical in UTC and Europe/Kyiv.
                    recorded_at = datetime.combine(day, time(12, 0), tzinfo=UTC)
                    await repo.record_price(
                        store_product_id=store_product_id,
                        price_uah=generated[day],
                        usd_rate=usd_rate,
                        recorded_at=recorded_at,
                    )
                    inserted_prices += 1

        logger.info(
            "Seed completed: %d NBU rate entries upserted, %d historical price rows added.",
            len(nbu_items),
            inserted_prices,
        )
        return len(nbu_items), inserted_prices
    finally:
        await close_db()


def main() -> None:
    setup_logging(
        log_dir="logs", log_file="app.log", default_level="INFO", silence_third_party=True
    )
    parser = argparse.ArgumentParser(
        description="Backfill historical NBU rates and product price history."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of past days to backfill (default: 30).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible historical price drift.",
    )
    args = parser.parse_args()
    rates_count, prices_count = asyncio.run(seed_history(days=args.days, seed=args.seed))
    print(
        f"Seeded {rates_count} NBU rate entries and {prices_count} historical price rows."
    )


if __name__ == "__main__":
    main()
