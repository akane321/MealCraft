# Prices recorded by hand

The last fill layer. After FairPrice, Cold Storage and RedMart, an ingredient none of them prices may have a price
that a person recorded from an online platform, such as Shopee, Lazada or Amazon. Source: the owner, 2026-10-31
(Knowledge ADR-0110, which this extends). Lazada blocked the RedMart capture after about 60 requests, so the
remaining gap is filled by hand, and the list groups these lines by platform.

## The sheet

`data-engineering/data/enrichment/manual/v1/price-sheet.csv` (UTF-8 with BOM, so that Excel reads it) lists the
ingredients no store priced when it was drawn up (ranks 1-132, ordered by how many release recipes use them).
Since the coverage counts only mappings with a product in stock (2026-11-02), 150 bought ingredients were unpriced
(549 of 699 priced, 78.5%). The 18 of them whose only FairPrice or Cold Storage products were out of stock at
capture were added on 2026-11-06 as ranks 133-148 when a product was found (basil, mustard, msg, baguette, ...).

**2026-11-06 lookup.** An AI web lookup (FairPrice search pages, Amazon.sg, RedMart and Lazada pages, each read
that day) filled 72 rows for 71 ingredients, 61 and 60 after the review below; every row's note says "claude-ai web lookup 2026-11-06, pending owner
spot-check". A product found on FairPrice is recorded as `other` with its fairprice.com.sg URL: the FairPrice
snapshot is not edited, and an `other` line never goes to the FairPrice cart. Anything not clearly the ingredient
(a stand-in, a different form, an unclear pack size) was left blank. A review the same day blanked 11 more rows that
would charge a recipe far more than it uses: six multi-packs (for example enchilada sauce, 6 cans, S$25.46), turkey
mince standing in for turkey, and oversize packs (pistachio, calamansi, venison, Old Bay). Each blank row's note says
why, and a single-unit product can still be recorded there. Coverage is now 609 of 699 (87.1%), so 21
more reach the 90% target; the [coverage report](../evaluation/price-coverage/latest.md) lists the most used still
unpriced.

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
  - the size is positive, and works out to at least 0.01 g;
  - a number too long to read is listed as a problem, like any other;
  - a comma is read only as a thousands separator in a price (`1,234.50`). A decimal comma such as `4,5` is
    refused, never read as 45, and a size may not contain a comma at all;
  - the unit is known;
  - the URL's host belongs to the stated platform, as the domain or one of its subdomains: `shopee.sg`,
    `lazada.sg`, `amazon.sg`; `redmart.lazada.sg` or `lazada.sg` for `redmart`, since RedMart's own product pages
    are on `www.lazada.sg`; any host for `other`. A `redmart` row's URL cannot be told from another Lazada
    seller's by its host, since both are `www.lazada.sg/products/...` pages; the person recording it checks that
    RedMart sells it (see "Not in this version");
  - the date is not in the future.

  It names every problem by rank.
- **`export <sheet>`** writes `manual-v1-snapshot.json` into `data/products/` (`snapshot_version: "manual-v1"`,
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
- **Review.** The person who records the price is the review: such a row is `owner_recorded`, and there is no
  proposal step. An ingredient with a row whose note says `claude-ai web lookup` is `ai_lookup_unreviewed`: an AI read
  that price and no person has checked it yet.
- **One unit.** The planner buys whole listings, so `validate` refuses a product name that says it is a multi-pack
  (`pack of 6`, `12 pack`, `9 x 5.5 oz`).

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
- **Labels.** A manual line's note reads "No store we read sells this; price recorded by hand on <date>". Halal is
  unknown (`None`), as for every store but FairPrice.
- **Evidence.** In the evidence packet a confirmed plan saves, a manual line's item has `source: "manual"` whatever
  its platform: the observation is the person's (`schemas/retrieval.EvidenceSource`).
- **Cart and coverage.** The cart's `other_stores` has one entry per platform. The coverage report adds a
  "Recorded by hand only" column.

## Not in this version

- Live prices for these lines.
- A check that a `redmart` row is RedMart's own listing. The URL host cannot show it, and nothing else in the row
  does.
- A console page for them: the sheet is edited and imported again.
