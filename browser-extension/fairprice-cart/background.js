// Service worker of the MealCraft FairPrice cart extension (docs/design/fairprice-cart.md).
// Takes messages from the MealCraft page only. It opens no FairPrice tab: it reads the person's
// auth_token cookie and calls FairPrice's cart API itself (cart-core.js). The token, the address
// and the account id never leave this worker.
importScripts("cart-core.js");

const core = globalThis.__mealcraftFairPriceCart;
const ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"];
const FAIRPRICE = "https://www.fairprice.com.sg";
const CUSTOMER_KEY = "fairprice_customer";

// One write at a time: a second write message while one runs gets "busy". get_cart may run alongside.
let writing = false;

// The account id is kept for the browser session only; cart-core ties it to the current login.
const cache = {
  get: async () => (await chrome.storage.session.get(CUSTOMER_KEY))[CUSTOMER_KEY],
  set: (value) => chrome.storage.session.set({ [CUSTOMER_KEY]: value }),
};

function senderAllowed(sender) {
  try {
    return ALLOWED_ORIGINS.includes(new URL(sender && sender.url).origin);
  } catch {
    return false;
  }
}

async function readToken() {
  try {
    const cookie = await chrome.cookies.get({ url: FAIRPRICE, name: "auth_token" });
    return cookie ? cookie.value : null;
  } catch {
    return null;
  }
}

async function handle(message) {
  const opts = { token: await readToken(), cache };
  if (message.type === "get_cart") return core.getCart(opts);
  if (message.type === "set_quantity") return core.setQuantity(message.cart_item_id, message.quantity, opts);
  return core.addToCart(message.lines, { ...opts, dryRun: message.dry_run === true });
}

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (!senderAllowed(sender) || !message) return false;
  if (message.type === "ping") {
    sendResponse({ ok: true, version: chrome.runtime.getManifest().version });
    return false;
  }
  if (message.type !== "get_cart" && message.type !== "add_to_cart" && message.type !== "set_quantity") return false;
  if (!core.validateMessage(message)) {
    sendResponse({ ok: false, error: "invalid_request" });
    return false;
  }
  const isWrite = message.type !== "get_cart";
  if (isWrite && writing) {
    sendResponse({ ok: false, error: "busy" });
    return false;
  }
  if (isWrite) writing = true;
  handle(message)
    .catch((e) => ({ ok: false, error: "unexpected_response", detail: String((e && e.message) || e).slice(0, 200) }))
    .then((answer) => {
      if (isWrite) writing = false;
      sendResponse(core.checkAnswer(message, answer));
    });
  return true;
});
