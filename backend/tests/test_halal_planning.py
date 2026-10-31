"""Halal planning and products (docs/design/halal.md, ADR-0104), unit level with built labels.

The labels and the certified-product facts are built here; no data file of the halal feature is read.
"""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data import halal as halal_data
from app.db.base import Base
from app.planning import grocery_estimator
from app.planning.constraint_compiler import compile_constraints
from app.planning.final_scope_reference import FinalScopeReferencePlanner
from app.planning.final_scope_validator import FinalPlanningValidator
from app.planning.grocery_estimator import ProductMatcher, choose_product
from app.planning.halal import halal_ok
from app.planning.meal_beam import dish_eligible
from app.products.provider import FairPriceProductProvider
from app.repositories.product import ProductSnapshotRepository
from app.schemas.planning_v2 import FinalPlanningProblem, PlanningAssignment, PlanningShoppingSelection
from app.schemas.product import ProductResponse
from tests.test_wp1_final_prices import Provider, line, observed, service

NOW = datetime(2026, 10, 30, tzinfo=UTC)
NUTRIENTS = ("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g")


def label(status="halal", certify=False):
    return {"status": status, "needs_certification": certify, "source": "test", "reason": "test"}


@pytest.fixture(autouse=True)
def labels(monkeypatch):
    built = {
        "chicken_breast": {"normalized_name": "chicken_breast", **label(certify=True)},
        "rice": {"normalized_name": "rice", **label()},
    }
    monkeypatch.setattr(halal_data, "halal_labels", lambda: built)
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {"cert": True})


def recipe(recipe_id="chicken-rice", status="needs_certification", *ingredients):
    return {
        "recipe_id": recipe_id,
        "title": recipe_id.replace("-", " "),
        "servings": 2,
        "allowed_meal_types": ["dinner"],
        "total_time_minutes": 30,
        "allergens": [],
        "halal_status": status,
        "ingredients": [
            {"ingredient_id": i, "quantity": 300, "unit": "g"} for i in (ingredients or ("chicken_breast",))
        ],
        "nutrients_per_serving": dict.fromkeys(NUTRIENTS, 10),
    }


def option(product_id, price, *, certified=None, available=True, ingredient="chicken_breast"):
    return {
        "ingredient_id": ingredient,
        "product_id": product_id,
        "package_quantity": 500,
        "package_unit": "g",
        "price_sgd": price,
        "available": available,
        "halal_certified": certified,
    }


def problem(recipes, products=(), *, requires_halal=True):
    return FinalPlanningProblem.model_validate(
        {
            "problem_id": "halal",
            "slots": [
                {
                    "slot_id": "d1",
                    "planned_date": date(2026, 10, 30).isoformat(),
                    "meal_type": "dinner",
                    "servings": 2,
                }
            ],
            "recipes": recipes,
            "products": list(products),
            "allergen_vocabulary": [],
            "requires_halal": requires_halal,
            "catalog_version": "test",
            "product_snapshot_version": "test",
            "policy_version": "test",
        }
    )


def test_halal_is_accepted_and_needs_certification_needs_a_certified_option():
    certified = [option("cert", 9, certified=True)]
    dearer_uncertified = [option("cheap", 4), option("unknown", 5, certified=None)]
    assert halal_ok(problem([recipe(status="halal")]).recipes[0], problem([recipe(status="halal")]))
    for products, expected in [
        ([], False),
        (dearer_uncertified, False),
        (certified, True),
        ([*dearer_uncertified, *certified], True),
        ([option("cert", 9, certified=True, available=False)], False),
        ([option("cert", 9, certified=True, ingredient="rice")], False),
    ]:
        found = problem([recipe()], products)
        assert halal_ok(found.recipes[0], found) is expected


def test_a_recipe_of_lines_that_need_no_certification_needs_no_product():
    found = problem([recipe("rice-bowl", "needs_certification", "rice")])
    assert halal_ok(found.recipes[0], found)


@pytest.mark.parametrize("status", ["uncertain", "not_halal", None])
def test_uncertain_not_halal_and_unlabelled_recipes_are_rejected_even_with_certified_products(status):
    found = problem([recipe(status=status)], [option("cert", 9, certified=True)])
    assert not halal_ok(found.recipes[0], found)


def test_without_the_household_switch_every_recipe_passes():
    found = problem([recipe(status="not_halal")], requires_halal=False)
    assert halal_ok(found.recipes[0], found)


def test_the_engine_screens_the_status_before_any_product_exists():
    """The recommendation engine passes the request, which has no products: it keeps halal and needs_certification."""
    request = SimpleNamespace(requires_halal=True)
    assert halal_ok(SimpleNamespace(halal_status="halal"), request)
    assert halal_ok(SimpleNamespace(halal_status="needs_certification"), request)
    assert not halal_ok(SimpleNamespace(halal_status="uncertain"), request)
    assert not halal_ok(SimpleNamespace(halal_status=None), request)


def test_the_compiler_the_beam_and_the_reference_planner_agree():
    without = problem([recipe()], [option("cheap", 4)])
    with_cert = problem([recipe()], [option("cheap", 4), option("cert", 9, certified=True)])
    slot = without.slots[0]
    assert {row.rejection_codes for row in compile_constraints(without)} == {("halal_requirement",)}
    assert all(not row.rejection_codes for row in compile_constraints(with_cert))
    assert not dish_eligible(without, slot, without.recipes[0])
    assert dish_eligible(with_cert, slot, with_cert.recipes[0])
    assert FinalScopeReferencePlanner._eligible(without, slot) == []
    assert FinalScopeReferencePlanner._eligible(with_cert, slot) == with_cert.recipes


def solution_for(found, product_id):
    packages = 1
    return (
        [PlanningAssignment(slot_id="d1", recipe_id="chicken-rice")],
        [
            PlanningShoppingSelection(
                ingredient_id="chicken_breast",
                required_quantity=300,
                unit="g",
                pantry_deduction=0,
                remaining_quantity=300,
                selected_product_id=product_id,
                packages=packages,
                purchase_cost_sgd=next(p.price_sgd for p in found.products if p.product_id == product_id) * packages,
                surplus_quantity=200,
            )
        ],
    )


def test_the_validator_catches_an_uncertified_meat_product_and_a_dish_without_one():
    found = problem([recipe()], [option("cheap", 4), option("cert", 9, certified=True)])
    report = FinalPlanningValidator().validate(found, *solution_for(found, "cheap"))
    failed = {check.code for check in report.checks if check.status == "failed"}
    assert "halal_product" in failed and report.status == "failed"
    report = FinalPlanningValidator().validate(found, *solution_for(found, "cert"))
    assert not {check.code for check in report.checks if check.status == "failed"}

    bare = problem([recipe()], [option("cheap", 4)])
    report = FinalPlanningValidator().validate(bare, *solution_for(bare, "cheap"))
    failed = {check.code for check in report.checks if check.status == "failed"}
    assert {"halal_requirement", "halal_product"} <= failed


def test_the_reference_planner_buys_the_certified_product_even_when_dearer():
    found = problem([recipe()], [option("cheap", 4), option("cert", 9, certified=True)])
    shopping = FinalScopeReferencePlanner()._build_shopping(
        found, [PlanningAssignment(slot_id="d1", recipe_id="chicken-rice")]
    )
    assert [row.selected_product_id for row in shopping] == ["cert"]


def release_entry():
    def item(external_id, price):
        return {
            "external_id": external_id,
            "name": external_id,
            "brand": None,
            "category": None,
            "package_grams": 500,
            "price_sgd": price,
            "product_url": f"https://www.fairprice.com.sg/product/{external_id}",
            "in_stock": True,
            "fetched_at": NOW.isoformat(),
            "query": "chicken breast",
        }

    return {"status": "mapped", "products": [item("cheap", 4.0), item("cert", 9.0)]}


def pick(monkeypatch, name, *, requires_halal):
    monkeypatch.setattr(grocery_estimator, "matchable_ingredients", lambda: frozenset())
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: {name: release_entry()})
    return choose_product(
        None, ProductMatcher(), name, name, "g", live=False, quantity=300, requires_halal=requires_halal
    )


def test_product_choice_picks_the_certified_release_product_even_when_dearer(monkeypatch):
    chosen = pick(monkeypatch, "chicken_breast", requires_halal=True)
    assert chosen.product.external_id == "cert" and chosen.product.halal_certified is True
    cheaper = pick(monkeypatch, "chicken_breast", requires_halal=False)
    assert cheaper.product.external_id == "cheap" and cheaper.product.halal_certified is None


def test_a_line_that_needs_no_certification_keeps_its_cheapest_product(monkeypatch):
    assert pick(monkeypatch, "rice", requires_halal=True).product.external_id == "cheap"


def test_a_meat_line_with_no_certified_product_has_no_product(monkeypatch):
    monkeypatch.setattr(halal_data, "release_halal_certification", lambda: {})
    chosen = pick(monkeypatch, "chicken_breast", requires_halal=True)
    assert chosen.product is None and "halal-certified" in chosen.warnings[0]


def test_product_choice_from_a_search_takes_only_certified_products(monkeypatch):
    def listed(external_id, price, certified):
        return ProductResponse(
            external_id=external_id,
            name="Chicken Breast",
            brand=None,
            category=None,
            package_size=500,
            package_unit="g",
            price_sgd=price,
            product_url=f"https://www.fairprice.com.sg/product/{external_id}",
            image_url=None,
            in_stock=True,
            source="fairprice",
            fetched_at=NOW,
            halal_certified=certified,
        )

    trace = SimpleNamespace(mode="live", query="chicken breast", parser_version="test")
    items = [listed("cheap", 4.0, None), listed("cert", 9.0, True)]
    searched = SimpleNamespace(
        search=lambda *args, **kwargs: SimpleNamespace(items=items, warning=None, retrieval=trace)
    )
    monkeypatch.setattr(grocery_estimator, "matchable_ingredients", lambda: frozenset({"chicken_breast"}))
    monkeypatch.setattr(grocery_estimator, "release_products", lambda: {})
    for requires_halal, expected in [(True, "cert"), (False, "cheap")]:
        chosen = choose_product(
            searched,
            ProductMatcher(),
            "chicken_breast",
            "chicken breast",
            "g",
            live=True,
            requires_halal=requires_halal,
        )
        assert chosen.product.external_id == expected


def parsed(metadata):
    provider = FairPriceProductProvider(base_url="https://www.fairprice.com.sg", timeout_seconds=1)
    record = {
        "id": 1,
        "clientItemId": 2,
        "name": "Chicken",
        "slug": "chicken-2",
        "final_price": 6.95,
        "metaData": metadata,
    }
    return provider._parse_product(record, NOW)


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"Dietary Attributes": ["Halal"]}, True),
        ({"Dietary Attributes": ["Healthier Choice", "Halal"]}, True),
        ({"Dietary Attributes": ["Vegetarian"]}, None),
        ({"Dietary Attributes": []}, None),
        ({}, None),
    ],
)
def test_the_live_parser_reads_the_halal_attribute_and_never_infers_false(metadata, expected):
    assert parsed(metadata).halal_certified is expected


def test_the_snapshot_cache_keeps_the_halal_attribute():
    engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    products = [parsed({"Dietary Attributes": ["Halal"]}), parsed({}).model_copy(update={"external_id": "3"})]
    with sessionmaker(bind=engine)() as session:
        repository = ProductSnapshotRepository(session)
        repository.replace_query_results(source="fairprice", search_query="chicken", products=products)
        cached = repository.get_fresh(source="fairprice", search_query="chicken", fetched_after=NOW.min, limit=5)
    assert [product.halal_certified for product in cached] == [True, None]


def test_the_final_price_refresh_copies_the_halal_attribute():
    original = line()
    result = service(Provider(lambda query: [observed(original, halal_certified=True)])).refresh_selected([original])[0]
    assert original.product.halal_certified is None and result.product.halal_certified is True
