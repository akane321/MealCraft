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
  is_locked: boolean;
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
  revision: number;
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
  revision: number;
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
  is_locked: boolean;
  consumed_at: string | null;
  nutrition_per_person: RecipeNutrition;
}

export interface WeeklyNutritionDashboard {
  plan_id: number;
  revision: number;
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

export type MealPlanEventType = "REPLACE_MEAL" | "CANCEL_MEAL" | "LOCK_MEAL" | "ITEM_UNAVAILABLE";
export type MealPlanEventStatus = "previewed" | "applied";

export interface MealPlanEntrySnapshot {
  entry_id: number;
  recipe_id: number;
  recipe_slug: string;
  recipe_title: string;
  status: MealPlanEntryStatus;
  is_locked: boolean;
  recommendation_score: number;
}

export interface MealPlanNutritionDelta {
  calories_kcal: number;
  protein_g: number;
  carbohydrate_g: number;
  fat_g: number;
  sodium_mg: number;
  sugar_g: number;
}

export interface MealPlanGroceryDeltaLine {
  ingredient_name: string;
  ingredient_display_name: string;
  change: "added" | "removed" | "updated";
  before_required_quantity: number | null;
  after_required_quantity: number | null;
  unit: string | null;
  before_packages_required: number;
  after_packages_required: number;
  purchase_cost_delta_sgd: number;
}

export interface MealPlanReplanPreviewRequest {
  event_type: MealPlanEventType;
  entry_id: number;
  reason: string | null;
  unavailable_ingredient: string | null;
}

export interface MealPlanReplanEvent {
  id: number;
  plan_id: number;
  base_revision: number;
  applied_revision: number | null;
  event_type: MealPlanEventType;
  status: MealPlanEventStatus;
  reason: string | null;
  unavailable_ingredient: string | null;
  before_entry: MealPlanEntrySnapshot;
  after_entry: MealPlanEntrySnapshot;
  nutrition_delta: MealPlanNutritionDelta;
  grocery_delta: MealPlanGroceryDeltaLine[];
  purchase_total_delta_sgd: number;
  created_at: string;
  applied_at: string | null;
}

export interface MealPlanReplanEventCollection {
  items: MealPlanReplanEvent[];
}

export interface MealPlanReplanConfirmation {
  event: MealPlanReplanEvent;
  plan: WeeklyMealPlan;
}
