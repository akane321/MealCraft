import { expect, test } from "@playwright/test";

function mealPlanFixture() {
  const recipe = {
    id: 1,
    slug: "evaluation-bowl",
    title: "Evaluation Bowl",
    description: "Deterministic browser-test fixture",
    cuisine: "Test kitchen",
    total_time_minutes: 25,
    servings: 2,
    dietary_tags: ["vegetarian"],
  };
  const nutrition = {
    calories_kcal: 520,
    protein_g: 32,
    carbohydrate_g: 58,
    fat_g: 16,
    sodium_mg: 610,
    sugar_g: 8,
  };
  return {
    id: 7001,
    revision: 1,
    household_profile_id: null,
    household_profile_version: null,
    replaces_plan_id: null,
    start_date: "2026-09-07",
    end_date: "2026-09-13",
    day_count: 7,
    household_size: 2,
    days: Array.from({ length: 7 }, (_, index) => ({
      entry_id: index + 1,
      day_index: index + 1,
      planned_date: `2026-09-${String(index + 7).padStart(2, "0")}`,
      recipe: { ...recipe, id: index + 1, slug: `evaluation-bowl-${index + 1}` },
      recommendation_score: 88 - index,
      nutrition_per_person: nutrition,
      consumed_cost_sgd: 6.5,
      purchase_cost_sgd: 9.8,
      status: "planned",
      is_locked: false,
      consumed_at: null,
    })),
    nutrition_summary_per_person: {
      calories_kcal: 3640,
      protein_g: 224,
      carbohydrate_g: 406,
      fat_g: 112,
      sodium_mg: 4270,
      sugar_g: 56,
    },
    grocery_estimate: {
      pricing_mode: "fixture",
      complete: true,
      purchase_total_sgd: 45.2,
      consumed_total_sgd: 39.5,
      weekly_budget_sgd: 60,
      within_weekly_budget: true,
      items: [
        {
          ingredient_name: "brown_rice",
          ingredient_display_name: "Brown rice",
          required_quantity: 700,
          pantry_deduction: 200,
          remaining_quantity: 500,
          unit: "g",
          product: {
            product_id: "fixture-rice",
            name: "FairPrice Brown Rice 1kg",
            product_url: "https://www.fairprice.com.sg/",
            package_quantity: 1000,
            package_unit: "g",
            price_sgd: 4.8,
          },
          packages_required: 1,
          purchase_cost_sgd: 4.8,
          consumed_cost_sgd: 2.4,
        },
      ],
      unmapped_ingredients: [],
      warnings: [],
    },
    warnings: [],
    created_at: "2026-09-03T12:00:00Z",
  };
}

test.beforeEach(async ({ page }) => {
  await page.route("**/api/household-profiles/current", route => route.fulfill({
    status: 404,
    contentType: "application/json",
    body: JSON.stringify({ detail: "No household profile" }),
  }));
});

async function openHydratedPlanner(page: import("@playwright/test").Page) {
  const profileResponse = page.waitForResponse("**/api/household-profiles/current");
  await page.goto("/weekly-plan");
  await profileResponse;
  const removeButtons = page.getByRole("button", { name: /Remove pantry item/ });
  await expect(removeButtons).toHaveCount(2);
  await page.getByRole("button", { name: "Remove pantry item 2" }).click();
  await expect(removeButtons).toHaveCount(1);
}

test("renders a complete seven-day result and shopping list", async ({ page }) => {
  await page.route("**/api/plans/generate", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(mealPlanFixture()),
  }));
  await openHydratedPlanner(page);

  await expect(page.getByRole("heading", { name: "One week, planned as a complete system." })).toBeVisible();
  await expect(page.getByText("No saved household profile")).toBeVisible();
  await page.getByRole("button", { name: "Generate seven-day plan" }).click();

  await expect(page.locator(".weekly-day-card")).toHaveCount(7);
  await expect(page.getByText("Consolidated shopping list")).toBeVisible();
  await expect(page.getByText("Within weekly budget")).toBeVisible();
});

test("shows a recoverable planning error", async ({ page }) => {
  await page.route("**/api/plans/generate", route => route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: "No recipes satisfy the supplied hard constraints." }),
  }));
  await openHydratedPlanner(page);
  await page.getByRole("button", { name: "Generate seven-day plan" }).click();

  await expect(page.getByText("No recipes satisfy the supplied hard constraints.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate seven-day plan" })).toBeEnabled();
});
