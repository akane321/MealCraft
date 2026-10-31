import type {
  FairPriceCartAddLine,
  FairPriceCartLine,
  FairPriceCartPrepare,
  FairPriceCartResult,
  FairPriceCartState,
  FairPriceExtensionError,
  FairPriceExtensionReply,
  FairPriceLiveCart,
  FairPriceResultStatus,
} from "~/types/meal-plan";
import { formatSgd } from "./home-surface";

export const FAIRPRICE_LOGIN_URL = "https://www.fairprice.com.sg/login";
export const FAIRPRICE_CHECKOUT_URL = "https://www.fairprice.com.sg/checkout";
/** The small window the login opens in; the password is typed only there. */
export const LOGIN_WINDOW_FEATURES = "popup=yes,width=520,height=720";
/** How long the panel waits after the last − / + press before it tells FairPrice the quantity. */
export const QUANTITY_DEBOUNCE_MS = 500;
/** How long after the window regains focus (or becomes visible) the panel waits before it reads the cart again. */
export const RETURN_REFRESH_MS = 300;

/** The key a shopping trip has in the plan's stored cart state: a plan's only trip is "1". */
export const tripKey = (trip: number | null): string => String(trip ?? 1);

/** Lines the extension can put in the cart: live product id, in stock. */
export const readyLines = (lines: FairPriceCartLine[]): FairPriceCartLine[] =>
  lines.filter(line => line.status === "ready" && line.cart_item_id);

/** The ids of the products already in the person's cart. */
export const cartIds = (cart: FairPriceLiveCart | null | undefined): Set<string> =>
  new Set((cart?.items ?? []).map(item => item.cart_item_id));

/** Ready lines whose product is already in the cart (same cart_item_id). */
export const linesInCart = (lines: FairPriceCartLine[], inCart: Set<string>): FairPriceCartLine[] =>
  readyLines(lines).filter(line => inCart.has(line.cart_item_id!));

/** What the extension is asked to add: the ready lines, except those already in the cart unless `again`. */
export const cartPayload = (lines: FairPriceCartLine[], inCart: Set<string> = new Set(), again = false): FairPriceCartAddLine[] =>
  readyLines(lines)
    .filter(line => again || !inCart.has(line.cart_item_id!))
    .map(line => ({ line_key: line.line_key, cart_item_id: line.cart_item_id!, quantity: line.quantity }));

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

/** Cold Storage lines are links, not cart items; the panel says so when the trip has any. */
export const COLD_STORAGE_NOTE = "Cold Storage items stay on your list with links; buy them on coldstorage.com.sg.";

/** What the trip's lines at other stores cost: they count toward the budget though the cart does not take them. */
export const otherStoresTotal = (prepare: FairPriceCartPrepare): number =>
  Math.round((prepare.other_stores ?? []).reduce((sum, store) => sum + store.purchase_total_sgd, 0) * 100) / 100;

/** The budget warning of a prepared trip, or null within budget (or without one). The plan is never changed. */
export function budgetWarning(prepare: FairPriceCartPrepare): string | null {
  if (!prepare.over_budget || prepare.budget_sgd == null) return null;
  const other = otherStoresTotal(prepare);
  const total = Math.round((prepare.projected_total_sgd + other) * 100) / 100;
  const over = formatSgd(Math.round((total - prepare.budget_sgd) * 100) / 100);
  const prices = other > 0 ? `At today's FairPrice prices, plus ${formatSgd(other)} from Cold Storage,` : "At today's FairPrice prices";
  return `${prices} this trip comes to ${formatSgd(total)}, ${over} over your ${formatSgd(prepare.budget_sgd)} budget. Your plan is not changed.`;
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

/** One reported line in the panel. `quantity` is what this add put in the cart; `asked` is what the list needed. */
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

/** A fee as FairPrice's cart shows it: "Free" when waived (0 against a usual fee above 0), S$0.00 when there is no fee at all, else the amount; the usual fee is struck through when higher. */
export function feeParts(current: number, standard: number): { text: string; was: string | null } {
  const was = standard > current ? formatSgd(standard) : null;
  return { text: current === 0 && standard > 0 ? "Free" : formatSgd(current), was };
}

/** An amount FairPrice's reply may leave out: "—" then. */
export const sgdOrDash = (value: number | null | undefined): string => (value == null ? "—" : formatSgd(value));

/** Quantity a stepper may take: a whole number from 1 to the item's maximum (0 is the remove button). */
export const clampQuantity = (quantity: number, max: number): number => Math.min(Math.max(1, Math.round(quantity)), Math.max(1, max));

/** True when the original price should show struck through. */
export const isDiscounted = (item: { unit_price_sgd: number | null; unit_mrp_sgd: number | null }): boolean =>
  item.unit_price_sgd != null && item.unit_mrp_sgd != null && item.unit_mrp_sgd - item.unit_price_sgd >= 0.005;

/** Free items the server adds can't be changed. */
export const isLocked = (item: { unit_mrp_sgd: number | null; is_free?: boolean }): boolean => item.is_free === true || item.unit_mrp_sgd === 0;

/** The sentence the assistant already reads as "this ingredient is not available": it finds the dishes that use it. */
export const swapSentence = (line: Pick<FairPriceCartLine, "ingredient_display_name">): string =>
  `I can't buy ${line.ingredient_display_name} this week`;

/** Chrome's own words for "no extension is listening there"; any other `lastError` is an extension that stopped on the way. */
const NO_EXTENSION_ERROR = /Receiving end does not exist|Could not establish connection/;
export const runtimeErrorCode = (message: string | undefined): FairPriceExtensionError =>
  NO_EXTENSION_ERROR.test(message ?? "") ? "no_extension" : "interrupted";

/** What to tell the person when the extension (or the page's wait for it) failed. A refused, late or unreadable
 *  answer can come after the write, so those ask the person to look at the cart before trying again. */
export function cartErrorMessage(code: FairPriceExtensionError): string {
  switch (code) {
    case "no_extension": return "The MealCraft FairPrice cart extension isn't installed in this browser.";
    case "not_logged_in": return "You're not logged in to FairPrice. Log in at fairprice.com.sg in this browser, then try again.";
    case "cart_unreadable": return "The extension couldn't read your current FairPrice cart, so it changed nothing. Try again in a minute.";
    case "request_refused": return "FairPrice refused the request, possibly with a check to confirm you're a person. Open fairprice.com.sg, complete any check, then check your FairPrice cart before trying again, or use the product links below.";
    case "invalid_request": return "The extension refused the list as invalid, so nothing was sent. Try again, or use the product links below.";
    case "not_in_cart": return "That item is no longer in your FairPrice cart";
    case "interrupted": return "The extension stopped before answering. MealCraft is reading your FairPrice cart again; check it before trying again, so nothing is added twice.";
    case "busy": return "Another add to your FairPrice cart is still running. Wait for it to finish, then check your cart before trying again.";
    case "timeout": return "The extension didn't answer in time. Check your FairPrice cart before trying again, so nothing is added twice, or use the product links below.";
    default: return "The extension sent back something MealCraft didn't expect. Check your FairPrice cart before trying again, so nothing is added twice, or use the product links below.";
  }
}

/** The same, for a read of the cart: nothing was written, so the person is only asked to try again. */
export function readErrorMessage(code: FairPriceExtensionError): string {
  switch (code) {
    case "request_refused": return "FairPrice refused to show your cart, possibly with a check to confirm you're a person. Open fairprice.com.sg, complete any check, then try again.";
    case "timeout": return "The extension didn't answer in time while reading your cart. Try again.";
    case "unexpected_response": return "The extension sent back something MealCraft didn't expect when reading your cart. Try again.";
    case "interrupted": return "The extension stopped before it could read your cart. Try again.";
    default: return cartErrorMessage(code);
  }
}
