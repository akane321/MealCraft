// Run from the repository root: node --test browser-extension/fairprice-cart/cart-core.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("./cart-core.js");

const line = (id, quantity = 2, key = "1|x|g") => ({ line_key: key, cart_item_id: id, quantity });

function jsonResponse(payload, status = 200) {
  return { status, text: async () => JSON.stringify(payload) };
}

function mockFetch(responses) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    return responses.shift();
  };
  fn.calls = calls;
  return fn;
}

const CART = { data: { cart: { items: [{ id: 5, q: "1", isChecked: true, t: 1 }], storeId: 165, addressId: 9, orderType: "DELIVERY" } } };

test("authToken reads the auth_token cookie", () => {
  assert.equal(core.authToken("a=1; auth_token=abc%2Fdef; b=2"), "abc/def");
  assert.equal(core.authToken("a=1; xauth_token=zzz"), null);
  assert.equal(core.authToken(""), null);
  assert.equal(core.authToken(undefined), null);
});

test("validateLines enforces the contract limits", () => {
  assert.equal(core.validateLines([line("172993")]), true);
  assert.equal(core.validateLines([]), false);
  assert.equal(core.validateLines(Array.from({ length: 501 }, () => line("1"))), false);
  assert.equal(core.validateLines(Array.from({ length: 500 }, () => line("1"))), true);
  assert.equal(core.validateLines([line("0123")]), false);
  assert.equal(core.validateLines([line("0")]), false);
  assert.equal(core.validateLines([line("999999999999")]), true);
  assert.equal(core.validateLines([line("12a")]), false);
  assert.equal(core.validateLines([line("1234567890123")]), false);
  assert.equal(core.validateLines([line("1", 0)]), false);
  assert.equal(core.validateLines([line("1", 999)]), true);
  assert.equal(core.validateLines([line("1", 1000)]), false);
  assert.equal(core.validateLines([line("1", 1.5)]), false);
  assert.equal(core.validateLines([line(1)]), false);
  assert.equal(core.validateLines([line("1", 1, "k".repeat(201))]), false);
  assert.equal(core.validateLines([null]), false);
  assert.equal(core.validateRequest({ lines: [line("1")], dry_run: "yes" }), false);
  assert.equal(core.validateRequest({ lines: [line("1")], dry_run: true }), true);
  assert.equal(core.validateRequest({ lines: [line("1")] }), true);
});

test("extractCart finds the cart in plausible shapes", () => {
  const items = [{ id: 1, q: "1" }];
  assert.deepEqual(core.extractCart(CART), { items: CART.data.cart.items, storeId: 165, addressId: 9, orderType: "DELIVERY" });
  assert.deepEqual(core.extractCart({ cart: { items, storeId: 1 } }), { items, storeId: 1, addressId: undefined, orderType: undefined });
  const viaData = core.extractCart({ data: { items, store: { id: 7 }, address: { id: 3 } } });
  assert.equal(viaData.storeId, 7);
  assert.equal(viaData.addressId, 3);
  assert.equal(core.extractCart({ data: { something: [] } }), null);
  assert.equal(core.extractCart(null), null);
  assert.equal(core.extractCart({ data: { cart: { items: "no" } } }), null);
  // An item without an id or a readable quantity makes the cart unreadable, so nothing is written.
  assert.equal(core.extractCart({ cart: { items: [{ id: 1, q: "1" }, { product: { id: 2 }, q: "1" }] } }), null);
  assert.equal(core.extractCart({ cart: { items: [{ id: 1, q: "many" }] } }), null);
  // Only whole-number quantities are readable.
  for (const q of [1.5, "1.5", "", "-1", -1, null, "1e2", " 2", true]) {
    assert.equal(core.extractCart({ cart: { items: [{ id: 1, q }] } }), null, JSON.stringify(q));
  }
  for (const q of [0, 3, "0", "12"]) assert.notEqual(core.extractCart({ cart: { items: [{ id: 1, q }] } }), null, JSON.stringify(q));
});

test("mergeItems sends every item the way FairPrice's site does and adds the quantity", () => {
  const current = [
    { id: 5, q: "1", isChecked: false, t: 1, adIds: ["ad"], reason: "BackInStock", product: { name: "x" } },
    { id: 6, q: "3" },
    { id: 7, q: "1", isFree: true },
    { id: 8, q: "1", product: { storeSpecificData: { mrp: 0 } } },
  ];
  const merged = core.mergeItems(current, [line("5", 2), line("77", 4)], 1000);
  assert.deepEqual(merged, [
    { id: "5", isChecked: false, q: "3", t: 1, adIds: ["ad"], reason: "BackInStock" },
    { id: "6", isChecked: true, q: "3", t: 1000, adIds: [], reason: "InStock" },
    { id: "77", isChecked: true, q: "4", t: 1000, adIds: [], reason: "InStock" },
  ]);
  assert.equal(current[0].q, "1", "input is not mutated");
});

test("buildBody is the body FairPrice's own site sends", () => {
  const body = core.buildBody({ storeId: 165, addressId: "9", orderType: "PICKUP" }, [{ id: "1" }], 4242);
  assert.deepEqual(body, {
    customerId: 4242,
    storeId: "165",
    addressId: "9",
    cart: { items: [{ id: "1" }], isOutOfStockEnabled: true, dropUnavailableItems: [] },
    orderType: "PICKUP",
    isOutOfStockEnabled: true,
    isCheckerEnabled: true,
    isSellerCheckerEnabled: true,
    isSellerTimeSlotEnabled: true,
    isDirectFulfilmentEnabled: true,
    poaItemDropOff: false,
  });
  const bare = core.buildBody({}, []);
  assert.equal(bare.orderType, "DELIVERY");
  assert.equal("addressId" in bare, false);
  assert.equal("customerId" in bare, false);
});

test("resultsFor reports added, reduced, out_of_stock and failed", () => {
  const lines = [line("1", 2, "a"), line("2", 3, "b"), line("3", 1, "c"), line("4", 1, "d"), line("5", 1, "e"), line("6", 2, "f")];
  const response = [
    { id: 1, q: "2", price: 6.95 },
    { id: 2, q: "1" },
    { id: 3, q: "1", isOutOfStock: true },
    { id: 4, q: "abc" },
    { id: 6, q: "4", price: "2.50" },
  ];
  const results = core.resultsFor(lines, response, [{ id: 6, q: "2" }]);
  assert.deepEqual(results.map((r) => r.status), ["added", "reduced", "out_of_stock", "failed", "out_of_stock", "added"]);
  assert.deepEqual(results[0], { line_key: "a", cart_item_id: "1", status: "added", quantity: 2, cart_price_sgd: 6.95 });
  assert.equal(results[1].quantity, 1);
  assert.equal(results[1].cart_price_sgd, null);
  assert.equal(results[5].cart_price_sgd, 2.5);
  const reduced = core.resultsFor([line("6", 2)], [{ id: 6, q: "3" }], [{ id: 6, q: "2" }]);
  assert.equal(reduced[0].status, "reduced");
  assert.equal(reduced[0].quantity, 1, "2 already in the cart, 3 after: this add put in 1");
});

test("resultsFor quantity is what this add put in the cart, for every status", () => {
  const results = core.resultsFor([line("1", 4, "a"), line("2", 2, "b"), line("3", 2, "c")], [{ id: 1, q: "6" }, { id: 3, q: "0" }], [{ id: 1, q: "3" }]);
  assert.deepEqual(results.map((r) => [r.status, r.quantity]), [["reduced", 3], ["out_of_stock", 0], ["failed", 0]]);
});

test("resultsFor checks lines sharing a cart item together and takes a shortfall from the later lines", () => {
  const two = [line("7", 2, "a"), line("7", 3, "b")];
  const full = core.resultsFor(two, [{ id: 7, q: "6" }], [{ id: "7", q: "1" }]);
  assert.deepEqual(full.map((r) => [r.status, r.quantity]), [["added", 2], ["added", 3]]);
  const short = core.resultsFor(two, [{ id: 7, q: "4" }], [{ id: 7, q: "1" }]);
  assert.deepEqual(short.map((r) => [r.status, r.quantity]), [["added", 2], ["reduced", 1]]);
  const worse = core.resultsFor(two, [{ id: "7", q: "1" }], [{ id: 7, q: "1" }]);
  assert.deepEqual(worse.map((r) => [r.status, r.quantity]), [["reduced", 0], ["reduced", 0]]);
  const gone = core.resultsFor(two, [], []);
  assert.deepEqual(gone.map((r) => r.status), ["out_of_stock", "out_of_stock"]);
});

test("ids match as numbers, so 5 and the string 5 are one cart item", () => {
  assert.equal(core.mergeItems([{ id: "5", q: "1" }], [line("5", 2)], 1).length, 1);
  assert.equal(core.mergeItems([{ id: 5, q: "1" }], [line("5", 2)], 1)[0].q, "3");
  assert.equal(core.resultsFor([line("5", 2)], [{ id: "5", q: "3" }], [{ id: 5, q: "1" }])[0].status, "added");
  // Two lines for one new id add up in the body instead of creating two items.
  const merged = core.mergeItems([], [line("8", 1, "a"), line("8", 2, "b")], 1);
  assert.deepEqual(merged.map((i) => [i.id, i.q]), [["8", "3"]]);
});

test("pickTab takes a loaded, non-discarded FairPrice tab that is not on checkout or payment", () => {
  const tab = (id, url, extra = {}) => ({ id, url, status: "complete", discarded: false, ...extra });
  const tabs = [
    tab(1, "https://www.fairprice.com.sg/checkout"),
    tab(2, "https://www.fairprice.com.sg/payment/card"),
    tab(3, "https://www.fairprice.com.sg/", { status: "loading" }),
    tab(4, "https://www.fairprice.com.sg/", { discarded: true }),
    tab(5, "https://www.fairprice.com.sg/product/x"),
  ];
  assert.equal(core.pickTab(tabs).id, 5);
  assert.equal(core.pickTab(tabs.slice(0, 4)), undefined);
  assert.equal(core.pickTab([]), undefined);
  assert.equal(core.pickTab([tab(6, "https://www.fairprice.com.sg/checkout-tips")]).id, 6);
});

test("checkInjected only lets a well-formed answer through", () => {
  const lines = [line("1", 2, "a"), line("2", 1, "b")];
  const good = { ok: true, results: [{ line_key: "a", cart_item_id: "1", status: "added", quantity: 2, cart_price_sgd: null }, { line_key: "b", cart_item_id: "2", status: "reduced", quantity: 0, cart_price_sgd: null }], cart_changed: ["9"] };
  assert.equal(core.checkInjected(good, lines, false), good);
  const bad = { ok: false, error: "unexpected_response" };
  assert.deepEqual(core.checkInjected(undefined, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: "yes" }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: true }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: true, results: good.results.slice(0, 1) }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: true, results: [good.results[0], { ...good.results[1], status: "weird" }] }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: true, results: [good.results[0], { ...good.results[1], quantity: "1" }] }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: true, results: [good.results[0], { ...good.results[1], line_key: "z" }] }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ...good, cart_changed: "9" }, lines, false), bad);
  assert.deepEqual(core.checkInjected({ ok: false, error: "not_logged_in" }, lines, false), { ok: false, error: "not_logged_in" });
  assert.deepEqual(core.checkInjected({ ok: false, error: "made_up" }, lines, false), bad);
  const dry = { ok: true, dry_run: true, results: good.results.map((r) => ({ ...r, status: "would_add" })) };
  assert.equal(core.checkInjected(dry, lines, true), dry);
  assert.deepEqual(core.checkInjected(good, lines, true), bad);
});

test("addToCart without a token does nothing", async () => {
  const fetch = mockFetch([]);
  assert.deepEqual(await core.addToCart([line("1")], { fetch, cookie: "a=1" }), { ok: false, error: "not_logged_in" });
  assert.equal(fetch.calls.length, 0);
});

test("addToCart never POSTs when the cart cannot be read", async () => {
  const cases = [
    [{ status: 403, text: async () => "" }, "request_refused", "HTTP 403"],
    [{ status: 200, text: async () => "<html>challenge</html>" }, "request_refused", "HTTP 200"],
    [{ status: 200, text: async () => "{broken" }, "unexpected_response", "HTTP 200"],
    [jsonResponse({ data: { nothing: true } }), "cart_unreadable", '{"keys":"data","dataKeys":"nothing"}'],
  ];
  for (const [response, error, detail] of cases) {
    const fetch = mockFetch([response]);
    const result = await core.addToCart([line("1")], { fetch, cookie: "auth_token=t" });
    assert.deepEqual(result, detail ? { ok: false, error, detail } : { ok: false, error });
    assert.deepEqual(fetch.calls.map((c) => c.init.method), ["GET"]);
  }
  const throwing = async () => {
    throw new Error("network");
  };
  assert.deepEqual(await core.addToCart([line("1")], { fetch: throwing, cookie: "auth_token=t" }), { ok: false, error: "unexpected_response", detail: "network" });
});

test("addToCart dry run returns the body and sends no POST", async () => {
  const fetch = mockFetch([jsonResponse(CART)]);
  const result = await core.addToCart([line("5", 2), line("9", 1)], { fetch, cookie: "auth_token=secret", dryRun: true, now: 42 });
  assert.equal(result.ok, true);
  assert.equal(result.dry_run, true);
  assert.deepEqual(result.results.map((r) => r.status), ["would_add", "would_add"]);
  assert.deepEqual(result.body.cart.items.map((i) => [i.id, i.q, i.t]), [["5", "3", 1], ["9", "1", 42]]);
  assert.equal(result.body.storeId, "165");
  assert.deepEqual(fetch.calls.map((c) => c.init.method), ["GET"]);
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("addToCart writes once and reports per line", async () => {
  const after = { data: { cart: { items: [{ id: 5, q: "3", price: 1.2 }, { id: 9, q: "1", price: 3 }] } } };
  const fetch = mockFetch([jsonResponse(CART), jsonResponse(after)]);
  const result = await core.addToCart([line("5", 2, "a"), line("9", 1, "b")], { fetch, cookie: "auth_token=t", now: 42 });
  assert.deepEqual(fetch.calls.map((c) => [c.init.method, c.url.split("?")[0]]), [
    ["GET", "https://website-api.omni.fairprice.com.sg/api/cart"],
    ["POST", "https://website-api.omni.fairprice.com.sg/api/cart"],
  ]);
  assert.equal(fetch.calls[1].init.headers.Authorization, "Bearer t");
  assert.equal(fetch.calls[1].init.headers["Content-Type"], "application/json");
  assert.equal(JSON.parse(fetch.calls[1].init.body).cart.items.length, 2);
  assert.deepEqual(result.results.map((r) => [r.status, r.quantity]), [["added", 2], ["added", 1]]);
  assert.equal(JSON.stringify(result).includes("Bearer"), false);
});

test("addToCart reports cart items that changed or went missing, not our own", async () => {
  const before = { data: { cart: { items: [{ id: 5, q: "1" }, { id: 6, q: "2" }, { id: 7, q: "3" }, { id: 8, q: "1" }] } } };
  const after = { data: { cart: { items: [{ id: 5, q: "3" }, { id: 6, q: "1" }, { id: 8, q: "1" }] } } };
  const fetch = mockFetch([jsonResponse(before), jsonResponse(after)]);
  const result = await core.addToCart([line("5", 2)], { fetch, cookie: "auth_token=t" });
  assert.equal(result.ok, true);
  assert.deepEqual(result.cart_changed, ["6", "7"]);
  const calm = mockFetch([jsonResponse(CART), jsonResponse({ data: { cart: { items: [{ id: 5, q: "3" }] } } })]);
  assert.equal("cart_changed" in (await core.addToCart([line("5", 2)], { fetch: calm, cookie: "auth_token=t" })), false);
});

test("addToCart writes nothing when an item quantity is not a whole number", async () => {
  const fetch = mockFetch([jsonResponse({ data: { cart: { items: [{ id: 5, q: "1.5" }] } } })]);
  assert.deepEqual(await core.addToCart([line("9")], { fetch, cookie: "auth_token=t" }), { ok: false, error: "cart_unreadable", detail: '{"keys":"data","dataKeys":"cart","cartKeys":"items"}' });
  assert.deepEqual(fetch.calls.map((c) => c.init.method), ["GET"]);
});

test("addToCart reports a refused or unreadable write", async () => {
  const refused = mockFetch([jsonResponse(CART), { status: 403, text: async () => "" }]);
  assert.deepEqual(await core.addToCart([line("9")], { fetch: refused, cookie: "auth_token=t" }), { ok: false, error: "request_refused", detail: "HTTP 403" });
  const odd = mockFetch([jsonResponse(CART), jsonResponse({ ok: true })]);
  assert.deepEqual(await core.addToCart([line("9")], { fetch: odd, cookie: "auth_token=t" }), { ok: false, error: "unexpected_response", detail: '{"keys":"ok","dataKeys":""}' });
});

test("cart requests carry the bearer token only, never cookies, and failures say why", async () => {
  const calls = [];
  const fetch = async (url, init) => {
    calls.push(init);
    if (init.method === "GET") return { status: 200, text: async () => JSON.stringify({ data: { cart: { items: [], storeId: 165 } } }) };
    throw new TypeError("Failed to fetch");
  };
  const result = await core.addToCart([{ line_key: "a", cart_item_id: "185350", quantity: 1 }], { fetch, cookie: "auth_token=abc", now: 1 });
  assert.deepEqual(result, { ok: false, error: "unexpected_response", detail: "Failed to fetch" });
  assert.equal(calls.length, 2);
  for (const init of calls) assert.equal(init.credentials, undefined);
  const refused = await core.addToCart([{ line_key: "a", cart_item_id: "185350", quantity: 1 }], {
    fetch: async () => ({ status: 403, text: async () => "" }), cookie: "auth_token=abc",
  });
  assert.deepEqual(refused, { ok: false, error: "request_refused", detail: "HTTP 403" });
  assert.deepEqual(core.checkInjected({ ok: false, error: "request_refused", detail: "HTTP 403" }, [], false), { ok: false, error: "request_refused", detail: "HTTP 403" });
});

test("describeAnswer names FairPrice's status, message and keys but no cart values", () => {
  const said = JSON.parse(core.describeAnswer({ code: 400, status: "ERROR", message: "storeId is required", data: { cart: { items: [{ id: 1 }], addressId: "secret" } } }));
  assert.deepEqual(said, { code: "400", status: "ERROR", message: "storeId is required", keys: "code,status,message,data", dataKeys: "cart", cartKeys: "items,addressId" });
  assert.ok(!core.describeAnswer({ data: { cart: { addressId: "secret" } } }).includes("secret"));
});

test("addToCart sends the account id from the FairPrice page data, when the page has it", async () => {
  globalThis.__NEXT_DATA__ = { props: { account: { id: 777 } } };
  try {
    const fetch = mockFetch([jsonResponse(CART)]);
    const result = await core.addToCart([line("5", 1)], { fetch, cookie: "auth_token=t", dryRun: true, now: 9 });
    assert.equal(result.body.customerId, 777);
  } finally {
    delete globalThis.__NEXT_DATA__;
  }
  const fetch = mockFetch([jsonResponse(CART)]);
  const without = await core.addToCart([line("5", 1)], { fetch, cookie: "auth_token=t", dryRun: true, now: 9 });
  assert.equal("customerId" in without.body, false);
});
