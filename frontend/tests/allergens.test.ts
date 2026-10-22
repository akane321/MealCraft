import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { CHECKED_ALLERGENS } from "../app/lib/allergens";

describe("checked allergens", () => {
  it("are exactly data/ingredients/allergen-vocabulary.json (a safety list)", () => {
    const file = new URL("../../data/ingredients/allergen-vocabulary.json", import.meta.url);
    const checked = JSON.parse(readFileSync(file, "utf-8")).checked as string[];
    expect([...CHECKED_ALLERGENS].sort()).toEqual([...checked].sort());
  });
});
