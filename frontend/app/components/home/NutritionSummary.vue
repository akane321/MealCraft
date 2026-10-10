<script setup lang="ts">
import { nutritionMetrics } from "~/lib/dashboard";
import { MEAL_LABEL, mealsByDay } from "~/lib/home-surface";
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { nutritionForDishes } from "~/lib/nutrition-summary";
import type { WeeklyNutritionDashboard } from "~/types/meal-plan";

const props = defineProps<{ dashboard: WeeklyNutritionDashboard; sodiumLimit: number | null }>();
const emit = defineEmits<{ details: [] }>();

const week = computed(() => mealsByDay(props.dashboard.days));
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
    { name: "Protein", grams: plan.protein_g, share: plan.protein_g * 4 / energy, color: "var(--c-blue)" },
    { name: "Carbs", grams: plan.carbohydrate_g, share: plan.carbohydrate_g * 4 / energy, color: "var(--c-amber)" },
    { name: "Fat", grams: plan.fat_g, share: plan.fat_g * 9 / energy, color: "var(--c-coral)" },
  ];
});
const scopeLabel = computed(() => {
  if (!day.value) return "";
  const when = formatPlanDate(day.value.date, { weekday: "long" });
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
          {{ formatPlanDate(item.date, { weekday: "short" }) }}<span class="mc-num">{{ kcal(dayKcal(item.dayIndex)) }}</span>
        </button>
      </div>
      <div class="body">
        <div class="big">
          <span class="mc-display mc-num">{{ kcal(totals.currentPlan.calories_kcal) }}</span>
          <span class="what">kcal a person · {{ scopeLabel }}</span>
          <label v-if="day.meals.length > 1" class="meal-pick">
            <span class="visually-hidden">Meal</span>
            <select v-model="selectedMeal" aria-label="Nutrition meal">
              <option value="all">All meals</option>
              <option v-for="item in day.meals" :key="item.key" :value="item.mealType">{{ MEAL_LABEL[item.mealType] }}</option>
            </select>
          </label>
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
            <HomeDishIcon :title="dish.recipe.title" :course="dish.recipe.course" :role-id="dish.role_id" :size="32" />
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
          {{ Math.round(dashboard.completed_nutrition_per_person.protein_g) }} g protein per person. General guidance, not medical advice.
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
.days { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px; padding: 14px 16px 6px; }
.days button { height: 48px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 0; border-radius: 10px; background: var(--c-rail); color: var(--c-ink) !important; font-size: 12px; line-height: 16px; font-weight: 800; }
.days button span { font-weight: 700; color: var(--c-muted); }
.days button[aria-pressed="true"] { background: var(--c-ink); color: #fff !important; }
.days button[aria-pressed="true"] span { color: #c9c7da; }
.body { display: flex; flex-direction: column; gap: 14px; padding: 10px 16px 16px; }
.big { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.what { min-width: 0; font-size: 13px; color: var(--c-neutral-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.meal-pick { margin-left: auto; align-self: center; }
.meal-pick select { height: 30px; padding: 0 8px; border: 1px solid var(--c-border); border-radius: 10px; background: #fff; color: var(--c-ink); font: inherit; font-size: 12px; font-weight: 800; }
.actual { margin: -10px 0 0; }
.macros { display: flex; flex-direction: column; gap: 10px; }
.macro { display: grid; grid-template-columns: 76px minmax(0, 1fr) 56px; align-items: center; gap: 10px; }
.name { font-size: 13px; font-weight: 800; }
.bar { height: 10px; border-radius: 999px; background: var(--c-line-soft); overflow: hidden; }
.bar i { display: block; height: 100%; border-radius: 999px; }
.g { text-align: right; font-weight: 800; }
.six { width: 100%; border-collapse: collapse; font-size: 12px; line-height: 16px; }
.six th, .six td { padding: 5px 0; text-align: right; border-bottom: 1px solid var(--c-line-soft); }
.six th:first-child { text-align: left; }
.six thead th { color: var(--c-muted); font-weight: 800; }
.six tbody th { font-weight: 700; }
.six td { font-weight: 800; }
.dishes-head { height: 36px; display: flex; align-items: center; padding: 0 14px; background: var(--c-canvas); border-bottom: 1px solid var(--c-line-soft); font-size: 12px; font-weight: 800; color: var(--c-muted); }
.dish { display: grid; grid-template-columns: 32px minmax(0, 1fr) auto; align-items: center; gap: 10px; min-height: 52px; padding: 6px 14px; border-bottom: 1px solid var(--c-line-soft); }
.dish:last-child { border-bottom: 0; }
.dish.skipped { opacity: 0.55; }
.dish-name { display: flex; flex-direction: column; min-width: 0; }
.dish-name b { font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-name small { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.kcal { font-weight: 800; }
.details { align-self: flex-start; }
.body > p { margin: 0; }
.body strong { color: var(--c-ink); font-weight: 800; }
</style>
