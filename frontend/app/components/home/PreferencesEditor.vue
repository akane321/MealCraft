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
        <label>Flavour {{ index + 1 }}
          <select v-model="boost.flavor" :aria-label="`Flavour ${index + 1}`"><option v-for="flavor in flavors" :key="flavor" :value="flavor">{{ titleCase(flavor) }}</option></select>
        </label>
        <label>Days for flavour {{ index + 1 }}
          <select v-model="boost.weekdays" :aria-label="`Days for flavour ${index + 1}`" multiple size="3"><option v-for="day in days" :key="day" :value="day">{{ titleCase(day) }}</option></select>
        </label>
        <label>Meals for flavour {{ index + 1 }}
          <select v-model="boost.meal_types" :aria-label="`Meals for flavour ${index + 1}`" multiple size="3"><option v-for="meal in meals" :key="meal" :value="meal">{{ titleCase(meal) }}</option></select>
        </label>
        <button type="button" class="mc-btn secondary sm" :aria-label="`Remove flavour ${index + 1}`" @click="draft.flavor_boosts.splice(index, 1)">Remove</button>
      </div>
      <p class="mc-small">No day or meal selected means all. Hold Ctrl to select several or deselect an option.</p>
      <button type="button" class="mc-btn secondary sm" :disabled="draft.flavor_boosts.length >= 20" @click="draft.flavor_boosts.push({ flavor: 'fragrant', weekdays: [], meal_types: [] })">Add flavour</button>
    </fieldset>
    <div class="options">
      <button type="submit" class="mc-btn primary sm" :disabled="disabled">Save preferences</button>
      <button type="button" class="mc-btn secondary sm" :disabled="disabled" @click="emit('cancel')">Cancel</button>
    </div>
  </form>
</template>

<style scoped>
.preference-editor { display: grid; gap: 12px; margin-top: 12px; }
fieldset { border: 1px solid #deded5; border-radius: 8px; padding: 12px; }
legend { font-weight: 600; padding: 0 4px; }
fieldset > label { display: inline-flex; align-items: center; gap: 5px; margin: 4px 12px 4px 0; }
.flavor-row { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin-bottom: 12px; }
.flavor-row label { display: grid; gap: 5px; font-size: .85rem; }
select { padding: 5px; border: 1px solid #deded5; border-radius: 4px; background: white; font: inherit; }
</style>
