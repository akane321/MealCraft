<script setup lang="ts">
const { load } = useAuth();
const route = useRoute();
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

// Product pages scroll inside the frame, not the window, so start each page at the top.
const frame = ref<HTMLElement | null>(null);
watch(() => route.path, () => frame.value?.scrollTo({ top: 0 }));

onMounted(load);
</script>

<template>
  <UApp>
    <div class="app-shell">
      <!-- Product pages sit in the sidebar shell; the home surface and the console (/ops) draw their own. -->
      <div v-if="shellPage" class="mc-shell mc-page product-shell">
        <ShellSidebar :current="shellPage" />
        <div ref="frame" class="mc-frame product-frame">
          <div class="mc-bar"><NuxtLink to="/" class="bar-home" aria-label="Back to My plan"><UIcon name="i-lucide-arrow-left" /></NuxtLink><UIcon :name="BARS[shellPage].icon" />{{ BARS[shellPage].label }}<ShellSimulated /></div>
          <NuxtPage />
        </div>
      </div>
      <!-- Sign-in: a glowing page with one card (the mark is in the card); the home surface and the console (/ops) draw their own. -->
      <div v-else-if="route.path.startsWith('/login')" class="mc-shell mc-page auth-shell">
        <ShellSimulated floating />
        <NuxtPage />
      </div>
      <NuxtPage v-else />
    </div>
  </UApp>
</template>

<style scoped>
/* Sidebar and the white panel, both the height of the window; the panel scrolls. */
.product-shell { display: grid; grid-template-columns: 244px minmax(0, 1fr); height: 100vh; overflow: hidden; }
.product-frame { height: calc(100vh - 16px); overflow-y: auto; }
.product-frame > .mc-bar { position: sticky; top: 0; z-index: 5; background: #fff; }
/* Phone (ADR-0116): the page alone, full width; the bar's arrow goes back to My plan. */
.bar-home { display: none; }
@media (max-width: 767px) {
  .product-shell { grid-template-columns: minmax(0, 1fr); height: 100dvh; }
  .product-shell > .sb { display: none; }
  .product-frame { height: 100dvh; margin: 0; border: 0; border-radius: 0; }
  .bar-home { width: 44px; height: 44px; margin: 0 -6px 0 -12px; display: grid; place-items: center; }
  .bar-home .iconify { width: 20px; height: 20px; color: #18181b; }
  .auth-shell { padding: 12px; }
}
/* The home's pastel glow behind the sign-in card. */
.auth-shell {
  min-height: 100vh; padding: 12px 18px;
  background:
    radial-gradient(560px 300px at 50% 8%, rgba(255, 226, 200, 0.7), transparent 70%),
    radial-gradient(420px 320px at 30% 40%, rgba(233, 213, 255, 0.45), transparent 70%),
    radial-gradient(460px 240px at 55% 70%, rgba(255, 240, 166, 0.45), transparent 70%),
    radial-gradient(400px 300px at 75% 45%, rgba(255, 211, 230, 0.4), transparent 70%),
    #f5f5f7;
}
</style>
