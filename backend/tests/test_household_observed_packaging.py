import importlib.util

from app.core.paths import repository_root


def runner():
    path = repository_root() / "scripts/compare_household_observed_packaging.py"
    spec = importlib.util.spec_from_file_location("compare_household_observed_packaging", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_line_comparison_holds_demand_and_observed_options_constant():
    module = runner()
    snapshot = {
        "ingredients": {
            "rice": {
                "status": "mapped",
                "products": [
                    {
                        "external_id": "large",
                        "package_grams": 600,
                        "price_sgd": 4.0,
                        "in_stock": True,
                    },
                    {
                        "external_id": "small",
                        "package_grams": 400,
                        "price_sgd": 3.0,
                        "in_stock": True,
                    },
                ],
            }
        }
    }
    result = module.compare_line(
        {
            "ingredient_name": "rice",
            "remaining_quantity": 1000,
            "unit": "g",
            "shopping_trip": 1,
        },
        snapshot,
    )
    assert result["status"] == "compared"
    assert result["single_product"]["cost_sgd"] == 8.0
    assert result["mixed_package"]["cost_sgd"] == 7.0
    assert result["saving_sgd"] == 1.0


def test_unmapped_line_is_reported_not_priced_as_zero():
    module = runner()
    result = module.compare_line(
        {"ingredient_name": "unknown", "remaining_quantity": 1, "unit": "g", "shopping_trip": None},
        {"ingredients": {}},
    )
    assert result["status"] == "unresolved"
    assert result["reason"] == "no_in_stock_observed_option"
