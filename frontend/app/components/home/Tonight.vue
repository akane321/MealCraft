<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { MEAL_LABEL, nextMeal, plateStyle, type PlannedMeal } from "~/lib/home-surface";
import type { NutritionDashboardDay } from "~/types/meal-plan";
import type { TutorialRecommendation } from "~/types/recipe";

const props = defineProps<{ days: NutritionDashboardDay[]; updatingEntryId: number | null }>();
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
    <span class="mc-eyebrow">{{ eyebrow }} · {{ formatPlanDate(tonight.day.planned_date, { weekday: "short", day: "numeric", month: "short" }) }}</span>
    <h2 class="mc-serif">{{ tonight.day.recipe.title }}</h2>
    <p v-if="others.length" class="with">
      with
      <template v-for="(dish, index) in others" :key="dish.entry_id">
        <button type="button" class="dish-link" @click="emit('openRecipe', dish.recipe.slug)">{{ dish.recipe.title }}</button><span v-if="index < others.length - 1">, </span>
      </template>
    </p>
    <p class="meta">
      <span>{{ tonight.day.recipe.total_time_minutes }} min</span>
      <span>{{ mealKcal }} kcal each</span>
      <span v-if="next?.meal.status === 'completed'" class="done">Cooked</span>
    </p>
    <div class="acts">
      <button type="button" class="mc-primary" @click="emit('openRecipe', tonight.day.recipe.slug)">Recipe &amp; steps</button>
      <button
        v-if="next && next.meal.status !== 'completed' && next.meal.status !== 'skipped'"
        type="button"
        class="mc-pill"
        :disabled="updatingEntryId === tonight.day.entry_id"
        @click="markCooked"
      >
        {{ updatingEntryId === tonight.day.entry_id ? "Saving…" : "Mark as cooked" }}
      </button>
      <button type="button" class="mc-pill" @click="emit('swap', tonight.day)">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 8h13l-3-3M20 16H7l3 3" /></svg>Swap
      </button>
    </div>
    <span class="plate" :style="plateStyle(tonight.day.recipe.slug)" aria-hidden="true" />

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
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>
        </span>
        <span class="caption">
          <small>{{ tutorial?.retrieval.provider_used === "youtube" ? "How-to video · best match on YouTube" : "Sample how-to video" }}</small>
          <span>{{ video.title }}</span>
        </span>
      </button>
      <p v-else class="no-video">No how-to video for this dish yet.</p>
    </div>
  </section>
  <section v-else-if="days.length" class="tonight quiet" aria-label="Next meal">
    <span class="mc-eyebrow">This week</span>
    <h2 class="mc-serif">Every meal this week is done.</h2>
    <p class="meta">Ask for next week whenever you're ready.</p>
  </section>
</template>

<style scoped>
.tonight {
  position: relative;
  flex: none;
  padding: 20px 22px 18px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 4px 16px;
  overflow: hidden;
  border-bottom: 1px solid var(--line);
  background:
    linear-gradient(180deg, rgba(21, 18, 16, 0.2) 0%, rgba(21, 18, 16, 0.6) 45%, rgba(21, 18, 16, 0.94) 85%, var(--s1) 100%),
    url("/media/hero-poster.jpg") center 88% / cover;
}
.tonight > .mc-eyebrow, .acts, .video { grid-column: 1 / -1; }
h2 { margin: 6px 0 0; font-size: 28px; line-height: 1.08; letter-spacing: -0.01em; text-wrap: balance; }
.with { margin: 6px 0 0; font-size: 13px; color: var(--t2); line-height: 1.5; }
.dish-link { padding: 0; border: 0; background: none; color: var(--ivory); font: inherit; text-decoration: underline; text-decoration-color: var(--line-2); text-underline-offset: 3px; }
.dish-link:hover { text-decoration-color: var(--accent); }
.meta { margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 12px; color: var(--t2); font-size: 12.5px; }
.meta .done { color: var(--sage); }
.acts { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 8px; }
.tonight > .plate { --size: 92px; grid-row: 2 / 4; grid-column: 2; align-self: center; animation: turn 60s linear infinite; }
@keyframes turn { to { transform: rotate(360deg); } }

.video { margin-top: 14px; }
.video iframe { width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: 12px; display: block; }
.poster { width: 100%; padding: 6px; border: 1px solid var(--line); border-radius: 12px; background: rgba(14, 12, 10, 0.55); display: flex; align-items: center; gap: 12px; text-align: left; }
.poster:hover { border-color: var(--line-2); }
.thumb { width: 88px; aspect-ratio: 16 / 9; flex: none; border-radius: 8px; background: radial-gradient(circle at 35% 40%, #6b4a33, #2a1d15) center / cover; display: grid; place-items: center; }
.thumb svg { width: 16px; height: 16px; fill: var(--ivory); filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.6)); }
.caption { min-width: 0; display: grid; font-size: 12.5px; }
.caption small { font-size: 11px; color: var(--t3); }
.caption span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.no-video { margin: 0; font-size: 12px; color: var(--t3); }
.quiet { background: var(--s1); }
</style>
