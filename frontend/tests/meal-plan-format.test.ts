import { describe, expect, it } from "vitest";

import { daysLabel, formatPlanDate, planDayName, planLabels, planRange, sentenceDay, todayIsoDate } from "../app/lib/meal-plan-format";

describe("weekly meal plan formatting", () => {
  it("formats plan dates without timezone drift", () => {
    expect(formatPlanDate("2026-09-01")).toBe("Tue, 1 Sept");
    expect(formatPlanDate("2026-09-01", { weekday: "narrow" })).toBe("T");
  });

  it("collapses a one-day plan's range to one date", () => {
    expect(planRange("2026-10-29", "2026-10-29")).toBe(formatPlanDate("2026-10-29", { day: "numeric", month: "short" }));
    expect(planRange("2026-10-29", "2026-11-04")).toMatch(/^29 Oct.* – 4 Nov/);
  });

  it("counts days and names the date number only when asked", () => {
    expect([daysLabel(1), daysLabel(3), daysLabel(14)]).toEqual(["1 day", "3 days", "14 days"]);
    expect(planDayName("2026-09-21", "long")).toBe("Monday");
    expect(planDayName("2026-09-21", "short", true)).toMatch(/^Mon.*21$/);
  });

  it("says week for a seven-day plan and plan for any other length", () => {
    expect(planLabels(7)).toMatchObject({ isWeek: true, noun: "week", Noun: "Week", budgetSuffix: "a week", budgetName: "weekly budget" });
    expect(planLabels()).toMatchObject({ isWeek: true });
    expect(planLabels(null)).toMatchObject({ isWeek: true });
    for (const days of [1, 3, 6, 14]) {
      expect(planLabels(days)).toMatchObject({ isWeek: false, noun: "plan", Noun: "Plan", budgetSuffix: "for this plan", budgetName: "plan budget" });
    }
  });

  it("names a day by weekday, and by weekday and date past seven days", () => {
    expect(sentenceDay("2026-10-22")).toBe("Thursday");
    expect(sentenceDay("2026-10-22", true)).toBe("Thursday 22 Oct");
  });

  it("returns the local ISO date", () => {
    expect(todayIsoDate(new Date("2026-09-01T08:00:00Z"))).toMatch(/^2026-09-01$/);
  });
});
