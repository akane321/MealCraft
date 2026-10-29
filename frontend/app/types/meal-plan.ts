import type { RecipeListItem, RecipeNutrition } from "~/types/recipe";
import type { MealRole, PlannedMealType, PlanShape } from "~/types/household";
import type {
  GroceryLineEstimate,
  NutritionTargetsInput,
  PricingMode,
  RecipeRecommendationRequest,
} from "~/types/recommendation";

export interface WeeklyMealPlanRequest extends RecipeRecommendationRequest {
  start_date: string;
  day_count: number;
  weekly_budget_sgd: number | null;
}

export type MealPlanEntryStatus = "planned" | "completed" | "skipped";

export interface WeeklyPlanDay {
  entry_id: number;
  day_index: number;
  planned_date: string;
  /** One dish of one meal (ADR-0036); a one-dish plan is the dinner main at share 1. */
  meal_type: string;
  role_id: string;
  portion_share: number;
  /** Portions cooked of this dish (layer 08); null for a plan made without household rules. */
  servings?: number | null;
  /** Members at this meal who cannot eat this dish (ADR-0071); empty when everyone at the meal can. */
  not_for?: string[];
  recipe: RecipeListItem;
  recommendation_score: number;
  nutrition_per_person: RecipeNutrition;
  consumed_cost_sgd: number;
  purchase_cost_sgd: number;
  status: MealPlanEntryStatus;
  is_locked: boolean;
  consumed_at: string | null;
}

export type WeeklyNutritionSummary = RecipeNutrition;

export interface WeeklyGroceryEstimate {
  pricing_mode: PricingMode;
  complete: boolean;
  purchase_total_sgd: number;
  consumed_total_sgd: number | null;
  weekly_budget_sgd: number | null;
  within_weekly_budget: boolean | null;
  items: GroceryLineEstimate[];
  unmapped_ingredients: string[];
  warnings: string[];
}

export interface WeeklyMealPlan {
  current?: boolean;
  id: number;
  revision: number;
  household_profile_id: number | null;
  household_profile_version: number | null;
  replaces_plan_id: number | null;
  start_date: string;
  end_date: string;
  day_count: number;
  household_size: number;
  days: WeeklyPlanDay[];
  nutrition_summary_per_person: WeeklyNutritionSummary;
  grocery_estimate: WeeklyGroceryEstimate;
  warnings: string[];
  created_at: string;
  plan_shape?: PlanShape | null;
  /** Where each shopping trip's FairPrice cart stands, keyed "1", "2"; null before anything was sent. */
  fairprice_cart?: FairPriceCartState | null;
}

export interface WeeklyMealPlanListItem {
  id: number;
  revision: number;
  household_profile_id: number | null;
  household_profile_version: number | null;
  replaces_plan_id: number | null;
  start_date: string;
  end_date: string;
  household_size: number;
  purchase_total_sgd: number;
  consumed_total_sgd: number | null;
  within_weekly_budget: boolean | null;
  created_at: string;
  /** False when a newer plan covers any of its days and so replaced it (backend `current`). */
  current: boolean;
}

export interface WeeklyMealPlanCollection {
  items: WeeklyMealPlanListItem[];
}

export interface MealPlanStatusCounts {
  planned: number;
  completed: number;
  skipped: number;
}

export interface NutritionDashboardDay {
  entry_id: number;
  day_index: number;
  planned_date: string;
  recipe: RecipeListItem;
  status: MealPlanEntryStatus;
  is_locked: boolean;
  consumed_at: string | null;
  nutrition_per_person: RecipeNutrition;
  // Which meal and dish position this is, and its share of the meal (ADR-0046); absent means one dinner dish.
  meal_type?: "breakfast" | "lunch" | "dinner" | "snack";
  role_id?: string;
  portion_share?: number;
  /** Members at this meal who cannot eat this dish (ADR-0071); empty when everyone at the meal can. */
  not_for?: string[];
  /** The household's Like, Dislike or Never again on this dish (ADR-0087); null or absent when none. */
  feedback?: FeedbackKind | null;
  /** Up to two facts true of this dish (layer 08 section 7.2); empty or absent when none holds. */
  reasons?: DishReason[];
  /** What one serving cost, for the facts panel; null when the week saved no grocery estimate for it. */
  cost_per_serving_sgd?: number | null;
}

export interface DishReason {
  code: "preference" | "cheap_main" | "quick";
  label: string;
}

export type FeedbackKind = "like" | "dislike" | "never_again";

/** One dish of the household's feedback, as `GET /api/feedback/recipes` lists it. */
export interface RecipeFeedbackItem {
  recipe_id: number;
  slug: string;
  title: string;
  kind: FeedbackKind;
  created_at: string;
}

export interface WeeklyNutritionDashboard {
  plan_id: number;
  revision: number;
  start_date: string;
  end_date: string;
  household_size: number;
  completion_rate: number;
  status_counts: MealPlanStatusCounts;
  nutrition_targets: NutritionTargetsInput;
  planned_nutrition_per_person: WeeklyNutritionSummary;
  completed_nutrition_per_person: WeeklyNutritionSummary;
  days: NutritionDashboardDay[];
}

export type MealPlanEventType = "REPLACE_MEAL" | "CANCEL_MEAL" | "LOCK_MEAL" | "ITEM_UNAVAILABLE" | "CHANGE_SHAPE";
export type MealPlanEventStatus = "previewed" | "applied";

export interface MealPlanEntrySnapshot {
  entry_id: number;
  day_index?: number | null;
  meal_type?: string;
  recipe_id: number;
  recipe_slug: string;
  recipe_title: string;
  status: MealPlanEntryStatus;
  is_locked: boolean;
  recommendation_score: number;
  // The dish role it fills in its meal (backend MealPlanEntrySnapshot).
  role_id?: string | null;
}

export interface MealPlanNutritionDelta {
  calories_kcal: number;
  protein_g: number;
  carbohydrate_g: number;
  fat_g: number;
  sodium_mg: number;
  sugar_g: number;
}

export interface MealPlanGroceryDeltaLine {
  ingredient_name: string;
  ingredient_display_name: string;
  change: "added" | "removed" | "updated";
  before_required_quantity: number | null;
  after_required_quantity: number | null;
  unit: string | null;
  before_packages_required: number;
  after_packages_required: number;
  purchase_cost_delta_sgd: number;
}

export interface MealPlanReplanPreviewRequest {
  event_type: MealPlanEventType;
  entry_id: number;
  reason: string | null;
  unavailable_ingredient: string | null;
}

/** A meal added, dropped or recomposed on some days (ADR-0046). */
export interface MealPlanShapeChange {
  meal_type: PlannedMealType;
  scope: "week" | "meal";
  day_indexes: number[];
  roles: MealRole[] | null;
  removed: MealPlanEntrySnapshot[];
  added: MealPlanEntrySnapshot[];
  // The dishes that stay on their day while one is added or taken away; in neither list.
  kept?: number;
  plan_shape: PlanShape | null;
}

export interface MealPlanReplanEvent {
  id: number;
  plan_id: number;
  base_revision: number;
  applied_revision: number | null;
  event_type: MealPlanEventType;
  status: MealPlanEventStatus;
  reason: string | null;
  unavailable_ingredient: string | null;
  // Null for a shape change, which moves several dishes (shape_change).
  before_entry: MealPlanEntrySnapshot | null;
  after_entry: MealPlanEntrySnapshot | null;
  // A whole-meal lock: every dish of before_entry's meal it keeps; empty otherwise.
  meal_entries?: MealPlanEntrySnapshot[];
  shape_change?: MealPlanShapeChange | null;
  nutrition_delta: MealPlanNutritionDelta;
  grocery_delta: MealPlanGroceryDeltaLine[];
  purchase_total_delta_sgd: number;
  // How far a change that costs more takes the week over its weekly budget; null within it, and for a keep or a skip.
  over_budget_sgd?: number | null;
  created_at: string;
  applied_at: string | null;
}

export interface MealPlanReplanEventCollection {
  items: MealPlanReplanEvent[];
}

export interface MealPlanReplanConfirmation {
  event: MealPlanReplanEvent;
  plan: WeeklyMealPlan;
}

// FairPrice cart (docs/design/fairprice-cart.md): the list is checked live, sent to the person's own cart by the
// browser extension, and what the extension did is reported back.
export type FairPriceLineStatus = "ready" | "out_of_stock" | "not_found" | "no_product" | "not_bought";

export interface FairPriceCartLine {
  /** "{trip or 1}|{ingredient_name}|{unit or ''}", the line's identity in a plan. */
  line_key: string;
  ingredient_name: string;
  ingredient_display_name: string;
  product_name: string | null;
  client_item_id: string | null;
  /** FairPrice's internal product id, the one its cart takes; null when the live listing gave none (a ready line always has one). */
  cart_item_id: string | null;
  quantity: number;
  planned_price_sgd: number | null;
  live_price_sgd: number | null;
  product_url: string | null;
  status: FairPriceLineStatus;
}

export interface FairPriceCartPrepare {
  plan_id: number;
  shopping_trip: number | null;
  fingerprint: string;
  lines: FairPriceCartLine[];
  ready_total_sgd: number;
  planned_total_sgd: number;
  projected_total_sgd: number;
  budget_sgd: number | null;
  over_budget: boolean;
}

export type FairPriceResultStatus = "added" | "reduced" | "out_of_stock" | "failed";

export interface FairPriceCartResult {
  line_key: string;
  cart_item_id: string | null;
  status: FairPriceResultStatus;
  /** What this add put in the cart: the asked quantity when added, less when reduced, 0 otherwise. */
  quantity: number;
  cart_price_sgd: number | null;
}

export interface FairPriceCartReportBody {
  shopping_trip: number | null;
  fingerprint: string;
  results: FairPriceCartResult[];
}

export interface FairPriceCartTrip {
  status: "in_cart" | "ordered";
  sent_at: string;
  ordered_at?: string | null;
  fingerprint: string;
  results: FairPriceCartResult[];
  /** True when the plan's list changed after it was sent. */
  stale?: boolean;
}

export type FairPriceCartState = Record<string, FairPriceCartTrip>;

/** What the extension sends back: `error` is set when `ok` is false. Whether the cart was written depends on the error (see cartErrorMessage). */
export type FairPriceExtensionError =
  | "not_logged_in" | "cart_unreadable" | "request_refused" | "unexpected_response" | "invalid_request" | "busy"
  // A row write for an item that is no longer in the cart; nothing was written:
  | "not_in_cart"
  // Said by the page itself, not the extension ("interrupted": the extension stopped before it answered, so a write may have happened):
  | "no_extension" | "timeout" | "interrupted";

export interface FairPriceExtensionReply {
  ok: boolean;
  error?: FairPriceExtensionError;
  version?: string;
  results?: FairPriceCartResult[];
  /** Ids of other items in the cart whose quantity differed after the write. */
  cart_changed?: string[];
  /** A dry run wrote nothing and is never reported. */
  dry_run?: boolean;
  /** The person's FairPrice cart as it is now (get_cart, set_quantity, and add_to_cart after its write). */
  cart?: FairPriceLiveCart;
}

// The person's real FairPrice cart, as the extension normalizes it (no address, account or token).
export interface FairPriceCartItem {
  cart_item_id: string;
  name: string;
  brand: string | null;
  display_unit: string | null;
  image_url: string | null;
  product_url: string | null;
  quantity: number;
  /** The three money fields are null when FairPrice's reply gave no price. */
  unit_price_sgd: number | null;
  /** The price before any discount; above `unit_price_sgd` when discounted. */
  unit_mrp_sgd: number | null;
  line_total_sgd: number | null;
  line_saving_sgd: number | null;
  max_quantity: number;
  is_checked: boolean;
  /** The site's own row notice: "Only 2 left", "Back in stock". */
  note: string | null;
  /** A free item the server added: shown, never changed. */
  is_free?: boolean;
}

export interface FairPriceUnavailableItem {
  cart_item_id: string;
  name: string;
  image_url: string | null;
  want_quantity: number;
}

export interface FairPriceCartTotals {
  /** Null when FairPrice's reply gave no subtotal. */
  subtotal_sgd: number | null;
  savings_sgd: number;
  delivery_sgd: number;
  delivery_standard_sgd: number;
  service_fee_sgd: number;
  service_fee_standard_sgd: number;
  /** Null when FairPrice's reply gave no total ("you pay"). */
  total_sgd: number | null;
}

export interface FairPriceLiveCart {
  store: { id: string; name: string } | null;
  items: FairPriceCartItem[];
  unavailable: FairPriceUnavailableItem[];
  totals: FairPriceCartTotals;
}

export interface FairPriceCartAddLine {
  line_key: string;
  cart_item_id: string;
  quantity: number;
}
