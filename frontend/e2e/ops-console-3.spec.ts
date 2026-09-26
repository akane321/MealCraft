import { expect, test, type Page, type Route } from "@playwright/test";

// Console slice 3 (ADR-0047 Data): edit and withdraw a recipe, rename an ingredient and change a product
// mapping, all against stubbed APIs.
const SHOTS = process.env.OPS_CONSOLE_SHOTS;

const admin = {
  user: { id: 7, normalized_email: "ops@example.test", display_name: "Ops Lead", locale: "en-SG", timezone: "Asia/Singapore", status: "active", system_role: "admin", email_verified_at: null, created_at: "2026-09-20T08:00:00Z" },
  active_household_id: null,
  household_role: null,
};

const stew = { id: 3, slug: "v2-bean-stew", title: "Bean Stew", course: "main", meal_types: ["dinner"], dietary_tags: ["vegan"], release_version: "v2.1", withdrawn: null as string | null, withdrawn_reason: null as string | null };
const stewDetail = {
  ...stew,
  description: "A slow bean stew.",
  cuisine: "british",
  servings: 4,
  prep_time_minutes: 10,
  cook_time_minutes: 50,
  allergens: [],
  nutrition: { calories_kcal: 420, protein_g: 21 },
  ingredients: [{ ingredient_id: 11, name: "Adzuki bean", normalized_name: "adzuki_bean", quantity: 200, unit: "g", preparation: "soaked", original_text: "200 g adzuki beans, soaked" }],
  steps: ["Simmer the beans.", "Season and serve."],
  withdrawn_at: null as string | null,
};
const catFood = { id: 4, slug: "v2-cat-stir-fry", title: "Stir Fry For Your Cat", course: "main", meal_types: ["dinner"], dietary_tags: [], release_version: "v2.1", withdrawn: "file", withdrawn_reason: "Pet food, not a dinner for people." };

const beans = { id: 11, normalized_name: "adzuki_bean", display_name: "Adzuki bean", zh_names: ["红豆"], aliases: ["red bean"], allergens: [], recipes: 12 };
const peanut = { id: 12, normalized_name: "peanut", display_name: "Peanut", zh_names: ["花生"], aliases: [], allergens: ["peanut"], recipes: 40 };

const product = (id: string, name: string, price: number, grams: number) => ({ external_id: id, name, brand: "Test", category: "Beans", package_grams: grams, package_grams_basis: `printed ${grams} G`, price_sgd: price, product_url: `https://www.fairprice.com.sg/product/${id}`, in_stock: true, query: "adzuki bean", fetched_at: "2026-09-21T10:21:00Z" });
const beanMapping = { ingredient: "adzuki_bean", display_name: "Adzuki bean", status: "mapped", review_status: "proposed", products: [product("90031017", "Green Earth Organic Adzuki Beans", 7.2, 500), product("90044211", "Hirao Azuki Red Beans", 10.95, 250)], source: "file" };

const json = (body: unknown, status = 200) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
const path = (pathname: string) => (url: URL) => url.pathname === pathname;

async function stubConsole(page: Page) {
  let signedIn = false;
  let recipe = { ...stewDetail };
  let ingredient = { ...beans };
  let mapping: Record<string, unknown> = { ...beanMapping };

  await page.route(path("/api/auth/me"), route => route.fulfill(signedIn ? json(admin) : json({ detail: "Authentication required" }, 401)));
  await page.route(path("/api/auth/login"), (route) => {
    signedIn = true;
    return route.fulfill(json({ actor: admin, session: {}, csrf_token: "csrf-test" }));
  });
  await page.route(path("/api/ops/overview"), route => route.fulfill(json({ app_version: "0.1.0", generated_at: "2026-09-26T08:00:00Z", latest_recorded_versions: { code_commit: null, catalog_version: null, product_snapshot_version: null }, runs: { queued: 0, running: 0, failures_last_24_hours: {}, provider_modes_last_24_hours: {} } })));
  await page.route(path("/api/ops/overview/series"), route => route.fulfill(json({ days: [], provider_modes: {} })));

  await page.route(path("/api/ops/data/recipes"), (route: Route) => {
    const withdrawn = new URL(route.request().url()).searchParams.get("withdrawn");
    const all = [recipe, catFood];
    const items = withdrawn === "true" ? all.filter(item => item.withdrawn) : all;
    return route.fulfill(json({ total: items.length, items }));
  });
  await page.route(path("/api/ops/data/recipes/3"), (route: Route) => {
    if (route.request().method() === "PATCH") {
      const change = route.request().postDataJSON();
      expect(change).toEqual({ title: "Red Bean Stew", dietary_tags: ["vegan", "gluten-free"], meal_types: ["dinner", "lunch"], course: "soup" });
      recipe = { ...recipe, ...change };
    }
    return route.fulfill(json(recipe));
  });
  await page.route(path("/api/ops/data/recipes/3/withdraw"), (route: Route) => {
    expect(route.request().postDataJSON()).toEqual({ reason: "Duplicate of another stew." });
    recipe = { ...recipe, withdrawn: "console", withdrawn_reason: "Duplicate of another stew.", withdrawn_at: "2026-09-28T09:00:00Z" };
    return route.fulfill(json(recipe));
  });

  await page.route(path("/api/ops/data/ingredients"), route => route.fulfill(json({ total: 2, items: [ingredient, peanut] })));
  await page.route(path("/api/ops/data/ingredients/11"), (route: Route) => {
    const change = route.request().postDataJSON();
    expect(change).toEqual({ display_name: "Adzuki bean", zh_names: ["红豆", "赤小豆"], aliases: ["red bean", "azuki"] });
    ingredient = { ...ingredient, ...change };
    return route.fulfill(json(ingredient));
  });

  await page.route(path("/api/ops/data/mappings"), route => route.fulfill(json({ total: 1, items: [mapping] })));
  await page.route(path("/api/ops/data/mappings/adzuki_bean"), (route: Route) => {
    expect(route.request().method()).toBe("PUT");
    const change = route.request().postDataJSON();
    expect(change.product).toMatchObject({ external_id: "555", package_grams: 400, query: "adzuki beans" });
    mapping = { ...mapping, products: [change.product], review_status: "console", source: "console" };
    return route.fulfill(json(mapping));
  });
  await page.route(path("/api/products/search"), route => route.fulfill(json({ query: "adzuki beans", provider_used: "fixture", fallback_used: false, cached: false, warning: null, items: [{ external_id: "555", name: "Pasar Red Beans", brand: "Pasar", category: "Beans", package_size: 400, package_unit: "g", price_sgd: 2.15, product_url: "https://www.fairprice.com.sg/product/555", image_url: null, in_stock: true, source: "fixture", fetched_at: "2026-09-21T10:21:00Z" }] })));
}

async function signIn(page: Page) {
  await page.goto("/login");
  await expect(async () => {
    await page.getByRole("radio", { name: "Administrator" }).click();
    await expect(page.getByRole("heading", { name: "Administrator sign in" })).toBeVisible({ timeout: 1000 });
  }).toPass();
  await page.getByLabel("Email").fill("ops@example.test");
  await page.getByLabel("Password").fill("console-password");
  await page.getByRole("button", { name: "Sign in to the console" }).click();
  await expect(page).toHaveURL(/\/ops$/);
}

test("an administrator edits and withdraws a recipe, renames an ingredient and remaps a product", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await stubConsole(page);
  await signIn(page);
  await page.getByRole("navigation", { name: "Console" }).getByRole("link", { name: /^Data/ }).click();

  // Recipes: the reviewed file's withdrawal shows, then edit and withdraw one.
  const recipes = page.getByRole("region", { name: "Recipes" });
  await expect(recipes.getByRole("row", { name: /Stir Fry For Your Cat .* Withdrawn/ })).toBeVisible();
  await recipes.getByRole("button", { name: "Bean Stew" }).click();
  await expect(page).toHaveURL(/recipe=3/);
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText("Simmer the beans.")).toBeVisible();
  await drawer.getByLabel("Title").fill("Red Bean Stew");
  await drawer.getByLabel("Course").selectOption("soup");
  await drawer.getByLabel("Lunch").check();
  await drawer.getByLabel("gluten-free").check();
  await drawer.getByRole("button", { name: "Save changes" }).click();
  await expect(drawer.getByRole("status")).toHaveText("Saved.");
  await expect(drawer.getByRole("heading", { name: "Red Bean Stew" })).toBeVisible();

  await drawer.getByLabel("Reason").fill("Duplicate of another stew.");
  await drawer.getByRole("button", { name: "Withdraw" }).click();
  const confirm = page.getByRole("alertdialog");
  await expect(confirm).toContainText("the planner never chooses it again");
  await confirm.getByRole("button", { name: "Withdraw" }).click();
  await expect(drawer.getByRole("status")).toContainText("Withdrawn.");
  await expect(drawer.getByRole("button", { name: "Restore" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-7-recipe.png` });
  await drawer.getByRole("button", { name: "Close" }).click();

  // Ingredients: add a Chinese name and an alias; allergens are view only.
  await page.getByRole("tab", { name: "Ingredients" }).click();
  await expect(page).toHaveURL(/tab=ingredients/);
  await page.getByRole("button", { name: "Peanut" }).click();
  await expect(page.getByRole("dialog").getByText("cannot be edited here")).toBeVisible();
  await expect(page.getByRole("dialog").getByLabel(/Allergen/)).toHaveCount(0);
  await page.getByRole("dialog").getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "Adzuki bean" }).click();
  const ingredient = page.getByRole("dialog");
  await ingredient.getByLabel("Chinese names, one per line").fill("红豆\n赤小豆");
  await ingredient.getByLabel("Other names (aliases), one per line").fill("red bean, azuki");
  await ingredient.getByRole("button", { name: "Save changes" }).click();
  await expect(ingredient.getByRole("status")).toContainText("Saved.");
  await expect(page.getByRole("region", { name: "Ingredients" }).getByRole("row", { name: /红豆、赤小豆/ })).toBeVisible();
  await ingredient.getByRole("button", { name: "Close" }).click();

  // Product mappings: search FairPrice and map the ingredient to another product.
  await page.getByRole("tab", { name: "Product mappings" }).click();
  const mappings = page.getByRole("region", { name: "Product mappings" });
  await expect(mappings.getByRole("row", { name: /Green Earth Organic Adzuki Beans .* S\$7\.20/ })).toBeVisible();
  await mappings.getByRole("button", { name: "Adzuki bean" }).click();
  const mapping = page.getByRole("dialog");
  await mapping.getByLabel("Search FairPrice").fill("adzuki beans");
  await mapping.getByRole("button", { name: "Search", exact: true }).click();
  await mapping.getByRole("list", { name: "Search results" }).getByRole("button", { name: "Use" }).click();
  await expect(mapping.getByLabel("Package in grams of this ingredient")).toHaveValue("400");
  await mapping.getByRole("button", { name: "Map to this product" }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Pasar Red Beans (400 g, S$2.15)");
  await page.getByRole("alertdialog").getByRole("button", { name: "Change mapping" }).click();
  await expect(mapping.getByRole("status")).toHaveText("Mapping changed.");
  await expect(mappings.getByRole("row", { name: /Pasar Red Beans .* Console/ })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ops-8-mapping.png` });
});
