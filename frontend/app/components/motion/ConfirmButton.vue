<script setup lang="ts">
import { motion } from "motion-v";

// A confirm action. Pressed, it gives on a spring; while its request runs it reshapes (a layout spring) into a pill
// whose ring fills; a failure shakes it once and it comes back. Success is played by the page (MotionSuccess),
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
    <motion.span v-if="busy" layout="position" class="spinner" aria-hidden="true">
      <svg viewBox="0 0 20 20"><circle class="track" cx="10" cy="10" r="7.5" /><circle class="fill" cx="10" cy="10" r="7.5" pathLength="100" /></svg>
    </motion.span>
    <motion.span layout="position" class="text">{{ busy && busyLabel ? busyLabel : label }}</motion.span>
  </motion.button>
</template>

<style scoped>
.mc-confirm { position: relative; display: inline-flex; align-items: center; gap: 9px; overflow: hidden; }
/* While it runs: a soft light passes over the pill. */
.mc-confirm.busy::after { content: ""; position: absolute; inset: 0; background: linear-gradient(100deg, transparent 30%, rgba(255, 255, 255, 0.16) 50%, transparent 70%) 0 0 / 250% 100%; animation: sheen 1.6s linear infinite; pointer-events: none; }
.spinner { width: 18px; height: 18px; flex: none; display: grid; place-items: center; }
.spinner svg { width: 18px; height: 18px; transform: rotate(-90deg); }
.spinner circle { fill: none; stroke-width: 2.4; stroke-linecap: round; }
.track { stroke: rgba(255, 255, 255, 0.22); }
/* The ring fills toward closed while the request runs (it never closes on its own: success closes it). */
.fill { stroke: #fff; stroke-dasharray: 100 100; stroke-dashoffset: 92; animation: fill 9s cubic-bezier(0.1, 0.7, 0.2, 1) forwards, spin 1.4s linear infinite; transform-origin: 10px 10px; }
.text { white-space: nowrap; }
.shake { animation: shake 480ms cubic-bezier(0.36, 0.07, 0.19, 0.97); box-shadow: 0 0 0 4px rgba(240, 68, 56, 0.22) !important; }
@keyframes fill { to { stroke-dashoffset: 14; } }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes sheen { from { background-position: 120% 0; } to { background-position: -130% 0; } }
@keyframes shake { 10%, 90% { transform: translateX(-2px); } 20%, 80% { transform: translateX(5px); } 30%, 50%, 70% { transform: translateX(-9px); } 40%, 60% { transform: translateX(9px); } }
@media (prefers-reduced-motion: reduce) { .fill, .mc-confirm.busy::after { animation: none; } }
</style>
