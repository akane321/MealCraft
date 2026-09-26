<script setup lang="ts">
import { splitNames } from "~/lib/ops";
import type { OpsIngredient } from "~/types/ops";

// Ingredients: names the household and the parser use. Allergens are shown, never edited (ADR-0024).
const PAGE = 25;
const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const api = (path: string) => `${config.public.apiBase}/api/ops/data${path}`;

const search = ref("");
const offset = ref(0);
const page = ref<{ items: OpsIngredient[]; total: number } | null>(null);
const listFailed = ref(false);
async function loadList() {
  listFailed.value = false;
  const query: Record<string, string | number> = { offset: offset.value, limit: PAGE };
  if (search.value.trim()) query.q = search.value.trim();
  try {
    page.value = await apiFetch(api("/ingredients"), { query });
  }
  catch {
    listFailed.value = true;
  }
}
let searchTimer: ReturnType<typeof setTimeout> | undefined;
watch(search, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    offset.value = 0;
    loadList();
  }, 250);
});
watch(offset, loadList);
onMounted(loadList);

const selected = ref<OpsIngredient | null>(null);
const edit = reactive({ display_name: "", zh: "", aliases: "" });
const message = ref("");
const failure = ref("");
function open(ingredient: OpsIngredient) {
  selected.value = ingredient;
  edit.display_name = ingredient.display_name;
  edit.zh = ingredient.zh_names.join("\n");
  edit.aliases = ingredient.aliases.join("\n");
  message.value = "";
  failure.value = "";
}
function onKey(event: KeyboardEvent) {
  if (event.key === "Escape") selected.value = null;
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

const same = (a: string[], b: string[]) => JSON.stringify(a) === JSON.stringify(b);
const changed = computed(() => {
  const item = selected.value;
  return Boolean(item) && (edit.display_name.trim() !== item!.display_name || !same(splitNames(edit.zh), item!.zh_names) || !same(splitNames(edit.aliases), item!.aliases));
});
const saving = ref(false);
async function save() {
  const item = selected.value;
  if (!item) return;
  saving.value = true;
  failure.value = "";
  try {
    const saved = await apiFetch<OpsIngredient>(api(`/ingredients/${item.id}`), {
      method: "PATCH",
      body: { display_name: edit.display_name.trim(), zh_names: splitNames(edit.zh), aliases: splitNames(edit.aliases) },
    });
    open(saved);
    message.value = "Saved. The assistant uses these names from its next message.";
    await loadList();
  }
  catch {
    failure.value = "The ingredient couldn't be saved.";
  }
  finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="ops-page">
    <div class="filters">
      <label class="grow">Search any name, Chinese name or alias <input v-model="search" type="search" placeholder="e.g. spring onion or 葱"></label>
    </div>

    <div v-if="listFailed" class="ops-card" role="alert">
      <p class="ops-error">The ingredient list couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="loadList">Try again</button>
    </div>
    <p v-else-if="!page" class="ops-muted" aria-busy="true">Loading ingredients…</p>
    <p v-else-if="!page.items.length" class="ops-card ops-muted">No ingredient matches.</p>
    <section v-else class="ops-card table-card" aria-label="Ingredients">
      <table>
        <thead><tr><th>Ingredient</th><th>Chinese names</th><th>Aliases</th><th>Allergens</th><th>Recipes</th></tr></thead>
        <tbody>
          <tr v-for="item in page.items" :key="item.id" :class="{ current: item.id === selected?.id }">
            <td><button type="button" class="link" @click="open(item)">{{ item.display_name }}</button><span class="ops-muted sub">{{ item.normalized_name }}</span></td>
            <td>{{ item.zh_names.join("、") || "—" }}</td>
            <td>{{ item.aliases.join(", ") || "—" }}</td>
            <td>{{ item.allergens.join(", ") || "—" }}</td>
            <td class="mc-num">{{ item.recipes }}</td>
          </tr>
        </tbody>
      </table>
      <footer class="pager">
        <span class="ops-muted">{{ offset + 1 }}–{{ offset + page.items.length }} of {{ page.total }}</span>
        <button type="button" class="mc-pill" :disabled="offset === 0" @click="offset = Math.max(0, offset - PAGE)">Previous</button>
        <button type="button" class="mc-pill" :disabled="offset + PAGE >= page.total" @click="offset += PAGE">Next</button>
      </footer>
    </section>

    <div v-if="selected" class="drawer-scrim" @click.self="selected = null">
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="ingredient-title">
        <header class="drawer-head">
          <div>
            <p class="mc-eyebrow">Ingredient</p>
            <h2 id="ingredient-title" class="mc-serif">{{ selected.display_name }}</h2>
            <p class="ops-muted">{{ selected.normalized_name }} · in {{ selected.recipes }} {{ selected.recipes === 1 ? "recipe" : "recipes" }}</p>
          </div>
          <button type="button" class="mc-pill" @click="selected = null">Close</button>
        </header>

        <p v-if="message" class="note" role="status">{{ message }}</p>
        <p v-if="failure" class="ops-error" role="alert">{{ failure }}</p>

        <form class="edit" @submit.prevent="save">
          <h3>Edit</h3>
          <label>Display name <input v-model="edit.display_name" maxlength="160" required></label>
          <label>Chinese names, one per line <textarea v-model="edit.zh" rows="3" /></label>
          <label>Other names (aliases), one per line <textarea v-model="edit.aliases" rows="3" /></label>
          <p class="ops-muted small">The assistant matches these names exactly when a household uses them.</p>
          <button type="submit" class="mc-primary" :disabled="!changed || saving">{{ saving ? "Saving…" : "Save changes" }}</button>
        </form>

        <section>
          <h3>Allergens</h3>
          <div v-if="selected.allergens.length" class="chips"><span v-for="item in selected.allergens" :key="item" class="chip">{{ item }}</span></div>
          <p v-else class="ops-muted">None.</p>
          <p class="ops-muted small">Allergens are derived by rule and cannot be edited here. They change in their own reviewed files (data/ingredients/allergen-vocabulary.json and app/data/allergens.py).</p>
        </section>
      </aside>
    </div>
  </div>
</template>
