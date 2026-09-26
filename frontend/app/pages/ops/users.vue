<script setup lang="ts">
import { formatValue, formatWhen, humanKey } from "~/lib/ops";
import type { OpsUser, OpsUserDetail } from "~/types/ops";

const PAGE = 25;
const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const route = useRoute();
const router = useRouter();
const { actor } = useAuth();
const api = (path: string) => `${config.public.apiBase}/api/ops${path}`;

const search = ref("");
const offset = ref(0);
const page = ref<{ items: OpsUser[]; total: number } | null>(null);
const listFailed = ref(false);
async function loadList() {
  listFailed.value = false;
  const query: Record<string, string | number> = { offset: offset.value, limit: PAGE };
  if (search.value.trim()) query.q = search.value.trim();
  try {
    page.value = await apiFetch(api("/users"), { query });
  }
  catch {
    listFailed.value = true;
  }
}
let searchTimer: ReturnType<typeof setTimeout> | undefined;
watch(search, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    offset.value = 0;
    loadList();
  }, 250);
});
watch(offset, loadList);
onMounted(loadList);

// The open account lives in the URL (?user=12).
const selectedId = computed(() => (typeof route.query.user === "string" && /^\d+$/.test(route.query.user) ? Number(route.query.user) : null));
const detail = ref<OpsUserDetail | null>(null);
const detailFailed = ref(false);
const message = ref("");
const failure = ref("");
const edit = reactive({ display_name: "", admin: false });
async function loadDetail(id: number | null) {
  detail.value = null;
  detailFailed.value = false;
  message.value = "";
  if (id === null) return;
  try {
    detail.value = await apiFetch<OpsUserDetail>(api(`/users/${id}`));
    edit.display_name = detail.value.display_name;
    edit.admin = detail.value.system_role === "admin";
  }
  catch {
    detailFailed.value = true;
  }
}
watch(selectedId, loadDetail, { immediate: true });
const isMe = computed(() => detail.value?.id === actor.value?.user.id);

function open(user: OpsUser) {
  router.push({ query: { ...route.query, user: user.id } });
}
function close() {
  const { user: _user, ...rest } = route.query;
  router.push({ query: rest });
}

const detailOf = (error: unknown, fallback: string) => {
  const found = (error as { data?: { detail?: unknown } }).data?.detail;
  return typeof found === "string" ? found : fallback;
};
const saving = ref(false);
const changed = computed(() => detail.value && (edit.display_name.trim() !== detail.value.display_name || edit.admin !== (detail.value.system_role === "admin")));
async function save() {
  if (!detail.value) return;
  saving.value = true;
  failure.value = "";
  try {
    detail.value = await apiFetch<OpsUserDetail>(api(`/users/${detail.value.id}`), {
      method: "PATCH",
      body: { display_name: edit.display_name.trim(), system_role: edit.admin ? "admin" : "ordinary_user" },
    });
    message.value = "Saved.";
    await loadList();
  }
  catch (error) {
    failure.value = detailOf(error, "The account couldn't be saved.");
  }
  finally {
    saving.value = false;
  }
}

type Removal = "conversations" | "plans" | "account";
const pending = ref<Removal | null>(null);
const removing = ref(false);
const confirmText = computed(() => {
  const who = detail.value?.display_name ?? "this account";
  if (pending.value === "conversations") return `Every conversation in ${who}'s households (${detail.value?.conversations ?? 0}) is deleted for good. Saved plans stay.`;
  if (pending.value === "plans") return `Every saved plan in ${who}'s households (${detail.value?.plans ?? 0}) is deleted for good, with its shopping list and check-ins.`;
  return `${who} can no longer sign in. Households nobody else belongs to are deleted with their conversations, plans and profile.`;
});
async function confirmRemoval() {
  if (!detail.value || !pending.value) return;
  const id = detail.value.id;
  const what = pending.value;
  removing.value = true;
  failure.value = "";
  try {
    const path = what === "account" ? `/users/${id}` : `/users/${id}/${what}`;
    const result = await apiFetch<{ deleted: number }>(api(path), { method: "DELETE" });
    pending.value = null;
    await loadList();
    if (what === "account") return close();
    await loadDetail(id);
    message.value = `Deleted ${result.deleted} ${what === "plans" ? (result.deleted === 1 ? "plan" : "plans") : (result.deleted === 1 ? "conversation" : "conversations")}.`;
  }
  catch (error) {
    pending.value = null;
    failure.value = detailOf(error, "That couldn't be deleted.");
  }
  finally {
    removing.value = false;
  }
}
</script>

<template>
  <div class="ops-page">
    <header>
      <p class="mc-eyebrow">Users</p>
      <h1 class="mc-serif">Accounts and their households</h1>
      <p>Find an account to see its household, profile, conversations and plans. You can rename it, give or take console access, and delete its conversations, its plans or the account itself.</p>
    </header>

    <label class="search">Search by name or email
      <input v-model="search" type="search" placeholder="e.g. alice or @example.com">
    </label>

    <div v-if="listFailed" class="ops-card" role="alert">
      <p class="ops-error">The account list couldn't be loaded.</p>
      <button type="button" class="mc-pill" @click="loadList">Try again</button>
    </div>
    <p v-else-if="!page" class="ops-muted" aria-busy="true">Loading accounts…</p>
    <p v-else-if="!page.items.length" class="ops-card ops-muted">No account matches.</p>
    <section v-else class="ops-card table-card" aria-label="Accounts">
      <table>
        <thead><tr><th>Account</th><th>Household</th><th>Conversations</th><th>Plans</th><th>Console</th><th>Last seen</th></tr></thead>
        <tbody>
          <tr v-for="user in page.items" :key="user.id" :class="{ current: user.id === selectedId }">
            <td><button type="button" class="link" @click="open(user)">{{ user.display_name }}</button><span class="ops-muted email">{{ user.email }}</span></td>
            <td>{{ user.households.map(item => item.name).join(", ") || "—" }}</td>
            <td class="mc-num">{{ user.conversations }}</td>
            <td class="mc-num">{{ user.plans }}</td>
            <td>{{ user.system_role === "ordinary_user" ? "—" : humanKey(user.system_role) }}</td>
            <td class="ops-muted">{{ formatWhen(user.last_seen_at) }}</td>
          </tr>
        </tbody>
      </table>
      <footer class="pager">
        <span class="ops-muted">{{ offset + 1 }}–{{ offset + page.items.length }} of {{ page.total }}</span>
        <button type="button" class="mc-pill" :disabled="offset === 0" @click="offset = Math.max(0, offset - PAGE)">Previous</button>
        <button type="button" class="mc-pill" :disabled="offset + PAGE >= page.total" @click="offset += PAGE">Next</button>
      </footer>
    </section>

    <div v-if="selectedId !== null" class="drawer-scrim" @click.self="close">
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="user-title">
        <header class="drawer-head">
          <div>
            <p class="mc-eyebrow">Account #{{ selectedId }}</p>
            <h2 id="user-title" class="mc-serif">{{ detail?.display_name ?? "Loading…" }}</h2>
            <p v-if="detail" class="ops-muted">{{ detail.email }} · joined {{ formatWhen(detail.created_at) }}</p>
          </div>
          <button type="button" class="mc-pill" @click="close">Close</button>
        </header>

        <p v-if="detailFailed" class="ops-error" role="alert">This account couldn't be loaded. It may have been deleted.</p>
        <template v-else-if="detail">
          <p v-if="message" class="note" role="status">{{ message }}</p>
          <p v-if="failure" class="ops-error" role="alert">{{ failure }}</p>

          <form class="edit" @submit.prevent="save">
            <h3>Edit</h3>
            <label>Display name <input v-model="edit.display_name" maxlength="120" required></label>
            <label class="check"><input v-model="edit.admin" type="checkbox" :disabled="isMe"> Console administrator</label>
            <p v-if="isMe" class="ops-muted small">This is your own account, so console access stays on.</p>
            <button type="submit" class="mc-primary" :disabled="!changed || saving">{{ saving ? "Saving…" : "Save changes" }}</button>
          </form>

          <section>
            <h3>Households</h3>
            <p v-if="!detail.households.length" class="ops-muted">Not in any household.</p>
            <div v-for="household in detail.households" :key="household.id" class="household">
              <p><b>{{ household.name }}</b> <span class="ops-muted">· {{ humanKey(household.role) }} · {{ household.members }} {{ household.members === 1 ? "member" : "members" }}</span></p>
              <dl v-if="household.profile" class="profile">
                <template v-for="(value, key) in household.profile" :key="key"><dt>{{ humanKey(String(key)) }}</dt><dd>{{ formatValue(value) }}</dd></template>
              </dl>
              <p v-else class="ops-muted small">No household profile saved.</p>
            </div>
          </section>

          <section>
            <h3>Conversations ({{ detail.conversations }})</h3>
            <p v-if="!detail.recent_conversations.length" class="ops-muted">None.</p>
            <ul v-else class="rows">
              <li v-for="item in detail.recent_conversations" :key="item.id"><span>“{{ item.first_message ?? "…" }}”</span><span class="ops-muted">{{ humanKey(item.status) }} · {{ item.messages }} messages · {{ formatWhen(item.created_at) }}</span></li>
            </ul>
          </section>

          <section>
            <h3>Plans ({{ detail.plans }})</h3>
            <p v-if="!detail.recent_plans.length" class="ops-muted">None.</p>
            <ul v-else class="rows">
              <li v-for="plan in detail.recent_plans" :key="plan.id"><span>Week of {{ plan.start_date }} for {{ plan.household_size }}</span><span class="ops-muted mc-num">S${{ plan.total_sgd.toFixed(2) }} · {{ formatWhen(plan.created_at) }}</span></li>
            </ul>
          </section>

          <section class="danger-zone">
            <h3>Delete</h3>
            <div class="actions">
              <button type="button" class="mc-pill" :disabled="!detail.conversations" @click="pending = 'conversations'">Delete conversations</button>
              <button type="button" class="mc-pill" :disabled="!detail.plans" @click="pending = 'plans'">Delete plans</button>
              <button type="button" class="mc-pill danger" :disabled="isMe" @click="pending = 'account'">Delete account</button>
            </div>
          </section>
        </template>
        <p v-else class="ops-muted" aria-busy="true">Loading the account…</p>
      </aside>
    </div>

    <OpsConfirm
      v-if="pending"
      :title="pending === 'account' ? 'Delete this account?' : `Delete these ${pending}?`"
      :message="confirmText"
      :action="pending === 'account' ? 'Delete account' : `Delete ${pending}`"
      danger
      :busy="removing"
      @confirm="confirmRemoval"
      @cancel="pending = null"
    />
  </div>
</template>

<style scoped>
.search { display: grid; gap: 6px; max-width: 420px; color: var(--t3); font-size: 12px; }
input:not([type="checkbox"]) { padding: 9px 12px; border: 1px solid var(--line-2); border-radius: 10px; background: var(--s2); color: var(--ivory); font: inherit; font-size: 13px; }
.table-card { padding: 0; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { padding: 12px 16px; border-bottom: 1px solid var(--line-2); color: var(--t3); font-weight: 500; text-align: left; white-space: nowrap; }
td { padding: 10px 16px; border-bottom: 1px solid var(--line); }
tr.current td { background: var(--s2); }
.link { padding: 0; border: 0; background: none; color: var(--ivory); text-align: left; }
.link:hover { color: var(--accent); }
.email { display: block; font-size: 12px; }
.pager { display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding: 12px 16px; }
.pager span { margin-right: auto; font-size: 12.5px; }
.drawer-scrim { position: fixed; inset: 0; z-index: 30; display: flex; justify-content: flex-end; background: rgba(14, 12, 10, 0.6); }
.drawer { width: min(640px, 100%); height: 100%; overflow-y: auto; padding: 24px; border-left: 1px solid var(--line-2); background: var(--s1); animation: mc-rise 320ms var(--ease) both; }
.drawer-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.drawer-head h2 { margin: 6px 0 2px; font-size: 24px; font-weight: 300; }
.drawer-head p { margin: 0; font-size: 12.5px; }
.drawer section, .drawer form { margin-top: 22px; padding-top: 16px; border-top: 1px solid var(--line); }
.drawer h3 { margin: 0 0 12px; color: var(--t2); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.edit { display: grid; gap: 10px; }
.edit label { display: grid; gap: 6px; color: var(--t3); font-size: 12px; }
.edit label.check { display: flex; align-items: center; gap: 8px; color: var(--ivory); font-size: 13px; }
.edit .mc-primary { justify-self: start; }
.edit p { margin: 0; }
.small { font-size: 12px; }
.note { padding: 9px 12px; border-radius: 10px; background: rgba(169, 183, 154, 0.12); color: var(--ivory); }
.household p { margin: 0 0 8px; }
.profile { display: grid; grid-template-columns: minmax(120px, 34%) 1fr; gap: 6px 14px; margin: 0 0 14px; font-size: 13px; }
.profile dt { color: var(--t3); }
.profile dd { margin: 0; }
.rows { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
.rows li { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; padding: 8px 12px; border-radius: 10px; background: var(--s2); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.mc-pill.danger { color: var(--warn); border-color: rgba(236, 122, 90, 0.35); }
</style>
