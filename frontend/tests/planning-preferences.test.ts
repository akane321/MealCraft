import { describe, expect, it } from "vitest";
import { copyPlanningPreferences, planningPreferenceLabels } from "../app/lib/planning-preferences";

describe("planning preference confirmation labels", () => {
  it("keeps cancelled drafts and undo snapshots separate from current preferences", () => {
    const current = copyPlanningPreferences();
    current.flavor_boosts.push({ flavor: "spicy", weekdays: ["friday"], meal_types: ["dinner"] });
    const draft = copyPlanningPreferences(current);
    draft.flavor_boosts[0]!.weekdays.length = 0;
    draft.more_vegetables = true;
    expect(current.more_vegetables).toBe(false);
    expect(current.flavor_boosts[0]!.weekdays).toEqual(["friday"]);
  });
  it("shows repeat rules, scoped flavor choices, and soft goals", () => {
    expect(planningPreferenceLabels({
      repeat_allowed_meals: ["breakfast"],
      flavor_boosts: [{ flavor: "fragrant", weekdays: ["wednesday", "friday"], meal_types: ["dinner"] }],
      more_vegetables: true,
      lighter: true,
    })).toEqual([
      "breakfast can repeat",
      "Fragrant · Wed, Fri dinner",
      "More vegetables",
      "Lighter meals",
    ]);
  });

  it("shows no preference chip for an omitted default state", () => {
    expect(planningPreferenceLabels(undefined)).toEqual([]);
    expect(planningPreferenceLabels({
      repeat_allowed_meals: [],
      flavor_boosts: [],
      more_vegetables: false,
      lighter: false,
    })).toEqual([]);
  });
});
