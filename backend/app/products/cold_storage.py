import json
import re
from datetime import UTC, datetime
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.products.provider import (
    ProductProviderError,
    ProductSchemaDriftError,
    normalize_search_text,
    parse_package_size,
)
from app.schemas.product import ProductResponse

PARSER_VERSION = "cold-storage-flight-v1"
# The React flight payload of the Next.js page: one string per push, joined (docs/design/cold-storage.md). Pushes
# may share a script tag, so nothing is required after the call (as in the capture script).
FLIGHT_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.DOTALL)
PRODUCTS_KEY = '"initialProducts":'
NO_RESULTS_TEXT = "Sorry, we couldn't find any results for"


class ColdStorageProductProvider:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, limit: int, timeout_seconds: float | None = None) -> list[ProductResponse]:
        normalized_query = normalize_search_text(query)
        url = f"{self.base_url}/search?{urlencode({'q': normalized_query}, quote_via=quote)}"
        request = Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "MealCraft/0.1 academic prototype",
            },
        )
        try:
            timeout = self.timeout_seconds if timeout_seconds is None else min(self.timeout_seconds, timeout_seconds)
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                html = response.read().decode("utf-8")
        except (OSError, TimeoutError) as error:
            raise ProductProviderError(f"Cold Storage request failed: {error}") from error

        return self.parse_page(html, limit=limit)

    def parse_page(self, html: str, *, limit: int) -> list[ProductResponse]:
        """The products on one Cold Storage search page; a page of an unknown shape is schema drift."""
        try:
            flight = "".join(json.loads(chunk) for chunk in FLIGHT_PATTERN.findall(html))
        except json.JSONDecodeError as error:
            raise ProductSchemaDriftError("Cold Storage page payload was not recognised") from error
        start = flight.find(PRODUCTS_KEY)
        if start < 0:
            # A search with no results has no product list but says so in the page: answered, nothing stocked.
            if NO_RESULTS_TEXT in html.replace("&#x27;", "'"):
                return []
            raise ProductSchemaDriftError("Cold Storage page did not include its product list")
        try:
            products, _ = json.JSONDecoder().raw_decode(flight[start + len(PRODUCTS_KEY) :])
        except json.JSONDecodeError as error:
            raise ProductSchemaDriftError("Cold Storage product list could not be read") from error
        if not isinstance(products, list):
            raise ProductSchemaDriftError("Cold Storage product data structure was not recognised")

        fetched_at = datetime.now(UTC)
        parsed = [self._parse_product(product, fetched_at) for product in products[:limit]]
        kept = [product for product in parsed if product is not None]
        if products[:limit] and not kept:
            raise ProductSchemaDriftError("Cold Storage products were listed but none had the fields the parser reads")
        return kept

    def _parse_product(self, record: dict, fetched_at: datetime) -> ProductResponse | None:
        try:
            external_id = f"cs-{int(record['productId'])}"
            name = str(record["name"])
            slug = str(record["slug"])
            regular = float(record["price"])
            price = float(record["promoPrice"]) if record.get("promoPrice") is not None else regular
            weight = float(record["averageWeight"]) if record.get("averageWeight") is not None else None
            in_stock = record["inventoryStatus"] == "In Stock"
        except (KeyError, TypeError, ValueError):
            return None

        if weight:
            # Sold by weight: both prices are per kg, and the pack the shopper gets weighs `averageWeight` kg.
            price, regular = round(price * weight, 2), round(regular * weight, 2)
            package_size, package_unit = parse_package_size(f"{weight}kg")
            package_size = round(package_size, 3) if package_size is not None else None
        else:
            price, regular = round(price, 2), round(regular, 2)
            package_size, package_unit = parse_package_size(name)
        image = record.get("image")

        return ProductResponse(
            external_id=external_id,
            name=name,
            brand=None,
            category=None,
            package_size=package_size,
            package_unit=package_unit,
            price_sgd=price,
            product_url=f"{self.base_url}/product/{slug}",
            image_url=image if isinstance(image, str) else None,
            in_stock=in_stock,
            source="cold_storage",
            fetched_at=fetched_at,
            package_text=name,
            regular_price_sgd=regular if regular > price else None,
            # The listing's isHalal was false on every sampled product, "(Halal)" ones included: unknown, never True.
            halal_certified=None,
            package_warning=(
                "unknown_package" if package_size is None else "count_package" if package_unit == "whole" else None
            ),
        )
