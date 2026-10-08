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
// Cooked, Next and Skipped read as icon chips; a plain planned meal has none.
function chip(meal: PlannedMeal): { kind: string; label: string } | null {
  if (next.value?.meal.key === meal.key) return { kind: "next", label: next.value.isToday ? (meal.mealType === "dinner" ? "Tonight" : "Today") : "Next" };
  return STATE[meal.status] ? { kind: meal.status, label: STATE[meal.status]! } : null;
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
          <HomeDishIcon class="icon" :title="meal.dishes[0]!.recipe.title" :course="meal.dishes[0]!.recipe.course" :role-id="meal.dishes[0]!.role_id" :size="36" />
          <span class="dishes">
            <span v-for="(dish, index) in meal.dishes" :key="dish.entry_id" class="dish" :class="{ side: index > 0 }">
              <button type="button" class="name mc-serif" @click="emit('openRecipe', dish.recipe.slug)">{{ dish.recipe.title }}</button>
              <small v-if="index === 0">{{ dish.recipe.total_time_minutes }} min · {{ Math.round(meal.dishes.reduce((sum, d) => sum + d.nutrition_per_person.calories_kcal, 0)) }} kcal</small>
              <span v-if="!readonly && dish.status === 'planned' && !dish.is_locked" class="acts" role="group" :aria-label="`Change ${dish.recipe.title}`">
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
          <span v-if="chip(meal)" class="state" :class="chip(meal)!.kind">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path v-if="chip(meal)!.kind === 'completed'" d="m5 12.5 4.5 4.5L19 7.5" />
              <path v-else-if="chip(meal)!.kind === 'skipped'" d="M6 12h12" />
              <path v-else-if="chip(meal)!.kind === 'partial'" d="M12 5a7 7 0 1 0 0 14V5Z" />
              <path v-else d="M5 12h13M13 6l6 6-6 6" />
            </svg>{{ chip(meal)!.label }}
          </span>
        </div>
      </li>
    </ol>
    <div class="log"><HomeChangeLog :plan-id="planId" :revision="revision" :start-date="startDate" /></div>
  </div>
</template>

<style scoped>
.days { list-style: none; margin: 0; padding: 0; }
.day-head { margin: 0; padding: 14px 22px 4px; font-size: 12px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.day-head span { color: var(--t2); }
.row { display: grid; grid-template-columns: 58px 36px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 12px 20px; border-bottom: 1px solid var(--line); }
.row { transition: background 150ms; }
.row:hover { background: rgba(42, 42, 72, 0.04); }
.row.done .icon { opacity: 0.55; }
.row.today { background: #fff4e0; }
.d { display: grid; line-height: 1.1; }
.d span { font-size: 12px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.today .d span { color: #8a4f00; }
.d b { font-size: 19px; }

.dishes { min-width: 0; display: grid; gap: 2px; }
.dish { display: grid; min-width: 0; }
.name { padding: 0; border: 0; background: none; text-align: left; font-size: 15px; font-weight: 700; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.side .name { font-size: 13px; font-weight: 600; color: var(--t2); }
.name:hover { text-decoration: underline; text-underline-offset: 3px; }
.done .name { color: var(--t3); }
.dish small { font-size: 12px; color: var(--t3); }
.state { display: inline-flex; align-items: center; gap: 4px; padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; background: #fff1d6; color: #8a4f00; white-space: nowrap; }
.state svg { width: 12px; height: 12px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
.state.partial svg { fill: currentColor; stroke-width: 1.5; }
.state.completed { background: #e3f4e9; color: #1f6b3a; }
.state.skipped { background: var(--s3); color: var(--t2); }
.log { padding: 4px 22px 18px; }
/* A dish's changes, quiet until the row is pointed at or focused. */
.acts { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; opacity: 0.55; transition: opacity 0.15s var(--ease); }
.row:hover .acts, .row:focus-within .acts { opacity: 1; }
.acts button { padding: 2px 8px; border: 1px solid var(--line); border-radius: 999px; background: transparent; color: var(--t3); font-size: 12px; }
.acts button:hover { color: var(--ivory); border-color: var(--accent); }
.kept { color: var(--sage); }
</style>
