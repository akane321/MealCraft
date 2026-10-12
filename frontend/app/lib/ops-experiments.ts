import { humanKey } from "./ops";
import type { OpsEvaluation, OpsExperiment, OpsExperimentComparisonRow, OpsRuntimeSetting } from "~/types/ops";

const count = (value: unknown) => (typeof value === "number" ? value : Number.NaN);

// Each evaluation's outcome: how many passed, out of which total. Never a fixture size on its own.
const OUTCOMES: Record<string, [passed: (metrics: Record<string, unknown>) => number, total: string, noun: string]> = {
  "developer-planning": [m => count(m.scenario_count) - count(m.failure_case_count), "scenario_count", "scenarios passed"],
  "agent-benchmark": [m => count(m.case_count) - count(m.failure_case_count), "case_count", "messages read exactly"],
  "planning-components": [m => count(m.passed_audit_count), "condition_run_count", "condition runs passed the audit"],
  "planning-final-gate": [m => count(m.gate_selected_count), "case_count", "cases got a valid week through the gate"],
  "planning-final-gate-composed": [m => count(m.gate_selected_count), "case_count", "cases got a valid week through the gate"],
};

/** "18 of 20 scenarios passed": a run's outcome in the Results table. */
export function experimentHeadline(run: OpsExperiment) {
  const outcome = OUTCOMES[run.evaluation];
  if (!outcome) return "—";
  const [passed, totalKey, noun] = outcome;
  const value = passed(run.metrics);
  if (Number.isNaN(value)) return "—";
  const total = run.metrics[totalKey];
  return typeof total === "number" ? `${value} of ${total} ${noun}` : `${value} ${noun}`;
}

/** The Gates column: a gated run's verdict, else whether the server finds its conditions complete. */
export function experimentGates(run: OpsExperiment) {
  if (run.passed !== null) return run.passed ? "Passed" : "Not passed";
  if (run.conditions.conditions_complete === true) return "Conditions recorded";
  return run.status === "succeeded" ? "Conditions incomplete" : "—";
}

const absent = (value: unknown) => value === null || value === undefined;

/** An A/B evidence row: "Same", "Different", or which side recorded nothing. */
export function evidenceMatch(row: OpsExperimentComparisonRow) {
  if (row.matches) return "Same";
  if (absent(row.a) && absent(row.b)) return "Missing in both";
  if (absent(row.a)) return "Missing in A";
  return absent(row.b) ? "Missing in B" : "Different";
}

const PARSERS: Record<string, string> = { fixture: "rule-based fixture", openai: "OpenAI model, paid" };

/** The Parser option that leaves the switch as it is, naming what the switch is set to. */
export function currentParserLabel(value: unknown) {
  return `Current switch (${typeof value === "string" ? PARSERS[value] ?? value : "not loaded"})`;
}

/** Whether this run may call the paid OpenAI model; an unread switch may be set to it. */
export function spendsOpenAI(evaluation: string, parser: unknown) {
  return evaluation === "agent-benchmark" && parser !== "fixture";
}

/** Only a durable-worker run waits in a queue; the others start in the request or in a background thread. */
export const queuesRun = (evaluation: OpsEvaluation) => evaluation.execution_mode === "durable_worker";

/** How the run executes, for the chip: the API calls every non-worker run "legacy_inline", but the paid OpenAI benchmark runs in the background. */
export function experimentExecution(evaluation: OpsEvaluation, parser: unknown) {
  if (queuesRun(evaluation)) return "Durable worker";
  return evaluation.name === "agent-benchmark" && parser === "openai" ? "Runs in the background" : "Legacy inline";
}

/** The confirmation before an evaluation starts; `parser` is the one the run will use. */
export function experimentConfirmMessage(evaluation: OpsEvaluation, parser: unknown) {
  const message = `${queuesRun(evaluation) ? "Queue" : "Run"} ${evaluation.label} on ${evaluation.dataset}. The run records its parameters, the data hashes and the code revision where the server knows it, and cannot replace an earlier result.`;
  if (!spendsOpenAI(evaluation.name, parser)) return message;
  return parser === "openai"
    ? `${message} It calls the paid OpenAI model twice for every message (it reads each message, then runs the assistant on it) and runs in the background.`
    : `${message} The parser switch couldn't be read, so it may call the paid OpenAI model.`;
}

/** Whether a switch's draft is a new, valid value. A number input's v-model holds a number after a keystroke. */
export function draftChanges(setting: OpsRuntimeSetting, draft: unknown) {
  if (setting.choices) return draft !== setting.value;
  const text = String(draft ?? "").trim();
  const value = Number(text);
  return text !== "" && Number.isFinite(value) && value !== setting.value;
}

const CASE_KEYS = [
  "message",
  "name",
  "expected_extraction",
  "actual_extraction",
  "mismatched_fields",
  "hallucinated_fields",
  "expected_missing_fields",
  "actual_missing_fields",
  "medical_boundary_match",
  "expected_feasible",
  "actual_feasible",
  "selected_slugs",
  "hard_constraint_violations",
  "failure_reasons",
];

/** An inline run's case as what was asked, expected and returned; null for a worker's row, which is shown whole. */
export function caseEvidence(row: Record<string, unknown>) {
  if (!("message" in row) && !("name" in row)) return null;
  return Object.fromEntries(CASE_KEYS.filter(key => key in row).map(key => [key, row[key]]));
}

type Row = Record<string, unknown>;

/** What one preset did on one case: the audit verdict over its repeats and the hard failures it hit. */
function presetOutcome(rows: Row[]) {
  if (!rows.length) return "—";
  if (rows.every(row => row.status === "not_applicable")) return "Not applicable";
  const verdicts = rows.map(row => String((row.audit as Row | null | undefined)?.status ?? row.status));
  const passed = verdicts.filter(verdict => verdict === "passed").length;
  const verdict = rows.length === 1 ? humanKey(verdicts[0]!) : `${passed} of ${rows.length} passed`;
  // The search's own answer when it found no feasible week, e.g. infeasible.
  const unsolved = [...new Set(rows.map(row => row.status).filter(status => status !== "feasible"))].map(String);
  const codes = [...new Set(rows.flatMap(row => (Array.isArray(row.failures) ? row.failures.map(failure => String((failure as Row).code)) : [])))];
  return `${verdict}${unsolved.length ? ` (${unsolved.map(humanKey).join(", ")})` : ""}${codes.length ? `: ${codes.join(", ")}` : ""}`;
}

/** A component ablation's report as case × preset (beam, greedy, variety_off, overlap_off, repair_off); null for any other report. */
export function presetBreakdown(report: Row | null) {
  const presets = Array.isArray(report?.presets) ? report.presets.map(String) : [];
  if (!presets.length || !Array.isArray(report?.runs)) return null;
  const cases = new Map<string, Record<string, Row[]>>();
  for (const row of report.runs as Row[]) {
    if (!row || typeof row.case_id !== "string" || typeof row.preset !== "string") continue;
    const byPreset = cases.get(row.case_id) ?? {};
    (byPreset[row.preset] ??= []).push(row);
    cases.set(row.case_id, byPreset);
  }
  return { presets, rows: [...cases].map(([caseId, byPreset]) => ({ caseId, cells: presets.map(preset => presetOutcome(byPreset[preset] ?? [])) })) };
}

/** A stored report's per-category counts: cases and failed cases. */
export function categoryRows(report: Record<string, unknown> | null) {
  const categories = report?.category_metrics;
  if (!categories || typeof categories !== "object") return [];
  return Object.entries(categories as Record<string, Record<string, unknown>>).map(([category, counts]) => ({
    category,
    cases: counts.case_count ?? counts.scenario_count,
    failed: counts.failure_case_count,
  }));
}
