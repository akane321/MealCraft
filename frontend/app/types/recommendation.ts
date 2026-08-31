import type { RecipeListItem } from "~/types/recipe";

export type DietaryPreference = "vegetarian" | "vegan" | "gluten-free" | "dairy-free";
export type HealthPreference = "low-sodium" | "low-sugar" | "lower-calorie";
export type PricingMode = "fixture" | "live";

export interface Product {
  external_id: string;
  name: string;
  brand: string | null;
  category: string | null;
  package_size: number | null;
  package_unit: string | null;
  price_sgd: number;
  product_url: string;
  image_url: string | null;
  in_stock: boolean;
  source: "fairprice" | "fixture";
  fetched_at: string;
}

export interface ProductSearchResponse {
  query: string;
  provider_used: "fairprice" | "fixture";
  fallback_used: boolean;
  cached: boolean;
  warning: string | null;
  items: Product[];
}

export interface GroceryLineEstimate {
  ingredient_name: string;
  ingredient_display_name: string;
  required_quantity: number | null;
  unit: string | null;
  pantry_deduction: number;
  remaining_quantity: number | null;
  product: Product | null;
  match_score: number | null;
  packages_required: number;
  purchase_cost_sgd: number;
  consumed_cost_sgd: number | null;
  excess_quantity: number | null;
  note: string | null;
}

export interface GroceryEstimate {
  pricing_mode: PricingMode;
  complete: boolean;
  purchase_total_sgd: number;
  consumed_total_sgd: number | null;
  budget_per_meal_sgd: number | null;
  within_budget: boolean | null;
  items: GroceryLineEstimate[];
  unmapped_ingredients: string[];
  warnings: string[];
}

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
  pricing_mode: PricingMode;
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
  grocery_estimate: GroceryEstimate | null;
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
