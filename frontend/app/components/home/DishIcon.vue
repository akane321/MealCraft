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

const C = { ink: "#2A2A48", coral: "#F0675C", blue: "#3A63E0", green: "#4FB86E", yellow: "#FFE27A", orange: "#F5A33C", cream: "#F7F4EE", white: "#FFFFFF", brown: "#A8673A", pale: "#D4F2DE" };

const strands = ["M-9,-5 q3,-4 6,0 t6,0 t6,0", "M-9,0 q3,-4 6,0 t6,0 t6,0", "M-9,5 q3,-4 6,0 t6,0 t6,0"];

// Where the food sits on each container: centre + scale. Contents are drawn in a -12..12 box.
const SPOT: Record<DishRole, string> = {
  main: "translate(24 25)",
  other: "translate(24 25)",
  vegetable: "translate(24 26) scale(.7)",
  salad: "translate(24 18) scale(.8)",
  soup: "translate(24 24)",
  dessert: "translate(24 16.5) scale(.55)",
  drink: "translate(24 24)",
};

// Drink has no solid food on it: the group only tints the liquid.
const DRINK_FILL: Partial<Record<FoodGroup, string>> = { fruit_sweet: C.coral, leafy: C.green, veg_mix: C.orange, broth: C.orange, bread: C.brown, noodles: C.yellow };
const drinkFill = computed(() => DRINK_FILL[group.value] ?? C.yellow);
</script>

<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 48 48"
    :width="size"
    :height="size"
    aria-hidden="true"
    :data-role="role"
    :data-group="group"
    fill="none"
    :stroke="C.ink"
    stroke-width="1.5"
    stroke-linejoin="round"
    stroke-linecap="round"
  >
    <!-- container -->
    <template v-if="role === 'main' || role === 'other'">
      <circle cx="24" cy="25" r="20" :fill="role === 'main' ? C.white : C.yellow" />
      <circle cx="24" cy="25" r="14" :fill="C.cream" />
    </template>
    <template v-else-if="role === 'vegetable'">
      <ellipse cx="24" cy="26" rx="20" ry="13" :fill="C.pale" />
      <ellipse cx="24" cy="26" rx="14.5" ry="8.8" :fill="C.cream" />
    </template>
    <template v-else-if="role === 'salad'">
      <path d="M4,22 H44 Q44,40 24,40 Q4,40 4,22Z" :fill="C.green" />
      <ellipse cx="24" cy="22" rx="20" ry="5" :fill="C.pale" />
    </template>
    <template v-else-if="role === 'soup'">
      <path d="M17,16 q-3,-3 0,-6 q3,-3 0,-6 M26,16 q-3,-3 0,-6 q3,-3 0,-6 M35,16 q-3,-3 0,-6 q3,-3 0,-6" stroke-width="1.5" />
      <path d="M5,24 H43 Q43,42 24,42 Q5,42 5,24Z" :fill="C.blue" />
      <ellipse cx="24" cy="24" rx="19" ry="4.8" :fill="C.yellow" />
      <path d="M17,42 v3 h14 v-3" :fill="C.cream" />
    </template>
    <template v-else-if="role === 'dessert'">
      <path d="M24,31 V40 M15,42 Q24,38 33,42" />
      <path d="M10,22 H38 Q38,33 24,33 Q10,33 10,22Z" :fill="C.coral" />
      <ellipse cx="24" cy="22" rx="14" ry="3.2" :fill="C.cream" />
    </template>
    <template v-else>
      <!-- drink -->
      <path d="M26,25 L31,4" :stroke="C.blue" stroke-width="3" />
      <path d="M13,11 H35 L32,43 H16Z" :fill="C.white" />
      <path d="M14,19 H34 L32,43 H16Z" :fill="drinkFill" />
      <rect x="19" y="23" width="6" height="6" rx="1.2" :fill="C.white" transform="rotate(-12 22 26)" />
    </template>

    <!-- contents -->
    <g v-if="role !== 'drink'" :transform="SPOT[role]">
      <template v-if="group === 'noodles'">
        <template v-for="d in strands" :key="d">
          <path :d="d" :stroke-width="4.6" />
          <path :d="d" :stroke="C.yellow" :stroke-width="2" />
        </template>
        <path d="M3,-12 L11,3 M7,-13 L14,1" :stroke="C.brown" stroke-width="1.8" />
      </template>
      <template v-else-if="group === 'rice'">
        <path d="M-11,7 Q-10,-9 0,-9 Q10,-9 11,7Z" :fill="C.white" />
        <path d="M-5,-2 l2,1 M2,-4 l2,1 M5,1 l2,1 M-2,3 l2,1 M-7,4 l2,1" stroke-width="1.2" />
      </template>
      <template v-else-if="group === 'poultry'">
        <path d="M2,3 L10,11" :stroke-width="4.5" />
        <path d="M2,3 L10,11" :stroke="C.cream" :stroke-width="2" />
        <circle cx="9" cy="8" r="2.6" :fill="C.cream" />
        <circle cx="12" cy="11" r="2.6" :fill="C.cream" />
        <path d="M-10,-3 C-10,-11 3,-11 5,-4 C6,2 0,6 -4,5 C-8,4 -10,1 -10,-3Z" :fill="C.orange" />
        <path d="M-6,-4 q2,-3 5,-2" stroke-width="1.2" />
      </template>
      <template v-else-if="group === 'red_meat'">
        <path d="M-11,0 C-11,-8 0,-11 7,-8 C12,-5 12,5 4,9 C-4,11 -11,7 -11,0Z" :fill="C.coral" />
        <path d="M-6,-2 q3,2 6,-1 M-3,4 q4,-3 8,-1" :stroke="C.cream" stroke-width="1.6" />
        <circle cx="6" cy="-3" r="2" :fill="C.cream" stroke-width="1.2" />
      </template>
      <template v-else-if="group === 'seafood'">
        <path d="M5,0 L12,-6 L12,6Z" :fill="C.blue" />
        <path d="M-11,0 Q-3,-9 6,0 Q-3,9 -11,0Z" :fill="C.blue" />
        <circle cx="-6" cy="-1" r="1.3" :fill="C.ink" stroke="none" />
        <path d="M-1,-4 q2,4 0,8" stroke-width="1.2" :stroke="C.white" />
      </template>
      <template v-else-if="group === 'tofu_egg'">
        <rect x="1" y="-2" width="11" height="11" rx="2" :fill="C.white" />
        <path d="M-11,-3 C-11,-10 -3,-11 -1,-8 C3,-8 4,-2 0,0 C-2,5 -10,5 -11,-3Z" :fill="C.white" />
        <circle cx="-5" cy="-3" r="3.2" :fill="C.yellow" />
      </template>
      <template v-else-if="group === 'leafy'">
        <path d="M-11,4 C-12,-6 -2,-11 3,-11 C5,-1 -2,6 -11,4Z" :fill="C.green" />
        <path d="M-9,2 L1,-8" stroke-width="1.2" />
        <path d="M0,9 C-2,-1 6,-8 11,-6 C12,3 8,9 0,9Z" :fill="C.pale" />
        <path d="M2,7 L9,-3" stroke-width="1.2" />
      </template>
      <template v-else-if="group === 'veg_mix'">
        <circle cx="-6" cy="-4" r="5" :fill="C.orange" />
        <circle cx="-6" cy="-4" r="1.5" :fill="C.yellow" stroke-width="1.2" />
        <circle cx="7" cy="-6" r="3.3" :fill="C.green" />
        <path d="M0,10 V6 H6 V10Z" :fill="C.pale" />
        <circle cx="-1" cy="4" r="3.6" :fill="C.green" />
        <circle cx="4" cy="2" r="3.8" :fill="C.green" />
        <circle cx="9" cy="5" r="3.2" :fill="C.green" />
      </template>
      <template v-else-if="group === 'broth'">
        <ellipse v-if="role !== 'soup'" cx="0" cy="0" rx="11" ry="9" :fill="C.yellow" />
        <circle cx="-5" cy="-1" r="2.4" :fill="C.green" />
        <circle cx="2" cy="2" r="2.4" :fill="C.coral" />
        <circle cx="7" cy="-2" r="2.2" :fill="C.white" />
      </template>
      <template v-else-if="group === 'bread'">
        <path d="M-11,3 H11 V6 Q11,9 8,9 H-8 Q-11,9 -11,6Z" :fill="C.brown" />
        <path d="M-11,1 Q-11,-10 0,-10 Q11,-10 11,1Z" :fill="C.orange" />
        <path d="M-4,-5 l2,1 M2,-6 l2,1 M5,-2 l2,1 M-6,-1 l2,1" :stroke="C.cream" stroke-width="1.4" />
      </template>
      <template v-else-if="group === 'fruit_sweet'">
        <path d="M-1,10 C-11,5 -11,-4 -5,-6 Q-1,-4 3,-6 C9,-4 9,5 -1,10Z" :fill="C.coral" />
        <path d="M-6,-6 L-1,-10 L4,-6" :fill="C.green" />
        <path d="M-5,-1 l.1 0 M0,1 l.1 0 M-3,4 l.1 0 M3,-1 l.1 0" :stroke="C.yellow" stroke-width="1.8" />
        <circle cx="9" cy="-4" r="3.6" :fill="C.blue" />
      </template>
      <template v-else>
        <circle cx="-6" cy="-3" r="4.5" :fill="C.coral" />
        <rect x="1" y="-11" width="9" height="9" rx="2" :fill="C.green" />
        <path d="M-1,10 L4,1 L9,10Z" :fill="C.yellow" />
      </template>
    </g>
  </svg>
</template>
