<script setup lang="ts">
import { allergenLabel, CHECKED_ALLERGENS } from "~/lib/allergens";
import { todayIsoDate } from "~/lib/meal-plan-format";
import {
  defaultServings,
  formatPortions,
  hpbSodiumLimit,
  NO_TIME_LIMIT_MINUTES,
  noGoals,
  ownSelfOnlyAllergens,
  statedTimeLimit,
  summarizeHouseholdMembers,
  totalServings as totalOf,
} from "~/lib/household-profile";
import type { MemberLimitSummary } from "~/lib/household-profile";
import {
  cleanAvailableIngredients,
  parseExcludedIngredients,
  toOptionalNumber,
} from "~/lib/recommendation-form";
import { DEFAULT_SHAPE, EQUIPMENT, EQUIPMENT_LABEL, describeShape } from "~/lib/plan-shape";
import type {
  ActivityLevel,
  AgeBand,
  CookingTimeRule,
  Equipment,
  HouseholdMemberInput,
  HouseholdProfileInput,
  PersonalGoal,
  PlanShape,
  PresenceRule,
  Sex,
} from "~/types/household";
import type {
  AvailableIngredientInput,
  DietaryPreference,
  HealthPreference,
  PricingMode,
} from "~/types/recommendation";

useHead({ title: "Household · MealCraft" });

interface MemberForm {
  name: string;
  // Auto is the HPB default from age group, sex, activity and goal; set is the household's own number.
  servingsMode: "auto" | "set";
  servingsPerMeal: number;
  ageBand: AgeBand | "";
  sex: Sex | "";
  activity: ActivityLevel | "";
  goal: PersonalGoal | "";
  defaultPresent: boolean;
  allergens: string[];
  // Allergens of this member's own that only this member avoids; a subset of `allergens`.
  selfOnlyAllergens: string[];
  excludedIngredients: string;
  dietaryPreferences: DietaryPreference[];
}

const allergenOptions = CHECKED_ALLERGENS;
const ageOptions: { label: string; value: AgeBand }[] = [
  { label: "Toddler (1–3)", value: "toddler" },
  { label: "Child (4–12)", value: "child" },
  { label: "Teen (13–18)", value: "teen" },
  { label: "Adult (19–59)", value: "adult" },
  { label: "Older adult (60+)", value: "senior" },
];
// HPB's three columns: Light / Moderate / Vigorous (children, teens), Low / Moderate / Very active (adults).
const activityOptions: { label: string; value: ActivityLevel }[] = [
  { label: "Light (mostly sitting)", value: "low" },
  { label: "Very active (sport or physical work)", value: "high" },
];
const goalOptions: { label: string; value: PersonalGoal }[] = [
  { label: "Fat loss (slightly smaller portions)", value: "fat_loss" },
  { label: "Muscle gain (protein-rich dishes rank higher)", value: "muscle_gain" },
];
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

// A new household starts with no limit or goal it did not enter (the help text promises as much).
const form = reactive({
  name: "My household",
  ...noGoals(),
  pricingMode: "fixture" as PricingMode,
  planningStartDate: todayIsoDate(),
});
function newMember(number: number): MemberForm {
  return {
    name: `Person ${number}`,
    servingsMode: "auto",
    servingsPerMeal: 1,
    ageBand: "",
    sex: "",
    activity: "",
    goal: "",
    defaultPresent: true,
    allergens: [],
    selfOnlyAllergens: [],
    excludedIngredients: "",
    dietaryPreferences: [],
  };
}
const members = ref<MemberForm[]>([newMember(1)]);
// Layer 08: confirmed sentences, the basics run out, and the daily sodium limit.
const presenceRules = ref<PresenceRule[]>([]);
const timeRules = ref<CookingTimeRule[]>([]);
const missingBasics = ref<string[]>([]);
const sodiumLimitOn = ref(false);
const sodiumLimitMg = ref<number | null>(null); // empty: the HPB limit
const pantryItems = ref<AvailableIngredientInput[]>([
  { normalized_name: "", quantity: null, unit: null },
]);
const saveNotice = ref<string | null>(null);
// Which meals each day plans and each one's dishes (ADR-0046).
const planShape = ref<PlanShape>(structuredClone(DEFAULT_SHAPE));
// Equipment the kitchen lacks (layer 08): a dish that needs it is never planned. Empty: all at home.
const missingEquipment = ref<Equipment[]>([]);
// Days a plan covers (1 to 14); longer than a week shops twice, before day 1 and day 8 (ADR-0072).
const dayCount = ref(7);
const DAY_OPTIONS = Array.from({ length: 14 }, (_, index) => index + 1);

const {
  current,
  errorMessage,
  generatePlan,
  isLoading,
  isPlanning,
  isSaving,
  loadCurrent,
  loadReference,
  planResult,
  reference,
  replanLatest,
  save,
} = useHouseholdProfile();

const memberPayloads = computed(() => members.value.map(memberPayload));
const totalServings = computed(() => totalOf(memberPayloads.value, reference.value));
const draftSummary = computed(() => summarizeHouseholdMembers(memberPayloads.value, reference.value));
const savedSummary = computed(() => current.value
  ? summarizeHouseholdMembers(current.value.current.members.map(member => ({ ...member, servings_per_meal: member.resolved_servings_per_meal })))
  : null);
const homePortions = computed(() => (savedSummary.value ?? draftSummary.value).planningHouseholdSize);
/** One member's own limits in a line, or "No limits" when they have none. */
function memberLimitText(member: MemberLimitSummary): string {
  const own = member.selfOnlyAllergens.map(allergen => `${allergenLabel(allergen)} (only ${member.name})`);
  const parts = [...own, ...member.dietaryPreferences, ...member.excludedIngredients];
  return parts.length ? parts.join(", ") : "No limits of their own";
}
// The editor's dish counts follow the draft: the people usually home as entered now, not their portions
// (ADR-0070, backend slot_people): two adults and three small children are five at the table.
const tablePeople = computed(() => Math.max(1, memberPayloads.value.filter(member => member.default_present !== false).length));
const planWord = computed(() => (dayCount.value === 7 ? "Plan this week" : `Plan ${dayCount.value} ${dayCount.value === 1 ? "day" : "days"}`));
const ruleMembers = computed(() => members.value.map(member => ({
  name: member.name,
  age_band: member.ageBand || null,
  default_present: member.defaultPresent,
})));
/** The name on this member's card; a card still being filled in reads as "this person". */
function memberName(member: MemberForm): string {
  return member.name.trim() || "this person";
}
const memberNames = computed(() => members.value.map(member => member.name.trim()));
const orphanRules = computed(() => presenceRules.value.some(rule => !memberNames.value.includes(rule.member_name)));
const hpbSodium = computed(() => hpbSodiumLimit(reference.value, memberPayloads.value));
// The planned meals' share of the day (backend meal_shares): a daily limit is kept by these meals alone.
const plannedShare = computed(() => Object.keys(planShape.value.meals)
  .reduce((sum, meal) => sum + (reference.value?.meal_shares[meal] ?? 0), 0));
const sodiumPerDay = computed(() => toOptionalNumber(sodiumLimitMg.value) ?? hpbSodium.value);

function autoServings(member: MemberForm) {
  return defaultServings(reference.value, { age_band: member.ageBand || null, sex: member.sex || null, activity: member.activity || null, goal: member.goal || null });
}
const hasCurrentPlan = computed(() => current.value?.latest_plan_id !== null && current.value?.latest_plan_id !== undefined);

function hydrateFromCurrent() {
  if (!current.value) return;
  const profile = current.value;
  const version = profile.current;
  form.name = profile.name;
  form.maxCookingTimeMinutes = statedTimeLimit(version.max_cooking_time_minutes);
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
    servingsMode: member.servings_per_meal === null ? "auto" : "set",
    servingsPerMeal: member.resolved_servings_per_meal,
    ageBand: member.age_band ?? "",
    sex: member.sex ?? "",
    activity: member.activity ?? "",
    goal: member.goal ?? "",
    defaultPresent: member.default_present ?? true,
    allergens: [...member.allergens],
    selfOnlyAllergens: [...(member.self_only_allergens ?? [])],
    excludedIngredients: member.excluded_ingredients.join(", "),
    dietaryPreferences: [...member.dietary_preferences],
  }));
  presenceRules.value = (version.presence_rules ?? []).map(rule => ({ ...rule }));
  timeRules.value = (version.cooking_time_rules ?? []).map(rule => ({ ...rule }));
  missingBasics.value = [...(version.missing_basics ?? [])];
  missingEquipment.value = [...(version.missing_equipment ?? [])];
  const sodium = (version.nutrition_limits ?? []).find(limit => limit.nutrient === "sodium_mg");
  sodiumLimitOn.value = Boolean(sodium);
  sodiumLimitMg.value = sodium?.max_value ?? null;
  planShape.value = version.plan_shape
    ?? (version.meal_composition ? { meals: { dinner: version.meal_composition } } : structuredClone(DEFAULT_SHAPE));
  pantryItems.value = version.available_ingredients.length
    ? version.available_ingredients.map(item => ({ ...item }))
    : [{ normalized_name: "", quantity: null, unit: null }];
}

function addMember() {
  members.value.push(newMember(members.value.length + 1));
}

function removeMember(index: number) {
  if (members.value.length <= 1) return;
  // Their presence rules go with them.
  const [removed] = members.value.splice(index, 1);
  presenceRules.value = presenceRules.value.filter(rule => rule.member_name !== removed!.name.trim());
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
    servings_per_meal: member.servingsMode === "set" ? toOptionalNumber(member.servingsPerMeal) : null,
    age_band: member.ageBand || null,
    sex: member.sex || null,
    activity: member.activity || null,
    goal: member.goal || null,
    default_present: member.defaultPresent,
    allergens: member.allergens,
    // Only an allergen this member still has: unticking the allergen drops its "only I avoid it" with it.
    self_only_allergens: ownSelfOnlyAllergens(member.allergens, member.selfOnlyAllergens),
    excluded_ingredients: parseExcludedIngredients(member.excludedIngredients),
    dietary_preferences: member.dietaryPreferences,
  };
}

function buildPayload(): HouseholdProfileInput {
  return {
    name: form.name,
    members: members.value.map(memberPayload),
    max_cooking_time_minutes: toOptionalNumber(form.maxCookingTimeMinutes) ?? NO_TIME_LIMIT_MINUTES,
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
    plan_shape: planShape.value,
    presence_rules: presenceRules.value,
    cooking_time_rules: timeRules.value,
    missing_basics: missingBasics.value,
    missing_equipment: missingEquipment.value,
    nutrition_limits: sodiumLimitOn.value
      ? [{ nutrient: "sodium_mg", scope: "per_day", max_value: toOptionalNumber(sodiumLimitMg.value) }]
      : [],
  };
}

async function saveProfile() {
  saveNotice.value = null;
  const saved = await save(buildPayload());
  if (saved) {
    saveNotice.value = "Saved. New weeks will follow these details.";
    hydrateFromCurrent();
  }
}

async function generateFromProfile() {
  saveNotice.value = null;
  const generated = await generatePlan({ start_date: form.planningStartDate, day_count: dayCount.value });
  if (generated) saveNotice.value = "Your new plan is ready. It's on the home page now.";
}

async function rebuildLatestPlan() {
  saveNotice.value = null;
  const rebuilt = await replanLatest({ start_date: form.planningStartDate, day_count: dayCount.value });
  if (rebuilt) saveNotice.value = "Your plan was redone with these details. The home page shows the new one.";
}

onMounted(async () => {
  await Promise.all([loadCurrent(), loadReference()]);
  hydrateFromCurrent();
});
</script>

<template>
  <main class="page-width profile-page">
    <section class="profile-hero">
      <div>
        <p class="eyebrow">Your household</p>
        <h1>Tell us once who's eating. Every week follows it.</h1>
      </div>
      <p>
        Everyone shares the same dishes, and every meal gives each person something they can eat. An allergy keeps a dish off the whole table; a diet and the foods someone won't eat are that person's own. Targets are only the ones you set here; this isn't medical advice.
      </p>
    </section>

    <div v-if="isLoading" class="notice-panel">Loading your household…</div>
    <div v-if="errorMessage" class="notice-panel error-notice">{{ errorMessage }}</div>
    <div v-if="saveNotice" class="notice-panel success-notice">{{ saveNotice }}</div>

    <form class="profile-layout" @submit.prevent="saveProfile">
      <section class="profile-main">
        <div class="profile-section-heading">
          <div>
            <p class="form-kicker">Household</p>
            <h2>{{ current ? current.name : "Set up your household" }}</h2>
          </div>
          <span v-if="current" class="version-badge">Saved</span>
        </div>

        <label class="profile-name-field">
          <span>Household name</span>
          <input v-model="form.name" type="text" maxlength="120" required>
        </label>

        <div class="profile-section-heading member-heading">
          <div>
            <p class="form-kicker">Who's eating</p>
            <h2>{{ members.length }} {{ members.length === 1 ? "person" : "people" }}, {{ formatPortions(draftSummary.planningHouseholdSize) }} {{ draftSummary.planningHouseholdSize === 1 ? "portion" : "portions" }} a meal</h2>
          </div>
          <button class="secondary-button" type="button" :disabled="members.length >= 12" @click="addMember">+ Add person</button>
        </div>

        <div class="member-list">
          <article v-for="(member, index) in members" :key="index" class="member-card">
            <div class="member-card-header">
              <strong>Member {{ index + 1 }}</strong>
              <button type="button" class="text-button danger-text" :disabled="members.length === 1" @click="removeMember(index)">Remove</button>
            </div>
            <div class="member-core-fields">
              <label><span>Name</span><input v-model="member.name" type="text" maxlength="80" required></label>
              <label>
                <span>Portions a meal</span>
                <span class="portion-field">
                  <select v-model="member.servingsMode" aria-label="How portions are set">
                    <option value="auto">Auto{{ autoServings(member) === null ? "" : ` (${formatPortions(autoServings(member)!)})` }}, from age, sex and activity</option>
                    <option value="set">A set number</option>
                  </select>
                  <input v-if="member.servingsMode === 'set'" v-model.number="member.servingsPerMeal" type="number" min="0.25" max="3" step="0.05" aria-label="Portions they eat" required>
                </span>
              </label>
            </div>
            <div class="profile-field-grid member-basis">
              <label>
                <span>Age group</span>
                <select v-model="member.ageBand">
                  <option value="">Not set (adult)</option>
                  <option v-for="option in ageOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </label>
              <label>
                <span>Sex</span>
                <select v-model="member.sex">
                  <option value="">Not set</option>
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                </select>
              </label>
              <label>
                <span>Activity</span>
                <select v-model="member.activity">
                  <option value="">Moderate (not set)</option>
                  <option v-for="option in activityOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </label>
              <label>
                <span>Goal</span>
                <select v-model="member.goal">
                  <option value="">None</option>
                  <option v-for="option in goalOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                </select>
              </label>
            </div>
            <div class="member-presence">
              <label class="choice-card plain"><input v-model="member.defaultPresent" type="checkbox"><span>Usually eats at home</span></label>
              <p v-if="!member.defaultPresent" class="field-help">Occasional guest: joins only when a rule below says so.</p>
              <p v-else-if="member.servingsMode === 'auto'" class="field-help">Auto portions follow HPB's energy need for this age group, sex and activity.</p>
            </div>
            <div class="member-constraint-group">
              <p>Allergens</p>
              <div class="choice-grid">
                <label v-for="allergen in allergenOptions" :key="allergen" class="choice-card">
                  <input v-model="member.allergens" type="checkbox" :value="allergen"><span>{{ allergenLabel(allergen) }}</span>
                </label>
              </div>
              <div v-if="member.allergens.length" class="self-only-group">
                <p class="field-help">An allergen is left out of every dish for everyone. Turn one of these on and only {{ memberName(member) }}'s dishes leave it out.</p>
                <label v-for="allergen in member.allergens" :key="allergen" class="choice-card plain self-only">
                  <input v-model="member.selfOnlyAllergens" type="checkbox" :value="allergen">
                  <span>Only {{ memberName(member) }} avoids {{ allergenLabel(allergen) }}</span>
                </label>
                <p v-if="member.selfOnlyAllergens.length" class="inline-warning">
                  Cooking in the same kitchen can cause cross-contact. Only turn this on if that is safe for {{ memberName(member) }}.
                </p>
              </div>
            </div>
            <div class="member-constraint-group">
              <p>Diet</p>
              <div class="choice-grid">
                <label v-for="option in dietaryOptions" :key="option.value" class="choice-card">
                  <input v-model="member.dietaryPreferences" type="checkbox" :value="option.value"><span>{{ option.label }}</span>
                </label>
              </div>
            </div>
            <label>
              <span>Won't eat <small>separate with commas</small></span>
              <input v-model="member.excludedIngredients" type="text" placeholder="mushroom, onion">
            </label>
          </article>
        </div>

        <section class="profile-form-section">
          <p class="form-kicker">Meals and dishes</p>
          <h2>What each day plans</h2>
          <p class="field-help">{{ describeShape(planShape) }}. Dish counts follow who's home at each meal. A dish marked "if one fits" is the one a meal may leave out when the budget, time or dishes can't fit it. You can also change this in the chat for one week, e.g. "also plan lunch" or "add a soup on Friday".</p>
          <ProfileMealsEditor v-model="planShape" :people="tablePeople" />
        </section>

        <section class="profile-form-section">
          <p class="form-kicker">Every week</p>
          <h2>Budget, cooking time and goals</h2>
          <div class="profile-field-grid">
            <label><span>Longest cooking time (min)</span><input v-model.number="form.maxCookingTimeMinutes" type="number" min="5" max="240" placeholder="No limit"></label>
            <label><span>Budget per meal</span><input v-model.number="form.budgetPerMealSgd" type="number" min="0.01" step="0.01" placeholder="Optional S$"></label>
            <label><span>Budget per week</span><input v-model.number="form.weeklyBudgetSgd" type="number" min="0.01" step="0.01" placeholder="Optional S$"></label>
            <label>
              <span>Prices</span>
              <select v-model="form.pricingMode">
                <option value="fixture">Sample prices (stay the same)</option>
                <option value="live">Today's FairPrice prices</option>
              </select>
            </label>
            <label><span>Calories per meal</span><input v-model.number="form.calorieTarget" type="number" min="100" max="2500" placeholder="kcal"></label>
            <label><span>Protein per meal</span><input v-model.number="form.proteinTarget" type="number" min="0" max="300" placeholder="g"></label>
            <label><span>Carbs per meal</span><input v-model.number="form.carbohydrateTarget" type="number" min="0" max="500" placeholder="g"></label>
            <label><span>Fat per meal</span><input v-model.number="form.fatTarget" type="number" min="0" max="200" placeholder="g"></label>
            <label><span>Most sodium per meal</span><input v-model.number="form.maxSodiumMgPerMeal" type="number" min="100" max="5000" placeholder="Optional mg"></label>
          </div>
          <p class="field-help">Leave these empty if you have no goal. MealCraft only uses what you enter; it doesn't work out needs or give medical diets.</p>
          <div class="member-constraint-group sodium-limit">
            <label class="choice-card plain"><input v-model="sodiumLimitOn" type="checkbox"><span>Keep sodium within a daily limit</span></label>
            <template v-if="sodiumLimitOn">
              <label class="sodium-field">
                <span>Most sodium per person a day (mg)</span>
                <input
                  v-model.number="sodiumLimitMg"
                  type="number"
                  min="100"
                  max="10000"
                  :required="hpbSodium === null"
                  :placeholder="hpbSodium === null ? 'Enter a limit' : `${hpbSodium} (HPB adult limit)`"
                >
              </label>
              <p class="field-help">
                <template v-if="hpbSodium === null && sodiumLimitMg === null">HPB gives no daily limit for this age group; enter one.</template>
                <template v-else>
                  {{ sodiumPerDay }} mg per person a day{{ sodiumLimitMg === null ? " (HPB adult limit)" : "" }}. A hard limit.
                  <template v-if="plannedShare > 0 && plannedShare < 1">The meals you plan keep within their {{ Math.round(plannedShare * 100) }}% share of the day: {{ Math.round(sodiumPerDay! * plannedShare) }} mg.</template>
                </template>
                Estimates, not medical advice.
              </p>
            </template>
          </div>
          <div class="member-constraint-group">
            <p>Lean towards</p>
            <div class="choice-grid">
              <label v-for="option in healthOptions" :key="option.value" class="choice-card">
                <input v-model="form.healthPreferences" type="checkbox" :value="option.value"><span>{{ option.label }}</span>
              </label>
            </div>
          </div>
        </section>

        <section class="profile-form-section">
          <p class="form-kicker">Who's home and cooking time</p>
          <h2>Tell us in one sentence</h2>
          <p class="field-help">Write it the way you'd say it, in English or Chinese. We show what we understood before anything is added; added rules are kept when you save.</p>
          <ProfileRuleSentence v-model="presenceRules" kind="presence" :members="ruleMembers" />
          <ProfileRuleSentence v-model="timeRules" kind="cooking_time" :members="ruleMembers" />
        </section>

        <section class="profile-form-section">
          <p class="form-kicker">Kitchen</p>
          <h2>Cooking equipment</h2>
          <p class="field-help">We assume a stove and a rice cooker. Tick what your kitchen doesn't have, and dishes that need it are never planned.</p>
          <div class="member-constraint-group">
            <p>We don't have</p>
            <div class="choice-grid">
              <label v-for="item in reference?.meal_structure?.equipment ?? EQUIPMENT" :key="item" class="choice-card plain">
                <input v-model="missingEquipment" type="checkbox" :value="item"><span>{{ EQUIPMENT_LABEL[item] }}</span>
              </label>
            </div>
          </div>
        </section>

        <section v-if="reference?.basics.length" class="profile-form-section">
          <p class="form-kicker">Basics at home</p>
          <h2>Salt, oil, soy sauce and the like</h2>
          <p class="field-help">We assume these are in your kitchen and leave them off the shopping list. Tick any you've run out of, and they're bought and priced again.</p>
          <div class="member-constraint-group">
            <p>Run out of</p>
            <div class="choice-grid">
              <label v-for="basic in reference.basics" :key="basic.normalized_name" class="choice-card plain">
                <input v-model="missingBasics" type="checkbox" :value="basic.normalized_name">
                <span>{{ basic.display_name }}<small v-if="basic.allergens.length"> · contains {{ basic.allergens.map(allergenLabel).join(", ") }}</small></span>
              </label>
            </div>
          </div>
          <p class="field-help basics-safety">Allergen checks still apply to basics: a dish with soy sauce is never planned for a soy allergy.</p>
        </section>

        <section class="profile-form-section">
          <div class="profile-section-heading compact-heading">
            <div><p class="form-kicker">Pantry</p><h2>Already at home</h2></div>
            <button class="secondary-button" type="button" @click="addPantryItem">+ Add ingredient</button>
          </div>
          <p class="field-help">With an amount, it comes off the shopping list. Without one, dishes that use it are just more likely.</p>
          <div class="weekly-pantry-list">
            <div v-for="(item, index) in pantryItems" :key="index" class="weekly-pantry-row">
              <input v-model="item.normalized_name" type="text" aria-label="Ingredient" placeholder="brown rice">
              <input v-model.number="item.quantity" type="number" min="0.01" step="0.01" aria-label="Amount" placeholder="Amount">
              <input v-model="item.unit" type="text" :required="item.quantity !== null" aria-label="Unit" placeholder="g">
              <button type="button" class="remove-button" :aria-label="`Remove pantry item ${index + 1}`" @click="removePantryItem(index)">×</button>
            </div>
          </div>
        </section>

        <button class="primary-button profile-save-button" type="submit" :disabled="isSaving || totalServings > 12 || orphanRules">
          {{ isSaving ? "Saving…" : current ? "Save changes" : "Save household" }}
        </button>
        <p v-if="totalServings > 12" class="inline-error">MealCraft can plan for up to 12 portions a meal, guests included.</p>
        <p v-if="orphanRules" class="inline-error">A "who's home" rule names someone who is no longer a member. Remove it to save.</p>
      </section>

      <aside class="profile-sidebar">
        <section class="profile-summary-card">
          <p class="form-kicker">At the table</p>
          <h2>{{ formatPortions(homePortions) }} {{ homePortions === 1 ? "portion" : "portions" }} a meal</h2>
          <p>An allergen is left out for everyone, unless someone marks it "only I avoid it". A diet and the foods someone won't eat are that person's own: every meal still gives each person a main dish, a staple and a vegetable they can eat. Meals with someone away or a guest over are cooked for who's home.</p>
          <dl v-if="current" class="profile-summary-list">
            <div><dt>Whole household avoids</dt><dd>{{ current.current.allergens.join(", ") || "None" }}</dd></div>
            <div v-for="(member, index) in savedSummary?.members ?? []" :key="index">
              <dt>{{ member.name }}</dt>
              <dd>{{ memberLimitText(member) }}</dd>
            </div>
            <div><dt>Rules</dt><dd>{{ current.current.presence_rules.length + current.current.cooking_time_rules.length || "None" }}</dd></div>
            <div><dt>Kitchen</dt><dd>{{ current.current.missing_equipment?.length ? `No ${current.current.missing_equipment.map(item => EQUIPMENT_LABEL[item].toLowerCase()).join(", ")}` : "All equipment" }}</dd></div>
            <div><dt>Latest plan</dt><dd>{{ current.latest_plan_id ? "Planned" : "Not planned yet" }}</dd></div>
          </dl>
          <dl v-else class="profile-summary-list">
            <div><dt>Whole household avoids</dt><dd>{{ draftSummary.allergens.join(", ") || "None" }}</dd></div>
            <div v-for="(member, index) in draftSummary.members" :key="index">
              <dt>{{ member.name }}</dt>
              <dd>{{ memberLimitText(member) }}</dd>
            </div>
          </dl>
        </section>

        <section class="profile-planning-card">
          <p class="form-kicker">Plan your meals</p>
          <div class="plan-when">
            <label><span>Starts</span><input v-model="form.planningStartDate" type="date" required></label>
            <label>
              <span>Days to plan</span>
              <select v-model.number="dayCount">
                <option v-for="days in DAY_OPTIONS" :key="days" :value="days">{{ days }} {{ days === 1 ? "day" : "days" }}{{ days === 7 ? " (a week)" : "" }}</option>
              </select>
            </label>
          </div>
          <p v-if="dayCount > 7" class="field-help">Two shopping trips: before day 1 and before day 8. Fresh meat, fish and greens are used within 3 days of the trip they're bought on.</p>
          <button class="primary-button" type="button" :disabled="!current || isPlanning" @click="generateFromProfile">
            {{ isPlanning ? "Planning…" : planWord }}
          </button>
          <p v-if="isPlanning" class="field-help" role="status">A large household on a tight budget can take up to a minute to plan.</p>
          <button v-if="hasCurrentPlan" class="secondary-button profile-replan-button" type="button" :disabled="isPlanning" @click="rebuildLatestPlan">
            Replan with these details
          </button>
          <p class="field-help">Replanning keeps the old plan in your history and notes what changed. Save your changes first.</p>
        </section>

        <section v-if="planResult" class="profile-change-card">
          <p class="form-kicker">Done</p>
          <h2>Your plan is ready</h2>
          <p v-if="planResult.constraint_changes.length">What changed since the last plan:</p>
          <ul v-if="planResult.constraint_changes.length">
            <li v-for="change in planResult.constraint_changes" :key="change.field">{{ change.field.replaceAll("_", " ") }}</li>
          </ul>
          <NuxtLink class="secondary-button" to="/">See the plan</NuxtLink>
        </section>
      </aside>
    </form>
  </main>
</template>

<style scoped>
.portion-field { display: grid; grid-template-columns: minmax(0, 1fr) 96px; gap: 9px; }
.portion-field:has(select:only-child) { grid-template-columns: minmax(0, 1fr); }
.member-basis { margin-top: 0; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.member-presence { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.choice-card.plain > span { text-transform: none; }
.choice-card small { color: var(--muted); font-size: 12px; }
.sodium-limit { gap: 12px; }
.sodium-limit > .choice-card { justify-self: start; }
.sodium-field { max-width: 320px; }
.basics-safety { margin-top: 12px; }
.plan-when { display: grid; gap: 12px; }
</style>
