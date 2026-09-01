import type { HouseholdMemberInput } from "~/types/household";

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
