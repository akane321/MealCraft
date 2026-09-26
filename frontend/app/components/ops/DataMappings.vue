<script setup lang="ts">
import { humanKey, packageGrams } from "~/lib/ops";
import type { OpsMappedProduct, OpsProductMapping } from "~/types/ops";
import type { Product, ProductSearchResponse } from "~/types/recommendation";

// The reviewed ingredient → FairPrice mapping the estimator prices release ingredients with.
const PAGE = 25;
const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const api = (path: string) => `${config.public.apiBase}/api/ops/data${path}`;
const detailOf = (error: unknown, fallback: string) => {
  const found = (error as { data?: { detail?: unknown } }).data?.detail;
  return typeof found === "string" ? found : fallback;
};

const filters = reactive({ q: "", status: "" });
const offset = ref(0);
const page = ref<{ items: OpsProductMapping[]; total: number } | null>(null);
const listFailed = ref(false);
async function loadList() {
  listFailed.value = false;
  const query: Record<string, string | number> = { offset: offset.value, limit: PAGE };
  if (filters.q.trim()) query.q = filters.q.trim();
  if (filters.status) query.status = filters.status;
  try {
    page.value = await apiFetch(api("/mappings"), { query });
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

const selected = ref<OpsProductMapping | null>(null);
const message = ref("");
const failure = ref("");
function open(mapping: OpsProductMapping) {
  selected.value = mapping;
  message.value = "";
  failure.value = "";
  search.q = mapping.products[0]?.query ?? mapping.ingredient.replaceAll("_", " ");
  results.value = null;
  choice.value = null;
}
function onKey(event: KeyboardEvent) {
  if (event.key === "Escape" && !pending.value) selected.value = null;
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

// Find a replacement in FairPrice (the stored fixture unless "live" is ticked).
const search = reactive({ q: "", live: false });
const results = ref<Product[] | null>(null);
const searching = ref(false);
async function find() {
  searching.value = true;
  failure.value = "";
  try {
    const found = await apiFetch<ProductSearchResponse>(`${config.public.apiBase}/api/products/search`, { query: { q: search.q.trim(), live: search.live, limit: 8 } });
    results.value = found.items;
  }
  catch {
    failure.value = "The product search failed.";
  }
  finally {
    searching.value = false;
  }
}

// The one product the change maps to, with its package in grams of this ingredient.
const choice = ref<{ product: OpsMappedProduct; grams: number | null } | null>(null);
function pickResult(product: Product) {
  const grams = packageGrams(product.package_size, product.package_unit);
  choice.value = {
    grams,
    product: {
      external_id: product.external_id,
      name: product.name,
      brand: product.brand,
      category: product.category,
      package_grams: grams ?? 0,
      package_grams_basis: product.package_size ? `printed ${product.package_size} ${product.package_unit ?? ""}`.trim() : null,
      price_sgd: product.price_sgd,
      product_url: product.product_url,
      in_stock: product.in_stock,
      query: search.q.trim(),
      fetched_at: product.fetched_at,
    },
  };
}
function pickCurrent(product: OpsMappedProduct) {
  choice.value = { grams: product.package_grams, product: { ...product } };
}

const pending = ref<"change" | "remove" | null>(null);
const busy = ref(false);
const pendingText = computed(() => {
  const name = selected.value?.display_name ?? selected.value?.ingredient;
  if (pending.value === "remove") return `${name} loses its FairPrice product. Its cost shows as unknown and release recipes that need it are no longer planned.`;
  return `${name} is bought as ${choice.value?.product.name} (${choice.value?.grams} g, S$${choice.value?.product.price_sgd.toFixed(2)}) from the next estimate.`;
});
async function confirmChange() {
  const mapping = selected.value;
  if (!mapping || !pending.value) return;
  busy.value = true;
  failure.value = "";
  try {
    const path = api(`/mappings/${mapping.ingredient}`);
    selected.value = pending.value === "remove"
      ? await apiFetch<OpsProductMapping>(path, { method: "DELETE" })
      : await apiFetch<OpsProductMapping>(path, { method: "PUT", body: { product: { ...choice.value!.product, package_grams: choice.value!.grams } } });
    message.value = pending.value === "remove" ? "Mapping removed." : "Mapping changed.";
    choice.value = null;
    await loadList();
  }
  catch (error) {
    failure.value = detailOf(error, "The mapping couldn't be changed.");
  }
  finally {
    pending.value = null;
    busy.value = false;
  }
}

const cheapest = (mapping: OpsProductMapping) => mapping.products.reduce<OpsMappedProduct | null>((best, item) => (!best || item.price_sgd < best.price_sgd ? item : best), null);
</script>

<template>
  <div class="ops-page">
    <div class="filters">
      <label class="grow">Search ingredient or product <input v-model="filters.q" type="search" placeholder="e.g. agar or Swallow"></label>
      <label>Show
        <select v-model="filters.status">
          <option value="">All</option>
          <option value="mapped">Mapped</option>
          <option value="not_purchased">Not purchased</option>
          <option value="removed">Removed</option>
          <option value="console">Changed in the console</option>
        </select>
      </label>
    </div>
    <p class="ops-muted small">The reviewed snapshot keeps no per-product match score: every mapping in it passed review at 0.6 confidence or more, so the review status is shown instead.</p>

    <div v-if="listFailed" class="ops-card" role="alert">
      <p class="ops-error">The mapping list couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="loadList">Try again</button>
    </div>
    <p v-else-if="!page" class="ops-muted" aria-busy="true">Loading mappings…</p>
    <p v-else-if="!page.items.length" class="ops-card ops-muted">No mapping matches.</p>
    <section v-else class="ops-card table-card" aria-label="Product mappings">
      <table>
        <thead><tr><th>Ingredient</th><th>Product</th><th>Price</th><th>Package</th><th>Review</th><th>Source</th></tr></thead>
        <tbody>
          <tr v-for="item in page.items" :key="item.ingredient" :class="{ current: item.ingredient === selected?.ingredient }">
            <td><button type="button" class="link" @click="open(item)">{{ item.display_name ?? item.ingredient }}</button><span class="ops-muted sub">{{ item.ingredient }}</span></td>
            <template v-if="cheapest(item)">
              <td>{{ cheapest(item)!.name }}<span v-if="item.products.length > 1" class="ops-muted sub">+ {{ item.products.length - 1 }} more</span></td>
              <td class="mc-num">S${{ cheapest(item)!.price_sgd.toFixed(2) }}</td>
              <td class="mc-num">{{ cheapest(item)!.package_grams }} g</td>
            </template>
            <td v-else colspan="3" class="ops-muted">{{ humanKey(item.status) }}</td>
            <td>{{ item.review_status ? humanKey(item.review_status) : "—" }}</td>
            <td>{{ item.source === "console" ? "Console" : "Snapshot" }}</td>
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
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="mapping-title">
        <header class="drawer-head">
          <div>
            <p class="mc-eyebrow">Product mapping</p>
            <h2 id="mapping-title" class="mc-serif">{{ selected.display_name ?? selected.ingredient }}</h2>
            <p class="ops-muted">{{ selected.ingredient }} · {{ humanKey(selected.status) }} · {{ selected.source === "console" ? "changed in the console" : "reviewed snapshot" }}</p>
          </div>
          <button type="button" class="mc-pill" @click="selected = null">Close</button>
        </header>

        <p v-if="message" class="note" role="status">{{ message }}</p>
        <p v-if="failure" class="ops-error" role="alert">{{ failure }}</p>

        <section>
          <h3>Products ({{ selected.products.length }})</h3>
          <p v-if="!selected.products.length" class="ops-muted">None.</p>
          <ul v-else class="rows">
            <li v-for="product in selected.products" :key="product.external_id">
              <span><a :href="product.product_url" target="_blank" rel="noopener">{{ product.name }}</a><span class="ops-muted sub">{{ product.package_grams }} g · {{ product.package_grams_basis ?? "—" }}{{ product.in_stock ? "" : " · out of stock" }}</span></span>
              <span class="mc-num">S${{ product.price_sgd.toFixed(2) }}</span>
              <button v-if="selected.products.length > 1" type="button" class="mc-pill" @click="pickCurrent(product)">Use only this</button>
            </li>
          </ul>
          <p class="ops-muted small">The estimator buys the in-stock product that costs least for the quantity a recipe needs.</p>
          <div v-if="selected.status !== 'removed'" class="actions"><button type="button" class="mc-pill danger" @click="pending = 'remove'">Remove mapping</button></div>
        </section>

        <form class="edit" @submit.prevent="find">
          <h3>Change the product</h3>
          <label>Search FairPrice <input v-model="search.q" required minlength="2" maxlength="100"></label>
          <fieldset><label><input v-model="search.live" type="checkbox"> Live FairPrice (otherwise the stored fixture)</label></fieldset>
          <button type="submit" class="mc-pill" :disabled="searching || search.q.trim().length < 2">{{ searching ? "Searching…" : "Search" }}</button>
          <p v-if="results && !results.length" class="ops-muted">Nothing found.</p>
          <ul v-else-if="results" class="rows" aria-label="Search results">
            <li v-for="product in results" :key="product.external_id">
              <span>{{ product.name }}<span class="ops-muted sub">{{ product.package_size ?? "?" }} {{ product.package_unit ?? "" }}{{ product.in_stock ? "" : " · out of stock" }}</span></span>
              <span class="mc-num">S${{ product.price_sgd.toFixed(2) }}</span>
              <button type="button" class="mc-pill" @click="pickResult(product)">Use</button>
            </li>
          </ul>
        </form>

        <form v-if="choice" class="edit" @submit.prevent="pending = 'change'">
          <h3>New mapping</h3>
          <p>{{ choice.product.name }} · S${{ choice.product.price_sgd.toFixed(2) }}</p>
          <label>Package in grams of this ingredient <input v-model.number="choice.grams" type="number" min="0.001" step="any" required></label>
          <p class="ops-muted small">For a volume or a count, enter what the package weighs as this ingredient (e.g. 1 L of milk ≈ 1030 g).</p>
          <button type="submit" class="mc-primary" :disabled="!choice.grams || choice.grams <= 0">Map to this product</button>
        </form>
      </aside>
    </div>

    <OpsConfirm
      v-if="pending"
      :title="pending === 'remove' ? 'Remove this mapping?' : 'Change this mapping?'"
      :message="pendingText"
      :action="pending === 'remove' ? 'Remove mapping' : 'Change mapping'"
      :danger="pending === 'remove'"
      :busy="busy"
      @confirm="confirmChange"
      @cancel="pending = null"
    />
  </div>
</template>
