<script setup lang="ts">
import { formatPlanDate, sentenceDay, todayIsoDate } from "~/lib/meal-plan-format";
import { FEEDBACK_BUTTONS, MEAL_LABEL, dishFacts, isStapleDish, mealsByDay, nextFeedback, nextMeal, type PlannedMeal } from "~/lib/home-surface";
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
// The dish whose facts panel is open: any of its reason tags opens or closes it.
const factsOpen = ref<number | null>(null);
const toggleFacts = (entryId: number) => { factsOpen.value = factsOpen.value === entryId ? null : entryId; };

// Dishes whose recipe just changed (a confirmed swap): their rows glow once and the new dish pops in.
const fresh = ref(new Set<number>());
let freshTimer: ReturnType<typeof setTimeout> | undefined;
watch(() => props.days, (days) => {
  const changed = new Set<number>();
  for (const dish of days) {
    const before = lastShown.get(dish.entry_id);
    if (before && before !== dish.recipe.slug) changed.add(dish.entry_id);
    lastShown.set(dish.entry_id, dish.recipe.slug);
  }
  if (!changed.size) return;
  fresh.value = changed;
  clearTimeout(freshTimer);
  freshTimer = setTimeout(() => { fresh.value = new Set(); }, 2600);
  void nextTick(showFresh);
}, { immediate: true });
// The plan column scrolls the changed row to about a third of the way down, so the glow is seen.
const list = ref<HTMLElement | null>(null);
function showFresh() {
  const row = list.value?.querySelector<HTMLElement>(".row.fresh");
  let scroller = row?.parentElement ?? null;
  while (scroller && !/(auto|scroll)/.test(getComputedStyle(scroller).overflowY)) scroller = scroller.parentElement;
  if (!row || !scroller) return;
  const top = row.getBoundingClientRect().top - scroller.getBoundingClientRect().top + scroller.scrollTop - scroller.clientHeight / 3;
  scroller.scrollTo({ top: Math.max(0, top), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}
onBeforeUnmount(() => clearTimeout(freshTimer));

const week = computed(() => mealsByDay(props.days));
// Past seven days a weekday repeats, so an action names the date too.
const numbered = computed(() => week.value.length > 7);
const next = computed(() => nextMeal(props.days, todayIsoDate()));
// A dinner-only week reads as before, one row a day; with several meals each day gets a heading.
const severalMeals = computed(() => week.value.some(day => day.meals.length > 1));
const STATE: Record<string, string> = { completed: "Cooked", skipped: "Skipped", partial: "Part cooked" };
const CHIP_TONE: Record<string, string> = { next: "warn", tomorrow: "info", completed: "ok" };
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
// Shown as small icon buttons; the label is each one's name and tooltip (icon names literal for the icon bundle).
const ACTIONS = [
  { label: "Swap", icon: "i-lucide-repeat", text: (when: string, title: string) => `Swap ${when}'s ${title} for something else` },
  { label: "Keep", icon: "i-lucide-lock", text: (when: string, title: string) => `Lock ${when}'s ${title}` },
  { label: "Skip", icon: "i-lucide-skip-forward", text: (when: string, title: string) => `Skip ${when}'s ${title}` },
  { label: "Can't buy…", icon: "i-lucide-package-x", text: (when: string, title: string) => `I can't buy an ingredient for ${when}'s ${title}: ` },
];
const FEEDBACK_ICON: Record<string, string> = { like: "i-lucide-thumbs-up", dislike: "i-lucide-thumbs-down", never_again: "i-lucide-ban" };
</script>

<script lang="ts">
// Each dish entry's recipe as last shown, kept across mounts: the phone's plan sheet is closed while a swap is
// confirmed, and the changed dish should still stand out when it opens again.
const lastShown = new Map<number, string>();
</script>

<template>
  <div ref="list">
    <p v-if="feedbackError" class="feedback-error" role="alert">{{ feedbackError }}</p>
    <ol class="days" aria-label="Plan days">
      <li v-for="day in week" :key="day.dayIndex" class="day">
        <p v-if="severalMeals" class="day-head mc-label">
          {{ formatPlanDate(day.date, { weekday: "long" }) }} {{ formatPlanDate(day.date, { day: "numeric", month: "short" }) }}
        </p>
        <div
          v-for="meal in day.meals"
          :key="meal.key"
          class="row"
          :class="{ done: meal.status === 'completed' || meal.status === 'skipped', named: severalMeals, fresh: meal.dishes.some(dish => fresh.has(dish.entry_id)) }"
        >
          <span v-if="!severalMeals" class="d"><b>{{ formatPlanDate(day.date, { weekday: "short" }) }}</b><span>{{ Number(day.date.slice(8, 10)) }}</span></span>
          <HomeDishIcon class="icon" :slug="meal.dishes[0]!.recipe.slug" :title="meal.dishes[0]!.recipe.title" :size="32" />
          <!-- One line per dish: its name, then its own changes, so a meal of several dishes never shows unlabelled rows. -->
          <span class="dishes">
            <span v-for="(dish, index) in meal.dishes" :key="dish.entry_id" class="dish" :class="{ side: index > 0 }">
              <!-- With several meals a day, the meal's name is a caption over its first dish. -->
              <span v-if="severalMeals && index === 0" class="meal-cap">{{ MEAL_LABEL[meal.mealType] }}</span>
              <span class="title-line">
                <button type="button" class="name" :title="dish.recipe.title" @click="emit('openRecipe', dish.recipe.slug)"><span>{{ dish.recipe.title }}</span></button>
                <span v-if="isStapleDish(dish)" class="role-tag" title="Rice, noodles or bread with the meal">Staple</span>
                <!-- Who at this meal cannot eat this dish: the meal's other dishes cover them (ADR-0071). -->
                <span v-if="dish.not_for?.length" class="not-for" :title="`${dish.not_for.join(', ')} cannot eat this dish; other dishes at this meal are for them`">Not for {{ dish.not_for.join(", ") }}</span>
              </span>
              <!-- Facts true of the dish, never why it was chosen; a tag opens the dish's facts. Without a meta line they get their own row. -->
              <span v-if="dish.reasons?.length && !(index === 0 || dish.is_locked)" class="reasons">
                <button v-for="reason in dish.reasons" :key="reason.code" type="button" class="reason" :aria-expanded="factsOpen === dish.entry_id" @click="toggleFacts(dish.entry_id)">{{ reason.label }}</button>
              </span>
              <!-- The meta line: time and energy for a one-dish meal, then the meal's state (a one-dish count says nothing). -->
              <span v-if="index === 0 || dish.is_locked" class="rest">
                <span v-if="meal.dishes.length === 1" class="when">{{ dish.recipe.total_time_minutes }} min · {{ Math.round(dish.nutrition_per_person.calories_kcal) }} kcal</span>
                <span v-if="index === 0 && chip(meal).label !== '1 dish'" class="mc-chip" :class="CHIP_TONE[chip(meal).kind]">
                  <svg v-if="chip(meal).kind === 'completed'" class="ok-tick" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
                  <svg v-else-if="chip(meal).kind === 'partial'" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5a7 7 0 1 0 0 14V5Z" /></svg>
                  {{ chip(meal).label }}
                </span>
                <span v-if="dish.is_locked" class="kept">Kept as is</span>
                <button v-for="reason in dish.reasons ?? []" :key="reason.code" type="button" class="reason" :aria-expanded="factsOpen === dish.entry_id" @click="toggleFacts(dish.entry_id)">{{ reason.label }}</button>
              </span>
              <span v-if="factsOpen === dish.entry_id" :id="`facts-${dish.entry_id}`" class="facts" role="region" :aria-label="`Facts about ${dish.recipe.title}`">
                <span class="facts-head">Dish facts</span>
                <span v-for="fact in dishFacts(dish)" :key="fact.label" class="fact"><b>{{ fact.label }}</b> {{ fact.value }}</span>
              </span>
              <span v-if="changeable(dish) || rated(dish)" class="act-row">
                <span v-if="changeable(dish)" class="acts" role="group" :aria-label="`Change ${dish.recipe.title}`">
                  <button
                    v-for="(action, k) in ACTIONS"
                    :key="action.label"
                    type="button"
                    :style="{ '--k': k }"
                    :aria-label="action.label"
                    :title="action.label"
                    @click="emit('ask', action.text(sentenceDay(day.date, numbered), dish.recipe.title))"
                  >
                    <UIcon :name="action.icon" aria-hidden="true" />
                  </button>
                </span>
                <!-- Pressing the pressed button again undoes it; the whole household's, whoever pressed it. -->
                <span v-if="rated(dish)" class="feedback" role="group" :aria-label="`Feedback on ${dish.recipe.title}`">
                  <button
                    v-for="(button, k) in FEEDBACK_BUTTONS"
                    :key="button.kind"
                    type="button"
                    :style="{ '--k': k + ACTIONS.length }"
                    :aria-pressed="dish.feedback === button.kind"
                    :aria-busy="feedbackRecipeId === dish.recipe.id"
                    :disabled="feedbackRecipeId === dish.recipe.id"
                    :aria-label="button.label"
                    :title="button.label"
                    @click="emit('feedback', dish.recipe.id, nextFeedback(dish.feedback, button.kind))"
                  >
                    <UIcon :name="FEEDBACK_ICON[button.kind]!" aria-hidden="true" />
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
.days { list-style: none; margin: 0; padding: 0 16px; }
.day-head { margin: 0; padding: 12px 0 2px; }
.row { display: grid; grid-template-columns: 36px 32px minmax(0, 1fr); gap: 10px; align-items: start; min-height: 52px; padding: 12px 0 8px; border-bottom: 1px solid var(--c-line-soft); }
/* With several meals a day the day is the heading and the meal a caption over the dish: no first column. */
.row.named { grid-template-columns: 32px minmax(0, 1fr); }
.meal-cap { color: #71717a; font-size: 11px; line-height: 14px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; }
.d { display: flex; flex-direction: column; font-size: 12px; line-height: 16px; }
.d b { color: #71717a; font-weight: 600; }
.d span { color: #71717a; }
.dishes { min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.dish { min-width: 0; display: flex; flex-direction: column; }
.title-line { display: flex; align-items: center; gap: 8px; min-width: 0; }
.title-line .name { flex: 0 1 auto; min-width: 0; }
.not-for { flex: none; color: var(--c-muted); font-size: 11px; line-height: 18px; font-weight: 500; }
.role-tag { flex: none; padding: 0 7px; border: 1px solid var(--c-line); border-radius: 999px; color: var(--c-muted); font-size: 11px; line-height: 18px; font-weight: 500; }
.rest .mc-chip { flex: none; height: 20px; padding: 0 7px; font-size: 11.5px; }
.rest .mc-chip.warn { background: #f5f3ff; color: #6d28d9; }
.rest .mc-chip.info { background: #f4f4f5; color: #52525b; }
/* A long name takes two lines rather than an ellipsis. */
.name { max-width: 100%; padding: 0; border: 0; background: none; color: var(--mc-strong); font: inherit; font-size: 14px; line-height: 20px; font-weight: 600; text-align: left; }
.name > span { display: -webkit-box; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.dish.side .name { font-size: 13px; font-weight: 500; }
.name:hover { color: #6d28d9; }
/* Each chip keeps its own 20px line, so a wrapped line never runs into the next one. */
.rest { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; min-height: 20px; margin-top: 2px; font-size: 12.5px; line-height: 20px; color: var(--c-muted); }
.rest > * { flex: none; }
.rest .when { white-space: nowrap; }
.kept { color: var(--c-green-text); font-weight: 500; }
.ok-tick { color: var(--c-green); }
/* A dish's changes and its feedback: small ghost icon buttons on their own line under the chips. */
.act-row { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; min-height: 26px; margin: 6px 0 0 -5px; }
.acts, .feedback { display: flex; align-items: center; gap: 2px; }
.feedback { padding-left: 6px; border-left: 1px solid #f0f0f2; transition: border-color 200ms; }
/* Desktop: the icons wait until the row is pointed at or holds the focus, then come in one after another on a
   spring; they stay in place (and clickable) meanwhile. A pressed feedback button stays shown. Phone: always shown. */
@media (min-width: 768px) {
  .row { position: relative; }
  .row::before { content: ""; position: absolute; inset: 3px -8px; z-index: -1; border-radius: 12px; background: #f4f4f5; opacity: 0; transform: scale(0.98); transition: opacity 200ms ease, transform 420ms var(--spring); }
  .days { position: relative; z-index: 0; }
  .row:is(:hover, :focus-within)::before { opacity: 0.7; transform: none; }
  .act-row button:not([aria-pressed="true"]) { opacity: 0; transform: translateY(5px) scale(0.85); transition: opacity 160ms ease, transform 460ms var(--spring), background 150ms, color 150ms; transition-delay: 0ms; }
  .row:is(:hover, :focus-within) .act-row button { opacity: 1; transform: none; transition-delay: calc(var(--k, 0) * 22ms); }
  .feedback { border-left-color: transparent; }
  .row:is(:hover, :focus-within) .feedback { border-left-color: #e4e4e7; }
}
/* Dark enough that the dimmed icons still reach 3:1 on the plan column. */
.acts button, .feedback button { flex: none; width: 26px; height: 26px; display: grid; place-items: center; padding: 0; border: 0; border-radius: 8px; background: transparent; color: #3f3f46; }
.acts button .iconify, .feedback button .iconify { width: 16px; height: 16px; }
.acts button:hover, .feedback button:hover { background: #f4f4f5; color: var(--mc-strong); }
.feedback button[aria-pressed="true"] { background: #f5f3ff; color: #6d28d9; }
.feedback button:disabled { opacity: 0.5; }
.never { font-size: 12px; line-height: 24px; color: var(--c-muted); font-weight: 500; white-space: nowrap; }
.never button { padding: 0; border: 0; background: none; color: #6d28d9; font: inherit; font-weight: 600; }
.reasons { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
.reason { height: 20px; padding: 0 8px; border: 0; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 11.5px; font-weight: 500; white-space: nowrap; }
.reason:hover { background: #e9e9ec; color: #18181b; }
.reason[aria-expanded="true"] { background: #e4e4e7; color: #18181b; }
.facts { display: flex; flex-wrap: wrap; gap: 2px 14px; margin-top: 6px; padding: 8px 12px; border: 1px solid #f0f0f2; border-radius: 10px; background: #fafafa; color: #27272a; font-size: 12px; line-height: 18px; }
.facts-head { flex-basis: 100%; color: #71717a; font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; }
.fact b { font-weight: 500; }
.feedback-error { margin: 8px 16px 0; color: #b42318; font-size: 12px; font-weight: 500; }
/* A dish just swapped in: a violet wash on its row that fades, the new dish's plate pops and its name rises. */
.days { position: relative; z-index: 0; }
.row.fresh { position: relative; }
.row.fresh::after { content: ""; position: absolute; inset: 3px -8px; z-index: -1; border-radius: 12px; background: #f5f3ff; box-shadow: inset 0 0 0 1px #ddd6fe; animation: fresh-wash 2.6s ease-out both; }
.row.fresh .icon { animation: fresh-pop 760ms var(--spring) both; }
.row.fresh .name { animation: fresh-rise 620ms var(--spring) 90ms both; }
@keyframes fresh-wash { 0%, 50% { opacity: 1; } 100% { opacity: 0; } }
@keyframes fresh-pop { from { opacity: 0; transform: scale(0.4) rotate(-30deg); } }
@keyframes fresh-rise { from { opacity: 0; transform: translateY(8px); filter: blur(4px); } }
@media (prefers-reduced-motion: reduce) { .row.fresh .icon, .row.fresh .name { animation: none; } }
</style>
