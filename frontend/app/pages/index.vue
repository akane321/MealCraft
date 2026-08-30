<script setup lang="ts">
import { createServiceStatuses } from "~/lib/system-status";

const config = useRuntimeConfig();
const { data, error, refresh, status } = await useBackendStatus();

const services = computed(() => createServiceStatuses(data.value?.health));
const isHealthy = computed(() => services.value.every(service => service.healthy));
const apiDocumentationUrl = computed(() => `${config.public.apiBase}/docs`);
const healthCheckUrl = computed(() => `${config.public.apiBase}/api/health`);
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="page-width">
        <p class="brand-name">Dietary Planner MVP</p>
      </div>
    </header>

    <main class="page-width main-content">
      <section class="intro" aria-labelledby="page-title">
        <h1 id="page-title">Development environment</h1>
        <p>
          {{ isHealthy ? "The application services are ready and operating as expected." : "Some application services are currently unavailable." }}
        </p>
      </section>

      <section class="status-panel" aria-label="Application service status">
        <div class="status-table" role="table" aria-label="Services">
          <div class="status-row status-heading" role="row">
            <span role="columnheader">Service</span>
            <span role="columnheader">Status</span>
          </div>

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
              {{ status === "pending" && service.name !== "Frontend" ? "Checking" : service.state }}
            </span>
          </div>
        </div>

        <div class="technical-details">
          <div class="detail-copy">
            <h2>Technical details</h2>
            <dl>
              <div>
                <dt>API Version</dt>
                <dd>{{ data?.info.version ?? "—" }}</dd>
              </div>
              <div>
                <dt>Environment</dt>
                <dd>{{ data?.info.environment ?? "—" }}</dd>
              </div>
            </dl>
          </div>

          <nav class="technical-links" aria-label="Technical links">
            <a :href="apiDocumentationUrl" target="_blank" rel="noreferrer">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M6 3.5h8l4 4V20.5H6z" />
                <path d="M14 3.5v4h4" />
                <path d="M9 12h6M9 15.5h6" />
              </svg>
              Open API documentation
            </a>
            <a :href="healthCheckUrl" target="_blank" rel="noreferrer">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M3 13h4l2-6 4 11 2-6h6" />
              </svg>
              Run health check
            </a>
            <button v-if="error" type="button" @click="refresh()">Retry connection</button>
          </nav>
        </div>
      </section>
    </main>
  </div>
</template>
