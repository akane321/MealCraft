<script setup lang="ts">
import { isConsoleAccount, OPS_MODULES } from "~/lib/ops";

useHead({ title: "Operations · MealCraft" });

const { actor, load, logout } = useAuth();
const route = useRoute();
const ready = ref(false);

// The console is client-rendered behind the account check; a household account goes back to its week.
onMounted(async () => {
  if (!actor.value) await load();
  if (!actor.value) return navigateTo("/login?as=admin");
  if (!isConsoleAccount(actor.value)) return navigateTo("/");
  ready.value = true;
});

function active(path: string) {
  return path === "/ops" ? route.path === "/ops" || route.path === "/ops/" : route.path.startsWith(path);
}
</script>

<template>
  <div class="mc-surface ops-shell">
    <nav class="ops-nav" aria-label="Console">
      <NuxtLink class="ops-brand" to="/ops">
        <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true"><circle cx="16" cy="18" r="10.5" fill="none" stroke="currentColor" stroke-width="1.6" /><path d="M16 7.5c1.4-3.2 4.6-4.2 7-3.3-.9 2.8-3.7 4.4-7 3.3z" fill="#c2553a" /></svg>
        <span class="mc-serif">MealCraft</span>
      </NuxtLink>
      <p class="mc-eyebrow">Operations</p>
      <ul>
        <li v-for="module in OPS_MODULES" :key="module.slug">
          <NuxtLink :to="module.path" :class="{ active: active(module.path) }">
            {{ module.label }}<span v-if="!module.ready" class="soon">soon</span>
          </NuxtLink>
        </li>
      </ul>
      <div v-if="ready && actor" class="ops-account">
        <span>{{ actor.user.display_name }}</span>
        <NuxtLink to="/">Open the product</NuxtLink>
        <button type="button" @click="logout">Sign out</button>
      </div>
    </nav>
    <main class="ops-main">
      <NuxtPage v-if="ready" />
      <p v-else class="ops-wait" aria-busy="true">Checking your account…</p>
    </main>
  </div>
</template>

<style scoped>
.ops-shell { display: grid; grid-template-columns: 232px 1fr; }
.ops-nav { display: flex; flex-direction: column; gap: 14px; padding: 22px 16px; border-right: 1px solid var(--line); background: var(--s1); overflow-y: auto; }
.ops-brand { display: inline-flex; align-items: center; gap: 10px; color: var(--ivory); font-size: 20px; text-decoration: none; }
.ops-nav .mc-eyebrow { margin: 10px 0 0 4px; }
.ops-nav ul { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.ops-nav li a { display: flex; align-items: center; justify-content: space-between; padding: 9px 12px; border-radius: 10px; color: var(--t2); text-decoration: none; transition: background 160ms; }
.ops-nav li a:hover { background: var(--s2); }
.ops-nav li a.active { background: var(--s3); color: var(--ivory); box-shadow: inset 2px 0 0 var(--accent); }
.soon { color: var(--t4); font-size: 11px; }
.ops-account { display: grid; gap: 6px; margin-top: auto; padding: 14px 12px 0; border-top: 1px solid var(--line); color: var(--t3); font-size: 12.5px; }
.ops-account span { color: var(--ivory); }
.ops-account a, .ops-account button { justify-self: start; padding: 0; border: 0; background: none; color: var(--t2); font-size: 12.5px; text-decoration: none; }
.ops-account a:hover, .ops-account button:hover { color: var(--accent); }
.ops-main { min-width: 0; overflow-y: auto; padding: clamp(20px, 4vw, 40px); }
.ops-wait { color: var(--t3); }

@media (max-width: 760px) {
  .ops-shell { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .ops-nav { flex-direction: row; flex-wrap: wrap; align-items: center; border-right: 0; border-bottom: 1px solid var(--line); padding: 12px 16px; }
  .ops-nav .mc-eyebrow { display: none; }
  .ops-nav ul { display: flex; gap: 4px; overflow-x: auto; width: 100%; }
  .ops-nav li a { white-space: nowrap; }
  .ops-account { display: flex; gap: 12px; margin: 0; padding: 0; border: 0; width: 100%; }
  .ops-main { padding: 20px 16px; }
}
</style>

<style>
/* Shared console building blocks for the pages under /ops. */
.ops-page { display: grid; gap: 22px; max-width: 1180px; }
.ops-page > header h1 { margin: 6px 0 4px; font-size: clamp(28px, 4vw, 38px); }
.ops-page > header p { margin: 0; color: var(--t3); max-width: 70ch; }
.ops-card { padding: 20px; border: 1px solid var(--line); border-radius: 16px; background: var(--s1); min-width: 0; }
.ops-card h2 { margin: 0 0 14px; font-family: var(--serif); font-size: 19px; font-weight: 400; }
.ops-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); gap: 16px; }
.ops-muted { color: var(--t3); }
.ops-error { color: var(--warn); }
.ops-badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 9px; border-radius: 999px; border: 1px solid var(--line-2); font-size: 12px; white-space: nowrap; }
.ops-badge::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--dot, var(--t3)); }
</style>
