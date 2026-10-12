import { formatPlanDate } from "./meal-plan-format";
import type { DishCourse, MealRole, PlannedMealType, PlanShape } from "~/types/household";
import type { MealPlanShapeChange } from "~/types/meal-plan";

export const PLANNED_MEALS: PlannedMealType[] = ["breakfast", "lunch", "dinner"];

const role = (role_id: string, courses: DishCourse[], required = true): MealRole => ({ role_id, courses, required });

/** The presets of ADR-0046 (mirrors backend MEAL_PRESETS); the first of each meal is its default. */
export const MEAL_PRESETS: Record<PlannedMealType, Record<string, MealRole[]>> = {
  breakfast: { "One dish": [role("main", ["breakfast", "baked_good"])] },
  lunch: {
    "One dish": [role("main", ["main", "salad", "soup"])],
    "Main and a veg": [role("main", ["main"]), role("vegetable", ["side", "salad"])],
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

/** The vegetable role and its copies ("vegetable-2"): the planner gives them only vegetable dishes (backend `vegetable_role`). */
export function isVegetableRole(roleId: string): boolean {
  return roleId.replace(/-\d+$/, "") === "vegetable";
}

/** What a dish row is called, by what the planner does with it: the vegetable role by its id, any other by its courses. */
export function dishLabel(item: MealRole): string {
  if (isVegetableRole(item.role_id)) return "Vegetable dish";
  if (item.courses.includes("main")) return item.role_id === "main" ? "Main dish" : "Another main";
  if (item.courses.includes("soup")) return "Soup";
  if (item.courses.includes("breakfast")) return "Breakfast dish";
  return item.courses.every(course => course === "side" || course === "salad") ? "Side or salad" : "Another dish";
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

/** A plan day by its weekday ("Sun"), from the plan's own start date; "day 4" only while no date is known. */
export function planDayLabel(startDate: string | null | undefined, dayIndex: number): string {
  if (!startDate) return `day ${dayIndex}`;
  const date = new Date(`${startDate}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + dayIndex - 1);
  return formatPlanDate(date.toISOString().slice(0, 10), { weekday: "short" });
}

/** What a shape change does, in plain words: "Lunch added for the rest of the week", "Dinner on Fri: main, vegetable if it fits, soup". */
export function shapeChangeSummary(change: MealPlanShapeChange, startDate: string | null | undefined): string {
  const meal = `${change.meal_type[0]!.toUpperCase()}${change.meal_type.slice(1)}`;
  const where = change.scope === "week"
    ? "for the rest of the week"
    : `on ${change.day_indexes.map(day => planDayLabel(startDate, day)).join(", ")}`;
  if (change.roles === null) return `No ${change.meal_type} ${where}`;
  if (!change.removed.length && !change.kept) return `${meal} added ${where}`;
  // Each new dish takes a dish's own place (its day and role in the one meal a change plans), as when the week's
  // repeated dishes are swapped ("the dishes are boring"): the change is the swaps, not a meal's new make-up.
  const swapped = change.removed.length > 0 && change.added.length === change.removed.length && change.added.every(dish => change.removed.some(
    old => old.day_index === dish.day_index && old.role_id === dish.role_id,
  ));
  if (swapped) return `${change.added.length === 1 ? "A dish" : `${change.added.length} dishes`} swapped ${where}`;
  const labels: string[] = [];
  for (const item of change.roles) {
    // Show household-facing dish names rather than planner role ids such as "main".
    const label = dishLabel(item);
    labels.push(`${label}${item.required === false ? " if it fits" : ""}`);
  }
  const dishes = labels.join(", ");
  return `${meal} ${where}: ${dishes}`;
}
