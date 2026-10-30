// Run from the repository root: node --test browser-extension/fairprice-cart/cart-core.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const core = require("./cart-core.js");

const line = (id, quantity = 2, key = "1|x|g") => ({ line_key: key, cart_item_id: id, quantity });

function jsonResponse(payload, status = 200) {
  return { status, text: async () => JSON.stringify(payload) };
}

// Answers in order and records every call. The profile call is answered by url so tests need not order it.
function mockFetch(responses, profile = jsonResponse({ id: 4242 })) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init });
    return url.endsWith("/user-profile") ? profile : responses.shift();
  };
  fn.calls = calls;
  fn.cartCalls = () => calls.filter((c) => c.url.includes("/api/cart")).map((c) => c.init.method);
  return fn;
}

// The body of the cart write a mocked fetch received.
const posted = (fetch) => JSON.parse(fetch.calls.find((c) => c.init.method === "POST").init.body);

const memoryCache = () => {
  let value;
  return { get: async () => value, set: async (v) => (value = v), peek: () => value };
};

const CART = { data: { cart: { items: [{ id: 5, q: "1", isChecked: true, t: 1 }], storeId: 165, addressId: 9, orderType: "DELIVERY" } } };

// A cart the way FairPrice's site replies (public bundle, 2026-10-29).
function realCart() {
  return {
    code: "200",
    status: "SUCCESS",
    data: {
      cart: {
        cartId: "c1",
        youPay: 8.54,
        savings: 1,
        totalCartDiscount: 1,
        changes: [],
        items: [
          {
            id: "185350", q: "2", isChecked: true, t: 100, adIds: [], reason: "InStock",
            product: {
              id: 185350, name: "FairPrice Fine Salt", slug: "fairprice-fine-salt-500g", images: ["https://media.example/salt.jpg"],
              brand: { name: "FairPrice" }, metaData: { DisplayUnit: "500g", pricePerUnit: "$0.09 per 100g" },
              storeSpecificData: { mrp: 0.45, discount: 0, stock: 50, unlimitedStock: false },
            },
          },
          {
            id: "167545", q: "3", isChecked: false, t: 101, adIds: ["ad1"], reason: "ReducedQuantity", wantQuantity: 6,
            product: {
              id: 167545, name: "Sea Salt", slug: "sea-salt", images: ["https://media.example/sea.jpg?v=2"],
              brand: { name: "Sea Co" }, metaData: { DisplayUnit: "1kg" },
              stockOverride: { maxPurchasableStock: 5, storeBulkOrderThreshold: 10 },
              storeSpecificData: { mrp: 2.5, discount: 0.5, stock: 20, unlimitedStock: false },
            },
          },
          {
            id: "190001", q: "1", t: 102, reason: "BackInStock",
            product: { id: 190001, name: "Rice", slug: "rice", images: [], storeSpecificData: { mrp: 5, discount: 0, stock: 3, unlimitedStock: true } },
          },
          { id: "999", q: "1", isFree: true, t: 103, product: { id: 999, name: "Gift", storeSpecificData: { mrp: 0, discount: 0 } } },
        ],
        unavailableItems: [{ id: 150002, mrp: 3, wantQuantity: 1, product: { id: 150002, name: "Gone Item", images: ["https://media.example/gone.jpg"], slug: "gone" } }],
        storeId: "165",
        storeInfo: { id: 165, name: "FairPrice PFC", address: "1 Secret Road", storeFormat: "hyper" },
        amounts: { orderAmount: 7.55, shippingAmount: 0, standardShippingAmount: 7.99, standardServiceFee: 0.99, currentServiceFee: 0.99, slotSurcharge: 0, totalCouponDiscount: 0 },
        sellersAmounts: [{ amount: { orderAmount: 5 } }, { amount: { orderAmount: 2.55 } }],
        orderType: "DELIVERY",
        addressId: "98765",
      },
    },
  };
}

test("cleanToken decodes the cookie value", () => {
  assert.equal(core.cleanToken("abc%2Fdef"), "abc/def");
  assert.equal(core.cleanToken("100%"), "100%");
  assert.equal(core.cleanToken(""), null);
  assert.equal(core.cleanToken(undefined), null);
  assert.equal(core.cleanToken(null), null);
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
});

test("validateMessage checks get_cart, add_to_cart and set_quantity", () => {
  assert.equal(core.validateMessage({ type: "get_cart" }), true);
  assert.equal(core.validateMessage({ type: "add_to_cart", lines: [line("1")] }), true);
  assert.equal(core.validateMessage({ type: "add_to_cart", lines: [line("1")], dry_run: true }), true);
  assert.equal(core.validateMessage({ type: "add_to_cart", lines: [line("1")], dry_run: "yes" }), false);
  assert.equal(core.validateMessage({ type: "add_to_cart", lines: [] }), false);
  assert.equal(core.validateMessage({ type: "set_quantity", cart_item_id: "185350", quantity: 0 }), true);
  assert.equal(core.validateMessage({ type: "set_quantity", cart_item_id: "185350", quantity: 999 }), true);
  for (const bad of [
    { type: "set_quantity", cart_item_id: "185350", quantity: 1000 },
    { type: "set_quantity", cart_item_id: "185350", quantity: -1 },
    { type: "set_quantity", cart_item_id: "185350", quantity: 1.5 },
    { type: "set_quantity", cart_item_id: "185350", quantity: "2" },
    { type: "set_quantity", cart_item_id: 185350, quantity: 2 },
    { type: "set_quantity", cart_item_id: "0185350", quantity: 2 },
    { type: "set_quantity", cart_item_id: "185350" },
    { type: "ping" },
    { type: "other" },
    {},
    null,
    "get_cart",
  ]) {
    assert.equal(core.validateMessage(bad), false, JSON.stringify(bad));
  }
});

test("extractCart finds the cart in plausible shapes", () => {
  const items = [{ id: 1, q: "1" }];
  const found = core.extractCart(CART);
  assert.deepEqual([found.items, found.storeId, found.addressId, found.orderType], [CART.data.cart.items, 165, 9, "DELIVERY"]);
  assert.deepEqual(found.unavailable, []);
  assert.equal(core.extractCart({ cart: { items, storeId: 1 } }).storeId, 1);
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

test("normalizeCart: items, prices, discounts, free items, notes and max_quantity", () => {
  const cart = core.normalizeCart(realCart());
  assert.deepEqual(cart.store, { id: "165", name: "FairPrice PFC" });
  assert.deepEqual(cart.items.map((i) => i.cart_item_id), ["185350", "167545", "190001", "999"]);
  const [salt, sea, rice, gift] = cart.items;
  assert.deepEqual(salt, {
    cart_item_id: "185350", name: "FairPrice Fine Salt", brand: "FairPrice", display_unit: "500g",
    image_url: "https://media.example/salt.jpg?w=320&q=60", product_url: "https://www.fairprice.com.sg/product/fairprice-fine-salt-500g",
    quantity: 2, unit_price_sgd: 0.45, unit_mrp_sgd: 0.45, line_total_sgd: 0.9, line_saving_sgd: 0,
    max_quantity: 50, is_checked: true, is_free: false, note: null,
  });
  // Discounted: unit price is mrp - discount, the line total follows the site's cart row.
  assert.equal(sea.unit_price_sgd, 2);
  assert.equal(sea.unit_mrp_sgd, 2.5);
  assert.equal(sea.line_total_sgd, 6);
  assert.equal(sea.line_saving_sgd, 1.5);
  assert.equal(sea.image_url, "https://media.example/sea.jpg?v=2&w=320&q=60");
  assert.equal(sea.is_checked, false);
  // max_quantity: the smaller of the purchase cap and stock; unlimited stock ignores stock; else 99.
  assert.equal(sea.max_quantity, 5);
  assert.equal(rice.max_quantity, 99);
  assert.equal(rice.image_url, null);
  assert.equal(sea.note, "Only 3 left");
  assert.equal(rice.note, "Back in stock");
  // A free item is shown but marked, with its quantity as its limit.
  assert.equal(gift.is_free, true);
  assert.equal(gift.unit_price_sgd, 0);
  assert.equal(gift.max_quantity, 1);
  assert.deepEqual(cart.unavailable, [{ cart_item_id: "150002", name: "Gone Item", image_url: "https://media.example/gone.jpg?w=320&q=60", want_quantity: 1 }]);
});

test("normalizeCart: totals, with and without sellers", () => {
  const totals = core.normalizeCart(realCart()).totals;
  assert.deepEqual(totals, {
    subtotal_sgd: 7.55, savings_sgd: 1, delivery_sgd: 0, delivery_standard_sgd: 7.99,
    service_fee_sgd: 0.99, service_fee_standard_sgd: 0.99, total_sgd: 8.54,
  });
  const noSellers = realCart();
  delete noSellers.data.cart.sellersAmounts;
  noSellers.data.cart.amounts.orderAmount = 6.1;
  assert.equal(core.normalizeCart(noSellers).totals.subtotal_sgd, 6.1);
  // No amounts at all: every total is a finite number (fees and savings 0, subtotal and total 0 for an empty cart).
  const bare = core.normalizeCart({ data: { cart: { items: [], storeId: 165 } } });
  assert.deepEqual(bare.totals, { subtotal_sgd: 0, savings_sgd: 0, delivery_sgd: 0, delivery_standard_sgd: 0, service_fee_sgd: 0, service_fee_standard_sgd: 0, total_sgd: 0 });
  assert.deepEqual(bare.store, { id: "165", name: null });
});

test("normalizeCart totals fall back to the lines and the fees, and are always finite", () => {
  // No orderAmount and no youPay: subtotal = sum of line totals (0.9 + 6 + 5), total = subtotal + delivery + service fee.
  const degraded = realCart();
  delete degraded.data.cart.sellersAmounts;
  delete degraded.data.cart.amounts.orderAmount;
  delete degraded.data.cart.youPay;
  degraded.data.cart.amounts.shippingAmount = 2;
  const totals = core.normalizeCart(degraded).totals;
  assert.equal(totals.subtotal_sgd, 11.9);
  assert.equal(totals.total_sgd, 14.89);
  // youPay wins over the sum when it is there; unreadable values count as missing.
  degraded.data.cart.youPay = "9.5";
  degraded.data.cart.amounts.orderAmount = "n/a";
  degraded.data.cart.amounts.currentServiceFee = NaN;
  const second = core.normalizeCart(degraded).totals;
  assert.deepEqual([second.subtotal_sgd, second.service_fee_sgd, second.total_sgd], [11.9, 0, 9.5]);
  for (const cart of [core.normalizeCart(realCart()), core.normalizeCart(degraded), core.normalizeCart({ data: { cart: { items: [{ id: 1, q: "1" }] } } })]) {
    for (const value of Object.values(cart.totals)) assert.ok(Number.isFinite(value), JSON.stringify(cart.totals));
  }
});

test("normalizeCart item money is a finite number or null, null when there is no readable price", () => {
  const item = core.normalizeCart({ data: { cart: { items: [{ id: 1, q: "2", product: { name: "No price" } }] } } }).items[0];
  assert.deepEqual([item.unit_price_sgd, item.unit_mrp_sgd, item.line_total_sgd, item.line_saving_sgd], [null, null, null, null]);
  assert.equal(item.max_quantity, 99);
  for (const key of ["unit_price_sgd", "unit_mrp_sgd", "line_total_sgd", "line_saving_sgd"]) {
    for (const mrp of ["abc", NaN, Infinity]) {
      const odd = core.normalizeCart({ data: { cart: { items: [{ id: 1, q: "1", product: { storeSpecificData: { mrp, discount: "x" } } }] } } }).items[0];
      assert.equal(odd[key], null, key + " " + mrp);
    }
  }
});

test("normalizeCart leaves out items at quantity 0, the request side keeps them", () => {
  const cart = realCart();
  cart.data.cart.items[1].q = "0";
  const normalized = core.normalizeCart(cart);
  assert.deepEqual(normalized.items.map((i) => i.cart_item_id), ["185350", "190001", "999"]);
  assert.equal(core.mergeItems(core.extractCart(cart).items, [], 1).some((i) => i.id === "167545" && i.q === "0"), true);
});

test("normalizeCart line math follows the site's cart row", () => {
  const priced = (product, extra = {}) => core.normalizeCart({ data: { cart: { items: [{ id: 1, q: "3", product, ...extra }] } } }).items[0];
  const pick = (i) => [i.unit_price_sgd, i.line_total_sgd, i.line_saving_sgd];
  // Product-level discount beats the item's, which beats the store's.
  assert.deepEqual(pick(priced({ discount: 1, storeSpecificData: { mrp: 5, discount: 0.5 } }, { discount: 2 })), [4, 12, 3]);
  assert.deepEqual(pick(priced({ storeSpecificData: { mrp: 5, discount: 0.5 } }, { discount: 2 })), [3, 9, 6]);
  assert.deepEqual(pick(priced({ storeSpecificData: { mrp: 5, discount: 0.5 } })), [4.5, 13.5, 1.5]);
  // An applied offer's discount comes first, on the item or its product.
  const offer = { productsBought: [{ discount: 1.25 }] };
  assert.deepEqual(pick(priced({ discount: 1, storeSpecificData: { mrp: 5 } }, { appliedOffer: offer })), [3.75, 11.25, 3.75]);
  assert.deepEqual(pick(priced({ appliedOffer: offer, storeSpecificData: { mrp: 5, discount: 0.5 } })), [3.75, 11.25, 3.75]);
  // A saving above the line's price is shown as 0 (the site's totalDiscount > mrp x count rule).
  assert.deepEqual(pick(priced({ storeSpecificData: { mrp: 2, discount: 3 } })), [2, 6, 0]);
  assert.deepEqual(pick(priced({ storeSpecificData: { mrp: 2, discount: 2 } })), [0, 0, 6]);
});

test("normalizeCart max_quantity stays below the bulk thresholds", () => {
  const max = (product) => core.normalizeCart({ data: { cart: { items: [{ id: 1, q: "1", product: { storeSpecificData: { mrp: 1, stock: 50 }, ...product } }] } } }).items[0].max_quantity;
  assert.equal(max({}), 50);
  assert.equal(max({ bulkOrderThreshold: 10 }), 9);
  assert.equal(max({ stockOverride: { storeBulkOrderThreshold: 8 } }), 7);
  assert.equal(max({ bulkOrderThreshold: 10, stockOverride: { storeBulkOrderThreshold: 4 } }), 3);
  assert.equal(max({ bulkOrderThreshold: 0, stockOverride: { storeBulkOrderThreshold: 6 } }), 5, "a zero threshold is not set");
  assert.equal(max({ bulkOrderThreshold: 0, stockOverride: { storeBulkOrderThreshold: 0 } }), 50);
  assert.equal(max({ bulkOrderThreshold: 1 }), 1, "never below 1");
  assert.equal(max({ bulkOrderThreshold: 100, stockOverride: { maxPurchasableStock: 5 } }), 5, "the smallest cap wins");
});

test("normalizeCart keeps the address, account and token out", () => {
  const text = JSON.stringify(core.normalizeCart(realCart()));
  assert.equal(text.includes("98765"), false);
  assert.equal(text.includes("Secret Road"), false);
  assert.equal(core.normalizeCart({ data: { nothing: 1 } }), null);
  assert.equal(core.normalizeCart({ data: { cart: { items: [{ id: 1, q: "x" }] } } }), null);
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

test("buildBody is the body FairPrice's own site sends, with the address id as a number", () => {
  const body = core.buildBody({ storeId: 165, addressId: "9", orderType: "PICKUP" }, [{ id: "1" }], 4242);
  assert.deepEqual(body, {
    customerId: 4242,
    storeId: "165",
    addressId: 9,
    cart: { items: [{ id: "1" }], isOutOfStockEnabled: true, dropUnavailableItems: [] },
    orderType: "PICKUP",
    isOutOfStockEnabled: true,
    isCheckerEnabled: true,
    isSellerCheckerEnabled: true,
    isSellerTimeSlotEnabled: true,
    isDirectFulfilmentEnabled: true,
    poaItemDropOff: false,
  });
  // The store stays a string; an address that is not a numeric string is left as it is.
  assert.equal(typeof core.buildBody({ storeId: 165, addressId: 9 }, []).addressId, "number");
  assert.equal(core.buildBody({ storeId: "165", addressId: "home" }, []).addressId, "home");
  assert.equal(core.buildBody({ storeId: "165" }, [], 1, ["150002"]).cart.dropUnavailableItems[0], "150002");
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

test("resultsFor takes the price from the product's store data, as the real reply has it", () => {
  const item = { id: 7, q: "1", product: { storeSpecificData: { mrp: 2.5, discount: 0.5 } } };
  assert.equal(core.resultsFor([line("7", 1)], [item], [])[0].cart_price_sgd, 2);
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

test("checkAnswer only lets a well-formed answer through, and only the contract's fields", () => {
  const cart = core.normalizeCart(realCart());
  const lines = [line("1", 2, "a"), line("2", 1, "b")];
  const message = { type: "add_to_cart", lines };
  const results = [{ line_key: "a", cart_item_id: "1", status: "added", quantity: 2, cart_price_sgd: null }, { line_key: "b", cart_item_id: "2", status: "reduced", quantity: 0, cart_price_sgd: null }];
  const good = { ok: true, results, cart, cart_changed: ["9"] };
  assert.deepEqual(core.checkAnswer(message, { ...good, secret: "x" }), good);
  const bad = { ok: false, error: "unexpected_response" };
  assert.deepEqual(core.checkAnswer(message, undefined), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: "yes" }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: true, cart }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: true, results }), bad, "an add answer needs the cart");
  assert.deepEqual(core.checkAnswer(message, { ok: true, results: results.slice(0, 1), cart }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: true, cart, results: [results[0], { ...results[1], status: "weird" }] }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: true, cart, results: [results[0], { ...results[1], quantity: "1" }] }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: true, cart, results: [results[0], { ...results[1], line_key: "z" }] }), bad);
  assert.deepEqual(core.checkAnswer(message, { ...good, cart_changed: "9" }), bad);
  assert.deepEqual(core.checkAnswer(message, { ...good, cart: { items: [] } }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: false, error: "not_logged_in" }), { ok: false, error: "not_logged_in" });
  assert.deepEqual(core.checkAnswer(message, { ok: false, error: "made_up" }), bad);
  assert.deepEqual(core.checkAnswer(message, { ok: false, error: "request_refused", detail: "HTTP 403" }), { ok: false, error: "request_refused", detail: "HTTP 403" });
  const dryMessage = { ...message, dry_run: true };
  const dry = { ok: true, dry_run: true, body: { cart: {} }, results: results.map((r) => ({ ...r, status: "would_add" })) };
  assert.deepEqual(core.checkAnswer(dryMessage, dry), dry);
  assert.deepEqual(core.checkAnswer(dryMessage, { ...dry, body: undefined }), bad);
  assert.deepEqual(core.checkAnswer(dryMessage, good), bad);
  assert.deepEqual(core.checkAnswer(message, dry), bad);
  // get_cart and set_quantity answer with the cart.
  assert.deepEqual(core.checkAnswer({ type: "get_cart" }, { ok: true, cart, extra: 1 }), { ok: true, cart });
  assert.deepEqual(core.checkAnswer({ type: "set_quantity" }, { ok: true, cart }), { ok: true, cart });
  assert.deepEqual(core.checkAnswer({ type: "get_cart" }, { ok: true }), bad);
  // Money must be finite: totals always, item prices a finite number or null.
  const withTotals = (patch) => ({ ok: true, cart: { ...cart, totals: { ...cart.totals, ...patch } } });
  for (const patch of [{ total_sgd: null }, { subtotal_sgd: null }, { total_sgd: NaN }, { delivery_sgd: Infinity }, { service_fee_sgd: "0.99" }, { savings_sgd: undefined }]) {
    assert.deepEqual(core.checkAnswer({ type: "get_cart" }, withTotals(patch)), bad, JSON.stringify(patch));
  }
  const withItem = (patch) => ({ ok: true, cart: { ...cart, items: [{ ...cart.items[0], ...patch }] } });
  const nulls = { unit_price_sgd: null, unit_mrp_sgd: null, line_total_sgd: null, line_saving_sgd: null, name: null };
  assert.equal(core.checkAnswer({ type: "get_cart" }, withItem(nulls)).ok, true, "null item money is allowed");
  for (const patch of [{ unit_price_sgd: NaN }, { line_total_sgd: "1" }, { unit_mrp_sgd: undefined }, { line_saving_sgd: Infinity }, { quantity: NaN }, { max_quantity: null }, { max_quantity: NaN }]) {
    assert.deepEqual(core.checkAnswer({ type: "set_quantity" }, withItem(patch)), bad, JSON.stringify(patch));
  }
  assert.deepEqual(core.checkAnswer({ type: "set_quantity" }, { ok: false, error: "not_in_cart" }), { ok: false, error: "not_in_cart" });
  assert.deepEqual(core.checkAnswer({ type: "get_cart" }, { ok: true, cart: { store: {}, items: [{ cart_item_id: 1 }], unavailable: [], totals: cart.totals } }), bad);
});

test("every call without a token does nothing", async () => {
  const fetch = mockFetch([]);
  const none = { ok: false, error: "not_logged_in" };
  assert.deepEqual(await core.addToCart([line("1")], { fetch }), none);
  assert.deepEqual(await core.getCart({ fetch, token: "" }), none);
  assert.deepEqual(await core.setQuantity("1", 1, { fetch, token: null }), none);
  assert.equal(fetch.calls.length, 0);
});

test("a 401 means not logged in", async () => {
  const fetch = mockFetch([{ status: 401, text: async () => "" }]);
  assert.deepEqual(await core.getCart({ fetch, token: "t" }), { ok: false, error: "not_logged_in", detail: "HTTP 401" });
});

test("getCart returns the normalized cart from a GET", async () => {
  const fetch = mockFetch([jsonResponse(realCart())]);
  const result = await core.getCart({ fetch, token: "secret-token" });
  assert.equal(result.ok, true);
  assert.equal(result.cart.items.length, 4);
  assert.deepEqual(fetch.cartCalls(), ["GET"]);
  assert.equal(fetch.calls.length, 1, "no profile call for a read");
  assert.equal(fetch.calls[0].init.headers.Authorization, "Bearer secret-token");
  assert.equal(fetch.calls[0].init.credentials, undefined);
  assert.equal(JSON.stringify(result).includes("secret-token"), false);
});

test("nothing is written when the cart cannot be read", async () => {
  const cases = [
    [{ status: 403, text: async () => "" }, "request_refused", "HTTP 403"],
    [{ status: 200, text: async () => "<html>challenge</html>" }, "request_refused", "HTTP 200"],
    [{ status: 200, text: async () => "{broken" }, "unexpected_response", "HTTP 200"],
    [jsonResponse({ data: { nothing: true } }), "cart_unreadable", '{"keys":"data","dataKeys":"nothing"}'],
    [jsonResponse({ data: { cart: { items: [{ id: 5, q: "1.5" }] } } }), "cart_unreadable", '{"keys":"data","dataKeys":"cart","cartKeys":"items"}'],
  ];
  for (const [response, error, detail] of cases) {
    for (const run of [
      (fetch) => core.addToCart([line("1")], { fetch, token: "t" }),
      (fetch) => core.setQuantity("5", 0, { fetch, token: "t" }),
      (fetch) => core.getCart({ fetch, token: "t" }),
    ]) {
      const fetch = mockFetch([response]);
      assert.deepEqual(await run(fetch), { ok: false, error, detail });
      assert.deepEqual(fetch.cartCalls(), ["GET"]);
    }
  }
  const throwing = async () => {
    throw new Error("network");
  };
  assert.deepEqual(await core.addToCart([line("1")], { fetch: throwing, token: "t" }), { ok: false, error: "unexpected_response", detail: "network" });
});

test("addToCart dry run returns the body and sends no POST", async () => {
  const fetch = mockFetch([jsonResponse(CART)]);
  const result = await core.addToCart([line("5", 2), line("9", 1)], { fetch, token: "secret", dryRun: true, now: 42 });
  assert.equal(result.ok, true);
  assert.equal(result.dry_run, true);
  assert.deepEqual(result.results.map((r) => r.status), ["would_add", "would_add"]);
  assert.deepEqual(result.body.cart.items.map((i) => [i.id, i.q, i.t]), [["5", "3", 1], ["9", "1", 42]]);
  assert.equal(result.body.storeId, "165");
  assert.equal(result.body.customerId, "<set>", "a dry run shows only that the account id is set");
  assert.equal(result.body.addressId, "<set>");
  assert.deepEqual(fetch.cartCalls(), ["GET"]);
  assert.equal(JSON.stringify(result).includes("secret"), false);
});

test("addToCart writes once, reports per line and returns the cart", async () => {
  const after = realCart();
  const fetch = mockFetch([jsonResponse(realCart()), jsonResponse(after)]);
  const result = await core.addToCart([line("185350", 1, "a"), line("167545", 1, "b")], { fetch, token: "t", now: 42 });
  assert.deepEqual(fetch.cartCalls(), ["GET", "POST"]);
  const post = fetch.calls.find((c) => c.init.method === "POST");
  assert.equal(post.url, "https://website-api.omni.fairprice.com.sg/api/cart");
  assert.equal(post.init.headers.Authorization, "Bearer t");
  assert.equal(post.init.headers["Content-Type"], "application/json");
  assert.equal(post.init.credentials, undefined);
  const body = JSON.parse(post.init.body);
  assert.equal(body.addressId, 98765, "the live write with a string address id was refused");
  assert.equal(body.storeId, "165");
  assert.equal(body.customerId, 4242);
  assert.deepEqual(body.cart.items.map((i) => [i.id, i.q]), [["185350", "3"], ["167545", "4"], ["190001", "1"]], "the free item is not sent back");
  // The mock answers with the same cart as before (quantities unchanged), so the adds count as reduced.
  assert.deepEqual(result.results.map((r) => [r.status, r.quantity]), [["reduced", 0], ["reduced", 0]]);
  assert.equal(result.cart.store.id, "165");
  assert.equal(JSON.stringify(result).includes("Bearer"), false);
});

test("addToCart reports cart items that changed or went missing, not our own", async () => {
  const before = { data: { cart: { items: [{ id: 5, q: "1" }, { id: 6, q: "2" }, { id: 7, q: "3" }, { id: 8, q: "1" }] } } };
  const after = { data: { cart: { items: [{ id: 5, q: "3" }, { id: 6, q: "1" }, { id: 8, q: "1" }] } } };
  const fetch = mockFetch([jsonResponse(before), jsonResponse(after)]);
  const result = await core.addToCart([line("5", 2)], { fetch, token: "t" });
  assert.equal(result.ok, true);
  assert.deepEqual(result.cart_changed, ["6", "7"]);
  const calm = mockFetch([jsonResponse(CART), jsonResponse({ data: { cart: { items: [{ id: 5, q: "3" }] } } })]);
  assert.equal("cart_changed" in (await core.addToCart([line("5", 2)], { fetch: calm, token: "t" })), false);
});

test("addToCart reports a refused or unreadable write", async () => {
  const refused = mockFetch([jsonResponse(CART), { status: 403, text: async () => "" }]);
  assert.deepEqual(await core.addToCart([line("9")], { fetch: refused, token: "t" }), { ok: false, error: "request_refused", detail: "HTTP 403" });
  const odd = mockFetch([jsonResponse(CART), jsonResponse({ ok: true })]);
  assert.deepEqual(await core.addToCart([line("9")], { fetch: odd, token: "t" }), { ok: false, error: "unexpected_response", detail: '{"keys":"ok","dataKeys":""}' });
  const invalid = mockFetch([jsonResponse(CART), jsonResponse({ code: "400", status: "ERROR", message: "Invalid Cart - error when unmarshalling request cart" }, 400)]);
  const answer = await core.addToCart([line("9")], { fetch: invalid, token: "t" });
  assert.equal(answer.error, "unexpected_response");
  assert.ok(answer.detail.includes("Invalid Cart"));
});

test("requests carry the bearer token only, never cookies, and failures say why", async () => {
  const calls = [];
  const fetch = async (url, init) => {
    calls.push(init);
    if (url.endsWith("/user-profile")) return jsonResponse({ id: 1 });
    if (init.method === "GET") return jsonResponse({ data: { cart: { items: [], storeId: 165 } } });
    throw new TypeError("Failed to fetch");
  };
  const result = await core.addToCart([line("185350", 1, "a")], { fetch, token: "abc", now: 1 });
  assert.deepEqual(result, { ok: false, error: "unexpected_response", detail: "Failed to fetch" });
  assert.equal(calls.length, 3);
  for (const init of calls) assert.equal(init.credentials, undefined);
  const refused = await core.addToCart([line("185350", 1, "a")], { fetch: async () => ({ status: 403, text: async () => "" }), token: "abc" });
  assert.deepEqual(refused, { ok: false, error: "request_refused", detail: "HTTP 403" });
});

test("describeAnswer names FairPrice's status, message and keys but no cart values", () => {
  const said = JSON.parse(core.describeAnswer({ code: 400, status: "ERROR", message: "storeId is required", data: { cart: { items: [{ id: 1 }], addressId: "secret" } } }));
  assert.deepEqual(said, { code: "400", status: "ERROR", message: "storeId is required", keys: "code,status,message,data", dataKeys: "cart", cartKeys: "items,addressId" });
  assert.ok(!core.describeAnswer({ data: { cart: { addressId: "secret" } } }).includes("secret"));
});

test("the customer id is read from /user-profile once and cached for the same login", async () => {
  const cache = memoryCache();
  const first = mockFetch([jsonResponse(CART), jsonResponse(CART)], jsonResponse({ id: 777, email: "a@b.c" }));
  const dry = await core.addToCart([line("5", 1)], { fetch: first, token: "tokenAAAAAAAAAAAAAAAAAAAA", cache });
  assert.equal(posted(first).customerId, 777);
  const profileCall = first.calls.find((c) => c.url === "https://www.fairprice.com.sg/user-profile");
  assert.equal(profileCall.init.method, "GET");
  assert.equal(profileCall.init.headers.Authorization, "Bearer tokenAAAAAAAAAAAAAAAAAAAA");
  assert.equal(JSON.stringify(cache.peek()).includes("tokenAAAAAAAAAAAAAAAAAAAA"), false, "the token is not stored");
  // The key is the first 16 hex characters of SHA-256(token): nothing of the token itself, not even its tail.
  const digest = require("node:crypto").createHash("sha256").update("tokenAAAAAAAAAAAAAAAAAAAA").digest("hex");
  assert.deepEqual(cache.peek(), { key: digest.slice(0, 16), id: 777 });
  assert.match(cache.peek().key, /^[0-9a-f]{16}$/);
  assert.equal("tokenAAAAAAAAAAAAAAAAAAAA".includes(cache.peek().key), false);
  assert.equal(JSON.stringify(dry).includes("a@b.c"), false);
  // Same login: no second profile call.
  const second = mockFetch([jsonResponse(CART), jsonResponse(CART)], jsonResponse({ id: 1 }));
  await core.addToCart([line("5", 1)], { fetch: second, token: "tokenAAAAAAAAAAAAAAAAAAAA", cache });
  assert.equal(posted(second).customerId, 777);
  assert.equal(second.calls.filter((c) => c.url.endsWith("/user-profile")).length, 0);
  // Another login asks again.
  const other = mockFetch([jsonResponse(CART), jsonResponse(CART)], jsonResponse({ id: 888 }));
  await core.addToCart([line("5", 1)], { fetch: other, token: "tokenBBBBBBBBBBBBBBBBBBBB", cache });
  assert.equal(posted(other).customerId, 888);
  // A cache that throws is ignored.
  const broken = { get: async () => { throw new Error("no storage"); }, set: async () => { throw new Error("no storage"); } };
  const brokenFetch = mockFetch([jsonResponse(CART), jsonResponse(CART)]);
  await core.addToCart([line("5", 1)], { fetch: brokenFetch, token: "t", cache: broken });
  assert.equal(posted(brokenFetch).customerId, 4242);
});

test("the account id is resolved before the cart is read, so the read and the write are back to back", async () => {
  for (const run of [
    (fetch) => core.addToCart([line("5", 1)], { fetch, token: "t" }),
    (fetch) => core.setQuantity("5", 2, { fetch, token: "t" }),
  ]) {
    const fetch = mockFetch([jsonResponse(CART), jsonResponse(CART)]);
    assert.equal((await run(fetch)).ok, true);
    assert.deepEqual(fetch.calls.map((c) => c.init.method + " " + (c.url.endsWith("/user-profile") ? "profile" : "cart")), ["GET profile", "GET cart", "POST cart"]);
  }
});

test("a write without a readable customer id is not sent", async () => {
  for (const profile of [jsonResponse({ name: "x" }), jsonResponse({ id: "abc" }), { status: 401, text: async () => "" }, jsonResponse({ id: 0 })]) {
    const fetch = mockFetch([jsonResponse(CART)], profile);
    const result = await core.addToCart([line("5", 1)], { fetch, token: "t" });
    assert.equal(result.ok, false);
    assert.deepEqual(fetch.cartCalls(), [], "the cart is not even read");
  }
  const unauthorized = await core.addToCart([line("5", 1)], { fetch: mockFetch([jsonResponse(CART)], { status: 401, text: async () => "" }), token: "t" });
  assert.equal(unauthorized.error, "not_logged_in");
  // A numeric string id becomes a number.
  const fetch = mockFetch([jsonResponse(CART), jsonResponse(CART)], jsonResponse({ id: "321" }));
  await core.addToCart([line("5", 1)], { fetch, token: "t" });
  assert.equal(posted(fetch).customerId, 321);
});

test("setQuantity changes one item, sends the rest back and returns the normalized cart", async () => {
  const after = realCart();
  after.data.cart.items[0].q = "5";
  const fetch = mockFetch([jsonResponse(realCart()), jsonResponse(after)]);
  const result = await core.setQuantity("185350", 5, { fetch, token: "t", now: 7 });
  assert.deepEqual(fetch.cartCalls(), ["GET", "POST"]);
  const body = JSON.parse(fetch.calls.find((c) => c.init.method === "POST").init.body);
  assert.deepEqual(body.cart.items.map((i) => [i.id, i.q, i.isChecked, i.t]), [["185350", "5", true, 100], ["167545", "3", false, 101], ["190001", "1", true, 102]]);
  assert.deepEqual(body.cart.dropUnavailableItems, []);
  assert.equal(body.addressId, 98765);
  assert.equal(result.ok, true);
  assert.equal(result.cart.items[0].quantity, 5);
});

test("setQuantity 0 removes an item by sending it with q \"0\"", async () => {
  const fetch = mockFetch([jsonResponse(realCart()), jsonResponse(realCart())]);
  await core.setQuantity("167545", 0, { fetch, token: "t" });
  const body = JSON.parse(fetch.calls.find((c) => c.init.method === "POST").init.body);
  assert.deepEqual(body.cart.items.map((i) => [i.id, i.q]), [["185350", "2"], ["167545", "0"], ["190001", "1"]]);
});

test("setQuantity removes an unavailable item through dropUnavailableItems", async () => {
  const fetch = mockFetch([jsonResponse(realCart()), jsonResponse(realCart())]);
  const result = await core.setQuantity("150002", 0, { fetch, token: "t" });
  assert.equal(result.ok, true);
  const body = JSON.parse(fetch.calls.find((c) => c.init.method === "POST").init.body);
  assert.deepEqual(body.cart.dropUnavailableItems, ["150002"]);
  assert.deepEqual(body.cart.items.map((i) => [i.id, i.q]), [["185350", "2"], ["167545", "3"], ["190001", "1"]], "the other items go back unchanged");
  // An unavailable item cannot be given a quantity.
  const refused = mockFetch([jsonResponse(realCart())]);
  const answer = await core.setQuantity("150002", 2, { fetch: refused, token: "t" });
  assert.equal(answer.error, "invalid_request");
  assert.deepEqual(refused.cartCalls(), ["GET"]);
});

test("setQuantity answers not_in_cart for an id that is neither in the cart nor unavailable, and refuses a free item, without writing", async () => {
  for (const [id, error] of [["12345", "not_in_cart"], ["999", "invalid_request"]]) {
    const fetch = mockFetch([jsonResponse(realCart())]);
    const answer = await core.setQuantity(id, 1, { fetch, token: "t" });
    assert.equal(answer.ok, false);
    assert.equal(answer.error, error);
    assert.deepEqual(fetch.cartCalls(), ["GET"]);
  }
  // Also when the person asks to remove it, and an id that was in the cart a moment ago.
  const gone = mockFetch([jsonResponse(realCart())]);
  assert.equal((await core.setQuantity("12345", 0, { fetch: gone, token: "t" })).error, "not_in_cart");
  assert.deepEqual(gone.cartCalls(), ["GET"]);
  assert.deepEqual(core.checkAnswer({ type: "set_quantity" }, { ok: false, error: "not_in_cart", detail: "item 12345" }), { ok: false, error: "not_in_cart", detail: "item 12345" });
});

test("setQuantity reports a refused or unreadable write", async () => {
  const refused = mockFetch([jsonResponse(realCart()), { status: 403, text: async () => "" }]);
  assert.deepEqual(await core.setQuantity("185350", 3, { fetch: refused, token: "t" }), { ok: false, error: "request_refused", detail: "HTTP 403" });
  const odd = mockFetch([jsonResponse(realCart()), jsonResponse({ code: "400", status: "ERROR", message: "bad" }, 400)]);
  const answer = await core.setQuantity("185350", 3, { fetch: odd, token: "t" });
  assert.equal(answer.error, "unexpected_response");
  assert.ok(answer.detail.includes('"message":"bad"'));
});
