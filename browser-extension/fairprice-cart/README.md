# MealCraft FairPrice cart extension

Puts a confirmed MealCraft shopping list into your own FairPrice cart. You check out and pay on
FairPrice's site. Design and message format: `docs/design/fairprice-cart.md`.

## What it does

- Answers only the MealCraft page at `http://localhost:3000` or `http://127.0.0.1:3000`.
- Finds (or opens) a `www.fairprice.com.sg` tab and, inside it, as you, reads your current cart and writes
  it back with the MealCraft lines added.
- Reports per line: added, reduced, out of stock or failed.

## What it never does

- No checkout, no payment, no address or slot change.
- Nothing is removed from the cart. If the current cart cannot be read, nothing is written.
- Never works around a bot check or a refused request; it reports `request_refused` instead.
- Never logs, stores or returns your FairPrice login token. It talks to no server except FairPrice.

## Load it

1. Chrome: open `chrome://extensions`. Edge: open `edge://extensions`.
2. Turn on Developer mode, choose "Load unpacked" and pick this folder (`browser-extension/fairprice-cart`).
3. The id is fixed by the `key` in `manifest.json`: `iogncfhaaajiccdgdnncocllpojhdepm`.
4. Log in to FairPrice in the same browser.

## Dry run

`add_to_cart` with `dry_run: true` reads the cart and returns the request body it would send, with every
line as `would_add`. Nothing is written.

## Live test

The live test against a real FairPrice account is run by the owner, who logs in themselves. Until it is done,
the cart response shape and the store/address fields are unconfirmed (see "Live test" in the design doc).

## Tests

From the repository root: `node --test browser-extension/fairprice-cart/cart-core.test.js`
