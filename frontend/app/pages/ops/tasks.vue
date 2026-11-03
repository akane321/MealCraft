<script setup lang="ts">
import { TASK_STATUSES, formatSeconds, formatWhen, humanKey, parseTaskKey, singaporeMidnight, statusColor } from "~/lib/ops";
import type { OpsReplay, OpsTaskCollection, OpsTaskDetail, OpsTaskSummary } from "~/types/ops";

const PAGE = 25;

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
  if (since.value) query.since = singaporeMidnight(since.value);
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
// Replay the open task through the current code and show the two results side by side.
const replaying = ref(false);
const replayError = ref("");
watch(selected, () => (replayError.value = ""));
async function replay() {
  if (!selected.value || selected.value.kind === "intake") return;
  replaying.value = true;
  replayError.value = "";
  try {
    const result = await apiFetch<OpsReplay>(`${config.public.apiBase}/api/ops/replay/${selected.value.kind}/${selected.value.id}`, { method: "POST", body: {} });
    await navigateTo({ path: "/ops/debugging", query: { replay: result.id } });
  }
  catch (error) {
    const detail = (error as { data?: { detail?: unknown } }).data?.detail;
    replayError.value = typeof detail === "string" ? detail : "The replay couldn't be run.";
  }
  finally {
    replaying.value = false;
  }
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
      <h1 class="mc-serif">Conversation, planning, and recipe intake traces</h1>
      <p>Open a task to inspect what the assistant or intake pipeline did, what the validator decided, and how long each stage took.</p>
    </header>

    <OpsJobActions />

    <form class="filters" @submit.prevent>
      <label>Type
        <select v-model="kind">
          <option value="">All</option>
          <option value="agent">Assistant turns</option>
          <option value="planning">Planning runs</option>
          <option value="intake">External recipe intake</option>
        </select>
      </label>
      <label>Status
        <select v-model="status">
          <option value="">Any</option>
          <option v-for="item in TASK_STATUSES" :key="item" :value="item">{{ humanKey(item) }}</option>
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
    <p v-else-if="!page.items.length" class="ops-card ops-muted ops-empty">No tasks match these filters.</p>
    <section v-else class="ops-card table-card" aria-label="Tasks">
      <table>
        <thead>
          <tr><th>Task</th><th>Status</th><th>Source</th><th class="mc-num">Time</th><th>When</th></tr>
        </thead>
        <tbody>
          <tr v-for="task in page.items" :key="`${task.kind}-${task.id}`" :class="{ current: selected?.kind === task.kind && selected?.id === task.id }">
            <td><button type="button" class="link" @click="open(task)">{{ task.label }}</button></td>
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
            <p class="mc-eyebrow">{{ selected.kind === "agent" ? "Assistant turn" : selected.kind === "intake" ? "External recipe intake" : "Planning run" }} #{{ selected.id }}</p>
            <h2 id="task-title" class="mc-serif">{{ detail?.summary.label ?? "Loading…" }}</h2>
          </div>
          <div class="drawer-actions">
            <button v-if="selected.kind !== 'intake'" type="button" class="mc-primary" :disabled="replaying || !detail" :aria-busy="replaying" @click="replay">{{ replaying ? "Replaying…" : "Replay" }}</button>
            <button type="button" class="mc-close" aria-label="Close" @click="close"><UIcon name="i-lucide-x" aria-hidden="true" /></button>
          </div>
        </header>
        <p v-if="replayError" class="ops-error" role="alert">{{ replayError }}</p>

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
            <p v-else class="ops-muted">{{ selected.kind === "agent" ? "Assistant turns are not validated themselves; open the planning run they started." : selected.kind === "intake" ? "No admission decision was recorded." : "The validator did not run for this plan." }}</p>
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
            <h3 id="sec-config">{{ selected.kind === "agent" ? "Model configuration" : selected.kind === "intake" ? "Intake configuration" : "Planner configuration" }}</h3>
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
.filters { display: flex; flex-wrap: wrap; gap: 12px; }
.filters :is(select, input) { min-width: 180px; }
.drawer-head + .chips { margin-bottom: 4px; }
.conversation { display: grid; gap: 8px; margin: 0 0 14px; padding: 0; list-style: none; font-size: 13px; }
.conversation li { padding: 9px 12px; border: 1px solid #f2f2f4; border-radius: 10px; background: #fafafa; }
.conversation li.user { border-color: #ede9fe; background: #faf8ff; }
.conversation b { display: block; margin-bottom: 2px; color: #71717a; font-size: 12px; font-weight: 500; text-transform: capitalize; }
details { margin-bottom: 6px; border: 1px solid #ececef; border-radius: 10px; }
summary { padding: 9px 12px; color: #27272a; cursor: pointer; font-size: 13px; font-weight: 500; }
.drawer details pre { border: 0; border-top: 1px solid #ececef; border-radius: 0 0 10px 10px; }
</style>
