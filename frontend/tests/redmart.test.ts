import { describe, expect, it } from "vitest";

import { budgetWarning, otherStoresNote, otherStoresTotal } from "../app/lib/fairprice-cart";
import { groceryPriceLabel, groceryTrips, hasOtherStore, lineRetailer, priceSourceLabel } from "../app/lib/home-surface";
import type { FairPriceCartPrepare, WeeklyGroceryEstimate } from "../app/types/meal-plan";
import type { GroceryLineEstimate } from "../app/types/recommendation";

function line(name: string, cost: number, category: string, retailer: GroceryLineEstimate["retailer"]): GroceryLineEstimate {
  return {
    ingredient_name: name.toLowerCase(),
    ingredient_display_name: name,
    packages_required: 1,
    purchase_cost_sgd: cost,
    required_quantity: 300,
    unit: "g",
    retailer,
    product: { category, package_size: 500, package_unit: "g", fetched_at: "2026-11-02T08:00:00Z", source: retailer ?? "fairprice", product_url: `https://store.example/${name}` },
  } as GroceryLineEstimate;
}

const items = [
  line("Rice", 4, "Pantry", "fairprice"),
  line("Miso", 6, "Pantry", "cold_storage"),
  line("Kale", 5.5, "Vegetables", "redmart"),
  line("Egg", 3, "Dairy", "fairprice"),
];

describe("RedMart on the list", () => {
  it("names a RedMart line from its retailer, else its product", () => {
    expect(lineRetailer(items[2]!)).toBe("redmart");
    expect(lineRetailer({ ...items[2]!, retailer: undefined })).toBe("redmart");
    expect(hasOtherStore([items[0]!, items[3]!])).toBe(false);
    expect(hasOtherStore([items[0]!, items[2]!])).toBe(true);
  });

  it("groups each trip FairPrice, Cold Storage, RedMart, and a missing store is left out", () => {
    const [trip] = groceryTrips(items);
    expect(trip!.stores.map(store => store.name)).toEqual(["FairPrice", "Cold Storage", "RedMart (Lazada)"]);
    expect(trip!.stores[2]!.groups.map(group => [group.name, group.lines.map(item => item.ingredient_display_name)])).toEqual([["Vegetables", ["Kale"]]]);
    expect(groceryTrips([items[0]!, items[2]!])[0]!.stores.map(store => store.retailer)).toEqual(["fairprice", "redmart"]);
  });

  it("labels a RedMart price and names the stores in the price note", () => {
    expect(groceryPriceLabel(items[2]!)).toBe("RedMart price from 2 Nov");
    const estimate = { pricing_mode: "fixture", items } as WeeklyGroceryEstimate;
    expect(priceSourceLabel(estimate)).toBe("FairPrice, Cold Storage and RedMart prices from 2 Nov");
    expect(priceSourceLabel({ ...estimate, items: [items[2]!] })).toBe("RedMart prices from 2 Nov");
  });
});

describe("the FairPrice cart with three stores", () => {
  const prepare = (over: Partial<FairPriceCartPrepare>): FairPriceCartPrepare => ({
    plan_id: 12, shopping_trip: null, fingerprint: "abc", lines: [], ready_total_sgd: 13.9, planned_total_sgd: 131.2, projected_total_sgd: 132.3,
    budget_sgd: 140, over_budget: true, ...over,
  });
  const both = [{ retailer: "redmart" as const, lines: 1, purchase_total_sgd: 3 }, { retailer: "cold_storage" as const, lines: 2, purchase_total_sgd: 11.5 }];

  it("names every other store in the note", () => {
    expect(otherStoresNote(prepare({ other_stores: both }))).toBe("Cold Storage and RedMart items stay on your list with links; buy them on their sites.");
    expect(otherStoresNote(prepare({ other_stores: [both[1]!] }))).toBe("Cold Storage items stay on your list with links; buy them on coldstorage.com.sg.");
    expect(otherStoresNote(prepare({ other_stores: [both[0]!] }))).toBe("RedMart items stay on your list with links; buy them on RedMart (lazada.sg).");
  });

  it("adds every other store's total to the budget figure", () => {
    expect(otherStoresTotal(prepare({ other_stores: both }))).toBe(14.5);
    expect(budgetWarning(prepare({ other_stores: both }))).toBe(
      "At today's FairPrice prices, plus S$11.50 from Cold Storage and S$3.00 from RedMart, this trip comes to S$146.80, S$6.80 over your S$140.00 budget. Your plan is not changed.",
    );
  });
});
