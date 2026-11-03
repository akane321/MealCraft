<script setup lang="ts">
// A plain yes/no before the household removes something of its own (a conversation, a week).
defineProps<{ title: string; message: string; action: string; busy?: boolean }>();
const emit = defineEmits<{ confirm: []; cancel: [] }>();
const confirmButton = ref<HTMLButtonElement | null>(null);

function onKey(event: KeyboardEvent) {
  if (event.key === "Escape") emit("cancel");
}
onMounted(() => {
  window.addEventListener("keydown", onKey);
  confirmButton.value?.focus();
});
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="scrim" @click.self="emit('cancel')">
    <section class="box mc-panel" role="alertdialog" aria-modal="true" aria-labelledby="home-confirm-title" aria-describedby="home-confirm-message">
      <h2 id="home-confirm-title">{{ title }}</h2>
      <p id="home-confirm-message">{{ message }}</p>
      <footer>
        <button type="button" class="mc-btn secondary" :disabled="busy" @click="emit('cancel')">Cancel</button>
        <button ref="confirmButton" type="button" class="mc-btn danger" :disabled="busy" :aria-busy="busy || undefined" @click="emit('confirm')">
          <UIcon v-if="busy" name="i-lucide-loader-circle" class="mc-spin" aria-hidden="true" />{{ busy ? "Deleting…" : action }}
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.scrim { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 16px; background: rgba(15, 15, 18, 0.32); }
.box { width: min(440px, 100%); padding: 24px; }
h2 { margin: 0 0 6px; color: var(--mc-strong); font-size: 17px; line-height: 24px; font-weight: 600; }
p { margin: 0; color: #71717a; font-size: 14px; line-height: 20px; }
footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
</style>
