import { expect, test, type Page } from "@playwright/test";

const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
const nutrition = { calories_kcal: 480, protein_g: 30, carbohydrate_g: 50, fat_g: 15, sodium_mg: 600, sugar_g: 6 };
const recipe = (id: number, title: string, course = "main") => ({
  id, slug: `r-${id}`, title, description: "", cuisine: "Home", meal_type: "dinner", servings: 2,
  total_time_minutes: 30, dietary_tags: [], nutrition, course,
});

async function signedIn(page: Page) {
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "user" },
    active_household_id: 1,
    household_role: "owner",
  })));
}

test("recipes can be searched and filtered, and groceries looked up", async ({ page }) => {
  await signedIn(page);
  const asked: URLSearchParams[] = [];
  await page.route("**/api/recipes?*", (route) => {
    const params = new URL(route.request().url()).searchParams;
    asked.push(params);
    const items = params.get("q") === "tofu" ? [recipe(2, "Tofu Soba")] : [recipe(1, "Lemon Chicken"), recipe(2, "Tofu Soba"), recipe(3, "Tomato Soup", "soup")];
    return route.fulfill(json({ items: params.get("course") === "soup" ? items.filter(item => item.course === "soup") : items, next_cursor: null }));
  });
  await page.route("**/api/products/search?*", route => route.fulfill(json({
    query: "chicken breast", provider_used: "fixture", fallback_used: false, cached: false, warning: null,
    items: [{ external_id: "fp-1", name: "FairPrice Chicken Breast", brand: "FairPrice", category: null, package_size: 500, package_unit: "g", price_sgd: 6.95, product_url: "https://www.fairprice.com.sg/product/1", image_url: null, in_stock: true, source: "fixture", fetched_at: "2026-09-26T00:00:00Z" }],
  })));

  await page.goto("/browse");
  await page.waitForLoadState("networkidle");
  await expect(page.getByText("Lemon Chicken")).toBeVisible();
  await page.getByPlaceholder("Search recipes").fill("tofu");
  await expect(page.getByText("Lemon Chicken")).toBeHidden();
  await expect(page.getByText("Tofu Soba")).toBeVisible();
  await page.getByPlaceholder("Search recipes").fill("");
  await page.getByRole("group", { name: "Course" }).getByRole("button", { name: "Soups" }).click();
  await expect(page.getByText("Tomato Soup")).toBeVisible();
  await expect(page.getByText("Tofu Soba")).toBeHidden();
  expect(asked.at(-1)?.get("course")).toBe("soup");

  await page.getByRole("tab", { name: "Groceries" }).click();
  await page.getByPlaceholder("Search FairPrice").fill("chicken breast");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("cell", { name: /FairPrice Chicken Breast/ })).toBeVisible();
  await expect(page.getByRole("cell", { name: "S$6.95" })).toBeVisible();
});

test("past weeks open to show what was eaten", async ({ page }) => {
  await signedIn(page);
  await page.route("**/api/plans?*", route => route.fulfill(json({ items: [{
    id: 7, revision: 2, household_profile_id: null, household_profile_version: null, replaces_plan_id: null,
    start_date: "2026-09-14", end_date: "2026-09-20", household_size: 2, purchase_total_sgd: 84.2,
    consumed_total_sgd: 70, within_weekly_budget: true, created_at: "2026-09-14T08:00:00Z",
  }] })));
  const dish = (day: number, meal: string, title: string, status = "completed") => ({
    entry_id: day * 10 + meal.length, day_index: day, planned_date: `2026-09-${13 + day}`, meal_type: meal, role_id: "main",
    portion_share: 1, recipe: recipe(day * 10 + meal.length, title), recommendation_score: 80, nutrition_per_person: nutrition,
    consumed_cost_sgd: 5, purchase_cost_sgd: 6, status, is_locked: false, consumed_at: null,
  });
  await page.route("**/api/plans/7", route => route.fulfill(json({
    id: 7, days: [dish(1, "dinner", "Lemon Chicken"), dish(1, "lunch", "Tofu Soba"), dish(2, "dinner", "Tomato Soup", "skipped")],
  })));

  await page.goto("/history");
  await page.waitForLoadState("networkidle");
  const week = page.getByRole("button", { name: /14 Sept – 20 Sept|14 Sep – 20 Sep/ });
  await week.click();
  await expect(week).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("button", { name: "Tofu Soba" })).toBeVisible();
  await expect(page.getByText("2 of 3 dishes cooked")).toBeVisible();
});
