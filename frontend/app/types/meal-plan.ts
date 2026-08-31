import type { RecipeListItem, RecipeNutrition } from "~/types/recipe";
import type {
  GroceryLineEstimate,
  NutritionTargetsInput,
  PricingMode,
  RecipeRecommendationRequest,
} from "~/types/recommendation";

export interface WeeklyMealPlanRequest extends RecipeRecommendationRequest {
  start_date: string;
  day_count: 7;
  weekly_budget_sgd: number | null;
}

export type MealPlanEntryStatus = "planned" | "completed" | "skipped";

export interface WeeklyPlanDay {
  entry_id: number;
  day_index: number;
  planned_date: string;
  recipe: RecipeListItem;
  recommendation_score: number;
  nutrition_per_person: RecipeNutrition;
  consumed_cost_sgd: number;
  purchase_cost_sgd: number;
  status: MealPlanEntryStatus;
  consumed_at: string | null;
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

export interface WeeklyMealPlanListItem {
  id: number;
  start_date: string;
  end_date: string;
  household_size: number;
  purchase_total_sgd: number;
  consumed_total_sgd: number | null;
  within_weekly_budget: boolean | null;
  created_at: string;
}

export interface WeeklyMealPlanCollection {
  items: WeeklyMealPlanListItem[];
}

export interface MealPlanStatusCounts {
  planned: number;
  completed: number;
  skipped: number;
}

export interface NutritionDashboardDay {
  entry_id: number;
  day_index: number;
  planned_date: string;
  recipe: RecipeListItem;
  status: MealPlanEntryStatus;
  consumed_at: string | null;
  nutrition_per_person: RecipeNutrition;
}

export interface WeeklyNutritionDashboard {
  plan_id: number;
  start_date: string;
  end_date: string;
  household_size: number;
  completion_rate: number;
  status_counts: MealPlanStatusCounts;
  nutrition_targets: NutritionTargetsInput;
  planned_nutrition_per_person: WeeklyNutritionSummary;
  completed_nutrition_per_person: WeeklyNutritionSummary;
  days: NutritionDashboardDay[];
}
