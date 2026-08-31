import type { WeeklyMealPlan, WeeklyMealPlanRequest } from "~/types/meal-plan";

export function useWeeklyMealPlan() {
  const config = useRuntimeConfig();
  const result = ref<WeeklyMealPlan | null>(null);
  const errorMessage = ref<string | null>(null);
  const isGenerating = ref(false);

  async function generate(payload: WeeklyMealPlanRequest) {
    isGenerating.value = true;
    errorMessage.value = null;
    try {
      result.value = await $fetch<WeeklyMealPlan>(`${config.public.apiBase}/api/plans/generate`, {
        method: "POST",
        body: payload,
      });
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "The weekly plan could not be generated. Check the constraints and try again.";
    }
    finally {
      isGenerating.value = false;
    }
  }

  return { errorMessage, generate, isGenerating, result };
}
