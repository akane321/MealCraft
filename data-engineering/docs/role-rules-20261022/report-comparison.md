# Developer-report comparison

Base: `31ece86`. No timing report was updated. These are developer regressions, not held-out capability or accuracy claims. The comparison uses archived base reports, not a newly run control baseline; changes cannot all be causally attributed to this rule repair when the archived reports predate other main changes.

## full-default

Checks: PASS → PASS. JSON changed.

### one-adult

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 54 | 51 |
| grocery_lines_by_trip | {"None": 87} | {"None": 93} |
| purchase_total_sgd | 405.82 | 439.09 |
| staples | ["Assyrian Rice", "Easy Round Italian Bread", "Super Easy Naan Bread"] | ["Assyrian Rice"] |

New selected titles: Bul-Ko-Kee (Korean Barbecue Beef), Couscous Tabbouleh, Ham And Cheese Quesadillas, Indian-Spiced Shrimp Wrap, Italian-Style Lima Beans, Kimchi, Kimchi Chahan (Fried Rice), Mediterranean Green Beans (Lo-Fat), Moroccan Spiced Beef, Teriyaki Snow Peas And Mushrooms, Thai Cucumber Toss, Thai Ginger Soup.

No longer selected: Beef Stir Fry With Tri-Colored Peppers, Easy Round Italian Bread, Fried Green Tomatoes, Korean Bean Sprout Salad, Marinated Velveted Chicken For Stir-Fry, Mexican Chicken (Low-Fat), Primary Taco Meat, Sauerkraut With Caraway, Super Easy Naan Bread, Szechuan Broccoli (Chinese), Tangy Cole Slaw, Thai Beef, Vietnamese Style Pickled Carrots.

### four-with-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.93 | 2 |
| dishes | 57 | 58 |
| grocery_lines_by_trip | {"None": 111} | {"None": 113} |
| purchase_total_sgd | 567.89 | 665.38 |
| staples | ["Assyrian Rice", "Ramen With Peas And Parmesan"] | ["Assyrian Rice"] |

New selected titles: Black Bean Garlic Edamame, Chinese Salt And Pepper Tofu, Confetti Couscous, Easy Keto Korean Beef With Cauli Rice, Green Bean And Red Bell Pepper Stir-Fry, Hearty Potato Soup, Hungarian Potato Soup, Italian-Style Lima Beans, Lebanese Cabbage Salad, Lemon And Feta Pasta, Lou's German Slaw, Marinated Teriyaki Tofu, Mediterranean Pizza, Mexican Scrambled Eggs, Miso Beef, Pad Thai (Vegan), Pasta Primavera, Scrambled Egg And Noodle Stir-Fry, Shredded Beef For Tacos Or Burritos, Simple Fried Rice, Sliced Cabbage Kimchi, Sweet And Sour Cucumbers, Teriyaki Edamame, Teriyaki Grilled Tofu, Tom Yum Soup With Vegetables.

No longer selected: Baked Veggie Quesadillas, Banana Couscous, Cheese And Corn Chowder, Chinese Fried Rice, Crunchy Szechuan Green Beans, Cuban Corn On The Cob, Egyptian Omelet (Eggah), Elote (Mexican Corn On The Cob), Fried Rice, Japanese Ginger Pork, Korean Barbecue Tofu, Korean Beef, Martha's Gazpacho, Mexican Couscous, Nilaga (Filipino Chicken Stew), Quick And Easy Mexican Pizza, Ramen Noodle Salad (Serve Lots), Ramen With A Twist, Ramen With Peas And Parmesan, Raw Cauliflower Korma, Spicy Nasi Goreng, Spicy Sweet And Sour Cabbage, Spinach Stir Fry With Garlic, Tofu Egg Foo Young, Tofu Omelet Indonesia, Tomato Dumplings.

### six-tight-budget

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.57 | 2.43 |
| dishes | 64 | 62 |
| grocery_lines_by_trip | {"None": 57} | {"None": 54} |
| purchase_total_sgd | 240.27 | 254.54 |
| staples | ["Assyrian Rice", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Super Easy Naan Bread"] | ["Indian Restaurant Style Basmati Rice", "Super Easy Naan Bread"] |

New selected titles: Calico Cauliflower Salad, Chicken Fried Rice, China Fried Rice, Chinese Egg Flower Soup, Chinese Salt And Pepper Tofu, Chinese-Style Vegetables, Cuban Cucumber Salad, Easy Carrot Salad (Indian-Style), Easy Vietnamese Cauliflower, Fat-Free Vegie Stir-Fry, Indian Crepes, Indian Cucumber Salad, Japanese Pickled Cucumber, Korean Bean Spouts, Lean Sweet And Sour Cabbage Borscht, Microwaved Parmesan Chicken, Shish Kabobs, Teriyaki Chicken, Teriyaki Tilapia (My Mock Unagi), Vegetable Fried Rice, “Banquet” Fried Rice.

No longer selected: Assyrian Rice, Broccoli Ginger Stir-Fry, Broccoli Soup, Chinese Cucumber Salad, Chinese Egg Drop Soup, Chinese Sesame Chicken Kabobs, Cinnamon Crepes, Cucumber Namasu, Easy Round Italian Bread, Egyptian Omelet (Eggah), Grilled Parmesan Tomatoes, Hawaiian Curry, Kimchi, Kimchi Salad Aka Quick Kimchi, Korean Bean Sprout Salad, Korean Style Namasu, Mock Fried Rice, Stir-Fried Cabbage, Tandoori Chicken Thighs, Teriyaki Grilled Tofu, Teriyaki Tofu, Tsukemono (Japanese Cabbage Salad), Vietnamese Caramel Chicken.

### two-no-oven-ten-days

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.45 | 1.4 |
| dishes | 74 | 73 |
| grocery_lines_by_trip | {"1": 78, "2": 51} | {"1": 90, "2": 58} |
| purchase_total_sgd | 642.77 | 682.65 |
| staples | ["Assyrian Rice"] | ["Assyrian Rice", "Brazilian Rice", "Super Easy Naan Bread"] |

New selected titles: Banana Couscous, Beef Stir Fry With Tri-Colored Peppers, Bibimbap, Brazilian Rice, Chicken Laksa, Chinese Cabbage, Chinese Chilled Asparagus, Cucumber-Onion Salad, Egg Fried Rice, Elotes, Galbi (Kalbi) Grilled Korean Short Ribs (Flanken Cut), Gazpacho, Greek Grilled Cheese, Hoisin Eggplant Chicken, Indonesian Cucumber Salad, Instant Kimchi Ramyun (Spicy Kimchi Noodles), Japanese Style Cucumber Salad, Korean Barbecued Beef (4 Servings), Sautéed Miso Cucumber Salad, Savory Italian Asparagus, Seared Baby Bok Choy, Seviche-Style Shrimp And Avocado Tacos, Slow Cooker Chicken Tikka Masala (Weight Watchers), Super Easy Naan Bread, Teriyaki Burger, Vietnamese Cabbage, Vietnamese Fish And Tomato Soup.

No longer selected: Bento Chicken Teriyaki, Breakfast Burrito (Like Mc Donald's!), Chinese Egg Flower Soup, Easy Keto Korean Beef With Cauli Rice, Egyptian Tomato Salad, German Coleslaw, Greek Vegetable Salad, Grilled Milkimcheeze Sandwich From 'The Kimchi Cookbook', Indonesian Fried Rice, Japanese Ginger Pork (Shogayaki), Kimchi, Korean Barbecued Beef, Korean Bean Spouts, Korean Bean Sprouts, Korean Ground Beef And Rice Bowls, Korean Krunch Quesadilla, Lemon And Feta Pasta, Mediterranean Kale With Feta, Orange Chicken, Sloppy Joes, Spinach With Sesame And Miso, Stir-Fry Cashew Chicken, Vietnamese Beef And Spinach Soup, Vietnamese Style Pickled Carrots, Wafu Salad (Japanese Style Onion Salad).

### seven-with-young-children

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.14 | 2.36 |
| dishes | 74 | 72 |
| grocery_lines_by_trip | {"None": 110} | {"None": 109} |
| moves | ["day 5 dinner: main left out"] | [] |
| purchase_total_sgd | 739.2 | 810.41 |
| staples | ["Assyrian Rice", "Brazilian Rice", "Claudia Roden's Basic Couscous", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Mama D's Italian Bread", "Super Easy Naan Bread"] | ["Assyrian Rice", "Brazilian Rice", "Claudia Roden's Basic Couscous", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Super Easy Naan Bread"] |

New selected titles: Beef Bulgogi, Chicken And Snow Peas Stir-Fry, Chinese Style Fried Rice, Easy Carrot Salad (Indian-Style), Fresh Broccoli Salad, Ham And Cheese Quesadillas, Hoisin Eggplant Chicken, Indian-Spiced Shrimp Wrap, Japanese Sesame Spinach, Kalbi-Style Short Ribs, Kimchi, Microwaved Parmesan Chicken, Pizza Chicken Melts, Primary Taco Meat, Salmon Steaks Teriyaki, Szechuan Shrimp, Tangy Cole Slaw, Teriyaki Edamame, Thai Cucumber Toss, Thai Sweet And Sour Fresh Cucumber, Vietnamese Cucumber Salad.

No longer selected: Beef Stir Fry With Tri-Colored Peppers, Broiled Tuna Teriyaki, Cucumber Raita, Easy Kimchi Slaw, French Vinaigrette Slaw, Greek Salad Iv, Honey Teriyaki Salmon, Japanese Ginger Pork (Shogayaki), Kimchi Chahan (Fried Rice), Korean Barbecued Beef, Mama D's Italian Bread, Mexican Chicken (Low-Fat), Microwave Shrimp Scampi, Miso Beef, Salmon Yakitori, Salsa Chicken, Sigumchi Namul (Korean Spinach Salad Kimchi), Slow Cooker Chicken Tikka Masala (Weight Watchers), Steamed Thai Mussels, Szechuan Broccoli (Chinese), Thai Beef.

## shared-dish

Checks: PASS → PASS. JSON changed.

### four-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 55 | 56 |
| distinct_dishes_excluding_staples | 47 | 48 |
| energy_attainment_by_member | {"Ann": 1.5, "Ben": 1.673, "Kai": 1.674, "Mei": 1.681} | {"Ann": 1.507, "Ben": 1.662, "Kai": 1.663, "Mei": 1.67} |
| lowest_energy_attainment | 1.5 | 1.507 |
| purchase_total_sgd | 535.59 | 664.17 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2041, "Ben": 7566, "Kai": 7566, "Mei": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 154.0 | 155.02 |

### two-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 64 | 67 |
| distinct_dishes_excluding_staples | 60 | 59 |
| energy_attainment_by_member | {"Lin": 1.509, "Raj": 1.54} | {"Lin": 1.487, "Raj": 1.522} |
| lowest_energy_attainment | 1.509 | 1.487 |
| purchase_total_sgd | 644.5 | 625.39 |
| recipe_pool_by_member | {"Lin": 2037, "Raj": 7544} | {"Lin": 2041, "Raj": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 94.68 | 98.74 |

### with-a-child

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 26 | 24 |
| energy_attainment_by_member | {"Ann": 1.424, "Ben": 1.424, "Mei": 1.431} | {"Ann": 1.446, "Ben": 1.446, "Mei": 1.453} |
| lowest_energy_attainment | 1.424 | 1.446 |
| purchase_total_sgd | 276.49 | 322.41 |
| recipe_pool_by_member | {"Ann": 7544, "Ben": 7544, "Mei": 7087} | {"Ann": 7566, "Ben": 7566, "Mei": 7109} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 49.82 | 45.73 |

### weekday-lunch-away

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 55 | 56 |
| distinct_dishes_excluding_staples | 47 | 48 |
| energy_attainment_by_member | {"Ann": 1.5, "Ben": 1.673, "Kai": 1.674, "Mei": 1.833} | {"Ann": 1.507, "Ben": 1.662, "Kai": 1.663, "Mei": 1.916} |
| lowest_energy_attainment | 1.5 | 1.507 |
| purchase_total_sgd | 527.27 | 660.99 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2041, "Ben": 7566, "Kai": 7566, "Mei": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 147.43 | 149.55 |

### weekend-guest

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 57 | 58 |
| energy_attainment_by_member | {"Ann": 1.546, "Ben": 1.699, "Grandma": 1.318, "Kai": 1.7, "Mei": 1.707} | {"Ann": 1.49, "Ben": 1.653, "Grandma": 1.019, "Kai": 1.654, "Mei": 1.661} |
| lowest_energy_attainment | 1.318 | 1.019 |
| purchase_total_sgd | 567.2 | 661.43 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2041, "Ben": 7566, "Kai": 7566, "Mei": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 161.43 | 161.57 |

### peanut-whole-household

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 23 | 22 |
| energy_attainment_by_member | {"Ann": 1.461, "Ben": 1.461, "Kai": 1.461, "Mei": 1.468} | {"Ann": 1.496, "Ben": 1.496, "Kai": 1.497, "Mei": 1.503} |
| lowest_energy_attainment | 1.461 | 1.496 |
| purchase_total_sgd | 296.25 | 366.28 |
| recipe_pool_by_member | {"Ann": 7119, "Ben": 7119, "Kai": 7119, "Mei": 7119} | {"Ann": 7141, "Ben": 7141, "Kai": 7141, "Mei": 7141} |
| recipe_pool_servable | 7119 | 7141 |
| servings_cooked | 66.3 | 63.24 |

### peanut-only-mei-avoids

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| energy_attainment_by_member | {"Ann": 1.473, "Ben": 1.473, "Kai": 1.474, "Mei": 1.481} | {"Ann": 1.397, "Ben": 1.397, "Kai": 1.398, "Mei": 1.404} |
| lowest_energy_attainment | 1.473 | 1.397 |
| purchase_total_sgd | 316.58 | 357.4 |
| recipe_pool_by_member | {"Ann": 7544, "Ben": 7544, "Kai": 7544, "Mei": 7119} | {"Ann": 7566, "Ben": 7566, "Kai": 7566, "Mei": 7141} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 66.3 | 65.28 |

### mixed-diets

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 24 | 25 |
| distinct_dishes_excluding_staples | 20 | 21 |
| energy_attainment_by_member | {"Ann": 1.392, "Ben": 1.526, "Kai": 1.393, "Mei": 1.533} | {"Ann": 1.307, "Ben": 1.467, "Kai": 1.334, "Mei": 1.474} |
| lowest_energy_attainment | 1.392 | 1.307 |
| purchase_total_sgd | 246.51 | 247.84 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 4718, "Mei": 7544} | {"Ann": 2041, "Ben": 7566, "Kai": 4735, "Mei": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 65.0 | 68.06 |

### six-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 27 | 28 |
| distinct_dishes_excluding_staples | 24 | 23 |
| energy_attainment_by_member | {"Adult 1": 1.364, "Adult 2": 1.531, "Adult 3": 1.531, "Adult 4": 1.531, "Adult 5": 1.531, "Adult 6": 1.531} | {"Adult 1": 1.392, "Adult 2": 1.543, "Adult 3": 1.543, "Adult 4": 1.543, "Adult 5": 1.543, "Adult 6": 1.543} |
| lowest_energy_attainment | 1.364 | 1.392 |
| purchase_total_sgd | 330.92 | 328.76 |
| recipe_pool_by_member | {"Adult 1": 2037, "Adult 2": 7544, "Adult 3": 7544, "Adult 4": 7544, "Adult 5": 7544, "Adult 6": 7544} | {"Adult 1": 2041, "Adult 2": 7566, "Adult 3": 7566, "Adult 4": 7566, "Adult 5": 7566, "Adult 6": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 100.34 | 104.66 |

### tight-budget

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| dishes | 22 | 23 |
| energy_attainment_by_member | {"Ann": 1.323, "Ben": 1.371, "Kai": 1.371, "Mei": 1.377} | {"Ann": 1.3, "Ben": 1.393, "Kai": 1.394, "Mei": 1.4} |
| lowest_energy_attainment | 1.323 | 1.3 |
| purchase_total_sgd | 84.33 | 105.01 |
| recipe_pool_by_member | {"Ann": 2037, "Ben": 7544, "Kai": 7544, "Mei": 7544} | {"Ann": 2041, "Ben": 7566, "Kai": 7566, "Mei": 7566} |
| recipe_pool_servable | 7544 | 7566 |
| servings_cooked | 63.38 | 64.98 |

## household-rules

Checks: PASS → PASS. JSON byte-identical.

## legacy-dev

Checks: PASS → PASS. JSON byte-identical.
