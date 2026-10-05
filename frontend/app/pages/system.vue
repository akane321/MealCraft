<script setup lang="ts">
import { isConsoleAccount } from "~/lib/ops";
import { createServiceStatuses, pricesLine } from "~/lib/system-status";

useHead({ title: "Service status · MealCraft" });

const config = useRuntimeConfig();
const { actor } = useAuth();
const household = useHouseholdProfile();
const { data, refresh, status } = await useBackendStatus();

const services = computed(() => createServiceStatuses(data.value?.health));
// Said only once the check has answered: a check still running is neither.
const healthy = computed(() => status.value === "pending" || services.value.every(row => row.healthy));
const prices = computed(() => pricesLine(household.current.value?.current.pricing_mode));
// Version, environment and the API's own pages are for whoever runs MealCraft, not for the household.
const isAdmin = computed(() => isConsoleAccount(actor.value));
const apiDocumentationUrl = computed(() => `${config.public.apiBase}/docs`);
const healthCheckUrl = computed(() => `${config.public.apiBase}/api/health`);

// Only once signed in: the household's own price choice. Signed out, the page still says what works.
watch(actor, (signedIn) => {
  if (signedIn && !household.current.value) void household.loadCurrent();
}, { immediate: true });
</script>

<template>
  <main class="page-width main-content">
    <section class="intro" aria-labelledby="page-title">
      <h1 id="page-title">Service status</h1>
      <p>
        {{ status === "pending" ? "Checking…" : healthy ? "Everything is working." : "Part of MealCraft isn't working right now. Your saved weeks are safe; try again in a moment." }}
      </p>
    </section>

    <section class="status-panel" aria-label="What works right now">
      <div class="status-table" role="table" aria-label="What works right now">
        <div v-for="service in services" :key="service.name" class="status-row" role="row">
          <span class="service-name" role="cell">{{ service.name }}</span>
          <span :class="['service-state', { unavailable: !service.healthy }]" role="cell">
            <svg v-if="service.healthy" aria-hidden="true" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="9" />
              <path d="m8.5 12 2.2 2.2 4.8-5" />
            </svg>
            <svg v-else aria-hidden="true" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 7.5v5" />
              <path d="M12 16.5h.01" />
            </svg>
            {{ status === "pending" ? "Checking" : service.state }}
          </span>
        </div>
        <div class="status-row" role="row">
          <span class="service-name" role="cell">Prices on your shopping list</span>
          <span class="prices" role="cell">{{ prices }}</span>
        </div>
      </div>

      <div v-if="isAdmin || !healthy" class="technical-details">
        <div v-if="isAdmin" class="detail-copy">
          <h2>For administrators</h2>
          <dl>
            <div>
              <dt>API version</dt>
              <dd>{{ data?.info.version ?? "—" }}</dd>
            </div>
            <div>
              <dt>Environment</dt>
              <dd>{{ data?.info.environment ?? "—" }}</dd>
            </div>
          </dl>
        </div>

        <nav class="technical-links" :aria-label="isAdmin ? 'Administrator links' : 'Check again'">
          <template v-if="isAdmin">
            <NuxtLink to="/ops">Operations console</NuxtLink>
            <a :href="apiDocumentationUrl" target="_blank" rel="noreferrer">API documentation</a>
            <a :href="healthCheckUrl" target="_blank" rel="noreferrer">Raw health check</a>
          </template>
          <button v-if="!healthy" type="button" @click="refresh()">Check again</button>
        </nav>
      </div>
    </section>
  </main>
</template>

<style scoped>
.prices { color: var(--muted); font-size: 16px; line-height: 1.5; }
</style>
