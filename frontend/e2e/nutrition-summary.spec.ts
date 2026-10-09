import { expect, test, type Page } from "@playwright/test";

function date(offset: number) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return day.toLocaleDateString("en-CA");
}

function dish(id: number, day: number, meal: string, calories: number, status: string) {
  const nutrition = { calories_kcal: calories, protein_g: calories / 10, carbohydrate_g: calories / 5, fat_g: calories / 20, sodium_mg: calories * 2, sugar_g: calories / 40 };
  return {
    entry_id: id, day_index: day, planned_date: date(day - 1), meal_type: meal,
    role_id: id === 2 ? "vegetable" : "main", portion_share: 1,
    recipe: { id, slug: `dish-${id}`, title: `Dish ${id}`, description: "", cuisine: "Home", meal_type: meal, servings: 2, total_time_minutes: 20, dietary_tags: [], nutrition },
    status, is_locked: false, consumed_at: null, nutrition_per_person: nutrition,
  };
}

async function stubNutrition(page: Page) {
  const days = [
    dish(1, 1, "lunch", 240, "completed"), dish(2, 1, "lunch", 120, "planned"),
    dish(3, 1, "lunch", 900, "skipped"), dish(4, 1, "dinner", 600, "planned"),
    dish(5, 2, "dinner", 500, "planned"),
    ...Array.from({ length: 5 }, (_, i) => dish(i + 6, i + 3, "dinner", 100, "planned")),
  ];
  const targets = { calories_kcal: 1000, protein_g: 100, carbohydrate_g: null, fat_g: null };
  const plan = {
    id: 9001, revision: 1, start_date: date(0), end_date: date(6), day_count: 7,
    household_size: 2, days, nutrition_summary_per_person: days[0]!.nutrition_per_person,
    grocery_estimate: { pricing_mode: "fixture", complete: true, purchase_total_sgd: 40, consumed_total_sgd: 30, weekly_budget_sgd: 100, within_weekly_budget: true, items: [], unmapped_ingredients: [], warnings: [] },
    warnings: [], created_at: "2026-10-07T08:00:00Z",
  };
  const dashboard = {
    plan_id: plan.id, revision: 1, start_date: plan.start_date, end_date: plan.end_date,
    household_size: 2, completion_rate: 0.1, status_counts: { completed: 1, planned: 8, skipped: 1 },
    nutrition_targets: targets, days, completed_nutrition_per_person: days[0]!.nutrition_per_person,
    planned_nutrition_per_person: { calories_kcal: 1960, protein_g: 196, carbohydrate_g: 392, fat_g: 98, sodium_mg: 3920, sugar_g: 49 },
  };
  const session = (planned: boolean) => ({
    id: 51, status: planned ? "planned" : "ready", parser_provider: "fixture", plan_id: planned ? plan.id : null,
    constraints: { household_size: 2, weekly_budget_sgd: 100, max_cooking_time_minutes: null, budget_per_meal_sgd: null, allergens: [], excluded_ingredients: [], dietary_preferences: [], health_preferences: [], nutrition_targets: targets, max_sodium_mg_per_meal: 100, available_ingredients: [], pricing_mode: "fixture", max_uses_per_recipe: null },
    missing_fields: [], clarification_questions: [],
    messages: [{ id: 1, role: "user", content: "Plan lunch and dinner for two", created_at: "2026-10-07T08:00:00Z" }, { id: 2, role: "assistant", content: "Ready", created_at: "2026-10-07T08:00:00Z" }],
    replan_draft: {}, pending_replan: null, pending_interaction: null, can_confirm: !planned,
  });
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/auth/me", route => route.fulfill(json({ user: { id: 1, email: "synthetic@example.com", display_name: "Synthetic household", system_role: "user", status: "active" }, active_household_id: 1, household_role: "owner" })));
  await page.route("**/api/household-profiles/current", route => route.fulfill({ status: 404, contentType: "application/json", body: "{}" }));
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [] })));
  await page.route("**/api/agent/sessions", route => route.fulfill({ ...json(session(false)), status: 201 }));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: session(true), plan })));
  await page.route("**/api/plans/9001", route => route.fulfill(json(plan)));
  await page.route("**/api/plans/9001/dashboard", route => route.fulfill(json(dashboard)));
  await page.route("**/api/plans/9001/events", route => route.fulfill(json({ items: [] })));
  await page.route("**/api/recipes/*/tutorial", route => route.fulfill(json({ selected_video: null, retrieval: { provider_used: "fixture", mode: "fixture", status: "success" }, warning: null })));
}

for (const [width, height] of [[1280, 720], [1440, 900]]) {
  test(`nutrition shows selected day and meal, all six nutrients and details without scrolling at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width: width!, height: height! });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await stubNutrition(page);
    await page.goto("/");
    await expect(page).toHaveTitle(/MealCraft/);
    await page.getByLabel("Message MealCraft").fill("Plan lunch and dinner for two");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await page.getByRole("button", { name: "Plan my week", exact: true }).click();
    const panel = page.getByRole("complementary", { name: "This week" });
    await expect(panel.getByRole("tab", { name: "Nutrition", exact: true })).toBeVisible();
    await panel.getByRole("tab", { name: "Nutrition", exact: true }).click();
    const summary = panel.getByRole("region", { name: "Nutrition per day and meal" });
    await expect(summary.getByText("Eaten so far", { exact: true })).toBeVisible();
    const total = summary.locator(".big .mc-display");
    const eaten = summary.getByText(/kcal eaten so far/);
    await expect(total).toHaveText("960");
    await expect(eaten).toContainText("240 kcal eaten so far");
    await expect(summary.getByRole("row", { name: "Calories 240 kcal 960 kcal", exact: true })).toBeVisible();
    await expect(summary.getByRole("row", { name: "Sugar 6 g 24 g", exact: true })).toBeVisible();
    await expect(summary.getByRole("row")).toHaveCount(7);
    await expect(summary.locator(".macros").getByText("96 g", { exact: true })).toBeVisible();
    await expect(summary.getByText(/1 skipped dish not counted/)).toBeVisible();
    await expect(summary.getByText(/target|limit \d/i)).toHaveCount(0);
    const body = panel.getByRole("tabpanel", { name: "Nutrition", exact: true });
    const details = summary.getByRole("button", { name: "All six nutrients & daily detail", exact: true });
    const bodyBounds = await body.boundingBox();
    const buttonBounds = await details.boundingBox();
    expect(buttonBounds!.y + buttonBounds!.height).toBeLessThanOrEqual(bodyBounds!.y + bodyBounds!.height);
    expect(await body.evaluate(element => element.scrollTop)).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (process.env.NUTRITION_SHOTS) await page.screenshot({ path: `${process.env.NUTRITION_SHOTS}/nutrition-${width}x${height}-day.png` });
    await summary.getByLabel("Nutrition meal").selectOption("lunch");
    await expect(total).toHaveText("360");
    await expect(eaten).toContainText("240 kcal eaten so far");
    await summary.getByLabel("Nutrition meal").selectOption("dinner");
    await expect(total).toHaveText("600");
    await expect(eaten).toContainText("0 kcal eaten so far");
    await summary.getByRole("group", { name: "Nutrition day" }).getByRole("button").nth(1).click();
    await expect(summary.getByLabel("Nutrition meal")).toHaveCount(0);
    await expect(summary.getByText(/ dinner, per person$/)).toBeVisible();
    await expect(total).toHaveText("500");
    await expect(eaten).toContainText("0 kcal eaten so far");
    await details.click();
    await expect(page.getByRole("dialog", { name: "Nutrition details", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}
