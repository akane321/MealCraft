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
// Thin bars, at most 8 units wide, centred in their day.
const barWidth = computed(() => Math.min(slot.value * 0.5, 8));

// Nothing to draw: no series, or every day at zero.
const empty = computed(() => totals.value.every(total => !total));
const bars = computed(() => props.days.flatMap((day, index) => {
  let top = HEIGHT;
  return props.series.flatMap((item) => {
    const value = item.values[index] ?? 0;
    if (!value) return [];
    const height = (value / max.value) * HEIGHT;
    top -= height;
    return [{ key: `${day}-${item.name}`, x: index * slot.value + (slot.value - barWidth.value) / 2, y: top, width: barWidth.value, height, color: item.color, title: `${shortDay(day)}: ${value} ${item.name.replaceAll("_", " ")}` }];
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
      <text v-if="!empty" x="0" y="-2" class="tick">{{ max }}</text>
      <rect v-for="bar in bars" :key="bar.key" :x="bar.x" :y="bar.y" :width="bar.width" :height="bar.height" :fill="bar.color" rx="3">
        <title>{{ bar.title }}</title>
      </rect>
      <template v-for="(day, index) in days" :key="day">
        <text v-if="index === 0 || index === days.length - 1 || index === Math.floor(days.length / 2)" :x="index * slot + slot / 2" :y="HEIGHT + 16" class="tick" text-anchor="middle">{{ shortDay(day) }}</text>
      </template>
    </svg>
    <figcaption v-if="!empty" class="legend">
      <span v-for="item in series" :key="item.name"><i :style="{ background: item.color }" />{{ item.name.replaceAll("_", " ") }}</span>
    </figcaption>
    <figcaption v-else class="empty-note"><UIcon name="i-lucide-chart-no-axes-column" aria-hidden="true" />Nothing recorded in these two weeks.</figcaption>
  </figure>
</template>

<style scoped>
/* Calm series: violet for counts, lilac for the good statuses, red only for failures. */
.ops-chart { margin: 0; --sage: #c4b5fd; --accent: #8b5cf6; --danger: #f87171; --c-green: #ddd6fe; --c-blue: #a5b4fc; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
.axis { stroke: #ececef; }
.grid { stroke: #f0f0f2; stroke-dasharray: 3 4; }
.tick { fill: #a1a1aa; font-size: 11px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 10px; color: var(--t3); font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 8px; height: 8px; border-radius: 50%; }
/* No data: the note sits in the middle of the plot, with no tick or legend. */
.ops-chart { position: relative; }
.empty-note { position: absolute; left: 0; right: 0; top: 34%; display: flex; flex-direction: column; align-items: center; gap: 6px; margin: 0; color: #a1a1aa; font-size: 13px; text-align: center; }
.empty-note .iconify { width: 18px; height: 18px; }
</style>
