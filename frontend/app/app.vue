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
  ],
});

onMounted(load);
</script>

<template>
  <div class="app-shell">
    <p v-if="simulatedLabel" class="simulated-clock" role="status">Simulated date: {{ simulatedLabel }} · for debugging</p>
    <!-- The home surface and the console (/ops) draw their own navigation. -->
    <header v-if="route.path !== '/' && !route.path.startsWith('/ops')" class="app-header">
      <div class="page-width header-content">
        <NuxtLink class="brand-name" to="/">
          <svg viewBox="0 0 32 32" width="24" height="24" aria-hidden="true"><circle cx="16" cy="18" r="10.5" fill="none" stroke="currentColor" stroke-width="1.6" /><path d="M16 7.5c1.4-3.2 4.6-4.2 7-3.3-.9 2.8-3.7 4.4-7 3.3z" fill="#c2553a" /></svg>MealCraft
        </NuxtLink>
        <!-- The week happens on the home surface; these pages lead back to it and to each other. -->
        <nav class="primary-nav" aria-label="Primary navigation">
          <NuxtLink to="/">Back to my week</NuxtLink>
          <NuxtLink to="/browse">Recipes</NuxtLink>
          <NuxtLink to="/history">Past weeks</NuxtLink>
          <button v-if="actor" class="nav-auth" type="button" @click="logout">
            Sign out {{ actor.user.display_name }}
          </button>
          <NuxtLink v-else to="/login">Sign in</NuxtLink>
        </nav>
      </div>
    </header>

    <NuxtPage />
  </div>
</template>

<style scoped>
/* A thin strip along the top edge, where every page leaves room, so it never covers a title. */
.simulated-clock { position: fixed; z-index: 1000; top: 0; left: 0; right: 0; margin: 0; padding: 1px 12px; background: #2b2a33; color: #ffd76a; font-size: 11px; line-height: 16px; font-weight: 800; text-align: center; pointer-events: none; }
</style>
