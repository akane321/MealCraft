<script setup lang="ts">
import { formatPlanDate } from "~/lib/meal-plan-format";
import { shapeChangeSummary } from "~/lib/plan-shape";
import type { MealPlanReplanEvent, MealPlanReplanEventCollection } from "~/types/meal-plan";

const props = defineProps<{ planId: number | null }>();

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const events = ref<MealPlanReplanEvent[]>([]);

// Only changes that were actually applied belong in a history; a discarded
// suggestion never happened.
const applied = computed(() => events.value.filter(event => event.status === "applied"));

watch(() => props.planId, async (planId) => {
  events.value = [];
  if (!planId) return;
  try {
    const collection = await apiFetch<MealPlanReplanEventCollection>(
      `${config.public.apiBase}/api/plans/${planId}/events`,
    );
    events.value = collection.items;
  }
  catch {
    // A missing history is not worth interrupting the week for.
    events.value = [];
  }
}, { immediate: true });

function when(event: MealPlanReplanEvent) {
  return formatPlanDate((event.applied_at ?? event.created_at).slice(0, 10), { day: "numeric", month: "short" });
}

function kcal(event: MealPlanReplanEvent) {
  const value = Math.round(event.nutrition_delta.calories_kcal);
  return `${value >= 0 ? "+" : ""}${value} kcal`;
}

function money(event: MealPlanReplanEvent) {
  const value = event.purchase_total_delta_sgd;
  return `${value >= 0 ? "+" : "−"}S$${Math.abs(value).toFixed(2)}`;
}
</script>

<template>
  <details v-if="applied.length" class="changes">
    <summary>
      <span>Changes this week</span>
      <span class="count">{{ applied.length }}</span>
    </summary>
    <ol>
      <li v-for="event in applied" :key="event.id">
        <p v-if="event.shape_change" class="swap">
          <strong>{{ shapeChangeSummary(event.shape_change, day => `day ${day}`) }}</strong>
        </p>
        <p v-else-if="event.before_entry && event.after_entry" class="swap">
          <s>{{ event.before_entry.recipe_title }}</s>
          <span aria-hidden="true">→</span>
          <strong>{{ event.after_entry.recipe_title }}</strong>
        </p>
        <p class="meta">{{ when(event) }} · {{ kcal(event) }} · groceries {{ money(event) }}</p>
        <p v-if="event.reason" class="meta reason">{{ event.reason }}</p>
      </li>
    </ol>
  </details>
</template>

<style scoped>
.changes { margin: 4px 0 0; border-top: 1px solid var(--mc-line); padding-top: 12px; }
summary {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--mc-text-3);
}
summary::-webkit-details-marker { display: none; }
summary::before { content: "▸"; font-size: 10px; transition: transform 200ms var(--mc-ease); }
.changes[open] summary::before { transform: rotate(90deg); }
.count {
  margin-left: auto;
  padding: 1px 7px;
  border: 1px solid var(--mc-line);
  border-radius: 999px;
  font-size: 11px;
  letter-spacing: 0;
}
ol { margin: 12px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 12px; }
.swap { margin: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; font-size: 13px; color: var(--mc-text-2); }
.swap s { color: var(--mc-text-3); }
.swap strong { font-family: var(--mc-serif); font-weight: 400; color: var(--mc-ivory); }
.meta { margin: 3px 0 0; font-size: 12px; color: var(--mc-text-3); }
.reason { font-style: italic; }

@media (prefers-reduced-motion: reduce) {
  summary::before { transition: none; }
}
</style>
