export default defineNuxtConfig({
  compatibilityDate: "2026-08-31",
  css: ["~/assets/css/main.css"],
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
});
