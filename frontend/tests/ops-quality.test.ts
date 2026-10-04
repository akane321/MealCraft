import { describe, expect, it } from "vitest";

import { qualityBytes, qualityDistribution, qualityPageLabel, qualityPercent, shortQualityDigest } from "../app/lib/ops-quality";

describe("operations data-quality helpers", () => {
  it("formats estimated shares without turning missing evidence into zero", () => {
    expect(qualityPercent(0)).toBe("0%");
    expect(qualityPercent(0.126)).toBe("12.6%");
    expect(qualityPercent(null)).toBe("—");
    expect(qualityPercent(Number.NaN)).toBe("—");
  });

  it("orders distributions by count and derives shares from their own total", () => {
    expect(qualityDistribution({ british: 2, chinese: 5, american: 5 })).toEqual([
      { label: "american", count: 5, share: 5 / 12 },
      { label: "chinese", count: 5, share: 5 / 12 },
      { label: "british", count: 2, share: 2 / 12 },
    ]);
    expect(qualityDistribution(null)).toEqual([]);
    expect(qualityDistribution({ unknown: 0 })).toEqual([{ label: "unknown", count: 0, share: 0 }]);
  });

  it("distinguishes a missing dropped artifact from a valid empty page", () => {
    expect(qualityPageLabel(0, 0, null)).toBe("Total unavailable");
    expect(qualityPageLabel(0, 0, 0)).toBe("No records");
    expect(qualityPageLabel(25, 3, 28)).toBe("26–28 of 28");
  });

  it("keeps artifact metadata compact without changing the evidence", () => {
    expect(shortQualityDigest("a".repeat(64))).toBe(`${"a".repeat(12)}…`);
    expect(shortQualityDigest("abc")).toBe("abc");
    expect(qualityBytes(900)).toBe("900 B");
    expect(qualityBytes(2048)).toBe("2.0 KB");
    expect(qualityBytes(2 * 1024 ** 2)).toBe("2.0 MB");
  });
});
