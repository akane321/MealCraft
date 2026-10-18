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

test("a household sentence is read, confirmed and saved with portions, basics and the sodium limit", async ({ page }) => {
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "user" },
    active_household_id: 1,
    household_role: "owner",
  })));
  await page.route("**/api/household-profiles/current", route => route.fulfill(json({ detail: "none" }, 404)));
  await page.route("**/api/household-profiles/reference", route => route.fulfill(json({
    default_servings: {
      adult: { female: { moderate: { none: 0.88 } }, male: { moderate: { none: 1.12 } }, any: { moderate: { none: 1 } } },
      child: { female: { moderate: { none: 0.7 } }, male: { moderate: { none: 0.75 } }, any: { moderate: { none: 0.73 } } },
    },
    sodium_limit_mg: { adult: 2000, child: null },
    basics: [{ normalized_name: "salt", display_name: "Salt", allergens: [] }, { normalized_name: "soy_sauce", display_name: "Soy sauce", allergens: ["soy", "gluten"] }],
    meal_shares: { breakfast: 0.25, lunch: 0.35, dinner: 0.35 },
    sources: [],
  })));
  let parsed: Record<string, unknown> | null = null;
  await page.route("**/api/household-profiles/parse-rule", async (route) => {
    parsed = route.request().postDataJSON();
    await route.fulfill(json({
      rules: [{ source_text: "孩子工作日午饭在学校吃", restatement: "Monday to Friday, lunch: Mei eats elsewhere.", member_name: "Mei", present: false, weekdays: ["monday", "tuesday", "wednesday", "thursday", "friday"], meal_types: ["lunch"] }],
      issues: [],
      provider: "rules",
      fell_back: false,
    }));
  });
  let saved: Record<string, unknown> | null = null;
  await page.route("**/api/household-profiles", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill(json({ detail: "stop here" }, 422));
  });

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/profile");
  await page.waitForLoadState("networkidle"); // clicks before hydration are lost
  await page.getByLabel("Name", { exact: true }).fill("Mei");
  await page.getByLabel("Age group").selectOption("child");
  await expect(page.getByRole("option", { name: "Auto (0.73), from age, sex and activity" })).toBeAttached();

  await page.getByLabel("Who's home: one sentence").fill("孩子工作日午饭在学校吃");
  await page.getByRole("button", { name: "Read it" }).first().click();
  await expect(page.getByText("We understood:")).toBeVisible();
  await expect(page.getByText("Monday to Friday, lunch: Mei eats elsewhere.")).toBeVisible();
  await page.getByRole("button", { name: "Add this rule" }).click();
  await expect(page.getByText("From \"孩子工作日午饭在学校吃\"")).toBeVisible();
  expect(parsed).toMatchObject({ kind: "presence", members: [{ name: "Mei", age_band: "child", default_present: true }] });

  await page.getByRole("checkbox", { name: /Soy sauce/ }).check();
  await page.getByRole("checkbox", { name: "Keep sodium within a daily limit" }).check();
  await page.getByLabel("Most sodium per person a day (mg)").fill("1500");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/15-profile-rules.png`, fullPage: true });

  await page.getByRole("button", { name: "Save household" }).click();
  await expect.poll(() => saved).not.toBeNull();
  expect(saved).toMatchObject({
    members: [{ name: "Mei", servings_per_meal: null, age_band: "child", sex: null, activity: null, goal: null, default_present: true }],
    presence_rules: [{ member_name: "Mei", present: false, meal_types: ["lunch"] }],
    cooking_time_rules: [],
    missing_basics: ["soy_sauce"],
    nutrition_limits: [{ nutrient: "sodium_mg", scope: "per_day", max_value: 1500 }],
  });
});
