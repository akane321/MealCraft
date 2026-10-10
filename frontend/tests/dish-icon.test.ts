import { describe, expect, it } from "vitest";

import { dishRole, foodGroup } from "../app/lib/dish-icon";

const pick = (d: Parameters<typeof dishRole>[0]) => {
  const role = dishRole(d);
  return [role, foodGroup(d, role)];
};

describe("dish icon mapping", () => {
  it("reads the main ingredient first, then the title", () => {
    expect(pick({ title: "Singapore Noodles", course: "main", ingredients: ["rice vermicelli", "shrimp", "egg"] })).toEqual(["main", "noodles"]);
    expect(pick({ title: "Singapore Noodles" })).toEqual(["other", "noodles"]);
    expect(pick({ title: "Steamed Fish with Ginger", course: "main", ingredients: [{ normalized_name: "sea bass fillet", name: "Sea bass" }, { name: "ginger" }] })).toEqual(["main", "seafood"]);
    expect(pick({ title: "Mapo Tofu", course: "main", ingredients: ["tofu", "pork mince"] })).toEqual(["main", "tofu_egg"]);
    expect(pick({ title: "Beef Rendang", course: "main", ingredients: ["beef", "coconut milk"] })).toEqual(["main", "red_meat"]);
    expect(pick({ title: "麻婆豆腐", course: "main" })).toEqual(["main", "tofu_egg"]);
  });

  it("lets the course set the role and keeps the protein for salads", () => {
    expect(pick({ title: "Thai Chicken Salad", course: "salad", ingredients: ["chicken breast", "lettuce"] })).toEqual(["salad", "poultry"]);
    expect(pick({ title: "Garden Salad", course: "salad" })).toEqual(["salad", "leafy"]);
    expect(pick({ title: "Stir-fried Kai Lan", course: "side", ingredients: ["kai lan", "garlic"] })).toEqual(["vegetable", "leafy"]);
    expect(pick({ title: "Roasted Vegetables", roleId: "vegetable-2" })).toEqual(["vegetable", "veg_mix"]);
  });

  it("makes every soup broth, whatever is in it", () => {
    expect(pick({ title: "Chicken Laksa", course: "soup", ingredients: ["chicken", "rice noodles"] })).toEqual(["soup", "broth"]);
    expect(pick({ title: "Tomato Soup" })).toEqual(["soup", "broth"]);
  });

  it("finds drinks and desserts by title when no course is given", () => {
    expect(pick({ title: "Iced Lemon Tea" })).toEqual(["drink", "fruit_sweet"]);
    expect(pick({ title: "Strawberry Pudding", course: "dessert" })).toEqual(["dessert", "fruit_sweet"]);
  });

  it("does not match inside longer words and falls back to mixed", () => {
    expect(foodGroup({ title: "Eggplant Curry" }, "main")).toBe("veg_mix");
    expect(foodGroup({ title: "Peanut Sauce" }, "main")).toBe("mixed");
    expect(pick({})).toEqual(["other", "mixed"]);
    expect(pick({ title: "Something Unknown", course: "main" })).toEqual(["main", "mixed"]);
  });
});
