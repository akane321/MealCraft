# Food images

Illustrative photos for dishes (`dishes/`, 320 px) and ingredients (`ingredients/`, 192 px), as WebP at quality 78.
They are AI-generated, not photographs of the dishes; the recipe dialog says so.

- Model: FLUX.1-schnell (Black Forest Labs, Apache-2.0), run locally at 512 px with 4 steps.
- Dish images: one per group of similar recipes in release v3 (1,915 images for 18,335 recipes), so similar dishes
  share a picture. Recipes in catch-all groups reuse the nearest picture (TF-IDF on title and ingredients).
- Ingredient images: one per canonical ingredient (701), on white.
- Prompts, seeds and scripts stay outside this repo, in the course folder `local-image-gen/` (`prompts.py`,
  `make_batch.py`, `batch_jobs.json`, `gen_batch.py`). Seven ingredients with a grey background were re-rendered on
  other seeds on 2026-11-06: halloumi, vanilla ice cream, milk or water, mixed vegetables, mushroom, stuffing mix
  and mascarpone.

`food-images.json` maps them. `dishes` lists, per image, the recipes it stands for (the last 12 characters of the
slug). `ingredients` lists the file names: the lower-cased display name with every non-alphanumeric character replaced
by `-`. A recipe that is not listed (curated or private) keeps its drawn icon.
