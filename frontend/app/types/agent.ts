import type {
  MealPlanEventType,
  MealPlanReplanEvent,
  WeeklyMealPlan,
} from "~/types/meal-plan";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  NutritionTargetsInput,
  PricingMode,
} from "~/types/recommendation";

export type AgentSessionStatus = "collecting" | "ready" | "planned";
export type AgentParserProvider = "fixture" | "openai";

export interface AgentMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface AgentConstraintState {
  household_size: number | null;
  max_cooking_time_minutes: number;
  budget_per_meal_sgd: number | null;
  weekly_budget_sgd: number | null;
  allergens: string[];
  excluded_ingredients: string[];
  dietary_preferences: DietaryPreference[];
  health_preferences: HealthPreference[];
  nutrition_targets: NutritionTargetsInput;
  max_sodium_mg_per_meal: number | null;
  available_ingredients: AvailableIngredientInput[];
  pricing_mode: PricingMode;
}

export interface AgentReplanDraft {
  event_type: MealPlanEventType | null;
  entry_id: number | null;
  unavailable_ingredient: string | null;
  reason: string | null;
}

export interface AgentSession {
  id: number;
  status: AgentSessionStatus;
  parser_provider: AgentParserProvider;
  constraints: AgentConstraintState;
  missing_fields: string[];
  clarification_questions: string[];
  messages: AgentMessage[];
  plan_id: number | null;
  replan_draft: AgentReplanDraft;
  pending_replan: MealPlanReplanEvent | null;
  can_confirm: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentSessionCollection {
  items: AgentSession[];
}

export interface AgentConfirmation {
  session: AgentSession;
  plan: WeeklyMealPlan;
}

export interface AgentReplanConfirmation {
  session: AgentSession;
  event: MealPlanReplanEvent;
  plan: WeeklyMealPlan;
}
