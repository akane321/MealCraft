<script setup lang="ts">
import { MEAL_LABEL } from "~/lib/home-surface";
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
// the same scale, then labelled daily detail, one row a dish in the order the backend gives: by day, then meal.
// A replaced week (readonly) is only read: its dishes can no longer be marked.
const props = defineProps<{ dashboard: WeeklyNutritionDashboard; updatingEntryId: number | null; readonly?: boolean }>();
const emit = defineEmits<{ close: []; setStatus: [entryId: number, status: MealPlanEntryStatus] }>();

const metric = ref<NutritionMetric>("calories_kcal");
// The plot is drawn at the card's own width, so the series fills it rather than sitting in the middle.
const plot = ref<SVGSVGElement | null>(null);
const width = ref(640);
let observer: ResizeObserver | undefined;
onMounted(() => {
  observer = new ResizeObserver(([entry]) => { width.value = Math.max(320, Math.round(entry!.contentRect.width)); });
  if (plot.value) observer.observe(plot.value);
});
onBeforeUnmount(() => observer?.disconnect());
const definition = computed(() => nutritionMetrics.find(item => item.key === metric.value)!);
// The chart runs through the days in calendar order (a day's meals keep their order), so each day is labelled once.
const ordered = computed(() => [...props.dashboard.days].sort((a, b) => a.planned_date.localeCompare(b.planned_date)));
const chart = computed(() => {
  const done = cumulativeNutritionValues(ordered.value, metric.value, "completed");
  const plan = cumulativeNutritionValues(ordered.value, metric.value, "planned");
  const max = Math.max(...done, ...plan, 1);
  const donePoints = chartPointCoordinates(done, width.value, 180, 24, max);
  const planPoints = chartPointCoordinates(plan, width.value, 180, 24, max);
  // One tick a day, under the day's first dish.
  const ticks = planPoints.flatMap((point, index) => {
    const date = ordered.value[index]?.planned_date;
    return date && date !== ordered.value[index - 1]?.planned_date ? [{ x: point.x, label: formatPlanDate(date, { weekday: "short" }) }] : [];
  });
  return {
    done: lineSegments(donePoints),
    plan: lineSegments(planPoints),
    // A one-dish plan has a single point and so no line: it is drawn as a dot.
    doneDots: donePoints.length === 1 ? donePoints : [],
    planDots: planPoints.length === 1 ? planPoints : [],
    max: Math.round(max),
    ticks,
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

const overlay = ref<HTMLElement | null>(null);
useDialog(overlay, () => emit("close"));
</script>

<template>
  <div ref="overlay" class="mc-overlay" role="dialog" aria-modal="true" aria-label="Nutrition details">
    <section class="mc-panel panel">
      <header class="mc-sheet-head">
        <div>
          <h2>Nutrition</h2>
          <p>Per person · cooked dishes count as actual · general guidance, not medical advice</p>
        </div>
        <button type="button" class="mc-close" aria-label="Close nutrition details" @click="emit('close')">
          <UIcon name="i-lucide-x" aria-hidden="true" />
        </button>
      </header>

      <div class="metrics">
        <button
          v-for="item in nutritionMetrics"
          :key="item.key"
          type="button"
          class="metric"
          :class="{ active: metric === item.key }"
          :aria-pressed="metric === item.key"
          @click="metric = item.key"
        >
          <span>{{ item.label }}</span>
          <strong>{{ Math.round(dashboard.completed_nutrition_per_person[item.key]).toLocaleString("en-SG") }} {{ item.unit }}</strong>
          <small>of {{ Math.round(dashboard.planned_nutrition_per_person[item.key]).toLocaleString("en-SG") }} planned<template v-if="progress(item.key) !== null"> · {{ progress(item.key) }}%</template></small>
        </button>
      </div>

      <figure class="chart">
        <figcaption>Cumulative {{ definition.label.toLowerCase() }} ({{ definition.unit }}), up to {{ chart.max.toLocaleString("en-SG") }}</figcaption>
        <svg ref="plot" :viewBox="`0 0 ${width} 180`" role="img" :aria-label="`Cumulative ${definition.label}: cooked against the current plan`">
          <line v-for="y in [24, 90, 156]" :key="`g${y}`" x1="0" :x2="width" :y1="y" :y2="y" class="grid" />
          <text v-for="(y, index) in [24, 90, 156]" :key="`y${y}`" x="0" :y="y - 5" class="axis">{{ Math.round(chart.max * (2 - index) / 2).toLocaleString("en-SG") }}</text>
          <text v-for="tick in chart.ticks" :key="`x${tick.x}`" :x="tick.x" y="176" text-anchor="middle" class="axis">{{ tick.label }}</text>
          <polyline v-for="(points, index) in chart.plan" :key="`p${index}`" :points="points" class="plan" />
          <polyline v-for="(points, index) in chart.done" :key="`d${index}`" :points="points" class="done" />
          <circle v-for="(point, index) in chart.planDots" :key="`pd${index}`" :cx="point.x" :cy="point.y" r="5" class="plan-dot" />
          <circle v-for="(point, index) in chart.doneDots" :key="`dd${index}`" :cx="point.x" :cy="point.y" r="4" class="done-dot" />
        </svg>
        <p class="legend"><span><i class="done" />Cooked</span><span><i class="plan" />Current plan</span></p>
      </figure>

      <div class="table-card">
      <table class="days">
        <caption class="visually-hidden">Nutrition per dish</caption>
        <thead>
          <tr>
            <th scope="col">Day</th><th scope="col">Meal</th><th scope="col">Dish</th><th scope="col">Counts as</th>
            <th v-for="item in nutritionMetrics" :key="item.key" scope="col">{{ item.label }}</th>
            <th v-if="!readonly" scope="col"><span class="visually-hidden">Change status</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="day in dashboard.days" :key="day.entry_id" :class="day.status">
            <td class="nowrap">{{ shortDate(day.planned_date) }}</td>
            <td class="nowrap">{{ MEAL_LABEL[day.meal_type ?? "dinner"] }}</td>
            <td class="dish"><span :title="day.recipe.title">{{ day.recipe.title }}</span></td>
            <td class="nowrap">{{ statusLabel(day) }}</td>
            <td v-for="item in nutritionMetrics" :key="item.key">{{ Math.round(day.nutrition_per_person[item.key]) }}</td>
            <td v-if="!readonly" class="actions">
              <template v-if="day.status === 'planned'">
                <button type="button" class="mc-btn quiet" :disabled="updatingEntryId === day.entry_id" @click="emit('setStatus', day.entry_id, 'completed')">Cooked</button>
                <button type="button" class="mc-btn quiet" :disabled="updatingEntryId === day.entry_id" @click="emit('setStatus', day.entry_id, 'skipped')">Skip</button>
              </template>
              <button v-else type="button" class="mc-btn quiet" :disabled="updatingEntryId === day.entry_id" @click="emit('setStatus', day.entry_id, 'planned')">Undo</button>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.panel { width: min(1040px, calc(100vw - 64px)); max-height: calc(100vh - 64px); overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding: 0 24px 24px; }
.mc-sheet-head { margin: 0 -24px; }
.metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.metric { display: flex; flex-direction: column; gap: 2px; padding: 14px; border: 1px solid #ececef; border-radius: 12px; background: #fff; text-align: left; color: #27272a; box-shadow: var(--mc-shadow-xs); }
.metric:hover { border-color: #d4d4d8; }
.metric span { color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; }
.metric strong { color: var(--mc-strong); font-size: 20px; line-height: 28px; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
.metric small { color: #a1a1aa; font-size: 12px; line-height: 16px; }
.metric.active { border-color: #c4b5fd; background: #f5f3ff; }
.chart { margin: 0; padding: 14px 16px; border: 1px solid #ececef; border-radius: 12px; }
.chart figcaption { color: #71717a; font-size: 12px; font-weight: 500; }
.chart svg { display: block; width: 100%; height: 180px; margin-top: 8px; overflow: visible; }
.chart .axis { fill: #a1a1aa; font-size: 11px; }
.chart .grid { stroke: #f0f0f2; stroke-width: 1; vector-effect: non-scaling-stroke; }
.chart polyline { fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
.chart .done { stroke: #8b5cf6; }
.chart .plan { stroke: #c4b5fd; stroke-dasharray: 6 5; }
.chart .plan-dot { fill: #fff; stroke: #8b5cf6; stroke-width: 2; }
.chart .done-dot { fill: #8b5cf6; stroke: none; }
.legend { margin: 6px 0 0; display: flex; gap: 16px; color: #a1a1aa; font-size: 11px; }
.legend span { display: flex; align-items: center; gap: 6px; }
.legend i { width: 18px; height: 0; border-top: 2px solid #8b5cf6; }
.legend i.plan { border-top: 2px dashed #c4b5fd; }
.table-card { border: 1px solid #ececef; border-radius: 12px; overflow-x: auto; }
.days { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.days th { height: 36px; padding: 0 10px; border-bottom: 1px solid #ececef; background: #fafafa; color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; text-align: right; white-space: nowrap; }
.days td { height: 44px; padding: 10px 10px; border-bottom: 1px solid #f2f2f4; color: #27272a; font-size: 14px; line-height: 20px; text-align: right; }
.days tbody tr:last-child td { border-bottom: 0; }
.days tbody tr:hover td { background: #fafafb; }
.days th:nth-child(-n+4), .days td:nth-child(-n+4) { text-align: left; }
.days .nowrap { white-space: nowrap; }
.days .dish { font-variant-numeric: normal; }
.days .dish > span { display: block; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.days tr.skipped td { color: #a1a1aa; }
.days .actions { width: 1%; padding-block: 0; padding-right: 14px; white-space: nowrap; }
.days .actions button { height: 28px; padding: 0 8px; margin-left: 2px; border-radius: 8px; font-size: 13px; font-weight: 500; }
</style>
