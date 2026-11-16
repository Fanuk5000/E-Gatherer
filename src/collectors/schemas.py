from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(slots=True, frozen=True)
class ExchangeRateItem:
    """Validated official daily exchange rate entry."""

    currency_code: str
    rate_to_uah: Decimal  # numbers after point - Decimal, 0.5, 0.7 and etc
    exchange_date: date

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class ScrapedPriceItem:
    """Validated scraped store listing offer."""

    external_id: str
    name: str
    price_uah: Decimal
    url: str
    is_in_stock: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
