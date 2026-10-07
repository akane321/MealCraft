import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

describe("home page week guard", () => {
  it("clears a stale dish action synchronously when another week starts opening", () => {
    const source = readFileSync(new URL("../app/pages/index.vue", import.meta.url), "utf8");
    const start = source.indexOf("watch([() => plan.value?.id, lastPlanId]");
    const end = source.indexOf("\nwatch(", start + 1);

    expect(start).toBeGreaterThanOrEqual(0);
    expect(source.slice(start, end)).toMatch(/},\s*{\s*flush:\s*["']sync["']\s*}\);/);
  });
});
