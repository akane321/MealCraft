<script setup lang="ts">
import { formatPlanDate } from "~/lib/meal-plan-format";
import type { ServerClock } from "~/plugins/server-today";

// A simulated day (SIMULATED_TODAY, debugging and demos) is always visible, so it is never mistaken for today.
// Inside a panel's header bar it is a small badge; `floating` puts it at the top centre of a page with no bar.
defineProps<{ floating?: boolean }>();
const clock = useState<ServerClock | null>("server-clock");
const label = computed(() => {
  const value = clock.value?.simulated;
  if (!value || !clock.value) return null;
  const day = formatPlanDate(clock.value.today, { weekday: "short", day: "numeric", month: "short" });
  return value.includes("T") ? `${day}, ${value.slice(11, 16)}` : day;
});
</script>

<template>
  <span v-if="label" class="simulated-clock" :class="{ floating }" role="status"><UIcon name="i-lucide-clock" aria-hidden="true" />Simulated date: {{ label }} · for debugging</span>
</template>

<style scoped>
.simulated-clock { flex: none; height: 22px; display: inline-flex; align-items: center; gap: 6px; margin: 0; padding: 0 8px; border: 1px solid #fedf89; border-radius: 999px; background: #fffaeb; color: #b54708; font: 500 12px/16px var(--font-sans, Inter, ui-sans-serif, system-ui, sans-serif); white-space: nowrap; }
.simulated-clock .iconify { width: 12px; height: 12px; }
.floating { position: fixed; z-index: 1000; top: 8px; left: 50%; transform: translateX(-50%); box-shadow: 0 1px 2px rgba(16, 16, 20, 0.05); pointer-events: none; }
</style>
