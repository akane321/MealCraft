<script setup lang="ts">
// Where a success moment settles: a white pill with the mark (ring, check, leaf) and what was done.
// `waiting` keeps it invisible (but laid out) while the success card collapses onto it.
defineProps<{ text: string; waiting?: boolean }>();
</script>

<template>
  <div class="stamp" :class="{ waiting }" role="status" data-stamp><span class="tile"><MotionMarkAnim v-if="!waiting" state="done" /></span>{{ text }}</div>
</template>

<style scoped>
.stamp { position: sticky; bottom: 8px; z-index: 2; align-self: flex-start; display: inline-flex; align-items: center; gap: 9px; height: 36px; padding: 0 14px 0 4px; border: 1px solid #ececef; border-radius: 999px; background: #fff; color: #18181b; font-size: 13.5px; font-weight: 500; box-shadow: 0 10px 28px -12px rgba(16, 16, 20, 0.28), 0 1px 2px rgba(16, 16, 20, 0.06); }
.stamp.waiting { visibility: hidden; }
.tile { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 999px; background: #18181b; color: #fff; }
.tile .mark-anim { width: 22px; height: 22px; }
</style>
