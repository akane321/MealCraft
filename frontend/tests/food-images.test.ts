import { existsSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { dishImageSrc, indexFoodImages, ingredientImageSrc, type FoodImageFile } from "../app/composables/useFoodImages";

const IMAGES = new URL("../public/images/", import.meta.url);
const file: FoodImageFile = JSON.parse(readFileSync(new URL("../app/assets/food-images.json", import.meta.url), "utf8"));
const index = indexFoodImages(file);

describe("food images", () => {
  it("finds a release dish by its slug", () => {
    const [image, ids] = Object.entries(file.dishes)[0]!;
    const id = ids.split(" ")[0]!;
    expect(dishImageSrc(index, `v2-some-title-${id}`)).toBe(`/images/dishes/${image}.webp`);
    expect(dishImageSrc(null, `v2-some-title-${id}`)).toBeNull();
  });

  it("tells curated dishes apart by their whole slug", () => {
    const small = indexFoodImages({ dishes: { d0001: "tuna-spinach-pasta", d0002: "mushroom-spinach-pasta" }, ingredients: [], words: {}, fallback: "d0003" });
    expect(dishImageSrc(small, "mushroom-spinach-pasta")).toBe("/images/dishes/d0002.webp");
    expect(dishImageSrc(small, "tuna-spinach-pasta")).toBe("/images/dishes/d0001.webp");
  });

  it("gives an imported dish the picture of its rarest known title word", () => {
    const small = indexFoodImages({ dishes: {}, ingredients: [], words: { rendang: "d0001", beef: "d0002" }, fallback: "d0003" });
    expect(dishImageSrc(small, "curated-1", "Beef Rendang")).toBe("/images/dishes/d0001.webp");
    expect(dishImageSrc(small, "curated-2", "Grilled beef")).toBe("/images/dishes/d0002.webp");
    expect(dishImageSrc(small, "curated-3", "麻婆豆腐")).toBe("/images/dishes/d0003.webp");
    expect(dishImageSrc(small, "", "")).toBe("/images/dishes/d0003.webp");
  });

  it("finds an ingredient by its display name, whatever the case or punctuation", () => {
    expect(ingredientImageSrc(index, "Vanilla Ice Cream")).toBe("/images/ingredients/vanilla-ice-cream.webp");
    expect(ingredientImageSrc(index, "rice cake (tteok)")).toBe("/images/ingredients/rice-cake--tteok-.webp");
    expect(ingredientImageSrc(index, "no such thing")).toBeNull();
    expect(ingredientImageSrc(index, "Baby spinach")).toBe("/images/ingredients/spinach.webp");
    expect(ingredientImageSrc(index, "Red lentils")).toBe("/images/ingredients/lentil.webp");
  });

  it("every listed image is in the repo", () => {
    const missing = [
      ...[...Object.keys(file.dishes), ...Object.values(file.words), file.fallback].map(image => `dishes/${image}.webp`),
      ...file.ingredients.map(name => `ingredients/${name}.webp`),
      ...Object.values(file.ingredient_aliases ?? {}).map(name => `ingredients/${name}.webp`),
    ].filter(path => !existsSync(new URL(path, IMAGES)));
    expect(missing).toEqual([]);
  });
});
