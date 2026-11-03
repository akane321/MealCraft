<script setup lang="ts">
import { RETAILER_SHORT, basicsNote, formatSgd, groceryPriceLabel, groceryTrips, hasOtherStore, lineRetailer, packageLabel, priceSourceLabel } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";
import type { GroceryLineEstimate } from "~/types/recommendation";

const props = defineProps<{
  estimate: WeeklyGroceryEstimate;
  rangeLabel: string;
  householdSize: number;
}>();
// The close button is for the on-screen preview only; print hides it.
const emit = defineEmits<{ close: [] }>();

const trips = computed(() => groceryTrips(props.estimate.items));
// Store sections (FairPrice, Cold Storage, RedMart) only once some line is bought away from FairPrice.
const byStore = computed(() => hasOtherStore(props.estimate.items));
const storeSum = (lines: GroceryLineEstimate[]) => lines.reduce((total, line) => total + line.purchase_cost_sgd, 0);
const basics = computed(() => basicsNote(props.estimate));
</script>

<template>
  <article class="sheet">
    <header>
      <div>
        <h2>Shopping list</h2>
        <p>MealCraft · {{ rangeLabel }} · {{ householdSize }} {{ householdSize === 1 ? "person" : "people" }}</p>
      </div>
      <button type="button" class="mc-close" aria-label="Close shopping list" @click="emit('close')"><UIcon name="i-lucide-x" aria-hidden="true" /></button>
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
                <!-- On screen a short link; on paper the address itself, so it can be typed in. -->
                <small v-if="store.retailer !== 'fairprice' && line.product?.product_url">
                  <a class="on-screen" :href="line.product.product_url">View at {{ store.retailer === "other" ? "the shop" : RETAILER_SHORT[store.retailer] }}<UIcon name="i-lucide-arrow-up-right" aria-hidden="true" /></a>
                  <span class="on-paper">{{ line.product.product_url }}</span>
                </small>
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
/* On paper the line sits above the title. */
header > div { display: flex; flex-direction: column-reverse; }
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
/* On screen the sheet is a plain white panel; print keeps the paper look above. */
@media screen {
  .sheet { padding: 0 28px 24px; background: #fff; color: #27272a; font-family: var(--sans); }
  /* The sheets' one header: title, a muted line, the close button at the right; it stays while the list scrolls. */
  header { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 12px; min-height: 64px; margin: 0 -28px 8px; padding: 12px 16px 12px 28px; border-bottom: 1px solid #f0f0f2; background: #fff; }
  header > div { display: block; flex: 1; min-width: 0; }
  header p { margin: 2px 0 0; color: #71717a; font-size: 13px; line-height: 18px; }
  header h2 { margin: 0; font-size: 18px; line-height: 24px; letter-spacing: -0.01em; }
  .on-screen { display: inline-flex; align-items: center; gap: 2px; }
  .on-screen .iconify { width: 12px; height: 12px; }
  .on-paper { display: none; }
  h2 { margin: 2px 0 12px; color: #0f0f12; font-family: var(--sans); font-size: 20px; line-height: 28px; font-weight: 600; letter-spacing: -0.015em; }
  h2.trip { margin: 20px 0 0; font-size: 16px; line-height: 22px; }
  h3 { margin: 18px 0 4px; color: #9a9aa3; font-size: 11px; line-height: 16px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; }
  /* A store is a heading with its total; a rule above each store after the first. */
  h2.store { margin: 16px 0 0; padding-top: 0; color: #0f0f12; font-size: 14px; line-height: 20px; font-weight: 600; letter-spacing: 0; }
  h2.store span { font-variant-numeric: tabular-nums; }
  h2.store ~ h2.store { padding-top: 16px; border-top: 1px solid #ececef; }
  li { min-height: 40px; border-top: 1px solid #f2f2f4; font-size: 14px; line-height: 20px; }
  .box { width: 14px; height: 14px; border: 1px solid #d4d4d8; border-radius: 4px; }
  .name { color: #18181b; font-weight: 500; }
  .name small, .pack { color: #71717a; font-size: 12px; font-weight: 400; }
  .name a { color: #6d28d9; text-decoration: none; }
  .price { color: #18181b; font-weight: 500; font-variant-numeric: tabular-nums; }
  .unpriced { color: #52525b; }
  footer { margin-top: 20px; padding-top: 12px; border-top: 1px solid #ececef; color: #71717a; }
  .sum { color: #18181b; }
  .sum strong { font-family: var(--sans); font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
}
@media print {
  .mc-close, .on-screen { display: none !important; }
  section { break-inside: avoid; }
  h3 { break-after: avoid; }
  footer { break-inside: avoid; }
}
</style>
