import type {
  RecipeRecommendationCollection,
  RecipeRecommendationRequest,
} from "~/types/recommendation";

export function useRecipeRecommendations() {
  const config = useRuntimeConfig();
  const result = ref<RecipeRecommendationCollection | null>(null);
  const errorMessage = ref<string | null>(null);
  const isSubmitting = ref(false);

  async function recommend(payload: RecipeRecommendationRequest) {
    isSubmitting.value = true;
    errorMessage.value = null;

    try {
      result.value = await $fetch<RecipeRecommendationCollection>(
        `${config.public.apiBase}/api/recommendations/recipes`,
        {
          method: "POST",
          body: payload,
        },
      );
    }
    catch {
      errorMessage.value = "Recommendations could not be generated. Check the entered quantities and try again.";
    }
    finally {
      isSubmitting.value = false;
    }
  }

  return { errorMessage, isSubmitting, recommend, result };
}
