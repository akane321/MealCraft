<script setup lang="ts">
import { motion } from "motion-v";

// A confirm action. Pressed, it gives on a spring; while its request runs it reshapes (a layout spring) into a pill
// with the loader's dots; a failure shakes it once and it comes back. Success is played by the page (MotionSuccess),
// growing out of this button, since the card holding it goes.
const props = defineProps<{ busy?: boolean; failed?: boolean; disabled?: boolean; label: string; busyLabel?: string }>();
defineEmits<{ press: [event: MouseEvent] }>();
const shake = ref(false);
watch(() => props.busy, (now, before) => {
  if (before && !now && props.failed) {
    shake.value = true;
    setTimeout(() => { shake.value = false; }, 520);
  }
});
const spring = { type: "spring", stiffness: 520, damping: 34, mass: 0.9 } as const;
</script>

<template>
  <motion.button
    type="button"
    class="mc-btn primary mc-confirm"
    :class="{ shake, busy }"
    :disabled="disabled"
    :aria-busy="busy || undefined"
    layout
    :transition="{ layout: spring }"
    :while-press="disabled ? undefined : { scale: 0.95 }"
    :while-hover="disabled ? undefined : { y: -1 }"
    @click="$emit('press', $event)"
  >
    <motion.span v-if="busy" layout="position" class="busy-dots" :initial="{ opacity: 0, scale: 0.6 }" :animate="{ opacity: 1, scale: 1 }"><MotionLoader /></motion.span>
    <motion.span layout="position" class="text">{{ busy && busyLabel ? busyLabel : label }}</motion.span>
  </motion.button>
</template>

<style scoped>
.mc-confirm { position: relative; display: inline-flex; align-items: center; gap: 9px; overflow: hidden; }
/* While it runs: a soft light passes over the pill. */
.mc-confirm.busy::after { content: ""; position: absolute; inset: 0; background: linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, 0.16) 50%, transparent 70%) 0 0 / 250% 100%; animation: sheen 1.6s linear infinite; pointer-events: none; }
.busy-dots { flex: none; display: inline-flex; }
.text { white-space: nowrap; }
.shake { animation: shake 480ms cubic-bezier(0.36, 0.07, 0.19, 0.97); box-shadow: 0 0 0 4px rgba(240, 68, 56, 0.22) !important; }
@keyframes sheen { from { background-position: 120% 0; } to { background-position: -130% 0; } }
@keyframes shake { 10%, 90% { transform: translateX(-2px); } 20%, 80% { transform: translateX(5px); } 30%, 50%, 70% { transform: translateX(-9px); } 40%, 60% { transform: translateX(9px); } }
@media (prefers-reduced-motion: reduce) { .mc-confirm.busy::after { animation: none; } }
</style>
