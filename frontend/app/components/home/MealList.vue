<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { MEAL_LABEL, mealsByDay, nextMeal, type PlannedMeal } from "~/lib/home-surface";
import type { NutritionDashboardDay } from "~/types/meal-plan";

// A replaced week (readonly) is only read: its dishes offer no changes.
const props = defineProps<{ days: NutritionDashboardDay[]; planId: number | null; revision?: number; startDate?: string | null; readonly?: boolean }>();
const emit = defineEmits<{ openRecipe: [slug: string]; ask: [text: string] }>();

const week = computed(() => mealsByDay(props.days));
const next = computed(() => nextMeal(props.days, todayIsoDate()));
// A dinner-only week reads as before, one row a day; with several meals each day gets a heading.
const severalMeals = computed(() => week.value.some(day => day.meals.length > 1));

const STATE: Record<string, string> = { completed: "Cooked", skipped: "Skipped", partial: "Part cooked" };
const CHIP_TONE: Record<string, string> = { next: "warn", tomorrow: "info" };
const tomorrow = computed(() => {
  const date = new Date(`${todayIsoDate()}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
});
// One chip a row: Tonight/Next (amber), Tomorrow (blue), a cooked or skipped state, else how many dishes (neutral).
function chip(meal: PlannedMeal): { kind: string; label: string } {
  if (next.value?.meal.key === meal.key) return { kind: "next", label: next.value.isToday ? (meal.mealType === "dinner" ? "Tonight" : "Today") : "Next" };
  if (STATE[meal.status]) return { kind: meal.status, label: STATE[meal.status]! };
  if (meal.date === tomorrow.value) return { kind: "tomorrow", label: "Tomorrow" };
  return { kind: "count", label: `${meal.dishes.length} ${meal.dishes.length === 1 ? "dish" : "dishes"}` };
}

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
    <ol class="overview" aria-label="Week overview">
      <li v-for="day in week" :key="day.dayIndex">
        <span>{{ formatPlanDate(day.date, { weekday: "short" }) }}</span>
        <span class="overview-dishes" :title="day.meals.map(meal => `${MEAL_LABEL[meal.mealType]}: ${meal.dishes.map(dish => dish.recipe.title).join(', ')}`).join('; ')">
          {{ day.meals.map(meal => `${MEAL_LABEL[meal.mealType]}: ${meal.dishes.map(dish => dish.recipe.title).join(', ')}`).join('; ') }}
        </span>
      </li>
    </ol>
    <ol class="days">
      <li v-for="day in week" :key="day.dayIndex" class="day">
        <p v-if="severalMeals" class="day-head mc-label">
          {{ formatPlanDate(day.date, { weekday: "long" }) }} {{ formatPlanDate(day.date, { day: "numeric", month: "short" }) }}
        </p>
        <div
          v-for="meal in day.meals"
          :key="meal.key"
          class="row"
          :class="{ done: meal.status === 'completed' || meal.status === 'skipped' }"
        >
          <span class="d">
            <template v-if="severalMeals"><b>{{ MEAL_LABEL[meal.mealType] }}</b></template>
            <template v-else><b>{{ formatPlanDate(day.date, { weekday: "short" }) }}</b><span>{{ Number(day.date.slice(8, 10)) }}</span></template>
          </span>
          <HomeDishIcon class="icon" :title="meal.dishes[0]!.recipe.title" :course="meal.dishes[0]!.recipe.course" :role-id="meal.dishes[0]!.role_id" :size="32" />
          <span class="dishes">
            <button type="button" class="name" :title="meal.dishes[0]!.recipe.title" @click="emit('openRecipe', meal.dishes[0]!.recipe.slug)">{{ meal.dishes[0]!.recipe.title }}</button>
            <span class="rest">
              <template v-if="meal.dishes.length > 1">
                <template v-for="(dish, index) in meal.dishes.slice(1)" :key="dish.entry_id"><span v-if="index"> · </span><button type="button" class="side" @click="emit('openRecipe', dish.recipe.slug)">{{ dish.recipe.title }}</button></template>
              </template>
              <template v-else>{{ meal.dishes[0]!.recipe.total_time_minutes }} min · {{ Math.round(meal.dishes[0]!.nutrition_per_person.calories_kcal) }} kcal</template>
              <span v-if="meal.dishes.some(dish => dish.is_locked)" class="kept"> · Kept as is</span>
            </span>
            <span v-for="dish in meal.dishes.filter(item => !readonly && item.status === 'planned' && !item.is_locked)" :key="dish.entry_id" class="acts" role="group" :aria-label="`Change ${dish.recipe.title}`">
              <button
                v-for="action in ACTIONS"
                :key="action.label"
                type="button"
                @click="emit('ask', action.text(formatPlanDate(day.date, { weekday: 'long' }), dish.recipe.title))"
              >
                {{ action.label }}
              </button>
              <span v-if="meal.dishes.length > 1" class="for">{{ dish.recipe.title }}</span>
            </span>
          </span>
          <span class="mc-chip" :class="CHIP_TONE[chip(meal).kind]">
            <svg v-if="chip(meal).kind === 'completed'" class="ok-tick" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
            <svg v-else-if="chip(meal).kind === 'partial'" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5a7 7 0 1 0 0 14V5Z" /></svg>
            {{ chip(meal).label }}
          </span>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.overview { list-style: none; margin: 0; padding: 8px 16px; border-bottom: 1px solid var(--c-line-soft); }
.overview li { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 8px; font-size: 12px; line-height: 22px; }
.overview li > span:first-child { font-weight: 800; }
.overview-dishes { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; color: var(--c-muted); }
.days { list-style: none; margin: 0; padding: 0 16px; }
.day-head { margin: 0; padding: 12px 0 2px; }
.row { display: grid; grid-template-columns: 44px 32px minmax(0, 1fr) auto; gap: 10px; align-items: center; min-height: 52px; padding: 6px 0; border-bottom: 1px solid var(--c-line-soft); }
.row.done { opacity: 0.6; }
.d { display: flex; flex-direction: column; font-size: 12px; line-height: 16px; }
.d b { font-weight: 800; }
.d span { color: var(--c-muted); }
.dishes { min-width: 0; display: flex; flex-direction: column; }
.name, .side { padding: 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; }
.name { font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.name:hover, .side:hover { color: var(--c-coral); }
.rest { font-size: 12px; line-height: 16px; color: var(--c-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kept { color: var(--c-green-text); font-weight: 800; }
.ok-tick { color: var(--c-green); }
/* A dish's changes, quiet until the row is pointed at or focused, always on one line. */
.acts { display: flex; flex-wrap: nowrap; align-items: center; gap: 4px; margin-top: 4px; opacity: 0.6; transition: opacity 150ms var(--ease); }
.row:hover .acts, .row:focus-within .acts { opacity: 1; }
.acts button { flex: none; height: 24px; padding: 0 8px; white-space: nowrap; border: 1px solid var(--c-line); border-radius: 999px; background: #fff; color: var(--c-ink); font-size: 12px; font-weight: 700; }
.acts button:hover { border-color: var(--c-coral); }
.for { font-size: 12px; color: var(--c-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 120px; }
</style>
