import { describe, expect, it } from "vitest";

import { summarizeHouseholdMembers } from "../app/lib/household-profile";

describe("household profile constraints", () => {
  it("merges member safety constraints and sums planned servings", () => {
    expect(summarizeHouseholdMembers([
      {
        name: "Akane",
        servings_per_meal: 1,
        allergens: ["soy"],
        excluded_ingredients: ["mushroom"],
        dietary_preferences: [],
      },
      {
        name: "Guest",
        servings_per_meal: 2,
        allergens: ["soy", "sesame"],
        excluded_ingredients: ["yellow_onion"],
        dietary_preferences: ["vegetarian"],
      },
    ])).toEqual({
      planningHouseholdSize: 3,
      allergens: ["sesame", "soy"],
      excludedIngredients: ["mushroom", "yellow_onion"],
      dietaryPreferences: ["vegetarian"],
    });
  });
});
