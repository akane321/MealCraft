import pytest

from app.agent.parser import RuleBasedConstraintParser
from app.schemas.agent import AgentConstraintState


def parse(message: str):
    return RuleBasedConstraintParser().parse(
        message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )


@pytest.mark.parametrize(
    ("message", "size", "weekly"),
    [
        ("Dinners for two this week, around S$90", 2, 90),
        ("Dinners for two this week, around S$90. We still have brown rice at home.", 2, 90),
        ("Cooking for a family of four, weekly budget 120", 4, 120),
        ("Three people, S$15 per meal this week", 3, None),
        ("for 2 people", 2, None),
        ("Something with twos and threes", None, None),
    ],
)
def test_household_size_and_weekly_budget_in_words(message, size, weekly) -> None:
    extraction = parse(message)
    assert extraction.household_size == size
    assert extraction.weekly_budget_sgd == weekly


@pytest.mark.parametrize(
    ("message", "excluded"),
    [
        ("Dinners for two. We don't eat pork.", ["pork"]),
        ("We don\u2019t eat pork or beef", ["pork"]),
        ("Plan for 2 people but exclude mushrooms.", ["mushroom"]),
        ("No chicken breast this week", ["chicken_breast"]),
        ("No chicken please", ["chicken"]),
        ("不要料酒", ["wine_cooking"]),
        ("不吃猪肉，不放香菜", ["cilantro", "pork"]),
        ("no alcohol at all", ["group:alcohol"]),
        ("No more than 30 minutes", None),
    ],
)
def test_common_exclusions(message, excluded) -> None:
    assert parse(message).excluded_ingredients == excluded


@pytest.mark.parametrize(
    ("message", "field", "value"),
    [
        ("Plan for 2 people and keep cooking under half an hour.", "max_cooking_time_minutes", 30),
        ("做饭一个小时以内", "max_cooking_time_minutes", 60),
        ("A S$12 budget for each dinner, serving 2 people.", "budget_per_meal_sgd", 12),
        ("S$10 per dinner", "budget_per_meal_sgd", 10),
        ("三个人，每周预算70新币", "household_size", 3),
        ("我们家四口人", "household_size", 4),
    ],
)
def test_time_budget_and_chinese_numbers(message, field, value) -> None:
    assert getattr(parse(message), field) == value


def test_a_recipe_name_that_states_an_avoided_food_counts() -> None:
    from app.planning.recommendation_engine import title_mentions

    # A release recipe can lose its main line; its name still says what it is.
    assert title_mentions("Korean Pork Chops", ["pork"]) == ["pork"]
    assert title_mentions("Peanut Noodles", ["peanut", "group:alcohol"]) == ["peanut"]
    assert title_mentions("Grilled Mushrooms", ["mushroom"]) == ["mushroom"]
    assert title_mentions("Eggplant Curry", ["egg"]) == []
    assert title_mentions("Chicken Rice", ["pork", "tree_nut"]) == []


def test_release_titles_lose_the_capital_after_an_apostrophe() -> None:
    from app.data.release_v2 import display_title

    assert display_title("Magdalena'S Empanadas") == "Magdalena's Empanadas"
    assert display_title("Morgan'S Kal-Bi (From Morgan'S)") == "Morgan's Kal-Bi (From Morgan's)"
    assert display_title("Rock 'N' Roll Stew") == "Rock 'N' Roll Stew"


@pytest.mark.parametrize(
    "message",
    ["Can tomorrow be fish instead?", "Swap tomorrow's dinner", "Skip Friday", "Don't change Sunday", "明天换成鱼"],
)
def test_follow_ups_after_a_plan_are_planning_requests(message) -> None:
    from app.orchestration.contracts import ScopeClass
    from app.orchestration.scope_policy import ReferenceScopePolicy

    assert ReferenceScopePolicy().classify(message).scope_class != ScopeClass.AMBIGUOUS


def test_instead_asks_for_a_swap() -> None:
    from app.agent.replanning import AgentReplanInterpreter

    assert AgentReplanInterpreter._event_type("can tomorrow be fish instead?") == "REPLACE_MEAL"
    assert AgentReplanInterpreter._event_type("明天换成鱼") == "REPLACE_MEAL"
    assert AgentReplanInterpreter._event_type("don't change sunday") == "LOCK_MEAL"


def test_a_run_records_the_parser_it_used() -> None:
    from types import SimpleNamespace

    from app.services.agent import AgentSessionService

    service = SimpleNamespace(parser=RuleBasedConstraintParser())
    assert AgentSessionService.model_config(service) == {"parser": "fixture", "parser_model": None}
    live = SimpleNamespace(parser=SimpleNamespace(provider="openai", model="gpt-5.4-mini"))
    config = AgentSessionService.model_config(live)
    assert config["parser_model"] == "gpt-5.4-mini"
    assert config["ingredient_vectors"].startswith("text-embedding-3-small@")
    assert "key" not in str(config).lower()


def test_the_live_parser_reply_is_a_template_not_the_models_sentence() -> None:
    from types import SimpleNamespace

    from app.agent.parser import OpenAIConstraintParser
    from app.schemas.agent import AgentConstraintExtraction

    parser = OpenAIConstraintParser.__new__(OpenAIConstraintParser)
    parser.vocabulary = None
    written = AgentConstraintExtraction(
        household_size=2, excluded_ingredients=["pork"], assistant_summary="Sure! Pork is S$1 at FairPrice."
    )
    parser.structured_model = SimpleNamespace(invoke=lambda prompt: written)
    out = parser.parse("dinners for two, no pork", current=AgentConstraintState(), acknowledged_unknowns=[], history=[])
    assert out.assistant_summary == "Got it: 2 people, no pork."
