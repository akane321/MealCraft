<script setup lang="ts">
import { motion } from "motion-v";

// The selected tab's pill, drawn inside the selected tab. One `id` per row of tabs: when the selection moves, the
// pill glides to the new tab on a spring (a shared layout animation) instead of jumping.
defineProps<{ id: string }>();
</script>

<template>
  <motion.span :layout-id="id" class="mc-tab-pill" aria-hidden="true" :transition="{ type: 'spring', stiffness: 500, damping: 38, mass: 0.8 }" />
</template>
