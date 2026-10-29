// Service worker of the MealCraft FairPrice cart extension (docs/design/fairprice-cart.md).
// Takes messages from the MealCraft page only, then runs cart-core.js inside a logged-in
// www.fairprice.com.sg tab. The FairPrice session never leaves that tab.
importScripts("cart-core.js");

const ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"];
const FAIRPRICE_HOME = "https://www.fairprice.com.sg/";
const TAB_LOAD_TIMEOUT_MS = 30000;

// One add at a time: a second message while one runs gets "busy".
let adding = false;

function senderAllowed(sender) {
  try {
    return ALLOWED_ORIGINS.includes(new URL(sender && sender.url).origin);
  } catch {
    return false;
  }
}

function waitForLoad(tabId) {
  return new Promise((resolve, reject) => {
    const done = (fn, arg) => {
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(onUpdated);
      fn(arg);
    };
    const onUpdated = (id, info) => {
      if (id === tabId && info.status === "complete") done(resolve);
    };
    const timer = setTimeout(() => done(reject, new Error("tab load timeout")), TAB_LOAD_TIMEOUT_MS);
    chrome.tabs.onUpdated.addListener(onUpdated);
    // The tab may have finished loading before the listener was added.
    chrome.tabs.get(tabId).then((tab) => {
      if (tab.status === "complete") done(resolve);
    }, (err) => done(reject, err));
  });
}

async function fairpriceTab() {
  const open = globalThis.__mealcraftFairPriceCart.pickTab(await chrome.tabs.query({ url: "https://www.fairprice.com.sg/*" }));
  if (open) return open.id;
  const created = await chrome.tabs.create({ url: FAIRPRICE_HOME, active: false });
  await waitForLoad(created.id);
  return created.id;
}

async function addToCart(message) {
  const tabId = await fairpriceTab();
  const target = { tabId };
  await chrome.scripting.executeScript({ target, world: "MAIN", files: ["cart-core.js"] });
  const [injection] = await chrome.scripting.executeScript({
    target,
    world: "MAIN",
    func: (lines, dryRun) => globalThis.__mealcraftFairPriceCart.addToCart(lines, { dryRun }),
    args: [message.lines, message.dry_run === true],
  });
  return globalThis.__mealcraftFairPriceCart.checkInjected(injection && injection.result, message.lines, message.dry_run === true);
}

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (!senderAllowed(sender) || !message) return false;
  if (message.type === "ping") {
    sendResponse({ ok: true, version: chrome.runtime.getManifest().version });
    return false;
  }
  if (message.type !== "add_to_cart") return false;
  if (!globalThis.__mealcraftFairPriceCart.validateRequest(message)) {
    sendResponse({ ok: false, error: "invalid_request" });
    return false;
  }
  if (adding) {
    sendResponse({ ok: false, error: "busy" });
    return false;
  }
  adding = true;
  addToCart(message)
    .catch((e) => ({ ok: false, error: "unexpected_response", detail: String((e && e.message) || e).slice(0, 200) }))
    .then((answer) => {
      adding = false;
      sendResponse(answer);
    });
  return true;
});
