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
  allergen: string | null;
}

export interface RecipeStep {
  step_number: number;
  instruction: string;
}

export interface RecipeDetail extends RecipeListItem {
  ingredients: RecipeIngredient[];
  steps: RecipeStep[];
}
