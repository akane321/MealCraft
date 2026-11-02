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

const initials = computed(() => (actor.value?.user.display_name ?? "?")
  .split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]!.toUpperCase()).join(""));
// Written out here (not in lib/ops.ts) so the icon bundle finds every name.
const icons: Record<string, string> = {
  overview: "i-lucide-layout-dashboard",
  tasks: "i-lucide-list-checks",
  debugging: "i-lucide-bug",
  services: "i-lucide-server",
  data: "i-lucide-database",
  quality: "i-lucide-badge-check",
  experiments: "i-lucide-flask-conical",
  users: "i-lucide-users",
};

function active(path: string) {
  return path === "/ops" ? route.path === "/ops" || route.path === "/ops/" : route.path.startsWith(path);
}
</script>

<template>
  <div class="mc-surface mc-shell ops-shell">
    <nav class="ops-nav sb" aria-label="Console">
      <NuxtLink class="sb-brand" to="/ops"><ShellMark />MealCraft</NuxtLink>
      <p class="sb-label">Operations</p>
      <ul>
        <li v-for="module in OPS_MODULES" :key="module.slug">
          <NuxtLink :to="module.path" class="sb-item" :class="{ on: active(module.path) }">
            <UIcon :name="icons[module.slug] ?? 'i-lucide-circle'" />{{ module.label }}<UBadge v-if="!module.ready" class="soon" size="sm" color="neutral" variant="soft" label="soon" />
          </NuxtLink>
        </li>
        <li><NuxtLink to="/" class="sb-item"><UIcon name="i-lucide-arrow-up-right" />Open the product</NuxtLink></li>
      </ul>
      <div class="sb-fill" />
      <div v-if="ready && actor" class="sb-user">
        <span class="sb-avatar" aria-hidden="true">{{ initials }}</span>
        <span class="sb-who"><b>{{ actor.user.display_name }}</b><small>Operations</small></span>
        <UTooltip text="Sign out">
          <UButton color="neutral" variant="ghost" size="sm" square class="sb-icon" icon="i-lucide-log-out" aria-label="Sign out" @click="logout" />
        </UTooltip>
      </div>
    </nav>
    <main class="ops-main mc-frame">
      <NuxtPage v-if="ready" />
      <p v-else class="ops-wait" aria-busy="true">Checking your account…</p>
    </main>
  </div>
</template>

<style scoped>
.ops-shell { display: grid; grid-template-columns: 244px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
.ops-nav { overflow-y: auto; }
.ops-nav ul { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.ops-nav .sb-label { margin-top: 6px; }
.soon { margin-left: auto; }
.ops-main { overflow-y: auto; padding: 28px 40px 40px; }
.ops-wait { color: var(--t3); }
</style>

<style>
/* Shared console building blocks for the pages under /ops. */
.ops-page { display: grid; gap: 24px; max-width: 1180px; margin: 0 auto; }
.ops-page > header h1 { margin: 4px 0 4px; color: var(--mc-strong, var(--ivory)); font-size: 22px; line-height: 28px; }
.ops-page > header p { margin: 0; color: var(--t3); max-width: 70ch; }
.ops-card { padding: 20px; border: 1px solid #ececef; border-radius: 12px; background: #fff; box-shadow: 0 1px 2px rgba(16, 16, 20, 0.05); min-width: 0; }
.ops-card h2 { margin: 0 0 14px; color: var(--mc-strong, var(--ivory)); font-family: var(--serif); font-size: 15px; line-height: 20px; font-weight: 600; letter-spacing: -0.01em; }
.ops-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); gap: 16px; }
.ops-muted { color: var(--t3); }
.ops-error { color: var(--warn); }
.ops-badge { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 8px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 12px; font-weight: 500; white-space: nowrap; }
.ops-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--dot, var(--t3)); }
</style>
