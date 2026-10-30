<script setup lang="ts">
import { todayIsoDate } from "~/lib/meal-plan-format";
import type { AgentSession } from "~/types/agent";

// The household's conversations: search, pinned first, then by when each last changed; each can be renamed,
// pinned or deleted from its menu. Opening one is the only thing a row itself does.
const props = defineProps<{ items: AgentSession[]; currentId: number | null; weekId: number | null }>();
const emit = defineEmits<{
  open: [item: AgentSession];
  rename: [id: number, title: string | null];
  pin: [id: number, pinned: boolean];
  remove: [item: AgentSession];
}>();

const query = ref("");
const menuFor = ref<number | null>(null);
const editing = ref<number | null>(null);
const draftTitle = ref("");
const removing = ref<AgentSession | null>(null);

const titleOf = (item: AgentSession) => item.title || item.messages.find(m => m.role === "user")?.content || "New plan";
function statusOf(item: AgentSession): { label: string; tone: string } {
  if (item.plan_id && item.plan_id === props.weekId) return { label: "Current plan", tone: "week" };
  if (item.plan_id) return { label: "Planned", tone: "planned" };
  if (item.status === "planned") return { label: "Plan deleted", tone: "gone" };
  return { label: "Setting up", tone: "setup" };
}

const filtered = computed(() => {
  const words = query.value.trim().toLowerCase();
  if (!words) return props.items;
  return props.items.filter(item =>
    titleOf(item).toLowerCase().includes(words) || item.messages.some(m => m.content.toLowerCase().includes(words)),
  );
});
const groups = computed(() => {
  const today = todayIsoDate();
  const weekAgo = new Date(`${today}T00:00:00Z`);
  weekAgo.setUTCDate(weekAgo.getUTCDate() - 6);
  const since = weekAgo.toISOString().slice(0, 10);
  const buckets: Record<string, AgentSession[]> = { Pinned: [], Today: [], "Last 7 days": [], Earlier: [] };
  for (const item of filtered.value) {
    const changed = new Date(item.updated_at);
    // A conversation without a readable time (an older copy) is listed under Earlier rather than breaking the list.
    const day = Number.isNaN(changed.getTime()) ? "" : todayIsoDate(changed);
    const key = item.pinned_at ? "Pinned" : day >= today ? "Today" : day >= since ? "Last 7 days" : "Earlier";
    buckets[key]!.push(item);
  }
  return Object.entries(buckets).filter(([, list]) => list.length).map(([label, list]) => ({ label, list }));
});

function startRename(item: AgentSession) {
  menuFor.value = null;
  editing.value = item.id;
  draftTitle.value = titleOf(item);
  void nextTick(() => document.getElementById(`rename-${item.id}`)?.focus());
}
function saveRename(item: AgentSession) {
  if (editing.value !== item.id) return;
  editing.value = null;
  const title = draftTitle.value.trim();
  if (title !== titleOf(item)) emit("rename", item.id, title || null);
}
function togglePin(item: AgentSession) {
  menuFor.value = null;
  emit("pin", item.id, !item.pinned_at);
}
function askRemove(item: AgentSession) {
  menuFor.value = null;
  removing.value = item;
}
function confirmRemove() {
  if (removing.value) emit("remove", removing.value);
  removing.value = null;
}
const removeMessage = computed(() => {
  const item = removing.value;
  if (!item) return "";
  const base = `“${titleOf(item)}” and its messages will be deleted. This cannot be undone.`;
  if (item.plan_id === props.weekId && item.plan_id) return `${base} This plan stays: it is still on this page and in Past plans.`;
  return item.plan_id ? `${base} The plan it made stays in Past plans.` : base;
});

// A click anywhere else closes an open menu.
function onDocument(event: MouseEvent) {
  if (!(event.target as HTMLElement).closest(".row-menu, .more")) menuFor.value = null;
}
onMounted(() => document.addEventListener("click", onDocument));
onBeforeUnmount(() => document.removeEventListener("click", onDocument));
</script>

<template>
  <section class="convos" aria-label="Your plans">
    <label class="search">
      <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg>
      <input id="plan-search" v-model="query" type="search" placeholder="Search plans" aria-label="Search plans" autocomplete="off">
    </label>
    <p v-if="!filtered.length" class="empty mc-small">{{ query ? "No plan matches." : "Your plans will appear here." }}</p>
    <div class="groups">
      <section v-for="group in groups" :key="group.label" :aria-label="group.label">
        <h3 class="mc-label">{{ group.label }}</h3>
        <ul>
          <li v-for="item in group.list" :key="item.id" class="row" :class="{ on: item.id === currentId }">
            <input
              v-if="editing === item.id"
              :id="`rename-${item.id}`"
              v-model="draftTitle"
              class="rename"
              maxlength="120"
              aria-label="Rename plan"
              @keydown.enter.prevent="saveRename(item)"
              @keydown.esc.prevent="editing = null"
              @blur="saveRename(item)"
            >
            <button v-else type="button" class="open" :title="titleOf(item)" :aria-current="item.id === currentId ? 'true' : undefined" @click="emit('open', item)">
              <span class="t"><svg v-if="item.pinned_at" class="pin" viewBox="0 0 24 24" aria-label="Pinned"><path d="M9 4h6l-1 6 3 3H7l3-3zM12 13v7" /></svg>{{ titleOf(item) }}</span>
              <span class="s" :class="statusOf(item).tone">{{ statusOf(item).label }}</span>
            </button>
            <button type="button" class="more" :aria-label="`Options for ${titleOf(item)}`" aria-haspopup="menu" :aria-expanded="menuFor === item.id" @click.stop="menuFor = menuFor === item.id ? null : item.id">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="18" cy="12" r="1.6" /></svg>
            </button>
            <div v-if="menuFor === item.id" class="row-menu mc-card" role="menu">
              <button type="button" role="menuitem" @click="startRename(item)">Rename</button>
              <button type="button" role="menuitem" @click="togglePin(item)">{{ item.pinned_at ? "Unpin" : "Pin to top" }}</button>
              <button type="button" role="menuitem" class="danger" @click="askRemove(item)">Delete…</button>
            </div>
          </li>
        </ul>
      </section>
    </div>
    <HomeConfirm v-if="removing" title="Delete this conversation?" :message="removeMessage" action="Delete" @confirm="confirmRemove" @cancel="removing = null" />
  </section>
</template>

<style scoped>
.convos { min-height: 0; display: flex; flex-direction: column; gap: 10px; }
.search { display: flex; align-items: center; gap: 8px; height: 36px; padding: 0 10px; border: 1px solid var(--c-line); border-radius: 10px; background: #fff; }
.search svg { width: 16px; height: 16px; flex: none; fill: none; stroke: var(--c-muted); stroke-width: 2; stroke-linecap: round; }
.search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font: inherit; font-size: 14px; color: var(--c-ink); }
.empty { margin: 4px 10px; color: var(--c-muted); }
.groups { min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 12px; }
h3 { margin: 0; padding: 0 10px 4px; }
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
.row { position: relative; display: flex; align-items: center; border-radius: 10px; }
.row:hover, .row:focus-within { background: rgba(42, 42, 72, 0.05); }
.row.on { background: #fff; box-shadow: 0 0 0 1px var(--c-line); }
.open { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 1px; padding: 6px 4px 6px 10px; border: 0; background: transparent; color: var(--c-neutral-text); text-align: left; }
.row.on .open { color: var(--c-ink); }
.t { display: flex; align-items: center; gap: 4px; min-width: 0; font-size: 14px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row.on .t { font-weight: 800; }
.pin { width: 13px; height: 13px; flex: none; fill: none; stroke: var(--c-coral); stroke-width: 2; stroke-linejoin: round; }
.s { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.s.week { color: var(--c-green-text); font-weight: 800; }
.s.gone { font-style: italic; }
.more { flex: none; width: 28px; height: 28px; margin-right: 4px; display: grid; place-items: center; border: 0; border-radius: 8px; background: transparent; opacity: 0; }
.row:hover .more, .row:focus-within .more, .row.on .more, .more[aria-expanded="true"] { opacity: 1; }
.more:hover { background: rgba(42, 42, 72, 0.08); }
.more svg { width: 18px; height: 18px; fill: var(--c-ink); }
.row-menu { position: absolute; z-index: 20; top: 34px; right: 4px; min-width: 150px; padding: 4px; display: grid; }
.row-menu button { padding: 8px 10px; border: 0; border-radius: 8px; background: transparent; color: var(--c-ink); font: inherit; font-size: 14px; text-align: left; }
.row-menu button:hover, .row-menu button:focus-visible { background: rgba(42, 42, 72, 0.06); }
.row-menu .danger { color: var(--c-coral); }
.rename { flex: 1; min-width: 0; margin: 4px; padding: 6px 8px; border: 1px solid var(--c-coral); border-radius: 8px; font: inherit; font-size: 14px; }
</style>
