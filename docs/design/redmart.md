# RedMart, the third retailer

RedMart, Lazada Singapore's grocery store, fills ingredients that neither FairPrice nor Cold Storage prices. The
fill order is FairPrice, then Cold Storage, then RedMart. A later store is used only when every earlier one has no
in-stock product for the line, and never because it is cheaper. Sources:
- Knowledge ADR-0072 section 1 (other retailers fill gaps, the same flow);
- ADR-0109 (mappings confirmed as FairPrice's; coverage by ingredient; the evaluation takes the second stores in at
  the 11-07 freeze);
- ADR-0110 (owner, 2026-10-31): add an online platform to reach 90%, with RedMart chosen and the risk of Lazada's
  terms accepted.

The machinery is Cold Storage's (`docs/design/cold-storage.md`), generalised from one second store to an ordered
list.

## The site (observed 2026-10-31)

- **Search.** `GET https://www.lazada.sg/tag/<slug>/?ajax=true&q=<query>&page=<n>` returns JSON. The front end
  calls it itself, and it needs no login.
  - `<slug>` is the query lower-cased, with spaces as dashes.
  - The items are `j["mods"]["listItems"]`, 40 to a page.
  - The search covers all of Lazada.
- **RedMart only.** An item is RedMart's when `sellerName == "RedMart"`, or its `sellerId` is `1000008313`, or its
  `icons` include `bizType == "Redmart"`. Every other seller is ignored.
- **Fields:**
  - identity: `itemId`, `skuId`, `name`, `brandName`, `image`, `itemUrl` (`//www.lazada.sg/products/pdp-i<itemId>.html`);
  - price: `price` (a string, SGD) and `originalPrice` (the regular price, when there is a discount);
  - stock: `inStock` (a boolean).
- **Pack size.** It is only in the name. The live adapter reads it with `products.redmart.pack_size`: a bracketed
  bonus counts (`[EXTRA 50G] NESCAFE Gold 200g` is 250 g), a count after the size multiplies it (`Milo 200g x 3` is
  600 g), and the rest is `products.provider.parse_package_size`, which FairPrice's names keep. A product whose name
  gives no size cannot be priced by weight. It is rejected in the mapping, unless the proposal states a size with a
  basis.
- **Empty result.** An empty `listItems`, or no RedMart item on the page, is a no-match.
- **Schema drift.** A response that is not JSON with a `mods.listItems` list is schema drift. That includes `mods`
  without `listItems`, an HTML challenge page, any page with "punish", "captcha" or "x5sec", and a redirect to a
  login. A stock flag that is not a boolean is drift too, never a guess.
- **Halal.** There is no attribute; "Halal" appears only in some names. Every RedMart product has
  `halal_certified = None`, as Cold Storage's do.
- **Etiquette and terms (ADR-0110).**
  - Lazada's robots.txt allows the search paths. Lazada's terms restrict robots, and the owner accepted that risk.
  - Public GETs of this one endpoint only: no login, no account, at most one request a second, and a cap per run.
  - A stop at the first non-200, challenge or unrecognised response. The capture's one exception is a 404: Lazada
    has no such tag, so the capture records a `no_tag` row with no products and goes on. Nothing is ever bypassed:
    no proxies, no header or cookie tricks, no signed APIs.
  - The User-Agent is the app's own.

## Identity

- `external_id` is `rm-<itemId>`, for example `rm-3124212075`. `product_url` is `https:` plus `itemUrl`.
- `ProductResponse.source` and `PriceEvidence.source` are `"redmart"`.
- Parser versions are `redmart-ajax-v1` (live) and `redmart-capture-v1` (capture).

## Data: the same flow as Cold Storage

- **Capture.** `data-engineering/scripts/capture_redmart_snapshot.py` uses the standard library only.
  - It searches every v2.2 release ingredient that neither `fairprice-v2-snapshot.json` nor
    `cold-storage-v1-snapshot.json` prices, and that is not `not_purchased`.
  - The queries are the canonical name, a simpler shopper's form, then the FairPrice and Cold Storage mappings'
    untried `search_again` texts: at most 3 per ingredient.
  - It reads page 2 only when page 1 has no RedMart item.
  - Rows go to `data-engineering/data/enrichment/redmart/v1/observations.jsonl`, in the Cold Storage row shape.
    Each trimmed product is `{product_id, sku_id, name, brand, price, original_price, in_stock, url, image}`.
- **Proposal, export and review.** `data-engineering/scripts/redmart_mapping.py` adapts
  `cold_storage_mapping.py`, with the same checks.
  - The mapping is `data-engineering/data/enrichment/redmart/v1/mapping.jsonl`.
  - The snapshot is `data/products/redmart-v1-snapshot.json` (`snapshot_version: "redmart-v1"`,
    `source: "redmart"`).
  - A fixed-seed sample of 40 is drawn for a person. Its verdicts are accepted, corrected or uncertain.

## Runtime: an ordered list of second stores

- **`planning/retailers.py`.**
  - `SECOND_STORES = ("cold_storage", "redmart", "manual")`, in fill order; the last is the prices recorded by hand
    (`docs/design/manual-prices.md`). Each has a snapshot `products/<cold-storage|redmart|manual>-v1-snapshot.json`
    and a console override kind `product_mapping:<store>`.
  - `store_products(store)` generalises `cold_storage_products()`, which stays as `store_products("cold_storage")`.
    Inside `fairprice_only()`, every second store returns `{}`.
  - `retailer_of(product)` returns `product.source` when it is a second store, else `"fairprice"`.
- **`Retailer`** (backend `schemas/product.py` and frontend `types/recommendation.ts`) is `"fairprice" |
  "cold_storage" | "redmart"`, and the hand-recorded platforms `"shopee" | "lazada" | "amazon" | "other"`
  (`docs/design/manual-prices.md`). `ProductSource`, `PriceEvidence.source` and the retrieval literals gain
  `"redmart"`.
- **Choosing (`grocery_estimator.choose_product`).**
  - The FairPrice branches run first, unchanged. Then each second store is tried in order, and the first that has
    an in-stock reviewed product wins.
  - The skip rules hold for every second store: a halal household's line that needs certification, an ingredient
    with no mapped entry.
  - In live mode a store's products are refreshed by its own live search (limit 40 for RedMart), one search per
    query the reviewed products were captured with, until every reviewed id is seen. Only reviewed ids are kept; one
    no search returns is gone from the shelf.
  - A store that cannot be read live (a failure or a challenge, and no cached answer) keeps its reviewed snapshot
    prices, with a warning: it is not a store with nothing, so no later store fills the line in its place.
- **Live search.** `ProductSearchService.search(..., retailer="redmart")` has its own provider, lookup budget,
  failure counter and cache source. Its chain is live, then cache, then nothing.
  - RedMart is asked nothing more in a request after its first failure (`REDMART_FAILURE_LIMIT = 1`; the other
    stores allow three in a row).
  - The adapter spaces its requests at least a second apart, across the whole process.
- **Settings.** `redmart_base_url` (`https://www.lazada.sg`), `redmart_timeout_seconds`,
  `redmart_cache_ttl_minutes`.
- **`product_path.cheap_first`.** "Needs a second store" means any line whose `retailer` is not `fairprice`.
- **Cart.** `prepare` takes only FairPrice lines. `other_stores` has one entry per other store that has lines.
- **Console.** The mapping routes accept `retailer=redmart`.
- **Coverage.** The report gives one row per layer (FairPrice, Cold Storage only, RedMart only, recorded by hand
  only) and the combined share. An ingredient counts for a layer only when its mapping has a product in stock.

## Interface

- **Store order.** The list and print sheet show FairPrice, then Cold Storage, then RedMart, each with a header and
  subtotal.
- **RedMart lines.** They read "RedMart (Lazada)" and link to the product page; the link does not toggle the
  checkbox.
- **Cart panel.** Its note names every other store: "Cold Storage and RedMart items stay on your list with links."
- **Console.** The store switch has three options.

## Evaluation

The frozen-catalog evaluation stays FairPrice-only until the 11-07 freeze, through `fairprice_only()`. At the freeze
the frozen catalog takes both second-store snapshots in, together with data v3 (ADR-0109, ADR-0110).

## Not in this version

- **Lazada's other sellers.** A third-party Lazada seller's listing is not used: only RedMart.
- **Product-page fetches.** Pack sizes come only from names.
- **Multi-buy offers.**
