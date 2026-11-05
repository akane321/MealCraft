<script setup lang="ts">
// The confirm motion, drawn from the MealCraft mark: `busy` is a ring turning while the request runs;
// `done` closes the ring into the plate, draws a check in it and grows the leaf (under 700 ms).
defineProps<{ state: "busy" | "done" }>();
</script>

<template>
  <svg class="mark-anim" :class="state" viewBox="-1.5 0.5 35 35" aria-hidden="true">
    <circle class="ring" cx="16" cy="18" r="9.5" pathLength="100" />
    <template v-if="state === 'done'">
      <path class="check" d="M11.6 18.3l3.1 3.1 5.8-6.2" pathLength="100" />
      <path class="sprout" d="M15.2 9.2c1-4.6 5.4-6.6 9.4-5.6-.9 4.2-5 6.9-9.4 5.6z" />
    </template>
  </svg>
</template>

<style scoped>
.mark-anim { width: 18px; height: 18px; flex: none; overflow: visible; }
.ring, .check { fill: none; stroke: currentColor; stroke-width: 2.6; stroke-linecap: round; stroke-linejoin: round; }
.busy .ring { stroke-dasharray: 30 100; transform-box: fill-box; transform-origin: center; animation: mc-ring 800ms linear infinite; }
.done .ring { stroke-dasharray: 100 100; animation: mc-close 260ms cubic-bezier(0.22, 1, 0.36, 1) both; }
.check { stroke-dasharray: 100 100; animation: mc-draw 220ms ease-out 230ms both; }
.sprout { fill: #e8775a; transform-box: fill-box; transform-origin: 0% 100%; animation: mc-leaf 260ms cubic-bezier(0.34, 1.56, 0.64, 1) 420ms both; }
@keyframes mc-ring { to { transform: rotate(360deg); } }
@keyframes mc-close { from { stroke-dashoffset: 70; } to { stroke-dashoffset: 0; } }
@keyframes mc-draw { from { stroke-dashoffset: 100; } to { stroke-dashoffset: 0; } }
@keyframes mc-leaf { from { transform: scale(0); } to { transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { .ring, .check, .sprout { animation: none !important; } }
</style>
