import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.HOME_SURFACE_SHOTS;

function isoDay(offset: number) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return day.toLocaleDateString("en-CA");
}

const dinners: Array<[string, number, number, number]> = [
  ["Lemon Herb Chicken Rice Bowl", 540, 38, 40],
  ["Chickpea Tomato Stew", 405, 17, 35],
  ["Salmon Quinoa Bowl", 590, 44, 35],
  ["Tofu Brown Rice Stir-fry", 500, 24, 35],
  ["Mushroom Spinach Pasta", 465, 18, 30],
  ["Chicken Broccoli Rice", 565, 41, 35],
  ["Lentil Sweet Potato Curry", 445, 19, 50],
];

const days = dinners.map(([title, kcal, protein, minutes], index) => ({
  entry_id: index + 1,
  day_index: index + 1,
  planned_date: isoDay(index - 3),
  recipe: {
    id: index + 1,
    slug: `dinner-${index + 1}`,
    title,
    description: "",
    cuisine: "Home",
    meal_type: "dinner",
    servings: 2,
    total_time_minutes: minutes,
    dietary_tags: [],
    nutrition: { calories_kcal: kcal, protein_g: protein, carbohydrate_g: 50, fat_g: 15, sodium_mg: 600, sugar_g: 6 },
  },
  status: index < 3 ? "completed" : "planned",
  is_locked: false,
  consumed_at: null,
  nutrition_per_person: { calories_kcal: kcal, protein_g: protein, carbohydrate_g: 50, fat_g: 15, sodium_mg: 600, sugar_g: 6 },
}));

function grocery(name: string, category: string, cost: number, size: number, packages = 1) {
  return {
    ingredient_name: name.toLowerCase().replaceAll(" ", "_"),
    ingredient_display_name: name,
    required_quantity: size * packages,
    unit: "g",
    pantry_deduction: 0,
    remaining_quantity: size * packages,
    product: { category, package_size: size, package_unit: "g", fetched_at: "2026-09-14T08:00:00Z", source: "fixture" },
    match_score: 1,
    packages_required: packages,
    purchase_cost_sgd: cost,
    consumed_cost_sgd: cost,
    excess_quantity: 0,
    note: null,
  };
}

const plan = {
  id: 9001,
  revision: 1,
  household_profile_id: null,
  household_profile_version: null,
  replaces_plan_id: null,
  start_date: isoDay(-3),
  end_date: isoDay(3),
  day_count: 7,
  household_size: 2,
  days,
  nutrition_summary_per_person: days[0]!.nutrition_per_person,
  grocery_estimate: {
    pricing_mode: "fixture",
    complete: true,
    purchase_total_sgd: 82.6,
    consumed_total_sgd: 70.1,
    weekly_budget_sgd: 90,
    within_weekly_budget: true,
    items: [
      grocery("Chicken breast", "Meat & Seafood", 10.15, 800),
      grocery("Salmon fillet", "Meat & Seafood", 10.9, 300),
      grocery("Broccoli", "Fruit & Vegetables", 5.8, 300, 2),
      grocery("Baby spinach", "Fruit & Vegetables", 4.6, 400),
      grocery("Chickpeas", "Pantry", 2.1, 400),
      grocery("Red lentils", "Pantry", 3.4, 500),
    ],
    unmapped_ingredients: [],
    warnings: [],
  },
  warnings: [],
  created_at: "2026-09-14T08:00:00Z",
};

const dashboard = {
  plan_id: 9001,
  revision: 1,
  start_date: plan.start_date,
  end_date: plan.end_date,
  household_size: 2,
  completion_rate: 3 / 7,
  status_counts: { planned: 4, completed: 3, skipped: 0 },
  nutrition_targets: { calories_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
  planned_nutrition_per_person: { calories_kcal: 3510, protein_g: 201, carbohydrate_g: 350, fat_g: 105, sodium_mg: 4200, sugar_g: 42 },
  completed_nutrition_per_person: { calories_kcal: 1535, protein_g: 99, carbohydrate_g: 150, fat_g: 45, sodium_mg: 1800, sugar_g: 18 },
  days,
};

function session(planned: boolean) {
  return {
    id: 51,
    status: planned ? "planned" : "ready",
    parser_provider: "fixture",
    constraints: {
      household_size: 2,
      max_cooking_time_minutes: 60,
      budget_per_meal_sgd: null,
      weekly_budget_sgd: 90,
      allergens: [],
      excluded_ingredients: [],
      dietary_preferences: [],
      health_preferences: [],
      nutrition_targets: { calories_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
      max_sodium_mg_per_meal: null,
      available_ingredients: [{ normalized_name: "brown_rice", quantity: 500, unit: "g" }],
      pricing_mode: "fixture",
    },
    missing_fields: [],
    clarification_questions: [],
    messages: [
      { id: 1, role: "user", content: "Dinners for two this week, around S$90. We still have brown rice at home.", created_at: "2026-09-14T08:00:00Z" },
      { id: 2, role: "assistant", content: planned ? "Seven dinners for S$82.60, about 500 kcal a night. Your brown rice covers every rice dish." : "Got it: 2 people, S$90 for the week, brown rice at home. Ready when you are.", created_at: "2026-09-14T08:00:01Z" },
    ],
    plan_id: planned ? 9001 : null,
    replan_draft: { event_type: null, entry_id: null, unavailable_ingredient: null, reason: null },
    pending_replan: null,
    context_version: 2,
    last_scope_decision: null,
    pending_interaction: null,
    can_confirm: !planned,
    created_at: "2026-09-14T08:00:00Z",
    updated_at: "2026-09-14T08:00:01Z",
  };
}

async function stubApi(page: Page) {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "user" },
    active_household_id: 1,
    household_role: "owner",
  })));
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [] })));
  await page.route("**/api/household-profiles/current", route => route.fulfill({ status: 404, contentType: "application/json", body: "{}" }));
  await page.route("**/api/agent/sessions", route => route.fulfill({ ...json(session(false)), status: 201 }));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: session(true), plan })));
  await page.route("**/api/plans/9001", route => route.fulfill(json(plan)));
  await page.route("**/api/plans/9001/dashboard", route => route.fulfill(json(dashboard)));
  await page.route("**/api/plans/9001/events", route => route.fulfill(json({ items: [] })));
  await page.route("**/api/recipes/*/tutorial", route => route.fulfill(json({
    recipe_slug: "dinner-4",
    recipe_title: "Tofu Brown Rice Stir-fry",
    selected_video: null,
    retrieval: { provider_used: "fixture", mode: "fixture", status: "success" },
    warning: null,
  })));
}

test("sending from the film entry opens the workspace with the week beside the chat", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  await page.goto("/");
  await page.locator("video").evaluate(video => (video as HTMLVideoElement).pause());
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/1-landing.png` });

  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90. We still have brown rice at home.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Ready when you are.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Plan the week/ })).toBeHidden();
  const week = page.getByRole("complementary", { name: "This week" });
  await expect(week.getByText("Your week shows up here once it's planned", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await expect(page.getByText("Seven dinners for S$82.60")).toBeVisible();

  // The week sits in its own column: nothing overlaps the conversation.
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  const chat = await page.getByRole("region", { name: "Conversation" }).boundingBox();
  const panel = await week.boundingBox();
  expect(chat!.x + chat!.width).toBeLessThanOrEqual(panel!.x + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect(page.getByRole("region", { name: "Your week" }).getByText("Seven dinners,")).toBeVisible();
  await page.waitForTimeout(1200);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/2-workspace.png` });

  await expect(week.getByText("S$82.60")).toBeVisible();
  await expect(week.getByText("S$7.40 under your S$90.00")).toBeVisible();
  await week.getByRole("tab", { name: /Groceries/ }).click();
  await expect(week.getByText("Salmon fillet")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/3-groceries.png` });

  await week.getByRole("button", { name: "Preview list" }).click();
  const sheet = page.getByRole("dialog", { name: "Shopping list preview" });
  await expect(sheet.getByText("Estimated total")).toBeVisible();
  await expect(sheet.getByText("Sample prices", { exact: false })).toBeVisible();
  await page.waitForTimeout(600);
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/4-preview.png` });
    await page.pdf({ path: `${SHOTS}/5-list.pdf`, format: "A4" });
    await page.getByRole("button", { name: "Back", exact: true }).click();
    for (const [width, height, name] of [[1280, 720, "6-min-size"], [900, 900, "7-tablet"], [390, 844, "8-phone"]] as const) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(500);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: `${SHOTS}/${name}.png` });
    }
  }
});

async function planWeek(page: Page) {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await expect(page.getByText("Seven dinners for S$82.60")).toBeVisible();
}

test("a clarification option sends a stable structured answer", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  const asking = {
    ...session(false),
    status: "collecting",
    can_confirm: false,
    constraints: { ...session(false).constraints, household_size: null },
    messages: [{ id: 1, role: "user", content: "Plan dinners under S$15 per meal.", created_at: "2026-09-14T08:00:00Z" }],
    context_version: 1,
    pending_interaction: {
      type: "single_select",
      prompt: "How many people should this plan serve?",
      field_path: "household_size",
      question_id: "context-1:household_size",
      options: [
        { id: "household_size_1", label: "1 person", value: 1 },
        { id: "household_size_2", label: "2 people", value: 2 },
      ],
      allow_free_text: true,
      context_version: 1,
      plan_revision: null,
      expires_at: null,
    },
  };
  await page.route("**/api/agent/sessions", route => route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(asking) }));
  let answer: unknown = null;
  await page.route("**/api/agent/sessions/51/interactions", async (route) => {
    answer = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(session(false)) });
  });

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Plan dinners under S$15 per meal.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "2 people" }).click();

  await expect(page.getByRole("button", { name: "Plan my week" })).toBeVisible();
  expect(answer).toEqual({
    question_id: "context-1:household_size",
    option_ids: ["household_size_2"],
    free_text: null,
    context_version: 1,
    plan_revision: null,
  });
});

test("nutrition details show all six nutrients and let a dinner be skipped", async ({ page }) => {
  await planWeek(page);
  let patched: unknown = null;
  await page.route("**/api/plans/9001/entries/5", async (route) => {
    patched = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(plan) });
  });

  await page.getByRole("tab", { name: "Nutrition" }).click();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/9-nutrition-tab.png` });
  await page.getByRole("button", { name: "All six nutrients & daily detail" }).click();
  const details = page.getByRole("dialog", { name: "Nutrition details" });
  for (const label of ["Calories", "Protein", "Carbohydrate", "Fat", "Sodium", "Sugar"]) {
    await expect(details.getByRole("button", { name: new RegExp(`^${label}`) })).toBeVisible();
  }
  await expect(details.getByText("Actual").first()).toBeVisible();
  if (SHOTS) await page.waitForTimeout(500).then(() => page.screenshot({ path: `${SHOTS}/10-nutrition.png` }));
  await details.getByRole("row", { name: /Mushroom Spinach Pasta/ }).getByRole("button", { name: "Skip" }).click();
  await expect.poll(() => patched).toEqual({ status: "skipped" });
});

test("a dinner opens its recipe with steps on the same surface", async ({ page }) => {
  await planWeek(page);
  await page.route("**/api/recipes/dinner-4", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ...days[3]!.recipe,
      ingredients: [
        { name: "Firm tofu", normalized_name: "firm_tofu", quantity: 300, unit: "g", preparation: "cubed", allergens: ["soy"] },
        { name: "Brown rice", normalized_name: "brown_rice", quantity: 150, unit: "g", preparation: null, allergens: [] },
      ],
      steps: [{ step_number: 1, instruction: "Cook the rice." }, { step_number: 2, instruction: "Stir-fry the tofu." }],
    }),
  }));

  await page.getByRole("button", { name: "Recipe & steps" }).click();
  const recipe = page.getByRole("dialog", { name: "Tofu Brown Rice Stir-fry" });
  await expect(recipe.getByText("Stir-fry the tofu.")).toBeVisible();
  await expect(recipe.getByText("Contains soy")).toBeVisible();
  await expect(recipe.getByText(/Allergens come from ingredient data/)).toBeVisible();
  if (SHOTS) await page.waitForTimeout(500).then(() => page.screenshot({ path: `${SHOTS}/11-recipe.png` }));
});

test("a failed request says so in the conversation", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  await page.route("**/api/agent/sessions", route => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "The planning service is unavailable." }),
  }));

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByRole("alert")).toHaveText("The planning service is unavailable.");
});

const replanEvent = {
  id: 7,
  plan_id: 9001,
  base_revision: 1,
  applied_revision: 2,
  event_type: "meal_change",
  status: "applied",
  reason: "Salmon was out of stock",
  unavailable_ingredient: "salmon",
  before_entry: { entry_id: 3, day_index: 3, planned_date: isoDay(-1), recipe_id: 3, recipe_slug: "dinner-3", recipe_title: "Salmon Quinoa Bowl" },
  after_entry: { entry_id: 3, day_index: 3, planned_date: isoDay(-1), recipe_id: 8, recipe_slug: "dinner-8", recipe_title: "Miso Tofu Bowl" },
  nutrition_delta: { calories_kcal: -85, protein_g: -6, carbohydrate_g: 4, fat_g: -5, sodium_mg: 120, sugar_g: 1 },
  grocery_delta: [],
  purchase_total_delta_sgd: -2.4,
  created_at: "2026-09-14T09:00:00Z",
  applied_at: "2026-09-14T09:01:00Z",
};

test("a week still loading shows a skeleton rather than the empty message", async ({ page }) => {
  await stubApi(page);
  // Hold the plan request open so the loading state is observable.
  let release = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/plans/9001", async (route) => {
    await held;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(plan) });
  });

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();

  const week = page.getByRole("complementary", { name: "This week" });
  await expect(week.locator("[aria-busy='true']")).toBeVisible();
  await expect(week.getByText("Your week shows up here once it's planned", { exact: false })).toBeHidden();
  if (SHOTS) await page.waitForTimeout(700).then(() => page.screenshot({ path: `${SHOTS}/12-loading.png` }));

  release();
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await expect(week.locator("[aria-busy='true']")).toBeHidden();
});

test("a week that failed to load offers a retry that works", async ({ page }) => {
  await stubApi(page);
  // The fetch layer retries a GET on its own, so the stub fails until the test
  // says otherwise rather than counting attempts.
  let failing = true;
  await page.route("**/api/plans/9001", async (route) => {
    if (failing) return route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(plan) });
  });

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();

  const week = page.getByRole("complementary", { name: "This week" });
  await expect(week.getByText("Your week couldn't be loaded.")).toBeVisible();
  failing = false;
  await week.getByRole("button", { name: "Try again" }).click();
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
});

test("Escape closes a sheet from anywhere and focus goes back to what opened it", async ({ page }) => {
  await planWeek(page);
  await page.getByRole("tab", { name: "Nutrition" }).click();
  const opener = page.getByRole("button", { name: "All six nutrients & daily detail" });
  await opener.click();

  const details = page.getByRole("dialog", { name: "Nutrition details" });
  await expect(details).toBeVisible();
  // Focus starts inside the sheet, not on the page behind it.
  await expect(details.locator(":focus")).toBeVisible();

  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Escape");
  await expect(details).toBeHidden();
  await expect(opener).toBeFocused();
});

test("applied changes are listed in the week panel", async ({ page }) => {
  await stubApi(page);
  await page.route("**/api/plans/9001/events", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [replanEvent, { ...replanEvent, id: 8, status: "pending", applied_at: null }] }),
  }));
  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();

  const week = page.getByRole("complementary", { name: "This week" });
  const summary = week.getByText("Changes this week");
  await expect(summary).toBeVisible();
  await expect(week.getByText("Miso Tofu Bowl")).toBeHidden();
  await summary.click();
  await expect(week.getByText("Miso Tofu Bowl")).toBeVisible();
  await expect(week.getByText("Salmon was out of stock")).toBeVisible();
  // A pending suggestion is not history: only the applied event is listed.
  await expect(week.getByText("Miso Tofu Bowl")).toHaveCount(1);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/13-changes.png` });
});

test("opening the app shows the newest plan, and says when that week has ended", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  // The last conversation made plan 9001; a newer week, 9002, was planned on the household page and has ended.
  const ended = { ...plan, id: 9002, start_date: isoDay(-10), end_date: isoDay(-4), days: days.map(day => ({ ...day, recipe: { ...day.recipe, title: `Old ${day.recipe.title}` } })) };
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(true)] })));
  await page.route("**/api/plans", route => route.fulfill(json({ items: [{ ...ended, purchase_total_sgd: 80, consumed_total_sgd: null, within_weekly_budget: true }, { ...plan, purchase_total_sgd: 82.6, consumed_total_sgd: null, within_weekly_budget: true }] })));
  await page.route("**/api/plans/9002", route => route.fulfill(json(ended)));
  await page.route("**/api/plans/9002/dashboard", route => route.fulfill(json({ ...dashboard, plan_id: 9002, start_date: ended.start_date, end_date: ended.end_date, days: ended.days })));
  await page.route("**/api/plans/9002/events", route => route.fulfill(json({ items: [] })));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  await expect(week.getByText("Old Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await page.waitForTimeout(600);
  await expect(week.getByText("Old Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await expect(page.getByText(/This plan ended on .* plan a new one\./)).toBeVisible();
});

test("a session that expires mid-sentence keeps the draft and comes back to it", async ({ page }) => {
  await planWeek(page);
  await page.route("**/api/agent/sessions/51/messages", route => route.fulfill({ status: 401, contentType: "application/json", body: "{}" }));
  await page.getByLabel("Message MealCraft").fill("Can Friday be vegetarian?");
  await page.getByRole("button", { name: "Send" }).click();
  await page.waitForURL(url => url.pathname === "/login" && url.searchParams.get("next") === "/");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  // Signing in again (the stubbed session is valid again) returns to the home page with the draft.
  await page.goto("/");
  await page.getByRole("button", { name: "Open my week" }).click();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue("Can Friday be vegetarian?");
});
