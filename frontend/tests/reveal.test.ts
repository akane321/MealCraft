import { describe, expect, it } from "vitest";

import { REVEAL_MAX_MS, revealDuration, revealTokens } from "../app/lib/reveal";

describe("reply reveal", () => {
  it("keeps the reply's text unchanged and splits Chinese by character", () => {
    const text = "Here's your week:\n7 dinners 晚餐不要牛肉";
    expect(revealTokens(text).join("")).toBe(text);
    expect(revealTokens("不要牛肉")).toEqual(["不", "要", "牛", "肉"]);
  });

  it("never takes longer than the cap, however long the reply", () => {
    expect(revealDuration("word ".repeat(2000))).toBeLessThanOrEqual(REVEAL_MAX_MS);
    expect(revealDuration("Hi")).toBeLessThan(REVEAL_MAX_MS);
  });
});
