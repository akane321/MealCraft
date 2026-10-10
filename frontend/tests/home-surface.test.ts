import { describe, expect, it } from "vitest";

import { budgetGap, budgetLine, changedMealWhen, conversationForPlan, groceriesChange, groceryGroups, groceryPriceLabel, groceryPriceTimes, packageLabel, perDinner, previewChoices, priceSourceLabel, productSourceLabel, sameDishChange, tonightEntry } from "../app/lib/home-surface";
import type { MealPlanEntrySnapshot, MealPlanShapeChange, NutritionDashboardDay, WeeklyGroceryEstimate } from "../app/types/meal-plan";
import type { GroceryLineEstimate, ProductSearchResponse } from "../app/types/recommendation";

function day(date: string, status: NutritionDashboardDay["status"]): NutritionDashboardDay {
  return { planned_date: date, status } as NutritionDashboardDay;
}

function line(name: string, cost: number, category: string | null, packages = 1, source = "fairprice"): GroceryLineEstimate {
  return {
    ingredient_display_name: name,
    packages_required: packages,
    purchase_cost_sgd: cost,
    required_quantity: 300,
    unit: "g",
    product: category === null ? null : { category, package_size: 500, package_unit: "g", fetched_at: "2026-09-14T08:00:00Z", source },
  } as GroceryLineEstimate;
}

describe("tonightEntry", () => {
  const days = [day("2026-09-14", "completed"), day("2026-09-15", "planned"), day("2026-09-16", "planned")];

  it("prefers today's dinner", () => {
    expect(tonightEntry(days, "2026-09-15")).toEqual({ day: days[1], isToday: true });
  });

  it("falls back to the next planned dinner when today is not covered", () => {
    expect(tonightEntry(days, "2026-09-10")).toEqual({ day: days[1], isToday: false });
  });

  it("returns null when nothing is left to cook", () => {
    expect(tonightEntry([day("2026-09-14", "completed")], "2026-09-20")).toBeNull();
  });
});

describe("grocery helpers", () => {
  const estimate = { weekly_budget_sgd: 90, purchase_total_sgd: 82.6, pricing_mode: "fixture", items: [] } as unknown as WeeklyGroceryEstimate;

  it("states the budget gap in whole cents", () => {
    expect(budgetLine(estimate)).toBe("S$7.40 under your S$90.00");
    expect(budgetLine({ ...estimate, purchase_total_sgd: 95.5 })).toBe("S$5.50 over your S$90.00");
    expect(budgetLine({ ...estimate, weekly_budget_sgd: null })).toBeNull();
    expect(budgetGap(estimate)).toEqual({ amount: "S$7.40", over: false });
    expect(budgetGap({ ...estimate, purchase_total_sgd: 95.5 })).toEqual({ amount: "S$5.50", over: true });
    expect(budgetGap({ ...estimate, weekly_budget_sgd: null })).toBeNull();
  });

  it("labels prices by the source actually used, not the mode asked for", () => {
    expect(priceSourceLabel(estimate)).toBe("Sample prices");
    const live = (...sources: string[]) => ({
      ...estimate,
      pricing_mode: "live",
      items: sources.map(source => line("Salmon", 10.9, "Seafood", 1, source)),
    }) as WeeklyGroceryEstimate;
    expect(priceSourceLabel(live("fairprice"))).toMatch(/^FairPrice prices from /);
    expect(priceSourceLabel(live("fixture"))).toBe("Sample prices");
    expect(priceSourceLabel(live("fairprice", "fixture"))).toBe("FairPrice and sample prices — source shown on each item");
  });

  it("separates uncheckable samples from a timeout and keeps observation and attempt dates apart", () => {
    const item = line("Cucumber", 2.2, "Vegetables", 1, "fixture");
    item.evidence = { source: "fixture", mode: "fixture", fetched_at: "2026-09-14T08:00:00Z", price_source: "no_external_product", lookup_status: "no_external_id", checked_at: null };
    expect(groceryPriceLabel(item)).toBe("Sample price · no matching FairPrice product; not checked");
    expect(groceryPriceLabel(item)).not.toMatch(/timeout|respond/i);
    expect(groceryPriceTimes(item)).not.toContain("check attempted");
    const saved = { ...item, product: { ...item.product!, source: "fairprice" as const }, evidence: { ...item.evidence, source: "release_snapshot" as const, mode: "snapshot" as const, price_source: "snapshot" as const, lookup_status: "timeout" as const, checked_at: "2026-10-07T08:00:00Z" } };
    expect(groceryPriceLabel(saved)).toBe("Saved FairPrice price · 14 Sept · not checked live in time");
    expect(groceryPriceTimes(saved)).toMatch(/Price observed:.*14.*9.*2026.*check attempted:.*7.*10.*2026/);
    expect(groceryPriceLabel({ ...saved, evidence: { ...saved.evidence, lookup_status: "out_of_stock" } })).toContain("product marked unavailable");
    // The reviewed snapshot is stored as a "fixture" product; after a timeout it is still a saved FairPrice price.
    expect(groceryPriceLabel({ ...item, evidence: { ...item.evidence, source: "release_snapshot" as const, mode: "snapshot" as const, price_source: "snapshot", lookup_status: "timeout" } })).toBe("Saved FairPrice price · 14 Sept · not checked live in time");
    // A real sample (no snapshot, no live check) stays a sample.
    expect(groceryPriceLabel(line("Cucumber", 2.2, "Vegetables", 1, "fixture"))).toBe("Sample price");
  });

  it("says when prices were checked and how many are live, saved and sample", () => {
    const evidence = (price_source: string, lookup_status: string | null, checked_at: string | null) =>
      ({ source: "fairprice", mode: price_source, fetched_at: "2026-10-02T08:00:00Z", price_source, lookup_status, checked_at }) as GroceryLineEstimate["evidence"];
    const make = (name: string, source: "fairprice" | "fixture", ev: GroceryLineEstimate["evidence"]) => ({ ...line(name, 1, "Veg", 1, source), evidence: ev });
    const water = { ...line("Water", 0, "Veg", 0), product: null, evidence: null };
    const items = [
      make("A", "fairprice", evidence("live", "success", "2026-10-08T07:40:03Z")),
      make("B", "fairprice", evidence("live", "success", "2026-10-08T07:40:01Z")),
      make("C", "fixture", evidence("snapshot", "timeout", "2026-10-08T07:40:02Z")),
      make("D", "fixture", evidence("no_external_product", "no_external_id", null)),
      water,
    ];
    const estimate = { weekly_budget_sgd: 90, purchase_total_sgd: 4, pricing_mode: "live", items } as unknown as WeeklyGroceryEstimate;
    // 07:40 UTC is 15:40 in Singapore; the water line to skip is neither counted nor labelled "Not priced".
    expect(priceSourceLabel(estimate)).toBe("Prices checked at 15:40 · 2 live · 1 saved · 1 sample");
    expect(groceryPriceLabel(water)).toBe("Not bought · no price needed");
    expect(groceryPriceLabel({ ...water, packages_required: 1 })).toBe("Not priced");
    // A live check that got nothing must not say prices were checked.
    const none = { ...estimate, items: items.slice(2, 4) } as WeeklyGroceryEstimate;
    expect(priceSourceLabel(none)).toBe("Live prices not available at 15:40 · 1 saved · 1 sample");
    // Without any live check there is no time to show.
    expect(priceSourceLabel({ ...estimate, items: [line("Salmon", 10.9, "Seafood", 1, "fixture")] })).toBe("Sample prices");
  });

  it("says where /browse prices came from in plain words", () => {
    const result = (provider_used: "fairprice" | "fixture", cached: boolean, fallback_used = false) => ({
      query: "chicken", provider_used, cached, fallback_used, warning: "Live FairPrice lookup was unavailable (timeout)",
      items: [{ fetched_at: "2026-09-26T12:00:00Z" }],
    }) as ProductSearchResponse;
    expect(productSourceLabel(result("fixture", false))).toBe("Sample prices");
    expect(productSourceLabel(result("fixture", false, true))).toBe("Sample prices: FairPrice didn't respond");
    expect(productSourceLabel(result("fairprice", false))).toBe("FairPrice prices now");
    expect(productSourceLabel(result("fairprice", true))).toMatch(/^FairPrice prices from 26 Sep/);
    expect(productSourceLabel(result("fairprice", true, true))).toMatch(/^FairPrice prices from .+: FairPrice didn't respond$/);
    for (const label of [true, false].map(cached => productSourceLabel(result("fairprice", cached, true)))) {
      expect(label).not.toMatch(/live|cache|fixture|degraded|parser|unavailable/i);
    }
  });

  it("groups only lines that need buying, costliest first", () => {
    const groups = groceryGroups([
      line("Broccoli", 5.8, "Vegetables"),
      line("Spinach", 4.6, "Vegetables"),
      line("Rice", 3.2, "Pantry", 0),
      line("Mystery", 1, null),
    ]);
    expect(groups.map(group => group.name)).toEqual(["Other", "Vegetables"]);
    expect(groups[1]!.lines.map(item => item.ingredient_display_name)).toEqual(["Broccoli", "Spinach"]);
  });

  it("labels packages from the matched product", () => {
    expect(packageLabel(line("Broccoli", 5.8, "Vegetables", 2))).toBe("2 × 500 g");
    expect(packageLabel(line("Loose", 1, null))).toBe("300 g");
  });
});

describe("averages", () => {
  it("averages only the dinners that still count", () => {
    const eat = (kcal: number, status: NutritionDashboardDay["status"]) =>
      ({ status, nutrition_per_person: { calories_kcal: kcal, protein_g: 10 } }) as unknown as NutritionDashboardDay;
    expect(perDinner([eat(400, "completed"), eat(600, "planned"), eat(2000, "skipped")])).toEqual({ calories_kcal: 500, protein_g: 10 });
    expect(perDinner([eat(2000, "skipped")])).toBeNull();
  });
});

describe("meals by day", () => {
  const dish = (day: number, meal: "lunch" | "dinner", role: string, kcal: number, status: NutritionDashboardDay["status"] = "planned") =>
    ({ entry_id: day * 10 + (meal === "lunch" ? 0 : 5) + (role === "main" ? 0 : 1), day_index: day, planned_date: `2026-09-2${day}`, meal_type: meal, role_id: role, status, nutrition_per_person: { calories_kcal: kcal } }) as unknown as NutritionDashboardDay;

  it("groups dishes into days of meals, lunch before dinner, main first", async () => {
    const { mealsByDay } = await import("../app/lib/home-surface");
    const week = mealsByDay([dish(1, "dinner", "vegetable", 100), dish(1, "dinner", "main", 400), dish(1, "lunch", "main", 300)]);
    expect(week).toHaveLength(1);
    expect(week[0]!.meals.map(m => m.mealType)).toEqual(["lunch", "dinner"]);
    expect(week[0]!.meals[1]!.dishes.map(d => d.role_id)).toEqual(["main", "vegetable"]);
  });

  it("finds the next meal still to cook and averages per meal and per day", async () => {
    const { nextMeal, perMealAndDay } = await import("../app/lib/home-surface");
    const days = [dish(1, "lunch", "main", 300, "completed"), dish(1, "dinner", "main", 400), dish(1, "dinner", "vegetable", 100)];
    expect(nextMeal(days, "2026-09-21")).toMatchObject({ isToday: true, meal: { mealType: "dinner" } });
    expect(perMealAndDay(days)).toMatchObject({ meal: { calories_kcal: 400 }, day: { calories_kcal: 800 }, mealsPerDay: 2 });
  });
});

describe("sameDishChange", () => {
  const before = { recipe_title: "Refried Beans" } as MealPlanEntrySnapshot;

  it("reads a kept or skipped dish as what happens to it, not a swap to itself", () => {
    expect(sameDishChange({ event_type: "LOCK_MEAL", before_entry: before })).toBe("Keep Refried Beans as it is");
    expect(sameDishChange({ event_type: "CANCEL_MEAL", before_entry: before })).toBe("Skip Refried Beans");
  });

  it("leaves a swap to show both dishes", () => {
    expect(sameDishChange({ event_type: "REPLACE_MEAL", before_entry: before })).toBeNull();
    expect(sameDishChange({ event_type: "ITEM_UNAVAILABLE", before_entry: before })).toBeNull();
  });

  it("reads a kept meal as every dish it keeps", () => {
    const rice = { recipe_title: "Rice" } as MealPlanEntrySnapshot;
    const soup = { recipe_title: "Potato Soup" } as MealPlanEntrySnapshot;
    expect(sameDishChange({ event_type: "LOCK_MEAL", before_entry: before, meal_entries: [before, rice, soup] }))
      .toBe("Keep Refried Beans, Rice and Potato Soup as they are");
    expect(sameDishChange({ event_type: "LOCK_MEAL", before_entry: before, meal_entries: [] })).toBe("Keep Refried Beans as it is");
  });
});

describe("groceriesChange", () => {
  it("says the groceries stay the same rather than +S$0.00", () => {
    expect(groceriesChange(0)).toBe("groceries stay the same");
    expect(groceriesChange(2.8)).toBe("groceries +S$2.80");
    expect(groceriesChange(-4.95)).toBe("groceries −S$4.95");
  });
});

describe("previewChoices", () => {
  it("never offers \"Keep as is\" to throw a lock away", () => {
    expect(previewChoices("LOCK_MEAL")).toEqual({ confirm: "Keep it locked", discard: "Cancel" });
  });

  it("keeps the words of a swap or a skip, where \"Keep as is\" keeps the dish", () => {
    for (const type of ["REPLACE_MEAL", "CANCEL_MEAL", "ITEM_UNAVAILABLE", "CHANGE_SHAPE"] as const) {
      expect(previewChoices(type)).toEqual({ confirm: "Confirm change", discard: "Keep as is" });
    }
  });
});

describe("changedMealWhen", () => {
  const applied = { applied_at: "2026-10-04T09:00:00Z", created_at: "2026-10-04T08:59:00Z", shape_change: null };
  const dish = (day_index: number | null, meal_type?: string) => ({ day_index, meal_type, recipe_title: "Rolled Dumplings" }) as MealPlanEntrySnapshot;

  it("dates a changed dish by the plan's weekday and meal, not the day it was changed", () => {
    // The week starts on Sunday 4 Oct; day 5 is Thursday.
    expect(changedMealWhen({ ...applied, before_entry: dish(5, "lunch"), after_entry: dish(5, "lunch") }, "2026-10-04")).toBe("Thu lunch");
    expect(changedMealWhen({ ...applied, before_entry: dish(2), after_entry: null }, "2026-10-04")).toBe("Mon dinner");
  });

  it("leaves a shape change to name its own days, and an old event without a day keeps its date", () => {
    expect(changedMealWhen({ ...applied, shape_change: {} as MealPlanShapeChange, before_entry: null, after_entry: null }, "2026-10-04")).toBeNull();
    expect(changedMealWhen({ ...applied, before_entry: dish(null), after_entry: null }, "2026-10-04")).toBe("4 Oct");
  });
});

describe("conversationForPlan", () => {
  // The newest conversation first, as the recent list comes back.
  const offTopic = { id: 3, plan_id: null, can_confirm: false };
  const planner = { id: 2, plan_id: 9001, can_confirm: false };
  const older = { id: 1, plan_id: 8000, can_confirm: false };
  const readyToPlan = { id: 4, plan_id: null, can_confirm: true };

  it("reopens the conversation that planned the current week, not the newest one", () => {
    expect(conversationForPlan([offTopic, planner, older], 9001)).toBe(planner);
    expect(conversationForPlan([readyToPlan, offTopic, planner], 9001)).toBe(planner);
  });

  it("otherwise picks up a first plan interrupted before it was made", () => {
    // A new household that signed in again mid-way: no week yet, its conversation ready to plan.
    expect(conversationForPlan([offTopic, readyToPlan], null)).toBe(readyToPlan);
    expect(conversationForPlan([readyToPlan, planner], 9002)).toBe(readyToPlan);
  });

  it("opens a fresh conversation when no conversation planned the current week or is ready to", () => {
    expect(conversationForPlan([offTopic, planner], 9002)).toBeNull();
    expect(conversationForPlan([offTopic, planner], null)).toBeNull();
  });
});
