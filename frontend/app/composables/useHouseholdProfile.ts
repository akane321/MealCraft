import type {
  HouseholdProfile,
  HouseholdProfileInput,
  HouseholdProfilePlanRequest,
  HouseholdProfilePlanResult,
  HouseholdProfileUpdate,
} from "~/types/household";

export function useHouseholdProfile() {
  const config = useRuntimeConfig();
  const current = ref<HouseholdProfile | null>(null);
  const planResult = ref<HouseholdProfilePlanResult | null>(null);
  const errorMessage = ref<string | null>(null);
  const isLoading = ref(false);
  const isSaving = ref(false);
  const isPlanning = ref(false);

  function detail(error: unknown, fallback: string) {
    return (error as { data?: { detail?: string } }).data?.detail || fallback;
  }

  async function loadCurrent() {
    isLoading.value = true;
    errorMessage.value = null;
    try {
      current.value = await $fetch<HouseholdProfile>(
        `${config.public.apiBase}/api/household-profiles/current`,
      );
    }
    catch (error) {
      const statusCode = (error as { statusCode?: number; response?: { status?: number } }).statusCode
        || (error as { response?: { status?: number } }).response?.status;
      if (statusCode === 404) {
        current.value = null;
      }
      else {
        errorMessage.value = detail(error, "The household profile could not be loaded.");
      }
    }
    finally {
      isLoading.value = false;
    }
  }

  async function save(payload: HouseholdProfileInput) {
    isSaving.value = true;
    errorMessage.value = null;
    try {
      if (current.value) {
        const update: HouseholdProfileUpdate = {
          ...payload,
          expected_version: current.value.current_version,
        };
        current.value = await $fetch<HouseholdProfile>(
          `${config.public.apiBase}/api/household-profiles/${current.value.id}`,
          { method: "PUT", body: update },
        );
      }
      else {
        current.value = await $fetch<HouseholdProfile>(
          `${config.public.apiBase}/api/household-profiles`,
          { method: "POST", body: payload },
        );
      }
      return current.value;
    }
    catch (error) {
      errorMessage.value = detail(error, "The household profile could not be saved.");
      return null;
    }
    finally {
      isSaving.value = false;
    }
  }

  async function generatePlan(payload: HouseholdProfilePlanRequest) {
    if (!current.value) return null;
    isPlanning.value = true;
    errorMessage.value = null;
    try {
      planResult.value = await $fetch<HouseholdProfilePlanResult>(
        `${config.public.apiBase}/api/household-profiles/${current.value.id}/plans`,
        { method: "POST", body: payload },
      );
      current.value.latest_plan_id = planResult.value.plan.id;
      return planResult.value;
    }
    catch (error) {
      errorMessage.value = detail(error, "A plan could not be generated from this profile.");
      return null;
    }
    finally {
      isPlanning.value = false;
    }
  }

  async function replanLatest(payload: HouseholdProfilePlanRequest) {
    if (!current.value?.latest_plan_id) return null;
    isPlanning.value = true;
    errorMessage.value = null;
    try {
      planResult.value = await $fetch<HouseholdProfilePlanResult>(
        `${config.public.apiBase}/api/household-profiles/${current.value.id}/plans/${current.value.latest_plan_id}/replan`,
        { method: "POST", body: payload },
      );
      current.value.latest_plan_id = planResult.value.plan.id;
      return planResult.value;
    }
    catch (error) {
      errorMessage.value = detail(error, "The latest plan could not be rebuilt from this profile.");
      return null;
    }
    finally {
      isPlanning.value = false;
    }
  }

  return {
    current,
    errorMessage,
    generatePlan,
    isLoading,
    isPlanning,
    isSaving,
    loadCurrent,
    planResult,
    replanLatest,
    save,
  };
}
