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
  <div v-else-if="state === 'error'" class="panel-state error mc-empty" role="alert">
    <div class="mc-empty-art" aria-hidden="true">
      <span><span class="mc-tile" data-tone="rose"><UIcon name="i-lucide-circle-alert" /></span></span>
    </div>
    <h2 v-if="title" class="mc-serif">{{ title }}</h2>
    <p>{{ errorText ?? "This couldn't be loaded." }}</p>
    <button type="button" class="mc-btn secondary sm" @click="emit('retry')">Try again</button>
  </div>
  <div v-else class="panel-state empty mc-empty">
    <div class="mc-empty-art" aria-hidden="true">
      <span><span class="mc-tile" data-tone="violet"><UIcon name="i-lucide-utensils" /></span></span>
    </div>
    <h2 v-if="title" class="mc-serif">{{ title }}</h2>
    <p>{{ emptyText }}</p>
  </div>
</template>

<style scoped>
.panel-state { display: flex; flex-direction: column; gap: 10px; padding: 20px 16px; color: var(--c-muted); font-size: 14px; }
.panel-state h2 { margin: 0 0 4px; font-size: 16px; line-height: 22px; font-weight: 600; color: var(--mc-strong); }
.panel-state p { margin: 0; }
.panel-state.empty, .panel-state.error { gap: 0; margin-top: 12vh; padding: 24px; }
.panel-state.empty h2, .panel-state.error h2 { margin: 16px 0 0; }
.panel-state.empty p, .panel-state.error p { max-width: 300px; margin-top: 6px; color: #71717a; line-height: 20px; }
.panel-state.error .mc-empty-art > span { background: #fff1f3; }
.panel-state.error button { margin-top: 16px; }

.skeleton {
  height: 54px;
  border-radius: 8px;
  background: linear-gradient(100deg, #f4f4f5 30%, #fafafa 50%, #f4f4f5 70%);
  background-size: 260% 100%;
  animation: mc-shimmer 1400ms var(--ease) infinite;
}
.skeleton:first-of-type { height: 128px; }

@keyframes mc-shimmer {
  from { background-position: 140% 0; }
  to { background-position: -40% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
}
</style>
