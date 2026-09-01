import { describe, expect, it } from "vitest";

import { eventTypeLabel, formatSigned, groceryDeltaSummary } from "../app/lib/replanning";

describe("replanning presentation helpers", () => {
  it("uses readable event labels and signed nutrition deltas", () => {
    expect(eventTypeLabel("ITEM_UNAVAILABLE")).toBe("Ingredient unavailable");
    expect(formatSigned(120, " kcal")).toBe("+120 kcal");
    expect(formatSigned(-2.5, " g")).toBe("−2.5 g");
    expect(formatSigned(0, " mg")).toBe("0 mg");
  });

  it("summarises package-level shopping changes", () => {
    expect(groceryDeltaSummary({
      ingredient_name: "tofu",
      ingredient_display_name: "Tofu",
      change: "updated",
      before_required_quantity: 300,
      after_required_quantity: 600,
      unit: "g",
      before_packages_required: 1,
      after_packages_required: 2,
      purchase_cost_delta_sgd: 2.5,
    })).toBe("1 → 2 package(s)");
  });
});
