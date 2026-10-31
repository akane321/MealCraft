# Cold Storage, the second retailer

FairPrice stays the main store. Cold Storage fills only the ingredients FairPrice lacks, and it is never chosen
because it is cheaper. Sources: Knowledge ADR-0072 section 1, ADR-0103 section 5, and the owner's decisions of
2026-10-31: the mapping is confirmed as FairPrice's is, the evaluation takes Cold Storage in at the 11-07 freeze,
and price coverage is counted by ingredient. Public issue #394.

## The site (observed 2026-10-31)

- **Search.** `GET https://coldstorage.com.sg/search?q=<query>` returns server-rendered HTML (Next.js App Router).
  - The data is in the React flight payload: the `self.__next_f.push([1,"…"])` strings, concatenated. The product
    list is the JSON value after `"initialProducts":`.
  - Only the first 30 results come with a plain GET, so queries must be specific.
  - `robots.txt` allows everything. No bot check was met at one request a second.
- **Product record.** The fields read are:
  - identity: `productId` (int), `name`, `slug`, `image`;
  - price: `price` (regular), `promoPrice` (what is paid now);
  - stock and weight: `inventoryStatus` (`"In Stock"` / `"Out of Stock"`), `averageWeight` (null, or kg as a
    string).
- **Weighted items.** With a non-null `averageWeight`, `price` and `promoPrice` are per kg. The pack price is
  `round(promoPrice × averageWeight, 2)`, and the regular price is computed the same way from `price`.
- **Empty result.** A page with no `initialProducts` that contains "Sorry, we couldn't find any results for" is a
  no-match. A page with neither is schema drift (`ProductSchemaDriftError`).
- **Package size.** It is only in the name ("600ml", "24oz (680g)", "1Kg"). It is read with
  `products.provider.parse_package_size`. A weighted item's size is its `averageWeight`.
- **Halal.** `isHalal` was false on all 114 products sampled, including products named "(Halal)". It is not
  trusted: every Cold Storage product has `halal_certified = None`. A halal household therefore never buys a line
  that needs certification from Cold Storage (docs/design/halal.md).
- **Etiquette.** Public GETs only, no login, at most one request a second, a cap per run, and a stop at the first
  non-200 or unrecognised page. The User-Agent is the app's own (`MealCraft/0.1 academic prototype`).

## Identity

- A Cold Storage product's `external_id` is `cs-<productId>`, for example `cs-78715`, everywhere: in the live
  provider, the snapshot, the cache, the grocery line and the console. This keeps it apart from FairPrice's numeric
  ids in every map keyed by `external_id`, such as the halal facts and the frozen catalog.
- `product_url` is `https://coldstorage.com.sg/product/<slug>`.
- `ProductResponse.source` and `PriceEvidence.source` are `"cold_storage"`, whether the product came live, from the
  cache or from the snapshot. `PriceEvidence.mode` says which.
- Parser versions are `cold-storage-flight-v1` (live) and `cold-storage-capture-v1` (capture).

## Data: the same flow as FairPrice

The data-engineering side mirrors `capture_fairprice_snapshot.py` and `fairprice_mapping.py`.

- **Capture.** `data-engineering/scripts/capture_cold_storage_snapshot.py` uses the standard library only.
  - It searches the ingredients FairPrice lacks: every v2.2 release ingredient that is not in
    `data/products/fairprice-v2-snapshot.json` and is not `not_purchased`.
  - The queries are the mapping's `search_again` texts, then the canonical name; at most 3 per ingredient.
  - It appends rows to `data-engineering/data/enrichment/cold_storage/v1/observations.jsonl`, in the FairPrice row
    shape: `{ingredient_id, query, parser_version, status, result_count, products[], fetched_at}`. Each trimmed
    product is `{product_id, name, slug, price, promo_price, average_weight, in_stock, url}`.
- **Proposal.** The AI proposes rows in `data-engineering/data/enrichment/cold_storage/v1/mapping.jsonl`, with the
  same fields and checks as FairPrice: `ingredient_id`, `status` (`mapped` / `unavailable`), `selected[{product_id,
  package_grams, package_grams_basis}]`, `rejected[{product_id, reason}]`, `search_again[]`, `confidence`, `notes`,
  `enriched_by`, `review_status: "proposed"`.
- **Export.** It writes `data/products/cold-storage-v1-snapshot.json`, in the shape of `fairprice-v2-snapshot.json`
  (`snapshot_version: "cold-storage-v1"`, `source: "cold_storage"`, `fetched_from`, `fetched_to`,
  `min_confidence: 0.6`, `ingredients`). The ingredients are keyed by the lower-case id without `ING_`. Each entry
  is `{status, review_status, products[{external_id: "cs-…", name, brand: null, category: null, package_grams,
  package_grams_basis, price_sgd, product_url, in_stock, query, fetched_at}]}`. The same skip rules apply:
  `unavailable`, `owner_corrected`, and `mapped` below 0.6.
- **Review (owner, 2026-10-31: as FairPrice).** The proposals are used as they are. A person reviews a fixed-seed
  sample of 40 (`data-engineering/docs/cold-storage-v1-review-sample.csv`). Their verdicts are recorded by
  `cold_storage_mapping.py record` into the sampled-review JSON beside it, and corrections are made in the console.
- **Coverage after two capture passes.**
  - The first pass searched the `search_again` texts. The follow-up searched the canonical name and a simpler
    shopper's form.
  - Together they made 669 requests at one a second.
  - Cold Storage prices 45 of the 180 ingredients FairPrice lacks. 49 of them had no candidate at Cold Storage at
    all.
  - The coverage report (`docs/evaluation/price-coverage/latest.md`) has the shares.
- **`fairprice-v2-snapshot.json` and FairPrice's `mapping.jsonl` are never edited.** The frozen evaluation reads
  them.

## Runtime

- **Loader: `backend/app/planning/retailers.py`.**
  - `COLD_STORAGE_SNAPSHOT_FILE = "products/cold-storage-v1-snapshot.json"`.
  - `cold_storage_snapshot()` is cached and rounds prices to 2 dp, like `release_snapshot()`.
  - `cold_storage_products()` returns the snapshot plus console overrides of kind `product_mapping:cold_storage`,
    minus entries whose status is `removed`.
  - `fairprice_only()` is a context manager over a `ContextVar`. Inside it, `cold_storage_products()` returns `{}`.
  - `retailer_of(product) -> "fairprice" | "cold_storage"` returns `"cold_storage"` exactly when
    `product.source == "cold_storage"`.
- **Priceable.** `grocery_estimator.priceable_ingredients()` also includes `cold_storage_products()` keys whose
  status is `mapped`.
- **Choosing (`grocery_estimator.choose_product`, the one place).**
  1. The FairPrice branches run first, unchanged: the curated matcher, then the reviewed FairPrice mapping.
  2. If they end with no product, Cold Storage is tried. That covers no FairPrice mapping, FairPrice's mapping not
     `mapped`, and no FairPrice product in stock. Cold Storage is skipped when the line needs certification for a
     halal household, and when the ingredient has no mapped Cold Storage entry.
  3. Cold Storage takes the cheapest in-stock product for the quantity, by the same cost function. In live mode
     the products are first refreshed by a live Cold Storage search of the entry's first query, as the FairPrice
     release branch does. Only reviewed ids are kept.
  4. A FairPrice product in stock always wins, whatever it costs.
- **The budget half of the candidate packet.** With a budget, half of each kind's places go to the cheapest of the
  rest. They are ordered by `product_path.cheap_first`: dishes FairPrice alone supplies come first, then cost as
  used. A dish that buys a line at Cold Storage comes after those.
  - Why: such dishes, mostly soups with a Cold Storage broth, are cheap as used and dear in whole packages.
  - Ranked by use alone, they pushed the cheap FairPrice soups out of the packet, and the walkthrough's cheapest
    week went from S$70 to S$110 although it bought nothing at Cold Storage.
  - Without a Cold Storage line the order is unchanged.
- **Live search.** `ProductSearchService.search(query, *, live, refresh=False, limit=10, retailer="fairprice")`
  - With `retailer="cold_storage"` it uses the Cold Storage live provider, the cache under
    `source="cold_storage"`, and its own lookup budget and failure counters.
  - Its degradation chain is live, then cache, then nothing. There are no Cold Storage fixtures for
    non-live mode: offline, Cold Storage products come from the snapshot.
  - `refresh_selected` (the final price check before the cart) stays FairPrice-only, and only FairPrice lines are
    passed to it.
- **Settings.** `coldstorage_base_url` (`https://coldstorage.com.sg`), `coldstorage_timeout_seconds`,
  `coldstorage_cache_ttl_minutes`.
- **The grocery line.**
  - `GroceryLineEstimate.retailer: Literal["fairprice", "cold_storage"] | None` is `retailer_of(product)` when the
    line has a product, else `None`. It is set wherever a line gets its product.
  - It is saved in `meal_plan_grocery_items.retailer`, a column that exists already, and read back.
  - A line bought at Cold Storage carries a short `note`: "FairPrice has no product for this; bought at Cold
    Storage."
- **Budget.** The totals count both stores, as they already sum every line. A two-trip plan keeps the budget per
  trip (ADR-0084).
- **FairPrice cart.**
  - `prepare` takes only lines whose `retailer` is `fairprice` (or `None`). A Cold Storage line is neither
    rechecked nor counted as a cart problem.
  - The response adds `other_stores: [{retailer, lines, purchase_total_sgd}]`. The panel's budget figure is the
    FairPrice projection plus these totals.
- **Console (the same queue).**
  - The mapping list, change and remove routes take `retailer` (query parameter, default `fairprice`).
  - Cold Storage edits are console overrides of kind `product_mapping:cold_storage`.
  - `OpsProductMapping.retailer` names the store.
  - The product search used to pick a replacement takes the same `retailer` parameter.

## Evaluation (owner, 2026-10-31: Cold Storage joins at the 11-07 freeze)

- Until the freeze, the frozen-catalog evaluation stays FairPrice-only. That covers the v2 and v3 runners and their
  scorers, the baselines, the workbench and the held-out paths. They run inside `fairprice_only()`, so their reports
  and digests do not change. `release_catalog` and the held-out label derivation keep reading only the FairPrice
  snapshot.
- The product's regression reports plan the release catalog as the product does, with Cold Storage:
  `docs/evaluation/full-default`, `shared-dish` and `household-rules`. They are regenerated.
- At the freeze, the frozen catalog takes `cold-storage-v1-snapshot.json` in, together with data v3.

## Price coverage (owner, 2026-10-31: by ingredient)

`python -m app.data.price_coverage` writes `docs/evaluation/price-coverage/latest.md` and `latest.json`. The report
opens with a `> Scope:` line.

- **Ingredient level, the target.** It counts the v2.2 release ingredients that are bought, excluding
  `not_purchased` ones. It reports how many have a price at FairPrice, at Cold Storage only, and in either. The
  target is 90% combined.
- **Recipe level.** It counts the recipes whose every bought line is priced, at FairPrice alone and combined.
- **Line level.** It counts the recipe lines that are priced, at FairPrice alone and combined.

## Interface

- The list is grouped by store within each trip: FairPrice first, then Cold Storage.
  - Each store has a header with its subtotal.
  - Each line names its store.
  - A Cold Storage line links to its product page, and the link does not toggle the line's checkbox.
- The print sheet has the same store sections.
- The FairPrice cart panel says: "Cold Storage items stay on your list with links; buy them on coldstorage.com.sg."
  Its budget figure includes them.
- Price labels name the line's store ("Cold Storage price from <date>").
- The console's mapping page has a store switch, FairPrice or Cold Storage.

## Not in this version

- Cold Storage checkout or cart: its lines are links.
- Any other retailer.
- Cold Storage halal facts: there is no trustworthy attribute.
- Multi-buy offers.
