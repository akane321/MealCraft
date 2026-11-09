import importlib.util

from app.core.paths import repository_root


def runner():
    path = repository_root() / "scripts/product_household_comparison.py"
    spec = importlib.util.spec_from_file_location("product_household_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conditions_are_repeated_with_rotated_interleaving():
    scheduled = runner().interleaved_conditions([8, 16], [0, 50], 3)
    assert scheduled[:4] == [
        (0, 0, 8, 0),
        (0, 1, 8, 50),
        (0, 2, 16, 0),
        (0, 3, 16, 50),
    ]
    assert scheduled[4:8] == [
        (1, 0, 8, 50),
        (1, 1, 16, 0),
        (1, 2, 16, 50),
        (1, 3, 8, 0),
    ]
    assert sorted((width, steps) for _, _, width, steps in scheduled) == sorted(
        [(8, 0), (8, 50), (16, 0), (16, 50)] * 3
    )
