<script setup lang="ts">
import {
  chartPointCoordinates,
  completedNutritionValues,
  lineSegments,
  nutritionMetrics,
  type NutritionMetric,
} from "~/lib/dashboard";
import { formatNutrition, formatPlanDate } from "~/lib/meal-plan-format";
import type { MealPlanEntryStatus } from "~/types/meal-plan";

useHead({ title: "Nutrition dashboard · MealCraft" });

const route = useRoute();
const router = useRouter();
const selectedMetric = ref<NutritionMetric>("calories_kcal");
const {
  dashboard,
  errorMessage,
  isLoading,
  loadDashboard,
  loadPlans,
  plans,
  updateStatus,
  updatingEntryId,
} = useNutritionDashboard();

const selectedMetricDefinition = computed(() => {
  const metric = nutritionMetrics.find(item => item.key === selectedMetric.value);
  if (!metric) throw new Error(`Unknown nutrition metric: ${selectedMetric.value}`);
  return metric;
});
const chartValues = computed(() => (
  dashboard.value ? completedNutritionValues(dashboard.value.days, selectedMetric.value) : []
));
const chartPoints = computed(() => chartPointCoordinates(chartValues.value));
const chartSegments = computed(() => lineSegments(chartPoints.value));
const selectedPlanId = computed(() => dashboard.value?.plan_id || null);

function queryPlanId(): number | null {
  const value = Array.isArray(route.query.plan) ? route.query.plan[0] : route.query.plan;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

async function selectPlan(event: Event) {
  const planId = Number((event.target as HTMLSelectElement).value);
  if (!planId) return;
  await loadDashboard(planId);
  await router.replace({ query: { ...route.query, plan: String(planId) } });
}

async function selectStatus(entryId: number, event: Event) {
  const status = (event.target as HTMLSelectElement).value as MealPlanEntryStatus;
  await updateStatus(entryId, status);
}

function statusLabel(status: MealPlanEntryStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

onMounted(async () => {
  await loadPlans(queryPlanId());
  if (dashboard.value && route.query.plan !== String(dashboard.value.plan_id)) {
    await router.replace({ query: { ...route.query, plan: String(dashboard.value.plan_id) } });
  }
});
</script>

<template>
  <main class="page-width dashboard-page">
    <header class="dashboard-heading">
      <div>
        <h1>Nutrition dashboard</h1>
        <p v-if="dashboard">{{ formatPlanDate(dashboard.start_date) }} — {{ formatPlanDate(dashboard.end_date) }} · per person</p>
        <p v-else>Track only the meals planned and completed inside MealCraft.</p>
      </div>
      <label v-if="plans.length" class="dashboard-plan-select">
        <span>Weekly plan</span>
        <select :value="selectedPlanId || ''" @change="selectPlan">
          <option v-for="plan in plans" :key="plan.id" :value="plan.id">
            #{{ plan.id }} · {{ formatPlanDate(plan.start_date) }} — {{ formatPlanDate(plan.end_date) }}
          </option>
        </select>
      </label>
    </header>

    <div v-if="errorMessage" class="notice-panel error-notice">{{ errorMessage }}</div>
    <div v-if="isLoading" class="dashboard-empty" aria-live="polite">Loading saved meal plans…</div>
    <section v-else-if="!dashboard" class="dashboard-empty">
      <h2>No weekly plan yet</h2>
      <p>Generate a seven-day plan before recording completed meals.</p>
      <NuxtLink class="primary-button" to="/weekly-plan">Create a weekly plan</NuxtLink>
    </section>

    <template v-else>
      <section class="dashboard-summary" aria-label="Weekly execution summary">
        <div class="dashboard-summary-primary">
          <span>Completed meals</span>
          <strong>{{ dashboard.status_counts.completed }} of {{ dashboard.days.length }}</strong>
        </div>
        <div class="dashboard-progress-summary">
          <span>Weekly progress</span>
          <div><progress :value="dashboard.completion_rate" max="100" /><strong>{{ Math.round(dashboard.completion_rate) }}%</strong></div>
        </div>
        <div><span>Calories</span><strong>{{ formatNutrition(dashboard.completed_nutrition_per_person.calories_kcal, "kcal") }}</strong></div>
        <div><span>Protein</span><strong>{{ formatNutrition(dashboard.completed_nutrition_per_person.protein_g, "g") }}</strong></div>
        <div><span>Carbohydrate</span><strong>{{ formatNutrition(dashboard.completed_nutrition_per_person.carbohydrate_g, "g") }}</strong></div>
        <div><span>Fat</span><strong>{{ formatNutrition(dashboard.completed_nutrition_per_person.fat_g, "g") }}</strong></div>
        <div><span>Sodium</span><strong>{{ formatNutrition(dashboard.completed_nutrition_per_person.sodium_mg, "mg") }}</strong></div>
        <div><span>Sugar</span><strong>{{ formatNutrition(dashboard.completed_nutrition_per_person.sugar_g, "g") }}</strong></div>
      </section>

      <section class="dashboard-analytics">
        <div class="nutrition-trend-panel">
          <div class="dashboard-section-heading">
            <div><h2>Daily nutrition</h2><p>Completed MealCraft dishes only</p></div>
            <div class="metric-tabs" aria-label="Nutrition metric">
              <button
                v-for="metric in nutritionMetrics"
                :key="metric.key"
                type="button"
                :class="{ active: selectedMetric === metric.key }"
                @click="selectedMetric = metric.key"
              >{{ metric.label }}</button>
            </div>
          </div>

          <div class="nutrition-chart">
            <svg viewBox="0 0 760 220" role="img" :aria-label="`${selectedMetricDefinition.label} by completed meal`">
              <line v-for="y in [28, 83, 138, 192]" :key="y" x1="28" :y1="y" x2="732" :y2="y" class="chart-grid-line" />
              <polyline
                v-for="segment in chartSegments"
                :key="segment"
                :points="segment"
                fill="none"
                :stroke="selectedMetricDefinition.color"
                stroke-width="3"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <g v-for="(point, index) in chartPoints" :key="index">
                <circle v-if="point.value !== null" :cx="point.x" :cy="point.y" r="5" :fill="selectedMetricDefinition.color" />
                <circle v-else :cx="point.x" cy="192" r="4" class="chart-empty-point" />
              </g>
            </svg>
            <div class="chart-day-labels">
              <span v-for="day in dashboard.days" :key="day.entry_id">{{ formatPlanDate(day.planned_date) }}</span>
            </div>
          </div>
          <p class="chart-note">Values are {{ selectedMetricDefinition.label.toLowerCase() }} per person ({{ selectedMetricDefinition.unit }}). Planned and skipped meals are shown as empty points.</p>
        </div>

        <aside class="completion-panel" aria-label="Completion status">
          <h2>Completion status</h2>
          <dl>
            <div class="completed"><dt>Completed</dt><dd>{{ dashboard.status_counts.completed }}</dd></div>
            <div class="skipped"><dt>Skipped</dt><dd>{{ dashboard.status_counts.skipped }}</dd></div>
            <div class="planned"><dt>Planned</dt><dd>{{ dashboard.status_counts.planned }}</dd></div>
          </dl>
          <div class="completion-ring" :style="{ '--completion': `${dashboard.completion_rate * 3.6}deg` }">
            <strong>{{ Math.round(dashboard.completion_rate) }}%</strong>
            <span>complete</span>
          </div>
          <p>Only completed planned dishes contribute to the nutrition totals.</p>
        </aside>
      </section>

      <section class="meal-checkin-section">
        <div class="dashboard-section-heading">
          <div><h2>Planned meals</h2><p>Update execution status without recording food outside this plan.</p></div>
        </div>
        <div class="meal-checkin-table">
          <div class="meal-checkin-header" aria-hidden="true"><span>Date</span><span>Recipe</span><span>Nutrition summary</span><span>Status</span></div>
          <article v-for="day in dashboard.days" :key="day.entry_id" class="meal-checkin-row">
            <time :datetime="day.planned_date">{{ formatPlanDate(day.planned_date) }}</time>
            <NuxtLink :to="`/recipes/${day.recipe.slug}`">{{ day.recipe.title }}</NuxtLink>
            <p>
              {{ formatNutrition(day.nutrition_per_person.calories_kcal, "kcal") }} ·
              {{ formatNutrition(day.nutrition_per_person.protein_g, "g protein") }} ·
              {{ formatNutrition(day.nutrition_per_person.sodium_mg, "mg sodium") }}
            </p>
            <label class="status-select" :class="day.status">
              <span class="sr-only">Status for {{ day.recipe.title }}</span>
              <select :value="day.status" :disabled="updatingEntryId === day.entry_id" @change="selectStatus(day.entry_id, $event)">
                <option value="planned">{{ statusLabel("planned") }}</option>
                <option value="completed">{{ statusLabel("completed") }}</option>
                <option value="skipped">{{ statusLabel("skipped") }}</option>
              </select>
            </label>
          </article>
        </div>
      </section>
    </template>
  </main>
</template>
