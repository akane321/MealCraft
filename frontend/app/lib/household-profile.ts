import type { HouseholdMemberInput } from "~/types/household";
import type { HealthPreference } from "~/types/recommendation";

export interface HouseholdConstraintSummary {
  planningHouseholdSize: number;
  allergens: string[];
  excludedIngredients: string[];
  dietaryPreferences: string[];
}

export function summarizeHouseholdMembers(members: HouseholdMemberInput[]): HouseholdConstraintSummary {
  return {
    planningHouseholdSize: members.reduce((sum, member) => sum + member.servings_per_meal, 0),
    allergens: [...new Set(members.flatMap(member => member.allergens))].sort(),
    excludedIngredients: [...new Set(members.flatMap(member => member.excluded_ingredients))].sort(),
    dietaryPreferences: [...new Set(members.flatMap(member => member.dietary_preferences))].sort(),
  };
}

/** No cooking-time limit: the longest a planning request accepts (backend NO_COOKING_TIME_LIMIT). */
export const NO_TIME_LIMIT_MINUTES = 240;

/** The time limit the household stated, or null: "no limit" is stored as the widest one. */
export function statedTimeLimit(minutes: number | null | undefined): number | null {
  return typeof minutes === "number" && minutes < NO_TIME_LIMIT_MINUTES ? minutes : null;
}

export interface HouseholdGoals {
  maxCookingTimeMinutes: number | null;
  budgetPerMealSgd: number | null;
  weeklyBudgetSgd: number | null;
  healthPreferences: HealthPreference[];
  calorieTarget: number | null;
  proteinTarget: number | null;
  carbohydrateTarget: number | null;
  fatTarget: number | null;
  maxSodiumMgPerMeal: number | null;
}

/** A new household's limits and goals: none. Only what the household enters is planned for. */
export function noGoals(): HouseholdGoals {
  return {
    maxCookingTimeMinutes: null,
    budgetPerMealSgd: null,
    weeklyBudgetSgd: null,
    healthPreferences: [],
    calorieTarget: null,
    proteinTarget: null,
    carbohydrateTarget: null,
    fatTarget: null,
    maxSodiumMgPerMeal: null,
  };
}
