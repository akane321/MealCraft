<script setup lang="ts">
import { formatPlanDate } from "~/lib/meal-plan-format";
import type { ServerClock } from "~/plugins/server-today";

const { actor, load, logout } = useAuth();
const route = useRoute();
// A simulated day (SIMULATED_TODAY, debugging and demos) is always visible, so it is never mistaken for today.
const clock = useState<ServerClock | null>("server-clock");
const simulatedLabel = computed(() => {
  const value = clock.value?.simulated;
  if (!value || !clock.value) return null;
  const day = formatPlanDate(clock.value.today, { weekday: "short", day: "numeric", month: "short" });
  return value.includes("T") ? `${day}, ${value.slice(11, 16)}` : day;
});

useHead({
  link: [
    { rel: "preconnect", href: "https://fonts.googleapis.com" },
    { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=Nunito:wght@500;600;700;800&display=swap" },
    // The product and the console use Inter. No bold face: every heavier weight there renders at 600.
    { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" },
  ],
});

// Which product page shows in the sidebar shell (null: the page draws its own frame).
const shellPage = computed(() => {
  const path = route.path;
  if (path === "/" || path.startsWith("/ops") || path.startsWith("/login")) return null;
  const page = path.split("/")[1];
  return page === "browse" || page === "history" || page === "profile" || page === "system" ? page : "other";
});
// The panel's top bar: the page's icon and name (icon names literal so the icon bundle finds them).
const BARS = {
  browse: { icon: "i-lucide-book-open", label: "Recipes & groceries" },
  history: { icon: "i-lucide-calendar-clock", label: "Past plans" },
  profile: { icon: "i-lucide-users", label: "Household" },
  system: { icon: "i-lucide-activity", label: "Status" },
  other: { icon: "i-lucide-layout-grid", label: "MealCraft" },
} as const;

onMounted(load);
</script>

<template>
  <UApp>
    <div class="app-shell">
      <p v-if="simulatedLabel" class="simulated-clock" role="status">Simulated date: {{ simulatedLabel }} · for debugging</p>
      <!-- Product pages sit in the sidebar shell; the home surface and the console (/ops) draw their own. -->
      <div v-if="shellPage" class="mc-shell mc-page product-shell">
        <ShellSidebar :current="shellPage" />
        <div class="mc-frame product-frame">
          <div class="mc-bar"><UIcon :name="BARS[shellPage].icon" />{{ BARS[shellPage].label }}</div>
          <NuxtPage />
        </div>
      </div>
      <template v-else>
        <header v-if="route.path !== '/' && !route.path.startsWith('/ops')" class="app-header">
          <div class="page-width header-content">
            <NuxtLink class="brand-name" to="/">
              <svg viewBox="0 0 32 32" width="24" height="24" aria-hidden="true"><circle cx="16" cy="18" r="10.5" fill="none" stroke="currentColor" stroke-width="1.6" /><path d="M16 7.5c1.4-3.2 4.6-4.2 7-3.3-.9 2.8-3.7 4.4-7 3.3z" fill="#c2553a" /></svg>MealCraft
            </NuxtLink>
            <nav class="primary-nav" aria-label="Primary navigation">
              <NuxtLink to="/">Back to my plan</NuxtLink>
              <NuxtLink to="/browse">Recipes</NuxtLink>
              <NuxtLink to="/history">Past plans</NuxtLink>
              <button v-if="actor" class="nav-auth" type="button" @click="logout">
                Sign out {{ actor.user.display_name }}
              </button>
              <NuxtLink v-else to="/login">Sign in</NuxtLink>
            </nav>
          </div>
        </header>
        <NuxtPage />
      </template>
    </div>
  </UApp>
</template>

<style scoped>
/* A thin strip along the top edge, where every page leaves room, so it never covers a title. */
.simulated-clock { position: fixed; z-index: 1000; top: 0; left: 0; right: 0; margin: 0; padding: 1px 12px; background: #2b2a33; color: #ffd76a; font-size: 11px; line-height: 16px; font-weight: 800; text-align: center; pointer-events: none; }
/* Sidebar and the white panel, both the height of the window; the panel scrolls. */
.product-shell { display: grid; grid-template-columns: 244px minmax(0, 1fr); height: 100vh; overflow: hidden; }
.product-frame { height: calc(100vh - 16px); overflow-y: auto; }
/* The profile's sticky column sticks inside the panel, not the window. */
.product-frame :deep(.profile-sidebar) { top: 72px; max-height: calc(100vh - 104px); }
.product-frame > .mc-bar { position: sticky; top: 0; z-index: 5; background: #fff; }
</style>
