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
      <UIcon name="i-lucide-search" aria-hidden="true" />
      <input id="plan-search" v-model="query" type="search" placeholder="Search plans" aria-label="Search plans" autocomplete="off">
    </label>
    <p v-if="!filtered.length" class="empty mc-small">{{ query ? "No plan matches." : "Your plans will appear here." }}</p>
    <div class="groups">
      <section v-for="group in groups" :key="group.label" :aria-label="group.label">
        <h3 v-if="groups.length > 1" class="mc-label">{{ group.label }}</h3>
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
              <UIcon name="i-lucide-message-circle" class="ic" aria-hidden="true" />
              <svg v-if="item.pinned_at" class="pin" viewBox="0 0 24 24" aria-label="Pinned"><path d="M9 4h6l-1 6 3 3H7l3-3zM12 13v7" /></svg>
              <span class="t">{{ titleOf(item) }}</span>
              <!-- One line a row: the status is a dot for the current plan, and read out for every row. -->
              <span class="s" :class="statusOf(item).tone" aria-hidden="true" />
              <span class="visually-hidden">{{ statusOf(item).label }}</span>
            </button>
            <button type="button" class="more" :aria-label="`Options for ${titleOf(item)}`" aria-haspopup="menu" :aria-expanded="menuFor === item.id" @click.stop="menuFor = menuFor === item.id ? null : item.id">
              <UIcon name="i-lucide-ellipsis" aria-hidden="true" />
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
.convos { min-height: 0; display: flex; flex-direction: column; gap: 8px; }
.search { flex: none; display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px; border: 1px solid #ededf0; border-radius: 10px; background: #fff; }
.search .iconify { width: 15px; height: 15px; flex: none; color: #a1a1aa; }
.search input { min-width: 0; flex: 1; border: 0; outline: 0; background: transparent; font: inherit; font-size: 13.5px; color: #18181b; }
.search input::placeholder { color: #a1a1aa; }
.search:focus-within { border-color: #c4b5fd; box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.12); }
.empty { margin: 4px 10px; color: #a1a1aa; }
.groups { min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 10px; -webkit-mask-image: linear-gradient(#000 calc(100% - 6px), transparent); mask-image: linear-gradient(#000 calc(100% - 6px), transparent); }
h3 { margin: 0; padding: 0 10px 2px; font-size: 11px; line-height: 14px; font-weight: 500; color: #a1a1aa; }
ul { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; }
.row { position: relative; display: flex; align-items: center; height: 36px; border: 1px solid transparent; border-radius: 10px; transition: background 150ms, border-color 150ms; }
.row:hover, .row:focus-within { background: #efeff1; }
.row.on { border-color: #ececef; background: #fff; }
.open { min-width: 0; flex: 1; height: 100%; display: flex; align-items: center; gap: 8px; padding: 0 4px 0 10px; border: 0; background: transparent; color: #27272a; text-align: left; }
.ic { flex: none; width: 16px; height: 16px; color: #a1a1aa; }
.row.on .ic { color: #8b5cf6; }
.t { min-width: 0; flex: 1; overflow: hidden; font-size: 13.5px; line-height: 18px; font-weight: 500; white-space: nowrap; text-overflow: ellipsis; }
.row.on .t { color: #0f0f12; }
.pin { width: 12px; height: 12px; flex: none; fill: none; stroke: #a1a1aa; stroke-width: 2; stroke-linejoin: round; }
.s { display: none; }
.s.week { display: block; flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--c-green); }
.more { flex: none; width: 24px; height: 24px; margin-right: 4px; display: grid; place-items: center; border: 0; border-radius: 6px; background: transparent; color: #71717a; opacity: 0; }
.row:hover .more, .row:focus-within .more, .more[aria-expanded="true"] { opacity: 1; }
.more:hover { background: #f4f4f5; color: #18181b; }
.more .iconify { width: 16px; height: 16px; }
.row-menu { position: absolute; z-index: 20; top: 36px; right: 0; min-width: 160px; padding: 4px; display: grid; border-radius: 12px; box-shadow: 0 1px 2px rgba(16, 16, 20, 0.04), 0 12px 32px -12px rgba(16, 16, 20, 0.16); }
.row-menu button { height: 32px; padding: 0 10px; border: 0; border-radius: 8px; background: transparent; color: #27272a; font: inherit; font-size: 13.5px; text-align: left; }
.row-menu button:hover, .row-menu button:focus-visible { background: #f4f4f5; }
.row-menu .danger { color: #b42318; }
.rename { flex: 1; min-width: 0; margin: 3px; height: 30px; padding: 0 8px; border: 1px solid #a78bfa; border-radius: 8px; outline: 0; box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.15); font: inherit; font-size: 13.5px; }
</style>
