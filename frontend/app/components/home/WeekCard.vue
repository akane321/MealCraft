<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { MEAL_LABEL, budgetGap, countWord, formatSgd, mealsByDay, perMealAndDay } from "~/lib/home-surface";
import type { PlannedMeal } from "~/lib/home-surface";
import type { NutritionDashboardDay, WeeklyGroceryEstimate } from "~/types/meal-plan";

const props = defineProps<{ days: NutritionDashboardDay[]; estimate: WeeklyGroceryEstimate; rangeLabel: string; householdSize?: number | null }>();
const emit = defineEmits<{ open: [tab: "groceries" | "nutrition"]; openRecipe: [slug: string] }>();

const today = todayIsoDate();
const week = computed(() => mealsByDay(props.days));
const meals = computed(() => week.value.flatMap(day => day.meals));
const dinnersOnly = computed(() => meals.value.every(meal => meal.mealType === "dinner"));
const headline = computed(() => (dinnersOnly.value ? `${countWord(meals.value.length)} dinners` : `${countWord(meals.value.length)} meals`));
const eyebrow = computed(() => [props.rangeLabel, props.householdSize ? `${dinnersOnly.value ? "dinners" : "meals"} for ${props.householdSize}` : null].filter(Boolean).join(" · "));
// Cooking time of a meal is its main dish's; nutrition per meal, or per day when a day has several.
const avgCook = computed(() => Math.round(meals.value.reduce((sum, meal) => sum + meal.dishes[0]!.recipe.total_time_minutes, 0) / (meals.value.length || 1)));
const averages = computed(() => perMealAndDay(props.days));
const perPlate = computed(() => Math.round((averages.value && averages.value.mealsPerDay > 1 ? averages.value.day : averages.value?.meal)?.calories_kcal ?? 0));
const perPlateLabel = computed(() => (averages.value && averages.value.mealsPerDay > 1 ? "Per day" : "Per meal"));
// What is left of the budget (or how far over), shown beside the groceries total.
const left = computed(() => {
  const gap = budgetGap(props.estimate);
  return gap && { label: gap.over ? "Over" : "Left", value: gap.amount, over: gap.over };
});
// A tight budget or few eligible dishes can bring a dinner back; say so rather than let it look like a slip.
const repeats = computed(() => new Set(props.days.map(day => day.recipe.slug)).size < props.days.length);
const slugCount = computed(() => {
  const counts = new Map<string, number>();
  for (const dish of props.days) counts.set(dish.recipe.slug, (counts.get(dish.recipe.slug) ?? 0) + 1);
  return counts;
});
const repeated = (meal: PlannedMeal) => meal.dishes.some(dish => (slugCount.value.get(dish.recipe.slug) ?? 0) > 1);
const mealTitle = (meal: PlannedMeal) => `${MEAL_LABEL[meal.mealType]}: ${meal.dishes.map(dish => dish.recipe.title).join(" and ")}`;
// The small badge on a meal's icon: its soup, else its second dish.
const badge = (meal: PlannedMeal) => meal.dishes.slice(1).find(dish => dish.role_id === "soup") ?? meal.dishes[1];
const dishCount = (n: number) => `${n} ${n === 1 ? "dish" : "dishes"}`;
</script>

<template>
  <section class="week-card mc-card" aria-label="Your week">
    <div class="head">
      <div class="title">
        <span class="mc-label">{{ eyebrow }}</span>
        <h3 class="mc-title">{{ headline }}, one shop.</h3>
      </div>
      <div class="figures">
        <div class="fig"><span class="k">Groceries</span><span class="v mc-num">{{ formatSgd(estimate.purchase_total_sgd) }}</span></div>
        <div v-if="left" class="fig" :class="left.over ? 'over' : 'ok'"><span class="k">{{ left.label }}</span><span class="v mc-num">{{ left.value }}</span></div>
        <div class="fig"><span class="k">Avg cook</span><span class="v mc-num">{{ avgCook }} min</span></div>
        <div v-if="!left" class="fig"><span class="k">{{ perPlateLabel }}</span><span class="v mc-num">{{ perPlate }} kcal</span></div>
      </div>
    </div>
    <div class="strip">
      <button
        v-for="day in week"
        :key="day.dayIndex"
        type="button"
        class="tile"
        :class="{ today: day.date === today, skipped: day.meals.every(meal => meal.status === 'skipped') }"
        :aria-current="day.date === today ? 'date' : undefined"
        :aria-label="`${formatPlanDate(day.date, { weekday: 'long' })}: ${day.meals.map(meal => meal.dishes.map(d => d.recipe.title).join(' and ')).join('; ')}`"
        @click="emit('openRecipe', day.meals[day.meals.length - 1]!.dishes[0]!.recipe.slug)"
      >
        <span class="d">{{ formatPlanDate(day.date, { weekday: "short" }).toUpperCase() }} <span>{{ Number(day.date.slice(8, 10)) }}</span></span>
        <span class="meals">
          <span v-for="meal in day.meals" :key="meal.key" class="meal" :class="[meal.status, { several: day.meals.length > 1 }]" :title="mealTitle(meal)">
            <HomeDishIcon :title="meal.dishes[0]!.recipe.title" :course="meal.dishes[0]!.recipe.course" :role-id="meal.dishes[0]!.role_id" :size="day.meals.length > 1 ? 32 : 48" />
            <span v-if="badge(meal) && day.meals.length === 1" class="badge">
              <HomeDishIcon :title="badge(meal)!.recipe.title" :course="badge(meal)!.recipe.course" :role-id="badge(meal)!.role_id" :size="22" />
            </span>
            <svg v-if="meal.status === 'completed'" class="tick" viewBox="0 0 24 24" aria-label="Cooked"><circle cx="12" cy="12" r="11" /><path d="m7 12.5 3.5 3.5L17 9" /></svg>
            <svg v-if="repeated(meal)" class="again" viewBox="0 0 24 24" aria-label="Appears more than once this week"><circle cx="12" cy="12" r="11" /><path d="M7 11a5 5 0 0 1 9-2.5M17 13a5 5 0 0 1-9 2.5M16 5v4h-4M8 19v-4h4" /></svg>
          </span>
        </span>
        <span class="n">{{ day.meals[day.meals.length - 1]!.dishes[0]!.recipe.title }}</span>
        <span class="mc-small more">{{ [...day.meals.slice(0, -1).map(meal => MEAL_LABEL[meal.mealType]), dishCount(day.meals.reduce((sum, meal) => sum + meal.dishes.length, 0))].join(" · ") }}</span>
      </button>
    </div>
    <div class="foot">
      <button type="button" class="mc-btn secondary" @click="emit('open', 'groceries')">Shopping list</button>
      <button type="button" class="mc-btn quiet" @click="emit('open', 'nutrition')">Nutrition</button>
      <span v-if="repeats" class="mc-small repeat-note">Some dishes appear more than once: not enough different ones fit your limits this week.</span>
    </div>
  </section>
</template>

<style scoped>
.head { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 16px; padding: 16px 20px 14px; }
.title { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
h3 { margin: 0; }
.figures { margin-left: auto; display: flex; gap: 22px; }
.fig { display: flex; flex-direction: column; align-items: flex-end; }
.k { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.v { font-family: var(--font-display); font-weight: 700; font-size: 20px; line-height: 26px; white-space: nowrap; }
.fig.ok .v { color: var(--c-green-text); }
.fig.over .v { color: var(--c-amber-text); }
.strip { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); border-top: 1px solid var(--c-line-soft); }
.tile { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; padding: 12px 6px 14px; border: 0; border-right: 1px solid var(--c-line-soft); background: #fff; color: var(--c-ink); text-align: center; }
.tile:last-child { border-right: 0; }
.tile:hover { background: var(--c-canvas); }
.tile.skipped { opacity: 0.5; }
.tile.today { background: var(--c-today); }
.d { font-size: 12px; line-height: 16px; font-weight: 800; color: var(--c-ink); }
.d span { color: var(--c-muted); font-weight: 700; }
.today .d { color: var(--c-today-text); }
.meals { display: flex; flex-direction: column; align-items: center; gap: 4px; min-height: 56px; justify-content: center; }
.meal { position: relative; display: flex; width: 56px; height: 56px; align-items: center; justify-content: center; }
.meal.several { width: 40px; height: 36px; }
.meal.completed > :first-child { opacity: 0.45; }
.meal.skipped { opacity: 0.4; }
.badge { position: absolute; right: -6px; bottom: -4px; display: flex; }
.tick, .again { position: absolute; width: 16px; height: 16px; fill: #fff; stroke-linecap: round; stroke-linejoin: round; }
.tick { right: -2px; top: -2px; fill: var(--c-green); }
.tick path { fill: none; stroke: #fff; stroke-width: 2.4; }
.tick circle { stroke: #fff; stroke-width: 1.5; }
.again { left: -2px; top: -2px; stroke: var(--c-blue); stroke-width: 1.8; }
.again path { fill: none; stroke-width: 2; }
.n { height: 36px; width: 100%; font-size: 12px; line-height: 18px; font-weight: 800; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.foot { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--c-line-soft); }
.repeat-note { flex: 1 1 200px; text-align: right; }
</style>
