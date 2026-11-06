<script setup lang="ts">
import { revealStep, revealTokens } from "~/lib/reveal";

// A new reply shows word by word, each word rising from a blur on a spring; a tap shows it whole. The text is
// complete in the page from the start. `delay` holds the first word back (while a success moment plays).
const props = defineProps<{ text: string; animate?: boolean; delay?: number }>();
const skipped = ref(false);
const tokens = computed(() => revealTokens(props.text));
const delays = computed(() => {
  const step = revealStep(props.text);
  let n = 0;
  return tokens.value.map(token => (token.trim() ? (props.delay ?? 0) + n++ * step : 0));
});
</script>

<template>
  <p v-if="!animate || skipped">{{ text }}</p>
  <p v-else class="reveal" @click="skipped = true"><template v-for="(token, i) in tokens" :key="i"><span v-if="token.trim()" class="w" :style="{ '--d': `${delays[i]}ms` }">{{ token }}</span><template v-else>{{ token }}</template></template></p>
</template>

<style scoped>
.w { display: inline-block; animation: mc-word-in 380ms ease-out var(--d) both, mc-word-rise 700ms var(--spring) var(--d) both; }
@keyframes mc-word-in { from { opacity: 0; filter: blur(7px); } to { opacity: 1; filter: none; } }
@keyframes mc-word-rise { from { transform: translateY(0.45em); } to { transform: none; } }
</style>
