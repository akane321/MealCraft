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
      <p class="mc-eyebrow">Services</p>
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
          <span class="ops-badge" :style="{ '--dot': service.configured ? 'var(--sage)' : 'var(--t4)' }">{{ service.configured ? "Configured" : "Not configured" }}</span>
        </header>
        <p class="ops-muted">Mode: {{ service.mode }}</p>

        <dl v-if="service.recent" class="recent">
          <div><dt>Calls</dt><dd class="mc-num">{{ service.recent.calls }}</dd></div>
          <div><dt>Failures</dt><dd class="mc-num" :class="{ bad: service.recent.failures }">{{ service.recent.failures }}</dd></div>
          <div><dt>Fallbacks</dt><dd class="mc-num" :class="{ bad: service.recent.fallbacks }">{{ service.recent.fallbacks }}</dd></div>
        </dl>
        <p v-if="service.note" class="ops-muted">{{ service.note }}</p>

        <footer>
          <button type="button" class="mc-primary" :disabled="checking !== null" @click="check(service.name)">
            {{ checking === service.name ? "Checking…" : "Run live check" }}
          </button>
          <p class="ops-muted cost">{{ CHECK_COST[service.name] }}</p>
          <p v-if="results[service.name] === 'failed'" class="ops-error" role="status">The check itself couldn't be run.</p>
          <p v-else-if="outcome(service.name)" class="result" :class="{ ok: outcome(service.name)!.ok }" role="status">
            <template v-if="outcome(service.name)!.ok">Answered in {{ outcome(service.name)!.latency_ms }} ms.</template>
            <template v-else>Failed ({{ humanKey(outcome(service.name)!.error_kind ?? "error") }}) after {{ outcome(service.name)!.latency_ms }} ms.</template>
            {{ outcome(service.name)!.detail }}
            <span class="ops-muted">{{ formatWhen(outcome(service.name)!.checked_at) }}</span>
          </p>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(320px, 100%), 1fr)); gap: 16px; }
.service { display: flex; flex-direction: column; gap: 12px; }
.service > header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.service h2 { margin: 0; }
.service p { margin: 0; font-size: 13px; line-height: 1.55; }
.recent { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0; }
.recent div { padding: 10px 12px; border-radius: 10px; background: var(--s2); }
.recent dt { color: var(--t3); font-size: 12px; }
.recent dd { margin: 2px 0 0; font-family: var(--serif); font-size: 24px; font-weight: 300; }
.recent dd.bad { color: var(--warn); }
.service footer { display: grid; gap: 8px; margin-top: auto; padding-top: 12px; border-top: 1px solid var(--line); }
.service footer .mc-primary { justify-self: start; }
.cost { font-size: 12px !important; }
.result { padding: 10px 12px; border-radius: 10px; background: var(--warn-soft); color: var(--ivory); }
.result.ok { background: rgba(169, 183, 154, 0.12); }
.result span { display: block; margin-top: 2px; font-size: 12px; }
</style>
