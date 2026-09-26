export function useApiFetch() {
  const csrfToken = useCookie<string | null>("mealcraft_csrf");
  const route = useRoute();
  const actor = useState("mealcraft-actor");

  return $fetch.create({
    credentials: "include",
    onRequest({ options }) {
      const method = String(options.method || "GET").toUpperCase();
      if (!["GET", "HEAD", "OPTIONS"].includes(method) && csrfToken.value) {
        const headers = new Headers(options.headers);
        headers.set("X-CSRF-Token", csrfToken.value);
        options.headers = headers;
      }
    },
    onResponseError({ request, response }) {
      if (
        import.meta.client
        && response.status === 401
        && !String(request).includes("/api/auth/")
      ) {
        // The session is over: forget who was signed in (or the login page would send them straight
        // back), and return to where they were afterwards; the home page keeps the typed draft.
        actor.value = null;
        void navigateTo({ path: "/login", query: { next: route.fullPath } });
      }
    },
  });
}
