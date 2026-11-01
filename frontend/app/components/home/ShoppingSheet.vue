<script setup lang="ts">
import { basicsNote, formatSgd, groceryPriceLabel, groceryTrips, hasColdStorage, lineRetailer, packageLabel, priceSourceLabel } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";

const props = defineProps<{
  estimate: WeeklyGroceryEstimate;
  rangeLabel: string;
  householdSize: number;
}>();

const trips = computed(() => groceryTrips(props.estimate.items));
// Store sections (FairPrice, then Cold Storage) only once some line is bought at Cold Storage.
const byStore = computed(() => hasColdStorage(props.estimate.items));
const storeSum = (lines: GroceryLineEstimate[]) => lines.reduce((total, line) => total + line.purchase_cost_sgd, 0);
const basics = computed(() => basicsNote(props.estimate));
</script>

<template>
  <article class="sheet">
    <header>
      <p>MealCraft · {{ rangeLabel }} · {{ householdSize }} {{ householdSize === 1 ? "person" : "people" }}</p>
      <h2>Shopping list</h2>
    </header>

    <template v-for="trip in trips" :key="trip.trip ?? 0">
      <h2 v-if="trip.label" class="trip">{{ trip.label }}</h2>
      <template v-for="store in trip.stores" :key="store.retailer">
        <h2 v-if="byStore" class="store">{{ store.name }}<span>{{ formatSgd(storeSum(store.groups.flatMap(group => group.lines))) }}</span></h2>
        <section v-for="group in store.groups" :key="group.name">
          <h3>{{ group.name }}</h3>
          <ul>
            <li v-for="line in group.lines" :key="`${lineRetailer(line)}:${line.ingredient_name}`">
              <span class="box" aria-hidden="true" />
              <span class="name">
                {{ line.ingredient_display_name }}
                <small v-if="line.pantry_deduction > 0">uses {{ line.pantry_deduction }}{{ line.unit ? ` ${line.unit}` : "" }} from home</small>
                <small v-if="line.note">{{ line.note }}</small>
                <small v-if="line.perishable">Use within 3 days of this shop</small>
                <small v-if="line.product?.halal_certified">Halal-certified</small>
                <small>{{ groceryPriceLabel(line) }}</small>
                <small v-if="store.retailer === 'cold_storage' && line.product?.product_url"><a :href="line.product.product_url">{{ line.product.product_url }}</a></small>
              </span>
              <span class="pack">{{ packageLabel(line) }}</span>
              <span class="price">{{ formatSgd(line.purchase_cost_sgd) }}</span>
            </li>
          </ul>
        </section>
      </template>
    </template>

    <section v-if="estimate.unmapped_ingredients.length">
      <h3>Also needed, not priced</h3>
      <p class="unpriced">{{ estimate.unmapped_ingredients.join(", ") }}</p>
    </section>

    <footer>
      <p class="sum"><span>Estimated total</span><strong>{{ formatSgd(estimate.purchase_total_sgd) }}</strong></p>
      <p v-if="basics">{{ basics }}</p>
      <p>{{ priceSourceLabel(estimate) }}. Prices can change at the store. Check allergens on product labels.</p>
    </footer>
  </article>
</template>

<style scoped>
.sheet { box-sizing: border-box; width: 100%; padding: 40px 44px; background: #fbf8f2; color: #1d1b16; font-family: Nunito, system-ui, sans-serif; }
header p { margin: 0; font-size: 12px; color: #5e574b; }
h2 { margin: 4px 0 20px; font-family: "Bricolage Grotesque", system-ui, sans-serif; font-size: 32px; font-weight: 700; }
h2.trip { margin: 24px 0 0; font-size: 20px; }
h2.store { margin: 18px 0 0; display: flex; justify-content: space-between; font-size: 16px; }
.name a { color: inherit; }
h3 { margin: 18px 0 4px; font-size: 12px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: #5e574b; }
ul { list-style: none; margin: 0; padding: 0; }
li { display: flex; align-items: center; gap: 12px; min-height: 34px; border-top: 1px solid #e7dfd0; font-size: 14px; break-inside: avoid; }
.box { width: 13px; height: 13px; flex-shrink: 0; border: 1.5px solid #5e574b; border-radius: 3px; }
.name { flex-grow: 1; display: flex; flex-direction: column; }
.name small { font-size: 12px; color: #5e574b; }
.pack { color: #5e574b; font-size: 13px; }
.price { width: 70px; text-align: right; font-weight: 600; }
.unpriced { margin: 6px 0 0; font-size: 13px; }
footer { margin-top: 24px; padding-top: 12px; border-top: 1.5px solid #1d1b16; font-size: 12px; color: #5e574b; }
footer p { margin: 4px 0; }
.sum { display: flex; justify-content: space-between; align-items: baseline; color: #1d1b16; font-size: 14px; }
.sum strong { font-family: "Bricolage Grotesque", system-ui, sans-serif; font-size: 24px; font-weight: 700; }
@media print {
  section { break-inside: avoid; }
  h3 { break-after: avoid; }
  footer { break-inside: avoid; }
}
</style>
