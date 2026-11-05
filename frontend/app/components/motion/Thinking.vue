<script setup lang="ts">
import { AnimatePresence, motion } from "motion-v";

// A reply on its way: the MealCraft plate filled with a living gradient, the leaf circling it, and a shimmering
// line that walks through what is being done (it stays on the last step until the reply comes).
const props = withDefaults(defineProps<{ steps?: string[] }>(), { steps: () => ["Thinking"] });
const step = ref(0);
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  timer = setInterval(() => {
    if (step.value < props.steps.length - 1) step.value += 1;
  }, 2100);
});
onBeforeUnmount(() => clearInterval(timer));
watch(() => props.steps.join("|"), () => { step.value = 0; });
</script>

<template>
  <span class="think">
    <span class="mark" aria-hidden="true">
      <span class="glow" />
      <MotionOrb class="fill" :size="25" />
      <svg viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="12.5" fill="none" stroke="#18181b" stroke-width="2.4" />
        <g class="orbit"><path d="M17.2 5.6c1-4.6 5.4-6.6 9.4-5.6-.9 4.2-5 6.9-9.4 5.6z" fill="#e8775a" /></g>
      </svg>
    </span>
    <span class="label">
      <AnimatePresence mode="wait" :initial="false">
        <motion.span
          :key="step"
          class="shimmer"
          :initial="{ opacity: 0, y: 7, filter: 'blur(4px)' }"
          :animate="{ opacity: 1, y: 0, filter: 'blur(0px)' }"
          :exit="{ opacity: 0, y: -7, filter: 'blur(4px)' }"
          :transition="{ type: 'spring', stiffness: 420, damping: 32, mass: 0.8 }"
        >{{ steps[step] }}…</motion.span>
      </AnimatePresence>
    </span>
  </span>
</template>

<style scoped>
.think { display: inline-flex; align-items: center; gap: 10px; min-height: 40px; }
.mark { position: relative; width: 40px; height: 40px; flex: none; display: grid; place-items: center; }
.mark > * { grid-area: 1 / 1; }
.glow { width: 40px; height: 40px; border-radius: 50%; background: radial-gradient(circle, rgba(139, 92, 246, 0.35), rgba(232, 119, 90, 0.12) 55%, transparent 70%); animation: breathe 2.4s ease-in-out infinite; }
.fill { animation: breathe-in 2.4s ease-in-out infinite; }
.mark svg { width: 40px; height: 40px; overflow: visible; }
.orbit { transform-origin: 18px 18px; animation: orbit 1.9s cubic-bezier(0.55, 0.1, 0.35, 0.95) infinite; }
.label { position: relative; display: inline-grid; min-width: 0; font-size: 14px; line-height: 20px; font-weight: 500; }
/* A light sweep across the words, as ChatGPT and Claude do while they think. */
.shimmer { grid-area: 1 / 1; white-space: nowrap; color: transparent; background: linear-gradient(100deg, #71717a 0%, #71717a 38%, #18181b 50%, #71717a 62%, #71717a 100%) 0 0 / 220% 100%; -webkit-background-clip: text; background-clip: text; animation: sweep 1.9s linear infinite; }
@keyframes orbit { to { transform: rotate(360deg); } }
@keyframes breathe { 50% { transform: scale(1.18); opacity: 0.65; } }
@keyframes breathe-in { 50% { transform: scale(0.92); } }
@keyframes sweep { from { background-position: 100% 0; } to { background-position: -120% 0; } }
@media (prefers-reduced-motion: reduce) { .glow, .fill, .orbit, .shimmer { animation: none; } .shimmer { color: #52525b; background: none; } }
</style>
