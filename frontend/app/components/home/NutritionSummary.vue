<script setup lang="ts">
import { perDinner } from "~/lib/home-surface";
import type { WeeklyNutritionDashboard } from "~/types/meal-plan";
import type { RecipeNutrition } from "~/types/recipe";

const props = defineProps<{ dashboard: WeeklyNutritionDashboard; sodiumLimit: number | null }>();
const emit = defineEmits<{ details: [] }>();

const average = computed(() => perDinner(props.dashboard.days));
const cooked = computed(() => props.dashboard.status_counts.completed);
const kcalTarget = computed(() => props.dashboard.nutrition_targets.calories_kcal);

const rows = computed(() => {
  const avg = average.value;
  if (!avg) return [];
  const targets = props.dashboard.nutrition_targets;
  const spec: Array<[keyof RecipeNutrition, string, string, number | null, boolean]> = [
    ["protein_g", "Protein", "g", targets.protein_g, false],
    ["carbohydrate_g", "Carbohydrate", "g", targets.carbohydrate_g, false],
    ["fat_g", "Fat", "g", targets.fat_g, false],
    ["sodium_mg", "Sodium", "mg", props.sodiumLimit, true],
    ["sugar_g", "Sugar", "g", null, false],
  ];
  return spec.map(([key, label, unit, target, isLimit]) => {
    const value = avg[key];
    // The bar's full width sits a little past the larger of value and target.
    const scale = Math.max(value, target ?? 0) / 0.8 || 1;
    return {
      key,
      label,
      value: `${Math.round(value)} ${unit}`,
      target: target === null ? null : `${isLimit ? "limit" : "target"} ${Math.round(target)} ${unit}`,
      width: `${value / scale * 100}%`,
      tick: target === null ? null : `${target / scale * 100}%`,
      over: isLimit && target !== null && value > target,
    };
  });
});
</script>

<template>
  <div class="nutri">
    <div class="big">
      <b class="mc-serif mc-num">{{ Math.round(average?.calories_kcal ?? 0) }}</b>
      <span>kcal per person, per dinner<template v-if="kcalTarget"> · target {{ Math.round(kcalTarget) }}</template></span>
    </div>
    <div v-for="row in rows" :key="row.key" class="bar-row" :class="{ over: row.over }">
      <div class="top"><span>{{ row.label }}</span><span v-if="row.target" class="t">{{ row.target }}</span><span class="v mc-num">{{ row.value }}</span></div>
      <div class="bar"><i :style="{ width: row.width }" /><span v-if="row.tick" class="tick" :style="{ left: row.tick }" /></div>
    </div>
    <p class="eaten">
      Eaten so far: {{ cooked }} {{ cooked === 1 ? "dinner" : "dinners" }},
      {{ Math.round(dashboard.completed_nutrition_per_person.calories_kcal).toLocaleString("en-SG") }} kcal and
      {{ Math.round(dashboard.completed_nutrition_per_person.protein_g) }} g protein per person.
    </p>
    <button type="button" class="mc-pill" @click="emit('details')">All six nutrients &amp; daily detail</button>
    <p class="lead">Averaged over this week's dinners. General guidance, not medical advice.</p>
  </div>
</template>

<style scoped>
.nutri { padding: 18px 22px; display: grid; gap: 18px; }
.big { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px; }
.big b { font-size: 44px; line-height: 1; font-weight: 300; }
.big span { color: var(--t3); font-size: 12.5px; }
.bar-row { display: grid; gap: 6px; }
.top { display: flex; align-items: baseline; gap: 8px; font-size: 13px; }
.top .t { color: var(--t4); font-size: 11.5px; }
.top .v { margin-left: auto; }
.bar { position: relative; height: 6px; border-radius: 99px; background: var(--s3); }
.bar i { position: absolute; inset: 0 auto 0 0; border-radius: 99px; background: var(--sage); }
.tick { position: absolute; top: -4px; bottom: -4px; width: 1.5px; background: var(--ivory); opacity: 0.5; }
.over .bar i { background: var(--warn); }
.over .v { color: var(--warn); }
.eaten, .lead { margin: 0; font-size: 12.5px; line-height: 1.6; color: var(--t3); }
</style>
