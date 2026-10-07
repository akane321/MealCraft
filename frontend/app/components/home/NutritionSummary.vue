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
watch(day, value => {
  if (!value?.meals.some(item => item.mealType === selectedMeal.value)) selectedMeal.value = "all";
});

function chooseDay(value: string) {
  selectedDay.value = Number(value);
  selectedMeal.value = "all";
}
</script>

<template>
  <section class="nutri" aria-label="Nutrition per day and meal">
    <p class="eaten">
      <strong>Eaten so far</strong>: {{ cooked }} {{ cooked === 1 ? "dish" : "dishes" }},
      {{ Math.round(dashboard.completed_nutrition_per_person.calories_kcal).toLocaleString("en-SG") }} kcal and
      {{ Math.round(dashboard.completed_nutrition_per_person.protein_g) }} g protein per person.
    </p>
    <template v-if="day">
      <div class="selectors">
        <label>
          <span>Day</span>
          <select aria-label="Nutrition day" :value="day.dayIndex" @change="chooseDay(($event.target as HTMLSelectElement).value)">
            <option v-for="item in week" :key="item.dayIndex" :value="item.dayIndex">{{ formatPlanDate(item.date) }}</option>
          </select>
        </label>
        <label v-if="day.meals.length > 1">
          <span>Meal</span>
          <select v-model="selectedMeal" aria-label="Nutrition meal">
            <option value="all">All meals</option>
            <option v-for="item in day.meals" :key="item.key" :value="item.mealType">{{ MEAL_LABEL[item.mealType] }}</option>
          </select>
        </label>
      </div>
      <p class="scope">{{ meal ? MEAL_LABEL[meal.mealType] : day.meals.length === 1 ? `${MEAL_LABEL[day.meals[0]!.mealType]} · daily total` : "Daily total" }} · per person</p>
      <table>
        <caption class="visually-hidden">Nutrition per person for the selected day and meal</caption>
        <thead><tr><th scope="col">Nutrient</th><th scope="col">Actual</th><th scope="col">Current plan</th></tr></thead>
        <tbody>
          <tr v-for="item in nutritionMetrics" :key="item.key">
            <th scope="row">{{ item.label }}</th>
            <td class="mc-num">{{ Math.round(totals.actual[item.key]).toLocaleString("en-SG") }} {{ item.unit }}</td>
            <td class="mc-num">{{ Math.round(totals.currentPlan[item.key]).toLocaleString("en-SG") }} {{ item.unit }}</td>
          </tr>
        </tbody>
      </table>
      <p class="lead">Actual counts cooked dishes only. Current plan includes them.<template v-if="notCounted">{{ ` ${notCounted} skipped ${notCounted === 1 ? "dish" : "dishes"} not counted.` }}</template></p>
    </template>
    <p v-else class="lead">No meals to show.</p>
    <button type="button" class="mc-pill" @click="emit('details')">All six nutrients &amp; daily detail</button>
    <p class="lead">General guidance, not medical advice.</p>
  </section>
</template>

<style scoped>
.nutri { padding: 16px 22px; display: grid; gap: 10px; }
.eaten, .lead, .scope { margin: 0; font-size: 12px; line-height: 1.5; color: var(--t3); }
.eaten strong { color: var(--ivory); font-weight: 500; }
.selectors { display: flex; gap: 12px; }
.selectors label { min-width: 0; display: grid; gap: 4px; font-size: 11px; color: var(--t3); }
.selectors select { min-height: 34px; max-width: 100%; padding: 0 8px; color: var(--ivory); background: var(--s2); border: 1px solid var(--line); border-radius: 6px; font: inherit; font-size: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 7px 0; text-align: right; border-bottom: 1px solid var(--line); }
th:first-child { text-align: left; }
th { color: var(--t3); font-weight: 400; }
thead th { font-size: 11px; }
.nutri > button { justify-self: start; min-height: 34px; font-size: 12px; }
</style>
