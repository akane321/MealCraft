// The allergens the recipe catalog is checked against
// (data/ingredients/allergen-vocabulary.json). Offering any other allergen would
// let a user declare one that nothing filters on.
export const CHECKED_ALLERGENS = [
  "dairy",
  "egg",
  "fish",
  "gluten",
  "peanut",
  "sesame",
  "shellfish",
  "soy",
  "tree_nut",
] as const;

export function allergenLabel(value: string): string {
  return value === "tree_nut" ? "tree nuts" : value;
}
