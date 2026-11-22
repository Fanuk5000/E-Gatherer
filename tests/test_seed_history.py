import random
from datetime import date
from decimal import Decimal

from scripts.seed_history import generate_historical_prices, missing_backfill_dates


def test_missing_backfill_dates_skips_existing_and_sorts() -> None:
    targets = [date(2026, 11, 21), date(2026, 11, 19), date(2026, 11, 20)]
    existing = {date(2026, 11, 20)}

    assert missing_backfill_dates(targets, existing) == [
        date(2026, 11, 19),
        date(2026, 11, 21),
    ]


def test_generate_historical_prices_is_deterministic_and_positive() -> None:
    dates = [date(2026, 11, 19), date(2026, 11, 20), date(2026, 11, 21)]
    first = generate_historical_prices(Decimal("1000.00"), dates, random.Random(42))
    second = generate_historical_prices(Decimal("1000.00"), dates, random.Random(42))

    assert first == second
    assert set(first) == set(dates)
    for price in first.values():
        assert price > Decimal("0")
        assert price == price.quantize(Decimal("0.01"))
