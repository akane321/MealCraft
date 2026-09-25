<script setup lang="ts">
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { plateStyle, tonightEntry } from "~/lib/home-surface";
import type { NutritionDashboardDay } from "~/types/meal-plan";

const props = defineProps<{ days: NutritionDashboardDay[]; planId: number | null }>();
const emit = defineEmits<{ openRecipe: [slug: string] }>();

const tonight = computed(() => tonightEntry(props.days, todayIsoDate()));

function statusLabel(day: NutritionDashboardDay) {
  if (day.status === "completed") return "Cooked";
  if (day.status === "skipped") return "Skipped";
  if (tonight.value?.day.entry_id === day.entry_id) return tonight.value.isToday ? "Tonight" : "Next";
  return "";
}
</script>

<template>
  <div>
    <ol class="rows">
      <li
        v-for="day in days"
        :key="day.entry_id"
        class="row"
        :class="{ today: tonight?.day.entry_id === day.entry_id, done: day.status !== 'planned' }"
      >
        <span class="d"><span>{{ formatPlanDate(day.planned_date, { weekday: "short" }) }}</span><b class="mc-serif">{{ Number(day.planned_date.slice(8, 10)) }}</b></span>
        <span class="plate" :style="plateStyle(day.recipe.slug)" aria-hidden="true" />
        <span class="dish">
          <button type="button" class="name mc-serif" @click="emit('openRecipe', day.recipe.slug)">{{ day.recipe.title }}</button>
          <small>{{ day.recipe.total_time_minutes }} min · {{ Math.round(day.nutrition_per_person.calories_kcal) }} kcal</small>
        </span>
        <span class="state" :class="day.status">{{ statusLabel(day) }}</span>
      </li>
    </ol>
    <div class="log"><HomeChangeLog :plan-id="planId" /></div>
  </div>
</template>

<style scoped>
.rows { list-style: none; margin: 0; padding: 0; }
.row { display: grid; grid-template-columns: 38px 36px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 11px 22px; border-bottom: 1px solid var(--line); }
.row:hover { background: rgba(242, 237, 228, 0.025); }
.row.today { background: rgba(232, 144, 111, 0.06); }
.d { display: grid; line-height: 1.1; }
.d span { font-size: 10px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.today .d span { color: var(--accent); }
.d b { font-size: 19px; }
.row .plate { --size: 36px; }
.dish { min-width: 0; display: grid; }
.name { padding: 0; border: 0; background: none; text-align: left; font-size: 15px; font-weight: 400; line-height: 1.25; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.name:hover { text-decoration: underline; text-underline-offset: 3px; }
.done .name { color: var(--t3); }
.dish small { font-size: 11.5px; color: var(--t3); }
.state { font-size: 11px; font-weight: 500; color: var(--accent); text-align: right; }
.state.completed { color: var(--sage); }
.state.skipped { color: var(--t4); }
.log { padding: 4px 22px 18px; }
</style>
