<script setup lang="ts">
// Decorative: the line prints the name beside it. An ingredient without a picture keeps its place as an empty tile.
const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 32 });
const { ingredientSrc } = useFoodImages();
const src = computed(() => ingredientSrc(props.name));
</script>

<template>
  <span class="ingredient-image" :style="{ width: `${size}px`, height: `${size}px` }">
    <img v-if="src" :src="src" alt="" :width="size" :height="size" loading="lazy" decoding="async">
  </span>
</template>

<style scoped>
/* Multiply melts each picture's near-white backdrop into one tile colour, so slightly grey backdrops don't show. */
.ingredient-image { flex: none; display: block; overflow: hidden; border-radius: 8px; background: #f4f4f5; isolation: isolate; }
img { display: block; width: 100%; height: 100%; object-fit: cover; mix-blend-mode: multiply; transform: scale(1.12); }
</style>
