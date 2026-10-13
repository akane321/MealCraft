export interface HealthResponse {
  status: string;
  service: string;
  database: string;
  // The date the product plans from, and the simulated now when one is set (backend app/core/clock.py).
  today?: string;
  simulated_today?: string | null;
}

export interface AppInfoResponse {
  name: string;
  version: string;
  environment: string;
}

export interface BackendSystemStatus {
  health: HealthResponse;
  info: AppInfoResponse;
}
