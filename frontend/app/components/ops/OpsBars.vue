<script setup lang="ts">
import { niceMax } from "~/lib/ops";

// Stacked daily bars drawn in plain SVG; a charting library would outweigh the whole console.
const props = defineProps<{
  /** Accessible name of the chart. */
  label: string;
  days: string[];
  series: Array<{ name: string; color: string; values: number[] }>;
}>();

const WIDTH = 560;
const HEIGHT = 150;
const totals = computed(() => props.days.map((_, index) => props.series.reduce((sum, item) => sum + (item.values[index] ?? 0), 0)));
const max = computed(() => niceMax(Math.max(0, ...totals.value)));
const slot = computed(() => WIDTH / Math.max(props.days.length, 1));

const bars = computed(() => props.days.flatMap((day, index) => {
  let top = HEIGHT;
  return props.series.flatMap((item) => {
    const value = item.values[index] ?? 0;
    if (!value) return [];
    const height = (value / max.value) * HEIGHT;
    top -= height;
    return [{ key: `${day}-${item.name}`, x: index * slot.value + slot.value * 0.18, y: top, width: slot.value * 0.64, height, color: item.color, title: `${shortDay(day)}: ${value} ${item.name.replaceAll("_", " ")}` }];
  });
}));

function shortDay(day: string) {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
}
</script>

<template>
  <figure class="ops-chart">
    <svg :viewBox="`0 -12 ${WIDTH} ${HEIGHT + 32}`" role="img" :aria-label="label">
      <line x1="0" :y1="HEIGHT" :x2="WIDTH" :y2="HEIGHT" class="axis" />
      <line x1="0" y1="0" :x2="WIDTH" y2="0" class="grid" />
      <text x="0" y="-2" class="tick">{{ max }}</text>
      <rect v-for="bar in bars" :key="bar.key" :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height" :fill="bar.color" rx="2">
        <title>{{ bar.title }}</title>
      </rect>
      <template v-for="(day, index) in days" :key="day">
        <text v-if="index === 0 || index === days.length - 1 || index === Math.floor(days.length / 2)" :x="index * slot + slot / 2" :y="HEIGHT + 16" class="tick" text-anchor="middle">{{ shortDay(day) }}</text>
      </template>
    </svg>
    <figcaption v-if="series.length" class="legend">
      <span v-for="item in series" :key="item.name"><i :style="{ background: item.color }" />{{ item.name.replaceAll("_", " ") }}</span>
    </figcaption>
    <figcaption v-else class="legend">Nothing recorded in these two weeks.</figcaption>
  </figure>
</template>

<style scoped>
.ops-chart { margin: 0; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
.axis { stroke: var(--border); }
.grid { stroke: rgba(242, 237, 228, 0.06); stroke-dasharray: 3 4; }
.tick { fill: var(--t3); font-size: 11px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 10px; color: var(--t3); font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 9px; height: 9px; border-radius: 2px; }
</style>
