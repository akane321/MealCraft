<script setup lang="ts">
import { formatSeconds, linePath, niceMax } from "~/lib/ops";

const props = defineProps<{
  label: string;
  days: string[];
  series: Array<{ name: string; color: string; values: Array<number | null> }>;
}>();

const WIDTH = 560;
const HEIGHT = 150;
const max = computed(() => niceMax(Math.max(0, ...props.series.flatMap(item => item.values.filter((value): value is number => value !== null)))));
const step = computed(() => (props.days.length > 1 ? WIDTH / (props.days.length - 1) : 0));
// Days with no timed run leave a gap; a dashed line joins the points either side, so a gap reads as "no runs".
function bridges(values: Array<number | null>) {
  const points = values.flatMap((value, index) => (value === null ? [] : [{ index, value }]));
  return points.slice(1).map((to, i) => ({ from: points[i]!, to })).filter(pair => pair.to.index - pair.from.index > 1);
}
const gapped = computed(() => props.series.some(item => bridges(item.values).length));
const y = (value: number) => HEIGHT - (value / max.value) * HEIGHT;
const empty = computed(() => props.series.every(item => item.values.every(value => value === null)));

function shortDay(day: string) {
  return new Date(`${day}T00:00:00`).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
}
</script>

<template>
  <figure class="ops-chart">
    <svg :viewBox="`-4 -12 ${WIDTH + 8} ${HEIGHT + 32}`" role="img" :aria-label="label">
      <line x1="0" :y1="HEIGHT" :x2="WIDTH" :y2="HEIGHT" class="axis" />
      <line x1="0" y1="0" :x2="WIDTH" y2="0" class="grid" />
      <text v-if="!empty" x="0" y="-2" class="tick">{{ formatSeconds(max) }}</text>
      <g v-for="item in series" :key="item.name">
        <line v-for="gap in bridges(item.values)" :key="gap.from.index" :x1="gap.from.index * step" :y1="y(gap.from.value)" :x2="gap.to.index * step" :y2="y(gap.to.value)" class="gap" />
        <path :d="linePath(item.values, max, WIDTH, HEIGHT)" fill="none" :stroke="item.color" stroke-width="2" stroke-linejoin="round" />
        <template v-for="(value, index) in item.values" :key="index">
          <circle v-if="value !== null" :cx="index * step" :cy="HEIGHT - (value / max) * HEIGHT" r="3" :fill="item.color">
            <title>{{ shortDay(days[index] ?? "") }}: {{ item.name }} {{ formatSeconds(value) }}</title>
          </circle>
        </template>
      </g>
      <template v-for="(day, index) in days" :key="day">
        <text v-if="index === 0 || index === days.length - 1 || index === Math.floor(days.length / 2)" :x="index * step" :y="HEIGHT + 16" class="tick" text-anchor="middle">{{ shortDay(day) }}</text>
      </template>
    </svg>
    <figcaption v-if="empty" class="empty-note"><UIcon name="i-lucide-chart-no-axes-column" aria-hidden="true" />No timed planning runs in these two weeks.</figcaption>
    <figcaption v-else class="legend">
      <span v-for="item in series" :key="item.name"><i :style="{ background: item.color }" />{{ item.name }}</span>
      <span v-if="gapped"><i class="gap-key" />no timed runs</span>
    </figcaption>
  </figure>
</template>

<style scoped>
.ops-chart { margin: 0; --sage: #8b5cf6; --accent: #c4b5fd; --danger: #f87171; --c-green: #ddd6fe; --c-blue: #a5b4fc; }
.gap { stroke: #d4d4d8; stroke-width: 1.5; stroke-dasharray: 3 4; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
.axis { stroke: #ececef; }
.grid { stroke: #f0f0f2; stroke-dasharray: 3 4; }
.tick { fill: #a1a1aa; font-size: 11px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 10px; color: var(--t3); font-size: 12px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 8px; height: 8px; border-radius: 50%; }
.legend .gap-key { width: 14px; height: 0; border-radius: 0; border-top: 1.5px dashed #d4d4d8; }
/* No data: the note sits in the middle of the plot, with no tick or legend. */
.ops-chart { position: relative; }
.empty-note { position: absolute; left: 0; right: 0; top: 34%; display: flex; flex-direction: column; align-items: center; gap: 6px; margin: 0; color: #a1a1aa; font-size: 13px; text-align: center; }
.empty-note .iconify { width: 18px; height: 18px; }
</style>
