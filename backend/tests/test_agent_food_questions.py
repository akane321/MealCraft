from types import SimpleNamespace

from app.api.routes.agent import create_web_food_question_answerer
from app.core.config import Settings
from app.orchestration.contracts import ScopeClass, ScopeDecision
from app.services.agent import AgentSessionService, answer_saved_plan_question
from app.services.food_questions import OpenAIWebFoodQuestionAnswerer


def saved_plan():
    return SimpleNamespace(
        id=18,
        revision=3,
        nutrition_summary_per_person=SimpleNamespace(
            calories_kcal=1840.5,
            protein_g=72.25,
            carbohydrate_g=210.0,
            fat_g=61.5,
            sodium_mg=1820.0,
            sugar_g=42.0,
        ),
        days=[
            SimpleNamespace(
                day_index=2,
                meal_type="dinner",
                role_id="main",
                status="planned",
                recipe=SimpleNamespace(title="Tofu Curry", slug="tofu-curry"),
            ),
            SimpleNamespace(
                day_index=1,
                meal_type="breakfast",
                role_id="main",
                status="planned",
                recipe=SimpleNamespace(title="Oat Porridge", slug="oat-porridge"),
            ),
            SimpleNamespace(
                day_index=3,
                meal_type="dinner",
                role_id="main",
                status="skipped",
                recipe=SimpleNamespace(title="Skipped Dish", slug="skipped-dish"),
            ),
        ],
    )


def test_nutrition_answer_uses_saved_plan_values_and_names_the_scope() -> None:
    answer = answer_saved_plan_question("How much protein is in my plan?", saved_plan(), lang="en")

    assert answer == (
        "Saved plan 18, revision 3: per person across the planned week, 72.25 g protein. "
        "Source: MealCraft plan nutrition summary."
    )


def test_chinese_nutrition_answer_uses_same_tool_value() -> None:
    answer = answer_saved_plan_question("这周计划的蛋白质和热量是多少？", saved_plan(), lang="zh")

    assert answer is not None
    assert "72.25 克蛋白质" in answer
    assert "1840.5 千卡" in answer
    assert "来源：MealCraft 计划营养汇总" in answer


def test_dish_list_is_ordered_and_excludes_skipped_entries() -> None:
    answer = answer_saved_plan_question("Which dishes are in my plan?", saved_plan(), lang="en")

    assert answer is not None
    assert answer.index("Oat Porridge") < answer.index("Tofu Curry")
    assert "Skipped Dish" not in answer
    assert "MealCraft saved plan" in answer


def test_chinese_dish_list_is_grounded_and_skipped_entries_are_omitted() -> None:
    answer = answer_saved_plan_question("这周计划了哪些菜？", saved_plan(), lang="zh")

    assert answer is not None
    assert answer.index("Oat Porridge") < answer.index("Tofu Curry")
    assert "Skipped Dish" not in answer
    assert "来源：MealCraft 已保存计划" in answer


def test_unimplemented_question_shape_does_not_invent_an_answer() -> None:
    assert answer_saved_plan_question("Why was this recipe selected?", saved_plan(), lang="en") is None
    assert answer_saved_plan_question("How much protein is in tonight's dinner?", saved_plan(), lang="en") is None


def test_recipe_scaling_multiplies_only_catalog_gram_values() -> None:
    recipe = SimpleNamespace(
        title="Tofu Curry",
        slug="tofu-curry",
        recipe_ingredients=[
            SimpleNamespace(ingredient=SimpleNamespace(display_name="tofu"), grams=200),
            SimpleNamespace(ingredient=SimpleNamespace(display_name="salt"), grams=None),
        ],
    )
    repository = SimpleNamespace(get_by_slug=lambda slug: recipe if slug == recipe.slug else None)

    answer = answer_saved_plan_question(
        "How do I halve the ingredients in Tofu Curry?",
        saved_plan(),
        lang="en",
        recipe_repository=repository,
    )

    assert answer is not None
    assert "tofu: 100 g" in answer
    assert "salt: not recorded" in answer
    assert "tofu-curry" in answer


def test_chinese_recipe_scaling_uses_database_grams_and_source() -> None:
    recipe = SimpleNamespace(
        title="Tofu Curry",
        slug="tofu-curry",
        recipe_ingredients=[SimpleNamespace(ingredient=SimpleNamespace(display_name="豆腐"), grams=200)],
    )
    repository = SimpleNamespace(get_by_slug=lambda _slug: recipe)

    answer = answer_saved_plan_question(
        "《Tofu Curry》食材减半后是多少？",
        saved_plan(),
        lang="zh",
        recipe_repository=repository,
    )

    assert answer is not None
    assert "豆腐: 100 克" in answer
    assert "来源：MealCraft 菜谱目录（tofu-curry）" in answer


def test_planned_food_question_is_answered_and_persisted_without_state_mutation() -> None:
    plan = saved_plan()
    decision = ScopeDecision(
        scope_class=ScopeClass.DOMAIN_QUESTION,
        detected_intents=["answer_food_question"],
        supported_segments=["How much protein is in my plan?"],
        should_call_tools=True,
        reason_code="GROUNDED_SAVED_PLAN_QUESTION",
    )
    saved = {}
    service = AgentSessionService.__new__(AgentSessionService)
    service._change_shape = lambda *args, **kwargs: None
    service.orchestrator = SimpleNamespace(
        classify=lambda _message, history: decision,
        boundary_message=lambda _decision, _lang: "Use the saved plan.",
    )
    service.meal_plan_service = SimpleNamespace(
        get=lambda plan_id: plan if plan_id == plan.id else None,
        recipe_repository=SimpleNamespace(),
    )
    service.repository = SimpleNamespace(
        append_bounded_exchange=lambda session_id, **values: saved.update(session_id=session_id, **values) or saved
    )
    service._to_response = lambda updated: updated
    snapshot = SimpleNamespace(
        plan_id=plan.id,
        pending_interaction=None,
        messages=[],
        clarification_questions=[],
    )

    result = service._reply_to_planned(9, snapshot, "How much protein is in my plan?")

    assert result is saved
    assert "72.25 g protein" in saved["assistant_message"]
    assert saved["scope_decision"].should_mutate_state is False
    assert saved["scope_decision"].should_call_tools is True


def test_food_question_prefers_catalog_then_uses_cited_web_fallback() -> None:
    service = AgentSessionService.__new__(AgentSessionService)
    web_calls = []
    service.food_question_answerer = SimpleNamespace(answer=lambda _message, *, lang: "catalog result")
    service.web_food_question_answerer = SimpleNamespace(
        answer=lambda message, *, lang: web_calls.append((message, lang)) or "cited web result"
    )

    assert service._answer_food_question("Which recipe has most protein?", "en") == "catalog result"
    assert web_calls == []

    service.food_question_answerer = SimpleNamespace(answer=lambda _message, *, lang: None)
    assert service._answer_food_question("What is miso?", "en") == "cited web result"
    assert web_calls == [("What is miso?", "en")]


def test_live_food_search_requires_explicit_openai_provider(monkeypatch) -> None:
    settings = Settings(openai_api_key="test-key")
    monkeypatch.setattr("app.api.routes.agent.runtime_value", lambda _key, _settings, _db: "fixture")

    assert create_web_food_question_answerer(settings) is None

    monkeypatch.setattr("app.api.routes.agent.runtime_value", lambda _key, _settings, _db: "openai")
    assert isinstance(create_web_food_question_answerer(settings), OpenAIWebFoodQuestionAnswerer)
    assert create_web_food_question_answerer(Settings(agent_parser_provider="openai")) is None
