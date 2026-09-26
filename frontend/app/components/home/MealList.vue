<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { MEAL_LABEL, mealsByDay, nextMeal, plateStyle } from "~/lib/home-surface";
import type { NutritionDashboardDay } from "~/types/meal-plan";

const props = defineProps<{ days: NutritionDashboardDay[]; planId: number | null }>();
const emit = defineEmits<{ openRecipe: [slug: string]; ask: [text: string] }>();

const week = computed(() => mealsByDay(props.days));
const next = computed(() => nextMeal(props.days, todayIsoDate()));
// A dinner-only week reads as before, one row a day; with several meals each day gets a heading.
const severalMeals = computed(() => week.value.some(day => day.meals.length > 1));

const STATE: Record<string, string> = { completed: "Cooked", skipped: "Skipped", partial: "Part cooked" };

// Each action is a sentence the assistant already understands; it is previewed before anything changes.
const ACTIONS = [
  { label: "Swap", text: (when: string, title: string) => `Swap ${when}'s ${title} for something else` },
  { label: "Keep", text: (when: string, title: string) => `Lock ${when}'s ${title}` },
  { label: "Skip", text: (when: string, title: string) => `Skip ${when}'s ${title}` },
  { label: "Can't buy…", text: (when: string, title: string) => `I can't buy an ingredient for ${when}'s ${title}: ` },
];
</script>

<template>
  <div>
    <ol class="days">
      <li v-for="day in week" :key="day.dayIndex" class="day">
        <p v-if="severalMeals" class="day-head">
          <span>{{ formatPlanDate(day.date, { weekday: "long" }) }}</span> {{ formatPlanDate(day.date, { day: "numeric", month: "short" }) }}
        </p>
        <div
          v-for="meal in day.meals"
          :key="meal.key"
          class="row"
          :class="{ today: next?.meal.key === meal.key, done: meal.status === 'completed' || meal.status === 'skipped' }"
        >
          <span class="d">
            <template v-if="severalMeals"><span>{{ MEAL_LABEL[meal.mealType] }}</span></template>
            <template v-else><span>{{ formatPlanDate(day.date, { weekday: "short" }) }}</span><b class="mc-serif">{{ Number(day.date.slice(8, 10)) }}</b></template>
          </span>
          <span class="plate" :style="plateStyle(meal.dishes[0]!.recipe.slug)" aria-hidden="true" />
          <span class="dishes">
            <span v-for="(dish, index) in meal.dishes" :key="dish.entry_id" class="dish" :class="{ side: index > 0 }">
              <button type="button" class="name mc-serif" @click="emit('openRecipe', dish.recipe.slug)">{{ dish.recipe.title }}</button>
              <small v-if="index === 0">{{ dish.recipe.total_time_minutes }} min · {{ Math.round(meal.dishes.reduce((sum, d) => sum + d.nutrition_per_person.calories_kcal, 0)) }} kcal</small>
              <span v-if="dish.status === 'planned' && !dish.is_locked" class="acts" role="group" :aria-label="`Change ${dish.recipe.title}`">
                <button
                  v-for="action in ACTIONS"
                  :key="action.label"
                  type="button"
                  @click="emit('ask', action.text(formatPlanDate(day.date, { weekday: 'long' }), dish.recipe.title))"
                >
                  {{ action.label }}
                </button>
              </span>
              <small v-else-if="dish.is_locked" class="kept">Kept as is</small>
            </span>
          </span>
          <span class="state" :class="meal.status">{{ next?.meal.key === meal.key ? (next.isToday ? (meal.mealType === "dinner" ? "Tonight" : "Today") : "Next") : STATE[meal.status] ?? "" }}</span>
        </div>
      </li>
    </ol>
    <div class="log"><HomeChangeLog :plan-id="planId" /></div>
  </div>
</template>

<style scoped>
.days { list-style: none; margin: 0; padding: 0; }
.day-head { margin: 0; padding: 14px 22px 4px; font-size: 10.5px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.day-head span { color: var(--t2); }
.row { display: grid; grid-template-columns: 58px 36px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 11px 22px; border-bottom: 1px solid var(--line); }
.row:hover { background: rgba(242, 237, 228, 0.025); }
.row.today { background: rgba(232, 144, 111, 0.06); }
.d { display: grid; line-height: 1.1; }
.d span { font-size: 10px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.today .d span { color: var(--accent); }
.d b { font-size: 19px; }
.row .plate { --size: 36px; }
.dishes { min-width: 0; display: grid; gap: 2px; }
.dish { display: grid; min-width: 0; }
.name { padding: 0; border: 0; background: none; text-align: left; font-size: 15px; font-weight: 400; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.side .name { font-size: 13px; color: var(--t2); }
.name:hover { text-decoration: underline; text-underline-offset: 3px; }
.done .name { color: var(--t3); }
.dish small { font-size: 11.5px; color: var(--t3); }
.state { font-size: 11px; font-weight: 500; color: var(--accent); text-align: right; }
.state.completed { color: var(--sage); }
.state.skipped { color: var(--t4); }
.log { padding: 4px 22px 18px; }
/* A dish's changes, quiet until the row is pointed at or focused. */
.acts { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; opacity: 0.55; transition: opacity 0.15s var(--ease); }
.row:hover .acts, .row:focus-within .acts { opacity: 1; }
.acts button { padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px; background: transparent; color: var(--t3); font-size: 11px; }
.acts button:hover { color: var(--ivory); border-color: var(--accent); }
.kept { color: var(--sage); }
</style>
