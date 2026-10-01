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
      max_uses_per_recipe: null,
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
    // Desktop only (ADR-0010): the supported minimum is 1280x720.
    for (const [width, height, name] of [[1280, 720, "6-min-size"]] as const) {
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
    body: JSON.stringify({ items: [
      replanEvent,
      { ...replanEvent, id: 8, status: "pending", applied_at: null },
      { ...replanEvent, id: 9, event_type: "CHANGE_SHAPE", before_entry: null, after_entry: null, reason: null, shape_change: {
        meal_type: "dinner", scope: "meal", day_indexes: [4], roles: null, removed: [], added: [], plan_shape: null,
      } },
    ] }),
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
  // A meal change names the plan's own weekday, as its preview did, never "day 4".
  const fourthDay = new Date(`${isoDay(0)}T00:00:00Z`).toLocaleDateString("en-SG", { weekday: "short", timeZone: "UTC" });
  await expect(week.getByText(`No dinner on ${fourthDay}`)).toBeVisible();
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
  // No conversation planned 9002, so a fresh one opens: conversation 51 stays in the recent list,
  // and neither its messages nor a card of the week appear inside the conversation.
  const conversation = page.getByRole("region", { name: "Conversation" });
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await expect(conversation.getByRole("region", { name: "Your week" })).toBeHidden();
  await expect(page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /Dinners for two this week/ })).toBeVisible();
});

// A conversation that planned nothing: an off-topic opener the walkthrough left behind.
const offTopic = {
  ...session(false),
  id: 60,
  status: "collecting",
  can_confirm: false,
  plan_id: null,
  messages: [
    { id: 10, role: "user", content: "something nice", created_at: "2026-09-15T08:00:00Z" },
    { id: 11, role: "assistant", content: "I plan meals and shopping. Who's eating this week?", created_at: "2026-09-15T08:00:01Z" },
  ],
  updated_at: "2026-09-15T08:00:01Z",
};
const planList = { items: [{ ...plan, purchase_total_sgd: 82.6, consumed_total_sgd: null, within_weekly_budget: true }] };

test("reopening the app opens the conversation that planned the week, not the newest one", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // The newest conversation is off topic and planned nothing; conversation 51 planned the current week.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [offTopic, session(true)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();

  const conversation = page.getByRole("region", { name: "Conversation" });
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();
  await expect(conversation.getByRole("region", { name: "Your week" })).toBeVisible();
  await expect(conversation.getByText("something nice")).toBeHidden();
  await expect(page.getByRole("complementary", { name: "This week" }).getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();

  // The off-topic conversation, opened from the list, shows only itself: no card of another week. It has
  // planned nothing, so the panel keeps the household's current week, and so does a new conversation.
  const week = page.getByRole("complementary", { name: "This week" });
  let reloaded = page.waitForRequest("**/api/plans");
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: "something nice" }).click();
  await expect(conversation.getByText("I plan meals and shopping.")).toBeVisible();
  await expect(conversation.getByRole("region", { name: "Your week" })).toBeHidden();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await reloaded;
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  reloaded = page.waitForRequest("**/api/plans");
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("I plan meals and shopping.")).toBeHidden();
  await reloaded;
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await expect(week.getByText("Your week shows up here", { exact: false })).toBeHidden();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/17-new-plan-beside-week.png` });
});

const tofu = { entry_id: 4, day_index: 4, planned_date: isoDay(0), recipe_id: 4, recipe_slug: "dinner-4", recipe_title: "Tofu Brown Rice Stir-fry" };
// The assistant's preview of a change to Thursday's tofu, not yet confirmed.
const tofuPreview = (eventType: string) => ({
  ...replanEvent,
  id: 14,
  status: "previewed",
  applied_revision: null,
  applied_at: null,
  event_type: eventType,
  reason: null,
  unavailable_ingredient: null,
  before_entry: tofu,
  after_entry: { ...tofu, recipe_id: 8, recipe_slug: "dinner-8", recipe_title: "Miso Tofu Bowl" },
});
// Conversation `base` after the household's dish action `message`: it holds week 9001 and previews the change.
const changing = (base: ReturnType<typeof session>, message: string, eventType: string) => ({
  ...base,
  status: "planned",
  plan_id: 9001,
  can_confirm: false,
  messages: [
    ...base.messages,
    { id: 20, role: "user", content: message, created_at: "2026-09-15T09:00:00Z" },
    { id: 21, role: "assistant", content: "How about Miso Tofu Bowl instead of Tofu Brown Rice Stir-fry? Nothing changes until you confirm.", created_at: "2026-09-15T09:00:01Z" },
  ],
  pending_replan: tofuPreview(eventType),
});
type Sent = Array<{ url: string; body: { message: string; plan_id: number | null } }>;

test("a dish's change on a week no conversation planned takes it on once, then goes to that conversation", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; the only conversation is off topic.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [offTopic] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(body.plan_id ? changing({ ...session(false), id: 70, messages: [] }, body.message, "REPLACE_MEAL") : session(false), 201));
  });
  await page.route("**/api/agent/sessions/*/messages", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing({ ...session(false), id: 70, messages: [] }, body.message, "CANCEL_MEAL")));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const conversation = page.getByRole("region", { name: "Conversation" });
  const dish = week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" });

  // Beside a fresh conversation, with no conversation holding the week: the dish's Swap takes that week on.
  await dish.getByRole("button", { name: "Swap" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(conversation.getByText("How about Miso Tofu Bowl")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.url).toMatch(/\/api\/agent\/sessions$/);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Swap \w+day's Tofu Brown Rice Stir-fry for something else$/), plan_id: 9001 });

  // Beside the off-topic conversation, the week's Skip goes to the conversation that now holds the week,
  // which opens: the off-topic one never takes it on as well.
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: "something nice" }).click();
  await expect(conversation.getByText("I plan meals and shopping.")).toBeVisible();
  await dish.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1]!.url).toMatch(/\/api\/agent\/sessions\/70\/messages$/);
  expect(sent[1]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Tofu Brown Rice Stir-fry$/), plan_id: null });
  await expect(conversation.getByText("I plan meals and shopping.")).toBeHidden();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/18-week-taken-on.png` });

  // A dish's words typed over with a new request plan as before, like any typed message.
  await page.getByRole("button", { name: /New plan/ }).click();
  await dish.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(/^Skip /);
  await page.getByLabel("Message MealCraft").selectText();
  await page.keyboard.type("Dinners for three next week");
  await page.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(3);
  expect(sent[2]!.url).toMatch(/\/api\/agent\/sessions$/);
  expect(sent[2]!.body).toEqual({ message: "Dinners for three next week", plan_id: null });
});

test("a dish's change beside a new conversation goes to the conversation that planned the week", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Conversation 51 planned the current week.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(true)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions", (route) => {
    sent.push({ url: route.request().url(), body: route.request().postDataJSON() });
    return route.fulfill(json(session(false), 201));
  });
  await page.route("**/api/agent/sessions/51/messages", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing(session(true), body.message, "REPLACE_MEAL")));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const conversation = page.getByRole("region", { name: "Conversation" });
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();

  // New plan, then a dish's Swap: the request goes to conversation 51, which opens with the week.
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Swap" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(conversation.getByText("How about Miso Tofu Bowl")).toBeVisible();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.url).toMatch(/\/api\/agent\/sessions\/51\/messages$/);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Swap \w+day's Tofu Brown Rice Stir-fry for something else$/), plan_id: null });
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();

  // Back to it from Recent after another new plan: it comes back as it was left, preview included.
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("How about Miso Tofu Bowl")).toBeHidden();
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /Dinners for two this week/ }).click();
  await expect(conversation.getByText("How about Miso Tofu Bowl")).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
});

test("switching between two conversations that hold the same week keeps that week in the panel", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Conversation 51 planned week 9001; the newer 70 took it on with a dish's Swap (possible before one
  // conversation held a week, and still when the planning conversation is not among the recent ones).
  const tookOn = {
    ...session(true),
    id: 70,
    messages: [
      { id: 30, role: "user", content: "Swap Thursday's Tofu Brown Rice Stir-fry for something else", created_at: "2026-09-15T09:00:00Z" },
      { id: 31, role: "assistant", content: "Done: Miso Tofu Bowl on Thursday.", created_at: "2026-09-15T09:00:01Z" },
    ],
    updated_at: "2026-09-15T09:00:01Z",
  };
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [tookOn, session(true)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const conversation = page.getByRole("region", { name: "Conversation" });
  const recent = page.getByRole("complementary", { name: "Navigation" });
  await expect(conversation.getByText("Done: Miso Tofu Bowl on Thursday.")).toBeVisible();
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();

  for (const [title, line] of [[/^Dinners for two this week/, "Seven dinners for S$82.60"], [/^Swap Thursday's/, "Done: Miso Tofu Bowl on Thursday."]] as const) {
    await recent.getByRole("button", { name: title }).click();
    await expect(conversation.getByText(line)).toBeVisible();
    await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
    await expect(week.getByText("Your week shows up here", { exact: false })).toBeHidden();
    await expect(conversation.getByRole("region", { name: "Your week" })).toBeVisible();
  }
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/19-same-week-switch.png` });
});

test("a conversation ready to plan asks before a dish's change takes the current week on", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; conversation 51 is ready to plan a new week.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(false)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions/51/messages", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing(session(false), body.message, "CANCEL_MEAL")));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const dish = week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" });
  const question = page.getByLabel("Change the current week here?");
  await expect(page.getByRole("button", { name: "Plan my week" })).toBeVisible();

  // Asked first; keeping the plan sends nothing and keeps "Plan my week".
  await dish.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(question).toBeVisible();
  if (SHOTS) await page.waitForTimeout(700).then(() => page.screenshot({ path: `${SHOTS}/20-ask-before-taking-on.png` }));
  await question.getByRole("button", { name: "Keep planning" }).click();
  await expect(question).toBeHidden();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue("");
  await expect(page.getByRole("button", { name: "Plan my week" })).toBeVisible();
  expect(sent).toHaveLength(0);

  // Said yes: the conversation takes the week on and previews the change.
  await dish.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await question.getByRole("button", { name: "Change the current week" }).click();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Tofu Brown Rice Stir-fry$/), plan_id: 9001 });
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

test("asking for lunch too previews the new meals, then asks whether to keep it", async ({ page }) => {
  await stubApi(page);
  const dish = (day: number, title: string) => ({
    entry_id: 0, day_index: day, meal_type: "lunch", role_id: "main", portion_share: 1, recipe_id: 100 + day,
    recipe_slug: `lunch-${day}`, recipe_title: title, status: "planned", is_locked: false, recommendation_score: 80,
  });
  const change = {
    ...replanEvent,
    id: 12,
    applied_revision: null,
    status: "previewed",
    event_type: "CHANGE_SHAPE",
    before_entry: null,
    after_entry: null,
    purchase_total_delta_sgd: 21.4,
    shape_change: {
      meal_type: "lunch",
      scope: "week",
      day_indexes: [1, 2],
      roles: [{ role_id: "main", courses: ["main", "salad", "soup"], required: true }],
      removed: [],
      added: [dish(1, "Chicken Soba Salad"), dish(2, "Lentil Soup")],
      plan_shape: null,
    },
  };
  const planned = session(true);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/agent/sessions/51/messages", route => route.fulfill(json({ ...planned, pending_replan: change })));
  await page.route("**/api/agent/sessions/51/replan/confirm", route => route.fulfill(json({
    session: {
      ...planned,
      pending_interaction: {
        type: "quick_reply",
        prompt: "Should new weeks plan meals this way too?",
        field_path: "plan_shape.keep",
        question_id: "keep-shape-12",
        options: [{ id: "keep", label: "Keep it as our usual", value: "keep" }, { id: "week", label: "Just this week", value: "week" }],
        allow_free_text: false,
        context_version: 2,
      },
    },
    event: { ...change, status: "applied" },
    plan,
  })));
  let answer: { option_ids?: string[] } | null = null;
  await page.route("**/api/agent/sessions/51/interactions", async (route) => {
    answer = route.request().postDataJSON();
    await route.fulfill(json(planned));
  });

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await page.getByLabel("Message MealCraft").fill("Also plan lunch");
  await page.getByRole("button", { name: "Send" }).click();

  const card = page.getByLabel("Proposed change to your meals");
  await expect(card.getByText("Lunch added for the rest of the week")).toBeVisible();
  await expect(card.getByText("Chicken Soba Salad")).toBeVisible();
  await expect(card.getByText("groceries +S$21.40")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/15-shape-change.png` });

  await card.getByRole("button", { name: "Confirm change" }).click();
  await page.getByRole("button", { name: "Keep it as our usual" }).click();
  await expect.poll(() => answer?.option_ids).toEqual(["keep"]);
});

test("a dish's own buttons put the change into words for the assistant", async ({ page }) => {
  await stubApi(page);
  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();

  const week = page.getByRole("complementary", { name: "This week" });
  const actions = week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" });
  await actions.getByRole("button", { name: "Keep" }).click();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(/^Lock \w+day's Tofu Brown Rice Stir-fry$/);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/16-dish-actions.png` });
  // A cooked dinner offers nothing to change.
  await expect(week.getByRole("group", { name: "Change Lemon Herb Chicken Rice Bowl" })).toHaveCount(0);
});

test("keeping a dish previews as keeping it, and the change log shows it once confirmed", async ({ page }) => {
  await stubApi(page);
  const tofu = { entry_id: 4, day_index: 4, planned_date: isoDay(0), recipe_id: 4, recipe_slug: "dinner-4", recipe_title: "Tofu Brown Rice Stir-fry" };
  const lock = {
    ...replanEvent,
    id: 13,
    applied_revision: null,
    status: "previewed",
    event_type: "LOCK_MEAL",
    reason: null,
    unavailable_ingredient: null,
    before_entry: tofu,
    after_entry: tofu,
    nutrition_delta: { calories_kcal: 0, protein_g: 0, carbohydrate_g: 0, fat_g: 0, sodium_mg: 0, sugar_g: 0 },
    purchase_total_delta_sgd: 0,
  };
  const planned = session(true);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  let applied = false;
  await page.route("**/api/plans/9001", route => route.fulfill(json(applied ? { ...plan, revision: 2 } : plan)));
  await page.route("**/api/plans/9001/events", route => route.fulfill(json({ items: applied ? [{ ...lock, status: "applied", applied_revision: 2 }] : [] })));
  await page.route("**/api/agent/sessions/51/messages", route => route.fulfill(json({ ...planned, pending_replan: lock })));
  await page.route("**/api/agent/sessions/51/replan/confirm", (route) => {
    applied = true;
    return route.fulfill(json({ session: planned, event: { ...lock, status: "applied" }, plan: { ...plan, revision: 2 } }));
  });

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  await expect(week.getByText("Changes this week")).toHaveCount(0);

  await page.getByLabel("Message MealCraft").fill("Lock Thursday's Tofu Brown Rice Stir-fry");
  await page.getByRole("button", { name: "Send" }).click();
  // Not a swap from the dish to itself.
  await expect(page.getByText("Keep Tofu Brown Rice Stir-fry as it is")).toBeVisible();
  await expect(page.locator(".swap-card s")).toHaveCount(0);

  await page.getByRole("button", { name: "Confirm change" }).click();
  await week.getByText("Changes this week").click();
  await expect(week.getByText("Keep Tofu Brown Rice Stir-fry as it is")).toBeVisible();
});
