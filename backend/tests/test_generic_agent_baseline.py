from types import SimpleNamespace

import pytest

from app.agent.ingredient_matcher import IngredientMatcher
from app.evaluation.baseline_recomputation import IngredientEvaluationFacts
from app.evaluation.generic_agent_baseline import (
    ALLOWED_TOOL_NAMES,
    SYSTEM_ID,
    LangGraphGenericAgent,
    calculator,
    create_agent,
    generate,
    render_prompt,
    run_episode,
)
from app.evaluation.pure_llm_baseline import BaselineResources
from app.schemas.planning_v2 import PlanningNutrients, PlanningProductOption

EPISODE = {
    "episode_id": "dev-agent-1",
    "scenario": {
        "user_request": "Plan Monday dinner for two people.",
        "household_profile": {"household_size": 2, "allergens": []},
        "planning_horizon": {"slots": ["mon-dinner"]},
        "recipe_candidate_slugs": ["private-recipe"],
        "fairprice_product_ids": ["private-product"],
    },
    "gold": {"class": "feasible", "secret": "private-label"},
}


def response() -> dict:
    return {
        "episode_id": "dev-agent-1",
        "system_id": SYSTEM_ID,
        "status": "plan",
        "plan": {
            "meals": [
                {
                    "slot_id": "mon-dinner",
                    "role_id": "main",
                    "dishes": [
                        {
                            "name": "Tofu rice",
                            "cooking_time_minutes": 25,
                            "ingredients": [
                                {"name": "tofu", "quantity_g": 200},
                                {"name": "rice", "quantity_g": 300},
                            ],
                        }
                    ],
                }
            ]
        },
    }


class MockAgent:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return next(self.answers)


class MockGraph:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    def invoke(self, value):
        self.inputs.append(value)
        return self.result


def resources() -> BaselineResources:
    nutrients = PlanningNutrients(
        calories_kcal=100,
        protein_g=10,
        carbohydrate_g=20,
        fat_g=5,
        sodium_mg=50,
        sugar_g=2,
    )
    names = {"tofu": "Tofu", "rice": "Rice"}
    return BaselineResources(
        names=names,
        aliases={},
        matcher=IngredientMatcher(names, mode="spelling"),
        ingredient_facts={
            "tofu": IngredientEvaluationFacts(("soy",), nutrients),
            "rice": IngredientEvaluationFacts((), nutrients),
        },
        frozen_products=[
            PlanningProductOption(
                ingredient_id="tofu",
                product_id="tofu-200",
                package_quantity=200,
                package_unit="g",
                price_sgd=2,
                available=True,
            ),
            PlanningProductOption(
                ingredient_id="rice",
                product_id="rice-500",
                package_quantity=500,
                package_unit="g",
                price_sgd=3,
                available=True,
            ),
        ],
        not_purchased=frozenset(),
    )


def test_prompt_exposes_household_input_but_no_private_evaluation_data():
    prompt = render_prompt(EPISODE)

    assert "Plan Monday dinner for two people" in prompt
    assert "private-recipe" not in prompt
    assert "private-product" not in prompt
    assert "private-label" not in prompt
    assert "web\nsearch and calculator" in prompt
    assert "no MealCraft recipe catalog" in prompt
    assert ALLOWED_TOOL_NAMES == {"web_search", "calculator"}


def test_calculator_accepts_arithmetic_and_rejects_code():
    assert calculator.invoke({"expression": "(200 * 2 + 300) / 7"}) == "100.0"

    with pytest.raises(ValueError, match="arithmetic expressions only"):
        calculator.invoke({"expression": "__import__('os').getcwd()"})


def test_agent_uses_configured_baseline_model_and_only_generic_tools(monkeypatch):
    import app.evaluation.generic_agent_baseline as baseline

    captured = {}

    class Secret:
        def get_secret_value(self):
            return "test-key"

    class FakeModel:
        def __init__(self, **kwargs):
            captured["model_kwargs"] = kwargs

    def fake_graph(model, *, tools, response_format, version):
        captured.update(model=model, tools=tools, response_format=response_format, version=version)
        return object()

    settings = SimpleNamespace(
        openai_api_key=Secret(),
        openai_model="same-mini-model",
        openai_timeout_seconds=30,
    )
    monkeypatch.setattr(baseline, "get_settings", lambda: settings)
    monkeypatch.setattr(baseline, "ChatOpenAI", FakeModel)
    monkeypatch.setattr(baseline, "create_react_agent", fake_graph)
    monkeypatch.setattr(baseline.model_client, "http_client", lambda: "shared-client")

    agent = create_agent()

    assert isinstance(agent, LangGraphGenericAgent)
    assert captured["model_kwargs"]["model"] == "same-mini-model"
    assert captured["model_kwargs"]["http_client"] == "shared-client"
    assert captured["tools"][0] == {"type": "web_search"}
    assert captured["tools"][1].name == "calculator"
    assert captured["response_format"] is baseline.BaselineResponse


def test_langgraph_adapter_returns_structured_response_and_combined_usage():
    graph = MockGraph(
        {
            "structured_response": response(),
            "messages": [
                SimpleNamespace(
                    usage_metadata={"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
                    response_metadata={},
                ),
                SimpleNamespace(
                    usage_metadata={"input_tokens": 8, "output_tokens": 7, "total_tokens": 15},
                    response_metadata={},
                ),
            ],
        }
    )

    result = LangGraphGenericAgent(graph).invoke("plan")

    assert result["parsed"] == response()
    assert result["raw"].usage_metadata == {
        "input_tokens": 18,
        "output_tokens": 10,
        "total_tokens": 28,
    }
    assert graph.inputs == [{"messages": [("user", "plan")]}]


def test_malformed_agent_output_retries_whole_run_with_shared_usage_policy():
    agent = MockAgent(
        [
            {
                "parsed": None,
                "raw": SimpleNamespace(usage_metadata={"total_tokens": 20}, response_metadata={}),
                "parsing_error": "bad output",
            },
            {
                "parsed": response(),
                "raw": SimpleNamespace(usage_metadata={"total_tokens": 30, "cost_usd": 0.03}, response_metadata={}),
            },
        ]
    )

    result = generate(EPISODE, agent)

    assert result.response is not None
    assert result.attempts == 2
    assert result.usage.total_tokens == 30
    assert result.usage.cost_usd == 0.03
    assert agent.prompts[0] == agent.prompts[1]


def test_final_output_uses_private_data_only_in_shared_evaluator_pipeline():
    agent = MockAgent([{"parsed": response(), "raw": SimpleNamespace()}])

    result = run_episode(EPISODE, agent=agent, resources=resources())

    assert result.system_id == SYSTEM_ID
    assert result.valid_output is True
    assert result.coverage is not None and result.coverage.coverage == 1
    assert result.verification is not None and result.verification.verifiable is True
    assert result.recomputation is not None
    assert result.recomputation.allergens == ("soy",)
    assert result.recomputation.purchase_total_sgd == 5
