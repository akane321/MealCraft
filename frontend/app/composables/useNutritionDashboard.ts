import type {
  FeedbackKind,
  MealPlanEntryStatus,
  WeeklyMealPlan,
  WeeklyMealPlanCollection,
  WeeklyMealPlanListItem,
  WeeklyNutritionDashboard,
} from "~/types/meal-plan";

export function useNutritionDashboard() {
  const config = useRuntimeConfig();
  const apiFetch = useApiFetch();
  const plans = ref<WeeklyMealPlanListItem[]>([]);
  const dashboard = ref<WeeklyNutritionDashboard | null>(null);
  const errorMessage = ref<string | null>(null);
  const isLoading = ref(false);
  const updatingEntryId = ref<number | null>(null);
  const feedbackRecipeId = ref<number | null>(null);
  const feedbackError = ref<string | null>(null);

  async function loadPlans(preferredPlanId?: number | null) {
    isLoading.value = true;
    errorMessage.value = null;
    try {
      const collection = await apiFetch<WeeklyMealPlanCollection>(`${config.public.apiBase}/api/plans`);
      plans.value = collection.items;
      const selected = plans.value.find(plan => plan.id === preferredPlanId) || plans.value[0];
      if (selected) await loadDashboard(selected.id);
      else dashboard.value = null;
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "The nutrition dashboard could not be loaded.";
    }
    finally {
      isLoading.value = false;
    }
  }

  let requested: number | null = null;

  async function loadDashboard(planId: number) {
    requested = planId;
    const loaded = await apiFetch<WeeklyNutritionDashboard>(
      `${config.public.apiBase}/api/plans/${planId}/dashboard`,
    );
    // Switching weeks quickly must not let the slower, older answer win.
    if (requested === planId) dashboard.value = loaded;
  }

  async function updateStatus(entryId: number, status: MealPlanEntryStatus) {
    if (!dashboard.value) return;
    updatingEntryId.value = entryId;
    errorMessage.value = null;
    try {
      await apiFetch<WeeklyMealPlan>(
        `${config.public.apiBase}/api/plans/${dashboard.value.plan_id}/entries/${entryId}`,
        { method: "PATCH", body: { status } },
      );
      await loadDashboard(dashboard.value.plan_id);
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "The meal status could not be updated.";
    }
    finally {
      updatingEntryId.value = null;
    }
  }

  /** Marks every dish of one meal at once (the whole-meal check-in of ADR-0036). */
  async function updateMeal(dayIndex: number, mealType: string, status: MealPlanEntryStatus, firstEntryId: number) {
    if (!dashboard.value) return;
    updatingEntryId.value = firstEntryId;
    errorMessage.value = null;
    try {
      await apiFetch<WeeklyMealPlan>(
        `${config.public.apiBase}/api/plans/${dashboard.value.plan_id}/meals/${dayIndex}/${mealType}`,
        { method: "PATCH", body: { status } },
      );
      await loadDashboard(dashboard.value.plan_id);
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "The meal status could not be updated.";
    }
    finally {
      updatingEntryId.value = null;
    }
  }

  /** Like, Dislike or Never again on a dish for the whole household (ADR-0087); null undoes it. */
  async function setFeedback(recipeId: number, kind: FeedbackKind | null) {
    if (!dashboard.value) return;
    feedbackRecipeId.value = recipeId;
    feedbackError.value = null;
    try {
      const url = `${config.public.apiBase}/api/feedback/recipes/${recipeId}`;
      await (kind ? apiFetch(url, { method: "PUT", body: { kind } }) : apiFetch(url, { method: "DELETE" }));
      await loadDashboard(dashboard.value.plan_id);
    }
    catch {
      feedbackError.value = "Your feedback could not be saved.";
    }
    finally {
      feedbackRecipeId.value = null;
    }
  }

  return {
    dashboard,
    errorMessage,
    feedbackError,
    feedbackRecipeId,
    isLoading,
    loadDashboard,
    loadPlans,
    plans,
    setFeedback,
    updateMeal,
    updateStatus,
    updatingEntryId,
  };
}
