import { describe, expect, it } from "vitest";

import { formatPlanDate, todayIsoDate } from "../app/lib/meal-plan-format";

describe("weekly meal plan formatting", () => {
  it("formats plan dates without timezone drift", () => {
    expect(formatPlanDate("2026-09-01")).toBe("Tue, 1 Sept");
    expect(formatPlanDate("2026-09-01", { weekday: "narrow" })).toBe("T");
  });

  it("returns the local ISO date", () => {
    expect(todayIsoDate(new Date("2026-09-01T08:00:00Z"))).toMatch(/^2026-09-01$/);
  });
});
