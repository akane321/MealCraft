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

// --- Slice 2: Debugging, Experiments & configuration, Users. ---

export interface OpsReplayDish { day: number | null; meal: string; role: string; recipe: string }

/** One side of a replay. Planning fills the first group of fields, an assistant turn the second. */
export interface OpsReplayOutcome {
  status: string;
  evidence?: string | null;
  message?: string | null;
  dishes?: OpsReplayDish[];
  total_cost_sgd?: number | null;
  failed_checks?: Array<{ code: string; status: string }>;
  settings?: Record<string, unknown>;
  constraints?: Record<string, unknown>;
  assistant_message?: string;
  missing_fields?: string[];
  parser?: string | null;
  error?: string | null;
  duration_seconds?: number | null;
}

export interface OpsReplay {
  id: number;
  kind: OpsTaskKind;
  source_id: number;
  overrides: Record<string, unknown>;
  original: OpsReplayOutcome | null;
  replay: OpsReplayOutcome;
  triggered_by_user_id: number | null;
  created_at: string;
}

export interface OpsReplaySummary {
  id: number;
  kind: OpsTaskKind;
  source_id: number;
  overrides: Record<string, unknown>;
  original_status: string | null;
  replay_status: string | null;
  created_at: string;
}

export interface OpsRuntimeSetting {
  key: string;
  label: string;
  meaning: string;
  choices: string[] | null;
  minimum: number | null;
  maximum: number | null;
  integer: boolean;
  default: unknown;
  value: unknown;
  overridden: boolean;
  wired: boolean;
  updated_at: string | null;
}

export interface OpsSettingChange { key: string; before: unknown; after: unknown; actor: string | null; created_at: string }

export type OpsEvaluationName = "developer-planning" | "agent-benchmark";

export interface OpsEvaluation { name: OpsEvaluationName; label: string; description: string; dataset: string; options: Record<string, string[]> }

export interface OpsExperiment {
  id: number;
  evaluation: OpsEvaluationName;
  label: string | null;
  status: string;
  configuration: Record<string, unknown>;
  metrics: Record<string, unknown>;
  passed: boolean | null;
  conditions: Record<string, unknown>;
  error: string | null;
  created_at: string;
  duration_seconds: number | null;
}

export interface OpsUserHousehold { id: number; name: string; role: string; members: number; profile: Record<string, unknown> | null }

export interface OpsUser {
  id: number;
  email: string;
  display_name: string;
  system_role: string;
  status: string;
  households: OpsUserHousehold[];
  conversations: number;
  plans: number;
  last_seen_at: string | null;
  created_at: string;
}

export interface OpsUserDetail extends OpsUser {
  recent_conversations: Array<{ id: number; status: string; messages: number; first_message: string | null; created_at: string }>;
  recent_plans: Array<{ id: number; start_date: string; total_sgd: number; household_size: number; created_at: string }>;
}

export interface OpsServiceCheck {
  name: OpsServiceName;
  ok: boolean;
  latency_ms: number;
  error_kind: string | null;
  detail: string;
  checked_at: string;
}
