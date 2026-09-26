<script setup lang="ts">
import { formatSeconds, formatWhen, humanKey, parseTaskKey, statusColor } from "~/lib/ops";
import type { OpsTaskCollection, OpsTaskDetail, OpsTaskSummary } from "~/types/ops";

const PAGE = 25;
const STATUSES = ["succeeded", "committed", "failed", "degraded", "needs_clarification", "preview_ready", "running", "queued", "cancelled"];

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const route = useRoute();
const router = useRouter();

const kind = ref("");
const status = ref("");
const since = ref("");
const offset = ref(0);
const page = ref<OpsTaskCollection | null>(null);
const listFailed = ref(false);

async function loadList() {
  listFailed.value = false;
  const query: Record<string, string | number> = { offset: offset.value, limit: PAGE };
  if (kind.value) query.type = kind.value;
  if (status.value) query.status = status.value;
  if (since.value) query.since = `${since.value}T00:00:00`;
  try {
    page.value = await apiFetch<OpsTaskCollection>(`${config.public.apiBase}/api/ops/tasks`, { query });
  }
  catch {
    listFailed.value = true;
  }
}
watch([kind, status, since], () => {
  offset.value = 0;
  loadList();
});
watch(offset, loadList);
onMounted(loadList);

// The open task lives in the URL (?task=planning-12), so a task can be linked and reopened.
const selected = computed(() => parseTaskKey(route.query.task));
const detail = ref<OpsTaskDetail | null>(null);
const detailFailed = ref(false);
watch(selected, async (key) => {
  detail.value = null;
  detailFailed.value = false;
  if (!key) return;
  try {
    detail.value = await apiFetch<OpsTaskDetail>(`${config.public.apiBase}/api/ops/tasks/${key.kind}/${key.id}`);
  }
  catch {
    detailFailed.value = true;
  }
}, { immediate: true });

function open(task: OpsTaskSummary) {
  router.push({ query: { ...route.query, task: `${task.kind}-${task.id}` } });
}
function close() {
  const { task: _task, ...rest } = route.query;
  router.push({ query: rest });
}
function onKey(event: KeyboardEvent) {
  if (event.key === "Escape" && selected.value) close();
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

const conversation = computed(() => {
  const messages = detail.value?.inputs?.conversation;
  return Array.isArray(messages) ? (messages as Array<{ role: string; content: string }>) : [];
});
const otherInputs = computed(() => {
  const { conversation: _conversation, ...rest } = detail.value?.inputs ?? {};
  return rest;
});
const traceSections = computed(() => Object.entries(detail.value?.trace ?? {}));
const validation = computed(() => {
  const value = detail.value?.validation;
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
});
</script>

<template>
  <div class="ops-page">
    <header>
      <p class="mc-eyebrow">Tasks</p>
      <h1 class="mc-serif">Every conversation turn and planning run</h1>
      <p>Open a task to see what it was asked, how it was understood, what the planner and validator did, and how long it took.</p>
    </header>

    <form class="filters" @submit.prevent>
      <label>Type
        <select v-model="kind">
          <option value="">All</option>
          <option value="agent">Assistant turns</option>
          <option value="planning">Planning runs</option>
        </select>
      </label>
      <label>Status
        <select v-model="status">
          <option value="">Any</option>
          <option v-for="item in STATUSES" :key="item" :value="item">{{ humanKey(item) }}</option>
        </select>
      </label>
      <label>Since
        <input v-model="since" type="date">
      </label>
    </form>

    <div v-if="listFailed" class="ops-card" role="alert">
      <p class="ops-error">The task list couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="loadList">Try again</button>
    </div>
    <p v-else-if="!page" class="ops-muted" aria-busy="true">Loading tasks…</p>
    <p v-else-if="!page.items.length" class="ops-card ops-muted">No tasks match these filters.</p>
    <section v-else class="ops-card table-card" aria-label="Tasks">
      <table>
        <thead>
          <tr><th>Task</th><th>Status</th><th>Source</th><th>Time</th><th>When</th></tr>
        </thead>
        <tbody>
          <tr v-for="task in page.items" :key="`${task.kind}-${task.id}`" :class="{ current: selected?.kind === task.kind && selected?.id === task.id }">
            <td><button type="button" class="task-link" @click="open(task)">{{ task.label }}</button></td>
            <td><span class="ops-badge" :style="{ '--dot': statusColor(task.status) }">{{ humanKey(task.status) }}</span></td>
            <td class="ops-muted">{{ task.provider_mode ?? "—" }}</td>
            <td class="mc-num">{{ formatSeconds(task.duration_seconds) }}</td>
            <td class="ops-muted">{{ formatWhen(task.created_at) }}</td>
          </tr>
        </tbody>
      </table>
      <footer class="pager">
        <span class="ops-muted">{{ offset + 1 }}–{{ offset + page.items.length }} of {{ page.total }}</span>
        <button type="button" class="mc-pill" :disabled="offset === 0" @click="offset = Math.max(0, offset - PAGE)">Newer</button>
        <button type="button" class="mc-pill" :disabled="offset + PAGE >= page.total" @click="offset += PAGE">Older</button>
      </footer>
    </section>

    <div v-if="selected" class="drawer-scrim" @click.self="close">
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="task-title">
        <header class="drawer-head">
          <div>
            <p class="mc-eyebrow">{{ selected.kind === "agent" ? "Assistant turn" : "Planning run" }} #{{ selected.id }}</p>
            <h2 id="task-title" class="mc-serif">{{ detail?.summary.label ?? "Loading…" }}</h2>
          </div>
          <button type="button" class="mc-pill" @click="close">Close</button>
        </header>

        <p v-if="detailFailed" class="ops-error" role="alert">This task couldn't be loaded. It may have been removed.</p>
        <template v-else-if="detail">
          <div class="chips">
            <span class="ops-badge" :style="{ '--dot': statusColor(detail.summary.status) }">{{ humanKey(detail.summary.status) }}</span>
            <span class="mc-chip">Source <b>{{ detail.summary.provider_mode ?? "—" }}</b></span>
            <span class="mc-chip">Time <b>{{ formatSeconds(detail.summary.duration_seconds) }}</b></span>
            <span v-if="detail.summary.error_code" class="mc-chip alert">{{ detail.summary.error_code }}</span>
          </div>

          <section v-if="detail.error_detail" aria-labelledby="sec-error">
            <h3 id="sec-error">What went wrong</h3>
            <p class="ops-error">{{ detail.error_detail }}</p>
          </section>

          <section aria-labelledby="sec-inputs">
            <h3 id="sec-inputs">Inputs and understood constraints</h3>
            <ol v-if="conversation.length" class="conversation">
              <li v-for="(message, index) in conversation" :key="index" :class="message.role"><b>{{ message.role }}</b>{{ message.content }}</li>
            </ol>
            <OpsFields :data="otherInputs" />
          </section>

          <section aria-labelledby="sec-validation">
            <h3 id="sec-validation">Validation</h3>
            <OpsFields v-if="validation" :data="validation" />
            <p v-else class="ops-muted">{{ selected.kind === "agent" ? "Assistant turns are not validated themselves; open the planning run they started." : "The validator did not run for this plan." }}</p>
          </section>

          <section aria-labelledby="sec-trace">
            <h3 id="sec-trace">Trace</h3>
            <p v-if="!traceSections.length" class="ops-muted">No trace was stored.</p>
            <details v-for="[name, value] in traceSections" :key="name">
              <summary>{{ humanKey(name) }}</summary>
              <pre>{{ JSON.stringify(value, null, 2) }}</pre>
            </details>
          </section>

          <section aria-labelledby="sec-evidence">
            <h3 id="sec-evidence">Evidence digests and versions</h3>
            <OpsFields :data="detail.evidence" />
          </section>

          <section aria-labelledby="sec-config">
            <h3 id="sec-config">{{ selected.kind === "agent" ? "Model configuration" : "Planner configuration" }}</h3>
            <OpsFields v-if="detail.model_configuration" :data="detail.model_configuration" />
            <p v-else class="ops-muted">This run recorded no configuration.</p>
          </section>

          <section aria-labelledby="sec-timings">
            <h3 id="sec-timings">Timings and budgets</h3>
            <OpsFields :data="detail.timings" />
          </section>

          <section v-if="detail.warnings.length" aria-labelledby="sec-warnings">
            <h3 id="sec-warnings">Warnings</h3>
            <ul><li v-for="(warning, index) in detail.warnings" :key="index">{{ warning }}</li></ul>
          </section>
        </template>
        <p v-else class="ops-muted" aria-busy="true">Loading the task…</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; gap: 14px; }
.filters label { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
.filters select, .filters input { min-width: 170px; padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 10px; background: var(--s2); color: var(--ivory); font: inherit; font-size: 13px; }
.table-card { padding: 0; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 12px 16px; border-bottom: 1px solid var(--line-2); color: var(--t3); font-weight: 500; text-align: left; white-space: nowrap; }
td { padding: 10px 16px; border-bottom: 1px solid var(--line); }
tr.current td { background: var(--s2); }
.task-link { padding: 0; border: 0; background: none; color: var(--ivory); text-align: left; }
.task-link:hover { color: var(--accent); }
.pager { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 12px 16px; }
.pager span { margin-right: auto; font-size: 12.5px; }
.drawer-scrim { position: fixed; inset: 0; z-index: 30; display: flex; justify-content: flex-end; background: rgba(14, 12, 10, 0.6); }
.drawer { width: min(720px, 100%); height: 100%; overflow-y: auto; padding: 24px; border-left: 1px solid var(--line-2); background: var(--s1); animation: mc-rise 320ms var(--ease) both; }
.drawer-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.drawer-head h2 { margin: 6px 0 0; font-size: 24px; font-weight: 300; }
.drawer section { margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--line); }
.drawer h3 { margin: 0 0 12px; color: var(--t2); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.conversation { display: grid; gap: 8px; margin: 0 0 14px; padding: 0; list-style: none; font-size: 13px; }
.conversation li { padding: 9px 12px; border-radius: 10px; background: var(--s2); }
.conversation li.user { background: var(--s3); }
.conversation b { display: block; margin-bottom: 2px; color: var(--t3); font-size: 11px; font-weight: 500; text-transform: uppercase; }
details { margin-bottom: 6px; border: 1px solid var(--line); border-radius: 10px; }
summary { padding: 9px 12px; color: var(--t2); cursor: pointer; font-size: 13px; }
details pre { margin: 0; max-height: 360px; overflow: auto; padding: 10px 12px; border-top: 1px solid var(--line); color: var(--t2); font-size: 11.5px; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
