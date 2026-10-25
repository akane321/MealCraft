from types import SimpleNamespace

import pytest

from app.planning.member_coverage import MemberLimits, catalog_can_eat, member_can_eat
from app.planning.recommendation_engine import RecipeRecommendationEngine
from app.schemas.planning_v2 import PlanningSlotMember


@pytest.mark.parametrize(
    "unknown,limits,reason",
    [
        ("allergens", {"allergens": ["peanut"]}, "allergen_status_unknown"),
        ("diet", {"dietary_requirements": ["vegan"]}, "dietary_status_unknown"),
    ],
)
def test_unknown_evidence_never_covers_the_restricted_member(unknown, limits, reason):
    member = PlanningSlotMember(name="Ann", servings=1, **limits)
    unrestricted = PlanningSlotMember(name="Ben", servings=1)
    recipe = SimpleNamespace(
        title="Invented vegetable bowl",
        unknown_safety=[unknown],
        allergens=[],
        ingredients=[],
        recipe_ingredients=[],
        dietary_tags=["vegan"],
    )
    assert not member_can_eat(member, recipe)
    assert not catalog_can_eat(member, recipe)
    assert member_can_eat(unrestricted, recipe)
    assert catalog_can_eat(unrestricted, recipe)

    # Recommendation explanations use the same gate, not an empty-allergen safe inference.
    described = MemberLimits(
        name=member.name,
        allergens=frozenset(member.allergens),
        excluded_ingredients=frozenset(),
        dietary_requirements=tuple(member.dietary_requirements),
    )
    assert reason in RecipeRecommendationEngine()._member_reasons(recipe, [], described)

    recipe.unknown_safety = []
    assert member_can_eat(member, recipe)
    assert catalog_can_eat(member, recipe)
