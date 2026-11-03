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
// The module shown in the panel's top bar.
const current = computed(() => OPS_MODULES.find(module => active(module.path)) ?? null);
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
      </ul>
      <div class="sb-fill" />
      <NuxtLink to="/" class="sb-item product-link"><UIcon name="i-lucide-arrow-up-right" />Open the product</NuxtLink>
      <div v-if="ready && actor" class="sb-user">
        <span class="sb-avatar" aria-hidden="true">{{ initials }}</span>
        <span class="sb-who"><b>{{ actor.user.display_name }}</b><small>Operations</small></span>
        <UTooltip text="Sign out">
          <UButton color="neutral" variant="ghost" size="sm" square class="sb-icon" icon="i-lucide-log-out" aria-label="Sign out" @click="logout" />
        </UTooltip>
      </div>
    </nav>
    <main class="ops-main mc-frame">
      <div class="mc-bar"><UIcon :name="icons[current?.slug ?? ''] ?? 'i-lucide-layout-dashboard'" />{{ current?.label ?? "Operations" }}</div>
      <div class="ops-body">
        <NuxtPage v-if="ready" />
        <p v-else class="ops-wait mc-loading" aria-busy="true"><UIcon name="i-lucide-loader-circle" class="mc-spin" aria-hidden="true" />Checking your account…</p>
      </div>
    </main>
  </div>
</template>

<style scoped>
.ops-shell { display: grid; grid-template-columns: 244px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); }
.ops-nav { overflow-y: auto; }
.ops-nav ul { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.ops-nav .sb-label { margin-top: 6px; }
.soon { margin-left: auto; }
.ops-main { overflow-y: auto; }
.ops-main > .mc-bar { position: sticky; top: 0; z-index: 5; background: #fff; }
.ops-body { padding: 28px 40px 40px; }
.product-link { flex: none; margin-top: 8px; padding-top: 0; border-top: 0; color: #71717a; font-size: 13px; box-shadow: 0 -9px 0 -8px #f0f0f2; }
.product-link > .iconify { width: 16px; height: 16px; color: #a1a1aa; }
.ops-wait { justify-content: center; min-height: 240px; }
</style>

<style>
/* Shared console building blocks for the pages under /ops. */
.ops-page { display: grid; gap: 24px; max-width: 1180px; margin: 0 auto; }
.ops-page > header h1 { margin: 4px 0 4px; color: var(--mc-strong); font-size: 22px; line-height: 28px; }
.ops-page > header p { margin: 0; color: var(--t3); max-width: 760px; }
.ops-card { padding: 20px; border: 1px solid #ececef; border-radius: 12px; background: #fff; box-shadow: 0 1px 2px rgba(16, 16, 20, 0.05); min-width: 0; }
.ops-card h2 { margin: 0 0 14px; color: var(--mc-strong); font-family: var(--serif); font-size: 15px; line-height: 20px; font-weight: 600; letter-spacing: -0.01em; }
.ops-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); gap: 16px; }
.ops-muted { color: var(--t3); }
.ops-error { color: var(--warn); }
.ops-badge { display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 8px; border-radius: 999px; background: #f4f4f5; color: #52525b; font-size: 12px; font-weight: 500; white-space: nowrap; }
.ops-badge::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: var(--dot, currentColor); }
/* Status badges: the soft pairs, so done, failed, needs a look and in flight read apart at a glance. */
.ops-badge.success { background: #ecfdf3; color: #067647; }
.ops-badge.error { background: #fef3f2; color: #b42318; }
.ops-badge.warning { background: #fffaeb; color: #b54708; }
.ops-badge.info { background: #eff8ff; color: #175cd3; }
.ops-badge.neutral::before { background: #a1a1aa; }

/* Everything below is scoped to the console shell, so none of it reaches the product pages. */
/* A list that failed to load: the soft red box led by a circle-alert icon, then Try again. */
.ops-shell { --ops-alert-icon: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpath d='M12 8v4M12 16h.01'/%3E%3C/svg%3E"); }
.ops-shell .ops-card[role="alert"] { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-color: #fecdca; background: #fef3f2; box-shadow: none; }
.ops-shell .ops-card[role="alert"]::before { content: ""; width: 16px; height: 16px; flex: none; background: #d92d20; -webkit-mask: var(--ops-alert-icon) no-repeat center / 16px; mask: var(--ops-alert-icon) no-repeat center / 16px; }
.ops-shell .ops-card[role="alert"] > p { flex: 1; margin: 0; color: #b42318; font-size: 14px; }
/* Nothing yet or nothing matched: the dotted art, a violet tile, a title and help. */
.ops-shell .ops-empty-state { display: flex; flex-direction: column; align-items: center; padding: 28px 20px; text-align: center; }
.ops-shell .ops-empty-state .t { margin: 12px 0 0; color: var(--mc-strong); font-size: 15px; line-height: 20px; font-weight: 600; }
.ops-shell .ops-empty-state .h { max-width: 360px; margin: 6px 0 0; color: #71717a; font-size: 13px; line-height: 18px; }
.ops-shell .ops-empty-state .t + .h { margin-top: 4px; }
/* Nothing matched: a quiet centred line in the card. */
.ops-shell .ops-card.ops-empty { padding: 32px 20px; color: #71717a; text-align: center; }

/* Buttons: flat grey when disabled; busy keeps the ink pill; danger is the soft red pair. */
.ops-shell :is(.mc-primary, .mc-pill)[aria-busy="true"]:disabled { opacity: 1; cursor: progress; }
.ops-shell :is(.mc-primary, .mc-pill).danger { border: 1px solid #fecaca; background: #fef2f2; color: #b42318 !important; box-shadow: none; }
.ops-shell :is(.mc-primary, .mc-pill).danger:hover:not(:disabled) { background: #fee4e2; }
.ops-shell .mc-pill.sm { min-height: 28px; height: 28px; padding: 0 10px; font-size: 12.5px; }

/* Tables: a tinted 36px head, 44px rows, a hover tint and the open row in violet-50. */
.ops-shell .table-card { padding: 0; overflow-x: auto; }
.ops-shell main table { width: 100%; border-collapse: collapse; font-size: 14px; line-height: 20px; }
.ops-shell main thead th { height: 36px; padding: 0 14px; border-bottom: 1px solid #ececef; background: #fafafa; color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; text-align: left; white-space: nowrap; }
.ops-shell main :is(td, tbody th) { height: 44px; padding: 10px 14px; border-bottom: 1px solid #f2f2f4; color: #27272a; text-align: left; vertical-align: top; }
.ops-shell main tbody th { color: #52525b; font-weight: 400; }
.ops-shell main tbody tr:last-child > * { border-bottom: 0; }
.ops-shell main tbody tr:hover > td { background: #fafafb; }
.ops-shell main tbody tr.current > td { background: #f5f3ff; }
.ops-shell :is(.table-card, .table-wrap, .job-table) .mc-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ops-shell .table-card .link { padding: 0; border: 0; background: none; color: #18181b; font-weight: 500; text-align: left; }
.ops-shell .table-card .link:hover { color: #6d28d9; }
.ops-shell .table-card .sub { display: block; color: #a1a1aa; font-size: 12px; line-height: 16px; }
.ops-shell .pager { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 10px 14px; border-top: 1px solid #f2f2f4; }
.ops-shell .pager span { margin-right: auto; font-size: 12.5px; }

/* Filters above a table. */
.ops-shell .filters label { display: grid; gap: 6px; color: #71717a; font-size: 12px; line-height: 16px; font-weight: 500; }

/* Drawers: a floating white panel on the right with a sticky head. */
.ops-shell .drawer-scrim { position: fixed; inset: 0; z-index: 30; background: rgba(15, 15, 18, 0.32); }
.ops-shell .drawer { position: fixed; top: 8px; right: 8px; bottom: 8px; width: min(640px, calc(100vw - 16px)); overflow-y: auto; padding: 0 24px 24px; border: 1px solid #ececef; border-radius: 16px; background: #fff; box-shadow: var(--mc-shadow-md); animation: mc-rise 240ms var(--ease, ease-out) both; }
.ops-shell .drawer-head { position: sticky; top: 0; z-index: 2; display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin: 0 -24px 20px; padding: 20px 24px; border-bottom: 1px solid #f0f0f2; background: #fff; }
.ops-shell .drawer-head h2 { margin: 2px 0; color: var(--mc-strong); font-size: 20px; line-height: 28px; font-weight: 600; }
.ops-shell .drawer-head p { margin: 0; color: #71717a; font-size: 13px; line-height: 18px; }
.ops-shell .drawer-actions { display: flex; align-items: center; gap: 8px; }
.ops-shell .drawer :is(section, form) { margin-top: 20px; padding-top: 20px; border-top: 1px solid #f0f0f2; }
.ops-shell .drawer-head + :is(section, form), .ops-shell .drawer > :is(.note, p[role="alert"]) + :is(section, form) { margin-top: 0; padding-top: 0; border-top: 0; }
/* A drawer's own failure line: the soft red box. */
.ops-shell .drawer > p.ops-error[role="alert"] { margin: 0 0 12px; padding: 10px 14px; border: 1px solid #fecdca; border-radius: 12px; background: #fef3f2; color: #b42318; font-size: 13px; }
.ops-shell .drawer section p { margin: 0 0 8px; }
.ops-shell .drawer section p:last-child { margin-bottom: 0; }
.ops-shell .drawer h3 { margin: 0 0 12px; color: var(--mc-strong); font-size: 13px; line-height: 18px; font-weight: 600; letter-spacing: 0; text-transform: none; }
.ops-shell .drawer a { color: #6d28d9; text-decoration: none; }
.ops-shell .drawer a:hover { text-decoration: underline; }
.ops-shell .drawer pre { margin: 0; max-height: 360px; overflow: auto; padding: 10px 12px; border: 1px solid #ececef; border-radius: 10px; background: #fafafa; color: #3f3f46; font: 12px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
.ops-shell .rows { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
.ops-shell .rows li { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 4px 12px; padding: 8px 12px; border: 1px solid #f2f2f4; border-radius: 10px; background: #fafafa; }
.ops-shell .rows .sub { display: block; color: #a1a1aa; font-size: 12px; }
/* Disclosures: a Lucide chevron that turns when open, never the browser's triangle. */
.ops-shell details > summary { display: flex; align-items: center; gap: 8px; list-style: none; }
.ops-shell details > summary::-webkit-details-marker { display: none; }
.ops-shell details > summary::before { content: ""; width: 14px; height: 14px; flex: none; background: #a1a1aa; -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m9 18 6-6-6-6'/%3E%3C/svg%3E") no-repeat center / 14px; mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23000' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m9 18 6-6-6-6'/%3E%3C/svg%3E") no-repeat center / 14px; transition: transform 150ms; }
.ops-shell details[open] > summary::before { transform: rotate(90deg); }
/* Product rows: name, a right-aligned price column, then the action, so prices line up. */
.ops-shell .rows.prod-rows li { display: grid; grid-template-columns: minmax(0, 1fr) 88px 104px; gap: 12px; }
.ops-shell .rows.prod-rows .mc-num { text-align: right; font-variant-numeric: tabular-nums; }
.ops-shell .rows.prod-rows button { justify-self: end; }
.ops-shell .empty-cell { color: #a1a1aa; }
.ops-shell .ops-badge.allergen { margin: 0 4px 2px 0; }
.ops-shell .ops-badge.allergen::before { display: none; }
/* Saved: the soft green box. */
.ops-shell .note { margin: 0 0 12px; padding: 10px 14px; border: 1px solid #abefc6; border-radius: 12px; background: #ecfdf3; color: #067647; font-size: 13px; }
.ops-shell .small { font-size: 12px; }
.ops-shell .actions { display: flex; flex-wrap: wrap; gap: 8px; }
.ops-shell .chips { display: flex; flex-wrap: wrap; gap: 6px; }
/* A drawer's edit form: label above field, checkboxes in a row. */
.ops-shell .edit { display: grid; gap: 12px; }
.ops-shell .edit label { display: grid; gap: 6px; color: #3f3f46; font-size: 13px; font-weight: 500; }
.ops-shell .edit fieldset { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 0; padding: 0; border: 0; }
.ops-shell .edit legend { margin-bottom: 8px; color: #3f3f46; font-size: 13px; font-weight: 500; }
.ops-shell .edit fieldset label, .ops-shell .edit label.check { display: flex; align-items: center; gap: 8px; color: #27272a; font-size: 13px; font-weight: 400; }
.ops-shell .edit :is(.mc-primary, .mc-pill) { justify-self: start; }
.ops-shell .edit p { margin: 0; }
</style>
