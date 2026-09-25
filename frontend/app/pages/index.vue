<script setup lang="ts">
import { allergenLabel } from "~/lib/allergens";
import { budgetLine, formatSgd, groceryGroups, plateStyle } from "~/lib/home-surface";
import { formatPlanDate } from "~/lib/meal-plan-format";
import type { AgentMessage, AgentSession } from "~/types/agent";
import type { MealPlanEntryStatus, NutritionDashboardDay, WeeklyMealPlan, WeeklyMealPlanCollection } from "~/types/meal-plan";

useHead({ title: "MealCraft" });

type Tab = "dinners" | "groceries" | "nutrition";

const DRAFT_KEY = "mealcraft-draft";
const starters = ["Dinners for two this week, around S$90", "A high-protein week", "Vegetarian, under S$60"];
const followUps = ["Make one night vegetarian", "Make it S$10 cheaper", "I have eggs and spinach to use up"];

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const { actor, logout } = useAuth();
const agent = useMealCraftAgent();
const { session, isLoading, errorMessage, generatedPlan } = agent;
const nutrition = useNutritionDashboard();
const household = useHouseholdProfile();

const view = ref<"landing" | "app">("landing");
const draft = ref("");
const plan = ref<WeeklyMealPlan | null>(null);
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
    ...(c.max_cooking_time_minutes ? [{ text: "Up to", value: `${c.max_cooking_time_minutes} min` }] : []),
    ...c.dietary_preferences.map(value => ({ text: "", value: value.replaceAll("_", " ") })),
    ...c.excluded_ingredients.map(value => ({ text: "No", value: value.replaceAll("_", " ") })),
    ...c.allergens.map(value => ({ text: "No", value: allergenLabel(value).toLowerCase(), alert: true })),
  ];
});
const title = computed(() => messages.value.find(m => m.role === "user")?.content ?? "New plan");
const rangeLabel = computed(() => {
  if (!plan.value) return "";
  const fmt = (d: string) => formatPlanDate(d, { day: "numeric", month: "short" });
  return `${fmt(plan.value.start_date)} – ${fmt(plan.value.end_date)}`;
});
const days = computed(() => nutrition.dashboard.value?.days ?? []);
const groceryCount = computed(() => groceryGroups(plan.value?.grocery_estimate.items ?? []).reduce((n, g) => n + g.lines.length, 0));
const estimate = computed(() => plan.value?.grocery_estimate ?? null);
const budgetShare = computed(() => {
  const budget = estimate.value?.weekly_budget_sgd;
  return budget ? Math.min(100, estimate.value!.purchase_total_sgd / budget * 100) : null;
});
const showWeek = computed(() => Boolean(plan.value && days.value.length && !session.value?.can_confirm && !session.value?.pending_replan));
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

async function requireAccount(): Promise<boolean> {
  if (actor.value) return true;
  try { sessionStorage.setItem(DRAFT_KEY, draft.value); }
  catch { /* storage may be blocked; the draft is only a convenience */ }
  await navigateTo({ path: "/login", query: { next: "/" } });
  return false;
}

async function enter() {
  if (!(await requireAccount())) return;
  view.value = "app";
  if (!session.value) await agent.restoreLatest();
  // A plan made on the profile page has no conversation; show the latest one.
  if (!session.value?.plan_id && !plan.value) await loadLatestPlan();
}

async function loadLatestPlan() {
  try {
    const latest = await apiFetch<WeeklyMealPlanCollection>(`${config.public.apiBase}/api/plans`);
    if (latest.items[0]) await loadPlan(latest.items[0].id);
  }
  catch { /* no plan yet is not an error */ }
}

async function send(text = draft.value) {
  const message = text.trim();
  if (!message) return;
  draft.value = message;
  if (!(await requireAccount())) return;
  view.value = "app";
  const pending = interaction.value;
  if (pending?.allow_free_text) {
    await agent.answerInteraction({
      question_id: pending.question_id,
      option_ids: [],
      free_text: message,
      context_version: pending.context_version,
      plan_revision: pending.plan_revision,
    });
  }
  else if (session.value) await agent.reply(message);
  else await agent.create(message);
  if (!errorMessage.value) draft.value = "";
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
    plan.value = await apiFetch<WeeklyMealPlan>(`${config.public.apiBase}/api/plans/${planId}`);
    await nutrition.loadDashboard(planId);
    planState.value = "ready";
  }
  catch {
    planState.value = "error";
  }
}

function retryPlan() {
  if (lastPlanId.value) void loadPlan(lastPlanId.value);
  else void loadLatestPlan();
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

function newChat() {
  agent.reset();
  plan.value = null;
  planState.value = "empty";
  lastPlanId.value = null;
  nutrition.dashboard.value = null;
  draft.value = "";
  ask.value?.focus();
}

function openSession(item: AgentSession) {
  if (item.id === session.value?.id) return;
  newChat();
  session.value = item;
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
watch(() => [messages.value.length, isLoading.value, session.value?.pending_replan?.id, showWeek.value], async () => {
  await nextTick();
  log.value?.scrollTo({ top: log.value.scrollHeight, behavior: "smooth" });
});

useDialog(preview, () => { previewOpen.value = false; }, previewOpen);

onMounted(() => {
  window.addEventListener("keydown", onKey);
  try {
    const saved = sessionStorage.getItem(DRAFT_KEY);
    if (saved) draft.value = saved;
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
          <button type="button" class="mc-pill" @click="enter">Open my week</button>
          <NuxtLink v-if="actor" to="/profile" class="avatar" :aria-label="`Household settings for ${actor.user.display_name}`">{{ initials }}</NuxtLink>
        </header>
        <div class="hero-block">
          <h1 class="hero mc-serif">Plan the week. Shop it once.<br>Eat <em>well.</em></h1>
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
          <p class="trust"><span>Allergies and dislikes respected</span><span>Prices from FairPrice</span><span>Nutrition counted as you cook</span></p>
        </div>
        <button type="button" class="film-toggle mc-pill" :aria-label="filmPlaying ? 'Pause background video' : 'Play background video'" @click="toggleFilm">
          <svg v-if="filmPlaying" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6v12M15 6v12" /></svg>
          <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>
        </button>
      </section>
    </Transition>

    <div v-if="view === 'app'" class="app" :class="{ 'no-panel': !panelOpen }">
      <aside class="rail" aria-label="Navigation">
        <button type="button" class="brand" aria-label="Back to home" @click="view = 'landing'">
          <svg aria-hidden="true"><use href="#mc-logo" /></svg><span class="mc-serif">MealCraft</span>
        </button>
        <button type="button" class="new" @click="newChat">
          <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>New plan<kbd>Ctrl K</kbd>
        </button>
        <nav class="nav-list" aria-label="Sections">
          <button type="button" class="nav" aria-current="page" @click="ask?.focus()">
            <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4Z" /></svg>Assistant
          </button>
          <button type="button" class="nav" @click="openTab('dinners')">
            <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></svg>This week<span v-if="days.length" class="count">{{ days.length }}</span>
          </button>
          <button type="button" class="nav" @click="openTab('groceries')">
            <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l2 11h11l2-8H6.5" /><circle cx="9" cy="19" r="1.3" /><circle cx="17" cy="19" r="1.3" /></svg>Groceries<span v-if="groceryCount" class="count">{{ groceryCount }}</span>
          </button>
          <button type="button" class="nav" @click="openTab('nutrition')">
            <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 20V10M12 20V4M19 20v-7" /></svg>Nutrition
          </button>
          <NuxtLink to="/profile" class="nav">
            <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11 12 4l8 7v9H4Z" /><path d="M10 20v-5h4v5" /></svg>Household
          </NuxtLink>
        </nav>
        <template v-if="recent.length">
          <div class="rail-label">Recent</div>
          <div class="recent">
            <button v-for="item in recent" :key="item.id" type="button" :class="{ on: item.id === session?.id }" :title="sessionTitle(item)" @click="openSession(item)">
              {{ sessionTitle(item) }}
            </button>
          </div>
        </template>
        <div class="home-card">
          <div class="who">
            <span class="avatar">{{ initials }}</span>
            <div><b>{{ home.name }}</b><small>{{ home.line }}</small></div>
          </div>
          <div v-if="home.chips.length" class="chips">
            <span v-for="chip in home.chips" :key="chip.label" class="mc-chip" :class="{ alert: chip.alert }">{{ chip.label }}</span>
          </div>
          <div class="home-links">
            <NuxtLink to="/profile">Edit household</NuxtLink>
            <button type="button" @click="logout">Sign out</button>
          </div>
        </div>
      </aside>

      <main class="chat">
        <header class="chat-head">
          <h1 class="mc-serif">{{ title }}</h1>
          <span v-if="plan" class="date">Week of {{ formatPlanDate(plan.start_date, { day: "numeric", month: "short" }) }}</span>
          <span class="spacer" />
          <button type="button" class="ghost" :aria-pressed="panelOpen" @click="panelOpen = !panelOpen">
            <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M15 4v16" /></svg>{{ panelOpen ? "Hide plan" : "Show plan" }}
          </button>
        </header>

        <section ref="log" class="thread" aria-label="Conversation" aria-live="polite">
          <div class="col">
            <div v-if="!messages.length && !isLoading" class="bot mc-rise">
              <div class="bot-name"><svg aria-hidden="true"><use href="#mc-logo" /></svg>MealCraft</div>
              <p>Tell me who's eating, what you can spend and anything to avoid. I'll plan seven dinners and one shopping list.</p>
              <div class="options">
                <button v-for="starter in starters" :key="starter" type="button" class="mc-pill" @click="send(starter)">{{ starter }}</button>
              </div>
            </div>

            <template v-for="message in messages" :key="message.id">
              <div v-if="message.role === 'user'" class="me mc-rise">{{ message.content }}</div>
              <div v-else class="bot mc-rise">
                <div class="bot-name"><svg aria-hidden="true"><use href="#mc-logo" /></svg>MealCraft</div>
                <p>{{ message.content }}</p>
              </div>
            </template>

            <div v-if="interaction?.options.length" class="options mc-rise">
              <button v-for="option in interaction.options" :key="option.id" type="button" class="mc-pill" :disabled="isLoading" @click="choose(option.id)">
                {{ option.label }}
              </button>
            </div>

            <div v-if="session?.can_confirm && session.status !== 'planned'" class="card mc-rise">
              <div v-if="heard.length" class="heard">
                <span v-for="item in heard" :key="item.text + item.value" class="mc-chip" :class="{ alert: item.alert }">{{ item.text }} <b>{{ item.value }}</b></span>
              </div>
              <p>Ready to plan your week with these details.</p>
              <button type="button" class="mc-primary" :disabled="isLoading" @click="agent.confirm()">
                {{ isLoading ? "Planning seven dinners…" : "Plan my week" }}
              </button>
            </div>

            <HomeWeekCard
              v-if="showWeek && estimate"
              class="mc-rise"
              :days="days"
              :estimate="estimate"
              :range-label="rangeLabel"
              @open="openTab"
              @open-recipe="recipeSlug = $event"
            />

            <div v-if="session?.pending_replan" class="swap-card mc-rise">
              <div class="plates">
                <span class="plate" :style="plateStyle(session.pending_replan.before_entry.recipe_slug)" />
                <svg class="mc-icon arrow" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
                <span class="plate" :style="plateStyle(session.pending_replan.after_entry.recipe_slug)" />
              </div>
              <div>
                <s>{{ session.pending_replan.before_entry.recipe_title }}</s>
                <div class="to mc-serif">{{ session.pending_replan.after_entry.recipe_title }}</div>
                <small>
                  {{ session.pending_replan.nutrition_delta.calories_kcal >= 0 ? "+" : "" }}{{ Math.round(session.pending_replan.nutrition_delta.calories_kcal) }} kcal ·
                  groceries {{ session.pending_replan.purchase_total_delta_sgd >= 0 ? "+" : "−" }}S${{ Math.abs(session.pending_replan.purchase_total_delta_sgd).toFixed(2) }} ·
                  the other dinners stay the same
                </small>
              </div>
              <div class="acts">
                <button type="button" class="mc-primary" :disabled="isLoading" @click="agent.confirmReplan()">Confirm change</button>
                <button type="button" class="mc-pill" :disabled="isLoading" @click="agent.discardReplan()">Keep as is</button>
              </div>
            </div>

            <div v-if="isLoading" class="typing" aria-label="MealCraft is thinking"><span /><span /><span /></div>
            <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
          </div>
        </section>

        <div class="composer-wrap">
          <form class="composer" @submit.prevent="send()">
            <span v-if="contextLabel" class="context">
              <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11 12 4l8 7v9H4Z" /><path d="M10 20v-5h4v5" /></svg>{{ contextLabel }}
            </span>
            <label for="mc-ask" class="visually-hidden">Message MealCraft</label>
            <input
              id="mc-ask"
              ref="ask"
              v-model="draft"
              type="text"
              autocomplete="off"
              :placeholder="interaction?.prompt || (plan ? 'Swap a night, change the budget, use up what\'s in the fridge…' : 'Who\'s eating, what to spend, anything to avoid…')"
            >
            <button type="submit" class="send" aria-label="Send" :disabled="isLoading || !draft.trim()">
              <svg class="mc-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
            </button>
          </form>
          <div class="after">
            <template v-if="plan">
              <button v-for="text in followUps" :key="text" type="button" class="suggest" @click="suggest(text)">{{ text }}</button>
            </template>
            <span class="fine">Suggestions can be wrong. Check allergens on product labels.</span>
          </div>
        </div>
      </main>

      <aside v-if="panelOpen" class="panel" aria-label="This week">
        <template v-if="plan && days.length">
          <HomeTonight
            :days="days"
            :updating-entry-id="nutrition.updatingEntryId.value"
            @mark-cooked="setStatus($event, 'completed')"
            @open-recipe="recipeSlug = $event"
            @swap="swap"
          />
          <div class="tabs" role="tablist" aria-label="Plan details">
            <button id="tab-dinners" type="button" role="tab" class="tab" :aria-selected="tab === 'dinners'" aria-controls="panel-body" @click="tab = 'dinners'">Dinners</button>
            <button id="tab-groceries" type="button" role="tab" class="tab" :aria-selected="tab === 'groceries'" aria-controls="panel-body" @click="tab = 'groceries'">
              Groceries<span class="c">{{ groceryCount }}</span>
            </button>
            <button id="tab-nutrition" type="button" role="tab" class="tab" :aria-selected="tab === 'nutrition'" aria-controls="panel-body" @click="tab = 'nutrition'">Nutrition</button>
          </div>
          <div id="panel-body" class="panel-body" role="tabpanel" :aria-labelledby="`tab-${tab}`">
            <HomeDinnerList v-if="tab === 'dinners'" :days="days" :plan-id="plan.id" @open-recipe="recipeSlug = $event" />
            <HomeGroceryList v-else-if="tab === 'groceries'" :estimate="plan.grocery_estimate" />
            <HomeNutritionSummary
              v-else-if="nutrition.dashboard.value"
              :dashboard="nutrition.dashboard.value"
              :sodium-limit="constraints?.max_sodium_mg_per_meal ?? household.current.value?.current.max_sodium_mg_per_meal ?? null"
              @details="nutritionOpen = true"
            />
          </div>
          <footer v-if="estimate" class="panel-foot">
            <div class="spend">
              <b class="mc-serif mc-num">{{ formatSgd(estimate.purchase_total_sgd) }}</b>
              <span class="of">{{ groceryCount }} items</span>
              <span v-if="budgetLine(estimate)" class="left" :class="{ over: estimate.within_weekly_budget === false }">{{ budgetLine(estimate) }}</span>
            </div>
            <div v-if="budgetShare !== null" class="meter" role="img" :aria-label="`${Math.round(budgetShare)} percent of the weekly budget`">
              <i :style="{ width: `${budgetShare}%` }" :class="{ over: estimate.within_weekly_budget === false }" />
            </div>
            <div class="foot-acts">
              <button type="button" class="mc-pill" @click="previewOpen = true">Preview list</button>
              <button type="button" class="mc-primary" @click="exportPdf">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 9V4h10v5M7 17H5v-6h14v6h-2M8 14h8v6H8Z" /></svg>Export PDF
              </button>
            </div>
          </footer>
        </template>
        <HomePanelState
          v-else
          :state="planState === 'ready' ? 'empty' : planState"
          title="This week"
          empty-text="Your week shows up here once it's planned: tonight's dinner, the shopping list and nutrition."
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
      @close="nutritionOpen = false"
      @set-status="setStatus"
    />
    <HomeRecipeSheet v-if="recipeSlug" :slug="recipeSlug" @close="recipeSlug = null" />

    <div v-if="plan" v-show="previewOpen" ref="preview" class="mc-sheet-overlay" role="dialog" aria-modal="true" aria-label="Shopping list preview">
      <div class="sheet-frame">
        <HomeShoppingSheet class="mc-print-sheet" :estimate="plan.grocery_estimate" :range-label="rangeLabel" :household-size="plan.household_size" />
      </div>
      <div class="sheet-actions">
        <button type="button" class="mc-pill" @click="previewOpen = false">Back</button>
        <button type="button" class="mc-primary" @click="exportPdf">Export PDF</button>
      </div>
    </div>
    <div class="mc-grain" aria-hidden="true" />
  </div>
</template>

<style scoped>
.defs { position: absolute; }
.brand svg, .bot-name svg { fill: none; stroke: currentColor; stroke-width: 1.6; }
:deep(.leaf) { fill: var(--accent-fill); stroke: none; }

/* Film entry */
.film { position: absolute; inset: 0; transition: opacity 900ms var(--ease), transform 1200ms var(--ease), filter 900ms var(--ease); }
.film video { width: 100%; height: 100%; object-fit: cover; }
.film::after { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(14, 12, 10, 0.55) 0%, rgba(14, 12, 10, 0.1) 38%, rgba(14, 12, 10, 0.72) 78%, var(--ink) 100%); }
[data-view="app"] .film { opacity: 0; transform: scale(1.06); filter: blur(20px); }

.landing { position: absolute; inset: 0; z-index: 2; display: flex; flex-direction: column; padding: 18px clamp(16px, 3vw, 32px) 26px; }
.landing-leave-active { transition: opacity 500ms var(--ease), transform 700ms var(--ease); }
.landing-enter-active { transition: opacity 600ms var(--ease) 200ms, transform 900ms var(--ease) 200ms; }
.landing-leave-to, .landing-enter-from { opacity: 0; transform: translateY(-24px); }
.topbar { display: flex; align-items: center; gap: 10px; }
.brand { display: flex; align-items: center; gap: 10px; padding: 0; border: 0; background: none; color: var(--ivory); }
.brand svg { width: 26px; height: 26px; }
.brand > span { font-size: 21px; letter-spacing: 0.02em; }
.spacer { flex: 1; }
.link { padding: 0 10px; font-size: 13px; font-weight: 500; color: var(--t2); text-decoration: none; }
.avatar { width: 34px; height: 34px; flex: none; border-radius: 50%; display: grid; place-items: center; background: #3a2a22; color: var(--accent); font-size: 12px; font-weight: 600; text-decoration: none; }
.hero-block { margin-top: auto; display: grid; justify-items: center; gap: 26px; text-align: center; }
.hero { margin: 0; font-size: clamp(40px, 5vw, 70px); line-height: 1.04; letter-spacing: -0.01em; text-wrap: balance; }
.hero em { color: var(--accent); }
.ask { width: min(640px, 100%); display: flex; align-items: center; gap: 8px; padding: 6px 6px 6px 20px; border-radius: 999px; background: rgba(21, 18, 16, 0.82); border: 1px solid var(--line-2); box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35); }
.ask input, .composer input { flex: 1; min-width: 0; height: 42px; border: 0; background: transparent; outline: 0; color: var(--ivory); font: inherit; font-size: 15px; }
.ask input::placeholder { color: var(--t3); }
.send { width: 42px; height: 42px; flex: none; border-radius: 50%; border: 0; background: var(--ivory); color: var(--ink) !important; display: grid; place-items: center; }
.send svg { width: 17px; height: 17px; }
.starters { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.trust { margin: 8px 0 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 6px 20px; font-size: 12px; letter-spacing: 0.06em; color: var(--t3); }
.film-toggle { position: absolute; left: clamp(16px, 3vw, 32px); bottom: 22px; width: 36px; min-height: 36px; padding: 0; }
.film-toggle svg { width: 14px; height: 14px; }

/* Workspace: three fixed columns, nothing floats over anything */
.app { position: absolute; inset: 0; z-index: 1; display: grid; grid-template-columns: 236px minmax(0, 1fr) 424px; animation: mc-rise 900ms var(--ease) 200ms both; }
.app.no-panel { grid-template-columns: 236px minmax(0, 1fr); }

.rail { display: flex; flex-direction: column; gap: 18px; min-height: 0; padding: 18px 14px; border-right: 1px solid var(--line); background: var(--ink); }
.rail .brand { padding: 2px 8px 6px; }
.rail .brand > span { font-size: 19px; }
.new { display: flex; align-items: center; gap: 9px; width: 100%; height: 38px; padding: 0 12px; border-radius: 10px; border: 1px solid var(--line-2); background: var(--s2); font-weight: 500; }
.new:hover { background: var(--s3); }
.new kbd { margin-left: auto; font: 11px var(--sans); color: var(--t4); }
.nav-list { display: grid; gap: 2px; }
.nav { display: flex; align-items: center; gap: 11px; width: 100%; padding: 8px 10px; border: 0; border-radius: 9px; background: transparent; color: var(--t3) !important; font-size: 14px; text-align: left; text-decoration: none; white-space: nowrap; transition: color 150ms, background 150ms; }
.nav:hover { color: var(--ivory) !important; background: rgba(242, 237, 228, 0.04); }
.nav[aria-current="page"] { color: var(--ivory) !important; background: var(--s2); }
.nav[aria-current="page"] svg { color: var(--accent); }
.count { margin-left: auto; font-size: 11.5px; color: var(--t4); }
.rail-label { padding: 0 10px; font-size: 10.5px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--t4); }
.recent { display: grid; gap: 1px; min-height: 0; overflow: auto; margin-top: -10px; }
.recent button { width: 100%; padding: 6px 10px; border: 0; border-radius: 8px; background: transparent; color: var(--t3); font-size: 13px; text-align: left; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.recent button:hover, .recent button.on { color: var(--ivory); background: rgba(242, 237, 228, 0.04); }
.home-card { margin-top: auto; display: grid; gap: 10px; padding: 14px; border-radius: 14px; background: var(--s1); border: 1px solid var(--line); }
.who { display: flex; align-items: center; gap: 10px; min-width: 0; }
.who .avatar { width: 30px; height: 30px; }
.who > div { min-width: 0; }
.who b { display: block; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.who small { color: var(--t3); font-size: 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 5px; }
.home-links { display: flex; justify-content: space-between; font-size: 12px; }
.home-links a, .home-links button { padding: 0; border: 0; background: none; color: var(--t3); text-decoration: none; }
.home-links a:hover, .home-links button:hover { color: var(--ivory); }

.chat { display: flex; flex-direction: column; min-width: 0; min-height: 0; background: var(--ink); }
.chat-head { display: flex; align-items: center; gap: 12px; padding: 16px 28px; border-bottom: 1px solid var(--line); }
.chat-head h1 { min-width: 0; margin: 0; font-size: 17px; font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.date { flex: none; color: var(--t3); font-size: 12.5px; }
.ghost { flex: none; display: inline-flex; align-items: center; gap: 7px; padding: 6px 9px; border: 0; border-radius: 8px; background: transparent; color: var(--t3) !important; font-size: 13px; }
.ghost:hover { color: var(--ivory) !important; background: rgba(242, 237, 228, 0.05); }
.thread { flex: 1; min-height: 0; overflow: auto; padding: 32px 28px 16px; }
.col { max-width: 720px; margin: 0 auto; display: grid; gap: 22px; }
.me { justify-self: end; max-width: 76%; padding: 10px 16px; border-radius: 18px 18px 6px 18px; background: var(--s2); border: 1px solid var(--line); color: var(--t2); white-space: pre-line; }
.bot { display: grid; gap: 12px; }
.bot-name { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--t3); }
.bot-name svg { width: 18px; height: 18px; color: var(--ivory); }
.bot p { margin: 0; max-width: 62ch; line-height: 1.7; color: var(--t2); white-space: pre-line; }
.options, .heard { display: flex; flex-wrap: wrap; gap: 8px; }
.heard { gap: 6px; }
.card { justify-self: start; width: min(460px, 100%); display: grid; gap: 12px; padding: 16px 18px; border-radius: 16px; background: var(--s1); border: 1px solid var(--line); }
.card p { margin: 0; color: var(--t2); }
.card .mc-primary { min-height: 42px; }
.swap-card { display: grid; grid-template-columns: auto 1fr; gap: 16px; align-items: center; padding: 16px 18px; border-radius: 16px; background: var(--s1); border: 1px solid var(--line); }
.plates { display: flex; align-items: center; gap: 6px; }
.plates .plate:first-child { --size: 34px; opacity: 0.45; filter: grayscale(0.6); }
.plates .plate:last-child { --size: 48px; }
.arrow { color: var(--t4); }
.swap-card s { color: var(--t4); font-size: 12.5px; }
.to { font-size: 18px; line-height: 1.2; font-weight: 400; }
.swap-card small { display: block; margin-top: 3px; color: var(--t3); font-size: 12px; }
.swap-card .acts { grid-column: 1 / -1; display: flex; gap: 8px; }
.typing { display: flex; gap: 5px; padding: 8px 0; }
.typing span { width: 7px; height: 7px; border-radius: 999px; background: var(--t3); animation: mc-dot 1.2s ease-in-out infinite; }
.typing span:nth-child(2) { animation-delay: 150ms; }
.typing span:nth-child(3) { animation-delay: 300ms; }
@keyframes mc-dot { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.error { margin: 0; padding: 10px 14px; border-radius: 12px; background: var(--warn-soft); color: var(--warn); font-size: 13px; }

.composer-wrap { padding: 12px 28px 16px; }
.composer { max-width: 720px; margin: 0 auto; display: flex; align-items: center; gap: 8px; padding: 6px 6px 6px 8px; border-radius: 999px; background: var(--s2); border: 1px solid var(--line-2); }
.composer input { height: 40px; padding: 0 8px; font-size: 14.5px; }
.composer input::placeholder { color: var(--t4); }
.composer .send { width: 38px; height: 38px; }
.context { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: 999px; background: var(--s3); color: var(--t2); font-size: 12.5px; white-space: nowrap; }
.after { max-width: 720px; margin: 10px auto 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.fine { margin-left: auto; font-size: 11.5px; color: var(--t4); }
.suggest { padding: 4px 11px; border: 1px solid var(--line); border-radius: 999px; background: transparent; color: var(--t3) !important; font-size: 12px; }
.suggest:hover { color: var(--ivory) !important; border-color: var(--line-2); }

.panel { display: flex; flex-direction: column; min-height: 0; background: var(--s1); border-left: 1px solid var(--line); }
.tabs { flex: none; display: flex; gap: 4px; padding: 10px 14px 0; border-bottom: 1px solid var(--line); }
.tab { position: relative; padding: 8px 10px 11px; border: 0; background: transparent; color: var(--t3) !important; font-weight: 500; }
.tab:hover, .tab[aria-selected="true"] { color: var(--ivory) !important; }
.tab[aria-selected="true"]::after { content: ""; position: absolute; left: 10px; right: 10px; bottom: -1px; height: 2px; border-radius: 2px; background: var(--accent); }
.tab .c { margin-left: 4px; color: var(--t4); font-weight: 400; }
.panel-body { flex: 1; min-height: 0; overflow: auto; }
.panel-foot { flex: none; display: grid; gap: 12px; padding: 16px 22px 18px; border-top: 1px solid var(--line); }
.spend { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 8px; }
.spend b { font-size: 26px; line-height: 1; }
.spend .of { color: var(--t3); font-size: 12.5px; }
.spend .left { margin-left: auto; color: var(--sage); font-size: 12.5px; }
.spend .left.over { color: var(--warn); }
.meter { height: 4px; border-radius: 99px; background: var(--s3); overflow: hidden; }
.meter i { display: block; height: 100%; border-radius: 99px; background: linear-gradient(90deg, var(--sage), #c6cfae); transition: width 600ms var(--ease); }
.meter i.over { background: var(--warn); }
.foot-acts { display: flex; gap: 8px; }
.foot-acts button { flex: 1; min-height: 40px; }

/* Shopping list preview */
.mc-sheet-overlay { position: fixed; inset: 0; z-index: 20; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; padding: 16px; background: rgba(14, 12, 10, 0.72); animation: mc-rise 420ms var(--ease) both; }
.sheet-frame { width: min(680px, 100%); max-height: calc(100vh - 160px); overflow-y: auto; border-radius: 6px; box-shadow: 0 40px 90px rgba(0, 0, 0, 0.6); }
.sheet-actions { display: flex; gap: 10px; }
.sheet-actions button { min-width: 140px; min-height: 44px; font-size: 14px; }

/* Narrower screens: the plan drops below the chat and the page scrolls. */
@media (max-width: 1200px) {
  .mc-surface { overflow: auto; }
  .app, .app.no-panel { grid-template-columns: 220px minmax(0, 1fr); min-height: 100%; bottom: auto; }
  .panel { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--line); }
  .panel-body { overflow: visible; }
  .chat { height: 100vh; position: sticky; top: 0; }
}
@media (max-width: 760px) {
  .app, .app.no-panel { grid-template-columns: minmax(0, 1fr); }
  .rail { border-right: 0; border-bottom: 1px solid var(--line); }
  .recent, .rail-label, .home-card, .new kbd { display: none; }
  .nav-list { grid-auto-flow: column; overflow-x: auto; }
  .chat { position: static; height: 80vh; }
  .chat-head, .thread, .composer-wrap { padding-inline: 16px; }
  .context { display: none; }
  .landing { overflow: auto; }
}
</style>
