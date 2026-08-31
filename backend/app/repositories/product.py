from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.product import ProductSnapshot
from app.schemas.product import ProductResponse


class ProductSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_fresh(
        self,
        *,
        source: str,
        search_query: str,
        fetched_after: datetime,
        limit: int,
    ) -> list[ProductResponse]:
        statement = (
            select(ProductSnapshot)
            .where(
                ProductSnapshot.source == source,
                ProductSnapshot.search_query == search_query,
                ProductSnapshot.fetched_at >= fetched_after,
            )
            .order_by(ProductSnapshot.rank)
            .limit(limit)
        )
        snapshots = self.session.scalars(statement).all()
        return [self._to_response(snapshot) for snapshot in snapshots]

    def replace_query_results(
        self,
        *,
        source: str,
        search_query: str,
        products: list[ProductResponse],
    ) -> None:
        if not products:
            return

        values = [
            {
                "source": source,
                "search_query": search_query,
                "external_id": product.external_id,
                "rank": rank,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "package_size": product.package_size,
                "package_unit": product.package_unit,
                "price_sgd": product.price_sgd,
                "product_url": product.product_url,
                "image_url": product.image_url,
                "in_stock": product.in_stock,
                "fetched_at": product.fetched_at,
                "raw_data": {},
            }
            for rank, product in enumerate(products)
        ]
        dialect_name = self.session.bind.dialect.name if self.session.bind is not None else ""
        index_elements = ["source", "search_query", "external_id"]

        if dialect_name == "postgresql":
            statement = postgresql_insert(ProductSnapshot).values(values)
            updates = {key: getattr(statement.excluded, key) for key in values[0] if key not in index_elements}
            self.session.execute(statement.on_conflict_do_update(index_elements=index_elements, set_=updates))
        elif dialect_name == "sqlite":
            statement = sqlite_insert(ProductSnapshot).values(values)
            updates = {key: getattr(statement.excluded, key) for key in values[0] if key not in index_elements}
            self.session.execute(statement.on_conflict_do_update(index_elements=index_elements, set_=updates))
        else:
            self.session.execute(
                delete(ProductSnapshot).where(
                    ProductSnapshot.source == source,
                    ProductSnapshot.search_query == search_query,
                )
            )
            self.session.add_all(ProductSnapshot(**value) for value in values)
        self.session.commit()

    @staticmethod
    def _to_response(snapshot: ProductSnapshot) -> ProductResponse:
        return ProductResponse(
            external_id=snapshot.external_id,
            name=snapshot.name,
            brand=snapshot.brand,
            category=snapshot.category,
            package_size=float(snapshot.package_size) if snapshot.package_size is not None else None,
            package_unit=snapshot.package_unit,
            price_sgd=float(snapshot.price_sgd),
            product_url=snapshot.product_url,
            image_url=snapshot.image_url,
            in_stock=snapshot.in_stock,
            source=snapshot.source,
            fetched_at=snapshot.fetched_at,
        )
