<script setup lang="ts">
import { formatSeconds, statusColor, statusesIn } from "~/lib/ops";
import type { OpsDayPoint, OpsOverview, OpsSeries } from "~/types/ops";

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const overview = ref<OpsOverview | null>(null);
const series = ref<OpsSeries | null>(null);
const failed = ref(false);

async function load() {
  failed.value = false;
  try {
    [overview.value, series.value] = await Promise.all([
      apiFetch<OpsOverview>(`${config.public.apiBase}/api/ops/overview`),
      apiFetch<OpsSeries>(`${config.public.apiBase}/api/ops/overview/series`),
    ]);
  }
  catch {
    failed.value = true;
  }
}
onMounted(load);

const days = computed(() => series.value?.days ?? []);
const labels = computed(() => days.value.map(day => day.day));
const sum = (pick: (day: OpsDayPoint) => number) => days.value.reduce((total, day) => total + pick(day), 0);
const count = (record: Record<string, number>) => Object.values(record).reduce((total, value) => total + value, 0);

function stacked(pick: (day: OpsDayPoint) => Record<string, number>) {
  return statusesIn(days.value, pick).map(status => ({
    name: status,
    color: statusColor(status),
    values: days.value.map(day => pick(day)[status] ?? 0),
  }));
}

const tiles = computed(() => {
  const planning = sum(day => count(day.planning_runs));
  const planningFailed = sum(day => day.planning_runs.failed ?? 0);
  const agentFailed = sum(day => (day.agent_runs.failed ?? 0) + (day.agent_runs.degraded ?? 0));
  return [
    { label: "Conversations", value: sum(day => day.agent_sessions), note: "started in 14 days" },
    { label: "Assistant turns", value: sum(day => count(day.agent_runs)), note: `${agentFailed} failed or degraded` },
    { label: "Planning runs", value: planning, note: `${planningFailed} failed` },
    { label: "In flight now", value: (overview.value?.runs.queued ?? 0) + (overview.value?.runs.running ?? 0), note: "queued or running" },
  ];
});

const modes = computed(() => {
  const entries = Object.entries(series.value?.provider_modes ?? {}).sort((a, b) => b[1] - a[1]);
  const top = Math.max(1, ...entries.map(([, value]) => value));
  return entries.map(([name, value]) => ({ name, value, share: value / top }));
});
const failures = computed(() => Object.entries(overview.value?.runs.failures_last_24_hours ?? {}));
</script>

<template>
  <div class="ops-page">
    <header>
      <p class="mc-eyebrow">Overview</p>
      <h1 class="mc-serif">The last two weeks</h1>
      <p>Counts come from stored runs only; a day with nothing recorded shows as empty, not as zero failures.</p>
    </header>

    <div v-if="failed" class="ops-card" role="alert">
      <p class="ops-error">The overview couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="load">Try again</button>
    </div>
    <p v-else-if="!series" class="ops-muted" aria-busy="true">Loading the overview…</p>

    <template v-else>
      <section class="tiles" aria-label="Totals">
        <div v-for="tile in tiles" :key="tile.label" class="ops-card tile">
          <span class="ops-muted">{{ tile.label }}</span>
          <strong class="mc-serif mc-num">{{ tile.value }}</strong>
          <span class="ops-muted">{{ tile.note }}</span>
        </div>
      </section>

      <div class="ops-grid">
        <section class="ops-card" aria-labelledby="chart-conversations">
          <h2 id="chart-conversations">Conversations started</h2>
          <OpsBars label="Conversations started per day" :days="labels" :series="[{ name: 'conversations', color: 'var(--accent)', values: days.map(day => day.agent_sessions) }]" />
        </section>
        <section class="ops-card" aria-labelledby="chart-agent">
          <h2 id="chart-agent">Assistant turns by outcome</h2>
          <OpsBars label="Assistant turns per day by status" :days="labels" :series="stacked(day => day.agent_runs)" />
        </section>
        <section class="ops-card" aria-labelledby="chart-planning">
          <h2 id="chart-planning">Planning runs by outcome</h2>
          <OpsBars label="Planning runs per day by status" :days="labels" :series="stacked(day => day.planning_runs)" />
        </section>
        <section class="ops-card" aria-labelledby="chart-latency">
          <h2 id="chart-latency">Planning time</h2>
          <OpsLines
            label="Median and 90th percentile planning time per day"
            :days="labels"
            :series="[
              { name: 'median', color: 'var(--sage)', values: days.map(day => day.planning_median_seconds) },
              { name: '90th percentile', color: 'var(--accent)', values: days.map(day => day.planning_p90_seconds) },
            ]"
          />
        </section>
      </div>

      <div class="ops-grid">
        <section class="ops-card" aria-labelledby="modes">
          <h2 id="modes">Price sources used by plans</h2>
          <p v-if="!modes.length" class="ops-muted">No plan recorded a price source in these two weeks.</p>
          <ul v-else class="modes">
            <li v-for="mode in modes" :key="mode.name">
              <span>{{ mode.name }}</span>
              <span class="meter"><i :style="{ width: `${mode.share * 100}%` }" /></span>
              <span class="mc-num">{{ mode.value }}</span>
            </li>
          </ul>
        </section>
        <section class="ops-card" aria-labelledby="recent">
          <h2 id="recent">Last 24 hours</h2>
          <p v-if="!failures.length" class="ops-muted">No failed runs.</p>
          <ul v-else class="modes">
            <li v-for="[code, value] in failures" :key="code"><span>{{ code }}</span><span /><span class="mc-num">{{ value }}</span></li>
          </ul>
          <p class="ops-muted versions">
            Latest recorded code {{ overview?.latest_recorded_versions.code_commit ?? "—" }},
            catalog {{ overview?.latest_recorded_versions.catalog_version ?? "—" }},
            products {{ overview?.latest_recorded_versions.product_snapshot_version ?? "—" }}.
            Median planning time today {{ formatSeconds(days.at(-1)?.planning_median_seconds) }}.
          </p>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; }
.tile { display: grid; gap: 4px; font-size: 12.5px; }
.tile strong { font-size: 36px; line-height: 1.1; color: var(--ivory); }
.modes { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
.modes li { display: grid; grid-template-columns: minmax(90px, 30%) 1fr auto; align-items: center; gap: 12px; }
.meter { height: 8px; border-radius: 999px; background: var(--s3); overflow: hidden; }
.meter i { display: block; height: 100%; border-radius: inherit; background: var(--accent); }
.versions { margin: 16px 0 0; font-size: 12.5px; line-height: 1.6; }
</style>
