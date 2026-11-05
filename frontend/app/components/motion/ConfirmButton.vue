<script setup lang="ts">
// A confirm action: pressed it gives a little; while its request runs a ring turns in it; a failure shakes it once.
// Success is drawn where the change lands (the stamp in the chat), since the card holding this button goes.
const props = defineProps<{ busy?: boolean; failed?: boolean; disabled?: boolean; label: string; busyLabel?: string }>();
defineEmits<{ press: [] }>();
const shake = ref(false);
watch(() => props.busy, (now, before) => {
  if (before && !now && props.failed) {
    shake.value = true;
    setTimeout(() => { shake.value = false; }, 450);
  }
});
</script>

<template>
  <button type="button" class="mc-btn primary mc-confirm" :class="{ shake }" :disabled="disabled" :aria-busy="busy || undefined" @click="$emit('press')">
    <MotionMarkAnim v-if="busy" state="busy" />{{ busy && busyLabel ? busyLabel : label }}
  </button>
</template>

<style scoped>
.mc-confirm { display: inline-flex; align-items: center; gap: 8px; transition: transform 120ms cubic-bezier(0.22, 1, 0.36, 1), background 150ms; }
.mc-confirm:active:not(:disabled) { transform: scale(0.97); }
.shake { animation: mc-shake 420ms ease-in-out; box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.35) !important; }
@keyframes mc-shake { 20%, 60% { transform: translateX(-4px); } 40%, 80% { transform: translateX(4px); } }
</style>
