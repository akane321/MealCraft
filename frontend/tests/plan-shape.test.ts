import { describe, expect, it } from "vitest";

import { DEFAULT_SHAPE, MEAL_PRESETS, describeShape, nextRoleId, presetName, shapeChangeSummary } from "../app/lib/plan-shape";
import type { MealRole } from "../app/types/household";
import type { MealPlanShapeChange } from "../app/types/meal-plan";

describe("plan shape", () => {
  it("names presets and says a shape in plain words", () => {
    expect(presetName("dinner", MEAL_PRESETS.dinner["One meat, one veg"]!)).toBe("One meat, one veg");
    expect(presetName("dinner", [{ role_id: "main", courses: ["main"], required: true }, { role_id: "main-2", courses: ["main"], required: true }])).toBe("Custom");
    expect(describeShape({ meals: { lunch: MEAL_PRESETS.lunch["One dish"]!, ...DEFAULT_SHAPE.meals } })).toBe("Lunch: one dish · Dinner: one meat, one veg");
  });

  it("keeps the first main as main and numbers the others", () => {
    const roles = MEAL_PRESETS.dinner["Meat, veg and soup"]!;
    expect(nextRoleId(roles, ["main"])).toBe("main-2");
    expect(nextRoleId([], ["main"])).toBe("main");
    expect(nextRoleId(roles, ["side", "salad"])).toBe("vegetable-2");
  });
});

describe("shapeChangeSummary", () => {
  const change = (patch: Partial<MealPlanShapeChange>): MealPlanShapeChange => ({
    meal_type: "dinner", scope: "meal", day_indexes: [5], roles: null, removed: [], added: [], plan_shape: null, ...patch,
  });
  const day = (index: number) => ["", "Mon", "Tue", "Wed", "Thu", "Fri"][index]!;

  it("says what changes and where", () => {
    expect(shapeChangeSummary(change({ meal_type: "lunch", scope: "week", roles: [], removed: [] }), day)).toBe("Lunch added for the rest of the week");
    expect(shapeChangeSummary(change({ roles: null }), day)).toBe("No dinner on Fri");
    const roles = [{ role_id: "main", courses: ["main"] }, { role_id: "soup", courses: ["soup"] }, { role_id: "main-2", courses: ["main"] }] as MealRole[];
    const removed = [{ entry_id: 1 }] as MealPlanShapeChange["removed"];
    expect(shapeChangeSummary(change({ roles, removed }), day)).toBe("Dinner on Fri: 2 mains, soup");
  });
});
