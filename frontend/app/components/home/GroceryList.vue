<script setup lang="ts">
import { formatSgd, groceryGroups, packageLabel, priceSourceLabel } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";

const props = defineProps<{ estimate: WeeklyGroceryEstimate }>();

const groups = computed(() => groceryGroups(props.estimate.items));
// Ticked items only matter while shopping; they are not saved.
const got = ref(new Set<string>());

function toggle(name: string) {
  const next = new Set(got.value);
  if (!next.delete(name)) next.add(name);
  got.value = next;
}
</script>

<template>
  <div class="groceries">
    <p class="source">{{ priceSourceLabel(estimate) }}</p>
    <template v-for="group in groups" :key="group.name">
      <h3 class="aisle">{{ group.name }}</h3>
      <label v-for="line in group.lines" :key="line.ingredient_name" class="item">
        <input type="checkbox" :checked="got.has(line.ingredient_name)" @change="toggle(line.ingredient_name)">
        <span><span class="p">{{ line.ingredient_display_name }}</span><span class="s">{{ packageLabel(line) }}</span></span>
        <span class="c mc-num">{{ formatSgd(line.purchase_cost_sgd) }}</span>
      </label>
    </template>
    <template v-if="estimate.unmapped_ingredients.length">
      <h3 class="aisle">No price found</h3>
      <p class="unmapped">{{ estimate.unmapped_ingredients.join(", ") }}</p>
    </template>
    <p v-if="!groups.length && !estimate.unmapped_ingredients.length" class="unmapped">Everything this week is already at home.</p>
  </div>
</template>

<style scoped>
.groceries { padding-bottom: 12px; }
.source { margin: 0; padding: 14px 22px 0; font-size: 12px; color: var(--t3); }
.aisle { margin: 0; padding: 16px 22px 6px; font-size: 10.5px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.item { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 8px 22px; cursor: pointer; }
.item:hover { background: rgba(242, 237, 228, 0.025); }
.item > span:nth-child(2) { display: grid; min-width: 0; }
.item input { appearance: none; width: 16px; height: 16px; margin: 0; border-radius: 5px; border: 1px solid var(--line-2); background: var(--s2); display: grid; place-items: center; cursor: pointer; }
.item input:checked { background: var(--sage); border-color: var(--sage); }
.item input:checked::after { content: ""; width: 7px; height: 4px; border: solid var(--ink); border-width: 0 0 1.6px 1.6px; transform: rotate(-45deg) translate(1px, -1px); }
.p { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s { font-size: 11.5px; color: var(--t3); }
.c { font-size: 13px; color: var(--t2); }
.item:has(input:checked) .p { color: var(--t4); text-decoration: line-through; }
.unmapped { margin: 0; padding: 0 22px; font-size: 12.5px; line-height: 1.6; color: var(--t3); }
</style>
