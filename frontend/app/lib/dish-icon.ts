export type DishRole = "main" | "vegetable" | "soup" | "salad" | "drink" | "dessert" | "other";
export type FoodGroup = "noodles" | "rice" | "poultry" | "red_meat" | "seafood" | "tofu_egg" | "leafy" | "veg_mix" | "broth" | "bread" | "fruit_sweet" | "mixed";

export const DISH_ROLES: DishRole[] = ["main", "vegetable", "soup", "salad", "drink", "dessert", "other"];
export const FOOD_GROUPS: FoodGroup[] = ["noodles", "rice", "poultry", "red_meat", "seafood", "tofu_egg", "leafy", "veg_mix", "broth", "bread", "fruit_sweet", "mixed"];

/** What the frontend already has per dish: RecipeListItem (title, cuisine, course), RecipeDetail.ingredients[], plan entries (role_id, recipe_title). */
export interface DishLike {
  title?: string | null;
  course?: string | null;
  roleId?: string | null;
  cuisine?: string | null;
  ingredients?: (string | { name?: string | null; normalized_name?: string | null })[] | null;
}

// ponytail: keyword heuristic; use a catalog ingredient-group field if the API adds one
// Order = precedence: the first row that matches wins. Egg sits below the meats so "chicken and egg" reads as poultry.
const GROUP_RULES: [FoodGroup, RegExp][] = [
  ["noodles", /\b(noodles?|pasta|spaghetti|laksa|ramen|udon|vermicelli|bee ?hoon|mee|macaroni|linguine|fettuccine)\b|面|粉丝|米粉|河粉/i],
  ["rice", /\b(rice|risotto|congee|porridge|biryani|nasi|pilaf)\b|饭|粥/i],
  ["tofu_egg", /\b(tofu|tempeh|bean ?curd|taukwa)\b|豆腐/i],
  ["seafood", /\b(fish|salmon|cod|tuna|prawns?|shrimps?|squid|crab|clams?|mussels?|scallops?|seafood|barramundi|sea ?bass|mackerel|anchov\w*|sardines?|lobster|oysters?)\b|鱼|虾|蟹|贝|鱿/i],
  ["poultry", /\b(chicken|duck|turkey|poultry|drumsticks?|wings?)\b|鸡|鸭/i],
  ["red_meat", /\b(beef|pork|lamb|mutton|steak|bacon|ham|sausages?|mince|meatballs?|ribs?|veal)\b|牛|猪|羊|肉/i],
  ["tofu_egg", /\beggs?\b|蛋/i],
  ["bread", /\b(bread|toast|bun|buns|bagel|sandwich|burger|wrap|tortilla|naan|roti|prata|pizza|pancakes?)\b|面包|饼/i],
  ["leafy", /\b(kai ?lan|bok ?choy|pak ?choi|choy ?sum|spinach|lettuce|cabbage|kale|kangkong|water spinach|rocket|arugula|greens|romaine|watercress|xiao bai cai)\b|菜心|白菜|青菜|菠菜|生菜|芥兰|空心菜/i],
  ["veg_mix", /\b(carrots?|peas?|broccoli|cauliflower|mushrooms?|tomato\w*|corn|capsicum|bell pepper|zucchini|courgette|eggplant|aubergine|beans?|okra|pumpkin|potato\w*|onions?|cucumber|vegetables?|veggies?)\b|胡萝卜|豌豆|西兰花|蘑菇|番茄|土豆|蔬菜/i],
  ["fruit_sweet", /\b(apples?|bananas?|berry|berries|strawberr\w*|blueberr\w*|mango\w*|grapes?|melon|pineapple|peach|fruit|chocolate|cake|pudding|ice ?cream|jelly|custard|cookies?|brownies?)\b|水果|苹果|香蕉|芒果|蛋糕/i],
  ["broth", /\b(soup|broth|consomme|chowder|stew)\b|汤/i],
];

const DRINK_RE = /\b(tea|coffee|juice|smoothie|latte|milkshake|shake|lemonade|cocktail|drink|kopi|teh|milo)\b|茶|咖啡|果汁|饮/i;
const DESSERT_RE = /\b(dessert|cake|pudding|ice ?cream|custard|brownies?|cookies?|tart|mousse|sorbet|jelly)\b|甜点|蛋糕|布丁/i;
const SOUP_RE = /\b(soup|broth|chowder|consomme)\b|汤/i;
const SALAD_RE = /\b(salad|slaw)\b|沙拉/i;

const COURSE_ROLE: Record<string, DishRole> = {
  main: "main", side: "vegetable", vegetable: "vegetable", soup: "soup", salad: "salad", drink: "drink", beverage: "drink", dessert: "dessert",
};
const ROLE_DEFAULT_GROUP: Partial<Record<DishRole, FoodGroup>> = { soup: "broth", salad: "leafy", vegetable: "veg_mix", dessert: "fruit_sweet", drink: "fruit_sweet" };

function norm(v: string | null | undefined): string {
  return (v ?? "").toLowerCase().replace(/[_-]+/g, " ").replace(/\s+\d+$/, "").trim();
}

/** Role precedence: course -> role_id (e.g. "main-2", "side") -> title keywords -> "other". */
export function dishRole(dish: DishLike): DishRole {
  const byCourse = COURSE_ROLE[norm(dish.course)];
  if (byCourse) return byCourse;
  const byId = COURSE_ROLE[norm(dish.roleId)];
  if (byId) return byId;
  const title = dish.title ?? "";
  if (DRINK_RE.test(title)) return "drink";
  if (SOUP_RE.test(title)) return "soup";
  if (SALAD_RE.test(title)) return "salad";
  if (DESSERT_RE.test(title)) return "dessert";
  return "other";
}

function matchGroup(text: string): FoodGroup | null {
  for (const [group, re] of GROUP_RULES) if (re.test(text)) return group;
  return null;
}

/**
 * Group precedence: soup role is always broth (the bowl is the point) -> ingredient names
 * (first GROUP_RULES row any ingredient hits) -> title -> role default -> mixed.
 * Ingredient lists never pick "broth" (stock is everywhere); only the title can.
 */
export function foodGroup(dish: DishLike, role: DishRole = dishRole(dish)): FoodGroup {
  if (role === "soup") return "broth";
  const names = (dish.ingredients ?? []).map((i) => (typeof i === "string" ? i : `${i.normalized_name ?? ""} ${i.name ?? ""}`)).join(" | ");
  const fromIngredients = names ? matchGroup(names) : null;
  if (fromIngredients && fromIngredients !== "broth") return fromIngredients;
  return matchGroup(dish.title ?? "") ?? ROLE_DEFAULT_GROUP[role] ?? "mixed";
}
