import type { NutritionDashboardDay } from "~/types/meal-plan";
import type { RecipeNutrition } from "~/types/recipe";

export type NutritionMetric = keyof RecipeNutrition;

export interface NutritionMetricDefinition {
  key: NutritionMetric;
  label: string;
  unit: string;
  color: string;
}

export const nutritionMetrics: NutritionMetricDefinition[] = [
  { key: "calories_kcal", label: "Calories", unit: "kcal", color: "#0969da" },
  { key: "protein_g", label: "Protein", unit: "g", color: "#168a4b" },
  { key: "carbohydrate_g", label: "Carbohydrate", unit: "g", color: "#7657d5" },
  { key: "fat_g", label: "Fat", unit: "g", color: "#c58a00" },
  { key: "sodium_mg", label: "Sodium", unit: "mg", color: "#168a9b" },
  { key: "sugar_g", label: "Sugar", unit: "g", color: "#d96321" },
];

export function completedNutritionValues(
  days: NutritionDashboardDay[],
  metric: NutritionMetric,
): Array<number | null> {
  return days.map(day => day.status === "completed" ? day.nutrition_per_person[metric] : null);
}

export function chartPointCoordinates(
  values: Array<number | null>,
  width = 760,
  height = 220,
  padding = 28,
): Array<{ x: number; y: number; value: number | null }> {
  const nonNullValues = values.filter((value): value is number => value !== null);
  const maximum = Math.max(...nonNullValues, 1);
  const usableWidth = width - padding * 2;
  const usableHeight = height - padding * 2;
  const denominator = Math.max(values.length - 1, 1);

  return values.map((value, index) => ({
    x: padding + usableWidth * index / denominator,
    y: value === null ? height - padding : padding + usableHeight * (1 - value / maximum),
    value,
  }));
}

export function lineSegments(points: Array<{ x: number; y: number; value: number | null }>): string[] {
  const segments: string[] = [];
  let current: string[] = [];
  for (const point of points) {
    if (point.value === null) {
      if (current.length > 1) segments.push(current.join(" "));
      current = [];
      continue;
    }
    current.push(`${point.x},${point.y}`);
  }
  if (current.length > 1) segments.push(current.join(" "));
  return segments;
}
