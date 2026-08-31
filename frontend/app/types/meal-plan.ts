import type { RecipeListItem, RecipeNutrition } from "~/types/recipe";
import type {
  GroceryLineEstimate,
  PricingMode,
  RecipeRecommendationRequest,
} from "~/types/recommendation";

export interface WeeklyMealPlanRequest extends RecipeRecommendationRequest {
  start_date: string;
  day_count: 7;
  weekly_budget_sgd: number | null;
}

export interface WeeklyPlanDay {
  day_index: number;
  planned_date: string;
  recipe: RecipeListItem;
  recommendation_score: number;
  nutrition_per_person: RecipeNutrition;
  consumed_cost_sgd: number;
  purchase_cost_sgd: number;
}

export type WeeklyNutritionSummary = RecipeNutrition;

export interface WeeklyGroceryEstimate {
  pricing_mode: PricingMode;
  complete: boolean;
  purchase_total_sgd: number;
  consumed_total_sgd: number | null;
  weekly_budget_sgd: number | null;
  within_weekly_budget: boolean | null;
  items: GroceryLineEstimate[];
  unmapped_ingredients: string[];
  warnings: string[];
}

export interface WeeklyMealPlan {
  id: number;
  start_date: string;
  end_date: string;
  day_count: number;
  household_size: number;
  days: WeeklyPlanDay[];
  nutrition_summary_per_person: WeeklyNutritionSummary;
  grocery_estimate: WeeklyGroceryEstimate;
  warnings: string[];
  created_at: string;
}
