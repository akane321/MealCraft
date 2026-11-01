// Cart logic for the MealCraft FairPrice cart extension (docs/design/fairprice-cart.md).
// Pure and injectable (fetch, token, customer-id cache, clock), so node tests run it without a browser.
// The service worker calls it with the person's FairPrice auth_token cookie as the bearer; no FairPrice tab
// is involved. It only ever calls GET /api/cart, POST /api/cart and GET /user-profile. It never calls
// checkout, never logs or returns the auth token, and never returns the address or account id.
(function (root) {
  "use strict";

  const API = "https://website-api.omni.fairprice.com.sg/api/cart";
  const GET_URL = API + "?orderType=DELIVERY&isCheckerEnabled=true&isSellerCheckerEnabled=true&isOutOfStockEnabled=true";
  const PROFILE_URL = "https://www.fairprice.com.sg/user-profile";
  const PRODUCT_URL = "https://www.fairprice.com.sg/product/";
  const MAX_LINES = 500;
  const MAX_QUANTITY = 999;
  const DEFAULT_MAX = 99;
  const ERRORS = ["not_logged_in", "cart_unreadable", "request_refused", "unexpected_response", "invalid_request", "not_in_cart", "busy"];
  const STATUSES = ["added", "reduced", "out_of_stock", "failed"];
  const ID = /^[1-9]\d{0,11}$/;

  // The cookie value as chrome.cookies returns it; FairPrice's site decodes it before use.
  function cleanToken(value) {
    if (typeof value !== "string" || value === "") return null;
    try {
      return decodeURIComponent(value) || null;
    } catch {
      return value;
    }
  }

  function validateLines(lines) {
    if (!Array.isArray(lines) || lines.length < 1 || lines.length > MAX_LINES) return false;
    return lines.every(
      (line) =>
        line !== null &&
        typeof line === "object" &&
        typeof line.cart_item_id === "string" &&
        ID.test(line.cart_item_id) &&
        Number.isInteger(line.quantity) &&
        line.quantity >= 1 &&
        line.quantity <= MAX_QUANTITY &&
        typeof line.line_key === "string" &&
        line.line_key.length <= 200,
    );
  }

  // The whole message of the page: get_cart, add_to_cart (lines plus the optional dry_run) or set_quantity.
  function validateMessage(message) {
    if (!message || typeof message !== "object") return false;
    if (message.type === "get_cart") return true;
    if (message.type === "add_to_cart") return validateLines(message.lines) && (message.dry_run === undefined || typeof message.dry_run === "boolean");
    if (message.type === "set_quantity") {
      return typeof message.cart_item_id === "string" && ID.test(message.cart_item_id) && Number.isInteger(message.quantity) && message.quantity >= 0 && message.quantity <= MAX_QUANTITY;
    }
    return false;
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
  // plausibly has (the live one is data.cart). null when there is no items array: the caller then writes nothing.
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
        raw: cart,
        items: cart.items,
        unavailable: Array.isArray(cart.unavailableItems) ? cart.unavailableItems.filter((u) => u && u.id !== undefined && u.id !== null) : [],
        storeId: firstDefined(cart.storeId, data && data.storeId, json.storeId, store.id),
        addressId: firstDefined(cart.addressId, data && data.addressId, json.addressId, address.id),
        orderType: firstDefined(cart.orderType, data && data.orderType, json.orderType),
      };
    }
    return null;
  }

  // The product's store data is an object in the reply; an array's first entry is accepted too.
  function storeData(product) {
    const s = product && product.storeSpecificData;
    const one = Array.isArray(s) ? s[0] : s;
    return one && typeof one === "object" ? one : {};
  }

  // Free items the server adds itself (a gift with purchase) are never sent back, as the site does.
  function isFreeItem(item) {
    const product = item.product || {};
    const store = storeData(product);
    return item.isFree === true || item.mrp === 0 || store.mrp === 0;
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
  // New lines are appended in the shape of FairPrice's own cart items.
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

  // The site sends the address id as a number; the cart read returns it as a string, which the server refuses
  // ("Invalid Cart - error when unmarshalling request cart", live write 2026-10-29).
  function numericId(value) {
    return typeof value === "string" && /^\d+$/.test(value) ? Number(value) : value;
  }

  // The body FairPrice's own site sends (getCartRequestBody in its public bundle): the account id,
  // the store as a string, the address as a number and the site's flags. dropIds are unavailable items to remove.
  function buildBody(cart, merged, customerId, dropIds) {
    const body = {};
    if (customerId !== undefined && customerId !== null) body.customerId = customerId;
    if (cart.storeId !== undefined && cart.storeId !== null) body.storeId = String(cart.storeId);
    if (cart.addressId !== undefined && cart.addressId !== null) body.addressId = numericId(cart.addressId);
    body.cart = { items: merged, isOutOfStockEnabled: true, dropUnavailableItems: dropIds || [] };
    body.orderType = cart.orderType || "DELIVERY";
    body.isOutOfStockEnabled = true;
    body.isCheckerEnabled = true;
    body.isSellerCheckerEnabled = true;
    body.isSellerTimeSlotEnabled = true;
    body.isDirectFulfilmentEnabled = true;
    body.poaItemDropOff = false;
    return body;
  }

  // ---- The normalized cart (what the page renders; no address, account or token) ----

  function round2(n) {
    return Math.round(n * 100) / 100;
  }

  // Money from a number or numeric string, in cents precision; null when it is not one.
  function money(value) {
    const n = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
    return typeof n === "number" && Number.isFinite(n) ? round2(n) : null;
  }

  function imageUrl(product) {
    const url = Array.isArray(product.images) ? product.images[0] : undefined;
    return typeof url === "string" && /^https:\/\//.test(url) ? url + (url.includes("?") ? "&" : "?") + "w=320&q=60" : null;
  }

  function maxQuantity(product) {
    const store = storeData(product);
    const caps = [];
    const override = money(product.stockOverride && product.stockOverride.maxPurchasableStock);
    if (override !== null && override > 0) caps.push(override);
    // Plain stock only counts when the product is not unlimited.
    const stock = store.unlimitedStock === true ? null : money(store.stock);
    if (stock !== null && stock >= 0) caps.push(stock);
    // The site's bulk routing starts at the smaller positive threshold, so one fewer is the most it takes as a plain add.
    const bulk = [product.bulkOrderThreshold, product.stockOverride && product.stockOverride.storeBulkOrderThreshold].map(money).filter((n) => n !== null && n > 0);
    if (bulk.length) caps.push(Math.max(1, Math.min(...bulk) - 1));
    return Math.min(MAX_QUANTITY, ...(caps.length ? caps : [DEFAULT_MAX]));
  }

  // The site's own row notice.
  function noteFor(reason, quantity) {
    if (reason === "ReducedQuantity") return "Only " + quantity + " left";
    if (reason === "BackInStock") return "Back in stock";
    return null;
  }

  function normalizeItem(item) {
    const product = item.product || {};
    const store = storeData(product);
    const quantity = Number(item.q);
    const free = isFreeItem(item);
    const mrp = money(firstDefined(store.mrp, item.mrp));
    // As the site's cart row (c-1571): an applied offer's discount, else the product's, per unit; the line's
    // saving is shown as 0 when it would exceed the line's price.
    const offer = firstDefined(item.appliedOffer, product.appliedOffer);
    const offered = offer && Array.isArray(offer.productsBought) && offer.productsBought[0] ? money(offer.productsBought[0].discount) : null;
    const wanted = offered !== null ? offered : money(firstDefined(product.discount, item.discount, store.discount)) || 0;
    const discount = mrp !== null && wanted * quantity > mrp * quantity ? 0 : wanted;
    return {
      cart_item_id: String(item.id),
      name: typeof product.name === "string" ? product.name : null,
      brand: product.brand && typeof product.brand.name === "string" ? product.brand.name : null,
      display_unit: product.metaData && typeof product.metaData.DisplayUnit === "string" ? product.metaData.DisplayUnit : null,
      image_url: imageUrl(product),
      product_url: typeof product.slug === "string" && /^[\w-]+$/.test(product.slug) ? PRODUCT_URL + product.slug : null,
      quantity,
      unit_price_sgd: mrp === null ? null : round2(mrp - discount),
      unit_mrp_sgd: mrp,
      line_total_sgd: mrp === null ? null : round2(mrp * quantity - quantity * discount),
      line_saving_sgd: mrp === null ? null : round2(quantity * discount),
      max_quantity: free ? quantity : maxQuantity(product),
      is_checked: item.isChecked !== false,
      is_free: free,
      note: noteFor(item.reason, quantity),
    };
  }

  function normalizeUnavailable(entry) {
    const product = entry.product || {};
    const want = Number(entry.wantQuantity);
    return {
      cart_item_id: String(entry.id),
      name: typeof product.name === "string" ? product.name : null,
      image_url: imageUrl(product),
      want_quantity: Number.isFinite(want) ? want : null,
    };
  }

  // The reply of GET/POST /api/cart as the page renders it; null when the cart cannot be read.
  function normalizeCart(json) {
    const found = extractCart(json);
    if (!found) return null;
    const cart = found.raw;
    const amounts = cart.amounts && typeof cart.amounts === "object" ? cart.amounts : {};
    const sellers = Array.isArray(cart.sellersAmounts) ? cart.sellersAmounts : [];
    const info = cart.storeInfo && typeof cart.storeInfo === "object" ? cart.storeInfo : {};
    // Items at quantity 0 are what the site keeps after a removal; it does not list them.
    const items = found.items.filter((item) => Number(item.q) > 0).map(normalizeItem);
    const fee = (v) => money(v) || 0;
    // Totals are always numbers: the subtotal falls back to the lines, the total to the subtotal plus the fees.
    const reported = sellers.length > 0 ? sellers.reduce((sum, s) => sum + (money(s && s.amount && s.amount.orderAmount) || 0), 0) : money(amounts.orderAmount);
    const subtotal = round2(reported !== null ? reported : items.reduce((sum, i) => sum + (i.line_total_sgd || 0), 0));
    const delivery = fee(amounts.shippingAmount);
    const service = fee(amounts.currentServiceFee);
    const youPay = money(cart.youPay);
    return {
      store: {
        id: found.storeId !== undefined && found.storeId !== null ? String(found.storeId) : null,
        name: typeof info.name === "string" ? info.name : null,
      },
      items,
      unavailable: found.unavailable.map(normalizeUnavailable),
      totals: {
        subtotal_sgd: subtotal,
        savings_sgd: fee(cart.savings),
        delivery_sgd: delivery,
        delivery_standard_sgd: fee(amounts.standardShippingAmount),
        service_fee_sgd: service,
        service_fee_standard_sgd: fee(amounts.standardServiceFee),
        total_sgd: youPay !== null ? youPay : round2(subtotal + delivery + service),
      },
    };
  }

  // ---- Results of an add ----

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

  // The unit price in the cart: the store's mrp less the discount, else a plain price field.
  function priceOf(item) {
    const product = item.product || {};
    const store = storeData(product);
    const mrp = money(firstDefined(store.mrp, item.mrp));
    if (mrp !== null) {
      const net = round2(mrp - (money(firstDefined(store.discount, item.discount)) || 0));
      if (net > 0) return net;
    }
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

  // ---- The answer to the page ----

  function validCart(cart) {
    const finite = (n) => typeof n === "number" && Number.isFinite(n);
    const orNull = (n) => n === null || finite(n);
    const okItem = (i) =>
      !!i &&
      typeof i.cart_item_id === "string" &&
      finite(i.quantity) &&
      finite(i.max_quantity) &&
      ["unit_price_sgd", "unit_mrp_sgd", "line_total_sgd", "line_saving_sgd"].every((k) => orNull(i[k]));
    const totals = cart && cart.totals;
    return (
      !!cart &&
      typeof cart === "object" &&
      !!cart.store &&
      typeof cart.store === "object" &&
      Array.isArray(cart.items) &&
      cart.items.every(okItem) &&
      Array.isArray(cart.unavailable) &&
      cart.unavailable.every((u) => u && typeof u.cart_item_id === "string") &&
      !!totals &&
      typeof totals === "object" &&
      ["subtotal_sgd", "savings_sgd", "delivery_sgd", "delivery_standard_sgd", "service_fee_sgd", "service_fee_standard_sgd", "total_sgd"].every((k) => finite(totals[k]))
    );
  }

  // Every answer is checked before it goes back to the page, and only the contract's fields are passed on.
  // message is the page's request the result answers.
  function checkAnswer(message, result) {
    const bad = { ok: false, error: "unexpected_response" };
    if (!result || typeof result.ok !== "boolean") return bad;
    if (!result.ok) {
      const answer = { ok: false, error: ERRORS.includes(result.error) ? result.error : "unexpected_response" };
      if (typeof result.detail === "string") answer.detail = result.detail.slice(0, 200);
      return answer;
    }
    if (message.type === "get_cart" || message.type === "set_quantity") return validCart(result.cart) ? { ok: true, cart: result.cart } : bad;
    if (message.type !== "add_to_cart") return bad;
    const dryRun = message.dry_run === true;
    const lines = message.lines;
    const allowed = dryRun ? ["would_add"] : STATUSES;
    const fine =
      Array.isArray(result.results) &&
      result.results.length === lines.length &&
      result.results.every(
        (r, i) => r && r.line_key === lines[i].line_key && r.cart_item_id === lines[i].cart_item_id && allowed.includes(r.status) && typeof r.quantity === "number",
      ) &&
      (result.cart_changed === undefined || Array.isArray(result.cart_changed));
    if (!fine) return bad;
    if (dryRun) return result.body && typeof result.body === "object" ? { ok: true, dry_run: true, body: result.body, results: result.results } : bad;
    if (!validCart(result.cart)) return bad;
    const answer = { ok: true, results: result.results, cart: result.cart };
    if (result.cart_changed !== undefined) answer.cart_changed = result.cart_changed;
    return answer;
  }

  // ---- Talking to FairPrice ----

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

  // 401 is a login that ended; 403 or a non-JSON page (a bot-check challenge) is a refusal and is never worked around.
  async function readJson(response) {
    const status = response.status;
    if (status === 401) return { error: "not_logged_in", status };
    if (status === 403) return { error: "request_refused", status };
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

  // What went wrong, for the person and the developer; never the token or a cart value.
  function failWith(error, e) {
    return { ok: false, error, detail: String((e && e.message) || e).slice(0, 200) };
  }

  // A dry run's body leaves the extension, so the account and address ids show only that they are set.
  function withoutIds(body) {
    const shown = { ...body };
    for (const key of ["customerId", "addressId"]) if (key in shown) shown[key] = "<set>";
    return shown;
  }

  // opts: {token, fetch, cache, now, dryRun}. token is the auth_token cookie value; cache is
  // {get(), set(value)} (the worker backs it with chrome.storage.session); fetch and now only differ in tests.
  // null when there is no token.
  function context(opts) {
    const o = opts || {};
    const token = cleanToken(o.token);
    if (!token) return null;
    return { token, fetch: o.fetch || globalThis.fetch, cache: o.cache, nowSec: o.now !== undefined ? o.now : Math.floor(Date.now() / 1000), dryRun: o.dryRun === true };
  }

  // One request to FairPrice: the bearer token only, never cookies. The cart API answers any origin with "*"
  // and no credentials, so a credentialed request is blocked by the browser (live test, 2026-10-29).
  async function request(c, method, url, body) {
    const headers = { Authorization: "Bearer " + c.token, Accept: "application/json", "Accept-Language": "en" };
    const init = { method, headers };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const doFetch = c.fetch;
    let read;
    try {
      read = await readJson(await doFetch(url, init));
    } catch (e) {
      return failWith("unexpected_response", e);
    }
    return read.error ? failWith(read.error, "HTTP " + read.status) : read;
  }

  // A one-way digest of the token tells a changed login apart without keeping any part of the token.
  async function tokenKey(token) {
    const digest = await globalThis.crypto.subtle.digest("SHA-256", new TextEncoder().encode(token));
    return Array.from(new Uint8Array(digest).slice(0, 8), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function validCustomerId(id) {
    return typeof id === "number" ? Number.isInteger(id) && id > 0 : typeof id === "string" && /^[1-9]\d*$/.test(id);
  }

  // The account id of the write body: the cache first (for the same login), else GET /user-profile once.
  async function customerIdFor(c) {
    const key = await tokenKey(c.token);
    try {
      const hit = c.cache && (await c.cache.get());
      if (hit && hit.key === key && validCustomerId(hit.id)) return { id: hit.id };
    } catch {
      // A cache that cannot be read only costs one more profile call.
    }
    const read = await request(c, "GET", PROFILE_URL);
    if (read.ok === false) return read;
    const raw = read.json && read.json.id;
    if (!validCustomerId(raw)) return failWith("unexpected_response", "profile without an account id: " + Object.keys(read.json || {}).join(",").slice(0, 100));
    const id = Number(raw);
    try {
      if (c.cache) await c.cache.set({ key, id });
    } catch {
      // Not caching is harmless.
    }
    return { id };
  }

  async function readCart(c) {
    const read = await request(c, "GET", GET_URL);
    if (read.ok === false) return read;
    const cart = extractCart(read.json);
    return cart ? { cart, json: read.json } : failWith("cart_unreadable", describeAnswer(read.json));
  }

  // The whole cart goes back; the answer must carry a cart again or the write is reported as unreadable.
  async function writeCart(c, body) {
    const written = await request(c, "POST", API, body);
    if (written.ok === false) return written;
    const after = extractCart(written.json);
    return after ? { after, json: written.json } : failWith("unexpected_response", describeAnswer(written.json));
  }

  async function getCart(opts) {
    const c = context(opts);
    if (!c) return { ok: false, error: "not_logged_in" };
    const read = await readCart(c);
    return read.ok === false ? read : { ok: true, cart: normalizeCart(read.json) };
  }

  async function addToCart(lines, opts) {
    const c = context(opts);
    if (!c) return { ok: false, error: "not_logged_in" };
    // The account id first, so the cart read and the write follow each other with nothing in between.
    const customer = await customerIdFor(c);
    if (customer.ok === false) return customer;
    const read = await readCart(c);
    if (read.ok === false) return read;
    const made = { body: buildBody(read.cart, mergeItems(read.cart.items, lines, c.nowSec), customer.id, []) };
    if (c.dryRun) {
      return {
        ok: true,
        dry_run: true,
        body: withoutIds(made.body),
        results: lines.map((line) => ({
          line_key: line.line_key,
          cart_item_id: line.cart_item_id,
          status: "would_add",
          quantity: line.quantity,
          cart_price_sgd: null,
        })),
      };
    }
    const written = await writeCart(c, made.body);
    if (written.ok === false) return written;
    const out = { ok: true, results: resultsFor(lines, written.after.items, read.cart.items), cart: normalizeCart(written.json) };
    const changed = changedItems(read.cart.items, lines, written.after.items);
    if (changed.length > 0) out.cart_changed = changed;
    return out;
  }

  // Sets one item's quantity from the current cart: 0 removes it (the item stays in the list as q "0", as the
  // site does); an unavailable item can only be removed, through dropUnavailableItems. An id not in the cart answers not_in_cart.
  async function setQuantity(cartItemId, quantity, opts) {
    const c = context(opts);
    if (!c) return { ok: false, error: "not_logged_in" };
    const customer = await customerIdFor(c);
    if (customer.ok === false) return customer;
    const read = await readCart(c);
    if (read.ok === false) return read;
    const refuse = (why) => failWith("invalid_request", why);
    const merged = mergeItems(read.cart.items, [], c.nowSec);
    let dropIds = [];
    const current = read.cart.items.find((item) => sameId(item.id, cartItemId));
    if (current) {
      if (isFreeItem(current)) return refuse("a free item cannot be changed");
      merged.find((item) => sameId(item.id, cartItemId)).q = String(quantity);
    } else {
      const gone = read.cart.unavailable.find((u) => sameId(u.id, cartItemId));
      if (!gone) return failWith("not_in_cart", "item " + cartItemId);
      if (quantity !== 0) return refuse("an unavailable item can only be removed");
      dropIds = [String(gone.id)];
    }
    const written = await writeCart(c, buildBody(read.cart, merged, customer.id, dropIds));
    return written.ok === false ? written : { ok: true, cart: normalizeCart(written.json) };
  }

  const api = {
    describeAnswer,
    cleanToken,
    validateLines,
    validateMessage,
    extractCart,
    normalizeCart,
    mergeItems,
    buildBody,
    resultsFor,
    changedItems,
    checkAnswer,
    getCart,
    addToCart,
    setQuantity,
  };
  root.__mealcraftFairPriceCart = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
