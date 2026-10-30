# FairPrice cart

MealCraft puts a confirmed shopping list into the person's own FairPrice cart. The person checks out and pays on
FairPrice's own site; MealCraft never sees the FairPrice account, a password or a payment detail (Knowledge
ADR-0101, ADR-0103 section 4).

## Shape

```
MealCraft page (groceries tab → FairPrice cart panel)
  ├─ POST /api/plans/{id}/fairprice-cart/prepare ──▶ MealCraft API ──live re-check──▶ FairPrice listing
  ├─ chrome.runtime.sendMessage(EXTENSION_ID, get_cart | add_to_cart | set_quantity)
  │      ▶ MealCraft FairPrice cart extension (service worker, no tab)
  │          reads the person's FairPrice session cookie, then GET/POST FairPrice's /api/cart itself
  │      ◀ the person's real cart, normalized (items, thumbnails, prices, totals)
  └─ POST /api/plans/{id}/fairprice-cart/report | ordered ──▶ MealCraft API (plan marked in cart / ordered)
```

- The MealCraft server never calls FairPrice's cart. Only the extension does, with the person's own session.
- Nothing is removed from the person's cart unless they press remove or set a quantity to 0 in the panel. A write
  sends every existing item back as it was; if the current cart cannot be read, nothing is written.
- No checkout, no payment, no address change. A bot check or a refused request is never worked around.
- Delivery fee, minimum order and slots are not modelled in the plan (Knowledge ADR-0068); the panel shows
  FairPrice's own fees.

## FairPrice facts this relies on (read from the public site, 2026-10-29)

- The cart is `https://website-api.omni.fairprice.com.sg/api/cart`: `GET` reads it, `POST` writes the whole cart.
  Requests carry `Authorization: Bearer <token>`, where the token is the `auth_token` cookie of
  `www.fairprice.com.sg`. Without that cookie the person is not logged in. The API answers CORS with
  `Access-Control-Allow-Origin: *` and no credentials, so the request sends the bearer token only and never cookies;
  a credentialed request is blocked by the browser (first live dry run, 2026-10-29).
- The write body follows the site's own `getCartRequestBody` (read from its public bundle on 2026-10-29): the
  account's `customerId` (the page data's `account.id`), `storeId` as a string, `addressId`, `cart.items`,
  `cart.isOutOfStockEnabled`, `cart.dropUnavailableItems: []`, `orderType`, and the flags `isOutOfStockEnabled`,
  `isCheckerEnabled`, `isSellerCheckerEnabled`, `isSellerTimeSlotEnabled`, `isDirectFulfilmentEnabled` and
  `poaItemDropOff: false`. Items are `{id: string, isChecked, q: string, t: epoch seconds, adIds, reason}`; free
  items the server adds are left out; a removal is the item with `q: "0"`. The first write, with numeric ids and
  `t` in milliseconds, added nothing.
- A cart item is `{id, q, isChecked, t, ...}`: `id` is FairPrice's internal product id (the listing's `id`, for
  example `172993`), **not** the number at the end of a product URL (`clientItemId`, for example `13097675`, which
  MealCraft keeps as `external_id`). `q` is the quantity as a string.
- The exact shape of the cart response, and where the store and address of the request come from, are checked on
  the owner's logged-in account during the live test (section "Live test"). Until then the extension's FairPrice
  code is written against the request shape above and keeps a dry-run mode that returns the body it would send.

## API

All three routes need the household session; the two `POST` routes need `X-CSRF-Token`, like plan changes.

### `POST /api/plans/{plan_id}/fairprice-cart/prepare`

Body: `{"shopping_trip": 1 | 2 | null}` (`null` is a plan's only trip). It re-checks the chosen FairPrice
products live, the same way the final basket does (`ProductSearchService.refresh_selected`), and returns:

```json
{
  "plan_id": 12,
  "shopping_trip": null,
  "fingerprint": "sha256 hex of the trip's bought FairPrice lines, see below",
  "lines": [
    {
      "line_key": "1|chicken_breast|g",
      "ingredient_name": "chicken_breast",
      "ingredient_display_name": "chicken breast",
      "product_name": "Kee Song Fresh Chicken - Boneless Breast",
      "client_item_id": "13097675",
      "cart_item_id": "172993",
      "quantity": 2,
      "planned_price_sgd": 6.95,
      "live_price_sgd": 6.95,
      "product_url": "https://www.fairprice.com.sg/product/...",
      "status": "ready"
    }
  ],
  "ready_total_sgd": 13.90,
  "planned_total_sgd": 131.20,
  "projected_total_sgd": 131.20,
  "budget_sgd": 140.0,
  "over_budget": false
}
```

- `status` is one of:
  - `ready`: has a live `cart_item_id` and is in stock.
  - `out_of_stock`: FairPrice lists it as out of stock now.
  - `not_found`: the live listing no longer returns the product, the re-check failed or timed out, or it returned
    no cart id.
  - `no_product`: the line has no FairPrice product (unpriced, a fixture product, another retailer).
  - `not_bought`: `packages_required` is 0, for example covered by the pantry.
- `line_key` is `"{trip or 1}|{ingredient_name}|{unit or ''}"`, the line's identity in a plan.
- `cart_item_id` comes from the live listing record's `id`. `ProductResponse` gains `cart_item_id: str | None`,
  filled by the FairPrice parser and copied by `refresh_selected`. `product_snapshots.cart_item_id` keeps it, so
  a price served from the 15-minute cache still has it; plan lines do not store it.
- `fingerprint` is the SHA-256 hex of the sorted `line_key|client_item_id|quantity` strings, joined by newlines,
  of the trip's stored lines that have a FairPrice product and `packages_required > 0`. It uses only stored fields,
  so the plan response can recompute it.
- Totals:
  - `ready_total_sgd` is the cost of the `ready` lines at live prices (quantity times `live_price_sgd`).
  - `planned_total_sgd` is the trip's saved purchase total.
  - `projected_total_sgd` is that total with each re-checked line at its live price.
  - `budget_sgd` is the trip's weekly budget: per trip for a plan longer than seven days (Knowledge ADR-0084),
    or `null`.
  - `over_budget` is `projected_total_sgd > budget_sgd`. The plan never changes by itself.
- `planned_price_sgd` is the line's saved unit price. `live_price_sgd` is the re-checked unit price, or `null`.
- A plan in fixture pricing mode returns every line as `no_product`, with a 200 and no live calls.

### `POST /api/plans/{plan_id}/fairprice-cart/report`

Body: what the extension reported.

```json
{
  "shopping_trip": null,
  "fingerprint": "from prepare",
  "results": [
    {"line_key": "1|chicken_breast|g", "cart_item_id": "172993", "status": "added", "quantity": 2, "cart_price_sgd": 6.95}
  ]
}
```

- Each result `status` is one of:
  - `added`;
  - `out_of_stock`;
  - `reduced`: FairPrice accepted fewer than asked;
  - `failed`.
- `quantity` is always what this add put in the cart: the asked quantity for `added`, less for `reduced`, 0
  otherwise. When two lines share a product, the shortfall is taken from the later lines.
- A report in which nothing was added (no `added` or `reduced` result with `quantity > 0`) is not stored; the
  response is the unchanged state.
- The plan stores one record per trip: `{status: "in_cart", sent_at, fingerprint, results}`. It lives in the new
  nullable JSON column `meal_plans.fairprice_cart` (migration `20261029_0032`), keyed by trip (`"1"`, `"2"`). A
  `shopping_trip` of `null` is stored as `"1"`.
- The response is the plan's `fairprice_cart` state: `{"1": {status, sent_at, ordered_at, fingerprint, results,
  stale}}`, with no wrapper object.

### `POST /api/plans/{plan_id}/fairprice-cart/ordered`

Body: `{"shopping_trip": ...}`. The person says they checked out. It sets that trip's status to `ordered` with
`ordered_at`. It is a 409 when the trip was never sent.

### In the plan response

- `WeeklyMealPlanResponse.fairprice_cart` is the stored state, or `null`.
- Each trip also carries `stale: true` when its stored fingerprint no longer matches the fingerprint of the
  plan's current lines. In that case the list changed after it was sent.

## Extension

- Lives in `browser-extension/fairprice-cart/` and is loaded unpacked in Chrome or Edge. A fixed `key` in the
  manifest keeps its id stable on every machine, so the page knows `EXTENSION_ID`.
- `externally_connectable` lets only `http://localhost:3000` and `http://127.0.0.1:3000` message it, and it
  checks `sender.url`.
- **It opens no FairPrice tab** (owner, 2026-10-29: the cart lives inside MealCraft).
  - The service worker reads the person's `auth_token` cookie of `www.fairprice.com.sg` with `chrome.cookies`
    (permissions `cookies`, and `storage` for the session cache).
  - It calls FairPrice itself, with that token as the bearer, from the extension: `GET`/`POST
    https://website-api.omni.fairprice.com.sg/api/cart`, and `GET https://www.fairprice.com.sg/user-profile` once a
    session for the account id (`customerId`; kept in `chrome.storage.session` under the first 16 hex characters
    of the token's SHA-256, never returned). The account id is resolved before the cart is read, so the cart
    read and the write run back to back.
  - Nothing else is called. The token, the address and the profile never leave the extension.
- **Write body.** The site's own: see "FairPrice facts". `addressId` is sent as a number, the account address id the
  site sends; the cart GET returns it as a string, and the server refuses a string with "Invalid Cart - error when
  unmarshalling request cart" (live write, 2026-10-29).
- **Messages:**
  - `{type: "ping"}` returns `{ok: true, version}`.
  - `{type: "get_cart"}` returns `{ok, cart}`, the normalized cart below.
  - `{type: "add_to_cart", lines: [{line_key, cart_item_id, quantity}], dry_run?: boolean}` returns
    `{ok, results: [{line_key, cart_item_id, status, quantity, cart_price_sgd}], cart_changed?, cart}`.
    - Limits: 1 to 500 lines, `cart_item_id` digits with no leading zero, `quantity` 1 to 999.
    - A dry run returns `{ok: true, dry_run: true, body, results}` with status `would_add`. It writes nothing and
      is never reported to the API. In its `body`, `customerId` and `addressId` read `"<set>"`, never their values.
    - `cart_changed` lists the ids of items already in the cart whose quantity was different after the write, or
      that were missing.
  - `{type: "set_quantity", cart_item_id, quantity}` sets one item's quantity in the cart (0 removes it, as the
    site does with `q: "0"`) and returns `{ok, cart}`. `quantity` is 0 to 999; the item must already be in the
    cart. A removed unavailable item goes in `cart.dropUnavailableItems`.
  - One write runs at a time; an overlapping write gets `busy`. `get_cart` may run alongside.
- **Normalized cart** (what the page renders; no address, account or token):

  ```json
  {
    "store": {"id": "165", "name": "FairPrice PFC"},
    "items": [{
      "cart_item_id": "185350", "name": "FairPrice Premium Quality Fine Salt", "brand": "FairPrice",
      "display_unit": "500g", "image_url": "https://.../salt.jpg?w=320&q=60",
      "product_url": "https://www.fairprice.com.sg/product/<slug>",
      "quantity": 2, "unit_price_sgd": 0.45, "unit_mrp_sgd": 0.45, "line_total_sgd": 0.9, "line_saving_sgd": 0,
      "max_quantity": 99, "is_checked": true, "note": null
    }],
    "unavailable": [{"cart_item_id": "150002", "name": "...", "image_url": "...", "want_quantity": 1}],
    "totals": {"subtotal_sgd": 0.9, "savings_sgd": 0, "delivery_sgd": 0, "delivery_standard_sgd": 7.99,
               "service_fee_sgd": 0.99, "service_fee_standard_sgd": 0.99, "total_sgd": 1.89}
  }
  ```

  - The unit saving is an applied offer's `productsBought[0].discount` when the item has one, else
    `product.discount`, `item.discount` or `storeSpecificData.discount`. The line saving is that times the
    quantity, shown as 0 when it exceeds `mrp * quantity`, as the site's cart row does (bundle chunk c-1571).
    `unit_price_sgd`, `line_total_sgd` and `line_saving_sgd` follow from it. Where the reply carries an
    applied offer is not confirmed on a live cart.
  - Totals are always numbers: the subtotal falls back to the sum of the line totals, fees to 0, and the total
    to `youPay`, else subtotal plus fees. An item's four money fields are a number, or all `null` when the reply
    has no readable price; the panel shows a dash.
  - Items at quantity 0 are left out of the cart the page sees (the write still sends them as the site does).
  - `subtotal_sgd` is the sum of `sellersAmounts[].amount.orderAmount`, or `amounts.orderAmount` without sellers.
  - `total_sgd` is `youPay`; `savings_sgd` is `savings`.
  - `delivery_*` and `service_fee_*` come from `amounts.shippingAmount`, `standardShippingAmount`,
    `currentServiceFee` and `standardServiceFee`.
  - `note` is the site's own row notice: "Only N left" for `ReducedQuantity`, "Back in stock".
  - `max_quantity` follows stock, `unlimitedStock` and `stockOverride.maxPurchasableStock`, else 99, and stays
    below the bulk thresholds (`bulkOrderThreshold`, `stockOverride.storeBulkOrderThreshold`).
  - Free items the server adds carry `is_free: true`; they are shown but cannot be changed.
- **Errors.** `error` is one of:
  - `not_logged_in`: no `auth_token` cookie, or FairPrice answered 401;
  - `cart_unreadable`;
  - `request_refused`: a 403 or a challenge page;
  - `unexpected_response`;
  - `invalid_request`: the message broke the limits, so nothing was sent;
  - `not_in_cart`: a `set_quantity` for an item no longer in the cart, so nothing was written;
  - `busy`: another write is still running.

  Before a write (`not_logged_in`, `cart_unreadable`, or a refused or unreadable read), nothing was written. When
  the write itself is refused or its answer cannot be read, the write may or may not have happened; the page reads
  the cart again and shows what is there.
- An item in the current cart without an id or a whole-number quantity makes the cart `cart_unreadable`, because
  sending it back could change it.
- An error may carry `detail`: the HTTP status, FairPrice's status and message, or the browser's error message,
  never the token or a cart value.
- The page adds errors of its own: `no_extension` (Chrome found no extension to answer), `timeout`, and
  `interrupted` (the extension stopped before answering, for example when it was reloaded mid-write; the panel
  reads the cart again).
- Tests: `node --test browser-extension/fairprice-cart/cart-core.test.js`.

## Panel

The groceries tab's footer has **FairPrice cart** next to **Preview list** and **Export PDF**. It opens a panel over
the workspace, like the list preview, and shows the person's real FairPrice cart the way a shopping app does.

- **Header:** "FairPrice cart", the store name, a refresh button and close.
- **Setup states:**
  - the extension is missing: install steps and "Check again";
  - not logged in: **Log in to FairPrice**, which opens FairPrice's own login in a small window (the password is
    typed only there), and "I've logged in".
- **This week's list:** `prepare` gives the ready lines. The panel shows how many are ready and their total, which
  are already in the cart (same `cart_item_id`), the price changes and a budget warning, and the lines that can't be
  added, each with **Swap** or a product link. **Add all to cart** sends the ready lines not yet in the cart (a
  line already in the cart is not added twice unless the person asks), then reports to the API.
- **Your cart:** one row per item.
  - Each row shows a thumbnail, the name, the pack size and the unit price (with the original struck through when
    discounted).
  - It has a − / quantity / + stepper (changes wait 500 ms, then `set_quantity`; the row shows it is saving), a
    remove button and the line total.
  - It has a "From this plan" tag for the plan's products, and the site's notices.
  - Unavailable items are listed apart, each with Remove.
- **Summary**, kept in view: subtotal, savings, delivery fee (struck through when waived, "Free" at 0), service
  fee and total.
  - **Checkout on FairPrice** opens FairPrice's checkout in a new tab, the only step that leaves MealCraft.
    Payment always happens on FairPrice's own page, and its pages cannot be embedded (`X-Frame-Options:
    SAMEORIGIN`).
  - **I've checked out** marks the trip ordered.
- **Keeping the view true to the cart.**
  - Adding needs a cart read that is known to be current. A failed first read keeps adding off until
    "Try again" works, and after an unclear failure the panel reads the cart again before it allows another add.
  - Reads and writes go through one queue.
  - The cart is read again when the window regains focus, for example after FairPrice login or checkout.
  - Closing, a Swap or a trip switch first sends a quantity change still waiting for its 500 ms.
  - An item not ticked for checkout on FairPrice shows "Not selected for checkout" and still counts as in the
    cart.
- Nothing in the panel changes the plan. A Swap only puts a can't-buy request in the message box.
- Desktop only (1280×720 and 1440).

## Live test

- The owner logs in to FairPrice in their own browser. The agent never types the password and never checks out.
- First a `dry_run` with two cheap items, read against the real cart response. Then one real add of those two
  items. The cart is checked by eye, and the owner decides whether to remove them.
- What the live test confirms is written back into this document: the response shape, and where the store and
  address come from.
