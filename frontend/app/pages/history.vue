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
    <p class="eyebrow">Past plans</p>
    <h1>Every plan you made, as it ended up.</h1>

    <p v-if="loading" class="notice">Loading your plans…</p>
    <p v-if="error" class="notice" role="alert">{{ error }}</p>
    <p v-if="!loading && !error && !weeks.length" class="notice">No plans yet. <NuxtLink to="/">Make your first one</NuxtLink>.</p>

    <ol class="weeks">
      <!-- Planning the same days again replaces a week (backend `current`): it stays listed, marked, under the newer one. -->
      <li v-for="week in weeks" :key="week.id" class="week" :class="{ replaced: week.current === false }">
        <button type="button" class="remove" :aria-label="`Delete the plan for ${planRange(week.start_date, week.end_date)}`" title="Delete this plan" @click="removing = week">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12" /></svg>
        </button>
        <button type="button" class="summary" :aria-expanded="open === week.id" @click="toggle(week.id)">
          <span class="when mc-serif">{{ planRange(week.start_date, week.end_date) }}<span v-if="week.current === false" class="tag">Replaced by a newer plan</span></span>
          <span class="meta">
            <template v-if="week.day_count">{{ daysLabel(week.day_count) }} · </template>planned {{ plannedAt(week.created_at) }} ·
            {{ week.household_size }} {{ week.household_size === 1 ? "person" : "people" }} ·
            groceries {{ formatSgd(week.purchase_total_sgd) }}
            <template v-if="week.within_weekly_budget === false"> · over budget</template>
            <template v-if="details[week.id]"> · {{ cooked(details[week.id]!) }} of {{ details[week.id]!.days.length }} dishes cooked</template>
          </span>
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
.history { padding-block: 32px 64px; }
h1 { margin: 6px 0 22px; font-family: var(--serif); font-weight: 300; font-size: clamp(26px, 4vw, 36px); text-wrap: balance; }
.notice { color: var(--t3); }
.weeks { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.week { position: relative; border: 1px solid var(--border); border-radius: 14px; background: var(--s1); overflow: hidden; }
.remove { position: absolute; z-index: 1; top: 10px; right: 10px; width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; color: var(--t3); }
.remove:hover, .remove:focus-visible { background: var(--s2); color: var(--c-coral); }
.remove svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.summary { width: 100%; display: flex; flex-wrap: wrap; gap: 4px 16px; align-items: baseline; justify-content: space-between; padding: 14px 52px 14px 16px; border: 0; background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer; }
.summary:hover, .summary:focus-visible { background: var(--s2); }
.when { display: inline-flex; align-items: baseline; gap: 10px; font-size: 18px; }
.tag { padding: 1px 8px; border: 1px solid var(--border); border-radius: 999px; font-family: Nunito, system-ui, sans-serif; font-size: 12px; color: var(--t3); }
.week.replaced .when { color: var(--t3); }
.meta { color: var(--t3); font-size: 13px; font-variant-numeric: tabular-nums; }
.days { display: grid; gap: 8px; padding: 4px 16px 16px; }
.day { display: grid; grid-template-columns: 70px 1fr; gap: 10px; align-items: baseline; }
.day b { color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.meals p { margin: 0 0 4px; font-size: 14px; }
.meal { display: inline-block; min-width: 70px; color: var(--t3); font-size: 12px; }
.dish { display: inline-flex; gap: 6px; align-items: center; padding: 0; border: 0; background: transparent; color: var(--ivory); font: inherit; cursor: pointer; }
.dish:hover { color: var(--accent); }
.dish.skipped { color: var(--muted); text-decoration: line-through; }

</style>
