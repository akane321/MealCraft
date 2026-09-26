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
      <p class="mc-eyebrow">Data</p>
      <h1 class="mc-serif">Recipes, ingredients and product mappings</h1>
      <p>Browse the catalog the planner reads and correct it. Every change is recorded with who made it and what it was before. Allergens stay rule-derived and are shown, not edited.</p>
    </header>

    <nav class="tabs" role="tablist" aria-label="Data">
      <button v-for="item in TABS" :key="item.key" type="button" role="tab" :aria-selected="tab === item.key" :class="{ active: tab === item.key }" @click="show(item.key)">{{ item.label }}</button>
    </nav>

    <OpsDataRecipes v-if="tab === 'recipes'" />
    <OpsDataIngredients v-else-if="tab === 'ingredients'" />
    <OpsDataMappings v-else />
  </div>
</template>

<style scoped>
.tabs { display: flex; flex-wrap: wrap; gap: 6px; }
.tabs button { padding: 8px 14px; border: 1px solid var(--line-2); border-radius: 999px; background: none; color: var(--t2); font-size: 13px; }
.tabs button.active { background: var(--s3); color: var(--ivory); border-color: var(--accent); }

/* Shared by the three tables and their drawers. */
:deep(.filters) { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; }
:deep(.filters label) { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
:deep(.filters label.grow) { flex: 1 1 260px; max-width: 420px; }
:deep(input:not([type="checkbox"])), :deep(select), :deep(textarea) { padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 10px; background: var(--s2); color: var(--ivory); font: inherit; font-size: 13px; }
:deep(.table-card) { padding: 0; overflow-x: auto; }
:deep(table) { width: 100%; border-collapse: collapse; font-size: 13px; }
:deep(th) { padding: 12px 16px; border-bottom: 1px solid var(--line-2); color: var(--t3); font-weight: 500; text-align: left; white-space: nowrap; }
:deep(td) { padding: 10px 16px; border-bottom: 1px solid var(--line); vertical-align: top; }
:deep(tr.current td) { background: var(--s2); }
:deep(.link) { padding: 0; border: 0; background: none; color: var(--ivory); text-align: left; }
:deep(.link:hover) { color: var(--accent); }
:deep(.sub) { display: block; font-size: 12px; }
:deep(.pager) { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 12px 16px; }
:deep(.pager span) { margin-right: auto; font-size: 12.5px; }
:deep(.drawer-scrim) { position: fixed; inset: 0; z-index: 30; display: flex; justify-content: flex-end; background: rgba(14, 12, 10, 0.6); }
:deep(.drawer) { width: min(640px, 100%); height: 100%; overflow-y: auto; padding: 24px; border-left: 1px solid var(--line-2); background: var(--s1); animation: mc-rise 320ms var(--ease) both; }
:deep(.drawer-head) { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
:deep(.drawer-head h2) { margin: 6px 0 2px; font-size: 24px; font-weight: 300; }
:deep(.drawer-head p) { margin: 0; font-size: 12.5px; }
:deep(.drawer section), :deep(.drawer form) { margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--line); }
:deep(.drawer h3) { margin: 0 0 12px; color: var(--t2); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
:deep(.edit) { display: grid; gap: 12px; }
:deep(.edit label) { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
:deep(.edit fieldset) { display: flex; flex-wrap: wrap; gap: 8px 14px; margin: 0; padding: 0; border: 0; }
:deep(.edit legend) { margin-bottom: 6px; color: var(--t3); font-size: 12px; }
:deep(.edit fieldset label) { display: flex; align-items: center; gap: 6px; color: var(--ivory); font-size: 13px; }
:deep(.edit .mc-primary), :deep(.edit .mc-pill) { justify-self: start; }
:deep(.drawer a) { color: var(--ivory); }
:deep(.drawer a:hover) { color: var(--accent); }
:deep(.edit p), :deep(.drawer section p) { margin: 0; }
:deep(.small) { font-size: 12px; }
:deep(.note) { padding: 9px 12px; border-radius: 10px; background: rgba(169, 183, 154, 0.12); color: var(--ivory); }
:deep(.chips) { display: flex; flex-wrap: wrap; gap: 6px; }
:deep(.chip) { padding: 2px 9px; border: 1px solid var(--line-2); border-radius: 999px; font-size: 12px; white-space: nowrap; }
:deep(.rows) { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
:deep(.rows li) { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 12px; padding: 8px 12px; border-radius: 10px; background: var(--s2); }
:deep(.actions) { display: flex; flex-wrap: wrap; gap: 8px; }
:deep(.mc-pill.danger) { color: var(--warn); border-color: rgba(236, 122, 90, 0.35); }
</style>
