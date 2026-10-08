<script setup lang="ts">
import { dishRole, foodGroup } from "~/lib/dish-icon";
import type { DishRole, FoodGroup } from "~/lib/dish-icon";

// `title` is the dish title used for mapping. The icon is decorative (call sites print the title next to it).
// `role`/`group` override the mapping (used by the /dev/dish-icons gallery).
const props = withDefaults(defineProps<{
  title?: string;
  course?: string | null;
  roleId?: string | null;
  ingredients?: string[];
  size?: number;
  role?: DishRole;
  group?: FoodGroup;
}>(), { title: "", course: null, roleId: null, ingredients: () => [], size: 40, role: undefined, group: undefined });

const dish = computed(() => ({ title: props.title, course: props.course, roleId: props.roleId, ingredients: props.ingredients }));
const role = computed(() => props.role ?? dishRole(dish.value));
const group = computed(() => props.group ?? foodGroup(dish.value, role.value));

// Foods are drawn once in 64x64 plate coordinates (centre ~32,36); each container moves/scales them onto itself.
const SPOT: Record<DishRole, string> = {
  main: "translate(0 -2)",
  other: "translate(0 -2)",
  vegetable: "translate(32 35) scale(.72) translate(-32 -36)",
  salad: "translate(32 21) scale(.6) translate(-32 -36)",
  soup: "",
  dessert: "translate(32 20) scale(.48) translate(-32 -36)",
  drink: "",
};

// Drink has no solid food on it: the group only tints the liquid.
const DRINK_FILL: Partial<Record<FoodGroup, string>> = { fruit_sweet: "#F0675C", leafy: "#6CC383", veg_mix: "#F5A33C", broth: "#E7AE45", bread: "#C98A55", noodles: "#FFE27A" };
const drinkFill = computed(() => DRINK_FILL[group.value] ?? "#FFE27A");
</script>

<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 64 64"
    :width="size"
    :height="size"
    aria-hidden="true"
    :data-role="role"
    :data-group="group"
    fill="none"
    stroke="#2A2A48"
    stroke-width="1.8"
    stroke-linejoin="round"
    stroke-linecap="round"
  >
    <ellipse cx="32" cy="58" rx="22" ry="3" fill="#2A2A48" fill-opacity="0.08" stroke="none" />

    <!-- container -->
    <template v-if="role === 'main' || role === 'other'">
      <circle cx="32" cy="32" r="26" :fill="role === 'main' ? '#FFFFFF' : '#FFF1C2'" />
      <circle cx="32" cy="32" r="19" fill="#F6F1E7" stroke="#D9D0BF" stroke-width="1.4" />
      <path d="M14 22a21 21 0 0 1 9-9" stroke="#FFFFFF" stroke-width="3" />
    </template>
    <template v-else-if="role === 'vegetable'">
      <ellipse cx="32" cy="35" rx="27" ry="18" fill="#FFFFFF" />
      <ellipse cx="32" cy="35" rx="20" ry="12.5" fill="#E8F4EA" stroke="#C6E2CC" stroke-width="1.4" />
      <path d="M10 30c2-4 6-7 11-9" stroke="#FFFFFF" stroke-width="3" />
    </template>
    <template v-else-if="role === 'salad'">
      <path d="M6 30h52c0 11-11 20-26 20S6 41 6 30z" fill="#4FB86E" />
      <path d="M12 35c1 5 5 9 11 11" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="2.6" />
      <path d="M24 52h16" stroke-width="2.4" />
      <ellipse cx="32" cy="30" rx="26" ry="6" fill="#E8F4EA" />
    </template>
    <template v-else-if="role === 'soup'">
      <path d="M7 30h50c0 13-11 23-25 23S7 43 7 30z" fill="#F0675C" />
      <path d="M12 34c1 6 5 11 11 14" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="2.6" />
      <path d="M23 53h18" stroke-width="2.4" />
      <ellipse cx="32" cy="30" rx="25" ry="6" fill="#F7C873" />
      <ellipse cx="32" cy="30" rx="19" ry="3.6" fill="#F1B24A" stroke="none" />
      <circle cx="25" cy="30" r="1.8" fill="#4FB86E" stroke="none" />
      <circle cx="37" cy="29" r="1.6" fill="#4FB86E" stroke="none" />
      <circle cx="31" cy="31.5" r="1.4" fill="#FFFFFF" stroke="none" />
      <path d="M24 21c-3-3 3-4 0-8M32 21c-3-3 3-4 0-8M40 21c-3-3 3-4 0-8" stroke-width="1.8" stroke-opacity="0.7" />
    </template>
    <template v-else-if="role === 'dessert'">
      <path d="M32 40V52M20 55q12-5 24 0" />
      <path d="M12 28h40q0 14-20 14T12 28z" fill="#F0675C" />
      <path d="M17 32c1 3 3 5 6 6" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="2.6" />
      <ellipse cx="32" cy="28" rx="20" ry="4.5" fill="#F6F1E7" />
    </template>
    <template v-else>
      <!-- drink -->
      <path d="M36 32L44 6" stroke="#F0675C" stroke-width="4" />
      <path d="M17 14H47L43 56H21z" fill="#FFFFFF" />
      <path d="M18.2 25H45.8L43 56H21z" :fill="drinkFill" />
      <rect x="25" y="31" width="9" height="9" rx="2" fill="#FFFFFF" fill-opacity="0.85" transform="rotate(-12 29 35)" />
      <path d="M22 19l1.5 14" stroke="#FFFFFF" stroke-width="2.6" />
    </template>

    <!-- contents -->
    <g v-if="role !== 'drink' && role !== 'soup'" :transform="SPOT[role]">
      <template v-if="group === 'noodles'">
        <path d="M18 30c4-4 6 4 10 0s6 4 10 0 6 4 8 1" stroke="#D6962E" stroke-width="2.6" />
        <path d="M17 36c4-4 6 4 10 0s6 4 10 0 6 4 9 1" stroke="#E7AE45" stroke-width="2.6" />
        <path d="M20 42c4-3 6 3 10 0s6 3 10 0" stroke="#D6962E" stroke-width="2.6" />
        <circle cx="26" cy="27" r="1.8" fill="#4FB86E" stroke="none" />
        <circle cx="38" cy="39" r="1.8" fill="#4FB86E" stroke="none" />
        <circle cx="33" cy="33" r="2" fill="#F0675C" stroke="none" />
        <path d="M40 14l12 13M44 12l10 11" stroke="#A8673A" stroke-width="2.2" />
      </template>
      <template v-else-if="group === 'rice'">
        <path d="M17 40c0-10 7-16 15-16s15 6 15 16z" fill="#FFFFFF" />
        <path d="M24 33h3M30 29h3M35 34h3M27 37h3M38 38h2.4" stroke-width="1.8" />
        <circle cx="40" cy="27" r="2.2" fill="#4FB86E" />
        <circle cx="22" cy="29" r="2.2" fill="#F0675C" />
        <circle cx="33" cy="25" r="2" fill="#FFE27A" />
        <path d="M17 40h30" />
      </template>
      <template v-else-if="group === 'poultry'">
        <path d="M20 39c-4-9 4-17 12-15 8 2 10 11 4 16-4 3-13 4-16-1z" fill="#E59A4F" />
        <path d="M24 30c3-3 7-3 9-1" stroke="#F6C58E" stroke-width="2.4" />
        <path d="M36 40l7 7" stroke-width="2.8" />
        <circle cx="44" cy="48" r="2.4" fill="#FFFFFF" />
        <circle cx="46.5" cy="46" r="2.2" fill="#FFFFFF" />
        <path d="M40 22c2-1 4 0 5 2M42 26c2 0 3 1 4 2" stroke="#4FB86E" stroke-width="2" />
      </template>
      <template v-else-if="group === 'red_meat'">
        <path d="M17 29c6-7 22-7 28 1 2 7-4 12-14 12s-17-5-14-13z" fill="#B94A3E" />
        <path d="M23 31c4 2 8-1 12 1M25 36c3 0 6-1 9 0" stroke="#F3C9C1" stroke-width="1.8" />
        <path d="M20 29c3-3 7-5 12-5" stroke="#D9776B" stroke-width="2.2" />
        <circle cx="42" cy="22" r="2.6" fill="#4FB86E" />
        <circle cx="46" cy="25" r="2" fill="#7CCB8F" />
        <path d="M22 45l3-1M29 46l3-1M36 45l3-1" stroke="#F5A33C" stroke-width="2.2" />
      </template>
      <template v-else-if="group === 'seafood'">
        <path d="M16 33c6-9 20-9 26 0-6 9-20 9-26 0z" fill="#F59E7C" />
        <path d="M42 33l8-6v12z" fill="#F59E7C" />
        <path d="M24 28c1 3 1 7 0 10M30 27c1 4 1 8 0 12M36 28c1 3 1 7 0 10" stroke="#FFFFFF" stroke-width="1.8" />
        <circle cx="21" cy="31.5" r="1.4" fill="#2A2A48" stroke="none" />
        <path d="M22 44c3-2 5 0 8-1M34 44c2-1 4 0 6-1" stroke="#4FB86E" stroke-width="2" />
        <circle cx="44" cy="21" r="2.6" fill="#FFE27A" />
      </template>
      <template v-else-if="group === 'tofu_egg'">
        <path d="M14 38L28 34L34 40L20 45z" fill="#F6F1E7" />
        <path d="M14 38L20 45V50L14 43z" fill="#E8DFCB" />
        <path d="M20 45L34 40V45L20 50z" fill="#FFFFFF" />
        <path d="M30 24c5-4 14-3 16 3 4 3 2 10-4 11-4 3-12 1-14-3-4-3-3-8 2-11z" fill="#FFFFFF" />
        <circle cx="38" cy="30" r="5" fill="#FFE27A" />
        <path d="M36 28.5a3 3 0 0 1 2.5-1" stroke="#FFFFFF" stroke-width="1.6" />
      </template>
      <template v-else-if="group === 'leafy'">
        <path d="M14 41c3-11 11-17 19-17-1 10-8 17-19 17z" fill="#3FA65C" />
        <path d="M27 44c4-10 12-14 20-13-3 9-10 13-20 13z" fill="#6CC383" />
        <path d="M15 41c7-4 12-9 17-16M28 44c6-3 11-7 16-12" stroke="#E8F4EA" stroke-width="1.8" />
        <circle cx="24" cy="44" r="1.4" fill="#FFFFFF" stroke="none" />
        <circle cx="38" cy="27" r="1.4" fill="#FFFFFF" stroke="none" />
      </template>
      <template v-else-if="group === 'veg_mix'">
        <circle cx="23" cy="37" r="6.5" fill="#F5A33C" />
        <circle cx="23" cy="37" r="2.4" stroke="#FFFFFF" stroke-width="1.6" />
        <path d="M35 40c-3-3-2-9 3-10 1-4 7-4 8 0 4 1 4 7 0 9-2 3-8 4-11 1z" fill="#4FB86E" />
        <path d="M40 41v4" stroke-width="2.2" />
        <circle cx="30" cy="27" r="3" fill="#9BD07A" />
        <circle cx="36" cy="25" r="2.6" fill="#9BD07A" />
        <path d="M16 29l5-4" stroke="#F0675C" stroke-width="2.6" />
      </template>
      <template v-else-if="group === 'broth'">
        <ellipse cx="32" cy="38" rx="17" ry="9" fill="#F7C873" />
        <ellipse cx="32" cy="38" rx="11" ry="5" fill="#F1B24A" stroke="none" />
        <circle cx="26" cy="38" r="2" fill="#4FB86E" stroke="none" />
        <circle cx="38" cy="37" r="1.8" fill="#4FB86E" stroke="none" />
        <circle cx="32" cy="40" r="1.6" fill="#FFFFFF" stroke="none" />
        <path d="M25 29c-3-3 3-4 0-8M32 29c-3-3 3-4 0-8M39 29c-3-3 3-4 0-8" stroke-opacity="0.7" />
      </template>
      <template v-else-if="group === 'bread'">
        <path d="M14 38h36v4q0 6-6 6H20q-6 0-6-6z" fill="#A8673A" />
        <path d="M14 38q0-16 18-16t18 16z" fill="#E59A4F" />
        <path d="M21 32c1-3 3-5 6-6" stroke="#F6C58E" stroke-width="2.4" />
        <path d="M28 28l3 6M35 27l3 6M42 30l2 5" stroke="#A8673A" stroke-width="2" />
      </template>
      <template v-else-if="group === 'fruit_sweet'">
        <path d="M30 48c-12-5-14-17-8-21 4-2 7 0 9 1 2-1 6-3 10-1 6 4 4 16-11 21z" fill="#F0675C" />
        <path d="M24 31c1-2 3-3 5-3" stroke="#FFFFFF" stroke-opacity="0.7" stroke-width="2.4" />
        <path d="M31 28c0-4 1-6 4-8" stroke-width="2" />
        <path d="M35 20c3-3 7-2 8 0-3 3-6 3-8 0z" fill="#4FB86E" />
        <circle cx="46" cy="40" r="4.2" fill="#6B7FE8" />
        <circle cx="42" cy="46" r="3.4" fill="#6B7FE8" />
        <circle cx="45" cy="38.8" r="1" fill="#FFFFFF" stroke="none" />
      </template>
      <template v-else>
        <circle cx="24" cy="36" r="7.5" fill="#F0675C" />
        <path d="M19 33a6 6 0 0 1 4-3" stroke="#FFFFFF" stroke-opacity="0.7" stroke-width="2" />
        <rect x="31" y="21" width="12" height="12" rx="2.5" fill="#6CC383" />
        <path d="M34 25h4" stroke="#E8F4EA" stroke-width="2" />
        <path d="M28 49l7-12 8 12z" fill="#FFE27A" />
        <circle cx="35" cy="45" r="1.4" fill="#F5A33C" stroke="none" />
      </template>
    </g>
  </svg>
</template>
