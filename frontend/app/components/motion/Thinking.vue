<script setup lang="ts">
import { AnimatePresence, motion } from "motion-v";

// A reply on its way: the loader's large dots and a shimmering line that walks through what is being done
// (it stays on the last step until the reply comes).
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
    <MotionLoader size="lg" />
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
.label { position: relative; display: inline-grid; min-width: 0; font-size: 14px; line-height: 20px; font-weight: 500; }
/* A light sweep across the words, as ChatGPT and Claude do while they think. */
.shimmer { grid-area: 1 / 1; white-space: nowrap; color: transparent; background: linear-gradient(100deg, #71717a 0%, #71717a 38%, #18181b 50%, #71717a 62%, #71717a 100%) 0 0 / 220% 100%; -webkit-background-clip: text; background-clip: text; animation: sweep 1.9s linear infinite; }
@keyframes sweep { from { background-position: 100% 0; } to { background-position: -120% 0; } }
@media (prefers-reduced-motion: reduce) { .shimmer { animation: none; } .shimmer { color: #52525b; background: none; } }
</style>
