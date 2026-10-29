import type {
  FairPriceCartAddLine,
  FairPriceCartLine,
  FairPriceCartPrepare,
  FairPriceCartResult,
  FairPriceCartState,
  FairPriceCartTrip,
  FairPriceExtensionError,
  FairPriceExtensionReply,
  FairPriceResultStatus,
} from "~/types/meal-plan";
import { formatSgd } from "./home-surface";

export const FAIRPRICE_CART_URL = "https://www.fairprice.com.sg/cart";

/** The key a shopping trip has in the plan's stored cart state: a plan's only trip is "1". */
export const tripKey = (trip: number | null): string => String(trip ?? 1);

/** Lines the extension can put in the cart: live product id, in stock. */
export const readyLines = (lines: FairPriceCartLine[]): FairPriceCartLine[] =>
  lines.filter(line => line.status === "ready" && line.cart_item_id);

/** What the extension is asked to add. */
export const cartPayload = (lines: FairPriceCartLine[]): FairPriceCartAddLine[] =>
  readyLines(lines).map(line => ({ line_key: line.line_key, cart_item_id: line.cart_item_id!, quantity: line.quantity }));

/** Lines that cannot go in the cart as planned; a line the pantry covers (not bought) is no problem. */
export const problemLines = (lines: FairPriceCartLine[]): FairPriceCartLine[] =>
  lines.filter(line => line.status !== "ready" && line.status !== "not_bought");

export function problemLabel(line: FairPriceCartLine): string {
  switch (line.status) {
    case "out_of_stock": return "Out of stock at FairPrice now";
    case "not_found": return "FairPrice no longer lists this product";
    case "no_product": return "No FairPrice product chosen for this line";
    default: return "";
  }
}

export interface PriceChange {
  line: FairPriceCartLine;
  planned: number;
  live: number;
  direction: "up" | "down";
}

/** Lines whose live unit price is not the one the plan was priced with. */
export function priceChanges(lines: FairPriceCartLine[]): PriceChange[] {
  const changes: PriceChange[] = [];
  for (const line of lines) {
    const { planned_price_sgd: planned, live_price_sgd: live } = line;
    if (planned == null || live == null || Math.abs(live - planned) < 0.005) continue;
    changes.push({ line, planned, live, direction: live > planned ? "up" : "down" });
  }
  return changes;
}

/** The budget warning of a prepared trip, or null within budget (or without one). The plan is never changed. */
export function budgetWarning(prepare: FairPriceCartPrepare): string | null {
  if (!prepare.over_budget || prepare.budget_sgd == null) return null;
  const over = formatSgd(Math.round((prepare.projected_total_sgd - prepare.budget_sgd) * 100) / 100);
  return `At today's FairPrice prices this trip comes to ${formatSgd(prepare.projected_total_sgd)}, ${over} over your ${formatSgd(prepare.budget_sgd)} budget. Your plan is not changed.`;
}

export interface ResultCounts {
  added: number;
  reduced: number;
  out_of_stock: number;
  failed: number;
}

export function summarizeResults(results: FairPriceCartResult[]): ResultCounts {
  const counts: ResultCounts = { added: 0, reduced: 0, out_of_stock: 0, failed: 0 };
  for (const result of results) counts[result.status] += 1;
  return counts;
}

/** "3 added, 1 reduced, 1 out of stock"; only what happened. */
export function summaryLine(counts: ResultCounts): string {
  const parts = [
    counts.added && `${counts.added} added`,
    counts.reduced && `${counts.reduced} reduced`,
    counts.out_of_stock && `${counts.out_of_stock} out of stock`,
    counts.failed && `${counts.failed} failed`,
  ].filter(Boolean);
  return parts.join(", ") || "Nothing was added";
}

/** One reported line in the dialog. `quantity` is what this add put in the cart; `asked` is what the list needed. */
export function resultNote(result: FairPriceCartResult, asked?: number): string {
  switch (result.status) {
    case "added": return `${result.quantity} added to your cart`;
    case "reduced": return `FairPrice took ${result.quantity} of ${asked ?? "the amount you asked for"}. Add the rest on FairPrice.`;
    case "out_of_stock": return "Out of stock at FairPrice, so it wasn't added";
    default: return "FairPrice didn't accept it. Add it on FairPrice yourself.";
  }
}

const REPORTABLE: FairPriceResultStatus[] = ["added", "reduced", "out_of_stock", "failed"];

/** A reply the page may report to the plan. A dry run (or any result that is not one of the four statuses) is not one. */
export function reportableReply(reply: FairPriceExtensionReply): FairPriceExtensionReply {
  if (!reply.ok) return reply;
  const fine = !reply.dry_run && Array.isArray(reply.results) && reply.results.every(result => REPORTABLE.includes(result.status));
  return fine ? reply : { ok: false, error: "unexpected_response" };
}

export const CART_CHANGED_NOTE = "Other items already in your FairPrice cart changed. Check your cart.";

/** True when the extension saw other items of the cart differ after its write. */
export const cartChanged = (reply: FairPriceExtensionReply): boolean => Array.isArray(reply.cart_changed) && reply.cart_changed.length > 0;

/** The warning for a trip already sent (in the cart or ordered), or null for a trip never sent. */
export const alreadyAddedNote = (trip: FairPriceCartTrip | null | undefined): string | null =>
  trip ? `Already added on ${shortDate(trip.sent_at)}. Adding again adds these quantities a second time.` : null;

/** A date in Singapore, as "29 Oct". */
export const shortDate = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-SG", { day: "numeric", month: "short", timeZone: "Asia/Singapore" });

export interface CartStateLabel {
  key: string;
  label: string;
  tone: "ok" | "warn" | "info";
}

/**
 * Where each trip's cart stands, for the groceries tab: "In your FairPrice cart on 29 Oct", "Ordered on 30 Oct", or
 * (the list changed after it was sent) "List changed since it was sent". A plan with two trips names each one.
 */
export function cartStateLabels(state: FairPriceCartState | null | undefined): CartStateLabel[] {
  const entries = Object.entries(state ?? {}).sort(([a], [b]) => a.localeCompare(b));
  return entries.map(([key, trip]) => {
    const prefix = entries.length > 1 ? `Trip ${key}: ` : "";
    if (trip.status === "ordered") return { key, tone: "ok", label: `${prefix}Ordered on ${shortDate(trip.ordered_at ?? trip.sent_at)}` };
    if (trip.stale) return { key, tone: "warn", label: `${prefix}List changed since it was sent` };
    return { key, tone: "info", label: `${prefix}In your FairPrice cart on ${shortDate(trip.sent_at)}` };
  });
}

/** The sentence the assistant already reads as "this ingredient is not available": it finds the dishes that use it. */
export const swapSentence = (line: Pick<FairPriceCartLine, "ingredient_display_name">): string =>
  `I can't buy ${line.ingredient_display_name} this week`;

/** What to tell the person when the extension (or the page's wait for it) failed. A refused, late or unreadable
 *  answer can come after the write, so those ask the person to look at the cart before trying again. */
export function cartErrorMessage(code: FairPriceExtensionError): string {
  switch (code) {
    case "no_extension": return "The MealCraft FairPrice cart extension isn't installed in this browser.";
    case "not_logged_in": return "You're not logged in to FairPrice. Log in at fairprice.com.sg in this browser, then try again.";
    case "cart_unreadable": return "The extension couldn't read your current FairPrice cart, so it added nothing. Try again in a minute.";
    case "request_refused": return "FairPrice refused the request, possibly with a check to confirm you're a person. Open fairprice.com.sg, complete any check, then check your FairPrice cart before trying again, or use the product links below.";
    case "invalid_request": return "The extension refused the list as invalid, so nothing was sent. Try again, or use the product links below.";
    case "busy": return "Another add to your FairPrice cart is still running. Wait for it to finish, then check your cart before trying again.";
    case "timeout": return "The extension didn't answer in time. Check your FairPrice cart before trying again, so nothing is added twice, or use the product links below.";
    default: return "The extension sent back something MealCraft didn't expect. Check your FairPrice cart before trying again, so nothing is added twice, or use the product links below.";
  }
}
