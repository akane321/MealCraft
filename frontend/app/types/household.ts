import type { WeeklyMealPlan } from "~/types/meal-plan";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  NutritionTargetsInput,
  PricingMode,
} from "~/types/recommendation";

export type AgeBand = "toddler" | "child" | "teen" | "adult" | "senior";
export type Sex = "female" | "male";
export type PersonalGoal = "fat_loss" | "muscle_gain";
export type Weekday = "monday" | "tuesday" | "wednesday" | "thursday" | "friday" | "saturday" | "sunday";

export interface HouseholdMemberInput {
  name: string;
  /** Portions a meal (0.25-3, two decimals); null is the HPB default from age band, sex and goal. */
  servings_per_meal: number | null;
  age_band?: AgeBand | null;
  sex?: Sex | null;
  goal?: PersonalGoal | null;
  /** False is an occasional guest, who eats only at the meals a presence rule adds them to. */
  default_present?: boolean;
  allergens: string[];
  excluded_ingredients: string[];
  dietary_preferences: DietaryPreference[];
}

export interface HouseholdMemberResponse extends HouseholdMemberInput {
  resolved_servings_per_meal: number;
  servings_source: "stated" | "hpb_default" | "fallback_todo";
}

export type PlannedMealType = "breakfast" | "lunch" | "dinner";

/** A confirmed sentence as a rule; empty weekdays or meal types are every one. */
interface StatedRule {
  source_text: string;
  restatement: string;
  weekdays: Weekday[];
  meal_types: PlannedMealType[];
}

export interface PresenceRule extends StatedRule {
  member_name: string;
  present: boolean;
}

export interface CookingTimeRule extends StatedRule {
  max_minutes: number;
}

export type RuleKind = "presence" | "cooking_time";
export type HouseholdRule = PresenceRule | CookingTimeRule;

export interface NutritionLimit {
  nutrient: "sodium_mg";
  scope: "per_day";
  /** null: the tightest HPB limit of the members usually home. */
  max_value: number | null;
}

export interface RuleParseRequest {
  kind: RuleKind;
  text: string;
  members: { name: string; age_band?: AgeBand | null; default_present?: boolean }[];
  speaker?: string | null;
}

export interface RuleParseResult {
  rules: HouseholdRule[];
  /** When any, the sentence was not read in full and there is nothing to confirm. */
  issues: string[];
  provider: "openai" | "rules";
  fell_back: boolean;
}

export interface BasicSeasoning {
  normalized_name: string;
  display_name: string;
  allergens: string[];
}

/** GET /api/household-profiles/reference: looked up, never recomputed, on the page. */
export interface HouseholdReference {
  /** age band -> "female" | "male" | "any" -> "none" | "fat_loss" | "muscle_gain" -> portions a meal. */
  default_servings: Record<string, Record<string, Record<string, number>>>;
  sodium_limit_mg: Record<string, number | null>;
  basics: BasicSeasoning[];
  meal_shares: Record<string, number>;
  sources: { title: string; url: string; retrieved_on: string }[];
}
export type DishCourse = "main" | "side" | "salad" | "soup" | "breakfast" | "dessert" | "snack_appetizer" | "baked_good";

/** One dish position in a meal (ADR-0036). */
export interface MealRole {
  role_id: string;
  courses: DishCourse[];
  required: boolean;
}

/** Which meals of each day are planned, and each one's dishes (ADR-0046). */
export interface PlanShape {
  meals: Partial<Record<PlannedMealType, MealRole[]>>;
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
  plan_shape?: PlanShape | null;
  presence_rules: PresenceRule[];
  cooking_time_rules: CookingTimeRule[];
  missing_basics: string[];
  nutrition_limits: NutritionLimit[];
}

export interface HouseholdProfileUpdate extends HouseholdProfileInput {
  expected_version: number;
}

export interface HouseholdProfileVersion extends Omit<HouseholdProfileInput, "name" | "members"> {
  members: HouseholdMemberResponse[];
  meal_composition?: MealRole[] | null;
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
