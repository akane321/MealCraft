# Same-request developer demo: rule and basket changes

Source revisions, request, checks, meal choices and package lines are in demo-cost-comparison.json. These are fresh replays, not merely archived reports. No timing artifacts were produced.

| Condition | Checkout S$ | Dishes | Distinct non-staples |
|---|---:|---:|---:|
| main | 527.27 | 55 | 47 |
| round1 | 660.99 | 56 | 48 |
| round2 | 507.92 | 56 | 46 |

## main → round1

Checkout change: S$+133.72. All ingredient deltas sum to this exact change.

### Largest whole-package basket changes

| Ingredient | Before | After | Delta |
|---|---:|---:|---:|
| beef | 13.49 | 38.40 | +24.91 |
| feta | 16.24 | 40.60 | +24.36 |
| cooking_spray | 0.00 | 15.00 | +15.00 |
| parmesan | 7.95 | 22.10 | +14.15 |
| broccoli | 2.90 | 14.50 | +11.60 |
| jalapeno | 0.00 | 10.98 | +10.98 |
| white_wine | 0.00 | 9.00 | +9.00 |
| tomato | 11.52 | 20.16 | +8.64 |
| pork | 8.00 | 0.00 | -8.00 |
| sake | 0.00 | 8.00 | +8.00 |
| miso | 0.00 | 7.47 | +7.47 |
| cheddar | 14.16 | 7.08 | -7.08 |

### First-round seasoning admissions actually selected as vegetables

None.

### Changed meal slots (before → after)

- 1 / breakfast / main: Easy 5 – Minute Nutella Champorado (Filipino-Style) → Banana Couscous.
- 1 / dinner / main: Japanese Ginger Pork (Shogayaki) → Marinated Velveted Chicken For Stir-Fry.
- 1 / dinner / main-2: Teriyaki Tofu → Chinese Salt And Pepper Tofu.
- 1 / dinner / vegetable: Korean Bean Sprout Salad → Italian-Style Lima Beans.
- 1 / lunch / main: Chinese Fried Rice → Teriyaki Edamame.
- 1 / lunch / staple: empty → Assyrian Rice.
- 2 / breakfast / main: Sunrise Taco → Easy 5 – Minute Nutella Champorado (Filipino-Style).
- 2 / dinner / main-2: Tofu Omelet Indonesia → Black Bean Garlic Edamame.
- 2 / dinner / soup: Gazpacho (Spanish Cold Soup) → Hearty Potato Soup.
- 2 / dinner / vegetable: Grilled Parmesan Tomatoes → Green Bean And Red Bell Pepper Stir-Fry.
- 2 / lunch / main: Ramen With A Twist → Lemon And Feta Pasta.
- 2 / lunch / vegetable: Ramen Noodle Salad (Serve Lots) → Fresh Pesto And Tomato Salad.
- 3 / breakfast / main: Kittencal's Greek Feta And Olive Omelette → Sunrise Taco.
- 3 / dinner / main: Thai-Style Omelet (Khai Jiao) → Miso Beef.
- 3 / dinner / main-2: Teriyaki Tofu → Teriyaki Grilled Tofu.
- 3 / dinner / soup: Nilaga (Filipino Chicken Stew) → Iranian Yogurt Soup.
- 3 / dinner / vegetable: Jim's Raita → Korean Bean Sprout Salad.
- 3 / lunch / main: Tofu Egg Foo Young → Simple Fried Rice.
- 3 / lunch / staple: Ramen With Peas And Parmesan → empty.
- 3 / lunch / vegetable: Spinach Stir Fry With Garlic → Sweet And Sour Cucumbers.
- 4 / dinner / main: Fried Rice → Easy Keto Korean Beef With Cauli Rice.
- 4 / dinner / main-2: Anitas Lemon Chicken → Marinated Teriyaki Tofu.
- 4 / dinner / soup: Tomato Dumplings → Gazpacho (Spanish Cold Soup).
- 4 / dinner / staple: empty → Assyrian Rice.
- 4 / lunch / main: Vegetable Stir Fry → Scrambled Egg And Noodle Stir-Fry.
- 4 / lunch / staple: Assyrian Rice → empty.
- 4 / lunch / vegetable: Spicy Sweet And Sour Cabbage → Jim's Raita.
- 5 / dinner / main: Mexican Couscous → Thai-Style Omelet (Khai Jiao).
- 5 / dinner / main-2: Korean Barbecue Tofu → Vegetable Stir Fry.
- 5 / dinner / staple: empty → Assyrian Rice.
- 5 / dinner / vegetable: Broccoli Salad → Grilled Parmesan Tomatoes.
- 5 / lunch / main: Quick And Easy Mexican Pizza → Mediterranean Pizza.
- 5 / lunch / vegetable: Fresh Pesto And Tomato Salad → Broccoli Salad.
- 6 / dinner / main: Teriyaki Fried Rice → Shredded Beef For Tacos Or Burritos.
- 6 / dinner / main-2: Korean Barbeque Beef (Bea Wright) → Teriyaki Tofu.
- 6 / dinner / soup: Iranian Yogurt Soup → Hungarian Potato Soup.
- 6 / dinner / staple: empty → Assyrian Rice.
- 6 / dinner / vegetable: Raw Cauliflower Korma → Sliced Cabbage Kimchi.
- 6 / lunch / main: Baked Veggie Quesadillas → Pad Thai (Vegan).
- 6 / lunch / vegetable: Cuban Corn On The Cob → Cuban Cucumber Salad.
- 7 / dinner / main: Pizza Chicken Melts → Teriyaki Fried Rice.
- 7 / dinner / main-2: Egyptian Omelet (Eggah) → Korean Beef Patties.
- 7 / dinner / staple: Assyrian Rice → empty.
- 7 / dinner / vegetable: Taj Tabbouleh → Zucchini Couscous.
- 7 / lunch / main: Spicy Nasi Goreng → Pasta Primavera.
- 7 / lunch / vegetable: Cuban Cucumber Salad → Lou's German Slaw.

## round1 → round2

Checkout change: S$-153.07. All ingredient deltas sum to this exact change.

### Largest whole-package basket changes

| Ingredient | Before | After | Delta |
|---|---:|---:|---:|
| beef | 38.40 | 13.49 | -24.91 |
| feta | 40.60 | 21.50 | -19.10 |
| cooking_spray | 15.00 | 0.00 | -15.00 |
| parmesan | 22.10 | 7.95 | -14.15 |
| jalapeno | 10.98 | 0.00 | -10.98 |
| white_wine | 9.00 | 0.00 | -9.00 |
| broccoli | 14.50 | 5.80 | -8.70 |
| sake | 8.00 | 0.00 | -8.00 |
| chicken_breast | 7.90 | 15.80 | +7.90 |
| miso | 7.47 | 0.00 | -7.47 |
| cheddar | 7.08 | 14.16 | +7.08 |
| sun_dried_tomato | 6.95 | 0.00 | -6.95 |

### First-round seasoning admissions actually selected as vegetables

None.

### Changed meal slots (before → after)

- 1 / dinner / main: Marinated Velveted Chicken For Stir-Fry → Microwaved Parmesan Chicken.
- 1 / dinner / main-2: Chinese Salt And Pepper Tofu → Vegetable Stir Fry.
- 1 / dinner / soup: Quick gazpacho → Gazpacho (Spanish Cold Soup).
- 1 / dinner / vegetable: Italian-Style Lima Beans → Chimichurri Broccoli.
- 1 / lunch / main: Teriyaki Edamame → Chinese Salt And Pepper Tofu.
- 1 / lunch / vegetable: Korean Coleslaw → Spinach Stir Fry With Garlic.
- 2 / dinner / main-2: Black Bean Garlic Edamame → Tofu Egg Foo Young.
- 2 / dinner / vegetable: Green Bean And Red Bell Pepper Stir-Fry → Elote (Mexican Corn On The Cob).
- 3 / dinner / main: Miso Beef → Primary Taco Meat.
- 3 / dinner / vegetable: Korean Bean Sprout Salad → Grilled Parmesan Tomatoes.
- 3 / lunch / main: Simple Fried Rice → Korean Barbecue Tofu.
- 3 / lunch / staple: empty → Assyrian Rice.
- 3 / lunch / vegetable: Sweet And Sour Cucumbers → Korean Bean Sprout Salad.
- 4 / dinner / main: Easy Keto Korean Beef With Cauli Rice → Fried Rice.
- 4 / dinner / main-2: Marinated Teriyaki Tofu → Anitas Lemon Chicken.
- 4 / dinner / soup: Gazpacho (Spanish Cold Soup) → Tomato Dumplings.
- 4 / dinner / staple: Assyrian Rice → empty.
- 4 / lunch / main: Scrambled Egg And Noodle Stir-Fry → Vegetable Stir Fry.
- 4 / lunch / staple: empty → Assyrian Rice.
- 4 / lunch / vegetable: Jim's Raita → Spicy Sweet And Sour Cabbage.
- 5 / dinner / main: Thai-Style Omelet (Khai Jiao) → Mexican Chicken (Low-Fat).
- 5 / dinner / main-2: Vegetable Stir Fry → Chinese Salt And Pepper Tofu.
- 5 / dinner / soup: Cheese And Corn Chowder → Quick gazpacho.
- 5 / dinner / vegetable: Grilled Parmesan Tomatoes → Broccoli Salad.
- 5 / lunch / main: Mediterranean Pizza → Quick And Easy Mexican Pizza.
- 5 / lunch / vegetable: Broccoli Salad → Cuban Cucumber Salad.
- 6 / dinner / main: Shredded Beef For Tacos Or Burritos → Teriyaki Fried Rice.
- 6 / dinner / main-2: Teriyaki Tofu → Instant Pot Korean Beef.
- 6 / dinner / staple: Assyrian Rice → empty.
- 6 / dinner / vegetable: Sliced Cabbage Kimchi → Raw Cauliflower Korma.
- 6 / lunch / main: Pad Thai (Vegan) → Baked Veggie Quesadillas.
- 6 / lunch / vegetable: Cuban Cucumber Salad → Cuban Corn On The Cob.
- 7 / dinner / main: Teriyaki Fried Rice → Quick Chinese Fried Rice.
- 7 / dinner / main-2: Korean Beef Patties → Chinese Salt And Pepper Tofu.
- 7 / dinner / soup: Iranian Yogurt Soup → Venezuelan Black Bean Soup.
- 7 / dinner / vegetable: Zucchini Couscous → Vegetable Stir-Fry.
- 7 / lunch / main: Pasta Primavera → Spicy Nasi Goreng.
- 7 / lunch / vegetable: Lou's German Slaw → Jim's Raita.

## main → round2

Checkout change: S$-19.35. All ingredient deltas sum to this exact change.

### Largest whole-package basket changes

| Ingredient | Before | After | Delta |
|---|---:|---:|---:|
| ramen | 11.00 | 0.00 | -11.00 |
| tomato | 11.52 | 20.16 | +8.64 |
| pork | 8.00 | 0.00 | -8.00 |
| sunflower_seed | 6.90 | 0.00 | -6.90 |
| cheese | 6.81 | 0.00 | -6.81 |
| croutons | 0.00 | 5.90 | +5.90 |
| chicken | 5.80 | 0.00 | -5.80 |
| egg | 17.10 | 11.40 | -5.70 |
| feta | 16.24 | 21.50 | +5.26 |
| almond | 4.89 | 0.00 | -4.89 |
| avocado | 4.80 | 0.00 | -4.80 |
| cinnamon | 0.00 | 4.50 | +4.50 |

### First-round seasoning admissions actually selected as vegetables

None.

### Changed meal slots (before → after)

- 1 / breakfast / main: Easy 5 – Minute Nutella Champorado (Filipino-Style) → Banana Couscous.
- 1 / dinner / main: Japanese Ginger Pork (Shogayaki) → Microwaved Parmesan Chicken.
- 1 / dinner / main-2: Teriyaki Tofu → Vegetable Stir Fry.
- 1 / dinner / soup: Quick gazpacho → Gazpacho (Spanish Cold Soup).
- 1 / dinner / vegetable: Korean Bean Sprout Salad → Chimichurri Broccoli.
- 1 / lunch / main: Chinese Fried Rice → Chinese Salt And Pepper Tofu.
- 1 / lunch / staple: empty → Assyrian Rice.
- 1 / lunch / vegetable: Korean Coleslaw → Spinach Stir Fry With Garlic.
- 2 / breakfast / main: Sunrise Taco → Easy 5 – Minute Nutella Champorado (Filipino-Style).
- 2 / dinner / main-2: Tofu Omelet Indonesia → Tofu Egg Foo Young.
- 2 / dinner / soup: Gazpacho (Spanish Cold Soup) → Hearty Potato Soup.
- 2 / dinner / vegetable: Grilled Parmesan Tomatoes → Elote (Mexican Corn On The Cob).
- 2 / lunch / main: Ramen With A Twist → Lemon And Feta Pasta.
- 2 / lunch / vegetable: Ramen Noodle Salad (Serve Lots) → Fresh Pesto And Tomato Salad.
- 3 / breakfast / main: Kittencal's Greek Feta And Olive Omelette → Sunrise Taco.
- 3 / dinner / main: Thai-Style Omelet (Khai Jiao) → Primary Taco Meat.
- 3 / dinner / main-2: Teriyaki Tofu → Teriyaki Grilled Tofu.
- 3 / dinner / soup: Nilaga (Filipino Chicken Stew) → Iranian Yogurt Soup.
- 3 / dinner / vegetable: Jim's Raita → Grilled Parmesan Tomatoes.
- 3 / lunch / main: Tofu Egg Foo Young → Korean Barbecue Tofu.
- 3 / lunch / staple: Ramen With Peas And Parmesan → Assyrian Rice.
- 3 / lunch / vegetable: Spinach Stir Fry With Garlic → Korean Bean Sprout Salad.
- 5 / dinner / main: Mexican Couscous → Mexican Chicken (Low-Fat).
- 5 / dinner / main-2: Korean Barbecue Tofu → Chinese Salt And Pepper Tofu.
- 5 / dinner / soup: Cheese And Corn Chowder → Quick gazpacho.
- 5 / dinner / staple: empty → Assyrian Rice.
- 5 / lunch / vegetable: Fresh Pesto And Tomato Salad → Cuban Cucumber Salad.
- 6 / dinner / main-2: Korean Barbeque Beef (Bea Wright) → Instant Pot Korean Beef.
- 6 / dinner / soup: Iranian Yogurt Soup → Hungarian Potato Soup.
- 7 / dinner / main: Pizza Chicken Melts → Quick Chinese Fried Rice.
- 7 / dinner / main-2: Egyptian Omelet (Eggah) → Chinese Salt And Pepper Tofu.
- 7 / dinner / soup: Iranian Yogurt Soup → Venezuelan Black Bean Soup.
- 7 / dinner / staple: Assyrian Rice → empty.
- 7 / dinner / vegetable: Taj Tabbouleh → Vegetable Stir-Fry.
- 7 / lunch / vegetable: Cuban Cucumber Salad → Jim's Raita.

Fresh same-environment replays; all member checks pass. Fixed snapshot prices. Candidate/role changes alter the whole week's search and package basket, not just vegetable line costs. No timing claim, protected cases or new capability comparison.

Do not sum per-dish purchase estimates: shared ingredients and whole packages are priced at basket level. The two revisions also change staple/protein-side roles; these joint changes cannot be attributed solely to the flesh percentage without a separate ablation.
