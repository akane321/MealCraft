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
    <section class="box mc-card" role="alertdialog" aria-modal="true" aria-labelledby="home-confirm-title" aria-describedby="home-confirm-message">
      <h2 id="home-confirm-title" class="mc-title">{{ title }}</h2>
      <p id="home-confirm-message">{{ message }}</p>
      <footer>
        <button type="button" class="mc-btn secondary" :disabled="busy" @click="emit('cancel')">Cancel</button>
        <button ref="confirmButton" type="button" class="mc-btn danger" :disabled="busy" @click="emit('confirm')">{{ busy ? "Deleting…" : action }}</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.scrim { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 16px; background: rgba(30, 28, 40, 0.42); }
.box { width: min(440px, 100%); padding: 22px 24px; }
h2 { margin: 0 0 8px; font-size: 20px; }
p { margin: 0; color: var(--c-muted); line-height: 1.5; }
footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.danger { border: 0; background: var(--c-coral); color: #fff; }
</style>
