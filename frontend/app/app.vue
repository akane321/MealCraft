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
        <nav class="primary-nav" aria-label="Primary navigation">
          <NuxtLink to="/assistant">Assistant</NuxtLink>
          <NuxtLink to="/profile">Profile</NuxtLink>
          <NuxtLink to="/weekly-plan">Weekly plan</NuxtLink>
          <NuxtLink to="/dashboard">Dashboard</NuxtLink>
          <NuxtLink to="/plan">Plan</NuxtLink>
          <NuxtLink to="/recipes">Recipes</NuxtLink>
          <NuxtLink to="/products">Products</NuxtLink>
          <NuxtLink to="/system">System</NuxtLink>
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
