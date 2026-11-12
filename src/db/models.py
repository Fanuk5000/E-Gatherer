from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy 2.0 models."""


class Store(Base):
    """Monitored e-commerce stores (e.g. Telemart, Brain, ITbox)."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    store_products: Mapped[list[StoreProduct]] = relationship(
        back_populates="store", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Store id={self.id} name='{self.name}'>"


class Category(Base):
    """Hierarchical catalog categories (e.g. PC Components -> Graphics Cards)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    parent: Mapped[Category | None] = relationship(
        "Category", remote_side=[id], back_populates="subcategories"
    )
    subcategories: Mapped[list[Category]] = relationship(
        "Category", back_populates="parent"
    )
    products: Mapped[list[Product]] = relationship(back_populates="category")

    def __repr__(self) -> str:
        return f"<Category id={self.id} name='{self.name}'>"


class Product(Base):
    """Canonical/reference product entity (e.g. 'GeForce RTX 4070 Ti SUPER')."""

    __tablename__ = "products"
    __table_args__ = (
        Index(
            "ix_products_model_name_trgm",
            "model_name",
            postgresql_using="gin",
            postgresql_ops={"model_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    brand: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    specs: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    category: Mapped[Category] = relationship(back_populates="products")
    store_listings: Mapped[list[StoreProduct]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} model='{self.model_name}'>"


class StoreProduct(Base):
    """Store-specific product offer mapping canonical product to store item URL/ID."""

    __tablename__ = "store_products"
    __table_args__ = (
        UniqueConstraint("store_id", "external_id", name="uq_store_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(150), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    is_in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    store: Mapped[Store] = relationship(back_populates="store_products")
    product: Mapped[Product] = relationship(back_populates="store_listings")
    prices: Mapped[list[PriceHistory]] = relationship(
        back_populates="store_product", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<StoreProduct id={self.id} store_id={self.store_id} ext_id='{self.external_id}'>"


class PriceHistory(Base):
    """Time-series raw price points captured by scraper."""

    __tablename__ = "price_history"
    __table_args__ = (
        Index(
            "ix_price_history_store_prod_recorded",
            "store_product_id",
            text("recorded_at DESC"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("store_products.id", ondelete="CASCADE"), nullable=False
    )
    price_uah: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    price_usd_computed: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    store_product: Mapped[StoreProduct] = relationship(back_populates="prices")

    def __repr__(self) -> str:
        return f"<PriceHistory id={self.id} price_uah={self.price_uah} at={self.recorded_at}>"


class ExchangeRate(Base):
    """Daily official NBU currency rates."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint(
            "currency_code", "exchange_date", name="uq_currency_exchange_date"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    rate_to_uah: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    exchange_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ExchangeRate {self.currency_code}={self.rate_to_uah} date={self.exchange_date}>"


class ScrapeLog(Base):
    """Audit trail of scheduled scraping executions."""

    __tablename__ = "scrape_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'SUCCESS', 'FAILED', 'PARTIAL'
    items_scraped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<ScrapeLog id={self.id} scraper='{self.scraper_name}' status='{self.status}'>"
