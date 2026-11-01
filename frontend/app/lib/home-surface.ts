import type { FeedbackKind, MealPlanReplanEvent, NutritionDashboardDay, WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate, ProductSearchResponse, Retailer } from "~/types/recommendation";
import type { RecipeNutrition } from "~/types/recipe";
import { formatPlanDate, sentenceDay } from "./meal-plan-format";
import { planDayLabel } from "./plan-shape";

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

/** What is left of the weekly budget, or how far over it the week is; null without a budget. */
export function budgetGap(estimate: WeeklyGroceryEstimate): { amount: string; over: boolean } | null {
  const budget = estimate.weekly_budget_sgd;
  if (budget === null) return null;
  const gap = Math.round((budget - estimate.purchase_total_sgd) * 100) / 100;
  return { amount: formatSgd(Math.abs(gap)), over: gap < 0 };
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

/** The store a line is bought at: its own `retailer`, else its product's source (FairPrice unless it says Cold Storage). */
export function lineRetailer(line: GroceryLineEstimate): Retailer {
  return (line.retailer ?? (line.product?.source === "cold_storage" ? "cold_storage" : "fairprice"));
}

export const RETAILER_NAME: Record<Retailer, string> = { fairprice: "FairPrice", cold_storage: "Cold Storage" };

/** True when some line is bought at Cold Storage: only then does a list show its stores apart. */
export const hasColdStorage = (items: GroceryLineEstimate[]): boolean => items.some(line => lineRetailer(line) === "cold_storage");

export interface GroceryStore {
  retailer: Retailer;
  name: string;
  groups: Array<{ name: string; lines: GroceryLineEstimate[] }>;
}

/** A trip's lines by store, FairPrice first and then Cold Storage, each as groceryGroups; a store with nothing to buy is left out. */
export function groceryStores(items: GroceryLineEstimate[]): GroceryStore[] {
  return (["fairprice", "cold_storage"] as const)
    .map(retailer => ({ retailer, name: RETAILER_NAME[retailer], groups: groceryGroups(items.filter(line => lineRetailer(line) === retailer)) }))
    .filter(store => store.groups.length);
}

export interface GroceryTrip {
  /** 1 before day 1, 2 before day 8; null for a plan's only trip. */
  trip: number | null;
  /** "Shop before day 8"; null for a plan's only trip. */
  label: string | null;
  groups: Array<{ name: string; lines: GroceryLineEstimate[] }>;
  /** The same lines by store; one FairPrice entry when no line is Cold Storage's. */
  stores: GroceryStore[];
}

/** Days one shopping trip covers: the backend's meal_structure trip_days (a plan of up to 7 days is one trip). */
export const TRIP_DAYS = 7;

/** A plan longer than a week shops twice (ADR-0072): its lines by trip, each grouped as groceryGroups; one trip otherwise. */
export function groceryTrips(items: GroceryLineEstimate[], tripDays = TRIP_DAYS): GroceryTrip[] {
  const make = (trip: number | null, label: string | null, lines: GroceryLineEstimate[]): GroceryTrip => ({ trip, label, groups: groceryGroups(lines), stores: groceryStores(lines) });
  if (!items.some(line => line.shopping_trip)) return [make(null, null, items)];
  const trips = [...new Set(items.map(line => line.shopping_trip ?? 1))].sort((a, b) => a - b);
  return trips
    .map(trip => make(trip, `Shop before day ${1 + (trip - 1) * tripDays}`, items.filter(line => (line.shopping_trip ?? 1) === trip)))
    .filter(trip => trip.groups.length);
}

/** How many shopping trips a plan's list has: two for a plan longer than a week. */
export function shoppingTrips(estimate: WeeklyGroceryEstimate): number {
  return Math.max(1, ...estimate.items.map(line => line.shopping_trip ?? 1));
}

type PriceKind = "live" | "saved" | "sample";

/**
 * Where a displayed price really came from. A price kept in the reviewed snapshot is a saved FairPrice price
 * once a live check was attempted for it (the snapshot product itself is stored as a "fixture" product, so
 * the product's own source cannot tell a reviewed price from a made-up sample). A price from the short-lived
 * lookup cache was fetched live minutes ago, so it counts as live.
 */
function priceKind(line: GroceryLineEstimate): PriceKind {
  const evidence = line.evidence;
  const source = evidence?.price_source ?? evidence?.mode;
  if (source === "no_external_product" || source === "fixture") return "sample";
  if (source === "live" || source === "cache") return "live";
  if (source === "snapshot" && evidence?.lookup_status) return "saved";
  return line.product?.source === "fixture" ? "sample" : "saved";
}

const priced = (estimate: WeeklyGroceryEstimate) => estimate.items.filter(line => line.product && line.packages_required > 0);

/** How many lines to buy have a live, saved and sample price, by priceKind: the one count every price note uses. */
export function priceCounts(estimate: WeeklyGroceryEstimate): Record<PriceKind, number> {
  const counts: Record<PriceKind, number> = { live: 0, saved: 0, sample: 0 };
  for (const line of priced(estimate)) counts[priceKind(line)] += 1;
  return counts;
}

/** A saved (not freshly checked) FairPrice price: the lines labelled "Saved FairPrice price", which the list shows in amber. */
export function isSavedPrice(line: GroceryLineEstimate): boolean {
  return Boolean(line.product) && priceKind(line) === "saved";
}

/**
 * The price note's dot: green when every price is FairPrice's (live or saved), amber when some are samples or when a live
 * check got no live price at all (the note then says "Live prices not available"), grey when every price is a sample.
 */
export function priceTone(estimate: WeeklyGroceryEstimate): "ok" | "warn" | "" {
  const { live, saved, sample } = priceCounts(estimate);
  if (!(live + saved)) return "";
  const checked = priced(estimate).some(line => line.evidence?.checked_at);
  return sample || (checked && !live) ? "warn" : "ok";
}

/** "Prices checked at 15:40 · 15 live · 19 saved · 3 sample", from the evidence of the lines to buy; null if no live check ran. */
function priceCheckLine(estimate: WeeklyGroceryEstimate): string | null {
  const checked = priced(estimate).map(line => line.evidence?.checked_at).filter((value): value is string => !!value).sort().at(-1);
  if (!checked) return null;
  const count = priceCounts(estimate);
  const time = new Date(checked).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Singapore" });
  const mix = ([[count.live, "live"], [count.saved, "saved"], [count.sample, "sample"]] as const)
    .filter(([n]) => n > 0).map(([n, word]) => `${n} ${word}`).join(" · ");
  return `${count.live ? `Prices checked at ${time}` : `Live prices not available at ${time}`} · ${mix}`;
}

/**
 * Short, user-facing note on where prices came from, read from the products
 * actually used rather than the mode that was asked for: a live request that
 * fell back to sample data must not be labelled as FairPrice prices.
 */
/** The backend's note that pantry basics (seasonings, rice, flours and the like) are assumed at home (layer 08),
 *  or null when the week assumes none. */
export function basicsNote(estimate: WeeklyGroceryEstimate): string | null {
  return estimate.warnings?.find(warning => warning.startsWith("Pantry basics are assumed at home")) ?? null;
}

/** "A", "A and B", "A, B and C". */
const andList = (words: string[]): string => (words.length < 2 ? words.join("") : `${words.slice(0, -1).join(", ")} and ${words.at(-1)}`);

export function priceSourceLabel(estimate: WeeklyGroceryEstimate): string {
  const checked = priceCheckLine(estimate);
  if (checked) return checked;
  const lines = priced(estimate);
  const samples = priceCounts(estimate).sample;
  if (!lines.length || samples === lines.length) return "Sample prices";
  // The stores whose prices are shown (FairPrice alone unless a line is Cold Storage's).
  const stores = (["fairprice", "cold_storage"] as const).filter(store => lines.some(line => lineRetailer(line) === store && priceKind(line) !== "sample"));
  const names = stores.length ? stores.map(store => RETAILER_NAME[store]) : [RETAILER_NAME.fairprice];
  if (samples) return `${andList([...names, "sample"])} prices — source shown on each item`;
  const fetched = lines.map(line => line.evidence?.fetched_at ?? line.product!.fetched_at).sort()[0]!;
  const date = new Date(fetched).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  return `${andList(names)} prices from ${date}`;
}

/** An observation's date is never replaced by the time a later price check was attempted. */
export function groceryPriceLabel(line: GroceryLineEstimate): string {
  if (!line.product) return line.packages_required > 0 ? "Not priced" : "Not bought · no price needed";
  const evidence = line.evidence;
  const source = evidence?.price_source ?? evidence?.mode;
  if (source === "no_external_product") return "Sample price · no matching FairPrice product; not checked";
  const kind = priceKind(line);
  const date = new Date(evidence?.fetched_at ?? line.product.fetched_at).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  const base = kind === "sample"
    ? "Sample price"
    : lineRetailer(line) === "cold_storage" ? `${RETAILER_NAME.cold_storage} price from ${date}` : `${kind === "live" ? "FairPrice" : "Saved FairPrice"} price · ${date}`;
  switch (evidence?.lookup_status) {
    case "timeout": return `${base} · not checked live in time`;
    case "selected_product_not_returned": return `${base} · selected product not found`;
    case "out_of_stock": return `${base} · product marked unavailable`;
    case "provider_error":
    case "schema_drift":
    case "invalid_price": return `${base} · current price could not be checked`;
    default: return base;
  }
}

export function groceryPriceTimes(line: GroceryLineEstimate): string | undefined {
  if (!line.product) return undefined;
  const format = (value: string) => new Date(value).toLocaleString("en-SG", { timeZone: "Asia/Singapore" });
  const observed = line.evidence?.fetched_at ?? line.product.fetched_at;
  const checked = line.evidence?.checked_at;
  return `Price observed: ${format(observed)}${checked ? `; check attempted: ${format(checked)}` : ""}`;
}

/**
 * The same note for a /browse product search (ADR-0026 section 4): sample prices say so,
 * saved FairPrice prices give their date, and a fallback is one plain clause, never the raw warning.
 */
export function productSourceLabel(result: ProductSearchResponse): string {
  const missed = result.fallback_used ? ": FairPrice didn't respond" : "";
  if (result.provider_used !== "fairprice") return `Sample prices${missed}`;
  if (!result.cached) return "FairPrice prices now";
  const fetched = result.items.map(item => item.fetched_at).sort()[0];
  if (!fetched) return `Saved FairPrice prices${missed}`;
  const date = new Date(fetched).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  return `FairPrice prices from ${date}${missed}`;
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
  /** The main dish first, then the other mains, the vegetable dishes, the soup and the staple last. */
  dishes: NutritionDashboardDay[];
  status: "planned" | "completed" | "skipped" | "partial";
}

export interface PlannedDay {
  dayIndex: number;
  date: string;
  meals: PlannedMeal[];
}

// A meal's dishes as a table reads them: main, other mains, vegetables, soup, anything else, then the staple.
const ROLE_ORDER = ["main", "vegetable", "soup", "", "staple"];

function roleRank(roleId: string | undefined): number {
  const [, base = "main", copy] = /^(.*?)(?:-(\d+))?$/.exec(roleId ?? "main") ?? [];
  const rank = ROLE_ORDER.indexOf(base);
  return (rank < 0 ? ROLE_ORDER.indexOf("") : rank) * 100 + Number(copy ?? 1);
}

/** The staple of a full meal (ADR-0070): rice, noodles or bread, shown as such. */
export function isStapleDish(dish: Pick<NutritionDashboardDay, "role_id">): boolean {
  return dish.role_id === "staple";
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
      meal.dishes.sort((a, b) => roleRank(a.role_id) - roleRank(b.role_id));
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

/**
 * Follow-up chips from the plan's own days and meals: swap the next meal still to cook, skip the day after its day,
 * keep the last day. A chip whose day the plan does not have is left out, so a one-day plan offers a swap only.
 * Past seven days a weekday repeats, so a chip names the date the assistant reads.
 */
export function followUpChips(days: NutritionDashboardDay[], today: string): string[] {
  const next = nextMeal(days, today);
  if (!next) return [];
  const weekday = (date: string) => sentenceDay(date, new Set(days.map(item => item.planned_date)).size > 7);
  const open = mealsByDay(days).filter(day => day.meals.some(meal => meal.status === "planned" || meal.status === "partial"));
  const first = open.findIndex(day => day.dayIndex === next.meal.dayIndex);
  const later = open.slice(first + 1);
  const skip = later[0];
  const keep = later.length > 1 ? later.at(-1) : undefined;
  return [
    `Swap ${weekday(next.meal.date)}'s ${next.meal.mealType}`,
    ...(skip ? [`Skip ${weekday(skip.date)}`] : []),
    ...(keep ? [`Don't change ${weekday(keep.date)}`] : []),
  ];
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


/** A kept or skipped dish stays the same dish, so it reads as what happens to it, not as a swap to itself. */
export function sameDishChange(event: Pick<MealPlanReplanEvent, "event_type" | "before_entry" | "meal_entries">): string | null {
  const title = event.before_entry?.recipe_title;
  if (!title) return null;
  // "Don't change Monday's dinner" keeps every dish of that meal.
  const kept = (event.meal_entries ?? []).map(dish => dish.recipe_title);
  if (event.event_type === "LOCK_MEAL" && kept.length > 1) return `Keep ${kept.slice(0, -1).join(", ")} and ${kept.at(-1)} as they are`;
  if (event.event_type === "LOCK_MEAL") return `Keep ${title} as it is`;
  if (event.event_type === "CANCEL_MEAL") return `Skip ${title}`;
  return null;
}

/** What a change does to the shopping: "groceries +S$2.80", or "groceries stay the same", never "+S$0.00". */
export function groceriesChange(delta: number): string {
  if (Math.abs(delta) < 0.005) return "groceries stay the same";
  return `groceries ${delta > 0 ? "+" : "−"}S$${Math.abs(delta).toFixed(2)}`;
}

/**
 * A preview card's two buttons, in the words of what each does. Discarding a lock keeps the dish
 * unlocked, so "Keep as is" would say the opposite; for a swap or a skip it keeps the dish, as it says.
 */
export function previewChoices(eventType: MealPlanReplanEvent["event_type"]): { confirm: string; discard: string } {
  if (eventType === "LOCK_MEAL") return { confirm: "Keep it locked", discard: "Cancel" };
  return { confirm: "Confirm change", discard: "Keep as is" };
}

/**
 * When a changed dish is eaten, by the plan's own weekday and meal ("Thu dinner"), as a shape change names
 * its days; a shape change says that itself (null), and an old event without the dish's day keeps its date.
 */
export function changedMealWhen(event: Pick<MealPlanReplanEvent, "before_entry" | "after_entry" | "shape_change" | "applied_at" | "created_at">, startDate: string | null | undefined): string | null {
  if (event.shape_change) return null;
  const dish = event.before_entry ?? event.after_entry;
  if (dish?.day_index) return `${planDayLabel(startDate, dish.day_index)} ${dish.meal_type ?? "dinner"}`;
  return formatPlanDate((event.applied_at ?? event.created_at).slice(0, 10), { day: "numeric", month: "short" });
}

/**
 * The conversation to reopen beside the household's current week: the newest one that planned it or
 * took it on to change it. Else the newest one ready to plan a week, so an interrupted first plan
 * picks up where it stopped. Else none: a fresh conversation, never an unrelated one.
 */
export function conversationForPlan<T extends { plan_id: number | null; can_confirm: boolean }>(conversations: T[], planId: number | null): T | null {
  return (planId === null ? undefined : conversations.find(item => item.plan_id === planId))
    ?? conversations.find(item => item.can_confirm)
    ?? null;
}

export const FEEDBACK_BUTTONS: Array<{ kind: FeedbackKind; label: string }> = [
  { kind: "like", label: "Like" },
  { kind: "dislike", label: "Dislike" },
  { kind: "never_again", label: "Never again" },
];

/** The dish's feedback after a button is clicked: the pressed one again undoes it (null), another replaces it. */
export function nextFeedback(current: FeedbackKind | null | undefined, clicked: FeedbackKind): FeedbackKind | null {
  return current === clicked ? null : clicked;
}

/** A dish's facts for the panel its reason tags open (layer 08 section 7.2): what is true of it as planned, never
 * why it was chosen. Nutrition is per person at the dish's share of the meal. */
export function dishFacts(dish: Pick<NutritionDashboardDay, "recipe" | "nutrition_per_person" | "cost_per_serving_sgd">): Array<{ label: string; value: string }> {
  return [
    { label: "Cooking time", value: `${dish.recipe.total_time_minutes} min` },
    { label: "Energy", value: `${Math.round(dish.nutrition_per_person.calories_kcal)} kcal per person` },
    { label: "Sodium", value: `${Math.round(dish.nutrition_per_person.sodium_mg)} mg per person` },
    { label: "Cost to buy", value: dish.cost_per_serving_sgd == null ? "Not known" : `${formatSgd(dish.cost_per_serving_sgd)} per serving` },
  ];
}
