import type { AppInfoResponse, BackendSystemStatus, HealthResponse } from "~/types/system";

export function useBackendStatus() {
  const config = useRuntimeConfig();
  const apiBase = import.meta.server ? config.apiBase : config.public.apiBase;

  return useAsyncData<BackendSystemStatus>("backend-system-status", async () => {
    const [health, info] = await Promise.all([
      $fetch<HealthResponse>(`${apiBase}/api/health`),
      $fetch<AppInfoResponse>(`${apiBase}/api/info`),
    ]);

    return { health, info };
  });
}
