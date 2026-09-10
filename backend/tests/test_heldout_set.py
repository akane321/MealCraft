import json
import shutil

import pytest

from app.core.paths import repository_root
from app.evaluation.heldout_set import (
    SET_RELATIVE,
    compile_heldout_packets,
    freeze,
    to_source_scenario,
    verify,
)


def build_set(tmp_path, episodes):
    """A miniature repository: the real catalogs, a synthetic set."""
    root = repository_root()
    work = tmp_path / "repo"
    (work / "data").mkdir(parents=True)
    for relative in ("data/recipes", "data/ingredients", "data/fixtures"):
        shutil.copytree(root / relative, work / relative)
    shutil.copy(root / "scripts/check_heldout_episodes.py", _scripts(work) / "check_heldout_episodes.py")

    set_dir = work / SET_RELATIVE
    (set_dir / "episodes").mkdir(parents=True)
    manifest = json.loads((root / SET_RELATIVE / "set-manifest.json").read_text(encoding="utf-8"))
    manifest["categories"] = {
        "standard": {"quota": len(episodes), "systems_under_test": ["planning"], "description": "x"}
    }
    manifest["language_plan"] = {"en": len(episodes), "zh": 0, "mixed": 0}
    manifest["min_languages_per_category"] = 1
    (set_dir / "set-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for episode in episodes:
        (set_dir / "episodes" / f"{episode['episode_id']}.json").write_text(
            json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return work


def _scripts(work):
    path = work / "scripts"
    path.mkdir(exist_ok=True)
    return path


def episode(episode_id="ho-standard-001", **overrides):
    base = {
        "schema_version": "heldout-episode-v1",
        "episode_id": episode_id,
        "category": "standard",
        "language": "en",
        "authored_by": "backend",
        "reviewed_by": "frontend-evaluation",
        "review_notes": None,
        "scenario": {
            "user_request": "Plan two dinners for two people.",
            "conversation_history": [],
            "household_profile": {
                "household_size": 2,
                "allergens": [],
                "excluded_ingredients": [],
                "dietary_preferences": [],
            },
            "pantry": [],
            "planning_horizon": {"start_date": "2026-09-07", "slots": ["mon-dinner", "tue-dinner"]},
            "recipe_candidate_slugs": ["tomato-lentil-stew", "chickpea-quinoa-salad"],
            "fairprice_product_ids": [],
        },
        "gold": {
            "class": "feasible",
            "required_clarification_fields": [],
            "forbidden_clarification_fields": [],
            "applicable_hard_constraints": {
                "allergens_absent": [],
                "excluded_ingredients_absent": [],
                "dietary_tags_required": [],
                "max_cooking_time_minutes": None,
                "budget_sgd": None,
                "nutrition_bands": [],
            },
            "pantry_ground_truth": {"deductible": [], "not_deductible_unknown_quantity": []},
            "conflict_reason": None,
            "allowed_relaxations": [],
            "required_disclosures": [],
            "replan_invariants": None,
            "author_rationale": "A plain request; a wrong answer would repeat one dish.",
        },
    }
    base.update(overrides)
    return base


def with_covering_products(ep):
    """Attach every product that supplies the candidate ingredients."""
    root = repository_root()
    recipes = {row["slug"]: row for row in json.loads((root / "data/recipes/recipes.json").read_text(encoding="utf-8"))}
    needed = {
        item["ingredient"] for slug in ep["scenario"]["recipe_candidate_slugs"] for item in recipes[slug]["ingredients"]
    }
    products = json.loads((root / "data/fixtures/fairprice-products.json").read_text(encoding="utf-8"))
    ep["scenario"]["fairprice_product_ids"] = sorted(
        p["external_id"] for p in products if set(p["ingredient_keys"]) & needed
    )
    return ep


# --- the property that matters most ------------------------------------------


def test_gold_never_reaches_a_packet(tmp_path):
    """The packet is what every compared system receives. Any gold value in it
    hands the answer to the systems being measured."""
    marked = with_covering_products(episode())
    marked["gold"]["conflict_reason"] = "SENTINEL-CONFLICT"
    marked["gold"]["author_rationale"] = "SENTINEL-RATIONALE"
    marked["gold"]["required_clarification_fields"] = ["SENTINEL-FIELD"]
    work = build_set(tmp_path, [marked])

    bundle = compile_heldout_packets(work)
    rendered = json.dumps(bundle, ensure_ascii=False)
    assert "SENTINEL-CONFLICT" not in rendered
    assert "SENTINEL-RATIONALE" not in rendered
    assert "SENTINEL-FIELD" not in rendered
    assert "gold" not in rendered


def test_projection_takes_named_fields_only():
    """A splat would carry along whatever an author added, including an answer."""
    ep = episode()
    ep["scenario"]["surprise_hint"] = "the answer is recipe A"
    scenario = to_source_scenario(ep)
    assert not hasattr(scenario, "surprise_hint")
    assert scenario.scenario_id == "ho-standard-001"


# --- compiling is the honest test of whether an episode is usable -------------


def test_compiling_produces_one_packet_per_episode(tmp_path):
    work = build_set(tmp_path, [with_covering_products(episode())])
    bundle = compile_heldout_packets(work)
    assert bundle["episode_count"] == 1
    assert len(bundle["packets"]) == 1
    assert bundle["packets"][0]["scenario_id"] == "ho-standard-001"
    assert bundle["evaluation_role"] == "held_out_set"
    assert bundle["live_api_used"] is False


def test_an_episode_whose_products_miss_an_ingredient_cannot_compile(tmp_path):
    """No system could run it, so this must surface at authoring time."""
    thin = with_covering_products(episode())
    thin["scenario"]["fairprice_product_ids"] = thin["scenario"]["fairprice_product_ids"][:1]
    work = build_set(tmp_path, [thin])
    with pytest.raises(ValueError, match="does not cover candidate ingredients"):
        compile_heldout_packets(work)


def test_compiling_is_deterministic(tmp_path):
    work = build_set(tmp_path, [with_covering_products(episode())])
    first = compile_heldout_packets(work)
    second = compile_heldout_packets(work)
    assert first["packet_set_sha256"] == second["packet_set_sha256"]
    assert first["episode_set_sha256"] == second["episode_set_sha256"]


# --- freezing -----------------------------------------------------------------


def test_freeze_stamps_a_digest_and_verify_confirms_it(tmp_path):
    work = build_set(tmp_path, [with_covering_products(episode())])
    manifest = freeze(work)
    assert manifest["status"] == "frozen"
    assert manifest["frozen_at"]
    assert len(manifest["frozen_digest"]) == 64
    assert verify(work) is True


def test_editing_a_frozen_episode_is_detected(tmp_path):
    work = build_set(tmp_path, [with_covering_products(episode())])
    freeze(work)

    path = work / SET_RELATIVE / "episodes" / "ho-standard-001.json"
    edited = json.loads(path.read_text(encoding="utf-8"))
    edited["gold"]["author_rationale"] = "quietly rewritten after the fact"
    path.write_text(json.dumps(edited, ensure_ascii=False, indent=2), encoding="utf-8")

    assert verify(work) is False


def test_a_frozen_set_refuses_to_be_frozen_again(tmp_path):
    work = build_set(tmp_path, [with_covering_products(episode())])
    freeze(work)
    with pytest.raises(SystemExit, match="not edited"):
        freeze(work)


def test_freeze_refuses_a_set_that_breaks_the_authoring_rules(tmp_path):
    """Freeze delegates to the checker rather than restating its rules."""
    unreviewed = with_covering_products(episode())
    unreviewed["reviewed_by"] = None
    work = build_set(tmp_path, [unreviewed])
    with pytest.raises(SystemExit, match="authoring rules"):
        freeze(work)


def test_freeze_refuses_when_the_quota_is_unmet(tmp_path):
    work = build_set(tmp_path, [with_covering_products(episode())])
    manifest_path = work / SET_RELATIVE / "set-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["categories"]["standard"]["quota"] = 12
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(SystemExit, match="authoring rules"):
        freeze(work)
