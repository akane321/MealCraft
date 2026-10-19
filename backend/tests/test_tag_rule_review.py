import importlib.util

from app.core.paths import repository_root


def test_changed_case_sampling_is_reproducible_unique_and_bounded():
    path = repository_root() / "data-engineering/scripts/review_tag_rule_changes.py"
    spec = importlib.util.spec_from_file_location("tag_rule_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    known = sorted(module.KNOWN_CASES)
    pool = known + [f"case-{index}" for index in range(100)]
    first = module.choose(pool, 25, 20261019)
    assert first == module.choose(list(reversed(pool)), 25, 20261019)
    assert len(first) == len(set(first)) == 25
    assert set(known) <= set(first) <= set(pool)


def test_only_an_unreviewed_critical_model_field_triggers_the_gate():
    path = repository_root() / "data-engineering/scripts/review_tag_rule_changes.py"
    spec = importlib.util.spec_from_file_location("tag_rule_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    estimates = {
        "blocked": {"estimated": {"meal_role": {"method": "llm", "reviewed": False}}},
        "accepted": {"estimated": {"meal_role": {"method": "llm", "reviewed": True}}},
        "flavor": {"estimated": {"flavor_tags": {"method": "llm", "reviewed": False}}},
        "rule": {"estimated": {"meal_role": {"method": "rule", "reviewed": False}}},
    }
    assert module.gated(estimates) == {"blocked"}
