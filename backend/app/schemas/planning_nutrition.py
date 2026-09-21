"""Structured product targets; natural-language interpretation belongs to Agent."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.planning_v2 import NutrientMetric


class ProductNutritionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: NutrientMetric
    lower: float | None = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    upper: float | None = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    scope: Literal["horizon_average", "per_serving"] = "horizon_average"

    @model_validator(mode="after")
    def valid_bounds(self):
        if self.lower is None and self.upper is None:
            raise ValueError("Supply at least one numeric nutrition bound")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("Lower bound cannot exceed upper bound")
        return self
