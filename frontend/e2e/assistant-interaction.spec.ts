import { expect, test } from "@playwright/test";

function sessionFixture({ ready = false } = {}) {
  return {
    id: 42,
    status: ready ? "ready" : "collecting",
    parser_provider: "fixture",
    constraints: {
      household_size: ready ? 2 : null,
      max_cooking_time_minutes: 60,
      budget_per_meal_sgd: 15,
      weekly_budget_sgd: null,
      allergens: [],
      excluded_ingredients: [],
      dietary_preferences: [],
      health_preferences: [],
      nutrition_targets: {
        calories_kcal: null,
        protein_g: null,
        carbohydrate_g: null,
        fat_g: null,
      },
      max_sodium_mg_per_meal: null,
      available_ingredients: [],
      pricing_mode: "fixture",
    },
    missing_fields: ready ? [] : ["household_size"],
    clarification_questions: ready ? [] : ["How many people should this plan serve?"],
    messages: [
      { id: 1, role: "user", content: "Plan dinners under S$15 per meal.", created_at: "2026-09-06T00:00:00Z" },
      {
        id: 2,
        role: "assistant",
        content: ready ? "The constraints are ready for confirmation." : "How many people should this plan serve?",
        created_at: "2026-09-06T00:00:01Z",
      },
    ],
    plan_id: null,
    replan_draft: { event_type: null, entry_id: null, unavailable_ingredient: null, reason: null },
    pending_replan: null,
    context_version: ready ? 2 : 1,
    last_scope_decision: {
      scope_class: "domain_action",
      detected_intents: ["create_plan"],
      supported_segments: ["Plan dinners under S$15 per meal."],
      unsupported_segments: [],
      should_mutate_state: true,
      should_call_tools: true,
      requires_clarification: false,
      reason_code: ready ? "PENDING_CLARIFICATION_RESPONSE" : "SUPPORTED_MEAL_PLANNING_REQUEST",
    },
    pending_interaction: ready
      ? null
      : {
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
    can_confirm: ready,
    created_at: "2026-09-06T00:00:00Z",
    updated_at: "2026-09-06T00:00:01Z",
  };
}

test("submits a stable structured clarification answer", async ({ page }) => {
  await page.route("**/api/agent/sessions?limit=1", route => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ items: [] }),
  }));
  await page.route("**/api/agent/sessions", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 201,
      contentType: "application/json",
      body: JSON.stringify(sessionFixture()),
    });
  });
  await page.route("**/api/agent/sessions/42/interactions", async (route) => {
    const payload = route.request().postDataJSON();
    expect(payload).toEqual({
      question_id: "context-1:household_size",
      option_ids: ["household_size_2"],
      free_text: null,
      context_version: 1,
      plan_revision: null,
    });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(sessionFixture({ ready: true })),
    });
  });

  await page.goto("/assistant");
  await page.getByPlaceholder(/Plan for 2 people/).fill("Plan dinners under S$15 per meal.");
  await page.getByRole("button", { name: "Start planning" }).click();

  await expect(page.getByRole("region", { name: "Structured clarification" })).toBeVisible();
  await page.getByRole("button", { name: "2 people" }).click();

  await expect(page.getByText("2 people", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm and generate plan" })).toBeEnabled();
  await expect(page.getByRole("region", { name: "Structured clarification" })).toHaveCount(0);
});
