import { expect, test, type Page } from "@playwright/test";

const SHOTS = process.env.HOME_SURFACE_SHOTS;

test("a long shopping list exports every category and its items for print review", async ({ page }, testInfo) => {
  await stubApi(page);
  const items = Array.from({ length: 24 }, (_, i) => grocery(`Print item ${i + 1}`, `Print category ${i + 1}`, 3, 500));
  const printPlan = { ...plan, grocery_estimate: { ...plan.grocery_estimate, items } };
  await page.route("**/api/plans/9001", route => route.fulfill({ json: printPlan }));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill({ json: { session: session(true), plan: printPlan } }));
  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await page.getByRole("button", { name: "Preview list", exact: true }).click();
  await expect(page.locator(".mc-print-sheet li")).toHaveCount(24);
  await page.evaluate(() => document.fonts.ready);
  for (const printBackground of [false, true]) {
    const path = testInfo.outputPath(`shopping-background-${printBackground}.pdf`);
    await page.pdf({ path, format: "A4", printBackground });
    await testInfo.attach(`shopping-background-${printBackground}`, { path, contentType: "application/pdf" });
  }
});

test("New plan keeps its fresh draft when the previous conversation's delayed reply arrives", async ({ page }) => {
  await stubApi(page);
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/agent/sessions", async (route) => {
    await delayed;
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(session(false)) });
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByLabel("MealCraft is thinking")).toBeVisible();
  await page.getByRole("button", { name: /New plan/ }).click();
  const fresh = "A fresh week for three people";
  await page.getByLabel("Message MealCraft").fill(fresh);
  const oldResponse = page.waitForResponse(response => response.url().endsWith("/api/agent/sessions") && response.request().method() === "POST");
  release();
  await oldResponse;
  await expect(page.getByLabel("MealCraft is thinking")).toBeHidden();
  await expect(page.getByRole("heading", { name: "New plan", exact: true })).toBeVisible();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(fresh);
  await expect(page.getByText("Ready when you are.")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Plan my week" })).toHaveCount(0);
});

test("New plan supersedes an initial week reopen that has not listed the household's plans yet", async ({ page }) => {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/**", route => route.fulfill(json({ items: [] })));
  await stubApi(page);
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  let plansRequests = 0;
  let restoreRequests = 0;
  await page.route("**/api/plans", async (route) => {
    if (++plansRequests === 1) await delayed;
    await route.fulfill(json({ items: [{ ...plan, current: true }] }));
  });
  await page.route("**/api/agent/sessions?limit=8", (route) => {
    restoreRequests += 1;
    return route.fulfill(json({ items: [session(true)] }));
  });
  const sent: string[] = [];
  await page.route("**/api/agent/sessions", (route) => {
    sent.push(route.request().postDataJSON().message);
    return route.fulfill({ ...json(session(false)), status: 201 });
  });
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await expect.poll(() => plansRequests).toBe(1);
  await page.getByRole("button", { name: /New plan/ }).click();
  const fresh = "Dinners for a fresh household of three";
  await page.getByLabel("Message MealCraft").fill(fresh);
  await expect(page.getByRole("button", { name: "Send", exact: true })).toBeEnabled();
  const initialResponse = page.waitForResponse(response => response.url().endsWith("/api/plans") && response.request().method() === "GET");
  release();
  await initialResponse;
  await expect(page.getByRole("heading", { name: "New plan", exact: true })).toBeVisible();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(fresh);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect.poll(() => sent).toEqual([fresh]);
  expect(restoreRequests).toBe(0);
});

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
  await page.route("**/api/plans", route => route.fulfill(json({ items: [] })));
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

test("Groceries and Nutrition use the plan panel while Meals keeps Today at 1280x720", async ({ page }) => {
  await planWeek(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  const panel = page.getByRole("complementary", { name: "This week" });
  await expect(panel.getByRole("region", { name: "Next meal" })).toBeVisible();
  await panel.getByRole("tab", { name: "Nutrition", exact: true }).click();
  await expect(panel.getByRole("region", { name: "Next meal" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: /All six nutrients/ })).toBeInViewport();
  await panel.getByRole("tab", { name: "Meals", exact: true }).click();
  await expect(panel.getByRole("region", { name: "Next meal" })).toBeVisible();
  await panel.getByRole("tab", { name: /Groceries/ }).click();
  await expect(panel.getByRole("region", { name: "Next meal" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Preview list" })).toBeInViewport();
});

// A conversation still asking what it needs to plan a new week: who the plan serves.
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

test("a Chinese clarification keeps an English composer placeholder", async ({ page }) => {
  await stubApi(page);
  await page.route("**/api/agent/sessions", route => route.fulfill({
    status: 201, contentType: "application/json", body: JSON.stringify({
      ...asking,
      messages: [{ id: 2, role: "assistant", content: "这份计划供几个人吃？", created_at: "2026-09-14T08:00:00Z" }],
      pending_interaction: { ...asking.pending_interaction, prompt: "选一个，或者直接输入" },
    }),
  }));
  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("安排一周晚餐");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByLabel("Message MealCraft")).toHaveAttribute("placeholder", "Choose an option, or type your answer…");
  await expect(page.getByText("这份计划供几个人吃？", { exact: true })).toBeVisible();
});

for (const outcome of ["success", "error"] as const) {
  test(`an incoming week's dashboard ${outcome} never displays the previous week's dishes`, async ({ page }) => {
    await planWeek(page);
    const week = page.getByRole("complementary", { name: "This week" });
    await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
    let release = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    const updatedDays = days.map(day => ({ ...day, recipe: { ...day.recipe, title: `New ${day.recipe.title}` } }));
    await page.route("**/api/plans/9002", route => route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify({ ...plan, id: 9002, days: updatedDays }),
    }));
    await page.route("**/api/plans/9002/events", route => route.fulfill({ json: { items: [] } }));
    await page.route("**/api/plans/9002/dashboard", async (route) => {
      await held;
      await route.fulfill(outcome === "error"
        ? { status: 500, json: { detail: "Dashboard unavailable" } }
        : { json: { ...dashboard, plan_id: 9002, days: updatedDays } });
    });
    await page.route("**/api/agent/sessions/51/messages", route => route.fulfill({ json: { ...session(true), plan_id: 9002 } }));
    try {
      await page.getByLabel("Message MealCraft").fill("Use the updated week");
      await page.getByRole("button", { name: "Send" }).click();
      await expect(week.locator("[aria-busy='true']")).toBeVisible();
      await expect(week.getByText("Tofu Brown Rice Stir-fry", { exact: true })).toBeHidden();
    }
    finally { release(); }
    if (outcome === "error") await expect(week.getByRole("alert")).toBeVisible();
    else await expect(week.getByText("New Tofu Brown Rice Stir-fry").first()).toBeVisible();
    await expect(week.getByText("Tofu Brown Rice Stir-fry", { exact: true })).toBeHidden();
  });
}

test("a clarification option sends a stable structured answer", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
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
  await page.getByLabel("Nutrition day", { exact: true }).selectOption("1");
  const nutritionTable = page.getByRole("table", { name: "Nutrition per person for the selected day and meal" });
  await expect(nutritionTable).toBeVisible();
  await expect(nutritionTable.getByRole("row")).toHaveCount(7);
  await expect(nutritionTable.getByRole("row").nth(1).getByRole("cell")).toHaveText(["540 kcal", "540 kcal"]);
  await expect(page.locator(".bar-row")).toHaveCount(0);
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

for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }]) {
  test(`week overview and composer have room at ${viewport.width}`, async ({ page }) => {
    await planWeek(page);
    await page.setViewportSize(viewport);
    const overview = page.getByRole("list", { name: "Week overview" });
    await expect(overview.getByRole("listitem")).toHaveCount(7);
    const body = await page.getByRole("tabpanel").boundingBox();
    const last = await overview.getByRole("listitem").last().boundingBox();
    expect(last!.y + last!.height).toBeLessThanOrEqual(body!.y + body!.height);
    const context = await page.locator(".composer-wrap .context").boundingBox();
    const input = await page.getByLabel("Message MealCraft").boundingBox();
    expect(context).not.toBeNull();
    expect(context!.y + context!.height).toBeLessThanOrEqual(input!.y);
    await expect(overview.locator("[title]").first()).toHaveAttribute("title", /Lemon Herb Chicken Rice Bowl/);
  });
  test(`dish actions stay on one row at ${viewport.width}`, async ({ page }) => {
    await planWeek(page);
    await page.setViewportSize(viewport);
    const week = page.getByRole("complementary", { name: "This week" });
    const actions = week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" });
    await expect(actions.getByRole("button")).toHaveCount(4);
    const boxes = await actions.getByRole("button").evaluateAll(buttons => buttons.map(button => {
      const rect = button.getBoundingClientRect();
      return { top: rect.top, right: rect.right };
    }));
    expect(new Set(boxes.map(box => Math.round(box.top))).size).toBe(1);
    const panel = await week.boundingBox();
    expect(Math.max(...boxes.map(box => box.right))).toBeLessThanOrEqual(panel!.x + panel!.width);
    const heading = page.locator(".chat-head").getByRole("heading", { level: 1 });
    await expect(heading).toHaveAttribute("title", await heading.innerText());
  });
  test(`all six nutrients fit without scrolling at ${viewport.width}`, async ({ page }) => {
    await planWeek(page);
    await page.setViewportSize(viewport);
    await page.getByRole("tab", { name: "Nutrition" }).click();
    const table = page.getByRole("table", { name: "Nutrition per person for the selected day and meal" });
    await expect(table.getByRole("row")).toHaveCount(7);
    const body = page.getByRole("tabpanel");
    const bounds = await body.boundingBox();
    const lastRow = await table.getByRole("row").last().boundingBox();
    expect(bounds).not.toBeNull();
    expect(lastRow).not.toBeNull();
    expect(lastRow!.y + lastRow!.height).toBeLessThanOrEqual(bounds!.y + bounds!.height);
    expect(lastRow!.y + lastRow!.height).toBeLessThanOrEqual(viewport.height);
    await expect(page.getByRole("button", { name: "Recipe & steps" })).toHaveCount(0);
  });
}

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

test("a failed current-week lookup shows an error and can be retried", async ({ page }) => {
  await stubApi(page);
  let failing = true;
  await page.route("**/api/plans", route => route.fulfill(failing
    ? { status: 500, json: { detail: "Temporarily unavailable" } }
    : { json: { items: [] } }));
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  await expect(week.getByRole("alert")).toBeVisible();
  await expect(week.getByRole("heading", { name: "No plan yet" })).toHaveCount(0);
  failing = false;
  await week.getByRole("button", { name: "Try again" }).click();
  await expect(week.getByRole("heading", { name: "No plan yet" })).toBeVisible();
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
  await expect(week.locator("details").getByText(`No dinner on ${fourthDay}`)).toBeVisible();
  await summary.click();
  await page.getByRole("tab", { name: "Nutrition" }).click();
  const latest = week.getByRole("status", { name: "Latest plan change" });
  await expect(latest).toContainText(`No dinner on ${fourthDay}`);
  await expect(latest).toBeInViewport();
  await expect(week.locator("details")).not.toHaveAttribute("open", "");
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

test("a replaced week's clarification and composer are read-only", async ({ page }) => {
  await stubApi(page);
  await page.route("**/api/plans", route => route.fulfill({ json: {
    items: [{ ...planList.items[0], current: false }],
  } }));
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill({ json: {
    items: [{ ...session(true), pending_interaction: asking.pending_interaction }],
  } }));
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await expect(page.getByRole("main")).toBeVisible();
  await expect(page.getByText("You planned these days again", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "2 people", exact: true })).toBeDisabled();
  await expect(page.getByLabel("Message MealCraft")).toHaveAttribute("readonly", "");
  await expect(page.getByLabel("Message MealCraft")).toHaveAttribute("placeholder", "This week was replaced. Open the current week to make changes.");
});

test("a replaced week outside the recent list remains read-only", async ({ page }) => {
  await stubApi(page);
  await page.route("**/api/plans", route => route.fulfill({ json: {
    items: Array.from({ length: 20 }, (_, index) => ({ ...planList.items[0], id: 9100 + index, current: true })),
  } }));
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill({ json: {
    items: [{ ...session(true), pending_interaction: asking.pending_interaction }],
  } }));
  await page.route("**/api/plans/9001", route => route.fulfill({ json: { ...plan, current: false } }));
  await page.route("**/api/plans/9100", route => route.fulfill({ json: { ...plan, id: 9100, current: true } }));
  await page.route("**/api/plans/9100/dashboard", route => route.fulfill({ json: { ...dashboard, plan_id: 9100 } }));
  await page.route("**/api/plans/9100/events", route => route.fulfill({ json: { items: [] } }));
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /Dinners for two this week/ }).click();
  await expect(page.getByText("You planned these days again", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "2 people", exact: true })).toBeDisabled();
  await expect(page.getByLabel("Message MealCraft")).toHaveAttribute("readonly", "");
  await expect(page.getByLabel("Message MealCraft")).toHaveAttribute("placeholder", "This week was replaced. Open the current week to make changes.");
});

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
  // planned nothing, so the saved conversation retains its existing current-week lookup.
  const week = page.getByRole("complementary", { name: "This week" });
  const reloaded = page.waitForRequest("**/api/plans");
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: "something nice" }).click();
  await expect(conversation.getByText("I plan meals and shopping.")).toBeVisible();
  await expect(conversation.getByRole("region", { name: "Your week" })).toBeHidden();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await reloaded;
  await expect(week.getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("I plan meals and shopping.")).toBeHidden();
  await expect(week.getByText("Tofu Brown Rice Stir-fry")).toBeHidden();
  await expect(week.getByRole("heading", { name: "No plan yet" })).toBeVisible();
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

  // Replacing a dish's words sends ordinary text to the selected conversation,
  // without taking on the displayed household week.
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: "something nice" }).click();
  await dish.getByRole("button", { name: "Skip" }).click();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(/^Skip /);
  await page.getByLabel("Message MealCraft").selectText();
  await page.keyboard.type("Dinners for three next week");
  await page.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(3);
  expect(sent[2]!.url).toMatch(/\/api\/agent\/sessions\/60\/messages$/);
  expect(sent[2]!.body).toEqual({ message: "Dinners for three next week", plan_id: null });
});

test("a new conversation stays empty until its previous week is explicitly reopened", async ({ page }) => {
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

  // New plan clears the old week; reopening its conversation restores the dish actions.
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await expect(week.getByRole("heading", { name: "No plan yet" })).toBeVisible();
  await expect(week.getByRole("button", { name: "Swap", exact: true })).toHaveCount(0);
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /Dinners for two this week/ }).click();
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

test("planning the new week instead of answering the take-on question takes the question and the dish's words away", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; conversation 51 is ready to plan a new week, which becomes 9002.
  const next = { ...plan, id: 9002 };
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(false)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: { ...session(true), plan_id: 9002 }, plan: next })));
  await page.route("**/api/plans/9002", route => route.fulfill(json(next)));
  await page.route("**/api/plans/9002/dashboard", route => route.fulfill(json({ ...dashboard, plan_id: 9002 })));
  await page.route("**/api/plans/9002/events", route => route.fulfill(json({ items: [] })));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const dish = page.getByRole("complementary", { name: "This week" }).getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" });
  const question = page.getByLabel("Change the current week here?");
  await dish.getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(question).toBeVisible();

  // "Plan my week" instead: this conversation now holds 9002, so the question about taking 9001 on is gone.
  await page.getByRole("button", { name: "Plan my week" }).click();
  await expect(page.getByText("Seven dinners for S$82.60")).toBeVisible();
  await expect(question).toBeHidden();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue("");
});

test("a conversation still asking about a new week asks before a dish's change takes the current week on", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; a new conversation asks who the new week is for.
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  await page.route("**/api/agent/sessions", route => route.fulfill(json(asking, 201)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions/51/messages", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing(asking, body.message, "CANCEL_MEAL")));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await expect(page.getByRole("region", { name: "Home" })).toBeHidden();
  await page.getByLabel("Message MealCraft").fill("Plan dinners under S$15 per meal.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("button", { name: "2 people" })).toBeVisible();

  // The dish's Skip asks first, and the household's own question stays.
  const question = page.getByLabel("Change the current week here?");
  await page.getByRole("complementary", { name: "This week" }).getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(question).toContainText("still setting up a new week");
  await expect(page.getByRole("button", { name: "2 people" })).toBeVisible();
  expect(sent).toHaveLength(0);

  await question.getByRole("button", { name: "Change the current week" }).click();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Tofu Brown Rice Stir-fry$/), plan_id: 9001 });
});

test("the take-on question below a long conversation scrolls into view", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; conversation 51 is ready to plan after 14 messages.
  const long = {
    ...session(false),
    messages: Array.from({ length: 14 }, (_, i) => ({
      id: i + 1,
      role: i % 2 ? "assistant" : "user",
      content: i % 2 ? "Noted. Anything else the week should know?" : `One more thing about the week, number ${i / 2 + 1}.`,
      created_at: "2026-09-14T08:00:00Z",
    })),
  };
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [long] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await expect(page.getByRole("button", { name: "Plan my week" })).toBeVisible();
  await page.getByRole("complementary", { name: "This week" }).getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();
  await page.getByRole("button", { name: "Send" }).click();

  const thread = page.getByRole("region", { name: "Conversation" });
  const question = page.getByLabel("Change the current week here?");
  await expect(question).toBeVisible();
  await expect.poll(async () => {
    const [shown, card] = [await thread.boundingBox(), await question.boundingBox()];
    return Boolean(shown && card && card.y >= shown.y && card.y + card.height <= shown.y + shown.height);
  }).toBe(true);
});

test("the take-on question goes once the composer says something else", async ({ page }) => {
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
    return route.fulfill(json(body.plan_id ? changing(session(false), body.message, "CANCEL_MEAL") : session(false)));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const skip = (title: string) => week.getByRole("group", { name: `Change ${title}` }).getByRole("button", { name: "Skip" }).click();
  const composer = page.getByLabel("Message MealCraft");
  const question = page.getByLabel("Change the current week here?");

  // A request typed over the dish's words while the question shows: the question goes, and Send plans.
  await skip("Tofu Brown Rice Stir-fry");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(question).toBeVisible();
  await composer.fill("Make it dinners for three");
  await expect(question).toBeHidden();
  await page.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]!.body).toEqual({ message: "Make it dinners for three", plan_id: null });

  // Another dish's Skip while the question shows: the question about the first dish goes, and the new one asks.
  await skip("Tofu Brown Rice Stir-fry");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(question).toBeVisible();
  await skip("Mushroom Spinach Pasta");
  await expect(composer).toHaveValue(/^Skip \w+day's Mushroom Spinach Pasta$/);
  await expect(question).toBeHidden();
  await page.getByRole("button", { name: "Send" }).click();
  await question.getByRole("button", { name: "Change the current week" }).click();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  expect(sent).toHaveLength(2);
  expect(sent[1]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Mushroom Spinach Pasta$/), plan_id: 9001 });
});

test("a dish's words kept over a reload still change the week", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; no conversation holds it.
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing({ ...session(false), messages: [] }, body.message, "CANCEL_MEAL"), 201));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await page.getByRole("complementary", { name: "This week" }).getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(/^Skip /);

  await page.reload();
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  await expect(page.getByRole("region", { name: "Home" })).toBeHidden();
  await expect(page.getByLabel("Message MealCraft")).toHaveValue(/^Skip \w+day's Tofu Brown Rice Stir-fry$/);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("button", { name: "Confirm change" })).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Tofu Brown Rice Stir-fry$/), plan_id: 9001 });
});

for (const way of ["Open my week", "Enter in the landing box"]) test(`a dish's words kept over a navigation go once their week has been replanned (${way})`, async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; the only conversation is off topic.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [offTopic] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/agent/sessions")) sent.push(request.url());
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const composer = page.getByLabel("Message MealCraft");
  await week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();
  await expect(composer).toHaveValue(/^Skip /);

  // On the household page the week is replanned: 9002 replaces 9001.
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("link", { name: "Household", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/profile");
  const replanned = { ...plan, id: 9002, days: days.map(day => ({ ...day, recipe: { ...day.recipe, title: `New ${day.recipe.title}` } })) };
  await page.route("**/api/plans", route => route.fulfill(json({ items: [{ ...planList.items[0], id: 9002 }, ...planList.items] })));
  await page.route("**/api/plans/9002", route => route.fulfill(json(replanned)));
  await page.route("**/api/plans/9002/dashboard", route => route.fulfill(json({ ...dashboard, plan_id: 9002, days: replanned.days })));
  await page.route("**/api/plans/9002/events", route => route.fulfill(json({ items: [] })));
  await page.goBack();

  // Back home, the words of a dish in the replaced week go once the new week is shown: nothing sends them.
  await expect(composer).toHaveValue(/^Skip /);
  if (way === "Open my week") await page.getByRole("button", { name: "Open my week" }).click();
  else await composer.press("Enter");
  await expect(week.getByText("New Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await expect(composer).toHaveValue("");
  if (way === "Enter in the landing box") {
    await expect(page.getByRole("alert")).toContainText("That dish belonged to a previous week");
  }
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  await page.waitForTimeout(300);
  await expect(week.getByText("New Tofu Brown Rice Stir-fry").first()).toBeVisible();
  expect(sent).toEqual([]);
});

test("a dish's words kept over a navigation go once their week has been replanned, even if the new week fails to load", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; the only conversation is off topic.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [offTopic] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().includes("/api/agent/sessions")) sent.push(request.url());
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const composer = page.getByLabel("Message MealCraft");
  await week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();
  await expect(composer).toHaveValue(/^Skip /);

  // On the household page 9002 replaces 9001, and back home 9002 fails to load: the words still go.
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("link", { name: "Household", exact: true }).click();
  await page.waitForURL(url => url.pathname === "/profile");
  await page.route("**/api/plans", route => route.fulfill(json({ items: [{ ...planList.items[0], id: 9002 }, ...planList.items] })));
  await page.route("**/api/plans/9002", route => route.fulfill({ status: 500, contentType: "application/json", body: "{}" }));
  await page.goBack();
  await expect(composer).toHaveValue(/^Skip /);
  await composer.press("Enter");
  await expect(week.getByText("Your week couldn't be loaded.")).toBeVisible();
  await expect(composer).toHaveValue("");
  await page.waitForTimeout(300);
  expect(sent).toEqual([]);
});

test("a dish's words sent from the landing after a reload go to the conversation that planned the week", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Conversation 51 planned the current week.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(true)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing({ ...session(false), id: 70, messages: [] }, body.message, "CANCEL_MEAL"), 201));
  });
  await page.route("**/api/agent/sessions/51/messages", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing(session(true), body.message, "CANCEL_MEAL")));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const conversation = page.getByRole("region", { name: "Conversation" });
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await expect(page.getByRole("heading", { name: "No plan yet" })).toBeVisible();
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /Dinners for two this week/ }).click();
  await page.getByRole("complementary", { name: "This week" }).getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();

  // Enter in the landing box, which holds the dish's words: they go to conversation 51, as Open my week then Send would.
  await page.reload();
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  const composer = page.getByLabel("Message MealCraft");
  await expect(composer).toHaveValue(/^Skip \w+day's Tofu Brown Rice Stir-fry$/);
  await composer.press("Enter");
  await expect(conversation.getByText("How about Miso Tofu Bowl")).toBeVisible();
  expect(sent).toHaveLength(1);
  expect(sent[0]!.url).toMatch(/\/api\/agent\/sessions\/51\/messages$/);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Tofu Brown Rice Stir-fry$/), plan_id: null });
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();
  await expect(page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /^Skip / })).toHaveCount(0);
});

test("planning a new week takes away a dish's words left unsent beside the old one", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Week 9001 was planned on the profile page; conversation 51 is ready to plan a new week, which becomes
  // 9002 with Prawn Laksa on the tofu's night.
  const next = { ...plan, id: 9002, days: days.map(day => (day.entry_id === 4 ? { ...day, recipe: { ...day.recipe, title: "Prawn Laksa" } } : day)) };
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(false)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: { ...session(true), plan_id: 9002 }, plan: next })));
  await page.route("**/api/plans/9002", route => route.fulfill(json(next)));
  await page.route("**/api/plans/9002/dashboard", route => route.fulfill(json({ ...dashboard, plan_id: 9002, days: next.days })));
  await page.route("**/api/plans/9002/events", route => route.fulfill(json({ items: [] })));

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const week = page.getByRole("complementary", { name: "This week" });
  const composer = page.getByLabel("Message MealCraft");
  await week.getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();
  await expect(composer).toHaveValue(/^Skip \w+day's Tofu Brown Rice Stir-fry$/);

  // "Plan my week" with the words unsent: they named a dish of the old week, so they go, and Send has nothing to send.
  await page.getByRole("button", { name: "Plan my week" }).click();
  await expect(page.getByText("Seven dinners for S$82.60")).toBeVisible();
  await expect(week.getByText("Prawn Laksa").first()).toBeVisible();
  await expect(composer).toHaveValue("");
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
});

for (const way of ["Open my week", "Enter in the landing box"]) test(`nothing sends while the week reopens, so a dish's words never start a second conversation (${way})`, async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  // Conversation 51 planned the current week.
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: [session(true)] })));
  await page.route("**/api/plans", route => route.fulfill(json(planList)));
  const sent: Sent = [];
  await page.route("**/api/agent/sessions", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing({ ...session(false), id: 70, messages: [] }, body.message, "CANCEL_MEAL"), 201));
  });
  await page.route("**/api/agent/sessions/51/messages", (route) => {
    const body = route.request().postDataJSON();
    sent.push({ url: route.request().url(), body });
    return route.fulfill(json(changing(session(true), body.message, "CANCEL_MEAL")));
  });

  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
  const conversation = page.getByRole("region", { name: "Conversation" });
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();
  await page.getByRole("button", { name: /New plan/ }).click();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeHidden();
  await expect(page.getByRole("heading", { name: "No plan yet" })).toBeVisible();
  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: /Dinners for two this week/ }).click();
  await page.getByRole("complementary", { name: "This week" }).getByRole("group", { name: "Change Tofu Brown Rice Stir-fry" }).getByRole("button", { name: "Skip" }).click();

  // After a reload the current week is slow to come back; meanwhile the words are sent again and a starter is clicked.
  let answered = false;
  await page.route("**/api/plans", async (route) => {
    await new Promise(resolve => setTimeout(resolve, 1500));
    answered = true;
    await route.fulfill(json(planList));
  });
  await page.reload();
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  if (way === "Open my week") await page.getByRole("button", { name: "Open my week" }).click();
  else await page.getByRole("region", { name: "Home" }).getByLabel("Message MealCraft").press("Enter");
  const workspace = page.getByRole("main");
  const composer = workspace.getByLabel("Message MealCraft");
  await expect(composer).toHaveValue(/^Skip \w+day's Tofu Brown Rice Stir-fry$/);
  await expect(workspace.getByRole("button", { name: "Send" })).toBeDisabled();
  await expect(page.getByRole("button", { name: /New plan/ })).toBeEnabled();
  await composer.press("Enter");
  await conversation.getByRole("button", { name: "A high-protein week" }).click();
  expect(answered).toBe(false);

  // Once the week is back, the words reach conversation 51, once.
  if (way === "Open my week") await workspace.getByRole("button", { name: "Send" }).click();
  await expect(conversation.getByText("How about Miso Tofu Bowl")).toBeVisible();
  await expect(conversation.getByText("Seven dinners for S$82.60")).toBeVisible();
  await page.waitForTimeout(300);
  expect(sent).toHaveLength(1);
  expect(sent[0]!.url).toMatch(/\/api\/agent\/sessions\/51\/messages$/);
  expect(sent[0]!.body).toEqual({ message: expect.stringMatching(/^Skip \w+day's Tofu Brown Rice Stir-fry$/), plan_id: null });
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
    // S$82.60 + S$21.40 against S$90: the backend says how far over, the card and the reply say the same.
    over_budget_sgd: 14,
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
  await expect(card.getByText("This puts the week S$14.00 over your S$90.00 budget.")).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/15-shape-change.png` });

  await card.getByRole("button", { name: "Confirm change" }).click();
  await page.getByRole("button", { name: "Keep it as our usual" }).click();
  await expect.poll(() => answer?.option_ids).toEqual(["keep"]);
});

test("a swap card says how far over the budget the backend found; a skip on a week already over does not", async ({ page }) => {
  await stubApi(page);
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // A week already S$5 over its S$90 budget.
  const over = { ...plan, grocery_estimate: { ...plan.grocery_estimate, purchase_total_sgd: 95, within_weekly_budget: false } };
  await page.route("**/api/plans/9001", route => route.fulfill(json(over)));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: session(true), plan: over })));
  const tofu = { entry_id: 4, day_index: 4, planned_date: isoDay(0), recipe_id: 4, recipe_slug: "dinner-4", recipe_title: "Tofu Brown Rice Stir-fry" };
  const swap = {
    ...replanEvent,
    id: 14,
    applied_revision: null,
    status: "previewed",
    event_type: "REPLACE_MEAL",
    before_entry: tofu,
    after_entry: { ...tofu, recipe_id: 9, recipe_slug: "dinner-9", recipe_title: "Salmon Teriyaki" },
    purchase_total_delta_sgd: 3.2,
    over_budget_sgd: 8.2,
  };
  // Skipping saves S$2.40; the week stays over its budget, but the skip does not put it there.
  const skip = { ...swap, id: 15, event_type: "CANCEL_MEAL", after_entry: tofu, purchase_total_delta_sgd: -2.4, over_budget_sgd: null };
  let pending: unknown = swap;
  await page.route("**/api/agent/sessions/51/messages", route => route.fulfill(json({ ...session(true), pending_replan: pending })));

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await page.getByLabel("Message MealCraft").fill("Swap Thursday's Tofu Brown Rice Stir-fry");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator(".swap-card .to")).toHaveText("Salmon Teriyaki");
  await expect(page.getByText("This puts the week S$8.20 over your S$90.00 budget.")).toBeVisible();

  pending = skip;
  await page.getByLabel("Message MealCraft").fill("Skip Thursday's Tofu Brown Rice Stir-fry");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator(".swap-card .to")).toHaveText("Skip Tofu Brown Rice Stir-fry");
  await expect(page.locator(".swap-card .over-budget")).toHaveCount(0);
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

  await page.getByRole("button", { name: "Keep it locked" }).click();
  await week.getByText("Changes this week").click();
  await expect(week.locator("details").getByText("Keep Tofu Brown Rice Stir-fry as it is")).toBeVisible();
});

test("a week that cannot be planned is explained in the chat in place of the Plan card", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await stubApi(page);
  const why = "S$10 a week for 4 people comes to about S$0.36 a person a meal (7 meals). The cheapest week I could find costs S$38.16.";
  const explained = {
    ...session(false),
    status: "collecting",
    can_confirm: false,
    missing_fields: ["weekly_budget_sgd"],
    clarification_questions: [why],
    messages: [...session(false).messages, { id: 3, role: "assistant", content: why, created_at: "2026-09-14T08:00:02Z" }],
    pending_interaction: {
      type: "quick_reply",
      // The composer's hint; the question is the reply above it.
      prompt: "Pick an option or type your answer",
      field_path: "message",
      question_id: "context-2:unplanned",
      options: [{ id: "say_0", label: "Use S$39 for the week", value: "Make the weekly budget S$39" }],
      allow_free_text: true,
      context_version: 2,
      plan_revision: null,
      expires_at: null,
    },
  };
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: why }) }));
  await page.route("**/api/agent/sessions/51", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(explained) }));

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Plan a week for 4 for S$10 total");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();

  await expect(page.getByText(why).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Plan my week" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Use S$39 for the week" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByLabel("Message MealCraft")).toHaveAttribute("placeholder", "Choose an option, or type your answer…");
});

test("keeping a whole meal previews every dish it keeps, and groceries that do not change say so", async ({ page }) => {
  await stubApi(page);
  const tofu = { entry_id: 4, day_index: 4, planned_date: isoDay(0), recipe_id: 4, recipe_slug: "dinner-4", recipe_title: "Tofu Brown Rice Stir-fry" };
  const greens = { ...tofu, entry_id: 8, role_id: "vegetable", recipe_id: 8, recipe_slug: "dinner-8", recipe_title: "Garlic Greens" };
  const lock = {
    ...replanEvent,
    id: 16,
    applied_revision: null,
    status: "previewed",
    event_type: "LOCK_MEAL",
    reason: "Don't change Thursday's dinner",
    unavailable_ingredient: null,
    before_entry: tofu,
    after_entry: tofu,
    meal_entries: [tofu, greens],
    nutrition_delta: { calories_kcal: 0, protein_g: 0, carbohydrate_g: 0, fat_g: 0, sodium_mg: 0, sugar_g: 0 },
    purchase_total_delta_sgd: 0,
  };
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/api/agent/sessions/51/messages", route => route.fulfill(json({ ...session(true), pending_replan: lock })));

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await page.getByLabel("Message MealCraft").fill("Don't change Thursday's dinner");
  await page.getByRole("button", { name: "Send" }).click();

  const card = page.locator(".swap-card");
  await expect(card.locator(".to")).toHaveText("Keep Tofu Brown Rice Stir-fry and Garlic Greens as they are");
  await expect(card).toContainText("groceries stay the same");
  await expect(card).not.toContainText("S$0.00");
  for (const [width, height] of [[1280, 720], [1440, 900]] as const) {
    await page.setViewportSize({ width, height });
    await expect(card.getByRole("button", { name: "Keep it locked" })).toBeInViewport();
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/17-meal-lock-${width}.png` });
  }
});

test("grocery items and their printed list distinguish missing products from a timed-out price check", async ({ page }) => {
  const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  // Even a request not used in this focused scenario stays local to its synthetic API.
  await page.route("**/api/**", route => route.fulfill(json({ items: [] })));
  await stubApi(page);
  const observed = "2026-10-02T08:00:00Z";
  const checked = "2026-10-07T08:30:00Z";
  const livePlan = {
    ...plan,
    grocery_estimate: {
      ...plan.grocery_estimate,
      pricing_mode: "live",
      purchase_total_sgd: 12.9,
      consumed_total_sgd: 12.9,
      items: [
        { ...grocery("Garlic", "Fruit & Vegetables", 2, 100), evidence: {
          source: "fixture", mode: "fixture", price_source: "no_external_product", lookup_status: "no_external_id",
          fetched_at: "2026-10-01T08:00:00Z", checked_at: null,
        } },
        // As the API sends it: the reviewed snapshot is stored as a "fixture" product.
        { ...grocery("Salmon fillet", "Meat & Seafood", 10.9, 300),
          evidence: { source: "release_snapshot", mode: "snapshot", price_source: "snapshot", lookup_status: "timeout", fetched_at: observed, checked_at: checked },
        },
        { ...grocery("Chicken breast", "Meat & Seafood", 6.5, 500),
          product: { ...grocery("Chicken breast", "Meat & Seafood", 6.5, 500).product, source: "fairprice" },
          evidence: { source: "fairprice", mode: "live", price_source: "live", lookup_status: "success", fetched_at: checked, checked_at: checked },
        },
        { ...grocery("Water", "Other", 0, 500, 0), product: null, match_score: null, note: "Not purchased: drinking water and ice come from the tap and the freezer.", evidence: null },
      ],
    },
  };
  await page.route("**/api/plans/9001", route => route.fulfill(json(livePlan)));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: session(true), plan: livePlan })));
  await page.route("**/api/agent/sessions/51/messages", route => route.fulfill(json({
    ...session(true), pending_replan: { ...replanEvent, status: "previewed", applied_revision: null },
  })));

  await page.goto("/");
  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90.");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Plan my week" }).click();
  const panel = page.getByRole("complementary", { name: "This week" });
  const noProduct = "Sample price · no matching FairPrice product; not checked";
  const timedOut = "Saved FairPrice price · 2 Oct · not checked live in time";
  const checkedLine = "Prices checked at 16:30 · 1 live · 1 saved · 1 sample";
  await panel.getByRole("tab", { name: /Groceries/ }).click();
  for (const [width, height] of [[1280, 720], [1440, 900]] as const) {
    await page.setViewportSize({ width, height });
    await expect(panel.getByText(noProduct, { exact: true })).toBeVisible();
    await expect(panel.getByText(timedOut, { exact: true })).toBeVisible();
    await expect(panel.getByText(checkedLine, { exact: true })).toBeVisible();
    await expect(panel).not.toContainText("FairPrice didn't respond");
    await expect(panel).not.toContainText("Water");
    const format = (value: string) => new Date(value).toLocaleString("en-SG", { timeZone: "Asia/Singapore" });
    await expect(panel.getByText(timedOut, { exact: true })).toHaveAttribute("title", `Price observed: ${format(observed)}; check attempted: ${format(checked)}`);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/18-price-evidence-${width}.png` });

    await panel.getByRole("button", { name: "Preview list" }).click();
    const sheet = page.getByRole("dialog", { name: "Shopping list preview" });
    await expect(sheet.getByText(noProduct, { exact: true })).toBeVisible();
    await expect(sheet.getByText(timedOut, { exact: true })).toBeVisible();
    await expect(sheet.getByText(checkedLine, { exact: false })).toBeVisible();
    await expect(sheet).not.toContainText("FairPrice didn't respond");
    if (SHOTS) {
      await sheet.evaluate(async (node) => {
        await Promise.all(node.getAnimations({ subtree: true }).map(animation => animation.finished.catch(() => {})));
      });
      await page.screenshot({ path: `${SHOTS}/19-price-preview-${width}.png` });
    }
    await page.emulateMedia({ media: "print" });
    await expect(page.locator(".mc-print-sheet").getByText(noProduct, { exact: true })).toBeVisible();
    await expect(page.locator(".mc-print-sheet").getByText(timedOut, { exact: true })).toBeVisible();
    await page.emulateMedia({ media: "screen" });
    await sheet.getByRole("button", { name: "Back", exact: true }).click();
  }
  await page.getByLabel("Message MealCraft").fill("Swap Friday's dinner");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Grocery changes are estimates. Selected product prices are checked again when you confirm.", { exact: true })).toBeVisible();
});
