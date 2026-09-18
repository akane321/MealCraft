<script setup lang="ts">
const { actor, load, logout } = useAuth();
const route = useRoute();

onMounted(load);
</script>

<template>
  <div class="app-shell">
    <header v-if="route.path !== '/'" class="app-header">
      <div class="page-width header-content">
        <NuxtLink class="brand-name" to="/">MealCraft</NuxtLink>
        <!-- Everything happens on the home surface; these pages only need a way back. -->
        <nav class="primary-nav" aria-label="Primary navigation">
          <NuxtLink to="/">Back to my week</NuxtLink>
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
