<script setup lang="ts">
import { formatIngredient, formatNutrition, formatTag } from "~/lib/recipe-format";

const route = useRoute();
const slug = Array.isArray(route.params.slug) ? route.params.slug[0] : route.params.slug;
const { data: recipe, error, refresh, status } = await useRecipe(slug ?? "");

useHead(() => ({
  title: recipe.value ? `${recipe.value.title} · MealCraft` : "Recipe · MealCraft",
}));
</script>

<template>
  <main class="page-width recipe-detail-page">
    <NuxtLink class="back-link" to="/recipes"><span aria-hidden="true">←</span> All recipes</NuxtLink>

    <div v-if="status === 'pending'" class="notice-panel">Loading recipe…</div>
    <div v-else-if="error || !recipe" class="notice-panel error-notice">
      <p>This recipe could not be loaded.</p>
      <button type="button" @click="refresh()">Try again</button>
    </div>

    <template v-else>
      <section class="recipe-hero" aria-labelledby="recipe-title">
        <div class="recipe-hero-copy">
          <p class="eyebrow">{{ recipe.cuisine }} · {{ recipe.meal_type }}</p>
          <h1 id="recipe-title">{{ recipe.title }}</h1>
          <p>{{ recipe.description }}</p>
          <ul class="tag-list" aria-label="Dietary attributes">
            <li v-for="tag in recipe.dietary_tags" :key="tag">{{ formatTag(tag) }}</li>
          </ul>
        </div>

        <dl class="recipe-facts">
          <div>
            <dt>Total time</dt>
            <dd>{{ recipe.total_time_minutes }} minutes</dd>
          </div>
          <div>
            <dt>Servings</dt>
            <dd>{{ recipe.servings }}</dd>
          </div>
        </dl>
      </section>

      <section class="nutrition-strip" aria-labelledby="nutrition-title">
        <h2 id="nutrition-title">Nutrition per serving</h2>
        <dl>
          <div><dt>Energy</dt><dd>{{ formatNutrition(recipe.nutrition.calories_kcal, "kcal") }}</dd></div>
          <div><dt>Protein</dt><dd>{{ formatNutrition(recipe.nutrition.protein_g, "g") }}</dd></div>
          <div><dt>Carbohydrate</dt><dd>{{ formatNutrition(recipe.nutrition.carbohydrate_g, "g") }}</dd></div>
          <div><dt>Fat</dt><dd>{{ formatNutrition(recipe.nutrition.fat_g, "g") }}</dd></div>
          <div><dt>Sodium</dt><dd>{{ formatNutrition(recipe.nutrition.sodium_mg, "mg") }}</dd></div>
          <div><dt>Sugar</dt><dd>{{ formatNutrition(recipe.nutrition.sugar_g, "g") }}</dd></div>
        </dl>
      </section>

      <div class="recipe-content-grid">
        <section class="recipe-section" aria-labelledby="ingredients-title">
          <h2 id="ingredients-title">Ingredients</h2>
          <p class="section-note">Quantities are for {{ recipe.servings }} servings.</p>
          <ul class="ingredient-list">
            <li v-for="ingredient in recipe.ingredients" :key="ingredient.normalized_name">
              <div>
                <strong>{{ formatIngredient(ingredient) }}</strong>
                <span v-if="ingredient.preparation">{{ ingredient.preparation }}</span>
              </div>
              <span v-if="ingredient.allergen" class="allergen-label">Contains {{ ingredient.allergen }}</span>
            </li>
          </ul>
        </section>

        <section class="recipe-section" aria-labelledby="method-title">
          <h2 id="method-title">Method</h2>
          <ol class="method-list">
            <li v-for="step in recipe.steps" :key="step.step_number">
              <span aria-hidden="true">{{ step.step_number }}</span>
              <p>{{ step.instruction }}</p>
            </li>
          </ol>
        </section>
      </div>
    </template>
  </main>
</template>
