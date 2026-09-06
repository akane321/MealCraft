<script setup lang="ts">
import {
  chartPointCoordinates,
  cumulativeNutritionValues,
  lineSegments,
  nutritionMetrics,
  nutritionProgressPercentage,
  type NutritionMetric,
} from "~/lib/dashboard";
import { formatNutrition, formatPlanDate } from "~/lib/meal-plan-format";
import { eventTypeLabel, formatSigned, groceryDeltaSummary, replanEventOptions } from "~/lib/replanning";
import type {
  MealPlanEntryStatus,
  MealPlanEventType,
  NutritionDashboardDay,
} from "~/types/meal-plan";

useHead({ title: "Nutrition dashboard · MealCraft" });

const route = useRoute();
const router = useRouter();
const selectedMetric = ref<NutritionMetric>("calories_kcal");
const replanEntry = ref<NutritionDashboardDay | null>(null);
const replanForm = reactive({
  eventType: "REPLACE_MEAL" as MealPlanEventType,
  reason: "",
  unavailableIngredient: "",
});
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
const {
  clearPreview,
  confirmPreview,
  createPreview,
  errorMessage: replanError,
  events,
  isConfirming,
  isPreviewing,
  loadEvents,
  preview,
} = useMealReplanning();

const selectedMetricDefinition = computed(() => {
  const metric = nutritionMetrics.find(item => item.key === selectedMetric.value);
  if (!metric) throw new Error(`Unknown nutrition metric: ${selectedMetric.value}`);
  return metric;
});
const completedCumulativeValues = computed(() => (
  dashboard.value
    ? cumulativeNutritionValues(dashboard.value.days, selectedMetric.value, "completed")
    : []
));
const plannedCumulativeValues = computed(() => (
  dashboard.value
    ? cumulativeNutritionValues(dashboard.value.days, selectedMetric.value, "planned")
    : []
));
const cumulativeChartMaximum = computed(() => Math.max(
  ...completedCumulativeValues.value,
  ...plannedCumulativeValues.value,
  1,
));
const completedChartPoints = computed(() => chartPointCoordinates(
  completedCumulativeValues.value,
  760,
  220,
  28,
  cumulativeChartMaximum.value,
));
const plannedChartPoints = computed(() => chartPointCoordinates(
  plannedCumulativeValues.value,
  760,
  220,
  28,
  cumulativeChartMaximum.value,
));
const completedChartSegments = computed(() => lineSegments(completedChartPoints.value));
const plannedChartSegments = computed(() => lineSegments(plannedChartPoints.value));
const selectedPlanId = computed(() => dashboard.value?.plan_id || null);

function cumulativeProgress(metric: NutritionMetric): number | null {
  if (!dashboard.value) return null;
  return nutritionProgressPercentage(
    dashboard.value.completed_nutrition_per_person[metric],
    dashboard.value.planned_nutrition_per_person[metric],
  );
}

function queryPlanId(): number | null {
  const value = Array.isArray(route.query.plan) ? route.query.plan[0] : route.query.plan;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

async function selectPlan(event: Event) {
  const planId = Number((event.target as HTMLSelectElement).value);
  if (!planId) return;
  await loadDashboard(planId);
  await loadEvents(planId);
  closeReplan();
  await router.replace({ query: { ...route.query, plan: String(planId) } });
}

function openReplan(day: NutritionDashboardDay) {
  replanEntry.value = day;
  replanForm.eventType = "REPLACE_MEAL";
  replanForm.reason = "";
  replanForm.unavailableIngredient = "";
  clearPreview();
  nextTick(() => document.querySelector(".replan-workspace")?.scrollIntoView({ behavior: "smooth", block: "start" }));
}

function closeReplan() {
  replanEntry.value = null;
  clearPreview();
}

async function previewChange() {
  if (!dashboard.value || !replanEntry.value) return;
  await createPreview(dashboard.value.plan_id, {
    event_type: replanForm.eventType,
    entry_id: replanEntry.value.entry_id,
    reason: replanForm.reason.trim() || null,
    unavailable_ingredient: replanForm.eventType === "ITEM_UNAVAILABLE"
      ? replanForm.unavailableIngredient.trim()
      : null,
  });
}

async function applyPreview() {
  if (!dashboard.value) return;
  const result = await confirmPreview(dashboard.value.plan_id);
  if (!result) return;
  await loadDashboard(dashboard.value.plan_id);
  replanEntry.value = null;
}

function resetPreview() {
  clearPreview();
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
  if (dashboard.value) await loadEvents(dashboard.value.plan_id);
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
        <p v-if="dashboard">
          {{ formatPlanDate(dashboard.start_date) }} — {{ formatPlanDate(dashboard.end_date) }} · per person · revision {{ dashboard.revision }}
        </p>
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
      <section class="dashboard-summary" aria-label="Cumulative nutrition totals">
        <div class="dashboard-summary-intro">
          <span>Plan-based actuals</span>
          <strong>Cumulative nutrition</strong>
          <small>{{ dashboard.status_counts.completed }} completed meals · per person</small>
        </div>
        <div v-for="metric in nutritionMetrics" :key="metric.key" class="cumulative-metric-card">
          <span>{{ metric.label }}</span>
          <strong>{{ formatNutrition(dashboard.completed_nutrition_per_person[metric.key], metric.unit) }}</strong>
          <small>
            <template v-if="cumulativeProgress(metric.key) !== null">{{ cumulativeProgress(metric.key) }}% of current plan</template>
            <template v-else>No counted plan total</template>
          </small>
        </div>
      </section>

      <section class="dashboard-analytics">
        <div class="nutrition-trend-panel">
          <div class="dashboard-section-heading">
            <div><h2>Cumulative nutrition curve</h2><p>Completed actuals against the current non-skipped plan</p></div>
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
            <div class="chart-legend" aria-hidden="true">
              <span class="completed">Completed cumulative</span>
              <span class="planned">Current plan cumulative</span>
            </div>
            <svg viewBox="0 0 760 220" role="img" :aria-label="`Cumulative ${selectedMetricDefinition.label} for completed meals compared with the current plan`">
              <line v-for="y in [28, 83, 138, 192]" :key="y" x1="28" :y1="y" x2="732" :y2="y" class="chart-grid-line" />
              <polyline
                v-for="segment in plannedChartSegments"
                :key="`planned-${segment}`"
                :points="segment"
                fill="none"
                class="chart-planned-line"
                stroke-width="3"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <polyline
                v-for="segment in completedChartSegments"
                :key="`completed-${segment}`"
                :points="segment"
                fill="none"
                :stroke="selectedMetricDefinition.color"
                stroke-width="4"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
              <g v-for="(point, index) in completedChartPoints" :key="index">
                <circle :cx="point.x" :cy="point.y" r="5" :fill="selectedMetricDefinition.color" />
              </g>
            </svg>
            <div class="chart-day-labels">
              <span v-for="day in dashboard.days" :key="day.entry_id">{{ formatPlanDate(day.planned_date) }}</span>
            </div>
          </div>
          <p class="chart-note">Running {{ selectedMetricDefinition.label.toLowerCase() }} per person ({{ selectedMetricDefinition.unit }}). Completed meals add to actuals; planned days hold the actual line flat, and skipped meals are excluded from both current totals.</p>
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

      <section class="daily-nutrition-section" aria-labelledby="daily-nutrition-title">
        <div class="dashboard-section-heading">
          <div>
            <h2 id="daily-nutrition-title">Daily nutrition detail</h2>
            <p>Completed rows are actuals; planned rows are previews; skipped rows never enter cumulative totals.</p>
          </div>
        </div>
        <div class="daily-nutrition-table">
          <div class="daily-nutrition-header" aria-hidden="true">
            <span>Date</span><span>Basis</span><span>Calories</span><span>Protein</span><span>Carbs</span><span>Fat</span><span>Sodium</span><span>Sugar</span>
          </div>
          <article
            v-for="day in dashboard.days"
            :key="day.entry_id"
            class="daily-nutrition-row"
            :class="day.status"
          >
            <time :datetime="day.planned_date">{{ formatPlanDate(day.planned_date) }}</time>
            <strong>{{ day.status === "completed" ? "Actual" : day.status === "planned" ? "Planned" : "Not counted" }}</strong>
            <span>{{ formatNutrition(day.nutrition_per_person.calories_kcal, "kcal") }}</span>
            <span>{{ formatNutrition(day.nutrition_per_person.protein_g, "g") }}</span>
            <span>{{ formatNutrition(day.nutrition_per_person.carbohydrate_g, "g") }}</span>
            <span>{{ formatNutrition(day.nutrition_per_person.fat_g, "g") }}</span>
            <span>{{ formatNutrition(day.nutrition_per_person.sodium_mg, "mg") }}</span>
            <span>{{ formatNutrition(day.nutrition_per_person.sugar_g, "g") }}</span>
          </article>
        </div>
      </section>

      <section class="meal-checkin-section">
        <div class="dashboard-section-heading">
          <div><h2>Planned meals</h2><p>Update execution status without recording food outside this plan.</p></div>
        </div>
        <div class="meal-checkin-table">
          <div class="meal-checkin-header" aria-hidden="true">
            <span>Date</span><span>Recipe</span><span>Nutrition summary</span><span>Status</span><span>Plan</span>
          </div>
          <article v-for="day in dashboard.days" :key="day.entry_id" class="meal-checkin-row">
            <time :datetime="day.planned_date">{{ formatPlanDate(day.planned_date) }}</time>
            <div class="meal-recipe-cell">
              <NuxtLink :to="`/recipes/${day.recipe.slug}`">{{ day.recipe.title }}</NuxtLink>
              <span v-if="day.is_locked" class="locked-badge">Locked</span>
            </div>
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
            <button
              type="button"
              class="adjust-meal-button"
              :disabled="day.status === 'completed' || day.is_locked"
              @click="openReplan(day)"
            >{{ day.is_locked ? "Protected" : day.status === "completed" ? "Historical" : "Adjust" }}</button>
          </article>
        </div>
      </section>

      <section v-if="replanEntry" class="replan-workspace" aria-labelledby="replan-title">
        <div class="replan-heading">
          <div>
            <p class="form-kicker">Dynamic replanning</p>
            <h2 id="replan-title">Adjust {{ replanEntry.recipe.title }}</h2>
            <p>{{ formatPlanDate(replanEntry.planned_date) }} · only this meal and its shopping demand may change.</p>
          </div>
          <button type="button" class="replan-close" aria-label="Close replanning panel" @click="closeReplan">×</button>
        </div>

        <div v-if="replanError" class="notice-panel error-notice">{{ replanError }}</div>
        <div class="replan-grid">
          <form class="replan-form" @submit.prevent="previewChange">
            <fieldset>
              <legend>What changed?</legend>
              <label v-for="option in replanEventOptions" :key="option.value" class="replan-choice">
                <input v-model="replanForm.eventType" type="radio" :value="option.value" @change="resetPreview">
                <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
              </label>
            </fieldset>
            <label v-if="replanForm.eventType === 'ITEM_UNAVAILABLE'">
              <span>Unavailable ingredient</span>
              <input
                v-model="replanForm.unavailableIngredient"
                required
                type="text"
                placeholder="e.g. chicken breast"
                @input="resetPreview"
              >
            </label>
            <label>
              <span>Reason <small>optional</small></span>
              <textarea v-model="replanForm.reason" rows="3" placeholder="Record why this adjustment was requested." @input="resetPreview" />
            </label>
            <button type="submit" class="primary-button" :disabled="isPreviewing">
              {{ isPreviewing ? "Preparing preview…" : "Preview minimal change" }}
            </button>
          </form>

          <div class="replan-preview" :class="{ empty: !preview }">
            <template v-if="preview">
              <div class="preview-title-row">
                <div><p class="form-kicker">Preview only</p><h3>Review before applying</h3></div>
                <span>Based on revision {{ preview.base_revision }}</span>
              </div>
              <div class="recipe-change-card">
                <div><span>Before</span><strong>{{ preview.before_entry.recipe_title }}</strong></div>
                <span class="change-arrow">→</span>
                <div><span>After</span><strong>{{ preview.after_entry.recipe_title }}</strong></div>
              </div>
              <dl class="nutrition-delta-grid">
                <div><dt>Calories</dt><dd>{{ formatSigned(preview.nutrition_delta.calories_kcal, " kcal") }}</dd></div>
                <div><dt>Protein</dt><dd>{{ formatSigned(preview.nutrition_delta.protein_g, " g") }}</dd></div>
                <div><dt>Sodium</dt><dd>{{ formatSigned(preview.nutrition_delta.sodium_mg, " mg") }}</dd></div>
                <div><dt>Shopping total</dt><dd>{{ formatSigned(preview.purchase_total_delta_sgd, " SGD") }}</dd></div>
              </dl>
              <div class="shopping-delta">
                <h4>Shopping List delta</h4>
                <p v-if="!preview.grocery_delta.length">No package-level shopping change.</p>
                <ul v-else>
                  <li v-for="line in preview.grocery_delta" :key="line.ingredient_name">
                    <span :class="`delta-${line.change}`">{{ line.change }}</span>
                    <strong>{{ line.ingredient_display_name }}</strong>
                    <small>{{ groceryDeltaSummary(line) }} · {{ formatSigned(line.purchase_cost_delta_sgd, " SGD") }}</small>
                  </li>
                </ul>
              </div>
              <div class="preview-actions">
                <button type="button" class="secondary-button" @click="clearPreview">Discard preview</button>
                <button type="button" class="primary-button" :disabled="isConfirming" @click="applyPreview">
                  {{ isConfirming ? "Applying…" : "Confirm and update plan" }}
                </button>
              </div>
            </template>
            <template v-else>
              <p class="form-kicker">No plan changes yet</p>
              <h3>Preview first, then confirm</h3>
              <p>MealCraft keeps completed meals intact, changes the smallest possible scope, and shows shopping impact before saving.</p>
            </template>
          </div>
        </div>
      </section>

      <section v-if="events.length" class="plan-history-section">
        <div class="dashboard-section-heading">
          <div><h2>Plan history</h2><p>Persistent event trail for this weekly plan.</p></div>
        </div>
        <ol class="plan-history-list">
          <li v-for="event in events" :key="event.id">
            <span :class="event.status">{{ event.status }}</span>
            <div>
              <strong>{{ eventTypeLabel(event.event_type) }}</strong>
              <p>{{ event.before_entry.recipe_title }} → {{ event.after_entry.recipe_title }} · revision {{ event.base_revision }}<template v-if="event.applied_revision"> → {{ event.applied_revision }}</template></p>
            </div>
          </li>
        </ol>
      </section>
    </template>
  </main>
</template>
