import type { WeeklyMealPlan, WeeklyMealPlanRequest } from "~/types/meal-plan";
import type { HouseholdProfilePlanRequest, HouseholdProfilePlanResult } from "~/types/household";

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

  async function generateFromProfile(profileId: number, payload: HouseholdProfilePlanRequest) {
    isGenerating.value = true;
    errorMessage.value = null;
    try {
      const response = await $fetch<HouseholdProfilePlanResult>(
        `${config.public.apiBase}/api/household-profiles/${profileId}/plans`,
        { method: "POST", body: payload },
      );
      result.value = response.plan;
    }
    catch (error) {
      const detail = (error as { data?: { detail?: string } }).data?.detail;
      errorMessage.value = detail || "The weekly plan could not be generated from the saved profile.";
    }
    finally {
      isGenerating.value = false;
    }
  }

  return { errorMessage, generate, generateFromProfile, isGenerating, result };
}
