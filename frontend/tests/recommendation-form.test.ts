import { describe, expect, it } from "vitest";

import {
  cleanAvailableIngredients,
  formatRecommendationScore,
  parseExcludedIngredients,
  toOptionalNumber,
} from "../app/lib/recommendation-form";

describe("recommendation form helpers", () => {
  it("normalizes and deduplicates excluded ingredient IDs", () => {
    expect(parseExcludedIngredients(" Mushroom, yellow onion, mushroom ")).toEqual([
      "mushroom",
      "yellow_onion",
    ]);
  });

  it("removes empty pantry rows and clears units for unknown quantities", () => {
    expect(cleanAvailableIngredients([
      { normalized_name: " Brown Rice ", quantity: 200, unit: " G " },
      { normalized_name: "lemon", quantity: null, unit: "whole" },
      { normalized_name: "  ", quantity: null, unit: null },
    ])).toEqual([
      { normalized_name: "brown_rice", quantity: 200, unit: "g" },
      { normalized_name: "lemon", quantity: null, unit: null },
    ]);
    expect(formatRecommendationScore(87.24)).toBe("87.2");
    expect(toOptionalNumber(12)).toBe(12);
    expect(toOptionalNumber("")).toBeNull();
  });
});
