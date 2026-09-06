import { expect, test } from "@playwright/test";

const nutrition = {
  calories_kcal: 520,
  protein_g: 32,
  carbohydrate_g: 58,
  fat_g: 16,
  sodium_mg: 610,
  sugar_g: 8,
};

const days = Array.from({ length: 7 }, (_, index) => ({
  entry_id: index + 1,
  day_index: index + 1,
  planned_date: `2026-09-${String(index + 7).padStart(2, "0")}`,
  recipe: {
    id: index + 1,
    slug: `evaluation-bowl-${index + 1}`,
    title: `Evaluation Bowl ${index + 1}`,
    description: "Deterministic dashboard fixture",
    cuisine: "Test kitchen",
    meal_type: "main",
    total_time_minutes: 25,
    servings: 2,
    dietary_tags: ["vegetarian"],
    nutrition,
  },
  status: index === 0 ? "completed" : index === 1 ? "skipped" : "planned",
  is_locked: false,
  consumed_at: index === 0 ? "2026-09-07T12:00:00Z" : null,
  nutrition_per_person: nutrition,
}));

const planSummary = {
  id: 7001,
  revision: 1,
  household_profile_id: null,
  household_profile_version: null,
  replaces_plan_id: null,
  start_date: "2026-09-07",
  end_date: "2026-09-13",
  household_size: 2,
  purchase_total_sgd: 45.2,
  consumed_total_sgd: 39.5,
  within_weekly_budget: true,
  created_at: "2026-09-03T12:00:00Z",
};

test("prioritizes cumulative nutrition while retaining daily detail", async ({ page }) => {
  await page.route("**/api/plans", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [planSummary] }),
  }));
  await page.route("**/api/plans/7001/dashboard", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      plan_id: 7001,
      revision: 1,
      start_date: "2026-09-07",
      end_date: "2026-09-13",
      household_size: 2,
      completion_rate: 14.3,
      status_counts: { completed: 1, skipped: 1, planned: 5 },
      nutrition_targets: {},
      planned_nutrition_per_person: {
        calories_kcal: 3120,
        protein_g: 192,
        carbohydrate_g: 348,
        fat_g: 96,
        sodium_mg: 3660,
        sugar_g: 48,
      },
      completed_nutrition_per_person: nutrition,
      days,
    }),
  }));
  await page.route("**/api/plans/7001/events", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [] }),
  }));

  await page.goto("/dashboard");

  const cumulativeSummary = page.getByRole("region", { name: "Cumulative nutrition totals" });
  await expect(cumulativeSummary).toContainText("520 kcal");
  await expect(cumulativeSummary).toContainText("17% of current plan");
  await expect(page.getByRole("heading", { name: "Cumulative nutrition curve" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Daily nutrition detail" })).toBeVisible();
  await expect(page.locator(".daily-nutrition-row")).toHaveCount(7);
  await expect(page.locator(".daily-nutrition-row.completed")).toContainText("Actual");
  await expect(page.locator(".daily-nutrition-row.skipped")).toContainText("Not counted");

  await page.getByRole("button", { name: "Protein" }).click();
  await expect(page.getByRole("img", { name: /Cumulative Protein/ })).toBeVisible();
});
