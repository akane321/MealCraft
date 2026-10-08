import { describe, expect, it } from "vitest";
import { dishContainer, dishGroup } from "../app/lib/dish-icon";

describe("dish icon mapping", () => {
  it("reads the main ingredient group from the title", () => {
    expect(dishGroup("Chicken rice")).toBe("rice");
    expect(dishGroup("Singapore laksa with prawns")).toBe("noodles");
    expect(dishGroup("Grilled salmon")).toBe("seafood");
    expect(dishGroup("Garlic bok choy")).toBe("greens");
    expect(dishGroup("Braised tofu")).toBe("tofu-egg");
    expect(dishGroup("Something odd")).toBe("mixed");
  });
  it("falls back to ingredients when the title says nothing", () => {
    expect(dishGroup("Grandma's special", ["chicken thigh", "garlic"])).toBe("poultry");
  });
  it("picks the container from the role", () => {
    expect(dishContainer("soup")).toBe("bowl");
    expect(dishContainer("salad")).toBe("shallow");
    expect(dishContainer(null, "vegetable")).toBe("dish");
    expect(dishContainer("main")).toBe("plate");
    expect(dishContainer(undefined, undefined)).toBe("plate");
    expect(dishContainer("dessert")).toBe("dessert");
  });
});
