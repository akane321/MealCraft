"""All examples here are invented; no catalog, episode files or providers are loaded."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

import pytest
from pydantic import ValidationError

from app.core import clock
from app.evaluation.conversation_adapter import (
    CONFIRMATION_MESSAGE,
    ConversationHarness,
    PlanDish,
    PlanMeal,
    PlanOutput,
    RuntimeConfig,
    UnifiedOutput,
    normalize_product,
    shared_instructions,
)
from app.evaluation.conversation_adapter_demo import main as demo_main
from app.orchestration.contracts import ScopeClass, ScopeDecision
from app.schemas.agent import AgentSessionResponse
from app.schemas.meal_plan import WeeklyMealPlanResponse


def config(day="2031-02-03"):
    return RuntimeConfig(anchor_date=day)


def plan_output(name="Invented bean bowl"):
    return UnifiedOutput(
        plan=PlanOutput(
            meals=[PlanMeal(date="2031-02-04", meal_type="dinner", dishes=[PlanDish(name=name)])], household_size=2
        ),
        request_fields={"household_size": 2},
    )


def session(**changes):
    return AgentSessionResponse.model_validate(
        {
            "id": 1,
            "status": "ready",
            "parser_provider": "fixture",
            "constraints": {"household_size": 2},
            "missing_fields": [],
            "clarification_questions": [],
            "messages": [
                {"id": 1, "role": "assistant", "content": "Ready.", "created_at": "2031-02-03T12:00:00+08:00"}
            ],
            "plan_id": None,
            "replan_draft": {},
            "pending_replan": None,
            "context_version": 1,
            "last_scope_decision": {
                "scope_class": "domain_action",
                "should_mutate_state": True,
                "reason_code": "synthetic",
            },
            "pending_interaction": None,
            "can_confirm": True,
            "created_at": "2031-02-03T12:00:00+08:00",
            "updated_at": "2031-02-03T12:00:00+08:00",
            **changes,
        }
    )


def product_plan():
    nutrition = dict.fromkeys(("calories_kcal", "protein_g", "carbohydrate_g", "fat_g", "sodium_mg", "sugar_g"), 1.0)
    return WeeklyMealPlanResponse.model_validate(
        {
            "id": 7,
            "revision": 1,
            "household_profile_id": None,
            "household_profile_version": None,
            "replaces_plan_id": None,
            "start_date": "2031-02-04",
            "end_date": "2031-02-04",
            "day_count": 1,
            "household_size": 2,
            "days": [
                {
                    "entry_id": 3,
                    "day_index": 1,
                    "planned_date": "2031-02-04",
                    "recipe": {
                        "id": 9,
                        "slug": "invented-bowl",
                        "title": "Invented bowl",
                        "description": "Synthetic only",
                        "cuisine": "synthetic",
                        "meal_type": "dinner",
                        "servings": 2,
                        "total_time_minutes": 15,
                        "dietary_tags": [],
                        "nutrition": nutrition,
                    },
                    "servings": 1.5,
                    "not_for": ["Synthetic member"],
                    "recommendation_score": 1,
                    "nutrition_per_person": nutrition,
                    "consumed_cost_sgd": 3,
                    "purchase_cost_sgd": 4,
                    "status": "planned",
                    "is_locked": False,
                    "consumed_at": None,
                }
            ],
            "nutrition_summary_per_person": nutrition,
            "grocery_estimate": {
                "pricing_mode": "fixture",
                "complete": True,
                "purchase_total_sgd": 4,
                "consumed_total_sgd": 3,
                "weekly_budget_sgd": None,
                "within_weekly_budget": None,
                "items": [],
                "unmapped_ingredients": [],
                "warnings": [],
            },
            "warnings": [],
            "created_at": "2031-02-03T12:00:00+08:00",
        }
    )


def test_single_turn_plan_preserves_original_bytes_and_injects_product_clock(monkeypatch):
    monkeypatch.setattr(clock, "simulated", lambda: (_ for _ in ()).throw(AssertionError("No settings read")))
    harness = ConversationHarness(config())
    text = "  明天给两个人排晚餐。\n"

    def respond(message, history, instructions):
        assert message.encode() == text.encode()
        assert history == ()
        assert clock.now().isoformat() == "2031-02-03T12:00:00+08:00"
        assert config().clock_sentence in instructions
        assert "There is no saved household, plan or profile at the start of the conversation." in instructions
        return plan_output()

    result = harness.run("synthetic", [text], respond)
    assert result.final.plan is not None
    assert result.confirmation_count == 0


def test_confirmation_is_one_fixed_message_per_authored_turn_even_if_marker_repeats():
    harness = ConversationHarness(config())
    messages = []

    def respond(message, history, instructions):
        messages.append(message)
        return UnifiedOutput(awaiting_confirmation=True)

    result = harness.run("synthetic", ["first", "second"], respond)
    assert messages == ["first", CONFIRMATION_MESSAGE, "second", CONFIRMATION_MESSAGE]
    assert result.confirmation_count == harness.confirmation_counts["synthetic"] == 2
    assert sum(e.automatic_confirmation for e in result.exchanges) == 2


def test_confirmation_can_produce_a_plan():
    def respond(message, history, instructions):
        return plan_output() if message == CONFIRMATION_MESSAGE else UnifiedOutput(awaiting_confirmation=True)

    result = ConversationHarness(config()).run("synthetic", ["Plan tomorrow."], respond)
    assert result.final.plan is not None
    assert result.confirmation_count == 1


def test_question_takes_precedence_and_next_original_turn_is_still_delivered():
    def respond(message, history, instructions):
        if not history:
            return UnifiedOutput(awaiting_confirmation=True, clarification=["How many people?"])
        assert message == "Two."
        assert len(history) == 1
        return plan_output()

    result = ConversationHarness(config()).run("synthetic", ["Plan dinner.", "Two."], respond)
    assert result.confirmation_count == 0
    assert result.exchanges[0].output.clarification
    assert result.final.plan is not None


def test_second_turn_refers_to_this_systems_own_plan_and_cases_do_not_share_history():
    harness = ConversationHarness(config())

    def system(name):
        def respond(message, history, instructions):
            if not history:
                return plan_output(name)
            assert history[-1].output.plan.meals[0].dishes[0].name == name
            return plan_output(f"Changed {name}")

        return respond

    for name in ("Invented A", "Invented B", "Invented A"):
        result = harness.run(name, ["Plan dinner.", "Change that dish."], system(name))
        assert result.final.plan.meals[0].dishes[0].name == f"Changed {name}"


def test_callback_cannot_rewrite_previous_record_by_mutating_its_history_copy():
    def respond(message, history, instructions):
        if history:
            history[0].output.request_fields["household_size"] = 99
        return plan_output()

    result = ConversationHarness(config()).run("synthetic", ["first", "second"], respond)
    assert result.exchanges[0].output.request_fields["household_size"] == 2


@pytest.mark.parametrize("turns", [[], "not a list of turns", [{"gold": "not an input"}], [""]])
def test_no_episode_dictionary_or_initial_state_input(turns):
    with pytest.raises(ValueError):
        ConversationHarness(config()).run("synthetic", turns, lambda *_: pytest.fail("Must not execute"))


def test_malformed_output_and_exceptions_are_not_relabelled_as_infeasible():
    with pytest.raises(TypeError):
        ConversationHarness(config()).run("synthetic", ["first"], lambda *_: {"status": "infeasible"})

    def failing(*_):
        raise RuntimeError("synthetic apparatus failure")

    with pytest.raises(RuntimeError, match="apparatus failure"):
        ConversationHarness(config()).run("synthetic", ["first"], failing)


def test_one_shared_schema_with_coexisting_slots_and_no_category_argument():
    output = UnifiedOutput(plan=plan_output().plan, clarification=["A question"], refusal="No", answer="An answer")
    assert output.plan is not None  # a question/refusal must not erase an existing plan
    with pytest.raises(ValidationError):
        UnifiedOutput(category="a label must never select a schema")
    assert shared_instructions(config()) == shared_instructions(config())
    with pytest.raises(ValidationError):
        RuntimeConfig(anchor_date="2031-02-03", timezone="UTC")
    with pytest.raises(ValidationError):
        UnifiedOutput(awaiting_confirmation="true")


def test_product_normalizer_uses_observed_values_and_preserves_servings():
    output = normalize_product(session(plan_id=7, status="planned", can_confirm=False), product_plan())
    dish = output.plan.meals[0].dishes[0]
    assert dish.recipe_reference == "invented-bowl"
    assert dish.servings == 1.5
    assert dish.not_for == ["Synthetic member"]
    assert output.request_fields["household_size"] == 2
    assert output.plan.total_cost_sgd == 4
    assert not output.awaiting_confirmation


def test_normalizer_preserves_skip_lock_and_explicit_horizon_not_just_dates_with_dishes():
    plan = product_plan().model_copy(update={"day_count": 14, "end_date": date(2031, 2, 17)}, deep=True)
    plan.days[0].status = "skipped"
    plan.days[0].is_locked = True
    output = normalize_product(session(plan_id=7, status="planned", can_confirm=False), plan)
    assert output.plan.horizon_days == 14
    assert output.plan.start_date == date(2031, 2, 4)
    assert output.plan.end_date == date(2031, 2, 17)
    assert output.plan.meals[0].dishes[0].status == "skipped"
    assert output.plan.meals[0].dishes[0].locked is True


def test_normalizer_never_substitutes_another_plan_or_hides_a_missing_saved_plan():
    with pytest.raises(ValueError, match="actual saved plan"):
        normalize_product(session(plan_id=7))
    with pytest.raises(ValueError, match="not this session"):
        normalize_product(session(), product_plan())
    with pytest.raises(ValueError, match="actual saved plan"):
        normalize_product(session(plan_id=8), product_plan())


def test_product_question_and_marker_are_both_observed_without_clicking_confirm():
    output = normalize_product(session(clarification_questions=["Which day?"]))
    result = ConversationHarness(config()).run("product-shaped-stub", ["first"], lambda *_: output)
    assert result.confirmation_count == 0
    assert output.awaiting_confirmation and output.clarification == ["Which day?"]


@pytest.mark.parametrize("scope", [ScopeClass.OUT_OF_SCOPE, ScopeClass.RESTRICTED, ScopeClass.ADVERSARIAL])
def test_normalizer_observes_structured_scope_refusals(scope):
    decision = ScopeDecision(scope_class=scope, reason_code="synthetic")
    output = normalize_product(session(last_scope_decision=decision, can_confirm=False))
    assert output.refusal == "Ready."


@pytest.mark.parametrize("scope", [ScopeClass.OUT_OF_SCOPE, ScopeClass.DOMAIN_QUESTION, ScopeClass.SOCIAL])
def test_saved_ready_state_is_not_a_new_confirmation_invitation(scope):
    output = normalize_product(session(last_scope_decision=ScopeDecision(scope_class=scope, reason_code="synthetic")))
    result = ConversationHarness(config()).run("product-shaped-stub", ["A new question."], lambda *_: output)
    assert result.confirmation_count == 0


def test_clock_nested_restoration_on_error_and_naive_datetime_rejected(monkeypatch):
    monkeypatch.setattr(clock, "simulated", lambda: "2032-03-04T05:06")
    original = clock.now()
    with clock.frozen(config().instant):
        with pytest.raises(RuntimeError), clock.frozen(config("2033-04-05").instant):
            assert clock.today() == date(2033, 4, 5)
            raise RuntimeError("restore")
        assert clock.today() == date(2031, 2, 3)
    assert clock.now() == original
    with pytest.raises(ValueError, match="timezone"):
        with clock.frozen(datetime(2031, 2, 3)):
            pytest.fail("Naive clock accepted")


def test_concurrent_contexts_do_not_share_the_injected_clock():
    barrier = Barrier(2)

    def run(day):
        with clock.frozen(config(day).instant):
            barrier.wait(timeout=5)
            return clock.today()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(run, ("2031-02-03", "2032-03-04"))) == [date(2031, 2, 3), date(2032, 3, 4)]


def test_demo_report_is_byte_stable_and_lf_encoded(tmp_path, monkeypatch):
    files = [tmp_path / "first.json", tmp_path / "second.json"]
    for path in files:
        monkeypatch.setattr("sys.argv", ["demo", "--output", str(path)])
        demo_main()
    assert files[0].read_bytes() == files[1].read_bytes()
    assert b"\r\n" not in files[0].read_bytes()


# --- the revised shared instructions (ADR-0100 items 3 and 4, proposed) -----------------------------------------


def instructions_text():
    return shared_instructions(config())


def test_awaiting_confirmation_is_defined_with_both_cases_and_an_example():
    text = instructions_text()
    assert "Set awaiting_confirmation to true only when your reply proposes a meal plan, or a change to a plan" in text
    assert "that the user must approve before it takes effect" in text
    for false_case in ("ask for missing information", "answer a question", "refuse", "already applied the change"):
        assert false_case in text
    assert "Example: after proposing a weekly plan and asking whether to go ahead, set it to true." in text


def test_the_start_state_the_dates_and_the_sources_are_stated_plainly():
    text = instructions_text()
    assert "Initial state" not in text and "{}" not in text.split('{"')[0]
    assert 'Resolve relative dates such as "this weekend" or "next Monday" against this date.' in text
    assert "the tools or sources your registered configuration provides" in text
    assert "Use only this conversation" not in text


def test_plan_is_for_plan_requests_only():
    assert "Use plan only when the user asks for a meal plan or a change to one." in instructions_text()


def test_the_instructions_carry_no_confirmation_bytes_label_or_category():
    text = instructions_text()
    assert CONFIRMATION_MESSAGE not in text
    for word in ("planning", "intent", "multi_turn", "adversarial", "forum", "authored", "gold"):
        assert word not in text.split('{"')[0]
