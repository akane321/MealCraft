import { describe, expect, it } from "vitest";

import { formatSeconds, isConsoleAccount, linePath, niceMax, parseTaskKey, statusesIn } from "../app/lib/ops";

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
