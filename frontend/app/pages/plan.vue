<script setup lang="ts">
import {
  cleanAvailableIngredients,
  formatRecommendationScore,
  parseExcludedIngredients,
  toOptionalNumber,
} from "~/lib/recommendation-form";
import { formatQuantity, formatSgd } from "~/lib/product-format";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  PricingMode,
  RecipeRecommendationRequest,
} from "~/types/recommendation";

useHead({ title: "Plan a meal · MealCraft" });

const allergenOptions = ["soy", "gluten", "sesame"];
const dietaryOptions: { label: string; value: DietaryPreference }[] = [
  { label: "Vegetarian", value: "vegetarian" },
  { label: "Vegan", value: "vegan" },
  { label: "Gluten-free", value: "gluten-free" },
  { label: "Dairy-free", value: "dairy-free" },
];
const healthOptions: { label: string; value: HealthPreference; description: string }[] = [
  { label: "Lower sodium", value: "low-sodium", description: "Flexible 700 mg meal benchmark" },
  { label: "Lower sugar", value: "low-sugar", description: "Soft preference, not a medical limit" },
  { label: "Lower calorie", value: "lower-calorie", description: "Ranks lighter recipes higher" },
];

const form = reactive({
  householdSize: 2,
  maxCookingTimeMinutes: 45,
  budgetPerMealSgd: null as number | null,
  allergens: [] as string[],
  excludedIngredients: "",
  dietaryPreferences: [] as DietaryPreference[],
  healthPreferences: ["low-sodium"] as HealthPreference[],
  calorieTarget: 550 as number | null,
  proteinTarget: 35 as number | null,
  carbohydrateTarget: null as number | null,
  fatTarget: null as number | null,
  maxSodiumMg: null as number | null,
  pricingMode: "fixture" as PricingMode,
});

const pantryItems = ref<AvailableIngredientInput[]>([
  { normalized_name: "brown_rice", quantity: 200, unit: "g" },
  { normalized_name: "lemon", quantity: null, unit: null },
]);
const { errorMessage, isSubmitting, recommend, result } = useRecipeRecommendations();

function addPantryItem() {
  pantryItems.value.push({ normalized_name: "", quantity: null, unit: null });
}

function removePantryItem(index: number) {
  pantryItems.value.splice(index, 1);
}

function useSoyAllergyDemo() {
  form.allergens = ["soy"];
  form.healthPreferences = ["low-sodium"];
  form.maxCookingTimeMinutes = 45;
  form.calorieTarget = 550;
  form.proteinTarget = 35;
  pantryItems.value = [
    { normalized_name: "brown_rice", quantity: 200, unit: "g" },
    { normalized_name: "lemon", quantity: null, unit: null },
  ];
}

async function submitConstraints() {
  const payload: RecipeRecommendationRequest = {
    household_size: form.householdSize,
    max_cooking_time_minutes: form.maxCookingTimeMinutes,
    budget_per_meal_sgd: toOptionalNumber(form.budgetPerMealSgd),
    allergens: form.allergens,
    excluded_ingredients: parseExcludedIngredients(form.excludedIngredients),
    dietary_preferences: form.dietaryPreferences,
    health_preferences: form.healthPreferences,
    nutrition_targets: {
      calories_kcal: toOptionalNumber(form.calorieTarget),
      protein_g: toOptionalNumber(form.proteinTarget),
      carbohydrate_g: toOptionalNumber(form.carbohydrateTarget),
      fat_g: toOptionalNumber(form.fatTarget),
    },
    max_sodium_mg_per_meal: toOptionalNumber(form.maxSodiumMg),
    available_ingredients: cleanAvailableIngredients(pantryItems.value),
    pricing_mode: form.pricingMode,
  };

  await recommend(payload);
  await nextTick();
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.getElementById("results-title")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}
</script>

<template>
  <main class="page-width plan-page">
    <section class="plan-intro" aria-labelledby="plan-title">
      <p class="eyebrow">Constraint-aware matching</p>
      <h1 id="plan-title">Find recipes that fit real constraints.</h1>
      <p>
        Hard restrictions remove unsafe or incompatible recipes. Nutrition, time and available ingredients produce a transparent ranking.
      </p>
    </section>

    <div class="planner-grid">
      <form class="constraint-form" @submit.prevent="submitConstraints">
        <div class="form-toolbar">
          <div>
            <p class="form-kicker">Planning request</p>
            <h2>Your constraints</h2>
          </div>
          <button class="secondary-button" type="button" @click="useSoyAllergyDemo">Load demo</button>
        </div>

        <fieldset>
          <legend>Household and time</legend>
          <div class="form-row two-columns">
            <label>
              <span>Household size</span>
              <input v-model.number="form.householdSize" type="number" min="1" max="12" required>
            </label>
            <label>
              <span>Maximum cooking time</span>
              <div class="input-with-suffix">
                <input v-model.number="form.maxCookingTimeMinutes" type="number" min="5" max="240" required>
                <span>min</span>
              </div>
            </label>
          </div>
          <label>
            <span>Budget per meal <small>enforced using estimated ingredient-use cost</small></span>
            <div class="input-with-prefix">
              <span>S$</span>
              <input v-model.number="form.budgetPerMealSgd" type="number" min="0.01" step="0.01" placeholder="Optional">
            </div>
          </label>
          <label>
            <span>Product pricing <small>fixture is reproducible; live queries FairPrice and may be slower</small></span>
            <select v-model="form.pricingMode">
              <option value="fixture">Fixture · reproducible</option>
              <option value="live">Live · FairPrice with visible fallback</option>
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>Hard restrictions</legend>
          <p class="field-help">Matching recipes are removed when they contain a selected allergen.</p>
          <div class="choice-grid">
            <label v-for="allergen in allergenOptions" :key="allergen" class="choice-card">
              <input v-model="form.allergens" type="checkbox" :value="allergen">
              <span>{{ allergen }}</span>
            </label>
          </div>

          <p class="field-label">Dietary requirements</p>
          <div class="choice-grid">
            <label v-for="option in dietaryOptions" :key="option.value" class="choice-card">
              <input v-model="form.dietaryPreferences" type="checkbox" :value="option.value">
              <span>{{ option.label }}</span>
            </label>
          </div>

          <label>
            <span>Excluded ingredient IDs <small>comma-separated</small></span>
            <input v-model="form.excludedIngredients" type="text" placeholder="mushroom, yellow_onion">
          </label>
          <label>
            <span>Explicit sodium ceiling <small>hard limit only when entered</small></span>
            <div class="input-with-suffix">
              <input v-model.number="form.maxSodiumMg" type="number" min="100" max="5000" placeholder="Optional">
              <span>mg</span>
            </div>
          </label>
        </fieldset>

        <fieldset>
          <legend>Health preferences</legend>
          <div class="health-choice-list">
            <label v-for="option in healthOptions" :key="option.value">
              <input v-model="form.healthPreferences" type="checkbox" :value="option.value">
              <span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span>
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Nutrition targets per meal</legend>
          <p class="field-help">Only user-entered targets are scored. The system does not calculate BMR or TDEE.</p>
          <div class="nutrition-input-grid">
            <label><span>Calories</span><input v-model.number="form.calorieTarget" type="number" min="100" max="2500" placeholder="kcal"></label>
            <label><span>Protein</span><input v-model.number="form.proteinTarget" type="number" min="0" max="300" placeholder="g"></label>
            <label><span>Carbohydrate</span><input v-model.number="form.carbohydrateTarget" type="number" min="0" max="500" placeholder="g"></label>
            <label><span>Fat</span><input v-model.number="form.fatTarget" type="number" min="0" max="200" placeholder="g"></label>
          </div>
        </fieldset>

        <fieldset>
          <legend>Available ingredients</legend>
          <p class="field-help">Known quantities affect coverage. Unknown quantities only improve recipe ranking.</p>
          <div class="pantry-list">
            <div v-for="(item, index) in pantryItems" :key="index" class="pantry-row">
              <label>
                <span>Standard ingredient ID</span>
                <input v-model="item.normalized_name" type="text" placeholder="brown_rice">
              </label>
              <label>
                <span>Quantity</span>
                <input v-model.number="item.quantity" type="number" min="0.01" step="0.01" placeholder="Unknown">
              </label>
              <label>
                <span>Unit</span>
                <input v-model="item.unit" type="text" :required="item.quantity !== null" placeholder="g">
              </label>
              <button class="remove-button" type="button" :aria-label="`Remove pantry item ${index + 1}`" @click="removePantryItem(index)">×</button>
            </div>
          </div>
          <button class="secondary-button add-button" type="button" @click="addPantryItem">+ Add ingredient</button>
        </fieldset>

        <button class="primary-button" type="submit" :disabled="isSubmitting">
          {{ isSubmitting ? "Evaluating constraints…" : "Find matching recipes" }}
        </button>
      </form>

      <section class="recommendation-results" aria-live="polite" aria-labelledby="results-title">
        <div class="results-heading">
          <p class="form-kicker">Deterministic output</p>
          <h2 id="results-title">Recommendation results</h2>
        </div>

        <div v-if="errorMessage" class="result-empty error-notice">{{ errorMessage }}</div>
        <div v-else-if="!result" class="result-empty">
          <p>Submit the constraints to see ranked recipes and explicit exclusion reasons.</p>
          <ol>
            <li>Allergens and hard limits filter recipes.</li>
            <li>Nutrition, pantry coverage and time create the score.</li>
            <li>Every result explains why it was retained or removed.</li>
          </ol>
        </div>

        <template v-else>
          <div class="result-summary">
            <strong>{{ result.recommendations.length }} matches</strong>
            <span>{{ result.excluded.length }} excluded</span>
          </div>

          <div v-for="warning in result.warnings" :key="warning" class="result-warning">{{ warning }}</div>

          <div class="recommendation-list">
            <article v-for="(item, index) in result.recommendations" :key="item.recipe.id" class="recommendation-card">
              <div class="recommendation-rank">#{{ index + 1 }}</div>
              <div class="recommendation-card-body">
                <div class="recommendation-title-row">
                  <div>
                    <p>{{ item.recipe.cuisine }} · {{ item.recipe.total_time_minutes }} min</p>
                    <h3><NuxtLink :to="`/recipes/${item.recipe.slug}`">{{ item.recipe.title }}</NuxtLink></h3>
                  </div>
                  <div class="total-score"><strong>{{ formatRecommendationScore(item.total_score) }}</strong><span>match</span></div>
                </div>

                <dl class="score-breakdown">
                  <div><dt>Nutrition</dt><dd>{{ item.score_breakdown.nutrition ?? "—" }}</dd></div>
                  <div><dt>Pantry</dt><dd>{{ item.score_breakdown.pantry ?? "—" }}</dd></div>
                  <div><dt>Time</dt><dd>{{ item.score_breakdown.time }}</dd></div>
                </dl>

                <section v-if="item.grocery_estimate" class="grocery-estimate">
                  <div class="grocery-total-row">
                    <div>
                      <span>Ingredient-use cost</span>
                      <strong>{{ formatSgd(item.grocery_estimate.consumed_total_sgd) }}</strong>
                    </div>
                    <div>
                      <span>Checkout total</span>
                      <strong>{{ formatSgd(item.grocery_estimate.purchase_total_sgd) }}</strong>
                    </div>
                    <span
                      v-if="item.grocery_estimate.within_budget !== null"
                      class="budget-status"
                      :class="{ 'over-budget': !item.grocery_estimate.within_budget }"
                    >
                      {{ item.grocery_estimate.within_budget ? "Within budget" : "Over budget" }}
                    </span>
                  </div>

                  <details class="grocery-details">
                    <summary>Shopping estimate · {{ item.grocery_estimate.items.length }} ingredients</summary>
                    <div v-for="line in item.grocery_estimate.items" :key="line.ingredient_name" class="grocery-line">
                      <div>
                        <strong>{{ line.ingredient_display_name }}</strong>
                        <span>
                          Need {{ formatQuantity(line.remaining_quantity, line.unit) }}
                          <template v-if="line.pantry_deduction > 0"> · pantry −{{ formatQuantity(line.pantry_deduction, line.unit) }}</template>
                        </span>
                      </div>
                      <div v-if="line.product" class="grocery-product">
                        <a :href="line.product.product_url" target="_blank" rel="noreferrer">{{ line.product.name }} ↗</a>
                        <span>{{ line.packages_required }} pack(s) · {{ formatSgd(line.purchase_cost_sgd) }}</span>
                      </div>
                      <span v-else-if="line.remaining_quantity === 0" class="pantry-covered">Covered by known pantry quantity</span>
                      <span v-else class="unmapped-product">No product mapping</span>
                    </div>
                  </details>
                </section>

                <ul class="reason-list">
                  <li v-for="reason in item.reasons" :key="reason">{{ reason }}</li>
                </ul>
              </div>
            </article>
          </div>

          <details v-if="result.excluded.length" class="excluded-panel">
            <summary>Why {{ result.excluded.length }} recipes were excluded</summary>
            <div v-for="item in result.excluded" :key="item.id" class="excluded-item">
              <strong>{{ item.title }}</strong>
              <ul><li v-for="reason in item.reasons" :key="reason">{{ reason }}</li></ul>
            </div>
          </details>
        </template>
      </section>
    </div>
  </main>
</template>
