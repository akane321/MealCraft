<script setup lang="ts">
import { allergenLabel } from "~/lib/allergens";
import type { RecipeDetail } from "~/types/recipe";

const props = defineProps<{ slug: string }>();
const emit = defineEmits<{ close: [] }>();

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const recipe = ref<RecipeDetail | null>(null);
const failed = ref(false);

async function load(slug: string) {
  recipe.value = null;
  failed.value = false;
  try {
    recipe.value = await apiFetch<RecipeDetail>(`${config.public.apiBase}/api/recipes/${slug}`);
  }
  catch {
    failed.value = true;
  }
}

watch(() => props.slug, load, { immediate: true });

function amount(item: RecipeDetail["ingredients"][number]) {
  if (item.quantity === null) return "";
  return `${item.quantity}${item.unit ? ` ${item.unit}` : ""}`;
}

const overlay = ref<HTMLElement | null>(null);
useDialog(overlay, () => emit("close"));
</script>

<template>
  <div ref="overlay" class="mc-overlay" role="dialog" aria-modal="true" :aria-label="recipe ? recipe.title : 'Recipe'">
    <section class="mc-panel panel">
      <header class="mc-sheet-head">
        <span v-if="recipe" class="icon"><HomeDishIcon :title="recipe.title" :course="recipe.course" :ingredients="recipe.ingredients.map(item => item.name)" :size="32" /></span>
        <div>
          <h2>{{ recipe?.title ?? "Recipe" }}</h2>
          <p v-if="recipe">{{ recipe.total_time_minutes }} min · serves {{ recipe.servings }} · {{ recipe.cuisine }}</p>
        </div>
        <button type="button" class="mc-close" aria-label="Close recipe" @click="emit('close')">
          <UIcon name="i-lucide-x" aria-hidden="true" />
        </button>
      </header>

      <HomePanelState
        v-if="failed || !recipe"
        :state="failed ? 'error' : 'loading'"
        title=""
        empty-text=""
        error-text="This recipe couldn't be loaded."
        :rows="3"
        @retry="load(slug)"
      />
      <div v-else class="body">
        <section class="card" aria-label="Ingredients">
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
        <section class="card" aria-label="Steps">
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
.panel { width: min(920px, calc(100vw - 64px)); max-height: calc(100vh - 64px); overflow-y: auto; display: flex; flex-direction: column; }
.icon { width: 36px; height: 36px; flex: none; display: grid; place-items: center; border-radius: 10px; background: #fafafa; }
/* Two columns split by a thin rule, no cards inside the sheet. */
.body { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); align-items: stretch; padding: 0; }
.card { padding: 20px 24px 24px; }
.card + .card { border-left: 1px solid #f0f0f2; }
h3 { margin: 0 0 6px; color: #71717a; font-size: 11px; line-height: 16px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; }
.hint { margin: 0 0 8px; color: #71717a; font-size: 12px; line-height: 16px; }
ul { list-style: none; margin: 0; padding: 0; }
ul li { display: grid; grid-template-columns: 1fr auto; align-items: baseline; gap: 4px 12px; padding: 9px 0; border-top: 1px solid #f2f2f4; }
.name { color: #18181b; font-size: 14px; line-height: 20px; font-weight: 500; }
.name small { color: #71717a; font-size: 12px; font-weight: 400; }
.qty { color: #52525b; font-size: 14px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.allergen { grid-column: 1 / -1; justify-self: start; display: inline-flex; align-items: center; height: 22px; padding: 0 8px; border-radius: 999px; background: #fef3f2; color: #b42318; font-size: 12px; font-weight: 500; }
ol { counter-reset: step; margin: 8px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 12px; }
ol li { counter-increment: step; display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 10px; color: #27272a; font-size: 14px; line-height: 22px; }
ol li::before { content: counter(step); width: 22px; height: 22px; display: grid; place-items: center; border-radius: 50%; background: #f4f4f5; color: #52525b; font-size: 12px; line-height: 1; font-weight: 600; }
</style>
