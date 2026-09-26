<script setup lang="ts">
import { COURSE_LABEL, MEAL_PRESETS, PLANNED_MEALS, nextRoleId, presetName } from "~/lib/plan-shape";
import type { DishCourse, MealRole, PlannedMealType, PlanShape } from "~/types/household";

const shape = defineModel<PlanShape>({ required: true });

const MEAL_TITLE: Record<PlannedMealType, string> = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" };
const COURSES: DishCourse[] = ["main", "side", "salad", "soup", "breakfast", "baked_good", "dessert", "snack_appetizer"];
const MAX_DISHES = 6;
// Plain copies: structuredClone throws on Vue's reactive proxies.
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

function roles(meal: PlannedMealType): MealRole[] | undefined {
  return shape.value.meals[meal];
}

function setMeals(meals: PlanShape["meals"]) {
  shape.value = { meals };
}

function toggle(meal: PlannedMealType, on: boolean) {
  const meals: PlanShape["meals"] = on
    ? { ...shape.value.meals, [meal]: copy(Object.values(MEAL_PRESETS[meal])[0]!) }
    : Object.fromEntries(Object.entries(shape.value.meals).filter(([key]) => key !== meal));
  // A week plans at least one meal a day.
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

function addDish(meal: PlannedMealType, courses: DishCourse[]) {
  const list = copy(roles(meal)!);
  if (list.length >= MAX_DISHES) return;
  list.push({ role_id: nextRoleId(list, courses), courses, required: true });
  setMeals({ ...shape.value.meals, [meal]: list });
}

function removeDish(meal: PlannedMealType, index: number) {
  const list = copy(roles(meal)!);
  list.splice(index, 1);
  // Keep one required dish; the first main keeps the main dish's share.
  if (!list.some(item => item.required) && list[0]) list[0].required = true;
  if (list.length) setMeals({ ...shape.value.meals, [meal]: list });
}

function dishLabel(item: MealRole): string {
  if (item.courses.includes("main")) return item.role_id === "main" ? "Main dish" : "Another main";
  if (item.courses.includes("soup")) return "Soup";
  if (item.courses.includes("breakfast")) return "Breakfast dish";
  return "Vegetable or side";
}
</script>

<template>
  <div class="meals">
    <section v-for="meal in PLANNED_MEALS" :key="meal" class="meal" :class="{ on: roles(meal) }">
      <label class="switch">
        <input type="checkbox" :checked="Boolean(roles(meal))" :aria-label="`Plan ${MEAL_TITLE[meal].toLowerCase()}`" @change="toggle(meal, ($event.target as HTMLInputElement).checked)">
        <span class="title">{{ MEAL_TITLE[meal] }}</span>
        <small v-if="roles(meal)">{{ roles(meal)!.length }} {{ roles(meal)!.length === 1 ? "dish" : "dishes" }}</small>
        <small v-else>Not planned</small>
      </label>

      <template v-if="roles(meal)">
        <div class="presets" role="radiogroup" :aria-label="`${MEAL_TITLE[meal]} dishes`">
          <button
            v-for="name in Object.keys(MEAL_PRESETS[meal])"
            :key="name"
            type="button"
            role="radio"
            class="preset"
            :aria-checked="presetName(meal, roles(meal)!) === name"
            @click="choosePreset(meal, name)"
          >
            {{ name }}
          </button>
          <span v-if="presetName(meal, roles(meal)!) === 'Custom'" class="preset custom" aria-current="true">Custom</span>
        </div>

        <ol class="dishes">
          <li v-for="(item, index) in roles(meal)" :key="item.role_id" class="dish">
            <span class="dish-name">{{ dishLabel(item) }}</span>
            <span class="courses">
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
            <label class="optional"><input type="checkbox" :checked="!item.required" @change="updateRole(meal, index, { required: !($event.target as HTMLInputElement).checked })"> if one fits</label>
            <button v-if="roles(meal)!.length > 1" type="button" class="remove" :aria-label="`Remove ${dishLabel(item).toLowerCase()}`" @click="removeDish(meal, index)">×</button>
          </li>
        </ol>
        <div v-if="roles(meal)!.length < MAX_DISHES" class="add">
          <button type="button" class="secondary-button" @click="addDish(meal, ['main'])">+ Main</button>
          <button type="button" class="secondary-button" @click="addDish(meal, ['side', 'salad'])">+ Vegetable</button>
          <button type="button" class="secondary-button" @click="addDish(meal, ['soup'])">+ Soup</button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.meals { display: grid; gap: 12px; margin-top: 18px; }
.meal { padding: 14px 16px; border: 1px solid var(--border); border-radius: 14px; background: var(--s1); }
.meal.on { background: var(--s2); }
.switch { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.switch input { width: 16px; height: 16px; accent-color: var(--sage); }
.title { font-family: var(--serif); font-size: 18px; }
.switch small { margin-left: auto; color: var(--muted); font-size: 12px; }
.presets { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.preset { padding: 6px 12px; border: 1px solid var(--border); border-radius: 999px; background: transparent; color: var(--t2); font-size: 12px; cursor: pointer; }
.preset[aria-checked="true"], .preset.custom { border-color: var(--accent); color: var(--ivory); background: rgba(232, 144, 111, 0.12); }
.dishes { list-style: none; margin: 12px 0 0; padding: 0; display: grid; gap: 8px; }
.dish { display: grid; grid-template-columns: 130px minmax(0, 1fr) auto auto; gap: 10px; align-items: center; }
.dish-name { font-size: 13px; color: var(--ivory); }
.courses { display: flex; flex-wrap: wrap; gap: 4px; }
.course { padding: 3px 8px; border: 1px solid var(--border); border-radius: 999px; background: transparent; color: var(--muted); font-size: 11px; cursor: pointer; }
.course[aria-pressed="true"] { border-color: rgba(169, 183, 154, 0.6); color: var(--ivory); background: rgba(169, 183, 154, 0.14); }
.optional { display: flex; gap: 6px; align-items: center; font-size: 11px; color: var(--muted); white-space: nowrap; }
.remove { width: 26px; height: 26px; border: 1px solid var(--border); border-radius: 50%; background: transparent; color: var(--danger); cursor: pointer; }
.add { display: flex; gap: 8px; margin-top: 10px; }
@media (max-width: 700px) {
  .dish { grid-template-columns: minmax(0, 1fr) auto; }
  .courses { grid-column: 1 / -1; }
}
</style>
