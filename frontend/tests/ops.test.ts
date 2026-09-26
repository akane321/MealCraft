import { describe, expect, it } from "vitest";

import { compareMetrics, diffFields, dishRows, formatSeconds, formatValue, isConsoleAccount, linePath, niceMax, packageGrams, parseTaskKey, splitNames, statusesIn } from "../app/lib/ops";

describe("ops console slice 2 helpers", () => {
  it("lists changed fields first and compares values, not references", () => {
    const rows = diffFields({ household_size: 2, allergens: ["peanut"], budget: 90 }, { household_size: 2, allergens: ["peanut"], budget: 120 });
    expect(rows.map(row => [row.key, row.changed])).toEqual([["budget", true], ["allergens", false], ["household_size", false]]);
    expect(diffFields(null, { a: 1 })).toEqual([{ key: "a", before: undefined, after: 1, changed: true }]);
  });

  it("matches dishes by day, meal and role and marks the swaps", () => {
    const rows = dishRows(
      [{ day: 2, meal: "dinner", role: "main", recipe: "Tofu Soba" }, { day: 1, meal: "dinner", role: "main", recipe: "Lemon Chicken" }],
      [{ day: 1, meal: "dinner", role: "main", recipe: "Lemon Chicken" }, { day: 2, meal: "dinner", role: "main", recipe: "Lemon Chicken" }, { day: 2, meal: "dinner", role: "side", recipe: "Rice" }],
    );
    expect(rows.map(row => [row.slot, row.before, row.after, row.changed])).toEqual([
      ["Day 1 dinner", "Lemon Chicken", "Lemon Chicken", false],
      ["Day 2 dinner", "Tofu Soba", "Lemon Chicken", true],
      ["Day 2 dinner (side)", null, "Rice", true],
    ]);
    expect(dishRows()).toEqual([]);
  });

  it("subtracts A from B only where both are numbers", () => {
    expect(compareMetrics({ rate: 0.95, count: 3, provider: "fixture" }, { rate: 1, count: 3, extra: 2 })).toEqual([
      { metric: "count", a: 3, b: 3, delta: 0 },
      { metric: "extra", a: undefined, b: 2, delta: null },
      { metric: "provider", a: "fixture", b: undefined, delta: null },
      { metric: "rate", a: 0.95, b: 1, delta: 0.05 },
    ]);
  });

  it("formats stored values as plain text", () => {
    expect(formatValue(null)).toBe("—");
    expect(formatValue([])).toBe("none");
    expect(formatValue(["a", 2])).toBe("a, 2");
    expect(formatValue(true)).toBe("yes");
    expect(formatValue({ width: 4 })).toBe('{"width":4}');
  });
});

describe("ops console helpers", () => {
  it("lets every console role in and keeps households out", () => {
    expect(isConsoleAccount({ user: { system_role: "admin" } })).toBe(true);
    expect(isConsoleAccount({ user: { system_role: "operator" } })).toBe(true);
    expect(isConsoleAccount({ user: { system_role: "ordinary_user" } })).toBe(false);
    expect(isConsoleAccount(null)).toBe(false);
  });

  it("rounds axis maxima up to 1, 2 or 5 times a power of ten", () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(3)).toBe(5);
    expect(niceMax(12)).toBe(20);
    expect(niceMax(50)).toBe(50);
    expect(niceMax(51)).toBe(100);
  });

  it("breaks a line at a missing day instead of drawing it at zero", () => {
    expect(linePath([1, null, 2, 2], 2, 30, 10)).toBe("M0 5M20 0L30 0");
  });

  it("orders statuses good first and failures last", () => {
    const days = [
      { day: "2026-09-25", agent_sessions: 0, agent_runs: { failed: 1, committed: 2, running: 1 }, planning_runs: {}, planning_median_seconds: null, planning_p90_seconds: null },
    ];
    expect(statusesIn(days, day => day.agent_runs)).toEqual(["committed", "running", "failed"]);
  });

  it("formats durations and task keys", () => {
    expect(formatSeconds(0.25)).toBe("250 ms");
    expect(formatSeconds(4.21)).toBe("4.2 s");
    expect(formatSeconds(null)).toBe("—");
    expect(parseTaskKey("planning-12")).toEqual({ kind: "planning", id: 12 });
    expect(parseTaskKey("evil-1")).toBeNull();
  });
});

describe("ops console slice 3 helpers", () => {
  it("splits typed names on lines and commas, Chinese ones too", () => {
    expect(splitNames("老豆腐、豆腐\n firm tofu ,beancurd，豆腐\n\n")).toEqual(["老豆腐", "豆腐", "firm tofu", "beancurd"]);
    expect(splitNames("  ")).toEqual([]);
  });

  it("reads a package in grams only from a weight", () => {
    expect(packageGrams(500, "g")).toBe(500);
    expect(packageGrams(1.2, "KG")).toBe(1200);
    expect(packageGrams(1, "l")).toBeNull();
    expect(packageGrams(null, "g")).toBeNull();
  });
});
