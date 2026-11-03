<script setup lang="ts">
import { formatWhen, humanKey } from "~/lib/ops";

// A stored record as label/value rows; nested values fall back to formatted JSON so nothing is hidden.
defineProps<{ data: Record<string, unknown> }>();

// "weekly_budget_sgd" reads "Weekly budget (S$)"; a stored timestamp reads like the tables' dates.
const label = (key: string) => humanKey(key).replace(/ sgd$/i, " (S$)");
const isTime = (value: unknown): value is string => typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value);

function isPlain(value: unknown) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}
</script>

<template>
  <dl class="ops-fields">
    <template v-for="(value, key) in data" :key="key">
      <dt>{{ label(String(key)) }}</dt>
      <dd v-if="isTime(value)" :title="value">{{ formatWhen(value) }}</dd>
      <!-- A long hash stays on one line, cut, with the whole value as its tooltip; a number lines up on the right. -->
      <dd v-else-if="isPlain(value) && typeof value === 'string' && /^[0-9a-f]{16,}$/.test(value)" class="mono" :title="value">{{ value }}</dd>
      <dd v-else-if="isPlain(value)" :class="{ num: typeof value === 'number' }">{{ value === null || value === "" ? "—" : value }}</dd>
      <dd v-else><pre>{{ JSON.stringify(value, null, 2) }}</pre></dd>
    </template>
  </dl>
</template>

<style scoped>
/* A compact label column with the value right beside it. */
.ops-fields { display: grid; grid-template-columns: 148px minmax(0, 1fr); gap: 8px 12px; margin: 0; font-size: 13px; line-height: 18px; }
dt { color: #71717a; }
dd { margin: 0; min-width: 0; color: #27272a; overflow-wrap: anywhere; }
.mono { overflow: hidden; color: #52525b; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; white-space: nowrap; text-overflow: ellipsis; overflow-wrap: normal; }
.num { font-variant-numeric: tabular-nums; }
pre { margin: 0; max-height: 260px; overflow: auto; padding: 10px 12px; border: 1px solid #ececef; border-radius: 10px; background: #fafafa; color: #3f3f46; font: 12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
