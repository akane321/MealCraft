import { inflateSync } from "node:zlib";
import { expect, test, type Page } from "@playwright/test";

// The workspace's own layout and wording, found in the 2026-10-04 walkthrough. At the 1280x720 minimum
// (ADR-0010) unless a test says otherwise.

const json = (body: unknown) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

function isoDay(offset: number) {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return day.toLocaleDateString("en-CA");
}

const nutrition = { calories_kcal: 480, protein_g: 30, carbohydrate_g: 50, fat_g: 15, sodium_mg: 600, sugar_g: 6 };

function dish(id: number, dayIndex: number, meal: "lunch" | "dinner", title: string) {
  return {
    entry_id: id,
    day_index: dayIndex,
    planned_date: isoDay(dayIndex - 1),
    meal_type: meal,
    role_id: "main",
    portion_share: 1,
    recipe: { id, slug: `dish-${id}`, title, description: "", cuisine: "Home", meal_type: meal, servings: 2, total_time_minutes: 30, dietary_tags: [], nutrition },
    status: "planned",
    is_locked: false,
    consumed_at: null,
    nutrition_per_person: nutrition,
  };
}

// Day 1 has a lunch as well as a dinner; the dashboard lists them in the order they are eaten.
const days = [
  dish(11, 1, "lunch", "Tomato Egg Noodles"),
  dish(1, 1, "dinner", "Lemon Herb Chicken"),
  ...[2, 3, 4, 5, 6, 7].map(day => dish(day, day, "dinner", `Dinner ${day}`)),
];

function grocery(index: number) {
  return {
    ingredient_name: `item_${index}`,
    ingredient_display_name: `Grocery item ${index}`,
    required_quantity: 500,
    unit: "g",
    pantry_deduction: 0,
    remaining_quantity: 500,
    product: { category: index % 2 ? "Pantry" : "Fruit & Vegetables", package_size: 500, package_unit: "g", fetched_at: "2026-10-04T08:00:00Z", source: "fixture" },
    match_score: 1,
    packages_required: 1,
    purchase_cost_sgd: 2,
    consumed_cost_sgd: 2,
    excess_quantity: 0,
    note: null,
  };
}

function week(id: number) {
  return {
    id,
    revision: 1,
    household_profile_id: null,
    household_profile_version: null,
    replaces_plan_id: null,
    start_date: isoDay(0),
    end_date: isoDay(6),
    day_count: 7,
    household_size: 2,
    days: days.map(day => ({ ...day, recipe: { ...day.recipe, title: `${day.recipe.title}${id === 9001 ? "" : ` (${id})`}` } })),
    nutrition_summary_per_person: nutrition,
    // Enough lines for the printed list to run onto a second page.
    grocery_estimate: {
      pricing_mode: "fixture",
      complete: true,
      purchase_total_sgd: 90,
      consumed_total_sgd: 90,
      weekly_budget_sgd: 100,
      within_weekly_budget: true,
      items: Array.from({ length: 45 }, (_, index) => grocery(index + 1)),
      unmapped_ingredients: [],
      warnings: [],
    },
    warnings: [],
    created_at: "2026-10-04T08:00:00Z",
  };
}

const listed = (id: number, current: boolean) => ({ ...week(id), purchase_total_sgd: 90, consumed_total_sgd: null, within_weekly_budget: true, current });

function conversation(id: number, title: string, planId: number | null) {
  return {
    id,
    status: planId ? "planned" : "collecting",
    parser_provider: "fixture",
    constraints: {
      household_size: 2, max_cooking_time_minutes: 60, budget_per_meal_sgd: null, weekly_budget_sgd: 100, allergens: [],
      excluded_ingredients: [], dietary_preferences: [], health_preferences: [],
      nutrition_targets: { calories_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
      max_sodium_mg_per_meal: null, available_ingredients: [], pricing_mode: "fixture", max_uses_per_recipe: null,
    },
    missing_fields: [],
    clarification_questions: [],
    messages: [
      { id: id * 10, role: "user", content: title, created_at: "2026-10-04T08:00:00Z" },
      { id: id * 10 + 1, role: "assistant", content: planId ? `Your week ${planId} is planned.` : "Who's eating?", created_at: "2026-10-04T08:00:01Z" },
    ],
    plan_id: planId,
    replan_draft: { event_type: null, entry_id: null, unavailable_ingredient: null, reason: null },
    pending_replan: null,
    context_version: 2,
    last_scope_decision: null,
    pending_interaction: null,
    can_confirm: false,
    created_at: "2026-10-04T08:00:00Z",
    updated_at: "2026-10-04T08:00:01Z",
  };
}

async function stub(page: Page, { conversations, plans, role = "user" }: { conversations: unknown[]; plans: Array<{ id: number; current: boolean }>; role?: string }) {
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: role },
    active_household_id: 1,
    household_role: "owner",
  })));
  await page.route("**/api/agent/sessions?limit=8", route => route.fulfill(json({ items: conversations })));
  await page.route("**/api/household-profiles/current", route => route.fulfill({ status: 404, contentType: "application/json", body: "{}" }));
  await page.route("**/api/plans", route => route.fulfill(json({ items: plans.map(item => listed(item.id, item.current)) })));
  for (const { id } of plans) {
    await page.route(`**/api/plans/${id}`, route => route.fulfill(json(week(id))));
    await page.route(`**/api/plans/${id}/dashboard`, route => route.fulfill(json({
      plan_id: id, revision: 1, start_date: isoDay(0), end_date: isoDay(6), household_size: 2, completion_rate: 0,
      status_counts: { planned: days.length, completed: 0, skipped: 0 },
      nutrition_targets: { calories_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
      planned_nutrition_per_person: nutrition, completed_nutrition_per_person: nutrition, days: week(id).days,
    })));
    await page.route(`**/api/plans/${id}/events`, route => route.fulfill(json({ items: [] })));
  }
  await page.route("**/api/recipes/*/tutorial", route => route.fulfill(json({
    recipe_slug: "dish-11", recipe_title: "Tomato Egg Noodles", selected_video: null,
    retrieval: { provider_used: "fixture", mode: "fixture", status: "success" }, warning: null,
  })));
}

async function openWeek(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: "Open my week" }).click();
}

test("at 1280x720 eight recent conversations keep their rows and the list scrolls", async ({ page }) => {
  const titles = Array.from({ length: 8 }, (_, index) => `Conversation number ${index + 1} about a week of dinners`);
  await stub(page, { conversations: titles.map((title, index) => conversation(100 + index, title, index ? null : 9001)), plans: [{ id: 9001, current: true }] });
  await openWeek(page);
  const rail = page.getByRole("complementary", { name: "Navigation" });
  const rows = rail.locator(".recent button");
  await expect(rows).toHaveCount(8);
  await expect(page.getByRole("complementary", { name: "This week" }).getByText("Lemon Herb Chicken").first()).toBeVisible();

  const layout = await rail.locator(".recent").evaluate((list) => {
    const buttons = [...list.querySelectorAll("button")];
    return {
      scrolls: list.scrollHeight > list.clientHeight,
      rows: buttons.map(button => ({ top: button.offsetTop, height: button.offsetHeight, clipped: button.scrollHeight > button.clientHeight })),
    };
  });
  // Rows keep their own height (none clipped, none on top of the one before) and the list scrolls instead.
  expect(layout.scrolls).toBe(true);
  for (const [index, row] of layout.rows.entries()) {
    expect(row.clipped).toBe(false);
    expect(row.height).toBeGreaterThanOrEqual(28);
    if (index) expect(row.top).toBeGreaterThanOrEqual(layout.rows[index - 1]!.top + layout.rows[index - 1]!.height);
  }
  // The household card below the list is not covered.
  const lastBox = await rows.last().boundingBox();
  const card = await rail.locator(".home-card").boundingBox();
  expect(lastBox!.y).toBeGreaterThan(0);
  expect(card!.y + card!.height).toBeLessThanOrEqual(720);

  await rows.last().scrollIntoViewIfNeeded();
  await rows.last().click();
  await expect(page.getByRole("heading", { name: titles[7] })).toBeVisible();
});

test("printing the shopping list with background graphics puts every page on the light paper", async ({ page }) => {
  await stub(page, { conversations: [conversation(100, "Dinners for two", 9001)], plans: [{ id: 9001, current: true }] });
  await openWeek(page);
  await expect(page.getByRole("complementary", { name: "This week" }).getByText("Lemon Herb Chicken").first()).toBeVisible();

  await page.emulateMedia({ media: "print" });
  // The page itself is the paper past the sheet's first page: never the dark workspace.
  const backgrounds = await page.evaluate(() => [document.documentElement, document.body].map(node => getComputedStyle(node).backgroundColor));
  expect(backgrounds).toEqual(["rgb(251, 248, 242)", "rgb(251, 248, 242)"]);

  const pdf = await page.pdf({ format: "A4", printBackground: true });
  const pages = pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) ?? [];
  expect(pages.length).toBeGreaterThanOrEqual(2);
  // No page paints the workspace's dark ink (#0e0c0a) as a fill: page 2 printed dark-on-dark before.
  const fills = contentStreams(pdf).flatMap(stream => [...stream.matchAll(/([\d.]+) ([\d.]+) ([\d.]+) rg/g)].map(match => match.slice(1, 4).map(Number)));
  expect(fills.length).toBeGreaterThan(0);
  const ink = [14, 12, 10].map(value => value / 255);
  expect(fills.filter(fill => fill.every((value, index) => Math.abs(value - ink[index]!) < 0.01))).toEqual([]);
  await page.emulateMedia({ media: "screen" });
});

/** The PDF's decompressed content streams, as text. */
function contentStreams(pdf: Buffer): string[] {
  const text = pdf.toString("latin1");
  const streams: string[] = [];
  for (const match of text.matchAll(/stream\r?\n/g)) {
    const start = match.index! + match[0].length;
    const end = text.indexOf("endstream", start);
    try { streams.push(inflateSync(pdf.subarray(start, end)).toString("latin1")); }
    catch { /* not a deflated stream (an image or font) */ }
  }
  return streams;
}

test("a lock's preview offers to keep it locked or cancel, never \"Keep as is\"", async ({ page }) => {
  const planned = conversation(100, "Dinners for two", 9001);
  await stub(page, { conversations: [planned], plans: [{ id: 9001, current: true }] });
  const chicken = { entry_id: 1, day_index: 1, meal_type: "dinner", planned_date: isoDay(0), recipe_id: 1, recipe_slug: "dish-1", recipe_title: "Lemon Herb Chicken", status: "planned", is_locked: false, recommendation_score: 80 };
  const lock = {
    id: 13, plan_id: 9001, base_revision: 1, applied_revision: null, event_type: "LOCK_MEAL", status: "previewed", reason: null,
    unavailable_ingredient: null, before_entry: chicken, after_entry: chicken,
    nutrition_delta: { calories_kcal: 0, protein_g: 0, carbohydrate_g: 0, fat_g: 0, sodium_mg: 0, sugar_g: 0 },
    grocery_delta: [], purchase_total_delta_sgd: 0, created_at: "2026-10-04T09:00:00Z", applied_at: null,
  };
  let discarded = false;
  await page.route("**/api/agent/sessions/100/messages", route => route.fulfill(json({ ...planned, pending_replan: lock })));
  await page.route("**/api/agent/sessions/100/replan/discard", (route) => {
    discarded = true;
    return route.fulfill(json(planned));
  });
  await openWeek(page);
  const chat = page.getByRole("main");
  await chat.getByLabel("Message MealCraft").fill("Don't change today's dinner");
  await chat.getByRole("button", { name: "Send" }).click();

  await expect(page.getByText("Keep Lemon Herb Chicken as it is")).toBeVisible();
  await expect(page.getByRole("button", { name: "Keep it locked" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Keep as is" })).toHaveCount(0);
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect.poll(() => discarded).toBe(true);
});

test("a week planned again is shown read-only beside its conversation, with the way to the current week", async ({ page }) => {
  // 9001 was planned first; the same days were planned again as 9002, which replaced it.
  await stub(page, {
    conversations: [conversation(101, "Plan the week again", 9002), conversation(100, "First plan of the week", 9001)],
    plans: [{ id: 9002, current: true }, { id: 9001, current: false }],
  });
  await openWeek(page);
  const panel = page.getByRole("complementary", { name: "This week" });
  await expect(panel.getByText("Lemon Herb Chicken (9002)").first()).toBeVisible();
  await expect(panel.getByRole("button", { name: "Mark as cooked" })).toBeVisible();

  await page.getByRole("complementary", { name: "Navigation" }).getByRole("button", { name: "First plan of the week" }).click();
  await expect(panel.getByText("Lemon Herb Chicken").first()).toBeVisible();
  await expect(page.getByText("You planned these days again, so this week was replaced.")).toBeVisible();
  // Read, not changed: no marking cooked, no swaps, no change chips, nothing to send.
  await expect(panel.getByRole("button", { name: "Mark as cooked" })).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Swap" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Swap tomorrow's dinner" })).toHaveCount(0);
  const chat = page.getByRole("main");
  await expect(chat.getByLabel("Message MealCraft")).toHaveAttribute("readonly", "");
  await expect(chat.getByLabel("Message MealCraft")).not.toBeEditable();
  await expect(chat.getByRole("button", { name: "Send" })).toBeDisabled();
  await expect(panel.getByRole("button", { name: "Recipe & steps" })).toBeVisible();

  await page.getByRole("button", { name: "Open the current week" }).click();
  await expect(page.getByRole("heading", { name: "Plan the week again" })).toBeVisible();
  await expect(panel.getByText("Lemon Herb Chicken (9002)").first()).toBeVisible();
  await expect(page.getByText("You planned these days again")).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Mark as cooked" })).toBeVisible();
});

test("past weeks mark the weeks that were planned again", async ({ page }) => {
  await stub(page, { conversations: [], plans: [{ id: 9002, current: true }, { id: 9001, current: false }] });
  await page.route("**/api/plans?*", route => route.fulfill(json({ items: [listed(9002, true), listed(9001, false)] })));
  await page.goto("/history");
  const weeks = page.getByRole("listitem");
  await expect(weeks).toHaveCount(2);
  await expect(weeks.nth(0).getByText("Replaced by a newer plan")).toHaveCount(0);
  await expect(weeks.nth(1).getByText("Replaced by a newer plan")).toBeVisible();
});

test("nutrition details name each dish's meal, lunch before that day's dinner", async ({ page }) => {
  await stub(page, { conversations: [conversation(100, "Dinners for two", 9001)], plans: [{ id: 9001, current: true }] });
  await openWeek(page);
  const panel = page.getByRole("complementary", { name: "This week" });
  await panel.getByRole("tab", { name: "Nutrition" }).click();
  await panel.getByRole("button", { name: /All six nutrients/ }).click();
  const details = page.getByRole("dialog", { name: "Nutrition details" });
  await expect(details.getByRole("columnheader", { name: "Meal" })).toBeVisible();
  const cells = (row: number) => details.getByRole("row").nth(row).getByRole("cell");
  await expect(cells(1).nth(1)).toHaveText("Lunch");
  await expect(cells(1).nth(2)).toHaveText("Tomato Egg Noodles");
  await expect(cells(2).nth(1)).toHaveText("Dinner");
  await expect(cells(2).nth(2)).toHaveText("Lemon Herb Chicken");
});

test("the service status page speaks to the household; developer details are for administrators", async ({ page }) => {
  await stub(page, { conversations: [], plans: [] });
  await page.unroute("**/api/household-profiles/current");
  await page.route("**/api/household-profiles/current", route => route.fulfill(json({ id: 1, name: "Tan household", current_version: 1, current: { pricing_mode: "fixture" } })));
  await page.goto("/system");
  await expect(page.getByRole("heading", { name: "Service status" })).toBeVisible();
  await expect(page.getByText("Planning and the assistant")).toBeVisible();
  await expect(page.getByText("Sample prices. They stay the same and are not today's FairPrice prices.")).toBeVisible();
  for (const developer of ["Development environment", "API documentation", "Environment", "PostgreSQL"]) {
    await expect(page.getByText(developer, { exact: true })).toHaveCount(0);
  }

  await page.unroute("**/api/auth/me");
  await page.route("**/api/auth/me", route => route.fulfill(json({
    user: { id: 2, email: "admin@example.com", display_name: "Admin", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "admin" },
    active_household_id: null,
    household_role: null,
  })));
  await page.reload();
  await expect(page.getByRole("heading", { name: "For administrators" })).toBeVisible();
  await expect(page.getByRole("link", { name: "API documentation" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Operations console" })).toBeVisible();
});
