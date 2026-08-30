import { describe, expect, it } from "vitest";

import { createServiceStatuses } from "../app/lib/system-status";

describe("createServiceStatuses", () => {
  it("reports all services as healthy when the backend and database are connected", () => {
    const statuses = createServiceStatuses({
      status: "ok",
      service: "MealCraft",
      database: "connected",
    });

    expect(statuses).toEqual([
      { name: "Frontend", state: "Ready", healthy: true },
      { name: "Backend API", state: "Connected", healthy: true },
      { name: "PostgreSQL", state: "Connected", healthy: true },
    ]);
  });

  it("reports backend services as unavailable when no health response exists", () => {
    const statuses = createServiceStatuses();

    expect(statuses[0]?.healthy).toBe(true);
    expect(statuses[1]?.state).toBe("Unavailable");
    expect(statuses[2]?.state).toBe("Unavailable");
  });
});
