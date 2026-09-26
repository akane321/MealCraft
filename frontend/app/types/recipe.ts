export interface RecipeNutrition {
  calories_kcal: number;
  protein_g: number;
  carbohydrate_g: number;
  fat_g: number;
  sodium_mg: number;
  sugar_g: number;
}

export interface RecipeListItem {
  id: number;
  slug: string;
  title: string;
  description: string;
  cuisine: string;
  meal_type: string;
  servings: number;
  total_time_minutes: number;
  dietary_tags: string[];
  nutrition: RecipeNutrition;
  course?: string | null;
}

export interface RecipeCollection {
  items: RecipeListItem[];
  next_cursor: number | null;
}

export interface RecipeIngredient {
  name: string;
  normalized_name: string;
  quantity: number | null;
  unit: string | null;
  preparation: string | null;
  allergens: string[];
}

export interface RecipeStep {
  step_number: number;
  instruction: string;
}

export interface RecipeDetail extends RecipeListItem {
  ingredients: RecipeIngredient[];
  steps: RecipeStep[];
}

export interface TutorialVideo {
  video_id: string;
  title: string;
  channel_title: string;
  watch_url: string;
  embed_url: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
}

export interface TutorialRecommendation {
  recipe_slug: string;
  recipe_title: string;
  selected_video: TutorialVideo | null;
  retrieval: { provider_used: "youtube" | "fixture"; mode: string; status: string };
  warning: string | null;
}
