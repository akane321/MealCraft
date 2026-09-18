import type { NutritionDashboardDay, WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";

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
