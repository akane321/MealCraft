<script setup lang="ts">
import {
  COURSE_LABEL,
  DEFAULT_SHAPE,
  MEAL_PRESETS,
  MEAL_ROLE_LABEL,
  PLANNED_MEALS,
  dishCounts,
  dishLabel,
  isFullDefault,
  isStructured,
  isVegetableRole,
  newDish,
  plannedRoles,
  nextRoleId,
  presetName,
  removable,
  type DishKind,
} from "~/lib/plan-shape";
import type { DishCourse, MealRole, PlannedMealType, PlanShape } from "~/types/household";

const shape = defineModel<PlanShape>({ required: true });
// How many people a meal is planned for (members at the table, not their portions): the dinner grows with them.
const props = defineProps<{ people: number }>();

const MEAL_TITLE: Record<PlannedMealType, string> = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" };
const COURSES: DishCourse[] = ["main", "side", "salad", "soup", "breakfast", "baked_good", "dessert", "snack_appetizer"];
// Older course meals hold six dishes; meal-role meals eight (the dinner for seven and more has seven).
const maxDishes = (list: MealRole[]) => (isStructured(list) ? 8 : 6);
// A meal role, not permission to bypass any member's diet (owner, 2026-10-23).
const VEGETABLE_HINT =
  "At least half vegetables. Potatoes count only with at least 40% other vegetables; cured/minced meat up to 20%, other meat/fish up to 5%. Each person's diet still applies";
const HINT: Record<string, string> = {
  "Protein main": "A meat, fish, tofu, egg or bean dish, or a one-bowl dish that brings its own rice or noodles. No two mains of a meal share a protein.",
  "Another protein main": "A meat, fish, tofu, egg or bean dish with a different protein from the meal's other mains",
  "Staple": "Rice by default; noodles, bread or flatbread to suit the meal's cuisine. A one-bowl dish brings its own.",
  "One-bowl dish": "A dish that is a meal in one bowl, its rice or noodles included",
};
const ADD: { kind: DishKind; label: string }[] = [
  { kind: "main", label: "+ Protein main" },
  { kind: "vegetable", label: "+ Vegetable" },
  { kind: "soup", label: "+ Soup" },
];
// Plain copies: structuredClone throws on Vue's reactive proxies.
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

function roles(meal: PlannedMealType): MealRole[] | undefined {
  return shape.value.meals[meal];
}

function setMeals(meals: PlanShape["meals"]) {
  shape.value = { meals };
}

function useFullDay() {
  setMeals(copy(DEFAULT_SHAPE.meals));
}

function toggle(meal: PlannedMealType, on: boolean) {
  const meals: PlanShape["meals"] = on
    ? { ...shape.value.meals, [meal]: copy(Object.values(MEAL_PRESETS[meal])[0]!) }
    : Object.fromEntries(Object.entries(shape.value.meals).filter(([key]) => key !== meal));
  // A day plans at least one meal.
  if (Object.keys(meals).length) setMeals(meals);
}

function choosePreset(meal: PlannedMealType, name: string) {
  const preset = MEAL_PRESETS[meal][name];
  if (preset) setMeals({ ...shape.value.meals, [meal]: copy(preset) });
}

function updateRole(meal: PlannedMealType, index: number, change: Partial<MealRole>) {
  const list = copy(roles(meal)!);
  list[index] = { ...list[index]!, ...change };
  setMeals({ ...shape.value.meals, [meal]: list });
}

function toggleCourse(meal: PlannedMealType, index: number, course: DishCourse) {
  const current = roles(meal)![index]!.courses;
  const courses = current.includes(course) ? current.filter(item => item !== course) : [...current, course];
  if (courses.length) updateRole(meal, index, { courses });
}

function addDish(meal: PlannedMealType, kind: DishKind) {
  const list = copy(roles(meal)!);
  if (list.length >= maxDishes(list)) return;
  if (isStructured(list)) list.push(newDish(meal, list, kind));
  else {
    const courses: DishCourse[] = kind === "main" ? ["main"] : kind === "soup" ? ["soup"] : ["side", "salad"];
    list.push({ role_id: nextRoleId(list, courses), courses, required: true });
  }
  setMeals({ ...shape.value.meals, [meal]: list });
}

function removeDish(meal: PlannedMealType, index: number) {
  const list = copy(roles(meal)!);
  list.splice(index, 1);
  // Keep one required dish; the first main keeps the main dish's share.
  if (!list.some(item => item.required) && list[0]) list[0].required = true;
  if (list.length) setMeals({ ...shape.value.meals, [meal]: list });
}

/** What a meal-role dish takes: "protein main or one-bowl dish". */
function takes(item: MealRole): string {
  const words = (item.meal_roles ?? []).map(kind => MEAL_ROLE_LABEL[kind] ?? kind.replaceAll("_", " "));
  const text = words.join(" or ");
  return `${text[0]!.toUpperCase()}${text.slice(1)}`;
}

/** Always planned: a meal's only dish, and a real meal's core (the first main of a lunch or dinner). */
function fixedCore(meal: PlannedMealType, item: MealRole): boolean {
  const list = roles(meal) ?? [];
  return list.length === 1 || (meal !== "breakfast" && isStructured(list) && item.role_id === "main");
}

function hint(item: MealRole): string | undefined {
  return isVegetableRole(item.role_id) ? VEGETABLE_HINT : HINT[dishLabel(item)];
}

const tableWord = computed(() => `${props.people} at the table`);
// The dishes planned at this table: a dish "from N people" counts only from that many on.
const dishTotal = (list: MealRole[]) => (isStructured(list) ? plannedRoles(list, props.people).length : list.length);
</script>

<template>
  <div class="meals">
    <div class="recommend">
      <div>
        <strong>Recommended full day</strong>
        <small>Breakfast; a lunch of a main, a vegetable dish and rice; and a dinner that grows with who's home, with soup and rice. Noodles or bread instead of rice when the cuisine calls for it.</small>
      </div>
      <button type="button" class="secondary-button" :disabled="isFullDefault(shape)" @click="useFullDay">
        {{ isFullDefault(shape) ? "Using the recommended full day" : "Use the recommended full day" }}
      </button>
    </div>

    <section v-for="meal in PLANNED_MEALS" :key="meal" class="meal" :class="{ on: roles(meal) }">
      <label class="switch">
        <input type="checkbox" :checked="Boolean(roles(meal))" :aria-label="`Plan ${MEAL_TITLE[meal].toLowerCase()}`" @change="toggle(meal, ($event.target as HTMLInputElement).checked)">
        <span class="title">{{ MEAL_TITLE[meal] }}</span>
        <small v-if="roles(meal)">{{ dishTotal(roles(meal)!) }} {{ dishTotal(roles(meal)!) === 1 ? "dish" : "dishes" }}</small>
        <small v-else>Not planned</small>
      </label>

      <template v-if="roles(meal)">
        <div class="presets" role="radiogroup" :aria-label="`${MEAL_TITLE[meal]} dishes`">
          <button
            v-for="(name, index) in Object.keys(MEAL_PRESETS[meal])"
            :key="name"
            type="button"
            role="radio"
            class="preset"
            :aria-checked="presetName(meal, roles(meal)!) === name"
            @click="choosePreset(meal, name)"
          >
            {{ name }}<span v-if="index === 0 && meal !== 'breakfast'" class="tag">Recommended</span>
          </button>
          <span v-if="presetName(meal, roles(meal)!).startsWith('Custom')" class="preset custom" aria-current="true">{{ presetName(meal, roles(meal)!) }}</span>
        </div>
        <p v-if="isStructured(roles(meal))" class="counts">
          <b>{{ MEAL_TITLE[meal] }} for {{ tableWord }}:</b> {{ dishCounts(roles(meal)!, people) }}
        </p>

        <ol class="dishes">
          <li v-for="(item, index) in roles(meal)" :key="item.role_id" class="dish" :class="{ later: (item.min_people ?? 0) > people }">
            <span class="dish-name" :title="hint(item)">{{ dishLabel(item) }}</span>
            <span v-if="isStructured(roles(meal))" class="takes">
              {{ takes(item) }}
              <span v-if="item.min_people" class="from" :title="(item.min_people ?? 0) > people ? `Not planned for ${tableWord}` : undefined">From {{ item.min_people }} people</span>
            </span>
            <span v-else class="courses">
              <button
                v-for="course in COURSES"
                :key="course"
                type="button"
                class="course"
                :aria-pressed="item.courses.includes(course)"
                @click="toggleCourse(meal, index, course)"
              >
                {{ COURSE_LABEL[course] }}
              </button>
            </span>
            <label class="optional" :class="{ 'is-hidden': fixedCore(meal, item) }">
              <input type="checkbox" :checked="!item.required" :disabled="fixedCore(meal, item)" @change="updateRole(meal, index, { required: !($event.target as HTMLInputElement).checked })"> if one fits
            </label>
            <button v-if="removable(meal, roles(meal)!, index)" type="button" class="remove" :aria-label="`Remove ${dishLabel(item).toLowerCase()}`" @click="removeDish(meal, index)"><UIcon name="i-lucide-x" aria-hidden="true" /></button>
            <span v-else class="remove-space" aria-hidden="true" />
          </li>
        </ol>
        <div v-if="roles(meal)!.length < maxDishes(roles(meal)!)" class="add">
          <template v-if="meal === 'breakfast' && isStructured(roles(meal))">
            <button type="button" class="secondary-button" @click="addDish(meal, 'main')">+ Breakfast dish</button>
          </template>
          <template v-else>
            <button v-for="option in ADD" :key="option.kind" type="button" class="secondary-button" @click="addDish(meal, option.kind)">{{ option.label }}</button>
            <button v-if="isStructured(roles(meal)) && !roles(meal)!.some(item => item.role_id === 'staple')" type="button" class="secondary-button" @click="addDish(meal, 'staple')">+ Staple</button>
          </template>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
/* White inner cards on the white profile card; violet marks the chosen preset and courses. */
.meals { display: grid; gap: 12px; margin-top: 18px; }
.recommend { display: flex; align-items: center; gap: 16px; padding: 14px 16px; border: 1px solid #ececef; border-radius: 10px; background: #fafafa; }
.recommend > div { display: grid; gap: 4px; min-width: 0; }
.recommend strong { color: #0f0f12; font-size: 14px; line-height: 20px; font-weight: 600; }
.recommend small { color: #71717a; font-size: 12.5px; line-height: 18px; }
.recommend button { flex: none; margin-left: auto; }
.meal { padding: 14px 16px; border: 1px solid #ececef; border-radius: 10px; background: #fff; }
.switch { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.title { color: #0f0f12; font-size: 15px; line-height: 20px; font-weight: 600; }
.switch small { margin-left: auto; color: #71717a; font-size: 12px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.preset { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 12px; border: 1px solid #e4e4e7; border-radius: 999px; background: #fff; color: #3f3f46; font-size: 13px; font-weight: 500; cursor: pointer; transition: background 120ms, border-color 120ms; }
.preset:hover { border-color: #d4d4d8; background: #f7f7f8; }
.preset[aria-checked="true"], .preset.custom { border-color: #c4b5fd; background: #f5f3ff; color: #5b21b6; }
.preset .tag { height: 18px; padding: 0 6px; border-radius: 999px; background: #ede9fe; color: #6d28d9; font-size: 11px; line-height: 18px; font-weight: 500; }
.preset[aria-checked="true"] .tag { background: #fff; }
.counts { margin: 10px 0 0; color: #52525b; font-size: 13px; line-height: 18px; }
.counts b { color: #0f0f12; font-weight: 600; }
.dishes { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 4px; }
.dish { display: grid; grid-template-columns: 150px minmax(0, 1fr) auto 28px; gap: 10px; align-items: center; min-height: 32px; }
.dish.later { opacity: 0.55; }
.dish-name { color: #27272a; font-size: 13.5px; font-weight: 500; }
.courses { display: flex; flex-wrap: wrap; gap: 4px; }
.course { height: 26px; padding: 0 10px; border: 0; border-radius: 999px; background: transparent; color: #71717a; font-size: 12.5px; font-weight: 500; cursor: pointer; }
.course:hover { background: #f4f4f5; color: #27272a; }
.course[aria-pressed="true"] { background: #f5f3ff; color: #6d28d9; }
.takes { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #71717a; font-size: 12.5px; }
.from { height: 20px; padding: 0 8px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 11.5px; line-height: 20px; font-weight: 500; white-space: nowrap; }
.optional { display: flex; gap: 6px; align-items: center; color: #71717a; font-size: 12.5px; white-space: nowrap; }
/* Not "hidden": Tailwind's .hidden is display:none and would collapse the grid cell. */
.optional.is-hidden { visibility: hidden; }
.remove { width: 28px; height: 28px; display: grid; place-items: center; padding: 0; border: 0; border-radius: 8px; background: transparent; color: #a1a1aa; cursor: pointer; }
.remove:hover { background: #fef3f2; color: #b42318; }
.remove .iconify { width: 16px; height: 16px; }
.add { display: flex; gap: 8px; margin-top: 10px; }
</style>
