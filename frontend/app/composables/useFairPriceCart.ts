import { reportableReply } from "~/lib/fairprice-cart";
import type {
  FairPriceCartAddLine,
  FairPriceCartPrepare,
  FairPriceCartReportBody,
  FairPriceCartState,
  FairPriceExtensionError,
  FairPriceExtensionReply,
} from "~/types/meal-plan";

// Only a page the extension lists as externally connectable gets `chrome.runtime.sendMessage`; the type is the part used.
interface ChromeRuntime {
  sendMessage?: (id: string, message: unknown, callback: (reply?: unknown) => void) => void;
  lastError?: { message?: string };
}

const PING_TIMEOUT_MS = 1500;
// The extension may open a FairPrice tab, wait for it to load (up to 30 s) and then read and write the cart.
const ADD_TIMEOUT_MS = 90_000;
const ERRORS: FairPriceExtensionError[] = ["not_logged_in", "cart_unreadable", "request_refused", "unexpected_response", "invalid_request", "busy"];

export function useFairPriceCart() {
  const config = useRuntimeConfig();
  const apiFetch = useApiFetch();
  const base = (planId: number) => `${config.public.apiBase}/api/plans/${planId}/fairprice-cart`;
  const extensionId = String(config.public.fairpriceCartExtensionId);

  const prepare = (planId: number, shoppingTrip: number | null) =>
    apiFetch<FairPriceCartPrepare>(`${base(planId)}/prepare`, { method: "POST", body: { shopping_trip: shoppingTrip } });

  const report = (planId: number, body: FairPriceCartReportBody) =>
    apiFetch<FairPriceCartState>(`${base(planId)}/report`, { method: "POST", body });

  const markOrdered = (planId: number, shoppingTrip: number | null) =>
    apiFetch<FairPriceCartState>(`${base(planId)}/ordered`, { method: "POST", body: { shopping_trip: shoppingTrip } });

  /** One message to the extension. It never throws: a missing extension, a Chrome error or a wait too long is a reply with `ok: false`. */
  function send(message: object, timeoutMs: number): Promise<FairPriceExtensionReply> {
    const runtime = (globalThis as { chrome?: { runtime?: ChromeRuntime } }).chrome?.runtime;
    if (!runtime?.sendMessage) return Promise.resolve({ ok: false, error: "no_extension" });
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve({ ok: false, error: "timeout" }), timeoutMs);
      const done = (reply: FairPriceExtensionReply) => {
        clearTimeout(timer);
        resolve(reply);
      };
      try {
        runtime.sendMessage!(extensionId, message, (reply) => {
          // Read at once: Chrome clears it after the callback. "Receiving end does not exist" is an extension that isn't there.
          if (runtime.lastError) return done({ ok: false, error: "no_extension" });
          const given = reply as FairPriceExtensionReply | undefined;
          if (!given || typeof given !== "object" || typeof given.ok !== "boolean") return done({ ok: false, error: "unexpected_response" });
          done(given.ok ? given : { ok: false, error: given.error && ERRORS.includes(given.error) ? given.error : "unexpected_response" });
        });
      }
      catch {
        done({ ok: false, error: "no_extension" });
      }
    });
  }

  /** True when the extension answers a ping. */
  async function detectExtension(): Promise<boolean> {
    return (await send({ type: "ping" }, PING_TIMEOUT_MS)).ok;
  }

  async function addToCart(lines: FairPriceCartAddLine[]): Promise<FairPriceExtensionReply> {
    const reply = await send({ type: "add_to_cart", lines }, ADD_TIMEOUT_MS);
    return reportableReply(reply);
  }

  return { prepare, report, markOrdered, detectExtension, addToCart };
}
