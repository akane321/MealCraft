import type { PricingMode, ProductSearchResponse } from "~/types/recommendation";

export function useProductSearch() {
  const config = useRuntimeConfig();
  const result = ref<ProductSearchResponse | null>(null);
  const errorMessage = ref<string | null>(null);
  const isSearching = ref(false);

  async function search(query: string, mode: PricingMode, refresh = false) {
    isSearching.value = true;
    errorMessage.value = null;

    try {
      result.value = await $fetch<ProductSearchResponse>(
        `${config.public.apiBase}/api/products/search`,
        { query: { q: query, live: mode === "live", refresh, limit: 12 } },
      );
    }
    catch {
      errorMessage.value = "Product search failed. Check the backend connection and try again.";
    }
    finally {
      isSearching.value = false;
    }
  }

  return { errorMessage, isSearching, result, search };
}
