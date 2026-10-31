import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from app.core.paths import repository_root
from app.products.provider import ProductProviderError, ProductSchemaDriftError
from app.products.redmart import RedMartProductProvider

PAGES = repository_root() / "data/fixtures/redmart-pages"


def provider() -> RedMartProductProvider:
    return RedMartProductProvider(base_url="https://www.lazada.sg/", timeout_seconds=5)


def page(name: str) -> str:
    return (PAGES / name).read_text(encoding="utf-8")


def listing(*items: dict) -> str:
    return json.dumps({"mods": {"listItems": list(items)}})


def item(**fields) -> dict:
    base = {
        "itemId": "100",
        "name": "Rice 1kg",
        "price": "3.2",
        "inStock": True,
        "sellerName": "RedMart",
        "sellerId": "1000008313",
        "itemUrl": "//www.lazada.sg/products/pdp-i100.html",
    }
    return {**base, **fields}


def test_an_ordinary_page_keeps_only_redmarts_own_items() -> None:
    products = provider().parse_page(page("ordinary.json"), limit=10)

    # The third-party seller's item is ignored; the item with only RedMart's seller id is kept.
    assert [product.external_id for product in products] == [
        "rm-3124212075",
        "rm-2932350459",
        "rm-3434791625",
        "rm-9000000002",
    ]
    assert all(product.source == "redmart" for product in products)
    assert products[2].regular_price_sgd == 35.9
    assert (products[3].package_size, products[3].package_unit, products[3].in_stock) == (50, "g", False)
    first = products[0]
    assert (first.name, first.brand, first.price_sgd, first.in_stock) == (
        "Harras Turkish Allspice Pimento",
        "Harras",
        12.5,
        True,
    )
    assert first.product_url == "https://www.lazada.sg/products/pdp-i3124212075.html"
    assert first.halal_certified is None
    assert first.package_warning == "unknown_package"


def test_the_seller_name_the_seller_id_or_the_badge_each_make_an_item_redmarts() -> None:
    by_name = item(itemId="1", sellerId="9")
    by_id = item(itemId="2", sellerName="", sellerId=1000008313)
    by_badge = item(itemId="3", sellerName="Other", sellerId="9", icons=[{"bizType": "Redmart"}])
    other = item(itemId="4", sellerName="Other", sellerId="9", icons=[{"bizType": "Choice"}])

    products = provider().parse_page(listing(by_name, by_id, by_badge, other), limit=10)

    assert [product.external_id for product in products] == ["rm-1", "rm-2", "rm-3"]


def test_a_promotion_keeps_the_shelf_price_and_the_size_comes_from_the_name() -> None:
    discounted = item(itemId="5", name="Olive Oil 500ml", price="26.92", originalPrice="35.9")

    sized, plain = provider().parse_page(listing(discounted, item(itemId="6", originalPrice="")), limit=10)

    assert (sized.price_sgd, sized.regular_price_sgd) == (26.92, 35.9)
    assert (sized.package_size, sized.package_unit, sized.package_warning) == (500, "ml", None)
    assert (plain.regular_price_sgd, plain.package_size, plain.package_unit) == (None, 1000, "g")


def test_a_name_with_a_count_is_flagged_and_one_without_a_size_is_unknown() -> None:
    counted, unsized = provider().parse_page(
        listing(item(itemId="7", name="Eggs 10s"), item(itemId="8", name="Fresh Dill")), limit=10
    )

    assert counted.package_warning == "count_package"
    assert (unsized.package_size, unsized.package_warning) == (None, "unknown_package")


def test_halal_in_a_name_is_never_trusted() -> None:
    (product,) = provider().parse_page(listing(item(name="Chicken Breast 500g (Halal)")), limit=10)

    assert product.halal_certified is None


def test_the_limit_applies_to_redmarts_items() -> None:
    items = [item(itemId=str(number)) for number in range(5)]

    assert len(provider().parse_page(listing(*items), limit=2)) == 2


@pytest.mark.parametrize(
    "body",
    [
        page("empty.json"),
        listing(item(sellerName="Other", sellerId="9")),
    ],
    ids=["empty list", "no RedMart item on the page"],
)
def test_an_answered_page_with_no_redmart_item_is_a_no_match_not_a_failure(body: str) -> None:
    assert provider().parse_page(body, limit=10) == []


@pytest.mark.parametrize(
    "body",
    [
        page("challenge.html"),
        page("schema-drift.json"),
        "",
        "<html>login</html>",
        '{"mods": {}}',
        '{"mods": {"listItems": 3}}',
    ],
    ids=["challenge page", "no mods.listItems", "empty body", "login html", "no listItems", "listItems not a list"],
)
def test_anything_but_the_json_list_is_schema_drift(body: str) -> None:
    with pytest.raises(ProductSchemaDriftError):
        provider().parse_page(body, limit=10)


@pytest.mark.parametrize("marker", ["punish", "captcha", "x5sec"])
def test_a_page_carrying_a_bot_check_marker_is_called_a_bot_check(marker: str) -> None:
    with pytest.raises(ProductSchemaDriftError, match="bot-check"):
        provider().parse_page(f"<html>{marker}</html>", limit=10)


def test_items_that_cannot_be_read_are_schema_drift_too() -> None:
    with pytest.raises(ProductSchemaDriftError):
        provider().parse_page(listing({**item(), "price": "free"}, {**item(), "inStock": "yes"}), limit=10)
    kept = provider().parse_page(listing({"sellerName": "RedMart"}, item(itemId="9")), limit=10)
    assert [product.external_id for product in kept] == ["rm-9"]


class Response:
    def __init__(self, body: str, url: str = "https://www.lazada.sg/tag/x/") -> None:
        self.body, self.url = body, url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body.encode()

    def geturl(self):
        return self.url


def test_search_asks_for_the_ajax_endpoint_with_the_apps_own_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"], seen["agent"], seen["timeout"] = request.full_url, request.get_header("User-agent"), timeout
        return Response(page("empty.json"))

    monkeypatch.setattr("app.products.redmart.urlopen", fake_urlopen)

    assert provider().search("Vegetable_Broth", limit=5, timeout_seconds=2) == []
    assert seen == {
        "url": "https://www.lazada.sg/tag/vegetable-broth/?ajax=true&q=vegetable%20broth&page=1",
        "agent": "MealCraft/0.1 academic prototype",
        "timeout": 2,
    }


def test_a_non_200_answer_is_an_unavailable_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", Message(), None)

    monkeypatch.setattr("app.products.redmart.urlopen", refuse)

    with pytest.raises(ProductProviderError) as error:
        provider().search("buttermilk", limit=5)
    assert error.value.kind == "unavailable"


def redirect(location: str):
    def answer(request, timeout):
        headers = Message()
        headers["Location"] = location
        raise HTTPError(request.full_url, 302, "Found", headers, None)

    return answer


def test_a_redirect_to_a_login_is_schema_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.products.redmart.urlopen", redirect("https://member.lazada.sg/user/login?x=1"))

    with pytest.raises(ProductSchemaDriftError):
        provider().search("buttermilk", limit=5)


def test_a_login_word_only_in_the_query_is_not_a_login_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.products.redmart.urlopen", redirect("https://www.lazada.sg/tag/x/?q=login"))

    with pytest.raises(ProductProviderError) as error:
        provider().search("buttermilk", limit=5)
    assert error.value.kind == "unavailable"


def test_the_opener_never_follows_a_redirect() -> None:
    from urllib.request import Request

    from app.products.redmart import _NoRedirect

    request = Request("https://www.lazada.sg/x")
    assert _NoRedirect().redirect_request(request, None, 302, "Found", {}, "https://member.lazada.sg/login") is None
