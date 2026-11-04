// Docker Desktop on Windows does not pass file-change events through a bind mount, so the dev container
// (compose.yaml) polls for changes instead. A checkout run on the host keeps native file events.
const pollForChanges = process.env.MEALCRAFT_WATCH_POLLING === "true";
const polling = { usePolling: pollForChanges, interval: 300 };

export default defineNuxtConfig({
  compatibilityDate: "2026-08-31",
  // Phone browsers: safe-area insets need viewport-fit=cover; Chrome on Android resizes the page for the keyboard.
  app: {
    head: {
      meta: [{ name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content" }],
    },
  },
  css: ["~/assets/css/tailwind.css", "~/assets/css/main.css", "~/assets/css/surface.css", "~/assets/css/product.css"],
  devtools: { enabled: true },
  // Icons are bundled from @iconify-json/lucide; nothing is fetched at runtime.
  icon: { clientBundle: { scan: true }, fallbackToApi: false },
  modules: ["@nuxt/eslint", "@nuxt/ui"],
  runtimeConfig: {
    apiBase: "http://backend:8000",
    public: {
      apiBase: "http://localhost:8000",
      // The MealCraft FairPrice cart extension (browser-extension/fairprice-cart); its manifest key fixes this id.
      fairpriceCartExtensionId: "iogncfhaaajiccdgdnncocllpojhdepm",
    },
  },
  // Light only; fonts come from the Google Fonts links in app.vue. Only the components the app uses get theme
  // files, so the global stylesheet carries no utilities for the rest.
  ui: { colorMode: false, fonts: false, experimental: { componentDetection: true } },
  typescript: {
    strict: true,
  },
  // Vite's watcher reloads edited components; Nuxt's notices new and removed pages, components and composables.
  vite: { server: { watch: polling } },
  watchers: { chokidar: polling },
});
