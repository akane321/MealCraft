"""Recipe and package unit bases shared by grocery estimation and product parsing.

`app.evaluation.strict_success` keeps its own table on purpose: the scorer must
not share code with the planner it scores.
"""

UNIT_BASE: dict[str, tuple[str, float]] = {
    "g": ("g", 1.0),
    "kg": ("g", 1000.0),
    "ml": ("ml", 1.0),
    "l": ("ml", 1000.0),
    "tbsp": ("ml", 15.0),
    "tsp": ("ml", 5.0),
    "whole": ("whole", 1.0),
    "pc": ("whole", 1.0),
    "pcs": ("whole", 1.0),
}
