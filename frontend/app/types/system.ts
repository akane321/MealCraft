export interface HealthResponse {
  status: string;
  service: string;
  database: string;
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
