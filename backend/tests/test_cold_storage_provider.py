import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from app.core.paths import repository_root
from app.products.cold_storage import ColdStorageProductProvider
from app.products.provider import ProductProviderError, ProductSchemaDriftError

PAGES = repository_root() / "data/fixtures/coldstorage-pages"


def provider() -> ColdStorageProductProvider:
    return ColdStorageProductProvider(base_url="https://coldstorage.com.sg/", timeout_seconds=5)


def page(name: str) -> str:
    return (PAGES / f"{name}.html").read_text(encoding="utf-8")


def flight_page(products: list) -> str:
    flight = '1b:["$","$L1c",null,{"initialProducts":' + json.dumps(products) + ',"query":"x"}]\n'
    return f"<main></main><script>self.__next_f.push([1,{json.dumps(flight)}])</script>"


def test_an_ordinary_page_is_read_from_the_flight_payload() -> None:
    products = provider().parse_page(page("ordinary"), limit=10)

    assert [product.external_id for product in products] == [
        "cs-124005",
        "cs-78715",
        "cs-75868",
        "cs-7597461",
        "cs-214877",
    ]
    pancake_mix, buttermilk, promotion, drink, waffles = products
    assert pancake_mix.name == "Bob's Red Mill Whole Grain Buttermilk Pancake Mix 24oz (680g)"
    assert (pancake_mix.package_size, pancake_mix.package_unit) == (680.0, "g")
    assert (buttermilk.package_size, buttermilk.package_unit, buttermilk.price_sgd) == (600.0, "ml", 6.05)
    assert buttermilk.product_url == "https://coldstorage.com.sg/product/dairy-farmers-buttermilk-600ml"
    assert buttermilk.image_url and buttermilk.image_url.startswith("https://mcos.coldstorage.com.sg/")
    assert [product.in_stock for product in products] == [True, True, True, False, False]
    assert all(product.source == "cold_storage" for product in products)
    # The site's isHalal flag is not trusted: unknown, never True and never False.
    assert all(product.halal_certified is None for product in products)
    assert all(
        product.brand is None and product.category is None and product.cart_item_id is None for product in products
    )


def test_a_promotion_is_the_price_and_the_shelf_price_is_kept() -> None:
    promotion = provider().parse_page(page("ordinary"), limit=10)[2]

    assert (promotion.price_sgd, promotion.regular_price_sgd) == (6.05, 7.1)
    assert provider().parse_page(page("ordinary"), limit=10)[1].regular_price_sgd is None


def test_a_weighted_item_is_priced_per_pack_not_per_kilo() -> None:
    salmon, smoked = provider().parse_page(page("weighted"), limit=2)

    assert salmon.external_id == "cs-33396387"
    assert salmon.price_sgd == 18.02  # 42.90 a kilo x 0.420 kg
    assert salmon.regular_price_sgd == 20.96  # 49.90 a kilo x 0.420 kg
    assert (salmon.package_size, salmon.package_unit) == (420.0, "g")
    assert (smoked.price_sgd, smoked.package_size) == (10.2, 85.0)  # not weighted: the listed price as it is


def test_the_limit_applies() -> None:
    assert len(provider().parse_page(page("ordinary"), limit=2)) == 2


def test_no_results_is_an_empty_list_not_a_failure() -> None:
    assert provider().parse_page(page("empty"), limit=10) == []


def test_a_page_with_neither_products_nor_the_no_results_text_is_schema_drift() -> None:
    with pytest.raises(ProductSchemaDriftError) as error:
        provider().parse_page(page("schema-drift"), limit=10)
    assert error.value.kind == "schema_drift"


def test_products_that_cannot_be_read_are_schema_drift_too() -> None:
    with pytest.raises(ProductSchemaDriftError):
        provider().parse_page(flight_page([{"id": 1, "title": "moved fields"}]), limit=10)
    # One unreadable record among readable ones is skipped, not fatal.
    rice = {
        "productId": 1,
        "name": "Rice 1kg",
        "slug": "rice",
        "price": 3,
        "promoPrice": 3,
        "inventoryStatus": "In Stock",
    }
    kept = provider().parse_page(flight_page([{"bad": True}, rice]), limit=10)
    assert [product.external_id for product in kept] == ["cs-1"]


def test_search_asks_for_the_search_page_with_the_apps_own_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return page("empty").encode()

    def fake_urlopen(request, timeout):
        seen["url"], seen["agent"], seen["timeout"] = request.full_url, request.get_header("User-agent"), timeout
        return Response()

    monkeypatch.setattr("app.products.cold_storage.urlopen", fake_urlopen)

    assert provider().search("Vegetable_Broth", limit=5, timeout_seconds=2) == []
    assert seen == {
        "url": "https://coldstorage.com.sg/search?q=vegetable%20broth",
        "agent": "MealCraft/0.1 academic prototype",
        "timeout": 2,
    }


def test_a_non_200_answer_is_an_unavailable_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(request, timeout):
        raise HTTPError(request.full_url, 429, "Too Many Requests", Message(), None)

    monkeypatch.setattr("app.products.cold_storage.urlopen", refuse)

    with pytest.raises(ProductProviderError) as error:
        provider().search("buttermilk", limit=5)
    assert error.value.kind == "unavailable"


def test_a_raw_page_with_pushes_sharing_a_script_tag_is_read() -> None:
    """The live shape: several pushes in one script, separated by `;` or newlines, a bootstrap push that is not
    a flight string, and no `</script>` right after a push (the capture script reads these pages the same way)."""
    rice = {
        "productId": 7,
        "name": "Rice 1kg",
        "slug": "rice-1kg",
        "price": 3.2,
        "promoPrice": 3.2,
        "inventoryStatus": "In Stock",
    }
    flight = '1b:["$","$L1c",null,{"initialProducts":' + json.dumps([rice]) + ',"query":"rice"}]\n'
    cut = len(flight) // 2  # the product list is split across two pushes
    first, second = json.dumps(flight[:cut]), json.dumps(flight[cut:])
    raw = (
        '<!DOCTYPE html><html><head><script src="/_next/static/chunks/main.js" async=""></script></head><body>'
        "<script>(self.__next_f=self.__next_f||[]).push([0])</script>\n"
        f'<script nonce="x">self.__next_f.push([1,{first}]);\nself.__next_f.push([1,{second}])\n</script>'
        '<script>self.__next_f.push([2,"not a flight string"])</script></body></html>'
    )

    products = provider().parse_page(raw, limit=10)

    assert [(product.external_id, product.price_sgd) for product in products] == [("cs-7", 3.2)]
