<script setup lang="ts">
import { allergenLabel } from "~/lib/allergens";
import { budgetGap, budgetLine, changedMealWhen, formatSgd, groceriesChange, groceryGroups, previewChoices, sameDishChange } from "~/lib/home-surface";
import { statedTimeLimit } from "~/lib/household-profile";
import { formatPlanDate, todayIsoDate } from "~/lib/meal-plan-format";
import { planDayLabel, shapeChangeSummary } from "~/lib/plan-shape";
import type { AgentMessage, AgentSession } from "~/types/agent";
import type { MealPlanEntryStatus, NutritionDashboardDay, WeeklyMealPlan, WeeklyMealPlanCollection, WeeklyMealPlanListItem } from "~/types/meal-plan";

useHead({ title: "MealCraft" });

type Tab = "dinners" | "groceries" | "nutrition";

const DRAFT_KEY = "mealcraft-draft";
const starters = ["Dinners for two this week, around S$90", "A high-protein week", "Vegetarian, under S$60"];
const followUps = ["Swap tomorrow's dinner", "Skip Friday", "Don't change Sunday"];

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const { actor, logout } = useAuth();
const agent = useMealCraftAgent();
const { session, isLoading, errorMessage, generatedPlan } = agent;
const nutrition = useNutritionDashboard();
const household = useHouseholdProfile();

const view = ref<"landing" | "app">("landing");
const draft = ref("");
// A dish's button or a follow-up chip on a week the open conversation did not plan: its words and that week.
const dishAction = ref<{ text: string; week: number } | null>(null);
// Such an action that would set aside this conversation's "Plan my week", waiting for the household's answer.
const takeOn = ref<{ message: string; week: number } | null>(null);
// Open my week (enter) is reopening the week and its conversations.
const entering = ref(false);
// A delayed initial reopen must not override a conversation the household deliberately chose.
let conversationVersion = 0;
const plan = ref<WeeklyMealPlan | null>(null);
// The shown week was planned again for the same days (the plans list's `current`): it is only read.
const replaced = ref(false);
// A request in flight, a failed one and "nothing planned yet" are three different states.
const planState = ref<"empty" | "loading" | "error" | "ready">("empty");
const lastPlanId = ref<number | null>(null);
const panelOpen = ref(true);
const tab = ref<Tab>("dinners");
const previewOpen = ref(false);
const nutritionOpen = ref(false);
const recipeSlug = ref<string | null>(null);
const log = ref<HTMLElement | null>(null);
const ask = ref<HTMLInputElement | null>(null);
// Stays mounted while closed so the export can print it.
const preview = ref<HTMLElement | null>(null);
const film = ref<HTMLVideoElement | null>(null);
const filmPlaying = ref(true);

const messages = computed<AgentMessage[]>(() => session.value?.messages.filter(m => m.role !== "system") ?? []);
const interaction = computed(() => session.value?.pending_interaction ?? null);
const constraints = computed(() => session.value?.constraints ?? null);
// A stated cap on how often a dish may come back; 1 is the usual ask.
const repeatLabel = (cap: number | null | undefined) => (cap == null ? null : cap === 1 ? "No repeats" : `Each dish up to ${cap} times`);
const contextLabel = computed(() => {
  const c = constraints.value;
  if (!c?.household_size) return null;
  const people = `${c.household_size} ${c.household_size === 1 ? "person" : "people"}`;
  return c.weekly_budget_sgd ? `${people} · S$${c.weekly_budget_sgd}` : people;
});
const heard = computed<Array<{ text: string; value: string; alert?: boolean }>>(() => {
  const c = constraints.value;
  if (!c) return [];
  return [
    ...(c.household_size ? [{ text: "For", value: String(c.household_size) }] : []),
    ...(c.weekly_budget_sgd ? [{ text: "Budget", value: `S$${c.weekly_budget_sgd}` }] : []),
    ...(statedTimeLimit(c.max_cooking_time_minutes) ? [{ text: "Up to", value: `${c.max_cooking_time_minutes} min` }] : []),
    ...c.dietary_preferences.map(value => ({ text: "", value: value.replaceAll("_", " ") })),
    ...c.excluded_ingredients.map(value => ({ text: "No", value: value.replaceAll("_", " ") })),
    ...c.allergens.map(value => ({ text: "No", value: allergenLabel(value).toLowerCase(), alert: true })),
    ...(repeatLabel(c.max_uses_per_recipe) ? [{ text: "", value: repeatLabel(c.max_uses_per_recipe)! }] : []),
  ];
});
const title = computed(() => messages.value.find(m => m.role === "user")?.content ?? "New plan");
const rangeLabel = computed(() => {
  if (!plan.value) return "";
  const fmt = (d: string) => formatPlanDate(d, { day: "numeric", month: "short" });
  return `${fmt(plan.value.start_date)} – ${fmt(plan.value.end_date)}`;
});
// While another week loads, the one shown before is stale: show skeletons, never its data (T38).
const stale = computed(() => planState.value === "loading" && lastPlanId.value !== plan.value?.id);
const days = computed(() => (stale.value ? [] : nutrition.dashboard.value?.days ?? []));
const groceryCount = computed(() => groceryGroups(plan.value?.grocery_estimate.items ?? []).reduce((n, g) => n + g.lines.length, 0));
const estimate = computed(() => plan.value?.grocery_estimate ?? null);
// Budget bar: within (green), near at 95% or more (amber), over (red, the overage segment marked).
const budgetBar = computed(() => {
  const budget = estimate.value?.weekly_budget_sgd;
  if (!budget) return null;
  const total = estimate.value!.purchase_total_sgd;
  const ratio = total / budget;
  const state = ratio > 1 ? "over" : ratio >= 0.95 ? "near" : "within";
  const span = Math.max(total, budget);
  return { state, spent: Math.round(Math.min(total, budget) / span * 1000) / 10, over: state === "over" ? Math.round((total - budget) / span * 1000) / 10 : 0, percent: Math.round(ratio * 100) };
});
// The footer's short budget note: "S$7.40 left" or "S$3.10 over" (the full sentence is its tooltip).
const budgetGapLabel = computed(() => {
  const gap = estimate.value ? budgetGap(estimate.value) : null;
  return gap && `${gap.amount} ${gap.over ? "over" : "left"}`;
});
// A confirmed change stamps itself on the chat for a moment.
const stamp = ref(false);
let confirming = false;
let stampTimer: ReturnType<typeof setTimeout> | undefined;
function confirmChange() {
  confirming = true;
  void agent.confirmReplan();
}
watch(() => session.value?.pending_replan, (now, before) => {
  if (before && !now && confirming && !errorMessage.value) {
    stamp.value = true;
    clearTimeout(stampTimer);
    stampTimer = setTimeout(() => { stamp.value = false; }, 1600);
  }
  if (!now) confirming = false;
});
const weekEnded = computed(() => Boolean(plan.value && plan.value.end_date < todayIsoDate()));
const readOnly = computed(() => Boolean(plan.value && replaced.value));
// The preview's buttons say what each does to this kind of change (a lock is kept, not "changed").
const choices = computed(() => previewChoices(session.value?.pending_replan?.event_type ?? "REPLACE_MEAL"));
// How far the suggested change takes the week over its budget, said before the household confirms it.
const swapOverBudget = computed(() => {
  const over = session.value?.pending_replan?.over_budget_sgd;
  return over && estimate.value?.weekly_budget_sgd ? formatSgd(over) : null;
});
// A meal added, dropped or recomposed (ADR-0046): the new dishes by day, before the household confirms.
const shapePreview = computed(() => {
  const change = session.value?.pending_replan?.shape_change;
  if (!change) return null;
  const byDay = new Map<number, string[]>();
  for (const dish of change.added) byDay.set(dish.day_index ?? 0, [...(byDay.get(dish.day_index ?? 0) ?? []), dish.recipe_title]);
  return {
    title: shapeChangeSummary(change, plan.value?.start_date),
    days: [...byDay.entries()].map(([day, titles]) => ({ day: planDayLabel(plan.value?.start_date, day), titles })),
    dishes: change.added.slice(0, 3).map(dish => ({ slug: dish.recipe_slug, title: dish.recipe_title, roleId: dish.role_id })),
    removed: change.removed.length,
  };
});
// The week shown in the panel belongs to this conversation only when the conversation planned it;
// its card never appears inside another conversation.
const ownsPlan = computed(() => Boolean(plan.value && session.value?.plan_id === plan.value.id));
const showWeek = computed(() => Boolean(ownsPlan.value && days.value.length && !stale.value && !session.value?.pending_replan));
// A conversation that planned no week changes the one beside it (see send).
const canChangeWeek = computed(() => Boolean(plan.value && !readOnly.value && (ownsPlan.value || !session.value?.plan_id)));
const readyToPlan = computed(() => Boolean(session.value?.can_confirm && session.value.status !== "planned"));
// Still asking what it needs to plan a new week: taking the current week on would drop that question.
const settingUp = computed(() => {
  const s = session.value;
  return Boolean(s && !s.plan_id && (s.pending_interaction || s.missing_fields.length || s.clarification_questions.length));
});
// A conversation planning a new week of its own asks before a dish's change takes the current week on (see send).
const planningNew = computed(() => readyToPlan.value || settingUp.value);
const initials = computed(() => (actor.value?.user.display_name ?? "?")
  .split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]!.toUpperCase()).join(""));
const home = computed(() => {
  const p = household.current.value?.current;
  const c = constraints.value;
  const size = p?.planning_household_size ?? c?.household_size ?? null;
  const budget = p?.weekly_budget_sgd ?? c?.weekly_budget_sgd ?? null;
  return {
    name: household.current.value?.name ?? actor.value?.user.display_name ?? "Your household",
    line: [size ? `${size} ${size === 1 ? "person" : "people"}` : null, budget ? `S$${budget} a week` : null].filter(Boolean).join(" · ") || "Tell me who's eating",
    chips: [
      ...(p?.dietary_preferences ?? c?.dietary_preferences ?? []).map(value => ({ label: value.replaceAll("_", " "), alert: false })),
      ...(p?.excluded_ingredients ?? c?.excluded_ingredients ?? []).map(value => ({ label: `No ${value.replaceAll("_", " ")}`, alert: false })),
      ...(p?.allergens ?? c?.allergens ?? []).map(value => ({ label: `${allergenLabel(value)} allergy`, alert: true })),
      ...(repeatLabel(c?.max_uses_per_recipe) ? [{ label: repeatLabel(c?.max_uses_per_recipe)!, alert: false }] : []),
    ],
  };
});
const recent = computed(() => {
  const current = session.value;
  const others = agent.recent.value.filter(item => item.id !== current?.id);
  return (current?.messages.length ? [current, ...others] : others).slice(0, 8);
});

function sessionTitle(item: AgentSession) {
  return item.messages.find(m => m.role === "user")?.content ?? "New plan";
}

/** The draft, with the dish action its words came from, kept across sign-in and reloads (restored on mount). */
function saveDraft() {
  try { sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ text: draft.value, action: dishAction.value })); }
  catch { /* storage may be blocked; the draft is only a convenience */ }
}

async function requireAccount(): Promise<boolean> {
  if (actor.value) return true;
  saveDraft();
  await navigateTo({ path: "/login", query: { next: "/" } });
  return false;
}

async function enter() {
  if (!(await requireAccount())) return;
  view.value = "app";
  // Until the week and its conversations are back, a send could start a second conversation (see send).
  // Nothing below throws: each request reports its own failure.
  entering.value = true;
  const version = conversationVersion;
  // The household's current week is its newest plan. It reopens with the conversation that planned
  // it; a week with no conversation (rebuilt on the profile page) opens beside a fresh one.
  const current = await currentPlanId();
  if (version !== conversationVersion) return;
  if (!session.value) await agent.restore(current);
  if (version !== conversationVersion) return;
  // An open conversation keeps its own week; one that has not planned yet shows the current week.
  const shown = session.value?.plan_id ?? current;
  if (shown) await loadPlan(shown);
  if (version === conversationVersion) entering.value = false;
}

/** The household's weeks, newest first; none when they cannot be listed (no plan yet is not an error). */
async function recentWeeks(): Promise<WeeklyMealPlanListItem[]> {
  try { return (await apiFetch<WeeklyMealPlanCollection>(`${config.public.apiBase}/api/plans`)).items; }
  catch { return []; }
}

async function currentPlanId(): Promise<number | null> {
  return (await recentWeeks())[0]?.id ?? null;
}

/** From a replaced week to the household's current one, with the conversation that planned it when it is listed. */
async function openCurrentWeek() {
  const current = await currentPlanId();
  const planner = current ? agent.recent.value.find(item => item.plan_id === current) : undefined;
  if (planner) openSession(planner);
  else showConversation(null);
}

/** The panel's week: the open conversation's own, else the household's current week. */
async function loadShownPlan() {
  planState.value = "loading";
  const current = session.value?.plan_id ? null : await currentPlanId();
  // The open conversation may have changed, or planned, while the current week was looked up.
  const shown = session.value?.plan_id ?? current;
  if (shown) await loadPlan(shown);
  else planState.value = "empty";
}

/** The week a message changes for a conversation that did not plan it: while the draft still starts with a dish action's words. */
function actionWeek(message: string): number | null {
  const action = dishAction.value;
  return !session.value?.plan_id && action && message.startsWith(action.text) ? action.week : null;
}

async function send(text = draft.value) {
  const message = text.trim();
  if (!message || entering.value) return;
  draft.value = message;
  if (!(await requireAccount())) return;
  // A dish's words sent from the landing (kept over a reload or a sign-in) first reopen the week and its
  // conversations, as Open my week does, so they reach the conversation holding the week; if that week
  // was replaced meanwhile, the words go and nothing is sent.
  if (view.value === "landing" && actionWeek(message)) {
    await enter();
    if (!dishAction.value) return;
  }
  view.value = "app";
  takeOn.value = null;
  // A dish action on a week this conversation did not plan changes that week, never plans a new one. It goes
  // to the conversation that planned the week when that one is in the recent list, so one conversation holds
  // a week; else this conversation takes the week on, after asking if that sets aside the new week it is planning.
  const week = actionWeek(message);
  const planner = week ? agent.recent.value.find(item => item.plan_id === week) : undefined;
  if (planner) {
    openSession(planner);
    draft.value = message;
  }
  else if (week) {
    if (planningNew.value) takeOn.value = { message, week };
    else await changeWeek(message, week);
    return;
  }
  const pending = interaction.value;
  let sent;
  if (pending?.allow_free_text) {
    sent = await agent.answerInteraction({
      question_id: pending.question_id,
      option_ids: [],
      free_text: message,
      context_version: pending.context_version,
      plan_revision: pending.plan_revision,
    });
  }
  else if (session.value) sent = await agent.reply(message);
  else sent = await agent.create(message);
  if (sent && draft.value === message) draft.value = "";
}

/** This conversation takes `week` on and changes it with `message`. */
async function changeWeek(message: string, week: number) {
  takeOn.value = null;
  const sent = await (session.value ? agent.reply(message, week) : agent.create(message, week));
  if (sent && draft.value === message) draft.value = "";
}

function keepPlanning() {
  takeOn.value = null;
  draft.value = "";
}

async function choose(optionId: string) {
  const pending = interaction.value;
  if (!pending) return;
  await agent.answerInteraction({
    question_id: pending.question_id,
    option_ids: [optionId],
    free_text: null,
    context_version: pending.context_version,
    plan_revision: pending.plan_revision,
  });
}

async function loadPlan(planId: number) {
  // Both the generated-plan watcher and the session watcher fire for the same plan.
  if (planState.value === "loading" && lastPlanId.value === planId) return;
  lastPlanId.value = planId;
  planState.value = "loading";
  try {
    const [loaded, weeks] = await Promise.all([
      apiFetch<WeeklyMealPlan>(`${config.public.apiBase}/api/plans/${planId}`),
      recentWeeks(),
    ]);
    // A newer request replaced this one while it was in flight; its answer is stale.
    if (lastPlanId.value !== planId) return;
    plan.value = loaded;
    replaced.value = weeks.find(week => week.id === planId)?.current === false;
    await nutrition.loadDashboard(planId);
    if (lastPlanId.value === planId) planState.value = "ready";
  }
  catch {
    if (lastPlanId.value === planId) planState.value = "error";
  }
}

function retryPlan() {
  if (lastPlanId.value) void loadPlan(lastPlanId.value);
  else void loadShownPlan();
}

async function setStatus(entryId: number, status: MealPlanEntryStatus) {
  await nutrition.updateStatus(entryId, status);
}

function openTab(name: Tab) {
  tab.value = name;
  panelOpen.value = true;
}

function suggest(text: string) {
  draft.value = text;
  dishAction.value = !ownsPlan.value && plan.value ? { text, week: plan.value.id } : null;
  ask.value?.focus();
}

function swap(day: NutritionDashboardDay) {
  suggest(`Swap ${formatPlanDate(day.planned_date, { weekday: "long" })}'s ${day.recipe.title} for something else`);
}

function exportPdf() {
  window.print();
}

function toggleFilm() {
  const video = film.value;
  if (!video) return;
  if (video.paused) void video.play();
  else video.pause();
}

/**
 * Shows `item` (null: a new conversation) with its own week in the panel, or the household's current
 * week when it planned none. Every switch of conversation goes through here.
 */
function showConversation(item: AgentSession | null) {
  conversationVersion += 1;
  entering.value = false;
  // Keep the conversation being left in the recent list, as it is now (its listed copy may be older).
  const leaving = session.value;
  if (leaving?.messages.length) {
    agent.recent.value = [leaving, ...agent.recent.value.filter(other => other.id !== leaving.id)];
  }
  agent.reset();
  session.value = item;
  plan.value = null;
  lastPlanId.value = null;
  nutrition.dashboard.value = null;
  draft.value = "";
  dishAction.value = null;
  takeOn.value = null;
  ask.value?.focus();
  void loadShownPlan();
}

function newChat() {
  showConversation(null);
}

function openSession(item: AgentSession) {
  if (item.id !== session.value?.id) showConversation(item);
}

function onKey(event: KeyboardEvent) {
  if (view.value === "app" && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    newChat();
  }
}

// The film only plays on the entry.
watch(view, (value) => {
  if (value === "app") {
    film.value?.pause();
    if (!household.current.value) void household.loadCurrent();
  }
  else void film.value?.play();
});
watch(generatedPlan, (value) => {
  if (value) void loadPlan(value.id);
});
watch(() => session.value?.plan_id, (planId) => {
  if (planId && planId !== plan.value?.id) void loadPlan(planId);
});
// The take-on question stands only while this conversation plans a new week: once it plans one
// ("Plan my week") or stops, the question goes, and so do the dish's words it held in the composer.
watch(planningNew, (planning) => {
  if (planning || !takeOn.value) return;
  if (draft.value === takeOn.value.message) draft.value = "";
  takeOn.value = null;
});
// A dish's words change only their own week. Once another week is shown or opening (planned with
// "Plan my week", replanned on another page and reopened), they go, with the words themselves if
// still unedited. Synchronous, so a send that just reopened the week sees it (see send).
watch([() => plan.value?.id, lastPlanId], (weeks) => {
  const action = dishAction.value;
  if (!action || weeks.every(week => !week || week === action.week)) return;
  if (draft.value === action.text) draft.value = "";
  dishAction.value = null;
}, { flush: "sync" });
watch(() => [messages.value.length, isLoading.value, session.value?.pending_replan?.id, showWeek.value, takeOn.value], async () => {
  await nextTick();
  log.value?.scrollTo({ top: log.value.scrollHeight, behavior: "smooth" });
});

useDialog(preview, () => { previewOpen.value = false; }, previewOpen);

watch(draft, (value) => {
  if (!value) dishAction.value = null;
  // The take-on question sends its own message: it goes once the composer says something else.
  if (takeOn.value && value !== takeOn.value.message) takeOn.value = null;
});
// Kept as it is typed, so a session that expires mid-sentence loses nothing.
watch([draft, dishAction], saveDraft);

onMounted(() => {
  window.addEventListener("keydown", onKey);
  try {
    const saved = JSON.parse(sessionStorage.getItem(DRAFT_KEY) ?? "null") as { text?: string; action?: typeof dishAction.value } | null;
    if (saved?.text) {
      draft.value = saved.text;
      dishAction.value = saved.action ?? null;
    }
    sessionStorage.removeItem(DRAFT_KEY);
  }
  catch { /* ignore */ }
});
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="mc-surface" :data-view="view">
    <svg width="0" height="0" class="defs" aria-hidden="true">
      <symbol id="mc-logo" viewBox="0 0 32 32"><circle cx="16" cy="18" r="10.5" /><path class="leaf" d="M16 7.5c1.4-3.2 4.6-4.2 7-3.3-.9 2.8-3.7 4.4-7 3.3z" /></symbol>
    </svg>
    <div class="film" aria-hidden="true">
      <video ref="film" autoplay muted loop playsinline preload="auto" poster="/media/hero-poster.jpg" @play="filmPlaying = true" @pause="filmPlaying = false">
        <source src="/media/hero.mp4" type="video/mp4">
      </video>
    </div>

    <Transition name="landing">
      <section v-if="view === 'landing'" class="landing" aria-label="Home">
        <header class="topbar">
          <span class="brand"><svg aria-hidden="true"><use href="#mc-logo" /></svg><span class="mc-serif">MealCraft</span></span>
          <span class="spacer" />
          <NuxtLink v-if="!actor" to="/login?next=/" class="link">Sign in</NuxtLink>
          <button type="button" class="cta" @click="enter">Let’s plan my week</button>
          <NuxtLink v-if="actor" to="/profile" class="avatar" :aria-label="`Household settings for ${actor.user.display_name}`">{{ initials }}</NuxtLink>
        </header>
        <div class="hero-block">
          <h1 class="hero mc-serif">Plan the week.<br>Shop it once.<br><em>Eat well.</em></h1>
          <p class="lede">Tell us who’s eating and what you can spend. We plan the meals and price the groceries at FairPrice.</p>
          <form class="ask" @submit.prevent="send()">
            <label for="mc-ask" class="visually-hidden">Message MealCraft</label>
            <input id="mc-ask" v-model="draft" type="text" autocomplete="off" placeholder="What should this week look like…  e.g. dinners for two, no seafood">
            <button type="submit" class="send" aria-label="Send" :disabled="isLoading || !draft.trim()">
              <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </form>
          <div class="starters">
            <button v-for="starter in starters" :key="starter" type="button" class="mc-pill" @click="send(starter)">{{ starter }}</button>
          </div>
        </div>
        <p class="trust"><span>Allergies and dislikes respected</span><span>Prices from FairPrice</span><span>Nutrition counted as you cook</span></p>
        <button type="button" class="film-toggle mc-pill" :aria-label="filmPlaying ? 'Pause background video' : 'Play background video'" @click="toggleFilm">
          <svg v-if="filmPlaying" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6v12M15 6v12" /></svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>
        </button>
      </section>
    </Transition>

    <div v-if="view === 'app'" class="app" :class="{ 'no-panel': !panelOpen }">
      <aside class="rail" aria-label="Navigation">
        <button type="button" class="brand" aria-label="Back to home" @click="view = 'landing'">
          <span class="logo-dot" aria-hidden="true" /><span class="mc-serif">MealCraft</span>
        </button>
        <button type="button" class="new mc-btn strong" @click="newChat">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>New plan<kbd>Ctrl K</kbd>
        </button>
        <nav class="nav-list" aria-label="Sections">
          <button type="button" class="nav" aria-current="page" @click="ask?.focus()"><i aria-hidden="true" />Assistant</button>
          <button type="button" class="nav" @click="openTab('dinners')"><i aria-hidden="true" />This week<span v-if="days.length" class="count">{{ days.length }}</span></button>
          <button type="button" class="nav" @click="openTab('groceries')"><i aria-hidden="true" />Groceries<span v-if="groceryCount" class="count">{{ groceryCount }}</span></button>
          <button type="button" class="nav" @click="openTab('nutrition')"><i aria-hidden="true" />Nutrition</button>
          <NuxtLink to="/browse" class="nav"><i aria-hidden="true" />Recipes and groceries</NuxtLink>
          <NuxtLink to="/history" class="nav"><i aria-hidden="true" />Past weeks</NuxtLink>
          <NuxtLink to="/profile" class="nav"><i aria-hidden="true" />Household</NuxtLink>
        </nav>
        <div v-if="recent.length" class="recent-block">
          <div class="mc-label rail-label">Recent</div>
          <div class="recent">
            <button v-for="item in recent" :key="item.id" type="button" :class="{ on: item.id === session?.id }" :title="sessionTitle(item)" @click="openSession(item)">
              {{ sessionTitle(item) }}
            </button>
          </div>
        </div>
        <div class="home-card">
          <div class="who">
            <span class="avatar">{{ initials }}</span>
            <div><b>{{ home.name }}</b><small>{{ home.line }}</small></div>
          </div>
          <div v-if="home.chips.length" class="chips">
            <span v-for="chip in home.chips" :key="chip.label" class="mc-chip" :class="{ alert: chip.alert }">{{ chip.label }}</span>
          </div>
          <div class="home-links">
            <NuxtLink to="/profile">Household</NuxtLink>
            <NuxtLink to="/system">Status</NuxtLink>
            <button type="button" class="out" @click="logout">Sign out</button>
          </div>
        </div>
      </aside>

      <main class="chat">
        <header class="chat-head">
          <h1 class="mc-heading">{{ title }}</h1>
          <span v-if="plan" class="date">{{ rangeLabel }}</span>
          <span class="spacer" />
          <button type="button" class="ghost" :aria-pressed="panelOpen" @click="panelOpen = !panelOpen">{{ panelOpen ? "Hide plan" : "Show plan" }}</button>
        </header>

        <section ref="log" class="thread" aria-label="Conversation" aria-live="polite">
          <div class="col">
            <div v-if="!messages.length && !isLoading" class="bot mc-rise">
              <p>Tell me who's eating, what you can spend and anything to avoid. I'll plan the week's meals and one shopping list.</p>
              <div class="options">
                <button v-for="starter in starters" :key="starter" type="button" class="mc-suggest" @click="send(starter)">{{ starter }}</button>
              </div>
            </div>

            <template v-for="message in messages" :key="message.id">
              <div v-if="message.role === 'user'" class="me mc-rise">{{ message.content }}</div>
              <div v-else class="bot mc-rise"><p>{{ message.content }}</p></div>
            </template>

            <div v-if="interaction?.options.length" class="options mc-rise">
              <button v-for="option in interaction.options" :key="option.id" type="button" class="mc-btn secondary sm" :disabled="isLoading" @click="choose(option.id)">
                {{ option.label }}
              </button>
            </div>

            <div v-if="readyToPlan" class="card mc-card mc-rise">
              <div class="card-body">
                <div v-if="heard.length" class="heard">
                  <span v-for="item in heard" :key="item.text + item.value" class="mc-chip" :class="{ alert: item.alert }">{{ item.text }} <b>{{ item.value }}</b></span>
                </div>
                <p>Ready to plan your week with these details.</p>
              </div>
              <div class="card-foot">
                <button type="button" class="mc-btn primary" :disabled="isLoading" @click="agent.confirm()">
                  {{ isLoading ? "Planning your week…" : "Plan my week" }}
                </button>
              </div>
            </div>

            <div v-if="takeOn" class="card mc-card mc-rise" aria-label="Change the current week here?">
              <div class="card-body"><p>This conversation is {{ readyToPlan ? "ready to plan" : "still setting up" }} a new week. Changing the current week here sets that aside.</p></div>
              <div class="card-foot">
                <button type="button" class="mc-btn primary" :disabled="isLoading" @click="changeWeek(takeOn.message, takeOn.week)">Change the current week</button>
                <button type="button" class="mc-btn secondary" :disabled="isLoading" @click="keepPlanning">Keep planning</button>
              </div>
            </div>

            <HomeWeekCard
              v-if="showWeek && estimate"
              class="mc-rise"
              :days="days"
              :estimate="estimate"
              :range-label="rangeLabel"
              :household-size="plan?.household_size ?? null"
              @open="openTab"
              @open-recipe="recipeSlug = $event"
            />

            <div v-if="readOnly" class="card mc-card mc-rise" aria-label="A replaced week">
              <div class="card-body"><p>You planned these days again, so this week was replaced. It stays here to read; changes go to your current week.</p></div>
              <div class="card-foot">
                <button type="button" class="mc-btn primary" @click="openCurrentWeek">Open the current week</button>
              </div>
            </div>

            <div v-else-if="weekEnded && plan && !isLoading" class="card mc-card mc-rise">
              <div class="card-body"><p>This plan ended on {{ formatPlanDate(plan.end_date, { weekday: "long", day: "numeric", month: "short" }) }}. Tell me about this week and I'll plan a new one.</p></div>
            </div>

            <article v-if="session?.pending_replan && shapePreview" class="swap-card mc-card mc-rise" aria-label="Proposed change to your meals">
              <div class="swap-head">
                <span class="mc-label">Proposed change</span>
                <span class="to">{{ shapePreview.title }}</span>
              </div>
              <div class="shape-body">
                <div class="plates">
                  <HomeDishIcon v-for="dish in shapePreview.dishes" :key="dish.slug" class="swap-icon" :title="dish.title" :role-id="dish.roleId" :size="48" />
                </div>
                <ul v-if="shapePreview.days.length" class="shape-days">
                  <li v-for="item in shapePreview.days" :key="item.day"><b>{{ item.day }}</b> {{ item.titles.join(" · ") }}</li>
                </ul>
              </div>
              <div class="delta">
                <span>
                  <template v-if="shapePreview.removed">{{ shapePreview.removed }} {{ shapePreview.removed === 1 ? "dish comes" : "dishes come" }} off ·</template>
                  {{ groceriesChange(session.pending_replan.purchase_total_delta_sgd) }} · the other meals stay the same
                </span>
                <span v-if="swapOverBudget" class="mc-chip warn" :title="`This puts the week ${swapOverBudget} over your ${formatSgd(estimate!.weekly_budget_sgd!)} budget.`">{{ swapOverBudget }} over your {{ formatSgd(estimate!.weekly_budget_sgd!) }}</span>
              </div>
              <div class="card-foot">
                <button type="button" class="mc-btn primary" :disabled="isLoading" @click="confirmChange">{{ choices.confirm }}</button>
                <button type="button" class="mc-btn secondary" :disabled="isLoading" @click="agent.discardReplan()">{{ choices.discard }}</button>
              </div>
            </article>

            <article v-else-if="session?.pending_replan?.before_entry && session.pending_replan.after_entry" class="swap-card mc-card mc-rise" aria-label="Proposed change to your meals">
              <div class="swap-head">
                <span class="mc-label">{{ [changedMealWhen(session.pending_replan, plan?.start_date), "proposed change"].filter(Boolean).join(" · ") }}</span>
                <span class="to">{{ sameDishChange(session.pending_replan) ?? "Swap this dish?" }}</span>
              </div>
              <div class="tiles" :class="{ single: sameDishChange(session.pending_replan) }">
                <div class="tile-dish before">
                  <HomeDishIcon :title="session.pending_replan.before_entry.recipe_title" :role-id="session.pending_replan.before_entry.role_id" :size="48" />
                  <s v-if="!sameDishChange(session.pending_replan)">{{ session.pending_replan.before_entry.recipe_title }}</s>
                  <b v-else>{{ session.pending_replan.before_entry.recipe_title }}</b>
                </div>
                <template v-if="!sameDishChange(session.pending_replan)">
                  <svg class="arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                  <div class="tile-dish after">
                    <HomeDishIcon :title="session.pending_replan.after_entry.recipe_title" :role-id="session.pending_replan.after_entry.role_id" :size="48" />
                    <b>{{ session.pending_replan.after_entry.recipe_title }}</b>
                  </div>
                </template>
              </div>
              <div class="delta">
                <span>
                  {{ session.pending_replan.nutrition_delta.calories_kcal >= 0 ? "+" : "" }}{{ Math.round(session.pending_replan.nutrition_delta.calories_kcal) }} kcal ·
                  {{ groceriesChange(session.pending_replan.purchase_total_delta_sgd) }} · the rest of the week stays the same
                </span>
                <span v-if="swapOverBudget" class="mc-chip warn" :title="`This puts the week ${swapOverBudget} over your ${formatSgd(estimate!.weekly_budget_sgd!)} budget.`">{{ swapOverBudget }} over your {{ formatSgd(estimate!.weekly_budget_sgd!) }}</span>
              </div>
              <div class="card-foot">
                <button type="button" class="mc-btn primary" :disabled="isLoading" @click="confirmChange">{{ choices.confirm }}</button>
                <button type="button" class="mc-btn secondary" :disabled="isLoading" @click="agent.discardReplan()">{{ choices.discard }}</button>
              </div>
            </article>

            <p v-if="session?.pending_replan && estimate?.pricing_mode === 'live'" class="caveat mc-small">Grocery changes are estimates. Selected product prices are checked again when you confirm.</p>
            <div v-if="stamp" class="stamp" role="status"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5 9-10" /></svg>Change made</div>
            <div v-if="isLoading" class="typing" aria-label="MealCraft is thinking"><span /><span /><span /></div>
            <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
          </div>
        </section>

        <div class="composer-wrap">
          <div class="after">
            <template v-if="canChangeWeek">
              <button v-for="text in followUps" :key="text" type="button" class="mc-suggest" @click="suggest(text)">{{ text }}</button>
            </template>
            <span class="fine">Suggestions can be wrong. Check allergens on product labels.</span>
          </div>
          <form class="composer" @submit.prevent="send()">
            <span v-if="contextLabel" class="mc-chip context">{{ contextLabel }}</span>
            <label for="mc-ask" class="visually-hidden">Message MealCraft</label>
            <input
              id="mc-ask"
              ref="ask"
              v-model="draft"
              type="text"
              autocomplete="off"
              :placeholder="interaction?.prompt || (ownsPlan ? 'Swap a night, change the budget, use up what\'s in the fridge' : 'Who\'s eating, what to spend, anything to avoid…')"
            >
            <button type="submit" class="send" aria-label="Send" :disabled="isLoading || entering || readOnly || !draft.trim()">
              <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </form>
        </div>
      </main>

      <aside v-if="panelOpen" class="panel" aria-label="This week">
        <template v-if="plan && days.length && !stale">
          <div class="panel-head">
            <div class="tabs mc-segmented" role="tablist" aria-label="Plan details">
              <button id="tab-dinners" type="button" role="tab" :aria-selected="tab === 'dinners'" aria-controls="panel-body" @click="tab = 'dinners'">Week</button>
              <button id="tab-groceries" type="button" role="tab" :aria-selected="tab === 'groceries'" aria-controls="panel-body" @click="tab = 'groceries'">
                Groceries <span class="c">{{ groceryCount }}</span>
              </button>
              <button id="tab-nutrition" type="button" role="tab" :aria-selected="tab === 'nutrition'" aria-controls="panel-body" @click="tab = 'nutrition'">Nutrition</button>
            </div>
          </div>
          <div id="panel-body" class="panel-body" role="tabpanel" :aria-labelledby="`tab-${tab}`">
            <template v-if="tab === 'dinners'">
              <HomeTonight
                :days="days"
                :updating-entry-id="nutrition.updatingEntryId.value"
                :readonly="readOnly"
                @mark-cooked="setStatus($event, 'completed')"
                @mark-meal="nutrition.updateMeal($event.dayIndex, $event.mealType, 'completed', $event.dishes[0]?.entry_id ?? 0)"
                @open-recipe="recipeSlug = $event"
                @swap="swap"
              />
              <HomeMealList :days="days" :readonly="readOnly" :plan-id="plan.id" :revision="plan.revision" :start-date="plan.start_date" @open-recipe="recipeSlug = $event" @ask="suggest" />
            </template>
            <HomeGroceryList v-else-if="tab === 'groceries'" :estimate="plan.grocery_estimate" />
            <HomeNutritionSummary
              v-else-if="nutrition.dashboard.value"
              :dashboard="nutrition.dashboard.value"
              :sodium-limit="constraints?.max_sodium_mg_per_meal ?? household.current.value?.current.max_sodium_mg_per_meal ?? null"
              @details="nutritionOpen = true"
            />
          </div>
          <footer v-if="estimate && tab !== 'nutrition'" class="panel-foot">
            <div class="spend">
              <b class="mc-title mc-num">{{ formatSgd(estimate.purchase_total_sgd) }}</b>
              <span class="of">{{ estimate.weekly_budget_sgd ? `of ${formatSgd(estimate.weekly_budget_sgd)} · ` : "" }}{{ groceryCount }} items</span>
              <span v-if="budgetGapLabel" class="left" :class="budgetBar?.state" :title="budgetLine(estimate) ?? undefined">{{ budgetGapLabel }}</span>
            </div>
            <div v-if="budgetBar" class="meter" :class="budgetBar.state" role="img" :aria-label="`${budgetBar.percent} percent of the weekly budget${budgetBar.state === 'over' ? ', over budget' : ''}`">
              <i class="fill" :style="{ width: `${budgetBar.spent}%` }" />
              <i v-if="budgetBar.over" class="overage" :style="{ width: `${budgetBar.over}%` }" />
            </div>
            <div v-if="tab === 'groceries'" class="foot-acts">
              <button type="button" class="mc-btn secondary" @click="previewOpen = true">Preview list</button>
              <button type="button" class="mc-btn quiet" @click="exportPdf">Export PDF</button>
            </div>
          </footer>
        </template>
        <HomePanelState
          v-else
          :state="planState === 'ready' ? 'empty' : planState"
          title="This week"
          empty-text="Your week shows up here once it's planned: your next meal, the shopping list and nutrition."
          error-text="Your week couldn't be loaded."
          :rows="6"
          @retry="retryPlan"
        />
      </aside>
    </div>

    <HomeNutritionSheet
      v-if="nutritionOpen && nutrition.dashboard.value"
      :dashboard="nutrition.dashboard.value"
      :updating-entry-id="nutrition.updatingEntryId.value"
      :readonly="readOnly"
      @close="nutritionOpen = false"
      @set-status="setStatus"
    />
    <HomeRecipeSheet v-if="recipeSlug" :slug="recipeSlug" @close="recipeSlug = null" />

    <div v-if="plan" v-show="previewOpen" ref="preview" class="mc-sheet-overlay" role="dialog" aria-modal="true" aria-label="Shopping list preview">
      <div class="sheet-frame">
        <HomeShoppingSheet class="mc-print-sheet" :estimate="plan.grocery_estimate" :range-label="rangeLabel" :household-size="plan.household_size" />
      </div>
      <div class="sheet-actions">
        <button type="button" class="mc-btn secondary" @click="previewOpen = false">Back</button>
        <button type="button" class="mc-btn primary" @click="exportPdf">Export PDF</button>
      </div>
    </div>
    <div class="mc-grain" aria-hidden="true" />
  </div>
</template>

<style scoped>
.defs { position: absolute; }
.brand svg { fill: #fff; stroke: none; }
:deep(.leaf) { fill: #8fe3a6; stroke: none; }

/* Film entry */
.film { position: absolute; inset: 0; transition: opacity 900ms var(--ease), transform 1200ms var(--ease), filter 900ms var(--ease); }
.film video { width: 100%; height: 100%; object-fit: cover; }
.film::after { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(14, 12, 10, 0.28) 0%, rgba(14, 12, 10, 0) 30%, rgba(14, 12, 10, 0.18) 55%, rgba(14, 12, 10, 0.6) 82%, rgba(14, 12, 10, 0.85) 100%); }
[data-view="app"] .film { opacity: 0; transform: scale(1.06); filter: blur(20px); }

/* Landing (Main artboard): header 72, hero block at left 72 / top 170, trust row bottom-left. */
.landing { position: absolute; inset: 0; z-index: 2; color: #fff; }
.landing-leave-active { transition: opacity 500ms var(--ease), transform 700ms var(--ease); }
.landing-enter-active { transition: opacity 600ms var(--ease) 200ms, transform 900ms var(--ease) 200ms; }
.landing-leave-to, .landing-enter-from { opacity: 0; transform: translateY(-24px); }
.topbar { height: 72px; padding: 0 40px; display: flex; align-items: center; gap: 18px; }
.brand { display: flex; align-items: center; gap: 10px; padding: 0; border: 0; background: none; color: var(--c-ink); }
.landing .brand { color: #fff; }
.brand svg { width: 26px; height: 26px; }
.brand > span { font-size: 22px; line-height: 28px; letter-spacing: -0.3px; }
.spacer { flex: 1; }
.link { padding: 10px 6px; font-size: 15px; font-weight: 700; color: #fff; text-decoration: none; }
.link:hover { color: #ffe27a; }
.cta { padding: 10px 20px; border: 0; border-radius: 999px; background: #fff; color: #1b1b3a; font-size: 15px; font-weight: 800; }
.cta:hover { background: #fff4d6; }
.avatar { width: 34px; height: 34px; flex: none; border-radius: 50%; display: grid; place-items: center; background: rgba(255, 255, 255, 0.22); color: #fff; font-size: 12px; font-weight: 800; text-decoration: none; }
.hero-block { position: absolute; left: 72px; top: 170px; width: 720px; display: flex; flex-direction: column; gap: 24px; }
.hero { margin: 0; font-size: 64px; line-height: 1.02; letter-spacing: -1.5px; color: #fff; }
.hero em { color: #ffe27a; font-style: normal; }
.lede { margin: 0; max-width: 520px; font-size: 18px; line-height: 1.5; font-weight: 600; color: rgba(255, 255, 255, 0.88); }
.ask { width: 600px; display: flex; align-items: center; gap: 10px; padding: 7px 7px 7px 20px; border-radius: 18px; background: #fff; }
.ask input, .composer input { flex: 1; min-width: 0; border: 0; background: transparent; outline: 0; color: var(--c-ink); font: inherit; }
.ask input { height: 46px; color: #1b1b3a; font-size: 16px; font-weight: 600; }
.ask input::placeholder, .composer input::placeholder { color: var(--c-muted); }
.send { width: 40px; height: 40px; flex: none; border-radius: 12px; border: 0; background: var(--c-ink); color: #fff !important; display: grid; place-items: center; }
.send svg { width: 18px; height: 18px; }
.ask .send { width: 46px; height: 46px; border-radius: 13px; background: var(--c-coral); }
.ask .send svg { width: 20px; height: 20px; }
.starters { display: flex; flex-wrap: wrap; gap: 8px; }
.landing .mc-pill { min-height: 0; padding: 8px 15px; border-radius: 999px; background: rgba(255, 255, 255, 0.14); border: 1px solid rgba(255, 255, 255, 0.45); color: #fff; font-size: 14px; font-weight: 700; }
.landing .mc-pill:hover:not(:disabled) { background: rgba(255, 255, 255, 0.24); border-color: rgba(255, 255, 255, 0.7); }
.trust { position: absolute; left: 72px; bottom: 28px; margin: 0; display: flex; gap: 22px; font-size: 14px; font-weight: 700; color: rgba(255, 255, 255, 0.85); }
.trust span { display: inline-flex; align-items: center; gap: 8px; }
.trust span::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--c-coral); }
.trust span:nth-child(2)::before { background: #ffe27a; }
.trust span:nth-child(3)::before { background: #8fe3a6; }
.landing .film-toggle { position: absolute; right: 40px; bottom: 22px; width: 36px; height: 36px; padding: 0; }
.film-toggle svg { width: 14px; height: 14px; }

/* Workspace: three fixed columns, nothing floats over anything */
.app { position: absolute; inset: 0; z-index: 1; display: grid; grid-template-columns: 236px minmax(0, 1fr) 424px; animation: mc-rise 900ms var(--ease) 200ms both; }
.app.no-panel { grid-template-columns: 236px minmax(0, 1fr); }

/* Rail */
.rail { display: flex; flex-direction: column; gap: 20px; min-height: 0; padding: 20px 16px; border-right: 1px solid var(--c-line); background: var(--c-rail); }
.rail .brand { padding: 0 8px; }
.rail .brand > span { font-size: 20px; line-height: 24px; }
.logo-dot { width: 22px; height: 22px; flex: none; border-radius: 50%; background: var(--c-coral); }
.new { width: 100%; justify-content: flex-start; padding: 0 14px; }
.new kbd { margin-left: auto; font: 700 12px var(--sans); color: #b9b6cc; }
.nav-list { display: grid; gap: 2px; }
.nav { display: flex; align-items: center; gap: 10px; width: 100%; height: 36px; padding: 0 10px; border: 0; border-radius: 10px; background: transparent; color: var(--c-ink) !important; font-size: 14px; font-weight: 700; text-align: left; text-decoration: none; white-space: nowrap; }
.nav i { width: 8px; height: 8px; flex: none; border-radius: 3px; background: var(--c-dot); }
.nav:hover { background: rgba(42, 42, 72, 0.04); }
.nav[aria-current="page"] { background: #fff; font-weight: 800; }
.nav[aria-current="page"] i { background: var(--c-coral); }
.count { margin-left: auto; font-size: 12px; color: var(--c-muted); }
/* The list gives way to the rail and scrolls; each row keeps its own height. */
.recent-block { min-height: 0; display: flex; flex-direction: column; }
.rail-label { padding: 0 10px 6px; }
.recent { min-height: 0; display: grid; grid-auto-rows: max-content; gap: 2px; overflow: auto; }
.recent button { width: 100%; height: 34px; padding: 0 10px; border: 0; border-radius: 10px; background: transparent; color: var(--c-neutral-text); font-size: 14px; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.recent button:hover { color: var(--c-ink); background: rgba(42, 42, 72, 0.05); }
.recent button.on { color: var(--c-ink); background: #fff; box-shadow: 0 0 0 1px var(--c-line); font-weight: 800; }
.home-card { margin-top: auto; display: flex; flex-direction: column; gap: 10px; padding: 14px; border: 1px solid var(--c-line); border-radius: 16px; background: #fff; }
.who { display: flex; align-items: center; gap: 10px; min-width: 0; }
.who .avatar { width: 32px; height: 32px; background: var(--c-neutral); color: var(--c-ink); }
.who > div { min-width: 0; display: flex; flex-direction: column; }
.who b { font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who small { font-size: 12px; line-height: 16px; color: var(--c-muted); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.home-links { display: flex; gap: 14px; font-size: 12px; font-weight: 800; white-space: nowrap; }
.home-links a, .home-links button { padding: 0; border: 0; background: none; color: var(--c-ink); font-size: 12px; font-weight: 800; text-decoration: none; }
.home-links .out { color: var(--c-muted); }
.home-links a:hover, .home-links button:hover { color: var(--c-coral); }

/* Chat column on the canvas */
.chat { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--c-canvas); }
.chat-head { height: 56px; flex: none; display: flex; align-items: center; gap: 10px; padding: 0 28px; border-bottom: 1px solid var(--c-line); background: #fff; }
.chat-head h1 { min-width: 0; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.date { flex: none; color: var(--c-muted); font-size: 13px; }
.ghost { flex: none; height: 32px; padding: 0 12px; border: 0; border-radius: 10px; background: transparent; color: var(--c-ink) !important; font-size: 13px; font-weight: 800; }
.ghost:hover { background: var(--c-neutral); }
.thread { flex: 1; min-height: 0; overflow: auto; padding: 20px 28px; }
.col { max-width: 720px; margin: 0 auto; display: flex; flex-direction: column; gap: 16px; }
.me { align-self: flex-end; max-width: 420px; padding: 10px 14px; border-radius: 16px 16px 4px 16px; background: var(--c-ink); color: #fff; white-space: pre-line; }
.bot { display: flex; flex-direction: column; gap: 12px; }
.bot p { margin: 0; max-width: 560px; white-space: pre-line; }
.options, .heard { display: flex; flex-wrap: wrap; gap: 8px; }
.heard { gap: 6px; }
.card { align-self: flex-start; width: min(460px, 100%); }
.card-body { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px; }
.card-body p { margin: 0; }
.card-foot { display: flex; flex-wrap: wrap; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--c-line-soft); }

/* Swap preview (Panels artboard): before struck and faded, after with a green inset ring. */
.swap-card { align-self: stretch; max-width: 560px; }
.swap-head { display: flex; flex-direction: column; gap: 2px; padding: 16px 20px 12px; }
.to { font-family: var(--font-display); font-weight: 700; font-size: 18px; line-height: 24px; }
.tiles { display: grid; grid-template-columns: minmax(0, 1fr) 28px minmax(0, 1fr); align-items: center; gap: 8px; padding: 4px 20px 16px; }
.tiles.single { grid-template-columns: minmax(0, 1fr); }
.tile-dish { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 12px 8px; border-radius: 12px; text-align: center; font-size: 13px; font-weight: 800; }
.tile-dish.before { background: var(--c-canvas); }
.tiles:not(.single) .tile-dish.before { opacity: 0.75; }
.tile-dish.before s { color: var(--c-muted); }
.tile-dish.after { background: var(--c-ok-bg); box-shadow: inset 0 0 0 1.5px var(--c-green); }
.arrow { width: 28px; height: 28px; fill: none; stroke: var(--c-ink); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.shape-body { display: flex; align-items: center; gap: 16px; padding: 4px 20px 16px; }
.plates { display: flex; align-items: center; flex: none; }
.plates .swap-icon + .swap-icon { margin-left: -14px; }
.shape-days { margin: 0; padding: 0; list-style: none; display: grid; gap: 2px; font-size: 13px; color: var(--c-neutral-text); }
.shape-days b { display: inline-block; min-width: 34px; color: var(--c-ink); font-weight: 800; }
.delta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 10px 20px; border-top: 1px solid var(--c-line-soft); background: var(--c-canvas); font-size: 13px; color: var(--c-neutral-text); }
.delta .mc-chip { margin-left: auto; }
.caveat { margin: 0; }

.stamp { align-self: flex-start; display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border: 2px solid var(--c-green); border-radius: 8px; color: var(--c-green-text); font: 800 13px var(--serif); letter-spacing: 0.08em; text-transform: uppercase; transform: rotate(-3deg); animation: mc-stamp 520ms var(--ease) both; }
.stamp svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
@keyframes mc-stamp { 0% { opacity: 0; transform: rotate(-3deg) scale(1.8); } 60% { opacity: 1; transform: rotate(-3deg) scale(0.94); } 100% { transform: rotate(-3deg) scale(1); } }
.typing { display: flex; gap: 5px; padding: 8px 0; }
.typing span { width: 7px; height: 7px; border-radius: 999px; background: var(--c-muted); animation: mc-dot 1.2s ease-in-out infinite; }
.typing span:nth-child(2) { animation-delay: 150ms; }
.typing span:nth-child(3) { animation-delay: 300ms; }
@keyframes mc-dot { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.error { margin: 0; padding: 10px 14px; border-radius: 12px; background: var(--c-allergy-bg); color: var(--c-allergy-text); font-size: 13px; }

/* Suggestions above the composer; ink send. */
.composer-wrap { flex: none; padding: 0 28px 18px; }
.after { max-width: 720px; margin: 0 auto 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.fine { margin-left: auto; font-size: 12px; line-height: 16px; color: var(--c-muted); }
.composer { max-width: 720px; height: 52px; margin: 0 auto; display: flex; align-items: center; gap: 8px; padding: 0 6px 0 16px; border-radius: 16px; background: #fff; border: 1px solid var(--c-border); }
.composer input { height: 40px; font-size: 14px; font-weight: 600; }
.composer .context { flex: none; margin-left: -8px; }

/* Right panel */
.panel { display: flex; flex-direction: column; min-height: 0; background: #fff; border-left: 1px solid var(--c-line); }
.panel-head { height: 56px; flex: none; display: flex; align-items: center; padding: 0 16px; border-bottom: 1px solid var(--c-line); }
.tabs .c { color: var(--c-muted); }
.panel-body { flex: 1; min-height: 0; overflow: auto; }
.panel-foot { flex: none; display: flex; flex-direction: column; gap: 8px; padding: 14px 16px 16px; border-top: 1px solid var(--c-line); }
.spend { display: flex; align-items: baseline; gap: 8px; }
.spend .of { min-width: 0; font-size: 12px; color: var(--c-muted); white-space: nowrap; }
.spend .left { margin-left: auto; white-space: nowrap; color: var(--c-green-text); font-size: 12px; font-weight: 800; }
.spend .left.near, .spend .left.over { color: var(--c-amber-text); }
.meter { display: flex; height: 8px; border-radius: 999px; background: var(--c-line-soft); overflow: hidden; }
.meter i { display: block; height: 100%; transition: width 600ms var(--ease); }
.meter .fill { border-radius: 999px; background: var(--c-green); }
.meter.near .fill { background: var(--c-amber); }
.meter.over .fill { border-radius: 999px 0 0 999px; background: var(--c-amber); border-right: 2px solid #fff; }
.meter .overage { background: repeating-linear-gradient(135deg, var(--c-amber-text) 0 4px, #b86b00 4px 8px); }
.foot-acts { display: flex; gap: 8px; margin-top: 2px; }
.foot-acts button { flex: 1; }

/* Shopping list preview */
.mc-sheet-overlay { position: fixed; inset: 0; z-index: 20; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; padding: 16px; background: rgba(42, 42, 72, 0.45); animation: mc-rise 420ms var(--ease) both; }
.sheet-frame { width: min(680px, 100%); max-height: calc(100vh - 160px); overflow-y: auto; border-radius: 6px; box-shadow: 0 8px 30px rgba(42, 42, 72, 0.25); }
.sheet-actions { display: flex; gap: 10px; }
.sheet-actions button { min-width: 140px; }

/* Narrower screens: the plan drops below the chat and the page scrolls. */
@media (max-width: 1200px) {
  .mc-surface { overflow: auto; }
  .app, .app.no-panel { grid-template-columns: 220px minmax(0, 1fr); min-height: 100%; bottom: auto; }
  .panel { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--c-line); }
  .panel-body { overflow: visible; }
  .chat { height: 100vh; position: sticky; top: 0; }
}
</style>
