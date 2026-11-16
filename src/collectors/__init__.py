"""ETL parsers package for E-gatherer."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.collectors.api.currency import NbuCurrencyParser
    from src.collectors.base import BaseParser
    from src.collectors.schemas import ExchangeRateItem, ScrapedPriceItem

_EXPORTS: dict[str, tuple[str, str]] = {
    "BaseParser": ("src.parsers.base", "BaseParser"),
    "ExchangeRateItem": ("src.parsers.schemas", "ExchangeRateItem"),
    "NbuCurrencyParser": ("rc.collectors.api.currency", "NbuCurrencyParser"),
    "ScrapedPriceItem": ("src.parsers.schemas", "ScrapedPriceItem"),
}

__all__ = [
    "BaseParser",
    "ExchangeRateItem",
    "NbuCurrencyParser",
    "ScrapedPriceItem",
]


def __getattr__(name: str) -> Any:
    """Lazily import public parser symbols on first attribute access."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value
