"""Confirmed baskets observe selected SKUs, with a bounded wait and honest fallback."""

from datetime import UTC, datetime, timedelta
from threading import Event, Lock, get_ident
from time import monotonic, sleep
from types import SimpleNamespace

import pytest

from app.data import halal as halal_data
from app.models.meal_plan import MealPlan
from app.planning import grocery_estimator
from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.products.provider import ProductProviderError, ProductSchemaDriftError
from app.repositories.meal_plan import MealPlanRepository
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse, WeeklyMealPlanRequest
from app.schemas.product import GroceryLineEstimate, PriceEvidence, ProductResponse
from app.services import product as prices
from app.services.fairprice_cart import FairPriceCartService
from app.services.product import ProductSearchService


def line(index=0):
    observed = datetime.now(UTC) - timedelta(days=2)
    product = ProductResponse(
        external_id=str(10000 + index),
        name=f"Reviewed product {index}",
        brand=None,
        category=None,
        package_size=500,
        package_unit="g",
        price_sgd=2,
        product_url=f"https://www.fairprice.com.sg/product/{10000 + index}",
        image_url=None,
        in_stock=True,
        source="fairprice",
        fetched_at=observed,
    )
    return GroceryLineEstimate(
        ingredient_name=f"food{index}",
        ingredient_display_name=f"food{index}",
        required_quantity=600,
        unit="g",
        pantry_deduction=0,
        remaining_quantity=600,
        product=product,
        match_score=1,
        packages_required=2,
        purchase_cost_sgd=4,
        consumed_cost_sgd=2.4,
        excess_quantity=400,
        note=None,
        evidence=PriceEvidence(
            fact_id=f"{product.external_id}@{observed.isoformat()}",
            source="release_snapshot",
            mode="snapshot",
            query=f"food{index}",
            parser_version="release",
            fetched_at=observed,
        ),
    )


def observed(item, **updates):
    return item.product.model_copy(update={"price_sgd": 3, "fetched_at": datetime.now(UTC), **updates})


class Repository:
    def __init__(self, cached=None):
        self.cached = cached or {}
        self.writes = []
        self.owner = get_ident()

    def get_fresh(self, *, search_query, **kwargs):
        assert get_ident() == self.owner
        return self.cached.get(search_query, [])

    def replace_query_results(self, **kwargs):
        assert get_ident() == self.owner
        self.writes.append(kwargs)


class Provider:
    def __init__(self, respond):
        self.respond = respond
        self.calls = []

    def search(self, query, *, limit, timeout_seconds):
        assert limit == 20
        assert 0 < timeout_seconds <= 10  # a lookup never outwaits the basket (FINAL_PRICE_SECONDS)
        self.calls.append(query)
        return self.respond(query)


def service(provider, repository=None):
    return ProductSearchService(
        fixture_provider=None, live_provider=provider, repository=repository or Repository(), cache_ttl_minutes=15
    )


def test_concurrent_selected_only_prices_preserve_packaging_and_input():
    originals = [line(i) for i in range(34)]
    active = peak = 0
    lock = Lock()

    def respond(query):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.025)
        with lock:
            active -= 1
        item = originals[int(query.removeprefix("food"))]
        return [observed(item, package_size=999), observed(item, external_id="cheaper-other", price_sgd=1)]

    provider, repository = Provider(respond), Repository()
    refreshed = service(provider, repository).refresh_selected(originals)
    assert 1 < peak <= 8
    assert len(provider.calls) == 34
    assert all(item.product.price_sgd == 3 and item.product.package_size == 500 for item in refreshed)
    assert all(item.product.price_sgd == 2 and item.evidence.checked_at is None for item in originals)
    assert all(item.evidence.price_source == "live" and item.evidence.lookup_status == "success" for item in refreshed)
    assert all(item.packages_required == 2 and item.required_quantity == 600 for item in refreshed)
    assert all(write["commit"] is False and len(write["products"]) == 1 for write in repository.writes)
    assert all(write["products"][0].external_id != "cheaper-other" for write in repository.writes)


def test_deadline_returns_snapshot_and_late_results_never_mutate_or_cache(monkeypatch):
    monkeypatch.setattr(prices, "FINAL_PRICE_SECONDS", 0.08)
    release, all_started, all_finished = Event(), Event(), Event()
    started = finished = 0
    lock = Lock()
    original = line()

    def respond(query):
        nonlocal started, finished
        with lock:
            started += 1
            if started == 8:
                all_started.set()
        assert release.wait(2)
        with lock:
            finished += 1
            if finished == 8:
                all_finished.set()
        return [observed(original)]

    repository = Repository()
    engine = service(Provider(respond), repository)
    try:
        begin = monotonic()
        result = engine.refresh_selected([line(i) for i in range(12)])
        assert monotonic() - begin < 0.4
        assert all_started.is_set()
        second = engine.refresh_selected([line(i) for i in range(12)])
        assert started == 8  # overlapping requests still share the eight-worker ceiling
        assert all(item.evidence.lookup_status == "timeout" for item in result + second)
        assert all(item.product.price_sgd == 2 for item in result + second)
    finally:
        release.set()
    assert all_finished.wait(1)
    assert not repository.writes
    assert all(item.product.price_sgd == 2 for item in result + second)


def test_fresh_cache_retains_observation_time_without_network():
    original = line()
    cached = observed(original, cart_item_id="9001")
    provider = Provider(lambda query: pytest.fail("fresh selected SKU should not use network"))
    result = service(provider, Repository({"food0": [cached]})).refresh_selected([original])[0]
    assert result.evidence.price_source == "cache"
    assert result.evidence.fetched_at == cached.fetched_at
    assert result.evidence.checked_at >= cached.fetched_at
    assert result.product.price_sgd == 3
    assert not provider.calls


def test_cached_row_without_cart_id_is_a_miss_and_the_live_fetch_fills_it():
    original = line()
    provider = Provider(lambda query: [observed(original, price_sgd=4, cart_item_id="9001")])
    result = service(provider, Repository({"food0": [observed(original)]})).refresh_selected([original])[0]
    assert result.evidence.price_source == "live" and provider.calls
    assert (result.product.price_sgd, result.product.cart_item_id) == (4, "9001")


@pytest.mark.parametrize("response", [[], [observed(line(), external_id="another-sku")]])
def test_missing_selected_id_is_not_a_timeout_or_stock_assertion(response):
    original = line()
    result = service(Provider(lambda query: response)).refresh_selected([original])[0]
    assert result.evidence.lookup_status == "selected_product_not_returned"
    assert result.evidence.price_source == "snapshot"
    assert result.evidence.mode == "snapshot" and result.evidence.source == "release_snapshot"
    assert result.evidence.fetched_at == original.evidence.fetched_at
    assert result.evidence.checked_at is not None
    assert result.product == original.product


def test_fake_id_has_distinct_source_and_no_lookup_time():
    original = line()
    original.product.external_id = "fixture-cucumber-500g"
    provider = Provider(lambda query: pytest.fail("fake ID must never be queried"))
    result = service(provider).refresh_selected([original])[0]
    assert result.evidence.price_source == "no_external_product"
    assert result.evidence.lookup_status == "no_external_id"
    assert result.evidence.checked_at is None
    assert result.product.price_sgd == 2


@pytest.mark.parametrize(
    "failure,status",
    [(ProductProviderError("offline"), "provider_error"), (ProductSchemaDriftError("changed"), "schema_drift")],
)
def test_provider_failure_keeps_original_snapshot(failure, status):
    def respond(query):
        raise failure

    original = line()
    result = service(Provider(respond)).refresh_selected([original])[0]
    assert result.product == original.product
    assert result.evidence.lookup_status == status
    assert result.evidence.price_source == "snapshot"


@pytest.mark.parametrize("price", [float("inf"), float("nan"), -1, 2.345, 1e100])
def test_invalid_prices_are_not_cached_or_applied(price):
    original, repository = line(), Repository()
    result = service(Provider(lambda query: [observed(original, price_sgd=price)]), repository).refresh_selected(
        [original]
    )[0]
    assert result.product.price_sgd == 2
    assert result.evidence.lookup_status == "invalid_price"
    assert not repository.writes


def test_aggregator_reports_overrun_but_never_reselects_packages():
    original = line()
    grocery = WeeklyGroceryEstimateResponse(
        pricing_mode="fixture",
        complete=True,
        purchase_total_sgd=4,
        consumed_total_sgd=2.4,
        weekly_budget_sgd=5,
        within_weekly_budget=True,
        items=[original],
        unmapped_ingredients=[],
        warnings=[],
    )
    refreshed = WeeklyGroceryAggregator(service(Provider(lambda query: [observed(original)]))).refresh(
        grocery, WeeklyMealPlanRequest()
    )
    assert refreshed.purchase_total_sgd == 6
    assert refreshed.within_weekly_budget is False
    assert refreshed.items[0].packages_required == 2
    assert refreshed.items[0].product.external_id == original.product.external_id
    assert any("by S$1.00" in warning for warning in refreshed.warnings)
    assert grocery.purchase_total_sgd == 4


@pytest.mark.parametrize("event_type", ["CANCEL_MEAL", "REPLACE_MEAL", "CHANGE_SHAPE", "LOCK_MEAL"])
def test_generation_persists_prices_and_preview_only_refreshes_when_confirmed(monkeypatch, event_type):
    from app.products.provider import FairPriceProductProvider
    from app.repositories.product import ProductSnapshotRepository
    from tests.test_planning_capability import dish_client
    from tests.test_wp1_snapshot_planning import dishes

    calls = []
    price = 50
    selected = {}
    refresh = ProductSearchService.refresh_selected

    def refresh_synthetic(self, lines, find_replacement=None):
        # Assign real-ID-shaped synthetic SKUs without changing candidate selection.
        for index, item in enumerate(lines):
            if item.product:
                item.product = item.product.model_copy(update={"external_id": str(10000 + index)})
                selected[item.evidence.query] = item.product
        return refresh(self, lines, find_replacement)

    def search(self, query, *, limit, timeout_seconds):
        calls.append(query)
        return [
            selected[query].model_copy(
                update={"price_sgd": price, "source": "fairprice", "fetched_at": datetime.now(UTC)}
            )
        ]

    # No real site, paid model, or persistent database is involved.
    monkeypatch.setattr(ProductSearchService, "refresh_selected", refresh_synthetic)
    monkeypatch.setattr(FairPriceProductProvider, "search", search)
    monkeypatch.setattr(ProductSnapshotRepository, "get_fresh", lambda *args, **kwargs: [])
    with dish_client(monkeypatch, dishes()) as client:
        response = client.post(
            "/api/plans/generate",
            json={"requires_halal": False, **{"household_size": 2, "weekly_budget_sgd": 100, "pricing_mode": "live"}},
        )
        assert response.status_code == 201, response.text
        plan = response.json()
        grocery = plan["grocery_estimate"]
        assert not any("select live pricing" in warning for warning in plan["warnings"])
        assert grocery["within_weekly_budget"] is False
        assert all(item["evidence"]["price_source"] == "live" for item in grocery["items"])
        stored = client.get(f"/api/plans/{plan['id']}").json()
        assert stored["grocery_estimate"] == grocery
        before = len(calls)
        if event_type == "CHANGE_SHAPE":
            preview = client.post(
                f"/api/plans/{plan['id']}/shape/preview",
                json={"meal_type": "lunch", "roles": [{"role_id": "main", "courses": ["main"]}]},
            )
        else:
            preview = client.post(
                f"/api/plans/{plan['id']}/replan/preview",
                json={"entry_id": plan["days"][0]["entry_id"], "event_type": event_type},
            )
        assert preview.status_code == 201, preview.text
        assert len(calls) == before
        price = 80
        event = preview.json()
        confirmed = client.post(f"/api/plans/{plan['id']}/replan/{event['id']}/confirm")
        assert confirmed.status_code == 200, confirmed.text
        final = confirmed.json()["plan"]["grocery_estimate"]
        if event_type == "LOCK_MEAL":
            assert len(calls) == before
            assert final == grocery
        else:
            assert len(calls) > before
            assert all(item["product"]["price_sgd"] == 80 for item in final["items"])
            assert confirmed.json()["event"]["purchase_total_delta_sgd"] == pytest.approx(
                final["purchase_total_sgd"] - grocery["purchase_total_sgd"]
            )
        before = len(calls)
        assert client.post(f"/api/plans/{plan['id']}/replan/{event['id']}/confirm").status_code == 409
        assert len(calls) == before


def test_cache_of_other_sku_does_not_prevent_selected_product_lookup():
    original = line()
    provider = Provider(lambda query: [observed(original)])
    repository = Repository({"food0": [observed(original, external_id="other")]})
    result = service(provider, repository).refresh_selected([original])[0]
    assert provider.calls == ["food0"]
    assert result.evidence.price_source == "live"


def test_known_out_of_stock_price_is_not_a_claim_of_availability():
    original = line()
    result = service(Provider(lambda query: [observed(original, in_stock=False)])).refresh_selected([original])[0]
    assert result.product.price_sgd == 3 and result.product.in_stock is False
    assert result.evidence.lookup_status == "out_of_stock"


def test_failed_refresh_preserves_existing_rounded_costs():
    original = line()
    original.consumed_cost_sgd = 2.39  # rounding from the unrounded ingredient quantity
    grocery = WeeklyGroceryEstimateResponse(
        pricing_mode="live",
        complete=True,
        purchase_total_sgd=4,
        consumed_total_sgd=2.39,
        weekly_budget_sgd=5,
        within_weekly_budget=True,
        items=[original],
        unmapped_ingredients=[],
        warnings=[],
    )
    result = WeeklyGroceryAggregator(service(Provider(lambda query: []))).refresh(grocery, WeeklyMealPlanRequest())
    assert result.consumed_total_sgd == 2.39
    assert result.purchase_total_sgd == 4


def test_a_basket_waits_ten_seconds_for_its_final_prices():
    """Task 15 item 7: 3 s gave a slow retailer site too little time, and the household its snapshot prices. The
    lookup bound above only checks the upper limit, so a return to 3 s would pass it."""
    assert prices.FINAL_PRICE_SECONDS == 10.0


# A saved line FairPrice could not confirm gets a live FairPrice product, chosen as the estimator chooses one.


def on_shelf(external_id, grams=400, price=2.5, name="Agro Fresh Local Cucumber", **updates):
    return ProductResponse(
        **{
            "external_id": external_id,
            "name": name,
            "brand": None,
            "category": None,
            "package_size": grams,
            "package_unit": "g",
            "price_sgd": price,
            "product_url": f"https://www.fairprice.com.sg/product/{external_id}",
            "image_url": None,
            "in_stock": True,
            "source": "fairprice",
            "fetched_at": datetime.now(UTC),
            "cart_item_id": f"cart-{external_id}",
            **updates,
        }
    )


def unconfirmed(ingredient="cucumber", external_id="fixture-cucumber-500g"):
    """A list line whose product FairPrice cannot confirm: built-in or snapshot, its source "fixture"."""
    item = line()
    item.ingredient_name = item.ingredient_display_name = ingredient
    item.product = item.product.model_copy(update={"external_id": external_id, "source": "fixture"})
    item.evidence = item.evidence.model_copy(update={"query": ingredient})
    return item


def basket(*items, budget=100):
    return WeeklyGroceryEstimateResponse(
        pricing_mode="live",
        complete=True,
        purchase_total_sgd=sum(item.purchase_cost_sgd for item in items),
        consumed_total_sgd=sum(item.consumed_cost_sgd for item in items),
        weekly_budget_sgd=budget,
        within_weekly_budget=True,
        items=list(items),
        unmapped_ingredients=[],
        warnings=[],
    )


def final_check(grocery, shelf, **constraints):
    return WeeklyGroceryAggregator(service(shelf)).refresh(grocery, WeeklyMealPlanRequest(**constraints))


def reviewed_product(ingredient):
    """The ingredient's first product in the reviewed mapping, as a live page shows it."""
    item = grocery_estimator.release_products()[ingredient]["products"][0]
    return on_shelf(item["external_id"], item["package_grams"], item["price_sgd"], item["name"])


@pytest.fixture
def no_reviewed_mapping(monkeypatch):
    """The line's ingredient is curated with no reviewed products, as baby_spinach is: the name matcher serves it."""
    monkeypatch.setattr(grocery_estimator, "release_products", dict)


@pytest.mark.usefixtures("no_reviewed_mapping")
@pytest.mark.parametrize("external_id", ["fixture-cucumber-500g", "10000"], ids=["no_external_id", "not_returned"])
def test_an_unconfirmed_line_gets_a_live_fairprice_product_and_the_cart_can_take_it(external_id):
    shelf = Provider(lambda query: [on_shelf("cheap-gone", price=0.5, in_stock=False), on_shelf("77")])
    result = final_check(basket(unconfirmed(external_id=external_id), budget=4.5), shelf)
    (item,) = result.items
    assert (item.product.external_id, item.product.source, item.retailer) == ("77", "fairprice", "fairprice")
    assert (item.packages_required, item.purchase_cost_sgd, item.consumed_cost_sgd) == (2, 5, 3.75)
    assert item.excess_quantity == 200 and item.match_score is not None
    assert (item.required_quantity, item.remaining_quantity, item.unit) == (600, 600, "g")
    evidence = item.evidence
    assert (evidence.source, evidence.mode, evidence.price_source) == ("fairprice", "live", "live")
    assert (evidence.lookup_status, evidence.query) == ("success", "cucumber") and evidence.checked_at is not None
    assert (result.purchase_total_sgd, result.consumed_total_sgd, result.complete) == (5, 3.75, True)
    assert result.within_weekly_budget is False and any("by S$0.50" in warning for warning in result.warnings)
    assert not any("sample prices" in warning for warning in result.warnings)
    (rechecked,) = service(shelf).refresh_selected(result.items)
    assert FairPriceCartService._status(item, rechecked, True) == "ready"
    assert rechecked.product.cart_item_id == "cart-77"


@pytest.mark.usefixtures("no_reviewed_mapping")
def test_a_replacement_keeps_the_trip_and_perishable_mark_of_its_line():
    original = unconfirmed()
    original.shopping_trip, original.perishable = 2, True
    (item,) = final_check(basket(original), Provider(lambda query: [on_shelf("77")])).items
    assert item.product.external_id == "77" and (item.shopping_trip, item.perishable) == (2, True)


def test_a_release_ingredient_takes_only_a_reviewed_product_the_live_search_returned(monkeypatch):
    def reviewed(external_id, grams, price):
        return {
            "external_id": external_id,
            "name": f"Butter {external_id}",
            "package_grams": grams,
            "price_sgd": price,
            "product_url": f"https://www.fairprice.com.sg/product/{external_id}",
            "in_stock": True,
            "fetched_at": "2026-10-01T00:00:00+00:00",
            "query": "butter",
        }

    entry = {"status": "mapped", "products": [reviewed("gone", 200, 1), reviewed("kept", 250, 3)]}
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: {"butter": entry})
    # An unreviewed name on the page, however cheap, is what a generic release ingredient must not pick up.
    shelf = Provider(
        lambda query: [on_shelf("cookies", 100, 0.1, "Butter Cookies"), on_shelf("kept", 250, 3, "Butter")]
    )
    (item,) = final_check(basket(unconfirmed("butter", "gone")), shelf).items
    assert (item.product.external_id, item.product.source, item.product.package_size) == ("kept", "fairprice", 250)
    assert (item.packages_required, item.purchase_cost_sgd) == (3, 9)
    assert (item.evidence.lookup_status, item.evidence.query) == ("success", "butter")
    assert shelf.calls == ["butter"]  # the page its price check read is not asked for again
    (rechecked,) = service(shelf).refresh_selected([item])
    assert FairPriceCartService._status(item, rechecked, True) == "ready"


@pytest.mark.parametrize(
    "ingredient,decoy",
    [
        ("carrot", "Carrot Cake"),
        ("mushroom", "Mushroom Soup"),
        ("ginger", "Ginger Snaps"),
        ("garlic", "Garlic Bread"),
        ("garlic", "Garlic Powder"),
    ],
)
def test_a_reviewed_curated_ingredient_ignores_a_processed_food_on_the_page(ingredient, decoy):
    wanted = reviewed_product(ingredient)
    shown = wanted.model_copy(update={"package_size": 9999})  # the page's package is not the reviewed one
    shelf = Provider(lambda query: [on_shelf("decoy", 25, 0.5, decoy), shown])
    (item,) = final_check(basket(unconfirmed(ingredient, f"fixture-{ingredient}")), shelf).items
    assert (item.product.external_id, item.evidence.lookup_status) == (wanted.external_id, "success")
    assert item.product.package_size == wanted.package_size
    assert shelf.calls == [ingredient]
    # With no reviewed product on the page the line is not filled by a guess.
    (kept,) = final_check(
        basket(unconfirmed(ingredient, f"fixture-{ingredient}")),
        Provider(lambda query: [on_shelf("decoy", 25, 0.5, decoy)]),
    ).items
    assert (kept.product.source, kept.evidence.lookup_status) == ("fixture", "no_external_id")


def test_a_reviewed_ingredient_in_millilitres_takes_only_its_reviewed_products():
    item = grocery_estimator.release_products()["milk"]["products"][0]
    fresh = on_shelf(item["external_id"], 946, 3.5, item["name"], package_unit="ml")
    shelf = Provider(lambda query: [on_shelf("almond", 1000, 1, "Almond Milk", package_unit="ml"), fresh])
    original = unconfirmed("milk", "fixture-milk")
    original.unit = "ml"
    (chosen,) = final_check(basket(original), shelf).items
    assert chosen.product.external_id == item["external_id"]


@pytest.mark.usefixtures("no_reviewed_mapping")
@pytest.mark.parametrize(
    "ingredient,shelf_names,chosen",
    [
        ("carrot", ["Carrot Cake 300g", "Sumich Fresh Carrots 500g"], "Sumich Fresh Carrots 500g"),
        ("mushroom", ["Mushroom Soup 300g"], None),
        ("garlic", ["Garlic Powder 25g"], None),
        ("cucumber", ["Butter Cookies"], None),  # also under the matcher's threshold
        ("yellow_onion", ["Yellow Onions"], "Yellow Onions"),
        ("baby_spinach", ["Spinach Soup", "Pasar Baby Spinach"], "Pasar Baby Spinach"),
    ],
)
def test_the_name_matcher_only_takes_a_product_named_for_the_ingredient(ingredient, shelf_names, chosen):
    shelf = Provider(lambda query: [on_shelf(f"p{index}", name=name) for index, name in enumerate(shelf_names)])
    original = unconfirmed(ingredient, f"fixture-{ingredient}")
    (item,) = final_check(basket(original), shelf).items
    assert item.product.name == (chosen or original.product.name)
    assert item.evidence.lookup_status == ("success" if chosen else "no_external_id")


@pytest.mark.usefixtures("no_reviewed_mapping")
@pytest.mark.parametrize(
    "constraints,name",
    [
        ({"allergens": ["tree_nut"]}, "Almond Greek Yogurt"),
        ({"allergens": ["soy"]}, "Soy Greek Yogurt"),
        ({"excluded_ingredients": ["coconut"]}, "Coconut Greek Yogurt"),
    ],
)
def test_a_replacement_naming_what_the_household_avoids_is_refused(constraints, name):
    shelf = Provider(lambda query: [on_shelf("77", name=name)])
    original = unconfirmed("greek_yogurt", "fixture-greek-yogurt")
    (kept,) = final_check(basket(original), shelf, **constraints).items
    assert kept.product == original.product and kept.evidence.lookup_status == "no_external_id"
    (taken,) = final_check(basket(unconfirmed("greek_yogurt", "fixture-greek-yogurt")), shelf).items
    assert taken.product.name == name


@pytest.mark.usefixtures("no_reviewed_mapping")
def test_a_line_that_needs_certification_takes_only_a_certified_product(monkeypatch):
    monkeypatch.setattr(halal_data, "needs_certification", lambda name: True)
    products = [on_shelf("plain", price=1), on_shelf("certified", price=3, halal_certified=True)]
    (item,) = final_check(basket(unconfirmed()), Provider(lambda query: products), requires_halal=True).items
    assert item.product.external_id == "certified"
    (kept,) = final_check(basket(unconfirmed()), Provider(lambda query: products[:1]), requires_halal=True).items
    assert kept.product.source == "fixture" and kept.evidence.lookup_status == "no_external_id"


def failing(query):
    raise ProductProviderError("offline")


def unpriceable(query):
    return [on_shelf("77", price=2.345)]


@pytest.mark.usefixtures("no_reviewed_mapping")
@pytest.mark.parametrize(
    "external_id,status",
    [("fixture-cucumber-500g", "no_external_id"), ("10000", None)],
    ids=["no_external_id", "not_returned"],
)
@pytest.mark.parametrize("respond", [lambda query: [], failing, unpriceable], ids=["nothing", "failure", "bad price"])
def test_no_acceptable_product_leaves_the_line_as_it_was(respond, external_id, status):
    original = unconfirmed(external_id=external_id)
    result = final_check(basket(original), Provider(respond))
    (item,) = result.items
    assert item.product == original.product and item.purchase_cost_sgd == 4 and item.consumed_cost_sgd == 2.4
    expected = status or ("provider_error" if respond is failing else "selected_product_not_returned")
    assert item.evidence.lookup_status == expected
    assert (item.evidence.checked_at is None) == (status == "no_external_id")
    assert result.purchase_total_sgd == 4 and result.within_weekly_budget is True


def test_a_replacement_that_cannot_be_costed_does_not_replace_a_costed_line(monkeypatch):
    monkeypatch.setattr(grocery_estimator, "release_products", dict)  # no reviewed mapping to fall back on
    shelf = Provider(lambda query: [on_shelf("loose", None, 1, package_unit=None)])
    result = final_check(basket(unconfirmed()), shelf)
    assert result.items[0].product.source == "fixture"
    assert result.complete is True and result.consumed_total_sgd == 2.4


@pytest.mark.usefixtures("no_reviewed_mapping")
def test_a_replacement_that_prices_the_last_unknown_line_completes_the_list():
    confirmed = line(1)
    grocery = basket(confirmed, unconfirmed())
    grocery.items[1].consumed_cost_sgd = None
    grocery = grocery.model_copy(update={"complete": False, "consumed_total_sgd": None, "within_weekly_budget": None})

    def respond(query):
        return [on_shelf("77")] if query == "cucumber" else [observed(confirmed, price_sgd=2)]

    result = final_check(grocery, Provider(respond))
    assert (result.complete, result.consumed_total_sgd, result.within_weekly_budget) == (True, 6.15, True)


@pytest.mark.usefixtures("no_reviewed_mapping")
def test_a_replacement_past_the_deadline_is_never_applied(monkeypatch):
    monkeypatch.setattr(prices, "FINAL_PRICE_SECONDS", 0.08)
    release, finished = Event(), Event()

    def respond(query):
        assert release.wait(2)
        finished.set()
        return [on_shelf("77")]

    grocery = basket(unconfirmed())
    try:
        begin = monotonic()
        result = final_check(grocery, Provider(respond))
        assert monotonic() - begin < 0.4
    finally:
        release.set()
    assert finished.wait(1)
    assert result.items[0].product.source == "fixture" and result.items[0].evidence.lookup_status == "no_external_id"


def test_every_unconfirmed_line_of_a_full_list_is_replaced_inside_the_window(monkeypatch):
    """The reported list at 1/10 time scale: 40 price checks and 11 unconfirmed lines, 1.2 s a search, 10 s for all."""
    monkeypatch.setattr(prices, "FINAL_PRICE_SECONDS", 1.0)
    no_identity = ["broccoli", "chicken_breast", "cucumber", "garlic", "ginger", "mushroom"]
    not_returned = ["butter", "carrot", "chicken", "milk", "rice"]
    confirmed = [line(index) for index in range(35)]
    page = {name.replace("_", " "): [reviewed_product(name)] for name in no_identity + not_returned}
    active = peak = 0
    lock = Lock()

    def respond(query):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.12)
        with lock:
            active -= 1
        return page.get(query) or [observed(confirmed[int(query.removeprefix("food"))])]

    shelf = Provider(respond)
    missing = [unconfirmed(name, f"fixture-{name}") for name in no_identity]
    gone = [unconfirmed(name, "10000") for name in not_returned]
    items = final_check(basket(*confirmed, *missing, *gone), shelf).items
    assert all(item.product.source == "fairprice" for item in items)
    assert all(item.evidence.lookup_status == "success" for item in items)
    assert 1 < peak <= 8
    # The lines with nothing to wait for go first, and a page a price check just read is not asked for again.
    assert set(shelf.calls[:6]) == {name.replace("_", " ") for name in no_identity}
    assert len(shelf.calls) == 46 == len(set(shelf.calls))


def test_repeated_failures_stop_the_replacement_searches():
    one_at_a_time = Lock()

    def respond(query):
        with one_at_a_time:
            sleep(0.005)
        raise ProductProviderError("challenge page")

    shelf = Provider(respond)
    items = final_check(basket(*[unconfirmed() for _ in range(30)]), shelf).items
    assert all(item.product.source == "fixture" for item in items)
    assert len(shelf.calls) <= 10  # eight running, and the two started as the first failures came back


def test_a_replaced_line_reaches_the_cart_ready_after_it_is_saved():
    wanted = reviewed_product("carrot")
    shelf = Provider(lambda query: [on_shelf("other", name="Carrot Cake"), wanted])
    grocery = final_check(basket(unconfirmed("carrot", "fixture-carrot")), shelf)
    plan = MealPlan(id=1, pricing_mode="live", weekly_budget_sgd=100, grocery_items=[], fairprice_cart=None)
    session = SimpleNamespace(flush=lambda: None, commit=lambda: None)
    MealPlanRepository(session, household_id=1)._replace_grocery_items(plan, grocery)
    shelf.respond = lambda query: [wanted, on_shelf("other", name="Carrot Cake")]  # another order on the recheck
    cart = FairPriceCartService(
        repository=SimpleNamespace(get=lambda plan_id: plan, session=session), product_service=service(shelf)
    )
    (prepared,) = cart.prepare(1, None).lines
    assert (prepared.status, prepared.client_item_id) == ("ready", wanted.external_id)
    assert prepared.cart_item_id == f"cart-{wanted.external_id}"


@pytest.mark.parametrize("confirm", [False, True], ids=["generate", "confirm"])
def test_both_final_checks_pass_the_households_rules(monkeypatch, confirm):
    from tests.test_planning_capability import dish_client
    from tests.test_wp1_snapshot_planning import dishes

    seen = []

    def spy(self, grocery, constraints):
        seen.append(constraints)
        return grocery

    monkeypatch.setattr(WeeklyGroceryAggregator, "refresh", spy)
    rules = {"requires_halal": True, "allergens": ["peanut"], "excluded_ingredients": ["coconut"]}
    catalog = dishes()
    for dish in catalog:
        dish.halal_status = "halal"
    with dish_client(monkeypatch, catalog) as client:
        created = client.post(
            "/api/plans/generate",
            json={"household_size": 2, "weekly_budget_sgd": 500, "pricing_mode": "live", **rules},
        )
        assert created.status_code == 201, created.text
        plan = created.json()
        if confirm:
            preview = client.post(
                f"/api/plans/{plan['id']}/replan/preview",
                json={"entry_id": plan["days"][0]["entry_id"], "event_type": "CANCEL_MEAL"},
            )
            assert preview.status_code == 201, preview.text
            done = client.post(f"/api/plans/{plan['id']}/replan/{preview.json()['id']}/confirm")
            assert done.status_code == 200, done.text
    assert len(seen) == (2 if confirm else 1)
    assert (seen[-1].requires_halal, seen[-1].allergens, seen[-1].excluded_ingredients) == (
        True,
        ["peanut"],
        ["coconut"],
    )
