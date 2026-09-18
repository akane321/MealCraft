<script setup lang="ts">
import type { AgentMessage } from "~/types/agent";
import type { MealPlanEntryStatus, WeeklyMealPlan, WeeklyMealPlanCollection } from "~/types/meal-plan";

useHead({
  title: "MealCraft",
  link: [
    { rel: "preconnect", href: "https://fonts.googleapis.com" },
    { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,300&family=Figtree:wght@400;500;600&display=swap" },
  ],
});

const DRAFT_KEY = "mealcraft-draft";
// Lens displacement map, stretched over each glass surface: red/green ramps bend
// the backdrop near the edges, the blurred grey (neutral) centre leaves it clear.
const lensMap = `data:image/svg+xml;utf8,${encodeURIComponent(
  "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100' preserveAspectRatio='none'><defs>"
  + "<linearGradient id='r' x2='1'><stop offset='0' stop-color='#f00'/><stop offset='1' stop-color='#000'/></linearGradient>"
  + "<linearGradient id='g' x2='0' y2='1'><stop offset='0' stop-color='#0f0'/><stop offset='1' stop-color='#000'/></linearGradient>"
  + "<filter id='b'><feGaussianBlur stdDeviation='6'/></filter></defs>"
  + "<rect width='100' height='100' fill='url(#r)'/><rect width='100' height='100' fill='url(#g)' style='mix-blend-mode:screen'/>"
  + "<rect x='14' y='14' width='72' height='72' rx='14' fill='#808080' filter='url(#b)'/></svg>",
)}`;
const starters = ["Dinners for two this week, around S$90", "A high-protein week", "Vegetarian, under S$60"];

const config = useRuntimeConfig();
const apiFetch = useApiFetch();
const { actor } = useAuth();
const agent = useMealCraftAgent();
const { session, isLoading, errorMessage, generatedPlan } = agent;
const nutrition = useNutritionDashboard();

const view = ref<"landing" | "app">("landing");
const draft = ref("");
const plan = ref<WeeklyMealPlan | null>(null);
const hover = reactive({ left: false, right: false });
const pinned = reactive({ left: false, right: false });
const open = computed(() => ({ left: hover.left || pinned.left, right: hover.right || pinned.right }));
const previewOpen = ref(false);
const nutritionOpen = ref(false);
const recipeSlug = ref<string | null>(null);
const log = ref<HTMLElement | null>(null);
const film = ref<HTMLVideoElement | null>(null);
const filmPlaying = ref(true);

const messages = computed<AgentMessage[]>(() => session.value?.messages.filter(m => m.role !== "system") ?? []);
const interaction = computed(() => session.value?.pending_interaction ?? null);
const contextLabel = computed(() => {
  const c = session.value?.constraints;
  if (!c?.household_size) return null;
  const people = `${c.household_size} ${c.household_size === 1 ? "person" : "people"}`;
  return c.weekly_budget_sgd ? `${people} · S$${c.weekly_budget_sgd}` : people;
});
const rangeLabel = computed(() => {
  if (!plan.value) return "";
  const fmt = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString("en-SG", { day: "numeric", month: "short" });
  return `${fmt(plan.value.start_date)} – ${fmt(plan.value.end_date)}`;
});
const days = computed(() => nutrition.dashboard.value?.days ?? []);
const initials = computed(() => (actor.value?.user.display_name ?? "?")
  .split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]!.toUpperCase()).join(""));
const layoutVars = computed(() => ({
  "--pad-l": open.value.left ? "424px" : "0px",
  "--pad-r": open.value.right ? "424px" : "0px",
}));

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
  try {
    plan.value = await apiFetch<WeeklyMealPlan>(`${config.public.apiBase}/api/plans/${planId}`);
    await nutrition.loadDashboard(planId);
  }
  catch {
    errorMessage.value = "Your week couldn't be loaded. Try again in a moment.";
  }
}

async function markCooked(entryId: number) {
  await nutrition.updateStatus(entryId, "completed");
}

async function setStatus(entryId: number, status: MealPlanEntryStatus) {
  await nutrition.updateStatus(entryId, status);
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
  nutrition.dashboard.value = null;
}

// The film only plays on the entry; inside the app the glows take over.
watch(view, (value) => {
  if (value === "app") film.value?.pause();
  else void film.value?.play();
});
watch(generatedPlan, (value) => {
  if (value) void loadPlan(value.id);
});
watch(() => session.value?.plan_id, (planId) => {
  if (planId && planId !== plan.value?.id) void loadPlan(planId);
});
watch(() => [messages.value.length, isLoading.value, session.value?.pending_replan?.id], async () => {
  await nextTick();
  log.value?.scrollTo({ top: log.value.scrollHeight, behavior: "smooth" });
});

// Only Chromium bends the backdrop through an SVG filter; elsewhere the glass stays frosted.
const refracts = () => (navigator as Navigator & { userAgentData?: { brands: { brand: string }[] } })
  .userAgentData?.brands.some(item => item.brand === "Chromium") ?? false;

onUnmounted(() => document.documentElement.classList.remove("mc-refract"));

onMounted(() => {
  document.documentElement.classList.toggle("mc-refract", refracts());
  try {
    const saved = sessionStorage.getItem(DRAFT_KEY);
    if (saved) draft.value = saved;
    sessionStorage.removeItem(DRAFT_KEY);
  }
  catch { /* ignore */ }
});
</script>

<template>
  <div class="mc-surface" :class="{ 'is-app': view === 'app' }" :style="layoutVars">
    <div class="film" aria-hidden="true">
      <video ref="film" autoplay muted loop playsinline preload="auto" poster="/media/hero-poster.jpg" @play="filmPlaying = true" @pause="filmPlaying = false">
        <source src="/media/hero.mp4" type="video/mp4">
      </video>
    </div>
    <!-- Shared lens for every glass surface; Chromium applies it to the backdrop (see surface.css). -->
    <svg class="lens-defs" aria-hidden="true" width="0" height="0">
      <filter id="mc-liquid" primitiveUnits="objectBoundingBox" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">
        <feImage :href="lensMap" x="0" y="0" width="1" height="1" preserveAspectRatio="none" result="map" />
        <feDisplacementMap in="SourceGraphic" in2="map" scale="0.08" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </svg>
    <div class="glow" aria-hidden="true"><span class="blob a" /><span class="blob b" /><span class="blob c" /></div>
    <div class="scrim" aria-hidden="true" />
    <button v-if="view === 'landing'" type="button" class="film-toggle mc-pill" :aria-label="filmPlaying ? 'Pause background video' : 'Play background video'" @click="toggleFilm">
      <svg v-if="filmPlaying" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6v12M15 6v12" /></svg>
      <svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>
    </button>

    <header class="top">
      <button type="button" class="brand" aria-label="MealCraft home" @click="view = 'landing'">
        <svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="18" r="10.5" /><path class="leaf" d="M16 7.5c1.4-3.2 4.6-4.2 7-3.3-.9 2.8-3.7 4.4-7 3.3z" /></svg>
        <span class="mc-serif">MealCraft</span>
      </button>
      <div class="top-actions">
        <template v-if="view === 'landing'">
          <NuxtLink v-if="!actor" to="/login?next=/" class="link">Sign in</NuxtLink>
          <button type="button" class="mc-pill" @click="enter">Open my week</button>
        </template>
        <template v-else>
          <button type="button" class="mc-pill" @click="newChat">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>New chat
          </button>
          <NuxtLink to="/profile" class="mc-pill avatar" :aria-label="`Household settings for ${actor?.user.display_name ?? 'you'}`">
            {{ initials }}
          </NuxtLink>
        </template>
      </div>
    </header>

    <h1 class="hero mc-serif">Plan the week. Shop it once.<br>Eat <em>well.</em></h1>

    <div class="starters">
      <button v-for="starter in starters" :key="starter" type="button" class="mc-pill" @click="send(starter)">{{ starter }}</button>
    </div>
    <p class="trust">
      <span>Allergies and dislikes respected</span><span>·</span><span>Prices from FairPrice</span><span>·</span><span>Nutrition counted as you cook</span>
    </p>

    <section ref="log" class="chat" aria-label="Conversation" aria-live="polite">
      <div class="chat-inner">
        <p v-if="!messages.length && !isLoading" class="empty mc-rise">
          Tell me who's eating, what you can spend and anything to avoid.
        </p>
        <div v-for="message in messages" :key="message.id" class="msg mc-rise" :class="[message.role, { 'mc-frost': message.role === 'user' }]">{{ message.content }}</div>

        <div v-if="interaction?.options.length" class="options mc-rise">
          <button v-for="option in interaction.options" :key="option.id" type="button" class="mc-pill" :disabled="isLoading" @click="choose(option.id)">
            {{ option.label }}
          </button>
        </div>

        <div v-if="session?.can_confirm && session.status !== 'planned'" class="mc-frost card mc-rise">
          <p>Ready to plan your week with these details.</p>
          <button type="button" class="mc-primary" :disabled="isLoading" @click="agent.confirm()">
            {{ isLoading ? "Planning seven dinners…" : "Plan my week" }}
          </button>
        </div>

        <div v-if="session?.pending_replan" class="mc-frost card mc-rise">
          <span class="mc-eyebrow">Suggested change</span>
          <p class="swap"><s>{{ session.pending_replan.before_entry.recipe_title }}</s><strong class="mc-serif">{{ session.pending_replan.after_entry.recipe_title }}</strong></p>
          <small>
            {{ session.pending_replan.nutrition_delta.calories_kcal >= 0 ? "+" : "" }}{{ Math.round(session.pending_replan.nutrition_delta.calories_kcal) }} kcal ·
            groceries {{ session.pending_replan.purchase_total_delta_sgd >= 0 ? "+" : "−" }}S${{ Math.abs(session.pending_replan.purchase_total_delta_sgd).toFixed(2) }} ·
            other dinners unchanged
          </small>
          <div class="card-actions">
            <button type="button" class="mc-primary" :disabled="isLoading" @click="agent.confirmReplan()">Confirm change</button>
            <button type="button" class="mc-pill" :disabled="isLoading" @click="agent.discardReplan()">Keep as is</button>
          </div>
        </div>

        <div v-if="plan && session?.status === 'planned' && !session.pending_replan" class="jump mc-rise">
          <button type="button" class="mc-pill" @click="pinned.left = true">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>See the week
          </button>
          <button type="button" class="mc-pill" @click="pinned.right = true">
            Groceries &amp; nutrition<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
          </button>
        </div>

        <div v-if="isLoading" class="typing" aria-label="MealCraft is thinking"><span /><span /><span /></div>
        <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
      </div>
    </section>

    <form class="composer mc-pill" @submit.prevent="send()">
      <span v-if="contextLabel" class="context mc-pill">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11l8-6 8 6v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /><path d="M10 20v-5h4v5" /></svg>
        {{ contextLabel }}
      </span>
      <label for="mc-ask" class="visually-hidden">Message MealCraft</label>
      <input
        id="mc-ask"
        v-model="draft"
        type="text"
        autocomplete="off"
        :placeholder="view === 'app' ? (interaction?.prompt || 'Ask or change anything…') : 'What should this week look like…  e.g. dinners for two, no seafood'"
      >
      <button type="submit" class="send" aria-label="Send" :disabled="isLoading || !draft.trim()">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
      </button>
    </form>
    <p class="disclaimer">Suggestions can be wrong. Check allergens on product labels.</p>

    <template v-if="view === 'app'">
      <div
        class="edge left"
        :class="{ open: open.left }"
        @mouseenter="hover.left = true"
        @mouseleave="hover.left = false"
        @focusin="hover.left = true"
        @focusout="hover.left = false"
      >
        <button type="button" class="handle mc-pill" aria-label="Show this week's dinners" @click="pinned.left = !pinned.left">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M9 3v4M15 3v4" /></svg>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6" /></svg>
        </button>
        <aside class="drawer mc-ribbed" aria-label="This week">
          <HomeWeekPanel
            v-if="days.length"
            :days="days"
            :range-label="rangeLabel"
            :cooked-count="nutrition.dashboard.value?.status_counts.completed ?? 0"
            :updating-entry-id="nutrition.updatingEntryId.value"
            @mark-cooked="markCooked"
            @open-recipe="recipeSlug = $event"
          >
            <template #actions>
              <button type="button" class="mc-pill pin" :aria-label="pinned.left ? 'Close this panel' : 'Keep this panel open'" @click="pinned.left = !pinned.left">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="pinned.left ? 'M6 6l12 12M18 6L6 18' : 'M9 6l6 6-6 6'" /></svg>
              </button>
            </template>
          </HomeWeekPanel>
          <p v-else class="panel-empty">Your week shows up here once it's planned.</p>
        </aside>
      </div>

      <div
        class="edge right"
        :class="{ open: open.right }"
        @mouseenter="hover.right = true"
        @mouseleave="hover.right = false"
        @focusin="hover.right = true"
        @focusout="hover.right = false"
      >
        <button type="button" class="handle mc-pill" aria-label="Show nutrition and groceries" @click="pinned.right = !pinned.right">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6" /></svg>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 20V11M12 20V5M19 20v-6" /></svg>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h2l2 11h10l2-8H7" /></svg>
        </button>
        <aside class="drawer mc-ribbed" aria-label="Nutrition and groceries">
          <HomeKitchenPanel
            v-if="plan"
            :days="days"
            :eaten="nutrition.dashboard.value?.completed_nutrition_per_person ?? null"
            :estimate="plan.grocery_estimate"
            @preview="previewOpen = true"
            @details="nutritionOpen = true"
            @export="exportPdf"
          >
            <template #actions>
              <button type="button" class="mc-pill pin" :aria-label="pinned.right ? 'Close this panel' : 'Keep this panel open'" @click="pinned.right = !pinned.right">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="pinned.right ? 'M6 6l12 12M18 6L6 18' : 'M15 6l-6 6 6 6'" /></svg>
              </button>
            </template>
          </HomeKitchenPanel>
          <p v-else class="panel-empty">Nutrition and your shopping list show up here once the week is planned.</p>
        </aside>
      </div>
    </template>

    <HomeNutritionSheet
      v-if="nutritionOpen && nutrition.dashboard.value"
      :dashboard="nutrition.dashboard.value"
      :updating-entry-id="nutrition.updatingEntryId.value"
      @close="nutritionOpen = false"
      @set-status="setStatus"
    />
    <HomeRecipeSheet v-if="recipeSlug" :slug="recipeSlug" @close="recipeSlug = null" />

    <div v-if="plan" v-show="previewOpen" class="mc-sheet-overlay" role="dialog" aria-modal="true" aria-label="Shopping list preview" @keydown.esc="previewOpen = false">
      <div class="sheet-frame">
        <HomeShoppingSheet class="mc-print-sheet" :estimate="plan.grocery_estimate" :range-label="rangeLabel" :household-size="plan.household_size" />
      </div>
      <div class="sheet-actions">
        <button type="button" class="mc-pill" @click="previewOpen = false">Back</button>
        <button type="button" class="mc-primary" @click="exportPdf">Export PDF</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mc-surface {
  --chat-w: min(720px, calc(100vw - var(--pad-l) - var(--pad-r) - 48px));
  --chat-x: calc(var(--pad-l) + (100vw - var(--pad-l) - var(--pad-r) - var(--chat-w)) / 2);
}

svg { fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }

/* Film and backdrop */
.film {
  position: absolute;
  inset: -40px;
  background:
    radial-gradient(circle at 20% 20%, rgba(194, 85, 58, 0.4), transparent 55%),
    radial-gradient(circle at 75% 60%, rgba(222, 170, 98, 0.18), transparent 55%),
    var(--mc-base);
  transition: opacity 1000ms var(--mc-ease), transform 1400ms var(--mc-ease), filter 1000ms var(--mc-ease);
}
.film video { width: 100%; height: 100%; object-fit: cover; }
.film-toggle { position: absolute; left: 24px; bottom: 22px; z-index: 5; width: 36px; height: 36px; padding: 0; display: flex; align-items: center; justify-content: center; color: var(--mc-text-2); }
.film-toggle svg { width: 14px; height: 14px; }
.is-app .film { opacity: 0; transform: scale(1.06); filter: blur(22px); }

/* Inside the app the film gives way to slow warm glows */
.glow { position: absolute; inset: 0; opacity: 0; transition: opacity 1200ms ease; }
.is-app .glow { opacity: 1; }
.blob { position: absolute; border-radius: 50%; }
.blob.a { left: -8%; top: -12%; width: 62vw; height: 84vh; background: radial-gradient(circle, rgba(194, 85, 58, 0.42), transparent 65%); animation: drift-a 9s ease-in-out infinite alternate; }
.blob.b { left: 36%; top: 12%; width: 52vw; height: 70vh; background: radial-gradient(circle, rgba(222, 170, 98, 0.2), transparent 65%); animation: drift-b 11s ease-in-out infinite alternate; }
.blob.c { left: 66%; top: 46%; width: 44vw; height: 62vh; background: radial-gradient(circle, rgba(122, 132, 113, 0.22), transparent 65%); animation: drift-c 7s ease-in-out infinite alternate; }
@keyframes drift-a { to { transform: translate(60px, 30px) scale(1.12); } }
@keyframes drift-b { from { transform: scale(1.1); } to { transform: translate(-80px, -20px) scale(0.95); } }
@keyframes drift-c { to { transform: translate(40px, -50px); } }
.scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(14, 12, 10, 0.2) 0%, rgba(14, 12, 10, 0.55) 55%, rgba(14, 12, 10, 0.92) 100%);
  transition: background-color 900ms ease;
}
.is-app .scrim {
  background-color: transparent;
  background-image:
    linear-gradient(rgba(242, 237, 228, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(242, 237, 228, 0.025) 1px, transparent 1px);
  background-size: 40px 40px;
}

/* Header */
.top { position: absolute; top: 0; left: 0; right: 0; z-index: 8; height: 72px; padding: 0 32px; box-sizing: border-box; display: flex; align-items: center; justify-content: space-between; }
.brand { display: flex; align-items: center; gap: 10px; height: 44px; padding: 0; border: 0; background: none; color: var(--mc-ivory); }
.brand svg { width: 26px; height: 26px; stroke-width: 1.6; }
.brand .leaf { fill: var(--mc-accent-fill); stroke: none; }
.brand span { font-size: 21px; letter-spacing: 0.02em; }
.top-actions { display: flex; align-items: center; gap: 8px; }
.top-actions .mc-pill { min-height: 44px; padding: 0 18px; font-size: 14px; font-weight: 500; display: flex; align-items: center; gap: 8px; text-decoration: none; }
.top-actions svg { width: 15px; height: 15px; }
.link { padding: 0 14px; font-size: 14px; font-weight: 500; color: var(--mc-text-2); text-decoration: none; }
.avatar { width: 44px; padding: 0 !important; justify-content: center; font-size: 12px !important; font-weight: 600; color: #e8a48c !important; }

/* Landing copy: dissolves on send */
.hero, .starters, .trust {
  transition: opacity 520ms ease, transform 760ms var(--mc-ease), filter 520ms ease, visibility 0s linear 0s;
}
.is-app .hero, .is-app .starters, .is-app .trust {
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 520ms ease, transform 760ms var(--mc-ease), filter 520ms ease, visibility 0s linear 760ms;
}
.hero { position: absolute; left: 0; right: 0; bottom: 260px; margin: 0; text-align: center; font-weight: 300; font-size: clamp(48px, 4.6vw, 66px); line-height: 1.06; }
.hero em { color: var(--mc-accent); }
.is-app .hero { transform: translateY(-60px) scale(1.04); filter: blur(18px); }
.starters { position: absolute; left: 0; right: 0; bottom: 104px; display: flex; justify-content: center; gap: 10px; }
.starters .mc-pill { --lg-tint: rgba(14, 12, 10, 0.3); min-height: 40px; padding: 0 16px; font-size: 13px; font-weight: 500; color: var(--mc-text-2); }
.is-app .starters { transform: translateY(20px); filter: blur(8px); }
.trust { position: absolute; left: 0; right: 0; bottom: 28px; margin: 0; display: flex; justify-content: center; gap: 20px; font-size: 12px; letter-spacing: 0.06em; color: var(--mc-text-3); }
.is-app .trust { transform: translateY(12px); }

/* Conversation */
.chat {
  position: absolute;
  top: 80px;
  bottom: 128px;
  left: var(--chat-x);
  width: var(--chat-w);
  overflow-y: auto;
  scrollbar-width: none;
  mask-image: linear-gradient(180deg, transparent 0, #000 48px);
  opacity: 0;
  visibility: hidden;
  transition: left 700ms var(--mc-ease), width 700ms var(--mc-ease), opacity 400ms ease, visibility 0s linear 400ms;
}
.is-app .chat { opacity: 1; visibility: visible; transition: left 700ms var(--mc-ease), width 700ms var(--mc-ease), opacity 600ms ease 200ms; }
.chat-inner { min-height: 100%; box-sizing: border-box; padding: 48px 8px 12px; display: flex; flex-direction: column; justify-content: flex-end; gap: 16px; }
.empty { margin: 0 auto; font-size: 15px; color: var(--mc-text-2); }
.msg { max-width: 82%; font-size: 15px; line-height: 1.6; white-space: pre-line; }
.msg.user { --lg-tint: rgba(242, 237, 228, 0.1); --lg-blur: 6px; align-self: flex-end; padding: 12px 16px; border-radius: 20px 20px 6px 20px; }
.msg.assistant { align-self: flex-start; }
.options, .jump { display: flex; flex-wrap: wrap; gap: 8px; }
.options .mc-pill, .jump .mc-pill { min-height: 38px; padding: 0 14px; font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.jump svg { width: 14px; height: 14px; }
.card { align-self: flex-start; width: min(440px, 100%); padding: 14px 16px; border-radius: 20px; display: flex; flex-direction: column; gap: 8px; }
.card p { margin: 0; font-size: 14px; }
.card > .mc-primary { min-height: 44px; font-size: 13px; }
.card small { font-size: 12px; color: var(--mc-text-3); }
.swap { display: flex; flex-direction: column; }
.swap s { font-size: 13px; color: var(--mc-text-3); }
.swap strong { font-size: 21px; }
.card-actions { display: flex; gap: 8px; }
.card-actions button { flex: 1; min-height: 44px; font-size: 13px; }
.typing { align-self: flex-start; display: flex; gap: 5px; padding: 8px 0; }
.typing span { width: 7px; height: 7px; border-radius: 999px; background: var(--mc-text-3); animation: mc-dot 1.2s ease-in-out infinite; }
.typing span:nth-child(2) { animation-delay: 150ms; }
.typing span:nth-child(3) { animation-delay: 300ms; }
@keyframes mc-dot { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
.error { margin: 0; font-size: 13px; color: var(--mc-accent); }

/* Composer: glides from the middle of the film to the foot of the chat */
.composer {
  --lg-blur: 4px;
  --lg-tint: rgba(18, 14, 11, 0.42);
  position: absolute;
  z-index: 6;
  left: calc(50vw - 390px);
  bottom: 156px;
  width: 780px;
  height: 68px;
  padding: 0 7px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.5);
  transition: left 700ms var(--mc-ease), width 700ms var(--mc-ease), bottom 950ms var(--mc-ease), height 950ms var(--mc-ease);
}
.is-app .composer {
  --lg-blur: 3px;
  --lg-tint: rgba(242, 237, 228, 0.05);
  left: var(--chat-x);
  width: var(--chat-w);
  bottom: 36px;
  height: 64px;
}
.context { height: 46px; flex-shrink: 0; padding: 0 14px; box-shadow: none; display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; color: var(--mc-text-2); }
.context svg { width: 16px; height: 16px; stroke-width: 1.4; }
.composer input { flex-grow: 1; min-width: 0; height: 44px; padding: 0 10px; border: 0; background: transparent; color: var(--mc-ivory); font: inherit; font-size: 15px; }
.composer input::placeholder { color: #8c8476; }
.composer input:focus { outline: none; }
.send { width: 46px; height: 46px; flex-shrink: 0; border: 0; border-radius: 999px; background: var(--mc-ivory); color: var(--mc-base); display: flex; align-items: center; justify-content: center; }
.send svg { width: 17px; height: 17px; stroke-width: 1.8; }
.disclaimer { position: absolute; bottom: 12px; left: var(--chat-x); width: var(--chat-w); margin: 0; text-align: center; font-size: 11px; color: var(--mc-text-3); opacity: 0; transition: opacity 600ms ease, left 700ms var(--mc-ease), width 700ms var(--mc-ease); }
.is-app .disclaimer { opacity: 1; transition-delay: 900ms, 0ms, 0ms; }
.lens-defs { position: absolute; width: 0; height: 0; }
.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* Edge panels: hover the edge (or tab into it) to slide one out; the chat moves aside */
.edge { position: absolute; top: 72px; bottom: 0; z-index: 7; width: 40px; }
.edge.left { left: 0; }
.edge.right { right: 0; }
.handle { position: absolute; top: calc(50% - 90px); width: 30px; height: 132px; padding: 0; border-radius: 16px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--mc-text-2); transition: opacity 240ms ease; animation: mc-rise 560ms var(--mc-ease) 1200ms both; }
.handle svg { width: 16px; height: 16px; }
.left .handle { left: 6px; }
.right .handle { right: 6px; }
.edge.open .handle { opacity: 0; pointer-events: none; }
.drawer { position: absolute; top: 12px; bottom: 24px; width: 392px; padding: 18px; opacity: 0; visibility: hidden; pointer-events: none; transition: transform 560ms var(--mc-ease), opacity 360ms ease, visibility 0s linear 560ms; }
.left .drawer { left: 16px; transform: translateX(-430px) scale(0.98); }
.right .drawer { right: 16px; transform: translateX(430px) scale(0.98); }
.edge.open .drawer { transform: none; opacity: 1; visibility: visible; pointer-events: auto; transition: transform 560ms var(--mc-ease), opacity 360ms ease; }
.pin { width: 36px; height: 36px; padding: 0; display: flex; align-items: center; justify-content: center; }
.pin svg { width: 15px; height: 15px; }
.panel-empty { margin: 40px 8px; font-size: 14px; line-height: 1.6; color: var(--mc-text-2); }

/* Shopping list preview */
.mc-sheet-overlay { position: fixed; inset: 0; z-index: 20; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; background: rgba(14, 12, 10, 0.6); backdrop-filter: blur(12px); animation: mc-rise 420ms var(--mc-ease) both; }
.sheet-frame { width: 680px; max-height: calc(100vh - 160px); overflow-y: auto; border-radius: 6px; box-shadow: 0 40px 90px rgba(0, 0, 0, 0.6); }
.sheet-actions { display: flex; gap: 10px; }
.sheet-actions button { min-width: 140px; min-height: 44px; font-size: 14px; }
</style>
