"""Meal planning.

Served by the API: `weekly_planner`, `weekly_grocery`, `grocery_estimator`,
`recommendation_engine` and `dietary_tags`.

Everything else here is the offline Planning v2 track (constraint compiler,
beam and mixed planners, oracles, package optimisation, validators, workbench).
It runs from tests and `final_scope_cli` only; no route imports it. See
`docs/design/algorithm-engineering-handoff.md`.
"""

from app.planning.recommendation_engine import RecipeRecommendationEngine

__all__ = ["RecipeRecommendationEngine"]
