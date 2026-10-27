<script setup lang="ts">
import { basicsNote, formatSgd, groceryPriceLabel, groceryPriceTimes, groceryTrips, isSavedPrice, packageLabel, priceSourceLabel, priceTone } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";

const props = defineProps<{ estimate: WeeklyGroceryEstimate }>();

const sumOf = (lines: GroceryLineEstimate[]) => lines.reduce((total, line) => total + line.purchase_cost_sgd, 0);
// A plan longer than a week has two trips, each with its own aisles; otherwise one list as before.
const trips = computed(() => groceryTrips(props.estimate.items).map(trip => ({
  ...trip,
  groups: trip.groups.map(group => ({ ...group, sum: sumOf(group.lines) })),
  sum: sumOf(trip.groups.flatMap(group => group.lines)),
})));
const groups = computed(() => trips.value.flatMap(trip => trip.groups));
// A line of the second trip is its own purchase, even of an ingredient the first trip also buys.
const lineKey = (line: GroceryLineEstimate) => `${line.shopping_trip ?? 1}:${line.ingredient_name}`;
// The note counts live, saved and sample prices; its dot and the amber "Saved FairPrice price" lines read them the same way.
const source = computed(() => priceSourceLabel(props.estimate));
const basics = computed(() => basicsNote(props.estimate));
const sourceTone = computed(() => priceTone(props.estimate));
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
      <b :title="source">{{ source }}</b>
    </p>
    <div class="list">
      <template v-for="trip in trips" :key="trip.trip ?? 0">
        <h3 v-if="trip.label" class="trip">{{ trip.label }}<span class="mc-num">{{ formatSgd(trip.sum) }}</span></h3>
        <template v-for="group in trip.groups" :key="group.name">
          <h3 class="aisle">{{ group.name }}<span class="rule" /><span class="mc-num">{{ formatSgd(group.sum) }}</span></h3>
          <label v-for="line in group.lines" :key="lineKey(line)" class="item">
            <input type="checkbox" :checked="got.has(lineKey(line))" @change="toggle(lineKey(line))">
            <span class="what">
              <span class="p-line">
                <span class="p">{{ line.ingredient_display_name }}</span>
                <span v-if="line.perishable" class="fresh" title="Fresh: cooked within 3 days of this shop">Use within 3 days</span>
              </span>
              <span class="s" :class="{ stale: isSavedPrice(line) }">{{ packageLabel(line) }} · <span :title="groceryPriceTimes(line)">{{ groceryPriceLabel(line) }}</span></span>
            </span>
            <span class="c mc-num">{{ formatSgd(line.purchase_cost_sgd) }}</span>
          </label>
        </template>
      </template>
      <template v-if="estimate.unmapped_ingredients.length">
        <h3 class="aisle">No price found<span class="rule" /></h3>
        <p class="unmapped">{{ estimate.unmapped_ingredients.join(", ") }}</p>
      </template>
      <p v-if="!groups.length && !estimate.unmapped_ingredients.length" class="unmapped">Everything in this plan is already at home.</p>
      <p v-if="basics" class="basics">{{ basics }}</p>
    </div>
  </div>
</template>

<style scoped>
.source { position: sticky; top: 0; z-index: 1; margin: 0; display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--c-line-soft); background: #fff; font-size: 12px; line-height: 16px; }
.source i { width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--c-dot); }
.source i.ok { background: var(--c-green); }
.source i.warn { background: var(--c-amber); }
.source b { font-weight: 800; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.list { padding: 4px 16px 12px; }
.aisle { margin: 0; display: flex; align-items: center; gap: 8px; height: 34px; font-size: 12px; line-height: 16px; font-weight: 800; color: var(--c-muted); }
.rule { flex-grow: 1; height: 1px; background: var(--c-line-soft); }
.item { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 10px; align-items: center; min-height: 44px; padding: 2px 0; cursor: pointer; }
.what { display: flex; flex-direction: column; min-width: 0; }
.item input { appearance: none; width: 16px; height: 16px; margin: 0; border-radius: 5px; border: 1px solid var(--c-border); background: #fff; display: grid; place-items: center; cursor: pointer; }
.item input:checked { background: var(--c-green); border-color: var(--c-green); }
.item input:checked::after { content: ""; width: 7px; height: 4px; border: solid #fff; border-width: 0 0 2px 2px; transform: rotate(-45deg) translate(1px, -1px); }
.p-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
.p { min-width: 0; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fresh { flex: none; padding: 0 6px; border-radius: 999px; background: var(--c-info-bg); color: var(--c-info-text); font-size: 11px; line-height: 16px; font-weight: 700; }
.trip { margin: 10px 0 0; display: flex; align-items: center; justify-content: space-between; font-size: 13px; line-height: 18px; font-weight: 800; color: var(--c-ink); }
.s { font-size: 12px; line-height: 16px; color: var(--c-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s.stale { color: var(--c-amber-text); }
.c { font-weight: 800; }
.item:has(input:checked) .p { color: var(--c-muted); text-decoration: line-through; }
.unmapped { margin: 0; font-size: 12px; line-height: 16px; color: var(--c-muted); }
.basics { margin: 12px 0 0; padding: 8px 10px; border-radius: 10px; background: var(--c-info-bg); color: var(--c-info-text); font-size: 12px; line-height: 16px; }
</style>
