import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.paths import repository_root
from app.evaluation.v2_packets import (
    FrozenEvaluationPacket,
    compile_v2_developer_packets,
    context_matched_llm_prompt,
)

ROOT = repository_root()
SOURCE = ROOT / "data/evaluation/v2/dev/packet-source-v1.json"
BUNDLE = ROOT / "data/evaluation/v2/dev/packets-v1.json"
INGREDIENTS = ROOT / "data/ingredients/ingredients.json"
RECIPES = ROOT / "data/recipes/recipes.json"
PRODUCTS = ROOT / "data/fixtures/fairprice-products.json"


def _compiled() -> dict:
    return compile_v2_developer_packets(
        source_path=SOURCE,
        ingredient_path=INGREDIENTS,
        recipe_path=RECIPES,
        product_path=PRODUCTS,
    )


def test_v2_packet_compiler_is_offline_versioned_and_digest_protected() -> None:
    compiled = _compiled()

    assert compiled["evaluation_role"] == "developer_set"
    assert compiled["live_api_used"] is False
    assert compiled["packet_count"] == 2
    assert len(compiled["packet_set_sha256"]) == 64
    assert all(len(value) == 64 for value in compiled["source_digests"].values())


def test_committed_v2_packet_bundle_matches_reproducible_compiler_output() -> None:
    committed = json.loads(BUNDLE.read_text(encoding="utf-8"))

    assert committed == _compiled()


def test_v2_packet_contains_neutral_facts_without_mealcraft_intermediate_answers() -> None:
    compiled = _compiled()
    serialized = str(compiled["packets"])

    for forbidden in (
        "parsed_constraints",
        "eligibility",
        "hard_violations",
        "planner_score",
        "selected_plan",
        "selected_products",
        "grocery_total",
        "feasibility_label",
        "gold_answer",
    ):
        assert forbidden not in serialized
    assert compiled["packets"][0]["recipe_candidates"]
    assert compiled["packets"][0]["fairprice_snapshot"]


def test_v2_packet_product_snapshot_covers_every_candidate_ingredient() -> None:
    for packet in _compiled()["packets"]:
        candidate_ingredients = {
            ingredient["ingredient_id"]
            for recipe in packet["recipe_candidates"]
            for ingredient in recipe["ingredients"]
        }
        covered_ingredients = {
            ingredient_id
            for product in packet["fairprice_snapshot"]
            for ingredient_id in product["mapped_ingredient_ids"]
        }

        assert candidate_ingredients <= covered_ingredients


def test_v2_packet_compiler_rejects_incomplete_product_coverage(tmp_path: Path) -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    source["scenarios"][0]["fairprice_product_ids"] = ["fixture-brown-rice-1kg"]
    incomplete_source = tmp_path / "incomplete-source.json"
    incomplete_source.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(ValueError, match="does not cover candidate ingredients"):
        compile_v2_developer_packets(
            source_path=incomplete_source,
            ingredient_path=INGREDIENTS,
            recipe_path=RECIPES,
            product_path=PRODUCTS,
        )


def test_v2_packet_schema_rejects_answer_leakage() -> None:
    payload = _compiled()["packets"][0] | {"selected_plan": ["do-not-leak"]}

    with pytest.raises(ValidationError, match="selected_plan"):
        FrozenEvaluationPacket.model_validate(payload)


def test_context_matched_prompt_is_strong_but_does_not_run_an_api() -> None:
    packet = FrozenEvaluationPacket.model_validate(_compiled()["packets"][0])
    prompt = context_matched_llm_prompt(packet)

    assert "Use only the supplied packet" in prompt
    assert "no tools and no post-generation repair" in prompt
    assert "EVALUATION_PACKET" in prompt
    assert "selected_plan" not in prompt
