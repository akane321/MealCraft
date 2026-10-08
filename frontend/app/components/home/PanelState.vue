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
    <button type="button" class="mc-btn secondary" @click="emit('retry')">Try again</button>
  </div>
  <div v-else class="panel-state empty">
    <svg class="art" viewBox="0 0 96 64" aria-hidden="true">
      <ellipse cx="48" cy="56" rx="30" ry="4" fill="#f1ede5" stroke="none" />
      <circle cx="48" cy="32" r="22" fill="#fff" /><circle cx="48" cy="32" r="14" fill="#fff4e0" />
      <path d="M12 12v14a4 4 0 0 0 4 4v22M16 12v10M20 12v14a4 4 0 0 1-4 4" fill="none" />
      <path d="M82 12c-5 3-6 12-4 18h4v22" fill="none" /><circle cx="48" cy="32" r="4" fill="#f0675c" />
    </svg>
    <h2 v-if="title" class="mc-serif">{{ title }}</h2>
    <p>{{ emptyText }}</p>
  </div>
</template>

<style scoped>
.panel-state { display: flex; flex-direction: column; gap: 12px; padding: 20px 16px; color: var(--c-muted); font-size: 14px; }
.panel-state h2 { margin: 0 0 4px; font-size: 18px; line-height: 24px; font-weight: 700; color: var(--c-ink); }
.panel-state p { margin: 0; }
.panel-state.empty { align-items: flex-start; }
.art { width: 96px; height: 64px; fill: none; stroke: #2a2a48; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.panel-state.error { gap: 14px; align-items: flex-start; color: var(--mc-text-2); }
.panel-state.error p { margin: 0; line-height: 1.6; }

.skeleton {
  height: 54px;
  border-radius: 16px;
  border: 1px solid var(--c-line);
  background:
    linear-gradient(100deg, transparent 20%, rgba(42, 42, 72, 0.06) 40%, transparent 60%)
    rgba(42, 42, 72, 0.02);
  background-size: 260% 100%;
  animation: mc-shimmer 1400ms var(--mc-ease) infinite;
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
