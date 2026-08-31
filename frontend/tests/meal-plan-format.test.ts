import { describe, expect, it } from "vitest";

import { formatNutrition, formatPlanDate, todayIsoDate } from "../app/lib/meal-plan-format";

describe("weekly meal plan formatting", () => {
  it("formats plan dates without timezone drift", () => {
    expect(formatPlanDate("2026-09-01")).toBe("Tue, 1 Sept");
  });

  it("formats nutrition and ISO input defaults", () => {
    expect(formatNutrition(3780.4, "kcal")).toBe("3,780 kcal");
    expect(todayIsoDate(new Date("2026-09-01T08:00:00Z"))).toMatch(/^2026-09-01$/);
  });
});
