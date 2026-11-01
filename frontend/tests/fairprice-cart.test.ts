import { describe, expect, it } from "vitest";

import {
  CART_CHANGED_NOTE,
  budgetWarning,
  cartChanged,
  cartErrorMessage,
  cartIds,
  cartPayload,
  cartStateLabels,
  clampQuantity,
  feeParts,
  isDiscounted,
  isLocked,
  linesInCart,
  priceChanges,
  problemLabel,
  problemLines,
  readErrorMessage,
  readyLines,
  reportableReply,
  resultNote,
  runtimeErrorCode,
  sgdOrDash,
  summarizeResults,
  summaryLine,
  swapSentence,
  tripKey,
} from "../app/lib/fairprice-cart";
import type { FairPriceCartLine, FairPriceCartPrepare, FairPriceCartResult, FairPriceCartTrip, FairPriceLiveCart } from "../app/types/meal-plan";

function line(over: Partial<FairPriceCartLine>): FairPriceCartLine {
  return {
    line_key: "1|chicken_breast|g",
    ingredient_name: "chicken_breast",
    ingredient_display_name: "chicken breast",
    product_name: "Kee Song Fresh Chicken - Boneless Breast",
    client_item_id: "13097675",
    cart_item_id: "172993",
    quantity: 2,
    planned_price_sgd: 6.95,
    live_price_sgd: 6.95,
    product_url: "https://www.fairprice.com.sg/product/chicken-13097675",
    status: "ready",
    ...over,
  };
}

const result = (status: FairPriceCartResult["status"], key = "1|chicken_breast|g"): FairPriceCartResult =>
  ({ line_key: key, cart_item_id: "172993", status, quantity: 2, cart_price_sgd: 6.95 });

describe("FairPrice cart lines", () => {
  const lines = [
    line({}),
    line({ line_key: "1|rice|g", ingredient_display_name: "rice", cart_item_id: null, status: "out_of_stock" }),
    line({ line_key: "1|salt|g", cart_item_id: null, status: "no_product" }),
    line({ line_key: "1|oil|ml", cart_item_id: null, status: "not_bought" }),
    line({ line_key: "1|egg|g", cart_item_id: null, status: "not_found" }),
  ];

  it("sends only ready lines, with the id FairPrice's cart takes", () => {
    expect(readyLines(lines).map(l => l.line_key)).toEqual(["1|chicken_breast|g"]);
    expect(cartPayload(lines)).toEqual([{ line_key: "1|chicken_breast|g", cart_item_id: "172993", quantity: 2 }]);
    // A "ready" line with no cart id cannot be sent.
    expect(readyLines([line({ cart_item_id: null })])).toEqual([]);
  });

  it("leaves out ready lines already in the cart (same cart_item_id) unless asked to add again", () => {
    const cart = { items: [{ cart_item_id: "172993" }, { cart_item_id: "999" }] } as unknown as FairPriceLiveCart;
    const inCart = cartIds(cart);
    expect([...inCart]).toEqual(["172993", "999"]);
    expect(cartIds(null).size).toBe(0);
    expect(linesInCart(lines, inCart).map(l => l.line_key)).toEqual(["1|chicken_breast|g"]);
    expect(cartPayload(lines, inCart)).toEqual([]);
    expect(cartPayload(lines, inCart, true)).toEqual([{ line_key: "1|chicken_breast|g", cart_item_id: "172993", quantity: 2 }]);
  });

  it("calls everything except ready and pantry-covered lines a problem", () => {
    expect(problemLines(lines).map(l => l.status)).toEqual(["out_of_stock", "no_product", "not_found"]);
    expect(problemLabel(lines[1]!)).toBe("Out of stock at FairPrice now");
    expect(problemLabel(lines[4]!)).toBe("FairPrice no longer lists this product");
  });

  it("lists lines whose live price differs from the planned one", () => {
    const changes = priceChanges([
      line({ live_price_sgd: 7.45 }),
      line({ line_key: "same", live_price_sgd: 6.951 }),
      line({ line_key: "down", live_price_sgd: 5.5 }),
      line({ line_key: "none", live_price_sgd: null }),
      line({ line_key: "unplanned", planned_price_sgd: null }),
    ]);
    expect(changes.map(c => [c.line.line_key, c.planned, c.live, c.direction])).toEqual([
      ["1|chicken_breast|g", 6.95, 7.45, "up"],
      ["down", 6.95, 5.5, "down"],
    ]);
  });
});

describe("FairPrice cart budget", () => {
  const prepare = (over: Partial<FairPriceCartPrepare>): FairPriceCartPrepare => ({
    plan_id: 12,
    shopping_trip: null,
    fingerprint: "abc",
    lines: [],
    ready_total_sgd: 13.9,
    planned_total_sgd: 131.2,
    projected_total_sgd: 142.3,
    budget_sgd: 140,
    over_budget: true,
    ...over,
  });

  it("warns, with the gap, only when over budget", () => {
    expect(budgetWarning(prepare({}))).toBe(
      "At today's FairPrice prices this trip comes to S$142.30, S$2.30 over your S$140.00 budget. Your plan is not changed.",
    );
    expect(budgetWarning(prepare({ over_budget: false }))).toBeNull();
    expect(budgetWarning(prepare({ budget_sgd: null }))).toBeNull();
  });
});

describe("FairPrice cart results", () => {
  it("counts what the extension did and says it plainly", () => {
    const counts = summarizeResults([result("added"), result("added", "b"), result("reduced", "c"), result("out_of_stock", "d"), result("failed", "e")]);
    expect(counts).toEqual({ added: 2, reduced: 1, out_of_stock: 1, failed: 1 });
    expect(summaryLine(counts)).toBe("2 added, 1 reduced, 1 out of stock, 1 failed");
    expect(summaryLine(summarizeResults([result("added")]))).toBe("1 added");
    expect(summaryLine(summarizeResults([]))).toBe("Nothing was added");
  });

  it("asks the assistant the can't-buy sentence it already reads, naming the ingredient", () => {
    expect(swapSentence(line({ ingredient_display_name: "firm tofu" }))).toBe("I can't buy firm tofu this week");
  });

  it("explains every extension error in the person's terms", () => {
    expect(cartErrorMessage("not_logged_in")).toMatch(/not logged in to FairPrice/i);
    expect(cartErrorMessage("request_refused")).toMatch(/product links/);
    expect(cartErrorMessage("no_extension")).toMatch(/isn't installed/);
    expect(cartErrorMessage("unexpected_response")).toMatch(/Check your FairPrice cart/);
    expect(cartErrorMessage("invalid_request")).toMatch(/nothing was sent/);
    expect(cartErrorMessage("busy")).toMatch(/still running.*Wait for it.*check your cart/);
    expect(cartErrorMessage("not_in_cart")).toBe("That item is no longer in your FairPrice cart");
    expect(cartErrorMessage("interrupted")).toMatch(/stopped before answering.*reading your FairPrice cart again/);
    for (const code of ["not_logged_in", "cart_unreadable", "request_refused", "unexpected_response", "invalid_request", "busy", "no_extension", "timeout", "not_in_cart", "interrupted"] as const) {
      expect(cartErrorMessage(code).length).toBeGreaterThan(20);
    }
  });

  it("calls only Chrome's \"no listener\" errors a missing extension; any other runtime error is an interrupted one", () => {
    expect(runtimeErrorCode("Could not establish connection. Receiving end does not exist.")).toBe("no_extension");
    expect(runtimeErrorCode("Could not establish connection")).toBe("no_extension");
    expect(runtimeErrorCode("The message port closed before a response was received.")).toBe("interrupted");
    expect(runtimeErrorCode(undefined)).toBe("interrupted");
  });

  it("words a failed read as a read: nothing was written, so it only asks to try again", () => {
    for (const code of ["request_refused", "timeout", "unexpected_response", "interrupted"] as const) {
      expect(readErrorMessage(code)).toMatch(/cart/);
      expect(readErrorMessage(code)).not.toMatch(/twice|before trying again/);
    }
    expect(readErrorMessage("cart_unreadable")).toBe(cartErrorMessage("cart_unreadable"));
    expect(readErrorMessage("not_logged_in")).toBe(cartErrorMessage("not_logged_in"));
  });

  it("says what this add put in the cart, whatever the status", () => {
    expect(resultNote({ ...result("added"), quantity: 2 })).toBe("2 added to your cart");
    expect(resultNote({ ...result("reduced"), quantity: 1 }, 2)).toBe("FairPrice took 1 of 2. Add the rest on FairPrice.");
    expect(resultNote({ ...result("reduced"), quantity: 1 })).toMatch(/^FairPrice took 1 of the amount you asked for/);
    expect(resultNote({ ...result("out_of_stock"), quantity: 0 })).toMatch(/Out of stock/);
    expect(resultNote({ ...result("failed"), cart_item_id: null, quantity: 0 })).toMatch(/didn't accept it/);
  });

  it("reports only a real add: a dry run, or a result that is no add status, never is", () => {
    const ok = { ok: true, results: [result("added"), result("reduced", "b")] };
    expect(reportableReply(ok)).toBe(ok);
    const failed = { ok: false, error: "busy" } as const;
    expect(reportableReply(failed)).toBe(failed);
    const unexpected = { ok: false, error: "unexpected_response" };
    expect(reportableReply({ ok: true, dry_run: true, results: [result("added")] })).toEqual(unexpected);
    expect(reportableReply({ ok: true, results: [{ ...result("added"), status: "would_add" as never }] })).toEqual(unexpected);
    expect(reportableReply({ ok: true })).toEqual(unexpected);
  });

  it("notes other cart items that changed only when the extension names some", () => {
    expect(CART_CHANGED_NOTE).toBe("Other items already in your FairPrice cart changed. Check your cart.");
    expect(cartChanged({ ok: true, results: [], cart_changed: ["999"] })).toBe(true);
    expect(cartChanged({ ok: true, results: [], cart_changed: [] })).toBe(false);
    expect(cartChanged({ ok: true, results: [] })).toBe(false);
  });
});

describe("FairPrice cart state", () => {
  const trip = (over: Partial<FairPriceCartTrip>): FairPriceCartTrip => ({
    status: "in_cart", sent_at: "2026-10-29T03:00:00+00:00", fingerprint: "abc", results: [], ...over,
  });

  it("keys a plan's only trip as 1", () => {
    expect(tripKey(null)).toBe("1");
    expect(tripKey(2)).toBe("2");
  });

  it("labels in cart, ordered and changed-since-sent", () => {
    expect(cartStateLabels(null)).toEqual([]);
    expect(cartStateLabels({ 1: trip({}) })).toEqual([{ key: "1", tone: "info", label: "In your FairPrice cart on 29 Oct" }]);
    expect(cartStateLabels({ 1: trip({ stale: true }) })).toEqual([{ key: "1", tone: "warn", label: "List changed since it was sent" }]);
    expect(cartStateLabels({ 1: trip({ status: "ordered", ordered_at: "2026-10-30T01:00:00+00:00" }) })).toEqual([
      { key: "1", tone: "ok", label: "Ordered on 30 Oct" },
    ]);
  });

  it("dates by Singapore time and names each trip of a two-trip plan", () => {
    // 17:00 UTC on the 29th is 01:00 on the 30th in Singapore.
    const labels = cartStateLabels({ 2: trip({ sent_at: "2026-10-29T17:00:00Z" }), 1: trip({ status: "ordered", ordered_at: "2026-10-29T02:00:00Z" }) });
    expect(labels.map(l => l.label)).toEqual(["Trip 1: Ordered on 29 Oct", "Trip 2: In your FairPrice cart on 30 Oct"]);
  });
});

describe("FairPrice cart panel helpers", () => {
  it("shows a waived fee as Free with the usual fee struck through, no fee as S$0.00, and a charged one plainly", () => {
    expect(feeParts(0, 7.99)).toEqual({ text: "Free", was: "S$7.99" });
    expect(feeParts(0, 0.99)).toEqual({ text: "Free", was: "S$0.99" });
    expect(feeParts(0, 0)).toEqual({ text: "S$0.00", was: null });
    expect(feeParts(0.99, 0.99)).toEqual({ text: "S$0.99", was: null });
    expect(feeParts(3.99, 7.99)).toEqual({ text: "S$3.99", was: "S$7.99" });
  });

  it("shows an amount FairPrice left out as a dash", () => {
    expect(sgdOrDash(null)).toBe("—");
    expect(sgdOrDash(undefined)).toBe("—");
    expect(sgdOrDash(0)).toBe("S$0.00");
    expect(sgdOrDash(12.5)).toBe("S$12.50");
  });

  it("keeps a stepper quantity a whole number from 1 to the item's maximum", () => {
    expect(clampQuantity(0, 99)).toBe(1);
    expect(clampQuantity(3.4, 99)).toBe(3);
    expect(clampQuantity(120, 99)).toBe(99);
    expect(clampQuantity(5, 0)).toBe(1);
  });

  it("strikes the original price only when it is higher, and locks free items", () => {
    expect(isDiscounted({ unit_price_sgd: 1.8, unit_mrp_sgd: 2.5 })).toBe(true);
    expect(isDiscounted({ unit_price_sgd: 0.45, unit_mrp_sgd: 0.45 })).toBe(false);
    expect(isDiscounted({ unit_price_sgd: null, unit_mrp_sgd: 2.5 })).toBe(false);
    expect(isDiscounted({ unit_price_sgd: 1.8, unit_mrp_sgd: null })).toBe(false);
    expect(isLocked({ unit_mrp_sgd: null })).toBe(false);
    expect(isLocked({ unit_mrp_sgd: 0 })).toBe(true);
    expect(isLocked({ unit_mrp_sgd: 2, is_free: true })).toBe(true);
    expect(isLocked({ unit_mrp_sgd: 2 })).toBe(false);
  });
});
