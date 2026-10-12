import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { caseEvidence, categoryRows, currentParserLabel, draftChanges, evidenceMatch, experimentConfirmMessage, experimentGates, experimentHeadline, presetBreakdown, spendsOpenAI } from "../app/lib/ops-experiments";
import type { OpsEvaluation, OpsExperiment, OpsRuntimeSetting } from "../app/types/ops";

const run = (evaluation: string, metrics: Record<string, unknown>, extra: Partial<OpsExperiment> = {}) => ({
  id: 1, evaluation, label: null, status: "succeeded", configuration: {}, metrics, passed: null, conditions: {}, error: null, created_at: "", duration_seconds: 1, ...extra,
}) as OpsExperiment;

describe("experiments page", () => {
  it("heads each run with its outcome, never the fixture size", () => {
    expect(experimentHeadline(run("developer-planning", { scenario_count: 20, scenario_expectation_rate: 1, failure_case_count: 18 }))).toBe("2 of 20 scenarios passed");
    expect(experimentHeadline(run("agent-benchmark", { case_count: 24, exact_case_rate: 0.7083, failure_case_count: 7 }))).toBe("17 of 24 messages read exactly");
    expect(experimentHeadline(run("planning-components", { case_count: 6, condition_run_count: 20, passed_audit_count: 10 }))).toBe("10 of 20 condition runs passed the audit");
    expect(experimentHeadline(run("planning-final-gate", { case_count: 5, gate_selected_count: 3 }))).toBe("3 of 5 cases got a valid week through the gate");
    expect(experimentHeadline(run("planning-components", {}))).toBe("—");
  });

  it("says a worker run's conditions are incomplete when the server says so", () => {
    expect(experimentGates(run("planning-components", {}, { conditions: { conditions_complete: true } }))).toBe("Conditions recorded");
    expect(experimentGates(run("planning-components", {}, { conditions: { conditions_complete: false } }))).toBe("Conditions incomplete");
    expect(experimentGates(run("developer-planning", {}, { passed: false }))).toBe("Not passed");
    expect(experimentGates(run("planning-components", {}, { status: "running" }))).toBe("—");
  });

  it("names a missing A/B value instead of calling it different", () => {
    const row = (a: unknown, b: unknown, matches: boolean) => ({ key: "code_commit", a, b, delta: null, matches });
    expect(evidenceMatch(row(null, null, false))).toBe("Missing in both");
    expect(evidenceMatch(row(null, "abc", false))).toBe("Missing in A");
    expect(evidenceMatch(row("abc", null, false))).toBe("Missing in B");
    expect(evidenceMatch(row("abc", "def", false))).toBe("Different");
    // The seed: both unset is the same unseeded run.
    expect(evidenceMatch(row(null, null, true))).toBe("Same");
  });

  it("names the parser switch's value and warns before a paid run", () => {
    const benchmark = { name: "agent-benchmark", label: "Assistant benchmark", dataset: "data/evaluation/agent/fixture-v1.json", description: "", options: {}, execution_mode: "legacy_inline" } as OpsEvaluation;
    expect(currentParserLabel("openai")).toBe("Current switch (OpenAI model, paid)");
    expect(currentParserLabel("fixture")).toBe("Current switch (rule-based fixture)");
    expect(currentParserLabel(undefined)).toBe("Current switch (not loaded)");
    expect(experimentConfirmMessage(benchmark, "openai")).toContain("paid OpenAI model twice for every message");
    expect(experimentConfirmMessage(benchmark, undefined)).toContain("may call the paid OpenAI model");
    expect(experimentConfirmMessage(benchmark, "fixture")).not.toContain("OpenAI");
    expect(experimentConfirmMessage(benchmark, "fixture")).toContain("cannot replace an earlier result");
    expect([spendsOpenAI("agent-benchmark", "openai"), spendsOpenAI("agent-benchmark", "fixture"), spendsOpenAI("developer-planning", "openai")]).toEqual([true, false, false]);
  });

  it("offers a number switch's change only for a new finite value", () => {
    const width = { key: "beam_width", choices: null, value: 32 } as OpsRuntimeSetting;
    // v-model on a number input holds a number once typed.
    expect([draftChanges(width, 32), draftChanges(width, "32"), draftChanges(width, "32.0")]).toEqual([false, false, false]);
    expect([draftChanges(width, 64), draftChanges(width, ""), draftChanges(width, "1e999")]).toEqual([true, false, false]);
    const parser = { key: "agent_parser_provider", choices: ["fixture", "openai"], value: "fixture" } as OpsRuntimeSetting;
    expect([draftChanges(parser, "fixture"), draftChanges(parser, "openai")]).toEqual([false, true]);
  });

  it("shows a failing message with what was expected and what came back", () => {
    const failing = { case_id: "agent-007", status: "failed", category: "pantry", message: "I have 2 eggs", expected_extraction: { a: 1 }, actual_extraction: { a: 2 }, failure_reasons: ["extraction_mismatch"], failures: [{ code: "extraction_mismatch" }] };
    expect(caseEvidence(failing)).toEqual({ message: "I have 2 eggs", expected_extraction: { a: 1 }, actual_extraction: { a: 2 }, failure_reasons: ["extraction_mismatch"] });
    expect(caseEvidence({ case_id: "budget-edge", preset: "beam", failures: [] })).toBeNull();
    expect(categoryRows({ category_metrics: { pantry: { case_count: 3, failure_case_count: 1 }, budget: { scenario_count: 2, failure_case_count: 0 } } })).toEqual([
      { category: "pantry", cases: 3, failed: 1 },
      { category: "budget", cases: 2, failed: 0 },
    ]);
    expect(categoryRows(null)).toEqual([]);
  });

  it("breaks a component ablation down by case and preset", () => {
    const passed = { status: "feasible", audit: { status: "passed" }, failures: [] };
    const over = { status: "feasible", audit: { status: "failed" }, failures: [{ code: "weekly_budget" }] };
    const report = {
      presets: ["beam", "greedy", "variety_off"],
      runs: [
        { case_id: "budget-edge", preset: "beam", repeat: 0, ...passed },
        { case_id: "budget-edge", preset: "beam", repeat: 1, ...over },
        { case_id: "budget-edge", preset: "greedy", repeat: 0, ...over },
        { case_id: "budget-edge", preset: "variety_off", status: "not_applicable", reason: "No active explicit weight to remove" },
        { case_id: "no-week", preset: "beam", repeat: 0, status: "infeasible", audit: { status: "failed" }, failures: [{ code: "slot_unfilled" }] },
      ],
    };
    expect(presetBreakdown(report)).toEqual({
      presets: ["beam", "greedy", "variety_off"],
      rows: [
        { caseId: "budget-edge", cells: ["1 of 2 passed: weekly_budget", "Failed: weekly_budget", "Not applicable"] },
        { caseId: "no-week", cells: ["Failed (Infeasible): slot_unfilled", "—", "—"] },
      ],
    });
    // A gate or inline report has no presets.
    expect(presetBreakdown({ runs: [{ case_id: "dev-001", status: "passed" }] })).toBeNull();
    expect(presetBreakdown(null)).toBeNull();
  });

  it("styles its evidence drawer as an overlay and does not claim every switch reaches requests", () => {
    const source = readFileSync(new URL("../app/pages/ops/experiments.vue", import.meta.url), "utf8");
    const style = source.slice(source.indexOf("<style scoped>"));
    // Scoped styles of tasks.vue and users.vue never reach this page; it needs its own.
    expect(style).toMatch(/\.drawer-scrim \{[^}]*position: fixed/);
    expect(style).toMatch(/\.drawer \{[^}]*overflow-y: auto/);
    expect(source).not.toContain("and new requests pick it up");
    expect(source).toContain("Only switches marked “Used by the product” reach new requests");
  });
});
