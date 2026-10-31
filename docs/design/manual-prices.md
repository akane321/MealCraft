# Prices recorded by hand

The last fill layer. After FairPrice, Cold Storage and RedMart, an ingredient none of them prices may have a price
that a person recorded from an online platform, such as Shopee, Lazada or Amazon. Source: the owner, 2026-11-01
(Knowledge ADR-0110, which this extends). Lazada blocked the RedMart capture after about 60 requests, so the
remaining gap is filled by hand, and the list groups these lines by platform.

## The sheet

`data-engineering/data/enrichment/manual/v1/price-sheet.csv` (UTF-8 with BOM, so that Excel reads it) lists the
ingredients no store prices. They are ordered by how many release recipes use them, and the first 63 reach the 90%
target.

- **Given:** `rank`, `ingredient_id`, `ingredient`, `recipes`, `typical_grams_per_recipe`, `example_lines`, and
  search links for Shopee, Lazada and Amazon.
- **The person fills, per product:** `platform`, `product_name`, `product_url`, `price_sgd`, `package_size`,
  `package_unit`, `in_stock` and `observed_date`, with an optional `note`.
  - `platform` is one of `shopee`, `lazada`, `amazon`, `redmart` or `other`.
  - `price_sgd` is the price of the whole listing.
  - `package_unit` is one of `g`, `kg`, `ml`, `l` or `count`.
  - `in_stock` is `y` or `n`.
  - `observed_date` is `YYYY-MM-DD`.
- **Several products for one ingredient:** repeat the row.
- **Nothing found:** leave the row blank.

## Import: `data-engineering/scripts/manual_prices.py`

- **`validate <sheet>`** checks every filled row:
  - the fields are present and well formed;
  - the price is positive with whole cents;
  - the size is positive;
  - the unit is known;
  - the URL's host belongs to the stated platform (`shopee.sg`, `lazada.sg`, `amazon.sg`, `redmart.lazada.sg`, any
    host for `other`);
  - the date is not in the future.

  It names every problem by rank.
- **`export <sheet>`** writes `data/products/manual-v1-snapshot.json` (`snapshot_version: "manual-v1"`,
  `source: "manual"`), with entries keyed like the other snapshots. Each product carries:
  - `external_id: "mn-<rank>-<n>"`;
  - `name`, `product_url`, `price_sgd`, `in_stock`;
  - `retailer` (the platform);
  - `observed_date` as `fetched_at` (midnight Singapore time);
  - `package_grams` and `package_grams_basis`.
- **Grams.**
  - `g` and `kg` convert directly.
  - `ml` and `l` use the release ingredient's own grams per millilitre when its record has one, else 1.0 g/ml. The
    basis says which.
  - `count` uses the release ingredient's grams per item when known; otherwise the row is refused.
- **Review.** The person who records the price is the review: every row is `owner_recorded`, and there is no
  proposal step.

## Runtime

- **Fill order.** `planning/retailers.SECOND_STORES` gains `"manual"` last. `store_products("manual")` reads the
  snapshot, and returns `{}` inside `fairprice_only()`. A manual product is a candidate only when no earlier store
  has an in-stock product. It is never refreshed live, so it always reads as a saved price of its date.
- **Retailer of a line.** A manual product's `ProductResponse.source` is `"manual"`, and its `retailer` field is the
  platform. `retailer_of(product)` returns that platform.
  - `Retailer` becomes `"fairprice" | "cold_storage" | "redmart" | "shopee" | "lazada" | "amazon" | "other"`.
  - A manual line has `retailer` set to its platform, so the list groups it with that platform. A manual `redmart`
    row groups with RedMart's own lines.
  - `PriceEvidence.source` gains `"manual"`, with `mode: "snapshot"`.
- **Labels.** A manual line reads "Price recorded by hand on <date>". Halal is unknown (`None`), as for every store
  but FairPrice.
- **Cart and coverage.** The cart's `other_stores` has one entry per platform. The coverage report adds a
  "Recorded by hand only" column.

## Not in this version

- Live prices for these lines.
- A console page for them: the sheet is edited and imported again.
