import { cumulativeNutritionValues, nutritionMetrics } from "./dashboard";
import type { NutritionDashboardDay } from "~/types/meal-plan";
import type { RecipeNutrition } from "~/types/recipe";

/** Sum already portioned, per-person dish values; skipped dishes count in neither total. */
export function nutritionForDishes(dishes: NutritionDashboardDay[]): {
  actual: RecipeNutrition;
  currentPlan: RecipeNutrition;
} {
  const total = (scope: "completed" | "planned") => Object.fromEntries(
    nutritionMetrics.map(({ key }) => [key, cumulativeNutritionValues(dishes, key, scope).at(-1) ?? 0]),
  ) as unknown as RecipeNutrition;
  return { actual: total("completed"), currentPlan: total("planned") };
}
