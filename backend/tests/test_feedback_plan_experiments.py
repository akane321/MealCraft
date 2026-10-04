from app.core.paths import repository_root
from app.planning.feedback_plan_experiments import FeedbackPlanDataset, plan_with_feedback


def source():
    return FeedbackPlanDataset.model_validate_json(
        (repository_root() / "data/fixtures/planning-v2/feedback-plan-developer-v1.json").read_bytes()
    )


def run(data, enabled=False):
    return plan_with_feedback(
        data.problem, data.events, scope_id=data.scope_id, decision_at=data.decision_at, enabled=enabled
    )


def test_off_is_default_and_both_selected_plans_are_valid():
    data = source()
    before = data.model_dump_json()
    off, on = run(data), run(data, True)
    assert off["assignments"][0]["recipe_id"] == "a-large"
    assert on["assignments"][0]["recipe_id"] == "b-small"
    assert off["audit"]["status"] == on["audit"]["status"] == "passed"
    assert on["ranking"][0]["used_event_ids"] == ["past-b"]
    assert off["input_sha256"] == on["input_sha256"]
    assert data.model_dump_json() == before


def test_feedback_cannot_restore_an_excluded_candidate():
    data = source()
    data.problem.allergens = ["milk"]
    data.problem.allergen_vocabulary = ["milk"]
    data.problem.recipes[1].allergens = ["milk"]
    result = run(data, True)
    assert result["assignments"][0]["recipe_id"] == "a-large"
    assert "b-small" not in result["ranking"][0]["eligible"]


def test_ranking_never_overrides_budget_or_unknown_products():
    data = source()
    data.problem.purchase_budget_sgd = 0.99
    assert run(data, True)["status"] == "candidate_rejected"
    data.problem.products = []
    assert run(data, True)["status"] == "needs_data"


def test_other_scope_and_future_events_do_not_affect_order():
    data = source()
    data.scope_id = "another-scope"
    result = run(data, True)
    assert result["assignments"][0]["recipe_id"] == "a-large"
    assert result["ranking"][0]["used_event_ids"] == []


def test_locked_recipe_cannot_be_replaced_by_feedback():
    data = source()
    data.problem.slots[0].locked_recipe_id = "a-large"
    assert run(data, True)["assignments"][0]["recipe_id"] == "a-large"
