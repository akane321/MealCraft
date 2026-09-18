import { describe, expect, it } from "vitest";

import { budgetLine, groceryGroups, packageLabel, priceSourceLabel, tonightEntry } from "../app/lib/home-surface";
import type { NutritionDashboardDay, WeeklyGroceryEstimate } from "../app/types/meal-plan";
import type { GroceryLineEstimate } from "../app/types/recommendation";

function day(date: string, status: NutritionDashboardDay["status"]): NutritionDashboardDay {
  return { planned_date: date, status } as NutritionDashboardDay;
}

function line(name: string, cost: number, category: string | null, packages = 1): GroceryLineEstimate {
  return {
    ingredient_display_name: name,
    packages_required: packages,
    purchase_cost_sgd: cost,
    required_quantity: 300,
    unit: "g",
    product: category === null ? null : { category, package_size: 500, package_unit: "g", fetched_at: "2026-09-14T08:00:00Z" },
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
  });

  it("keeps sample and live prices distinguishable", () => {
    expect(priceSourceLabel(estimate)).toBe("Sample prices");
    const live = { ...estimate, pricing_mode: "live", items: [line("Salmon", 10.9, "Seafood")] } as WeeklyGroceryEstimate;
    expect(priceSourceLabel(live)).toMatch(/^FairPrice prices from /);
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
