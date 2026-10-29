<script setup lang="ts">
import {
  CART_CHANGED_NOTE,
  FAIRPRICE_CHECKOUT_URL,
  FAIRPRICE_LOGIN_URL,
  LOGIN_WINDOW_FEATURES,
  QUANTITY_DEBOUNCE_MS,
  RETURN_REFRESH_MS,
  budgetWarning,
  cartChanged,
  cartErrorMessage,
  cartIds,
  cartPayload,
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
  resultNote,
  sgdOrDash,
  summarizeResults,
  summaryLine,
  swapSentence,
  tripKey,
} from "~/lib/fairprice-cart";
import { formatSgd } from "~/lib/home-surface";
import type {
  FairPriceCartAddLine,
  FairPriceCartLine,
  FairPriceCartPrepare,
  FairPriceCartReportBody,
  FairPriceCartResult,
  FairPriceCartState,
  FairPriceExtensionError,
  FairPriceExtensionReply,
  FairPriceLiveCart,
} from "~/types/meal-plan";
import type { PricingMode } from "~/types/recommendation";

// The person's real FairPrice cart, inside MealCraft (docs/design/fairprice-cart.md, "Panel"): read and changed through
// the browser extension; they check out and pay on FairPrice. The plan is never changed here (a "Swap" only fills the
// composer, to be sent as a request). `cartState` is what the plan records per trip.
const props = defineProps<{ planId: number; pricingMode: PricingMode; trips: number; cartState?: FairPriceCartState | null }>();
const emit = defineEmits<{ close: []; state: [state: FairPriceCartState]; ask: [text: string] }>();

type Setup = "checking" | "missing" | "login" | "ready";
type ListStep = "loading" | "ready" | "error";
const SWAPPABLE = new Set(["out_of_stock", "not_found"]);
// A refused, late or unreadable answer to a write may come after the write: read the cart again to see what is there.
const AMBIGUOUS = new Set(["request_refused", "timeout", "unexpected_response", "interrupted"]);

const cart = useFairPriceCart();
const overlay = ref<HTMLElement | null>(null);
// Closing, swapping or changing trip while something is still being saved would hide or drop it: it is refused (a
// pending quantity edit is committed at once) and the panel says so; the person leaves once it is saved.
function close() {
  if (idle()) emit("close");
}
useDialog(overlay, close);

const errorDetail = (error: unknown) => (error as { data?: { detail?: string } }).data?.detail;

// ---- The person's cart ----
const setup = ref<Setup>("checking");
const liveCart = ref<FairPriceLiveCart | null>(null);
const cartLoading = ref(false);
const cartProblem = ref<string | null>(null);
const broken = reactive<Record<string, boolean>>({});
const loginNote = ref<string | null>(null);
// The cart on screen may differ from FairPrice's (a write's answer was lost or a row write failed): adding waits
// for a successful read, because the add sends the lines the page thinks are missing.
const cartStale = ref(false);
const canAdd = computed(() => setup.value === "ready" && liveCart.value !== null && !cartStale.value);

// One request at a time, reads and writes alike: the extension refuses an overlapping write, and a read that started
// before a write must not be applied after the write's answer.
let chain: Promise<unknown> = Promise.resolve();
function enqueue<T>(job: () => Promise<T>): Promise<T> {
  const run = chain.then(job);
  chain = run.catch(() => undefined);
  return run;
}

let reads = 0;
/** Reads the cart; returns the error code, or null when the cart was read. */
async function refreshCart(): Promise<FairPriceExtensionError | null> {
  reads += 1;
  cartLoading.value = true;
  const reply = await enqueue(() => cart.getCart());
  reads -= 1;
  cartLoading.value = reads > 0;
  if (reply.ok && reply.cart) {
    liveCart.value = reply.cart;
    cartProblem.value = null;
    loginNote.value = null;
    cartStale.value = false;
    setup.value = "ready";
    return null;
  }
  const code = reply.error ?? "unexpected_response";
  if (code === "no_extension") setup.value = "missing";
  else if (code === "not_logged_in") {
    liveCart.value = null;
    cartProblem.value = null;
    setup.value = "login";
  }
  else {
    cartProblem.value = readErrorMessage(code);
    if (!liveCart.value) setup.value = "ready";
  }
  return code;
}

async function connect() {
  setup.value = "checking";
  cartProblem.value = null;
  if (!(await cart.detectExtension())) {
    setup.value = "missing";
    return;
  }
  await refreshCart();
}

// The password is typed only in FairPrice's own window.
function openLogin() {
  loginNote.value = null;
  if (!window.open(FAIRPRICE_LOGIN_URL, "fairprice-login", LOGIN_WINDOW_FEATURES)) loginNote.value = `Allow pop-ups for ${location.host}, then try again`;
}

async function loggedIn() {
  loginNote.value = null;
  if ((await refreshCart()) === "not_logged_in") loginNote.value = "Still not logged in to FairPrice";
}

// ---- This week's list ----
const sample = props.pricingMode === "fixture";
const listStep = ref<ListStep>(sample ? "ready" : "loading");
const trip = ref<number | null>(props.trips > 1 ? 1 : null);
const prepared = ref<FairPriceCartPrepare | null>(null);
const listProblem = ref<string | null>(null);
let loadId = 0;

async function load() {
  if (sample) return;
  const id = ++loadId;
  listStep.value = "loading";
  listProblem.value = null;
  prepared.value = null;
  try {
    const loaded = await cart.prepare(props.planId, trip.value);
    if (id !== loadId) return;
    prepared.value = loaded;
    listStep.value = "ready";
  }
  catch (error) {
    if (id !== loadId) return;
    listProblem.value = errorDetail(error) || "Today's FairPrice prices couldn't be checked.";
    listStep.value = "error";
  }
}

const adding = ref(false);
const results = ref<FairPriceCartResult[]>([]);
const addProblem = ref<string | null>(null);
const changed = ref(false);
const confirmAgain = ref(false);
const saveNote = ref<string | null>(null);
// The report the plan couldn't save yet; saving it again never re-sends the list to FairPrice.
const unsaved = ref<FairPriceCartReportBody | null>(null);
const saving = ref(false);
const ordering = ref(false);

function chooseTrip(next: number) {
  if (next === trip.value || !idle()) return;
  trip.value = next;
  results.value = [];
  addProblem.value = null;
  changed.value = false;
  confirmAgain.value = false;
  saveNote.value = null;
  unsaved.value = null;
  void load();
}

const previous = computed(() => props.cartState?.[tripKey(trip.value)] ?? null);
const ordered = computed(() => previous.value?.status === "ordered");

const lines = computed(() => prepared.value?.lines ?? []);
const ready = computed(() => readyLines(lines.value));
const problems = computed(() => problemLines(lines.value));
const changes = computed(() => priceChanges(lines.value));
const warning = computed(() => (prepared.value ? budgetWarning(prepared.value) : null));
const inCart = computed(() => cartIds(liveCart.value));
const already = computed(() => linesInCart(lines.value, inCart.value));
const toAdd = computed(() => cartPayload(lines.value, inCart.value));
const planIds = computed(() => new Set(lines.value.map(line => line.cart_item_id).filter(Boolean)));
const links = computed(() => ready.value.filter(line => line.product_url));
const lineOf = (key: string): FairPriceCartLine | undefined => lines.value.find(line => line.line_key === key);
const left = computed(() => results.value.filter(result => result.status !== "added"));
const fees = computed(() => {
  const totals = liveCart.value?.totals;
  return totals
    ? [
        { label: "Delivery", ...feeParts(totals.delivery_sgd, totals.delivery_standard_sgd) },
        { label: "Service fee", ...feeParts(totals.service_fee_sgd, totals.service_fee_standard_sgd) },
      ]
    : [];
});

function add(again = false) {
  const current = prepared.value;
  if (!current || adding.value || !canAdd.value) return;
  const payload = cartPayload(current.lines, inCart.value, again);
  if (payload.length) void send(current, payload);
}

async function send(current: FairPriceCartPrepare, payload: FairPriceCartAddLine[]) {
  adding.value = true;
  addProblem.value = null;
  confirmAgain.value = false;
  results.value = [];
  const reply = await enqueue(() => cart.addToCart(payload));
  adding.value = false;
  if (!reply.ok || !reply.results) {
    afterFailure(reply, message => (addProblem.value = message));
    return;
  }
  if (reply.cart) liveCart.value = reply.cart;
  results.value = reply.results;
  changed.value = cartChanged(reply);
  await saveReport({ shopping_trip: current.shopping_trip, fingerprint: current.fingerprint, results: reply.results });
}

// A failed write, said in plain words; a late or unreadable answer may still have written, and a failed row write
// means the cart on screen is not FairPrice's, so the cart is read again (adding waits for that read).
function afterFailure(reply: FairPriceExtensionReply, say: (message: string) => void, row = false) {
  const code = reply.error ?? "unexpected_response";
  if (code === "no_extension") setup.value = "missing";
  else if (code === "not_logged_in") {
    liveCart.value = null;
    setup.value = "login";
  }
  say(cartErrorMessage(code));
  if (code !== "no_extension" && (row || AMBIGUOUS.has(code))) {
    cartStale.value = true;
    void refreshCart();
  }
}

async function saveReport(body: FairPriceCartReportBody) {
  saving.value = true;
  try {
    emit("state", await cart.report(props.planId, body));
    unsaved.value = null;
    saveNote.value = null;
  }
  catch {
    unsaved.value = body;
    saveNote.value = "Your FairPrice cart was updated, but MealCraft couldn't save that, so the plan won't show it yet.";
  }
  finally {
    saving.value = false;
  }
}

async function markOrdered() {
  ordering.value = true;
  try {
    emit("state", await cart.markOrdered(props.planId, trip.value));
    saveNote.value = null;
  }
  catch (error) {
    saveNote.value = errorDetail(error) || "MealCraft couldn't save that you checked out. Try again.";
  }
  finally {
    ordering.value = false;
  }
}

// The words go to the page, which closes this and puts them in the composer; nothing about the plan changes until
// the request is sent and its preview confirmed.
function swap(line: FairPriceCartLine) {
  if (idle()) emit("ask", swapSentence(line));
}

// ---- Rows ----
// A quantity the person has set but FairPrice has not confirmed yet; dropping it is the rollback.
const pending = reactive<Record<string, number>>({});
const removing = reactive<Record<string, boolean>>({});
const rowError = reactive<Record<string, string>>({});
const drop = (record: Record<string, unknown>, id: string) => Reflect.deleteProperty(record, id);
const timers = new Map<string, ReturnType<typeof setTimeout>>();

const isSaving = (id: string) => removing[id] === true || pending[id] !== undefined;
// A quantity is pending from the press until FairPrice answers; a remove from the press until its answer.
const rowBusy = computed(() => Object.keys(pending).length > 0 || Object.keys(removing).length > 0);
const busy = computed(() => adding.value || saving.value || ordering.value || rowBusy.value);
const leaveNote = ref<string | null>(null);
watch(busy, (now) => {
  if (!now) leaveNote.value = null;
});

/** True when nothing is being saved. Otherwise commits the quantity edits waiting out their debounce, says so, and is false. */
function idle(): boolean {
  if (!busy.value) return true;
  commitWaiting();
  leaveNote.value = "Saving your changes…";
  return false;
}

function commitWaiting() {
  for (const [id, timer] of [...timers]) {
    clearTimeout(timer);
    void commit(id);
  }
}

const quantityOf = (item: { cart_item_id: string; quantity: number }) => pending[item.cart_item_id] ?? item.quantity;
const totalOf = (item: { cart_item_id: string; quantity: number; unit_price_sgd: number | null; line_total_sgd: number | null }) =>
  pending[item.cart_item_id] === undefined || item.unit_price_sgd == null
    ? item.line_total_sgd
    : Math.round(pending[item.cart_item_id]! * item.unit_price_sgd * 100) / 100;

function step(item: { cart_item_id: string; quantity: number; max_quantity: number }, delta: number) {
  const id = item.cart_item_id;
  const next = clampQuantity(quantityOf(item) + delta, item.max_quantity);
  if (next === quantityOf(item)) return;
  pending[id] = next;
  drop(rowError, id);
  clearTimeout(timers.get(id));
  timers.set(id, setTimeout(() => void commit(id), QUANTITY_DEBOUNCE_MS));
}

async function commit(id: string) {
  timers.delete(id);
  const want = pending[id];
  if (want === undefined) return;
  // Checked when its turn comes: an earlier write for this item may have changed the cart since the press.
  const reply = await enqueue(async () =>
    liveCart.value?.items.find(item => item.cart_item_id === id)?.quantity === want ? null : cart.setQuantity(id, want));
  if (reply?.ok && reply.cart) liveCart.value = reply.cart;
  else if (reply) afterFailure(reply, message => (rowError[id] = message), true);
  if (pending[id] === want) drop(pending, id);
}

async function remove(id: string) {
  removing[id] = true;
  drop(rowError, id);
  const reply = await enqueue(() => cart.setQuantity(id, 0));
  if (reply.ok && reply.cart) liveCart.value = reply.cart;
  else afterFailure(reply, message => (rowError[id] = message), true);
  drop(removing, id);
}

// Back from FairPrice's checkout or login tab: the cart there may have changed, so read it again.
let returnTimer: ReturnType<typeof setTimeout> | undefined;
function returned() {
  if (document.visibilityState === "hidden") return;
  clearTimeout(returnTimer);
  returnTimer = setTimeout(() => {
    if ((setup.value === "ready" || setup.value === "login") && !cartLoading.value) void refreshCart();
  }, RETURN_REFRESH_MS);
}

onMounted(() => {
  void connect();
  void load();
  window.addEventListener("focus", returned);
  document.addEventListener("visibilitychange", returned);
});
onBeforeUnmount(() => {
  window.removeEventListener("focus", returned);
  document.removeEventListener("visibilitychange", returned);
  clearTimeout(returnTimer);
  commitWaiting();
});

const refreshAll = () => {
  void (setup.value === "ready" ? refreshCart() : connect());
  void load();
};
</script>

<template>
  <div ref="overlay" class="mc-overlay" role="dialog" aria-modal="true" aria-labelledby="fp-title" @click.self="close">
    <section class="panel mc-card">
      <header>
        <div>
          <h2 id="fp-title" class="mc-title">FairPrice cart</h2>
          <p class="mc-small">{{ liveCart?.store?.name ?? "Your own FairPrice cart" }} · You check out and pay on FairPrice.</p>
          <p v-if="leaveNote" class="mc-small" role="status">{{ leaveNote }}</p>
        </div>
        <button type="button" class="icon mc-btn quiet" aria-label="Refresh" :disabled="cartLoading || adding || rowBusy" @click="refreshAll">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" /></svg>
        </button>
        <button type="button" class="icon mc-btn quiet" aria-label="Close" @click="close">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </header>

      <div class="body">
        <section v-if="setup === 'checking'" class="setup" aria-label="Looking for the extension">
          <p role="status">Looking for the extension…</p>
        </section>

        <section v-else-if="setup === 'missing'" class="setup" aria-label="Install the extension">
          <h3 class="mc-label">One-time setup: the MealCraft FairPrice cart extension</h3>
          <ol>
            <li>Open <code>chrome://extensions</code> (or <code>edge://extensions</code>) and turn on Developer mode.</li>
            <li>Choose Load unpacked and pick the <code>browser-extension/fairprice-cart</code> folder of MealCraft.</li>
            <li>Reload this page, open the FairPrice cart again, or press Check again.</li>
          </ol>
          <p class="mc-small">More in <code>browser-extension/fairprice-cart/README.md</code>. Until then, use the product links below.</p>
          <div class="acts"><button type="button" class="mc-btn secondary sm" @click="connect">Check again</button></div>
        </section>

        <section v-else-if="setup === 'login'" class="setup" aria-label="Log in to FairPrice">
          <h3 class="mc-label">Log in to FairPrice</h3>
          <p>You're not logged in to FairPrice in this browser. Log in on FairPrice's own page; MealCraft never sees your password.</p>
          <div class="acts">
            <button type="button" class="mc-btn primary sm" @click="openLogin">Log in to FairPrice</button>
            <button type="button" class="mc-btn secondary sm" :disabled="cartLoading" @click="loggedIn">I've logged in</button>
          </div>
          <p v-if="loginNote" class="msg alert" role="alert">{{ loginNote }}</p>
        </section>

        <p v-if="cartProblem" class="msg alert" role="alert">
          {{ cartProblem }}
          <button type="button" class="mc-btn secondary sm" :disabled="cartLoading" @click="refreshCart">Try again</button>
        </p>

        <section class="block" aria-label="This week's list">
          <div class="block-head">
            <h3 class="mc-heading">This week's list</h3>
            <div v-if="trips > 1 && !sample" class="mc-segmented" role="tablist" aria-label="Shopping trip">
              <button v-for="n in trips" :key="n" type="button" role="tab" :aria-selected="trip === n" :disabled="adding" @click="chooseTrip(n)">Trip {{ n }}</button>
            </div>
          </div>

          <p v-if="sample" class="note" role="status">
            This plan uses sample prices, so there are no real FairPrice products to put in a cart. Plan the week again with live FairPrice prices to use this.
          </p>
          <p v-else-if="listStep === 'loading'" class="note" role="status">Checking today's FairPrice prices and stock…</p>
          <template v-else-if="listStep === 'error'">
            <p class="msg alert" role="alert">{{ listProblem }}</p>
            <div class="acts"><button type="button" class="mc-btn secondary sm" @click="load">Try again</button></div>
          </template>

          <template v-else-if="prepared">
            <p class="lead">
              <span>{{ ready.length }} of {{ ready.length + problems.length }} {{ ready.length + problems.length === 1 ? "item" : "items" }} ready ·
                <span class="mc-num">{{ formatSgd(prepared.ready_total_sgd) }}</span> at today's prices</span>
              <span v-if="already.length" class="mc-chip ok">{{ already.length }} already in your cart</span>
            </p>
            <p v-if="warning" class="msg warn" role="alert">{{ warning }}</p>

            <div v-if="changes.length" role="group" aria-label="Price changes">
              <h4 class="mc-label">Prices that changed since the plan</h4>
              <ul class="lines">
                <li v-for="change in changes" :key="change.line.line_key">
                  <span class="what"><b>{{ change.line.ingredient_display_name }}</b><small>{{ change.line.product_name }}</small></span>
                  <span class="mc-num price" :class="change.direction">{{ formatSgd(change.planned) }} → {{ formatSgd(change.live) }}</span>
                </li>
              </ul>
            </div>

            <div v-if="problems.length" role="group" aria-label="Lines that can't be added">
              <h4 class="mc-label">Won't be added</h4>
              <ul class="lines">
                <li v-for="line in problems" :key="line.line_key" class="bad">
                  <span class="what"><b>{{ line.ingredient_display_name }}</b><small>{{ problemLabel(line) }}</small></span>
                  <button v-if="SWAPPABLE.has(line.status)" type="button" class="mc-btn secondary sm" @click="swap(line)">Swap</button>
                </li>
              </ul>
            </div>

            <p v-if="!ready.length" class="msg alert" role="status">Nothing in this trip can be added to the FairPrice cart right now.</p>

            <template v-if="results.length">
              <p class="lead" role="status">{{ summaryLine(summarizeResults(results)) }}</p>
              <ul v-if="left.length" class="lines">
                <li v-for="result in left" :key="result.line_key" :class="result.status === 'reduced' ? 'warn' : 'bad'">
                  <span class="what">
                    <b>{{ lineOf(result.line_key)?.ingredient_display_name ?? result.line_key }}</b>
                    <small>{{ resultNote(result, lineOf(result.line_key)?.quantity) }}</small>
                  </span>
                  <button v-if="result.status === 'out_of_stock' && lineOf(result.line_key)" type="button" class="mc-btn secondary sm" @click="swap(lineOf(result.line_key)!)">Swap</button>
                </li>
              </ul>
            </template>
            <p v-if="changed" class="msg warn" role="alert">{{ CART_CHANGED_NOTE }}</p>
            <p v-if="addProblem" class="msg alert" role="alert">{{ addProblem }}</p>
            <p v-if="saveNote" class="msg alert" role="alert">
              {{ saveNote }}
              <button v-if="unsaved" type="button" class="mc-btn secondary sm" :disabled="saving" @click="saveReport(unsaved)">{{ saving ? "Saving…" : "Save to plan again" }}</button>
            </p>

            <div v-if="ready.length" class="acts">
              <button v-if="adding" type="button" class="mc-btn primary" disabled>Adding to your cart…</button>
              <template v-else-if="toAdd.length">
                <button type="button" class="mc-btn primary" :disabled="!canAdd" @click="add()">Add all to cart</button>
                <span v-if="canAdd" class="mc-small">{{ toAdd.length }} {{ toAdd.length === 1 ? "item" : "items" }} not in your cart yet</span>
                <span v-else-if="setup === 'ready'" class="mc-small">Adding waits until your cart has been read.</span>
              </template>
              <template v-else-if="confirmAgain">
                <span class="again" role="alert">Everything is already in your cart. Adding again adds these quantities a second time.</span>
                <button type="button" class="mc-btn secondary" :disabled="!canAdd" @click="add(true)">Add again</button>
                <button type="button" class="mc-btn quiet" @click="confirmAgain = false">Cancel</button>
              </template>
              <template v-else>
                <span class="done">Everything ready is already in your cart.</span>
                <button type="button" class="mc-btn secondary" :disabled="!canAdd" @click="confirmAgain = true">Add again…</button>
              </template>
            </div>
            <p class="mc-small">Nothing is removed from your cart unless you remove it here, and nothing is bought. Your plan stays as it is.</p>

            <details v-if="(setup === 'missing' || addProblem) && links.length" class="links" open>
              <summary>Add them yourself ({{ links.length }})</summary>
              <ul class="lines">
                <li v-for="line in links" :key="line.line_key">
                  <span class="what"><b>{{ line.ingredient_display_name }}</b><small>{{ line.quantity }} × {{ line.product_name }}</small></span>
                  <a class="mc-btn quiet sm" :href="line.product_url!" target="_blank" rel="noopener">Open</a>
                </li>
              </ul>
            </details>
          </template>
        </section>

        <section v-if="liveCart" class="block" aria-label="Your cart">
          <div class="block-head">
            <h3 class="mc-heading">Your cart</h3>
            <span class="mc-small">{{ liveCart.items.length }} {{ liveCart.items.length === 1 ? "item" : "items" }}</span>
          </div>
          <p v-if="!liveCart.items.length" class="note">Your FairPrice cart is empty.</p>
          <ul v-else class="rows">
            <li v-for="item in liveCart.items" :key="item.cart_item_id" class="row" :class="{ saving: isSaving(item.cart_item_id) }" :data-cart-item="item.cart_item_id">
              <div class="thumb">
                <img v-if="item.image_url && !broken[item.cart_item_id]" :src="item.image_url" alt="" width="64" height="64" @error="broken[item.cart_item_id] = true">
                <span v-else class="ph" aria-hidden="true">
                  <svg viewBox="0 0 24 24"><path d="M5 8h14l-1 12H6L5 8zM9 8a3 3 0 0 1 6 0" /></svg>
                </span>
              </div>
              <div class="info">
                <b class="name">{{ item.name }}</b>
                <span v-if="item.display_unit" class="mc-small">{{ item.display_unit }}</span>
                <span class="unit">
                  <b class="mc-num" :class="{ sale: isDiscounted(item) }">{{ sgdOrDash(item.unit_price_sgd) }}</b>
                  <s v-if="isDiscounted(item)" class="mc-num">{{ sgdOrDash(item.unit_mrp_sgd) }}</s>
                </span>
                <span v-if="planIds.has(item.cart_item_id) || item.note || isLocked(item) || !item.is_checked" class="tags">
                  <span v-if="planIds.has(item.cart_item_id)" class="mc-chip info">From this plan</span>
                  <span v-if="isLocked(item)" class="mc-chip ok">Free</span>
                  <span v-if="!item.is_checked" class="mc-chip warn">Not selected for checkout</span>
                  <span v-if="item.note" class="mc-chip warn">{{ item.note }}</span>
                </span>
                <span v-if="rowError[item.cart_item_id]" class="msg alert" role="alert">{{ rowError[item.cart_item_id] }}</span>
              </div>
              <div class="side">
                <div v-if="!isLocked(item)" class="stepper" role="group" :aria-label="`Quantity of ${item.name}`">
                  <button type="button" aria-label="Decrease quantity" :disabled="removing[item.cart_item_id] || quantityOf(item) <= 1" @click="step(item, -1)">−</button>
                  <output class="mc-num" aria-live="polite">{{ quantityOf(item) }}</output>
                  <button type="button" aria-label="Increase quantity" :disabled="removing[item.cart_item_id] || quantityOf(item) >= item.max_quantity" @click="step(item, 1)">+</button>
                </div>
                <b class="total mc-num" :class="{ muted: !item.is_checked }">{{ sgdOrDash(totalOf(item)) }}</b>
                <span v-if="isSaving(item.cart_item_id)" class="mc-small" role="status">Saving…</span>
                <button
                  v-else-if="!isLocked(item)"
                  type="button"
                  class="mc-btn quiet xs"
                  :aria-label="`Remove ${item.name}`"
                  @click="remove(item.cart_item_id)"
                >
                  Remove
                </button>
              </div>
            </li>
          </ul>

          <div v-if="liveCart.unavailable.length" role="group" aria-label="Unavailable items">
            <h4 class="mc-label">Unavailable at this store</h4>
            <ul class="rows">
              <li v-for="item in liveCart.unavailable" :key="item.cart_item_id" class="row off">
                <div class="thumb">
                  <img v-if="item.image_url && !broken[item.cart_item_id]" :src="item.image_url" alt="" width="64" height="64" @error="broken[item.cart_item_id] = true">
                  <span v-else class="ph" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M5 8h14l-1 12H6L5 8zM9 8a3 3 0 0 1 6 0" /></svg></span>
                </div>
                <div class="info">
                  <b class="name">{{ item.name }}</b>
                  <span class="mc-small">Unavailable · you wanted {{ item.want_quantity }}</span>
                  <span v-if="rowError[item.cart_item_id]" class="msg alert" role="alert">{{ rowError[item.cart_item_id] }}</span>
                </div>
                <div class="side">
                  <button type="button" class="mc-btn secondary sm" :disabled="removing[item.cart_item_id]" :aria-label="`Remove ${item.name}`" @click="remove(item.cart_item_id)">
                    {{ removing[item.cart_item_id] ? "Removing…" : "Remove" }}
                  </button>
                </div>
              </li>
            </ul>
          </div>
        </section>
      </div>

      <footer v-if="liveCart" class="summary" aria-label="Cart summary">
        <dl>
          <div><dt>Subtotal</dt><dd class="mc-num">{{ sgdOrDash(liveCart.totals.subtotal_sgd) }}</dd></div>
          <div v-if="liveCart.totals.savings_sgd > 0" class="save"><dt>Savings</dt><dd class="mc-num">−{{ formatSgd(liveCart.totals.savings_sgd) }}</dd></div>
          <div v-for="fee in fees" :key="fee.label">
            <dt>{{ fee.label }}</dt>
            <dd class="mc-num">
              <s v-if="fee.was">{{ fee.was }}</s>
              <span :class="{ free: fee.text === 'Free' }">{{ fee.text }}</span>
            </dd>
          </div>
          <div class="grand"><dt>Total</dt><dd class="mc-num">{{ sgdOrDash(liveCart.totals.total_sgd) }}</dd></div>
        </dl>
        <div class="go">
          <a v-if="liveCart.items.length" class="mc-btn primary" :href="FAIRPRICE_CHECKOUT_URL" target="_blank" rel="noopener">Checkout on FairPrice</a>
          <button v-else type="button" class="mc-btn primary" disabled>Checkout on FairPrice</button>
          <p v-if="ordered" class="done" role="status">Marked as ordered. Thanks.</p>
          <button
            v-else
            type="button"
            class="mc-btn secondary"
            :disabled="ordering || !previous"
            :title="previous ? undefined : 'Add this week\'s list to your cart first.'"
            @click="markOrdered"
          >
            {{ ordering ? "Saving…" : "I've checked out" }}
          </button>
          <p class="mc-small">Payment happens on FairPrice's own page.</p>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.panel { width: min(760px, 100%); max-height: calc(100vh - 32px); display: flex; flex-direction: column; }
header { display: flex; align-items: flex-start; gap: 8px; padding: 18px 20px 12px; border-bottom: 1px solid var(--c-line-soft); }
header > div { flex: 1; min-width: 0; }
header h2 { margin: 0 0 2px; }
header p { margin: 0; }
.icon { width: 36px; height: 36px; padding: 0; }
.icon svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.body { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 14px; padding: 14px 20px 16px; overflow-y: auto; }
.body p { margin: 0; }
.setup { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 12px; background: var(--c-info-bg); color: var(--c-info-text); }
.setup ol { margin: 0; padding-left: 20px; display: grid; gap: 4px; font-size: 13px; line-height: 18px; }
.setup code, .body code { font-size: 12px; }
.setup .mc-small, .setup .mc-label { color: var(--c-info-text); }
.block { display: flex; flex-direction: column; gap: 10px; }
.block-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.block-head h3, h4 { margin: 0; }
.lead { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px; font-size: 14px; font-weight: 800; }
.note { color: var(--c-neutral-text); line-height: 1.5; }
.msg { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px; padding: 10px 12px; border-radius: 12px; font-size: 13px; line-height: 18px; }
.msg.warn { background: var(--c-warn-bg); color: var(--c-amber-text); font-weight: 700; }
.msg.alert { background: var(--c-allergy-bg); color: var(--c-allergy-text); }
.lines { list-style: none; margin: 0; padding: 0; }
.lines li { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 4px 0; border-top: 1px solid var(--c-line-soft); }
.what { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.what b { font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.what small { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.lines li.warn .what small { color: var(--c-amber-text); }
.lines li.bad .what small { color: var(--c-allergy-text); }
.price { flex: none; font-size: 13px; font-weight: 800; }
.price.up { color: var(--c-amber-text); }
.price.down { color: var(--c-green-text); }
.acts { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 10px; }
.again { flex: 1 1 100%; font-size: 13px; color: var(--c-amber-text); font-weight: 700; }
.done { margin: 0; font-size: 13px; font-weight: 800; color: var(--c-green-text); }
.links summary { cursor: pointer; font-size: 13px; font-weight: 800; }
.rows { list-style: none; margin: 0; padding: 0; }
.row { display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; gap: 14px; align-items: start; padding: 12px 0; border-top: 1px solid var(--c-line-soft); transition: opacity 150ms; }
.row.saving { opacity: 0.7; }
.row.off .name { color: var(--c-muted); }
.thumb { width: 64px; height: 64px; border-radius: 10px; overflow: hidden; background: var(--c-neutral); }
.thumb img { display: block; width: 64px; height: 64px; object-fit: cover; }
.ph { display: flex; width: 100%; height: 100%; align-items: center; justify-content: center; color: var(--c-muted); }
.ph svg { width: 26px; height: 26px; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.name { font-weight: 800; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.unit { display: flex; align-items: baseline; gap: 6px; font-size: 13px; }
.unit b.sale { color: var(--c-coral); }
.unit s { font-size: 12px; color: var(--c-muted); }
.tags { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
.side { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; min-width: 112px; }
.stepper { display: inline-flex; align-items: center; height: 32px; border: 1px solid var(--c-border); border-radius: 999px; background: #fff; }
.stepper button { width: 32px; height: 30px; border: 0; background: transparent; border-radius: 999px; font-size: 18px; line-height: 1; font-weight: 700; }
.stepper button:hover:not(:disabled) { background: var(--c-neutral); }
.stepper output { min-width: 28px; text-align: center; font-weight: 800; }
.total { font-size: 15px; }
.total.muted { color: var(--c-muted); font-weight: 600; }
.mc-btn.xs { height: 30px; padding: 0 10px; font-size: 12px; border-radius: 8px; color: var(--c-muted); }
.summary { display: flex; gap: 24px; align-items: flex-end; justify-content: space-between; padding: 12px 20px 16px; border-top: 1px solid var(--c-line); background: var(--c-rail); }
.summary dl { margin: 0; flex: 1; max-width: 300px; display: grid; gap: 2px; font-size: 13px; }
.summary dl > div { display: flex; justify-content: space-between; gap: 12px; }
.summary dt { color: var(--c-neutral-text); }
.summary dd { margin: 0; display: inline-flex; gap: 6px; font-weight: 700; }
.summary dd s { color: var(--c-muted); font-weight: 600; }
.summary dd .free { color: var(--c-green-text); }
.summary .save dd { color: var(--c-green-text); }
.summary .grand { margin-top: 4px; padding-top: 4px; border-top: 1px solid var(--c-line); font-size: 16px; }
.summary .grand dt { color: var(--c-ink); font-weight: 800; }
.summary .grand dd { font-weight: 800; }
.go { display: flex; flex-direction: column; align-items: stretch; gap: 8px; min-width: 220px; text-align: center; }
.go p { margin: 0; }
</style>
