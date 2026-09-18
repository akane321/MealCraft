<script setup lang="ts">
import { allergenLabel } from "~/lib/allergens";
import type { RecipeDetail } from "~/types/recipe";

const props = defineProps<{ slug: string }>();
const emit = defineEmits<{ close: [] }>();

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const recipe = ref<RecipeDetail | null>(null);
const failed = ref(false);

watch(() => props.slug, async (slug) => {
  recipe.value = null;
  failed.value = false;
  try {
    recipe.value = await apiFetch<RecipeDetail>(`${config.public.apiBase}/api/recipes/${slug}`);
  }
  catch {
    failed.value = true;
  }
}, { immediate: true });

function amount(item: RecipeDetail["ingredients"][number]) {
  if (item.quantity === null) return "";
  return `${item.quantity}${item.unit ? ` ${item.unit}` : ""}`;
}
</script>

<template>
  <div class="mc-overlay" role="dialog" aria-modal="true" :aria-label="recipe ? recipe.title : 'Recipe'" @keydown.esc="emit('close')">
    <section class="mc-ribbed panel">
      <header>
        <div>
          <h2 class="mc-serif">{{ recipe?.title ?? "Recipe" }}</h2>
          <p v-if="recipe">{{ recipe.total_time_minutes }} min · serves {{ recipe.servings }} · {{ recipe.cuisine }}</p>
        </div>
        <button type="button" class="mc-pill close" aria-label="Close recipe" @click="emit('close')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </header>

      <p v-if="failed" class="note">This recipe couldn't be loaded. Try again in a moment.</p>
      <p v-else-if="!recipe" class="note">Loading…</p>
      <div v-else class="body">
        <section class="mc-frost card" aria-label="Ingredients">
          <h3>Ingredients</h3>
          <p class="hint">Quantities serve {{ recipe.servings }}. Allergens come from ingredient data; check product labels.</p>
          <ul>
            <li v-for="item in recipe.ingredients" :key="item.normalized_name">
              <span class="name">{{ item.name }}<small v-if="item.preparation">, {{ item.preparation }}</small></span>
              <span class="qty">{{ amount(item) }}</span>
              <span v-if="item.allergens.length" class="allergen">Contains {{ item.allergens.map(allergenLabel).join(", ") }}</span>
            </li>
          </ul>
        </section>
        <section class="mc-frost card" aria-label="Steps">
          <h3>Steps</h3>
          <ol>
            <li v-for="step in recipe.steps" :key="step.step_number">{{ step.instruction }}</li>
          </ol>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.panel { width: min(920px, calc(100vw - 64px)); max-height: calc(100vh - 64px); overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
header { display: flex; align-items: flex-start; gap: 12px; }
header > div { flex-grow: 1; }
h2 { margin: 0; font-size: 28px; }
header p { margin: 4px 0 0; font-size: 12px; color: var(--mc-text-3); }
.close { width: 40px; height: 40px; padding: 0; display: flex; align-items: center; justify-content: center; }
svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; }
.note { margin: 12px 0; font-size: 14px; color: var(--mc-text-2); }
.body { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 14px; align-items: start; }
.card { padding: 16px; border-radius: 18px; }
h3 { margin: 0 0 6px; font-size: 14px; }
.hint { margin: 0 0 8px; font-size: 11px; color: var(--mc-text-3); }
ul { list-style: none; margin: 0; padding: 0; }
ul li { padding: 8px 0; border-top: 1px solid rgba(242, 237, 228, 0.08); display: grid; grid-template-columns: 1fr auto; gap: 2px 10px; font-size: 13px; }
.name small { color: var(--mc-text-3); }
.qty { color: var(--mc-text-2); }
.allergen { grid-column: 1 / -1; font-size: 11px; font-weight: 600; color: var(--mc-accent); }
ol { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 10px; font-size: 14px; line-height: 1.55; }
</style>
