import hashlib
import importlib.util
import json

import pytest

from app.core.paths import repository_root

pytestmark = pytest.mark.skipif(
    not (repository_root() / "data-engineering/scripts/review_tag_rule_changes.py").is_file(),
    reason="Repository-only review script is not shipped in the backend image.",
)


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


def test_owner_application_check_keeps_rejected_outputs_and_requires_actual_corrections(tmp_path, monkeypatch):
    path = repository_root() / "data-engineering/scripts/review_tag_rule_changes.py"
    spec = importlib.util.spec_from_file_location("tag_rule_review", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "OUT", tmp_path / "review")
    packet = {
        "owner_confirmed": True,
        "sample_count": 2,
        "tag_file_sha256": "original-snapshot-hash",
        "records": [
            {
                "key": "rice",
                "title": "Rice",
                "changed_fields": ["meal_role"],
                "after": {"meal_role": None},
                "corrected_values": {"meal_role": "staple"},
                "verdict": {"meal_role": False},
                "model_batch_still_gated": False,
            },
            {
                "key": "missing",
                "title": "Missing",
                "changed_fields": ["protein_sources"],
                "after": {"protein_sources": None},
                "verdict": {"protein_sources": True},
                "model_batch_still_gated": False,
            },
        ],
    }
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(packet), encoding="utf-8")
    tags = tmp_path / module.RECIPE_TAGS
    tags.parent.mkdir(parents=True)
    tags.write_text(
        json.dumps({"recipes": {"rice": {"meal_role": "staple"}, "missing": {"protein_sources": None}}}),
        encoding="utf-8",
    )
    result = module.verify_owner_review()
    assert result["all_current_expectations_applied"] and result["owner_reviewed_cases"] == 2
    assert (
        result["review_packet_sha256"] == hashlib.sha256(review_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    )
    assert result["cases"][0]["corrected"] == {"meal_role": "staple"}
    assert json.loads(review_path.read_text(encoding="utf-8")) == packet
    original_tag_bytes = tags.read_bytes()
    with monkeypatch.context() as revised_policy:
        revised_policy.setattr(module, "MEASUREMENT_POLICY_REVISIONS", {"rice": {"meal_role": "one_bowl"}})
        tags.write_text(
            json.dumps({"recipes": {"rice": {"meal_role": "one_bowl"}, "missing": {"protein_sources": None}}}),
            encoding="utf-8",
        )
        revised = module.verify_owner_review()
        assert revised["all_current_expectations_applied"] and not revised["all_original_owner_values_unchanged"]
        assert revised["cases"][0]["original_owner_values"] == {"meal_role": "staple"}
        assert json.loads(review_path.read_text(encoding="utf-8")) == packet
    tags.write_bytes(original_tag_bytes)
    current = json.loads(tags.read_text(encoding="utf-8"))
    current["recipes"]["rice"]["meal_role"] = None
    tags.write_text(json.dumps(current), encoding="utf-8")
    with pytest.raises(AssertionError, match="Not applied"):
        module.verify_owner_review()
    current["recipes"]["rice"]["meal_role"] = "staple"
    tags.write_text(json.dumps(current), encoding="utf-8")
    packet["records"][1]["verdict"]["protein_sources"] = None
    review_path.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(AssertionError, match="Unreviewed field"):
        module.verify_owner_review()
    packet["records"][1]["verdict"]["protein_sources"] = True
    packet["records"][0]["corrected_values"] = {}
    review_path.write_text(json.dumps(packet), encoding="utf-8")
    with pytest.raises(AssertionError, match="Missing or excessive owner corrections"):
        module.verify_owner_review()
