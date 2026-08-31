<script setup lang="ts">
import { formatNutrition, formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { formatQuantity, formatSgd } from "~/lib/product-format";
import {
  cleanAvailableIngredients,
  parseExcludedIngredients,
  toOptionalNumber,
} from "~/lib/recommendation-form";
import type { WeeklyMealPlanRequest } from "~/types/meal-plan";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  PricingMode,
} from "~/types/recommendation";

useHead({ title: "Weekly meal plan · MealCraft" });

const allergenOptions = ["soy", "gluten", "sesame"];
const dietaryOptions: { label: string; value: DietaryPreference }[] = [
  { label: "Vegetarian", value: "vegetarian" },
  { label: "Vegan", value: "vegan" },
  { label: "Gluten-free", value: "gluten-free" },
  { label: "Dairy-free", value: "dairy-free" },
];
const healthOptions: { label: string; value: HealthPreference }[] = [
  { label: "Lower sodium", value: "low-sodium" },
  { label: "Lower sugar", value: "low-sugar" },
  { label: "Lower calorie", value: "lower-calorie" },
];

const form = reactive({
  startDate: todayIsoDate(),
  householdSize: 2,
  maxCookingTimeMinutes: 60,
  budgetPerMealSgd: null as number | null,
  weeklyBudgetSgd: 60 as number | null,
  pricingMode: "fixture" as PricingMode,
  allergens: [] as string[],
  excludedIngredients: "",
  dietaryPreferences: [] as DietaryPreference[],
  healthPreferences: ["low-sodium"] as HealthPreference[],
  calorieTarget: 550 as number | null,
  proteinTarget: 35 as number | null,
});

const pantryItems = ref<AvailableIngredientInput[]>([
  { normalized_name: "brown_rice", quantity: 200, unit: "g" },
  { normalized_name: "lemon", quantity: null, unit: null },
]);
const { errorMessage, generate, isGenerating, result } = useWeeklyMealPlan();

function addPantryItem() {
  pantryItems.value.push({ normalized_name: "", quantity: null, unit: null });
}

function removePantryItem(index: number) {
  pantryItems.value.splice(index, 1);
}

async function submitPlan() {
  const payload: WeeklyMealPlanRequest = {
    start_date: form.startDate,
    day_count: 7,
    household_size: form.householdSize,
    max_cooking_time_minutes: form.maxCookingTimeMinutes,
    budget_per_meal_sgd: toOptionalNumber(form.budgetPerMealSgd),
    weekly_budget_sgd: toOptionalNumber(form.weeklyBudgetSgd),
    pricing_mode: form.pricingMode,
    allergens: form.allergens,
    excluded_ingredients: parseExcludedIngredients(form.excludedIngredients),
    dietary_preferences: form.dietaryPreferences,
    health_preferences: form.healthPreferences,
    nutrition_targets: {
      calories_kcal: toOptionalNumber(form.calorieTarget),
      protein_g: toOptionalNumber(form.proteinTarget),
      carbohydrate_g: null,
      fat_g: null,
    },
    max_sodium_mg_per_meal: null,
    available_ingredients: cleanAvailableIngredients(pantryItems.value),
  };
  await generate(payload);
  await nextTick();
  document.getElementById("weekly-results")?.scrollIntoView({ behavior: "smooth", block: "start" });
}
</script>

<template>
  <main class="page-width weekly-page">
    <section class="weekly-hero">
      <div>
        <p class="eyebrow">Seven-day deterministic planner</p>
        <h1>One week, planned as a complete system.</h1>
      </div>
      <p>
        MealCraft selects seven compatible main meals, avoids consecutive repetition where possible, aggregates nutrition and turns the full week into one package-aware shopping list.
      </p>
    </section>

    <form class="weekly-form" @submit.prevent="submitPlan">
      <div class="weekly-form-section">
        <h2>Schedule and budget</h2>
        <div class="weekly-fields four-columns">
          <label><span>Week starts</span><input v-model="form.startDate" type="date" required></label>
          <label><span>Household</span><input v-model.number="form.householdSize" type="number" min="1" max="12" required></label>
          <label><span>Time per meal</span><input v-model.number="form.maxCookingTimeMinutes" type="number" min="5" max="240" required></label>
          <label>
            <span>Pricing source</span>
            <select v-model="form.pricingMode">
              <option value="fixture">Fixture · reproducible</option>
              <option value="live">Live · FairPrice</option>
            </select>
          </label>
          <label><span>Per-meal budget</span><input v-model.number="form.budgetPerMealSgd" type="number" min="0.01" step="0.01" placeholder="Optional S$"></label>
          <label><span>Weekly budget</span><input v-model.number="form.weeklyBudgetSgd" type="number" min="0.01" step="0.01" placeholder="Optional S$"></label>
          <label><span>Calories per meal</span><input v-model.number="form.calorieTarget" type="number" min="100" max="2500" placeholder="kcal"></label>
          <label><span>Protein per meal</span><input v-model.number="form.proteinTarget" type="number" min="0" max="300" placeholder="g"></label>
        </div>
      </div>

      <div class="weekly-form-section">
        <h2>Restrictions and preferences</h2>
        <div class="weekly-choice-groups">
          <div>
            <p>Allergens</p>
            <label v-for="allergen in allergenOptions" :key="allergen" class="inline-choice">
              <input v-model="form.allergens" type="checkbox" :value="allergen"><span>{{ allergen }}</span>
            </label>
          </div>
          <div>
            <p>Dietary requirements</p>
            <label v-for="option in dietaryOptions" :key="option.value" class="inline-choice">
              <input v-model="form.dietaryPreferences" type="checkbox" :value="option.value"><span>{{ option.label }}</span>
            </label>
          </div>
          <div>
            <p>Health preferences</p>
            <label v-for="option in healthOptions" :key="option.value" class="inline-choice">
              <input v-model="form.healthPreferences" type="checkbox" :value="option.value"><span>{{ option.label }}</span>
            </label>
          </div>
        </div>
        <label class="wide-field">
          <span>Excluded ingredient IDs <small>comma-separated</small></span>
          <input v-model="form.excludedIngredients" type="text" placeholder="mushroom, yellow_onion">
        </label>
      </div>

      <div class="weekly-form-section">
        <div class="weekly-section-heading">
          <div><h2>Available ingredients</h2><p>Known quantities are deducted once from the weekly requirement. Unknown quantities only improve ranking.</p></div>
          <button class="secondary-button" type="button" @click="addPantryItem">+ Add ingredient</button>
        </div>
        <div class="weekly-pantry-list">
          <div v-for="(item, index) in pantryItems" :key="index" class="weekly-pantry-row">
            <input v-model="item.normalized_name" type="text" aria-label="Standard ingredient ID" placeholder="brown_rice">
            <input v-model.number="item.quantity" type="number" min="0.01" step="0.01" aria-label="Available quantity" placeholder="Unknown">
            <input v-model="item.unit" type="text" :required="item.quantity !== null" aria-label="Available unit" placeholder="g">
            <button type="button" class="remove-button" :aria-label="`Remove pantry item ${index + 1}`" @click="removePantryItem(index)">×</button>
          </div>
        </div>
      </div>

      <button class="primary-button weekly-submit" type="submit" :disabled="isGenerating">
        {{ isGenerating ? "Building the week…" : "Generate seven-day plan" }}
      </button>
    </form>

    <section id="weekly-results" class="weekly-results" aria-live="polite">
      <div v-if="errorMessage" class="notice-panel error-notice">{{ errorMessage }}</div>
      <div v-else-if="!result" class="weekly-empty">
        <p>Generate a plan to see the seven-day schedule, weekly nutrition and consolidated grocery list.</p>
      </div>
      <template v-else>
        <div class="weekly-result-heading">
          <div>
            <p class="eyebrow">Saved plan #{{ result.id }}</p>
            <h2>{{ formatPlanDate(result.start_date) }} — {{ formatPlanDate(result.end_date) }}</h2>
          </div>
          <div class="weekly-result-actions">
            <span>{{ result.household_size }} people · {{ result.day_count }} main meals</span>
            <NuxtLink class="secondary-button" :to="{ path: '/dashboard', query: { plan: result.id } }">Open nutrition dashboard</NuxtLink>
          </div>
        </div>

        <div v-for="warning in result.warnings" :key="warning" class="result-warning">{{ warning }}</div>

        <section class="weekly-summary-grid" aria-label="Weekly summary">
          <div><span>Ingredient-use value</span><strong>{{ formatSgd(result.grocery_estimate.consumed_total_sgd) }}</strong></div>
          <div><span>Package checkout</span><strong>{{ formatSgd(result.grocery_estimate.purchase_total_sgd) }}</strong></div>
          <div><span>Calories · per person</span><strong>{{ formatNutrition(result.nutrition_summary_per_person.calories_kcal, "kcal") }}</strong></div>
          <div><span>Protein · per person</span><strong>{{ formatNutrition(result.nutrition_summary_per_person.protein_g, "g") }}</strong></div>
        </section>

        <div class="weekly-day-grid">
          <article v-for="day in result.days" :key="day.day_index" class="weekly-day-card">
            <div class="weekly-day-date"><span>Day {{ day.day_index }}</span><strong>{{ formatPlanDate(day.planned_date) }}</strong></div>
            <p>{{ day.recipe.cuisine }} · {{ day.recipe.total_time_minutes }} min</p>
            <h3><NuxtLink :to="`/recipes/${day.recipe.slug}`">{{ day.recipe.title }}</NuxtLink></h3>
            <dl>
              <div><dt>Calories</dt><dd>{{ Math.round(day.nutrition_per_person.calories_kcal) }} kcal</dd></div>
              <div><dt>Protein</dt><dd>{{ Math.round(day.nutrition_per_person.protein_g) }} g</dd></div>
              <div><dt>Meal value</dt><dd>{{ formatSgd(day.consumed_cost_sgd) }}</dd></div>
            </dl>
          </article>
        </div>

        <section class="weekly-shopping">
          <div class="weekly-section-heading">
            <div>
              <p class="eyebrow">Consolidated shopping list</p>
              <h2>{{ result.grocery_estimate.items.length }} ingredients · package-aware</h2>
            </div>
            <span v-if="result.grocery_estimate.within_weekly_budget !== null" class="budget-status" :class="{ 'over-budget': !result.grocery_estimate.within_weekly_budget }">
              {{ result.grocery_estimate.within_weekly_budget ? "Within weekly budget" : "Over weekly budget" }}
            </span>
          </div>
          <div class="weekly-shopping-list">
            <div v-for="line in result.grocery_estimate.items" :key="line.ingredient_name" class="weekly-shopping-row">
              <div><strong>{{ line.ingredient_display_name }}</strong><span>Need {{ formatQuantity(line.required_quantity, line.unit) }}<template v-if="line.pantry_deduction > 0"> · pantry −{{ formatQuantity(line.pantry_deduction, line.unit) }}</template></span></div>
              <div v-if="line.product"><a :href="line.product.product_url" target="_blank" rel="noreferrer">{{ line.product.name }} ↗</a><span>{{ line.packages_required }} pack(s) · {{ formatSgd(line.purchase_cost_sgd) }}</span></div>
              <span v-else-if="line.remaining_quantity === 0" class="pantry-covered">Covered by pantry</span>
              <span v-else class="unmapped-product">No product mapping</span>
            </div>
          </div>
        </section>
      </template>
    </section>
  </main>
</template>
