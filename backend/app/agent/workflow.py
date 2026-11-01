from collections.abc import Callable
from datetime import timedelta
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent import replies
from app.agent.limits import Refusal
from app.agent.parser import ConstraintParser, bare_amount, read_budgets
from app.agent.plan_dates import MEAL_ORDER, default_start, read_span, read_start, reads_week
from app.agent.replies import language, say
from app.agent.shape_change import setup_shape
from app.core import clock
from app.schemas.agent import AgentConstraintExtraction, AgentConstraintState, AgentMessageResponse
from app.schemas.household_rules import HouseholdPlanning, limits_of_every_member
from app.schemas.meal_plan import MealPlanShape, default_plan_shape
from app.schemas.recommendation import AvailableIngredientInput, NutritionTargets


class AgentWorkflowState(TypedDict, total=False):
    message: str
    current_constraints: dict
    acknowledged_unknowns: list[str]
    history: list[AgentMessageResponse]
    extraction: dict
    merged_constraints: dict
    merged_acknowledged_unknowns: list[str]
    missing_fields: list[str]
    clarification_questions: list[str]
    status: str
    assistant_message: str
    language: str
    refusal: Refusal | None
    asked: str | None


BUDGET_FIELDS = {"weekly_budget_sgd", "budget_per_meal_sgd"}
# Before the assistant says it has everything: a limit no week can meet, or None (agent/limits.py).
FeasibilityCheck = Callable[[AgentConstraintState, str], Refusal | None]


class AgentConstraintWorkflow:
    def __init__(self, parser: ConstraintParser, *, check: FeasibilityCheck | None = None) -> None:
        self.parser = parser
        self.check = check
        graph = StateGraph(AgentWorkflowState)
        graph.add_node("parse_message", self._parse_message)
        graph.add_node("assess_constraints", self._assess_constraints)
        graph.add_edge(START, "parse_message")
        graph.add_edge("parse_message", "assess_constraints")
        graph.add_edge("assess_constraints", END)
        self.graph = graph.compile()

    def run(
        self,
        message: str,
        *,
        current: AgentConstraintState,
        acknowledged_unknowns: list[str],
        history: list[AgentMessageResponse],
        asked: str | None = None,
    ) -> AgentWorkflowState:
        """`asked` is the field the assistant's last question was about, if any."""
        return self.graph.invoke(
            {
                "message": message,
                "current_constraints": current.model_dump(mode="json"),
                "acknowledged_unknowns": acknowledged_unknowns,
                "history": history,
                "language": language(message, history),
                "asked": asked,
            }
        )

    def _parse_message(self, state: AgentWorkflowState) -> AgentWorkflowState:
        current = AgentConstraintState.model_validate(state["current_constraints"])
        extraction = self.parser.parse(
            state["message"],
            current=current,
            acknowledged_unknowns=state["acknowledged_unknowns"],
            history=state["history"],
        )
        return {"extraction": extraction.model_dump(mode="json")}

    def _assess_constraints(self, state: AgentWorkflowState) -> AgentWorkflowState:
        lang = state["language"]
        current = AgentConstraintState.model_validate(state["current_constraints"])
        extraction = AgentConstraintExtraction.model_validate(state["extraction"])
        asked = state.get("asked")
        if asked in BUDGET_FIELDS and extraction.weekly_budget_sgd is None and extraction.budget_per_meal_sgd is None:
            # Asked for a budget, "S$50" or 那就50新币吧 answers it, though it says neither meal nor week.
            amount = bare_amount(state["message"])
            if amount is not None:
                setattr(extraction, asked, amount)
                extraction.assistant_summary = say(
                    "got_it", lang, details=replies.details(AgentConstraintExtraction(**{asked: amount}), lang)[0]
                )
        merged = AgentConstraintWorkflow._merge_constraints(current, extraction)
        # "Next week", "from Wednesday": when the week starts, and the reply says so. "Dinner tomorrow", "this
        # weekend", "the next 3 days": the days and meals a short plan covers. "This week", "a week of dinners": the
        # household's week again. Their words are left out of what the shape reader sees, so "dinners with a soup
        # from Monday" still shapes the plan.
        notes: list[str] = []
        now, today = clock.now(), clock.today()
        message = state["message"]
        shown = merged.plan_shape or default_plan_shape()
        usual = merged.usual_plan_shape  # the household's meals, while the plan names fewer of them
        base = usual or shown
        start = read_start(message, today)
        span = read_span(message, now, tuple(meal for meal in MEAL_ORDER if meal in base.meals))
        week = reads_week(message)
        message = message.lower()
        for said in [*([start.words] if start else []), *(span.words if span else ())]:
            message = message.replace(said, " ")
        if start is not None:
            if start.start < today:
                notes.append(say("start_passed", lang, day=replies.weekday(start.start, lang)))
            merged.start_date = max(start.start, today)
        elif span is not None and span.day_count is not None:
            merged.start_date = span.start  # None: the default start, not where an earlier plan began
        if span is not None and span.moved:
            notes.append(say("span_passed", lang))
        # Rules win when they match; the model fills when they do not.
        day_count = span.day_count if span is not None and span.day_count is not None else extraction.plan_day_count
        meals = span.meals if span is not None and span.meals else extraction.plan_meals
        back = day_count is None and week
        if back:
            day_count = 7
            if start is None and current.day_count != 7:
                merged.start_date = None  # a week after a short plan starts as a week does, not where it began
        if day_count is not None:
            merged.day_count = day_count
        # "Dinners with a soup" in the request shapes the plan it sets up, and the reply says so.
        shaped = setup_shape(message, base, lang)
        if shaped is not None:
            base = shaped[0]
        keep = tuple(meals) if meals else (None if back or usual is None else tuple(shown.meals))
        if keep is not None:
            # Only these meals, each as the household composes it (one the household lacks, as the default does).
            full = default_plan_shape().meals
            merged.plan_shape = MealPlanShape(
                meals={meal: base.meals.get(meal) or full[meal] for meal in MEAL_ORDER if meal in keep}
            )
            merged.usual_plan_shape = base if set(keep) != set(base.meals) else None
        elif shaped is not None or usual is not None:
            merged.plan_shape, merged.usual_plan_shape = base, None
        if merged.start_date is None:
            planned = list((merged.plan_shape or default_plan_shape()).meals)
            merged.start_date = default_start(now, planned)
        if start is not None or day_count is not None:
            end = merged.start_date + timedelta(days=merged.day_count - 1)
            first = replies.weekday(merged.start_date, lang)
            if merged.day_count == 7:
                notes.append(say("week_runs", lang, start=first, end=replies.weekday(end, lang)))
            elif merged.day_count == 1:
                notes.append(say("plan_runs_day", lang, start=first))
            else:
                notes.append(say("plan_runs", lang, start=first, end=replies.weekday(end, lang)))
        if shaped is not None:
            notes.append(shaped[1])
        self._prorate_budget(
            merged,
            current,
            extraction,
            state["message"],
            changed=day_count is not None or bool(meals),
            notes=notes,
            lang=lang,
        )
        if notes:
            joined = ("" if lang == "zh" else " ").join(notes)
            extraction.assistant_summary = (
                f"{extraction.assistant_summary}{'' if lang == 'zh' else ' '}{joined}"
                if extraction.assistant_summary
                else joined
            )
        acknowledged = list(
            dict.fromkeys([*state["acknowledged_unknowns"], *extraction.acknowledged_unknown_quantities])
        )
        known_quantities = {item.normalized_name for item in merged.available_ingredients if item.quantity is not None}
        acknowledged = [item for item in acknowledged if item not in known_quantities]

        missing: list[str] = []
        questions: list[str] = []
        if merged.household_size is None:
            missing.append("household_size")
            questions.append(say("ask_people", lang, short=merged.day_count < 7))

        options = {item.term: item.options for item in extraction.unmatched_suggestions}
        for term in extraction.unmatched_terms:
            missing.append(f"unmatched.{term}")
            question = say("unmatched", lang, term=term)
            if options.get(term):
                names = replies.joined((replies.word(option, lang) for option in options[term]), lang)
                question += say("unmatched_options", lang, names=names)
            else:
                question += say("unmatched_open", lang)
            questions.append(question)

        for item in merged.available_ingredients:
            if item.quantity is None and item.normalized_name not in acknowledged:
                missing.append(f"available_ingredients.{item.normalized_name}.quantity")
                questions.append(say("ask_quantity", lang, name=replies.word(item.normalized_name, lang)))

        # Everything is known: before saying so, a limit no week can meet is refused with its reason.
        refusal = self.check(merged, lang) if self.check is not None and not missing else None
        aside = None
        if refusal is not None and refusal.aside:  # the week plans: said after "ready" (ADR-0067)
            aside, refusal = refusal.text, None
        if refusal is not None:
            missing, questions = [refusal.field], [refusal.text]
        status = "ready" if not missing else "collecting"
        if refusal is not None:
            parts = [refusal.text]
            if extraction.medical_request_detected:
                parts.append(say("medical", lang))
        else:
            parts = [extraction.assistant_summary or say("noted", lang)]
            if extraction.medical_request_detected:
                parts.append(say("medical", lang))
            parts.append(questions[0] if questions else say("ready", lang, short=merged.day_count < 7))
            if aside is not None:
                parts.append(aside)

        return {
            "merged_constraints": merged.model_dump(mode="json"),
            "merged_acknowledged_unknowns": acknowledged,
            "missing_fields": missing,
            "clarification_questions": questions,
            "status": status,
            "assistant_message": ("" if lang == "zh" else " ").join(parts),
            "refusal": refusal,
        }

    @staticmethod
    def _prorate_budget(
        merged: AgentConstraintState,
        current: AgentConstraintState,
        extraction: AgentConstraintExtraction,
        message: str,
        *,
        changed: bool,
        notes: list[str],
        lang: str,
    ) -> None:
        """The plan's weekly budget, from the unprorated week's (`base_weekly_budget_sgd`): the share of the week's
        meals the plan holds, every time its days or meals change, and the whole week's once it is a week again.

        An amount the message says per week ("S$140 a week") is the week's, even for a short plan. One it says for the
        plan ("S$15 for tomorrow's dinner") is the plan's, and stays so until the days or meals change."""
        base = merged.usual_plan_shape or merged.plan_shape or default_plan_shape()
        share = merged.day_count * len((merged.plan_shape or base).meals) / (7 * len(base.meals))
        weekly = current.base_weekly_budget_sgd
        if weekly is None and current.usual_plan_shape is None and current.day_count == 7:
            weekly = current.weekly_budget_sgd  # the week's, saved or stated, before any short plan
        stated = extraction.weekly_budget_sgd
        if stated is not None:
            _, found, per_week = read_budgets(message.lower(), merged.household_size, merged.day_count)
            if share >= 1 or (per_week and found is not None and abs(found - stated) < 0.005):
                weekly = stated
            else:
                merged.base_weekly_budget_sgd = weekly  # the plan's own amount; the week's is kept for a change
                return
        elif not changed:
            merged.base_weekly_budget_sgd = weekly if share < 1 else None
            return
        if weekly is None:
            return
        merged.base_weekly_budget_sgd = weekly if share < 1 else None
        merged.weekly_budget_sgd = max(round(weekly * share, 2), 0.01) if share < 1 else weekly
        if share < 1:
            notes.append(say("budget_prorated", lang, amount=merged.weekly_budget_sgd, weekly=weekly))

    @staticmethod
    def _merge_constraints(
        current: AgentConstraintState,
        extraction: AgentConstraintExtraction,
    ) -> AgentConstraintState:
        state = current.model_dump(mode="json")
        for field in (
            "household_size",
            "max_cooking_time_minutes",
            "budget_per_meal_sgd",
            "weekly_budget_sgd",
            "max_sodium_mg_per_meal",
            "pricing_mode",
            "max_uses_per_recipe",
        ):
            value = getattr(extraction, field)
            if value is not None:
                state[field] = value
        if extraction.requires_halal:
            state["requires_halal"] = True
        if (
            extraction.household_size is not None
            and extraction.household_size != current.household_size
            and state.get("household")
        ):
            # A size the conversation states wins over the saved members and who is home; the basics, time
            # rules and limits stay (layer 08). The members' own limits do not go with them: with nobody left
            # to hold a diet, an exclusion or an allergen against, each one becomes the whole household's
            # (ADR-0071 section 1 keeps a limit with its member only while that member is in the request).
            folded = limits_of_every_member(HouseholdPlanning.model_validate(state["household"]))
            state["household"] = {**state["household"], "members": None, "presence_rules": []}
            for field, values in folded.items():
                state[field] = list(dict.fromkeys([*state[field], *values]))

        for field in ("allergens", "excluded_ingredients", "dietary_preferences", "health_preferences"):
            values = getattr(extraction, field)
            if values:
                state[field] = list(dict.fromkeys([*state[field], *values]))

        if extraction.nutrition_targets is not None:
            current_targets = NutritionTargets.model_validate(state["nutrition_targets"]).model_dump()
            for field, value in extraction.nutrition_targets.model_dump().items():
                if value is not None:
                    current_targets[field] = value
            state["nutrition_targets"] = current_targets

        if extraction.available_ingredients:
            by_name = {
                item.normalized_name: item for item in AgentConstraintState.model_validate(state).available_ingredients
            }
            for item in extraction.available_ingredients:
                by_name[item.normalized_name] = AvailableIngredientInput.model_validate(item)
            state["available_ingredients"] = [item.model_dump(mode="json") for item in by_name.values()]

        if extraction.planning_preferences is not None:
            current_preferences = AgentConstraintState.model_validate(state).planning_preferences
            incoming = extraction.planning_preferences
            merged_preferences = current_preferences.model_copy(
                update={
                    "repeat_allowed_meals": list(
                        dict.fromkeys([*current_preferences.repeat_allowed_meals, *incoming.repeat_allowed_meals])
                    ),
                    "flavor_boosts": [
                        *current_preferences.flavor_boosts,
                        *[item for item in incoming.flavor_boosts if item not in current_preferences.flavor_boosts],
                    ],
                    "more_vegetables": current_preferences.more_vegetables or incoming.more_vegetables,
                    "lighter": current_preferences.lighter or incoming.lighter,
                }
            )
            state["planning_preferences"] = merged_preferences.model_dump(mode="json")

        return AgentConstraintState.model_validate(state)
