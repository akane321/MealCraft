import { expect, test, type Page, type Route } from "@playwright/test";

test.describe.configure({ timeout: 60_000 });

const admin = {
  user: { id: 7, normalized_email: "ops@example.test", display_name: "Ops Lead", locale: "en-SG", timezone: "Asia/Singapore", status: "active", system_role: "admin", email_verified_at: null, created_at: "2026-09-20T08:00:00Z" },
  active_household_id: null,
  household_role: null,
};

const artifact = (name: string) => ({
  name,
  sha256: "a".repeat(64),
  size_bytes: 2048,
  updated_at: "2026-10-02T08:00:00Z",
});

const summary = {
  status: "available",
  release_version: "v2.1",
  schema_version: "mealcraft.recipe.v2",
  generated_at: "2026-10-02T08:00:00Z",
  coverage: { released_recipes: 8968, enrichment_set: 12333, released_ingredients: 701, recipes_with_every_field: 8940 },
  by_cuisine: { chinese: 4200, italian: 2200, indian: 1200 },
  by_course: { main: 5680, soup: 1200, dessert: 900 },
  by_source: { recipenlg: 8968 },
  estimated_share: { servings: 0.126, times: 0.25, ingredient_amounts: 0.034 },
  nutrition: { complete_recipes: 8800, total_recipes: 8968, median_energy_kcal: 327.4 },
  dropped_by_reason: { missing_ingredient: 25, duplicate: 1 },
  allergen_rules_pending_human: 4,
  artifacts: [artifact("quality_summary.json"), artifact("release_manifest.json")],
  issues: [],
};

const candidates = [
  ...Array.from({ length: 25 }, (_, index) => ({
    candidate_id: `recipe-${index + 1}`,
    title: index === 0 ? "Incomplete Soup" : `Incomplete candidate ${index + 1}`,
    reason: "missing_ingredient",
  })),
  { candidate_id: "recipe-26", title: "Repeated Pie", reason: "duplicate" },
];

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const path = (pathname: string) => (url: URL) => url.pathname === pathname;

async function stubAdmin(page: Page) {
  await page.route(path("/api/auth/me"), route => route.fulfill(json(admin)));
}

async function stubQuality(page: Page) {
  await stubAdmin(page);
  await page.route(path("/api/ops/data-quality"), route => route.fulfill(json(summary)));
  await page.route(path("/api/ops/data-quality/dropped"), (route: Route) => {
    const url = new URL(route.request().url());
    const reason = url.searchParams.get("reason");
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 25);
    const matching = reason ? candidates.filter(item => item.reason === reason) : candidates;
    const items = matching.slice(offset, offset + limit);
    return route.fulfill(json({
      status: "available",
      release_version: "v2.1",
      items,
      total: matching.length,
      offset,
      limit,
      next_offset: offset + items.length < matching.length ? offset + items.length : null,
      skipped_records: 0,
      artifact: artifact("dropped.jsonl"),
      issues: [],
    }));
  });
}

test("an administrator inspects release coverage, provenance and dropped reasons", async ({ page }) => {
  await stubQuality(page);
  await page.goto("/ops/quality");

  await expect(page.getByRole("heading", { name: "What is in this release—and how it got there" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "v2.1" })).toBeVisible();
  await expect(page.locator("article.metric").filter({ hasText: "Recipes" }).getByText("8,968", { exact: true })).toBeVisible();
  await expect(page.getByText("12.6%", { exact: true })).toBeVisible();
  await expect(page.getByText("8,800 / 8,968", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "quality_summary.json" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Incomplete Soup" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("cell", { name: "Repeated Pie" })).toBeVisible();
  await expect(page.getByText("26–26 of 26")).toBeVisible();

  await page.getByRole("combobox", { name: "Reason", exact: true }).selectOption("duplicate");
  await expect(page.getByRole("cell", { name: "Repeated Pie" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Incomplete Soup" })).toHaveCount(0);
  await expect(page.getByText("1–1 of 1")).toBeVisible();
});

test("degraded evidence stays unavailable instead of looking like zero", async ({ page }) => {
  await stubAdmin(page);
  await page.route(path("/api/ops/data-quality"), route => route.fulfill(json({
    ...summary,
    status: "degraded",
    generated_at: null,
    coverage: null,
    by_cuisine: null,
    by_course: null,
    by_source: null,
    estimated_share: null,
    nutrition: null,
    dropped_by_reason: null,
    allergen_rules_pending_human: null,
    artifacts: [],
    issues: [{ artifact: "quality_summary.json", code: "artifact_missing", detail: "The registered summary is unavailable." }],
  })));
  await page.route(path("/api/ops/data-quality/dropped"), route => route.fulfill(json({
    status: "degraded",
    release_version: "v2.1",
    items: [],
    total: null,
    offset: 0,
    limit: 25,
    next_offset: null,
    skipped_records: 0,
    artifact: null,
    issues: [{ artifact: "dropped.jsonl", code: "artifact_missing", detail: "The registered dropped artifact is unavailable." }],
  })));

  await page.goto("/ops/quality");
  await expect(page.getByText("Degraded", { exact: true })).toBeVisible();
  await expect(page.getByText("Coverage is unavailable from this release.")).toBeVisible();
  await expect(page.getByText("The dropped artifact is unavailable; no total has been invented.")).toBeVisible();
  await expect(page.getByText("No records")).toHaveCount(0);
});
