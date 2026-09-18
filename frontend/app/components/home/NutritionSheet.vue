<script setup lang="ts">
import { formatPlanDate } from "~/lib/meal-plan-format";
import {
  chartPointCoordinates,
  cumulativeNutritionValues,
  lineSegments,
  nutritionMetrics,
  nutritionProgressPercentage,
  type NutritionMetric,
} from "~/lib/dashboard";
import type { MealPlanEntryStatus, NutritionDashboardDay, WeeklyNutritionDashboard } from "~/types/meal-plan";

// ADR-0017: cumulative actuals of completed dishes first, the current plan on
// the same scale, then labelled daily detail.
const props = defineProps<{ dashboard: WeeklyNutritionDashboard; updatingEntryId: number | null }>();
const emit = defineEmits<{ close: []; setStatus: [entryId: number, status: MealPlanEntryStatus] }>();

const metric = ref<NutritionMetric>("calories_kcal");
const definition = computed(() => nutritionMetrics.find(item => item.key === metric.value)!);
const chart = computed(() => {
  const done = cumulativeNutritionValues(props.dashboard.days, metric.value, "completed");
  const plan = cumulativeNutritionValues(props.dashboard.days, metric.value, "planned");
  const max = Math.max(...done, ...plan, 1);
  return {
    done: lineSegments(chartPointCoordinates(done, 640, 180, 24, max)),
    plan: lineSegments(chartPointCoordinates(plan, 640, 180, 24, max)),
    max: Math.round(max),
  };
});

function progress(key: NutritionMetric) {
  return nutritionProgressPercentage(
    props.dashboard.completed_nutrition_per_person[key],
    props.dashboard.planned_nutrition_per_person[key],
  );
}

function statusLabel(day: NutritionDashboardDay) {
  if (day.status === "completed") return "Actual";
  if (day.status === "skipped") return "Not counted";
  return "Planned";
}

function shortDate(value: string) {
  return formatPlanDate(value, { weekday: "short", day: "numeric" });
}
</script>

<template>
  <div class="mc-overlay" role="dialog" aria-modal="true" aria-label="Nutrition details" @keydown.esc="emit('close')">
    <section class="mc-ribbed panel">
      <header>
        <div>
          <h2 class="mc-serif">Nutrition this week</h2>
          <p>Per person · cooked dishes count as actual · general guidance, not medical advice</p>
        </div>
        <button type="button" class="mc-pill close" aria-label="Close nutrition details" @click="emit('close')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </header>

      <div class="metrics">
        <button
          v-for="item in nutritionMetrics"
          :key="item.key"
          type="button"
          class="mc-frost metric"
          :class="{ active: metric === item.key }"
          :aria-pressed="metric === item.key"
          @click="metric = item.key"
        >
          <span>{{ item.label }}</span>
          <strong class="mc-serif">{{ Math.round(dashboard.completed_nutrition_per_person[item.key]).toLocaleString("en-SG") }} {{ item.unit }}</strong>
          <small>of {{ Math.round(dashboard.planned_nutrition_per_person[item.key]).toLocaleString("en-SG") }} planned<template v-if="progress(item.key) !== null"> · {{ progress(item.key) }}%</template></small>
        </button>
      </div>

      <figure class="mc-frost chart">
        <figcaption>Cumulative {{ definition.label.toLowerCase() }} ({{ definition.unit }}), up to {{ chart.max.toLocaleString("en-SG") }}</figcaption>
        <svg viewBox="0 0 640 180" role="img" :aria-label="`Cumulative ${definition.label}: cooked against the current plan`">
          <polyline v-for="(points, index) in chart.plan" :key="`p${index}`" :points="points" class="plan" />
          <polyline v-for="(points, index) in chart.done" :key="`d${index}`" :points="points" class="done" />
        </svg>
        <p class="legend"><span><i class="done" />Cooked</span><span><i class="plan" />Current plan</span></p>
      </figure>

      <table class="mc-frost days">
        <caption class="visually-hidden">Nutrition per dinner</caption>
        <thead>
          <tr>
            <th scope="col">Day</th><th scope="col">Dinner</th><th scope="col">Counts as</th>
            <th v-for="item in nutritionMetrics" :key="item.key" scope="col">{{ item.label }}</th>
            <th scope="col"><span class="visually-hidden">Change status</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="day in dashboard.days" :key="day.entry_id" :class="day.status">
            <td>{{ shortDate(day.planned_date) }}</td>
            <td class="dish">{{ day.recipe.title }}</td>
            <td>{{ statusLabel(day) }}</td>
            <td v-for="item in nutritionMetrics" :key="item.key">{{ Math.round(day.nutrition_per_person[item.key]) }}</td>
            <td class="actions">
              <template v-if="day.status === 'planned'">
                <button type="button" class="mc-pill" :disabled="updatingEntryId === day.entry_id" @click="emit('setStatus', day.entry_id, 'completed')">Cooked</button>
                <button type="button" class="mc-pill" :disabled="updatingEntryId === day.entry_id" @click="emit('setStatus', day.entry_id, 'skipped')">Skip</button>
              </template>
              <button v-else type="button" class="mc-pill" :disabled="updatingEntryId === day.entry_id" @click="emit('setStatus', day.entry_id, 'planned')">Undo</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.panel { width: min(1040px, calc(100vw - 64px)); max-height: calc(100vh - 64px); overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
header { display: flex; align-items: flex-start; gap: 12px; }
header > div { flex-grow: 1; }
h2 { margin: 0; font-size: 26px; }
header p { margin: 4px 0 0; font-size: 12px; color: var(--mc-text-3); }
.close { width: 40px; height: 40px; padding: 0; display: flex; align-items: center; justify-content: center; }
svg { fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
.close svg { width: 16px; height: 16px; }
.metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.metric { padding: 12px; border-radius: 16px; text-align: left; display: flex; flex-direction: column; gap: 2px; color: var(--mc-ivory); }
.metric span { font-size: 12px; color: var(--mc-text-2); }
.metric strong { font-size: 20px; }
.metric small { font-size: 11px; color: var(--mc-text-3); }
.metric.active { outline: 1.5px solid var(--mc-accent); }
.chart { margin: 0; padding: 14px 16px; border-radius: 18px; }
.chart figcaption { font-size: 12px; color: var(--mc-text-2); }
.chart svg { width: 100%; height: 180px; }
.chart polyline { stroke-width: 2.5; }
.chart .done { stroke: var(--mc-ivory); }
.chart .plan { stroke: var(--mc-text-3); stroke-dasharray: 6 5; }
.legend { margin: 0; display: flex; gap: 16px; font-size: 11px; color: var(--mc-text-3); }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend i { width: 18px; height: 0; border-top: 2.5px solid var(--mc-ivory); }
.legend i.plan { border-top: 2.5px dashed var(--mc-text-3); }
.days { width: 100%; border-collapse: collapse; border-radius: 18px; overflow: hidden; font-size: 12px; }
.days th, .days td { padding: 9px 10px; text-align: right; border-bottom: 1px solid rgba(242, 237, 228, 0.08); }
.days th:nth-child(-n+3), .days td:nth-child(-n+3) { text-align: left; }
.days th { font-weight: 600; color: var(--mc-text-3); }
.days .dish { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.days tr.skipped td { color: var(--mc-text-3); }
.days .actions { white-space: nowrap; }
.days .actions button { min-height: 32px; padding: 0 12px; margin-left: 6px; font-size: 12px; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
