export interface QualityDistributionRow {
  label: string;
  count: number;
  share: number;
}

export function qualityPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const percent = Math.round(value * 1000) / 10;
  return `${percent.toFixed(Number.isInteger(percent) ? 0 : 1)}%`;
}

export function qualityDistribution(values: Record<string, number> | null | undefined): QualityDistributionRow[] {
  if (!values) return [];
  const total = Object.values(values).reduce((sum, count) => sum + count, 0);
  return Object.entries(values)
    .map(([label, count]) => ({ label, count, share: total ? count / total : 0 }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

export function qualityPageLabel(offset: number, count: number, total: number | null) {
  if (total === null) return "Total unavailable";
  if (total === 0) return "No records";
  return `${offset + 1}–${offset + count} of ${total}`;
}

export function shortQualityDigest(digest: string) {
  return digest.length > 12 ? `${digest.slice(0, 12)}…` : digest;
}

export function qualityBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
