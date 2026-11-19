"""API collectors package for E-gatherer."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.collectors.api.currency import NbuCurrencyParser

_EXPORTS: dict[str, tuple[str, str]] = {
    "NbuCurrencyParser": ("src.collectors.api.currency", "NbuCurrencyParser"),
}

__all__ = ["NbuCurrencyParser"]


def __getattr__(name: str) -> Any:
    """Lazily import API collector symbols on first attribute access."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_path, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_path), attr_name)
    globals()[name] = value
    return value
