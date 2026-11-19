from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Category,
    ExchangeRate,
    PriceHistory,
    Product,
    ScrapeLog,
    Store,
    StoreProduct,
)


class DatabaseRepository:
    """Handles transactional database persistence for scraped data."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_exchange_rate(
        self,
        currency_code: str,
        rate_to_uah: Decimal,
        exchange_date: date,
    ) -> None:
        """Inserts or updates daily NBU exchange rate."""
        stmt = (
            insert(ExchangeRate)
            .values(
                currency_code=currency_code,
                rate_to_uah=rate_to_uah,
                exchange_date=exchange_date,
            )
            .on_conflict_do_update(
                constraint="uq_currency_exchange_date",
                set_={"rate_to_uah": rate_to_uah},
            )
        )
        await self.session.execute(stmt)

    async def get_latest_usd_rate(self) -> Decimal | None:
        """Fetches the latest recorded USD to UAH exchange rate."""
        stmt = (
            select(ExchangeRate.rate_to_uah)
            .where(ExchangeRate.currency_code == "USD")
            .order_by(ExchangeRate.exchange_date.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def record_price(
        self,
        store_product_id: int,
        price_uah: Decimal,
        usd_rate: Decimal | None = None,
        recorded_at: datetime | None = None,
    ) -> PriceHistory:
        """Appends raw time-series price record and computes USD equivalent."""
        price_usd = None
        if usd_rate and usd_rate > 0:
            price_usd = round(price_uah / usd_rate, 2)

        record = PriceHistory(
            store_product_id=store_product_id,
            price_uah=price_uah,
            price_usd_computed=price_usd,
            recorded_at=recorded_at or datetime.now(),
        )
        self.session.add(record)
        return record

    async def log_scrape_event(
        self,
        scraper_name: str,
        status: str,
        items_scraped: int,
        started_at: datetime,
        error_message: str | None = None,
    ) -> ScrapeLog:
        """Logs scraper execution result into audit trail."""
        log = ScrapeLog(
            scraper_name=scraper_name,
            status=status,
            items_scraped=items_scraped,
            error_message=error_message,
            started_at=started_at,
            finished_at=datetime.now(),
        )
        self.session.add(log)
        return log

    async def get_or_create_store(self, name: str, base_url: str) -> Store:
        """Returns existing store by name or inserts a new store record."""
        stmt = select(Store).where(Store.name == name)
        store = (await self.session.execute(stmt)).scalar_one_or_none()
        if store is not None:
            return store

        store = Store(name=name, base_url=base_url)
        self.session.add(store)
        await self.session.flush()
        return store

    async def get_or_create_category(
        self,
        name: str,
        slug: str,
        parent_id: int | None = None,
    ) -> Category:
        """Returns existing category by slug or inserts a new category."""
        stmt = select(Category).where(Category.slug == slug)
        category = (await self.session.execute(stmt)).scalar_one_or_none()
        if category is not None:
            return category

        category = Category(name=name, slug=slug, parent_id=parent_id)
        self.session.add(category)
        await self.session.flush()
        return category

    async def get_or_create_product(
        self,
        category_id: int,
        brand: str,
        model_name: str,
    ) -> Product:
        """Returns existing canonical product or inserts a new product."""
        stmt = select(Product).where(
            Product.category_id == category_id,
            Product.model_name == model_name,
        )
        product = (await self.session.execute(stmt)).scalar_one_or_none()
        if product is not None:
            return product

        product = Product(category_id=category_id, brand=brand, model_name=model_name)
        self.session.add(product)
        await self.session.flush()
        return product

    async def upsert_store_product(
        self,
        store_id: int,
        product_id: int,
        external_id: str,
        url: str,
        is_in_stock: bool = True,
    ) -> StoreProduct:
        """Inserts or updates a store listing keyed by (store_id, external_id)."""
        stmt = (
            insert(StoreProduct)
            .values(
                store_id=store_id,
                product_id=product_id,
                external_id=external_id,
                url=url,
                is_in_stock=is_in_stock,
            )
            .on_conflict_do_update(
                constraint="uq_store_external_id",
                set_={
                    "product_id": product_id,
                    "url": url,
                    "is_in_stock": is_in_stock,
                },
            )
            .returning(StoreProduct)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def search_products_bare_sql(
        self,
        query: str,
        limit: int = 20,
    ) -> list[Product]:
        """Searches product model names with bare SQL ILIKE substring scan."""
        stmt = (
            select(Product)
            .where(Product.model_name.ilike(f"%{query}%"))
            .order_by(Product.model_name)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_products_trgm(
        self,
        query: str,
        min_similarity: float = 0.2,
        limit: int = 20,
    ) -> list[tuple[Product, float]]:
        """Searches product model names via pg_trgm % operator and GIN trigram index."""
        await self.session.execute(
            text("SELECT set_limit(:threshold)"),
            {"threshold": min_similarity},
        )
        sim_expr = func.similarity(Product.model_name, query).label("trgm_score")
        stmt = (
            select(Product, sim_expr)
            .where(Product.model_name.op("%")(query))
            .order_by(sim_expr.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]
