import asyncio
from dataclasses import dataclass
from typing import Any, cast

from playwright.async_api import Page, Route
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.websites.playwright_base import (
    DEFAULT_BLOCKED_RESOURCE_TYPES,
    DEFAULT_CHROMIUM_ARGS,
    DEFAULT_FIREFOX_PREFS,
    BasePlaywrightScraper,
)


class _DummyScraper(BasePlaywrightScraper[str, str]):
    @property
    def name(self) -> str:
        return "dummy"

    async def scrape_page(self, page: Page) -> str:
        return ""

    def parse(self, raw_data: str) -> list[str]:
        return [raw_data]

    async def save(self, items: list[str], session: AsyncSession) -> int:
        return len(items)


@dataclass
class _FakeRequest:
    resource_type: str


class _FakeRoute:
    def __init__(self, resource_type: str) -> None:
        self.request = _FakeRequest(resource_type=resource_type)
        self.aborted = False
        self.continued = False

    async def abort(self) -> None:
        self.aborted = True

    async def continue_(self) -> None:
        self.continued = True


def test_build_launch_kwargs_firefox_uses_prefs_not_chromium_args() -> None:
    scraper = _DummyScraper(browser_engine="firefox", headless=True)
    kwargs: dict[str, Any] = scraper._build_launch_kwargs()

    assert kwargs["headless"] is True
    assert kwargs["firefox_user_prefs"] == DEFAULT_FIREFOX_PREFS
    assert "args" not in kwargs


def test_build_launch_kwargs_chromium_uses_docker_args() -> None:
    scraper = _DummyScraper(browser_engine="chromium", headless=True)
    kwargs: dict[str, Any] = scraper._build_launch_kwargs()

    assert kwargs["headless"] is True
    assert kwargs["args"] == list(DEFAULT_CHROMIUM_ARGS)
    assert "firefox_user_prefs" not in kwargs


def test_build_launch_kwargs_webkit_has_no_engine_specific_flags() -> None:
    scraper = _DummyScraper(browser_engine="webkit", headless=False)
    assert scraper._build_launch_kwargs() == {"headless": False}


def test_handle_route_blocks_heavy_assets_and_allows_dom_and_css() -> None:
    scraper = _DummyScraper()
    assert scraper._blocked_resource_types == DEFAULT_BLOCKED_RESOURCE_TYPES

    async def _run() -> None:
        for resource_type in ("image", "media", "font"):
            route = _FakeRoute(resource_type)
            await scraper._handle_route(cast(Route, route))
            assert route.aborted is True
            assert route.continued is False

        for resource_type in ("document", "script", "stylesheet", "xhr", "fetch"):
            route = _FakeRoute(resource_type)
            await scraper._handle_route(cast(Route, route))
            assert route.aborted is False
            assert route.continued is True

    asyncio.run(_run())


def test_handle_route_respects_custom_blocked_resource_types() -> None:
    scraper = _DummyScraper(blocked_resource_types=frozenset())

    async def _run() -> None:
        route = _FakeRoute("image")
        await scraper._handle_route(cast(Route, route))
        assert route.aborted is False
        assert route.continued is True

    asyncio.run(_run())
