<script setup lang="ts">
import { animate } from "motion-v";
import { formatSgd } from "~/lib/home-surface";

// A price that counts to its new value when it changes (shown at once the first time, and under reduced motion).
const props = defineProps<{ value: number }>();
const shown = ref(props.value);
let run: { stop: () => void } | undefined;
watch(() => props.value, (to) => {
  run?.stop();
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    shown.value = to;
    return;
  }
  run = animate(shown.value, to, { duration: 0.9, ease: [0.22, 1, 0.36, 1], onUpdate: (value) => { shown.value = value; } });
});
onBeforeUnmount(() => run?.stop());
</script>

<template>
  <span>{{ formatSgd(shown) }}</span>
</template>
