<script setup lang="ts">
import { formatSgd, plateStyle } from "~/lib/home-surface";
import type { ProductSearchResponse } from "~/types/recommendation";
import type { RecipeCollection, RecipeListItem } from "~/types/recipe";

useHead({ title: "Recipes and groceries · MealCraft" });

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const route = useRoute();

const tab = ref<"recipes" | "products">(route.query.tab === "products" ? "products" : "recipes");

// Recipes: every word of the search in the title, optionally one course.
const COURSES = [
  { id: null, label: "All" },
  { id: "main", label: "Mains" },
  { id: "side", label: "Sides" },
  { id: "salad", label: "Salads" },
  { id: "soup", label: "Soups" },
  { id: "breakfast", label: "Breakfast" },
  { id: "dessert", label: "Desserts" },
] as const;
const query = ref("");
const course = ref<string | null>(null);
const recipes = ref<RecipeListItem[]>([]);
const cursor = ref<number | null>(null);
const loadingRecipes = ref(false);
const recipeError = ref("");
const openSlug = ref<string | null>(null);

async function loadRecipes(more = false) {
  loadingRecipes.value = true;
  recipeError.value = "";
  try {
    const page = await apiFetch<RecipeCollection>(`${config.public.apiBase}/api/recipes`, {
      query: { q: query.value.trim() || undefined, course: course.value ?? undefined, limit: 24, after_id: more ? cursor.value ?? undefined : undefined },
    });
    recipes.value = more ? [...recipes.value, ...page.items] : page.items;
    cursor.value = page.next_cursor;
  }
  catch {
    recipeError.value = "Recipes could not be loaded. Try again in a moment.";
  }
  finally {
    loadingRecipes.value = false;
  }
}

let typing: ReturnType<typeof setTimeout> | undefined;
watch([query, course], () => {
  clearTimeout(typing);
  typing = setTimeout(() => loadRecipes(), 250);
});
onMounted(() => loadRecipes());

// Groceries: FairPrice products, from saved prices unless live prices are asked for.
const productQuery = ref("");
const live = ref(false);
const products = ref<ProductSearchResponse | null>(null);
const loadingProducts = ref(false);
const productError = ref("");

async function searchProducts() {
  const q = productQuery.value.trim();
  if (q.length < 2) return;
  loadingProducts.value = true;
  productError.value = "";
  try {
    products.value = await apiFetch<ProductSearchResponse>(`${config.public.apiBase}/api/products/search`, { query: { q, live: live.value, limit: 20 } });
  }
  catch {
    productError.value = "Products could not be searched. Try again in a moment.";
  }
  finally {
    loadingProducts.value = false;
  }
}

function packLabel(size: number | null, unit: string | null) {
  return size && unit ? `${size} ${unit}` : "";
}
</script>

<template>
  <main class="page-width browse">
    <section class="head">
      <p class="eyebrow">Browse</p>
      <h1>Everything the planner can choose from.</h1>
      <div class="tabs" role="tablist" aria-label="What to browse">
        <button type="button" role="tab" :aria-selected="tab === 'recipes'" @click="tab = 'recipes'">Recipes</button>
        <button type="button" role="tab" :aria-selected="tab === 'products'" @click="tab = 'products'">Groceries</button>
      </div>
    </section>

    <section v-if="tab === 'recipes'" aria-label="Recipes">
      <div class="controls">
        <label class="search">
          <span class="visually-hidden">Search recipes</span>
          <input v-model="query" type="search" placeholder="Search recipes, e.g. tofu soba" autocomplete="off">
        </label>
        <div class="chips" role="group" aria-label="Course">
          <button v-for="item in COURSES" :key="item.label" type="button" class="chip" :aria-pressed="course === item.id" @click="course = item.id">{{ item.label }}</button>
        </div>
      </div>
      <p v-if="recipeError" class="notice" role="alert">{{ recipeError }}</p>
      <p v-else-if="!loadingRecipes && !recipes.length" class="notice">No recipe matches that. Try fewer words.</p>
      <ul class="cards">
        <li v-for="recipe in recipes" :key="recipe.id">
          <button type="button" class="card" @click="openSlug = recipe.slug">
            <span class="plate" :style="plateStyle(recipe.slug)" aria-hidden="true" />
            <span class="title">{{ recipe.title }}</span>
            <small>{{ recipe.total_time_minutes }} min · {{ Math.round(recipe.nutrition.calories_kcal) }} kcal<template v-if="recipe.course"> · {{ recipe.course.replace("_", " ") }}</template></small>
          </button>
        </li>
      </ul>
      <button v-if="cursor" type="button" class="secondary-button more" :disabled="loadingRecipes" @click="loadRecipes(true)">
        {{ loadingRecipes ? "Loading…" : "Show more" }}
      </button>
    </section>

    <section v-else aria-label="Groceries">
      <form class="controls" @submit.prevent="searchProducts">
        <label class="search">
          <span class="visually-hidden">Search groceries</span>
          <input v-model="productQuery" type="search" placeholder="Search FairPrice, e.g. chicken breast" autocomplete="off" minlength="2">
        </label>
        <label class="live"><input v-model="live" type="checkbox"> Live prices</label>
        <button type="submit" class="secondary-button" :disabled="loadingProducts || productQuery.trim().length < 2">{{ loadingProducts ? "Searching…" : "Search" }}</button>
      </form>
      <p v-if="productError" class="notice" role="alert">{{ productError }}</p>
      <p v-if="products?.warning" class="notice">{{ products.warning }}</p>
      <p v-if="products && !products.items.length" class="notice">FairPrice has nothing for “{{ products.query }}”.</p>
      <table v-if="products?.items.length" class="products">
        <thead><tr><th>Product</th><th>Pack</th><th class="num">Price</th><th /></tr></thead>
        <tbody>
          <tr v-for="item in products.items" :key="item.external_id" :class="{ out: !item.in_stock }">
            <td>{{ item.name }}<small v-if="item.brand">{{ item.brand }}</small></td>
            <td>{{ packLabel(item.package_size, item.package_unit) }}</td>
            <td class="num">{{ formatSgd(item.price_sgd) }}<small v-if="!item.in_stock">Out of stock</small></td>
            <td><a :href="item.product_url" target="_blank" rel="noopener">FairPrice</a></td>
          </tr>
        </tbody>
      </table>
      <p v-if="products?.items.length" class="source">
        {{ products.provider_used === "fairprice" ? "Live FairPrice prices" : "Saved prices" }}{{ products.fallback_used ? " (live prices were unavailable)" : "" }}
      </p>
    </section>

    <HomeRecipeSheet v-if="openSlug" :slug="openSlug" @close="openSlug = null" />
  </main>
</template>

<style scoped>
.browse { padding-block: 32px 64px; }
.head h1 { margin: 6px 0 18px; font-family: var(--serif); font-weight: 300; font-size: clamp(26px, 4vw, 36px); text-wrap: balance; }
.tabs { display: flex; gap: 6px; }
.tabs button, .chip { padding: 7px 14px; border: 1px solid var(--border); border-radius: 999px; background: transparent; color: var(--t2); cursor: pointer; font: inherit; font-size: 13px; }
.tabs button[aria-selected="true"], .chip[aria-pressed="true"] { border-color: var(--accent); color: var(--ivory); background: rgba(232, 144, 111, 0.12); }
.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 22px 0 16px; }
.search { flex: 1 1 260px; }
.search input { width: 100%; padding: 10px 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--s1); color: var(--ivory); font: inherit; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.live { display: flex; gap: 6px; align-items: center; color: var(--t2); font-size: 13px; }
.notice { color: var(--t3); }
.cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 10px; }
.card { width: 100%; height: 100%; display: grid; grid-template-columns: 44px 1fr; grid-template-rows: auto auto; column-gap: 12px; align-items: center; padding: 12px; border: 1px solid var(--border); border-radius: 14px; background: var(--s1); color: inherit; text-align: left; cursor: pointer; font: inherit; }
.card:hover, .card:focus-visible { border-color: var(--accent); }
.card .plate { --size: 44px; grid-row: 1 / 3; }
.card .title { font-family: var(--serif); font-size: 15px; line-height: 1.25; }
.card small { color: var(--t3); font-size: 12px; }
.more { margin-top: 18px; }
.products { width: 100%; border-collapse: collapse; font-size: 14px; }
.products th { text-align: left; font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); padding: 8px 10px; border-bottom: 1px solid var(--border); }
.products td { padding: 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.products td small { display: block; color: var(--t3); font-size: 12px; }
.products .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.products .out td { color: var(--t3); }
.products a { color: var(--accent); }
.source { margin-top: 10px; color: var(--muted); font-size: 12px; }
@media (max-width: 640px) {
  .products th:nth-child(2), .products td:nth-child(2) { display: none; }
}
</style>
