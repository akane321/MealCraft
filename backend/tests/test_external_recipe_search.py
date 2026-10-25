import json
from types import SimpleNamespace

import pytest

from app.services.external_recipe_search import OpenAIRecipeSearchExtractor, RecipeSearchError


def response(*, url="https://www.wikibooks.org/wiki/Tofu_Bowl", citation=True):
    extracted = {
        "title": "Ginger Tofu Bowl",
        "source_url": url,
        "servings": 2,
        "servings_basis": "stated",
        "prep_time_minutes": 15,
        "cook_time_minutes": 20,
        "passive_time_minutes": 0,
        "time_basis": "stated",
        "course": "main",
        "cuisine": "international",
        "meal_types": ["dinner"],
        "difficulty": "easy",
        "nutrition_per_serving": None,
        "ingredients": [{"name": "firm tofu", "grams": 200}],
        "steps": ["Cook the tofu with ginger and serve."],
    }
    annotations = [{"type": "url_citation", "url": url, "title": "Tofu Bowl"}] if citation else []
    return SimpleNamespace(
        output_text=json.dumps(extracted),
        model_dump=lambda: {
            "output": [{"type": "message", "content": [{"type": "output_text", "annotations": annotations}]}]
        },
    )


class FakeResponses:
    def __init__(self, result):
        self.result = result
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.result


def test_recipe_search_uses_required_web_search_and_keeps_cited_source() -> None:
    responses = FakeResponses(response())
    extractor = OpenAIRecipeSearchExtractor(
        api_key="unused", model="test-model", client=SimpleNamespace(responses=responses)
    )

    draft = extractor.search_and_extract(" ginger tofu dinner ")

    assert responses.kwargs["tools"] == [{"type": "web_search", "search_context_size": "medium"}]
    assert responses.kwargs["tool_choice"] == "required"
    assert responses.kwargs["input"] == "ginger tofu dinner"
    assert str(draft.source_url) == "https://www.wikibooks.org/wiki/Tofu_Bowl"
    assert draft.source_tier == 2
    assert draft.license == "Unverified; structured facts only; source steps paraphrased"
    assert draft.steps_basis == "rewritten"
    assert draft.ingredients[0].canonical_id is None
    assert draft.ingredients[0].allergens is None
    assert draft.retrieved_at.tzinfo is not None


def test_uncited_or_malformed_search_results_are_not_admitted_as_drafts() -> None:
    for result in (response(citation=False), SimpleNamespace(output_text="not json", model_dump=lambda: {})):
        extractor = OpenAIRecipeSearchExtractor(
            api_key="unused", model="test-model", client=SimpleNamespace(responses=FakeResponses(result))
        )
        with pytest.raises(RecipeSearchError):
            extractor.search_and_extract("ginger tofu")


def test_recipe_search_rejects_empty_or_oversized_queries_before_api_call() -> None:
    responses = FakeResponses(response())
    extractor = OpenAIRecipeSearchExtractor(
        api_key="unused", model="test-model", client=SimpleNamespace(responses=responses)
    )

    for query in ("  ", "x" * 501):
        with pytest.raises(RecipeSearchError):
            extractor.search_and_extract(query)
    assert responses.kwargs is None


def test_search_drafts_stay_tier_two_until_license_is_policy_verified() -> None:
    candidate = response(url="https://example.test/recipe")
    extractor = OpenAIRecipeSearchExtractor(
        api_key="unused", model="test-model", client=SimpleNamespace(responses=FakeResponses(candidate))
    )

    draft = extractor.search_and_extract("recipe")
    assert draft.source_tier == 2
    assert draft.license.startswith("Unverified;")


@pytest.mark.parametrize(
    "updates",
    [
        {"servings_basis": None},
        {"prep_time_minutes": 0, "cook_time_minutes": 0},
        {"steps": ["x" * 501]},
    ],
)
def test_draft_validation_errors_are_bounded_search_errors(updates):
    result = response()
    payload = json.loads(result.output_text)
    payload.update(updates)
    result.output_text = json.dumps(payload)
    extractor = OpenAIRecipeSearchExtractor(
        api_key="unused", model="test", client=SimpleNamespace(responses=FakeResponses(result))
    )
    with pytest.raises(RecipeSearchError, match="invalid recipe draft"):
        extractor.search_and_extract("ginger tofu")
