<script setup lang="ts">
const { actor, load, logout } = useAuth();
const route = useRoute();

useHead({
  link: [
    { rel: "preconnect", href: "https://fonts.googleapis.com" },
    { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,400;1,9..144,300;1,9..144,400&family=Figtree:wght@400;500;600&display=swap" },
  ],
});

onMounted(load);
</script>

<template>
  <div class="app-shell">
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
