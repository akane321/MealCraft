import type { HealthResponse } from "~/types/system";

export interface ServiceStatus {
  name: string;
  state: "Ready" | "Connected" | "Unavailable";
  healthy: boolean;
}

export function createServiceStatuses(health?: HealthResponse): ServiceStatus[] {
  const backendHealthy = health?.status === "ok";
  const databaseHealthy = health?.database === "connected";

  return [
    { name: "Frontend", state: "Ready", healthy: true },
    {
      name: "Backend API",
      state: backendHealthy ? "Connected" : "Unavailable",
      healthy: backendHealthy,
    },
    {
      name: "PostgreSQL",
      state: databaseHealthy ? "Connected" : "Unavailable",
      healthy: databaseHealthy,
    },
  ];
}
