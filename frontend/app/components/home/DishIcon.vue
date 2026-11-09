<script setup lang="ts">
// A dish's photo. It is decorative (call sites print the title next to it).
// A transparent pixel: until the photo arrives the same element, at the same size, shows the empty disc.
const BLANK = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

const props = withDefaults(defineProps<{
  slug?: string | null;
  title?: string;
  size?: number;
}>(), { slug: null, title: "", size: 40 });

const { dishSrc } = useFoodImages();
const failedSrc = ref<string | null>(null);
const photo = computed(() => {
  const src = dishSrc(props.slug ?? "", props.title);
  return src === failedSrc.value ? null : src;
});
</script>

<template>
  <img
    class="dish-photo"
    :src="photo ?? BLANK"
    alt=""
    :width="size"
    :height="size"
    loading="lazy"
    decoding="async"
    @error="failedSrc = photo"
  >
</template>

<style scoped>
/* The empty disc holds the place until the photo arrives. */
.dish-photo { flex: none; display: block; border-radius: 50%; object-fit: cover; background: #f6f1e7; }
</style>
