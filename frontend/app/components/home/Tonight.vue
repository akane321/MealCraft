<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { MEAL_LABEL, nextMeal, type PlannedMeal } from "~/lib/home-surface";
import type { NutritionDashboardDay } from "~/types/meal-plan";
import type { TutorialRecommendation } from "~/types/recipe";

// A replaced week (readonly) is only read: no marking cooked, no swap.
const props = defineProps<{ days: NutritionDashboardDay[]; updatingEntryId: number | null; readonly?: boolean }>();
const emit = defineEmits<{
  markCooked: [entryId: number];
  markMeal: [meal: PlannedMeal];
  openRecipe: [slug: string];
  swap: [day: NutritionDashboardDay];
}>();

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
// The next meal to cook (ADR-0046): its main dish leads, the others are listed beside it.
const next = computed(() => nextMeal(props.days, todayIsoDate()));
const tonight = computed(() => (next.value ? { day: next.value.meal.dishes[0]!, isToday: next.value.isToday } : null));
const others = computed(() => next.value?.meal.dishes.slice(1) ?? []);
const mealKcal = computed(() => Math.round(next.value?.meal.dishes.reduce((sum, dish) => sum + dish.nutrition_per_person.calories_kcal, 0) ?? 0));
const eyebrow = computed(() => {
  if (!next.value) return "";
  const label = MEAL_LABEL[next.value.meal.mealType];
  if (!next.value.isToday) return `Next up · ${label}`;
  return next.value.meal.mealType === "dinner" ? "Tonight" : `Today's ${label.toLowerCase()}`;
});

function markCooked() {
  const meal = next.value?.meal;
  if (!meal) return;
  if (meal.dishes.length > 1) emit("markMeal", meal);
  else emit("markCooked", meal.dishes[0]!.entry_id);
}
const tutorial = ref<TutorialRecommendation | null>(null);
const playing = ref(false);
const video = computed(() => tutorial.value?.selected_video ?? null);

watch(() => tonight.value?.day.recipe.slug, async (slug) => {
  tutorial.value = null;
  playing.value = false;
  if (!slug) return;
  try {
    tutorial.value = await apiFetch<TutorialRecommendation>(`${config.public.apiBase}/api/recipes/${slug}/tutorial`);
  }
  catch {
    tutorial.value = null;
  }
}, { immediate: true });
</script>


<template>
  <section v-if="tonight" class="tonight" aria-label="Next meal">
    <HomeDishIcon class="big-icon" :title="tonight.day.recipe.title" :course="tonight.day.recipe.course" :role-id="tonight.day.role_id" :size="64" />
    <div class="head">
      <span class="kicker">{{ eyebrow }} · {{ formatPlanDate(tonight.day.planned_date, { weekday: "short", day: "numeric", month: "short" }) }}</span>
      <h2>{{ tonight.day.recipe.title }}</h2>
      <p v-if="others.length" class="with">
        with
        <template v-for="(dish, index) in others" :key="dish.entry_id">
          <button type="button" class="dish-link" @click="emit('openRecipe', dish.recipe.slug)">{{ dish.recipe.title }}</button><span v-if="index < others.length - 2">, </span><span v-else-if="index === others.length - 2"> and </span>
        </template>
      </p>
      <p class="meta">
        {{ tonight.day.recipe.total_time_minutes }} min · {{ mealKcal }} kcal each<template v-if="next?.meal.status === 'completed'"> · <span class="done">Cooked</span></template>
      </p>
    </div>

    <div class="video">
        <iframe
          v-if="playing && video"
          :src="`${video.embed_url}?autoplay=1`"
          :title="video.title"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowfullscreen
        />
        <button
          v-else-if="video"
          type="button"
          class="poster"
          :aria-label="`Play how-to video: ${video.title}`"
          @click="playing = true"
        >
          <span class="thumb" :style="video.thumbnail_url ? { backgroundImage: `url(${video.thumbnail_url})` } : undefined">
            <span class="play"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4v16l13-8z" /></svg></span>
            <span v-if="video.duration_seconds" class="len">{{ Math.floor(video.duration_seconds / 60) }}:{{ String(video.duration_seconds % 60).padStart(2, "0") }}</span>
          </span>
          <span class="caption">
            <small>{{ tutorial?.retrieval.provider_used === "youtube" ? "How-to video · best match on YouTube" : "Sample how-to video" }}</small>
            <span>{{ video.title }}</span>
          </span>
        </button>
        <p v-else class="no-video">No how-to video for this dish yet.</p>
      </div>

      <div class="acts">
        <button type="button" class="mc-btn primary sm" @click="emit('openRecipe', tonight.day.recipe.slug)">Recipe and steps</button>
        <button
          v-if="!readonly && next && next.meal.status !== 'completed' && next.meal.status !== 'skipped'"
          type="button"
          class="mc-btn secondary sm cooked"
          :disabled="updatingEntryId === tonight.day.entry_id"
          @click="markCooked"
        >
          {{ updatingEntryId === tonight.day.entry_id ? "Saving…" : "Mark cooked" }}
        </button>
        <button v-if="!readonly" type="button" class="mc-btn quiet sm" @click="emit('swap', tonight.day)">Swap</button>
      </div>
  </section>
  <section v-else-if="days.length" class="tonight quiet" aria-label="Next meal">
    <div class="head">
      <span class="mc-label">This week</span>
      <h2>Every meal this week is done.</h2>
      <p class="meta">Ask for next week whenever you're ready.</p>
    </div>
  </section>
</template>

<style scoped>
.tonight { display: grid; grid-template-columns: 64px minmax(0, 1fr); column-gap: 14px; margin: 16px 16px 4px; padding: 16px; border-radius: 16px; background: var(--c-tonight); }
.big-icon { grid-row: 1; align-self: start; }
.head { grid-column: 2; display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.video, .acts { grid-column: 1 / -1; }
.quiet .head { grid-column: 1 / -1; }
.kicker { font-size: 12px; line-height: 16px; font-weight: 800; color: var(--c-amber-text); }
h2 { margin: 0; font-family: var(--font-display); font-weight: 700; font-size: 20px; line-height: 26px; }
.with { margin: 0; font-size: 13px; color: var(--c-neutral-text); }
.dish-link { padding: 0; border: 0; background: none; color: inherit; font: inherit; text-decoration: underline; text-decoration-color: var(--c-tonight-border); text-underline-offset: 3px; }
.dish-link:hover { color: var(--c-ink); text-decoration-color: var(--c-coral); }
.meta { margin: 0; font-size: 12px; line-height: 16px; color: var(--c-muted); }
.meta .done { color: var(--c-green-text); font-weight: 800; }
.video { margin-top: 10px; }
.video iframe { width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: 12px; display: block; }
.poster { width: 100%; padding: 6px; border: 0; border-radius: 12px; background: #fff; display: flex; align-items: center; gap: 10px; text-align: left; color: var(--c-ink); }
.poster:hover .caption span { color: var(--c-coral); }
.thumb { position: relative; width: 88px; height: 50px; flex: none; border-radius: 8px; overflow: hidden; background: linear-gradient(135deg, #7a3e1e, #d98b3a 55%, #f3d08a) center / cover; }
.play { position: absolute; left: 50%; top: 50%; width: 24px; height: 24px; margin: -12px 0 0 -12px; border-radius: 50%; background: rgba(255, 255, 255, 0.92); display: flex; align-items: center; justify-content: center; }
.play svg { width: 10px; height: 10px; fill: var(--c-ink); }
.len { position: absolute; right: 4px; bottom: 3px; padding: 0 4px; border-radius: 4px; background: rgba(0, 0, 0, 0.55); color: #fff; font-size: 12px; line-height: 14px; font-weight: 800; }
.caption { min-width: 0; display: flex; flex-direction: column; }
.caption small { font-size: 12px; line-height: 16px; font-weight: 800; color: var(--c-muted); }
.caption span { font-size: 13px; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.no-video { margin: 0; padding: 10px 12px; border-radius: 12px; background: #fff; font-size: 12px; line-height: 16px; color: var(--c-muted); }
.acts { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.acts .cooked { border-color: var(--c-tonight-border); }
.quiet { background: var(--c-canvas); }
</style>
