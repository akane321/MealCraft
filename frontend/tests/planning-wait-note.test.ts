// The wait a plan may take is stated in one sentence, and ADR-0079 sets how long that is: a complex request
// may take up to about a minute. Both pages that plan say it, and the user guide says the same thing, so a
// change to the decision cannot leave one of the three behind. It guards the wording, not the behaviour:
// that the note appears while planning is an end-to-end concern.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const NOTE = "A large household on a tight budget can take up to a minute to plan.";
const PLANS = ["app/pages/index.vue", "app/pages/profile.vue"];

describe("the note on how long a plan may take", () => {
  it.each(PLANS)("%s states the wait a complex request is allowed", (page) => {
    expect(readFileSync(new URL(`../${page}`, import.meta.url), "utf8")).toContain(NOTE);
  });

  it("never promises the half minute ADR-0079 replaced", () => {
    for (const page of [...PLANS, "../docs/user-guide.md"]) {
      expect(readFileSync(new URL(`../${page}`, import.meta.url), "utf8")).not.toContain("half a minute");
    }
  });

  it("is the same wait the user guide describes", () => {
    const guide = readFileSync(new URL("../../docs/user-guide.md", import.meta.url), "utf8");
    expect(guide).toContain("up to about a minute");
  });
});
