import type { DishCourse, MealRole, PlannedMealType, PlanShape } from "~/types/household";

export const PLANNED_MEALS: PlannedMealType[] = ["breakfast", "lunch", "dinner"];

const role = (role_id: string, courses: DishCourse[], required = true): MealRole => ({ role_id, courses, required });

/** The presets of ADR-0046 (mirrors backend MEAL_PRESETS); the first of each meal is its default. */
export const MEAL_PRESETS: Record<PlannedMealType, Record<string, MealRole[]>> = {
  breakfast: { "One dish": [role("main", ["breakfast", "baked_good"])] },
  lunch: {
    "One dish": [role("main", ["main", "salad", "soup"])],
    "Main and a side": [role("main", ["main"]), role("vegetable", ["side", "salad"])],
  },
  dinner: {
    "One meat, one veg": [role("main", ["main"]), role("vegetable", ["side", "salad"], false)],
    "One main": [role("main", ["main"])],
    "Meat, veg and soup": [role("main", ["main"]), role("vegetable", ["side", "salad"]), role("soup", ["soup"])],
  },
};

export const DEFAULT_SHAPE: PlanShape = { meals: { dinner: MEAL_PRESETS.dinner["One meat, one veg"] } };

export const COURSE_LABEL: Record<DishCourse, string> = {
  main: "Main",
  side: "Side",
  salad: "Salad",
  soup: "Soup",
  breakfast: "Breakfast dish",
  baked_good: "Baked",
  dessert: "Dessert",
  snack_appetizer: "Snack",
};

/** The preset a meal's dishes match, or "Custom". */
export function presetName(meal: PlannedMealType, roles: MealRole[]): string {
  const same = (a: MealRole[], b: MealRole[]) => JSON.stringify(a) === JSON.stringify(b);
  return Object.entries(MEAL_PRESETS[meal]).find(([, preset]) => same(preset, roles))?.[0] ?? "Custom";
}

/** A fresh role id for a new dish: the first main is "main" (it gets the main dish's share). */
export function nextRoleId(roles: MealRole[], courses: DishCourse[]): string {
  const base = courses.includes("main") ? "main" : courses.includes("soup") ? "soup" : "vegetable";
  const taken = new Set(roles.map(item => item.role_id));
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/** Plain words for a shape: "Lunch: one dish · Dinner: one meat, one veg". */
export function describeShape(shape: PlanShape): string {
  return PLANNED_MEALS.filter(meal => shape.meals[meal])
    .map((meal) => {
      const name = presetName(meal, shape.meals[meal]!);
      return `${meal[0]!.toUpperCase()}${meal.slice(1)}: ${name === "Custom" ? `${shape.meals[meal]!.length} dishes` : name.toLowerCase()}`;
    })
    .join(" · ");
}
