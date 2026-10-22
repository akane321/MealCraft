from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BaselineStatus = Literal["plan", "clarification", "infeasible"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BaselineIngredient(StrictModel):
    name: str
    quantity_g: float = Field(gt=0)


class BaselineDish(StrictModel):
    name: str
    cooking_time_minutes: int = Field(ge=0)
    ingredients: list[BaselineIngredient]


class BaselineMeal(StrictModel):
    slot_id: str
    role_id: str | None = None
    dishes: list[BaselineDish]


class BaselinePlan(StrictModel):
    meals: list[BaselineMeal]


class BaselineResponse(StrictModel):
    episode_id: str
    system_id: str
    status: BaselineStatus
    plan: BaselinePlan | None = None
