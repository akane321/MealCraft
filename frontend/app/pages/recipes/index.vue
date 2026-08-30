<script setup lang="ts">
import { formatNutrition, formatTag } from "~/lib/recipe-format";

useHead({ title: "Recipes · Dietary Planner MVP" });

const { data, error, refresh, status } = await useRecipes();
</script>

<template>
  <main class="page-width catalog-page">
    <section class="catalog-intro" aria-labelledby="catalog-title">
      <p class="eyebrow">Recipe catalog</p>
      <h1 id="catalog-title">Practical meals, structured for planning.</h1>
      <p class="catalog-summary">
        Each recipe carries normalized ingredients, preparation time and per-serving nutrition data for the planning engine.
      </p>
    </section>

    <div v-if="status === 'pending'" class="notice-panel">Loading recipe catalog…</div>
    <div v-else-if="error" class="notice-panel error-notice">
      <p>The recipe catalog could not be loaded.</p>
      <button type="button" @click="refresh()">Try again</button>
    </div>

    <section v-else class="recipe-grid" aria-label="Recipe catalog">
      <article v-for="recipe in data?.items" :key="recipe.id" class="recipe-card">
        <div class="recipe-card-topline">
          <span>{{ recipe.cuisine }}</span>
          <span>{{ recipe.total_time_minutes }} min</span>
        </div>
        <div>
          <h2>
            <NuxtLink :to="`/recipes/${recipe.slug}`">{{ recipe.title }}</NuxtLink>
          </h2>
          <p>{{ recipe.description }}</p>
        </div>
        <ul class="tag-list" aria-label="Dietary attributes">
          <li v-for="tag in recipe.dietary_tags" :key="tag">{{ formatTag(tag) }}</li>
        </ul>
        <dl class="recipe-card-metrics">
          <div>
            <dt>Energy</dt>
            <dd>{{ formatNutrition(recipe.nutrition.calories_kcal, "kcal") }}</dd>
          </div>
          <div>
            <dt>Protein</dt>
            <dd>{{ formatNutrition(recipe.nutrition.protein_g, "g") }}</dd>
          </div>
          <div>
            <dt>Sodium</dt>
            <dd>{{ formatNutrition(recipe.nutrition.sodium_mg, "mg") }}</dd>
          </div>
        </dl>
        <NuxtLink class="text-link" :to="`/recipes/${recipe.slug}`">
          View recipe <span aria-hidden="true">→</span>
        </NuxtLink>
      </article>
    </section>
  </main>
</template>
