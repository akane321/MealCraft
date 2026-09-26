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
    <section class="confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
      <h2 id="confirm-title" class="mc-serif">{{ title }}</h2>
      <p id="confirm-message">{{ message }}</p>
      <footer>
        <button type="button" class="mc-pill" :disabled="busy" @click="emit('cancel')">Cancel</button>
        <button type="button" class="mc-primary" :class="{ danger }" :disabled="busy" @click="emit('confirm')">{{ busy ? "Working…" : action }}</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.confirm-scrim { position: fixed; inset: 0; z-index: 40; display: grid; place-items: center; padding: 16px; background: rgba(14, 12, 10, 0.66); }
.confirm { width: min(460px, 100%); padding: 22px; border: 1px solid var(--line-2); border-radius: 16px; background: var(--s1); animation: mc-rise 240ms var(--ease) both; }
.confirm h2 { margin: 0 0 8px; font-size: 22px; font-weight: 300; }
.confirm p { margin: 0; color: var(--t2); line-height: 1.55; }
.confirm footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.mc-primary.danger { background: var(--warn); color: var(--ink); }
</style>
