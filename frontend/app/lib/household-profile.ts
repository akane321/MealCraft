import type { HouseholdMemberInput, HouseholdReference } from "~/types/household";
import type { HealthPreference } from "~/types/recommendation";

/** One member's own limits, as the profile page lists them beside their name. */
export interface MemberLimitSummary {
  name: string;
  allergens: string[];
  selfOnlyAllergens: string[];
  excludedIngredients: string[];
  dietaryPreferences: string[];
}

export interface HouseholdConstraintSummary {
  planningHouseholdSize: number;
  /** Allergens the whole household avoids: every member's, less the ones only their own member avoids. */
  allergens: string[];
  /** Each member's own limits. Diets and foods someone won't eat are no longer merged into one household list. */
  members: MemberLimitSummary[];
}

type MemberBasis = Pick<HouseholdMemberInput, "age_band" | "sex" | "activity" | "goal">;

/** The HPB default portions for a member (backend reference table), or null before it loads. */
export function defaultServings(reference: HouseholdReference | null, member: MemberBasis): number | null {
  return reference?.default_servings[member.age_band ?? "adult"]?.[member.sex ?? "any"]
    ?.[member.activity ?? "moderate"]?.[member.goal ?? "none"] ?? null;
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

/** Allergens the whole household avoids: every member's, less the ones that member marked "only I avoid it".
 * One member keeping an allergen household-wide keeps it so, because one kitchen can cross-contact. */
export function householdAllergens(members: HouseholdMemberInput[]): string[] {
  const whole = members.flatMap(member =>
    member.allergens.filter(allergen => !(member.self_only_allergens ?? []).includes(allergen)));
  return [...new Set(whole)].sort();
}

/** Portions a usual meal (the members usually home; guests join only through a presence rule), the allergens
 * the whole household avoids, and each member's own limits. A diet or a food one member won't eat is that
 * member's own: a dish is served when at least one member at the meal can eat it. */
export function summarizeHouseholdMembers(members: HouseholdMemberInput[], reference: HouseholdReference | null = null): HouseholdConstraintSummary {
  return {
    planningHouseholdSize: totalServings(members.filter(member => member.default_present !== false), reference),
    allergens: householdAllergens(members),
    members: members.map(member => ({
      name: member.name,
      allergens: [...member.allergens].sort(),
      selfOnlyAllergens: [...(member.self_only_allergens ?? [])].sort(),
      excludedIngredients: [...member.excluded_ingredients].sort(),
      dietaryPreferences: [...member.dietary_preferences].sort(),
    })),
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
