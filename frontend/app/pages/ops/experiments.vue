<script setup lang="ts">
import { formatSeconds, formatValue, formatWhen, humanKey, statusTone } from "~/lib/ops";
import { caseEvidence, categoryRows, currentParserLabel, draftChanges, evidenceMatch, experimentConfirmMessage, experimentExecution, experimentGates, experimentHeadline, presetBreakdown, queuesRun, spendsOpenAI } from "~/lib/ops-experiments";
import type { OpsEvaluation, OpsEvaluationName, OpsExperiment, OpsExperimentComparison, OpsExperimentDetail, OpsRuntimeSetting, OpsSettingChange } from "~/types/ops";

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const api = (path: string) => `${config.public.apiBase}/api/ops${path}`;
const detailOf = (error: unknown, fallback: string) => {
  const detail = (error as { data?: { detail?: unknown } }).data?.detail;
  return typeof detail === "string" ? detail : fallback;
};

// --- Runtime settings ---

const settings = ref<OpsRuntimeSetting[] | null>(null);
const history = ref<OpsSettingChange[]>([]);
const settingsFailed = ref(false);
// A number input's v-model stores a number once typed in.
const drafts = reactive<Record<string, string | number>>({});

async function loadSettings() {
  settingsFailed.value = false;
  try {
    const [listed, changes] = await Promise.all([
      apiFetch<{ items: OpsRuntimeSetting[] }>(api("/config")),
      apiFetch<{ items: OpsSettingChange[] }>(api("/config/history")),
    ]);
    settings.value = listed.items;
    history.value = changes.items;
    for (const item of listed.items) drafts[item.key] = String(item.value);
  }
  catch {
    settingsFailed.value = true;
  }
}

const labelOf = (key: string) => settings.value?.find(item => item.key === key)?.label ?? humanKey(key);
const currentParser = computed(() => settings.value?.find(item => item.key === "agent_parser_provider")?.value);
const pending = ref<{ setting: OpsRuntimeSetting; value: string | number | null } | null>(null);
const saving = ref(false);
const saveError = ref("");

function ask(setting: OpsRuntimeSetting, reset = false) {
  saveError.value = "";
  const raw = drafts[setting.key] ?? "";
  pending.value = { setting, value: reset ? null : setting.choices ? raw : Number(raw) };
}
const pendingMessage = computed(() => {
  if (!pending.value) return "";
  const { setting, value } = pending.value;
  const next = value === null ? `its default (${formatValue(setting.default)})` : formatValue(value);
  const effect = setting.wired ? "New requests use it straight away." : "It is stored and recorded; the planner does not read it yet.";
  return `${setting.label} changes from ${formatValue(setting.value)} to ${next}. ${effect}`;
});
async function confirmChange() {
  if (!pending.value) return;
  saving.value = true;
  try {
    await apiFetch<unknown>(api(`/config/${pending.value.setting.key}`), { method: "PUT", body: { value: pending.value.value } });
    pending.value = null;
    await loadSettings();
  }
  catch (error) {
    saveError.value = detailOf(error, "The setting couldn't be changed.");
    pending.value = null;
  }
  finally {
    saving.value = false;
  }
}

// --- Evaluations ---

const experiments = ref<OpsExperiment[] | null>(null);
const evaluations = ref<OpsEvaluation[]>([]);
const experimentsFailed = ref(false);
async function loadExperiments() {
  experimentsFailed.value = false;
  try {
    const listed = await apiFetch<{ items: OpsExperiment[]; evaluations: OpsEvaluation[] }>(api("/experiments"));
    experiments.value = listed.items;
    evaluations.value = listed.evaluations;
    if (!evaluations.value.some(item => item.name === form.evaluation)) {
      form.evaluation = evaluations.value[0]?.name ?? "planning-components";
    }
    schedulePoll();
  }
  catch {
    experimentsFailed.value = true;
  }
}

let pollTimer: ReturnType<typeof setTimeout> | null = null;
function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer);
  if (experiments.value?.some(item => item.status === "queued" || item.status === "running")) {
    pollTimer = setTimeout(loadExperiments, 2000);
  }
}
onMounted(() => Promise.all([loadSettings(), loadExperiments()]));
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer);
});

const form = reactive({
  evaluation: "planning-components" as OpsEvaluationName,
  label: "",
  planner: "product-planner",
  parser: "",
  repeats: 1,
  width: 32,
  maxExpansions: 10000,
  repairRounds: 1,
});
const chosen = computed(() => evaluations.value.find(item => item.name === form.evaluation));
const isPlanningExperiment = computed(() => chosen.value?.execution_mode === "durable_worker");
const isComponentExperiment = computed(() => form.evaluation === "planning-components");
const running = ref(false);
const runError = ref("");
const pendingExperiment = ref(false);
// The parser the run will use: the one chosen, else the switch's current value.
const runParser = computed(() => form.parser || currentParser.value);
const experimentMessage = computed(() => (chosen.value ? experimentConfirmMessage(chosen.value, runParser.value) : ""));
function askExperiment() {
  runError.value = "";
  pendingExperiment.value = true;
}
async function runExperiment() {
  // Checked at once, not through a disabled button: a second click can arrive before the page redraws.
  if (running.value) return;
  running.value = true;
  runError.value = "";
  const overrides: Record<string, string> = {};
  if (form.evaluation === "developer-planning" && form.planner) overrides.planner = form.planner;
  if (form.evaluation === "agent-benchmark" && form.parser) overrides.agent_parser_provider = form.parser;
  const body = isPlanningExperiment.value
    ? {
        evaluation: form.evaluation,
        label: form.label || null,
        parameters: {
          repeats: isComponentExperiment.value ? form.repeats : 1,
          width: form.width,
          max_expansions: form.maxExpansions,
          ...(isComponentExperiment.value ? { repair_rounds: form.repairRounds } : {}),
        },
        confirm: true,
      }
    : { evaluation: form.evaluation, label: form.label || null, overrides };
  const idempotencyKey = `ops-experiment-${crypto.randomUUID()}`;
  try {
    const result = await apiFetch<OpsExperiment>(api("/experiments"), {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body,
    });
    await loadExperiments();
    pickB.value = pickA.value === result.id ? null : result.id;
  }
  catch (error) {
    runError.value = detailOf(error, "The evaluation couldn't be started.");
  }
  finally {
    running.value = false;
    pendingExperiment.value = false;
  }
}

// --- A/B ---

const pickA = ref<number | null>(null);
const pickB = ref<number | null>(null);
const runA = computed(() => experiments.value?.find(item => item.id === pickA.value) ?? null);
const runB = computed(() => experiments.value?.find(item => item.id === pickB.value) ?? null);
const comparison = ref<OpsExperimentComparison | null>(null);
const comparisonLoading = ref(false);
const comparisonError = ref("");
watch([pickA, pickB], async ([a, b]) => {
  comparison.value = null;
  comparisonError.value = "";
  if (a === null || b === null) return;
  if (a === b) {
    comparisonError.value = "Choose two different runs.";
    return;
  }
  comparisonLoading.value = true;
  try {
    comparison.value = await apiFetch<OpsExperimentComparison>(api(`/experiments/compare?ids=${a},${b}`));
  }
  catch (error) {
    comparisonError.value = detailOf(error, "The comparison couldn't be loaded.");
  }
  finally {
    comparisonLoading.value = false;
  }
});
const comparisonReadiness = computed(() => comparison.value
  ? { compatible: comparison.value.compatible, reasons: comparison.value.reasons }
  : comparisonError.value ? { compatible: false, reasons: [comparisonError.value] } : null);
const evidenceRows = computed(() => comparison.value?.evidence.map(row => ({ ...row, label: humanKey(row.key) })) ?? []);
const metricRows = computed(() => comparison.value?.metrics.map(row => ({ ...row, metric: row.key })) ?? []);
const configRows = computed(() => comparison.value?.configurations.filter(row => row.matches === false).map(row => ({ key: row.key, before: row.a, after: row.b })) ?? []);
const failureRows = computed(() => comparison.value?.failure_mechanisms.map(row => ({ key: row.key, before: row.a, after: row.b })) ?? []);
// Whether higher is better differs by metric, so a change is only marked, not judged.
const deltaClass = (delta: number | null) => (delta ? "moved" : "");

// --- Experiment evidence drawer ---

const selectedExperiment = ref<OpsExperimentDetail | null>(null);
const selectedExperimentId = ref<number | null>(null);
const detailLoading = ref(false);
const detailFailed = ref(false);
async function openExperiment(run: OpsExperiment) {
  selectedExperimentId.value = run.id;
  selectedExperiment.value = null;
  detailFailed.value = false;
  detailLoading.value = true;
  try {
    selectedExperiment.value = await apiFetch<OpsExperimentDetail>(api(`/experiments/${run.id}`));
  }
  catch {
    detailFailed.value = true;
  }
  finally {
    detailLoading.value = false;
  }
}
function closeExperiment() {
  selectedExperimentId.value = null;
  selectedExperiment.value = null;
  detailFailed.value = false;
}
// Escape closes the drawer, as on the Tasks page.
function onKey(event: KeyboardEvent) {
  if (event.key === "Escape" && selectedExperimentId.value !== null) closeExperiment();
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
const reportRuns = computed<Record<string, unknown>[]>(() => {
  const runs = selectedExperiment.value?.report?.runs;
  return Array.isArray(runs) ? runs.filter(item => item && typeof item === "object") as Record<string, unknown>[] : [];
});
const presets = computed(() => presetBreakdown(selectedExperiment.value?.report ?? null));
const failedCases = computed(() => reportRuns.value.filter((item) => {
  if (Array.isArray(item.failures) && item.failures.length) return true;
  if (item.audit && typeof item.audit === "object" && (item.audit as Record<string, unknown>).status !== "passed") return true;
  if (Array.isArray(item.candidate_checks)) {
    return item.candidate_checks.some((candidate) => {
      if (!candidate || typeof candidate !== "object") return false;
      return Array.isArray((candidate as Record<string, unknown>).failures) && ((candidate as Record<string, unknown>).failures as unknown[]).length > 0;
    });
  }
  return JSON.stringify(item).includes('"status":"failed"') || JSON.stringify(item).includes('"status":"indeterminate"');
}));
</script>

<template>
  <div class="ops-page">
    <header>
      <h1 class="mc-serif">Switches, evaluations and A/B comparisons</h1>
      <p>Each switch starts at the server's default, and a change is recorded with who made it and what it was before. Only switches marked “Used by the product” reach new requests; the others are stored until the planner reads them. Evaluations run only the developer sets; held-out sets are never offered here.</p>
    </header>

    <section class="ops-card" aria-labelledby="settings-title">
      <h2 id="settings-title">Runtime switches</h2>
      <p v-if="settingsFailed" class="ops-error" role="alert">The switches couldn't be loaded. <button type="button" class="mc-pill" @click="loadSettings">Try again</button></p>
      <p v-else-if="!settings" class="ops-muted" aria-busy="true">Loading…</p>
      <template v-else>
        <p v-if="saveError" class="ops-error" role="alert">{{ saveError }}</p>
        <ul class="switches">
          <li v-for="setting in settings" :key="setting.key">
            <div class="what">
              <label :for="`set-${setting.key}`">{{ setting.label }}</label>
              <p class="ops-muted">{{ setting.meaning }}</p>
              <p class="tags">
                <span class="mc-chip">{{ setting.overridden ? "Changed here" : "Server default" }}</span>
                <span class="mc-chip" :class="{ warn: !setting.wired }">{{ setting.wired ? "Used by the product" : "Stored only, not read yet" }}</span>
              </p>
            </div>
            <div class="how">
              <select v-if="setting.choices" :id="`set-${setting.key}`" v-model="drafts[setting.key]">
                <option v-for="choice in setting.choices" :key="choice" :value="choice">{{ choice }}</option>
              </select>
              <input v-else :id="`set-${setting.key}`" v-model="drafts[setting.key]" type="number" :min="setting.minimum ?? undefined" :max="setting.maximum ?? undefined" :step="setting.integer ? 1 : 'any'">
              <button type="button" class="mc-primary" :disabled="!draftChanges(setting, drafts[setting.key])" @click="ask(setting)">Change</button>
              <button v-if="setting.overridden" type="button" class="mc-pill" @click="ask(setting, true)">Use default</button>
            </div>
          </li>
        </ul>
      </template>
    </section>

    <section class="ops-card table-card" aria-labelledby="history-title">
      <h2 id="history-title">Change history</h2>
      <p v-if="!history.length" class="ops-muted">No switch has been changed yet.</p>
      <table v-else>
        <thead><tr><th>When</th><th>Who</th><th>Switch</th><th>Before</th><th>After</th></tr></thead>
        <tbody>
          <tr v-for="(change, index) in history" :key="index">
            <td class="ops-muted">{{ formatWhen(change.created_at) }}</td>
            <td>{{ change.actor ?? "Removed account" }}</td>
            <td>{{ labelOf(change.key) }}</td>
            <td>{{ formatValue(change.before) }}</td>
            <td>{{ formatValue(change.after) }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- One column: the form full width, then the comparison in its own full-width card. -->
    <div class="ops-stack">
      <form class="ops-card run-form" aria-labelledby="run-title" @submit.prevent="askExperiment">
        <h2 id="run-title">Run an evaluation</h2>
        <label>Evaluation
          <select v-model="form.evaluation">
            <option v-for="item in evaluations" :key="item.name" :value="item.name">{{ item.label }}</option>
          </select>
        </label>
        <p v-if="chosen" class="ops-muted small">
          {{ chosen.description }} Dataset {{ chosen.dataset }}.
          <span class="mc-chip">{{ experimentExecution(chosen, runParser) }}</span>
        </p>
        <template v-if="isPlanningExperiment">
          <div class="num-fields">
            <label v-if="isComponentExperiment">Repeats
              <input v-model.number="form.repeats" type="number" min="1" max="20">
            </label>
            <label>Beam width
              <input v-model.number="form.width" type="number" min="1" max="1000">
            </label>
            <label>Maximum expansions
              <input v-model.number="form.maxExpansions" type="number" min="1" max="1000000">
            </label>
            <label v-if="isComponentExperiment">Repair rounds
              <input v-model.number="form.repairRounds" type="number" min="0" max="10">
            </label>
          </div>
          <p class="ops-muted small">The fixed developer fixture is used. Held-out data and paid models are unavailable here.</p>
        </template>
        <label v-else-if="form.evaluation === 'developer-planning'">Planner
          <select v-model="form.planner">
            <option value="product-planner">MealCraft product planner (beam search, as the assistant plans)</option>
            <option value="greedy-baseline">Greedy baseline (the top-ranked recipe every night)</option>
            <option value="rule-only-baseline">Strong rule-only baseline (fixed tie-breaks, no repeat in a row)</option>
          </select>
        </label>
        <label v-else>Parser
          <select v-model="form.parser">
            <option value="">{{ currentParserLabel(currentParser) }}</option>
            <option value="fixture">Rule-based (fixture)</option>
            <option value="openai">OpenAI model (paid, runs in the background)</option>
          </select>
        </label>
        <label>Name (optional) <input v-model="form.label" maxlength="80" placeholder="e.g. before the budget change"></label>
        <p v-if="runError" class="ops-error" role="alert">{{ runError }}</p>
        <button type="submit" class="mc-primary" :disabled="running || !evaluations.length" :aria-busy="running">{{ running ? "Running…" : "Run evaluation" }}</button>
      </form>

      <section class="ops-card" aria-labelledby="ab-title">
        <h2 id="ab-title">A/B comparison</h2>
        <p v-if="!runA || !runB" class="ops-muted">Choose run A and run B in the results below.</p>
        <template v-else>
          <p class="ops-muted small">A is #{{ runA.id }} {{ runA.label ?? "" }}, B is #{{ runB.id }} {{ runB.label ?? "" }}.<template v-if="runA.evaluation !== runB.evaluation"> They ran different evaluations, so most metrics do not line up.</template></p>
          <p v-if="comparisonLoading" class="ops-muted" aria-busy="true">Checking whether these records are comparable…</p>
          <template v-else-if="comparisonReadiness">
          <p v-if="comparisonReadiness.compatible" class="comparison-ready" role="status">Comparable developer diagnostic. Deltas below share the same recorded evidence context.</p>
          <div v-else class="comparison-blocked" role="alert">
            <b>Do not interpret these deltas.</b>
            <ul><li v-for="reason in comparisonReadiness.reasons" :key="reason">{{ reason }}</li></ul>
          </div>
          <h3>Evidence context</h3>
          <table class="metrics evidence-table">
            <thead><tr><th>Condition</th><th>A</th><th>B</th><th>Match</th></tr></thead>
            <tbody>
              <tr v-for="row in evidenceRows" :key="row.label">
                <th>{{ row.label }}</th>
                <td :title="formatValue(row.a)">{{ formatValue(row.a) }}</td>
                <td :title="formatValue(row.b)">{{ formatValue(row.b) }}</td>
                <td>{{ evidenceMatch(row) }}</td>
              </tr>
            </tbody>
          </table>
          <h3>Configuration differences</h3>
          <p v-if="!configRows.length" class="ops-muted small">Both ran under the same configuration.</p>
          <ul v-else class="config-diff">
            <li v-for="row in configRows" :key="row.key">{{ humanKey(row.key) }}: <b>{{ formatValue(row.before) }}</b> → <b>{{ formatValue(row.after) }}</b></li>
          </ul>
          <table class="metrics">
            <thead><tr><th>Metric</th><th>A</th><th>B</th><th>B − A</th></tr></thead>
            <tbody>
              <tr v-for="row in metricRows" :key="row.metric">
                <th>{{ humanKey(row.metric) }}</th>
                <td class="mc-num">{{ formatValue(row.a) }}</td>
                <td class="mc-num">{{ formatValue(row.b) }}</td>
                <td class="mc-num" :class="comparisonReadiness?.compatible ? deltaClass(row.delta) : ''">{{ !comparisonReadiness?.compatible || row.delta === null ? "—" : row.delta > 0 ? `+${row.delta}` : row.delta }}</td>
              </tr>
            </tbody>
          </table>
          <h3>Failure mechanisms</h3>
          <p v-if="!failureRows.length" class="ops-muted small">Neither record contains aggregated failure mechanisms.</p>
          <table v-else class="metrics">
            <thead><tr><th>Mechanism</th><th>A count</th><th>B count</th></tr></thead>
            <tbody><tr v-for="row in failureRows" :key="row.key"><th>{{ humanKey(row.key) }}</th><td>{{ formatValue(row.before) }}</td><td>{{ formatValue(row.after) }}</td></tr></tbody>
          </table>
          <h3>Case changes</h3>
          <p v-if="!comparison?.case_differences" class="ops-muted small">One or both runs stored no case-level report, so case changes cannot be compared.</p>
          <p v-else-if="!comparison.case_differences.length" class="ops-muted small">No case changed status or failure mechanism.</p>
          <table v-else class="metrics case-changes">
            <thead><tr><th>Case / condition</th><th>A status</th><th>B status</th><th>Failures gained</th><th>Failures lost</th></tr></thead>
            <tbody>
              <tr v-for="item in comparison.case_differences" :key="`${item.case_id}-${item.condition}`">
                <th>{{ item.case_id }}<template v-if="item.condition"> · {{ item.condition }}</template></th>
                <td>{{ item.a_status ?? "—" }}</td>
                <td>{{ item.b_status ?? "—" }}</td>
                <td>{{ item.failures_gained.length ? item.failures_gained.map(humanKey).join(", ") : "none" }}</td>
                <td>{{ item.failures_lost.length ? item.failures_lost.map(humanKey).join(", ") : "none" }}</td>
              </tr>
            </tbody>
          </table>
          <p class="ops-muted small">This comparison is implementation-side developer evidence, never a held-out result or a production success-rate claim.</p>
          </template>
        </template>
      </section>
    </div>

    <section class="ops-card table-card" aria-labelledby="results-title">
      <header class="results-head">
        <h2 id="results-title">Results</h2>
        <button type="button" class="mc-pill" @click="loadExperiments">Refresh</button>
      </header>
      <p v-if="experimentsFailed" class="ops-error" role="alert">The results couldn't be loaded.</p>
      <p v-else-if="!experiments" class="ops-muted" aria-busy="true">Loading…</p>
      <p v-else-if="!experiments.length" class="ops-muted">No evaluation has been run yet.</p>
      <table v-else class="results">
        <thead><tr><th class="pick">A · B</th><th>Run</th><th>Status</th><th>Headline</th><th>Gates</th><th class="mc-num">Time</th><th>When</th><th>Evidence</th></tr></thead>
        <tbody>
          <tr v-for="run in experiments" :key="run.id">
            <td class="pick"><input v-model="pickA" type="radio" name="pick-a" :value="run.id" :aria-label="`Use run ${run.id} as A`"><input v-model="pickB" type="radio" name="pick-b" :value="run.id" :aria-label="`Use run ${run.id} as B`"></td>
            <td class="run-name"><span :title="`#${run.id} ${evaluations.find(item => item.name === run.evaluation)?.label ?? run.evaluation}${run.label ? ` · ${run.label}` : ''}`"><b>#{{ run.id }}</b> {{ evaluations.find(item => item.name === run.evaluation)?.label ?? run.evaluation }}<span v-if="run.label" class="ops-muted"> · {{ run.label }}</span></span></td>
            <td class="nowrap"><span class="ops-badge" :class="statusTone(run.status)">{{ humanKey(run.status) }}</span><p v-if="run.error" class="ops-error small">{{ run.error }}</p></td>
            <td class="headline"><span :title="experimentHeadline(run)">{{ experimentHeadline(run) }}</span></td>
            <td class="gates">{{ experimentGates(run) }}</td>
            <td class="mc-num">{{ formatSeconds(run.duration_seconds) }}</td>
            <td class="ops-muted nowrap">{{ formatWhen(run.created_at) }}</td>
            <td><button type="button" class="mc-pill sm" @click="openExperiment(run)">Open</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <OpsConfirm
      v-if="pending"
      title="Change this switch?"
      :message="pendingMessage"
      :action="pending.value === null ? 'Use the default' : 'Change it'"
      :busy="saving"
      @confirm="confirmChange"
      @cancel="pending = null"
    />
    <OpsConfirm
      v-if="pendingExperiment"
      :title="chosen && queuesRun(chosen) ? 'Queue this evaluation?' : 'Run this evaluation?'"
      :message="experimentMessage"
      :action="chosen && queuesRun(chosen) ? 'Queue evaluation' : 'Start run'"
      :danger="spendsOpenAI(form.evaluation, runParser)"
      :busy="running"
      @confirm="runExperiment"
      @cancel="pendingExperiment = false"
    />

    <div v-if="selectedExperimentId !== null" class="drawer-scrim" @click.self="closeExperiment">
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="experiment-detail-title">
        <header class="drawer-head">
          <div>
            <p class="mc-eyebrow">Experiment #{{ selectedExperimentId }}</p>
            <h2 id="experiment-detail-title" class="mc-serif">{{ selectedExperiment?.label ?? selectedExperiment?.evaluation ?? "Loading evidence…" }}</h2>
          </div>
          <button type="button" class="mc-close" aria-label="Close" @click="closeExperiment"><UIcon name="i-lucide-x" aria-hidden="true" /></button>
        </header>
        <p v-if="detailFailed" class="ops-error" role="alert">This experiment evidence couldn't be loaded.</p>
        <p v-else-if="detailLoading || !selectedExperiment" class="ops-muted" aria-busy="true">Loading recorded evidence…</p>
        <template v-else>
          <div class="chips">
            <span class="ops-badge" :class="statusTone(selectedExperiment.status)">{{ humanKey(selectedExperiment.status) }}</span>
            <span class="mc-chip" :class="{ alert: !selectedExperiment.reproducibility.complete }">{{ selectedExperiment.reproducibility.complete ? "Reproducibility complete" : "Conditions incomplete" }}</span>
            <span class="mc-chip">{{ humanKey(selectedExperiment.reproducibility.claim_scope) }}</span>
            <span v-if="selectedExperiment.passed !== null" class="mc-chip" :class="{ alert: !selectedExperiment.passed }">{{ selectedExperiment.passed ? "Gates passed" : "Gates not passed" }}</span>
          </div>
          <section aria-labelledby="detail-metrics">
            <h3 id="detail-metrics">Results</h3>
            <p v-if="!Object.keys(selectedExperiment.metrics).length" class="ops-muted">No result is recorded yet.</p>
            <OpsFields v-else :data="selectedExperiment.metrics" />
            <table v-if="categoryRows(selectedExperiment.report).length" class="metrics">
              <thead><tr><th>Category</th><th>Cases</th><th>Failed</th></tr></thead>
              <tbody>
                <tr v-for="row in categoryRows(selectedExperiment.report)" :key="row.category">
                  <th>{{ humanKey(row.category) }}</th>
                  <td class="mc-num">{{ formatValue(row.cases) }}</td>
                  <td class="mc-num">{{ formatValue(row.failed) }}</td>
                </tr>
              </tbody>
            </table>
          </section>
          <section v-if="presets" aria-labelledby="detail-presets">
            <h3 id="detail-presets">By preset</h3>
            <p class="ops-muted small">What each switch did on each case: beam is the beam search, greedy the reference greedy planner, variety_off and overlap_off drop that weight, repair_off skips repair. Each cell is the final audit and the hard failures it found.</p>
            <div class="preset-table">
              <table class="metrics">
                <thead><tr><th>Case</th><th v-for="preset in presets.presets" :key="preset">{{ preset }}</th></tr></thead>
                <tbody>
                  <tr v-for="row in presets.rows" :key="row.caseId">
                    <th>{{ row.caseId }}</th>
                    <td v-for="(cell, index) in row.cells" :key="presets.presets[index]">{{ cell }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <section aria-labelledby="detail-reproduce">
            <h3 id="detail-reproduce">Reproducibility</h3>
            <OpsFields :data="selectedExperiment.conditions" />
            <p v-if="selectedExperiment.reproducibility.missing.length" class="ops-error">Missing: {{ selectedExperiment.reproducibility.missing.join(", ") }}</p>
            <ul class="ops-muted small"><li v-for="warning in selectedExperiment.reproducibility.warnings" :key="warning">{{ warning }}</li></ul>
          </section>
          <section aria-labelledby="detail-failures">
            <h3 id="detail-failures">Failed cases</h3>
            <p v-if="!selectedExperiment.report" class="ops-muted">This legacy run stored no case-level report.</p>
            <p v-else-if="!failedCases.length" class="ops-muted">No failed or indeterminate case is recorded.</p>
            <template v-else>
              <details v-for="(item, index) in failedCases" :key="String(item.case_id ?? index)">
                <summary>{{ String(item.case_id ?? `Case ${index + 1}`) }}<template v-if="item.preset"> · {{ item.preset }}</template><template v-else-if="item.category"> · {{ humanKey(String(item.category)) }}</template></summary>
                <OpsFields v-if="caseEvidence(item)" :data="caseEvidence(item)!" />
                <pre v-else>{{ JSON.stringify(item, null, 2) }}</pre>
              </details>
            </template>
          </section>
          <details v-if="selectedExperiment.report">
            <summary>Complete stored report</summary>
            <pre>{{ JSON.stringify(selectedExperiment.report, null, 2) }}</pre>
          </details>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.switches { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.switches li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 20px; padding: 14px 0; border-bottom: 1px solid #f0f0f2; }
.switches li:last-child { border-bottom: 0; }
.what { flex: 1 1 320px; min-width: 0; }
.what label { color: #18181b; font-size: 14px; font-weight: 500; }
.what p { margin: 4px 0 0; font-size: 12.5px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.how { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.how select, .how input { width: 150px; }
.small { font-size: 12px; }
.ops-stack { display: grid; gap: 16px; }
/* Tables run edge to edge under the card's title. */
.ops-card.table-card > h2 { margin: 0; padding: 16px 20px; }
.ops-card.table-card > p { margin: 0; padding: 0 20px 16px; }
.results-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; }
.results-head h2 { margin: 0; }
td p { margin: 4px 0 0; }
.run-form { display: grid; gap: 12px; align-content: start; }
.run-form label { display: grid; gap: 6px; color: #71717a; font-size: 12px; font-weight: 500; }
.run-form p { margin: 0; }
.run-form .mc-primary { justify-self: start; }
.num-fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
/* Results: one line a cell; the full run name and headline are tooltips. */
.nowrap, .ops-shell main td.mc-num { white-space: nowrap; }
.results :is(th, td) { padding-inline: 10px !important; }
.results :is(th, td):first-child { padding-left: 16px !important; }
.pick { width: 64px; white-space: nowrap; }
.pick input { vertical-align: middle; }
.pick input + input { margin-left: 14px; }
/* The run's name on one line, the headline on two at most; both whole in their tooltip. */
.run-name > span { display: block; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-name b { font-weight: 600; }
.headline > span { display: -webkit-box; max-width: 260px; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.gates { min-width: 96px; }
h3 { margin: 18px 0 8px; color: var(--mc-strong); font-size: 13px; line-height: 18px; font-weight: 600; }
.config-diff { margin: 0; padding-left: 18px; font-size: 13px; }
.config-diff b { color: #0f0f12; font-weight: 600; }
/* The comparison tables sit in half a page: smaller cells than the full-width tables. */
.metrics { margin-top: 12px; border: 1px solid #ececef; border-radius: 10px; border-collapse: separate; border-spacing: 0; overflow: hidden; }
.metrics th, .metrics td { height: auto; padding: 8px 10px; font-size: 13px; line-height: 18px; }
.metrics thead th { height: 32px; padding-block: 0; }
.metrics tbody th { color: #52525b; font-weight: 400; white-space: normal; }
.metrics td.mc-num { text-align: right; font-variant-numeric: tabular-nums; }
/* A moved figure is data, not a link: ink and bold. */
.moved { color: #0f0f12; font-weight: 600; }
.comparison-ready, .comparison-blocked { margin: 12px 0; padding: 10px 14px; border: 1px solid; border-radius: 12px; font-size: 13px; line-height: 18px; }
.comparison-ready { border-color: #abefc6; background: #ecfdf3; color: #067647; }
.comparison-blocked { border-color: #fecdca; background: #fef3f2; color: #b42318; }
.comparison-blocked ul { margin: 6px 0 0; padding-left: 18px; }
.evidence-table td { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 12px/18px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.evidence-table td:last-child { font-family: inherit; font-size: 13px; }
.metrics thead th { white-space: nowrap; }
/* Five columns in half a page: headings and the humanized failure codes wrap at spaces rather than push the card wider; a status stays whole. */
.case-changes th, .case-changes td { padding: 9px 8px; }
.case-changes thead th { white-space: normal; }
.case-changes td:nth-child(-n+3) { white-space: nowrap; }
/* The drawer's overlay, with the same values as the shared console drawer in ops.vue. */
.drawer-scrim { position: fixed; inset: 0; z-index: 30; background: rgba(15, 15, 18, 0.32); }
.drawer { position: fixed; top: 8px; right: 8px; bottom: 8px; width: min(640px, calc(100vw - 16px)); overflow-y: auto; padding: 0 24px 24px; border: 1px solid #ececef; border-radius: 16px; background: #fff; box-shadow: var(--mc-shadow-md); }
.drawer-head + .chips { margin-bottom: 4px; }
.drawer h3 { margin: 0 0 12px; }
.preset-table { overflow-x: auto; }
.preset-table td { min-width: 96px; font-size: 12px; }
.drawer details { margin-top: 12px; border: 1px solid #ececef; border-radius: 10px; }
.drawer summary { padding: 9px 12px; color: #27272a; cursor: pointer; font-size: 13px; font-weight: 500; }
.drawer details pre, .drawer details .ops-fields { margin: 0 12px 12px; }
</style>
