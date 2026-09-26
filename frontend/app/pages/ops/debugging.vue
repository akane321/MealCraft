<script setup lang="ts">
import { diffFields, dishRows, formatSeconds, formatValue, formatWhen, humanKey, statusColor } from "~/lib/ops";
import type { OpsReplay, OpsReplaySummary } from "~/types/ops";

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const route = useRoute();
const router = useRouter();

const replays = ref<OpsReplaySummary[] | null>(null);
const listFailed = ref(false);
async function loadList() {
  listFailed.value = false;
  try {
    replays.value = (await apiFetch<{ items: OpsReplaySummary[] }>(`${config.public.apiBase}/api/ops/replays`)).items;
  }
  catch {
    listFailed.value = true;
  }
}
onMounted(loadList);

// The open replay lives in the URL (?replay=12), so the Tasks drawer can link straight to it.
const selectedId = computed(() => (typeof route.query.replay === "string" && /^\d+$/.test(route.query.replay) ? Number(route.query.replay) : null));
const replay = ref<OpsReplay | null>(null);
const replayFailed = ref(false);
watch(selectedId, async (id) => {
  replay.value = null;
  replayFailed.value = false;
  if (id === null) return;
  try {
    replay.value = await apiFetch<OpsReplay>(`${config.public.apiBase}/api/ops/replays/${id}`);
    resetOverrides();
  }
  catch {
    replayFailed.value = true;
  }
}, { immediate: true });

function open(id: number) {
  router.push({ query: { ...route.query, replay: id } });
}

const dishes = computed(() => dishRows(replay.value?.original?.dishes, replay.value?.replay.dishes));
const constraints = computed(() => diffFields(replay.value?.original?.constraints, replay.value?.replay.constraints));
const checks = (side: "original" | "replay") => {
  const found = replay.value?.[side]?.failed_checks ?? [];
  return found.length ? found.map(check => `${humanKey(check.code)}${check.status === "failed" ? "" : ` (${check.status})`}`).join(", ") : "none";
};
const money = (value: number | null | undefined) => (value === null || value === undefined ? "—" : `S$${value.toFixed(2)}`);

// Replay again with other settings. Empty fields keep what the stored run used.
const agentParser = ref("");
const planning = reactive({ planner_strategy: "", beam_width: "", max_expansions: "", pricing_mode: "", weekly_budget_sgd: "", planning_capability: "" });
function resetOverrides() {
  const overrides = replay.value?.overrides ?? {};
  agentParser.value = String(overrides.parser ?? "");
  for (const key of Object.keys(planning) as Array<keyof typeof planning>) planning[key] = overrides[key] === undefined ? "" : String(overrides[key]);
}
function overridesBody() {
  if (replay.value?.kind === "agent") return agentParser.value ? { parser: agentParser.value } : {};
  const numeric = new Set(["beam_width", "max_expansions", "weekly_budget_sgd"]);
  return Object.fromEntries(
    Object.entries(planning)
      .filter(([, value]) => value !== "")
      .map(([key, value]) => [key, numeric.has(key) ? Number(value) : value]),
  );
}
const running = ref(false);
const runError = ref("");
async function runAgain() {
  if (!replay.value) return;
  running.value = true;
  runError.value = "";
  try {
    const result = await apiFetch<OpsReplay>(`${config.public.apiBase}/api/ops/replay/${replay.value.kind}/${replay.value.source_id}`, { method: "POST", body: overridesBody() });
    await loadList();
    open(result.id);
  }
  catch (error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    runError.value = typeof detail === "string" ? detail : "The replay couldn't be run. Check the settings and try again.";
  }
  finally {
    running.value = false;
  }
}
</script>

<template>
  <div class="ops-page">
    <header>
      <p class="mc-eyebrow">Debugging</p>
      <h1 class="mc-serif">Replay a task and compare</h1>
      <p>A replay sends a stored conversation turn or planning run through today's code, with the settings you choose. Nothing is saved to anyone's household. Start one from a task in <NuxtLink to="/ops/tasks">Tasks</NuxtLink>.</p>
    </header>

    <div class="debug-grid">
      <section class="ops-card replay-list" aria-labelledby="replays-title">
        <h2 id="replays-title">Recent replays</h2>
        <p v-if="listFailed" class="ops-error" role="alert">The replay list couldn't be loaded.</p>
        <p v-else-if="!replays" class="ops-muted" aria-busy="true">Loading…</p>
        <p v-else-if="!replays.length" class="ops-muted">No replays yet. Open a task and choose Replay.</p>
        <ul v-else>
          <li v-for="item in replays" :key="item.id">
            <button type="button" :class="{ current: item.id === selectedId }" @click="open(item.id)">
              <span>{{ item.kind === "agent" ? "Assistant turn" : "Planning run" }} #{{ item.source_id }}</span>
              <span class="ops-muted small">{{ humanKey(item.original_status ?? "unknown") }} → {{ humanKey(item.replay_status ?? "unknown") }}</span>
              <span class="ops-muted small">{{ Object.keys(item.overrides).length ? Object.entries(item.overrides).map(([k, v]) => `${humanKey(k)} ${v}`).join(", ") : "Same settings" }} · {{ formatWhen(item.created_at) }}</span>
            </button>
          </li>
        </ul>
      </section>

      <section class="ops-card compare" aria-labelledby="compare-title">
        <p v-if="selectedId === null" class="ops-muted">Pick a replay to see the stored result beside the new one.</p>
        <p v-else-if="replayFailed" class="ops-error" role="alert">This replay couldn't be loaded.</p>
        <p v-else-if="!replay" class="ops-muted" aria-busy="true">Loading the replay…</p>
        <template v-else>
          <h2 id="compare-title">{{ replay.kind === "agent" ? "Assistant turn" : "Planning run" }} #{{ replay.source_id }}: stored and replayed</h2>

          <table class="side">
            <thead><tr><th /><th>Stored run</th><th>Replay</th></tr></thead>
            <tbody>
              <tr>
                <th>Result</th>
                <td><span class="ops-badge" :style="{ '--dot': statusColor(replay.original?.status ?? '') }">{{ humanKey(replay.original?.status ?? "unknown") }}</span></td>
                <td><span class="ops-badge" :style="{ '--dot': statusColor(replay.replay.status) }">{{ humanKey(replay.replay.status) }}</span></td>
              </tr>
              <template v-if="replay.kind === 'planning'">
                <tr><th>Evidence</th><td>{{ humanKey(replay.original?.evidence ?? "—") }}</td><td>{{ humanKey(replay.replay.evidence ?? "—") }}</td></tr>
                <tr :class="{ changed: replay.original?.total_cost_sgd !== replay.replay.total_cost_sgd }"><th>Total cost</th><td class="mc-num">{{ money(replay.original?.total_cost_sgd) }}</td><td class="mc-num">{{ money(replay.replay.total_cost_sgd) }}</td></tr>
                <tr><th>Checks not passed</th><td>{{ checks("original") }}</td><td>{{ checks("replay") }}</td></tr>
                <tr><th>Settings</th><td class="small">{{ formatValue(replay.original?.settings) }}</td><td class="small">{{ formatValue(replay.replay.settings) }}</td></tr>
                <tr v-if="replay.original?.message || replay.replay.message"><th>Message</th><td>{{ formatValue(replay.original?.message) }}</td><td>{{ formatValue(replay.replay.message) }}</td></tr>
              </template>
              <template v-else>
                <tr><th>Parser</th><td>{{ formatValue(replay.original?.parser) }}</td><td>{{ formatValue(replay.replay.parser) }}</td></tr>
                <tr :class="{ changed: replay.original?.assistant_message !== replay.replay.assistant_message }"><th>Reply</th><td>{{ formatValue(replay.original?.assistant_message ?? replay.original?.error) }}</td><td>{{ formatValue(replay.replay.assistant_message ?? replay.replay.error) }}</td></tr>
                <tr><th>Still missing</th><td>{{ formatValue(replay.original?.missing_fields) }}</td><td>{{ formatValue(replay.replay.missing_fields) }}</td></tr>
              </template>
              <tr><th>Time</th><td class="mc-num">{{ formatSeconds(replay.original?.duration_seconds) }}</td><td class="mc-num">{{ formatSeconds(replay.replay.duration_seconds) }}</td></tr>
            </tbody>
          </table>

          <template v-if="replay.kind === 'planning'">
            <h3>Dishes</h3>
            <p v-if="!dishes.length" class="ops-muted">Neither run produced a week.</p>
            <table v-else class="side">
              <thead><tr><th>Meal</th><th>Stored run</th><th>Replay</th></tr></thead>
              <tbody>
                <tr v-for="row in dishes" :key="row.slot" :class="{ changed: row.changed }"><th>{{ row.slot }}</th><td>{{ row.before ?? "—" }}</td><td>{{ row.after ?? "—" }}</td></tr>
              </tbody>
            </table>
          </template>
          <template v-else>
            <h3>What the message said</h3>
            <blockquote>{{ replay.original?.message }}</blockquote>
            <h3>Understood constraints</h3>
            <table class="side">
              <thead><tr><th>Field</th><th>Stored run</th><th>Replay</th></tr></thead>
              <tbody>
                <tr v-for="row in constraints" :key="row.key" :class="{ changed: row.changed }"><th>{{ humanKey(row.key) }}</th><td>{{ formatValue(row.before) }}</td><td>{{ formatValue(row.after) }}</td></tr>
              </tbody>
            </table>
          </template>

          <form class="overrides" @submit.prevent="runAgain">
            <h3>Replay again with other settings</h3>
            <p class="ops-muted small">Leave a field empty to keep what the stored run used.</p>
            <div v-if="replay.kind === 'agent'" class="fields">
              <label>Parser
                <select v-model="agentParser"><option value="">Current setting</option><option value="fixture">Rule-based (fixture)</option><option value="openai">OpenAI model</option></select>
              </label>
            </div>
            <div v-else class="fields">
              <label>Planner
                <select v-model="planning.planner_strategy"><option value="">As stored</option><option value="beam">Beam search</option><option value="greedy-baseline">Greedy baseline</option></select>
              </label>
              <label>Beam width <input v-model="planning.beam_width" type="number" min="1" max="512" placeholder="32"></label>
              <label>Search steps <input v-model="planning.max_expansions" type="number" min="1" max="1000000" placeholder="10000"></label>
              <label>Prices
                <select v-model="planning.pricing_mode"><option value="">As stored</option><option value="fixture">Fixture</option><option value="live">Live FairPrice</option></select>
              </label>
              <label>Weekly budget (S$) <input v-model="planning.weekly_budget_sgd" type="number" min="1" max="7000" step="0.01" placeholder="As stored"></label>
              <label>Capability
                <select v-model="planning.planning_capability"><option value="">Current setting</option><option value="mvp">MVP (one dish a meal)</option><option value="full">Full (several dishes)</option></select>
              </label>
            </div>
            <p v-if="runError" class="ops-error" role="alert">{{ runError }}</p>
            <button type="submit" class="mc-primary" :disabled="running">{{ running ? "Replaying…" : "Replay with these settings" }}</button>
          </form>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
header a { color: var(--accent); }
.debug-grid { display: grid; grid-template-columns: minmax(240px, 300px) 1fr; gap: 16px; align-items: start; }
.replay-list ul { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.replay-list button { display: grid; gap: 2px; width: 100%; padding: 10px 12px; border: 1px solid transparent; border-radius: 10px; background: none; color: var(--ivory); text-align: left; }
.replay-list button:hover { background: var(--s2); }
.replay-list button.current { border-color: var(--line-2); background: var(--s3); box-shadow: inset 2px 0 0 var(--accent); }
.small { font-size: 12px; }
.compare h3 { margin: 22px 0 10px; color: var(--t2); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
table.side { width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }
table.side th, table.side td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; overflow-wrap: anywhere; }
table.side thead th { color: var(--t3); font-weight: 500; }
table.side tbody th { width: 26%; color: var(--t3); font-weight: 400; }
table.side tr.changed td { background: rgba(232, 144, 111, 0.1); }
table.side tr.changed td:last-child { color: var(--accent); }
blockquote { margin: 0; padding: 10px 14px; border-left: 2px solid var(--accent); border-radius: 0 10px 10px 0; background: var(--s2); color: var(--ivory); }
.overrides { display: grid; gap: 10px; margin-top: 26px; padding-top: 6px; border-top: 1px solid var(--line); }
.overrides h3 { margin-bottom: 0; }
.overrides p { margin: 0; }
.fields { display: flex; flex-wrap: wrap; gap: 12px; }
.fields label { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
.fields select, .fields input { min-width: 150px; padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 10px; background: var(--s2); color: var(--ivory); font: inherit; font-size: 13px; }
.overrides .mc-primary { justify-self: start; }

@media (max-width: 900px) {
  .debug-grid { grid-template-columns: 1fr; }
}
</style>
