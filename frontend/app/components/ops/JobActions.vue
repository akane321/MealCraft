<script setup lang="ts">
import { formatWhen, isJobCancellable, jobIdempotencyKey, mayManageJobs, statusColor } from "~/lib/ops";
import type { OpsCatalogSource, OpsJob, OpsJobCancellation, OpsRunCollection, OpsRunSummary } from "~/types/ops";

const POLL_INTERVAL_MS = 2_000;

type PendingAction =
  | { kind: "enqueue"; idempotencyKey: string; source: OpsCatalogSource }
  | { kind: "cancel"; job: OpsRunSummary };

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const { actor } = useAuth();

const source = ref<OpsCatalogSource>("reference");
const jobs = ref<OpsRunSummary[]>([]);
const initialLoading = ref(true);
const refreshing = ref(false);
const listError = ref("");
const actionError = ref("");
const actionMessage = ref("");
const pending = ref<PendingAction | null>(null);
const acting = ref(false);
const cancellingId = ref<number | null>(null);
const retryEnqueue = ref<{ source: OpsCatalogSource; idempotencyKey: string } | null>(null);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const canManage = computed(() => mayManageJobs(actor.value));
const hasActiveJob = computed(() => jobs.value.some(job => isJobCancellable(job.status)));

async function loadJobs() {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    const page = await apiFetch<OpsRunCollection>(`${config.public.apiBase}/api/ops/runs`, {
      query: { type: "catalog_import", limit: 25 },
    });
    jobs.value = page.items;
    listError.value = "";
  }
  catch {
    listError.value = jobs.value.length
      ? "Job status could not be refreshed. The last recorded state is still shown."
      : "The job queue could not be loaded.";
  }
  finally {
    initialLoading.value = false;
    refreshing.value = false;
  }
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function updatePolling() {
  if (!hasActiveJob.value) return stopPolling();
  if (pollTimer === null) pollTimer = setInterval(loadJobs, POLL_INTERVAL_MS);
}

watch(hasActiveJob, updatePolling);
onMounted(async () => {
  await loadJobs();
  updatePolling();
});
onBeforeUnmount(stopPolling);

function openEnqueueConfirmation() {
  actionError.value = "";
  actionMessage.value = "";
  const previous = retryEnqueue.value;
  const idempotencyKey = previous?.source === source.value
    ? previous.idempotencyKey
    : jobIdempotencyKey(Date.now(), globalThis.crypto.randomUUID());
  pending.value = { kind: "enqueue", idempotencyKey, source: source.value };
}

function openCancelConfirmation(job: OpsRunSummary) {
  actionError.value = "";
  actionMessage.value = "";
  pending.value = { kind: "cancel", job };
}

function dismissConfirmation() {
  if (!acting.value) pending.value = null;
}

async function confirmAction() {
  const action = pending.value;
  if (!action) return;
  acting.value = true;
  actionError.value = "";
  actionMessage.value = "";
  try {
    if (action.kind === "enqueue") {
      retryEnqueue.value = { source: action.source, idempotencyKey: action.idempotencyKey };
      const result = await apiFetch<OpsJob>(`${config.public.apiBase}/api/ops/jobs`, {
        method: "POST",
        headers: { "Idempotency-Key": action.idempotencyKey },
        body: {
          name: "catalog_import",
          arguments: { source: action.source },
          confirm: true,
        },
      });
      retryEnqueue.value = null;
      actionMessage.value = result.created
        ? `Catalog import #${result.id} was queued.`
        : `Catalog import #${result.id} was already queued with this request key.`;
    }
    else {
      cancellingId.value = action.job.id;
      await apiFetch<OpsJobCancellation>(`${config.public.apiBase}/api/ops/jobs/${action.job.id}/cancel`, {
        method: "POST",
        body: { confirm: true },
      });
      actionMessage.value = `Cancellation recorded for job #${action.job.id}.`;
    }
    pending.value = null;
    await loadJobs();
  }
  catch (error) {
    pending.value = null;
    await loadJobs();
    if (action.kind === "cancel" && jobs.value.find(job => job.id === action.job.id)?.status === "cancelled") {
      actionMessage.value = `Cancellation recorded for job #${action.job.id}.`;
    }
    else {
      const detail = (error as { data?: { detail?: unknown } }).data?.detail;
      actionError.value = typeof detail === "string" ? detail : "The job action could not be completed.";
    }
  }
  finally {
    cancellingId.value = null;
    acting.value = false;
    updatePolling();
  }
}

const confirmation = computed(() => {
  if (pending.value?.kind === "enqueue") {
    const label = pending.value.source === "reference" ? "the reference catalog" : "release v2";
    return {
      title: "Queue catalog import?",
      message: `This adds a durable job to import ${label}. The worker may retry it, and the request is recorded in the audit history.`,
      action: "Queue job",
      danger: false,
    };
  }
  if (pending.value?.kind === "cancel") {
    return {
      title: `Cancel job #${pending.value.job.id}?`,
      message: "Cancellation is recorded as a new operation. The existing run history remains available and cannot be rewritten.",
      action: "Cancel job",
      danger: true,
    };
  }
  return null;
});
</script>

<template>
  <section class="ops-card job-actions" aria-labelledby="job-actions-title">
    <div class="job-heading">
      <div>
        <p class="mc-eyebrow">Durable worker</p>
        <h2 id="job-actions-title">Catalog jobs</h2>
        <p class="ops-muted">Queue a named import and watch the separate worker claim it. Only recorded job types and sources are accepted.</p>
      </div>
      <button type="button" class="mc-pill" :disabled="refreshing" @click="loadJobs">
        {{ refreshing ? "Refreshing…" : "Refresh" }}
      </button>
    </div>

    <form v-if="canManage" class="queue-form" @submit.prevent="openEnqueueConfirmation">
      <label>Catalog source
        <select v-model="source">
          <option value="reference">Reference catalog</option>
          <option value="release_v2">Release v2</option>
        </select>
      </label>
      <button type="submit" class="mc-primary" :disabled="acting">Queue catalog import</button>
    </form>
    <p v-else class="read-only-note">Your console role can inspect jobs but cannot queue or cancel them.</p>

    <p v-if="actionMessage" class="ops-success" role="status" aria-live="polite">{{ actionMessage }}</p>
    <p v-if="actionError" class="ops-error" role="alert">{{ actionError }}</p>
    <p v-if="listError" class="ops-error" role="status">{{ listError }}</p>
    <p v-if="initialLoading" class="ops-muted" aria-busy="true">Loading catalog jobs…</p>
    <p v-else-if="!jobs.length" class="empty-jobs ops-muted">No catalog job has been recorded yet.</p>
    <div v-else class="job-table">
      <table>
        <thead><tr><th>Job</th><th>Status</th><th>Attempts</th><th>Queued</th><th>Action</th></tr></thead>
        <tbody>
          <tr v-for="job in jobs" :key="job.id">
            <td>
              <b>Catalog import #{{ job.id }}</b>
              <span class="trace" :title="job.trace_id">{{ job.trace_id }}</span>
            </td>
            <td>
              <span class="ops-badge" :style="{ '--dot': statusColor(cancellingId === job.id ? 'cancelled' : job.status) }">
                {{ cancellingId === job.id ? "Cancellation requested" : job.status.replaceAll("_", " ") }}
              </span>
              <span v-if="job.error_code" class="error-code">{{ job.error_code }}</span>
            </td>
            <td class="mc-num">{{ job.attempt_count }}</td>
            <td class="ops-muted">{{ formatWhen(job.created_at) }}</td>
            <td>
              <button
                v-if="canManage && isJobCancellable(job.status)"
                type="button"
                class="mc-pill cancel-job"
                :disabled="acting"
                :aria-label="`Cancel job ${job.id}`"
                @click="openCancelConfirmation(job)"
              >Cancel</button>
              <span v-else class="ops-muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <OpsConfirm
      v-if="confirmation"
      :title="confirmation.title"
      :message="confirmation.message"
      :action="confirmation.action"
      :danger="confirmation.danger"
      :busy="acting"
      @confirm="confirmAction"
      @cancel="dismissConfirmation"
    />
  </section>
</template>

<style scoped>
.job-actions { display: grid; gap: 16px; }
.job-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.job-heading h2 { margin: 5px 0 6px; }
.job-heading p { margin: 0; max-width: 72ch; font-size: 13px; line-height: 1.5; }
.queue-form { display: flex; align-items: end; gap: 12px; padding: 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--s2); }
.queue-form label { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
.queue-form select { min-width: 210px; padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 10px; background: var(--s1); color: var(--ivory); }
.read-only-note, .empty-jobs { margin: 0; padding: 13px 14px; border: 1px solid var(--line); border-radius: 12px; background: var(--s2); font-size: 13px; }
.ops-success { margin: 0; color: var(--sage); }
.ops-error { margin: 0; }
.job-table { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 10px 12px; border-bottom: 1px solid var(--line-2); color: var(--t3); font-weight: 500; text-align: left; white-space: nowrap; }
td { padding: 11px 12px; border-bottom: 1px solid var(--line); vertical-align: middle; }
tbody tr:last-child td { border-bottom: 0; }
td b { display: block; font-weight: 550; }
.trace { display: block; max-width: 300px; overflow: hidden; color: var(--t3); font-family: ui-monospace, monospace; font-size: 10.5px; text-overflow: ellipsis; white-space: nowrap; }
.error-code { display: block; margin-top: 4px; color: var(--warn); font-size: 11px; }
.cancel-job { color: var(--warn); }
</style>
