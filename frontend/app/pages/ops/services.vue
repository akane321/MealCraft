<script setup lang="ts">
import { formatWhen, humanKey } from "~/lib/ops";
import type { OpsServiceCheck, OpsServiceName, OpsServiceStatus } from "~/types/ops";

// What one live check costs, so nobody spends YouTube quota without knowing.
const CHECK_COST: Record<OpsServiceName, string> = {
  openai: "Reads the configured model's record: no tokens are used.",
  fairprice: "Runs one product search for rice.",
  youtube: "Runs one search: about 101 of the 10,000 daily quota units.",
};

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const services = ref<OpsServiceStatus[] | null>(null);
const failed = ref(false);
const checking = ref<OpsServiceName | null>(null);
const results = ref<Partial<Record<OpsServiceName, OpsServiceCheck | "failed">>>({});

async function load() {
  failed.value = false;
  try {
    services.value = (await apiFetch<{ items: OpsServiceStatus[] }>(`${config.public.apiBase}/api/ops/services`)).items;
  }
  catch {
    failed.value = true;
  }
}
onMounted(load);

function outcome(name: OpsServiceName) {
  const result = results.value[name];
  return result && result !== "failed" ? result : null;
}

async function check(name: OpsServiceName) {
  checking.value = name;
  try {
    results.value[name] = await apiFetch<OpsServiceCheck>(`${config.public.apiBase}/api/ops/services/${name}/check`, { method: "POST" });
  }
  catch {
    results.value[name] = "failed";
  }
  finally {
    checking.value = null;
  }
}
</script>

<template>
  <div class="ops-page">
    <header>
      <h1 class="mc-serif">Outside services</h1>
      <p>Keys stay in the server environment; the console only says whether one is set. Recent numbers come from runs stored in the last week.</p>
    </header>

    <div v-if="failed" class="ops-card" role="alert">
      <p class="ops-error">Service status couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="load">Try again</button>
    </div>
    <p v-else-if="!services" class="ops-muted" aria-busy="true">Loading services…</p>

    <div v-else class="cards">
      <section v-for="service in services" :key="service.name" class="ops-card service" :aria-labelledby="`svc-${service.name}`">
        <header>
          <h2 :id="`svc-${service.name}`">{{ service.label }}</h2>
          <span class="ops-badge" :class="service.configured ? 'success' : 'neutral'">{{ service.configured ? "Configured" : "Not configured" }}</span>
        </header>
        <!-- Non-breaking hyphens keep a model id such as gpt-5.4-mini on one line. -->
        <p class="ops-muted mode">Mode: {{ service.mode.replaceAll("-", "‑") }}</p>

        <dl v-if="service.recent" class="recent">
          <div><dt>Runs</dt><dd class="mc-num">{{ service.recent.runs }}</dd></div>
          <div v-if="service.recent.model_calls !== null"><dt>Model calls</dt><dd class="mc-num">{{ service.recent.model_calls }}</dd></div>
          <div><dt>Failures</dt><dd class="mc-num" :class="{ bad: service.recent.failures }">{{ service.recent.failures }}</dd></div>
          <div><dt>Fallbacks</dt><dd class="mc-num" :class="{ bad: service.recent.fallbacks }">{{ service.recent.fallbacks }}</dd></div>
        </dl>
        <p v-if="service.note" class="ops-muted svc-note">{{ service.note }}</p>

        <footer>
          <button type="button" class="mc-pill sm" :disabled="checking !== null" :aria-busy="checking === service.name" @click="check(service.name)">
            {{ checking === service.name ? "Checking…" : "Run live check" }}
          </button>
          <p class="ops-muted cost">{{ CHECK_COST[service.name] }}</p>
        </footer>
        <!-- The check's answer gets the card's whole width, under everything else. -->
        <p v-if="results[service.name] === 'failed'" class="result" role="status">The check itself couldn't be run.</p>
        <p v-else-if="outcome(service.name)" class="result" :class="{ ok: outcome(service.name)!.ok }" role="status">
          <template v-if="outcome(service.name)!.ok">Answered in {{ outcome(service.name)!.latency_ms }} ms.</template>
          <template v-else>Failed ({{ humanKey(outcome(service.name)!.error_kind ?? "error") }}) after {{ outcome(service.name)!.latency_ms }} ms.</template>
          {{ outcome(service.name)!.detail }}
          <span class="ops-muted">{{ formatWhen(outcome(service.name)!.checked_at) }}</span>
        </p>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* One full-width row a service: name and mode, the recent figures, then the live check. */
.cards { display: grid; gap: 12px; }
/* Name and mode, the figures, the check; the explanation and the check's answer run under them, full width. */
.service { display: grid; grid-template-columns: minmax(240px, 280px) minmax(0, 1fr) 220px; grid-template-areas: "head stats foot" "mode stats foot" "note note note" "result result result"; gap: 8px 24px; align-items: start; }
.service > header { grid-area: head; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.service .mode { grid-area: mode; }
.service .recent { grid-area: stats; }
.service .svc-note { grid-area: note; max-width: 72ch; margin-top: 4px !important; color: #71717a; font-size: 13px !important; line-height: 20px !important; }
.service .result { grid-area: result; }
.service h2 { margin: 0; }
.service p { margin: 0; font-size: 13px; line-height: 1.55; }
/* Recent numbers: four light tiles, label over value. */
.recent { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 0; }
.recent div { display: flex; flex-direction: column; padding: 10px 12px; border-radius: 10px; background: #fafafa; }
.recent dt { color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; white-space: nowrap; }
.recent dd { margin: 2px 0 0; color: var(--mc-strong); font-size: 18px; line-height: 24px; font-weight: 600; font-variant-numeric: tabular-nums; }
.recent dd.bad { color: #b42318; }
.service footer { grid-area: foot; display: grid; gap: 8px; padding-left: 24px; border-left: 1px solid #f0f0f2; }
.service footer .mc-pill { justify-self: start; }
.cost { color: #a1a1aa; font-size: 12px !important; }
/* The live check: soft red unless it answered. */
.result { padding: 10px 14px; border: 1px solid #fecdca; border-radius: 12px; background: #fef3f2; color: #b42318; }
.result.ok { border-color: #abefc6; background: #ecfdf3; color: #067647; }
.result span { display: block; margin-top: 2px; color: inherit; font-size: 12px; opacity: 0.8; }
</style>
