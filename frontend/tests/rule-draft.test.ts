import { describe, expect, it } from "vitest";

import { addRules, failed, IDLE, LOADING, received, removeRule } from "../app/lib/rule-draft";
import type { CookingTimeRule, PresenceRule } from "../app/types/household";

const lunchAway: PresenceRule = {
  source_text: "孩子工作日午饭在学校吃",
  restatement: "Monday to Friday, lunch: Mei eats elsewhere.",
  member_name: "Mei",
  present: false,
  weekdays: ["monday", "tuesday", "wednesday", "thursday", "friday"],
  meal_types: ["lunch"],
};
const quickDinner: CookingTimeRule = {
  source_text: "weekday dinners within 30 minutes",
  restatement: "Monday to Friday, dinner: within 30 minutes.",
  weekdays: ["monday", "tuesday", "wednesday", "thursday", "friday"],
  meal_types: ["dinner"],
  max_minutes: 30,
};

describe("a sentence on its way to rules", () => {
  it("starts idle and reads while loading", () => {
    expect(IDLE.status).toBe("idle");
    expect(LOADING.status).toBe("loading");
  });

  it("asks the household to confirm what was understood", () => {
    expect(received({ rules: [lunchAway], issues: [], provider: "rules", fell_back: true })).toEqual({
      status: "confirm",
      rules: [lunchAway],
      fellBack: true,
    });
  });

  it("offers nothing to confirm when the sentence was not read in full", () => {
    const issue = "Couldn't tell whether they're home or away";
    expect(received({ rules: [lunchAway], issues: [issue], provider: "openai", fell_back: false })).toEqual({ status: "error", issues: [issue] });
    expect(received({ rules: [], issues: [], provider: "rules", fell_back: false }).status).toBe("error");
  });

  it("shows a failed request as its reason", () => {
    expect(failed("Network down")).toEqual({ status: "error", issues: ["Network down"] });
  });

  it("adds confirmed rules once and removes one by position", () => {
    const saved = addRules([lunchAway], [lunchAway, { ...lunchAway, member_name: "Wei", restatement: "Monday to Friday, lunch: Wei eats elsewhere." }]);
    expect(saved.map(rule => rule.member_name)).toEqual(["Mei", "Wei"]);
    expect(removeRule(saved, 0).map(rule => rule.member_name)).toEqual(["Wei"]);
    expect(addRules<CookingTimeRule>([], [quickDinner])).toEqual([quickDinner]);
  });
});
