# MealCraft FairPrice cart extension

Puts a confirmed MealCraft shopping list into your own FairPrice cart and shows that cart inside MealCraft. You
check out and pay on FairPrice's site. Design and message format: `docs/design/fairprice-cart.md`.

## What it does

- Answers only the MealCraft page at `http://localhost:3000` or `http://127.0.0.1:3000`.
- Opens no FairPrice tab. The service worker reads your `auth_token` cookie of `www.fairprice.com.sg`
  (permission `cookies`) and calls FairPrice's cart API itself, with the token as the bearer and no cookies.
- Asks `https://www.fairprice.com.sg/user-profile` once per login for your account id (needed in the write body)
  and keeps it in `chrome.storage.session` (permission `storage`); it is never returned.
- Messages from the page:
  - `{type: "ping"}` returns `{ok, version}`.
  - `{type: "get_cart"}` returns `{ok, cart}`: store, items (thumbnail, prices, line total, notes, max quantity),
    unavailable items and totals. No address, account or token.
  - `{type: "add_to_cart", lines: [{line_key, cart_item_id, quantity}], dry_run?}` reads the cart, writes it back
    with the lines added and returns per-line results (added, reduced, out of stock or failed) and the new `cart`.
  - `{type: "set_quantity", cart_item_id, quantity}` sets one item (0 removes it) and returns `{ok, cart}`. The item
    must already be in the cart.
- One write runs at a time; a second one gets `busy`. `get_cart` may run alongside.

## What it never does

- No checkout, no payment, no address or slot change.
- Nothing is removed from the cart except the item the person set to 0 in the panel. Every other item is sent back
  as it was; if the current cart cannot be read, nothing is written.
- Never works around a bot check or a refused request; it reports `request_refused` instead.
- Never logs, stores or returns your FairPrice login token. It talks to no server except FairPrice.

## Load it

1. Chrome: open `chrome://extensions`. Edge: open `edge://extensions`.
2. Turn on Developer mode, choose "Load unpacked" and pick this folder (`browser-extension/fairprice-cart`).
   After updating the files, press the reload button on the extension's card (the permissions changed in 0.2.0).
3. The id is fixed by the `key` in `manifest.json`: `iogncfhaaajiccdgdnncocllpojhdepm`.
4. Log in to FairPrice in the same browser.

## Errors

`not_logged_in` (no cookie, or FairPrice answered 401), `cart_unreadable`, `request_refused` (403 or a challenge
page), `unexpected_response`, `invalid_request` (the message broke the limits, or `set_quantity` named a free item; nothing was sent),
`not_in_cart` (`set_quantity` named an item that is neither in the cart nor unavailable; nothing was sent) and `busy`. An error may carry `detail` (HTTP status, FairPrice's status and message),
never the token or a cart value.

## Dry run

`add_to_cart` with `dry_run: true` reads the cart and returns the request body it would send, with every
line as `would_add`. Nothing is written.

## Live test

The live test against a real FairPrice account is run by the owner, who logs in themselves. Until it is done,
the cart response shape is read from FairPrice's public site code, not yet confirmed on a live reply (see "Live
test" in the design doc).

## Tests

From the repository root: `node --test browser-extension/fairprice-cart/cart-core.test.js`
and `node --check browser-extension/fairprice-cart/background.js`.
