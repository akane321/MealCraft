// Cart logic for the MealCraft FairPrice cart extension (docs/design/fairprice-cart.md).
// The pure pieces are unit-tested in node; addToCart runs inside the person's logged-in
// www.fairprice.com.sg tab (the extension injects this file into it) and only ever calls
// GET and POST on /api/cart. It never calls checkout, never removes an item, and never
// logs or returns the auth token.
(function (root) {
  "use strict";

  const API = "https://website-api.omni.fairprice.com.sg/api/cart";
  const GET_URL = API + "?orderType=DELIVERY&isCheckerEnabled=true&isSellerCheckerEnabled=true&isOutOfStockEnabled=true";
  const MAX_LINES = 500;
  const MAX_QUANTITY = 999;
  const ERRORS = ["not_logged_in", "cart_unreadable", "request_refused", "unexpected_response", "invalid_request", "busy"];
  const STATUSES = ["added", "reduced", "out_of_stock", "failed"];

  function authToken(cookie) {
    for (const part of String(cookie || "").split(";")) {
      const eq = part.indexOf("=");
      if (eq < 0 || part.slice(0, eq).trim() !== "auth_token") continue;
      const raw = part.slice(eq + 1).trim();
      try {
        return decodeURIComponent(raw) || null;
      } catch {
        return raw || null;
      }
    }
    return null;
  }

  function validateLines(lines) {
    if (!Array.isArray(lines) || lines.length < 1 || lines.length > MAX_LINES) return false;
    return lines.every(
      (line) =>
        line !== null &&
        typeof line === "object" &&
        typeof line.cart_item_id === "string" &&
        /^[1-9]\d{0,11}$/.test(line.cart_item_id) &&
        Number.isInteger(line.quantity) &&
        line.quantity >= 1 &&
        line.quantity <= MAX_QUANTITY &&
        typeof line.line_key === "string" &&
        line.line_key.length <= 200,
    );
  }

  // The whole add_to_cart message: lines plus the optional dry_run flag.
  function validateRequest(message) {
    if (!message || !validateLines(message.lines)) return false;
    return message.dry_run === undefined || typeof message.dry_run === "boolean";
  }

  // Ids are compared as numbers, so 5 and "5" are the same cart item.
  function sameId(a, b) {
    return String(Number(a)) === String(Number(b));
  }

  // An existing item's quantity must be a whole number, or sending the cart back could change it.
  function wholeQuantity(q) {
    return (typeof q === "number" && Number.isInteger(q) && q >= 0) || (typeof q === "string" && /^\d+$/.test(q));
  }

  function firstDefined(...values) {
    return values.find((v) => v !== undefined && v !== null);
  }

  // Finds the items array and the store/address of the cart in the shapes the response
  // plausibly has. null when there is no items array: the caller then writes nothing.
  function extractCart(json) {
    const data = json && json.data;
    for (const cart of [data && data.cart, json && json.cart, data]) {
      if (!cart || !Array.isArray(cart.items)) continue;
      // Sending back an item we cannot read would change the person's cart, so an unreadable item
      // makes the whole cart unreadable and nothing is written.
      if (!cart.items.every((item) => item && item.id !== undefined && item.id !== null && wholeQuantity(item.q))) return null;
      const store = cart.store || (data && data.store) || {};
      const address = cart.address || (data && data.address) || {};
      return {
        items: cart.items,
        storeId: firstDefined(cart.storeId, data && data.storeId, json.storeId, store.id),
        addressId: firstDefined(cart.addressId, data && data.addressId, json.addressId, address.id),
        orderType: firstDefined(cart.orderType, data && data.orderType, json.orderType),
      };
    }
    return null;
  }

  // Every existing item stays as it is, except that a matching id gets the quantity added.
  // New lines are appended in the shape of FairPrice's own cart items.
  // Free items the server adds itself (a gift with purchase) are never sent back, as the site does.
  function isFreeItem(item) {
    const product = item.product || {};
    const store = Array.isArray(product.storeSpecificData) ? product.storeSpecificData[0] : product.storeSpecificData;
    return item.isFree === true || item.mrp === 0 || (store !== undefined && store !== null && store.mrp === 0);
  }

  // An item the way FairPrice's own site sends it (its getCartRequestBody): the id and q as strings,
  // t in epoch seconds, adIds and reason kept.
  function requestItem(item, nowSec) {
    return {
      id: String(item.id),
      isChecked: item.isChecked === undefined ? true : item.isChecked,
      q: String(item.q),
      t: item.t !== undefined && item.t !== null ? item.t : nowSec,
      adIds: Array.isArray(item.adIds) ? item.adIds : [],
      reason: item.reason || "InStock",
    };
  }

  // Every existing item goes back unchanged, except that a matching id gets the quantity added.
  // The site sends the whole cart on every write, so leaving an item out could remove it.
  function mergeItems(currentItems, lines, nowSec) {
    const merged = currentItems.filter((item) => !isFreeItem(item)).map((item) => requestItem(item, nowSec));
    for (const line of lines) {
      const existing = merged.find((item) => sameId(item.id, line.cart_item_id));
      if (existing) {
        existing.q = String(Number(existing.q) + line.quantity);
      } else {
        merged.push({ id: String(Number(line.cart_item_id)), isChecked: true, q: String(line.quantity), t: nowSec, adIds: [], reason: "InStock" });
      }
    }
    return merged;
  }

  // The body FairPrice's own site sends (getCartRequestBody in its public bundle): the account id when
  // known, the store as a string and the address from the cart read back, and the site's flags.
  function buildBody(cart, merged, customerId) {
    const body = {};
    if (customerId !== undefined && customerId !== null) body.customerId = customerId;
    if (cart.storeId !== undefined && cart.storeId !== null) body.storeId = String(cart.storeId);
    if (cart.addressId !== undefined && cart.addressId !== null) body.addressId = cart.addressId;
    body.cart = { items: merged, isOutOfStockEnabled: true, dropUnavailableItems: [] };
    body.orderType = cart.orderType || "DELIVERY";
    body.isOutOfStockEnabled = true;
    body.isCheckerEnabled = true;
    body.isSellerCheckerEnabled = true;
    body.isSellerTimeSlotEnabled = true;
    body.isDirectFulfilmentEnabled = true;
    body.poaItemDropOff = false;
    return body;
  }

  // The logged-in account's id as the site's own page data carries it; undefined outside a FairPrice page.
  function accountId() {
    const data = globalThis.__NEXT_DATA__;
    const account = data && data.props && data.props.account;
    return account && account.id !== undefined ? account.id : undefined;
  }

  function isUnavailable(item) {
    return (
      item.isOutOfStock === true ||
      item.outOfStock === true ||
      item.isAvailable === false ||
      item.available === false ||
      item.inStock === false ||
      (typeof item.reason === "string" && /out.?of.?stock|unavailable/i.test(item.reason))
    );
  }

  function priceOf(item) {
    const product = item.product || {};
    for (const value of [item.price, item.unitPrice, item.displayPrice, product.price]) {
      const n = typeof value === "string" ? Number(value) : value;
      if (typeof n === "number" && Number.isFinite(n) && n > 0) return n;
    }
    return null;
  }

  // currentItems (the cart before our add) lets "reduced" account for what was already in the cart.
  // quantity is what this add put in the cart. Lines sharing a cart item are checked together:
  // the cart must hold before + everything asked for that item, and any shortfall comes off the later lines.
  function resultsFor(lines, responseItems, currentItems) {
    const results = lines.map((line) => ({ line_key: line.line_key, cart_item_id: line.cart_item_id, status: "failed", quantity: 0, cart_price_sgd: null }));
    const groups = new Map();
    lines.forEach((line, i) => {
      const key = String(Number(line.cart_item_id));
      groups.set(key, (groups.get(key) || []).concat(i));
    });
    for (const indexes of groups.values()) {
      const id = lines[indexes[0]].cart_item_id;
      const item = responseItems.find((it) => sameId(it.id, id));
      if (!item || isUnavailable(item)) {
        for (const i of indexes) results[i].status = "out_of_stock";
        continue;
      }
      const inCart = Number(item.q);
      if (!Number.isFinite(inCart) || inCart < 1) continue;
      const before = (currentItems || []).find((it) => sameId(it.id, id));
      const asked = indexes.reduce((sum, i) => sum + lines[i].quantity, 0);
      let shortfall = Math.max(0, (before ? Number(before.q) || 0 : 0) + asked - inCart);
      const price = priceOf(item);
      for (const i of indexes.slice().reverse()) {
        const take = Math.min(shortfall, lines[i].quantity);
        shortfall -= take;
        results[i].quantity = lines[i].quantity - take;
        results[i].status = take > 0 ? "reduced" : "added";
        results[i].cart_price_sgd = price;
      }
    }
    return results;
  }

  // Items that were in the cart before and are not ours: a missing id or a different quantity afterwards.
  function changedItems(before, lines, afterItems) {
    return before
      .filter((it) => !lines.some((line) => sameId(it.id, line.cart_item_id)))
      .filter((it) => {
        const now = afterItems.find((a) => sameId(a.id, it.id));
        return !now || Number(now.q) !== Number(it.q);
      })
      .map((it) => String(it.id));
  }

  // The tab the add runs in: loaded, not discarded, and not on a checkout or payment page.
  function pickTab(tabs) {
    return (tabs || []).find((tab) => {
      if (tab.status !== "complete" || tab.discarded) return false;
      try {
        return !/^\/(checkout|payment)(\/|$)/.test(new URL(tab.url).pathname);
      } catch {
        return false;
      }
    });
  }

  // The answer of the injected script is checked before it goes back to the page.
  function checkInjected(result, lines, dryRun) {
    const bad = { ok: false, error: "unexpected_response" };
    if (!result || typeof result.ok !== "boolean") return bad;
    if (!result.ok) {
      const answer = { ok: false, error: ERRORS.includes(result.error) ? result.error : "unexpected_response" };
      if (typeof result.detail === "string") answer.detail = result.detail.slice(0, 200);
      return answer;
    }
    const allowed = dryRun ? ["would_add"] : STATUSES;
    const fine =
      Array.isArray(result.results) &&
      result.results.length === lines.length &&
      result.results.every(
        (r, i) => r && r.line_key === lines[i].line_key && r.cart_item_id === lines[i].cart_item_id && allowed.includes(r.status) && typeof r.quantity === "number",
      ) &&
      (result.cart_changed === undefined || Array.isArray(result.cart_changed));
    return fine ? result : bad;
  }

  // What FairPrice said when its answer had no cart: its status fields and messages and the names of
  // its keys, never a cart value, address or token.
  function describeAnswer(json) {
    if (!json || typeof json !== "object") return String(typeof json);
    const data = json.data && typeof json.data === "object" ? json.data : {};
    const text = (v) => (typeof v === "string" || typeof v === "number" ? String(v) : undefined);
    const said = {
      code: text(json.code),
      status: text(json.status),
      message: text(json.message) || text(json.error) || text(data.message) || text(data.error),
      keys: Object.keys(json).join(","),
      dataKeys: Object.keys(data).join(","),
      cartKeys: data.cart && typeof data.cart === "object" ? Object.keys(data.cart).join(",") : undefined,
      // Product ids and reason codes only.
      unavailable: data.cart && Array.isArray(data.cart.unavailableItems) ? data.cart.unavailableItems.map((i) => String(i && i.id)).join(",") : undefined,
      changes: data.cart && Array.isArray(data.cart.changes)
        ? data.cart.changes.map((c) => String(c && c.id) + ":" + (c && typeof c.reason === "string" ? c.reason : c && c.reason && c.reason.dropOff ? "dropOff" : "?")).join(",")
        : undefined,
    };
    return JSON.stringify(said).slice(0, 300);
  }

  // 401/403 or a non-JSON page (a bot-check challenge) is a refusal and is never worked around.
  async function readJson(response) {
    const status = response.status;
    if (status === 401 || status === 403) return { error: "request_refused", status };
    let text;
    try {
      text = await response.text();
    } catch {
      return { error: "unexpected_response", status };
    }
    try {
      return { json: JSON.parse(text) };
    } catch {
      return { error: /^\s*</.test(text) ? "request_refused" : "unexpected_response", status };
    }
  }

  // opts: {dryRun, fetch, cookie, now} (the last three only differ from the defaults in tests).
  async function addToCart(lines, opts) {
    const o = opts || {};
    const doFetch = o.fetch || globalThis.fetch;
    const token = authToken(o.cookie !== undefined ? o.cookie : globalThis.document && globalThis.document.cookie);
    if (!token) return { ok: false, error: "not_logged_in" };
    // The cart API answers any origin with "*" and no credentials, so the request carries the bearer token
    // only, never cookies: a credentialed request is blocked by the browser (live test, 2026-10-29).
    const headers = { Authorization: "Bearer " + token, Accept: "application/json", "Accept-Language": "en" };
    const fail = (error) => ({ ok: false, error });
    // What went wrong, for the person and the developer; never the token or a cart value.
    const failWith = (error, e) => ({ ok: false, error, detail: String((e && e.message) || e).slice(0, 200) });

    let read;
    try {
      read = await readJson(await doFetch(GET_URL, { method: "GET", headers }));
    } catch (e) {
      return failWith("unexpected_response", e);
    }
    if (read.error) return failWith(read.error, "HTTP " + read.status);
    const cart = extractCart(read.json);
    if (!cart) return failWith("cart_unreadable", describeAnswer(read.json));

    const nowSec = o.now !== undefined ? o.now : Math.floor(Date.now() / 1000);
    const customerId = o.customerId !== undefined ? o.customerId : accountId();
    const body = buildBody(cart, mergeItems(cart.items, lines, nowSec), customerId);
    if (o.dryRun) {
      return {
        ok: true,
        dry_run: true,
        body,
        results: lines.map((line) => ({
          line_key: line.line_key,
          cart_item_id: line.cart_item_id,
          status: "would_add",
          quantity: line.quantity,
          cart_price_sgd: null,
        })),
      };
    }

    let written;
    try {
      written = await readJson(
        await doFetch(API, {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
      );
    } catch (e) {
      return failWith("unexpected_response", e);
    }
    if (written.error) return failWith(written.error, "HTTP " + written.status);
    const after = extractCart(written.json);
    if (!after) return failWith("unexpected_response", describeAnswer(written.json));
    const out = { ok: true, results: resultsFor(lines, after.items, cart.items) };
    const changed = changedItems(cart.items, lines, after.items);
    if (changed.length > 0) out.cart_changed = changed;
    return out;
  }

  const api = { describeAnswer, authToken, validateLines, validateRequest, extractCart, mergeItems, buildBody, resultsFor, changedItems, pickTab, checkInjected, addToCart };
  root.__mealcraftFairPriceCart = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
