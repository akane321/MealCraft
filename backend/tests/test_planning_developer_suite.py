import json

import pytest

from app.core.paths import repository_root
from app.planning.developer_experiments import MealExperimentDataset, run_experiments
from app.planning.developer_suite import analysis_markdown, run_planning_suite
from app.planning.meal_beam import MealState, repetition_loss


def dataset():
    return MealExperimentDataset.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/composed-ablation-developer-v1.json").read_bytes()
    )


def test_composed_reward_changes_selection_without_removing_caps():
    source = dataset()
    before = source.model_dump_json()
    report = run_experiments(source)
    rows = {(r["case_id"], r["preset"]): r for r in report["runs"]}
    on = rows["composed-overlap", "beam"]
    off = rows["composed-overlap", "overlap_off"]

    def names(row):
        return {a["recipe_id"] for a in row["solution"]["assignments"]}

    assert "greens" in names(on) and "a-plain-greens" in names(off)
    assert on["audit"]["status"] == off["audit"]["status"] == "passed"
    assert on["effective_weights"]["classifications"] == off["effective_weights"]["classifications"]
    assert (
        on["effective_weights"]["max_slots_per_core_ingredient"]
        == off["effective_weights"]["max_slots_per_core_ingredient"]
    )
    assert on["solution"]["trace"]["algorithm_version"] == "meal-beam-diversity-v2"
    assert source.model_dump_json() == before


def test_composed_repair_off_is_an_actual_condition():
    rows = {(r["case_id"], r["preset"]): r for r in run_experiments(dataset())["runs"]}
    assert rows["composed-repair", "beam"]["audit"]["status"] == "passed"
    off = rows["composed-repair", "repair_off"]
    assert off["audit"]["status"] == "indeterminate"
    assert len(off["attempts"]) == 1
    narrow = rows["composed-repair", "greedy"]
    assert narrow["configuration"]["engine"] == "width-one-meal-beam"
    assert narrow["configuration"]["engine_limits"]["width"] == 1


def test_explicit_composed_soft_terms_stay_bounded_and_each_switch_has_a_consumer():
    packet = dataset().cases[4].problem.model_copy(deep=True)
    packet.diversity_policy.diversity_penalty = 1
    packet.diversity_policy.overlap_reward_weight = 0
    state = MealState(choices=(("prior", (("main", "chicken"), ("vegetable", "greens"))),))
    dishes = (("vegetable", "a-plain-greens"),)
    on = repetition_loss(packet, state, dishes)
    assert 0 < on <= 0.1 / len(packet.slots)
    packet.diversity_policy.diversity_penalty = 0
    assert repetition_loss(packet, state, dishes) == 0
    packet.diversity_policy.overlap_reward_weight = 1
    dishes = (("main", "chicken"), ("vegetable", "greens"), ("soup", "broth"))
    assert -0.1 / len(packet.slots) <= repetition_loss(packet, MealState(), dishes) < 0


def test_suite_replays_feedback_and_keeps_diagnostics_separate():
    report = run_planning_suite(repeats=1)
    feedback = report["reports"]["feedback"]
    assert set(feedback["cooked_choice_top1_matches"]) == {"off", "experimental-cooked-share-v1"}
    assert report["evidence"] == "developer_diagnostic"
    assert report["conditions"]["provider"] == "fixture"
    text = analysis_markdown(report)
    assert "no selection" in text and "indeterminate" in text
    assert "not causal benefit" in text
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("repeats", [True, 0, 21, 1.5])
def test_suite_rejects_invalid_repeats(repeats):
    with pytest.raises(ValueError):
        run_planning_suite(repeats=repeats)
