<script setup lang="ts">
import { RETAILER_SHORT, basicsNote, formatSgd, groceryPriceLabel, groceryPriceTimes, groceryTrips, hasOtherStore, isSavedPrice, lineRetailer, packageLabel, priceSourceLabel, priceTone } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";

const props = defineProps<{ estimate: WeeklyGroceryEstimate }>();

const sumOf = (lines: GroceryLineEstimate[]) => lines.reduce((total, line) => total + line.purchase_cost_sgd, 0);
// A plan longer than a week has two trips, each with its own aisles; otherwise one list as before.
const trips = computed(() => groceryTrips(props.estimate.items).map(trip => ({
  ...trip,
  groups: trip.groups.map(group => ({ ...group, sum: sumOf(group.lines) })),
  stores: trip.stores.map(store => ({ ...store, groups: store.groups.map(group => ({ ...group, sum: sumOf(group.lines) })), sum: sumOf(store.groups.flatMap(group => group.lines)) })),
  sum: sumOf(trip.groups.flatMap(group => group.lines)),
})));
const groups = computed(() => trips.value.flatMap(trip => trip.groups));
// Stores are shown apart (FairPrice, Cold Storage, RedMart) only once some line is bought away from FairPrice.
const byStore = computed(() => hasOtherStore(props.estimate.items));
// A line of the second trip is its own purchase, even of an ingredient the first trip also buys; so is one of each store.
const lineKey = (line: GroceryLineEstimate) => `${line.shopping_trip ?? 1}:${lineRetailer(line)}:${line.ingredient_name}`;
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
        <template v-for="store in trip.stores" :key="store.retailer">
          <h3 v-if="byStore" class="store">{{ store.name }}<span class="mc-num">{{ formatSgd(store.sum) }}</span></h3>
          <template v-for="group in store.groups" :key="group.name">
            <h3 class="aisle">{{ group.name }}<span class="rule" /><span class="mc-num">{{ formatSgd(group.sum) }}</span></h3>
            <label v-for="line in group.lines" :key="lineKey(line)" class="item">
              <input type="checkbox" :checked="got.has(lineKey(line))" @change="toggle(lineKey(line))">
              <span class="what">
                <span class="p-line">
                  <span class="p">{{ line.ingredient_display_name }}</span>
                  <span v-if="line.perishable" class="fresh" title="Fresh: cooked within 3 days of this shop">Use within 3 days</span>
                  <span v-if="line.product?.halal_certified" class="fresh" title="FairPrice lists this product as Halal">Halal-certified</span>
                  <a v-if="store.retailer !== 'fairprice' && line.product?.product_url" class="shop-link" :href="line.product.product_url" target="_blank" rel="noopener" @click.stop>View at {{ store.retailer === 'other' ? 'the shop' : RETAILER_SHORT[store.retailer] }}</a>
                </span>
                <span class="s" :class="{ stale: isSavedPrice(line) }">{{ packageLabel(line) }} · <span :title="groceryPriceTimes(line)">{{ groceryPriceLabel(line) }}</span></span>
              </span>
              <span class="c mc-num">{{ formatSgd(line.purchase_cost_sgd) }}</span>
            </label>
          </template>
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
.source { position: sticky; top: 0; z-index: 1; margin: 0; display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--c-line-soft); background: #fff; color: #52525b; font-size: 12.5px; line-height: 16px; }
.source i { width: 8px; height: 8px; flex: none; border-radius: 50%; background: var(--c-dot); }
.source i.ok { background: var(--c-green); }
.source i.warn { background: var(--c-amber); }
.source b { min-width: 0; overflow: hidden; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.list { padding: 4px 16px 12px; }
.aisle { margin: 0; display: flex; align-items: center; gap: 8px; height: 34px; color: #9a9aa3; font-size: 11px; line-height: 16px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; }
.aisle .mc-num { color: #a1a1aa; font-size: 12px; font-weight: 400; letter-spacing: 0; }
.rule { flex-grow: 1; height: 1px; background: var(--c-line-soft); }
.item { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 10px; align-items: center; min-height: 44px; padding: 2px 0; cursor: pointer; }
.what { display: flex; flex-direction: column; min-width: 0; }
.p-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
.p { min-width: 0; color: #18181b; font-size: 14px; line-height: 20px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fresh { flex: none; padding: 0 6px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 11px; line-height: 16px; font-weight: 500; }
.store { margin: 12px 0 0; display: flex; align-items: baseline; justify-content: space-between; color: #0f0f12; font-size: 14px; line-height: 20px; font-weight: 600; }
.store .mc-num { font-size: 13px; font-weight: 600; }
.shop-link { flex: none; color: #7c3aed; font-size: 12px; line-height: 16px; font-weight: 500; text-decoration: none; }
.shop-link:hover { text-decoration: underline; text-underline-offset: 2px; }
.trip { margin: 12px 0 0; display: flex; align-items: baseline; justify-content: space-between; color: #0f0f12; font-size: 14px; line-height: 20px; font-weight: 600; }
.trip .mc-num { font-size: 13px; font-weight: 600; }
.s { color: #71717a; font-size: 12px; line-height: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.s.stale { color: var(--c-amber-text); font-weight: 400; }
.c { color: #18181b; font-weight: 500; font-variant-numeric: tabular-nums; }
.item:has(input:checked) .p { color: #a1a1aa; text-decoration: line-through; }
.unmapped { margin: 0; color: #71717a; font-size: 12px; line-height: 16px; }
.basics { margin: 12px 0 0; padding: 8px 10px; border: 1px solid #d1e9ff; border-radius: 10px; background: var(--c-info-bg); color: var(--c-info-text); font-size: 12px; line-height: 16px; }
</style>
