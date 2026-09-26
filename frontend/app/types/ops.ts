// Shapes of the /api/ops console endpoints (ADR-0047).

export interface OpsOverview {
  app_version: string;
  generated_at: string;
  latest_recorded_versions: { code_commit: string | null; catalog_version: string | null; product_snapshot_version: string | null };
  runs: { queued: number; running: number; failures_last_24_hours: Record<string, number>; provider_modes_last_24_hours: Record<string, number> };
}

export interface OpsDayPoint {
  day: string;
  agent_sessions: number;
  agent_runs: Record<string, number>;
  planning_runs: Record<string, number>;
  planning_median_seconds: number | null;
  planning_p90_seconds: number | null;
}

export interface OpsSeries {
  days: OpsDayPoint[];
  provider_modes: Record<string, number>;
}

export type OpsTaskKind = "agent" | "planning";

export interface OpsTaskSummary {
  kind: OpsTaskKind;
  id: number;
  label: string;
  status: string;
  error_code: string | null;
  provider_mode: string | null;
  created_at: string;
  duration_seconds: number | null;
}

export interface OpsTaskCollection {
  items: OpsTaskSummary[];
  total: number;
}

export interface OpsTaskDetail {
  summary: OpsTaskSummary;
  inputs: Record<string, unknown> | null;
  trace: Record<string, unknown> | null;
  validation: unknown;
  evidence: Record<string, unknown>;
  model_configuration: Record<string, unknown> | null;
  timings: Record<string, unknown>;
  error_detail: string | null;
  warnings: unknown[];
}

export type OpsServiceName = "openai" | "fairprice" | "youtube";

export interface OpsServiceStatus {
  name: OpsServiceName;
  label: string;
  configured: boolean;
  mode: string;
  recent: { window_days: number; calls: number; failures: number; fallbacks: number } | null;
  note: string | null;
}

export interface OpsServiceCheck {
  name: OpsServiceName;
  ok: boolean;
  latency_ms: number;
  error_kind: string | null;
  detail: string;
  checked_at: string;
}
