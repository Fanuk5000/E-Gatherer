"""Playwright websites scrapers package for E-gatherer."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.collectors.websites.playwright_base import BasePlaywrightScraper
    from src.collectors.websites.webscraper_io import WebScraperLoadMoreScraper

_EXPORTS: dict[str, tuple[str, str]] = {
    "BasePlaywrightScraper": (
        "src.collectors.websites.playwright_base",
        "BasePlaywrightScraper",
    ),
    "WebScraperLoadMoreScraper": (
        "src.collectors.websites.webscraper_io",
        "WebScraperLoadMoreScraper",
    ),
}

__all__ = [
    "BasePlaywrightScraper",
    "WebScraperLoadMoreScraper",
]


def __getattr__(name: str) -> Any:
    """Lazily import web scraper symbols on first attribute access."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value
