import { describe, expect, it } from "vitest";

import { formatQuantity, formatSgd } from "../app/lib/product-format";

describe("product formatting", () => {
  it("formats Singapore dollar values", () => {
    expect(formatSgd(1.85)).toBe("S$1.85");
    expect(formatSgd(null)).toBe("Unavailable");
  });

  it("formats known and unknown package quantities", () => {
    expect(formatQuantity(600, "g")).toBe("600 g");
    expect(formatQuantity(1.5, "kg")).toBe("1.5 kg");
    expect(formatQuantity(null, null)).toBe("Quantity unavailable");
  });
});
