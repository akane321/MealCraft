# Rule-change comparison: full default

Generated from the pre-fix and current developer-only `latest.json`. All cases still pass. This is a regression comparison, not a complete label-accuracy or speed claim. Original model fields remain gated. The timing artifact records the run's base HEAD; the run used the uncommitted rule fixes in this PR, not an unmodified base checkout.

No selected recipe title is a standalone filling/topping component. Component classification, not an unrestricted search for the word 'filling', is tested.

## one-adult

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| distinct_dishes_excluding_staples | 41 | 42 |
| grocery_lines_by_trip | {"None": 85} | {"None": 87} |
| purchase_total_sgd | 374.93 | 405.82 |
| staples | ["Assyrian Rice", "Claudia Roden's Basic Couscous"] | ["Assyrian Rice", "Easy Round Italian Bread", "Super Easy Naan Bread"] |

| Day / meal / role | Before | After |
|---|---|---|
| 1 / dinner / main | Pizza Cheesy Chicken (0.75 portions) | Anitas Lemon Chicken (0.75 portions) |
| 2 / dinner / main | Anitas Lemon Chicken (0.75 portions) | Pizza Cheesy Chicken (0.75 portions) |
| 3 / dinner / main | Salmon Yakitori (0.75 portions) | Microwave Shrimp Scampi (0.75 portions) |
| 3 / dinner / soup | Eunah's Korean-Style Seaweed Soup (0.5 portions) | Martha's Gazpacho (0.5 portions) |
| 3 / dinner / vegetable | Edamame Salad (0.5 portions) | English Pea Salad (0.5 portions) |
| 5 / dinner / soup | Martha's Gazpacho (0.5 portions) | Gazpacho (0.5 portions) |
| 5 / dinner / vegetable | Cuban Cucumber Salad (0.5 portions) | Broccoli Salad (0.5 portions) |
| 5 / lunch / main | Pizza Cheesy Chicken (0.75 portions) | Thai Beef (0.75 portions) |
| 5 / lunch / staple | Assyrian Rice (1.0 portions) | Super Easy Naan Bread (1.0 portions) |
| 5 / lunch / vegetable | Broccoli Salad (0.5 portions) | Jim's Raita (0.5 portions) |
| 6 / dinner / vegetable | Fried Green Tomatoes (0.5 portions) | Cuban Cucumber Salad (0.5 portions) |
| 6 / lunch / vegetable | Feta Cucumber Salad (0.5 portions) | Fried Green Tomatoes (0.5 portions) |
| 7 / dinner / main | Flank Steak Teriyaki (0.75 portions) | Primary Taco Meat (0.75 portions) |
| 7 / dinner / soup | Thai Ginger Soup (0.5 portions) | Iranian Yogurt Soup (0.5 portions) |
| 7 / dinner / staple | Claudia Roden's Basic Couscous (1.0 portions) | Easy Round Italian Bread (1.0 portions) |
| 7 / dinner / vegetable | Singapore Cucumber Salad (0.5 portions) | Sauerkraut With Caraway (0.5 portions) |
| 7 / lunch / main | Bento Chicken Teriyaki (0.75 portions) | Beef Stir Fry With Tri-Colored Peppers (0.75 portions) |
| 7 / lunch / vegetable | Jim's Raita (0.5 portions) | Szechuan Broccoli (Chinese) (0.5 portions) |

## four-with-vegetarian

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.71 | 1.64 |
| dishes | 58 | 59 |
| distinct_dishes_excluding_staples | 50 | 51 |
| purchase_total_sgd | 606.29 | 635.41 |
| staples | ["Assyrian Rice", "Indian Chapati Bread"] | ["Assyrian Rice", "Brazilian Rice"] |

| Day / meal / role | Before | After |
|---|---|---|
| 1 / dinner / vegetable | Korean Bean Sprout Salad (1.956 portions) | Grilled Parmesan Tomatoes (1.956 portions) |
| 2 / breakfast / main | Feta Omelet (4.08 portions) | Sunrise Taco (4.08 portions) |
| 2 / dinner / main | Greek Penne Pasta (6 Ww Points) (4.08 portions) | Korean Barbecue Tofu (2.04 portions) |
| 2 / dinner / staple | — | Assyrian Rice (4.08 portions) |
| 2 / dinner / vegetable | Grilled Parmesan Tomatoes (2.04 portions) | Taco Slaw (2.04 portions) |
| 2 / lunch / main | Turkish Grilled Cheese Sandwich (4.08 portions) | Ramen With A Twist (4.08 portions) |
| 2 / lunch / vegetable | Seared Wheels Of Sweet Corn In Indonesian Kecap (2.04 portions) | Korean Bean Sprout Salad (2.04 portions) |
| 3 / breakfast / main | Sunrise Taco (4.08 portions) | Tony's Breakfast Couscous (4.08 portions) |
| 3 / lunch / main | Marinated Teriyaki Tofu (3.06 portions) | Egg And Cheese Tostadas (4.08 portions) |
| 3 / lunch / staple | Assyrian Rice (4.08 portions) | — |
| 3 / lunch / vegetable | Edamame Salad (2.04 portions) | English Pea Salad (2.04 portions) |
| 4 / breakfast / main | Banana Couscous (4.08 portions) | Feta Omelet (4.08 portions) |
| 5 / breakfast / main | Easy Mexican Omelet (4.08 portions) | Banana Couscous (4.08 portions) |
| 5 / dinner / main-2 | Korean Barbecue Tofu (2.04 portions) | Tarka Dhall (2.04 portions) |
| 5 / dinner / soup | Irish Potato Soup (2.04 portions) | Lentil Potato Dal (2.04 portions) |
| 5 / dinner / vegetable | Sauerkraut With Caraway (2.04 portions) | Jim's Raita (2.04 portions) |
| 5 / lunch / main | Vegan Chickpea Korma (3.06 portions) | Madras Egg Curry (3.06 portions) |
| 5 / lunch / vegetable | Jim's Raita (2.04 portions) | Carrot Raita (2.04 portions) |
| 6 / dinner / staple | Indian Chapati Bread (4.08 portions) | Brazilian Rice (4.08 portions) |
| 6 / dinner / vegetable | Thai Sweet-Garlicky Cauliflower With Red Pepper Strips (2.04 portions) | Thai Sweet And Sour Fresh Cucumber (2.04 portions) |
| 7 / dinner / main | Chinese Fried Rice (4.89 portions) | Crispy Tofu Stir Fry (2.445 portions) |
| 7 / dinner / main-2 | Korean Barbecue Tofu (2.445 portions) | South African Curried Eggs (2.445 portions) |
| 7 / dinner / staple | — | Assyrian Rice (4.89 portions) |
| 7 / dinner / vegetable | Wafu Salad (Japanese Style Onion Salad) (1.956 portions) | Black Bean Garlic Edamame (1.956 portions) |

## six-tight-budget

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.21 | 2.43 |
| dishes | 64 | 69 |
| grocery_lines_by_trip | {"None": 64} | {"None": 59} |
| purchase_total_sgd | 264.32 | 270.4 |
| staples | ["Assyrian Rice", "Indian Restaurant Style Basmati Rice", "Super Easy Naan Bread"] | ["Assyrian Rice", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Mama D's Italian Bread", "Super Easy Naan Bread"] |

| Day / meal / role | Before | After |
|---|---|---|
| 1 / breakfast / main | Irish Porridge (6.0 portions) | Chinese Black Sesame Seed Porridge (Geema Woo) (6.0 portions) |
| 1 / dinner / main | Chinese Style Fried Rice (6.0 portions) | Quick Shake Pizza (3.0 portions) |
| 1 / dinner / main-2 | Moroccon Spiced Chicken Kabobs (3.0 portions) | Japanese Grilled Chicken (3.0 portions) |
| 1 / dinner / soup | Cream Of Potato Soup (3.0 portions) | Thai Ginger Soup (3.0 portions) |
| 1 / dinner / staple | — | Mama D's Italian Bread (6.0 portions) |
| 1 / dinner / vegetable | Broccoli Ginger Stir-Fry (2.4 portions) | Hot And Sour Cabbage Salad (2.4 portions) |
| 1 / dinner / vegetable-2 | Cantonese Family Stir Fried Vegetables (2.4 portions) | Korean Bean Spouts (2.4 portions) |
| 1 / lunch / main | Thai-Style Omelet (Khai Jiao) (4.5 portions) | Egg Fried Rice (6.0 portions) |
| 1 / lunch / staple | Assyrian Rice (6.0 portions) | — |
| 2 / dinner / main | Golden Chicken Nuggets (3.0 portions) | Great Chicken (3.0 portions) |
| 2 / dinner / main-2 | Egg Foo Young (3.0 portions) | Honey Teriyaki Salmon (3.0 portions) |
| 2 / dinner / soup | Irish Potato Soup (3.0 portions) | Broccoli Soup (3.0 portions) |
| 2 / dinner / staple | Indian Restaurant Style Basmati Rice (6.0 portions) | Easy Round Italian Bread (6.0 portions) |
| 2 / dinner / vegetable | Sliced Cabbage Kimchi (2.4 portions) | Broccoli Ginger Stir-Fry (2.4 portions) |
| 2 / dinner / vegetable-2 | Kimchi Salad Aka Quick Kimchi (2.4 portions) | Seasoned Power Greens (2.4 portions) |
| 2 / lunch / main | Korean Barbecue Tofu (4.5 portions) | Teriyaki Tofu (4.5 portions) |
| 2 / lunch / vegetable | German Coleslaw (3.0 portions) | Thai Sweet-Garlicky Cauliflower With Red Pepper Strips (3.0 portions) |
| 3 / dinner / main | Easy Pad Thai (6.0 portions) | Golden Chicken Nuggets (3.0 portions) |
| 3 / dinner / main-2 | Vietnamese Grilled Lemongrass Chicken (3.0 portions) | Egg Foo Young (3.0 portions) |
| 3 / dinner / soup | Chicken And Dumplings (3.0 portions) | Chinese Egg Drop Soup (3.0 portions) |
| 3 / dinner / staple | — | Indian Restaurant Style Basmati Rice (6.0 portions) |
| 3 / dinner / vegetable | Grilled Parmesan Tomatoes (2.4 portions) | Carrot And Spinach Stirfry (2.4 portions) |
| 3 / dinner / vegetable-2 | Easy Vietnamese Cauliflower (2.4 portions) | Stir-Fried Cabbage (2.4 portions) |
| 3 / lunch / main | Tofu Egg Foo Young (4.5 portions) | Vietnamese Pie] (4.5 portions) |
| 3 / lunch / staple | Super Easy Naan Bread (6.0 portions) | Assyrian Rice (6.0 portions) |
| 4 / breakfast / main | Crepes (6.0 portions) | Irish Porridge (6.0 portions) |
| 4 / dinner / main | Ramen Korean-Style (6.0 portions) | Teriyaki Grilled Tofu (3.0 portions) |
| 4 / dinner / main-2 | Great Chicken (3.0 portions) | Hurry Curry (3.0 portions) |
| 4 / dinner / soup | Chinese Egg Drop Soup (3.0 portions) | Hearty Potato Soup (3.0 portions) |
| 4 / dinner / staple | — | Indian Restaurant Style Basmati Rice (6.0 portions) |
| 4 / dinner / vegetable | Gingered Zucchini (2.4 portions) | Kimchi (2.4 portions) |
| 4 / dinner / vegetable-2 | Japanese Salad (2.4 portions) | Kimchi Salad Aka Quick Kimchi (2.4 portions) |
| 4 / lunch / main | Bento Chicken Teriyaki (4.5 portions) | Microwave Sweet And Sour Chicken (4.5 portions) |
| 4 / lunch / staple | Super Easy Naan Bread (6.0 portions) | Assyrian Rice (6.0 portions) |
| 4 / lunch / vegetable | Sesame-Carrot Edamame Salad (3.0 portions) | Cantonese Family Stir Fried Vegetables (3.0 portions) |
| 5 / dinner / main | Teriyaki Fried Rice (6.0 portions) | Korean Barbecue Tofu (3.0 portions) |
| 5 / dinner / main-2 | Hurry Curry (3.0 portions) | Vietnamese Grilled Lemongrass Chicken (3.0 portions) |
| 5 / dinner / soup | Hearty Potato Soup (3.0 portions) | Irish Potato Soup (3.0 portions) |
| 5 / dinner / staple | — | Mama D's Italian Bread (6.0 portions) |
| 5 / dinner / vegetable | Hot And Sour Cabbage Salad (2.4 portions) | Cho Na-Mool (Korean Cabbage Salad) (2.4 portions) |
| 5 / dinner / vegetable-2 | Easy Carrot Salad (Indian-Style) (2.4 portions) | Gingered Zucchini (2.4 portions) |
| 5 / lunch / staple | Indian Restaurant Style Basmati Rice (6.0 portions) | Super Easy Naan Bread (6.0 portions) |
| 5 / lunch / vegetable | Fried Cabbage (3.0 portions) | Calico Cauliflower Salad (3.0 portions) |
| 6 / breakfast / main | Chinese Black Sesame Seed Porridge (Geema Woo) (6.0 portions) | Scrambled Eggs (6.0 portions) |
| 6 / dinner / main | Chinese New Year Rice (6.0 portions) | Thai-Style Omelet (Khai Jiao) (3.0 portions) |
| 6 / dinner / main-2 | Quick Shake Pizza (3.0 portions) | Tandoori Chicken Thighs (3.0 portions) |
| 6 / dinner / soup | Lean Sweet And Sour Cabbage Borscht (3.0 portions) | Chicken And Dumplings (3.0 portions) |
| 6 / dinner / staple | — | Indian Restaurant Style Basmati Rice (6.0 portions) |
| 6 / dinner / vegetable | Moroccan Carrot And Cinnamon Salad (2.4 portions) | Grilled Parmesan Tomatoes (2.4 portions) |
| 6 / dinner / vegetable-2 | Cho Na-Mool (Korean Cabbage Salad) (2.4 portions) | Sweet And Sour Cabbage (2.4 portions) |
| 6 / lunch / main | Teriyaki Tofu (4.5 portions) | Chinese Sesame Chicken Kabobs (4.5 portions) |
| 6 / lunch / staple | Indian Restaurant Style Basmati Rice (6.0 portions) | Super Easy Naan Bread (6.0 portions) |
| 6 / lunch / vegetable | Colombian Coleslaw (3.0 portions) | German Coleslaw (3.0 portions) |
| 7 / breakfast / main | Tamagoyaki (Japanese Omelet) (6.0 portions) | Crepes (6.0 portions) |
| 7 / dinner / main | Hawaiian Curry (6.0 portions) | Chicken Burgers (3.0 portions) |
| 7 / dinner / soup | Broccoli Soup (3.0 portions) | Cream Of Potato Soup (3.0 portions) |
| 7 / dinner / staple | — | Mama D's Italian Bread (6.0 portions) |
| 7 / dinner / vegetable | Calico Cauliflower Salad (2.4 portions) | Shish Kabobs (2.4 portions) |
| 7 / dinner / vegetable-2 | Shish Kabobs (2.4 portions) | Easy Vietnamese Cauliflower (2.4 portions) |
| 7 / lunch / main | Vietnamese Pie] (4.5 portions) | Creamed Chicken Curry (4.5 portions) |
| 7 / lunch / vegetable | Thai-Style Beet Salad (3.0 portions) | Fried Cabbage (3.0 portions) |

## two-no-oven-ten-days

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.4 | 1.45 |
| dishes | 76 | 74 |
| distinct_dishes_excluding_staples | 60 | 59 |
| grocery_lines_by_trip | {"1": 89, "2": 60} | {"1": 78, "2": 51} |
| purchase_total_sgd | 705.74 | 642.77 |
| staples | ["Assyrian Rice", "Super Easy Naan Bread"] | ["Assyrian Rice"] |

| Day / meal / role | Before | After |
|---|---|---|
| 2 / lunch / main | Scallops Portuguese (1.5 portions) | Primary Taco Meat (1.5 portions) |
| 3 / lunch / main | Chicken Skewers With Satay Salad (1.5 portions) | Bento Chicken Teriyaki (1.5 portions) |
| 3 / lunch / staple | Super Easy Naan Bread (2.0 portions) | Assyrian Rice (2.0 portions) |
| 3 / lunch / vegetable | Fresh Pesto And Tomato Salad (1.0 portions) | Korean Bean Spouts (1.0 portions) |
| 4 / breakfast / main | Thai Omelette (2.0 portions) | Breakfast Burrito (Like Mc Donald's!) (2.0 portions) |
| 4 / lunch / main | Pizza Chicken Melts (1.5 portions) | Grilled Milkimcheeze Sandwich From 'The Kimchi Cookbook' (2.0 portions) |
| 4 / lunch / staple | Assyrian Rice (2.0 portions) | — |
| 4 / lunch / vegetable | Tomato And Cucumber Salad With Feta (1.0 portions) | Wafu Salad (Japanese Style Onion Salad) (1.0 portions) |
| 5 / breakfast / main | Jerica's French Toast (2.0 portions) | Thai Omelette (2.0 portions) |
| 5 / dinner / main | Easy Slow Cooker Sweet And Sour Pork Chops (1.5 portions) | Korean Ground Beef And Rice Bowls (2.0 portions) |
| 5 / dinner / soup | Martha's Gazpacho (1.0 portions) | Gazpacho (Spanish Cold Soup) (1.0 portions) |
| 5 / dinner / staple | Assyrian Rice (2.0 portions) | — |
| 5 / dinner / vegetable | Cuban Cucumber Salad (1.0 portions) | Cucumber Namasu (1.0 portions) |
| 5 / lunch / main | Kung Pao Pork (1.5 portions) | Lemon And Feta Pasta (2.0 portions) |
| 5 / lunch / staple | Assyrian Rice (2.0 portions) | — |
| 5 / lunch / vegetable | Asparagus & Mushroom Stir Fry (1.0 portions) | Fresh Pesto And Tomato Salad (1.0 portions) |
| 6 / dinner / main | Teriyaki Burger (1.5 portions) | Sloppy Joes (1.5 portions) |
| 6 / dinner / soup | Gazpacho (Spanish Cold Soup) (1.0 portions) | Martha's Gazpacho (1.0 portions) |
| 6 / dinner / vegetable | Easy, Dynamite Cauliflower Curry (1.0 portions) | Cuban Cucumber Salad (1.0 portions) |
| 7 / dinner / main | Korean Barbecued Beef (1.5 portions) | Bul-Ko-Kee (Korean Barbecue Beef) (1.5 portions) |
| 7 / dinner / vegetable | Cucumber Namasu (1.0 portions) | Kimchi (1.0 portions) |
| 7 / lunch / main | Primary Taco Meat (1.5 portions) | Indonesian Fried Rice (2.0 portions) |
| 7 / lunch / staple | Assyrian Rice (2.0 portions) | — |
| 8 / dinner / main | Easy Teriyaki Chops (1.5 portions) | Stir-Fry Cashew Chicken (1.5 portions) |
| 8 / lunch / main | Ramen With A Twist (2.0 portions) | Orange Chicken (1.5 portions) |
| 8 / lunch / staple | — | Assyrian Rice (2.0 portions) |
| 8 / lunch / vegetable | Sautéed Miso Cucumber Salad (1.0 portions) | Mediterranean Kale With Feta (1.0 portions) |
| 9 / dinner / main | Shrimp Curry In A Hurry (1.5 portions) | Moroccan Tuna Steaks (1.5 portions) |
| 9 / dinner / soup | Tomato Dumplings (1.0 portions) | Nigerian Peanut Soup (1.0 portions) |
| 9 / dinner / vegetable | Elotes (1.0 portions) | Egyptian Tomato Salad (1.0 portions) |
| 9 / lunch / main | Marinated Velveted Chicken For Stir-Fry (1.5 portions) | Thai-Style Omelet (Khai Jiao) (1.5 portions) |
| 9 / lunch / staple | Super Easy Naan Bread (2.0 portions) | Assyrian Rice (2.0 portions) |
| 9 / lunch / vegetable | Cucumber-Onion Salad (1.0 portions) | Jim's Raita (1.0 portions) |
| 10 / lunch / main | Indonesian Fried Rice (2.0 portions) | Korean Barbecued Beef (1.5 portions) |
| 10 / lunch / staple | — | Assyrian Rice (2.0 portions) |

## seven-with-young-children

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.21 | 2.14 |
| distinct_dishes_excluding_staples | 53 | 57 |
| grocery_lines_by_trip | {"None": 109} | {"None": 110} |
| purchase_total_sgd | 689.56 | 739.2 |
| staples | ["Assyrian Rice"] | ["Assyrian Rice", "Brazilian Rice", "Claudia Roden's Basic Couscous", "Easy Round Italian Bread", "Indian Restaurant Style Basmati Rice", "Mama D's Italian Bread", "Super Easy Naan Bread"] |

| Day / meal / role | Before | After |
|---|---|---|
| 1 / dinner / main-2 | Pizza Cheesy Chicken (1.912 portions) | Honey Teriyaki Salmon (1.912 portions) |
| 1 / dinner / main-3 | Thai-Style Omelet (Khai Jiao) (1.912 portions) | Pizza Cheesy Chicken (1.912 portions) |
| 1 / dinner / vegetable-2 | Sauerkraut With Caraway (1.912 portions) | Korean Bean Sprout Salad (1.912 portions) |
| 2 / breakfast / main | Feta Omelet (4.78 portions) | Sunrise Taco (4.78 portions) |
| 2 / dinner / staple | Assyrian Rice (4.78 portions) | Brazilian Rice (4.78 portions) |
| 2 / lunch / main | Miso Beef (3.585 portions) | Indonesian Fried Rice (4.78 portions) |
| 2 / lunch / staple | Assyrian Rice (4.78 portions) | — |
| 2 / lunch / vegetable | Korean Bean Sprout Salad (2.39 portions) | Fresh Pesto And Tomato Salad (2.39 portions) |
| 3 / breakfast / main | Sunrise Taco (4.78 portions) | Feta Omelet (4.78 portions) |
| 3 / dinner / main-3 | Thai-Style Omelet (Khai Jiao) (1.912 portions) | Steamed Thai Mussels (1.912 portions) |
| 3 / dinner / staple | Assyrian Rice (4.78 portions) | Easy Round Italian Bread (4.78 portions) |
| 3 / lunch / main | Teriyaki Chicken (3.585 portions) | Microwave Shrimp Scampi (3.585 portions) |
| 3 / lunch / vegetable | Edamame Salad (2.39 portions) | English Pea Salad (2.39 portions) |
| 4 / dinner / main-3 | Hoisin Eggplant Chicken (1.912 portions) | Japanese Ginger Pork (Shogayaki) (1.912 portions) |
| 4 / dinner / staple | Assyrian Rice (4.78 portions) | Indian Restaurant Style Basmati Rice (4.78 portions) |
| 4 / lunch / vegetable | Fresh Pesto And Tomato Salad (2.39 portions) | Cuban Cucumber Salad (2.39 portions) |
| 5 / dinner / main-3 | Microwaved Parmesan Chicken (2.39 portions) | Slow Cooker Chicken Tikka Masala (Weight Watchers) (2.39 portions) |
| 5 / lunch / main | Thai-Style Omelet (Khai Jiao) (3.585 portions) | Thai Beef (3.585 portions) |
| 5 / lunch / staple | Assyrian Rice (4.78 portions) | Super Easy Naan Bread (4.78 portions) |
| 5 / lunch / vegetable | Cuban Cucumber Salad (2.39 portions) | Chinese Ginger Garlic Asparagus (2.39 portions) |
| 6 / dinner / staple | Assyrian Rice (4.78 portions) | Mama D's Italian Bread (4.78 portions) |
| 6 / lunch / main | Indonesian Fried Rice (4.78 portions) | Bul-Ko-Kee (Korean Barbecue Beef) (3.585 portions) |
| 6 / lunch / staple | — | Assyrian Rice (4.78 portions) |
| 7 / dinner / main-3 | Korean Barbecued Beef (1.912 portions) | Miso Beef (1.912 portions) |
| 7 / dinner / staple | Assyrian Rice (4.78 portions) | Claudia Roden's Basic Couscous (4.78 portions) |
| 7 / lunch / main | Bento Chicken Teriyaki (3.585 portions) | Beef Stir Fry With Tri-Colored Peppers (3.585 portions) |
