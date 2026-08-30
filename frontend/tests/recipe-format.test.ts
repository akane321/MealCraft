import { describe, expect, it } from "vitest";

import { formatIngredient, formatNutrition, formatTag } from "../app/lib/recipe-format";

describe("recipe formatting", () => {
  it("formats dietary tags and nutrition values", () => {
    expect(formatTag("high-protein")).toBe("high protein");
    expect(formatNutrition(620, "mg")).toBe("620 mg");
    expect(formatNutrition(8.5, "g")).toBe("8.5 g");
  });

  it("formats ingredient amounts while preserving optional fields", () => {
    expect(formatIngredient({
      name: "Chicken breast",
      normalized_name: "chicken_breast",
      quantity: 300,
      unit: "g",
      preparation: "sliced",
      allergen: null,
    })).toBe("300 g Chicken breast");
  });
});
