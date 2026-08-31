from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.repositories.product import ProductSnapshotRepository
from app.schemas.product import ProductSearchResponse
from app.services.product import ProductSearchService, create_product_search_service

router = APIRouter(prefix="/products", tags=["products"])

DatabaseDependency = Annotated[Session, Depends(get_db_session)]


def get_product_search_service(database: DatabaseDependency) -> ProductSearchService:
    return create_product_search_service(ProductSnapshotRepository(database))


ProductSearchServiceDependency = Annotated[
    ProductSearchService,
    Depends(get_product_search_service),
]


@router.get("/search", response_model=ProductSearchResponse)
def search_products(
    service: ProductSearchServiceDependency,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    live: bool = False,
    refresh: bool = False,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> ProductSearchResponse:
    return service.search(q, live=live, refresh=refresh, limit=limit)
