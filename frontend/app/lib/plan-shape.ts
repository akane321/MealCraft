import { formatPlanDate } from "./meal-plan-format";
import type { DishCourse, DishMealRole, Equipment, MealRole, PlannedMealType, PlanShape } from "~/types/household";
import type { MealPlanShapeChange } from "~/types/meal-plan";

export const PLANNED_MEALS: PlannedMealType[] = ["breakfast", "lunch", "dinner"];

const CORE: DishMealRole[] = ["protein_main", "one_bowl"];
const VEG: DishMealRole[] = ["vegetable", "salad"];
/** A dish position by meal roles (ADR-0070), in the backend's key order. */
const dish = (role_id: string, meal_roles: DishMealRole[], extra: { required?: boolean; min_people?: number } = {}): MealRole => ({
  role_id,
  courses: [],
  required: extra.required ?? true,
  meal_roles,
  ...(extra.min_people ? { min_people: extra.min_people } : {}),
});

/**
 * The presets of ADR-0070 (mirrors backend STRUCTURED_PRESETS); the first of each meal is the full default.
 * The fixed presets have every dish required: a count the household chose. A saved shape of the older course
 * form (ADR-0046) is kept as it is and shows as "Custom (older format)".
 */
export const MEAL_PRESETS: Record<PlannedMealType, Record<string, MealRole[]>> = {
  breakfast: { "One dish": [dish("main", ["breakfast"])] },
  lunch: {
    "Full meal": [dish("main", CORE), dish("vegetable", VEG), dish("staple", ["staple"])],
    "One-bowl meal": [dish("main", ["one_bowl"])],
  },
  dinner: {
    "Full meal (grows with the household)": [
      dish("main", CORE),
      dish("main-2", ["protein_main"], { min_people: 3, required: false }),
      dish("main-3", ["protein_main"], { min_people: 7, required: false }),
      dish("vegetable", VEG),
      dish("vegetable-2", VEG, { min_people: 5, required: false }),
      dish("soup", ["soup"], { required: false }),
      dish("staple", ["staple"]),
    ],
    "Main, vegetable and staple": [dish("main", CORE), dish("vegetable", VEG), dish("staple", ["staple"])],
    "Main, vegetable, soup and staple": [dish("main", CORE), dish("vegetable", VEG), dish("soup", ["soup"]), dish("staple", ["staple"])],
  },
};

/** The full default (backend default_plan_shape): every meal with its first preset. */
export const DEFAULT_SHAPE: PlanShape = {
  meals: Object.fromEntries(PLANNED_MEALS.map(meal => [meal, Object.values(MEAL_PRESETS[meal])[0]!])),
};

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

/** What a meal role takes, in plain words ("protein main or one-bowl dish"). */
export const MEAL_ROLE_LABEL: Partial<Record<DishMealRole, string>> = {
  protein_main: "protein main",
  one_bowl: "one-bowl dish",
  vegetable: "vegetable dish",
  salad: "salad",
  soup: "soup",
  staple: "rice, noodles or bread",
  breakfast: "breakfast dish",
};

export const EQUIPMENT: Equipment[] = ["oven", "air_fryer", "steamer", "microwave", "blender"];
export const EQUIPMENT_LABEL: Record<Equipment, string> = {
  oven: "Oven",
  air_fryer: "Air fryer",
  steamer: "Steamer",
  microwave: "Microwave",
  blender: "Blender",
};

/** A meal of meal-role dishes (ADR-0070); the older form admits by courses. A meal's roles are all of one kind. */
export function isStructured(roles: MealRole[] | undefined): boolean {
  return Boolean(roles?.[0]?.meal_roles?.length);
}

const roleKey = (item: MealRole) => JSON.stringify([item.role_id, item.courses, item.required, item.meal_roles ?? null, item.min_people ?? null]);
const sameRoles = (a: MealRole[], b: MealRole[]) => a.length === b.length && a.every((item, index) => roleKey(item) === roleKey(b[index]!));

/** The preset a meal's dishes match, else "Custom", or "Custom (older format)" for a saved course shape. */
export function presetName(meal: PlannedMealType, roles: MealRole[]): string {
  const name = Object.entries(MEAL_PRESETS[meal]).find(([, preset]) => sameRoles(preset, roles))?.[0];
  return name ?? (isStructured(roles) ? "Custom" : "Custom (older format)");
}

/** True when every meal is planned with its recommended preset. */
export function isFullDefault(shape: PlanShape): boolean {
  return PLANNED_MEALS.every(meal => shape.meals[meal] && sameRoles(shape.meals[meal]!, DEFAULT_SHAPE.meals[meal]!));
}

/** The vegetable role and its copies ("vegetable-2"): the planner gives them only vegetable dishes (backend `vegetable_role`). */
export function isVegetableRole(roleId: string): boolean {
  return roleId.replace(/-\d+$/, "") === "vegetable";
}

/** What a dish row is called, by what the planner does with it: the vegetable role by its id, any other by what it takes. */
export function dishLabel(item: MealRole): string {
  if (isVegetableRole(item.role_id)) return "Vegetable dish";
  const kinds = item.meal_roles;
  if (kinds?.length) {
    if (kinds.includes("staple")) return "Staple";
    if (kinds.includes("soup")) return "Soup";
    if (kinds.includes("breakfast")) return "Breakfast dish";
    if (kinds.every(kind => kind === "one_bowl")) return "One-bowl dish";
    if (kinds.includes("protein_main")) return item.role_id === "main" ? "Protein main" : "Another protein main";
    return "Another dish";
  }
  if (item.courses.includes("main")) return item.role_id === "main" ? "Main dish" : "Another main";
  if (item.courses.includes("soup")) return "Soup";
  if (item.courses.includes("breakfast")) return "Breakfast dish";
  return item.courses.every(course => course === "side" || course === "salad") ? "Side or salad" : "Another dish";
}

/** A fresh role id: the base itself (the first main gets the main dish's share), else its first free copy ("main-2"). */
export function freeRoleId(roles: MealRole[], base: string): string {
  const taken = new Set(roles.map(item => item.role_id));
  if (!taken.has(base)) return base;
  let n = 2;
  while (taken.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
}

/** A fresh role id for a new dish of courses (the older form). */
export function nextRoleId(roles: MealRole[], courses: DishCourse[]): string {
  return freeRoleId(roles, courses.includes("main") ? "main" : courses.includes("soup") ? "soup" : "vegetable");
}

export type DishKind = "main" | "vegetable" | "soup" | "staple";

/** A new meal-role dish: another protein main, vegetable dish, soup or the staple; at breakfast, another breakfast dish. */
export function newDish(meal: PlannedMealType, roles: MealRole[], kind: DishKind): MealRole {
  if (meal === "breakfast") return dish(freeRoleId(roles, "main"), ["breakfast"]);
  if (kind === "main") return dish(freeRoleId(roles, "main"), roles.some(item => item.role_id === "main") ? ["protein_main"] : CORE);
  if (kind === "vegetable") return dish(freeRoleId(roles, "vegetable"), VEG);
  return dish(freeRoleId(roles, kind), [kind]);
}

/**
 * Whether a dish can be taken out (backend real_meal_roles): a real lunch or dinner keeps its filling core (the
 * first main) and, unless that core takes only one-bowl dishes, its staple. A meal keeps at least one dish.
 */
export function removable(meal: PlannedMealType, roles: MealRole[], index: number): boolean {
  if (roles.length <= 1) return false;
  if (meal === "breakfast" || !isStructured(roles)) return true;
  const item = roles[index]!;
  if (item.role_id === "main") return false;
  const core = roles.find(other => other.role_id === "main");
  return !(item.role_id === "staple" && !core?.meal_roles?.every(kind => kind === "one_bowl"));
}

/** How many people a meal's portions count as for its dish count (backend people_at): halves round up. */
export function peopleAt(portions: number): number {
  return Math.max(1, Math.floor(portions + 0.5));
}

/** The dishes a meal has with `people` at it: a dish "from N people" only from that many on. */
export function plannedRoles(roles: MealRole[], people: number): MealRole[] {
  return roles.filter(item => (item.min_people ?? 0) <= people);
}

const UNCOUNTED: Record<string, string> = { soup: "soup", staple: "a staple" };

/** A meal's dishes with `people` at it, counted: "2 protein mains, 1 vegetable dish, soup and a staple". */
export function dishCounts(roles: MealRole[], people: number): string {
  const tally = new Map<string, number>();
  for (const item of plannedRoles(roles, people)) {
    const label = dishLabel(item).toLowerCase().replace(/^another /, "");
    const noun = label === "main" ? "main dish" : label;
    tally.set(noun, (tally.get(noun) ?? 0) + 1);
  }
  const parts = [...tally].map(([noun, n]) => {
    if (n === 1 && UNCOUNTED[noun]) return UNCOUNTED[noun];
    return `${n} ${n === 1 ? noun : noun.endsWith("sh") ? `${noun}es` : `${noun}s`}`;
  });
  return parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts.at(-1)}` : parts[0] ?? "";
}

/** Plain words for a shape: "Breakfast: one dish · Lunch: full meal · Dinner: full meal (grows with the household)". */
export function describeShape(shape: PlanShape): string {
  return PLANNED_MEALS.filter(meal => shape.meals[meal])
    .map((meal) => {
      const roles = shape.meals[meal]!;
      const name = presetName(meal, roles);
      const dishes = `${roles.length} ${roles.length === 1 ? "dish" : "dishes"}${isStructured(roles) ? "" : " (older format)"}`;
      return `${meal[0]!.toUpperCase()}${meal.slice(1)}: ${name.startsWith("Custom") ? dishes : name.toLowerCase()}`;
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
