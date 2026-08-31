import { describe, expect, it } from "vitest";

import {
  chartPointCoordinates,
  completedNutritionValues,
  lineSegments,
} from "../app/lib/dashboard";
import type { NutritionDashboardDay } from "../app/types/meal-plan";

const nutrition = {
  calories_kcal: 480,
  protein_g: 42,
  carbohydrate_g: 36,
  fat_g: 18,
  sodium_mg: 590,
  sugar_g: 5,
};

function day(status: NutritionDashboardDay["status"], dayIndex: number): NutritionDashboardDay {
  return {
    entry_id: dayIndex,
    day_index: dayIndex,
    planned_date: `2026-09-0${dayIndex}`,
    recipe: {
      id: dayIndex,
      slug: `recipe-${dayIndex}`,
      title: `Recipe ${dayIndex}`,
      description: "Test recipe",
      cuisine: "Test",
      meal_type: "main",
      servings: 2,
      total_time_minutes: 30,
      dietary_tags: [],
      nutrition,
    },
    status,
    consumed_at: status === "completed" ? "2026-09-01T12:00:00Z" : null,
    nutrition_per_person: nutrition,
  };
}

describe("nutrition dashboard helpers", () => {
  it("excludes planned and skipped meals from completed nutrition", () => {
    expect(completedNutritionValues(
      [day("completed", 1), day("skipped", 2), day("planned", 3)],
      "calories_kcal",
    )).toEqual([480, null, null]);
  });

  it("keeps chart coordinates finite for empty and partial weeks", () => {
    const points = chartPointCoordinates([480, null, 510, null, null, null, null]);
    expect(points).toHaveLength(7);
    expect(points.every(point => Number.isFinite(point.x) && Number.isFinite(point.y))).toBe(true);
    expect(lineSegments(points)).toEqual([]);
  });

  it("creates separate line segments across missing check-ins", () => {
    const points = chartPointCoordinates([480, 510, null, 450, 470, null, null]);
    expect(lineSegments(points)).toHaveLength(2);
  });
});
