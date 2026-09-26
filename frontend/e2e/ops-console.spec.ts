import { expect, test, type Page, type Route } from "@playwright/test";

const SHOTS = process.env.OPS_CONSOLE_SHOTS;

function isoDay(offset: number) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return day.toLocaleDateString("en-CA");
}

function actor(systemRole: string) {
  return {
    user: { id: 7, normalized_email: "ops@example.test", display_name: "Ops Lead", locale: "en-SG", timezone: "Asia/Singapore", status: "active", system_role: systemRole, email_verified_at: null, created_at: "2026-09-20T08:00:00Z" },
    active_household_id: systemRole === "admin" ? null : 1,
    household_role: systemRole === "admin" ? null : "owner",
  };
}

const series = {
  days: Array.from({ length: 14 }, (_, index) => ({
    day: isoDay(index - 13),
    agent_sessions: index % 3,
    agent_runs: index % 2 ? { committed: 2, failed: 1 } : { committed: 1 },
    planning_runs: index % 4 ? { succeeded: 2 } : { succeeded: 1, failed: 1 },
    planning_median_seconds: index % 5 ? 1.2 + index / 10 : null,
    planning_p90_seconds: index % 5 ? 2.5 + index / 8 : null,
  })),
  provider_modes: { fixture: 12, fairprice: 5 },
};

const overview = {
  api_status: "ok",
  database_status: "connected",
  service: "MealCraft",
  app_version: "0.1.0",
  generated_at: "2026-09-26T08:00:00Z",
  latest_recorded_versions: { code_commit: "b71e802", catalog_version: "catalog-v2.1", product_snapshot_version: "fixture-2026-09" },
  runs: { queued: 0, running: 1, failures_last_24_hours: { infeasible: 2 }, provider_modes_last_24_hours: { fixture: 3 } },
};

const planningTask = {
  kind: "planning",
  id: 41,
  label: "Planning run (beam-product-v1)",
  status: "failed",
  error_code: "infeasible",
  provider_mode: "fixture",
  created_at: "2026-09-26T07:30:00Z",
  duration_seconds: 2.4,
};

const tasks = {
  total: 2,
  items: [
    planningTask,
    { kind: "agent", id: 90, label: "Conversation 12: plan week", status: "committed", error_code: null, provider_mode: "openai", created_at: "2026-09-26T07:29:00Z", duration_seconds: 5.1 },
  ],
};

const planningDetail = {
  summary: planningTask,
  inputs: { input_digest: "a".repeat(64), plan_id: null, note: "Constraints are kept with a saved plan; this run saved none, so only their digest remains." },
  trace: { search: { expansions: 812, completed_candidates: 0 }, explanation: { binding: "weekly_budget_sgd" } },
  validation: { feasible: false, checks: ["budget", "allergens"] },
  evidence: { input_digest: "a".repeat(64), shopping_digest: null, evidence_state: "complete" },
  model_configuration: { algorithm: "beam", settings: { width: 4 }, seed: 0 },
  timings: { created_at: "2026-09-26T07:30:00Z", duration_seconds: 2.4 },
  error_detail: "No week fits a S$40 budget.",
  warnings: [],
};

const services = {
  items: [
    { name: "openai", label: "OpenAI", configured: true, mode: "openai parser, model gpt-5.4-mini", recent: { window_days: 7, calls: 18, failures: 0, fallbacks: 1 }, note: null },
    { name: "fairprice", label: "FairPrice", configured: true, mode: "fixture prices unless a plan asks for live prices", recent: { window_days: 7, calls: 4, failures: 1, fallbacks: 2 }, note: null },
    { name: "youtube", label: "YouTube", configured: false, mode: "fixture", recent: null, note: "Tutorial lookups are not stored yet, so there is no call history." },
  ],
};

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const path = (pathname: string) => (url: URL) => url.pathname === pathname;

async function stubConsole(page: Page, role = "admin") {
  let signedIn = false;
  await page.route(path("/api/auth/me"), route => route.fulfill(signedIn ? json(actor(role)) : json({ detail: "Authentication required" }, 401)));
  await page.route(path("/api/auth/login"), (route) => {
    signedIn = true;
    return route.fulfill(json({ actor: actor(role), session: {}, csrf_token: "csrf-test" }));
  });
  await page.route(path("/api/ops/overview"), route => route.fulfill(json(overview)));
  await page.route(path("/api/ops/overview/series"), route => route.fulfill(json(series)));
  await page.route(path("/api/ops/tasks"), route => route.fulfill(json(tasks)));
  await page.route(path("/api/ops/tasks/planning/41"), route => route.fulfill(json(planningDetail)));
  await page.route(path("/api/ops/services"), route => route.fulfill(json(services)));
  await page.route(path("/api/ops/services/fairprice/check"), (route: Route) => {
    expect(route.request().method()).toBe("POST");
    return route.fulfill(json({ name: "fairprice", ok: true, latency_ms: 420, error_kind: null, detail: "One search returned Songhe Rice 5kg.", checked_at: "2026-09-26T08:00:00Z" }));
  });
  // The home surface, where a household account is sent back to.
  await page.route(path("/api/agent/sessions"), route => route.fulfill(json({ items: [] })));
  await page.route(path("/api/household-profiles/current"), route => route.fulfill(json({}, 404)));
}

async function signIn(page: Page) {
  await page.goto("/login");
  // A click before hydration is lost, so retry the switch until the page answers it.
  await expect(async () => {
    await page.getByRole("radio", { name: "Administrator" }).click();
    await expect(page.getByRole("heading", { name: "Administrator sign in" })).toBeVisible({ timeout: 1000 });
  }).toPass();
  await page.getByLabel("Email").fill("ops@example.test");
  await page.getByLabel("Password").fill("console-password");
  await page.getByRole("button", { name: "Sign in to the console" }).click();
}

test("an administrator signs in, reads the overview, opens a task and runs a live check", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubConsole(page);
  await signIn(page);

  await expect(page).toHaveURL(/\/ops$/);
  await expect(page.getByRole("heading", { name: "The last two weeks" })).toBeVisible();
  await expect(page.getByRole("img", { name: "Planning runs per day by status" })).toBeVisible();
  await expect(page.getByText("infeasible")).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Console" });
  for (const module of ["Overview", "Tasks", "Debugging", "Services", "Data", "Experiments & config", "Users"]) {
    await expect(nav.getByRole("link", { name: new RegExp(`^${module}`) })).toBeVisible();
  }
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-1-overview.png`, fullPage: true });

  await nav.getByRole("link", { name: "Tasks" }).click();
  await page.getByRole("button", { name: "Planning run (beam-product-v1)" }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("No week fits a S$40 budget.")).toBeVisible();
  await expect(drawer.getByRole("heading", { name: "Validation" })).toBeVisible();
  await expect(drawer.getByText("allergens")).toBeVisible();
  await expect(drawer.getByText("Search", { exact: true })).toBeVisible();
  await expect(page).toHaveURL(/task=planning-41/);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-2-task.png` });
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();

  await nav.getByRole("link", { name: "Services" }).click();
  const fairprice = page.getByRole("region", { name: "FairPrice" });
  await expect(fairprice.getByText("Configured")).toBeVisible();
  await fairprice.getByRole("button", { name: "Run live check" }).click();
  await expect(fairprice.getByRole("status")).toContainText("Answered in 420 ms.");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-3-services.png` });

  await nav.getByRole("link", { name: /^Debugging/ }).click();
  await expect(page.getByRole("heading", { name: "Debugging is coming in the next slice" })).toBeVisible();
});

test("a household account is told plainly it is not an administrator and kept out of /ops", async ({ page }) => {
  await stubConsole(page, "ordinary_user");
  await signIn(page);
  await expect(page.getByRole("alert")).toContainText("this account is not an administrator");
  await expect(page).toHaveURL(/\/login/);

  await page.goto("/ops");
  await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/$/);
});
