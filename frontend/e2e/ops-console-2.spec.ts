import { expect, test, type Page, type Route } from "@playwright/test";

// Console slice 2 (ADR-0047): a replay diff, a runtime switch and an account edit, all against stubbed APIs.
const SHOTS = process.env.OPS_CONSOLE_SHOTS;

const admin = {
  user: { id: 7, normalized_email: "ops@example.test", display_name: "Ops Lead", locale: "en-SG", timezone: "Asia/Singapore", status: "active", system_role: "admin", email_verified_at: null, created_at: "2026-09-20T08:00:00Z" },
  active_household_id: null,
  household_role: null,
};

const planningTask = { kind: "planning", id: 41, label: "Planning run (beam-product-v1)", status: "failed", error_code: "infeasible", provider_mode: "fixture", created_at: "2026-09-26T07:30:00Z", duration_seconds: 2.4 };
const planningDetail = {
  summary: planningTask,
  inputs: { input_digest: "a".repeat(64), plan_id: null },
  trace: { request: { weekly_budget_sgd: 30 } },
  validation: null,
  evidence: {},
  model_configuration: { algorithm: "beam" },
  timings: { duration_seconds: 2.4 },
  error_detail: "I couldn't fit seven dinners into S$30.00.",
  warnings: [],
};

const week = (recipes: string[]) => recipes.map((recipe, index) => ({ day: index + 1, meal: "dinner", role: "main", recipe }));
function replay(id: number, overrides: Record<string, unknown>, budget: number) {
  return {
    id,
    kind: "planning",
    source_id: 41,
    overrides,
    original: { status: "infeasible", evidence: "exhaustively_infeasible", message: "I couldn't fit seven dinners into S$30.00.", dishes: [], total_cost_sgd: 34.1, failed_checks: [{ code: "purchase_budget", status: "failed" }], duration_seconds: 2.4, settings: { planner: "beam", width: 32 } },
    replay: { status: "feasible", evidence: "validated", message: null, dishes: week(["Lemon Chicken", "Tofu Soba", "Lemon Chicken", "Tofu Soba", "Lemon Chicken", "Tofu Soba", "Lemon Chicken"]), total_cost_sgd: budget - 2.5, failed_checks: [], duration_seconds: 1.1, settings: { planner: "beam", width: 32 } },
    triggered_by_user_id: 7,
    created_at: "2026-09-26T08:10:00Z",
  };
}

const settings = [
  { key: "agent_parser_provider", label: "Assistant parser", meaning: "How the assistant reads a message.", choices: ["fixture", "openai"], minimum: null, maximum: null, integer: false, default: "fixture", value: "fixture", overridden: false, wired: true, updated_at: null },
  { key: "beam_width", label: "Beam width", meaning: "How many partial weeks the planner keeps at each step.", choices: null, minimum: 1, maximum: 512, integer: true, default: 32, value: 32, overridden: false, wired: false, updated_at: null },
];

const bob = {
  id: 12,
  email: "bob@example.test",
  display_name: "Bob",
  system_role: "ordinary_user",
  status: "active",
  households: [{ id: 3, name: "Bob's household", role: "owner", members: 1, profile: { people: 2, weekly_budget_sgd: 90, allergens: ["peanut"] } }],
  conversations: 2,
  plans: 1,
  last_seen_at: "2026-09-26T06:00:00Z",
  created_at: "2026-09-21T06:00:00Z",
};
const bobDetail = { ...bob, recent_conversations: [{ id: 5, status: "ready", messages: 4, first_message: "Dinners for two", created_at: "2026-09-25T06:00:00Z" }], recent_plans: [{ id: 9, start_date: "2026-09-28", total_sgd: 71.4, household_size: 2, created_at: "2026-09-25T06:10:00Z" }] };

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const path = (pathname: string) => (url: URL) => url.pathname === pathname;

async function stubConsole(page: Page) {
  let signedIn = false;
  const replays = [] as Array<ReturnType<typeof replay>>;
  let current = settings.map(item => ({ ...item }));
  const history: unknown[] = [];
  let user = { ...bobDetail };

  await page.route(path("/api/auth/me"), route => route.fulfill(signedIn ? json(admin) : json({ detail: "Authentication required" }, 401)));
  await page.route(path("/api/auth/login"), (route) => {
    signedIn = true;
    return route.fulfill(json({ actor: admin, session: {}, csrf_token: "csrf-test" }));
  });
  await page.route(path("/api/ops/tasks"), route => route.fulfill(json({ total: 1, items: [planningTask] })));
  await page.route(path("/api/ops/tasks/planning/41"), route => route.fulfill(json(planningDetail)));
  await page.route(path("/api/ops/replay/planning/41"), (route: Route) => {
    const overrides = route.request().postDataJSON() ?? {};
    const made = replay(replays.length + 5, overrides, Number(overrides.weekly_budget_sgd ?? 40));
    replays.unshift(made);
    return route.fulfill(json(made));
  });
  await page.route(path("/api/ops/replays"), route => route.fulfill(json({ items: replays.map(item => ({ id: item.id, kind: item.kind, source_id: 41, overrides: item.overrides, original_status: "infeasible", replay_status: "feasible", created_at: item.created_at })) })));
  await page.route(/\/api\/ops\/replays\/\d+$/, (route: Route) => {
    const id = Number(new URL(route.request().url()).pathname.split("/").pop());
    return route.fulfill(json(replays.find(item => item.id === id)));
  });
  await page.route(path("/api/ops/config"), route => route.fulfill(json({ items: current })));
  await page.route(path("/api/ops/config/history"), route => route.fulfill(json({ items: history })));
  await page.route(path("/api/ops/config/agent_parser_provider"), (route: Route) => {
    expect(route.request().method()).toBe("PUT");
    const { value } = route.request().postDataJSON();
    history.unshift({ key: "agent_parser_provider", before: "fixture", after: value, actor: "Ops Lead", created_at: "2026-09-26T08:20:00Z" });
    current = current.map(item => (item.key === "agent_parser_provider" ? { ...item, value, overridden: true } : item));
    return route.fulfill(json({ items: current }));
  });
  await page.route(path("/api/ops/experiments"), route => route.fulfill(json({ items: [], evaluations: [{ name: "developer-planning", label: "Developer planning set", description: "20 planning scenarios.", dataset: "data/evaluation/dev/planning-v1.json", options: { planner: ["mealcraft-planner"] } }] })));
  await page.route(path("/api/ops/users"), route => route.fulfill(json({ total: 1, items: [user] })));
  await page.route(path("/api/ops/users/12"), (route: Route) => {
    if (route.request().method() === "PATCH") {
      const change = route.request().postDataJSON();
      expect(change).toEqual({ display_name: "Robert", system_role: "admin" });
      user = { ...user, ...change };
    }
    return route.fulfill(json(user));
  });
}

async function signIn(page: Page) {
  await page.goto("/login");
  await expect(async () => {
    await page.getByRole("radio", { name: "Administrator" }).click();
    await expect(page.getByRole("heading", { name: "Administrator sign in" })).toBeVisible({ timeout: 1000 });
  }).toPass();
  await page.getByLabel("Email").fill("ops@example.test");
  await page.getByLabel("Password").fill("console-password");
  await page.getByRole("button", { name: "Sign in to the console" }).click();
  await expect(page).toHaveURL(/\/ops$/);
}

test("an administrator replays a failed plan, switches the parser and edits an account", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubConsole(page);
  await page.route(path("/api/ops/overview"), route => route.fulfill(json({ app_version: "0.1.0", generated_at: "2026-09-26T08:00:00Z", latest_recorded_versions: { code_commit: null, catalog_version: null, product_snapshot_version: null }, runs: { queued: 0, running: 0, failures_last_24_hours: {}, provider_modes_last_24_hours: {} } })));
  await page.route(path("/api/ops/overview/series"), route => route.fulfill(json({ days: [], provider_modes: {} })));
  await signIn(page);
  const nav = page.getByRole("navigation", { name: "Console" });

  // Replay from the task drawer, then read the diff.
  await nav.getByRole("link", { name: "Tasks" }).click();
  await page.getByRole("button", { name: "Planning run (beam-product-v1)" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Replay", exact: true }).click();
  await expect(page).toHaveURL(/\/ops\/debugging\?replay=5/);
  const compare = page.getByRole("region", { name: /Planning run #41: stored and replayed/ });
  await expect(compare.getByRole("row", { name: /Total cost S\$34\.10 S\$37\.50/ })).toBeVisible();
  await expect(compare.getByRole("row", { name: /Checks not passed Purchase budget none/ })).toBeVisible();
  await expect(compare.getByRole("row", { name: "Day 1 dinner — Lemon Chicken" })).toHaveClass(/changed/);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-4-replay.png`, fullPage: true });

  await compare.getByLabel("Weekly budget (S$)").fill("60");
  await compare.getByRole("button", { name: "Replay with these settings" }).click();
  await expect(page).toHaveURL(/replay=6/);
  await expect(compare.getByRole("row", { name: /Total cost S\$34\.10 S\$57\.50/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Recent replays" }).getByRole("button")).toHaveCount(2);

  // Switch the assistant parser, with a confirmation, and see it in the history.
  await nav.getByRole("link", { name: "Experiments & config" }).click();
  await page.getByLabel("Assistant parser").selectOption("openai");
  await page.getByRole("button", { name: "Change" }).first().click();
  const confirm = page.getByRole("alertdialog");
  await expect(confirm).toContainText("Assistant parser changes from fixture to openai. New requests use it straight away.");
  await confirm.getByRole("button", { name: "Change it" }).click();
  await expect(confirm).toBeHidden();
  await expect(page.getByRole("region", { name: "Change history" }).getByRole("row", { name: /Ops Lead Assistant parser fixture openai/ })).toBeVisible();
  await expect(page.getByText("Changed here")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-5-config.png`, fullPage: true });

  // Rename an account and give it console access.
  await nav.getByRole("link", { name: "Users" }).click();
  await page.getByRole("button", { name: "Bob" }).click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("“Dinners for two”")).toBeVisible();
  await drawer.getByLabel("Display name").fill("Robert");
  await drawer.getByLabel("Console administrator").check();
  await drawer.getByRole("button", { name: "Save changes" }).click();
  await expect(drawer.getByRole("status")).toHaveText("Saved.");
  await expect(drawer.getByRole("heading", { name: "Robert" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-6-users.png` });
});
