import { expect, test, type Page, type Route } from "@playwright/test";

// The experiments page against stubbed APIs: the case-changes table at desktop widths, and the run form's
// execution chip, wording and double-click guard.
const SHOTS = process.env.OPS_CONSOLE_SHOTS;

const admin = {
  user: { id: 7, normalized_email: "ops@example.test", display_name: "Ops Lead", locale: "en-SG", timezone: "Asia/Singapore", status: "active", system_role: "admin", email_verified_at: null, created_at: "2026-09-20T08:00:00Z" },
  active_household_id: null,
  household_role: null,
};

const evaluations = [
  { name: "planning-components", label: "Planning component ablations", description: "Fixed developer component conditions.", dataset: "data/fixtures/planning-v2/ablation-developer-v1.json", options: {}, execution_mode: "durable_worker" },
  { name: "developer-planning", label: "Developer planning set", description: "Protocol v1: 20 weeks of one dish a dinner.", dataset: "data/evaluation/dev/planning-v1.json", options: { planner: ["product-planner", "greedy-baseline", "rule-only-baseline"] }, execution_mode: "legacy_inline" },
  { name: "agent-benchmark", label: "Assistant benchmark", description: "Twenty-four messages read by the parser.", dataset: "data/evaluation/agent/fixture-v1.json", options: {}, execution_mode: "legacy_inline" },
];

const run = (id: number, label: string) => ({
  id,
  evaluation: "developer-planning",
  label,
  status: "succeeded",
  configuration: { planner: "product-planner" },
  metrics: { scenario_count: 20, failure_case_count: 0 },
  passed: null,
  conditions: { conditions_complete: true },
  error: null,
  created_at: "2026-10-12T08:00:00Z",
  duration_seconds: 0.4,
});

// What a real developer-planning pair returns: long failure codes and several to a case.
const caseDifferences = [
  { case_id: "dev-001", condition: "", a_status: "passed", b_status: "failed", failures_gained: ["consecutive_recipe_repetition"], failures_lost: [] },
  { case_id: "dev-002", condition: "", a_status: "passed", b_status: "failed", failures_gained: ["consecutive_recipe_repetition", "hard_constraint_violation"], failures_lost: [] },
  { case_id: "budget-edge", condition: "repair_off repeat 0", a_status: "failed", b_status: "passed", failures_gained: [], failures_lost: ["purchase_budget", "required_slot", "shopping_list"] },
];

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const path = (pathname: string) => (url: URL) => url.pathname === pathname;

async function stubExperiments(page: Page, onPost: () => Promise<void> = async () => {}) {
  const runs = [run(82, "second"), run(81, "first")];
  await page.route(path("/api/auth/me"), route => route.fulfill(json(admin)));
  await page.route(path("/api/ops/config"), route => route.fulfill(json({ items: [
    { key: "agent_parser_provider", label: "Assistant parser", meaning: "How the assistant reads a message.", choices: ["fixture", "openai"], minimum: null, maximum: null, integer: false, default: "fixture", value: "fixture", overridden: false, wired: true, updated_at: null },
  ] })));
  await page.route(path("/api/ops/config/history"), route => route.fulfill(json({ items: [] })));
  await page.route(path("/api/ops/experiments"), async (route: Route) => {
    if (route.request().method() === "POST") {
      await onPost();
      const made = run(83, "new");
      runs.unshift(made);
      return route.fulfill(json(made, 201));
    }
    return route.fulfill(json({ items: runs, evaluations }));
  });
  await page.route(path("/api/ops/experiments/compare"), route => route.fulfill(json({
    runs: [runs[1], runs[0]],
    compatible: true,
    reasons: [],
    evidence: [{ key: "code_commit", a: "50674b3", b: "50674b3", delta: null, matches: true }],
    configurations: [{ key: "planner", a: "product-planner", b: "greedy-baseline", delta: null, matches: false }],
    metrics: [{ key: "failure_case_count", a: 0, b: 3, delta: 3, matches: false }],
    failure_mechanisms: [],
    case_differences: caseDifferences,
    claim_scope: "developer_diagnostic_only",
  })));
}

for (const [width, height] of [[1280, 720], [1440, 900]] as const) {
  test(`the case-changes table fits its card at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await stubExperiments(page);
    await page.goto("/ops/experiments");
    await page.getByLabel("Use run 81 as A").check();
    await page.getByLabel("Use run 82 as B").check();
    const ab = page.getByRole("region", { name: "A/B comparison" });
    const table = ab.locator("table").last();
    await expect(table.getByRole("columnheader", { name: "Failures lost" })).toBeVisible();
    await table.scrollIntoViewIfNeeded();

    const fit = await page.evaluate(() => {
      const card = document.querySelector<HTMLElement>("section[aria-labelledby='ab-title']")!;
      const cardBox = card.getBoundingClientRect();
      const tableBox = [...card.querySelectorAll("table")].at(-1)!.getBoundingClientRect();
      const main = document.querySelector<HTMLElement>("main")!;
      return { tableRight: tableBox.right, cardRight: cardBox.right, cardOverflows: card.scrollWidth > card.clientWidth, mainOverflows: main.scrollWidth > main.clientWidth, pageOverflows: document.documentElement.scrollWidth > window.innerWidth };
    });
    expect(fit.tableRight).toBeLessThanOrEqual(fit.cardRight);
    expect(fit.cardOverflows).toBe(false);
    expect(fit.mainOverflows).toBe(false);
    expect(fit.pageOverflows).toBe(false);
    await expect(table.getByRole("row", { name: /dev-002.*consecutive_recipe_repetition, hard_constraint_violation/ })).toBeVisible();
    if (SHOTS) {
      await ab.screenshot({ path: `${SHOTS}/experiments-ab-card-${width}.png` });
      await page.screenshot({ path: `${SHOTS}/experiments-case-changes-${width}.png` });
    }
  });
}

test("the run form says how a run executes and does not start it twice", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  let posts = 0;
  await stubExperiments(page, async () => {
    posts += 1;
    await new Promise(resolve => setTimeout(resolve, 400));
  });
  await page.goto("/ops/experiments");
  const form = page.getByRole("form", { name: "Run an evaluation" });
  const chip = form.locator("p .mc-chip");

  // The OpenAI parser runs in the background; the rule-based one runs in the request.
  await form.getByLabel("Evaluation").selectOption("agent-benchmark");
  await expect(chip).toHaveText("Legacy inline");
  await form.getByLabel("Parser").selectOption("openai");
  await expect(chip).toHaveText("Runs in the background");
  await form.getByLabel("Parser").selectOption("fixture");
  await expect(chip).toHaveText("Legacy inline");
  await form.getByLabel("Evaluation").selectOption("planning-components");
  await expect(chip).toHaveText("Durable worker");

  // An inline run is run, not queued.
  await form.getByLabel("Evaluation").selectOption("developer-planning");
  await expect(chip).toHaveText("Legacy inline");
  await form.getByRole("button", { name: "Run evaluation" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Run this evaluation?" });
  await expect(confirm).toContainText("Run Developer planning set on data/evaluation/dev/planning-v1.json.");
  await expect(confirm).not.toContainText("Queue");

  // Two clicks before the page redraws start one run, and both buttons are off while it is in flight.
  await confirm.getByRole("button", { name: "Start run" }).evaluate((button: HTMLButtonElement) => {
    button.click();
    button.click();
  });
  await expect(confirm.getByRole("button", { name: "Working…" })).toBeDisabled();
  await expect(form.getByRole("button", { name: "Running…" })).toBeDisabled();
  await expect(confirm).toBeHidden();
  expect(posts).toBe(1);
  await expect(page.getByRole("row", { name: /#83 Developer planning set/ })).toBeVisible();
});
