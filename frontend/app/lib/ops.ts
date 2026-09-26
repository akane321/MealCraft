import type { OpsDayPoint, OpsReplayDish, OpsTaskKind } from "~/types/ops";

// Every system role the backend lets into /api/ops; ADR-0047 gives them all the same console.
const CONSOLE_ROLES = new Set(["admin", "operator", "data_reviewer"]);

export function isConsoleAccount(actor: { user: { system_role: string } } | null | undefined) {
  return Boolean(actor && CONSOLE_ROLES.has(actor.user.system_role));
}

export interface OpsModule {
  slug: string;
  label: string;
  path: string;
  blurb: string;
  ready: boolean;
}

export const OPS_MODULES: OpsModule[] = [
  { slug: "overview", label: "Overview", path: "/ops", blurb: "Conversations, plans, failures and latency over the last two weeks.", ready: true },
  { slug: "tasks", label: "Tasks", path: "/ops/tasks", blurb: "Every conversation and planning run with what it stored.", ready: true },
  { slug: "debugging", label: "Debugging", path: "/ops/debugging", blurb: "Replay one task through the current code or other settings and compare the two results side by side.", ready: true },
  { slug: "services", label: "Services", path: "/ops/services", blurb: "OpenAI, FairPrice and YouTube: configuration, recent failures and a live check.", ready: true },
  { slug: "data", label: "Data", path: "/ops/data", blurb: "Browse and edit recipes, ingredients and product mappings.", ready: false },
  { slug: "experiments", label: "Experiments & config", path: "/ops/experiments", blurb: "Runtime switches, evaluation runs and A/B comparisons of two configurations.", ready: true },
  { slug: "users", label: "Users", path: "/ops/users", blurb: "Accounts, households, profiles, conversations and plans.", ready: true },
];

const GOOD = new Set(["succeeded", "committed", "preview_ready"]);
const BAD = new Set(["failed"]);
const WARN = new Set(["degraded", "cancelled", "needs_clarification"]);

/** One colour per status family, so every chart and badge reads the same way. */
export function statusColor(status: string) {
  if (GOOD.has(status)) return "var(--sage)";
  if (BAD.has(status)) return "var(--danger)";
  if (WARN.has(status)) return "#d9a55a";
  if (status === "running" || status === "queued") return "var(--accent)";
  return "var(--t3)";
}

/** Statuses seen in a window, good ones first, so stacked bars keep a stable order. */
export function statusesIn(days: OpsDayPoint[], pick: (day: OpsDayPoint) => Record<string, number>) {
  const rank = (status: string) => (GOOD.has(status) ? 0 : WARN.has(status) ? 2 : BAD.has(status) ? 3 : 1);
  const seen = new Set(days.flatMap(day => Object.keys(pick(day))));
  return [...seen].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** A round axis maximum at or above the largest value (1, 2, 5 × 10ⁿ). */
export function niceMax(value: number) {
  if (!(value > 0)) return 1;
  const power = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 5, 10].find(multiple => multiple * power >= value) ?? 10;
  return step * power;
}

/** An SVG path through the points; a missing value breaks the line rather than dropping to zero. */
export function linePath(values: Array<number | null>, max: number, width: number, height: number) {
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  let path = "";
  let drawing = false;
  values.forEach((value, index) => {
    if (value === null) {
      drawing = false;
      return;
    }
    const x = +(index * step).toFixed(1);
    const y = +(height - (value / max) * height).toFixed(1);
    path += `${drawing ? "L" : "M"}${x} ${y}`;
    drawing = true;
  });
  return path;
}

export function formatSeconds(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export function formatWhen(value: string | null | undefined) {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-SG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** "requested_pricing_mode" → "Requested pricing mode". */
export function humanKey(key: string) {
  const words = key.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The drawer's query value, "planning-12", split back into its kind and id. */
export function parseTaskKey(value: unknown): { kind: OpsTaskKind; id: number } | null {
  const match = typeof value === "string" ? /^(agent|planning)-(\d+)$/.exec(value) : null;
  return match ? { kind: match[1] as OpsTaskKind, id: Number(match[2]) } : null;
}

// --- Slice 2: replay diffs, A/B metric comparison and value display. ---

/** A stored value as plain text: "—" for nothing, lists joined, objects as compact JSON. */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join(", ") : "none";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export interface FieldDiff { key: string; before: unknown; after: unknown; changed: boolean }

/** Every field of either side, changed ones first, so a replay's differences are read first. */
export function diffFields(before: Record<string, unknown> | null | undefined, after: Record<string, unknown> | null | undefined): FieldDiff[] {
  const keys = [...new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})])].sort();
  return keys
    .map(key => ({ key, before: before?.[key], after: after?.[key], changed: !same(before?.[key], after?.[key]) }))
    .sort((a, b) => Number(b.changed) - Number(a.changed));
}

export interface DishRow { slot: string; day: number | null; before: string | null; after: string | null; changed: boolean }

/** The two weeks dish by dish, matched on day, meal and role. */
export function dishRows(before: OpsReplayDish[] = [], after: OpsReplayDish[] = []): DishRow[] {
  const key = (dish: OpsReplayDish) => `${dish.day ?? "?"}|${dish.meal}|${dish.role}`;
  const rows = new Map<string, DishRow>();
  for (const [side, dishes] of [["before", before], ["after", after]] as const) {
    for (const dish of dishes) {
      const row = rows.get(key(dish)) ?? {
        slot: `Day ${dish.day ?? "?"} ${dish.meal}${dish.role === "main" ? "" : ` (${dish.role})`}`,
        day: dish.day,
        before: null,
        after: null,
        changed: false,
      };
      row[side] = dish.recipe;
      rows.set(key(dish), row);
    }
  }
  return [...rows.values()]
    .map(row => ({ ...row, changed: row.before !== row.after }))
    .sort((a, b) => (a.day ?? 99) - (b.day ?? 99) || a.slot.localeCompare(b.slot));
}

export interface MetricRow { metric: string; a: unknown; b: unknown; delta: number | null }

/** Run A against run B metric by metric; the difference is B minus A where both are numbers. */
export function compareMetrics(a: Record<string, unknown>, b: Record<string, unknown>): MetricRow[] {
  const metrics = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort();
  return metrics.map((metric) => {
    const left = a[metric];
    const right = b[metric];
    const delta = typeof left === "number" && typeof right === "number" ? Math.round((right - left) * 10_000) / 10_000 : null;
    return { metric, a: left, b: right, delta };
  });
}
