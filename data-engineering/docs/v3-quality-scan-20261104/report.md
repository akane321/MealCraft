# Data release v3: quality scan

18,335 recipes (v2.2 8,968, over-quota 1,867, new 7,500); 14,739 pattern hits on 9,484 recipes. `new` is wave 1 plus wave 2; `over-quota` is the built-but-over-quota v2.1 leg (see README).

## Caveats

- Counts are pattern matches, not defect rates. A recipe can match and still be correct, and a wrong recipe can match nothing.
- The trivial patterns P1b (salt), P1c (pepper), P1d (greasing fat) and P4c (juice or zest at whole-fruit weight) are not defects by themselves: the missing amount is tiny. Benign water (P1a2 cooking-medium water, P1f2 ice bath) is not a defect either. P8c (oven, no time) often has a doneness cue instead. That is why the core union leaves them out.
- Precision was only eyeballed on small samples by one reader when the rules were written; this tool does not measure it.
- In an earlier comparison against the human manual check (PR #421) about 30% of the recipes humans called correct were also hit, mostly by water, serve-with and greasing patterns. That comparison was made outside this tool and is not recomputed here.
- Hits are a worklist, not a verdict: read the evidence before changing a recipe.
- The planning-pool gates (price, completeness, meal role) need the backend and are not computed here, so there is no plannable column.

## Unions

| recipes hit by | all | share | v2.2 | over-quota | new |
|---|---:|---:|---:|---:|---:|
| any high-precision pattern (HP) | 4,771 | 26.0% | 2,434 (27.1%) | 348 (18.6%) | 1,989 (26.5%) |
| core (HP without salt, pepper, greasing fat, juice/zest, oven-no-time) | 2,824 | 15.4% | 1,459 (16.3%) | 154 (8.2%) | 1,211 (16.1%) |
| completeness (P1, P2, P3 in HP) | 3,261 | 17.8% | 1,826 (20.4%) | 227 (12.2%) | 1,208 (16.1%) |
| portion and nutrition (P4, P5, P6 in HP) | 1,143 | 6.2% | 422 (4.7%) | 53 (2.8%) | 668 (8.9%) |
| steps (P7b, P8 in HP) | 668 | 3.6% | 325 (3.6%) | 81 (4.3%) | 262 (3.5%) |

## Patterns

HP = in the high-precision list; core = HP without the trivial patterns; info = not in HP.

| pattern | tier | all | share | v2.2 | over-quota | new | share v2.2 | share new |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| P1a_water_quantified | core | 474 | 2.6% | 227 | 27 | 220 | 2.5% | 2.9% |
| P1a3_water_added_no_amount | info | 463 | 2.5% | 249 | 39 | 175 | 2.8% | 2.3% |
| P1a2_water_cooking_medium | info | 783 | 4.3% | 374 | 68 | 341 | 4.2% | 4.5% |
| P1b_salt | HP | 656 | 3.6% | 378 | 52 | 226 | 4.2% | 3.0% |
| P1c_pepper | HP | 494 | 2.7% | 291 | 34 | 169 | 3.2% | 2.3% |
| P1d_fat_greasing | HP | 975 | 5.3% | 488 | 115 | 372 | 5.4% | 5.0% |
| P1e_fat_frying_or_adding | core | 129 | 0.7% | 79 | 13 | 37 | 0.9% | 0.5% |
| P1f_ice_in_drink_or_dish | info | 54 | 0.3% | 19 | 13 | 22 | 0.2% | 0.3% |
| P1f2_ice_bath_or_cooling | info | 78 | 0.4% | 36 | 9 | 33 | 0.4% | 0.4% |
| P1g_sugar_dusting | info | 15 | 0.1% | 8 | 3 | 4 | 0.1% | 0.1% |
| P2_serve_carrier_not_listed | core | 1,057 | 5.8% | 679 | 22 | 356 | 7.6% | 4.7% |
| P3_named_subrecipe_not_listed | core | 93 | 0.5% | 52 | 3 | 38 | 0.6% | 0.5% |
| P4a_mini_item_whole_weight | core | 89 | 0.5% | 40 | 2 | 47 | 0.4% | 0.6% |
| P4b_fruit_slices_wedges_whole_weight | core | 60 | 0.3% | 30 | 0 | 30 | 0.3% | 0.4% |
| P4c_juice_zest_whole_fruit_weight | HP | 478 | 2.6% | 192 | 22 | 264 | 2.1% | 3.5% |
| P4d_small_large_ignored_LOW | info | 3,982 | 21.7% | 1,865 | 337 | 1,780 | 20.8% | 23.7% |
| P4e_small_chili_standard_weight | core | 238 | 1.3% | 94 | 13 | 131 | 1.0% | 1.7% |
| P4f_parenthetical_weight_ignored | core | 181 | 1.0% | 32 | 3 | 146 | 0.4% | 1.9% |
| P5a_cooked_item_dry_form | core | 50 | 0.3% | 11 | 0 | 39 | 0.1% | 0.5% |
| P5a2_cooked_after_noun_ambiguous | info | 16 | 0.1% | 8 | 0 | 8 | 0.1% | 0.1% |
| P5b_liquid_bouillon_as_cube | core | 36 | 0.2% | 22 | 0 | 14 | 0.2% | 0.2% |
| P6_energy_outlier | info | 274 | 1.5% | 108 | 30 | 136 | 1.2% | 1.8% |
| P6h_energy_outlier_hard_1.5x | core | 73 | 0.4% | 23 | 13 | 37 | 0.3% | 0.5% |
| P7_ingredient_never_in_steps | info | 788 | 4.3% | 403 | 68 | 317 | 4.5% | 4.2% |
| P7b_two_or_more_unused | core | 379 | 2.1% | 196 | 39 | 144 | 2.2% | 1.9% |
| P7c_major_ingredient_unused_50g | info | 610 | 3.3% | 303 | 56 | 251 | 3.4% | 3.3% |
| P8a_oven_without_temperature | core | 124 | 0.7% | 57 | 19 | 48 | 0.6% | 0.6% |
| P8b_fewer_than_2_steps | info | 1,321 | 7.2% | 619 | 175 | 527 | 6.9% | 7.0% |
| P8b2_single_short_step_lt200ch | info | 544 | 3.0% | 258 | 87 | 199 | 2.9% | 2.7% |
| P8c_oven_without_any_time | HP | 139 | 0.8% | 55 | 25 | 59 | 0.6% | 0.8% |
| P8d_truncated_steps | info | 11 | 0.1% | 6 | 0 | 5 | 0.1% | 0.1% |
| P8e_steps_point_elsewhere | core | 41 | 0.2% | 23 | 3 | 15 | 0.3% | 0.2% |
| P8f_no_cooking_verb_in_steps | core | 34 | 0.2% | 16 | 1 | 17 | 0.2% | 0.2% |

## Rules and examples

Five examples per pattern, picked with a fixed shuffle (seed 11).

### P1a_water_quantified (n=474)

Rule: Steps add a measured amount of water ("2 cups water"); no ingredient line is water, ice or milk-or-water. Sentences about steaming, baths, soaking, blanching, reserved liquid or covering with water are skipped.

- RCP2_A9BD8C7E9EE2 Korean Sirloin [v2.2]: Add 2 tbsp of water to the marinade in the saucepan and heat to boiling over high heat, boil for 2 minutes.
- RCP2_EED869B310B2 Chicken And Cucumbers [wave2]: Add 1 tablespoon water to chicken;
- RCP2_671566FE300C Company Cabbage [v2.2]: Add cabbage, garlic and 1/4 cup water.
- RCP2_0EE1A2A5EBC5 Bulgur Wheat Pilaf [wave2]: Add salt and 4 cups water and bring it to a boil.
- RCP2_179279DFBA6C Pork And Cashew Stir Fry [wave2]: Add the asparagus, beans and 1 tbsp water.

### P1a3_water_added_no_amount (n=463)

Rule: Steps say add/pour/stir in/cover with water with no amount; no water line, and not P1a.

- RCP2_23CB69E7B264 Vietnamese Cucumber Salad [v2.2]: ally. Add the cucumbers and red onion to the bowl and mix thoroughly. Add enough water to the bowl to submerge the cucumbers and place the bowl in the refri
- RCP2_4C80A7E78574 Ajiaco Or Colombian Chicken Soup [v2.2]: hicken. Place the chicken and the neck in a large, 8 quart stock pot. Cover the chicken with cool water, leaving about an inch or two of space at the top of the pot. Place t
- RCP2_BC9A3530C9B3 Jamaican Curry Chicken [v2.2]: t until the oil is hot. Reduce flame/heat and add chicken to hot oil. add enough water to cover chicken. Add diced potatoes and remaining ingredients, then
- RCP2_E87B837004CE Curried Red Lentils [wave2]: saucepan and simmer until the lentils are tender (about 30 minutes). Add water if necessary. While the lentils are cooking, caramelize the onions in
- RCP2_D684C70386F8 Easy Lemon Risotto With Peas [wave2]: immer for 15 minutes. Stir in frozen peas. If the rice is drying out, add a little water. Cover and return to low heat for 5 more minutes or until all of the

### P1a2_water_cooking_medium (n=783)

Rule: Only cooking-medium water (boiling or salted water, a pot of water, bring to a boil, in water); no water line. Benign.

- RCP2_7F42F6BC6527 Chorizo Pasta Bake [wave2]: han simmer for 30 minutes. Meanwhile, cook pasta in plenty of boiling salted water. Drain pasta. Add sauce to pasta and mix together well. Place in oven
- RCP2_2A86FA8BECC3 Ecuadorean Ceviche [wave1]: e juice from the lemons on the onions and set aside. Simmer shrimp in boiling water for 2 minutes. Reserve 1 cup of the liquid. Mix everything together,
- RCP2_C2B8F0E0DAF0 American Goulash(Kids Love This!) [wave1]: Brown ground beef (with onion if desired) in 9-inch skillet. Bring 6 cups of water to a boil in large pan. Boil macaroni until done; drain. Add corn to
- RCP2_AA57A3B53444 Japanese Style Sesame Beans And Carrot [wave2]: es. Remove the edges of the beans and blanch both carrot and beans in boiling water Roast sesame seeds in a heavy skillet till they turn brown. In a medi
- RCP2_D38784CF402A Never Fail Broccoli Souffle [overquota]: serole at 350 degrees for 30 minutes. You may wish to place dish in a pan of water while baking. Serves 4.

### P1b_salt (n=656)

Rule: Steps mention salt (not salt pork, salt cod, salt substitute); no salt line.

- RCP2_C92ED1E16745 Grilled Pork Chops With Chili Jam [wave2]: shed garlic, then brush with extra virgin olive oil. Season well with salt. Grill for 7 mins each side, or until browned and cooked to desired d
- RCP2_F406FB8CE7C8 Halibut With Capers, Tomatoes, And Olives! [wave2]: Season fish with salt and pepper and dredge in flour. Heat 2 tablespoons of olive oil in a
- RCP2_4A5334485BBE Braised Pork Chops [v2.2]: l tender. Add wine and bring to a boil. Pour over chops seasoned with salt and pepper. Cover. Braise in 300° oven 1 1/2 hours or until tender. R
- RCP2_DAD3E6E14609 Prawn Ceviche [overquota]: getables. Pour in the remaining lime juice marinade. Add cilantro and salt and pepper to taste. Toss gently to mix. Serve with tortilla chips, o
- RCP2_CEB8DF30D544 Fettuccine Alfredo [v2.2]: according to package instructions in a large pot of boiling water and salt. Add heavy cream and butter to a large skillet over medium heat until

### P1c_pepper (n=494)

Rule: Steps season with pepper (salt and pepper, black/white/ground pepper, pepper to taste, a tsp of pepper); no pepper line. Chili, bell and red pepper phrases are skipped.

- RCP2_65CCC1039509 Grilled aubergines with spicy chickpeas & wal [v2.2]: tbsp water, bring to the boil, then simmer for 10 mins. Add a little salt and pepper and the lemon juice. Arrange the aubergines over a grill pan. Brush l
- RCP2_27A686F0D947 Mediterranean Chicken & Chickpeas [wave2]: Season chicken with salt and pepper and brown on both sides in 3-5 tablespoons oil. Remove to plate. Add
- RCP2_48BBA2C697D2 Clam chowder [overquota]: s, if you've gone down that route, and simmer for a minute to reheat. Season with plenty of black pepper and a little salt, if needed, then stir through the parsley just befo
- RCP2_3B6140640DD4 Simple Italian Potato Pie [v2.2]: rown ground beef in skillet. Drain off excess fat. Place ground beef, seasoned with salt and pepper if desired, in bottom of shallow baking dish. Cook 2 cup mashed potat
- RCP2_8DFB11349C27 Ratatouille [v2.2]: matoes and half the basil. Return the vegetables to the pan with some salt and pepper and cook for 5 mins. Serve with basil.

### P1d_fat_greasing (n=975)

Rule: Steps grease, oil, butter or spray a pan, dish, sheet, rack or mold, use cooking spray, or brush with oil/butter; no fat or oil line (peanut butter, buttermilk etc. do not count as fat).

- RCP2_72B1F575F56B Sesame Pork Kabobs [v2.2]: ng metal or soaked wooden skewers, thread beef. Grill, covered, on an oiled rack over medium heat or broil 4 in. from the heat for 9-12 minutes or unt
- RCP2_C25D9C4D878B Yorkshire Pudding [v2.2]: 0°. Combine eggs and milk in bowl. Stir in flour; mix well. Pour into greased 8 inch square pan. Bake for 30 minutes. Yield: 4 to 6 serving.
- RCP2_529669CC5794 Easy Italian Lasagna [wave1]: nd green pepper. Put half of the lasagna noodles in a 13 x 9 x 2-inch buttered baking dish. Moisten lasagna with some meat sauce. Cover with cheese mixture; top
- RCP2_462AEC52EEBD Aebleskiver Poffertjes [wave2]: ewhat risen. Stir down batter and heat an aebleskiver pan. Spray with non-stick spray or melt margarine or butter in the indentations. Fill the indentation
- RCP2_C4A604BEDB59 Italian Spaghetti(Feeds 15) [wave2]: Put butter in pan. Brown meat until it falls apart. Add onions and peppers. Cook and ad

### P1e_fat_frying_or_adding (n=129)

Rule: Steps fry, saute or brown in, heat or melt oil, butter, margarine or fat; no fat line; not P1d.

- RCP2_F3829D4EDE4F Nem [overquota]: ped air which could explode when cooked. 5. After all nem are rolled, fry in hot oil (200-250 degrees fahrenheit), a first time for 3-5 minutes to fully h
- RCP2_2ED8F6E7C143 Tempura Vegetables [v2.2]: s together until smooth. Dip vegetables in tempura batter and cook in hot oil until brown.
- RCP2_945A8E29DD66 Tacos [v2.2]: Drop tortillas in hot oil, one at a time. After a few seconds, turn, fold in half and fry to de
- RCP2_B4564BDBA899 Danish Meat Balls [wave2]: onion, eggs and milk; mix well. Shape into 3/4 to 1-inch meat balls. Fry in butter or margarine. This may be made into a meat loaf. Bake at 370° until i
- RCP2_07ECA0FA8FEB Beer Batter For Tempura [v2.2]: . Pour mixture over food and chill for one hour. Remove when ready to fry and drop one at a time in hot oil until golden brown.

### P1f_ice_in_drink_or_dish (n=54)

Rule: Steps use ice (not ice cream, ice pop, ice cube tray) outside a bath or cooling context; no ice line.

- RCP2_3868C6C86E10 Fasoliyyeh Bi Z-Zayt (Syrian Green Beans with [v2.2]: to saute them, but to let them steam in the moisture released by the ice crystals. Add cilantro and garlic to the beans, and continue to cook
- RCP2_CDD0C9FFC827 Banana Nog [overquota]: Put all ingredients, except nutmeg, into blender with 1 cup ice cubes. Whip 30 seconds. Pour into tall glasses. Dust with nutmeg. Ser
- RCP2_854830291A29 Cafe Cubano Latte (Homemade Liquid Coffee Cre [wave2]: nk a lot of coffee in your house or if you have company. Or freeze in ice cube containers for individual use.
- RCP2_617CEF5625D0 My Mom'S Jamaican Style Carrot Juice [wave2]: mediately. The juice may need to be shaken before pouring. Serve over ice.
- RCP2_3FC3BF42BCF9 Persian Mint & Cucumber Cooler (Sekanjabin) [v2.2]: re water to dilute to your taste preference. The drink is best served ice cold. Serve the syrup with crispy lettuce leaves like Romaine hearts

### P1f2_ice_bath_or_cooling (n=78)

Rule: Same as P1f but the nearby words say bath, plunge, shock, cool or chill. Benign.

- RCP2_FC482062FEE3 Ayran (Turkish Yogurt Drink) [overquota]: salt and dried mint. Chill thoroughly and serve in tall glasses, with ice.
- RCP2_B9F8E3FCB0DB Chinese Green Beans [v2.2]: he beans for 4 minutes in hot water. Immediately immerse into bowl of ice water to stop cooking and retain bright color. Remove and pat dry. In
- RCP2_63596E6C5E2E Homemade Greek Yogurt [v2.2]: , stirring regularly, about 5 minutes. Fill a large bowl halfway with ice and water. Place a smaller, sterilized bowl over the ice bath for the
- RCP2_4A44C90AFAA7 City Ceviche [wave2]: t 1 minute. Use a slotted spoon to transfer the scallops to a bowl of ice water to stop the cooking process. Return the water to a boil and poa
- RCP2_CE3D69A2FFE6 Egg And Tomato Gratin [wave1]: l, then simmer the eggs very gently for 10 minutes. Drain and cool in ice water for at least 15 minutes, or until the centers of the eggs are c

### P1g_sugar_dusting (n=15)

Rule: Steps dust, sprinkle, roll, coat, top or garnish with (powdered, granulated or brown) sugar; no matching sugar or sweetener line.

- RCP2_B023CC0BD8F1 Danish Aebleskiver [wave2]: batter. 3. Serve with powdered sugar, jam or jelly, or syrup. Can be rolled in powdered sugar and served. Jam or Jelly can be dropped in the center of uncooked Aeb
- RCP2_58EADFB65F1E Churros Cubanos [v2.2]: hen both sides are brown. Drain on paper towels. When ready to serve, sprinkle with sugar.
- RCP2_01ADB8007DE9 Apple Empanadas [wave2]: ed butter and cinnamon. Fold and secure with toothpicks. Deep fry and sprinkle with cinnamon sugar.
- RCP2_0599E89D28E0 Anytime Crepes [v2.2]: person. (Four if you use a smaller pan.) Multiply recipe accordingly. Roll pancake with various fillings: butter, icing sugar, lemon juice / nutella and manderine orange or blueberries / sausage
- RCP2_A917AB04BFE2 Edinburgh Tearoom Scones(English Recipe) [wave2]: sheet about 1-inch apart. Brush tops of scones lightly with milk and sprinkle with sugar. Bake 10 minutes until golden brown.

### P2_serve_carrier_not_listed (n=1,057)

Rule: Steps serve over/with/on rice, pasta, pita, tortillas, bread, couscous/polenta or potatoes; no such carrier line. Skipped when the sentence marks it as optional or a suggestion (if desired, optional, can be served, good over, leftover).

- RCP2_A6E976FD6F5C Shrimp And Green Banana Curry (From The Islan [wave2]: [rice] ss or ripeness! Taste for seasoning and add salt. Serve over rice and sprinkle over chopped cilantro. Dessicated co
- RCP2_01F82740BBB9 Dinner Tonight: Palak Aalu, Palak Paneer'S Co [wave2]: [rice] k for 5 more minutes. Grate the nutmeg on top and serve with rice.
- RCP2_A1F0828B1276 Good For The Heart Chicken Curry [v2.2]: [rice] nutes or until apple pieces are tender and crisp. Serve over rice. Makes 4 to 6 servings. Calories per serving: 235
- RCP2_22A60B15676E Mandarin Chicken [v2.2]: [rice] hestnuts and ginger; cover and simmer 10 minutes. Serve with rice.
- RCP2_2F2F67E2796B Mango Pork Stir-Fry [wave2]: [rice] d reserved pork; heat through. Stir in seame oil. Serve with rice.

### P3_named_subrecipe_not_listed (n=93)

Rule: Steps serve/top/drizzle with a named sauce, salsa, gravy, dressing, chutney, pesto, glaze or frosting (or refer to a recipe for one) whose name words are in no ingredient line, mentioned once, not made in the steps.

- RCP2_D6CBB938CEA5 Falafel Patties [v2.2]: des, flipping over after a few minutes. Serve with tzatziki sauce.
- RCP2_C0C2D64F816C Miso Banana Bread With Yuzu Glaze [wave2]: and cool completely, about 30 minutes. Drizzle each loaf with Yuzu Glaze.
- RCP2_C681F2C54C49 Southern Pot Roast [v2.2]: ater. Cook in a 350° oven until tender. Serve with brown gravy. Serves 4.
- RCP2_AE0623C688C3 Beef Lumpia [wave1]: wn on all sides. Drain on paper towels. Serve with sweet and sour sauce.
- RCP2_858C515ED0E2 Brazilian Black Bean And Pork Stew [wave1]: . Season to taste with salt and pepper; serve with Brazilian Hot sauce.

### P4a_mini_item_whole_weight (n=89)

Rule: Cherry/baby/mini vegetable or fruit line whose grams equal quantity x the standard whole-piece weight.

- RCP2_ECB6AB4F57B9 Spicy Moroccan Chicken Skewers [wave1]: '12 cherry tomatoes' -> 1476.0 g = 12 x std piece 123 g (ING_TOMATO)
- RCP2_179A3C7F66C2 Zucchini, Carrot And Tomato Casserole [v2.2]: '12 to 14 cherry tomatoes' -> 1599.0 g = 13 x std piece 123 g (ING_TOMATO)
- RCP2_6C3BD613F185 Curry Rice [v2.2]: '3 to 4 baby carrots, sliced' -> 213.5 g = 3.5 x std piece 61 g (ING_CARROT)
- RCP2_8E8EC008868E Vegetable Chicken Kabobs [wave1]: '6 cherry tomatoes' -> 738.0 g = 6 x std piece 123 g (ING_TOMATO)
- RCP2_ABCBB528073A Thai Mango And Shrimp Salad [wave1]: '8 None cherry tomatoes, halved' -> 984.0 g = 8 x std piece 123 g (ING_TOMATO)

### P4b_fruit_slices_wedges_whole_weight (n=60)

Rule: Fruit slices, wedges, rounds, twists or halves line whose grams equal quantity x the standard whole-fruit weight.

- RCP2_6E6CB3E6C97B Lemon Chicken Milanese [wave2]: '8 lemon wedges' -> 800.0 g = 8 x std piece 100 g
- RCP2_8C910E0F2DDE Steamed Halibut With Sesame-Lime Sauce And Co [wave2]: '4 lime wedges' -> 268.0 g = 4 x std piece 67 g
- RCP2_69CDCFCBD166 Chile-Rubbed Steak Tacos [wave2]: '6 lime wedges' -> 402.0 g = 6 x std piece 67 g
- RCP2_BCA13FC11EB2 Blackened Tilapia Baja Tacos [v2.2]: '4 lime wedges' -> 268.0 g = 4 x std piece 67 g
- RCP2_2140990B5DEF Indian Grilled Sour Cream–Marinated Shrimp [wave1]: '4 lime wedges, for serving' -> 268.0 g = 4 x std piece 67 g

### P4c_juice_zest_whole_fruit_weight (n=478)

Rule: Lemon/lime/orange/grapefruit/tangerine line that says juice, zest or rind but whose grams equal quantity x the whole-fruit weight.

- RCP2_1271AFA48D32 Vietnamese Beef And Lettuce Curry [v2.2]: '1 lemon, juiced' -> 100.0 g = 1 x whole 100 g
- RCP2_24463443BD16 Thai Prawns And Squid Hot Soup (Tom Yum Kung  [wave1]: '1 limes, juice of (to taste) or 1 lemon, juice of (to taste)' -> 67.0 g = 1 x whole 67 g
- RCP2_F057C8391100 Chicken Mango Stir Fry [wave1]: '1 lime, juice of' -> 67.0 g = 1 x whole 67 g
- RCP2_EDFDF8B551CC Roasted Chicken Thighs With Zucchini And Feta [v2.2]: '1 lemon, zest of, finely grated' -> 100.0 g = 1 x whole 100 g
- RCP2_D805E45BC00B Lebanese Roasted Chicken [wave2]: '2 large lemons, juiced' -> 200.0 g = 2 x whole 100 g

### P4d_small_large_ignored_LOW (n=3,982)

Rule: Line says small/large/jumbo etc. but its grams equal quantity x the standard piece weight. Low impact; informational.

- RCP2_6CF5108C4FEE New England Boiled Dinner [v2.2]: '6 small onions' -> 660.0 g = std piece 110 g
- RCP2_002F78E6445D Puerto Rican Black Bean Soup [wave2]: '1 small onion, quartered' -> 110.0 g = std piece 110 g
- RCP2_5D6867B263F6 Flank Steak Stir-Fry [v2.2]: '1 small onion, thinly sliced' -> 110.0 g = std piece 110 g
- RCP2_B59AE8AFAD1A Asparagus Quiche [v2.2]: '5 large eggs' -> 250.0 g = std piece 50 g
- RCP2_3961BE6DC083 Mexican Beef Skillet [v2.2]: '1 small green bell pepper, chopped' -> 120.0 g = std piece 120 g

### P4e_small_chili_standard_weight (n=238)

Rule: Thai, bird's-eye, serrano, small or dried chili on ING_CHILI_PEPPER/ING_GREEN_CHILI at the standard piece weight (not a sauce, paste, powder, flakes or can).

- RCP2_BE47C7EA2B5D Chicken Seekh Kebab [wave1]: '4 dried red chilies' -> 180.0 g = 4 x std piece 45 g (ING_CHILI_PEPPER)
- RCP2_2BAD888FB0D3 Tom Kha Kai [v2.2]: '3–4 mini Thai bird chilies, finely chopped' -> 157.5 g = 3.5 x std piece 45 g (ING_CHILI_PEPPER)
- RCP2_33E97C290A86 Stir-Fried Broccolini, Vietnamese Style [v2.2]: '2 small dried red chiles (such as chiles de arbol), seeded, chopped' -> 90.0 g = 2 x std piece 45 g (ING_CHILI_PEPPER)
- RCP2_1BB420355E69 Singapore Noodles [v2.2]: '2 small red Thai chile, seeded and finely chopped' -> 90.0 g = 2 x std piece 45 g (ING_CHILI_PEPPER)
- RCP2_6B98370CEE0F Spanish Style Mussels [wave2]: '2 small hot peppers (optional)' -> 90.0 g = 2 x std piece 45 g (ING_CHILI_PEPPER)

### P4f_parenthetical_weight_ignored (n=181)

Rule: Line text has a package weight in parentheses ("(14 oz)") and the grams are more than 20% off both that weight and quantity x that weight; unit is piece, can, package, jar, box, bottle, bag, head, bunch or none, and basis is not stated_package.

- RCP2_7246E8F66853 Chiles Rellenos (Egg) Casserole [wave1]: '1 (4 oz.) can green chilies, chopped (optional)' -> 75.0 g, text says 113 g (x1) basis=estimated
- RCP2_82618EC5A764 Oven-Fried Chicken And Black Bean Chimichanga [wave2]: '3 (15 ounce) cans black beans' -> 750.0 g, text says 425 g (x3) basis=estimated
- RCP2_87C706CF543B Stuffed Mushrooms [overquota]: '16 large mushrooms (about 1 lb.)' -> 288.0 g, text says 454 g (x16) basis=stated
- RCP2_41AE9B357DCA Senegalese (African) Peanut Soup [v2.2]: '2 large sweet potatoes (about 2 pounds)' -> 228.0 g, text says 907 g (x2) basis=stated
- RCP2_F469F1BF6F5B Layered Spaghetti Casserole [wave2]: '1 (30 oz.) jar spaghetti sauce' -> 453.6 g, text says 850 g (x1) basis=estimated

### P5a_cooked_item_dry_form (n=50)

Rule: Line says cooked/steamed/boiled/leftover rice, pasta, beans, grains etc. but maps to the dry form, whose kcal/100 g is at least 1.5x the cooked form's.

- RCP2_71000327626D Bridget Jones'S Turkey Curry [v2.2]: '2 cups steamed rice' -> ING_RICE 370.0 g, prep=[], dry 365 vs cooked 130 kcal/100g
- RCP2_2E3B050C9F05 Vietnamese Fried Rice [v2.2]: '3 cups steamed white rice' -> ING_RICE 555.0 g, prep=[], dry 365 vs cooked 130 kcal/100g
- RCP2_7061CC7D6298 Steamed Snapper With Ginger And Bok Choy [wave2]: 'None None steamed rice, to serve' -> ING_RICE 740.0 g, prep=['none', 'to serve'], dry 365 vs cooked 130 kcal/100g
- RCP2_6868EE208D66 Bok Choy With Shrimp [wave2]: 'None None Steamed rice, to serve' -> ING_RICE 740.0 g, prep=['none', 'to serve'], dry 365 vs cooked 130 kcal/100g
- RCP2_BA81209A3EB1 Puerto Rican Chicken In Green Sauce [wave2]: 'steamed rice, and lime wedges for serving' -> ING_RICE 555.0 g, prep=['and lime wedges for serving'], dry 365 vs cooked 130 kcal/100g

### P5a2_cooked_after_noun_ambiguous (n=16)

Rule: Same as P5a with the wording "rice, cooked" (could be the amount after cooking). Ambiguous.

- RCP2_A705CB907145 Steamed Marinated Eggplant [wave2]: '1 cup white rice, boiled' -> ING_RICE 185.0 g, prep=['boiled'], dry 365 vs cooked 130 kcal/100g
- RCP2_744F800EDFEE Red Curry Fried Rice [v2.2]: '2 cups rice, steamed, cooled' -> ING_RICE 370.0 g, prep=['cooled', 'steamed'], dry 365 vs cooked 130 kcal/100g
- RCP2_04A8A51E9147 Bibimbap [v2.2]: '10 oz jasmine rice, steamed' -> ING_RICE 283.5 g, prep=['steamed'], dry 365 vs cooked 130 kcal/100g
- RCP2_25C350E683AE Salmon Fried Rice [v2.2]: '2 cups rice, prepared and cooled' -> ING_RICE 370.0 g, prep=['and cooled', 'prepared'], dry 365 vs cooked 130 kcal/100g
- RCP2_8FA60277E1B6 Crab And Avocado Roll - Sushi [wave2]: '4 cups sushi rice, prepared' -> ING_RICE 740.0 g, prep=['prepared'], dry 365 vs cooked 130 kcal/100g

### P5b_liquid_bouillon_as_cube (n=36)

Rule: ING_BOUILLON line described as a liquid (cups, broth, stock) with no cube/powder/teaspoon wording, or over 40 g without such wording.

- RCP2_A65C1F5BF595 Beef Curry With Onions [v2.2]: '1 c. beef bouillon' -> ING_BOUILLON 150.0 g (>40 g of dry bouillon)
- RCP2_A79685F90AE0 Swedish Meatballs [v2.2]: '1 c. beef bouillon' -> ING_BOUILLON 150.0 g (>40 g of dry bouillon)
- RCP2_676F4FEA1320 Pichelsteiner Topf (German)(Mixed Meat And Ve [wave1]: '4 c. beef bouillon' -> ING_BOUILLON 600.0 g (>40 g of dry bouillon)
- RCP2_AB3E3594986B Beef Stroganoff [v2.2]: '1 1/2 c. beef bouillon' -> ING_BOUILLON 225.0 g (>40 g of dry bouillon)
- RCP2_2258B11C95F2 Beef Teriyaki Hors D'Oeuvre [wave2]: '1/4 cup chicken bouillon' -> ING_BOUILLON 37.5 g (260 kcal/100g dry cube)

### P6_energy_outlier (n=274)

Rule: kcal per serving above the course threshold (soft; THRESH).

- RCP2_EAD88A616DC6 Colombian Puchero Soup [wave2]: main 1236.6 kcal/serving > 1200; servings=8 (estimated)
- RCP2_EBDD2942C571 Real Banana Pudding [overquota]: dessert 951.8 kcal/serving > 900; servings=8 (stated)
- RCP2_086DA953D9BB Irish Crème Liqueur In Chocolate Cups [wave2]: drink 679.5 kcal/serving > 500; servings=4 (estimated)
- RCP2_CB386B8363E1 Marilyn'S English Pasties [v2.2]: main 1235.8 kcal/serving > 1200; servings=20 (estimated)
- RCP2_84C10DDADBFA Authentic Mexican Beef Enchilladas [wave1]: main 1391.7 kcal/serving > 1200; servings=6 (stated)

### P6h_energy_outlier_hard_1.5x (n=73)

Rule: kcal per serving above 1.5x the course threshold.

- RCP2_C841B84CBAC7 Parmesan Wings [overquota]: snack_appetizer 1365.1 kcal/serving > 1.5x700; servings=3 (stated)
- RCP2_E2077E99E07C Jeanie'S Falafel [wave1]: snack_appetizer 2158.4 kcal/serving > 1.5x700; servings=4 (estimated)
- RCP2_50CC94B08256 Vietnamese Beef Marinade (Thit Bò Uop) [v2.2]: sauce_condiment 1400.0 kcal/serving > 1.5x400; servings=20 (estimated)
- RCP2_8B5CF0268D1E Sourdough Startergroves, Texas [wave1]: sauce_condiment 1308.3 kcal/serving > 1.5x400; servings=1 (estimated)
- RCP2_CC6EA4466598 Orange Breakfast Flip [overquota]: drink 986.1 kcal/serving > 1.5x500; servings=1 (stated)

### P7_ingredient_never_in_steps (n=788)

Rule: A non-optional line of 3 g or more (not salt, pepper, water, ice) shares no word with the steps, after exemptions for generic wording ("all ingredients"), hypernyms (meat, vegetables), seasoning, fat and liquid words. Not checked when the steps are under 80 characters or use generic wording (ingredients, together, the rest, remaining).

- RCP2_557753E022A8 Mon-Doo(Korean Egg Rolls) [v2.2]: 1 unused: 2 c. cabbage, shredded
- RCP2_7CD020B9B4A1 All-American Meatballs(Microwave Cooking) [v2.2]: 1 unused: 1 medium potato, peeled and coarsely grated
- RCP2_33D380525A75 Cauliflower Salad [v2.2]: 7 unused: 1 small head cauliflower, cut into small pieces | 1 small head lettuce, shredded | 1/2 c. Miracle Whip (spread over lettuce layer)
- RCP2_D0D83EB941C5 Stir-Fry Beef And Vegetables [wave2]: 1 unused: 1 Tbsp. cornstarch
- RCP2_B678943E7C43 Breakfast [overquota]: 1 unused: 4 Tbsp. dry mustard

### P7b_two_or_more_unused (n=379)

Rule: P7 with two or more such lines.

- RCP2_C681F2C54C49 Southern Pot Roast [v2.2]: 3 unused: 6 potatoes | 6 carrots | 2 small whole onions
- RCP2_B745E0078172 Beef Curry Delicious [v2.2]: 3 unused: 2 c. sliced onions | 1/2 c. tomato juice | salad oil
- RCP2_C75E93BF902D Busy Day Bake [v2.2]: 3 unused: 1 1/2 lb. sliced beef (liver) | 1 c. chopped celery | 1 c. chopped onion
- RCP2_7ED35556FC1B Rocky Road Pizza [wave2]: 2 unused: miniature marshmallows | chocolate chips
- RCP2_485FCB0D3C73 Chimichangas [wave1]: 2 unused: 1 teaspoon ground red chili pepper | 1 (4 ounce) can chopped green chilies, undrained

### P7c_major_ingredient_unused_50g (n=610)

Rule: P7 where an unused line weighs 50 g or more.

- RCP2_0A65A8AAA297 Cuban Pork Rub [v2.2]: 3 unused: 1 tablespoon unsweetened cocoa powder | 2 teaspoons oregano | 1 large onion, finely chopped
- RCP2_AA00FEFD1067 Spicy Garlic Chicken Lettuce Wraps [wave2]: 1 unused: 6 green onions sliced
- RCP2_C74C6BCEC751 Western Omelet With Mushrooms [overquota]: 1 unused: 1/4 c. milk
- RCP2_F4F108D33F2C Brazilian Black Beans And Rice [overquota]: 3 unused: 1/2 lb. beef sausage, sliced | 1 large onion, chopped | 1 large clove garlic, crushed
- RCP2_3F840960D5DC Shrimp Kabobs(Low-Fat) [wave2]: 2 unused: pineapple chunks (in its own juice) | 3 green peppers, cut into chunks

### P8a_oven_without_temperature (n=124)

Rule: A sentence says oven or bake (not a Dutch oven, microwave, grill, slow cooker etc.) and no step has an oven temperature.

- RCP2_452D9D2F36A9 Christmas Horns(Recipe From Czeckoslovakia) [wave2]: Bake on ungreased cookie sheet for 10 to 15 minutes, until pink.
- RCP2_3A9A629EC03C Rose'S Pizza Dough [v2.2]: Bake 10-15 minutes longer.
- RCP2_29E9E4335A80 Health Wealth And Happiness In A Bowl [wave2]: Prepare stock by combining the stock cubes with 750mls of hot water Bake pork and cut into thin slices.
- RCP2_9DF7BB19BDCA Healthy Chicken Gyros [wave2]: Wrap pitas in foil and warm pitas in the oven.
- RCP2_3979B00CE95F Pork Adobo [v2.2]: * Alternatively, put into 250-degree oven to simmer.

### P8b_fewer_than_2_steps (n=1,321)

Rule: Fewer than two instruction steps.

- RCP2_3FB55AD8597F Thai Coconut Milk Ice Cream [v2.2]: 1 step(s): Combine coconut milk, sugar, and salt in medium saucepan and bring to gentle boil over medium-high heat. Cook, stirring
- RCP2_98E1E87F0C67 Kalamata Olive Tapenade [wave2]: 1 step(s): Place the garlic cloves into a blender or food processor; pulse to mince. Add the olives, capers, parsley, lemon juice,
- RCP2_4D861EE30F27 Lemon-Thyme Cornish Hens [wave1]: 1 step(s): In an bowl, combine the first seven ingredients. Place hens on a rack in a shallow baking pan. Tuck wings under hen. Spo
- RCP2_D91C21F725A2 Overnight Souffle [v2.2]: 1 step(s): Grease a 9 x 13-inch pan. Alternate 6 slices of bread and half of combined cheeses. Repeat with the remaining bread and
- RCP2_4C4990BFCE3A Teriyaki Marinade [v2.2]: 1 step(s): Combine all ingredients. Pour over beef; cover and refrigerate for 2-24 hours.

### P8b2_single_short_step_lt200ch (n=544)

Rule: One step, shorter than 200 characters.

- RCP2_FC79701D19E8 Bread Pudding [overquota]: 153 chars: Combine eggs, milk, vanilla, cinnamon and salt. Add bread cubes, brown sugar and raisins. Pour into 8 inch round pan. Bake 350° for 45 minutes. Serves
- RCP2_83D393644703 Quick Thai Fried Bananas [v2.2]: 190 chars: Melt butter in a wok over high heat. Add bananas, brown sugar, and cinnamon; saute until bananas are golden brown and sugar is bubbling, about 5 minut
- RCP2_4A9EBF54BE30 Russian Pitter [v2.2]: 57 chars: Preheat oven to 350°. Grease and flour a 9 x 13-inch pan.
- RCP2_F2D9EE7A19A4 Vibrant Veggie Stir-Fry [v2.2]: 182 chars: In a nonstick skillet or wok, stir-fry broccoli and carrots in oil for 5 minutes. Add the zucchini, salt and pepper; stir-fry 4-5 minutes longer or un
- RCP2_834EF233AB8D Bernie Arnold'S Chinese Pepper Steak [wave2]: 115 chars: Slice steak as thinly as possible and cut in crosswise pieces (for easier cutting, cut meat when partially thawed).

### P8c_oven_without_any_time (n=139)

Rule: Same oven/bake sentence as P8a and no step has a time.

- RCP2_62EE970D79D5 Pineapple Chess Pie [overquota]: Pour filling into unbaked crust and bake at 350° until done.
- RCP2_A1261FEF0146 Thai Meatballs [wave2]: Preheat oven: 400F Add spring onions + ground and fresh corinander, chili sauce + lemon juice and mix well.
- RCP2_983C8A233F28 Ableskievers(Danish) [v2.2]: These take a special pan but bake as pancakes if pan is not available.
- RCP2_B68181BF3B4D Syrian Baked Chicken With Lemon [wave1]: Preheat oven at 375° to 400°.
- RCP2_96A7EDE01955 Colombian Recipes - Roasted Banana [wave1]: Place them on a surface or a mold that could lead to the oven (pre-oiled).

### P8d_truncated_steps (n=11)

Rule: A step ends with "...", or the last step ends with a dangling word (and, or, the, a, to, with, until, in, of...), a comma, a dash or an open bracket.

- RCP2_221A8DF66E2B Corn & Coconut Thai Street Food Dessert [v2.2]: last step: coconut meat, shredded coconut, sugar, and salt in the bowl. Add more sugar if needed, and ta-da...
- RCP2_39DA40A440A6 Turkish Mint Lemonade [v2.2]: last step: Serve, preferably with a sprig of mint in each glass.
- RCP2_37A532B50286 Tomato Chili Jam [wave2]: last step: ing on the water content of the tomatoes. The eventual amount of jam, similarly, will vary somewhat.
- RCP2_57A3CBE00EDA Baked Churro Sticks [v2.2]: last step: When you have paste and it's cold add the half egg and keep mixing,do sticks and cook them in the
- RCP2_2E1A7DB30BC3 Mango Kolaches [wave2]: last step: To make ahead: Prepare through Step 3; chill 8 to 24 hours. Proceed as directed in Steps 4 and

### P8e_steps_point_elsewhere (n=41)

Rule: Steps send the reader elsewhere (click, visit, www, http, .com, rest of the recipe, see the original). MyPlate boilerplate is skipped.

- RCP2_3074DBBA42A1 General Tso’S Chicken! [wave1]: Click this link http://bit.ly/15LQkAI for more information on rec
- RCP2_167387D57D86 Green Curry Shrimp With Pan-Roasted Bok Choy [wave1]: For recipe, go to: https://sunbasket.com/recipe/green-curry-shrimp-wit
- RCP2_47B930DC6889 Slow Cooker Chicken Curry [wave1]: ice, and fresh ginger and cook for 10 minutes. Read more at http://skinnyms.com/slow-cooker-chicken-curry/#ex6L5uqZWBbefI2S.9
- RCP2_1E017E4A662F Japanese Ginger Dressing [v2.2]: ds or until all of the ginger is well-pureed. Read more at: http://www.food.com/recipe/japanese-steakhouse-ginger-salad-dress
- RCP2_962272296BCF Brazilian Sauteed Kale [v2.2]: ed, about 4 minutes. Serve with white rice and black beens (see recipe)

### P8f_no_cooking_verb_in_steps (n=34)

Rule: No cooking verb (add, mix, cook, bake...) anywhere in the steps.

- RCP2_938CA091118F Chinese Smoked Ribs Or Chicken [v2.2]: You will need 4 cups hickory or fruitwood chips.
- RCP2_607E6A986389 Vietnamese Fish Sauce [v2.2]: sauce for spring rolls, summer noodle dish
- RCP2_A3EAAAC11C66 Mongolian Beef For 4: $10 Recipe! [v2.2]: See directions for this recipe at: http://couponcravings.com/easy-inexpensive-recipe-mongolian-beef/
- RCP2_0174FDE02BE4 Spicy Shrimp Curry [wave2]: *Available at Apsara-Oriental Gourmet Market in Herndon.
- RCP2_A5E3A0513E4A Pizza Meatballs [v2.2]: Makes 5 servings (20 balls).

## Share of recipes hit by the HP union, by course

| course | hit | recipes | share |
|---|---:|---:|---:|
| baked_good | 123 | 689 | 17.9% |
| breakfast | 187 | 669 | 28.0% |
| dessert | 192 | 1,071 | 17.9% |
| drink | 24 | 204 | 11.8% |
| main | 3,122 | 10,243 | 30.5% |
| salad | 171 | 981 | 17.4% |
| sauce_condiment | 182 | 828 | 22.0% |
| side | 407 | 2,172 | 18.7% |
| snack_appetizer | 218 | 856 | 25.5% |
| soup | 145 | 622 | 23.3% |
