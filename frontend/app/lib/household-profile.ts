import type { HouseholdMemberInput, HouseholdReference } from "~/types/household";
import type { HealthPreference } from "~/types/recommendation";

export interface HouseholdConstraintSummary {
  planningHouseholdSize: number;
  allergens: string[];
  excludedIngredients: string[];
  dietaryPreferences: string[];
}

type MemberBasis = Pick<HouseholdMemberInput, "age_band" | "sex" | "goal">;

/** The HPB default portions for a member (backend reference table), or null before it loads. */
export function defaultServings(reference: HouseholdReference | null, member: MemberBasis): number | null {
  return reference?.default_servings[member.age_band ?? "adult"]?.[member.sex ?? "any"]?.[member.goal ?? "none"] ?? null;
}

/** Portions a meal as planned: as stated, else the HPB default; 1 until the reference loads. */
export function memberServings(member: HouseholdMemberInput, reference: HouseholdReference | null = null): number {
  return member.servings_per_meal ?? defaultServings(reference, member) ?? 1;
}

/** Portions to two decimals, without trailing zeros: 1, 0.75, 1.5. */
export function formatPortions(value: number): string {
  return String(Math.round(value * 100) / 100);
}

/** The tightest HPB daily sodium limit of the members usually home, or null when HPB gives none. */
export function hpbSodiumLimit(reference: HouseholdReference | null, members: Pick<HouseholdMemberInput, "age_band" | "default_present">[]): number | null {
  const known = members
    .filter(member => member.default_present !== false)
    .map(member => reference?.sodium_limit_mg[member.age_band ?? "adult"])
    .filter((value): value is number => typeof value === "number");
  return known.length ? Math.min(...known) : null;
}

/** Portions every member could eat at once; the backend allows at most 12. */
export function totalServings(members: HouseholdMemberInput[], reference: HouseholdReference | null = null): number {
  return Math.round(members.reduce((sum, member) => sum + memberServings(member, reference), 0) * 100) / 100;
}

/** Portions a usual meal: the members usually home; guests join only through a presence rule. */
export function summarizeHouseholdMembers(members: HouseholdMemberInput[], reference: HouseholdReference | null = null): HouseholdConstraintSummary {
  return {
    planningHouseholdSize: totalServings(members.filter(member => member.default_present !== false), reference),
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

/** The API's reason, readable: a string detail, or the messages of a validation error (422). */
export function errorDetail(error: unknown, fallback: string): string {
  const value = (error as { data?: { detail?: unknown } }).data?.detail;
  if (typeof value === "string" && value) return value;
  if (Array.isArray(value)) {
    const messages = value
      .map(item => String((item as { msg?: unknown })?.msg ?? "").replace(/^Value error, /, ""))
      .filter(Boolean);
    if (messages.length) return messages.join(" ");
  }
  return fallback;
}
