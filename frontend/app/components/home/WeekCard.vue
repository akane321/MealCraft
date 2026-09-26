<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { MEAL_LABEL, budgetLine, countWord, formatSgd, mealsByDay, perMealAndDay, plateStyle } from "~/lib/home-surface";
import type { NutritionDashboardDay, WeeklyGroceryEstimate } from "~/types/meal-plan";

const props = defineProps<{ days: NutritionDashboardDay[]; estimate: WeeklyGroceryEstimate; rangeLabel: string }>();
const emit = defineEmits<{ open: [tab: "groceries" | "nutrition"]; openRecipe: [slug: string] }>();

const today = todayIsoDate();
const week = computed(() => mealsByDay(props.days));
const meals = computed(() => week.value.flatMap(day => day.meals));
const dinnersOnly = computed(() => meals.value.every(meal => meal.mealType === "dinner"));
const headline = computed(() => (dinnersOnly.value ? `${countWord(meals.value.length)} dinners` : `${countWord(meals.value.length)} meals`));
// Cooking time of a meal is its main dish's; nutrition per meal, or per day when a day has several.
const avgCook = computed(() => Math.round(meals.value.reduce((sum, meal) => sum + meal.dishes[0]!.recipe.total_time_minutes, 0) / (meals.value.length || 1)));
const averages = computed(() => perMealAndDay(props.days));
const perPlate = computed(() => Math.round((averages.value && averages.value.mealsPerDay > 1 ? averages.value.day : averages.value?.meal)?.calories_kcal ?? 0));
const perPlateLabel = computed(() => (averages.value && averages.value.mealsPerDay > 1 ? "Per day" : "Per meal"));
const budget = computed(() => budgetLine(props.estimate));
// A tight budget or few eligible dishes can bring a dinner back; say so rather than let it look like a slip.
const repeats = computed(() => new Set(props.days.map(day => day.recipe.slug)).size < props.days.length);
</script>

<template>
  <section class="week-card" aria-label="Your week">
    <div class="head">
      <div class="title">
        <span class="mc-eyebrow">{{ rangeLabel }}</span>
        <h3 class="mc-serif">{{ headline }}, <em>one shop.</em></h3>
      </div>
      <div class="figures">
        <div class="fig"><span class="k">Groceries</span><span class="v mc-serif mc-num">{{ formatSgd(estimate.purchase_total_sgd) }}</span></div>
        <div class="fig"><span class="k">Avg. cook</span><span class="v mc-serif mc-num">{{ avgCook }}<small>min</small></span></div>
        <div class="fig"><span class="k">{{ perPlateLabel }}</span><span class="v mc-serif mc-num">{{ perPlate }}<small>kcal</small></span></div>
      </div>
    </div>
    <div class="strip">
      <button
        v-for="day in week"
        :key="day.dayIndex"
        type="button"
        class="tile"
        :class="{ today: day.date === today, skipped: day.meals.every(meal => meal.status === 'skipped') }"
        :aria-label="`${formatPlanDate(day.date, { weekday: 'long' })}: ${day.meals.map(meal => meal.dishes.map(d => d.recipe.title).join(' and ')).join('; ')}`"
        @click="emit('openRecipe', day.meals[day.meals.length - 1]!.dishes[0]!.recipe.slug)"
      >
        <span class="d">{{ formatPlanDate(day.date, { weekday: "short" }) }}</span>
        <span class="plate" :style="plateStyle(day.meals[day.meals.length - 1]!.dishes[0]!.recipe.slug)" />
        <span class="n mc-serif">{{ day.meals[day.meals.length - 1]!.dishes[0]!.recipe.title }}</span>
        <span v-if="day.meals.length > 1 || day.meals[0]!.dishes.length > 1" class="more">
          <template v-if="day.meals.length > 1">{{ day.meals.slice(0, -1).map(meal => MEAL_LABEL[meal.mealType]).join(" · ") }} · </template>{{ day.meals.reduce((sum, meal) => sum + meal.dishes.length, 0) }} dishes
        </span>
      </button>
    </div>
    <div class="foot">
      <button type="button" class="mc-primary" @click="emit('open', 'groceries')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l2 11h11l2-8H6.5" /><circle cx="9" cy="19" r="1.3" /><circle cx="17" cy="19" r="1.3" /></svg>Shopping list
      </button>
      <button type="button" class="mc-pill" @click="emit('open', 'nutrition')">Nutrition</button>
      <span v-if="budget" class="note" :class="{ over: estimate.within_weekly_budget === false }"><span class="dot" />{{ budget }}</span>
      <p v-if="repeats" class="repeat-note">Some dishes appear twice: not enough different ones fit your limits this week.</p>
    </div>
  </section>
</template>

<style scoped>
.week-card { border-radius: 20px; background: var(--s1); border: 1px solid var(--line); overflow: hidden; }
.head { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 28px; padding: 22px 24px 18px; }
.title { display: grid; gap: 4px; }
h3 { margin: 0; font-size: 26px; line-height: 1.1; }
h3 em { color: var(--accent); }
.figures { margin-left: auto; display: flex; flex-wrap: wrap; gap: 12px 26px; }
.fig { display: grid; gap: 2px; }
.k { font-size: 11px; color: var(--t3); letter-spacing: 0.04em; }
.v { font-size: 24px; line-height: 1; }
.v small { margin-left: 3px; font: 400 12px var(--sans); color: var(--t3); }
.strip { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); border-top: 1px solid var(--line); }
.tile { display: grid; justify-items: center; align-content: start; gap: 9px; padding: 16px 6px 14px; border: 0; border-right: 1px solid var(--line); background: transparent; text-align: center; transition: background 200ms; }
.tile:last-child { border-right: 0; }
.tile:hover { background: rgba(242, 237, 228, 0.03); }
.tile.skipped { opacity: 0.45; }
.d { font-size: 10.5px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.today .d { color: var(--accent); }
.n { font-size: 12.5px; font-weight: 400; line-height: 1.25; color: var(--t2); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.more { font-size: 10.5px; color: var(--t4); line-height: 1.3; }
.tile .plate { --size: 52px; transition: transform 500ms var(--ease); }
.tile:hover .plate { transform: rotate(-14deg) scale(1.05); }
.foot { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding: 14px 24px; border-top: 1px solid var(--line); background: rgba(242, 237, 228, 0.015); }
.note { margin-left: auto; font-size: 12px; color: var(--sage); display: inline-flex; align-items: center; gap: 6px; }
.note.over { color: var(--warn); }
.repeat-note { flex-basis: 100%; margin: 2px 0 0; font-size: 12px; color: var(--t3); }
.dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

@media (max-width: 760px) {
  .figures { margin-left: 0; }
  .strip { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .tile:nth-child(4) { border-right: 0; }
  .tile:nth-child(-n+4) { border-bottom: 1px solid var(--line); }
  .tile .plate { --size: 44px; }
}
</style>
