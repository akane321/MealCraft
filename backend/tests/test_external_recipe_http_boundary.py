import pytest

from tests.test_external_recipe_intake import draft
from tests.test_recipes import recipe_client as recipe_client


@pytest.mark.parametrize("endpoint", ["intake", "search-and-intake"])
@pytest.mark.parametrize("flag", [{}, {"requires_halal": None}])
def test_external_halal_choice_is_required(recipe_client, endpoint, flag):
    payload = {"draft": draft().model_dump(mode="json")} if endpoint == "intake" else {"query": "tofu"}
    assert recipe_client.post(f"/api/external-recipes/{endpoint}", json={**payload, **flag}).status_code == 422
