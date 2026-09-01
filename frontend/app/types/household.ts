import type { WeeklyMealPlan } from "~/types/meal-plan";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  NutritionTargetsInput,
  PricingMode,
} from "~/types/recommendation";

export interface HouseholdMemberInput {
  name: string;
  servings_per_meal: number;
  allergens: string[];
  excluded_ingredients: string[];
  dietary_preferences: DietaryPreference[];
}

export interface HouseholdProfileInput {
  name: string;
  members: HouseholdMemberInput[];
  max_cooking_time_minutes: number;
  budget_per_meal_sgd: number | null;
  weekly_budget_sgd: number | null;
  health_preferences: HealthPreference[];
  nutrition_targets: NutritionTargetsInput;
  max_sodium_mg_per_meal: number | null;
  available_ingredients: AvailableIngredientInput[];
  pricing_mode: PricingMode;
}

export interface HouseholdProfileUpdate extends HouseholdProfileInput {
  expected_version: number;
}

export interface HouseholdProfileVersion extends Omit<HouseholdProfileInput, "name"> {
  version: number;
  planning_household_size: number;
  allergens: string[];
  excluded_ingredients: string[];
  dietary_preferences: DietaryPreference[];
  created_at: string;
}

export interface HouseholdProfile {
  id: number;
  name: string;
  current_version: number;
  current: HouseholdProfileVersion;
  latest_plan_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface HouseholdPlanningOverrides {
  max_cooking_time_minutes?: number | null;
  budget_per_meal_sgd?: number | null;
  weekly_budget_sgd?: number | null;
  health_preferences?: HealthPreference[] | null;
  nutrition_targets?: NutritionTargetsInput | null;
  max_sodium_mg_per_meal?: number | null;
  available_ingredients?: AvailableIngredientInput[] | null;
  pricing_mode?: PricingMode | null;
}

export interface HouseholdProfilePlanRequest {
  start_date: string;
  profile_version?: number | null;
  overrides?: HouseholdPlanningOverrides;
}

export interface ProfileConstraintChange {
  field: string;
  before: unknown;
  after: unknown;
}

export interface HouseholdProfilePlanResult {
  profile_id: number;
  profile_version: number;
  replaces_plan_id: number | null;
  constraint_changes: ProfileConstraintChange[];
  plan: WeeklyMealPlan;
}
