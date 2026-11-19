"""ETL collectors package for E-gatherer."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.collectors.api.currency import NbuCurrencyParser
    from src.collectors.base import BaseParser
    from src.collectors.schemas import ExchangeRateItem, ScrapedPriceItem
    from src.collectors.web.playwright_base import BasePlaywrightScraper
    from src.collectors.web.webscraper import WebScraperLoadMoreScraper

_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseParser": ("src.collectors.base", "BaseParser"),
    "BasePlaywrightScraper": (
        "src.collectors.web.playwright_base",
        "BasePlaywrightScraper",
    ),
    "ExchangeRateItem": ("src.collectors.schemas", "ExchangeRateItem"),
    "NbuCurrencyParser": ("src.collectors.api.currency", "NbuCurrencyParser"),
    "ScrapedPriceItem": ("src.collectors.schemas", "ScrapedPriceItem"),
    "WebScraperLoadMoreScraper": (
        "src.collectors.web.webscraper",
        "WebScraperLoadMoreScraper",
    ),
}

__all__ = [
    "BaseParser",
    "BasePlaywrightScraper",
    "ExchangeRateItem",
    "NbuCurrencyParser",
    "ScrapedPriceItem",
    "WebScraperLoadMoreScraper",
]


def __getattr__(name: str) -> Any:
    """Lazily import public parser symbols on first attribute access."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value
