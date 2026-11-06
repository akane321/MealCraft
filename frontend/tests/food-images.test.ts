import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { dishImageSrc, indexFoodImages, ingredientImageSrc, type FoodImageFile } from "../app/composables/useFoodImages";

const IMAGES = new URL("../public/images/", import.meta.url);
const file: FoodImageFile = JSON.parse(readFileSync(new URL("food-images.json", IMAGES), "utf8"));
const index = indexFoodImages(file);

describe("food images", () => {
  it("finds a release dish by its slug and leaves other recipes to the drawn icon", () => {
    const [image, ids] = Object.entries(file.dishes)[0]!;
    const id = ids.split(" ")[0]!;
    expect(dishImageSrc(index, `v2-some-title-${id}`)).toBe(`/images/dishes/${image}.webp`);
    expect(dishImageSrc(index, "dinner-1")).toBeNull();
    expect(dishImageSrc(null, `v2-some-title-${id}`)).toBeNull();
  });

  it("finds an ingredient by its display name, whatever the case or punctuation", () => {
    expect(ingredientImageSrc(index, "Vanilla Ice Cream")).toBe("/images/ingredients/vanilla-ice-cream.webp");
    expect(ingredientImageSrc(index, "rice cake (tteok)")).toBe("/images/ingredients/rice-cake--tteok-.webp");
    expect(ingredientImageSrc(index, "no such thing")).toBeNull();
  });

  it("every listed image is in the repo", () => {
    const missing = [
      ...Object.keys(file.dishes).map(image => `dishes/${image}.webp`),
      ...file.ingredients.map(name => `ingredients/${name}.webp`),
    ].filter(path => !existsSync(new URL(path, IMAGES)));
    expect(missing).toEqual([]);
  });
});
