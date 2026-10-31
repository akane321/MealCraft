import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.products.provider import (
    ProductProviderError,
    ProductSchemaDriftError,
    normalize_search_text,
    parse_package_size,
)
from app.schemas.product import ProductResponse

PARSER_VERSION = "redmart-ajax-v1"
REDMART_SELLER_ID = "1000008313"
# Words of Lazada's bot check and login pages (docs/design/redmart.md): such a page is never read as a result.
BLOCK_MARKERS = ("punish", "captcha", "x5sec")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect (a login, a challenge) is a stop, never followed
        return None


_OPENER = build_opener(_NoRedirect)


def urlopen(request: Request, timeout: float):
    return _OPENER.open(request, timeout=timeout)


class RedMartProductProvider:
    """RedMart's products from Lazada Singapore's public search (docs/design/redmart.md).

    One public GET of the search endpoint the site's own front end calls: no login, nothing bypassed. The search
    covers all of Lazada, so only RedMart's own items are kept.
    """

    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, *, limit: int, timeout_seconds: float | None = None) -> list[ProductResponse]:
        normalized_query = normalize_search_text(query)
        slug = quote("-".join(normalized_query.split()), safe="-")
        params = urlencode({"ajax": "true", "q": normalized_query, "page": 1}, quote_via=quote)
        url = f"{self.base_url}/tag/{slug}/?{params}"
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "MealCraft/0.1 academic prototype"},
        )
        try:
            timeout = self.timeout_seconds if timeout_seconds is None else min(self.timeout_seconds, timeout_seconds)
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read().decode("utf-8")
        except HTTPError as error:
            # A redirect is not followed: one to a login page is a stop before that page is fetched.
            location = error.headers.get("Location", "") if error.headers else ""
            if 300 <= error.code < 400 and "login" in urlparse(location).path.lower():
                raise ProductSchemaDriftError("RedMart search was redirected to a login page") from error
            raise ProductProviderError(f"RedMart request failed: {error}") from error
        except (OSError, TimeoutError) as error:
            raise ProductProviderError(f"RedMart request failed: {error}") from error

        return self.parse_page(body, limit=limit)

    def parse_page(self, body: str, *, limit: int) -> list[ProductResponse]:
        """RedMart's products on one search page; anything but the JSON list (a challenge page, say) is schema drift."""
        try:
            data = json.loads(body)
            items = data["mods"]["listItems"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            blocked = any(marker in body.lower() for marker in BLOCK_MARKERS)
            raise ProductSchemaDriftError(
                "RedMart answered with a bot-check page" if blocked else "RedMart page was not the expected JSON"
            ) from error
        if not isinstance(items, list):
            raise ProductSchemaDriftError("RedMart product list was not recognised")

        # An empty page, or one with no RedMart item, is answered and nothing stocked: a no-match.
        fetched_at = datetime.now(UTC)
        records = [item for item in items if isinstance(item, dict) and is_redmart(item)][:limit]
        parsed = [self._parse_product(record, fetched_at) for record in records]
        kept = [product for product in parsed if product is not None]
        if records and not kept:
            raise ProductSchemaDriftError("RedMart products were listed but none had the fields the parser reads")
        return kept

    def _parse_product(self, record: dict, fetched_at: datetime) -> ProductResponse | None:
        try:
            external_id = f"rm-{int(record['itemId'])}"
            name = str(record["name"])
            price = round(float(record["price"]), 2)
            in_stock = record["inStock"]
            item_url = str(record["itemUrl"])
            original = record.get("originalPrice")
            regular = round(float(original), 2) if original not in (None, "") else None
        except (KeyError, TypeError, ValueError):
            return None
        if not isinstance(in_stock, bool):
            return None

        package_size, package_unit = parse_package_size(name)
        image, brand = record.get("image"), record.get("brandName")
        return ProductResponse(
            external_id=external_id,
            name=name,
            brand=brand if isinstance(brand, str) and brand else None,
            category=None,
            package_size=package_size,
            package_unit=package_unit,
            price_sgd=price,
            product_url=f"https:{item_url}" if item_url.startswith("//") else item_url,
            image_url=image if isinstance(image, str) else None,
            in_stock=in_stock,
            source="redmart",
            fetched_at=fetched_at,
            package_text=name,
            regular_price_sgd=regular if regular is not None and regular > price else None,
            # No attribute: "Halal" appears only in some names. Unknown, never True.
            halal_certified=None,
            package_warning=(
                "unknown_package" if package_size is None else "count_package" if package_unit == "whole" else None
            ),
        )


def is_redmart(record: dict) -> bool:
    """RedMart's own item among all of Lazada's: by seller name, seller id or the RedMart badge."""
    return (
        record.get("sellerName") == "RedMart"
        or str(record.get("sellerId")) == REDMART_SELLER_ID
        or any(isinstance(icon, dict) and icon.get("bizType") == "Redmart" for icon in record.get("icons") or ())
    )
