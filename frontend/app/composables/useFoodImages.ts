import { onMounted, shallowRef } from "vue";

// public/images/food-images.json: each dish image with the recipe ids it stands for (the last 12 characters of a
// release slug, space separated to keep the file small), and the ingredients that have a picture.
export type FoodImageFile = { dishes: Record<string, string>; ingredients: string[] };
export type FoodImageIndex = { dishes: Map<string, string>; ingredients: Set<string> };

export function indexFoodImages(file: FoodImageFile): FoodImageIndex {
  const dishes = new Map<string, string>();
  for (const [image, ids] of Object.entries(file.dishes)) {
    for (const id of ids.split(" ")) dishes.set(id, image);
  }
  return { dishes, ingredients: new Set(file.ingredients) };
}

export function dishImageSrc(index: FoodImageIndex | null, slug: string): string | null {
  const image = index?.dishes.get(slug.slice(-12));
  return image ? `/images/dishes/${image}.webp` : null;
}

export function ingredientImageSrc(index: FoodImageIndex | null, name: string): string | null {
  const key = name.toLowerCase().replace(/[^a-z0-9]/g, "-");
  return index?.ingredients.has(key) ? `/images/ingredients/${key}.webp` : null;
}

const index = shallowRef<FoodImageIndex | null>(null);
let requested = false;

// Read once per page load, in the browser only: the server renders the drawn icons, so hydration matches.
export function useFoodImages() {
  onMounted(() => {
    if (requested) return;
    requested = true;
    fetch("/images/food-images.json")
      .then(response => (response.ok ? response.json() : null))
      .then((file: FoodImageFile | null) => { if (file) index.value = indexFoodImages(file); })
      .catch(() => {});
  });
  return {
    dishSrc: (slug: string) => dishImageSrc(index.value, slug),
    ingredientSrc: (name: string) => ingredientImageSrc(index.value, name),
  };
}
