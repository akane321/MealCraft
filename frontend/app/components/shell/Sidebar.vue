<script setup lang="ts">
// The product sidebar: brand, an optional action, the pages, an optional list (recent plans) and card, the account.
// The home surface fills the slots; the other product pages use it as it is.
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
    <slot name="action" />
    <nav class="pages" aria-label="Pages">
      <!-- On the plan itself this is not a link, so the nav holds only the pages that leave it. -->
      <span v-if="current === 'plan'" class="sb-item on" aria-current="page"><UIcon name="i-lucide-house" />My plan</span>
      <NuxtLink v-else to="/" class="sb-item"><UIcon name="i-lucide-house" />My plan</NuxtLink>
      <NuxtLink to="/browse" class="sb-item" :class="on('browse')"><UIcon name="i-lucide-book-open" />Recipes &amp; groceries</NuxtLink>
      <NuxtLink to="/history" class="sb-item" :class="on('history')"><UIcon name="i-lucide-calendar-clock" />Past plans</NuxtLink>
      <NuxtLink v-if="!slots.card" to="/profile" class="sb-item" :class="on('profile')"><UIcon name="i-lucide-users" />Household</NuxtLink>
    </nav>
    <template v-if="slots.default">
      <div class="sb-sep" />
      <p class="sb-label">Recent plans</p>
      <slot />
    </template>
    <div v-else class="sb-fill" />
    <slot name="card" />
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
