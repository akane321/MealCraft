export type OpsDataQualityStatus = "available" | "degraded";

export interface OpsDataQualityIssue {
  artifact: string;
  code: string;
  detail: string;
}

export interface OpsDataQualityArtifact {
  name: string;
  sha256: string;
  size_bytes: number;
  updated_at: string;
}

export interface OpsDataQualitySummary {
  status: OpsDataQualityStatus;
  release_version: string;
  schema_version: string | null;
  generated_at: string | null;
  coverage: {
    released_recipes: number;
    enrichment_set: number;
    released_ingredients: number;
    recipes_with_every_field: number;
  } | null;
  by_cuisine: Record<string, number> | null;
  by_course: Record<string, number> | null;
  by_source: Record<string, number> | null;
  estimated_share: {
    servings: number;
    times: number;
    ingredient_amounts: number;
  } | null;
  nutrition: {
    complete_recipes: number;
    total_recipes: number;
    median_energy_kcal: number | null;
  } | null;
  dropped_by_reason: Record<string, number> | null;
  allergen_rules_pending_human: number | null;
  artifacts: OpsDataQualityArtifact[];
  issues: OpsDataQualityIssue[];
}

export interface OpsDroppedCandidate {
  candidate_id: string;
  title: string;
  reason: string;
}

export interface OpsDroppedCandidateCollection {
  status: OpsDataQualityStatus;
  release_version: string;
  items: OpsDroppedCandidate[];
  total: number | null;
  offset: number;
  limit: number;
  next_offset: number | null;
  skipped_records: number;
  artifact: OpsDataQualityArtifact | null;
  issues: OpsDataQualityIssue[];
}
