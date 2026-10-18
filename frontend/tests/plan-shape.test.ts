import { describe, expect, it } from "vitest";

import {
  DEFAULT_SHAPE,
  MEAL_PRESETS,
  describeShape,
  dishCounts,
  dishLabel,
  isFullDefault,
  isStructured,
  newDish,
  nextRoleId,
  planDayLabel,
  plannedRoles,
  presetName,
  removable,
  shapeChangeSummary,
} from "../app/lib/plan-shape";
import type { MealRole } from "../app/types/household";
import type { MealPlanShapeChange } from "../app/types/meal-plan";

describe("plan shape", () => {
  it("names presets and says a shape in plain words", () => {
    expect(presetName("dinner", MEAL_PRESETS.dinner["Main, vegetable and staple"]!)).toBe("Main, vegetable and staple");
    expect(describeShape(DEFAULT_SHAPE)).toBe("Breakfast: one dish · Lunch: full meal · Dinner: full meal (grows with the household)");
    // A saved shape of the older course form is kept and read as such.
    const older = [{ role_id: "main", courses: ["main"], required: true }, { role_id: "vegetable", courses: ["side", "salad"], required: false }] as MealRole[];
    expect(isStructured(older)).toBe(false);
    expect(presetName("dinner", older)).toBe("Custom (older format)");
    expect(describeShape({ meals: { dinner: older } })).toBe("Dinner: 2 dishes (older format)");
    const extra = [...MEAL_PRESETS.lunch["Full meal"]!, newDish("lunch", MEAL_PRESETS.lunch["Full meal"]!, "soup")];
    expect(presetName("lunch", extra)).toBe("Custom");
    expect(describeShape({ meals: { lunch: extra } })).toBe("Lunch: 4 dishes");
  });

  it("mirrors the backend's full default (ADR-0070)", () => {
    expect(Object.keys(DEFAULT_SHAPE.meals)).toEqual(["breakfast", "lunch", "dinner"]);
    expect(isFullDefault(DEFAULT_SHAPE)).toBe(true);
    expect(isFullDefault({ meals: { dinner: DEFAULT_SHAPE.meals.dinner } })).toBe(false);
    expect(DEFAULT_SHAPE.meals.lunch).toEqual([
      { role_id: "main", courses: [], required: true, meal_roles: ["protein_main", "one_bowl"] },
      { role_id: "vegetable", courses: [], required: true, meal_roles: ["vegetable", "salad"] },
      { role_id: "staple", courses: [], required: true, meal_roles: ["staple"] },
    ]);
    expect(DEFAULT_SHAPE.meals.dinner!.map(item => [item.role_id, item.min_people ?? null, item.required])).toEqual([
      ["main", null, true],
      ["main-2", 3, false],
      ["main-3", 7, false],
      ["vegetable", null, true],
      ["vegetable-2", 5, false],
      ["soup", null, false],
      ["staple", null, true],
    ]);
  });

  it("counts the dinner's dishes by the people at it, as the backend's table", () => {
    const dinner = DEFAULT_SHAPE.meals.dinner!;
    expect(dishCounts(dinner, 1)).toBe("1 protein main, 1 vegetable dish, soup and a staple");
    expect(dishCounts(dinner, 2)).toBe("1 protein main, 1 vegetable dish, soup and a staple");
    expect(dishCounts(dinner, 3)).toBe("2 protein mains, 1 vegetable dish, soup and a staple");
    expect(dishCounts(dinner, 5)).toBe("2 protein mains, 2 vegetable dishes, soup and a staple");
    expect(dishCounts(dinner, 7)).toBe("3 protein mains, 2 vegetable dishes, soup and a staple");
    expect(plannedRoles(dinner, 4).map(item => item.role_id)).toEqual(["main", "main-2", "vegetable", "soup", "staple"]);
    expect(dishCounts(DEFAULT_SHAPE.meals.breakfast!, 4)).toBe("1 breakfast dish");
    expect(dishCounts(MEAL_PRESETS.lunch["One-bowl meal"]!, 2)).toBe("1 one-bowl dish");
  });

  it("adds meal-role dishes and keeps a real meal's core and staple", () => {
    const lunch = MEAL_PRESETS.lunch["Full meal"]!;
    expect(newDish("lunch", lunch, "main")).toEqual({ role_id: "main-2", courses: [], required: true, meal_roles: ["protein_main"] });
    expect(newDish("lunch", lunch, "vegetable")).toMatchObject({ role_id: "vegetable-2", meal_roles: ["vegetable", "salad"] });
    expect(newDish("breakfast", DEFAULT_SHAPE.meals.breakfast!, "main")).toMatchObject({ role_id: "main-2", meal_roles: ["breakfast"] });
    expect(lunch.map((_, index) => removable("lunch", lunch, index))).toEqual([false, true, false]);
    // A one-bowl core brings its own staple, so the staple may go.
    const oneBowl = [...MEAL_PRESETS.lunch["One-bowl meal"]!, newDish("lunch", MEAL_PRESETS.lunch["One-bowl meal"]!, "staple")];
    expect(removable("lunch", oneBowl, 1)).toBe(true);
    expect(removable("lunch", MEAL_PRESETS.lunch["One-bowl meal"]!, 0)).toBe(false);
  });

  it("keeps the first main as main and numbers the others", () => {
    const roles = [{ role_id: "main", courses: ["main"], required: true }, { role_id: "vegetable", courses: ["side"], required: true }] as MealRole[];
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
    // Meal-role dishes by what they take.
    const labels = [...DEFAULT_SHAPE.meals.dinner!, ...MEAL_PRESETS.lunch["One-bowl meal"]!, ...DEFAULT_SHAPE.meals.breakfast!].map(dishLabel);
    expect(labels).toEqual(["Protein main", "Another protein main", "Another protein main", "Vegetable dish", "Vegetable dish", "Soup", "Staple", "One-bowl dish", "Breakfast dish"]);
  });

  it("offers the full meal first, then the fixed counts", () => {
    expect(Object.keys(MEAL_PRESETS.lunch)).toEqual(["Full meal", "One-bowl meal"]);
    expect(Object.keys(MEAL_PRESETS.dinner)).toEqual(["Full meal (grows with the household)", "Main, vegetable and staple", "Main, vegetable, soup and staple"]);
    // A count the household chose is fixed: no dish "from N people", none left out.
    for (const name of ["Main, vegetable and staple", "Main, vegetable, soup and staple"]) {
      expect(MEAL_PRESETS.dinner[name]!.every(item => item.required && !item.min_people)).toBe(true);
    }
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
    expect(shapeChangeSummary(change({ roles, removed }), start)).toBe("Dinner on Fri: Main dish, Soup, Another main");
    const withVegetable = [{ role_id: "main", courses: ["main"], required: true }, { role_id: "vegetable", courses: ["side"], required: false }, { role_id: "soup", courses: ["soup"], required: true }] as MealRole[];
    expect(shapeChangeSummary(change({ roles: withVegetable, removed }), start)).toBe("Dinner on Fri: Main dish, Vegetable dish if it fits, Soup");
    expect(shapeChangeSummary(change({ roles: withVegetable, removed: [], kept: 2 }), start)).toBe("Dinner on Fri: Main dish, Vegetable dish if it fits, Soup");
  });

  it("says a swap of dishes in their places as swaps, not as the meal's make-up", () => {
    const roles = [{ role_id: "main", courses: ["main"], required: true }, { role_id: "soup", courses: ["soup"], required: true }] as MealRole[];
    const at = (entry_id: number, day_index: number, role_id: string) => ({ entry_id, day_index, role_id }) as MealPlanShapeChange["removed"][number];
    const removed = [at(1, 2, "main"), at(2, 4, "soup")];
    const added = [at(0, 2, "main"), at(0, 4, "soup")];
    expect(shapeChangeSummary(change({ day_indexes: [2, 4], roles, removed, added }), start)).toBe("2 dishes swapped on Tue, Thu");
    expect(shapeChangeSummary(change({ day_indexes: [2], roles, removed: removed.slice(0, 1), added: added.slice(0, 1) }), start)).toBe("A dish swapped on Tue");
    // A soup in the vegetable's place is a meal made up anew.
    expect(shapeChangeSummary(change({ day_indexes: [2], roles, removed: [at(1, 2, "vegetable")], added: [at(0, 2, "soup")] }), start)).toBe("Dinner on Tue: Main dish, Soup");
  });

  it("names days by the plan's own dates, the same way wherever a change is shown", () => {
    // A week starting on Thursday: its fourth day is Sunday, never "day 4".
    expect(planDayLabel("2026-10-01", 4)).toBe("Sun");
    expect(shapeChangeSummary(change({ day_indexes: [4], roles: null }), "2026-10-01")).toBe("No dinner on Sun");
    expect(planDayLabel(null, 4)).toBe("day 4");
  });
});
