<script setup lang="ts">
import { formatSgd, productSourceLabel } from "~/lib/home-surface";
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
      <h1>Everything the planner can choose from</h1>
      <p class="mc-sub">Open a recipe for its steps, or look up what a grocery costs at FairPrice.</p>
      <div class="tabs mc-segmented" role="tablist" aria-label="What to browse">
        <button type="button" role="tab" :aria-selected="tab === 'recipes'" @click="tab = 'recipes'"><MotionTabPill v-if="tab === 'recipes'" id="browse-tabs" />Recipes</button>
        <button type="button" role="tab" :aria-selected="tab === 'products'" @click="tab = 'products'"><MotionTabPill v-if="tab === 'products'" id="browse-tabs" />Groceries</button>
      </div>
    </section>

    <section v-if="tab === 'recipes'" aria-label="Recipes">
      <div class="controls">
        <label class="search">
          <UIcon name="i-lucide-search" aria-hidden="true" />
          <span class="visually-hidden">Search recipes</span>
          <input v-model="query" type="search" placeholder="Search recipes, e.g. tofu soba" autocomplete="off">
        </label>
        <div class="chips" role="group" aria-label="Course">
          <button v-for="item in COURSES" :key="item.label" type="button" class="chip" :aria-pressed="course === item.id" @click="course = item.id">{{ item.label }}</button>
        </div>
      </div>
      <p v-if="recipeError" class="mc-alert" role="alert"><UIcon name="i-lucide-circle-alert" aria-hidden="true" />{{ recipeError }}</p>
      <p v-else-if="loadingRecipes && !recipes.length" class="mc-loading"><MotionLoader />Loading recipes…</p>
      <div v-else-if="!loadingRecipes && !recipes.length" class="mc-empty">
        <div class="mc-empty-art"><span><span class="mc-tile" data-tone="violet"><UIcon name="i-lucide-search-x" /></span></span></div>
        <h2>No recipe matches that</h2>
        <p>Try fewer words.</p>
        <button v-if="query" type="button" class="secondary-button clear" @click="query = ''">Clear search</button>
      </div>
      <ul class="cards">
        <!-- While the first page loads, grey cards hold the grid's place. -->
        <li v-for="n in (loadingRecipes && !recipes.length && !recipeError ? 8 : 0)" :key="`skeleton-${n}`" class="skeleton-card" aria-hidden="true"><i /><b /><b /></li>
        <li v-for="recipe in recipes" :key="recipe.id">
          <button type="button" class="card" @click="openSlug = recipe.slug">
            <HomeDishIcon class="icon" :slug="recipe.slug" :title="recipe.title" :course="recipe.course ?? recipe.meal_type" :size="44" />
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
          <UIcon name="i-lucide-search" aria-hidden="true" />
          <span class="visually-hidden">Search groceries</span>
          <input v-model="productQuery" type="search" placeholder="Search FairPrice, e.g. chicken breast" autocomplete="off" minlength="2">
        </label>
        <label class="live"><input v-model="live" type="checkbox"> Ask FairPrice now</label>
        <button type="submit" class="primary-button" :disabled="loadingProducts || productQuery.trim().length < 2">{{ loadingProducts ? "Searching…" : "Search" }}</button>
      </form>
      <p v-if="productError" class="mc-alert" role="alert"><UIcon name="i-lucide-circle-alert" aria-hidden="true" />{{ productError }}</p>
      <p v-if="products && !products.items.length" class="notice">FairPrice has nothing for “{{ products.query }}”.</p>
      <div v-if="!products && !loadingProducts && !productError" class="mc-empty">
        <div class="mc-empty-art"><span><span class="mc-tile" data-tone="violet"><UIcon name="i-lucide-shopping-basket" /></span></span></div>
        <h2>Look up a grocery</h2>
        <p>Search a grocery to see its FairPrice price.</p>
      </div>
      <div v-if="products?.items.length" class="table-card">
        <table class="products">
          <thead><tr><th>Product</th><th class="num">Pack</th><th class="num">Price</th><th><span class="visually-hidden">Shop</span></th></tr></thead>
          <tbody>
            <tr v-for="item in products.items" :key="item.external_id" :class="{ out: !item.in_stock }">
              <td>{{ item.name }}<small v-if="item.brand">{{ item.brand }}</small></td>
              <td class="num">{{ packLabel(item.package_size, item.package_unit) }}</td>
              <td class="num"><span class="price">{{ formatSgd(item.price_sgd) }}<small v-if="!item.in_stock" class="stock">Out of stock</small></span></td>
              <td><a :href="item.product_url" target="_blank" rel="noopener">FairPrice</a></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="products?.items.length" class="source">
        {{ productSourceLabel(products) }}
      </p>
    </section>

    <HomeRecipeSheet v-if="openSlug" :slug="openSlug" @close="openSlug = null" />
  </main>
</template>

<style scoped>
.browse { padding-block: 28px 48px; }
.tabs { display: inline-flex; gap: 2px; }
.tabs button { border: 0; background: transparent; cursor: pointer; font: inherit; }
.tabs button[aria-selected="true"] { background: #fff; }
.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 16px 0; }
.search { flex: 0 1 320px; display: flex; align-items: center; gap: 8px; height: 36px; padding: 0 12px; border: 1px solid #e4e4e7; border-radius: 10px; background: #fff; box-shadow: var(--mc-shadow-xs); }
.search:focus-within { border-color: #8b5cf6; box-shadow: 0 0 0 3px #ede9fe; }
.search .iconify { width: 16px; height: 16px; flex: none; color: #a1a1aa; }
.search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; color: var(--mc-strong); font: inherit; }
.search input::placeholder { color: #71717a; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { height: 32px; padding: 0 12px; border: 1px solid #ececef; border-radius: 999px; background: #fff; color: #52525b; cursor: pointer; font: inherit; font-size: 13px; font-weight: 500; }
.chip:hover { border-color: #d4d4d8; }
.chip[aria-pressed="true"] { border-color: #18181b; background: #18181b; color: #fff; }
.live { display: flex; gap: 6px; align-items: center; color: var(--t2); font-size: 13px; }
.notice { color: #71717a; font-size: 14px; }
.cards { list-style: none; margin: 4px 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.card { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 14px; border: 1px solid #ececef; border-radius: 12px; background: #fff; color: inherit; text-align: left; cursor: pointer; font: inherit; box-shadow: var(--mc-shadow-sm); transition: border-color 160ms, box-shadow 160ms, transform 160ms; }
.card:hover, .card:focus-visible { border-color: #e1e1e5; box-shadow: 0 1px 2px rgba(16, 16, 20, 0.04), 0 12px 32px -12px rgba(16, 16, 20, 0.16); transform: translateY(-1px); }
@media (prefers-reduced-motion: reduce) { .card:hover, .card:focus-visible { transform: none; } }
.card .icon { margin-bottom: 6px; }
.card .title { color: var(--mc-strong); font-size: 14px; line-height: 20px; font-weight: 600; }
.card small { color: #71717a; font-size: 12.5px; }
.more { margin-top: 18px; }
.skeleton-card { height: 132px; display: flex; flex-direction: column; gap: 10px; padding: 14px; border: 1px solid #ececef; border-radius: 12px; background: #fff; animation: mc-pulse 1.4s ease-in-out infinite; }
.skeleton-card i { width: 40px; height: 40px; border-radius: 50%; background: #f4f4f5; }
.skeleton-card b { width: 70%; height: 12px; border-radius: 6px; background: #f4f4f5; }
.skeleton-card b + b { width: 45%; }
@keyframes mc-pulse { 50% { opacity: 0.55; } }
@media (prefers-reduced-motion: reduce) { .skeleton-card { animation: none; } }
/* The search button is the form's dark pill, as tall as the 36px field. */
.controls .primary-button { min-height: 36px; height: 36px; padding: 0 16px; font-size: 14px; }
.mc-empty .clear { margin-top: 16px; }
.mc-alert, .mc-loading { margin: 0 0 16px; }
/* Products: the spec table in a white card with a tinted header row. */
.table-card { border: 1px solid #ececef; border-radius: 12px; background: #fff; overflow: hidden; }
.products { width: 100%; border-collapse: collapse; font-size: 14px; line-height: 20px; }
.products th { height: 36px; padding: 0 14px; border-bottom: 1px solid #ececef; background: #fafafa; color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; text-align: left; }
.products td { padding: 10px 14px; border-bottom: 1px solid #f2f2f4; color: #27272a; vertical-align: middle; }
.products .price { display: inline-flex; align-items: center; justify-content: flex-end; gap: 6px; }
.products tbody tr:last-child td { border-bottom: 0; }
.products tbody tr:hover td { background: #fafafb; }
.products td small { display: block; color: #71717a; font-size: 12px; line-height: 16px; }
.products .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.products .out td { color: #71717a; }
.products .stock { display: inline-flex !important; align-items: center; height: 20px; padding: 0 8px; border-radius: 999px; background: #fffaeb; color: #b54708 !important; font-weight: 500; }
.products a { color: #6d28d9; font-size: 13px; font-weight: 500; text-decoration: none; }
.products a:hover { text-decoration: underline; }
.source { margin: 10px 0 0; color: #71717a; font-size: 12px; line-height: 16px; }
</style>
