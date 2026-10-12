interface AccountPublic {
  id: number;
  email: string;
  display_name: string;
  locale: string;
  timezone: string;
  status: string;
  system_role: string;
}

interface CurrentActor {
  user: AccountPublic;
  active_household_id: number | null;
  household_role: string | null;
}

interface AuthenticationResponse {
  actor: CurrentActor;
  csrf_token: string;
}

export function useAuth() {
  const config = useRuntimeConfig();
  const actor = useState<CurrentActor | null>("mealcraft-actor", () => null);
  const isLoading = useState("mealcraft-auth-loading", () => false);
  const errorMessage = useState<string | null>("mealcraft-auth-error", () => null);
  const apiFetch = useApiFetch();

  async function load() {
    isLoading.value = true;
    try {
      actor.value = await apiFetch<CurrentActor>(`${config.public.apiBase}/api/auth/me`);
    }
    catch {
      actor.value = null;
    }
    finally {
      isLoading.value = false;
    }
  }

  async function authenticate(mode: "login" | "register", payload: Record<string, string>) {
    isLoading.value = true;
    errorMessage.value = null;
    try {
      const response = await apiFetch<AuthenticationResponse>(`${config.public.apiBase}/api/auth/${mode}`, {
        method: "POST",
        body: payload,
      });
      useCookie<string | null>("mealcraft_csrf").value = response.csrf_token;
      actor.value = response.actor;
      return true;
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string | { msg?: string }[] } }).data?.detail;
      // A rejected field (422) comes as a list; show its first reason, as written by the API.
      const reason = Array.isArray(detail) ? detail[0]?.msg?.replace(/^Value error, /, "") : detail;
      errorMessage.value = reason ? reason.charAt(0).toUpperCase() + reason.slice(1) : "Authentication failed.";
      return false;
    }
    finally {
      isLoading.value = false;
    }
  }

  async function logout() {
    await apiFetch(`${config.public.apiBase}/api/auth/logout`, { method: "POST" });
    actor.value = null;
    useCookie<string | null>("mealcraft_csrf").value = null;
    await navigateTo("/login");
  }

  return { actor, authenticate, errorMessage, isLoading, load, logout };
}
