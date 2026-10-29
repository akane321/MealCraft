import { describe, expect, it } from "vitest";

import {
  CART_CHANGED_NOTE,
  alreadyAddedNote,
  budgetWarning,
  cartChanged,
  cartErrorMessage,
  cartPayload,
  cartStateLabels,
  priceChanges,
  problemLabel,
  problemLines,
  readyLines,
  reportableReply,
  resultNote,
  summarizeResults,
  summaryLine,
  swapSentence,
  tripKey,
} from "../app/lib/fairprice-cart";
import type { FairPriceCartLine, FairPriceCartPrepare, FairPriceCartResult, FairPriceCartTrip } from "../app/types/meal-plan";

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
    for (const code of ["not_logged_in", "cart_unreadable", "request_refused", "unexpected_response", "invalid_request", "busy", "no_extension", "timeout"] as const) {
      expect(cartErrorMessage(code).length).toBeGreaterThan(20);
    }
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

  it("warns that adding a sent trip again doubles the quantities", () => {
    expect(alreadyAddedNote(null)).toBeNull();
    expect(alreadyAddedNote(undefined)).toBeNull();
    expect(alreadyAddedNote(trip({}))).toBe("Already added on 29 Oct. Adding again adds these quantities a second time.");
    expect(alreadyAddedNote(trip({ status: "ordered", ordered_at: "2026-10-30T01:00:00Z" }))).toMatch(/^Already added on 29 Oct\./);
  });

  it("dates by Singapore time and names each trip of a two-trip plan", () => {
    // 17:00 UTC on the 29th is 01:00 on the 30th in Singapore.
    const labels = cartStateLabels({ 2: trip({ sent_at: "2026-10-29T17:00:00Z" }), 1: trip({ status: "ordered", ordered_at: "2026-10-29T02:00:00Z" }) });
    expect(labels.map(l => l.label)).toEqual(["Trip 1: Ordered on 29 Oct", "Trip 2: In your FairPrice cart on 30 Oct"]);
  });
});
