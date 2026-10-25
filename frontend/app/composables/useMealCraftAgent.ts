import { conversationForPlan } from "~/lib/home-surface";
import type { PlanningPreferencesView } from "~/lib/planning-preferences";
import type {
  AgentConfirmation,
  AgentInteractionAnswer,
  AgentReplanConfirmation,
  AgentSession,
  AgentSessionCollection,
} from "~/types/agent";

export function useMealCraftAgent() {
  const config = useRuntimeConfig();
  const apiFetch = useApiFetch();
  const session = ref<AgentSession | null>(null);
  const generatedPlan = ref<AgentConfirmation["plan"] | null>(null);
  const errorMessage = ref<string | null>(null);
  const isLoading = ref(false);
  const recent = ref<AgentSession[]>([]);
  // Switching conversations invalidates their in-flight answers, not the household's saved week.
  let generation = 0;

  async function run<T>(request: () => Promise<T>): Promise<T | null> {
    const current = generation;
    isLoading.value = true;
    errorMessage.value = null;
    try {
      const result = await request();
      return current === generation ? result : null;
    }
    catch (error) {
      if (current === generation) {
        const detail = (error as { data?: { detail?: string } }).data?.detail;
        errorMessage.value = detail || "The planning assistant could not complete that request.";
      }
      return null;
    }
    finally {
      if (current === generation) isLoading.value = false;
    }
  }

  // `planId`: the week the message changes, for a conversation that did not plan it (it takes the week on).
  async function create(message: string, planId: number | null = null) {
    generatedPlan.value = null;
    const result = await run(() => apiFetch<AgentSession>(`${config.public.apiBase}/api/agent/sessions`, {
      method: "POST",
      body: { message, plan_id: planId },
    }));
    if (result) session.value = result;
    return result;
  }

  async function reply(message: string, planId: number | null = null) {
    if (!session.value) return;
    const result = await run(() => apiFetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/messages`,
      { method: "POST", body: { message, plan_id: planId } },
    ));
    if (result) session.value = result;
    return result;
  }

  async function answerInteraction(answer: AgentInteractionAnswer) {
    if (!session.value) return;
    const result = await run(() => apiFetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/interactions`,
      { method: "POST", body: answer },
    ));
    if (result) session.value = result;
    return result;
  }

  async function updatePreferences(planningPreferences: PlanningPreferencesView, contextVersion: number) {
    if (!session.value) return null;
    const result = await run(() => apiFetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/preferences`,
      { method: "PUT", body: { context_version: contextVersion, planning_preferences: planningPreferences } },
    ));
    if (result) session.value = result;
    return result;
  }

  async function confirm() {
    if (!session.value) return;
    const id = session.value.id;
    const current = generation;
    const result = await run(() => apiFetch<AgentConfirmation>(
      `${config.public.apiBase}/api/agent/sessions/${id}/confirm`,
      { method: "POST" },
    ));
    if (current !== generation) return;
    if (result) {
      session.value = result.session;
      generatedPlan.value = result.plan;
      return;
    }
    // A week that could not be planned is explained in the conversation, which replaces the Plan card.
    const explained = await apiFetch<AgentSession>(`${config.public.apiBase}/api/agent/sessions/${id}`).catch(() => null);
    if (current === generation && explained && explained.messages.length > (session.value?.messages.length ?? 0)) {
      session.value = explained;
      errorMessage.value = null;
    }
  }

  async function confirmReplan() {
    if (!session.value) return null;
    const current = generation;
    let conflict = false;
    const result = await run(() => apiFetch<AgentReplanConfirmation>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/replan/confirm`,
      { method: "POST" },
    ).catch((error: { statusCode?: number }) => {
      conflict = error.statusCode === 409;
      throw error;
    }));
    if (result) {
      session.value = result.session;
      generatedPlan.value = result.plan;
    }
    else if (conflict && current === generation) {
      // A stale preview (the week changed, or a dish in it was marked Never again) can never be confirmed:
      // clear its card as Discard does and keep the 409's message, which says to ask for a new one.
      const discarded = await apiFetch<AgentSession>(
        `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/replan/discard`,
        { method: "POST" },
      ).catch(() => null);
      if (discarded && current === generation) session.value = discarded;
    }
    return result;
  }

  async function discardReplan() {
    if (!session.value) return;
    const result = await run(() => apiFetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${session.value?.id}/replan/discard`,
      { method: "POST" },
    ));
    if (result) session.value = result;
  }

  /** Fills the recent list and reopens the conversation for the week `planId` (conversationForPlan); with none, a fresh one. */
  async function restore(planId: number | null) {
    const result = await run(() => apiFetch<AgentSessionCollection>(
      `${config.public.apiBase}/api/agent/sessions`,
      { query: { limit: 50 } },
    ));
    if (!result) return;
    recent.value = result.items;
    session.value = conversationForPlan(result.items, planId);
  }

  /** Renames or (un)pins a conversation; the list and the open one take the server's copy. */
  async function label(id: number, change: { title?: string | null; pinned?: boolean }) {
    const result = await run(() => apiFetch<AgentSession>(
      `${config.public.apiBase}/api/agent/sessions/${id}`,
      { method: "PATCH", body: change },
    ));
    if (!result) return;
    recent.value = recent.value.map(item => (item.id === id ? result : item));
    if (!recent.value.some(item => item.id === id)) recent.value = [result, ...recent.value];
    // Pinned first, the latest pin on top, then by when each last changed (the server's order).
    recent.value = [...recent.value].sort((a, b) => (b.pinned_at ?? "").localeCompare(a.pinned_at ?? "") || (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));
    if (session.value?.id === id) session.value = result;
  }

  /** Deletes a conversation; true once it is gone. */
  async function remove(id: number): Promise<boolean> {
    const done = await run(async () => {
      await apiFetch(`${config.public.apiBase}/api/agent/sessions/${id}`, { method: "DELETE" });
      return true;
    });
    if (!done) return false;
    recent.value = recent.value.filter(item => item.id !== id);
    return true;
  }

  function reset() {
    generation += 1;
    session.value = null;
    generatedPlan.value = null;
    errorMessage.value = null;
    isLoading.value = false;
  }

  return {
    answerInteraction,
    confirm,
    confirmReplan,
    create,
    discardReplan,
    errorMessage,
    generatedPlan,
    isLoading,
    label,
    recent,
    remove,
    reply,
    reset,
    restore,
    session,
    updatePreferences,
  };
}
