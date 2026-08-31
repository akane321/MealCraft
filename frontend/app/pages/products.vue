<script setup lang="ts">
import { formatQuantity, formatSgd } from "~/lib/product-format";
import type { PricingMode } from "~/types/recommendation";

useHead({ title: "FairPrice products · MealCraft" });

const query = ref("tomato");
const mode = ref<PricingMode>("fixture");
const forceRefresh = ref(false);
const { errorMessage, isSearching, result, search } = useProductSearch();

async function submitSearch() {
  const normalizedQuery = query.value.trim();
  if (!normalizedQuery) return;
  await search(normalizedQuery, mode.value, forceRefresh.value);
}

onMounted(() => {
  void submitSearch();
});
</script>

<template>
  <main class="page-width products-page">
    <section class="catalog-intro">
      <p class="eyebrow">FairPrice product adapter</p>
      <h1>Turn recipe ingredients into purchasable products.</h1>
      <p class="catalog-summary">
        Use deterministic fixtures during development, or query the current FairPrice catalogue. Live failures fall back visibly instead of breaking planning.
      </p>
    </section>

    <form class="product-search-form" @submit.prevent="submitSearch">
      <label class="product-query">
        <span>Ingredient or product</span>
        <input v-model="query" type="search" placeholder="tomato" required>
      </label>
      <label>
        <span>Pricing source</span>
        <select v-model="mode">
          <option value="fixture">Fixture · reproducible</option>
          <option value="live">Live · FairPrice</option>
        </select>
      </label>
      <label class="refresh-choice">
        <input v-model="forceRefresh" type="checkbox" :disabled="mode !== 'live'">
        <span>Ignore cache</span>
      </label>
      <button class="primary-button product-search-button" type="submit" :disabled="isSearching">
        {{ isSearching ? "Searching…" : "Search products" }}
      </button>
    </form>

    <div v-if="errorMessage" class="notice-panel error-notice">{{ errorMessage }}</div>
    <section v-else-if="result" aria-live="polite">
      <div class="product-result-meta">
        <strong>{{ result.items.length }} products</strong>
        <span>Source: {{ result.provider_used }} · {{ result.cached ? "cache" : "fresh response" }}</span>
      </div>
      <div v-if="result.warning" class="result-warning">{{ result.warning }}</div>
      <div class="product-grid">
        <article v-for="product in result.items" :key="`${product.source}-${product.external_id}`" class="product-card">
          <div class="product-card-copy">
            <p>{{ product.brand || "FairPrice catalogue" }}</p>
            <h2>{{ product.name }}</h2>
            <span>{{ formatQuantity(product.package_size, product.package_unit) }}</span>
          </div>
          <div class="product-card-footer">
            <strong>{{ formatSgd(product.price_sgd) }}</strong>
            <a :href="product.product_url" target="_blank" rel="noreferrer">View product ↗</a>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>
