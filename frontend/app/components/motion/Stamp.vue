<script setup lang="ts">
defineProps<{ text: string }>();
</script>

<template>
  <!-- A confirmed change: the ring closes into the plate, a check, then the leaf. -->
  <div class="stamp" role="status"><span class="tile"><MotionMarkAnim state="done" /></span>{{ text }}</div>
</template>

<style scoped>
.stamp { position: sticky; bottom: 8px; z-index: 2; align-self: flex-start; display: inline-flex; align-items: center; gap: 8px; height: 32px; padding: 0 12px 0 4px; border-radius: 999px; background: var(--c-ok-bg, #ecfdf3); color: var(--c-green-text, #067647); font-size: 13px; font-weight: 500; box-shadow: 0 6px 20px -8px rgba(16, 16, 20, 0.25); animation: mc-rise 320ms cubic-bezier(0.22, 1, 0.36, 1) both; }
.tile { width: 24px; height: 24px; display: grid; place-items: center; border-radius: 999px; background: #18181b; color: #fff; }
.tile .mark-anim { width: 20px; height: 20px; }
</style>
