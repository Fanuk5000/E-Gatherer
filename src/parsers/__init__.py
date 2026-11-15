"""ETL parsers package for E-gatherer."""

from src.parsers.base import BaseParser
from src.parsers.currency import NbuCurrencyParser
from src.parsers.schemas import ExchangeRateItem, ScrapedPriceItem

__all__ = [
    "BaseParser",
    "ExchangeRateItem",
    "NbuCurrencyParser",
    "ScrapedPriceItem",
]
