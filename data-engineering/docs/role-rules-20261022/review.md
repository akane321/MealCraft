# Role-rule review suggestions

Generated with `data-engineering/scripts/role_rules_review.py`. No row is human-verified by this tool. Frozen model values and review flags are unchanged.

Base: `31ece86`. Random sample seed: 20261022. Rule-owned changes: 27. Frozen suggestions: 422. Deferred bean sides: 15.

The specific 109 IDs have not been supplied; the complete frozen batch is included below. Do not interpret a suggested role or an allowed role as review/acceptance.

## Frozen recipes reached by each new rule

These are evidence/rule categories, not reviewed truth; missing-data reasons and the model freeze still bind.

| Rule | Frozen recipes | IDs |
|---|---:|---|
| homemade_staple | 38 | RCP2_0CA3F3F66929, RCP2_0DBC46FF845C, RCP2_143B82A4800E, RCP2_16BF42FD100D, RCP2_1A1BA06D6CB5, RCP2_23DCDA368745, RCP2_2AC94AA7906B, RCP2_2E3012F8BABC, RCP2_3314EF4C89E1, RCP2_38391F938210, RCP2_43F241E2C2FA, RCP2_45391BFD9020, RCP2_47186AAC9989, RCP2_4B3B02F3D728, RCP2_4E9F363F8876, RCP2_5C8F72777948, RCP2_5F632D436B4E, RCP2_5FFD99ABD34E, RCP2_646039848924, RCP2_6C1E6D9E70BE, RCP2_6D9B39CCD991, RCP2_70B47600544A, RCP2_7791CF2A7CDD, RCP2_7F94EA2E2036, RCP2_829671202485, RCP2_92D0966923D6, RCP2_9CD7CD0DA72B, RCP2_A986B63ED3FF, RCP2_B8238A4718B6, RCP2_BA95359C23B7, RCP2_BBD46E78E711, RCP2_C8B759477F8B, RCP2_D57A6F473637, RCP2_E20C08DE6172, RCP2_E34384C91EB9, RCP2_EC29565337D3, RCP2_F918B184F959, RCP2_FB5F31874C8A |
| meat_seasoned_vegetable | 18 | RCP2_1087CA73F93D, RCP2_1106936B4750, RCP2_15BCD52E8739, RCP2_24B9AA68594B, RCP2_546DFF631ED4, RCP2_57E2F87CA748, RCP2_5ED49FFCF6D4, RCP2_5FDC54ED6B2B, RCP2_641ABD3FC590, RCP2_66CDC4D02656, RCP2_783368D92192, RCP2_7EC289C20A2A, RCP2_89F0058D53F5, RCP2_C81AEF8EF1AC, RCP2_D86FDF8D821E, RCP2_D8E98D9FFC37, RCP2_E091A77EFBE5, RCP2_F015BE03BD1C |
| protein_led_side | 24 | RCP2_15F1AAB4C310, RCP2_1722D847EECE, RCP2_33B9F1AECB3E, RCP2_4539937C1F3A, RCP2_45BE0219D45D, RCP2_472B6677B22B, RCP2_4869C3AEA8AD, RCP2_486E1D6A70D8, RCP2_6336ACA2F9AE, RCP2_6B3C9AD9D6E0, RCP2_6E757674305D, RCP2_7DCEB197520A, RCP2_888730AE4624, RCP2_88FDB464A695, RCP2_8D376D61D13A, RCP2_9150197BEBD9, RCP2_920C40633EDD, RCP2_92F5CA7EC6D3, RCP2_958B37782112, RCP2_9E095D1F1FB4, RCP2_A268F28D4812, RCP2_A86E37A6C8F4, RCP2_E8D667BA918A, RCP2_ED8C37EACE4D |

## Meat-share distribution (vegetable-led sides/salads containing flesh)

| Counted flesh share | Recipes |
|---|---:|
| (0,5%] | 12 |
| (10,15%] | 19 |
| (15,20%] | 17 |
| (20,25%] | 5 |
| (25,30%] | 10 |
| (30,40%] | 11 |
| (40,50%] | 5 |
| (5,10%] | 13 |
| unknown | 1 |

The 20% default is a conservative, interpretable boundary before the sparse 20–25% bin, not a statistically proved universal divide. Unknown quantities are excluded. See review.json for every newly admitted content candidate and its weighed evidence.

## Newly content-admitted vegetable candidates

This list describes the flesh-share gate only. Frozen tags, missing ingredients, course/role, member restrictions and other planning gates may still exclude a recipe.

| ID | Recipe | Flesh share | Frozen |
|---|---|---:|---|
| RCP2_010D47D8B41A | Mexican Crab Salad | 15.42% | False |
| RCP2_0403B8D87889 | Turnip Greens | 13.37% | False |
| RCP2_04FC6484009B | Mediterranean Tabbouleh | 15.29% | False |
| RCP2_0537FFE83166 | Barbecued Green Beans | 15.97% | False |
| RCP2_056FEB8B1C07 | Stewed Okra And Tomatoes | 3.40% | False |
| RCP2_0724466545EF | Kimchi With Daikon Radish | 1.79% | False |
| RCP2_081D6225586A | Daikon Kimchi | 0.93% | False |
| RCP2_0C19BCC4EDA8 | Vietnamese Chicken Cabbage Salad | 19.89% | False |
| RCP2_0DBD84E7C323 | Texas Okra And Tomatoes | 10.06% | False |
| RCP2_0FC977DCA3B4 | Broccoli Raisin Salad | 4.00% | False |
| RCP2_1087CA73F93D | Southern Smothered Green Beans | 17.53% | True |
| RCP2_1106936B4750 | Sweet And Sour Cabbage | 7.99% | True |
| RCP2_138C3FC46F0B | Cauliflower Salad(Make 24 Hours Ahead) | 5.36% | False |
| RCP2_15BCD52E8739 | Sprouts, Chorizo & Almond Bowl | 8.21% | True |
| RCP2_1A1EA8E63135 | Korean Salad | 16.79% | False |
| RCP2_20375A8F16C9 | Mediterranean Vegetable Casserole | 2.41% | False |
| RCP2_24B9AA68594B | Mushroom Supreme | 15.83% | True |
| RCP2_24ED2AE8A798 | Sweet And Sour Greens | 12.90% | False |
| RCP2_27674C5EEA07 | Italian Spinach Salad - Toh | 6.37% | False |
| RCP2_294D48225815 | Fresh Broccoli Salad | 13.00% | False |
| RCP2_29EADB2B9636 | Terry'S Feta-Bacon Zucchini | 3.40% | False |
| RCP2_2B542AC009D4 | Favorite Broccoli Salad | 12.78% | False |
| RCP2_2DA348FB447B | Curry Coleslaw | 4.35% | False |
| RCP2_2F1C44136A22 | Korean Salad | 18.99% | False |
| RCP2_305281DC4061 | Caesar Salad | 3.03% | False |
| RCP2_31CA4DA49B46 | Creamy Fresh Corn | 11.68% | False |
| RCP2_33D380525A75 | Cauliflower Salad | 18.73% | False |
| RCP2_36D4A3CA2374 | Vietnamese Cabbage Salad | 18.77% | False |
| RCP2_3A4F20CBF931 | Slata Tunisiya - Tunisian Salad | 7.76% | False |
| RCP2_431BB9960EB2 | Baked Sauerkraut Wirth | 7.60% | False |
| RCP2_4B90C8F8B8F7 | Korean Salad | 15.18% | False |
| RCP2_546DFF631ED4 | Cauliflower Au Gratin | 12.70% | True |
| RCP2_57E2F87CA748 | Grandma'S Sweet And Sauerkraut | 13.17% | True |
| RCP2_5ED49FFCF6D4 | Spanish Rice | 10.27% | True |
| RCP2_5FDC54ED6B2B | Sauerkraut | 18.05% | True |
| RCP2_641ABD3FC590 | Bavarian Cabbage | 9.15% | True |
| RCP2_66CDC4D02656 | Napa Cabbage with Dried Shrimp | 2.13% | True |
| RCP2_6B7C34C7955A | Antipasto Salad(Six Main Course Servings Or 12 First Course Servings) | 5.70% | False |
| RCP2_6C04EF417AF0 | German-Style Cabbage And Beans | 10.06% | False |
| RCP2_783368D92192 | Tempura | 12.56% | True |
| RCP2_7EC289C20A2A | Savory Sauerkraut Casserole | 14.78% | True |
| RCP2_7FA1C2089917 | Curried Couscous Salad | 4.49% | False |
| RCP2_84C25BF48AA5 | Bacon And Feta Green Beans | 10.21% | False |
| RCP2_89F0058D53F5 | German Style Beans | 14.80% | True |
| RCP2_8B2F4B847EE8 | Braised Celery (Irish) | 8.39% | False |
| RCP2_8CA1A70205AB | Sweet-Sour Red Cabbage | 10.98% | False |
| RCP2_9239A388BD64 | Korean Spinach Salad | 5.26% | False |
| RCP2_96DC46181242 | Sweet And Sour Cabbage With Bacon | 16.41% | False |
| RCP2_B26CCDD9EC11 | Teriyaki Mushroom Salad | 4.07% | False |
| RCP2_B8BA70677774 | Ceviche With Cabbage | 10.84% | False |
| RCP2_BB96EC674F08 | Baked Sauerkraut Wirth | 7.60% | False |
| RCP2_BEF6AEB06ABA | Tabbouleh With Chicken And Red Pepper | 14.21% | False |
| RCP2_C81AEF8EF1AC | Onion Creme Brulee | 10.57% | True |
| RCP2_CAA027B54117 | Greek Salad | 1.62% | False |
| RCP2_D190FCD7C0C1 | Sweet And Sour Red Cabbage | 16.41% | False |
| RCP2_D86FDF8D821E | Sweet And Sour Cabbage | 16.41% | True |
| RCP2_D8E98D9FFC37 | Tomatoes Provencale | 11.87% | True |
| RCP2_E091A77EFBE5 | Sauerkraut Auf Bayische Art(Bavarian Style Sauerkraut) | 6.13% | True |
| RCP2_F015BE03BD1C | Bubble And Squeak | 9.95% | True |
| RCP2_F216A17B1A97 | Couscous Seafood Side Salad | 17.18% | False |
| RCP2_F99CD39666E1 | Japanese Salad | 17.90% | False |

## Fixed-seed random sample — human confirmation required

### RCP2_96C115F8AE38 — Black Bean Garlic Edamame

Changes: `{"meal_role": {"before": "vegetable", "after": "protein_main"}}`

- 1 tablespoon peanut oil — 13.5 g
- 4 cloves garlic, minced — 12.0 g
- 2 pounds fresh edamame (in shell) — 907.2 g
- 1/4 cup black bean sauce — 76.0 g

Human decision: pending.

### RCP2_29EADB2B9636 — Terry'S Feta-Bacon Zucchini

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 4 medium zucchini, about 8-9-inch long — 784.0 g
- 2 tablespoons olive oil — 27.0 g
- 1 garlic clove, minced — 3.0 g
- 2 tablespoons parsley, chopped fine — 7.5 g
- 1/4 teaspoon pepper (no salt needed) — 0.6 g
- 4 pieces bacon, cooked and crumbled — 32.4 g
- 4 ounces feta cheese, crumbled — 113.4 g
- 2 tablespoons parmesan cheese, grated — 12.5 g

Human decision: pending.

### RCP2_84C25BF48AA5 — Bacon And Feta Green Beans

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 8 slices bacon, cooked, crumbled, and divided — 64.8 g
- 1 lb fresh green beans, cooked al dente with still some crunch to them — 453.6 g
- 1 teaspoon minced garlic — 2.8 g
- 4 ounces feta cheese, crumbled and divided — 113.4 g
- 1/2 teaspoon onion powder — 1.2 g
- 1/8 teaspoon ground black pepper — 0.3 g
- 2 tablespoons water — 29.6 g

Human decision: pending.

### RCP2_20375A8F16C9 — Mediterranean Vegetable Casserole

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 1 None aubergine, sliced lengthwise — 300.0 g
- 2 None courgettes, sliced legnthwise — 392.0 g
- 4-5 None tomatoes, sliced — 553.5 g
- 8 None anchovy fillets, chopped — 32.0 g
- 8 None black olives — 32.0 g
- 5 tbsp olive oil — 67.5 g
- 100 ml vegetable stock — 101.0 g
- 3 sprigs rosemary — 3.0 g
- 1 clove garlic, finely chopped — 3.0 g
- 1 None spring onion, very finely chopped — 15.0 g

Human decision: pending.

### RCP2_09178C4F96FC — Yorkshire Puddings

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "protein_main"}}`

- 140g Flour — 140.0 g
- 4 Egg — 200.0 g
- 200ml Milk — 206.3 g
- Drizzle Sunflower Oil — 13.6 g

Human decision: pending.

### RCP2_0537FFE83166 — Barbecued Green Beans

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 1-1/2 pound Fresh Green Beans, Trimmed — 680.4 g
- 5 slices Bacon — 140.0 g
- 1/3 cups Finely Chopped Onion — 53.3 g
- 1 clove Garlic, Minced — 3.0 g
- 1/3 cups Barbecue Sauce — 86.7 g
- 3 Tablespoons Ketchup — 51.0 g
- 1/4 teaspoons Freshly Ground Black Pepper, Or To Taste — 0.6 g

Human decision: pending.

### RCP2_0C181842D295 — Chinese Salt And Pepper Tofu

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "protein_main"}}`

- 1 lb firm tofu — 453.6 g
- 2 teaspoons salt — 12.2 g
- 2 teaspoons garlic powder — 5.3 g
- 1 teaspoon fresh ground black pepper — 2.3 g
- 3 tablespoons cornstarch — 24.0 g
- 3 tablespoons vegetable oil — 40.9 g

Human decision: pending.

### RCP2_8CA1A70205AB — Sweet-Sour Red Cabbage

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 4 slices bacon — 112.0 g
- 3/4 c. chopped onion — 120.0 g
- 3/4 c. chopped celery — 75.8 g
- 3/4 c. cider vinegar — 179.2 g
- 1/3 c. molasses — 106.7 g
- 1 Tbsp. prepared mustard — 15.5 g
- 1 tsp. salt — 6.1 g
- 8 c. shredded red cabbage — 712.0 g

Human decision: pending.

### RCP2_8B2F4B847EE8 — Braised Celery (Irish)

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 1 head celery — 500.0 g
- 1 medium onion — 110.0 g
- 1 teaspoon fresh parsley leaves, chopped — 1.3 g
- 2 slices bacon — 56.0 g
- 10 ounces chicken stock — 283.5 g
- salt and black pepper — 2.9 g
- 1 ounce butter — 28.3 g

Human decision: pending.

### RCP2_0403B8D87889 — Turnip Greens

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 2 lb. fresh turnip greens — 907.2 g
- 5 slices bacon — 140.0 g
- 4 c. water — 948.0 g
- 1 Tbsp. white vinegar — 15.0 g
- 1/4 to 1/2 tsp. red pepper flakes — 0.7 g
- 1 tsp. salt — 6.1 g
- 1/4 tsp. pepper — 0.6 g

Human decision: pending.

### RCP2_081D6225586A — Daikon Kimchi

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 6 cups peeled daikon radishes, in chunks — 696.0 g
- 2 tablespoons salt — 36.5 g
- 1/2 cup plus 2 tablespoons sugar — 100.0 g
- 1/2 cup korean chili powder (kochukaru, available at Korean markets or any good single-chili powder like ancho or New Mexican, bu) — 50.0 g
- 20 slices ginger — 40.0 g
- 20 garlic cloves — 60.0 g
- 1/4 cup fish sauce (nam pla) — 72.0 g
- 2 teaspoons salted shrimp (available at Korean markets) — 7.1 g
- 1/4 cup soy sauce — 63.8 g

Human decision: pending.

### RCP2_D190FCD7C0C1 — Sweet And Sour Red Cabbage

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 5 c. shredded red cabbage — 445.0 g
- 1 tsp. salt — 6.1 g
- 4 slices bacon — 112.0 g
- 2 Tbsp. brown sugar — 27.5 g
- 2 Tbsp. flour — 15.6 g
- 1/2 c. water — 118.5 g
- 1/3 c. vinegar — 80.0 g
- 1/8 tsp. pepper — 0.3 g
- 1 small sliced onion — 110.0 g

Human decision: pending.

### RCP2_0724466545EF — Kimchi With Daikon Radish

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 1 lb daikon radish, peeled — 453.6 g
- 4 ounces cabbage, shredded — 113.4 g
- 2 ounces carrots, peeled — 56.7 g
- 2 ounces gingerroot, peeled and grated — 56.7 g
- 2 garlic cloves, grated — 6.0 g
- 1 ounce green onion — 28.3 g
- 5 tablespoons kosher salt — 91.2 g
- 1 teaspoon crushed red pepper flakes (or Korean chili flakes) — 1.8 g
- 3 anchovy fillets, finely chopped — 12.0 g
- 1 ounce fish sauce — 28.3 g
- 2 ounces rice vinegar — 56.7 g
- 1 teaspoon sugar — 4.2 g

Human decision: pending.

### RCP2_431BB9960EB2 — Baked Sauerkraut Wirth

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 2 lb. sauerkraut, washed and well drained — 907.2 g
- 1 lb. chopped tomatoes — 453.6 g
- 1 1/4 c. dark brown sugar, firmly packed — 275.0 g
- 4 slices lean bacon, cut in half — 112.0 g

Human decision: pending.

### RCP2_6CA29419A1ED — Naan(Leaf-Shaped Bread)

Changes: `{"protein_sources": {"before": ["egg"], "after": []}}`

- 4 c. all-purpose flour — 500.0 g
- 1 Tbsp. sugar — 12.5 g
- 1 Tbsp. double-acting baking powder — 13.8 g
- 1/4 tsp. baking soda — 1.2 g
- 1/2 tsp. salt — 3.0 g
- 2 eggs — 100.0 g
- 1 c. milk — 244.0 g
- 4 to 6 tsp. oil — 22.7 g

Human decision: pending.

### RCP2_24ED2AE8A798 — Sweet And Sour Greens

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 6 slices bacon, chopped — 168.0 g
- 1/2 cup water — 118.5 g
- 1/4 cup vinegar — 60.0 g
- 1/2 cup white sugar — 100.0 g
- 1/8 teaspoon salt — 0.8 g
- 1/8 teaspoon black pepper — 0.3 g
- 2 1/2 pounds fresh collard greens, tough stems removed and leaves torn into bite-size pieces — 1134.0 g

Human decision: pending.

### RCP2_BB96EC674F08 — Baked Sauerkraut Wirth

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 2 lb. sauerkraut, washed well and drained — 907.2 g
- 1 lb. can tomatoes, drained and chopped (reserving the juice) — 453.6 g
- 1 1/4 c. firmly packed dark brown sugar — 275.0 g
- 4 slices lean bacon, halved crosswise — 112.0 g

Human decision: pending.

### RCP2_A6FB0E6E132E — Homemade Italian Egg Noodles

Changes: `{"contains_staple": {"before": false, "after": true}, "meal_role": {"before": "protein_main", "after": "staple"}, "protein_sources": {"before": ["egg"], "after": []}}`

- 2 c. flour — 250.0 g
- 3 egg yolks — 51.0 g
- 1 egg — 50.0 g
- 2 tsp. salt — 12.2 g
- 1/4 to 1/2 c. water — 88.9 g

Human decision: pending.

### RCP2_6C04EF417AF0 — German-Style Cabbage And Beans

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 1 pound fresh green beans, cut into 1-1/2-inch pieces — 453.6 g
- 3 bacon strips, cut into 1-inch pieces — 84.0 g
- 1/2 cup cider vinegar — 119.5 g
- 1/4 cup sugar — 50.0 g
- 3 tablespoons chopped onion — 30.0 g
- 1/2 teaspoon salt — 3.0 g
- 1/4 teaspoon pepper — 0.6 g
- 3 cups shredded red cabbage — 267.0 g

Human decision: pending.

### RCP2_3DC6485B1198 — Teriyaki Edamame

Changes: `{"meal_role": {"before": "vegetable", "after": "protein_main"}}`

- 1/4 cup teriyaki sauce — 72.0 g
- 2 tablespoons sesame oil — 27.2 g
- 2 tablespoons rice vinegar — 32.1 g
- 2 tablespoons dark brown sugar — 27.5 g
- 1/4 cup water — 59.2 g
- 16 ounces frozen edamame, in the pod — 453.6 g
- 1 tablespoon sesame seeds — 9.0 g

Human decision: pending.

### RCP2_0AA904922C1B — Kona K'S Korean-Style Steamed Egg Casserole (Egg Jjim)

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "protein_main"}}`

- 3 eggs — 150.0 g
- 1 cup water — 237.0 g
- 2 teaspoons salt — 12.2 g
- 1 tablespoon sesame oil — 13.6 g
- 1 tablespoon toasted sesame seeds — 9.0 g
- 1 tablespoon green onion, finely chopped — 6.2 g

Human decision: pending.

### RCP2_0DBD84E7C323 — Texas Okra And Tomatoes

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 4 slices bacon — 112.0 g
- 1/4 c. onion, chopped — 40.0 g
- 1 to 2 jalapeno peppers, chopped — 21.0 g
- 4 c. okra, sliced — 400.0 g
- 3 c. tomatoes, peeled and chopped — 540.0 g
- 1 tsp. salt — 6.1 g
- 1/2 tsp. pepper — 1.1 g

Human decision: pending.

### RCP2_31CA4DA49B46 — Creamy Fresh Corn

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 6 to 8 ears fresh corn — 630.0 g
- 3 strips bacon — 84.0 g
- 2/3 c. water — 158.0 g
- 1 tsp. salt — 6.1 g
- 1/2 tsp. sugar — 2.1 g
- 2 tsp. flour — 5.2 g
- 1/4 c. milk — 61.0 g
- 1/8 tsp. pepper — 0.3 g
- 1 Tbsp. butter — 14.2 g

Human decision: pending.

### RCP2_6F36672E582B — Edamame (Soy Beans) And Onions

Changes: `{"meal_role": {"before": "vegetable", "after": "protein_main"}}`

- 250 g shelled frozen edamame — 250.0 g
- 1 cup sweet onion, Chopped — 160.0 g
- cooking spray — 4.5 g

Human decision: pending.

### RCP2_BABE0CD66EEA — Vietnamese Steamed Tofu

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "protein_main"}}`

- 1 lb firm tofu, cut into 1-inch chunks — 453.6 g
- 2 tablespoons soy sauce (reduced sodium is best) — 31.9 g
- 2 tablespoons rice vinegar — 32.1 g
- 1/2 cup chopped scallion — 50.0 g
- 1/4 teaspoon salt — 1.5 g
- 1/2 teaspoon black pepper — 1.1 g
- 1 teaspoon red pepper flakes (less if you prefer less spicy foods) — 1.8 g

Human decision: pending.

### RCP2_96DC46181242 — Sweet And Sour Cabbage With Bacon

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 4 bacon strips, diced — 112.0 g
- 5 cups shredded cabbage — 445.0 g
- 1 medium onion, chopped — 110.0 g
- 1/2 cup water — 118.5 g
- 1/3 cup vinegar — 80.0 g
- 2 tablespoons all-purpose flour — 15.6 g
- 2 tablespoons brown sugar — 27.5 g
- 1/2 teaspoon salt — 3.0 g
- 1/8 teaspoon pepper — 0.3 g

Human decision: pending.

### RCP2_056FEB8B1C07 — Stewed Okra And Tomatoes

Changes: `{"contains_staple": {"before": null, "after": false}, "estimated": {"before": {"cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}, "after": {"contains_staple": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "cooking_methods": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "equipment": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "flavor_tags": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "meal_role": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}, "protein_sources": {"batch": "recipe-tags-v1/rules", "method": "rule", "reviewed": false}}}, "meal_role": {"before": null, "after": "vegetable"}}`

- 2 slices bacon, cut up — 56.0 g
- 1 large onion, chopped — 110.0 g
- 1 medium green pepper, chopped — 120.0 g
- 1 to 2 lb. okra, cut up — 680.4 g
- 1 to 2 lb. tomatoes, peeled and chopped — 680.4 g
- 1 tsp. salt — 6.1 g
- 1/2 tsp. pepper — 1.1 g

Human decision: pending.

## Deferred bean-led sides

No promotion is authorised. Potential benefit is an extra legume main for vegetarian/vegan or flesh-excluding members, subject to actual diets, allergens, pricing and review. This is not a claim that any household's plan changes.

The existing catalog diets indicate which member restrictions might benefit; they are not newly audited safety labels. Members with no diet restriction may gain alternatives too.

| ID | Recipe | Current role | Frozen | Existing catalog diets |
|---|---|---|---|---|
| RCP2_0AE60D683F0D | Abuela'S Frijoles Negros - Grandma'S Cuban Black Beans | None | False | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_0E0DC1E18373 | Brazilian Crock-Pot Beans | staple | True | dairy-free, gluten-free |
| RCP2_0F6692A9480A | Corn And Lima Beans | staple | True | gluten-free |
| RCP2_1BBDFA22270A | Sweet And Sour Lentils | one_bowl | True | dairy-free, gluten-free, vegetarian |
| RCP2_1D1DBCB06899 | Brazilian Black Beans | None | False | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_3465CC24E6FF | Pinto Beans For Burritos | snack | True | dairy-free, gluten-free |
| RCP2_428E51829F1A | Korean Spiced Kidney Beans | snack | True | dairy-free, vegetarian, vegan |
| RCP2_4808C28F01AE | Refried Beans | snack | True | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_5216E8F6555E | Refritos (Refried Beans) | sauce | True | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_561E7EDAC82C | Cuban Black Beans | sauce | True | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_634F7CFF5B86 | Mexican Low-Fat Pinto Beans | staple | True | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_66AD2CDBCB53 | Guatemalan Black Beans (Frijoles Parados) | staple | True | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_7767F8C932A9 | Frijoles Negros- Crock Pot Mexican Black Beans | staple | True | dairy-free, gluten-free, vegetarian, vegan |
| RCP2_B50E98C61A88 | Colombian Red Beans - Frijoles Colombianos | staple | True | dairy-free, gluten-free |
| RCP2_BA25EE029647 | Brazilian Black Beans - Vegitarian | staple | True | dairy-free, gluten-free, vegetarian, vegan |

## Frozen batch — suggestions for liu-ub

| ID | Recipe | Stored role | Rule suggestion | Allowed review roles |
|---|---|---|---|---|
| RCP2_00100560483E | Swedish Crescents | dessert | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_010100DDE2F6 | Cheesy Zucchini Lasagna | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_011288A0DAAA | Hush Puppies | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_011E8E50E3E6 | Feteer Meshaltet | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_01D48A672ACA | Sweet Potato Noodle Curry | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_02600E447144 | Festivals (Jamaican Fry Bread) | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_02ED221BB8C3 | Snowballs(Swedish) | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_03DEE14CDC60 | Hush Puppies | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_04FA63A313E5 | Dumplings | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_0537F95C51D2 | French Onion Soup | soup | None | soup, one_bowl |
| RCP2_05ED759BF701 | Fried Rice | one_bowl | one_bowl | one_bowl |
| RCP2_062390916CFF | Garden Ranch Pizza-Pampered Chef | one_bowl | None | staple, vegetable |
| RCP2_06BA84D12D67 | Meat Loaf With Cheese Sauce | protein_main | protein_main | protein_main |
| RCP2_0780C777C0AB | Stir Fry Rice | one_bowl | one_bowl | one_bowl |
| RCP2_0B06E6177DA3 | Crunchy Chicken Casserole | protein_main | protein_main | protein_main |
| RCP2_0CA3F3F66929 | Roti Jala (Malaysian Net Crepe) | breakfast | staple | staple |
| RCP2_0CFF755F4ED0 | Mexican Wedding Cakes | dessert | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_0D6EBFF557A4 | Japanese Rice | None | None | staple |
| RCP2_0DBC46FF845C | Oven Polenta | staple | staple | staple |
| RCP2_0DE59ED69BBF | Stuffed Bell Peppers | protein_main | protein_main | protein_main |
| RCP2_0E0DC1E18373 | Brazilian Crock-Pot Beans | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_0F2A138F47E4 | English Teaballs | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_0F6692A9480A | Corn And Lima Beans | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_1087CA73F93D | Southern Smothered Green Beans | staple | vegetable | vegetable |
| RCP2_1106936B4750 | Sweet And Sour Cabbage | staple | vegetable | vegetable |
| RCP2_12D50BBDB52E | Eggplant A La Parmesan | vegetable | None | staple, vegetable |
| RCP2_130F971CF821 | Ukrainian Bukovinian Nachynka (Cornbread Dressing) | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_140233207FB1 | Pizza Bianco | one_bowl | None | staple |
| RCP2_143B82A4800E | Spaetzle Noodles | staple | staple | staple |
| RCP2_1554F9789729 | Banh Mi Hotdog | one_bowl | one_bowl | one_bowl |
| RCP2_15AF96C45EB8 | Paneer (Panir) | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_15BCD52E8739 | Sprouts, Chorizo & Almond Bowl | staple | vegetable | vegetable |
| RCP2_15F1AAB4C310 | Korean Gaeran Mari (Stuffed Egg Omelette W Cheese) | breakfast | protein_main | protein_main |
| RCP2_1656CB038FF4 | Chinese Wedding Rings | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_16BF42FD100D | Udon Noodles | staple | staple | staple |
| RCP2_1722D847EECE | Southern Spoon Bread | staple | protein_main | protein_main |
| RCP2_1729D7258E04 | Egg Filling For Sushi | snack | sauce | sauce |
| RCP2_185C6CEAE1C2 | Enchiladas | one_bowl | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_192C01503365 | Lasagna | protein_main | protein_main | protein_main |
| RCP2_19650787C340 | Ome Rice(Korean) | one_bowl | one_bowl | one_bowl |
| RCP2_19FBD3D80909 | Texas Hash | one_bowl | protein_main | protein_main |
| RCP2_1A1BA06D6CB5 | Never Fail Noodles | staple | staple | staple |
| RCP2_1ABBF278577A | Jamaican Festival (Sweet Dumpling) | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_1ACC53E4DF5B | Baked Banana (Plantain) With Bacon And Cheese | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_1B153229C12F | Six In One | one_bowl | protein_main | protein_main |
| RCP2_1BBDFA22270A | Sweet And Sour Lentils | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_1C43BC6CC166 | Stroganoff Steak Sandwiches | protein_main | one_bowl | one_bowl |
| RCP2_1CB98FB35F9C | Mexican Slow Cooker Chicken Burritos | one_bowl | one_bowl | one_bowl |
| RCP2_1D11B4013577 | Mango Raisin Couscous ( Cous-Cous) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_1DDBB68902A6 | Cantonese Fried Rice | one_bowl | one_bowl | one_bowl |
| RCP2_1E03BFBAFC1E | Spinach Souffle | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_1E114667D956 | Cheesy Potato Lasagna | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_1EF61A58359F | Apple Casserole | dessert | None | staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_201F9250C196 | Algerian Vegetable Couscous | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_2056C574BA1E | Easy Spoon Bread | breakfast | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_207C22E16796 | Scottish Roast Chicken | protein_main | protein_main | protein_main |
| RCP2_20E9789E014D | Crock-Pot Polish Cabbage Rolls | protein_main | protein_main | protein_main |
| RCP2_212042A4393F | Zucchini Stir-Fry | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_21ADEFC9A0C2 | Satay | protein_main | protein_main | protein_main |
| RCP2_21D46B7E4C32 | Spaetzles | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_224C571A890D | Cheater'S Cheese Souffle | protein_main | protein_main | protein_main |
| RCP2_2258F6B702CB | Korean Kimchi Burgers | one_bowl | one_bowl | one_bowl |
| RCP2_229B831CE6C7 | Mexican Wedding Bells | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_22CB9F8E06FA | Skillet Cornbread | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_230081AE2244 | Filipino Pandesal Bread ( Bread Machine ) | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_23AEBF1FD190 | Sweet And Sour Meatballs(In The Microwave) | protein_main | protein_main | protein_main |
| RCP2_23DCDA368745 | Homemade Nama (Fresh) Udon Noodles | staple | staple | staple |
| RCP2_241D4DF15897 | Hungarian Keifleys | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_24B9AA68594B | Mushroom Supreme | snack | vegetable | vegetable |
| RCP2_24D1FD24F7F1 | Recipe Of 1985'S Burleson County Kolache(Queen'S Kolaches, Ella Drgac Queen) | breakfast | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_255BF2278F68 | Dumplings | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_25B174021AD8 | Gramma & Grampa Fjerstad'S Lefse | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_25EF3F0CA6AD | Homemade Queso Fresco In One Hour | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_2635DC1E3E4B | Pao De Queijo (Aka Brazilian Cheese Puffs) | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_265F52246FE6 | South African Rusks | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_275105C8694D | Cornbread | staple | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_27CF36D8964D | Flour Taco Shells | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_2848D4DD38CE | Fufu | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_284F4FEA733D | Jamaican Boiled Dumplings | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_290971CF4730 | Mexican Wedding Rings | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_293417D0F5D5 | Koulouria -- Greek Sesame Galettes | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_29BA89DD8246 | Trinidadian Coconut Bake | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_29EF8FF66D07 | Thai Chickpea Pizza | one_bowl | protein_main | protein_main |
| RCP2_2AC94AA7906B | Cou Cou (Caribbean Polenta) | staple | staple | staple |
| RCP2_2BA45D5AB524 | Taco Shells | staple | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_2BD9BFE7AE13 | My Mother Lillie'S Spinach Souffle | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_2C2A13538B08 | Chinese Chews | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_2C368BB10827 | Sweet Potato And Feta Gnocchi | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_2C3763B662FD | Venezuelan Arepas With Sesame, Chia, And Flaxseeds | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_2C6DCB5E0B50 | Chinese Egg Roll Wrap | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_2C7D7B4493C8 | Kolache | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_2CE4B2CB6AEE | Diner Meat Loaf | protein_main | protein_main | protein_main |
| RCP2_2DEFB0F27019 | Meat Croquettes | protein_main | protein_main | protein_main |
| RCP2_2E3012F8BABC | Gran'S Noodles | staple | staple | staple |
| RCP2_2E6B4C7D3281 | Granny Gibbs' Famous Dumplings | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_2EAB7EB9A23D | Chorizo Ball | one_bowl | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_2F5D13FF1C1A | Kentucky Hush Puppies | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_2FC102A3D309 | Mexican Corn Bread | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_30B5AB92CC91 | Vietnamese Fajitas (Bo Nuong Xa) | protein_main | protein_main | protein_main |
| RCP2_310A97E81CC3 | Taco Baked Potatoes | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_313E4C8B9C7B | Betty Crocker 1950S Welsh Rarebit | sauce | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_31457FBD2E5C | Indian Pinto Beans | soup | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_3314EF4C89E1 | Potato Gnocchi From Scratch | staple | staple | staple |
| RCP2_3330CF0BC620 | Korean Kimchi Burgers | one_bowl | one_bowl | one_bowl |
| RCP2_3368D505CC40 | Vietnamese Sandwiches | one_bowl | one_bowl | one_bowl |
| RCP2_33B9F1AECB3E | Homemade Tempeh | snack | protein_main | protein_main |
| RCP2_3465CC24E6FF | Pinto Beans For Burritos | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_35400FE238ED | Instant Pot® Smoky Korean Bbq Baked Beans | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_355D74D12F4C | Vietnamese Spiced Paté | snack | snack | snack |
| RCP2_35DC1259F6B0 | Soft Shell Tacos | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_35E7E466C238 | Pizza Burger'S Fcs School Recipe | one_bowl | one_bowl | one_bowl |
| RCP2_3703338B3886 | Spinach Pizza Topping | snack | sauce | sauce |
| RCP2_370E5046B39F | Spanish Rice | staple | staple | staple |
| RCP2_382B6B7AF64D | Southern Spoon Bread | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_38391F938210 | Dreamy Polenta | staple | staple | staple |
| RCP2_38C9D74E8995 | Nif'S Easy Baking Powder Dumplings (Crock Pot Or Stove Top) | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_392DCD1CADCE | Shrimp Creole | one_bowl | protein_main | protein_main |
| RCP2_39B142C1E4E8 | Caribbean Rice | one_bowl | one_bowl | one_bowl |
| RCP2_39BF39F7A6E4 | Banh Mi Hot Dogs | one_bowl | one_bowl | one_bowl |
| RCP2_39C56A95E326 | Barbecue pork buns | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_39CE51E9A95B | Rosalita'S Arepas Con Queso | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_3A80E3CCA5D1 | Buttermilk Rusks, South African | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_3A89815DD43E | Pancit(Rice Noodles) | one_bowl | one_bowl | one_bowl |
| RCP2_3B11D976623D | Vegetable Tempura | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_3C310D373BB9 | Pupusas | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_3CC1354BC571 | Brazilian Arroz De Festa (Confetti Rice) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_3D5ADFE023AB | Lamb & apricot meatballs | protein_main | protein_main | protein_main |
| RCP2_3F422D8D65F9 | Baked Plantains (Cooking Bananas) | dessert | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_402F11758D8C | Injera | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_4070469D0041 | French Onion Soup | soup | None | soup, one_bowl |
| RCP2_409262770DBA | Popovers(Portuguese) | breakfast | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_40ECCF6439F2 | Cajun Meat Loaf | protein_main | protein_main | protein_main |
| RCP2_420219DB3C60 | Fried Pheasant | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_428E51829F1A | Korean Spiced Kidney Beans | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_4295A6A55D85 | Tropical Beef Fajitas | one_bowl | protein_main | protein_main |
| RCP2_42AA5C0CA968 | Potato Lasagna | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_42EA59ACAAEA | Crescents(Portuguese) | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_43F241E2C2FA | Homemade Pasta | staple | staple | staple |
| RCP2_441BD2095B93 | Vietnamese Pâté Chaud | snack | snack | snack |
| RCP2_44870004D5FB | Lasagna Style Bow Tie Dish | one_bowl | one_bowl | one_bowl |
| RCP2_44C42897EBAD | Peruvian Alfajores | dessert | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_45391BFD9020 | Roti Jala (Malaysian Lacy Pancakes) | snack | staple | staple |
| RCP2_4539937C1F3A | Sauerkraut Dumplings | snack | protein_main | protein_main |
| RCP2_456CCADB7128 | Stuffed Green Peppers | protein_main | protein_main | protein_main |
| RCP2_45BE0219D45D | Heart-Shaped Tamagoyaki (Japanese Omelet) | breakfast | protein_main | protein_main |
| RCP2_45EBD2FEEEB0 | Paneer (Home Made) | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_47186AAC9989 | Creamy Polenta 10/08 Ba | staple | staple | staple |
| RCP2_472B6677B22B | Tofu Feta | snack | protein_main | protein_main |
| RCP2_474BD62093D1 | Cha-Soh Juhn(Korean Vegetable Pancakes) | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_4808C28F01AE | Refried Beans | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_4869C3AEA8AD | Thai Salty Egg(Side Dish) | snack | protein_main | protein_main |
| RCP2_486E1D6A70D8 | Japanese Sweet Omelet | breakfast | protein_main | protein_main |
| RCP2_48AF180797C2 | Vidalia Onion Soup | soup | None | soup, one_bowl |
| RCP2_491808DE2CEB | Spiedies (Kabobs) | protein_main | protein_main | protein_main |
| RCP2_499150EEF32D | Grandma O'Neill'S Irish Soda Bread | staple | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_49CA27EAC641 | Alfajores De Maizena | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_4A04FF1CF1AB | Watermelon Curry (Matira) | sauce | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_4A7CC5A410F0 | Plantains In Coconut Milk | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_4AFAD849C677 | Empanadas | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_4B3B02F3D728 | Roti Canai (Malaysian Style) | staple | staple | staple |
| RCP2_4CE4FA69CB3E | Pan-fried hake, white bean & chorizo broth | one_bowl | protein_main | protein_main |
| RCP2_4DF11493A5F5 | Lemon Chicken Soup With Quinoa | soup | None | soup, one_bowl |
| RCP2_4E9F363F8876 | Gnocchi | staple | staple | staple |
| RCP2_4EC013060AE0 | Luscious Layers | one_bowl | None | staple, vegetable |
| RCP2_4F7893458243 | Baked Sweet Potatoes With West African-Style Peanut Sauce | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_50567B7B0B2C | Kumpir | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_507B9CC45AC6 | Spanish Rice | one_bowl | protein_main | protein_main |
| RCP2_50FF85F5FDE0 | Breakfast Burritos | one_bowl | one_bowl | one_bowl |
| RCP2_515EDCDA8064 | Cream Cheese Crescents(Hungarian Kifli) | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_5216E8F6555E | Refritos (Refried Beans) | sauce | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_53FF54F0EB32 | Stir-Fry Venison | protein_main | protein_main | protein_main |
| RCP2_540A9A5CDB2A | Fried Rice | one_bowl | one_bowl | one_bowl |
| RCP2_543A1872318A | Texas Hash(Weight Watchers) | one_bowl | protein_main | protein_main |
| RCP2_546DFF631ED4 | Cauliflower Au Gratin | soup | vegetable | vegetable |
| RCP2_5497ED3C29EA | Soft Cornmeal Taco Shells | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_54B440E380EB | Fry Bread For Navaho Tacos | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_561E7EDAC82C | Cuban Black Beans | sauce | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_56684132208E | Ricotta Gnocchi | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_57A5EE0626CD | Texas Chili Con Carne | protein_main | protein_main | protein_main |
| RCP2_57E2F87CA748 | Grandma'S Sweet And Sauerkraut | soup | vegetable | vegetable |
| RCP2_57F7D87302B2 | California Quiche Lorraine | staple | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_59209F8AE7D0 | South African Vetkoek | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_5954131C04AC | Scrumpets | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_59D318263C91 | Mahshy Bandora (Stuffed Tomatoes)(Lebanese) | one_bowl | one_bowl | one_bowl |
| RCP2_5A5EBBE90C92 | Injera | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_5B8603D2B433 | Italian Cottage Cheese | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_5C1AF74A7B55 | Šúĺlance s Makom | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_5C8F72777948 | Spatzle | staple | staple | staple |
| RCP2_5CAF86FF5D5D | Potato Borek | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_5D77EC59057C | Creamy Polenta With Parmesan And Mozzarella | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_5D84F859E558 | English Popovers | breakfast | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_5ED49FFCF6D4 | Spanish Rice | staple | one_bowl | one_bowl |
| RCP2_5F3868736164 | Homemade Dumplings | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_5F632D436B4E | Ramen Noodles | staple | staple | staple |
| RCP2_5FDC54ED6B2B | Sauerkraut | staple | vegetable | vegetable |
| RCP2_5FECAA2C747F | Super Easy Pad Thai | one_bowl | one_bowl | one_bowl |
| RCP2_5FFD99ABD34E | Italian Gnocchi | staple | staple | staple |
| RCP2_607A6AFD87B4 | Chivito uruguayo | one_bowl | protein_main | protein_main |
| RCP2_614D0DC32132 | Meatballs | protein_main | protein_main | protein_main |
| RCP2_616382D3CF7F | Rabbit Stew | protein_main | protein_main | protein_main |
| RCP2_628A7F873ED3 | Mexican Higado Tacos | one_bowl | one_bowl | one_bowl |
| RCP2_62BE75BD23E4 | Zucchini Souffle | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_6336ACA2F9AE | Japanese Tamago Egg | breakfast | protein_main | protein_main |
| RCP2_634CE564B1EE | Middle Eastern Burgers | protein_main | protein_main | protein_main |
| RCP2_634F7CFF5B86 | Mexican Low-Fat Pinto Beans | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_641ABD3FC590 | Bavarian Cabbage | staple | vegetable | vegetable |
| RCP2_644A347C7523 | Jane Cody'S Awesome Stir Fry | protein_main | protein_main | protein_main |
| RCP2_646039848924 | Crumb-Coated Spaetzle | staple | staple | staple |
| RCP2_6466F4F7BF0A | Indian Tacos | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_64DBD7C2EF10 | Guadalajaran Jalisco Mexican Rice | staple | staple | staple |
| RCP2_65C7BEB7FEFD | Riyadh Rice - Middle Eastern Favourite! | one_bowl | one_bowl | one_bowl |
| RCP2_66540AABF0E0 | Thai Sweet Potato Stew | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_66AD2CDBCB53 | Guatemalan Black Beans (Frijoles Parados) | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_66CDC4D02656 | Napa Cabbage with Dried Shrimp | staple | vegetable | vegetable |
| RCP2_66D9A8C454B3 | Scottish Shortbread (For A Tea Party) | dessert | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_67A66B53DE3C | Slow Cooker Chicken Curry With Quinoa | one_bowl | protein_main | protein_main |
| RCP2_686557404CA1 | Tacos | one_bowl | one_bowl | one_bowl |
| RCP2_6AD2450270A2 | Russian Wafers | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_6AE2F530BFEE | Microwave Quick Lasagna | protein_main | protein_main | protein_main |
| RCP2_6B3C9AD9D6E0 | Chinese Eggs | breakfast | protein_main | protein_main |
| RCP2_6C1E6D9E70BE | Polenta(Microwave) | staple | staple | staple |
| RCP2_6CFCB11F79B9 | Thai Curry Pork Lettuce Wraps (Nam Prik Ong) | protein_main | protein_main | protein_main |
| RCP2_6D9B39CCD991 | Malaysian Roti Canai (Kinda Like A Pancake) | staple | staple | staple |
| RCP2_6E65362F51A9 | Beef Fajitas | protein_main | protein_main | protein_main |
| RCP2_6E757674305D | Danish Dumplings | snack | protein_main | protein_main |
| RCP2_70B47600544A | Ramen Noodles | staple | staple | staple |
| RCP2_7123F2300609 | Ethiopian Cheese | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_722E5F335AD4 | Greek Shortbread | dessert | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_7248F8960BF1 | Spanish Rice | one_bowl | one_bowl | one_bowl |
| RCP2_74EFF106FE7B | Pizza Stuffed Potatoes (Twice Baked) | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_75BFE1C39E34 | Taco Casserole | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_765D954B952B | Cheese Dumplings For Soup | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_76DAFDABA87D | Simply English Bubble & Squeak | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_7767F8C932A9 | Frijoles Negros- Crock Pot Mexican Black Beans | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_778D3F74C3CF | Bohemian Bread Dumplings | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_7791CF2A7CDD | Polenta | staple | staple | staple |
| RCP2_7803F1FEB333 | Shredded Beef Chimichangas | protein_main | protein_main | protein_main |
| RCP2_783368D92192 | Tempura | snack | vegetable | vegetable |
| RCP2_7877BC0F4362 | Indian Fry Bread | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_793CD2DF1D24 | 3 Cheese Lasagne(St. Rose Student Recipe) | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_7B354C6F9480 | Sauerkraut Dumplings(Hungarian Recipe) | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_7DCEB197520A | Korean Steamed Egg Custard | snack | protein_main | protein_main |
| RCP2_7EC289C20A2A | Savory Sauerkraut Casserole | one_bowl | vegetable | vegetable |
| RCP2_7EE413539148 | Pork Banh Mi Wraps | one_bowl | one_bowl | one_bowl |
| RCP2_7F94EA2E2036 | Potato Gnocchi | staple | staple | staple |
| RCP2_805CCFE62BA7 | Lasagna | one_bowl | one_bowl | one_bowl |
| RCP2_806075FC7BF8 | French Onion Soup | soup | None | soup, one_bowl |
| RCP2_8109D39756EC | Pan De Sal - Filipino Bread Rolls | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_81C30294D91B | Turkish Pogaca | snack | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_824A7E93FFE3 | Korean B.B.Q. | protein_main | protein_main | protein_main |
| RCP2_829671202485 | Potato Gnocchi | staple | staple | staple |
| RCP2_82DB38A4F424 | Stuffed Green Peppers | protein_main | protein_main | protein_main |
| RCP2_87713B74F837 | South African Meat Loaf | protein_main | protein_main | protein_main |
| RCP2_87B3FDF37675 | Dumplings(Italian Style) | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_87CBA929A2C6 | Spicy Thai One Pot | one_bowl | one_bowl | one_bowl |
| RCP2_888730AE4624 | Tamagoyaki - Japanese Rolled Omelette | breakfast | protein_main | protein_main |
| RCP2_88C46CBD6B93 | Chilean Chicken Stew With Pumpkin And Wild Rice | protein_main | one_bowl | one_bowl |
| RCP2_88FDB464A695 | Jang Jorim With Hard-Boiled Eggs (Korean Soy Beef Strips) | one_bowl | protein_main | protein_main |
| RCP2_897B7AF05CB0 | Baked Zucchini With Rice And Feta | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_89F0058D53F5 | German Style Beans | snack | vegetable | vegetable |
| RCP2_89F7211E3608 | Chinese Sweet And Sour Spareribs Vegetarian | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_8C859FF10E5B | Coconut Baked Bananas (Or Plantains) | dessert | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_8C948ACDB0BC | Vietnamese Beef Curry | protein_main | protein_main | protein_main |
| RCP2_8CDACD3A0704 | Vietnamese Fried Rice | one_bowl | one_bowl | one_bowl |
| RCP2_8D12144D2014 | Pork Fajita Kabobs | one_bowl | protein_main | protein_main |
| RCP2_8D376D61D13A | Slovak Easter Cheese (Cirak) | snack | protein_main | protein_main |
| RCP2_8F7B547C1808 | Banh Mi Hotdog | one_bowl | one_bowl | one_bowl |
| RCP2_8F83C05E5E00 | Siopao (Filipino Steamed Buns) | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_8F8576285D7F | Fried Plantains | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_9150197BEBD9 | Japanese Marinated Soft Boiled Egg For Ramen (Ajitsuke Tamago) Recipe | snack | protein_main | protein_main |
| RCP2_91E87A1057FC | Vegetarian Kenyan Curry | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_920C40633EDD | Egg Roll | snack | protein_main | protein_main |
| RCP2_92648ECC9FC9 | Hungarian Popovers(Kati Felfujtja) | breakfast | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_92D0966923D6 | Polenta | staple | staple | staple |
| RCP2_92F5CA7EC6D3 | Seven Hour Eggs - Korean Sauna | snack | protein_main | protein_main |
| RCP2_92FA53DECB5E | Mediterranean Chicken | one_bowl | protein_main | protein_main |
| RCP2_956FD7177508 | Ramen Hot And Sour Soup | one_bowl | one_bowl | one_bowl |
| RCP2_958B37782112 | Basic Souffle Recipe | breakfast | protein_main | protein_main |
| RCP2_9723078749EF | Thai Chicken Pizza With Carrots And Cilantro | one_bowl | protein_main | protein_main |
| RCP2_97D659CE8E07 | Japchae (Korean Glass Noodles) | one_bowl | one_bowl | one_bowl |
| RCP2_989AB5746A34 | Sage Polenta | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_98B58258E3BD | Gnocches(Italian Potato Pasta) | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_9B204E51C88D | Potatoes Moussaka * | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_9C278A40B536 | Ethiopian Vegetable Bowl | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_9C51F36C16C2 | Meat Curry | protein_main | protein_main | protein_main |
| RCP2_9C9E0673ECB8 | Quickly Made Kolache | dessert | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_9CD7CD0DA72B | Whole Wheat Egg Noodles Or Spaghetti Noodles | staple | staple | staple |
| RCP2_9E095D1F1FB4 | Korean Fried Tofu Side Dish | snack | protein_main | protein_main |
| RCP2_A130BD59E2A1 | Gyro Casserole | one_bowl | protein_main | protein_main |
| RCP2_A268F28D4812 | Tempeh “Bacon” | snack | protein_main | protein_main |
| RCP2_A26B07E48FE5 | Cheese Gnocchi | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_A31F833871D7 | Bread Dumplings | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_A4661EEE5B7A | Fainá | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_A5E3A0513E4A | Pizza Meatballs | protein_main | protein_main | protein_main |
| RCP2_A660E279682A | Easy Potato Dumplings | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_A7CE680FA0FD | Slovak Egg Dumplings | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_A804E2F5468A | Meat Loaf(Published In Southern Living) | protein_main | protein_main | protein_main |
| RCP2_A84B4E56257C | Asian Wraps | one_bowl | protein_main | protein_main |
| RCP2_A86E37A6C8F4 | Baked Tempeh | snack | protein_main | protein_main |
| RCP2_A887D44E2FC0 | Sauerkraut pierogii | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_A96FC949077E | Moroccan Lentils And Couscous | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_A986B63ED3FF | Lo Mein Noodles | staple | staple | staple |
| RCP2_AAD369D32D4F | Spinach Quesadilla | one_bowl | one_bowl | one_bowl |
| RCP2_ACE25C1DA124 | Welsh Rabbit | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_AFE6B5248965 | Moroccan Ksra | staple | None | breakfast, dessert, staple, snack, one_bowl |
| RCP2_B12163C95EC7 | Tofu Stir Fry | sauce | None |  |
| RCP2_B237C38BB623 | Italian Pizza With Zucchini, Cherry Tomatoes And Mozzarella Chee | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_B2843B21CE46 | Steak Teriyaki | sauce | None |  |
| RCP2_B2E38830A727 | Scottish (Or English) Rarebit | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_B3B862477980 | Jamaican Grits Rice Cooker Optional | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_B3BCAE1F73A7 | Chop Suey | protein_main | protein_main | protein_main |
| RCP2_B3CA4D294329 | Khao Pad (Thai Fried Rice) | one_bowl | one_bowl | one_bowl |
| RCP2_B4D718862D00 | Mexican Rice | one_bowl | one_bowl | one_bowl |
| RCP2_B4F178FA5B73 | Hot Tamales | protein_main | protein_main | protein_main |
| RCP2_B4F2A550663D | "Spaghetti And Meat Sauce For 50" | one_bowl | one_bowl | one_bowl |
| RCP2_B50E98C61A88 | Colombian Red Beans - Frijoles Colombianos | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_B6E9EAA502E0 | Dominican Chimichurri Burgers | protein_main | one_bowl | one_bowl |
| RCP2_B788087EF2A2 | Chicken Quesadillas With Tomato Salad | one_bowl | one_bowl | one_bowl |
| RCP2_B7B25D1E360E | Couscous-And-Feta Cakes | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_B7C012C51A6D | Vietnamese Vegetable Baguette (Banh Mi) | one_bowl | one_bowl | one_bowl |
| RCP2_B8238A4718B6 | Potato And Parmesan Gnocchi | staple | staple | staple |
| RCP2_B89951CCB635 | Hearty French Onion Soup | soup | None | soup, one_bowl |
| RCP2_B8E67A023CFD | Chtitha Batata (Algerian Potato Stew) | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_B941DA1AAB4A | Magdalena'S Empanadas | snack | staple | staple |
| RCP2_B9A91EEFEF2B | Chinese Rice | staple | staple | staple |
| RCP2_BA25EE029647 | Brazilian Black Beans - Vegitarian | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_BA5501343E98 | Hungarian Kifliks | dessert | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_BA741817426B | Corn Souffle | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_BA95359C23B7 | Fried Polenta | staple | staple | staple |
| RCP2_BB79A09A52AC | Wonton Wrappers | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_BBA025B49BA6 | Pierogi | snack | one_bowl | one_bowl |
| RCP2_BBD46E78E711 | Pupusas (El Salvadorean Tortilla) | staple | staple | staple |
| RCP2_BC3A7EE10152 | Authentic Gazpacho - Southern Spain | soup | None | soup, one_bowl |
| RCP2_BC729782E35F | Greek Egg Biscuits | snack | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_BE676A0D1F6F | Pressure-Cooker Asian Wraps | one_bowl | protein_main | protein_main |
| RCP2_BE6A51BF97A6 | Sloppy Joes | protein_main | protein_main | protein_main |
| RCP2_BF6BCDCBD8C3 | Cabbage Casserole | one_bowl | protein_main | protein_main |
| RCP2_C1E68B157F31 | Stuffed Lamb Tomatoes | one_bowl | protein_main | protein_main |
| RCP2_C25D9C4D878B | Yorkshire Pudding | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_C3B5C24F13AB | Tater Tot Beef Bake | one_bowl | protein_main | protein_main |
| RCP2_C58164F6E689 | Cousin Judy'S Chow Mein | one_bowl | one_bowl | one_bowl |
| RCP2_C7CFCE59ABE9 | Indian Potatoes With Cauliflower - Aloo Gobi | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_C7D3BB6B2788 | Easy Lasagne | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_C81AEF8EF1AC | Onion Creme Brulee | snack | vegetable | vegetable |
| RCP2_C8B5EA27D62D | Thai Chicken Tacos | one_bowl | one_bowl | one_bowl |
| RCP2_C8B759477F8B | Gözleme (Turkish Flatbread) | staple | staple | staple |
| RCP2_C8B86F1875A5 | Li'L Cheddar Meat Loaves | protein_main | protein_main | protein_main |
| RCP2_C8FFCB4AA279 | Fried Rice | one_bowl | one_bowl | one_bowl |
| RCP2_C94A3B3DAD51 | Grilled Steak Sandwiches With Chimichurri And Bell Peppers | one_bowl | one_bowl | one_bowl |
| RCP2_CAE614EE3D95 | Italian Meatballs Pat'S Reciepe | protein_main | protein_main | protein_main |
| RCP2_CB386B8363E1 | Marilyn'S English Pasties | one_bowl | one_bowl | one_bowl |
| RCP2_CB88A5A0DF4C | Africa-Bobotie | one_bowl | protein_main | protein_main |
| RCP2_CC48BBF1CD0E | Moo Shu Pancakes | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_CEEA9D67A7EE | Basic Italian Cookies | dessert | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_CEF5851EE683 | Enchilada Casserole | one_bowl | one_bowl | one_bowl |
| RCP2_CF40179BCF86 | Easy Bobotie For Kid Chefs | one_bowl | protein_main | protein_main |
| RCP2_D0F3CE9D133F | Hot Chicken Salad | one_bowl | protein_main | protein_main |
| RCP2_D1A78AFA0C85 | Teenage Sloppy Joes | one_bowl | protein_main | protein_main |
| RCP2_D1E77FB18316 | Lasagne | one_bowl | one_bowl | one_bowl |
| RCP2_D2771697D5AB | Rolled Dumplings | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_D2B871893000 | Never-Fail Meat Loaf | protein_main | protein_main | protein_main |
| RCP2_D30FB234E549 | Rice And Sorghum Injera | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_D453A4530ADE | Meat and Potatoes in Broth (Niku Jaga) | one_bowl | protein_main | protein_main |
| RCP2_D4970386CD19 | Royal Broccoli Souffle | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_D57A6F473637 | Gnocchi | staple | staple | staple |
| RCP2_D698B2F5CB69 | French Onion Soup | soup | None | soup, one_bowl |
| RCP2_D7BD0AAA0F99 | Greek-Style Couscous | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_D803B75A27D8 | Easy Cheese Lasagna | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_D82148B9AE3C | Broccoli Pizza | one_bowl | protein_main | protein_main |
| RCP2_D86FDF8D821E | Sweet And Sour Cabbage | snack | vegetable | vegetable |
| RCP2_D875F1D29484 | Kalbi Venison | protein_main | protein_main | protein_main |
| RCP2_D8E98D9FFC37 | Tomatoes Provencale | snack | vegetable | vegetable |
| RCP2_DB61A80B71EF | Sinigang | soup | soup | soup |
| RCP2_DBE7700244BE | Morrocan Couscous With Green Beans | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_DBF17212D390 | Easy Mexican Sopes | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_DBFF4DB83EF2 | Butternut Squash Curry | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_DC882B3F674A | Banana Raita With Coconut | dessert | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_DD44C3D25E8E | Banh Mi Bo Kho | one_bowl | one_bowl | one_bowl |
| RCP2_E091A77EFBE5 | Sauerkraut Auf Bayische Art(Bavarian Style Sauerkraut) | snack | vegetable | vegetable |
| RCP2_E20C08DE6172 | Polenta Gnocchi With Gorgonzola | staple | staple | staple |
| RCP2_E34384C91EB9 | Chinese Hand-Pulled Noodles | staple | staple | staple |
| RCP2_E3B3B3009341 | Teriyaki Steak | sauce | None |  |
| RCP2_E4454B4519B1 | Tempura | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_E5862A12458B | Potato Croquettes With Parmesan | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_E58EB09D4E0D | Cheese Stuffing For Manicotti | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_E5A66F91CB58 | Meat Ball Casserole | one_bowl | one_bowl | one_bowl |
| RCP2_E68974FE5EFE | West African Meat Kebabs | protein_main | protein_main | protein_main |
| RCP2_E6D5DE6253DA | Easy Manicotti | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_E729691E63DA | Sugar Free Cranberry Almond Biscotti | dessert | None | breakfast, dessert, staple, snack, one_bowl, protein_main |
| RCP2_E8D667BA918A | Fake Feta | sauce | protein_main | protein_main |
| RCP2_EA7BB1D1BA3A | Fried Rice | one_bowl | one_bowl | one_bowl |
| RCP2_EAAD839F9258 | Mushroom-Barley Soup | soup | None | soup, one_bowl |
| RCP2_EC29565337D3 | Dumpling Noodles | staple | staple | staple |
| RCP2_ED8C37EACE4D | Mock Feta Cheese ( Vegan Substitute ) | sauce | protein_main | protein_main |
| RCP2_EDF4D1848F6C | Mexican Rice | one_bowl | one_bowl | one_bowl |
| RCP2_EE292ED1DADA | Potato-Apple Gratin | staple | None | breakfast, snack, dessert, sauce, drink |
| RCP2_EEA0EE59804C | Putupap (South African Mealie Pap) | staple | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_EFA12409FC76 | Indian Raita (Cucumber Mix) | sauce | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_F015BE03BD1C | Bubble And Squeak | snack | vegetable | vegetable |
| RCP2_F0A2E3140892 | Hearty French Onion Soup | soup | None | soup, one_bowl |
| RCP2_F12F72458249 | Bread Dumplings (Houskove Knedliky) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink |
| RCP2_F14B2A2B76D7 | Teriyaki Rice Paper Salmon (Baked) | protein_main | protein_main | protein_main |
| RCP2_F19948BC59AA | Hungarian Goulash(Serves 6 To 8) | soup | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_F34E700C89B5 | Thai Red Curry | one_bowl | one_bowl | one_bowl |
| RCP2_F36753718C88 | Chicken Thai Pizza | one_bowl | protein_main | protein_main |
| RCP2_F480AAE0C111 | Sweet Potato & Pea Curry | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_F484CD172351 | Post Thanksgiving Turkey Casserole | one_bowl | protein_main | protein_main |
| RCP2_F58B8FD2E4BB | Country Pâté Banh Mi | one_bowl | one_bowl | one_bowl |
| RCP2_F5998F6963E8 | Sauerkraut pierogi | one_bowl | one_bowl | one_bowl |
| RCP2_F62EDB215278 | Cheese Dumplings | snack | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_F79DA309FE66 | Big Mac | one_bowl | protein_main | protein_main |
| RCP2_F8E5BA1851FC | Quesadilla Casserole | one_bowl | one_bowl | one_bowl |
| RCP2_F8F9D659EDAB | German Potato Salad With Cajun Sausage | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_F918B184F959 | Spaetzle | staple | staple | staple |
| RCP2_F96C60076A19 | Korean Noodles And Beef(Main Course From Abroad - Pungent Dish) | one_bowl | one_bowl | one_bowl |
| RCP2_F9AC64939A2C | Welsh Rarebit | sauce | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_FAC0F736C662 | Hoisin Chicken Wraps | one_bowl | one_bowl | one_bowl |
| RCP2_FAD4D33E3669 | Rice Paper Wrapped Fish | protein_main | protein_main | protein_main |
| RCP2_FB5F31874C8A | Fresh Ramen Egg Noodles From Scratch | staple | staple | staple |
| RCP2_FBB45D25EC0B | Seriously Asian: Hooked On Udon Recipe | one_bowl | None | soup, breakfast, snack, dessert, sauce, drink |
| RCP2_FE6B12FA54B8 | Crackling Rice Paper-Wrapped Fish | protein_main | protein_main | protein_main |
| RCP2_FF3C50B5519E | Vietnamese "Banh Mi" Chicken Burger | one_bowl | one_bowl | one_bowl |
