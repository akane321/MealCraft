import type { RecipeListItem } from "~/types/recipe";

export type DietaryPreference = "vegetarian" | "vegan" | "gluten-free" | "dairy-free";
export type HealthPreference = "low-sodium" | "low-sugar" | "lower-calorie";

export interface NutritionTargetsInput {
  calories_kcal: number | null;
  protein_g: number | null;
  carbohydrate_g: number | null;
  fat_g: number | null;
}

export interface AvailableIngredientInput {
  normalized_name: string;
  quantity: number | null;
  unit: string | null;
}

export interface RecipeRecommendationRequest {
  household_size: number;
  max_cooking_time_minutes: number;
  budget_per_meal_sgd: number | null;
  allergens: string[];
  excluded_ingredients: string[];
  dietary_preferences: DietaryPreference[];
  health_preferences: HealthPreference[];
  nutrition_targets: NutritionTargetsInput;
  max_sodium_mg_per_meal: number | null;
  available_ingredients: AvailableIngredientInput[];
}

export interface RecommendationScoreBreakdown {
  nutrition: number | null;
  pantry: number | null;
  time: number;
}

export interface RecipeRecommendation {
  recipe: RecipeListItem;
  total_score: number;
  score_breakdown: RecommendationScoreBreakdown;
  reasons: string[];
}

export interface ExcludedRecipe {
  id: number;
  slug: string;
  title: string;
  reasons: string[];
}

export interface RecipeRecommendationCollection {
  recommendations: RecipeRecommendation[];
  excluded: ExcludedRecipe[];
  warnings: string[];
}
