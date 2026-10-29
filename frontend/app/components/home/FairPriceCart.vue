<script setup lang="ts">
import {
  CART_CHANGED_NOTE,
  FAIRPRICE_CART_URL,
  alreadyAddedNote,
  budgetWarning,
  cartChanged,
  cartErrorMessage,
  cartPayload,
  priceChanges,
  problemLabel,
  problemLines,
  readyLines,
  resultNote,
  summarizeResults,
  summaryLine,
  swapSentence,
  tripKey,
} from "~/lib/fairprice-cart";
import { formatSgd } from "~/lib/home-surface";
import type { FairPriceCartLine, FairPriceCartPrepare, FairPriceCartReportBody, FairPriceCartResult, FairPriceCartState } from "~/types/meal-plan";
import type { PricingMode } from "~/types/recommendation";

// Puts the week's FairPrice lines in the person's own FairPrice cart, through the browser extension. They check out
// and pay on FairPrice; the plan is never changed here (a "Swap" only fills the composer, to be sent as a request).
// `cartState` is what the plan already records per trip; a trip that was sent needs a second confirm before it is added again.
const props = defineProps<{ planId: number; pricingMode: PricingMode; trips: number; cartState?: FairPriceCartState | null }>();
const emit = defineEmits<{ close: []; state: [state: FairPriceCartState]; ask: [text: string] }>();

type Step = "loading" | "review" | "sending" | "report" | "error";
const SWAPPABLE = new Set(["out_of_stock", "not_found"]);

const cart = useFairPriceCart();
const overlay = ref<HTMLElement | null>(null);
// While the extension is adding, closing would hide the one report that says what reached the cart.
function close() {
  if (step.value !== "sending") emit("close");
}
useDialog(overlay, close);

const sample = props.pricingMode === "fixture";
const step = ref<Step>(sample ? "review" : "loading");
const trip = ref<number | null>(props.trips > 1 ? 1 : null);
const prepared = ref<FairPriceCartPrepare | null>(null);
const extension = ref<"checking" | "found" | "missing">("checking");
// A failure to read the prices or to send, said in plain words; nothing was added when it is set in review.
const problem = ref<string | null>(null);
const results = ref<FairPriceCartResult[]>([]);
const saveNote = ref<string | null>(null);
// The report the plan couldn't save yet; saving it again never re-sends the list to FairPrice.
const unsaved = ref<FairPriceCartReportBody | null>(null);
const saving = ref(false);
const changed = ref(false);
const confirmAgain = ref(false);
const ordering = ref(false);
const ordered = ref(false);
let loadId = 0;

const errorDetail = (error: unknown) => (error as { data?: { detail?: string } }).data?.detail;

async function load() {
  const id = ++loadId;
  step.value = "loading";
  problem.value = null;
  prepared.value = null;
  try {
    const loaded = await cart.prepare(props.planId, trip.value);
    if (id !== loadId) return;
    prepared.value = loaded;
    step.value = "review";
  }
  catch (error) {
    if (id !== loadId) return;
    problem.value = errorDetail(error) || "Today's FairPrice prices couldn't be checked.";
    step.value = "error";
  }
}

async function detect() {
  extension.value = "checking";
  extension.value = (await cart.detectExtension()) ? "found" : "missing";
}

// Everything that belongs to one trip's add, so another trip never shows the last trip's report.
function resetTrip() {
  results.value = [];
  saveNote.value = null;
  unsaved.value = null;
  saving.value = false;
  changed.value = false;
  confirmAgain.value = false;
  ordering.value = false;
  ordered.value = false;
}

function chooseTrip(next: number) {
  if (next === trip.value || step.value === "sending") return;
  trip.value = next;
  resetTrip();
  void load();
}

const previous = computed(() => props.cartState?.[tripKey(trip.value)] ?? null);

const lines = computed(() => prepared.value?.lines ?? []);
const ready = computed(() => readyLines(lines.value));
const problems = computed(() => problemLines(lines.value));
const changes = computed(() => priceChanges(lines.value));
const warning = computed(() => (prepared.value ? budgetWarning(prepared.value) : null));
const links = computed(() => ready.value.filter(line => line.product_url));
const showLinks = computed(() => extension.value === "missing" || Boolean(problem.value));
const counts = computed(() => summarizeResults(results.value));
const lineOf = (key: string): FairPriceCartLine | undefined => lines.value.find(line => line.line_key === key);

interface Row { key: string; name: string; note: string; tone: "ok" | "warn" | "bad"; swap: FairPriceCartLine | null; url: string | null }
// What happened, worst first: each line the extension was sent, then each line that was never sent.
const rows = computed<Row[]>(() => {
  const sent: Row[] = results.value.map((result) => {
    const line = lineOf(result.line_key);
    const name = line?.ingredient_display_name ?? result.line_key;
    const url = line?.product_url ?? null;
    const note = resultNote(result, line?.quantity);
    if (result.status === "added") return { key: result.line_key, name, note, tone: "ok", swap: null, url: null };
    if (result.status === "reduced") return { key: result.line_key, name, note, tone: "warn", swap: null, url };
    if (result.status === "out_of_stock") return { key: result.line_key, name, note, tone: "bad", swap: line ?? null, url: null };
    return { key: result.line_key, name, note, tone: "bad", swap: null, url };
  });
  const sentKeys = new Set(results.value.map(result => result.line_key));
  const unsent: Row[] = problems.value.filter(line => !sentKeys.has(line.line_key)).map(line => ({
    key: line.line_key,
    name: line.ingredient_display_name,
    note: `${problemLabel(line)}, so it wasn't sent`,
    tone: "bad",
    swap: SWAPPABLE.has(line.status) ? line : null,
    url: null,
  }));
  const rank = { bad: 0, warn: 1, ok: 2 };
  return [...sent, ...unsent].sort((a, b) => rank[a.tone] - rank[b.tone]);
});

// A trip that was already sent asks once more before the same quantities go in a second time.
function add() {
  if (previous.value && !confirmAgain.value) confirmAgain.value = true;
  else void send();
}

async function send() {
  const current = prepared.value;
  if (!current || step.value === "sending") return;
  step.value = "sending";
  problem.value = null;
  confirmAgain.value = false;
  const reply = await cart.addToCart(cartPayload(current.lines));
  if (!reply.ok || !reply.results) {
    const code = reply.error ?? "unexpected_response";
    if (code === "no_extension") extension.value = "missing";
    problem.value = cartErrorMessage(code);
    step.value = "review";
    return;
  }
  results.value = reply.results;
  changed.value = cartChanged(reply);
  saveNote.value = null;
  step.value = "report";
  await saveReport({ shopping_trip: current.shopping_trip, fingerprint: current.fingerprint, results: reply.results });
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
    emit("state", await cart.markOrdered(props.planId, prepared.value?.shopping_trip ?? null));
    ordered.value = true;
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
const swap = (line: FairPriceCartLine) => emit("ask", swapSentence(line));

onMounted(() => {
  if (!sample) void load();
  void detect();
});
</script>

<template>
  <div ref="overlay" class="mc-overlay" role="dialog" aria-modal="true" aria-labelledby="fp-title" @click.self="close">
    <section class="box mc-card">
      <header>
        <div>
          <h2 id="fp-title" class="mc-title">Add to FairPrice cart</h2>
          <p class="mc-small">You check out and pay on FairPrice. MealCraft never sees your FairPrice login or payment details.</p>
        </div>
        <button type="button" class="close mc-btn quiet" aria-label="Close" :disabled="step === 'sending'" @click="close">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </header>

      <div v-if="trips > 1 && !sample && step !== 'report'" class="mc-segmented trips" role="tablist" aria-label="Shopping trip">
        <button v-for="n in trips" :key="n" type="button" role="tab" :aria-selected="trip === n" :disabled="step === 'sending'" @click="chooseTrip(n)">Trip {{ n }}</button>
      </div>

      <div class="body">
        <p v-if="sample" class="note" role="status">
          This plan uses sample prices, so there are no real FairPrice products to put in a cart. Plan the week again with live FairPrice prices to use this.
        </p>

        <template v-else-if="step === 'loading'">
          <p class="note" role="status">Checking today's FairPrice prices and stock…</p>
        </template>

        <template v-else-if="step === 'error'">
          <p class="msg alert" role="alert">{{ problem }}</p>
          <div class="acts"><button type="button" class="mc-btn secondary" @click="load">Try again</button></div>
        </template>

        <template v-else-if="step === 'report'">
          <p class="lead">{{ summaryLine(counts) }}</p>
          <ul class="lines">
            <li v-for="row in rows" :key="row.key" :class="row.tone">
              <span class="what"><b>{{ row.name }}</b><small>{{ row.note }}</small></span>
              <button v-if="row.swap" type="button" class="mc-btn secondary sm" @click="swap(row.swap)">Swap</button>
              <a v-else-if="row.url" class="mc-btn quiet sm" :href="row.url" target="_blank" rel="noopener">Open</a>
            </li>
          </ul>
          <p v-if="rows.some(row => row.swap)" class="mc-small">
            "Swap" puts a request in the message box. Send it to see the change before anything is replaced.
          </p>
          <p v-if="changed" class="msg warn" role="alert">{{ CART_CHANGED_NOTE }}</p>
          <p v-if="saveNote" class="msg alert" role="alert">{{ saveNote }}</p>
          <p v-if="ordered" class="msg done" role="status">Marked as ordered. Thanks.</p>
          <div class="acts">
            <a class="mc-btn primary" :href="FAIRPRICE_CART_URL" target="_blank" rel="noopener">Open FairPrice cart</a>
            <button v-if="unsaved" type="button" class="mc-btn secondary" :disabled="saving" @click="saveReport(unsaved)">
              {{ saving ? "Saving…" : "Save to plan again" }}
            </button>
            <button v-else-if="!ordered" type="button" class="mc-btn secondary" :disabled="ordering" @click="markOrdered">
              {{ ordering ? "Saving…" : "I've checked out" }}
            </button>
            <button v-else type="button" class="mc-btn quiet" @click="emit('close')">Close</button>
          </div>
        </template>

        <template v-else-if="prepared">
          <p class="lead">
            {{ ready.length }} of {{ ready.length + problems.length }} {{ ready.length + problems.length === 1 ? "item" : "items" }} ready ·
            <span class="mc-num">{{ formatSgd(prepared.ready_total_sgd) }}</span> at today's FairPrice prices
          </p>
          <p v-if="warning" class="msg warn" role="alert">{{ warning }}</p>
          <p v-if="previous" class="msg warn" role="alert">{{ alreadyAddedNote(previous) }}</p>

          <section v-if="changes.length" aria-label="Price changes">
            <h3 class="mc-label">Prices that changed since the plan</h3>
            <ul class="lines">
              <li v-for="change in changes" :key="change.line.line_key">
                <span class="what"><b>{{ change.line.ingredient_display_name }}</b><small>{{ change.line.product_name }}</small></span>
                <span class="mc-num price" :class="change.direction">{{ formatSgd(change.planned) }} → {{ formatSgd(change.live) }}</span>
              </li>
            </ul>
          </section>

          <section v-if="problems.length" aria-label="Lines that can't be added">
            <h3 class="mc-label">Won't be added</h3>
            <ul class="lines">
              <li v-for="line in problems" :key="line.line_key" class="bad">
                <span class="what"><b>{{ line.ingredient_display_name }}</b><small>{{ problemLabel(line) }}</small></span>
                <button v-if="SWAPPABLE.has(line.status)" type="button" class="mc-btn secondary sm" @click="swap(line)">Swap</button>
              </li>
            </ul>
          </section>

          <p v-if="!ready.length" class="msg alert" role="status">Nothing in this trip can be added to the FairPrice cart right now.</p>
          <p class="mc-small">Nothing is removed from your cart, and nothing is bought. Your plan stays as it is.</p>

          <p v-if="problem" class="msg alert" role="alert">{{ problem }}</p>

          <section v-if="extension === 'missing'" class="install" aria-label="Install the extension">
            <h3 class="mc-label">One-time setup</h3>
            <ol>
              <li>Open <code>chrome://extensions</code> (or <code>edge://extensions</code>) and turn on Developer mode.</li>
              <li>Choose Load unpacked and pick the <code>browser-extension/fairprice-cart</code> folder of MealCraft.</li>
              <li>Reload this page and open this again.</li>
            </ol>
            <p class="mc-small">More in <code>browser-extension/fairprice-cart/README.md</code>. Until then, use the links below.</p>
          </section>

          <details v-if="showLinks && links.length" class="links" open>
            <summary>Add them yourself ({{ links.length }})</summary>
            <ul class="lines">
              <li v-for="line in links" :key="line.line_key">
                <span class="what"><b>{{ line.ingredient_display_name }}</b><small>{{ line.quantity }} × {{ line.product_name }}</small></span>
                <a class="mc-btn quiet sm" :href="line.product_url!" target="_blank" rel="noopener">Open</a>
              </li>
            </ul>
          </details>

          <div class="acts">
            <button v-if="step === 'sending'" type="button" class="mc-btn primary" disabled>Sending to your cart…</button>
            <button v-else type="button" class="mc-btn primary" :disabled="!ready.length || extension !== 'found'" @click="add">
              {{ confirmAgain ? "Add again" : `Add ${ready.length} ${ready.length === 1 ? "item" : "items"} to FairPrice cart` }}
            </button>
            <button v-if="extension === 'missing'" type="button" class="mc-btn quiet" @click="detect">Check again</button>
            <button type="button" class="mc-btn quiet" :disabled="step === 'sending'" @click="close">Cancel</button>
          </div>
          <p v-if="step === 'sending'" class="mc-small" role="status">A FairPrice tab may open in the background. Keep this page open; it can take up to a minute.</p>
          <p v-else-if="extension === 'checking'" class="mc-small" role="status">Looking for the extension…</p>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.box { width: min(560px, 100%); max-height: calc(100vh - 64px); display: flex; flex-direction: column; }
header { display: flex; align-items: flex-start; gap: 12px; padding: 18px 20px 12px; }
header > div { flex: 1; min-width: 0; }
header h2 { margin: 0 0 4px; }
header p { margin: 0; }
.close { width: 36px; height: 36px; padding: 0; }
.close svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
.trips { margin: 0 20px 4px; align-self: flex-start; }
.body { display: flex; flex-direction: column; gap: 12px; padding: 4px 20px 18px; overflow-y: auto; }
.body p { margin: 0; }
.lead { font-size: 15px; font-weight: 800; }
.note { color: var(--c-neutral-text); line-height: 1.5; }
.msg { padding: 10px 12px; border-radius: 12px; font-size: 13px; line-height: 18px; }
.msg.warn { background: var(--c-warn-bg); color: var(--c-amber-text); font-weight: 700; }
.msg.alert { background: var(--c-allergy-bg); color: var(--c-allergy-text); }
.msg.done { background: var(--c-ok-bg); color: var(--c-green-text); font-weight: 800; }
h3 { margin: 0 0 2px; }
.lines { list-style: none; margin: 0; padding: 0; }
.lines li { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 4px 0; border-top: 1px solid var(--c-line-soft); }
.what { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.what b { font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.what small { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.lines li.ok .what small { color: var(--c-green-text); }
.lines li.warn .what small { color: var(--c-amber-text); }
.lines li.bad .what small { color: var(--c-allergy-text); }
.price { flex: none; font-size: 13px; font-weight: 800; }
.price.up { color: var(--c-amber-text); }
.price.down { color: var(--c-green-text); }
.install { padding: 12px 14px; border-radius: 12px; background: var(--c-info-bg); color: var(--c-info-text); }
.install ol { margin: 4px 0 8px; padding-left: 20px; display: grid; gap: 4px; font-size: 13px; line-height: 18px; }
.install code, .body code { font-size: 12px; }
.install .mc-small { color: var(--c-info-text); }
.links summary { cursor: pointer; font-size: 13px; font-weight: 800; }
.acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
</style>
