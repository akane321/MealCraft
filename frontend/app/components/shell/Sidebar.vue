<script setup lang="ts">
// The product sidebar: brand, New plan, the pages, an optional list (recent plans), the household card, the account.
// The home surface fills the slots; the other product pages get the same rows, so only the current item moves.
const props = defineProps<{ current?: "plan" | "browse" | "history" | "profile" | "system" | "other" | null; brandButton?: boolean }>();
const emit = defineEmits<{ brand: [] }>();
const { actor, logout } = useAuth();
const initials = computed(() => (actor.value?.user.display_name ?? "?")
  .split(/\s+/).filter(Boolean).slice(0, 2).map(word => word[0]!.toUpperCase()).join(""));
const on = (page: string) => ({ on: props.current === page });
// Ctrl K is New plan on every product page (the home binds its own, which also clears the chat).
// /?new=1 opens the home straight into a fresh conversation.
function onKey(event: KeyboardEvent) {
  if (!props.brandButton && (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    void navigateTo("/?new=1");
  }
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <aside class="rail sb" aria-label="Navigation">
    <button v-if="brandButton" type="button" class="sb-brand" aria-label="Back to home" @click="emit('brand')">
      <ShellMark />MealCraft
    </button>
    <NuxtLink v-else to="/" class="sb-brand"><ShellMark />MealCraft</NuxtLink>
    <slot name="action">
      <UButton to="/?new=1" color="neutral" variant="outline" class="sb-new" icon="i-lucide-plus">New plan<UKbd class="sb-kbd" value="Ctrl K" /></UButton>
    </slot>
    <nav class="pages" aria-label="Pages">
      <!-- On the plan itself this is not a link, so the nav holds only the pages that leave it. -->
      <span v-if="current === 'plan'" class="sb-item on" aria-current="page"><UIcon name="i-lucide-house" />My plan</span>
      <NuxtLink v-else to="/" class="sb-item"><UIcon name="i-lucide-house" />My plan</NuxtLink>
      <NuxtLink to="/browse" class="sb-item" :class="on('browse')"><UIcon name="i-lucide-book-open" />Recipes &amp; groceries</NuxtLink>
      <NuxtLink to="/history" class="sb-item" :class="on('history')"><UIcon name="i-lucide-calendar-clock" />Past plans</NuxtLink>
    </nav>
    <!-- The same section on every page, so the sidebar keeps its shape; the list itself lives on My plan. -->
    <div class="sb-sep" />
    <p class="sb-label">Recent plans</p>
    <slot>
      <p class="sb-hint">Open My plan to see your recent plans.</p>
      <div class="sb-fill" />
    </slot>
    <slot name="card">
      <div class="home-card">
        <b>Your household</b>
        <small>Who's eating, the budget and what to avoid.</small>
        <NuxtLink to="/profile" class="home-link">Household<UIcon name="i-lucide-chevron-right" /></NuxtLink>
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
.sb-hint { flex: none; margin: 4px 10px; color: #52525b; font-size: 12.5px; line-height: 18px; }
</style>
