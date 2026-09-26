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
      <text x="0" y="-2" class="tick">{{ formatSeconds(max) }}</text>
      <g v-for="item in series" :key="item.name">
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
    <figcaption class="legend">
      <template v-if="empty">No timed planning runs in these two weeks.</template>
      <span v-for="item in series" v-else :key="item.name"><i :style="{ background: item.color }" />{{ item.name }}</span>
    </figcaption>
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
.legend i { width: 12px; height: 2px; border-radius: 1px; }
</style>
