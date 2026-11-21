import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

from playwright.async_api import (
    Page,
    Route,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from src.collectors.base import BaseParser

BrowserEngine = Literal["firefox", "chromium", "webkit"]

DEFAULT_BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({"image", "media", "font"})
DEFAULT_FIREFOX_PREFS: dict[str, str | float | bool] = {
    "toolkit.telemetry.enabled": False,
    "app.update.enabled": False,
    "browser.shell.checkDefaultBrowser": False,
    "browser.cache.memory.enable": True,
    "browser.cache.memory.capacity": 32768,
}
DEFAULT_CHROMIUM_ARGS: tuple[str, ...] = (
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
)

logger = logging.getLogger(__name__)


class BasePlaywrightScraper[RawT, ParsedT](BaseParser[RawT, ParsedT], ABC):
    """Reusable Playwright base scraper managing browser lifecycle and common UI helpers."""

    def __init__(
        self,
        *,
        browser_engine: BrowserEngine = "firefox",
        headless: bool = True,
        timeout_ms: float = 15_000.0,
        user_agent: str | None = None,
        blocked_resource_types: frozenset[str] = DEFAULT_BLOCKED_RESOURCE_TYPES,
    ) -> None:
        self._browser_engine = browser_engine
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._user_agent = user_agent
        self._blocked_resource_types = blocked_resource_types

    def _build_launch_kwargs(self) -> dict[str, Any]:
        """Returns engine-specific launch options for low-memory headless execution."""
        kwargs: dict[str, Any] = {"headless": self._headless}
        if self._browser_engine == "firefox":
            kwargs["firefox_user_prefs"] = dict(DEFAULT_FIREFOX_PREFS)
        elif self._browser_engine == "chromium":
            kwargs["args"] = list(DEFAULT_CHROMIUM_ARGS)
        return kwargs

    async def _handle_route(self, route: Route) -> None:
        """Aborts configured heavy resource types to reduce RAM and bandwidth usage."""
        if route.request.resource_type in self._blocked_resource_types:
            await route.abort()
            return
        await route.continue_()

    async def fetch(self) -> RawT:
        """Launches configured Playwright engine, runs scrape_page, and cleans up."""
        async with async_playwright() as playwright:
            launcher = getattr(playwright, self._browser_engine)
            browser = await launcher.launch(**self._build_launch_kwargs())
            context = None
            page: Page | None = None
            try:
                context_kwargs: dict[str, Any] = {}
                if self._user_agent:
                    context_kwargs["user_agent"] = self._user_agent

                context = await browser.new_context(**context_kwargs)
                if self._blocked_resource_types:
                    await context.route("**/*", self._handle_route)
                page = await context.new_page()
                page.set_default_timeout(self._timeout_ms)
                return await self.scrape_page(page)
            finally:
                if page is not None:
                    await page.close()
                if context is not None:
                    await context.close()
                await browser.close()

    @abstractmethod
    async def scrape_page(self, page: Page) -> RawT:
        """Site-specific navigation, interaction, and raw payload extraction."""

    async def click_load_more(
        self,
        page: Page,
        button_selector: str,
        item_selector: str,
        max_clicks: int = 50,
        wait_timeout_ms: float = 5_000.0,
    ) -> int:
        """Clicks a load-more button until hidden or item count stops growing."""
        clicks = 0
        button = page.locator(button_selector).first
        items = page.locator(item_selector)

        while clicks < max_clicks:
            if await button.count() == 0 or not await button.is_visible():
                break

            prev_count = await items.count()
            await button.scroll_into_view_if_needed()
            await button.click()
            clicks += 1

            try:
                await page.wait_for_function(
                    "([selector, previous]) => document.querySelectorAll(selector).length > previous",
                    arg=[item_selector, prev_count],
                    timeout=wait_timeout_ms,
                )
            except PlaywrightTimeoutError:
                logger.debug(
                    "Stopped load-more after click %d on '%s' (no additional items).",
                    clicks,
                    button_selector,
                )
                break

        return clicks
