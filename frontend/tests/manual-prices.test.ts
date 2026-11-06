import { describe, expect, it } from "vitest";

import { budgetWarning, otherStoresNote } from "../app/lib/fairprice-cart";
import { groceryPriceLabel, groceryTrips, lineRetailer } from "../app/lib/home-surface";
import type { FairPriceCartPrepare } from "../app/types/meal-plan";
import type { GroceryLineEstimate, Retailer } from "../app/types/recommendation";

function line(name: string, cost: number, retailer: Retailer | undefined, source: "fairprice" | "cold_storage" | "redmart" | "manual"): GroceryLineEstimate {
  return {
    ingredient_name: name.toLowerCase(),
    ingredient_display_name: name,
    packages_required: 1,
    purchase_cost_sgd: cost,
    required_quantity: 20,
    unit: "g",
    retailer,
    product: { category: "Pantry", package_size: 50, package_unit: "g", fetched_at: "2026-11-01T16:00:00Z", source, product_url: `https://shop.example/${name}` },
  } as GroceryLineEstimate;
}

const items = [
  line("Rice", 4, "fairprice", "fairprice"),
  line("Miso", 6, "cold_storage", "cold_storage"),
  line("Kale", 5.5, "redmart", "redmart"),
  line("Saffron", 9, "shopee", "manual"),
  line("Sumac", 7, "lazada", "manual"),
  line("Matcha", 12, "amazon", "manual"),
  line("Galangal", 3, "other", "manual"),
];

describe("prices recorded by hand on the list", () => {
  it("groups the lines FairPrice, Cold Storage, RedMart, Shopee, Lazada, Amazon, Other shop", () => {
    const [trip] = groceryTrips([...items].reverse());
    expect(trip!.stores.map(store => store.name)).toEqual(["FairPrice", "Cold Storage", "RedMart (Lazada)", "Shopee", "Lazada", "Amazon", "Other shop"]);
    expect(groceryTrips([items[3]!, items[0]!])[0]!.stores.map(store => store.retailer)).toEqual(["fairprice", "shopee"]);
  });

  it("takes the platform from the line's retailer, and a manual product with none is another shop", () => {
    expect(lineRetailer(items[3]!)).toBe("shopee");
    expect(lineRetailer({ ...items[3]!, retailer: undefined })).toBe("other");
  });

  it("a manual RedMart row groups with RedMart's own lines", () => {
    const manual = line("Tahini", 8, "redmart", "manual");
    expect(groceryTrips([items[2]!, manual])[0]!.stores.map(store => [store.retailer, store.groups[0]!.lines.length])).toEqual([["redmart", 2]]);
  });

  it("labels a manual price with the Singapore day it was recorded, never as a live or store price", () => {
    expect(groceryPriceLabel(items[3]!)).toBe("Price from 2 Nov");
    expect(groceryPriceLabel({ ...items[3]!, evidence: { source: "manual", mode: "snapshot", fetched_at: "2026-11-01T16:00:00Z" } })).toBe("Price from 2 Nov");
    expect(groceryPriceLabel(items[2]!)).toBe("RedMart price from 2 Nov");
  });
});

describe("the FairPrice cart with platforms recorded by hand", () => {
  const prepare = (over: Partial<FairPriceCartPrepare>): FairPriceCartPrepare => ({
    plan_id: 12, shopping_trip: null, fingerprint: "abc", lines: [], ready_total_sgd: 13.9, planned_total_sgd: 131.2, projected_total_sgd: 132.3,
    budget_sgd: 140, over_budget: true, ...over,
  });
  const stores = [
    { retailer: "shopee" as const, lines: 1, purchase_total_sgd: 9 },
    { retailer: "redmart" as const, lines: 1, purchase_total_sgd: 3 },
    { retailer: "other" as const, lines: 1, purchase_total_sgd: 3 },
  ];

  it("names every store in order, and points to their sites", () => {
    expect(otherStoresNote(prepare({ other_stores: stores }))).toBe("RedMart, Shopee and Other shop items stay on your list with links; buy them on their sites.");
    expect(otherStoresNote(prepare({ other_stores: [stores[0]!] }))).toBe("Shopee items stay on your list with links; buy them on their sites.");
  });

  it("counts every platform in the budget figure", () => {
    expect(budgetWarning(prepare({ other_stores: stores }))).toBe(
      "At today's FairPrice prices, plus S$3.00 from RedMart, S$9.00 from Shopee and S$3.00 from Other shop, this trip comes to S$147.30, S$7.30 over your S$140.00 budget. Your plan is not changed.",
    );
  });
});
