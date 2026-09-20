<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { tonightEntry } from "~/lib/home-surface";
import type { NutritionDashboardDay } from "~/types/meal-plan";
import type { TutorialRecommendation } from "~/types/recipe";

const props = defineProps<{
  days: NutritionDashboardDay[];
  rangeLabel: string;
  cookedCount: number;
  updatingEntryId: number | null;
  planId: number | null;
}>();
const emit = defineEmits<{ markCooked: [entryId: number]; openRecipe: [slug: string] }>();

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const today = todayIsoDate();
const tonight = computed(() => tonightEntry(props.days, today));
const tutorial = ref<TutorialRecommendation | null>(null);
const playing = ref(false);

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

function dayParts(date: string) {
  return {
    weekday: formatPlanDate(date, { weekday: "short" }),
    date: Number(date.slice(8, 10)),
  };
}

function statusLabel(day: NutritionDashboardDay) {
  if (day.status === "completed") return "Cooked";
  if (day.status === "skipped") return "Skipped";
  if (tonight.value?.day.entry_id === day.entry_id) return tonight.value.isToday ? "Tonight" : "Next";
  return "Planned";
}
</script>

<template>
  <div class="week-panel">
    <header>
      <div>
        <h2 class="mc-serif">This week</h2>
        <p>{{ rangeLabel }} · {{ days.length }} dinners · {{ cookedCount }} cooked</p>
      </div>
      <slot name="actions" />
    </header>

    <ol class="mc-frost week-list">
      <li
        v-for="day in days"
        :key="day.entry_id"
        :class="{ current: tonight?.day.entry_id === day.entry_id, skipped: day.status === 'skipped' }"
      >
        <span class="date"><small>{{ dayParts(day.planned_date).weekday }}</small>{{ dayParts(day.planned_date).date }}</span>
        <span class="dish">
          <button type="button" class="title" @click="emit('openRecipe', day.recipe.slug)">{{ day.recipe.title }}</button>
          <small>{{ Math.round(day.nutrition_per_person.calories_kcal) }} kcal · {{ day.recipe.total_time_minutes }} min</small>
        </span>
        <span class="status" :class="day.status">
          <svg v-if="day.status === 'completed'" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
          {{ statusLabel(day) }}
        </span>
      </li>
    </ol>

    <HomeChangeLog :plan-id="planId" />

    <section v-if="tonight" class="mc-frost tonight" aria-label="Tonight's dinner">
      <p><span class="mc-eyebrow">{{ tonight.isToday ? "Tonight" : "Next up" }}</span> <strong class="mc-serif">{{ tonight.day.recipe.title }}</strong></p>
      <div class="video">
        <iframe
          v-if="playing && tutorial?.selected_video"
          :src="`${tutorial.selected_video.embed_url}?autoplay=1`"
          :title="tutorial.selected_video.title"
          allow="autoplay; encrypted-media; picture-in-picture"
          allowfullscreen
        />
        <button
          v-else-if="tutorial?.selected_video"
          type="button"
          class="poster"
          :style="tutorial.selected_video.thumbnail_url ? { backgroundImage: `url(${tutorial.selected_video.thumbnail_url})` } : undefined"
          :aria-label="`Play how-to video: ${tutorial.selected_video.title}`"
          @click="playing = true"
        >
          <span class="play"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg></span>
          <span class="caption">{{ tutorial.retrieval.provider_used === "youtube" ? "How-to video · best match on YouTube" : "Sample how-to video" }}</span>
        </button>
        <p v-else class="no-video">No how-to video for this dish yet.</p>
      </div>
      <div class="tonight-actions">
      <button type="button" class="mc-pill cooked" @click="emit('openRecipe', tonight.day.recipe.slug)">Recipe &amp; steps</button>
      <button
        v-if="tonight.day.status === 'planned'"
        type="button"
        class="mc-primary cooked"
        :disabled="updatingEntryId === tonight.day.entry_id"
        @click="emit('markCooked', tonight.day.entry_id)"
      >
        {{ updatingEntryId === tonight.day.entry_id ? "Saving…" : "Mark as cooked" }}
      </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.week-panel { display: flex; flex-direction: column; gap: 14px; height: 100%; overflow-y: auto; scrollbar-width: none; }
header { display: flex; align-items: center; gap: 8px; }
header > div { flex-grow: 1; }
h2 { margin: 0; font-size: 22px; }
header p { margin: 2px 0 0; font-size: 12px; color: var(--mc-text-3); }

.week-list { list-style: none; margin: 0; padding: 6px; border-radius: 18px; }
.week-list li { min-height: 50px; padding: 0 10px; border-radius: 12px; display: flex; align-items: center; gap: 12px; }
.week-list li:hover { background: rgba(242, 237, 228, 0.06); }
.week-list li.current { background: rgba(194, 85, 58, 0.16); box-shadow: inset 0 0 0 1px rgba(232, 144, 111, 0.45); }
.week-list li.skipped .dish { opacity: 0.55; }
.date { width: 34px; display: flex; flex-direction: column; font-size: 15px; line-height: 1.15; }
.date small { font-size: 11px; font-weight: 600; color: var(--mc-text-3); }
.dish { flex-grow: 1; min-width: 0; display: flex; flex-direction: column; }
.dish .title { padding: 0; border: 0; background: none; color: var(--mc-ivory); text-align: left; font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dish .title:hover { text-decoration: underline; }
.tonight-actions { display: flex; gap: 8px; }
.tonight-actions button { flex: 1; }
.dish small { font-size: 11px; color: var(--mc-text-3); }
.status { flex-shrink: 0; display: flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; color: var(--mc-text-3); }
.status.completed { color: var(--mc-sage); }
.current .status { color: var(--mc-accent); }
.status svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }

.tonight { padding: 14px; border-radius: 18px; display: flex; flex-direction: column; gap: 10px; }
.tonight > p { margin: 0; display: flex; align-items: baseline; gap: 8px; }
.tonight > p strong { font-size: 17px; }
.video { aspect-ratio: 16 / 9; border-radius: 14px; overflow: hidden; background: radial-gradient(circle at 35% 40%, #6b4a33, #2a1d15); }
.video iframe { width: 100%; height: 100%; border: 0; }
.poster { position: relative; width: 100%; height: 100%; padding: 0; border: 0; background-size: cover; background-position: center; display: flex; align-items: center; justify-content: center; }
.play { width: 52px; height: 52px; border-radius: 999px; background: rgba(242, 237, 228, 0.25); border: 1px solid rgba(242, 237, 228, 0.5); backdrop-filter: blur(12px); display: flex; align-items: center; justify-content: center; }
.play svg { width: 18px; height: 18px; fill: var(--mc-ivory); }
.caption { position: absolute; left: 10px; bottom: 10px; padding: 4px 10px; border-radius: 999px; background: rgba(14, 12, 10, 0.72); color: var(--mc-ivory); font-size: 11px; }
.no-video { margin: 0; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 13px; color: var(--mc-text-2); }
.cooked { min-height: 44px; font-size: 13px; }
</style>
