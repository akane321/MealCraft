import { describe, expect, it } from "vitest";

import { DEFAULT_SHAPE, MEAL_PRESETS, describeShape, dishLabel, nextRoleId, planDayLabel, presetName, shapeChangeSummary } from "../app/lib/plan-shape";
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

  it("names a dish row by what the planner does with it", () => {
    const row = (role_id: string, courses: MealRole["courses"]): MealRole => ({ role_id, courses, required: true });
    // The planner gives the vegetable role and its copies only vegetable dishes, whatever their courses.
    expect(dishLabel(row("vegetable", ["side", "salad"]))).toBe("Vegetable dish");
    expect(dishLabel(row("vegetable-2", ["main", "side", "salad"]))).toBe("Vegetable dish");
    // Any other role takes every dish of its courses, so it is not called a vegetable.
    expect(dishLabel(row("main-2", ["side"]))).toBe("Side or salad");
    expect(dishLabel(row("main", ["main", "salad", "soup"]))).toBe("Main dish");
    expect(dishLabel(row("main-2", ["main"]))).toBe("Another main");
    expect(dishLabel(row("soup", ["soup"]))).toBe("Soup");
    expect(dishLabel(row("main", ["breakfast", "baked_good"]))).toBe("Breakfast dish");
    expect(dishLabel(row("main-3", ["dessert"]))).toBe("Another dish");
  });

  it("names the lunch preset after its vegetable", () => {
    expect(Object.keys(MEAL_PRESETS.lunch)).toEqual(["One dish", "Main and a veg"]);
    expect(MEAL_PRESETS.lunch["Main and a veg"]!.map(item => item.role_id)).toEqual(["main", "vegetable"]);
  });
});

describe("shapeChangeSummary", () => {
  const change = (patch: Partial<MealPlanShapeChange>): MealPlanShapeChange => ({
    meal_type: "dinner", scope: "meal", day_indexes: [5], roles: null, removed: [], added: [], plan_shape: null, ...patch,
  });
  // A Monday, so day 5 is Friday.
  const start = "2026-09-28";

  it("says what changes and where", () => {
    expect(shapeChangeSummary(change({ meal_type: "lunch", scope: "week", roles: [], removed: [] }), start)).toBe("Lunch added for the rest of the week");
    expect(shapeChangeSummary(change({ roles: null }), start)).toBe("No dinner on Fri");
    const roles = [{ role_id: "main", courses: ["main"] }, { role_id: "soup", courses: ["soup"] }, { role_id: "main-2", courses: ["main"] }] as MealRole[];
    const removed = [{ entry_id: 1 }] as MealPlanShapeChange["removed"];
    expect(shapeChangeSummary(change({ roles, removed }), start)).toBe("Dinner on Fri: 2 mains, soup");
    const withVegetable = [{ role_id: "main", courses: ["main"], required: true }, { role_id: "vegetable", courses: ["side"], required: false }, { role_id: "soup", courses: ["soup"], required: true }] as MealRole[];
    expect(shapeChangeSummary(change({ roles: withVegetable, removed }), start)).toBe("Dinner on Fri: main, vegetable if it fits, soup");
    expect(shapeChangeSummary(change({ roles: withVegetable, removed: [], kept: 2 }), start)).toBe("Dinner on Fri: main, vegetable if it fits, soup");
  });

  it("says a swap of dishes in their places as swaps, not as the meal's make-up", () => {
    const roles = [{ role_id: "main", courses: ["main"], required: true }, { role_id: "soup", courses: ["soup"], required: true }] as MealRole[];
    const at = (entry_id: number, day_index: number, role_id: string) => ({ entry_id, day_index, role_id }) as MealPlanShapeChange["removed"][number];
    const removed = [at(1, 2, "main"), at(2, 4, "soup")];
    const added = [at(0, 2, "main"), at(0, 4, "soup")];
    expect(shapeChangeSummary(change({ day_indexes: [2, 4], roles, removed, added }), start)).toBe("2 dishes swapped on Tue, Thu");
    expect(shapeChangeSummary(change({ day_indexes: [2], roles, removed: removed.slice(0, 1), added: added.slice(0, 1) }), start)).toBe("A dish swapped on Tue");
    // A soup in the vegetable's place is a meal made up anew.
    expect(shapeChangeSummary(change({ day_indexes: [2], roles, removed: [at(1, 2, "vegetable")], added: [at(0, 2, "soup")] }), start)).toBe("Dinner on Tue: main, soup");
  });

  it("names days by the plan's own dates, the same way wherever a change is shown", () => {
    // A week starting on Thursday: its fourth day is Sunday, never "day 4".
    expect(planDayLabel("2026-10-01", 4)).toBe("Sun");
    expect(shapeChangeSummary(change({ day_indexes: [4], roles: null }), "2026-10-01")).toBe("No dinner on Sun");
    expect(planDayLabel(null, 4)).toBe("day 4");
  });
});
