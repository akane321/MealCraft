import type { RecipeIngredient } from "~/types/recipe";

export function formatTag(tag: string): string {
  return tag.replaceAll("-", " ");
}

export function formatNutrition(value: number, unit: "g" | "kcal" | "mg"): string {
  const roundedValue = Number.isInteger(value) ? value.toString() : value.toFixed(1);
  return `${roundedValue} ${unit}`;
}

export function formatIngredient(ingredient: RecipeIngredient): string {
  const quantity = ingredient.quantity === null
    ? ""
    : Number.isInteger(ingredient.quantity)
      ? ingredient.quantity.toString()
      : ingredient.quantity.toFixed(1);
  const amount = [quantity, ingredient.unit].filter(Boolean).join(" ");
  return [amount, ingredient.name].filter(Boolean).join(" ");
}
