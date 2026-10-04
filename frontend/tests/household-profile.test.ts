import { describe, expect, it } from "vitest";

import { NO_TIME_LIMIT_MINUTES, noGoals, statedTimeLimit, summarizeHouseholdMembers } from "../app/lib/household-profile";

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

describe("a new household's goals", () => {
  it("starts with no limit, budget, target or health preference it did not enter", () => {
    const goals = noGoals();
    for (const [field, value] of Object.entries(goals)) {
      expect(value, field).toEqual(field === "healthPreferences" ? [] : null);
    }
  });

  it("reads the widest time limit as none, and keeps a stated one", () => {
    expect(statedTimeLimit(NO_TIME_LIMIT_MINUTES)).toBeNull();
    expect(statedTimeLimit(null)).toBeNull();
    expect(statedTimeLimit(45)).toBe(45);
  });
});
