import { onMounted, shallowRef } from "vue";

// app/assets/food-images.json (scripts/build_food_images.py): each dish image with the recipes it stands for (a curated slug, or the last 12
// characters of a release slug, space separated to keep the file small), the ingredients that have a picture, and for a dish imported from the
// web the picture of each title word, rarest word first, then the picture to use when no word matches.
export type FoodImageFile = { dishes: Record<string, string>; ingredients: string[]; words: Record<string, string>; fallback: string };
export type FoodImageIndex = { dishes: Map<string, string>; ingredients: Set<string>; words: Map<string, { image: string; rank: number }>; fallback: string };

export function indexFoodImages(file: FoodImageFile): FoodImageIndex {
  const dishes = new Map<string, string>();
  for (const [image, ids] of Object.entries(file.dishes)) {
    for (const id of ids.split(" ")) dishes.set(id, image);
  }
  const words = new Map(Object.entries(file.words).map(([word, image], rank) => [word, { image, rank }]));
  return { dishes, ingredients: new Set(file.ingredients), words, fallback: file.fallback };
}

function nearestByTitle(index: FoodImageIndex, title: string): string {
  const known = (title.toLowerCase().match(/[a-z]+/g) ?? []).flatMap((word) => index.words.get(word) ?? []);
  return known.sort((a, b) => a.rank - b.rank)[0]?.image ?? index.fallback;
}

// Null only until the map has loaded.
export function dishImageSrc(index: FoodImageIndex | null, slug: string, title = ""): string | null {
  if (!index) return null;
  return `/images/dishes/${index.dishes.get(slug) ?? index.dishes.get(slug.slice(-12)) ?? nearestByTitle(index, title)}.webp`;
}

export function ingredientImageSrc(index: FoodImageIndex | null, name: string): string | null {
  const key = name.toLowerCase().replace(/[^a-z0-9]/g, "-");
  return index?.ingredients.has(key) ? `/images/ingredients/${key}.webp` : null;
}

const index = shallowRef<FoodImageIndex | null>(null);
let requested = false;

// Read once per page load, in the browser only: the server renders empty discs, so hydration matches.
// A dynamic import gives the map a content-hashed chunk, so a browser never keeps an old copy; a failure retries on the next mount.
export function useFoodImages() {
  onMounted(() => {
    if (requested) return;
    requested = true;
    import("../assets/food-images.json")
      .then((file) => { index.value = indexFoodImages(file.default); })
      .catch(() => { requested = false; });
  });
  return {
    dishSrc: (slug: string, title?: string) => dishImageSrc(index.value, slug, title),
    ingredientSrc: (name: string) => ingredientImageSrc(index.value, name),
  };
}
