<script setup lang="ts">
import { copyPlanningPreferences } from "~/lib/planning-preferences";
import type { PlanningPreferencesView } from "~/lib/planning-preferences";

const props = defineProps<{ value: PlanningPreferencesView; disabled: boolean }>();
const emit = defineEmits<{ save: [value: PlanningPreferencesView]; cancel: [] }>();
const draft = reactive(copyPlanningPreferences(props.value));
const meals = ["breakfast", "lunch", "dinner", "snack"] as const;
const days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const flavors = ["fragrant", "spicy", "light", "rich"];
const titleCase = (value: string) => value[0]!.toUpperCase() + value.slice(1);
</script>

<template>
  <form class="preference-editor" aria-label="Edit meal preferences" @submit.prevent="emit('save', copyPlanningPreferences(draft))">
    <p class="mc-small">These are preferences, not changes to allergies, dietary restrictions or your budget.</p>
    <fieldset :disabled="disabled">
      <legend>Soft goals</legend>
      <label><input v-model="draft.more_vegetables" type="checkbox"> More vegetables</label>
      <label><input v-model="draft.lighter" type="checkbox"> Lighter meals</label>
    </fieldset>
    <fieldset :disabled="disabled">
      <legend>Meals that may repeat</legend>
      <label v-for="meal in meals" :key="meal"><input v-model="draft.repeat_allowed_meals" type="checkbox" :value="meal"> {{ titleCase(meal) }}</label>
      <p class="mc-small">An explicit hard no-repeat limit still applies.</p>
    </fieldset>
    <fieldset :disabled="disabled">
      <legend>Flavour preferences</legend>
      <div v-for="(boost, index) in draft.flavor_boosts" :key="index" class="flavor-row">
        <label class="flavor">Flavour {{ index + 1 }}
          <select v-model="boost.flavor" :aria-label="`Flavour ${index + 1}`"><option v-for="flavor in flavors" :key="flavor" :value="flavor">{{ titleCase(flavor) }}</option></select>
        </label>
        <!-- Days and meals as toggle chips: one click each, no Ctrl. -->
        <div class="picks" role="group" :aria-label="`Days for flavour ${index + 1}`">
          <span class="picks-title" aria-hidden="true">Days</span>
          <label v-for="day in days" :key="day" class="pick"><input v-model="boost.weekdays" type="checkbox" :value="day">{{ titleCase(day).slice(0, 3) }}</label>
        </div>
        <div class="picks" role="group" :aria-label="`Meals for flavour ${index + 1}`">
          <span class="picks-title" aria-hidden="true">Meals</span>
          <label v-for="meal in meals" :key="meal" class="pick"><input v-model="boost.meal_types" type="checkbox" :value="meal">{{ titleCase(meal) }}</label>
        </div>
        <button type="button" class="mc-btn quiet sm remove" :aria-label="`Remove flavour ${index + 1}`" @click="draft.flavor_boosts.splice(index, 1)">Remove</button>
      </div>
      <p class="mc-small">No day or meal selected means all.</p>
      <button type="button" class="mc-btn secondary sm" :disabled="draft.flavor_boosts.length >= 20" @click="draft.flavor_boosts.push({ flavor: 'fragrant', weekdays: [], meal_types: [] })">Add flavour</button>
    </fieldset>
    <div class="options">
      <button type="submit" class="mc-btn primary sm" :disabled="disabled">Save preferences</button>
      <button type="button" class="mc-btn secondary sm" :disabled="disabled" @click="emit('cancel')">Cancel</button>
    </div>
  </form>
</template>

<style scoped>
.preference-editor { display: grid; gap: 12px; margin-top: 4px; }
fieldset { min-width: 0; margin: 0; padding: 12px 16px 14px; border: 1px solid #ececef; border-radius: 12px; background: #fff; }
/* The legend is the card's title, inside it rather than on its border. */
legend { float: left; width: 100%; margin: 0 0 6px; padding: 0; color: #0f0f12; font-size: 13px; line-height: 18px; font-weight: 600; }
legend + * { clear: both; }
fieldset > label { display: inline-flex; align-items: center; gap: 8px; margin: 4px 16px 4px 0; color: #27272a; font-size: 14px; }
fieldset .mc-small { margin: 6px 0 0; font-size: 12px; line-height: 16px; }
.flavor-row { display: grid; gap: 10px; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #f0f0f2; }
.flavor { display: flex; align-items: center; gap: 10px; color: #27272a; font-size: 13px; font-weight: 500; white-space: nowrap; }
.picks { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.picks-title { width: 52px; color: #71717a; font-size: 12px; font-weight: 500; }
/* The checkbox covers its chip, invisible: a click anywhere on the chip toggles it. */
.pick > input[type="checkbox"] { position: absolute; inset: 0; width: 100%; height: 100%; margin: 0; border: 0; border-radius: 999px; opacity: 0; cursor: pointer; }
.pick { position: relative; height: 28px; display: inline-flex; align-items: center; padding: 0 10px; border: 1px solid #e8e8eb; border-radius: 999px; background: #fff; color: #3f3f46; font-size: 12.5px; font-weight: 500; cursor: pointer; }
.pick:hover { background: #f7f7f8; }
.pick:has(input:checked) { border-color: #c4b5fd; background: #f5f3ff; color: #6d28d9; }
.pick:has(input:focus-visible) { outline: 2px solid rgba(139, 92, 246, 0.55); outline-offset: 2px; }
.flavor-row > .remove { justify-self: start; height: 28px; margin-left: 52px; padding: 0 8px; border-radius: 8px; color: #71717a; }
select { appearance: none; width: 160px; height: 32px; padding: 0 30px 0 12px; border: 1px solid #e4e4e7; border-radius: 10px; background: #fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2371717a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E") no-repeat right 10px center / 14px; color: #18181b; font: inherit; font-size: 13px; cursor: pointer; }
select:focus-visible { outline: 0; border-color: #8b5cf6; box-shadow: 0 0 0 3px #ede9fe; }
fieldset:disabled { opacity: 0.6; }
</style>
