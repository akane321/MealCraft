export function useApiFetch() {
  const csrfToken = useCookie<string | null>("mealcraft_csrf");

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
        void navigateTo("/login");
      }
    },
  });
}
