import type { HouseholdRule, RuleParseResult } from "~/types/household";

/**
 * One household sentence on its way to saved rules: read it, show what was understood, and only then add it.
 * idle -> loading -> confirm | error -> idle. Drafts are never sent with the profile until the household adds them.
 */
export type RuleDraft
  = | { status: "idle" }
    | { status: "loading" }
    | { status: "confirm"; rules: HouseholdRule[]; fellBack: boolean }
    | { status: "error"; issues: string[] };

export const IDLE: RuleDraft = { status: "idle" };
export const LOADING: RuleDraft = { status: "loading" };

/** The reader's answer: something to confirm, or why there is nothing to confirm. */
export function received(result: RuleParseResult): RuleDraft {
  if (result.issues.length) return { status: "error", issues: result.issues };
  if (!result.rules.length) return { status: "error", issues: ["No rule was found in that sentence. Name who, which days and which meal."] };
  return { status: "confirm", rules: result.rules, fellBack: result.fell_back };
}

export function failed(message: string): RuleDraft {
  return { status: "error", issues: [message] };
}

/** The confirmed drafts after the saved rules; a rule already there (same restatement) is not added twice. */
export function addRules<T extends HouseholdRule>(saved: T[], drafts: T[]): T[] {
  const seen = new Set(saved.map(rule => rule.restatement));
  return [...saved, ...drafts.filter(rule => !seen.has(rule.restatement))];
}

export function removeRule<T>(saved: T[], index: number): T[] {
  return saved.filter((_, position) => position !== index);
}
