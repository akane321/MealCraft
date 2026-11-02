<script setup lang="ts">
import { MEAL_LABEL, formatSgd } from "~/lib/home-surface";
import type { MealType } from "~/lib/home-surface";
import { daysLabel, formatPlanDate, planRange } from "~/lib/meal-plan-format";
import type { WeeklyMealPlan, WeeklyMealPlanCollection } from "~/types/meal-plan";

useHead({ title: "Past plans · MealCraft" });

const config = useRuntimeConfig();
const apiFetch = useApiFetch();

const weeks = ref<WeeklyMealPlanCollection["items"]>([]);
const loading = ref(true);
const error = ref("");
const open = ref<number | null>(null);
const details = ref<Record<number, WeeklyMealPlan>>({});
const openSlug = ref<string | null>(null);

onMounted(async () => {
  try {
    weeks.value = (await apiFetch<WeeklyMealPlanCollection>(`${config.public.apiBase}/api/plans`, { query: { limit: 30 } })).items;
  }
  catch {
    error.value = "Your past plans could not be loaded. Try again in a moment.";
  }
  finally {
    loading.value = false;
  }
});

// Deleting a plan (testing and demos pile them up): asked first, then gone with its days and groceries.
const removing = ref<WeeklyMealPlanCollection["items"][number] | null>(null);
const busy = ref(false);
async function removeWeek() {
  const week = removing.value;
  if (!week) return;
  busy.value = true;
  try {
    await apiFetch(`${config.public.apiBase}/api/plans/${week.id}`, { method: "DELETE" });
    weeks.value = weeks.value.filter(item => item.id !== week.id);
    if (open.value === week.id) open.value = null;
  }
  catch {
    error.value = "That plan could not be deleted. Try again in a moment.";
  }
  finally {
    busy.value = false;
    removing.value = null;
  }
}

async function toggle(planId: number) {
  open.value = open.value === planId ? null : planId;
  if (open.value === null || details.value[planId]) return;
  try {
    details.value = { ...details.value, [planId]: await apiFetch<WeeklyMealPlan>(`${config.public.apiBase}/api/plans/${planId}`) };
  }
  catch {
    error.value = "That plan could not be opened.";
  }
}

/** A plan's dishes by day, then by meal, in the order they are eaten. */
function byDay(plan: WeeklyMealPlan) {
  const days = new Map<string, Map<string, WeeklyMealPlan["days"]>>();
  for (const dish of plan.days) {
    const meals = days.get(dish.planned_date) ?? new Map();
    meals.set(dish.meal_type, [...(meals.get(dish.meal_type) ?? []), dish]);
    days.set(dish.planned_date, meals);
  }
  const order = ["breakfast", "lunch", "dinner"];
  return [...days.entries()].map(([date, meals]) => ({
    date,
    meals: [...meals.entries()].sort(([a], [b]) => order.indexOf(a) - order.indexOf(b)).map(([meal, dishes]) => ({ meal, dishes })),
  }));
}

function cooked(plan: WeeklyMealPlan) {
  return plan.days.filter(dish => dish.status === "completed").length;
}

// Several plans can cover the same days; when each was made tells them apart.
const plannedAt = (value: string) => new Date(value).toLocaleString("en-SG", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
</script>

<template>
  <main class="page-width history">
    <h1>Every plan you made, as it ended up</h1>
    <p class="mc-sub">Open a plan to see what was on each day and what got cooked.</p>

    <p v-if="loading" class="notice">Loading your plans…</p>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <div v-if="!loading && !error && !weeks.length" class="mc-empty">
      <div class="mc-empty-art"><span><span class="mc-tile" data-tone="violet"><UIcon name="i-lucide-calendar-days" /></span></span></div>
      <h2>No plans yet</h2>
      <p>Plans you make show up here, newest first.</p>
      <NuxtLink to="/" class="primary-button first">Make your first one</NuxtLink>
    </div>

    <ol class="weeks">
      <!-- Planning the same days again replaces a week (backend `current`): it stays listed, marked, under the newer one. -->
      <li v-for="week in weeks" :key="week.id" class="week" :class="{ replaced: week.current === false }">
        <button type="button" class="remove" :aria-label="`Delete the plan for ${planRange(week.start_date, week.end_date)}`" title="Delete this plan" @click="removing = week">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12" /></svg>
        </button>
        <button type="button" class="summary" :aria-expanded="open === week.id" @click="toggle(week.id)">
          <span class="mc-tile" data-tone="violet" aria-hidden="true"><UIcon name="i-lucide-calendar-days" /></span>
          <span class="text">
          <span class="when">{{ planRange(week.start_date, week.end_date) }}<span v-if="week.current === false" class="tag">Replaced by a newer plan</span></span>
          <span class="meta">
            <template v-if="week.day_count">{{ daysLabel(week.day_count) }} · </template>planned {{ plannedAt(week.created_at) }} ·
            {{ week.household_size }} {{ week.household_size === 1 ? "person" : "people" }} ·
            groceries {{ formatSgd(week.purchase_total_sgd) }}
            <template v-if="week.within_weekly_budget === false"> · over budget</template>
            <template v-if="details[week.id]"> · {{ cooked(details[week.id]!) }} of {{ details[week.id]!.days.length }} dishes cooked</template>
          </span>
          </span>
          <UIcon name="i-lucide-chevron-right" class="chev" aria-hidden="true" />
        </button>
        <div v-if="open === week.id && details[week.id]" class="days">
          <div v-for="day in byDay(details[week.id]!)" :key="day.date" class="day">
            <b>{{ formatPlanDate(day.date, { weekday: "short", day: "numeric" }) }}</b>
            <div class="meals">
              <p v-for="meal in day.meals" :key="meal.meal">
                <span class="meal">{{ MEAL_LABEL[meal.meal as MealType] ?? meal.meal }}</span>
                <template v-for="(dish, index) in meal.dishes" :key="dish.entry_id">
                  <template v-if="index"> · </template>
                  <button type="button" class="dish" :class="dish.status" @click="openSlug = dish.recipe.slug">
                    <HomeDishIcon :title="dish.recipe.title" :course="dish.recipe.course" :role-id="dish.role_id" :size="20" />{{ dish.recipe.title }}
                  </button>
                </template>
              </p>
            </div>
          </div>
        </div>
      </li>
    </ol>

    <HomeRecipeSheet v-if="openSlug" :slug="openSlug" @close="openSlug = null" />
    <HomeConfirm
      v-if="removing"
      title="Delete this plan?"
      :message="`The plan for ${planRange(removing.start_date, removing.end_date)} will be deleted with its dishes, groceries and changes. A conversation that planned it stays. This cannot be undone.`"
      action="Delete plan"
      :busy="busy"
      @confirm="removeWeek"
      @cancel="removing = null"
    />
  </main>
</template>

<style scoped>
.history { padding-block: 28px 48px; }
.notice { color: #71717a; }
.mc-empty .first { min-height: 36px; height: 36px; margin-top: 16px; padding: 0 16px; font-size: 13px; }
.weeks { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.week { position: relative; border: 1px solid #ececef; border-radius: 12px; background: #fff; box-shadow: var(--mc-shadow-xs); overflow: hidden; transition: border-color 150ms; }
.week:hover { border-color: #e1e1e5; }
.remove { position: absolute; z-index: 1; top: 18px; right: 44px; width: 28px; height: 28px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: #a1a1aa; }
.remove:hover, .remove:focus-visible { background: #fef3f2; color: #b42318; }
.remove svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.summary { width: 100%; min-height: 64px; display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.summary:hover, .summary:focus-visible { background: #fafafa; }
.summary .mc-tile { width: 32px; height: 32px; border-radius: 9px; }
.summary .mc-tile > * { width: 16px; height: 16px; }
.text { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 2px; padding-right: 44px; }
.when { display: inline-flex; align-items: baseline; gap: 10px; color: var(--mc-strong); font-size: 15px; line-height: 20px; font-weight: 600; }
.tag { padding: 0 8px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 12px; font-weight: 500; }
.week.replaced .when { color: #71717a; }
.meta { color: #71717a; font-size: 13px; line-height: 18px; font-variant-numeric: tabular-nums; }
.chev { flex: none; width: 16px; height: 16px; color: #a1a1aa; transition: transform 150ms; }
.summary[aria-expanded="true"] .chev { transform: rotate(90deg); }
.days { display: grid; gap: 8px; padding: 12px 16px 16px 60px; border-top: 1px solid #f0f0f2; }
.day { display: grid; grid-template-columns: 70px 1fr; gap: 10px; align-items: baseline; }
.day b { color: #71717a; font-size: 12px; font-weight: 600; }
.meals p { margin: 0 0 4px; font-size: 14px; }
.meal { display: inline-block; min-width: 70px; color: #a1a1aa; font-size: 12px; }
.dish { display: inline-flex; gap: 6px; align-items: center; padding: 0; border: 0; background: transparent; color: #27272a; font: inherit; cursor: pointer; }
.dish:hover { color: #6d28d9; }
.dish.skipped { color: #a1a1aa; text-decoration: line-through; }
</style>
