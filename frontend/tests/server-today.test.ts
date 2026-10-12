import { afterEach, expect, it } from "vitest";

import { setServerToday, todayIsoDate } from "../app/lib/meal-plan-format";

afterEach(() => setServerToday(null));

it("today is the server's once it has said, so the page and the planner agree on the day", () => {
  setServerToday("2026-10-19");
  expect(todayIsoDate()).toBe("2026-10-19");
  // A date asked about by name is still that date.
  expect(todayIsoDate(new Date(2026, 0, 2, 12))).toBe("2026-01-02");
});

it("without the server's word, the browser's own date stands in", () => {
  expect(todayIsoDate()).toBe(todayIsoDate(new Date()));
});
