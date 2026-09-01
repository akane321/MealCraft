<script setup lang="ts">
import { todayIsoDate } from "~/lib/meal-plan-format";
import { summarizeHouseholdMembers } from "~/lib/household-profile";
import {
  cleanAvailableIngredients,
  parseExcludedIngredients,
  toOptionalNumber,
} from "~/lib/recommendation-form";
import type { HouseholdMemberInput, HouseholdProfileInput } from "~/types/household";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  PricingMode,
} from "~/types/recommendation";

useHead({ title: "Household profile · MealCraft" });

interface MemberForm {
  name: string;
  servingsPerMeal: number;
  allergens: string[];
  excludedIngredients: string;
  dietaryPreferences: DietaryPreference[];
}

const allergenOptions = ["peanut", "soy", "gluten", "sesame", "dairy", "egg", "shellfish"];
const dietaryOptions: { label: string; value: DietaryPreference }[] = [
  { label: "Vegetarian", value: "vegetarian" },
  { label: "Vegan", value: "vegan" },
  { label: "Gluten-free", value: "gluten-free" },
  { label: "Dairy-free", value: "dairy-free" },
];
const healthOptions: { label: string; value: HealthPreference }[] = [
  { label: "Lower sodium", value: "low-sodium" },
  { label: "Lower sugar", value: "low-sugar" },
  { label: "Lower calorie", value: "lower-calorie" },
];

const form = reactive({
  name: "My household",
  maxCookingTimeMinutes: 60,
  budgetPerMealSgd: null as number | null,
  weeklyBudgetSgd: 60 as number | null,
  healthPreferences: ["low-sodium"] as HealthPreference[],
  calorieTarget: 550 as number | null,
  proteinTarget: 35 as number | null,
  carbohydrateTarget: null as number | null,
  fatTarget: null as number | null,
  maxSodiumMgPerMeal: null as number | null,
  pricingMode: "fixture" as PricingMode,
  planningStartDate: todayIsoDate(),
});
const members = ref<MemberForm[]>([
  {
    name: "Member 1",
    servingsPerMeal: 1,
    allergens: [],
    excludedIngredients: "",
    dietaryPreferences: [],
  },
]);
const pantryItems = ref<AvailableIngredientInput[]>([
  { normalized_name: "", quantity: null, unit: null },
]);
const saveNotice = ref<string | null>(null);

const {
  current,
  errorMessage,
  generatePlan,
  isLoading,
  isPlanning,
  isSaving,
  loadCurrent,
  planResult,
  replanLatest,
  save,
} = useHouseholdProfile();

const totalServings = computed(() => members.value.reduce((sum, member) => sum + member.servingsPerMeal, 0));
const draftSummary = computed(() => summarizeHouseholdMembers(members.value.map(memberPayload)));
const hasCurrentPlan = computed(() => current.value?.latest_plan_id !== null && current.value?.latest_plan_id !== undefined);

function hydrateFromCurrent() {
  if (!current.value) return;
  const profile = current.value;
  const version = profile.current;
  form.name = profile.name;
  form.maxCookingTimeMinutes = version.max_cooking_time_minutes;
  form.budgetPerMealSgd = version.budget_per_meal_sgd;
  form.weeklyBudgetSgd = version.weekly_budget_sgd;
  form.healthPreferences = [...version.health_preferences];
  form.calorieTarget = version.nutrition_targets.calories_kcal;
  form.proteinTarget = version.nutrition_targets.protein_g;
  form.carbohydrateTarget = version.nutrition_targets.carbohydrate_g;
  form.fatTarget = version.nutrition_targets.fat_g;
  form.maxSodiumMgPerMeal = version.max_sodium_mg_per_meal;
  form.pricingMode = version.pricing_mode;
  members.value = version.members.map(member => ({
    name: member.name,
    servingsPerMeal: member.servings_per_meal,
    allergens: [...member.allergens],
    excludedIngredients: member.excluded_ingredients.join(", "),
    dietaryPreferences: [...member.dietary_preferences],
  }));
  pantryItems.value = version.available_ingredients.length
    ? version.available_ingredients.map(item => ({ ...item }))
    : [{ normalized_name: "", quantity: null, unit: null }];
}

function addMember() {
  members.value.push({
    name: `Member ${members.value.length + 1}`,
    servingsPerMeal: 1,
    allergens: [],
    excludedIngredients: "",
    dietaryPreferences: [],
  });
}

function removeMember(index: number) {
  if (members.value.length > 1) members.value.splice(index, 1);
}

function addPantryItem() {
  pantryItems.value.push({ normalized_name: "", quantity: null, unit: null });
}

function removePantryItem(index: number) {
  pantryItems.value.splice(index, 1);
}

function memberPayload(member: MemberForm): HouseholdMemberInput {
  return {
    name: member.name,
    servings_per_meal: member.servingsPerMeal,
    allergens: member.allergens,
    excluded_ingredients: parseExcludedIngredients(member.excludedIngredients),
    dietary_preferences: member.dietaryPreferences,
  };
}

function buildPayload(): HouseholdProfileInput {
  return {
    name: form.name,
    members: members.value.map(memberPayload),
    max_cooking_time_minutes: form.maxCookingTimeMinutes,
    budget_per_meal_sgd: toOptionalNumber(form.budgetPerMealSgd),
    weekly_budget_sgd: toOptionalNumber(form.weeklyBudgetSgd),
    health_preferences: form.healthPreferences,
    nutrition_targets: {
      calories_kcal: toOptionalNumber(form.calorieTarget),
      protein_g: toOptionalNumber(form.proteinTarget),
      carbohydrate_g: toOptionalNumber(form.carbohydrateTarget),
      fat_g: toOptionalNumber(form.fatTarget),
    },
    max_sodium_mg_per_meal: toOptionalNumber(form.maxSodiumMgPerMeal),
    available_ingredients: cleanAvailableIngredients(pantryItems.value),
    pricing_mode: form.pricingMode,
  };
}

async function saveProfile() {
  saveNotice.value = null;
  const saved = await save(buildPayload());
  if (saved) {
    saveNotice.value = `Version ${saved.current_version} saved. Future plans can now use this profile.`;
    hydrateFromCurrent();
  }
}

async function generateFromProfile() {
  saveNotice.value = null;
  const generated = await generatePlan({ start_date: form.planningStartDate });
  if (generated) saveNotice.value = `Plan #${generated.plan.id} was generated from profile version ${generated.profile_version}.`;
}

async function rebuildLatestPlan() {
  saveNotice.value = null;
  const rebuilt = await replanLatest({ start_date: form.planningStartDate });
  if (rebuilt) saveNotice.value = `Plan #${rebuilt.plan.id} now replaces plan #${rebuilt.replaces_plan_id}.`;
}

onMounted(async () => {
  await loadCurrent();
  hydrateFromCurrent();
});
</script>

<template>
  <main class="page-width profile-page">
    <section class="profile-hero">
      <div>
        <p class="eyebrow">Persistent planning context</p>
        <h1>Define the household once. Keep every plan traceable.</h1>
      </div>
      <p>
        Member safety constraints are merged into one shared meal plan. Nutrition targets remain user-entered, non-medical planning inputs.
      </p>
    </section>

    <div v-if="isLoading" class="notice-panel">Loading the current household profile…</div>
    <div v-if="errorMessage" class="notice-panel error-notice">{{ errorMessage }}</div>
    <div v-if="saveNotice" class="notice-panel success-notice">{{ saveNotice }}</div>

    <form class="profile-layout" @submit.prevent="saveProfile">
      <section class="profile-main">
        <div class="profile-section-heading">
          <div>
            <p class="form-kicker">Household identity</p>
            <h2>{{ current ? `Editing version ${current.current_version}` : "Create the household profile" }}</h2>
          </div>
          <span v-if="current" class="version-badge">Profile #{{ current.id }} · v{{ current.current_version }}</span>
        </div>

        <label class="profile-name-field">
          <span>Profile name</span>
          <input v-model="form.name" type="text" maxlength="120" required>
        </label>

        <div class="profile-section-heading member-heading">
          <div>
            <p class="form-kicker">Members and hard constraints</p>
            <h2>{{ totalServings }} planned serving{{ totalServings === 1 ? "" : "s" }} per meal</h2>
          </div>
          <button class="secondary-button" type="button" :disabled="members.length >= 12" @click="addMember">+ Add member</button>
        </div>

        <div class="member-list">
          <article v-for="(member, index) in members" :key="index" class="member-card">
            <div class="member-card-header">
              <strong>Member {{ index + 1 }}</strong>
              <button type="button" class="text-button danger-text" :disabled="members.length === 1" @click="removeMember(index)">Remove</button>
            </div>
            <div class="member-core-fields">
              <label><span>Name</span><input v-model="member.name" type="text" maxlength="80" required></label>
              <label><span>Servings per meal</span><input v-model.number="member.servingsPerMeal" type="number" min="1" max="3" required></label>
            </div>
            <div class="member-constraint-group">
              <p>Allergens</p>
              <div class="choice-grid">
                <label v-for="allergen in allergenOptions" :key="allergen" class="choice-card">
                  <input v-model="member.allergens" type="checkbox" :value="allergen"><span>{{ allergen }}</span>
                </label>
              </div>
            </div>
            <div class="member-constraint-group">
              <p>Dietary requirements</p>
              <div class="choice-grid">
                <label v-for="option in dietaryOptions" :key="option.value" class="choice-card">
                  <input v-model="member.dietaryPreferences" type="checkbox" :value="option.value"><span>{{ option.label }}</span>
                </label>
              </div>
            </div>
            <label>
              <span>Prohibited ingredient IDs <small>comma-separated</small></span>
              <input v-model="member.excludedIngredients" type="text" placeholder="mushroom, yellow_onion">
            </label>
          </article>
        </div>

        <section class="profile-form-section">
          <p class="form-kicker">Shared planning defaults</p>
          <h2>Budget, time and user-entered targets</h2>
          <div class="profile-field-grid">
            <label><span>Maximum cooking time</span><input v-model.number="form.maxCookingTimeMinutes" type="number" min="5" max="240" required></label>
            <label><span>Per-meal budget</span><input v-model.number="form.budgetPerMealSgd" type="number" min="0.01" step="0.01" placeholder="Optional S$"></label>
            <label><span>Weekly budget</span><input v-model.number="form.weeklyBudgetSgd" type="number" min="0.01" step="0.01" placeholder="Optional S$"></label>
            <label>
              <span>Pricing source</span>
              <select v-model="form.pricingMode">
                <option value="fixture">Fixture · reproducible</option>
                <option value="live">Live · FairPrice</option>
              </select>
            </label>
            <label><span>Calories per meal</span><input v-model.number="form.calorieTarget" type="number" min="100" max="2500" placeholder="kcal"></label>
            <label><span>Protein per meal</span><input v-model.number="form.proteinTarget" type="number" min="0" max="300" placeholder="g"></label>
            <label><span>Carbohydrate per meal</span><input v-model.number="form.carbohydrateTarget" type="number" min="0" max="500" placeholder="g"></label>
            <label><span>Fat per meal</span><input v-model.number="form.fatTarget" type="number" min="0" max="200" placeholder="g"></label>
            <label><span>Sodium target per meal</span><input v-model.number="form.maxSodiumMgPerMeal" type="number" min="100" max="5000" placeholder="Optional mg"></label>
          </div>
          <p class="field-help">MealCraft applies only targets entered here. It does not calculate BMR/TDEE or prescribe medical diets.</p>
          <div class="member-constraint-group">
            <p>General health preferences</p>
            <div class="choice-grid">
              <label v-for="option in healthOptions" :key="option.value" class="choice-card">
                <input v-model="form.healthPreferences" type="checkbox" :value="option.value"><span>{{ option.label }}</span>
              </label>
            </div>
          </div>
        </section>

        <section class="profile-form-section">
          <div class="profile-section-heading compact-heading">
            <div><p class="form-kicker">Available ingredients</p><h2>Optional pantry preference</h2></div>
            <button class="secondary-button" type="button" @click="addPantryItem">+ Add ingredient</button>
          </div>
          <p class="field-help">Known quantities reduce the shopping requirement. Unknown quantities only improve recipe ranking.</p>
          <div class="weekly-pantry-list">
            <div v-for="(item, index) in pantryItems" :key="index" class="weekly-pantry-row">
              <input v-model="item.normalized_name" type="text" aria-label="Standard ingredient ID" placeholder="brown_rice">
              <input v-model.number="item.quantity" type="number" min="0.01" step="0.01" aria-label="Available quantity" placeholder="Unknown">
              <input v-model="item.unit" type="text" :required="item.quantity !== null" aria-label="Available unit" placeholder="g">
              <button type="button" class="remove-button" :aria-label="`Remove pantry item ${index + 1}`" @click="removePantryItem(index)">×</button>
            </div>
          </div>
        </section>

        <button class="primary-button profile-save-button" type="submit" :disabled="isSaving || totalServings > 12">
          {{ isSaving ? "Saving a new version…" : current ? "Save as new version" : "Create household profile" }}
        </button>
        <p v-if="totalServings > 12" class="inline-error">The deterministic planner currently supports at most 12 servings.</p>
      </section>

      <aside class="profile-sidebar">
        <section class="profile-summary-card">
          <p class="form-kicker">Effective shared constraints</p>
          <h2>{{ current ? `${current.current.planning_household_size} servings` : `${totalServings} servings` }}</h2>
          <p>Any member allergen, prohibited ingredient or dietary requirement applies to the complete shared plan.</p>
          <dl v-if="current" class="profile-summary-list">
            <div><dt>Allergens</dt><dd>{{ current.current.allergens.join(", ") || "None" }}</dd></div>
            <div><dt>Excluded</dt><dd>{{ current.current.excluded_ingredients.join(", ") || "None" }}</dd></div>
            <div><dt>Dietary</dt><dd>{{ current.current.dietary_preferences.join(", ") || "None" }}</dd></div>
            <div><dt>Latest plan</dt><dd>{{ current.latest_plan_id ? `#${current.latest_plan_id}` : "Not generated" }}</dd></div>
          </dl>
          <dl v-else class="profile-summary-list">
            <div><dt>Allergens</dt><dd>{{ draftSummary.allergens.join(", ") || "None" }}</dd></div>
            <div><dt>Excluded</dt><dd>{{ draftSummary.excludedIngredients.join(", ") || "None" }}</dd></div>
            <div><dt>Dietary</dt><dd>{{ draftSummary.dietaryPreferences.join(", ") || "None" }}</dd></div>
          </dl>
        </section>

        <section class="profile-planning-card">
          <p class="form-kicker">Plan from saved version</p>
          <label><span>Week starts</span><input v-model="form.planningStartDate" type="date" required></label>
          <button class="primary-button" type="button" :disabled="!current || isPlanning" @click="generateFromProfile">
            {{ isPlanning ? "Planning…" : "Generate new week" }}
          </button>
          <button v-if="hasCurrentPlan" class="secondary-button profile-replan-button" type="button" :disabled="isPlanning" @click="rebuildLatestPlan">
            Rebuild latest plan with current version
          </button>
          <p class="field-help">Rebuilding keeps the old plan immutable, creates a replacement and records every changed constraint.</p>
        </section>

        <section v-if="planResult" class="profile-change-card">
          <p class="form-kicker">Planning result</p>
          <h2>Plan #{{ planResult.plan.id }}</h2>
          <p>Profile v{{ planResult.profile_version }} · {{ planResult.constraint_changes.length }} changed constraint groups</p>
          <ul v-if="planResult.constraint_changes.length">
            <li v-for="change in planResult.constraint_changes" :key="change.field">{{ change.field }}</li>
          </ul>
          <NuxtLink class="secondary-button" :to="{ path: '/dashboard', query: { plan: planResult.plan.id } }">Open dashboard</NuxtLink>
        </section>
      </aside>
    </form>
  </main>
</template>
