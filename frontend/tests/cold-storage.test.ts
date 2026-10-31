import { describe, expect, it } from "vitest";

import { COLD_STORAGE_NOTE, budgetWarning, otherStoresTotal } from "../app/lib/fairprice-cart";
import { groceryPriceLabel, groceryStores, groceryTrips, hasColdStorage, lineRetailer, priceSourceLabel } from "../app/lib/home-surface";
import type { FairPriceCartPrepare, WeeklyGroceryEstimate } from "../app/types/meal-plan";
import type { GroceryLineEstimate } from "../app/types/recommendation";

function line(name: string, cost: number, category: string, retailer: GroceryLineEstimate["retailer"], extra: Partial<GroceryLineEstimate> = {}): GroceryLineEstimate {
  const source = retailer ?? "fairprice";
  return {
    ingredient_name: name.toLowerCase(),
    ingredient_display_name: name,
    packages_required: 1,
    purchase_cost_sgd: cost,
    required_quantity: 300,
    unit: "g",
    retailer,
    product: { category, package_size: 500, package_unit: "g", fetched_at: "2026-10-30T08:00:00Z", source, product_url: `https://store.example/${name}` },
    ...extra,
  } as GroceryLineEstimate;
}

const items = [
  line("Rice", 4, "Pantry", "fairprice"),
  line("Kale", 5.5, "Vegetables", "cold_storage"),
  line("Egg", 3, "Dairy", "fairprice"),
  line("Miso", 6, "Pantry", "cold_storage"),
];

describe("Cold Storage on the list", () => {
  it("names the store of a line from its retailer, else its product, else FairPrice", () => {
    expect(lineRetailer(items[1]!)).toBe("cold_storage");
    expect(lineRetailer({ ...items[1]!, retailer: undefined })).toBe("cold_storage");
    expect(lineRetailer({ ...items[0]!, retailer: undefined })).toBe("fairprice");
    expect(lineRetailer({ ...items[0]!, retailer: null, product: null })).toBe("fairprice");
    expect(hasColdStorage(items)).toBe(true);
    expect(hasColdStorage([items[0]!, items[2]!])).toBe(false);
  });

  it("groups each trip by store, FairPrice first, then Cold Storage, each with its aisles", () => {
    const [trip] = groceryTrips(items);
    expect(trip!.stores.map(store => store.name)).toEqual(["FairPrice", "Cold Storage"]);
    expect(trip!.stores[0]!.groups.map(group => group.name)).toEqual(["Dairy", "Pantry"]);
    expect(trip!.stores[1]!.groups.map(group => [group.name, group.lines.map(item => item.ingredient_display_name)])).toEqual([["Pantry", ["Miso"]], ["Vegetables", ["Kale"]]]);
    // The aisles across stores are still there, as before.
    expect(trip!.groups.map(group => group.name)).toEqual(["Dairy", "Pantry", "Vegetables"]);
  });

  it("splits each of two trips, and leaves a store with nothing to buy out", () => {
    const two = [{ ...items[0]!, shopping_trip: 1 }, { ...items[1]!, shopping_trip: 1 }, { ...items[3]!, shopping_trip: 2 }];
    const trips = groceryTrips(two);
    expect(trips.map(trip => trip.stores.map(store => store.name))).toEqual([["FairPrice", "Cold Storage"], ["Cold Storage"]]);
    expect(groceryStores([line("Rice", 0, "Pantry", "cold_storage", { packages_required: 0 })])).toEqual([]);
  });

  it("is one FairPrice store, the list as before, when no line is Cold Storage's", () => {
    const [trip] = groceryTrips([items[0]!, items[2]!]);
    expect(trip!.stores).toHaveLength(1);
    expect(trip!.stores[0]!.groups).toEqual(trip!.groups);
  });

  it("labels a price by its store", () => {
    expect(groceryPriceLabel(items[1]!)).toBe("Cold Storage price from 30 Oct");
    expect(groceryPriceLabel(items[0]!)).toBe("Saved FairPrice price · 30 Oct");
  });

  it("names both stores in the price note", () => {
    const estimate = { pricing_mode: "fixture", items } as WeeklyGroceryEstimate;
    expect(priceSourceLabel(estimate)).toBe("FairPrice and Cold Storage prices from 30 Oct");
    expect(priceSourceLabel({ ...estimate, items: [items[1]!] })).toBe("Cold Storage prices from 30 Oct");
    const sample = line("Salt", 1, "Pantry", "fairprice", { product: { ...items[0]!.product!, source: "fixture" } });
    expect(priceSourceLabel({ ...estimate, items: [items[1]!, sample] })).toBe("Cold Storage and sample prices — source shown on each item");
  });
});

describe("the FairPrice cart with Cold Storage lines", () => {
  const prepare = (over: Partial<FairPriceCartPrepare>): FairPriceCartPrepare => ({
    plan_id: 12,
    shopping_trip: null,
    fingerprint: "abc",
    lines: [],
    ready_total_sgd: 13.9,
    planned_total_sgd: 131.2,
    projected_total_sgd: 132.3,
    budget_sgd: 140,
    over_budget: false,
    ...over,
  });
  const other = [{ retailer: "cold_storage" as const, lines: 2, purchase_total_sgd: 11.5 }];

  it("counts the other stores' totals in the budget figure", () => {
    expect(otherStoresTotal(prepare({}))).toBe(0);
    expect(otherStoresTotal(prepare({ other_stores: other }))).toBe(11.5);
    expect(budgetWarning(prepare({ other_stores: other }))).toBeNull();
    expect(budgetWarning(prepare({ other_stores: other, over_budget: true }))).toBe(
      "At today's FairPrice prices, plus S$11.50 from Cold Storage, this trip comes to S$143.80, S$3.80 over your S$140.00 budget. Your plan is not changed.",
    );
  });

  it("says Cold Storage items stay on the list with links", () => {
    expect(COLD_STORAGE_NOTE).toBe("Cold Storage items stay on your list with links; buy them on coldstorage.com.sg.");
  });
});
