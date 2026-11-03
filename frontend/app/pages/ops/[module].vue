<script setup lang="ts">
import { OPS_MODULES } from "~/lib/ops";

// Modules ADR-0047 names but this slice does not build yet.
const route = useRoute();
const module = computed(() => OPS_MODULES.find(item => item.slug === route.params.module && !item.ready));
</script>

<template>
  <div class="ops-page">
    <header class="mc-empty">
      <div class="mc-empty-art"><span><span class="mc-tile" data-tone="violet"><UIcon name="i-lucide-construction" /></span></span></div>
      <h1>{{ module ? `${module.label} is coming in the next slice` : "There is no such part of the console" }}</h1>
      <p>{{ module?.blurb ?? "Pick a section from the list on the left." }}</p>
      <p v-if="module">Nothing here works yet. Overview, Tasks and Services are ready to use.</p>
    </header>
  </div>
</template>

<style scoped>
.ops-page > header.mc-empty { padding-top: 48px; }
.ops-page > header.mc-empty h1 { margin: 16px 0 0; font-size: 18px; line-height: 24px; }
.ops-page > header.mc-empty p { max-width: 420px; margin: 6px 0 0; color: #71717a; }
</style>
