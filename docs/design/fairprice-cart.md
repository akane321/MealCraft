# FairPrice cart

MealCraft puts a confirmed shopping list into the person's own FairPrice cart. The person checks out and pays on
FairPrice's own site; MealCraft never sees the FairPrice account, a password or a payment detail (Knowledge
ADR-0101, ADR-0103 section 4).

## Shape

```
MealCraft page ──(1) POST /api/plans/{id}/fairprice-cart/prepare──▶ MealCraft API ──live lookup──▶ FairPrice listing
      │  shows ready lines, problems, price changes, budget
      │
      ├──(2) chrome.runtime.sendMessage(EXTENSION_ID, add_to_cart)──▶ MealCraft FairPrice cart extension
      │                                                                 │ finds or opens a www.fairprice.com.sg tab
      │                                                                 │ runs in that tab, as the logged-in person:
      │                                                                 │   GET  /api/cart  (the current cart)
      │                                                                 │   POST /api/cart  (current items + ours)
      │◀──────────────────────────── report per line ────────────────────┘
      │
      └──(3) POST /api/plans/{id}/fairprice-cart/report──▶ MealCraft API  (plan marked "in FairPrice cart")
```

- The MealCraft server never calls FairPrice's cart. Only the extension does, inside the person's own logged-in
  tab, with that tab's own session.
- Nothing is removed from the person's cart. The extension reads the current cart first and sends it back with
  MealCraft's lines added; if it cannot read the current cart, it sends nothing.
- No checkout, no payment, no address change. A bot check or a refused request is never worked around: the
  report says so and the person can use the product links instead.
- Delivery fee, minimum order and slots are not modelled (Knowledge ADR-0068).

## FairPrice facts this relies on (read from the public site, 2026-10-29)

- The cart is `https://website-api.omni.fairprice.com.sg/api/cart`: `GET` reads it, `POST` writes the whole cart.
  Requests carry `Authorization: Bearer <token>`, where the token is the `auth_token` cookie of
  `www.fairprice.com.sg`. Without that cookie the person is not logged in.
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
- Messages:
  - `{type: "ping"}` returns `{ok: true, version}`.
  - `{type: "add_to_cart", lines: [{line_key, cart_item_id, quantity}], dry_run?: boolean}` returns
    `{ok, error?, results: [{line_key, cart_item_id, status, quantity, cart_price_sgd}], cart_changed?}`.
  - Limits: 1 to 500 lines, `cart_item_id` digits with no leading zero, `quantity` 1 to 999.
  - A dry run returns `{ok: true, dry_run: true, body, results}` with status `would_add`. It writes nothing and is
    never reported to the API.
  - `cart_changed` lists the ids of items already in the cart whose quantity was different after the write, or
    that were missing. The page then asks the person to check their cart.
  - One add runs at a time; an overlapping message gets `busy`.
  - The tab used is a loaded, non-discarded FairPrice tab that is not on a checkout or payment page. Otherwise a
    new tab is opened on the home page.
- `error` is one of:
  - `not_logged_in`: no `auth_token` cookie in the FairPrice tab;
  - `cart_unreadable`;
  - `request_refused`: a 401/403 or a challenge page;
  - `unexpected_response`;
  - `invalid_request`: the message broke the limits, so nothing was sent;
  - `busy`: another add is still running.
  For an error before the write (`not_logged_in`, `cart_unreadable`, or a refused or unreadable read), nothing was
  written. When the write itself is refused or its answer cannot be read, the write may or may not have happened,
  so the page asks the person to look at their FairPrice cart.
- An item in the current cart without an id or a whole-number quantity makes the cart `cart_unreadable`, because
  sending it back could change it.
- The page adds two errors of its own: `no_extension` and `timeout`.
- Tests: `node --test browser-extension/fairprice-cart/cart-core.test.js`.

## Live test

- The owner logs in to FairPrice in their own browser. The agent never types the password and never checks out.
- First a `dry_run` with two cheap items, read against the real cart response. Then one real add of those two
  items. The cart is checked by eye, and the owner decides whether to remove them.
- What the live test confirms is written back into this document: the response shape, and where the store and
  address come from.
