<script setup lang="ts">
import { formatSgd, groceryGroups, groceryPriceLabel, groceryPriceTimes, packageLabel, priceSourceLabel } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";

const props = defineProps<{ estimate: WeeklyGroceryEstimate }>();

const groups = computed(() => groceryGroups(props.estimate.items).map(group => ({
  ...group,
  sum: group.lines.reduce((total, line) => total + line.purchase_cost_sgd, 0),
})));
const lines = computed(() => groups.value.flatMap(group => group.lines));
const source = computed(() => priceSourceLabel(props.estimate));
// Green when every price is FairPrice's, amber when some are samples, grey when all are.
const sourceTone = computed(() => (source.value.startsWith("FairPrice prices") ? "ok" : source.value.startsWith("FairPrice") ? "warn" : ""));
const priceSource = (line: GroceryLineEstimate) => line.evidence?.price_source ?? line.evidence?.mode;
const live = computed(() => lines.value.filter(line => priceSource(line) === "live").length);
// A saved (not freshly checked) FairPrice price reads amber.
const stale = (line: GroceryLineEstimate) => Boolean(line.product && line.product.source === "fairprice" && priceSource(line) !== "live");
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
    <p class="source">
      <i :class="sourceTone" aria-hidden="true" />
      <b>{{ source }}</b>
      <span class="count">{{ live ? `${live} live · ${lines.length - live} saved` : `${lines.length} items` }}</span>
    </p>
    <div class="list">
      <template v-for="group in groups" :key="group.name">
        <h3 class="aisle">{{ group.name }}<span class="rule" /><span class="mc-num">{{ formatSgd(group.sum) }}</span></h3>
        <label v-for="line in group.lines" :key="line.ingredient_name" class="item">
          <input type="checkbox" :checked="got.has(line.ingredient_name)" @change="toggle(line.ingredient_name)">
          <span class="what">
            <span class="p">{{ line.ingredient_display_name }}</span>
            <span class="s" :class="{ stale: stale(line) }">{{ packageLabel(line) }} · <span :title="groceryPriceTimes(line)">{{ groceryPriceLabel(line) }}</span></span>
          </span>
          <span class="c mc-num">{{ formatSgd(line.purchase_cost_sgd) }}</span>
        </label>
      </template>
      <template v-if="estimate.unmapped_ingredients.length">
        <h3 class="aisle">No price found<span class="rule" /></h3>
        <p class="unmapped">{{ estimate.unmapped_ingredients.join(", ") }}</p>
      </template>
      <p v-if="!groups.length && !estimate.unmapped_ingredients.length" class="unmapped">Everything this week is already at home.</p>
    </div>
  </div>
</template>

<style scoped>
.source { position: sticky; top: 0; z-index: 1; margin: 0; display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--c-line-soft); background: #fff; font-size: 12px; line-height: 16px; }
.source i { width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--c-dot); }
.source i.ok { background: var(--c-green); }
.source i.warn { background: var(--c-amber); }
.source b { font-weight: 800; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.count { margin-left: auto; flex: none; color: var(--c-muted); }
.list { padding: 4px 16px 12px; }
.aisle { margin: 0; display: flex; align-items: center; gap: 8px; height: 34px; font-size: 12px; line-height: 16px; font-weight: 800; color: var(--c-muted); }
.rule { flex-grow: 1; height: 1px; background: var(--c-line-soft); }
.item { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 10px; align-items: center; min-height: 44px; padding: 2px 0; cursor: pointer; }
.what { display: flex; flex-direction: column; min-width: 0; }
.item input { appearance: none; width: 16px; height: 16px; margin: 0; border-radius: 5px; border: 1px solid var(--c-border); background: #fff; display: grid; place-items: center; cursor: pointer; }
.item input:checked { background: var(--c-green); border-color: var(--c-green); }
.item input:checked::after { content: ""; width: 7px; height: 4px; border: solid #fff; border-width: 0 0 2px 2px; transform: rotate(-45deg) translate(1px, -1px); }
.p { font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s { font-size: 12px; line-height: 16px; color: var(--c-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s.stale { color: var(--c-amber-text); }
.c { font-weight: 800; }
.item:has(input:checked) .p { color: var(--c-muted); text-decoration: line-through; }
.unmapped { margin: 0; font-size: 12px; line-height: 16px; color: var(--c-muted); }
</style>
