import type {
  AgentConfirmation,
  AgentReplanConfirmation,
  AgentSession,
  AgentSessionCollection,
} from "~/types/agent";

export function useMealCraftAgent() {
  const config = useRuntimeConfig();
  const session = ref<AgentSession | null>(null);
  const generatedPlan = ref<AgentConfirmation["plan"] | null>(null);
  const errorMessage = ref<string | null>(null);
  const isLoading = ref(false);

  async function run<T>(request: () => Promise<T>): Promise<T | null> {
    isLoading.value = true;
    errorMessage.value = null;
    try {
      return await request();
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "The planning assistant could not complete that request.";
      return null;
    }
    finally {
      isLoading.value = false;
    }
  }

  async function create(message: string) {
    generatedPlan.value = null;
    const result = await run(() => $fetch<AgentSession>(`${config.public.apiBase}/api/agent/sessions`, {
      method: "POST",
      body: { message },
    }));
    if (result) session.value = result;
  }

  async function reply(message: string) {
    if (!session.value) return;
    const result = await run(() => $fetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/messages`,
      { method: "POST", body: { message } },
    ));
    if (result) session.value = result;
  }

  async function confirm() {
    if (!session.value) return;
    const result = await run(() => $fetch<AgentConfirmation>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/confirm`,
      { method: "POST" },
    ));
    if (result) {
      session.value = result.session;
      generatedPlan.value = result.plan;
    }
  }

  async function confirmReplan() {
    if (!session.value) return null;
    const result = await run(() => $fetch<AgentReplanConfirmation>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/replan/confirm`,
      { method: "POST" },
    ));
    if (result) {
      session.value = result.session;
      generatedPlan.value = result.plan;
    }
    return result;
  }

  async function discardReplan() {
    if (!session.value) return;
    const result = await run(() => $fetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/replan/discard`,
      { method: "POST" },
    ));
    if (result) session.value = result;
  }

  async function restoreLatest() {
    const result = await run(() => $fetch<AgentSessionCollection>(
      `${config.public.apiBase}/api/agent/sessions`,
      { query: { limit: 1 } },
    ));
    if (result?.items[0]) session.value = result.items[0];
  }

  function reset() {
    session.value = null;
    generatedPlan.value = null;
    errorMessage.value = null;
  }

  return {
    confirm,
    confirmReplan,
    create,
    discardReplan,
    errorMessage,
    generatedPlan,
    isLoading,
    reply,
    reset,
    restoreLatest,
    session,
  };
}
