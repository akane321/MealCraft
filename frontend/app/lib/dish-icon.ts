export type DishContainer = "plate" | "dish" | "bowl" | "shallow" | "dessert" | "drink";
export type DishGroup = "noodles" | "rice" | "poultry" | "red-meat" | "seafood" | "tofu-egg" | "greens" | "veg" | "broth" | "bread" | "fruit" | "mixed";

// Order matters: the first group with a matching keyword wins (specific before general).
// ponytail: keyword heuristic; use a catalog ingredient-group field if the API adds one
const KEYWORDS: Array<[DishGroup, RegExp]> = [
  ["noodles", /noodle|pasta|spaghetti|ramen|laksa|udon|vermicelli|bee hoon|\bmee\b|macaroni|linguine|penne|lasagn/],
  ["rice", /\brice\b|risotto|biryani|congee|porridge|pilaf|nasi|claypot|fried rice/],
  ["poultry", /chicken|duck|turkey|poultry/],
  ["red-meat", /beef|lamb|mutton|pork|steak|meatball|rendang|burger|bacon|sausage|ham\b|ribs?\b/],
  ["seafood", /fish|salmon|tuna|prawn|shrimp|crab|squid|cod\b|sea bass|seafood|mussel|clam|sardine|mackerel|barramundi|anchov/],
  ["tofu-egg", /tofu|\begg(?!plant)|omelet|frittata|tempeh|bean curd|shakshuka/],
  ["greens", /salad|spinach|kale|lettuce|cabbage|bok choy|pak choi|kailan|broccoli|greens|cucumber|asparagus|beans?\b|choy sum/],
  ["bread", /bread|toast|sandwich|wrap|bun\b|pancake|waffle|muffin|pastry|pie\b|cake|cookie|scone|roti|prata|naan|pizza|quesadilla|taco/],
  ["fruit", /fruit|apple|banana|berry|berries|mango|orange|lemon|pudding|ice cream|custard|mousse|smoothie|jelly|dessert|compote/],
  ["broth", /soup|broth|stew|chowder|bisque|\bpot\b|hotpot|consomm|curry/],
  ["veg", /potato|carrot|pumpkin|squash|tomato|mushroom|eggplant|aubergine|corn|vegetable|veggie|zucchini|courgette|sweet potato|yam|radish|onion|pepper|stir[- ]fry/],
];

export function dishGroup(title: string, ingredients: string[] = []): DishGroup {
  // The title names the dish; ingredients are only a second look so a "stir-fry" with chicken still reads as chicken.
  for (const text of [title.toLowerCase(), ingredients.join(" ").toLowerCase()]) {
    if (!text) continue;
    for (const [group, pattern] of KEYWORDS) if (pattern.test(text)) return group;
  }
  return "mixed";
}

/** Container from the dish role: course first, then the planned role id. */
export function dishContainer(course?: string | null, roleId?: string | null): DishContainer {
  const key = course ?? roleId ?? "main";
  if (key === "soup") return "bowl";
  if (key === "salad") return "shallow";
  if (key === "side" || key === "vegetable") return "dish";
  if (key === "dessert" || key === "baked_good") return "dessert";
  if (key === "drink") return "drink";
  return "plate";
}
