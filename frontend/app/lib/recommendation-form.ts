import type { AvailableIngredientInput } from "~/types/recommendation";

export function parseExcludedIngredients(value: string): string[] {
  return [...new Set(
    value
      .split(",")
      .map(item => item.trim().toLowerCase().replaceAll(" ", "_"))
      .filter(Boolean),
  )].sort();
}

export function cleanAvailableIngredients(
  ingredients: AvailableIngredientInput[],
): AvailableIngredientInput[] {
  return ingredients
    .filter(item => item.normalized_name.trim())
    .map(item => ({
      normalized_name: item.normalized_name.trim().toLowerCase().replaceAll(" ", "_"),
      quantity: typeof item.quantity === "number" && Number.isFinite(item.quantity) ? item.quantity : null,
      unit: typeof item.quantity === "number" ? item.unit?.trim().toLowerCase() || null : null,
    }));
}

export function toOptionalNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function formatRecommendationScore(score: number): string {
  return score.toFixed(1);
}
