import type { RecipeCollection, RecipeDetail } from "~/types/recipe";

function useApiBase(): string {
  const config = useRuntimeConfig();
  return import.meta.server ? config.apiBase : config.public.apiBase;
}

export function useRecipes() {
  const apiBase = useApiBase();
  return useAsyncData<RecipeCollection>("recipe-catalog", () =>
    $fetch(`${apiBase}/api/recipes`, { query: { limit: 20 } }),
  );
}

export function useRecipe(slug: string) {
  const apiBase = useApiBase();
  return useAsyncData<RecipeDetail>(`recipe-${slug}`, () =>
    $fetch(`${apiBase}/api/recipes/${encodeURIComponent(slug)}`),
  );
}
