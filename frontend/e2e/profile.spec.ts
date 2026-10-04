import { expect, test } from "@playwright/test";

const SHOTS = process.env.HOME_SURFACE_SHOTS;

test("the household chooses its meals and each meal's dishes, and they are saved", async ({ page }) => {
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "user" },
    active_household_id: 1,
    household_role: "owner",
  })));
  await page.route("**/api/household-profiles/current", route => route.fulfill(json({ detail: "none" }, 404)));
  let saved: { plan_shape?: { meals: Record<string, Array<{ role_id: string }>> } } | null = null;
  await page.route("**/api/household-profiles", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill(json({ detail: "stop here" }, 422));
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/profile");
  await page.waitForLoadState("networkidle"); // clicks before hydration are lost
  await expect(page.getByText("Dinner: one meat, one veg")).toBeVisible();
  // The vegetable row is named by its role, which the planner holds to vegetable dishes whatever its courses.
  await expect(page.getByText("Vegetable dish", { exact: true })).toHaveAttribute("title", /no meat or fish/);

  await page.getByRole("checkbox", { name: "Plan lunch" }).check();
  await expect(page.getByRole("radiogroup", { name: "Lunch dishes" }).getByRole("radio", { name: "Main and a veg" })).toBeVisible();
  await page.getByRole("radiogroup", { name: "Dinner dishes" }).getByRole("radio", { name: "Meat, veg and soup" }).click();
  await expect(page.getByText("Lunch: one dish · Dinner: meat, veg and soup")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/14-profile-meals.png`, fullPage: true });

  await page.getByRole("button", { name: "Save household" }).click();
  await expect.poll(() => saved?.plan_shape?.meals && Object.keys(saved.plan_shape.meals)).toEqual(["dinner", "lunch"]);
  expect(saved!.plan_shape!.meals.dinner!.map(role => role.role_id)).toEqual(["main", "vegetable", "soup"]);
});

test("a new household is saved with no limit or goal it did not enter", async ({ page }) => {
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "user" },
    active_household_id: 1,
    household_role: "owner",
  })));
  await page.route("**/api/household-profiles/current", route => route.fulfill(json({ detail: "none" }, 404)));
  let saved: Record<string, unknown> | null = null;
  await page.route("**/api/household-profiles", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill(json({ detail: "stop here" }, 422));
  });

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/profile");
  await page.waitForLoadState("networkidle"); // clicks before hydration are lost
  await expect(page.getByLabel("Longest cooking time (min)")).toHaveValue("");
  await expect(page.getByLabel("Calories per meal")).toHaveValue("");
  await expect(page.getByRole("checkbox", { name: "Lower sodium" })).not.toBeChecked();

  await page.getByRole("button", { name: "Save household" }).click();
  await expect.poll(() => saved).not.toBeNull();
  expect(saved).toMatchObject({
    max_cooking_time_minutes: 240, // no limit
    budget_per_meal_sgd: null,
    weekly_budget_sgd: null,
    health_preferences: [],
    nutrition_targets: { calories_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
    max_sodium_mg_per_meal: null,
  });
});
