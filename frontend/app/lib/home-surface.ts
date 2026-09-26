import type { NutritionDashboardDay, WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";
import type { RecipeNutrition } from "~/types/recipe";

/** Today's dinner if the plan covers today, otherwise the next one still planned. */
export function tonightEntry(
  days: NutritionDashboardDay[],
  today: string,
): { day: NutritionDashboardDay; isToday: boolean } | null {
  const todays = days.find(day => day.planned_date === today && day.status !== "skipped");
  if (todays) return { day: todays, isToday: true };
  const next = days.find(day => day.planned_date >= today && day.status === "planned")
    ?? days.find(day => day.status === "planned");
  return next ? { day: next, isToday: false } : null;
}

export function formatSgd(value: number): string {
  return `S$${value.toFixed(2)}`;
}

export function budgetLine(estimate: WeeklyGroceryEstimate): string | null {
  const budget = estimate.weekly_budget_sgd;
  if (budget === null) return null;
  const gap = Math.round((budget - estimate.purchase_total_sgd) * 100) / 100;
  return gap >= 0
    ? `${formatSgd(gap)} under your ${formatSgd(budget)}`
    : `${formatSgd(-gap)} over your ${formatSgd(budget)}`;
}

export function packageLabel(line: GroceryLineEstimate): string {
  const size = line.product?.package_size;
  const unit = line.product?.package_unit ?? "";
  if (size) return `${line.packages_required} × ${size}${unit ? ` ${unit}` : ""}`;
  if (line.required_quantity !== null) return `${line.required_quantity}${line.unit ? ` ${line.unit}` : ""}`;
  return `${line.packages_required} pack${line.packages_required === 1 ? "" : "s"}`;
}

/** Lines that actually need buying, grouped by shop category, costliest first. */
export function groceryGroups(items: GroceryLineEstimate[]): Array<{ name: string; lines: GroceryLineEstimate[] }> {
  const groups = new Map<string, GroceryLineEstimate[]>();
  for (const line of items) {
    if (line.packages_required <= 0) continue;
    const name = line.product?.category || "Other";
    groups.set(name, [...(groups.get(name) ?? []), line]);
  }
  return [...groups.entries()]
    .map(([name, lines]) => ({ name, lines: lines.sort((a, b) => b.purchase_cost_sgd - a.purchase_cost_sgd) }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/**
 * Short, user-facing note on where prices came from, read from the products
 * actually used rather than the mode that was asked for: a live request that
 * fell back to sample data must not be labelled as FairPrice prices.
 */
export function priceSourceLabel(estimate: WeeklyGroceryEstimate): string {
  const products = estimate.items.map(line => line.product).filter(product => product !== null);
  const samples = products.filter(product => product.source !== "fairprice").length;
  if (!products.length || samples === products.length) {
    return estimate.pricing_mode === "live" ? "Sample prices: FairPrice didn't respond" : "Sample prices";
  }
  if (samples) return "Some prices are samples: FairPrice didn't respond";
  const fetched = products.map(product => product.fetched_at).sort()[0]!;
  const date = new Date(fetched).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  return `FairPrice prices from ${date}`;
}

// Sauce, starch and garnish colours; a dish's plate picks one of each.
const SAUCES = ["#c9803f", "#d9a54a", "#e58a62", "#d6533a", "#6b3a2a", "#d77b35", "#b8653f", "#a6582e"];
const STARCHES = ["#e9d9b5", "#f1e6cf", "#f4efe6", "#efe3c8", "#f0c64f", "#f2dfb4"];
const GREENS = ["#6f8f4e", "#4f7a3a", "#5d8a3f", "#7aa04a", "#4a3024", "#c24a2a"];

/** CSS variables for an abstract plate; the same dish always gets the same plate. */
export function plateStyle(seed: string): Record<string, string> {
  let hash = 2166136261;
  for (const char of seed) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0;
  return {
    "--a": SAUCES[hash % SAUCES.length]!,
    "--b": STARCHES[(hash >>> 8) % STARCHES.length]!,
    "--c": GREENS[(hash >>> 16) % GREENS.length]!,
  };
}

/** Per-person nutrition averaged over the dinners that still count (skipped ones don't). */
export function perDinner(days: NutritionDashboardDay[]): RecipeNutrition | null {
  const counted = days.filter(day => day.status !== "skipped");
  if (!counted.length) return null;
  const keys = Object.keys(counted[0]!.nutrition_per_person) as Array<keyof RecipeNutrition>;
  return Object.fromEntries(keys.map(key => [
    key,
    counted.reduce((sum, day) => sum + day.nutrition_per_person[key], 0) / counted.length,
  ])) as unknown as RecipeNutrition;
}

const WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

export function countWord(count: number): string {
  return WORDS[count] ?? String(count);
}

export type MealType = "breakfast" | "lunch" | "dinner" | "snack";
const MEAL_ORDER: MealType[] = ["breakfast", "lunch", "dinner", "snack"];
export const MEAL_LABEL: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};

export interface PlannedMeal {
  key: string;
  dayIndex: number;
  date: string;
  mealType: MealType;
  /** The main dish first, then the others in role order. */
  dishes: NutritionDashboardDay[];
  status: "planned" | "completed" | "skipped" | "partial";
}

export interface PlannedDay {
  dayIndex: number;
  date: string;
  meals: PlannedMeal[];
}

function mealStatus(dishes: NutritionDashboardDay[]): PlannedMeal["status"] {
  if (dishes.every(dish => dish.status === "completed")) return "completed";
  if (dishes.every(dish => dish.status === "skipped")) return "skipped";
  return dishes.some(dish => dish.status === "completed") ? "partial" : "planned";
}

/** The week as days of meals of dishes (ADR-0046); a one-dish dinner week is seven one-dish meals. */
export function mealsByDay(days: NutritionDashboardDay[]): PlannedDay[] {
  const byDay = new Map<number, PlannedDay>();
  for (const dish of days) {
    const day = byDay.get(dish.day_index) ?? { dayIndex: dish.day_index, date: dish.planned_date, meals: [] };
    byDay.set(dish.day_index, day);
    const mealType = (dish.meal_type ?? "dinner") as MealType;
    let meal = day.meals.find(item => item.mealType === mealType);
    if (!meal) {
      meal = { key: `${dish.day_index}-${mealType}`, dayIndex: dish.day_index, date: dish.planned_date, mealType, dishes: [], status: "planned" };
      day.meals.push(meal);
    }
    meal.dishes.push(dish);
  }
  const ordered = [...byDay.values()].sort((a, b) => a.dayIndex - b.dayIndex);
  for (const day of ordered) {
    day.meals.sort((a, b) => MEAL_ORDER.indexOf(a.mealType) - MEAL_ORDER.indexOf(b.mealType));
    for (const meal of day.meals) {
      meal.dishes.sort((a, b) => Number((b.role_id ?? "main") === "main") - Number((a.role_id ?? "main") === "main"));
      meal.status = mealStatus(meal.dishes);
    }
  }
  return ordered;
}

/** Today's next meal still to cook, otherwise the next planned one. */
export function nextMeal(days: NutritionDashboardDay[], today: string): { meal: PlannedMeal; isToday: boolean } | null {
  const meals = mealsByDay(days).flatMap(day => day.meals);
  const open = (meal: PlannedMeal) => meal.status === "planned" || meal.status === "partial";
  const todays = meals.find(meal => meal.date === today && open(meal));
  if (todays) return { meal: todays, isToday: true };
  const next = meals.find(meal => meal.date >= today && open(meal)) ?? meals.find(open);
  return next ? { meal: next, isToday: false } : null;
}

/** Per-person nutrition of an average meal and an average day, over what still counts (skipped dishes don't). */
export function perMealAndDay(days: NutritionDashboardDay[]): { meal: RecipeNutrition; day: RecipeNutrition; mealsPerDay: number } | null {
  const planned = mealsByDay(days.filter(dish => dish.status !== "skipped"));
  const meals = planned.flatMap(day => day.meals);
  if (!meals.length) return null;
  const keys = Object.keys(days[0]!.nutrition_per_person) as Array<keyof RecipeNutrition>;
  const total = Object.fromEntries(keys.map(key => [key, meals.reduce((sum, meal) => sum + meal.dishes.reduce((s, d) => s + d.nutrition_per_person[key], 0), 0)])) as unknown as RecipeNutrition;
  const scale = (divisor: number) => Object.fromEntries(keys.map(key => [key, total[key] / divisor])) as unknown as RecipeNutrition;
  return { meal: scale(meals.length), day: scale(planned.length), mealsPerDay: meals.length / planned.length };
}

