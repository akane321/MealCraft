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
  await page.route("**/api/agent/sessions?limit=1", route => route.fulfill(json({ items: [] })));
  await page.route("**/api/agent/sessions", route => route.fulfill({ ...json(session(false)), status: 201 }));
  await page.route("**/api/agent/sessions/51/confirm", route => route.fulfill(json({ session: session(true), plan })));
  await page.route("**/api/plans/9001", route => route.fulfill(json(plan)));
  await page.route("**/api/plans/9001/dashboard", route => route.fulfill(json(dashboard)));
  await page.route("**/api/recipes/*/tutorial", route => route.fulfill(json({
    recipe_slug: "dinner-4",
    recipe_title: "Tofu Brown Rice Stir-fry",
    selected_video: null,
    retrieval: { provider_used: "fixture", mode: "fixture", status: "success" },
    warning: null,
  })));
}

test("sending from the film entry opens the chat, and edge panels move it aside", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubApi(page);
  await page.goto("/");
  await page.locator("video").evaluate(video => (video as HTMLVideoElement).pause());
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/1-landing.png` });

  await page.getByLabel("Message MealCraft").fill("Dinners for two this week, around S$90. We still have brown rice at home.");
  await page.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Ready when you are.")).toBeVisible();
  await expect(page.getByRole("heading", { name: /Plan the week/ })).toBeHidden();
  await page.getByRole("button", { name: "Plan my week" }).click();
  await expect(page.getByText("Seven dinners for S$82.60")).toBeVisible();
  await page.waitForTimeout(1200);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/2-chat.png` });

  const chat = page.getByRole("region", { name: "Conversation" });
  const centred = await chat.boundingBox();
  await page.mouse.move(12, 450);
  await expect(page.getByRole("complementary", { name: "This week" }).getByText("Tofu Brown Rice Stir-fry").first()).toBeVisible();
  await page.waitForTimeout(800);
  const shifted = await chat.boundingBox();
  expect(shifted!.x).toBeGreaterThan(centred!.x);
  expect(shifted!.x).toBeGreaterThanOrEqual(424);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/3-week.png` });

  await page.mouse.move(720, 450);
  await page.mouse.move(1430, 450);
  const kitchen = page.getByRole("complementary", { name: "Nutrition and groceries" });
  await expect(kitchen.getByText("S$82.60")).toBeVisible();
  await expect(kitchen.getByText("S$7.40 under your S$90.00")).toBeVisible();
  await page.waitForTimeout(800);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/4-kitchen.png` });

  await kitchen.getByRole("button", { name: "Preview list" }).click();
  const sheet = page.getByRole("dialog", { name: "Shopping list preview" });
  await expect(sheet.getByText("Estimated total")).toBeVisible();
  await expect(sheet.getByText("Sample prices", { exact: false })).toBeVisible();
  await page.waitForTimeout(600);
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/5-preview.png` });
    await page.pdf({ path: `${SHOTS}/6-list.pdf`, format: "A4" });
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: "See the week" }).click();
    await page.waitForTimeout(900);
    await page.screenshot({ path: `${SHOTS}/7-min-size.png` });
  }
});
