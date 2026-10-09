import { describe, expect, it } from "vitest";

import { createServiceStatuses, pricesLine } from "../app/lib/system-status";

describe("createServiceStatuses", () => {
  it("says in a household's words that planning and its saved weeks work", () => {
    const statuses = createServiceStatuses({
      status: "ok",
      service: "MealCraft",
      database: "connected",
    });

    expect(statuses).toEqual([
      { name: "Planning and the assistant", state: "Working", healthy: true },
      { name: "Your weeks and household", state: "Working", healthy: true },
    ]);
  });

  it("says both are not available when the service does not answer", () => {
    const statuses = createServiceStatuses();

    expect(statuses.map(status => status.state)).toEqual(["Not available", "Not available"]);
  });
});

describe("pricesLine", () => {
  it("never lets sample prices pass as today's FairPrice prices", () => {
    expect(pricesLine("fixture")).toMatch(/^Sample prices\. .*not today's FairPrice prices/);
    expect(pricesLine("live")).toContain("may reuse saved prices");
    expect(pricesLine("live")).toContain("selected saved or sample price is kept");
    expect(pricesLine("live")).not.toContain("Today's FairPrice prices");
    expect(pricesLine(null)).toMatch(/^Sample prices, unless/);
  });
});
