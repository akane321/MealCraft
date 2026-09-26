import { describe, expect, it } from "vitest";

import { DEFAULT_SHAPE, MEAL_PRESETS, describeShape, nextRoleId, presetName } from "../app/lib/plan-shape";

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
