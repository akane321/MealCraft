"""Compile explicit product bounds without inferring medical targets or tolerance."""

from app.schemas.planning_v2 import PlanningNutritionBand


def compile_nutrition_targets(targets, guard_band):
    bands = []
    for target in targets:
        if target.scope == "per_serving":
            bands.append(
                PlanningNutritionBand(
                    metric=target.metric,
                    scope="per_slot",
                    lower=target.lower,
                    upper=target.upper,
                )
            )
            continue
        bands.append(
            PlanningNutritionBand(
                metric=target.metric,
                scope="horizon_average",
                average_basis="selected_slots",
                lower=target.lower,
                upper=target.upper,
            )
        )
        bands.append(
            PlanningNutritionBand(
                metric=target.metric,
                scope="per_slot",
                hard=False,
                purpose="guard",
                lower=target.lower * (1 - guard_band) if target.lower is not None else None,
                upper=target.upper * (1 + guard_band) if target.upper is not None else None,
            )
        )
    return bands


def nutrition_scope_notes(targets):
    notes = []
    labels = {
        "calories_kcal": ("Energy", "kcal"),
        "protein_g": ("Protein", "g"),
        "carbohydrate_g": ("Carbohydrate", "g"),
        "fat_g": ("Fat", "g"),
        "sodium_mg": ("Sodium", "mg"),
        "sugar_g": ("Sugar", "g"),
    }
    for target in targets:
        label, unit = labels[target.metric]
        if target.lower is not None and target.upper is not None:
            bounds = f"{target.lower:g} to {target.upper:g}"
        elif target.lower is not None:
            bounds = f"at least {target.lower:g}"
        else:
            bounds = f"at most {target.upper:g}"
        scope = "each planned meal" if target.scope == "per_serving" else "the average across planned meals"
        notes.append(f"{label}: {bounds} {unit} per person for {scope}.")
    return notes


def nutrition_guard_loss(problem, recipe):
    penalties = []
    for band in problem.nutrition_bands:
        if band.purpose != "guard":
            continue
        actual = getattr(recipe.nutrients_per_serving, band.metric)
        deviation = max(0, (band.lower or 0) - actual, actual - band.upper if band.upper is not None else 0)
        scale = max(band.lower or 0, band.upper or 0, 1)
        penalties.append(min(1, deviation / scale))
    return sum(penalties) / len(penalties) if penalties else 0.0
