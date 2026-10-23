<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { FEEDBACK_BUTTONS, MEAL_LABEL, isStapleDish, mealsByDay, nextFeedback, nextMeal, type PlannedMeal } from "~/lib/home-surface";
import type { FeedbackKind, NutritionDashboardDay } from "~/types/meal-plan";

// A replaced week (readonly) is only read: its dishes offer no changes. Feedback is on the dish, not the week
// (ADR-0087): it shows for every dish not skipped, to anyone but a viewer (`canGiveFeedback`).
const props = defineProps<{
  days: NutritionDashboardDay[];
  planId: number | null;
  revision?: number;
  startDate?: string | null;
  readonly?: boolean;
  canGiveFeedback?: boolean;
  feedbackRecipeId?: number | null;
  feedbackError?: string | null;
}>();
const emit = defineEmits<{ openRecipe: [slug: string]; ask: [text: string]; feedback: [recipeId: number, kind: FeedbackKind | null] }>();
const changeable = (dish: NutritionDashboardDay) => !props.readonly && dish.status === "planned" && !dish.is_locked;
const rated = (dish: NutritionDashboardDay) => Boolean(props.canGiveFeedback) && dish.status !== "skipped";

const week = computed(() => mealsByDay(props.days));
const next = computed(() => nextMeal(props.days, todayIsoDate()));
// A dinner-only week reads as before, one row a day; with several meals each day gets a heading.
const severalMeals = computed(() => week.value.some(day => day.meals.length > 1));
// The overview line of a day of several meals names each meal's main (in meal order), as the whole day of a full
// structure cannot fit one line; each main is shortened in proportion, so the dinner's stays in view at 1280. Its
// tooltip lists every dish.
const dayText = (day: { meals: PlannedMeal[] }) => day.meals.map(meal => `${MEAL_LABEL[meal.mealType]}: ${meal.dishes.map(dish => dish.recipe.title).join(", ")}`).join("; ");

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
        <span v-if="day.meals.length > 1" class="overview-dishes overview-mains" :title="dayText(day)">
          <span v-for="meal in day.meals" :key="meal.key">{{ meal.dishes[0]!.recipe.title }}</span>
        </span>
        <span v-else class="overview-dishes" :title="dayText(day)">{{ dayText(day) }}</span>
      </li>
    </ol>
    <p v-if="feedbackError" class="feedback-error" role="alert">{{ feedbackError }}</p>
    <ol class="days">
      <li v-for="day in week" :key="day.dayIndex" class="day">
        <p v-if="severalMeals" class="day-head mc-label">
          {{ formatPlanDate(day.date, { weekday: "long" }) }} {{ formatPlanDate(day.date, { day: "numeric", month: "short" }) }}
        </p>
        <div
          v-for="meal in day.meals"
          :key="meal.key"
          class="row"
          :class="{ done: meal.status === 'completed' || meal.status === 'skipped', named: severalMeals }"
        >
          <span class="d">
            <template v-if="severalMeals"><b>{{ MEAL_LABEL[meal.mealType] }}</b></template>
            <template v-else><b>{{ formatPlanDate(day.date, { weekday: "short" }) }}</b><span>{{ Number(day.date.slice(8, 10)) }}</span></template>
          </span>
          <HomeDishIcon class="icon" :title="meal.dishes[0]!.recipe.title" :course="meal.dishes[0]!.recipe.course" :role-id="meal.dishes[0]!.role_id" :size="32" />
          <!-- One line per dish: its name, then its own changes, so a meal of several dishes never shows unlabelled rows. -->
          <span class="dishes">
            <span v-for="(dish, index) in meal.dishes" :key="dish.entry_id" class="dish" :class="{ side: index > 0 }">
              <span class="title-line">
                <button type="button" class="name" :title="dish.recipe.title" @click="emit('openRecipe', dish.recipe.slug)">{{ dish.recipe.title }}</button>
                <span v-if="isStapleDish(dish)" class="role-tag" title="Rice, noodles or bread with the meal">Staple</span>
                <!-- Who at this meal cannot eat this dish: the meal's other dishes cover them (ADR-0071). -->
                <span v-if="dish.not_for?.length" class="not-for" :title="`${dish.not_for.join(', ')} cannot eat this dish; other dishes at this meal are for them`">Not for {{ dish.not_for.join(", ") }}</span>
                <!-- The meal's chip rides on its first dish's line, leaving the full width for each dish's changes. -->
                <span v-if="index === 0" class="mc-chip" :class="CHIP_TONE[chip(meal).kind]">
                  <svg v-if="chip(meal).kind === 'completed'" class="ok-tick" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
                  <svg v-else-if="chip(meal).kind === 'partial'" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5a7 7 0 1 0 0 14V5Z" /></svg>
                  {{ chip(meal).label }}
                </span>
              </span>
              <span v-if="meal.dishes.length === 1 || dish.is_locked" class="rest">
                <template v-if="meal.dishes.length === 1">{{ dish.recipe.total_time_minutes }} min · {{ Math.round(dish.nutrition_per_person.calories_kcal) }} kcal</template>
                <span v-if="dish.is_locked" class="kept"><template v-if="meal.dishes.length === 1"> · </template>Kept as is</span>
              </span>
              <span v-if="changeable(dish) || rated(dish)" class="act-row">
                <span v-if="changeable(dish)" class="acts" role="group" :aria-label="`Change ${dish.recipe.title}`">
                  <button
                    v-for="action in ACTIONS"
                    :key="action.label"
                    type="button"
                    @click="emit('ask', action.text(formatPlanDate(day.date, { weekday: 'long' }), dish.recipe.title))"
                  >
                    {{ action.label }}
                  </button>
                </span>
                <!-- Pressing the pressed button again undoes it; the whole household's, whoever pressed it. -->
                <span v-if="rated(dish)" class="feedback" role="group" :aria-label="`Feedback on ${dish.recipe.title}`">
                  <button
                    v-for="button in FEEDBACK_BUTTONS"
                    :key="button.kind"
                    type="button"
                    :aria-pressed="dish.feedback === button.kind"
                    :aria-busy="feedbackRecipeId === dish.recipe.id"
                    :disabled="feedbackRecipeId === dish.recipe.id"
                    @click="emit('feedback', dish.recipe.id, nextFeedback(dish.feedback, button.kind))"
                  >
                    {{ button.label }}
                  </button>
                </span>
                <span v-if="rated(dish) && dish.feedback === 'never_again'" class="never">
                  Won't be planned again ·
                  <button type="button" :disabled="feedbackRecipeId === dish.recipe.id" @click="emit('feedback', dish.recipe.id, null)">Undo</button>
                </span>
              </span>
            </span>
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
/* Each meal's main shrinks in proportion to its length, so the last (dinner) never falls off the line. */
.overview-mains { display: flex; min-width: 0; }
.overview-mains > span { flex: 0 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.overview-mains > span + span::before { content: " · "; white-space: pre; }
.days { list-style: none; margin: 0; padding: 0 16px; }
.day-head { margin: 0; padding: 12px 0 2px; }
.row { display: grid; grid-template-columns: 44px 32px minmax(0, 1fr); gap: 10px; align-items: start; min-height: 52px; padding: 6px 0; border-bottom: 1px solid var(--c-line-soft); }
/* With several meals a day the first column names the meal ("Breakfast"), wider than a weekday. */
.row.named { grid-template-columns: 64px 32px minmax(0, 1fr); }
.row.done { opacity: 0.6; }
.d { display: flex; flex-direction: column; font-size: 12px; line-height: 16px; }
.d b { font-weight: 800; }
.d span { color: var(--c-muted); }
.dishes { min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.dish { min-width: 0; display: flex; flex-direction: column; }
.title-line { display: flex; align-items: center; gap: 8px; min-width: 0; }
.title-line .name { flex: 0 1 auto; min-width: 0; }
.not-for { flex: none; color: var(--c-muted); font-size: 11px; line-height: 18px; font-weight: 700; }
.role-tag { flex: none; padding: 0 7px; border: 1px solid var(--c-line); border-radius: 999px; color: var(--c-muted); font-size: 11px; line-height: 18px; font-weight: 700; }
.title-line .mc-chip { flex: none; margin-left: auto; }
.name { max-width: 100%; padding: 0; border: 0; background: none; color: inherit; font: inherit; font-weight: 800; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dish.side .name { font-size: 13px; font-weight: 700; }
.name:hover { color: var(--c-coral); }
.rest { font-size: 12px; line-height: 16px; color: var(--c-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kept { color: var(--c-green-text); font-weight: 800; }
.ok-tick { color: var(--c-green); }
/* A dish's changes and its feedback, quiet until the row is pointed at or focused; each group wraps as a whole
   rather than run under the chip. */
.act-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; margin-top: 4px; }
.acts, .feedback { display: flex; align-items: center; gap: 4px; opacity: 0.6; transition: opacity 150ms var(--ease); }
.acts { flex-wrap: wrap; }
.row:hover .acts, .row:focus-within .acts, .row:hover .feedback, .row:focus-within .feedback { opacity: 1; }
.acts button, .feedback button { flex: none; height: 24px; padding: 0 8px; white-space: nowrap; border: 1px solid var(--c-line); border-radius: 999px; background: #fff; color: var(--c-ink); font-size: 12px; font-weight: 700; }
.acts button:hover, .feedback button:hover { border-color: var(--c-coral); }
.feedback button[aria-pressed="true"] { border-color: var(--c-ink); background: var(--c-ink); color: #fff; }
.feedback button:disabled { opacity: 0.6; }
.never { font-size: 12px; line-height: 24px; color: var(--c-muted); font-weight: 700; white-space: nowrap; }
.never button { padding: 0; border: 0; background: none; color: var(--c-coral); font: inherit; text-decoration: underline; }
.feedback-error { margin: 8px 16px 0; color: var(--c-coral); font-size: 12px; font-weight: 700; }
</style>
