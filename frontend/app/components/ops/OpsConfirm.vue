<script setup lang="ts">
// A plain yes/no before anything that changes the product or removes data.
defineProps<{ title: string; message: string; action: string; danger?: boolean; busy?: boolean }>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape") emit("cancel");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="confirm-scrim" @click.self="emit('cancel')">
    <section class="confirm mc-panel" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
      <h2 id="confirm-title">{{ title }}</h2>
      <p id="confirm-message">{{ message }}</p>
      <footer>
        <button type="button" class="mc-pill" :disabled="busy" @click="emit('cancel')">Cancel</button>
        <button type="button" class="mc-primary" :class="{ danger }" :disabled="busy" :aria-busy="busy || undefined" @click="emit('confirm')">
          <UIcon v-if="busy" name="i-lucide-loader-circle" class="mc-spin" aria-hidden="true" />{{ busy ? "Working…" : action }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.confirm-scrim { position: fixed; inset: 0; z-index: 40; display: grid; place-items: center; padding: 16px; background: rgba(15, 15, 18, 0.32); }
.confirm { width: min(440px, 100%); padding: 24px; animation: mc-rise 240ms var(--ease, ease-out) both; }
.confirm h2 { margin: 0 0 6px; color: var(--mc-strong); font-size: 17px; line-height: 24px; font-weight: 600; letter-spacing: -0.01em; }
.confirm p { margin: 0; color: #71717a; font-size: 14px; line-height: 20px; }
.confirm footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
</style>
