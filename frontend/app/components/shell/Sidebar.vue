<script setup lang="ts">
// The product sidebar: brand, New plan, the pages, an optional list (recent plans), the household card, the account.
// The home surface fills the slots; the other product pages get the same rows, so only the current item moves.
const props = defineProps<{ current?: "plan" | "browse" | "history" | "profile" | "system" | "other" | null; brandButton?: boolean }>();
const emit = defineEmits<{ brand: [] }>();
const slots = useSlots();
const { actor, logout } = useAuth();
const initials = computed(() => (actor.value?.user.display_name ?? "?")
  .split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]!.toUpperCase()).join(""));
const on = (page: string) => ({ on: props.current === page });
</script>

<template>
  <aside class="rail sb" aria-label="Navigation">
    <button v-if="brandButton" type="button" class="sb-brand" aria-label="Back to home" @click="emit('brand')">
      <ShellMark />MealCraft
    </button>
    <NuxtLink v-else to="/" class="sb-brand"><ShellMark />MealCraft</NuxtLink>
    <slot name="action">
      <UButton to="/" color="neutral" variant="outline" class="sb-new" icon="i-lucide-plus">New plan</UButton>
    </slot>
    <nav class="pages" aria-label="Pages">
      <!-- On the plan itself this is not a link, so the nav holds only the pages that leave it. -->
      <span v-if="current === 'plan'" class="sb-item on" aria-current="page"><UIcon name="i-lucide-house" />My plan</span>
      <NuxtLink v-else to="/" class="sb-item"><UIcon name="i-lucide-house" />My plan</NuxtLink>
      <NuxtLink to="/browse" class="sb-item" :class="on('browse')"><UIcon name="i-lucide-book-open" />Recipes &amp; groceries</NuxtLink>
      <NuxtLink to="/history" class="sb-item" :class="on('history')"><UIcon name="i-lucide-calendar-clock" />Past plans</NuxtLink>
    </nav>
    <template v-if="slots.default">
      <div class="sb-sep" />
      <p class="sb-label">Recent plans</p>
      <slot />
    </template>
    <div v-else class="sb-fill" />
    <slot name="card">
      <div class="home-card">
        <b>Your household</b>
        <small>Who's eating, the budget and what to avoid.</small>
        <NuxtLink to="/profile" class="home-link">Household<UIcon name="i-lucide-arrow-up-right" /></NuxtLink>
      </div>
    </slot>
    <div class="sb-user">
      <template v-if="actor">
        <span class="sb-avatar" aria-hidden="true">{{ initials }}</span>
        <span class="sb-who"><b>{{ actor.user.display_name }}</b><small>Signed in</small></span>
        <UTooltip text="Service status">
          <UButton to="/system" color="neutral" variant="ghost" size="sm" square class="sb-icon" icon="i-lucide-activity" aria-label="Status" />
        </UTooltip>
        <UTooltip text="Sign out">
          <UButton color="neutral" variant="ghost" size="sm" square class="sb-icon" icon="i-lucide-log-out" aria-label="Sign out" @click="logout" />
        </UTooltip>
      </template>
      <NuxtLink v-else to="/login" class="sb-item sb-signin"><UIcon name="i-lucide-log-in" />Sign in</NuxtLink>
    </div>
  </aside>
</template>

<style scoped>
.sb-signin { flex: 1; }
</style>
