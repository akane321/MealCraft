<script setup lang="ts">
import { dishContainer, dishGroup } from "~/lib/dish-icon";

// Container = the dish's role (plate, small dish, bowl, shallow bowl, dessert cup, drink);
// contents = its main ingredient group. Drawn top-down, flat, one stroke weight.
const props = withDefaults(defineProps<{
  title: string;
  course?: string | null;
  roleId?: string | null;
  ingredients?: string[];
  size?: number;
}>(), { course: null, roleId: null, ingredients: () => [], size: 40 });

const container = computed(() => dishContainer(props.course, props.roleId));
const group = computed(() => dishGroup(props.title, props.ingredients));
// Contents are drawn for a 28-wide area; smaller containers shrink them.
const scale = computed(() => ({ plate: 1, dish: 0.78, bowl: 0.92, shallow: 1, dessert: 0.7, drink: 0.62 })[container.value]);
const offset = computed(() => (container.value === "drink" ? -2 : 0));
</script>

<template>
  <svg class="dish-icon" viewBox="0 0 48 48" :width="size" :height="size" aria-hidden="true" :data-container="container" :data-group="group">
    <!-- containers -->
    <template v-if="container === 'plate'">
      <circle cx="24" cy="24" r="21" fill="#fff" />
      <circle cx="24" cy="24" r="16" fill="none" class="hair" />
    </template>
    <template v-else-if="container === 'dish'">
      <circle cx="24" cy="24" r="16" fill="#fff" />
      <circle cx="24" cy="24" r="11.5" fill="none" class="hair" />
    </template>
    <template v-else-if="container === 'bowl'">
      <circle cx="24" cy="24" r="21" fill="#DCE5FB" />
      <circle cx="24" cy="24" r="16.5" fill="#F4F7FF" />
    </template>
    <template v-else-if="container === 'shallow'">
      <circle cx="24" cy="24" r="21" fill="#E3F4E9" />
      <circle cx="24" cy="24" r="17" fill="#fff" class="hair" />
    </template>
    <template v-else-if="container === 'dessert'">
      <rect x="6" y="6" width="36" height="36" rx="12" fill="#FDE6E3" />
      <circle cx="24" cy="24" r="12.5" fill="#fff" class="hair" />
    </template>
    <template v-else>
      <path d="M36 19h3a4 4 0 0 1 0 9h-3" fill="none" />
      <circle cx="22" cy="24" r="17" fill="#fff" />
      <circle cx="22" cy="24" r="13.5" fill="#E9C9A0" />
    </template>

    <!-- contents -->
    <g :transform="`translate(${24 + offset} 24) scale(${scale}) translate(-24 -24)`">
      <template v-if="group === 'noodles'">
        <ellipse cx="24" cy="24" rx="13" ry="10.5" fill="#F6DFA0" />
        <path d="M13 21c3-3 5 3 8 0s5 3 8 0 4 1 6-1M13 26c3-3 5 3 8 0s5 3 8 0 4 1 6-1" fill="none" />
        <circle cx="30" cy="19" r="2.6" fill="#F0675C" />
        <circle cx="17" cy="29" r="1.6" fill="#4FB86E" />
      </template>
      <template v-else-if="group === 'rice'">
        <path d="M11 27c0-9 6-14 13-14s13 5 13 14c0 3-26 3-26 0z" fill="#FFF6E3" />
        <path d="M18 21l2 1M25 18l2 1M29 24l2 1M21 26l2 1M16 26l1.5.5" fill="none" />
        <circle cx="32" cy="17" r="2" fill="#4FB86E" />
      </template>
      <template v-else-if="group === 'poultry'">
        <ellipse cx="20" cy="20" rx="10" ry="7.5" transform="rotate(45 20 20)" fill="#E0A150" />
        <path d="M26.5 26.5l6 6" fill="none" />
        <circle cx="34" cy="31" r="2.2" fill="#fff" /><circle cx="31" cy="34" r="2.2" fill="#fff" />
      </template>
      <template v-else-if="group === 'red-meat'">
        <path d="M10 23c0-6 6-10 13-9s14 3 14 9-6 11-14 10-13-4-13-10z" fill="#D2605A" />
        <path d="M15 23c0-3 4-5 8-4s8 2 8 4" fill="none" class="soft" />
        <circle cx="19" cy="27" r="2.6" fill="#fff" />
      </template>
      <template v-else-if="group === 'seafood'">
        <path d="M9 24c5-9 15-10 21-2l6-5v14l-6-5c-6 8-16 7-21-2z" fill="#7FB6E8" />
        <circle cx="16" cy="23" r="1.3" fill="#2A2A48" stroke="none" />
        <path d="M22 18v12" fill="none" class="soft" />
      </template>
      <template v-else-if="group === 'tofu-egg'">
        <path d="M10 21c0-6 7-9 12-7 6-2 12 2 11 8s-4 9-11 8-12-3-12-9z" fill="#fff" />
        <circle cx="21" cy="22" r="5.5" fill="#F2C14E" />
        <rect x="27" y="26" width="9" height="9" rx="2" fill="#FFF6E3" />
      </template>
      <template v-else-if="group === 'greens'">
        <g fill="#4FB86E">
          <path d="M24 35C14 31 12 19 24 12c12 7 10 19 0 23z" />
          <path d="M24 35C14 31 12 19 24 12c12 7 10 19 0 23z" transform="rotate(-42 24 35) scale(.8) translate(6 7)" />
          <path d="M24 35C14 31 12 19 24 12c12 7 10 19 0 23z" transform="rotate(42 24 35) scale(.8) translate(6 7)" />
        </g>
        <path d="M24 34V17" fill="none" class="soft" />
      </template>
      <template v-else-if="group === 'veg'">
        <path d="M27 16l9 5-14 14z" fill="#F2994A" />
        <path d="M34 15l-3 4M37 18l-4 2" fill="none" stroke="#4FB86E" />
        <circle cx="18" cy="27" r="7.5" fill="#F0675C" />
        <path d="M15 20l3 2 3-2" fill="none" stroke="#4FB86E" />
      </template>
      <template v-else-if="group === 'broth'">
        <circle cx="24" cy="24" r="12.5" fill="#E7A94A" />
        <path d="M16 22c3-2 5 2 8 0s5 2 8 0M18 28c2-1.5 4 1 6 0s4 1 6 0" fill="none" class="soft" />
        <circle cx="19" cy="18" r="1.6" fill="#4FB86E" /><circle cx="29" cy="20" r="1.6" fill="#4FB86E" /><circle cx="26" cy="29" r="1.6" fill="#4FB86E" />
      </template>
      <template v-else-if="group === 'bread'">
        <path d="M12 34V21c-4-1-4-9 2-10h20c6 1 6 9 2 10v13z" fill="#EBC483" />
        <path d="M16 31V21c-2-1-1-5 2-5.5h12c3 .5 4 4.5 2 5.5v10z" fill="#F8E3B4" class="soft" />
      </template>
      <template v-else-if="group === 'fruit'">
        <circle cx="24" cy="24" r="12" fill="#F6A33C" />
        <circle cx="24" cy="24" r="8.5" fill="#FFD27A" class="soft" />
        <path d="M24 16v16M16 24h16M18.3 18.3l11.4 11.4M29.7 18.3L18.3 29.7" fill="none" class="soft" />
      </template>
      <template v-else>
        <circle cx="18" cy="20" r="5.5" fill="#F0675C" />
        <circle cx="30" cy="22" r="5.5" fill="#F2C14E" />
        <circle cx="23" cy="31" r="5.5" fill="#4FB86E" />
      </template>
    </g>

    <!-- container outline last so the rim stays crisp -->
    <circle v-if="container === 'plate'" cx="24" cy="24" r="21" fill="none" />
    <circle v-else-if="container === 'dish'" cx="24" cy="24" r="16" fill="none" />
    <circle v-else-if="container === 'bowl'" cx="24" cy="24" r="21" fill="none" />
    <circle v-else-if="container === 'shallow'" cx="24" cy="24" r="21" fill="none" />
    <rect v-else-if="container === 'dessert'" x="6" y="6" width="36" height="36" rx="12" fill="none" />
    <circle v-else cx="22" cy="24" r="17" fill="none" />
  </svg>
</template>

<style scoped>
.dish-icon { flex: none; display: block; overflow: visible; stroke: #2A2A48; stroke-width: 1.5; stroke-linejoin: round; stroke-linecap: round; }
.dish-icon :deep(*) { vector-effect: non-scaling-stroke; }
.hair { stroke: #E6E0D4; stroke-width: 1; }
.soft { stroke-opacity: 0.45; }
</style>
