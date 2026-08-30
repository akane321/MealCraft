from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.recipe import Recipe, RecipeIngredient


class RecipeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_after(self, *, after_id: int | None, limit: int) -> list[Recipe]:
        statement: Select[tuple[Recipe]] = (
            select(Recipe).options(joinedload(Recipe.nutrition)).order_by(Recipe.id).limit(limit + 1)
        )
        if after_id is not None:
            statement = statement.where(Recipe.id > after_id)

        return list(self.session.scalars(statement).unique().all())

    def get_by_slug(self, slug: str) -> Recipe | None:
        statement = (
            select(Recipe)
            .where(Recipe.slug == slug)
            .options(
                joinedload(Recipe.nutrition),
                selectinload(Recipe.recipe_ingredients).joinedload(RecipeIngredient.ingredient),
                selectinload(Recipe.steps),
            )
        )
        return self.session.scalars(statement).unique().one_or_none()
