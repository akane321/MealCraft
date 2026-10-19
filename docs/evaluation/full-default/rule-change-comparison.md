# Rule-change comparison: full default

Generated from the pre-fix and current developer-only `latest.json`. All cases still pass. This is a regression comparison, not a complete label-accuracy or speed claim. Original model fields remain gated. The timing artifact records the run's base HEAD; the run used the uncommitted rule fixes in this PR, not an unmodified base checkout.

No selected recipe title is a standalone filling/topping component. Component classification, not an unrestricted search for the word 'filling', is tested.

## one-adult

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.21 | 1.14 |
| grocery_lines_by_trip | {"None": 85} | {"None": 83} |
| purchase_total_sgd | 374.93 | 374.2 |

| Day / meal / role | Before | After |
|---|---|---|
| 7 / dinner / main | Flank Steak Teriyaki (0.75 portions) | Primary Taco Meat (0.75 portions) |
| 7 / dinner / soup | Thai Ginger Soup (0.5 portions) | Gazpacho (0.5 portions) |
| 7 / dinner / vegetable | Singapore Cucumber Salad (0.5 portions) | Sauerkraut With Caraway (0.5 portions) |

## four-with-vegetarian

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.71 | 1.57 |
| dishes | 58 | 59 |
| grocery_lines_by_trip | {"None": 107} | {"None": 110} |
| purchase_total_sgd | 606.29 | 674.36 |
| staples | ["Assyrian Rice", "Indian Chapati Bread"] | ["Assyrian Rice", "Indian Restaurant Style Basmati Rice"] |

| Day / meal / role | Before | After |
|---|---|---|
| 4 / dinner / main | Japanese Mom's Tofu Stir-Fry (2.04 portions) | Spanish Tortilla (2.04 portions) |
| 4 / dinner / main-2 | Egyptian Omelet (Eggah) (2.04 portions) | Korean Barbecue Tofu (2.04 portions) |
| 4 / dinner / soup | Egyptian Edamame Stew (2.04 portions) | Gazpacho With Jalapeno And Cilantro (2.04 portions) |
| 5 / dinner / main | Chinese Style Fried Rice (4.08 portions) | Malaysian Omelette (2.04 portions) |
| 5 / dinner / main-2 | Korean Barbecue Tofu (2.04 portions) | Tarka Dhall (2.04 portions) |
| 5 / dinner / soup | Irish Potato Soup (2.04 portions) | Lentil Potato Dal (2.04 portions) |
| 5 / dinner / staple | — | Indian Restaurant Style Basmati Rice (4.08 portions) |
| 5 / dinner / vegetable | Sauerkraut With Caraway (2.04 portions) | Singapore Cucumber Salad (2.04 portions) |
| 6 / dinner / main | Daal Curry (2.04 portions) | Waffled Falafel (2.04 portions) |
| 6 / dinner / main-2 | Quiche With Self-Forming Crust (2.04 portions) | Egyptian Omelet (Eggah) (2.04 portions) |
| 6 / dinner / soup | Cheese And Corn Chowder (2.04 portions) | Egyptian Edamame Stew (2.04 portions) |
| 6 / dinner / staple | Indian Chapati Bread (4.08 portions) | Assyrian Rice (4.08 portions) |
| 6 / dinner / vegetable | Thai Sweet-Garlicky Cauliflower With Red Pepper Strips (2.04 portions) | Thai Sweet And Sour Fresh Cucumber (2.04 portions) |
| 7 / dinner / main | Chinese Fried Rice (4.89 portions) | Chinese Style Fried Rice (4.89 portions) |
| 7 / dinner / main-2 | Korean Barbecue Tofu (2.445 portions) | Teriyaki Tofu (2.445 portions) |

## six-tight-budget

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|

| Day / meal / role | Before | After |
|---|---|---|

## two-no-oven-ten-days

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 1.4 | 1.3 |
| dishes | 76 | 77 |
| grocery_lines_by_trip | {"1": 89, "2": 60} | {"1": 86, "2": 57} |
| purchase_total_sgd | 705.74 | 719.21 |
| staples | ["Assyrian Rice", "Super Easy Naan Bread"] | ["Assyrian Rice", "Ramen With Peas And Parmesan", "Super Easy Naan Bread"] |

| Day / meal / role | Before | After |
|---|---|---|
| 2 / lunch / main | Scallops Portuguese (1.5 portions) | Primary Taco Meat (1.5 portions) |
| 5 / dinner / main | Easy Slow Cooker Sweet And Sour Pork Chops (1.5 portions) | Steamed Chicken Curry With Kabocha (1.5 portions) |
| 5 / dinner / soup | Martha's Gazpacho (1.0 portions) | Instant Pot Curry Ginger Squash Soup (1.0 portions) |
| 5 / dinner / vegetable | Cuban Cucumber Salad (1.0 portions) | Jim's Raita (1.0 portions) |
| 5 / lunch / main | Kung Pao Pork (1.5 portions) | Stir-Fry Cashew Chicken (1.5 portions) |
| 6 / dinner / vegetable | Easy, Dynamite Cauliflower Curry (1.0 portions) | Cuban Cucumber Salad (1.0 portions) |
| 6 / lunch / main | Korean Krunch Quesadilla (2.0 portions) | Greek Grilled Cheese (2.0 portions) |
| 7 / dinner / soup | Chinese Egg Flower Soup (1.0 portions) | Martha's Gazpacho (1.0 portions) |
| 7 / lunch / main | Primary Taco Meat (1.5 portions) | Vietnamese Garlic Beef (1.5 portions) |
| 8 / dinner / main | Easy Teriyaki Chops (1.5 portions) | Bibimbap (2.0 portions) |
| 8 / dinner / staple | Assyrian Rice (2.0 portions) | — |
| 8 / lunch / main | Ramen With A Twist (2.0 portions) | Teriyaki Sirloin Strips (1.5 portions) |
| 8 / lunch / staple | — | Assyrian Rice (2.0 portions) |
| 9 / lunch / main | Marinated Velveted Chicken For Stir-Fry (1.5 portions) | Microwaved Parmesan Chicken (1.5 portions) |
| 9 / lunch / staple | Super Easy Naan Bread (2.0 portions) | Assyrian Rice (2.0 portions) |
| 10 / dinner / main | Japanese Ginger Pork (Shogayaki) (1.5 portions) | Marinated Velveted Chicken For Stir-Fry (1.5 portions) |
| 10 / dinner / soup | Vietnamese Beef And Spinach Soup (1.0 portions) | Chinese Egg Drop Soup (1.0 portions) |
| 10 / dinner / staple | Assyrian Rice (2.0 portions) | Ramen With Peas And Parmesan (2.0 portions) |
| 10 / dinner / vegetable | Korean Bean Sprouts (1.0 portions) | Kimchi (1.0 portions) |
| 10 / lunch / main | Indonesian Fried Rice (2.0 portions) | Scallops Portuguese (1.5 portions) |
| 10 / lunch / staple | — | Assyrian Rice (2.0 portions) |

## seven-with-young-children

Checks: PASS → PASS.

| Changed metric | Before | After |
|---|---|---|
| cuisine_groups_per_meal | 2.21 | 2.14 |
| distinct_dishes_excluding_staples | 53 | 54 |
| grocery_lines_by_trip | {"None": 109} | {"None": 111} |
| purchase_total_sgd | 689.56 | 708.28 |

| Day / meal / role | Before | After |
|---|---|---|
| 3 / dinner / main | Pizza Cheesy Chicken (1.912 portions) | Thai-Style Omelet (Khai Jiao) (1.912 portions) |
| 3 / dinner / main-3 | Thai-Style Omelet (Khai Jiao) (1.912 portions) | Steamed Thai Mussels (1.912 portions) |
| 4 / dinner / main-3 | Hoisin Eggplant Chicken (1.912 portions) | Japanese Ginger Pork (Shogayaki) (1.912 portions) |
| 5 / dinner / main-3 | Microwaved Parmesan Chicken (2.39 portions) | Slow Cooker Chicken Tikka Masala (Weight Watchers) (2.39 portions) |
| 7 / dinner / main-3 | Korean Barbecued Beef (1.912 portions) | Miso Beef (1.912 portions) |
