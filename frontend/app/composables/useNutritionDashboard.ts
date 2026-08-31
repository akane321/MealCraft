import type {
  MealPlanEntryStatus,
  WeeklyMealPlan,
  WeeklyMealPlanCollection,
  WeeklyMealPlanListItem,
  WeeklyNutritionDashboard,
} from "~/types/meal-plan";

export function useNutritionDashboard() {
  const config = useRuntimeConfig();
  const plans = ref<WeeklyMealPlanListItem[]>([]);
  const dashboard = ref<WeeklyNutritionDashboard | null>(null);
  const errorMessage = ref<string | null>(null);
  const isLoading = ref(false);
  const updatingEntryId = ref<number | null>(null);

  async function loadPlans(preferredPlanId?: number | null) {
    isLoading.value = true;
    errorMessage.value = null;
    try {
      const collection = await $fetch<WeeklyMealPlanCollection>(`${config.public.apiBase}/api/plans`);
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

  async function loadDashboard(planId: number) {
    dashboard.value = await $fetch<WeeklyNutritionDashboard>(
      `${config.public.apiBase}/api/plans/${planId}/dashboard`,
    );
  }

  async function updateStatus(entryId: number, status: MealPlanEntryStatus) {
    if (!dashboard.value) return;
    updatingEntryId.value = entryId;
    errorMessage.value = null;
    try {
      await $fetch<WeeklyMealPlan>(
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

  return {
    dashboard,
    errorMessage,
    isLoading,
    loadDashboard,
    loadPlans,
    plans,
    updateStatus,
    updatingEntryId,
  };
}
