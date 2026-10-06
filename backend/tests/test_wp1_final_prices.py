"""Confirmed baskets observe selected SKUs, with a bounded wait and honest fallback."""

from datetime import UTC, datetime, timedelta
from threading import Event, Lock, get_ident
from time import monotonic, sleep

import pytest

from app.planning.weekly_grocery import WeeklyGroceryAggregator
from app.products.provider import ProductProviderError, ProductSchemaDriftError
from app.schemas.meal_plan import WeeklyGroceryEstimateResponse
from app.schemas.product import GroceryLineEstimate, PriceEvidence, ProductResponse
from app.services import product as prices
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
        assert 0 < timeout_seconds <= 3
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
    cached = observed(original)
    provider = Provider(lambda query: pytest.fail("fresh selected SKU should not use network"))
    result = service(provider, Repository({"food0": [cached]})).refresh_selected([original])[0]
    assert result.evidence.price_source == "cache"
    assert result.evidence.fetched_at == cached.fetched_at
    assert result.evidence.checked_at >= cached.fetched_at
    assert result.product.price_sgd == 3
    assert not provider.calls


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
    refreshed = WeeklyGroceryAggregator(service(Provider(lambda query: [observed(original)]))).refresh(grocery)
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

    def refresh_synthetic(self, lines):
        # Assign real-ID-shaped synthetic SKUs without changing candidate selection.
        for index, item in enumerate(lines):
            if item.product:
                item.product = item.product.model_copy(update={"external_id": str(10000 + index)})
                selected[item.evidence.query] = item.product
        return refresh(self, lines)

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
            "/api/plans/generate", json={"household_size": 2, "weekly_budget_sgd": 100, "pricing_mode": "live"}
        )
        assert response.status_code == 201, response.text
        plan = response.json()
        grocery = plan["grocery_estimate"]
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
    result = WeeklyGroceryAggregator(service(Provider(lambda query: []))).refresh(grocery)
    assert result.consumed_total_sgd == 2.39
    assert result.purchase_total_sgd == 4
