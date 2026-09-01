import type {
  MealPlanReplanConfirmation,
  MealPlanReplanEvent,
  MealPlanReplanEventCollection,
  MealPlanReplanPreviewRequest,
} from "~/types/meal-plan";

export function useMealReplanning() {
  const config = useRuntimeConfig();
  const preview = ref<MealPlanReplanEvent | null>(null);
  const events = ref<MealPlanReplanEvent[]>([]);
  const errorMessage = ref<string | null>(null);
  const isPreviewing = ref(false);
  const isConfirming = ref(false);

  async function loadEvents(planId: number) {
    const collection = await $fetch<MealPlanReplanEventCollection>(
      `${config.public.apiBase}/api/plans/${planId}/events`,
    );
    events.value = collection.items;
  }

  async function createPreview(planId: number, request: MealPlanReplanPreviewRequest) {
    isPreviewing.value = true;
    errorMessage.value = null;
    preview.value = null;
    try {
      preview.value = await $fetch<MealPlanReplanEvent>(
        `${config.public.apiBase}/api/plans/${planId}/replan/preview`,
        { method: "POST", body: request },
      );
      return preview.value;
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "MealCraft could not prepare this change.";
      return null;
    }
    finally {
      isPreviewing.value = false;
    }
  }

  async function confirmPreview(planId: number) {
    if (!preview.value) return null;
    isConfirming.value = true;
    errorMessage.value = null;
    try {
      const result = await $fetch<MealPlanReplanConfirmation>(
        `${config.public.apiBase}/api/plans/${planId}/replan/${preview.value.id}/confirm`,
        { method: "POST" },
      );
      preview.value = null;
      await loadEvents(planId);
      return result;
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "MealCraft could not apply this change.";
      return null;
    }
    finally {
      isConfirming.value = false;
    }
  }

  function clearPreview() {
    preview.value = null;
    errorMessage.value = null;
  }

  return {
    clearPreview,
    confirmPreview,
    createPreview,
    errorMessage,
    events,
    isConfirming,
    isPreviewing,
    loadEvents,
    preview,
  };
}
