from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"
    __table_args__ = (
        CheckConstraint("package_size IS NULL OR package_size > 0", name="product_snapshots_package_size_positive"),
        CheckConstraint("price_sgd >= 0", name="product_snapshots_price_nonnegative"),
        CheckConstraint("rank >= 0", name="product_snapshots_rank_nonnegative"),
        UniqueConstraint(
            "source",
            "search_query",
            "external_id",
            name="product_snapshots_source_query_external_key",
        ),
        Index(
            "product_snapshots_source_query_fetched_idx",
            "source",
            "search_query",
            "fetched_at",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    search_query: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str] = mapped_column(Text)
    rank: Mapped[int]
    name: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_size: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    package_unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_sgd: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    product_url: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
