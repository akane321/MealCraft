<script setup lang="ts">
import { budgetLine, formatSgd, groceryGroups, packageLabel, priceSourceLabel } from "~/lib/home-surface";
import type { NutritionDashboardDay, WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { RecipeNutrition } from "~/types/recipe";

const props = defineProps<{
  days: NutritionDashboardDay[];
  eaten: RecipeNutrition | null;
  estimate: WeeklyGroceryEstimate | null;
}>();
const emit = defineEmits<{ preview: []; export: []; details: [] }>();

const cooked = computed(() => props.days.filter(day => day.status === "completed").length);
const counted = computed(() => props.days.filter(day => day.status !== "skipped"));
const averageKcal = computed(() => counted.value.length
  ? Math.round(counted.value.reduce((sum, day) => sum + day.nutrition_per_person.calories_kcal, 0) / counted.value.length)
  : null);
const bars = computed(() => {
  const max = Math.max(...props.days.map(day => day.nutrition_per_person.calories_kcal), 1);
  return props.days.map(day => ({
    id: day.entry_id,
    label: new Date(`${day.planned_date}T00:00:00`).toLocaleDateString("en-SG", { weekday: "narrow" }),
    height: `${Math.max(6, Math.round(day.nutrition_per_person.calories_kcal / max * 100))}%`,
    status: day.status,
  }));
});
const barsLabel = computed(() => `Calories per dinner: ${props.days
  .map(day => `${day.planned_date} ${Math.round(day.nutrition_per_person.calories_kcal)} kcal ${day.status}`)
  .join(", ")}`);

const lines = computed(() => groceryGroups(props.estimate?.items ?? []).flatMap(group => group.lines));
const topLines = computed(() => [...lines.value].sort((a, b) => b.purchase_cost_sgd - a.purchase_cost_sgd).slice(0, 4));
const budgetShare = computed(() => {
  const budget = props.estimate?.weekly_budget_sgd;
  return budget ? Math.min(100, props.estimate!.purchase_total_sgd / budget * 100) : null;
});
</script>

<template>
  <div class="kitchen-panel">
    <header>
      <h2 class="mc-serif">Kitchen</h2>
      <slot name="actions" />
    </header>

    <section class="mc-frost card" aria-label="Nutrition">
      <p class="label">Eaten so far · {{ cooked }} {{ cooked === 1 ? "dinner" : "dinners" }} · per person</p>
      <div class="figures">
        <span><strong class="mc-serif">{{ Math.round(eaten?.calories_kcal ?? 0).toLocaleString("en-SG") }}</strong><small>kcal</small></span>
        <span><strong class="mc-serif">{{ Math.round(eaten?.protein_g ?? 0) }} g</strong><small>protein</small></span>
        <span v-if="averageKcal !== null"><strong class="mc-serif">{{ averageKcal }}</strong><small>kcal a night, planned</small></span>
      </div>
      <div class="bars" role="img" :aria-label="barsLabel">
        <span v-for="bar in bars" :key="bar.id" class="bar-slot">
          <span class="bar" :class="bar.status" :style="{ height: bar.height }" />
          <small>{{ bar.label }}</small>
        </span>
      </div>
      <p class="legend">
        <span><i class="swatch completed" />Cooked</span>
        <span><i class="swatch planned" />Planned</span>
        <span class="note">General guidance, not medical advice</span>
      </p>
      <button type="button" class="mc-pill details" @click="emit('details')">All six nutrients &amp; daily detail</button>
    </section>

    <section v-if="estimate" class="mc-frost card groceries" aria-label="Groceries">
      <p class="label"><span>Groceries · {{ priceSourceLabel(estimate) }}</span><span>{{ lines.length }} items</span></p>
      <p class="total"><strong class="mc-serif">{{ formatSgd(estimate.purchase_total_sgd) }}</strong>
        <span v-if="budgetLine(estimate)" :class="{ over: estimate.within_weekly_budget === false }">{{ budgetLine(estimate) }}</span>
      </p>
      <div v-if="budgetShare !== null" class="budget" role="img" :aria-label="`${Math.round(budgetShare)} percent of the weekly budget`">
        <span :style="{ width: `${budgetShare}%` }" />
      </div>
      <ul>
        <li v-for="line in topLines" :key="line.ingredient_name">
          <span class="name">{{ line.ingredient_display_name }}</span>
          <span class="pack">{{ packageLabel(line) }}</span>
          <span class="price">{{ formatSgd(line.purchase_cost_sgd) }}</span>
        </li>
      </ul>
      <p v-if="lines.length > topLines.length || estimate.unmapped_ingredients.length" class="more">
        <template v-if="lines.length > topLines.length">+ {{ lines.length - topLines.length }} more</template>
        <template v-if="estimate.unmapped_ingredients.length"> · {{ estimate.unmapped_ingredients.length }} without a price</template>
      </p>
      <div class="actions">
        <button type="button" class="mc-pill" @click="emit('preview')">Preview list</button>
        <button type="button" class="mc-primary" @click="emit('export')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14" /></svg>
          Export PDF
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.kitchen-panel { display: flex; flex-direction: column; gap: 14px; height: 100%; overflow-y: auto; scrollbar-width: none; }
header { display: flex; align-items: center; gap: 8px; }
h2 { flex-grow: 1; margin: 0; font-size: 22px; }
.card { padding: 14px; border-radius: 18px; display: flex; flex-direction: column; gap: 10px; }
.label { margin: 0; display: flex; justify-content: space-between; gap: 8px; font-size: 12px; font-weight: 600; color: var(--mc-text-2); }
.figures { display: flex; gap: 20px; }
.figures span { display: flex; flex-direction: column; }
.figures strong { font-size: 28px; }
.figures small { font-size: 11px; color: var(--mc-text-3); }
.bars { height: 104px; display: flex; align-items: flex-end; gap: 8px; }
.bar-slot { flex: 1; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; gap: 4px; }
.bar-slot small { font-size: 10px; color: var(--mc-text-3); }
.bar { width: 100%; box-sizing: border-box; border-radius: 6px; max-height: calc(100% - 16px); }
.bar.completed { background: var(--mc-ivory); }
.bar.planned { border: 1.5px dashed var(--mc-text-2); }
.bar.skipped { border: 1px solid var(--mc-line); }
.legend { margin: 0; display: flex; align-items: center; gap: 14px; font-size: 11px; color: var(--mc-text-3); }
.legend span { display: flex; align-items: center; gap: 5px; }
.legend .note { margin-left: auto; }
.details { min-height: 38px; font-size: 12px; font-weight: 500; }
.swatch { width: 10px; height: 10px; box-sizing: border-box; border-radius: 3px; }
.swatch.completed { background: var(--mc-ivory); }
.swatch.planned { border: 1.5px dashed var(--mc-text-2); }

.groceries { flex-grow: 1; min-height: 0; }
.total { margin: 0; display: flex; align-items: baseline; gap: 10px; }
.total strong { font-size: 32px; }
.total span { font-size: 12px; font-weight: 500; color: var(--mc-sage); }
.total span.over { color: var(--mc-accent); }
.budget { height: 6px; border-radius: 999px; background: rgba(242, 237, 228, 0.1); overflow: hidden; }
.budget span { display: block; height: 100%; border-radius: 999px; background: var(--mc-text-2); transition: width 600ms var(--mc-ease); }
ul { list-style: none; margin: 0; padding: 0; }
li { min-height: 34px; display: flex; align-items: center; gap: 10px; border-top: 1px solid rgba(242, 237, 228, 0.1); font-size: 13px; }
.name { flex-grow: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pack { color: var(--mc-text-3); }
.price { width: 60px; text-align: right; font-weight: 600; }
.more { margin: 0; font-size: 12px; color: var(--mc-text-3); }
.actions { margin-top: auto; display: flex; gap: 8px; }
.actions button { flex: 1; min-height: 44px; font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 8px; }
.actions svg { width: 15px; height: 15px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
</style>
