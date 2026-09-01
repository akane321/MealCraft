<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="page-width header-content">
        <NuxtLink class="brand-name" to="/">MealCraft</NuxtLink>
        <nav class="primary-nav" aria-label="Primary navigation">
          <NuxtLink to="/assistant">Assistant</NuxtLink>
          <NuxtLink to="/weekly-plan">Weekly plan</NuxtLink>
          <NuxtLink to="/dashboard">Dashboard</NuxtLink>
          <NuxtLink to="/plan">Plan</NuxtLink>
          <NuxtLink to="/recipes">Recipes</NuxtLink>
          <NuxtLink to="/products">Products</NuxtLink>
          <NuxtLink to="/">System</NuxtLink>
        </nav>
      </div>
    </header>

    <NuxtPage />
  </div>
</template>
