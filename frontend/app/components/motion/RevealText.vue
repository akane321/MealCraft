<script setup lang="ts">
import { revealStep, revealTokens } from "~/lib/reveal";

// A new reply shows word by word; a tap shows it whole. The text is complete in the page from the start.
const props = defineProps<{ text: string; animate?: boolean }>();
const skipped = ref(false);
const tokens = computed(() => revealTokens(props.text));
const delays = computed(() => {
  const step = revealStep(props.text);
  let n = 0;
  return tokens.value.map(token => (token.trim() ? n++ * step : 0));
});
</script>

<template>
  <p v-if="!animate || skipped">{{ text }}</p>
  <p v-else class="reveal" @click="skipped = true"><template v-for="(token, i) in tokens" :key="i"><span v-if="token.trim()" class="w" :style="{ animationDelay: `${delays[i]}ms` }">{{ token }}</span><template v-else>{{ token }}</template></template></p>
</template>

<style scoped>
.w { animation: mc-word 260ms ease-out both; }
@keyframes mc-word { from { opacity: 0; filter: blur(3px); } }
</style>
