<script setup lang="ts">
defineProps<{
  /** The panel's own heading, so a loading drawer still says what it is. */
  title: string;
  /** `loading` while a request is in flight, `error` when one failed, `empty` when there is nothing yet. */
  state: "loading" | "error" | "empty";
  /** What to say when there is nothing yet. */
  emptyText: string;
  /** What to say when the request failed. */
  errorText?: string;
  /** How many skeleton rows to draw; roughly the shape of the real content. */
  rows?: number;
}>();
const emit = defineEmits<{ retry: [] }>();
</script>

<template>
  <div v-if="state === 'loading'" class="panel-state" aria-busy="true">
    <h2 v-if="title" class="mc-serif">{{ title }}</h2>
    <p class="visually-hidden">Loading</p>
    <span v-for="row in rows ?? 4" :key="row" class="skeleton" aria-hidden="true" />
  </div>
  <div v-else-if="state === 'error'" class="panel-state error" role="alert">
    <h2 v-if="title" class="mc-serif">{{ title }}</h2>
    <p>{{ errorText ?? "This couldn't be loaded." }}</p>
    <button type="button" class="mc-pill" @click="emit('retry')">Try again</button>
  </div>
  <div v-else class="panel-state empty">
    <h2 v-if="title" class="mc-serif">{{ title }}</h2>
    <p>{{ emptyText }}</p>
  </div>
</template>

<style scoped>
.panel-state { display: flex; flex-direction: column; gap: 12px; padding: 22px; color: var(--mc-text-3); font-size: 13px; }
.panel-state h2 { margin: 0 0 4px; font-size: 22px; font-weight: 400; color: var(--mc-ivory); }
.panel-state p { margin: 0; line-height: 1.6; }
.panel-state.error { gap: 14px; align-items: flex-start; color: var(--mc-text-2); }
.panel-state.error p { margin: 0; line-height: 1.6; }

.skeleton {
  height: 54px;
  border-radius: 14px;
  border: 1px solid var(--mc-line);
  background:
    linear-gradient(100deg, transparent 20%, rgba(242, 237, 228, 0.07) 40%, transparent 60%)
    rgba(242, 237, 228, 0.03);
  background-size: 260% 100%;
  animation: mc-shimmer 1400ms var(--mc-ease) infinite;
}
.skeleton:first-of-type { height: 96px; }

@keyframes mc-shimmer {
  from { background-position: 140% 0; }
  to { background-position: -40% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}
</style>
