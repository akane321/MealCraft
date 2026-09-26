<script setup lang="ts">
import { OPS_MODULES } from "~/lib/ops";

// Modules ADR-0047 names but this slice does not build yet.
const route = useRoute();
const module = computed(() => OPS_MODULES.find(item => item.slug === route.params.module && !item.ready));
</script>

<template>
  <div class="ops-page">
    <header>
      <p class="mc-eyebrow">{{ module?.label ?? "Not found" }}</p>
      <h1 class="mc-serif">{{ module ? `${module.label} is coming in the next slice` : "There is no such part of the console" }}</h1>
      <p>{{ module?.blurb ?? "Pick a section from the list on the left." }}</p>
    </header>
    <p v-if="module" class="ops-card ops-muted">Nothing here works yet. Overview, Tasks and Services are ready to use.</p>
  </div>
</template>
