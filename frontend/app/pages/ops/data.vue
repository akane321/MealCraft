<script setup lang="ts">
// ADR-0047 Data: the catalog the planner reads, one table per kind. The open tab lives in the URL (?tab=).
const TABS = [
  { key: "recipes", label: "Recipes" },
  { key: "ingredients", label: "Ingredients" },
  { key: "mappings", label: "Product mappings" },
] as const;
type Tab = (typeof TABS)[number]["key"];

const route = useRoute();
const router = useRouter();
const tab = computed<Tab>(() => TABS.find(item => item.key === route.query.tab)?.key ?? "recipes");
function show(key: Tab) {
  router.push({ query: { tab: key } });
}
</script>

<template>
  <div class="ops-page">
    <header>
      <h1 class="mc-serif">Recipes, ingredients and product mappings</h1>
      <p>Browse the catalog the planner reads and correct it. Every change is recorded with who made it and what it was before. Allergens stay rule-derived and are shown, not edited.</p>
    </header>

    <nav class="tabs mc-segmented" role="tablist" aria-label="Data">
      <button v-for="item in TABS" :key="item.key" type="button" role="tab" :aria-selected="tab === item.key" @click="show(item.key)">{{ item.label }}</button>
    </nav>

    <OpsDataRecipes v-if="tab === 'recipes'" />
    <OpsDataIngredients v-else-if="tab === 'ingredients'" />
    <OpsDataMappings v-else />
  </div>
</template>

<style scoped>
/* Same segmented control as the browse page's Recipes / Groceries. */
.tabs { justify-self: start; display: inline-flex; }
.tabs button { cursor: pointer; }

/* Shared by the three tables and their drawers; tables, drawers and forms come from ops.vue. */
:deep(.data-pane) { display: grid; gap: 16px; min-width: 0; }
:deep(.filters) { display: grid; grid-auto-flow: column; grid-template-columns: minmax(0, 1fr); grid-auto-columns: minmax(140px, max-content); align-items: end; gap: 12px; margin: 0; }
:deep(.data-note) { margin: -4px 0 0; color: #71717a; font-size: 12.5px; line-height: 18px; }
:deep(.chip) { display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 12px; font-weight: 500; white-space: nowrap; }
</style>
