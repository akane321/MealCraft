// The shared-dish model on the two desktop widths (ADR-0071 sections 1 and 2): the member card's
// "only I avoid it" switch with its cross-contact warning, and who a dish is not for in the week.
import { expect, test } from "@playwright/test";

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const ME = {
  user: { id: 1, email: "demo@example.com", display_name: "Tan Wei", locale: "en", timezone: "Asia/Singapore", status: "active", system_role: "user" },
  active_household_id: 1,
  household_role: "owner",
};

test("an allergen can be narrowed to the one member who avoids it, with its cross-contact warning", async ({ page }) => {
  await page.route("**/api/auth/me", route => route.fulfill(json(ME)));
  await page.route("**/api/household-profiles/current", route => route.fulfill(json({ detail: "none" }, 404)));
  let saved: { members?: Array<{ allergens: string[]; self_only_allergens?: string[] }> } | null = null;
  await page.route("**/api/household-profiles", async (route) => {
    saved = route.request().postDataJSON();
    await route.fulfill(json({ detail: "stop here" }, 422));
  });

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/profile");
  await page.waitForLoadState("networkidle"); // clicks before hydration are lost

  // No allergen, no switch: the household avoids nothing, so there is nothing to narrow.
  await expect(page.getByText(/avoids peanut$/i)).toBeHidden();
  await page.getByRole("checkbox", { name: "Peanut" }).first().check();
  const narrow = page.getByRole("checkbox", { name: /^Only .* avoids peanut$/i });
  await expect(narrow).toBeVisible();
  await expect(narrow).not.toBeChecked(); // off by default: one kitchen can cross-contact

  await expect(page.getByText(/Cooking in the same kitchen can cause cross-contact/)).toBeHidden();
  await narrow.check();
  await expect(page.getByText(/Cooking in the same kitchen can cause cross-contact/)).toBeVisible();
  // The sidebar says the household avoids nothing, because the only allergen belongs to one member.
  await expect(page.getByText("Whole household avoids")).toBeVisible();

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByText(/Cooking in the same kitchen can cause cross-contact/)).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.getByRole("button", { name: "Save household" }).click();
  await expect.poll(() => saved?.members?.[0]?.self_only_allergens).toEqual(["peanut"]);

  // Unticking the allergen takes its mark with it, so no mark outlives the allergen it belongs to.
  await page.getByRole("checkbox", { name: "Peanut" }).first().uncheck();
  await expect(page.getByText(/Cooking in the same kitchen can cause cross-contact/)).toBeHidden();
  await page.getByRole("button", { name: "Save household" }).click();
  await expect.poll(() => saved?.members?.[0]?.self_only_allergens).toEqual([]);
});

test("the week says who each dish is not for", async ({ page }) => {
  const isoDay = () => new Date().toLocaleDateString("en-CA");
  const dish = (entryId: number, title: string, role: string, notFor: string[], share = 0.5) => ({
    entry_id: entryId, day_index: 1, planned_date: isoDay(), meal_type: "dinner", role_id: role,
    portion_share: share, servings: 3.2,
    recipe: {
      id: entryId, slug: `dish-${entryId}`, title, description: "", cuisine: "Home", meal_type: "dinner",
      servings: 4, total_time_minutes: 30, dietary_tags: [],
      nutrition: { calories_kcal: 600, protein_g: 30, carbohydrate_g: 50, fat_g: 15, sodium_mg: 600, sugar_g: 6 },
    },
    recommendation_score: 80, status: "planned", is_locked: false, consumed_at: null, not_for: notFor,
    nutrition_per_person: { calories_kcal: 600, protein_g: 30, carbohydrate_g: 50, fat_g: 15, sodium_mg: 600, sugar_g: 6 },
  });
  const days = [
    dish(1, "Curry Chicken", "main", ["Ann"]),
    dish(2, "Mapo Tofu", "main-2", []),
    dish(3, "Stir-fried Kai Lan", "vegetable", ["Mei"]),
    dish(4, "Steamed Rice", "staple", [], 1),
  ];
  const plan = {
    id: 9001, revision: 1, household_profile_id: 1, household_profile_version: 1, replaces_plan_id: null,
    start_date: isoDay(), end_date: isoDay(), day_count: 1, household_size: 4, days,
    nutrition_summary_per_person: days[0]!.nutrition_per_person,
    grocery_estimate: {
      pricing_mode: "fixture", complete: true, purchase_total_sgd: 42.6, consumed_total_sgd: 38.1,
      weekly_budget_sgd: null, within_weekly_budget: null, items: [], unmapped_ingredients: [], warnings: [],
    },
    warnings: [], created_at: "2027-01-03T08:00:00Z",
  };
  const dashboard = {
    plan_id: 9001, revision: 1, start_date: plan.start_date, end_date: plan.end_date, household_size: 4,
    completion_rate: 0, status_counts: { planned: 4, completed: 0, skipped: 0 },
    nutrition_targets: { calories_kcal: null, protein_g: null, carbohydrate_g: null, fat_g: null },
    planned_nutrition_per_person: days[0]!.nutrition_per_person,
    completed_nutrition_per_person: { calories_kcal: 0, protein_g: 0, carbohydrate_g: 0, fat_g: 0, sodium_mg: 0, sugar_g: 0 },
    days,
  };

  await page.route("**/api/auth/me", route => route.fulfill(json(ME)));
  await page.route("**/api/agent/sessions?limit=50", route => route.fulfill(json({ items: [] })));
  await page.route("**/api/plans?*", route => route.fulfill(json({ items: [{ ...plan, current: true }] })));
  await page.route("**/api/plans", route => route.fulfill(json({ items: [{ ...plan, current: true }] })));
  await page.route("**/api/household-profiles/current", route => route.fulfill(json({}, 404)));
  await page.route("**/api/plans/9001", route => route.fulfill(json(plan)));
  await page.route("**/api/plans/9001/dashboard", route => route.fulfill(json(dashboard)));
  await page.route("**/api/plans/9001/events", route => route.fulfill(json({ items: [] })));

  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");
  // The household link renders once the page has hydrated and read the routed account, so the click is not lost.
  // Waiting for the network to go idle timed out once on CI (task 14).
  await expect(page.getByRole("link", { name: /Household settings/ })).toBeVisible();
  await page.getByRole("button", { name: /Let.s plan my week/ }).click();

  await expect(page.getByText("Not for Ann")).toBeVisible();
  await expect(page.getByText("Not for Mei")).toBeVisible();
  // A dish everyone at the meal can eat carries no note.
  await expect(page.getByText("Not for", { exact: false })).toHaveCount(2);
  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.getByText("Not for Ann")).toBeVisible();
});
