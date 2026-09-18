<script setup lang="ts">
import { formatSgd, groceryGroups, packageLabel, priceSourceLabel } from "~/lib/home-surface";
import type { WeeklyGroceryEstimate } from "~/types/meal-plan";

const props = defineProps<{
  estimate: WeeklyGroceryEstimate;
  rangeLabel: string;
  householdSize: number;
}>();

const groups = computed(() => groceryGroups(props.estimate.items));
</script>

<template>
  <article class="sheet">
    <header>
      <p>MealCraft · {{ rangeLabel }} · {{ householdSize }} {{ householdSize === 1 ? "person" : "people" }}</p>
      <h2>Shopping list</h2>
    </header>

    <section v-for="group in groups" :key="group.name">
      <h3>{{ group.name }}</h3>
      <ul>
        <li v-for="line in group.lines" :key="line.ingredient_name">
          <span class="box" aria-hidden="true" />
          <span class="name">
            {{ line.ingredient_display_name }}
            <small v-if="line.pantry_deduction > 0">uses {{ line.pantry_deduction }}{{ line.unit ? ` ${line.unit}` : "" }} from home</small>
            <small v-if="line.note">{{ line.note }}</small>
          </span>
          <span class="pack">{{ packageLabel(line) }}</span>
          <span class="price">{{ formatSgd(line.purchase_cost_sgd) }}</span>
        </li>
      </ul>
    </section>

    <section v-if="estimate.unmapped_ingredients.length">
      <h3>Also needed, not priced</h3>
      <p class="unpriced">{{ estimate.unmapped_ingredients.join(", ") }}</p>
    </section>

    <footer>
      <p class="sum"><span>Estimated total</span><strong>{{ formatSgd(estimate.purchase_total_sgd) }}</strong></p>
      <p>{{ priceSourceLabel(estimate) }}. Prices can change at the store. Check allergens on product labels.</p>
    </footer>
  </article>
</template>

<style scoped>
.sheet { box-sizing: border-box; width: 100%; padding: 40px 44px; background: #fbf8f2; color: #1d1b16; font-family: Figtree, system-ui, sans-serif; }
header p { margin: 0; font-size: 12px; color: #5e574b; }
h2 { margin: 4px 0 20px; font-family: Fraunces, Georgia, serif; font-size: 32px; font-weight: 400; }
h3 { margin: 18px 0 4px; font-size: 11px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: #5e574b; }
ul { list-style: none; margin: 0; padding: 0; }
li { display: flex; align-items: center; gap: 12px; min-height: 34px; border-top: 1px solid #e7dfd0; font-size: 14px; break-inside: avoid; }
.box { width: 13px; height: 13px; flex-shrink: 0; border: 1.5px solid #5e574b; border-radius: 3px; }
.name { flex-grow: 1; display: flex; flex-direction: column; }
.name small { font-size: 11px; color: #5e574b; }
.pack { color: #5e574b; font-size: 13px; }
.price { width: 70px; text-align: right; font-weight: 600; }
.unpriced { margin: 6px 0 0; font-size: 13px; }
footer { margin-top: 24px; padding-top: 12px; border-top: 1.5px solid #1d1b16; font-size: 12px; color: #5e574b; }
footer p { margin: 4px 0; }
.sum { display: flex; justify-content: space-between; align-items: baseline; color: #1d1b16; font-size: 14px; }
.sum strong { font-family: Fraunces, Georgia, serif; font-size: 24px; font-weight: 400; }
</style>
