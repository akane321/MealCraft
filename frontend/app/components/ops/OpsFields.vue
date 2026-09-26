<script setup lang="ts">
import { humanKey } from "~/lib/ops";

// A stored record as label/value rows; nested values fall back to formatted JSON so nothing is hidden.
defineProps<{ data: Record<string, unknown> }>();

function isPlain(value: unknown) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}
</script>

<template>
  <dl class="ops-fields">
    <template v-for="(value, key) in data" :key="key">
      <dt>{{ humanKey(String(key)) }}</dt>
      <dd v-if="isPlain(value)" :class="{ mono: typeof value === 'string' && /^[0-9a-f]{16,}$/.test(value) }">{{ value === null || value === "" ? "—" : value }}</dd>
      <dd v-else><pre>{{ JSON.stringify(value, null, 2) }}</pre></dd>
    </template>
  </dl>
</template>

<style scoped>
.ops-fields { display: grid; grid-template-columns: minmax(120px, 34%) 1fr; gap: 8px 16px; margin: 0; font-size: 13px; }
dt { color: var(--t3); }
dd { margin: 0; min-width: 0; color: var(--ivory); overflow-wrap: anywhere; }
.mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; color: var(--t2); }
pre { margin: 0; max-height: 260px; overflow: auto; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--ink); color: var(--t2); font-size: 11.5px; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
