import { expect, it } from "vitest";
import { nutritionForDishes } from "../app/lib/nutrition-summary";
import type { NutritionDashboardDay } from "../app/types/meal-plan";

const nutrition = { calories_kcal: 240, protein_g: 21, carbohydrate_g: 18, fat_g: 9, sodium_mg: 295, sugar_g: 2.5 };
const dish = (status: NutritionDashboardDay["status"]) => ({
  status, nutrition_per_person: { ...nutrition }, portion_share: 0.5,
}) as NutritionDashboardDay;

it("sums all six already-portioned nutrients and separates actual from the current plan", () => {
  const dishes = [dish("completed"), dish("planned"), dish("skipped")];
  expect(nutritionForDishes(dishes)).toEqual({
    actual: nutrition,
    currentPlan: { calories_kcal: 480, protein_g: 42, carbohydrate_g: 36, fat_g: 18, sodium_mg: 590, sugar_g: 5 },
  });
  expect(dishes[0]!.nutrition_per_person).toEqual(nutrition);
});

it("returns zeroes for an empty or entirely skipped day or meal", () => {
  const zero = { calories_kcal: 0, protein_g: 0, carbohydrate_g: 0, fat_g: 0, sodium_mg: 0, sugar_g: 0 };
  expect(nutritionForDishes([])).toEqual({ actual: zero, currentPlan: zero });
  expect(nutritionForDishes([dish("skipped")])).toEqual({ actual: zero, currentPlan: zero });
});
