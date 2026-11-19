import argparse
import asyncio
import logging
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import Page
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.schemas import ScrapedPriceItem
from src.collectors.websites.playwright_base import BasePlaywrightScraper, BrowserEngine
from src.db.connection import close_db, init_db
from src.db.repository import DatabaseRepository

logger = logging.getLogger(__name__)

DEFAULT_TARGET_URL = "https://webscraper.io/test-sites/load-more"
DEFAULT_STORE_NAME = "webscraper.io"
DEFAULT_BASE_URL = "https://webscraper.io"
DEFAULT_CATEGORY_NAME = "Load More Test Catalog"
DEFAULT_CATEGORY_SLUG = "webscraper-load-more"
DEFAULT_USD_TO_UAH = Decimal("41.50")

LOAD_MORE_BUTTON_SELECTOR = ".load-more-btn.ecommerce-items-scroll-more"
PRODUCT_CARD_SELECTOR = "div.card.test-sites-card"


def _split_brand_and_model(title: str) -> tuple[str, str]:
    """Derives brand token and normalized model string from product title."""
    cleaned = " ".join(title.split())
    first_token = cleaned.split(" ", maxsplit=1)[0] if cleaned else "Unknown"
    return first_token[:80], cleaned[:255]


def _parse_decimal_price(raw_price: str) -> Decimal | None:
    """Extracts numeric price from strings like 'USD 228 511' or '$1,139.54'."""
    compact = re.sub(r"(?<=\d)\s+(?=\d)", "", raw_price)
    match = re.search(r"[\d,]+(?:\.\d+)?", compact)
    if not match:
        return None
    normalized = match.group(0).replace(",", "")
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _extract_external_id(href: str, fallback_name: str) -> str:
    """Extracts stable product identifier from listing URL or normalized title."""
    path = urlparse(href).path.rstrip("/")
    tail = path.rsplit("/", maxsplit=1)[-1] if path else ""
    if tail:
        return tail[:150]
    slug = re.sub(r"[^a-z0-9]+", "-", fallback_name.lower()).strip("-")
    return (slug or "unknown")[:150]


class WebScraperLoadMoreScraper(BasePlaywrightScraper[str, ScrapedPriceItem]):
    """Playwright Gecko scraper for webscraper.io load-more product listings."""

    def __init__(
        self,
        url: str = DEFAULT_TARGET_URL,
        *,
        browser_engine: BrowserEngine = "firefox",
        headless: bool = True,
        timeout_ms: float = 15_000.0,
        max_clicks: int = 50,
        usd_to_uah: Decimal = DEFAULT_USD_TO_UAH,
    ) -> None:
        super().__init__(
            browser_engine=browser_engine,
            headless=headless,
            timeout_ms=timeout_ms,
        )
        self._url = url
        self._max_clicks = max_clicks
        self._usd_to_uah = usd_to_uah

    @property
    def name(self) -> str:
        return "webscraper_load_more"

    async def scrape_page(self, page: Page) -> str:
        """Loads target URL, expands all load-more batches, and returns HTML."""
        await page.goto(self._url, wait_until="domcontentloaded")
        await page.locator(PRODUCT_CARD_SELECTOR).first.wait_for(state="visible")
        clicks = await self.click_load_more(
            page,
            button_selector=LOAD_MORE_BUTTON_SELECTOR,
            item_selector=PRODUCT_CARD_SELECTOR,
            max_clicks=self._max_clicks,
        )
        logger.info("Expanded load-more page in %d click(s).", clicks)
        return await page.content()

    def parse(self, raw_data: str) -> list[ScrapedPriceItem]:
        """Parses product cards from HTML into validated ScrapedPriceItem records."""
        soup = BeautifulSoup(raw_data, "html.parser")
        items: list[ScrapedPriceItem] = []
        seen_ids: set[str] = set()

        for card in soup.select(PRODUCT_CARD_SELECTOR):
            title_el = card.select_one("h3.card-title a")
            heading_el = card.select_one("h3.card-title")
            price_el = card.select_one(".price [itemprop='price']") or card.select_one(
                ".price"
            )
            if title_el is None or price_el is None:
                continue

            raw_title = str(
                (heading_el.get("title") if heading_el else None)
                or title_el.get_text(" ", strip=True)
            )
            title = " ".join(raw_title.split())
            usd_price = _parse_decimal_price(price_el.get_text(" ", strip=True))
            if not title or usd_price is None:
                continue

            href = str(title_el.get("href") or "")
            full_url = urljoin(self._url, href) if href else self._url
            external_id = _extract_external_id(href, title)
            if external_id in seen_ids:
                continue
            seen_ids.add(external_id)

            badge_el = card.select_one(".availability .badge")
            badge_text = badge_el.get_text(" ", strip=True).lower() if badge_el else ""
            is_in_stock = (
                "available: 0" not in badge_text and "out of stock" not in badge_text
            )

            price_uah = (usd_price * self._usd_to_uah).quantize(Decimal("0.01"))
            items.append(
                ScrapedPriceItem(
                    external_id=external_id,
                    name=title,
                    price_uah=price_uah,
                    url=full_url,
                    is_in_stock=is_in_stock,
                )
            )

        return items

    async def save(self, items: list[ScrapedPriceItem], session: AsyncSession) -> int:
        """Persists scraped listings into catalog.products, store_products, and price_history."""
        if not items:
            return 0

        repo = DatabaseRepository(session)
        store = await repo.get_or_create_store(
            name=DEFAULT_STORE_NAME,
            base_url=DEFAULT_BASE_URL,
        )
        category = await repo.get_or_create_category(
            name=DEFAULT_CATEGORY_NAME,
            slug=DEFAULT_CATEGORY_SLUG,
        )
        usd_rate = await repo.get_latest_usd_rate() or self._usd_to_uah

        for item in items:
            brand, model_name = _split_brand_and_model(item.name)
            product = await repo.get_or_create_product(
                category_id=category.id,
                brand=brand,
                model_name=model_name,
            )
            store_product = await repo.upsert_store_product(
                store_id=store.id,
                product_id=product.id,
                external_id=item.external_id,
                url=item.url,
                is_in_stock=item.is_in_stock,
            )
            await repo.record_price(
                store_product_id=store_product.id,
                price_uah=item.price_uah,
                usd_rate=usd_rate,
            )

        return len(items)


async def _main(save_to_db: bool, url: str) -> None:
    scraper = WebScraperLoadMoreScraper(url=url)
    if save_to_db:
        await init_db()
        try:
            saved = await scraper.run()
            print(f"Saved {saved} items to PostgreSQL.")
        finally:
            await close_db()
        return

    raw_html = await scraper.fetch()
    items = scraper.parse(raw_html)
    print(f"Scraped {len(items)} items from {url}:")
    for item in items[:10]:
        print(
            f"  - [{item.external_id}] {item.name} -> {item.price_uah} UAH ({item.url})"
        )
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run webscraper.io Playwright Gecko scraper."
    )
    parser.add_argument(
        "--url", default=DEFAULT_TARGET_URL, help="Target load-more URL."
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Persist scraped items via BaseParser.run() into PostgreSQL.",
    )
    args = parser.parse_args()
    asyncio.run(_main(save_to_db=args.save, url=args.url))
