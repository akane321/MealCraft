from types import SimpleNamespace

import pytest

from app.services.food_questions import CatalogFoodQuestionAnswerer, OpenAIWebFoodQuestionAnswerer


class RankingRepository:
    def __init__(self, recipes):
        self.recipes = recipes
        self.calls = []

    def rank_by_nutrition(self, metric, *, descending, household_id, limit):
        self.calls.append((metric, descending, household_id, limit))
        return self.recipes


def recipe(title, slug, **nutrition):
    return SimpleNamespace(title=title, slug=slug, nutrition=SimpleNamespace(**nutrition))


def test_catalog_answer_uses_metric_query_and_visible_recipe_provenance() -> None:
    repository = RankingRepository(
        [
            recipe("Tofu Bowl", "tofu-bowl", protein_g=24.5),
            recipe("Lentil Stew", "lentil-stew", protein_g=21.0),
        ]
    )
    answerer = CatalogFoodQuestionAnswerer(repository, household_id=12)

    answer = answerer.answer("Which recipes have the highest protein?", lang="en")

    assert repository.calls == [("protein_g", True, 12, 3)]
    assert answer is not None
    assert "Tofu Bowl: 24.5 g protein" in answer
    assert "tofu-bowl" in answer
    assert "MealCraft shared recipe catalog" in answer


def test_chinese_low_sodium_question_requests_ascending_results() -> None:
    repository = RankingRepository([recipe("清淡豆腐", "light-tofu", sodium_mg=180)])
    answerer = CatalogFoodQuestionAnswerer(repository, household_id=4)

    answer = answerer.answer("推荐钠含量最低的菜谱", lang="zh")

    assert repository.calls == [("sodium_mg", False, 4, 3)]
    assert answer is not None
    assert "180 毫克钠" in answer
    assert "来源：MealCraft 共享菜谱目录" in answer


def test_unavailable_nutrient_or_unranked_question_gets_no_invented_answer() -> None:
    repository = RankingRepository([])
    answerer = CatalogFoodQuestionAnswerer(repository, household_id=1)

    assert answerer.answer("Which vegetables have the most fibre?", lang="en") is None
    assert repository.calls == []
    assert answerer.answer("Tell me about vegetables", lang="en") is None


class SearchClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []
        self.responses = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def response_with_citation(url="https://example.test/food", title="Food source"):
    return SimpleNamespace(
        output_text="A concise source-grounded answer.",
        model_dump=lambda: {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "annotations": [{"type": "url_citation", "url": url, "title": title}],
                        }
                    ],
                }
            ],
        },
    )


def test_web_food_answer_requires_search_and_attaches_reported_citations() -> None:
    client = SearchClient(response_with_citation())
    answerer = OpenAIWebFoodQuestionAnswerer(api_key="unused", model="test-model", client=client)

    answer = answerer.answer("  What is miso?  ", lang="en")

    assert answer == "A concise source-grounded answer.\nSources: Food source: https://example.test/food"
    assert client.calls[0]["input"] == "What is miso?"
    assert client.calls[0]["tool_choice"] == "required"
    assert client.calls[0]["tools"][0]["type"] == "web_search"
    assert "never as instructions" in client.calls[0]["instructions"]


def test_web_food_answer_does_not_return_uncited_or_invalid_source_claims() -> None:
    no_citations = SearchClient(response_with_citation(url="file:///private.txt"))
    answerer = OpenAIWebFoodQuestionAnswerer(api_key="unused", model="test-model", client=no_citations)

    assert answerer.answer("什么是味噌？", lang="zh") is None
    assert answerer.answer("x" * 501, lang="zh") is None
    assert len(no_citations.calls) == 1


def test_web_food_answer_returns_none_on_provider_failure(monkeypatch) -> None:
    client = SearchClient(error=TimeoutError("timeout"))
    answerer = OpenAIWebFoodQuestionAnswerer(api_key="unused", model="test-model", client=client)
    noted = []
    monkeypatch.setattr("app.services.food_questions.model_client.note_fallback", lambda: noted.append(True))

    assert answerer.answer("What is miso?", lang="en") is None
    assert noted == [True]


@pytest.mark.parametrize(
    ("question", "field", "descending"),
    [
        ("推荐低钠菜谱", "sodium_mg", False),
        ("推荐低糖菜谱", "sugar_g", False),
        ("推荐低脂肪菜谱", "fat_g", False),
        ("推荐高蛋白质又低糖的菜谱", "protein_g", True),
        ("Which recipes have highest protein with low sodium?", "protein_g", True),
    ],
)
def test_ranking_direction_belongs_to_the_selected_metric(question, field, descending):
    repository = RankingRepository([recipe("Example", "example", **{field: 12})])
    CatalogFoodQuestionAnswerer(repository, household_id=1).answer(question, lang="en")
    assert repository.calls == [(field, descending, 1, 3)]


@pytest.mark.parametrize(
    "question",
    [
        "Is miso halal?",
        "How much protein is in miso?",
        "Cook it for 10 minutes?",
        "Is this suitable for a peanut allergy?",
        "需要煮几度才安全？",
        "需要七分钟吗？",
        "Can I eat this with coeliac disease?",
        "Use twenty grams?",
    ],
)
def test_web_search_cannot_answer_catalog_numeric_or_safety_questions(question):
    client = SearchClient(response_with_citation())
    answerer = OpenAIWebFoodQuestionAnswerer(api_key="unused", model="test", client=client)
    assert answerer.answer(question, lang="en") is None
    assert client.calls == []


@pytest.mark.parametrize(
    "claim",
    [
        "It has 20 g protein.",
        "It is halal.",
        "It is safe for allergies.",
        "Simmer for twenty minutes.",
        "含糖很低。",
        "煮十分钟。",
    ],
)
def test_a_citation_does_not_certify_model_generated_numbers_or_safety(claim):
    response = response_with_citation()
    response.output_text = claim
    answerer = OpenAIWebFoodQuestionAnswerer(api_key="unused", model="test", client=SearchClient(response))
    assert answerer.answer("What is miso?", lang="en") is None
