<script setup lang="ts">
import { nutritionMetrics } from "~/lib/dashboard";
import { MEAL_LABEL, mealsByDay } from "~/lib/home-surface";
import { formatPlanDate, planDayName, todayIsoDate } from "~/lib/meal-plan-format";
import { nutritionForDishes } from "~/lib/nutrition-summary";
import type { WeeklyNutritionDashboard } from "~/types/meal-plan";

const props = defineProps<{ dashboard: WeeklyNutritionDashboard; sodiumLimit: number | null }>();
const emit = defineEmits<{ details: [] }>();

const week = computed(() => mealsByDay(props.dashboard.days));
// Past seven days a weekday repeats, so the picker and the heading name the date too.
const numbered = computed(() => week.value.length > 7);
const selectedDay = ref<number | null>(null);
const selectedMeal = ref("all");
const day = computed(() => week.value.find(item => item.dayIndex === selectedDay.value)
  ?? week.value.find(item => item.date === todayIsoDate()) ?? week.value[0]);
const meal = computed(() => day.value?.meals.find(item => item.mealType === selectedMeal.value));
const dishes = computed(() => meal.value?.dishes ?? day.value?.meals.flatMap(item => item.dishes) ?? []);
const totals = computed(() => nutritionForDishes(dishes.value));
const cooked = computed(() => props.dashboard.status_counts.completed);
const notCounted = computed(() => dishes.value.filter(dish => dish.status === "skipped").length);
const dayKcal = (dayIndex: number) => Math.round(nutritionForDishes(week.value.find(item => item.dayIndex === dayIndex)!.meals.flatMap(item => item.dishes)).currentPlan.calories_kcal);
const kcal = (value: number) => Math.round(value).toLocaleString("en-SG");
// Each macro's bar is its share of the energy (protein and carbohydrate 4 kcal a gram, fat 9).
const macros = computed(() => {
  const plan = totals.value.currentPlan;
  const energy = plan.protein_g * 4 + plan.carbohydrate_g * 4 + plan.fat_g * 9 || 1;
  return [
    { name: "Protein", grams: plan.protein_g, share: plan.protein_g * 4 / energy, color: "#8b5cf6" },
    { name: "Carbs", grams: plan.carbohydrate_g, share: plan.carbohydrate_g * 4 / energy, color: "#38b2f0" },
    { name: "Fat", grams: plan.fat_g, share: plan.fat_g * 9 / energy, color: "#12b76a" },
  ];
});
const scopeLabel = computed(() => {
  if (!day.value) return "";
  const when = planDayName(day.value.date, "long", numbered.value);
  const only = meal.value ?? (day.value.meals.length === 1 ? day.value.meals[0] : undefined);
  return only ? `${when} ${MEAL_LABEL[only.mealType].toLowerCase()}` : `${when}, all meals`;
});
watch(day, value => {
  if (!value?.meals.some(item => item.mealType === selectedMeal.value)) selectedMeal.value = "all";
});

function chooseDay(value: number) {
  selectedDay.value = value;
  selectedMeal.value = "all";
}
</script>


<template>
  <section class="nutri" aria-label="Nutrition per day and meal">
    <template v-if="day">
      <div class="days" role="group" aria-label="Nutrition day">
        <button
          v-for="item in week"
          :key="item.dayIndex"
          type="button"
          :aria-pressed="item.dayIndex === day.dayIndex"
          :aria-label="`${formatPlanDate(item.date, { weekday: 'long', day: 'numeric', month: 'short' })}, ${kcal(dayKcal(item.dayIndex))} kcal`"
          @click="chooseDay(item.dayIndex)"
        >
          {{ planDayName(item.date, "short", numbered) }}<span class="mc-num">{{ kcal(dayKcal(item.dayIndex)) }}</span>
        </button>
      </div>
      <div class="body">
        <!-- The meal pick has its own line, so the total's label keeps its width. -->
        <label v-if="day.meals.length > 1" class="meal-pick">
          <span class="visually-hidden">Meal</span>
          <select v-model="selectedMeal" aria-label="Nutrition meal">
            <option value="all">All meals</option>
            <option v-for="item in day.meals" :key="item.key" :value="item.mealType">{{ MEAL_LABEL[item.mealType] }}</option>
          </select>
        </label>
        <div class="big">
          <span class="mc-display mc-num">{{ kcal(totals.currentPlan.calories_kcal) }}</span>
          <span class="what">kcal a person · {{ scopeLabel }}</span>
        </div>
        <p class="mc-small actual">{{ kcal(totals.actual.calories_kcal) }} kcal eaten so far: actual counts cooked dishes only.<template v-if="notCounted">{{ ` ${notCounted} skipped ${notCounted === 1 ? "dish" : "dishes"} not counted.` }}</template></p>
        <div class="macros">
          <div v-for="item in macros" :key="item.name" class="macro">
            <span class="name">{{ item.name }}</span>
            <div class="bar" role="img" :aria-label="`${item.name}: ${Math.round(item.share * 100)} percent of the energy`"><i :style="{ width: `${Math.round(item.share * 100)}%`, background: item.color }" /></div>
            <span class="g mc-num">{{ Math.round(item.grams) }} g</span>
          </div>
        </div>
        <table class="six">
          <caption class="visually-hidden">Nutrition per person for the selected day and meal</caption>
          <thead><tr><th scope="col">Nutrient</th><th scope="col">Actual</th><th scope="col">Current plan</th></tr></thead>
          <tbody>
            <tr v-for="item in nutritionMetrics" :key="item.key">
              <th scope="row">{{ item.label }}</th>
              <td class="mc-num">{{ kcal(totals.actual[item.key]) }} {{ item.unit }}</td>
              <td class="mc-num">{{ kcal(totals.currentPlan[item.key]) }} {{ item.unit }}</td>
            </tr>
          </tbody>
        </table>
        <button type="button" class="mc-btn secondary sm details" @click="emit('details')">All six nutrients &amp; daily detail</button>
        <div class="dishes mc-card">
          <span class="dishes-head">{{ scopeLabel }}, per person</span>
          <div v-for="dish in dishes" :key="dish.entry_id" class="dish" :class="{ skipped: dish.status === 'skipped' }">
            <HomeDishIcon :slug="dish.recipe.slug" :title="dish.recipe.title" :size="32" />
            <span class="dish-name">
              <b>{{ dish.recipe.title }}</b>
              <small>{{ Math.round(dish.nutrition_per_person.protein_g) }} g protein · {{ Math.round(dish.nutrition_per_person.fat_g) }} g fat{{ dish.status === "skipped" ? " · skipped" : dish.status === "completed" ? " · cooked" : "" }}</small>
            </span>
            <span class="kcal mc-num">{{ kcal(dish.nutrition_per_person.calories_kcal) }}</span>
          </div>
        </div>
        <p class="mc-small">
          <strong>Eaten so far</strong>: {{ cooked }} {{ cooked === 1 ? "dish" : "dishes" }},
          {{ kcal(dashboard.completed_nutrition_per_person.calories_kcal) }} kcal and
          {{ Math.round(dashboard.completed_nutrition_per_person.protein_g) }} g protein per person.
        </p>
      </div>
    </template>
    <div v-else class="body">
      <p class="mc-small">No meals to show.</p>
      <button type="button" class="mc-btn secondary sm details" @click="emit('details')">All six nutrients &amp; daily detail</button>
    </div>
  </section>
</template>

<style scoped>
/* The day picker is a light track; the chosen day is a raised white segment. */
.days { width: fit-content; max-width: calc(100% - 32px); display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 96px); gap: 2px; margin: 14px 16px 6px; padding: 3px; border-radius: 10px; background: #f4f4f5; }
.days button { min-width: 0; height: 40px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 0; border-radius: 8px; background: transparent; color: #52525b !important; font-size: 13px; line-height: 16px; font-weight: 500; }
.days button:hover { color: #18181b !important; }
.days button span { color: #71717a; font-size: 12px; font-weight: 400; }
.days button[aria-pressed="true"] { background: #fff; color: #0f0f12 !important; box-shadow: var(--mc-shadow-xs); }
.body { display: flex; flex-direction: column; gap: 14px; padding: 10px 16px 16px; }
.big { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.what { min-width: 0; font-size: 13px; color: var(--c-neutral-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meal-pick { align-self: flex-start; margin-bottom: -6px; }
.meal-pick select { appearance: none; height: 32px; padding: 0 30px 0 12px; border: 1px solid #e4e4e7; border-radius: 10px; background: #fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2371717a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 10px center / 14px; color: #18181b; font: inherit; font-size: 13px; font-weight: 500; box-shadow: var(--mc-shadow-xs); cursor: pointer; }
.meal-pick select:focus-visible { outline: 0; border-color: #8b5cf6; box-shadow: 0 0 0 3px #ede9fe; }
.actual { margin: -10px 0 0; }
.macros { display: flex; flex-direction: column; gap: 10px; }
.macro { display: grid; grid-template-columns: 76px minmax(0, 1fr) 56px; align-items: center; gap: 10px; }
.name { color: #52525b; font-size: 13px; font-weight: 500; }
.bar { height: 6px; border-radius: 999px; background: #f0f0f2; overflow: hidden; }
.bar i { display: block; height: 100%; border-radius: 999px; }
.g { color: #18181b; text-align: right; font-weight: 500; }
.six { width: 100%; border-collapse: collapse; font-size: 13px; line-height: 18px; font-variant-numeric: tabular-nums; }
.six th, .six td { padding: 5px 0; text-align: right; border-bottom: 1px solid #f2f2f4; }
.six tbody tr:last-child :is(th, td) { border-bottom: 0; }
.six th:first-child { text-align: left; }
.six thead th { border-bottom-color: #ececef; color: #71717a; font-size: 12px; font-weight: 500; }
.six tbody th { color: #52525b; font-weight: 400; }
.six td { color: #27272a; font-weight: 500; }
.dishes { overflow: hidden; }
.dishes-head { height: 36px; display: flex; align-items: center; padding: 0 14px; background: #fafafa; border-bottom: 1px solid #ececef; color: #71717a; font-size: 12px; font-weight: 500; }
.dish { display: grid; grid-template-columns: 32px minmax(0, 1fr) auto; align-items: center; gap: 10px; min-height: 52px; padding: 6px 14px; border-bottom: 1px solid #f2f2f4; }
.dish:last-child { border-bottom: 0; }
.dish.skipped { opacity: 0.55; }
.dish-name { display: flex; flex-direction: column; min-width: 0; }
.dish-name b { color: #18181b; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-name small { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.kcal { color: #18181b; font-weight: 500; }
.details { align-self: flex-start; }
.body > p { margin: 0; }
.body strong { color: #18181b; font-weight: 500; }
</style>
