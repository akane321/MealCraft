import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.schemas.product import ProductResponse

NEXT_DATA_PATTERN = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    re.DOTALL,
)
MULTIPACK_PATTERN = re.compile(
    r"(?P<count>\d+)\s*[xX]\s*(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|gm|ml|l|pc|pcs|s)\b",
    re.IGNORECASE,
)
PACKAGE_PATTERN = re.compile(
    r"(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|gm|ml|l|pc|pcs|piece|pieces|s)\b",
    re.IGNORECASE,
)


class ProductProviderError(RuntimeError):
    """Raised when a product provider cannot return a usable result."""


class ProductProvider(Protocol):
    def search(self, query: str, *, limit: int) -> list[ProductResponse]: ...


def normalize_search_text(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def search_tokens(value: str) -> set[str]:
    return {_singular_token(token) for token in value.split()}


def _singular_token(token: str) -> str:
    if token.endswith("oes") and len(token) > 4:
        return token[:-2]
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def parse_package_size(value: str | None) -> tuple[float | None, str | None]:
    if not value:
        return None, None

    multipack = MULTIPACK_PATTERN.search(value)
    if multipack:
        count = float(multipack.group("count"))
        size = float(multipack.group("size")) * count
        return _to_base_unit(size, multipack.group("unit"))

    match = PACKAGE_PATTERN.search(value)
    if not match:
        return None, None
    return _to_base_unit(float(match.group("size")), match.group("unit"))


def _to_base_unit(size: float, unit: str) -> tuple[float, str]:
    normalized = unit.lower()
    if normalized == "kg":
        return size * 1000.0, "g"
    if normalized == "l":
        return size * 1000.0, "ml"
    if normalized in {"g", "gm"}:
        return size, "g"
    if normalized == "ml":
        return size, "ml"
    return size, "whole"


class FixtureProductProvider:
    def __init__(self, fixture_path: str) -> None:
        self.fixture_path = Path(fixture_path)

    def search(self, query: str, *, limit: int) -> list[ProductResponse]:
        normalized_query = normalize_search_text(query)
        query_key = normalized_query.replace(" ", "_")
        try:
            records = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProductProviderError(f"Fixture products could not be loaded: {error}") from error

        ranked: list[tuple[int, dict]] = []
        query_tokens = search_tokens(normalized_query)
        for record in records:
            ingredient_keys = set(record.get("ingredient_keys", []))
            name = normalize_search_text(record["name"])
            name_tokens = search_tokens(name)
            if query_key in ingredient_keys:
                score = 100
            elif query_tokens and query_tokens.issubset(name_tokens):
                score = 80
            elif normalized_query in name:
                score = 60
            else:
                continue
            ranked.append((score, record))

        ranked.sort(key=lambda item: (-item[0], float(item[1]["price_sgd"]), item[1]["external_id"]))
        fetched_at = datetime.now(UTC)
        return [
            ProductResponse(
                external_id=record["external_id"],
                name=record["name"],
                brand=record.get("brand"),
                category=record.get("category"),
                package_size=record.get("package_size"),
                package_unit=record.get("package_unit"),
                price_sgd=record["price_sgd"],
                product_url=record["product_url"],
                image_url=record.get("image_url"),
                in_stock=record.get("in_stock", True),
                source="fixture",
                fetched_at=fetched_at,
            )
            for _, record in ranked[:limit]
        ]


class FairPriceProductProvider:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, limit: int) -> list[ProductResponse]:
        normalized_query = normalize_search_text(query)
        url = f"{self.base_url}/product-listing?{urlencode({'pageType': 'search', 'url': normalized_query})}"
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "MealCraft/0.1 academic prototype",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                html = response.read().decode("utf-8")
        except (OSError, TimeoutError) as error:
            raise ProductProviderError(f"FairPrice request failed: {error}") from error

        match = NEXT_DATA_PATTERN.search(html)
        if match is None:
            raise ProductProviderError("FairPrice page did not include __NEXT_DATA__ product data")

        try:
            payload = json.loads(match.group(1))
            products = payload["props"]["pageProps"]["data"]["data"]["product"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ProductProviderError("FairPrice product data structure was not recognised") from error

        fetched_at = datetime.now(UTC)
        parsed = [self._parse_product(product, fetched_at) for product in products[:limit]]
        return [product for product in parsed if product is not None]

    def _parse_product(self, record: dict, fetched_at: datetime) -> ProductResponse | None:
        try:
            price = float(record["final_price"])
            external_id = str(record.get("clientItemId") or record["id"])
            name = str(record["name"])
            slug = str(record["slug"])
        except (KeyError, TypeError, ValueError):
            return None

        metadata = record.get("metaData") or {}
        package_size, package_unit = parse_package_size(
            metadata.get("DisplayUnit") or metadata.get("Unit Of Weight") or name
        )
        brand_record = record.get("brand") or {}
        category_record = record.get("primaryCategory") or {}
        images = record.get("images") or []
        image_url = images[0] if images and isinstance(images[0], str) else None
        if images and isinstance(images[0], dict):
            image_url = images[0].get("url") or images[0].get("image")

        return ProductResponse(
            external_id=external_id,
            name=name,
            brand=brand_record.get("name"),
            category=category_record.get("name"),
            package_size=package_size,
            package_unit=package_unit,
            price_sgd=price,
            product_url=f"{self.base_url}/product/{slug}",
            image_url=image_url,
            in_stock=bool(record.get("has_stock", True)),
            source="fairprice",
            fetched_at=fetched_at,
        )
