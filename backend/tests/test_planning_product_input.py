from datetime import UTC, datetime

import pytest

from app.planning.package_optimizer import optimize_packages
from app.planning.product_input import product_input
from app.schemas.product import ProductResponse


def observation(**changes):
    data = dict(
        external_id="fixture-rice",
        name="Untrusted display title",
        brand=None,
        category=None,
        package_size=150,
        package_unit="g",
        price_sgd=2,
        product_url="https://example.test/rice",
        image_url=None,
        in_stock=True,
        source="fixture",
        fetched_at=datetime(2026, 9, 14, tzinfo=UTC),
    )
    data.update(changes)
    return ProductResponse.model_validate(data)


def test_projection_preserves_explicit_mapping_and_detaches_source():
    source = observation()
    result = product_input(source, ingredient_id="rice", required_unit="g")
    assert not result.issues
    assert result.option.ingredient_id == "rice"
    assert result.option.product_id == source.external_id
    assert result.observation.source == "fixture"
    assert result.observation.fetched_at == source.fetched_at
    source.price_sgd = 999
    assert result.observation.price_sgd == result.option.price_sgd == 2


@pytest.mark.parametrize(
    "changes,issue",
    [
        ({"package_size": None}, "unknown_package_quantity"),
        ({"package_size": 0}, "invalid_package_quantity"),
        ({"package_size": float("inf")}, "invalid_package_quantity"),
        ({"package_unit": None}, "unknown_package_unit"),
        ({"package_unit": "kg"}, "incompatible_package_unit"),
        ({"price_sgd": 1.001}, "fractional_cent_price"),
        ({"price_sgd": float("inf")}, "invalid_price"),
        ({"external_id": " "}, "missing_product_id"),
        ({"product_url": " "}, "observation_url_missing"),
        ({"fetched_at": datetime(2026, 9, 14)}, "observation_timezone_missing"),
    ],
)
def test_incomplete_or_invalid_facts_never_become_arithmetic_defaults(changes, issue):
    result = product_input(observation(**changes), ingredient_id="rice", required_unit="g")
    assert result.option is None
    assert issue in result.issues


def test_unavailable_observation_is_preserved_and_optimizer_will_not_buy_it():
    result = product_input(observation(in_stock=False), ingredient_id="rice", required_unit="g")
    assert not result.option.available
    assert not result.issues
    assert optimize_packages("rice", 100, "g", [result.option]).status == "needs_data"


def test_multiple_explicitly_mapped_sizes_reach_existing_optimizer():
    sources = [observation(), observation(external_id="small", package_size=100, price_sgd=1.5)]
    options = [product_input(p, ingredient_id="rice", required_unit="g").option for p in sources]
    result = optimize_packages("rice", 250, "g", options)
    assert result.status == "optimal"
    assert result.purchase_cost_sgd == 3.5
    assert len(result.allocations) == 2


@pytest.mark.parametrize("ingredient,unit", [("", "g"), ("rice", " ")])
def test_missing_explicit_mapping_context_is_rejected(ingredient, unit):
    with pytest.raises(ValueError):
        product_input(observation(), ingredient_id=ingredient, required_unit=unit)
