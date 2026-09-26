<script setup lang="ts">
import { compareMetrics, diffFields, formatSeconds, formatValue, formatWhen, humanKey, statusColor } from "~/lib/ops";
import type { OpsEvaluation, OpsEvaluationName, OpsExperiment, OpsRuntimeSetting, OpsSettingChange } from "~/types/ops";

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
const drafts = reactive<Record<string, string>>({});

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
    await apiFetch(api(`/config/${pending.value.setting.key}`), { method: "PUT", body: { value: pending.value.value } });
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
  }
  catch {
    experimentsFailed.value = true;
  }
}
onMounted(() => Promise.all([loadSettings(), loadExperiments()]));

const form = reactive({ evaluation: "developer-planning" as OpsEvaluationName, label: "", planner: "", parser: "" });
const chosen = computed(() => evaluations.value.find(item => item.name === form.evaluation));
const running = ref(false);
const runError = ref("");
async function runExperiment() {
  running.value = true;
  runError.value = "";
  const overrides: Record<string, string> = {};
  if (form.evaluation === "developer-planning" && form.planner) overrides.planner = form.planner;
  if (form.evaluation === "agent-benchmark" && form.parser) overrides.agent_parser_provider = form.parser;
  try {
    const result = await apiFetch<OpsExperiment>(api("/experiments"), { method: "POST", body: { evaluation: form.evaluation, label: form.label || null, overrides } });
    await loadExperiments();
    pickB.value = pickA.value === result.id ? null : result.id;
  }
  catch (error) {
    runError.value = detailOf(error, "The evaluation couldn't be started.");
  }
  finally {
    running.value = false;
  }
}

// --- A/B ---

const pickA = ref<number | null>(null);
const pickB = ref<number | null>(null);
const runA = computed(() => experiments.value?.find(item => item.id === pickA.value) ?? null);
const runB = computed(() => experiments.value?.find(item => item.id === pickB.value) ?? null);
const metricRows = computed(() => (runA.value && runB.value ? compareMetrics(runA.value.metrics, runB.value.metrics) : []));
const configRows = computed(() => (runA.value && runB.value ? diffFields(runA.value.configuration, runB.value.configuration).filter(row => row.changed) : []));
const headline = (run: OpsExperiment) => {
  const metric = run.evaluation === "developer-planning" ? "scenario_expectation_rate" : "exact_case_rate";
  return run.metrics[metric] === undefined ? "—" : `${humanKey(metric)} ${formatValue(run.metrics[metric])}`;
};
// Whether higher is better differs by metric, so a change is only marked, not judged.
const deltaClass = (delta: number | null) => (delta ? "moved" : "");
</script>

<template>
  <div class="ops-page">
    <header>
      <p class="mc-eyebrow">Experiments &amp; configuration</p>
      <h1 class="mc-serif">Switches, evaluations and A/B comparisons</h1>
      <p>Each switch starts at the server's default. A change is recorded with who made it and what it was before, and new requests pick it up. Evaluations run only the developer sets; held-out sets are never offered here.</p>
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
                <span class="mc-chip" :class="{ alert: !setting.wired }">{{ setting.wired ? "Used by the product" : "Stored only, not read yet" }}</span>
              </p>
            </div>
            <div class="how">
              <select v-if="setting.choices" :id="`set-${setting.key}`" v-model="drafts[setting.key]">
                <option v-for="choice in setting.choices" :key="choice" :value="choice">{{ choice }}</option>
              </select>
              <input v-else :id="`set-${setting.key}`" v-model="drafts[setting.key]" type="number" :min="setting.minimum ?? undefined" :max="setting.maximum ?? undefined" :step="setting.integer ? 1 : 'any'">
              <button type="button" class="mc-primary" :disabled="drafts[setting.key] === String(setting.value)" @click="ask(setting)">Change</button>
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

    <div class="ops-grid">
      <form class="ops-card run-form" aria-labelledby="run-title" @submit.prevent="runExperiment">
        <h2 id="run-title">Run an evaluation</h2>
        <label>Evaluation
          <select v-model="form.evaluation">
            <option v-for="item in evaluations" :key="item.name" :value="item.name">{{ item.label }}</option>
          </select>
        </label>
        <p v-if="chosen" class="ops-muted small">{{ chosen.description }} Dataset {{ chosen.dataset }}.</p>
        <label v-if="form.evaluation === 'developer-planning'">Planner
          <select v-model="form.planner">
            <option value="">MealCraft planner</option>
            <option value="greedy-baseline">Greedy baseline</option>
            <option value="rule-only-baseline">Rule-only baseline</option>
          </select>
        </label>
        <label v-else>Parser
          <select v-model="form.parser">
            <option value="">Current switch</option>
            <option value="fixture">Rule-based (fixture)</option>
            <option value="openai">OpenAI model (paid, runs in the background)</option>
          </select>
        </label>
        <label>Name (optional) <input v-model="form.label" maxlength="80" placeholder="e.g. before the budget change"></label>
        <p v-if="runError" class="ops-error" role="alert">{{ runError }}</p>
        <button type="submit" class="mc-primary" :disabled="running || !evaluations.length">{{ running ? "Running…" : "Run evaluation" }}</button>
      </form>

      <section class="ops-card" aria-labelledby="ab-title">
        <h2 id="ab-title">A/B comparison</h2>
        <p v-if="!runA || !runB" class="ops-muted">Choose run A and run B in the results below.</p>
        <template v-else>
          <p class="ops-muted small">A is #{{ runA.id }} {{ runA.label ?? "" }}, B is #{{ runB.id }} {{ runB.label ?? "" }}.<template v-if="runA.evaluation !== runB.evaluation"> They ran different evaluations, so most metrics do not line up.</template></p>
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
                <td class="mc-num" :class="deltaClass(row.delta)">{{ row.delta === null ? "—" : row.delta > 0 ? `+${row.delta}` : row.delta }}</td>
              </tr>
            </tbody>
          </table>
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
      <table v-else>
        <thead><tr><th>A</th><th>B</th><th>Run</th><th>Status</th><th>Headline</th><th>Gates</th><th>Time</th><th>When</th></tr></thead>
        <tbody>
          <tr v-for="run in experiments" :key="run.id">
            <td><input v-model="pickA" type="radio" name="pick-a" :value="run.id" :aria-label="`Use run ${run.id} as A`"></td>
            <td><input v-model="pickB" type="radio" name="pick-b" :value="run.id" :aria-label="`Use run ${run.id} as B`"></td>
            <td>#{{ run.id }} {{ evaluations.find(item => item.name === run.evaluation)?.label ?? run.evaluation }}<span v-if="run.label" class="ops-muted"> · {{ run.label }}</span></td>
            <td><span class="ops-badge" :style="{ '--dot': statusColor(run.status) }">{{ humanKey(run.status) }}</span><p v-if="run.error" class="ops-error small">{{ run.error }}</p></td>
            <td>{{ headline(run) }}</td>
            <td>{{ run.passed === null ? "—" : run.passed ? "Passed" : "Not passed" }}</td>
            <td class="mc-num">{{ formatSeconds(run.duration_seconds) }}</td>
            <td class="ops-muted">{{ formatWhen(run.created_at) }}</td>
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
  </div>
</template>

<style scoped>
.switches { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.switches li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 20px; padding: 14px 0; border-bottom: 1px solid var(--line); }
.switches li:last-child { border-bottom: 0; }
.what { flex: 1 1 320px; min-width: 0; }
.what label { color: var(--ivory); font-size: 14px; }
.what p { margin: 4px 0 0; font-size: 12.5px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; }
.how { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
select, input:not([type="radio"]) { padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 10px; background: var(--s2); color: var(--ivory); font: inherit; font-size: 13px; }
.how select, .how input { width: 150px; }
.small { font-size: 12px; }
.table-card { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 10px 12px; border-bottom: 1px solid var(--line-2); color: var(--t3); font-weight: 500; text-align: left; white-space: nowrap; }
td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
td p { margin: 4px 0 0; }
.run-form { display: grid; gap: 12px; align-content: start; }
.run-form label { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
.run-form p { margin: 0; }
.run-form .mc-primary { justify-self: start; }
.results-head { display: flex; align-items: center; justify-content: space-between; }
.results-head h2 { margin: 0; }
h3 { margin: 16px 0 8px; color: var(--t2); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.config-diff { margin: 0; padding-left: 18px; font-size: 13px; }
.config-diff b { color: var(--accent); font-weight: 500; }
.metrics { margin-top: 14px; }
.metrics tbody th { color: var(--t2); font-weight: 400; white-space: normal; }
.moved { color: var(--accent); }
</style>
