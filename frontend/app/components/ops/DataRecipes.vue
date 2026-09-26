<script setup lang="ts">
import { DATA_COURSES, DATA_MEAL_TYPES, DATA_TAGS, formatWhen, humanKey } from "~/lib/ops";
import type { OpsRecipe, OpsRecipeDetail } from "~/types/ops";

// Recipes: search and filters, then a drawer (?recipe=12) to edit, withdraw or restore one.
const PAGE = 25;
const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const route = useRoute();
const router = useRouter();
const api = (path: string) => `${config.public.apiBase}/api/ops/data${path}`;
const detailOf = (error: unknown, fallback: string) => {
  const found = (error as { data?: { detail?: unknown } }).data?.detail;
  return typeof found === "string" ? found : fallback;
};

const filters = reactive({ q: "", course: "", meal_type: "", origin: "", withdrawn: "" });
const offset = ref(0);
const page = ref<{ items: OpsRecipe[]; total: number } | null>(null);
const listFailed = ref(false);
async function loadList() {
  listFailed.value = false;
  const query: Record<string, string | number> = { offset: offset.value, limit: PAGE };
  for (const [key, value] of Object.entries(filters)) {
    if (value.trim()) query[key] = value.trim();
  }
  try {
    page.value = await apiFetch(api("/recipes"), { query });
  }
  catch {
    listFailed.value = true;
  }
}
let searchTimer: ReturnType<typeof setTimeout> | undefined;
watch(filters, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    offset.value = 0;
    loadList();
  }, 250);
});
watch(offset, loadList);
onMounted(loadList);

const selectedId = computed(() => (typeof route.query.recipe === "string" && /^\d+$/.test(route.query.recipe) ? Number(route.query.recipe) : null));
const detail = ref<OpsRecipeDetail | null>(null);
const detailFailed = ref(false);
const message = ref("");
const failure = ref("");
const edit = reactive({ title: "", course: "", tags: [] as string[], meal_types: [] as string[] });
function fill(recipe: OpsRecipeDetail) {
  detail.value = recipe;
  edit.title = recipe.title;
  edit.course = recipe.course ?? "";
  edit.tags = [...recipe.dietary_tags];
  edit.meal_types = [...(recipe.meal_types ?? [])];
}
async function loadDetail(id: number | null) {
  detail.value = null;
  detailFailed.value = false;
  message.value = "";
  failure.value = "";
  if (id === null) return;
  try {
    fill(await apiFetch<OpsRecipeDetail>(api(`/recipes/${id}`)));
  }
  catch {
    detailFailed.value = true;
  }
}
watch(selectedId, loadDetail, { immediate: true });

function open(recipe: OpsRecipe) {
  router.push({ query: { ...route.query, recipe: recipe.id } });
}
function close() {
  const { recipe: _recipe, ...rest } = route.query;
  router.push({ query: rest });
}

const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every(item => b.includes(item));
const changed = computed(() => {
  const recipe = detail.value;
  if (!recipe) return false;
  return edit.title.trim() !== recipe.title
    || edit.course !== (recipe.course ?? "")
    || !sameSet(edit.tags, recipe.dietary_tags)
    || !sameSet(edit.meal_types, recipe.meal_types ?? []);
});
const saving = ref(false);
async function save() {
  const recipe = detail.value;
  if (!recipe) return;
  saving.value = true;
  failure.value = "";
  const body: Record<string, unknown> = { title: edit.title.trim(), dietary_tags: edit.tags, meal_types: edit.meal_types };
  if (edit.course) body.course = edit.course;
  try {
    fill(await apiFetch<OpsRecipeDetail>(api(`/recipes/${recipe.id}`), { method: "PATCH", body }));
    message.value = "Saved.";
    await loadList();
  }
  catch (error) {
    failure.value = detailOf(error, "The recipe couldn't be saved.");
  }
  finally {
    saving.value = false;
  }
}

// Withdraw asks for a reason and a confirmation; restore only a confirmation.
const reason = ref("");
const pending = ref<"withdraw" | "restore" | null>(null);
const busy = ref(false);
async function confirmChange() {
  const recipe = detail.value;
  if (!recipe || !pending.value) return;
  const what = pending.value;
  busy.value = true;
  failure.value = "";
  try {
    const body = what === "withdraw" ? { reason: reason.value.trim() } : undefined;
    fill(await apiFetch<OpsRecipeDetail>(api(`/recipes/${recipe.id}/${what}`), { method: "POST", body }));
    message.value = what === "withdraw" ? "Withdrawn. It stays in the catalog but is never planned." : "Restored. The planner can choose it again.";
    reason.value = "";
    await loadList();
  }
  catch (error) {
    failure.value = detailOf(error, "That couldn't be changed.");
  }
  finally {
    pending.value = null;
    busy.value = false;
  }
}

const amount = (item: OpsRecipeDetail["ingredients"][number]) => [item.quantity, item.unit].filter(value => value !== null && value !== "").join(" ");
</script>

<template>
  <div class="ops-page">
    <div class="filters">
      <label class="grow">Search title or slug <input v-model="filters.q" type="search" placeholder="e.g. laksa"></label>
      <label>Course
        <select v-model="filters.course"><option value="">Any</option><option v-for="item in DATA_COURSES" :key="item" :value="item">{{ humanKey(item) }}</option></select>
      </label>
      <label>Meal type
        <select v-model="filters.meal_type"><option value="">Any</option><option v-for="item in DATA_MEAL_TYPES" :key="item" :value="item">{{ humanKey(item) }}</option></select>
      </label>
      <label>Source
        <select v-model="filters.origin"><option value="">Any</option><option value="release">Release</option><option value="curated">Curated</option></select>
      </label>
      <label>Planning
        <select v-model="filters.withdrawn"><option value="">Any</option><option value="false">Plannable</option><option value="true">Withdrawn</option></select>
      </label>
    </div>

    <div v-if="listFailed" class="ops-card" role="alert">
      <p class="ops-error">The recipe list couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="loadList">Try again</button>
    </div>
    <p v-else-if="!page" class="ops-muted" aria-busy="true">Loading recipes…</p>
    <p v-else-if="!page.items.length" class="ops-card ops-muted">No recipe matches.</p>
    <section v-else class="ops-card table-card" aria-label="Recipes">
      <table>
        <thead><tr><th>Recipe</th><th>Course</th><th>Meal types</th><th>Dietary tags</th><th>Source</th><th>Planning</th></tr></thead>
        <tbody>
          <tr v-for="recipe in page.items" :key="recipe.id" :class="{ current: recipe.id === selectedId }">
            <td><button type="button" class="link" @click="open(recipe)">{{ recipe.title }}</button><span class="ops-muted sub">{{ recipe.slug }}</span></td>
            <td>{{ recipe.course ? humanKey(recipe.course) : "—" }}</td>
            <td>{{ recipe.meal_types?.join(", ") || "—" }}</td>
            <td>{{ recipe.dietary_tags.join(", ") || "—" }}</td>
            <td>{{ recipe.release_version ? `Release ${recipe.release_version}` : "Curated" }}</td>
            <td><span class="ops-badge" :style="{ '--dot': recipe.withdrawn ? 'var(--warn)' : 'var(--sage)' }">{{ recipe.withdrawn ? "Withdrawn" : "Plannable" }}</span></td>
          </tr>
        </tbody>
      </table>
      <footer class="pager">
        <span class="ops-muted">{{ offset + 1 }}–{{ offset + page.items.length }} of {{ page.total }}</span>
        <button type="button" class="mc-pill" :disabled="offset === 0" @click="offset = Math.max(0, offset - PAGE)">Previous</button>
        <button type="button" class="mc-pill" :disabled="offset + PAGE >= page.total" @click="offset += PAGE">Next</button>
      </footer>
    </section>

    <div v-if="selectedId !== null" class="drawer-scrim" @click.self="close">
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="recipe-title">
        <header class="drawer-head">
          <div>
            <p class="mc-eyebrow">Recipe #{{ selectedId }}</p>
            <h2 id="recipe-title" class="mc-serif">{{ detail?.title ?? "Loading…" }}</h2>
            <p v-if="detail" class="ops-muted">{{ detail.slug }} · {{ detail.cuisine }} · serves {{ detail.servings }} · {{ detail.prep_time_minutes + detail.cook_time_minutes }} min</p>
          </div>
          <button type="button" class="mc-pill" @click="close">Close</button>
        </header>

        <p v-if="detailFailed" class="ops-error" role="alert">This recipe couldn't be loaded.</p>
        <template v-else-if="detail">
          <p v-if="message" class="note" role="status">{{ message }}</p>
          <p v-if="failure" class="ops-error" role="alert">{{ failure }}</p>

          <form class="edit" @submit.prevent="save">
            <h3>Edit</h3>
            <label>Title <input v-model="edit.title" maxlength="200" required></label>
            <label>Course
              <select v-model="edit.course"><option value="" disabled>None (curated: always a candidate)</option><option v-for="item in DATA_COURSES" :key="item" :value="item">{{ humanKey(item) }}</option></select>
            </label>
            <fieldset>
              <legend>Meal types</legend>
              <label v-for="item in DATA_MEAL_TYPES" :key="item"><input v-model="edit.meal_types" type="checkbox" :value="item"> {{ humanKey(item) }}</label>
            </fieldset>
            <fieldset>
              <legend>Dietary tags</legend>
              <label v-for="item in DATA_TAGS" :key="item"><input v-model="edit.tags" type="checkbox" :value="item"> {{ item }}</label>
            </fieldset>
            <button type="submit" class="mc-primary" :disabled="!changed || saving">{{ saving ? "Saving…" : "Save changes" }}</button>
          </form>

          <section>
            <h3>Planning</h3>
            <template v-if="detail.withdrawn">
              <p>Withdrawn{{ detail.withdrawn_at ? ` ${formatWhen(detail.withdrawn_at)}` : "" }}: {{ detail.withdrawn_reason ?? "no reason recorded" }}</p>
              <p v-if="detail.withdrawn === 'file'" class="ops-muted small">Withdrawn by the reviewed list in data/recipes/withdrawn.json; restore it there.</p>
              <div v-else class="actions"><button type="button" class="mc-pill" @click="pending = 'restore'">Restore</button></div>
            </template>
            <template v-else>
              <p class="ops-muted small">A withdrawn recipe stays browsable but is never planned.</p>
              <label class="edit">Reason <textarea v-model="reason" rows="2" maxlength="500" placeholder="e.g. pet food, not a dinner" /></label>
              <div class="actions"><button type="button" class="mc-pill danger" :disabled="!reason.trim()" @click="pending = 'withdraw'">Withdraw</button></div>
            </template>
          </section>

          <section>
            <h3>Ingredients ({{ detail.ingredients.length }})</h3>
            <ul class="rows">
              <li v-for="item in detail.ingredients" :key="`${item.ingredient_id}-${item.original_text}`">
                <span>{{ item.name }}<span v-if="item.preparation" class="ops-muted">, {{ item.preparation }}</span></span>
                <span class="ops-muted mc-num">{{ amount(item) || item.original_text || "—" }}</span>
              </li>
            </ul>
            <p v-if="detail.allergens?.length" class="ops-muted small">Allergens (rule-derived): {{ detail.allergens.join(", ") }}</p>
          </section>

          <section>
            <h3>Steps</h3>
            <ol class="steps"><li v-for="(step, index) in detail.steps" :key="index">{{ step }}</li></ol>
          </section>

          <section v-if="detail.nutrition">
            <h3>Nutrition per serving</h3>
            <OpsFields :data="detail.nutrition" />
          </section>
        </template>
        <p v-else class="ops-muted" aria-busy="true">Loading the recipe…</p>
      </aside>
    </div>

    <OpsConfirm
      v-if="pending"
      :title="pending === 'withdraw' ? 'Withdraw this recipe?' : 'Restore this recipe?'"
      :message="pending === 'withdraw' ? `${detail?.title} stays in the catalog but the planner never chooses it again. Reason: ${reason.trim()}` : `${detail?.title} can be planned again from the next request.`"
      :action="pending === 'withdraw' ? 'Withdraw' : 'Restore'"
      :danger="pending === 'withdraw'"
      :busy="busy"
      @confirm="confirmChange"
      @cancel="pending = null"
    />
  </div>
</template>

<style scoped>
.steps { display: grid; gap: 8px; margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.5; }
</style>
