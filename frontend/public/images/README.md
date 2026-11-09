# Food images

Illustrative photos for dishes (`dishes/`, 320 px) and ingredients (`ingredients/`, 192 px), as WebP at quality 78.
They are AI-generated, not photographs of the dishes.

- Model: FLUX.1-schnell (Black Forest Labs, Apache-2.0), run locally at 512 px with 4 steps.
- Dish images: one per group of similar recipes in release v3, so similar dishes share a picture. Recipes in
  catch-all groups reuse the nearest picture (TF-IDF on title and ingredients). 1,809 images serve all 18,335
  recipes and the 30 curated ones.
- Ingredient images: one per canonical ingredient (701), on white.
- Prompts, seeds and scripts stay outside this repo, in the course folder `local-image-gen/` (`prompts.py`,
  `make_batch.py`, `batch_jobs.json`, `gen_batch.py`). Seven ingredients with a grey background were re-rendered on
  other seeds on 2026-11-06: halloumi, vanilla ice cream, milk or water, mixed vegetables, mushroom, stuffing mix
  and mascarpone.

`app/assets/food-images.json` maps them, built by `scripts/build_food_images.py` (rerun it if recipes or images
change). `dishes` lists, per image, the recipes it stands for (the last 12 characters of a release slug, a curated slug whole). `ingredients` lists
the file names: the lower-cased display name with every non-alphanumeric character replaced by `-`. A dish that is not
listed (imported from the web) takes the picture of the rarest word of its title that `words` knows, else
`fallback`. Neither shows meat for a word that many meatless recipes use.

A shared AI picture must not contradict a recipe, so a recipe gets no picture that shows meat or fish it lacks (from the
prompt, from the recipes sharing the image, and for what the model added on its own, `SHOWS_MEAT`, listed by eye from
thumbnails of every image still serving a meatless recipe: a cautious review, not a guarantee), no egg or dairy picture
if vegan, and none whose dish word (soup, cake, ...) is rare among the recipes sharing it. Such a recipe takes the
nearest picture that passes; when none does (124 recipes, all for the dish word), the dish word gives way.
