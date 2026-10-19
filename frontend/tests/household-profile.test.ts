import { describe, expect, it } from "vitest";

import {
  defaultServings,
  errorDetail,
  formatPortions,
  hpbSodiumLimit,
  memberServings,
  NO_TIME_LIMIT_MINUTES,
  noGoals,
  statedTimeLimit,
  householdAllergens,
  summarizeHouseholdMembers,
  totalServings,
} from "../app/lib/household-profile";
import { basicsNote } from "../app/lib/home-surface";
import type { HouseholdMemberInput, HouseholdReference } from "../app/types/household";
import type { WeeklyGroceryEstimate } from "../app/types/meal-plan";

const reference: HouseholdReference = {
  default_servings: {
    adult: {
      female: { low: { none: 0.74 }, moderate: { none: 0.88, fat_loss: 0.79, muscle_gain: 0.88 } },
      male: { moderate: { none: 1.12, fat_loss: 1.01, muscle_gain: 1.12 }, high: { none: 1.54 } },
      any: { moderate: { none: 1, fat_loss: 0.9, muscle_gain: 1 } },
    },
    child: {
      female: { moderate: { none: 0.7, fat_loss: 0.63, muscle_gain: 0.7 } },
      male: { moderate: { none: 0.75, fat_loss: 0.68, muscle_gain: 0.75 } },
      any: { moderate: { none: 0.73, fat_loss: 0.65, muscle_gain: 0.73 } },
    },
  },
  sodium_limit_mg: { toddler: null, child: null, teen: null, adult: 2000, senior: 2000 },
  basics: [{ normalized_name: "soy_sauce", display_name: "Soy sauce", allergens: ["soy", "gluten"] }],
  meal_shares: { breakfast: 0.25, lunch: 0.35, dinner: 0.35 },
  sources: [],
};

function member(change: Partial<HouseholdMemberInput>): HouseholdMemberInput {
  return { name: "Akane", servings_per_meal: 1, allergens: [], excluded_ingredients: [], dietary_preferences: [], ...change };
}

describe("household profile constraints", () => {
  // ADR-0071 sections 1 and 2: allergens stay the household's, because one kitchen can cross-contact, while a
  // diet and the foods someone will not eat are that member's own. Merging them into one list made one
  // vegetarian member's week vegetarian for everyone.
  it("keeps allergens household-wide, each member's diet and exclusions their own, and sums planned servings", () => {
    expect(summarizeHouseholdMembers([
      member({ allergens: ["soy"], excluded_ingredients: ["mushroom"] }),
      member({ name: "Guest", servings_per_meal: 2, allergens: ["soy", "sesame"], excluded_ingredients: ["yellow_onion"], dietary_preferences: ["vegetarian"] }),
    ])).toEqual({
      planningHouseholdSize: 3,
      allergens: ["sesame", "soy"],
      members: [
        { name: "Akane", allergens: ["soy"], selfOnlyAllergens: [], excludedIngredients: ["mushroom"], dietaryPreferences: [] },
        { name: "Guest", allergens: ["sesame", "soy"], selfOnlyAllergens: [], excludedIngredients: ["yellow_onion"], dietaryPreferences: ["vegetarian"] },
      ],
    });
  });

  it("leaves an allergen only its own member avoids out of the household-wide list", () => {
    const members = [
      member({ allergens: ["peanut"], self_only_allergens: ["peanut"] }),
      member({ name: "Guest", allergens: ["sesame"] }),
    ];
    expect(householdAllergens(members)).toEqual(["sesame"]);
    // One member keeping it household-wide keeps it so for everyone.
    expect(householdAllergens([...members, member({ name: "Wei", allergens: ["peanut"] })]))
      .toEqual(["peanut", "sesame"]);
  });

  it("counts only members usually home at a meal, but every member towards the 12-portion limit", () => {
    const members = [
      member({ servings_per_meal: null, age_band: "child", sex: "female" }),
      member({ name: "Grandma", servings_per_meal: 0.8, default_present: false }),
      member({ name: "Wei", servings_per_meal: null }),
    ];
    expect(summarizeHouseholdMembers(members, reference).planningHouseholdSize).toBe(1.7);
    expect(totalServings(members, reference)).toBe(2.5);
  });
});

describe("portions from the HPB reference", () => {
  it("looks up the default by age band, sex and goal; unset reads as an adult of either sex", () => {
    expect(defaultServings(reference, { age_band: "child", sex: "male", goal: null })).toBe(0.75);
    expect(defaultServings(reference, { age_band: null, sex: null, goal: "fat_loss" })).toBe(0.9);
    expect(defaultServings(null, { age_band: "adult" })).toBeNull();
  });

  it("looks up the activity column; unset activity reads as moderate", () => {
    expect(defaultServings(reference, { age_band: "adult", sex: "male", activity: "high", goal: null })).toBe(1.54);
    expect(defaultServings(reference, { age_band: "adult", sex: "female", activity: "low" })).toBe(0.74);
    expect(defaultServings(reference, { age_band: "adult", sex: "female", activity: null })).toBe(0.88);
  });

  it("uses the stated number first, the default next, and 1 before the reference loads", () => {
    expect(memberServings(member({ servings_per_meal: 1.25, age_band: "child" }), reference)).toBe(1.25);
    expect(memberServings(member({ servings_per_meal: null, sex: "female" }), reference)).toBe(0.88);
    expect(memberServings(member({ servings_per_meal: null }), null)).toBe(1);
  });

  it("shows portions to two decimals", () => {
    expect(formatPortions(1)).toBe("1");
    expect(formatPortions(0.7 + 0.88)).toBe("1.58");
  });

  it("takes the tightest HPB sodium limit of the members usually home, or none", () => {
    expect(hpbSodiumLimit(reference, [{ age_band: "child" }, { age_band: null }])).toBe(2000);
    expect(hpbSodiumLimit(reference, [{ age_band: "child" }, { age_band: "adult", default_present: false }])).toBeNull();
  });
});

describe("API errors", () => {
  it("reads a string detail and the messages of a validation error", () => {
    expect(errorDetail({ data: { detail: "Profile changed" } }, "fallback")).toBe("Profile changed");
    expect(errorDetail({ data: { detail: [{ msg: "Value error, A presence rule names Mei, who is not a member" }] } }, "fallback"))
      .toBe("A presence rule names Mei, who is not a member");
    expect(errorDetail(new Error("offline"), "fallback")).toBe("fallback");
  });
});

describe("the grocery list's basics note", () => {
  it("shows the backend's note only when the week assumes basics at home", () => {
    const note = "Basic seasonings are assumed at home and left off this list: garlic, salt. Mark one as run out on your profile to buy it.";
    const estimate = { warnings: ["Some prices are samples.", note] } as WeeklyGroceryEstimate;
    expect(basicsNote(estimate)).toBe(note);
    expect(basicsNote({ warnings: [] } as unknown as WeeklyGroceryEstimate)).toBeNull();
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
