# Developer-report comparison

Baseline revision is recorded in review.json. No timing report was updated. These are developer regressions, not held-out capability or accuracy claims. This compares archived base reports. For weekday-lunch-away, demo-cost-comparison.json/md additionally records fresh main/round-one/round-two replays with an identical request; the main replay reproduces its archive. Other cases here are archive comparisons, not separate new control runs.

## full-default

Checks: PASS → PASS. JSON changed.

### one-adult

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.21 | 1.07 |
| grocery_lines_by_trip | {"None": 87} | {"None": 86} |
| purchase_total_sgd | 405.82 | 383.01 |
| staples | ["Assyrian Rice", "Easy Round Italian Bread", "Super Easy Naan Bread"] | ["Assyrian Rice"] |

New selected titles: Bul-Ko-Kee (Korean Barbecue Beef), Chinese Ginger Garlic Asparagus, Singapore Cucumber Salad, Stir-Fry Cashew Chicken, Thai Ginger Soup.

No longer selected: Easy Round Italian Bread, Fried Green Tomatoes, Iranian Yogurt Soup, Primary Taco Meat, Sauerkraut With Caraway, Super Easy Naan Bread, Thai Beef.

### four-with-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.93 | 1.71 |
| dishes | 57 | 59 |
| distinct_dishes_excluding_staples | 50 | 48 |
| grocery_lines_by_trip | {"None": 111} | {"None": 96} |
| purchase_total_sgd | 567.89 | 501.04 |
| staples | ["Assyrian Rice", "Ramen With Peas And Parmesan"] | ["Assyrian Rice", "Ramen With Peas And Parmesan", "Super Easy Naan Bread"] |

New selected titles: Carrot And Broccoli Stir-Fry, Chinese Egg Flower Soup, Chinese Salt And Pepper Tofu, Chinese-Style Zucchini, Hearty Potato Soup, Hungarian Potato Soup, Japanese Ginger Salad, Japanese-Style Sesame Green Beans, Lemon And Feta Pasta, Mexican Chicken (Low-Fat), Mexican Scrambled Eggs, Moroccan Chicken, Primary Taco Meat, Sigumchi Namul (Korean Spinach Salad Kimchi), Super Easy Naan Bread, Teriyaki Beef Stew, Teriyaki Grilled Tofu.

No longer selected: Banana Couscous, Cheese And Corn Chowder, Chilean Salad, Chinese Fried Rice, Crunchy Szechuan Green Beans, Egyptian Omelet (Eggah), Great Chicken, Japanese Ginger Pork, Korean Beef, Korean Coleslaw, Martha's Gazpacho, Mexican Couscous, Nilaga (Filipino Chicken Stew), Ramen Noodle Salad (Serve Lots), Ramen With A Twist, Raw Cauliflower Korma, Teriyaki Tofu, Tofu Omelet Indonesia.

### six-tight-budget

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.57 | 2.64 |
| dishes | 64 | 65 |
| grocery_lines_by_trip | {"None": 57} | {"None": 58} |
| purchase_total_sgd | 240.27 | 253.92 |
| staples | ["Assyrian Rice", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Super Easy Naan Bread"] | ["Assyrian Rice", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Mama D's Italian Bread", "Super Easy Naan Bread"] |

New selected titles: Calico Cauliflower Salad, Chicken Fried Rice, Chinese Salt And Pepper Tofu, Creamed Chicken Curry, Danish Cucumbers, Easy Carrot Salad (Indian-Style), Easy Vietnamese Cauliflower, Egg Foo Young, Hot And Sour Cabbage Salad, Hurry Curry, Japanese Salad, Korean Bean Spouts, Lean Sweet And Sour Cabbage Borscht, Mama D's Italian Bread, Scrambled Eggs, Shish Kabobs, Teriyaki Chicken, Teriyaki Tilapia (My Mock Unagi), Thai Ginger Soup, Vietnamese Grilled Lemongrass Chicken.

No longer selected: Chinese Cucumber Salad, Chinese Egg Drop Soup, Cinnamon Crepes, Cucumber Namasu, Gingered Zucchini, Great Chicken, Grilled Parmesan Tomatoes, Hawaiian Curry, Kimchi And Tofu Soup, Kimchi Chahan (Fried Rice), Korean Bean Sprout Salad, Menma (Braised Bamboo Ramen Topping), Microwave Sweet And Sour Chicken, Potato-Broccoli Frittata, Spicy Sweet And Sour Cabbage, Stir-Fried Cabbage, Teriyaki Grilled Tofu, Teriyaki Tofu, Vietnamese Caramel Chicken.

### two-no-oven-ten-days

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 74 | 72 |
| grocery_lines_by_trip | {"1": 78, "2": 51} | {"1": 86, "2": 52} |
| purchase_total_sgd | 642.77 | 680.04 |

New selected titles: Chicken Laksa, Couscous Tabbouleh, Ensalada Chilena (Chilean Salad), Greek Salad Iv, Indian-Spiced Shrimp Wrap, Instant Kimchi Ramyun (Spicy Kimchi Noodles), Japanese Style Cucumber Salad, Jerica's French Toast.

No longer selected: Breakfast Burrito (Like Mc Donald's!), Easy Keto Korean Beef With Cauli Rice, German Coleslaw, Greek Vegetable Salad, Kimchi, Korean Barbecued Beef, Korean Ground Beef And Rice Bowls, Spinach With Sesame And Miso.

### seven-with-young-children

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.14 | 2.29 |
| dishes | 74 | 75 |
| distinct_dishes_excluding_staples | 57 | 55 |
| grocery_lines_by_trip | {"None": 110} | {"None": 107} |
| moves | ["day 5 dinner: main left out"] | [] |
| purchase_total_sgd | 739.2 | 720.86 |
| staples | ["Assyrian Rice", "Brazilian Rice", "Claudia Roden's Basic Couscous", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Mama D's Italian Bread", "Super Easy Naan Bread"] | ["Assyrian Rice", "Brazilian Rice", "Claudia Roden's Basic Couscous", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Mama D's Italian Bread"] |

New selected titles: Grilled Orange Chicken On The George Foreman Grill, Hoisin Eggplant Chicken, Microwaved Parmesan Chicken, Stir-Fry Cashew Chicken, Thai Sesame Beef.

No longer selected: Jamaican Rubbed Chops, Japanese Ginger Pork (Shogayaki), Miso Beef, Shredded Beef For Tacos Or Burritos, Slow Cooker Chicken Tikka Masala (Weight Watchers), Steamed Thai Mussels, Super Easy Naan Bread, Thai Beef.

## shared-dish

Checks: PASS → PASS. JSON changed.

### four-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 55 | 56 |
| distinct_dishes_excluding_staples | 47 | 46 |
| energy_attainment_by_member | {"Ann": 1.5, "Ben": 1.673, "Kai": 1.674, "Mei": 1.681} | {"Ann": 1.466, "Ben": 1.589, "Kai": 1.59, "Mei": 1.597} |
| lowest_energy_attainment | 1.5 | 1.466 |
| purchase_total_sgd | 535.59 | 517.41 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} |
| recipe_pool_servable | 7544 | 7565 |
| servings_cooked | 154.0 | 157.5 |

### two-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| distinct_dishes_excluding_staples | 60 | 58 |
| energy_attainment_by_member | {"Lin": 1.509, "Raj": 1.54} | {"Lin": 1.457, "Raj": 1.506} |
| lowest_energy_attainment | 1.509 | 1.457 |
| purchase_total_sgd | 644.5 | 669.81 |
| recipe_pool_by_member | {"Lin": 2037, "Raj": 7544} | {"Lin": 2040, "Raj": 7565} |
| recipe_pool_servable | 7544 | 7565 |

### with-a-child

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| energy_attainment_by_member | {"Ann": 1.424, "Ben": 1.424, "Mei": 1.431} | {"Ann": 1.472, "Ben": 1.472, "Mei": 1.479} |
| lowest_energy_attainment | 1.424 | 1.472 |
| purchase_total_sgd | 276.49 | 276.27 |
| recipe_pool_by_member | {"Ann": 7544, "Ben": 7544, "Mei": 7087} | {"Ann": 7565, "Ben": 7565, "Mei": 7108} |
| recipe_pool_servable | 7544 | 7565 |

### weekday-lunch-away

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 55 | 56 |
| distinct_dishes_excluding_staples | 47 | 46 |
| energy_attainment_by_member | {"Ann": 1.5, "Ben": 1.673, "Kai": 1.674, "Mei": 1.833} | {"Ann": 1.466, "Ben": 1.589, "Kai": 1.59, "Mei": 1.748} |
| lowest_energy_attainment | 1.5 | 1.466 |
| purchase_total_sgd | 527.27 | 507.92 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} |
| recipe_pool_servable | 7544 | 7565 |
| servings_cooked | 147.43 | 150.93 |

### weekend-guest

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 57 | 59 |
| distinct_dishes_excluding_staples | 50 | 48 |
| energy_attainment_by_member | {"Ann": 1.546, "Ben": 1.699, "Grandma": 1.318, "Kai": 1.7, "Mei": 1.707} | {"Ann": 1.482, "Ben": 1.635, "Grandma": 1.276, "Kai": 1.636, "Mei": 1.643} |
| lowest_energy_attainment | 1.318 | 1.276 |
| purchase_total_sgd | 567.2 | 500.09 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} |
| recipe_pool_servable | 7544 | 7565 |
| servings_cooked | 161.43 | 164.49 |

### peanut-whole-household

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| energy_attainment_by_member | {"Ann": 1.461, "Ben": 1.461, "Kai": 1.461, "Mei": 1.468} | {"Ann": 1.502, "Ben": 1.502, "Kai": 1.503, "Mei": 1.509} |
| lowest_energy_attainment | 1.461 | 1.502 |
| purchase_total_sgd | 296.25 | 317.11 |
| recipe_pool_by_member | {"Ann": 7119, "Ben": 7119, "Kai": 7119, "Mei": 7119} | {"Ann": 7140, "Ben": 7140, "Kai": 7140, "Mei": 7140} |
| recipe_pool_servable | 7119 | 7140 |

### peanut-only-mei-avoids

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 23 | 24 |
| energy_attainment_by_member | {"Ann": 1.473, "Ben": 1.473, "Kai": 1.474, "Mei": 1.481} | {"Ann": 1.425, "Ben": 1.425, "Kai": 1.426, "Mei": 1.432} |
| lowest_energy_attainment | 1.473 | 1.425 |
| purchase_total_sgd | 316.58 | 301.3 |
| recipe_pool_by_member | {"Ann": 7544, "Ben": 7544, "Kai": 7544, "Mei": 7119} | {"Ann": 7565, "Ben": 7565, "Kai": 7565, "Mei": 7140} |
| recipe_pool_servable | 7544 | 7565 |
| servings_cooked | 66.3 | 68.34 |

### mixed-diets

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 24 | 26 |
| energy_attainment_by_member | {"Ann": 1.392, "Ben": 1.526, "Kai": 1.393, "Mei": 1.533} | {"Ann": 1.36, "Ben": 1.519, "Kai": 1.386, "Mei": 1.526} |
| lowest_energy_attainment | 1.392 | 1.36 |
| purchase_total_sgd | 246.51 | 219.26 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 4718, "Mei": 7544} | {"Ann": 2040, "Ben": 7565, "Kai": 4735, "Mei": 7565} |
| recipe_pool_servable | 7544 | 7565 |
| servings_cooked | 65.0 | 71.11 |

### six-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 27 | 28 |
| distinct_dishes_excluding_staples | 24 | 23 |
| energy_attainment_by_member | {"Adult 1": 1.364, "Adult 2": 1.531, "Adult 3": 1.531, "Adult 4": 1.531, "Adult 5": 1.531, "Adult 6": 1.531} | {"Adult 1": 1.406, "Adult 2": 1.561, "Adult 3": 1.561, "Adult 4": 1.561, "Adult 5": 1.561, "Adult 6": 1.561} |
| lowest_energy_attainment | 1.364 | 1.406 |
| purchase_total_sgd | 330.92 | 333.15 |
| recipe_pool_by_member | {"Adult 1": 2037, "Adult 2": 7544, "Adult 3": 7544, "Adult 4": 7544, "Adult 5": 7544, "Adult 6": 7544} | {"Adult 1": 2040, "Adult 2": 7565, "Adult 3": 7565, "Adult 4": 7565, "Adult 5": 7565, "Adult 6": 7565} |
| recipe_pool_servable | 7544 | 7565 |
| servings_cooked | 100.34 | 104.31 |

### tight-budget

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| energy_attainment_by_member | {"Ann": 1.323, "Ben": 1.371, "Kai": 1.371, "Mei": 1.377} | {"Ann": 1.275, "Ben": 1.328, "Kai": 1.329, "Mei": 1.335} |
| lowest_energy_attainment | 1.323 | 1.275 |
| purchase_total_sgd | 84.33 | 94.86 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} |
| recipe_pool_servable | 7544 | 7565 |

## household-rules

Checks: PASS → PASS. JSON byte-identical.

## legacy-dev

Checks: PASS → PASS. JSON byte-identical.
