// Docker Desktop on Windows does not pass file-change events through a bind mount, so the dev container
// (compose.yaml) polls for changes instead. A checkout run on the host keeps native file events.
const pollForChanges = process.env.MEALCRAFT_WATCH_POLLING === "true";
const polling = { usePolling: pollForChanges, interval: 300 };

export default defineNuxtConfig({
  compatibilityDate: "2026-08-31",
  css: ["~/assets/css/main.css", "~/assets/css/surface.css"],
  devtools: { enabled: true },
  modules: ["@nuxt/eslint"],
  runtimeConfig: {
    apiBase: "http://backend:8000",
    public: {
      apiBase: "http://localhost:8000",
    },
  },
  typescript: {
    strict: true,
  },
  // Vite's watcher reloads edited components; Nuxt's notices new and removed pages, components and composables.
  vite: { server: { watch: polling } },
  watchers: { chokidar: polling },
});
