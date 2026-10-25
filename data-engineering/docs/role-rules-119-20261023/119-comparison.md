# 119-recipe role review comparison

Source: owner's second-edition worksheet, sheet 3. This compares review suggestions, not human gold labels or admitted recipes. The 422-model batch remains gated. Source revision is in the JSON metadata.

## Counts

- blocked: 24
- target_allowed: 80
- owner_bean_decision: 13
- different_role: 2

## Rule effects (can overlap)

- tuber_vegetables: 19
- dough_only_shells: 10
- dumplings: 15
- staple_names: 13
- gnocchi: 2
- pizza_carrier: 5

## blocked

| ID | Recipe | Target | Rule | Reason |
|---|---|---|---|---|
| RCP2_01D48A672ACA | Sweet Potato Noodle Curry | vegetable | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Non-tuber vegetables 37.36%; resulting vegetable share 37.36% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_130F971CF821 | Ukrainian Bukovinian Nachynka (Cornbread Dressing) | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 40.05% (needs 50%). Sugar/carbohydrate 30.55% also exceeds the 20% ceiling (Yorkshire exception only). |
| RCP2_1722D847EECE | Southern Spoon Bread | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 43.98% (needs 50%). |
| RCP2_1E03BFBAFC1E | Spinach Souffle | vegetable | None | Souffle remains below the established vegetable/protein majority; thresholds unchanged. Non-tuber vegetables 49.83%; resulting vegetable share 49.83% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_1E114667D956 | Cheesy Potato Lasagna | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 0.00% (needs 50%). |
| RCP2_2056C574BA1E | Easy Spoon Bread | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 61.09% (needs 50%). Sugar/carbohydrate 29.21% also exceeds the 20% ceiling (Yorkshire exception only). |
| RCP2_2BD9BFE7AE13 | My Mother Lillie'S Spinach Souffle | vegetable | None | Souffle remains below the established vegetable/protein majority; thresholds unchanged. Non-tuber vegetables 9.40%; resulting vegetable share 9.40% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_310A97E81CC3 | Taco Baked Potatoes | staple | None | Stuffed/baked potatoes retain their previous classification. Listed raw-starch share 0.00% (needs 50%). |
| RCP2_42AA5C0CA968 | Potato Lasagna | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 0.00% (needs 50%). |
| RCP2_4A04FF1CF1AB | Watermelon Curry (Matira) | vegetable | None | Fruit-led dishes do not meet the vegetable definition. Non-tuber vegetables 0.28%; resulting vegetable share 0.28% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_4F7893458243 | Baked Sweet Potatoes With West African-Style Peanut Sauce | vegetable | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Non-tuber vegetables 7.57%; resulting vegetable share 7.57% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_50567B7B0B2C | Kumpir | staple | None | Stuffed/baked potatoes retain their previous classification. Listed raw-starch share 0.00% (needs 50%). |
| RCP2_62BE75BD23E4 | Zucchini Souffle | vegetable | None | Souffle remains below the established vegetable/protein majority; thresholds unchanged. Non-tuber vegetables 37.34%; resulting vegetable share 37.34% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_6466F4F7BF0A | Indian Tacos | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 88.03% (needs 50%). |
| RCP2_74EFF106FE7B | Pizza Stuffed Potatoes (Twice Baked) | staple | None | Stuffed/baked potatoes retain their previous classification. Listed raw-starch share 0.00% (needs 50%). |
| RCP2_87B3FDF37675 | Dumplings(Italian Style) | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 26.77% (needs 50%). Sugar/carbohydrate 30.23% also exceeds the 20% ceiling (Yorkshire exception only). |
| RCP2_89F7211E3608 | Chinese Sweet And Sour Spareribs Vegetarian | vegetable | None | Fruit-led dishes do not meet the vegetable definition. Non-tuber vegetables 41.01%; resulting vegetable share 41.01% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_958B37782112 | Basic Souffle Recipe | protein_main | None | Souffle remains below the established vegetable/protein majority; thresholds unchanged. Eligible protein-side share after unchanged batter/starch exclusions: 0.00% (needs 50%). |
| RCP2_989AB5746A34 | Sage Polenta | staple | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Listed raw-starch share 45.71% (needs 50%). |
| RCP2_9B204E51C88D | Potatoes Moussaka * | vegetable | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Non-tuber vegetables 38.15%; resulting vegetable share 38.15% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_B8E67A023CFD | Chtitha Batata (Algerian Potato Stew) | vegetable | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Non-tuber vegetables 5.91%; resulting vegetable share 5.91% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_BA741817426B | Corn Souffle | vegetable | None | Souffle remains below the established vegetable/protein majority; thresholds unchanged. Non-tuber vegetables 45.28%; resulting vegetable share 45.28% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_D4970386CD19 | Royal Broccoli Souffle | vegetable | None | Souffle remains below the established vegetable/protein majority; thresholds unchanged. Non-tuber vegetables 49.60%; resulting vegetable share 49.60% (needs 50%). Tubers need 40% non-tuber vegetables first. |
| RCP2_F8F9D659EDAB | German Potato Salad With Cajun Sausage | protein_main | None | No qualifying starch evidence or protein/vegetable majority under the retained rules; inspect listed ingredients. Eligible protein-side share after unchanged batter/starch exclusions: 44.21% (needs 50%). |

## target_allowed

| ID | Recipe | Target | Rule | Reason |
|---|---|---|---|---|
| RCP2_0CA3F3F66929 | Roti Jala (Malaysian Net Crepe) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_0DBC46FF845C | Oven Polenta | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_1087CA73F93D | Southern Smothered Green Beans | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_1106936B4750 | Sweet And Sour Cabbage | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_143B82A4800E | Spaetzle Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_15F1AAB4C310 | Korean Gaeran Mari (Stuffed Egg Omelette W Cheese) | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_16BF42FD100D | Udon Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_1A1BA06D6CB5 | Never Fail Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_212042A4393F | Zucchini Stir-Fry | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_21D46B7E4C32 | Spaetzles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_22CB9F8E06FA | Skillet Cornbread | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_23DCDA368745 | Homemade Nama (Fresh) Udon Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_24B9AA68594B | Mushroom Supreme | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_2AC94AA7906B | Cou Cou (Caribbean Polenta) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_2BA45D5AB524 | Taco Shells | sauce | sauce | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_2C368BB10827 | Sweet Potato And Feta Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_2E3012F8BABC | Gran'S Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_3314EF4C89E1 | Potato Gnocchi From Scratch | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_35DC1259F6B0 | Soft Shell Tacos | sauce | sauce | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_382B6B7AF64D | Southern Spoon Bread | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_43F241E2C2FA | Homemade Pasta | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_45391BFD9020 | Roti Jala (Malaysian Lacy Pancakes) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_45BE0219D45D | Heart-Shaped Tamagoyaki (Japanese Omelet) | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_47186AAC9989 | Creamy Polenta 10/08 Ba | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_486E1D6A70D8 | Japanese Sweet Omelet | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_4AFAD849C677 | Empanadas | sauce | sauce | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_4B3B02F3D728 | Roti Canai (Malaysian Style) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_4E9F363F8876 | Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_546DFF631ED4 | Cauliflower Au Gratin | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_5497ED3C29EA | Soft Cornmeal Taco Shells | sauce | sauce | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_54B440E380EB | Fry Bread For Navaho Tacos | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_57E2F87CA748 | Grandma'S Sweet And Sauerkraut | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_57F7D87302B2 | California Quiche Lorraine | sauce | sauce | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_5C8F72777948 | Spatzle | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_5F632D436B4E | Ramen Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_5FDC54ED6B2B | Sauerkraut | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_5FFD99ABD34E | Italian Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_641ABD3FC590 | Bavarian Cabbage | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_646039848924 | Crumb-Coated Spaetzle | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_66CDC4D02656 | Napa Cabbage with Dried Shrimp | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_6B3C9AD9D6E0 | Chinese Eggs | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_6C1E6D9E70BE | Polenta(Microwave) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_6D9B39CCD991 | Malaysian Roti Canai (Kinda Like A Pancake) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_76DAFDABA87D | Simply English Bubble & Squeak | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_7791CF2A7CDD | Polenta | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_7877BC0F4362 | Indian Fry Bread | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_7B354C6F9480 | Sauerkraut Dumplings(Hungarian Recipe) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_7DCEB197520A | Korean Steamed Egg Custard | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_7EC289C20A2A | Savory Sauerkraut Casserole | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_7F94EA2E2036 | Potato Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_829671202485 | Potato Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_888730AE4624 | Tamagoyaki - Japanese Rolled Omelette | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_89F0058D53F5 | German Style Beans | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_91E87A1057FC | Vegetarian Kenyan Curry | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_92D0966923D6 | Polenta | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_98B58258E3BD | Gnocches(Italian Potato Pasta) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_9C278A40B536 | Ethiopian Vegetable Bowl | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_9CD7CD0DA72B | Whole Wheat Egg Noodles Or Spaghetti Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_9E095D1F1FB4 | Korean Fried Tofu Side Dish | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_A660E279682A | Easy Potato Dumplings | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_A86E37A6C8F4 | Baked Tempeh | protein_main | protein_main | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_A986B63ED3FF | Lo Mein Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_B237C38BB623 | Italian Pizza With Zucchini, Cherry Tomatoes And Mozzarella Chee | one_bowl | one_bowl | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_B8238A4718B6 | Potato And Parmesan Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_BA95359C23B7 | Fried Polenta | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_BB79A09A52AC | Wonton Wrappers | sauce | sauce | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_C25D9C4D878B | Yorkshire Pudding | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_C7CFCE59ABE9 | Indian Potatoes With Cauliflower - Aloo Gobi | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_C81AEF8EF1AC | Onion Creme Brulee | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_C8B759477F8B | Gözleme (Turkish Flatbread) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_CC48BBF1CD0E | Moo Shu Pancakes | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_D57A6F473637 | Gnocchi | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_D86FDF8D821E | Sweet And Sour Cabbage | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_E091A77EFBE5 | Sauerkraut Auf Bayische Art(Bavarian Style Sauerkraut) | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_E20C08DE6172 | Polenta Gnocchi With Gorgonzola | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_E34384C91EB9 | Chinese Hand-Pulled Noodles | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_EEA0EE59804C | Putupap (South African Mealie Pap) | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_F015BE03BD1C | Bubble And Squeak | vegetable | vegetable | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_F918B184F959 | Spaetzle | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |
| RCP2_FB5F31874C8A | Fresh Ramen Egg Noodles From Scratch | staple | staple | Actual ingredient evidence permits the requested review role; human review still required. |

## owner_bean_decision

| ID | Recipe | Target | Rule | Reason |
|---|---|---|---|---|
| RCP2_0E0DC1E18373 | Brazilian Crock-Pot Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_0F6692A9480A | Corn And Lima Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_1BBDFA22270A | Sweet And Sour Lentils | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_31457FBD2E5C | Indian Pinto Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_35400FE238ED | Instant Pot® Smoky Korean Bbq Baked Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_428E51829F1A | Korean Spiced Kidney Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_5216E8F6555E | Refritos (Refried Beans) | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_561E7EDAC82C | Cuban Black Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_634F7CFF5B86 | Mexican Low-Fat Pinto Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_66AD2CDBCB53 | Guatemalan Black Beans (Frijoles Parados) | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_7767F8C932A9 | Frijoles Negros- Crock Pot Mexican Black Beans | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_B50E98C61A88 | Colombian Red Beans - Frijoles Colombianos | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |
| RCP2_BA25EE029647 | Brazilian Black Beans - Vegitarian | 待组长定 | None | Whole-bean sides are not promoted to protein mains (owner decision). |

## different_role

| ID | Recipe | Target | Rule | Reason |
|---|---|---|---|---|
| RCP2_3C310D373BB9 | Pupusas | one_bowl | staple | Evidence supports a different role, not the worksheet suggestion. |
| RCP2_BBD46E78E711 | Pupusas (El Salvadorean Tortilla) | one_bowl | staple | Evidence supports a different role, not the worksheet suggestion. |

## All-catalog changed rule suggestions

| ID | Recipe | Fields | Rules |
|---|---|---|---|
| RCP2_00100560483E | Swedish Crescents | `{}` |  |
| RCP2_02600E447144 | Festivals (Jamaican Fry Bread) | `{}` |  |
| RCP2_02ED221BB8C3 | Snowballs(Swedish) | `{}` |  |
| RCP2_037DE1F6C7F2 | Aloo Phujia | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_03BBF6ED0F99 | Braised Sauerkraut | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_0439059E67B0 | Veggie Curry Casserole | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_04AD5152E63A | Pot Pie(Square Dumplings) | `{"meal_role": {"before": "soup", "after": "sauce"}}` | dough_only_shells |
| RCP2_04FA63A313E5 | Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_06A36DD95C60 | Potato-Stuffed Eggplants With Indian Spices | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_071DD49C7186 | Indian Fry Bread | `{"protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_094A46921762 | Grandma'S Old-Fashioned Italian Cookies | `{}` |  |
| RCP2_09B1FDFC0350 | Homemade Taco Shells | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}, "protein_sources": {"before": ["egg"], "after": []}}` | dough_only_shells |
| RCP2_0B2FCB760777 | Jamaican Fried Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_0BA7DD6B8CD4 | Edamame Mashed Potatoes | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_0BB0579B8AC5 | Southern Cornbread | `{"protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_0BFA5255E06F | Greek Kouloudia | `{}` |  |
| RCP2_0CABBB4AE670 | Kale With Buttery Mashed Potatoes And Leeks (Colcannon) | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_0CFF755F4ED0 | Mexican Wedding Cakes | `{}` |  |
| RCP2_0F2A138F47E4 | English Teaballs | `{}` |  |
| RCP2_1656CB038FF4 | Chinese Wedding Rings | `{}` |  |
| RCP2_1B1222AB61D2 | Ethiopian Cabbage Dish | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_212042A4393F | Zucchini Stir-Fry | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_21D46B7E4C32 | Spaetzles | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_22CB9F8E06FA | Skillet Cornbread | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_230081AE2244 | Filipino Pandesal Bread ( Bread Machine ) | `{}` |  |
| RCP2_255BF2278F68 | Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_275105C8694D | Cornbread | `{}` |  |
| RCP2_27CF36D8964D | Flour Taco Shells | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}}` | dough_only_shells |
| RCP2_284F4FEA733D | Jamaican Boiled Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_290971CF4730 | Mexican Wedding Rings | `{}` |  |
| RCP2_2AB5DFF9B3BC | Texas Cornbread | `{"protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_2BA45D5AB524 | Taco Shells | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}, "protein_sources": {"before": ["egg"], "after": []}}` | dough_only_shells |
| RCP2_2C2A13538B08 | Chinese Chews | `{}` |  |
| RCP2_2C368BB10827 | Sweet Potato And Feta Gnocchi | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | gnocchi |
| RCP2_2C7D7B4493C8 | Kolache | `{}` |  |
| RCP2_2E6B4C7D3281 | Granny Gibbs' Famous Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_2F389C3628EA | Bubble And Squeak | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_2FC102A3D309 | Mexican Corn Bread | `{}` |  |
| RCP2_35DC1259F6B0 | Soft Shell Tacos | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}, "protein_sources": {"before": ["egg"], "after": []}}` | dough_only_shells |
| RCP2_382B6B7AF64D | Southern Spoon Bread | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_38391F938210 | Dreamy Polenta | `{"meal_role": {"before": "staple", "after": null}, "contains_staple": {"before": true, "after": null}}` |  |
| RCP2_38C9D74E8995 | Nif'S Easy Baking Powder Dumplings (Crock Pot Or Stove Top) | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_39C56A95E326 | Barbecue pork buns | `{}` |  |
| RCP2_3A80E3CCA5D1 | Buttermilk Rusks, South African | `{}` |  |
| RCP2_3C310D373BB9 | Pupusas | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | staple_names |
| RCP2_3D533F04D12A | Pizza | `{"meal_role": {"before": "protein_main", "after": "one_bowl"}, "contains_staple": {"before": false, "after": true}}` | pizza_carrier |
| RCP2_4117AD098162 | Margherita Pizza | `{"meal_role": {"before": "vegetable", "after": "one_bowl"}, "contains_staple": {"before": false, "after": true}}` | pizza_carrier |
| RCP2_42EA59ACAAEA | Crescents(Portuguese) | `{}` |  |
| RCP2_44C42897EBAD | Peruvian Alfajores | `{}` |  |
| RCP2_456FC7F0E61A | Colcannon | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_499150EEF32D | Grandma O'Neill'S Irish Soda Bread | `{}` |  |
| RCP2_49CA27EAC641 | Alfajores De Maizena | `{}` |  |
| RCP2_4AFAD849C677 | Empanadas | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}}` | dough_only_shells |
| RCP2_5497ED3C29EA | Soft Cornmeal Taco Shells | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}, "protein_sources": {"before": ["egg"], "after": []}}` | dough_only_shells |
| RCP2_54B440E380EB | Fry Bread For Navaho Tacos | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | staple_names |
| RCP2_57F7D87302B2 | California Quiche Lorraine | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}, "protein_sources": {"before": ["egg"], "after": []}}` | dough_only_shells |
| RCP2_5F3868736164 | Homemade Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_66D9A8C454B3 | Scottish Shortbread (For A Tea Party) | `{}` |  |
| RCP2_6AD2450270A2 | Russian Wafers | `{}` |  |
| RCP2_6BE1A90E3B64 | Homemade Pizza | `{"meal_role": {"before": "protein_main", "after": "one_bowl"}, "contains_staple": {"before": false, "after": true}}` | pizza_carrier |
| RCP2_75B48DFE5E23 | Scottish Bubbles And Squeak Patties | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_765D954B952B | Cheese Dumplings For Soup | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_76DAFDABA87D | Simply English Bubble & Squeak | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_778D3F74C3CF | Bohemian Bread Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_7877BC0F4362 | Indian Fry Bread | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | staple_names |
| RCP2_7B354C6F9480 | Sauerkraut Dumplings(Hungarian Recipe) | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_8109D39756EC | Pan De Sal - Filipino Bread Rolls | `{}` |  |
| RCP2_91E87A1057FC | Vegetarian Kenyan Curry | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_92892E4062D3 | Bubble And Squeak | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_98B58258E3BD | Gnocches(Italian Potato Pasta) | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | gnocchi |
| RCP2_9C278A40B536 | Ethiopian Vegetable Bowl | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_9C9E0673ECB8 | Quickly Made Kolache | `{}` |  |
| RCP2_A31F833871D7 | Bread Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_A660E279682A | Easy Potato Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_A7CE680FA0FD | Slovak Egg Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_B237C38BB623 | Italian Pizza With Zucchini, Cherry Tomatoes And Mozzarella Chee | `{"meal_role": {"before": null, "after": "one_bowl"}, "contains_staple": {"before": null, "after": true}}` | pizza_carrier |
| RCP2_B941DA1AAB4A | Magdalena'S Empanadas | `{"meal_role": {"before": "staple", "after": "sauce"}, "contains_staple": {"before": true, "after": false}}` | dough_only_shells |
| RCP2_BA5501343E98 | Hungarian Kifliks | `{}` |  |
| RCP2_BB79A09A52AC | Wonton Wrappers | `{"meal_role": {"before": null, "after": "sauce"}, "contains_staple": {"before": null, "after": false}, "protein_sources": {"before": ["egg"], "after": []}}` | dough_only_shells |
| RCP2_BC729782E35F | Greek Egg Biscuits | `{}` |  |
| RCP2_C1CA140E14B2 | Colleen'S Colcannon Potatoes | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_C25D9C4D878B | Yorkshire Pudding | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_C7CFCE59ABE9 | Indian Potatoes With Cauliflower - Aloo Gobi | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_C8BCC714AA60 | Yorkshire Pudding | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | staple_names |
| RCP2_CC48BBF1CD0E | Moo Shu Pancakes | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | staple_names |
| RCP2_CEEA9D67A7EE | Basic Italian Cookies | `{}` |  |
| RCP2_D0E1A366D88E | Kenyan Vegetable Curry | `{"meal_role": {"before": null, "after": "vegetable"}, "contains_staple": {"before": null, "after": false}}` | tuber_vegetables |
| RCP2_D2771697D5AB | Rolled Dumplings | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | dumplings |
| RCP2_EE70862CE312 | Traditional Bubble And Squeak Recipe | `{"meal_role": {"before": "staple", "after": "vegetable"}, "contains_staple": {"before": true, "after": false}}` | tuber_vegetables |
| RCP2_EEA0EE59804C | Putupap (South African Mealie Pap) | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}}` | staple_names |
| RCP2_F12F72458249 | Bread Dumplings (Houskove Knedliky) | `{"meal_role": {"before": null, "after": "staple"}, "contains_staple": {"before": null, "after": true}, "protein_sources": {"before": ["egg"], "after": []}}` | dumplings |
| RCP2_F5D923D65747 | Korean Pizza | `{"meal_role": {"before": "protein_main", "after": "one_bowl"}, "contains_staple": {"before": false, "after": true}}` | pizza_carrier |

## Fixed-seed sample: pending human review

- RCP2_2C2A13538B08 — Chinese Chews
- RCP2_2C368BB10827 — Sweet Potato And Feta Gnocchi
- RCP2_255BF2278F68 — Dumplings
- RCP2_92892E4062D3 — Bubble And Squeak
- RCP2_3D533F04D12A — Pizza
- RCP2_2AB5DFF9B3BC — Texas Cornbread
- RCP2_A660E279682A — Easy Potato Dumplings
- RCP2_4117AD098162 — Margherita Pizza
- RCP2_02ED221BB8C3 — Snowballs(Swedish)
- RCP2_4AFAD849C677 — Empanadas
- RCP2_071DD49C7186 — Indian Fry Bread
- RCP2_49CA27EAC641 — Alfajores De Maizena
- RCP2_275105C8694D — Cornbread
- RCP2_382B6B7AF64D — Southern Spoon Bread
- RCP2_3C310D373BB9 — Pupusas
- RCP2_2FC102A3D309 — Mexican Corn Bread
- RCP2_B237C38BB623 — Italian Pizza With Zucchini, Cherry Tomatoes And Mozzarella Chee
- RCP2_F12F72458249 — Bread Dumplings (Houskove Knedliky)
- RCP2_CEEA9D67A7EE — Basic Italian Cookies
- RCP2_D2771697D5AB — Rolled Dumplings
- RCP2_0439059E67B0 — Veggie Curry Casserole
- RCP2_C1CA140E14B2 — Colleen'S Colcannon Potatoes
- RCP2_C8BCC714AA60 — Yorkshire Pudding
- RCP2_0F2A138F47E4 — English Teaballs
- RCP2_6AD2450270A2 — Russian Wafers
- RCP2_44C42897EBAD — Peruvian Alfajores
- RCP2_EE70862CE312 — Traditional Bubble And Squeak Recipe
- RCP2_B941DA1AAB4A — Magdalena'S Empanadas
- RCP2_04AD5152E63A — Pot Pie(Square Dumplings)
- RCP2_7B354C6F9480 — Sauerkraut Dumplings(Hungarian Recipe)
