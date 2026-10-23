"""A household's Like, Dislike and "Never again" on recipes (ADR-0087).

The table stays append-only: a press adds a row, and a recipe's state is the kind of the household's latest row for
it. Pressing what is already the state adds nothing; undo deletes every row the household has for that recipe.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.recipe import Recipe, RecipeFeedback
from app.schemas.catalog_tags import FeedbackKind
from app.schemas.recommendation import RecipeRecommendationRequest


class RecipeFeedbackRepository:
    def __init__(self, session: Session, *, household_id: int) -> None:
        self.session = session
        self.household_id = household_id

    def latest(self) -> dict[int, RecipeFeedback]:
        """Each recipe's latest row, by recipe id."""
        # ponytail: reads every row of the household; a per-recipe latest-row query if Sprint 3 rows grow large.
        rows = self.session.scalars(
            select(RecipeFeedback).where(RecipeFeedback.household_id == self.household_id).order_by(RecipeFeedback.id)
        )
        return {row.recipe_id: row for row in rows}

    def states(self) -> dict[int, str]:
        return {recipe_id: row.kind for recipe_id, row in self.latest().items()}

    def set(self, recipe_id: int, kind: FeedbackKind) -> None:
        if self.states().get(recipe_id) == kind:
            return
        self.session.add(
            RecipeFeedback(household_id=self.household_id, recipe_id=recipe_id, kind=kind, source="button")
        )
        self.session.commit()

    def clear(self, recipe_id: int) -> None:
        self.session.execute(
            delete(RecipeFeedback).where(
                RecipeFeedback.household_id == self.household_id, RecipeFeedback.recipe_id == recipe_id
            )
        )
        self.session.commit()

    def listed(self, kind: FeedbackKind | None = None) -> list[tuple[Recipe, RecipeFeedback]]:
        """Each recipe in its current state (only `kind`, when given), latest first."""
        rows = [row for row in self.latest().values() if kind is None or row.kind == kind]
        recipes = {
            recipe.id: recipe
            for recipe in self.session.scalars(select(Recipe).where(Recipe.id.in_([row.recipe_id for row in rows])))
        }
        return [(recipes[row.recipe_id], row) for row in sorted(rows, key=lambda row: -row.id)]

    def never_again_slugs(self) -> list[str]:
        return sorted(recipe.slug for recipe, _ in self.listed("never_again"))


def with_never_again[Request: RecipeRecommendationRequest](
    constraints: Request, session: Session, household_id: int
) -> Request:
    """`constraints` with the household's live "Never again" dishes: a saved week's own copy may be stale."""
    slugs = RecipeFeedbackRepository(session, household_id=household_id).never_again_slugs()
    if slugs == constraints.never_again_recipes:
        return constraints
    return constraints.model_copy(update={"never_again_recipes": slugs})
