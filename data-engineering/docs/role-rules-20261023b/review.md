# Reviewer table for the frozen model batch

Generated with `data-engineering/scripts/role_review_table.py`. No row is human-verified by this tool; frozen model values, their provenance and the gate are unchanged. Revisions are in review.json.

## Frozen batch counts

Consistent: the rule names the stored role. Grey: the rule leaves the role open and the stored role is allowed. Blocked: the rule names another role, or the stored role is not allowed. Incomplete: a missing ingredient line closes the row.

| Stage | Consistent | Grey | Blocked | Incomplete |
|---|---:|---:|---:|---:|
| Before (base rules, model options) | 155 | 117 | 147 | 3 |
| After: these rules, model options | 162 | 112 | 145 | 3 |
| After: these rules, reviewer options | 162 | 145 | 112 | 3 |

## Frozen batch: suggestions for liu-ub

Reviewer roles add `staple` and `one_bowl` when the rule's staple share is 0 (owner 2026-10-23); the model prompt's roles are unchanged. 'Rule newer' names the rule revision that changed this row's suggestion after the batch was labelled: disagreement there is not a model error by itself.

| ID | Recipe | Stored role | Rule suggestion | Reviewer roles | Before → after | Rule newer |
|---|---|---|---|---|---|---|
| RCP2_00100560483E | Swedish Crescents | dessert | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_010100DDE2F6 | Cheesy Zucchini Lasagna | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_011288A0DAAA | Hush Puppies | snack | staple | staple | grey → blocked | owner 2026-10-23 |
| RCP2_011E8E50E3E6 | Feteer Meshaltet | staple | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_01D48A672ACA | Sweet Potato Noodle Curry | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_02600E447144 | Festivals (Jamaican Fry Bread) | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_02ED221BB8C3 | Snowballs(Swedish) | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_03DEE14CDC60 | Hush Puppies | snack | staple | staple | grey → blocked | owner 2026-10-23 |
| RCP2_04FA63A313E5 | Dumplings | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_0537F95C51D2 | French Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_05ED759BF701 | Fried Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_062390916CFF | Garden Ranch Pizza-Pampered Chef | one_bowl | None | vegetable, staple | blocked → blocked |  |
| RCP2_06BA84D12D67 | Meat Loaf With Cheese Sauce | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_0780C777C0AB | Stir Fry Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_0B06E6177DA3 | Crunchy Chicken Casserole | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_0CA3F3F66929 | Roti Jala (Malaysian Net Crepe) | breakfast | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_0CFF755F4ED0 | Mexican Wedding Cakes | dessert | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_0D6EBFF557A4 | Japanese Rice | None | None | staple | blocked → blocked |  |
| RCP2_0DBC46FF845C | Oven Polenta | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_0DE59ED69BBF | Stuffed Bell Peppers | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_0E0DC1E18373 | Brazilian Crock-Pot Beans | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_0F2A138F47E4 | English Teaballs | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_0F6692A9480A | Corn And Lima Beans | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_1087CA73F93D | Southern Smothered Green Beans | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_1106936B4750 | Sweet And Sour Cabbage | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_12D50BBDB52E | Eggplant A La Parmesan | vegetable | None | vegetable, staple | grey → grey |  |
| RCP2_130F971CF821 | Ukrainian Bukovinian Nachynka (Cornbread Dressing) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_140233207FB1 | Pizza Bianco | one_bowl | None | staple | blocked → blocked |  |
| RCP2_143B82A4800E | Spaetzle Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_1554F9789729 | Banh Mi Hotdog | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_15AF96C45EB8 | Paneer (Panir) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_15BCD52E8739 | Sprouts, Chorizo & Almond Bowl | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_15F1AAB4C310 | Korean Gaeran Mari (Stuffed Egg Omelette W Cheese) | breakfast | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_1656CB038FF4 | Chinese Wedding Rings | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_16BF42FD100D | Udon Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_1722D847EECE | Southern Spoon Bread | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_1729D7258E04 | Egg Filling For Sushi | snack | sauce | sauce | blocked → blocked |  |
| RCP2_185C6CEAE1C2 | Enchiladas | one_bowl | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_192C01503365 | Lasagna | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_19650787C340 | Ome Rice(Korean) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_19FBD3D80909 | Texas Hash | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_1A1BA06D6CB5 | Never Fail Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_1ABBF278577A | Jamaican Festival (Sweet Dumpling) | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_1ACC53E4DF5B | Baked Banana (Plantain) With Bacon And Cheese | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_1B153229C12F | Six In One | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_1BBDFA22270A | Sweet And Sour Lentils | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_1C43BC6CC166 | Stroganoff Steak Sandwiches | protein_main | one_bowl | one_bowl | blocked → blocked |  |
| RCP2_1CB98FB35F9C | Mexican Slow Cooker Chicken Burritos | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_1D11B4013577 | Mango Raisin Couscous ( Cous-Cous) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_1DDBB68902A6 | Cantonese Fried Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_1E03BFBAFC1E | Spinach Souffle | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_1E114667D956 | Cheesy Potato Lasagna | staple | staple | staple | blocked → consistent | owner 2026-10-23 |
| RCP2_1EF61A58359F | Apple Casserole | dessert | None | staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_201F9250C196 | Algerian Vegetable Couscous | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_2056C574BA1E | Easy Spoon Bread | breakfast | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_207C22E16796 | Scottish Roast Chicken | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_20E9789E014D | Crock-Pot Polish Cabbage Rolls | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_212042A4393F | Zucchini Stir-Fry | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_21ADEFC9A0C2 | Satay | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_21D46B7E4C32 | Spaetzles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_224C571A890D | Cheater'S Cheese Souffle | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_2258F6B702CB | Korean Kimchi Burgers | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_229B831CE6C7 | Mexican Wedding Bells | snack | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_22CB9F8E06FA | Skillet Cornbread | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_230081AE2244 | Filipino Pandesal Bread ( Bread Machine ) | staple | None | one_bowl, breakfast, snack, dessert | blocked → blocked | ADR-0082/0085 |
| RCP2_23AEBF1FD190 | Sweet And Sour Meatballs(In The Microwave) | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_23DCDA368745 | Homemade Nama (Fresh) Udon Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_241D4DF15897 | Hungarian Keifleys | snack | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_24B9AA68594B | Mushroom Supreme | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_24D1FD24F7F1 | Recipe Of 1985'S Burleson County Kolache(Queen'S Kolaches, Ella Drgac Queen) | breakfast | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_255BF2278F68 | Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_25B174021AD8 | Gramma & Grampa Fjerstad'S Lefse | staple | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_25EF3F0CA6AD | Homemade Queso Fresco In One Hour | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_2635DC1E3E4B | Pao De Queijo (Aka Brazilian Cheese Puffs) | snack | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_265F52246FE6 | South African Rusks | snack | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_275105C8694D | Cornbread | staple | None | protein_main, one_bowl, breakfast, snack, dessert | blocked → blocked | ADR-0082/0085 |
| RCP2_27CF36D8964D | Flour Taco Shells | staple | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_2848D4DD38CE | Fufu | staple | staple | staple | blocked → consistent | owner 2026-10-23 |
| RCP2_284F4FEA733D | Jamaican Boiled Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_290971CF4730 | Mexican Wedding Rings | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_293417D0F5D5 | Koulouria -- Greek Sesame Galettes | snack | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_29BA89DD8246 | Trinidadian Coconut Bake | staple | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_29EF8FF66D07 | Thai Chickpea Pizza | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_2AC94AA7906B | Cou Cou (Caribbean Polenta) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_2BA45D5AB524 | Taco Shells | staple | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_2BD9BFE7AE13 | My Mother Lillie'S Spinach Souffle | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_2C2A13538B08 | Chinese Chews | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_2C368BB10827 | Sweet Potato And Feta Gnocchi | one_bowl | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_2C3763B662FD | Venezuelan Arepas With Sesame, Chia, And Flaxseeds | staple | staple | staple | grey → consistent | owner 2026-10-23 |
| RCP2_2C6DCB5E0B50 | Chinese Egg Roll Wrap | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_2C7D7B4493C8 | Kolache | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_2CE4B2CB6AEE | Diner Meat Loaf | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_2DEFB0F27019 | Meat Croquettes | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_2E3012F8BABC | Gran'S Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_2E6B4C7D3281 | Granny Gibbs' Famous Dumplings | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_2EAB7EB9A23D | Chorizo Ball | one_bowl | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_2F5D13FF1C1A | Kentucky Hush Puppies | snack | staple | staple | grey → blocked | owner 2026-10-23 |
| RCP2_2FC102A3D309 | Mexican Corn Bread | snack | None | protein_main, one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_30B5AB92CC91 | Vietnamese Fajitas (Bo Nuong Xa) | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_310A97E81CC3 | Taco Baked Potatoes | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_313E4C8B9C7B | Betty Crocker 1950S Welsh Rarebit | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_31457FBD2E5C | Indian Pinto Beans | soup | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_3314EF4C89E1 | Potato Gnocchi From Scratch | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_3330CF0BC620 | Korean Kimchi Burgers | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_3368D505CC40 | Vietnamese Sandwiches | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_33B9F1AECB3E | Homemade Tempeh | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_3465CC24E6FF | Pinto Beans For Burritos | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_35400FE238ED | Instant Pot® Smoky Korean Bbq Baked Beans | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_355D74D12F4C | Vietnamese Spiced Paté | snack | snack | snack | consistent → consistent |  |
| RCP2_35DC1259F6B0 | Soft Shell Tacos | snack | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_35E7E466C238 | Pizza Burger'S Fcs School Recipe | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_3703338B3886 | Spinach Pizza Topping | snack | sauce | sauce | blocked → blocked |  |
| RCP2_370E5046B39F | Spanish Rice | staple | staple | staple | consistent → consistent |  |
| RCP2_382B6B7AF64D | Southern Spoon Bread | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_38391F938210 | Dreamy Polenta | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_38C9D74E8995 | Nif'S Easy Baking Powder Dumplings (Crock Pot Or Stove Top) | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_392DCD1CADCE | Shrimp Creole | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_39B142C1E4E8 | Caribbean Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_39BF39F7A6E4 | Banh Mi Hot Dogs | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_39C56A95E326 | Barbecue pork buns | snack | None | protein_main, one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_39CE51E9A95B | Rosalita'S Arepas Con Queso | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_3A80E3CCA5D1 | Buttermilk Rusks, South African | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_3A89815DD43E | Pancit(Rice Noodles) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_3B11D976623D | Vegetable Tempura | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_3C310D373BB9 | Pupusas | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_3CC1354BC571 | Brazilian Arroz De Festa (Confetti Rice) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_3D5ADFE023AB | Lamb & apricot meatballs | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_3F422D8D65F9 | Baked Plantains (Cooking Bananas) | dessert | None | soup, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_402F11758D8C | Injera | staple | staple | staple | grey → consistent | owner 2026-10-23 |
| RCP2_4070469D0041 | French Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_409262770DBA | Popovers(Portuguese) | breakfast | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_40ECCF6439F2 | Cajun Meat Loaf | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_420219DB3C60 | Fried Pheasant | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_428E51829F1A | Korean Spiced Kidney Beans | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_4295A6A55D85 | Tropical Beef Fajitas | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_42AA5C0CA968 | Potato Lasagna | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_42EA59ACAAEA | Crescents(Portuguese) | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_43F241E2C2FA | Homemade Pasta | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_441BD2095B93 | Vietnamese Pâté Chaud | snack | snack | snack | consistent → consistent |  |
| RCP2_44870004D5FB | Lasagna Style Bow Tie Dish | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_44C42897EBAD | Peruvian Alfajores | dessert | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_45391BFD9020 | Roti Jala (Malaysian Lacy Pancakes) | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_4539937C1F3A | Sauerkraut Dumplings | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_456CCADB7128 | Stuffed Green Peppers | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_45BE0219D45D | Heart-Shaped Tamagoyaki (Japanese Omelet) | breakfast | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_45EBD2FEEEB0 | Paneer (Home Made) | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_47186AAC9989 | Creamy Polenta 10/08 Ba | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_472B6677B22B | Tofu Feta | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey | ADR-0082/0085, owner 2026-10-23 |
| RCP2_474BD62093D1 | Cha-Soh Juhn(Korean Vegetable Pancakes) | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_4808C28F01AE | Refried Beans | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_4869C3AEA8AD | Thai Salty Egg(Side Dish) | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_486E1D6A70D8 | Japanese Sweet Omelet | breakfast | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_48AF180797C2 | Vidalia Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_491808DE2CEB | Spiedies (Kabobs) | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_499150EEF32D | Grandma O'Neill'S Irish Soda Bread | staple | None | protein_main, one_bowl, breakfast, snack, dessert | blocked → blocked | ADR-0082/0085 |
| RCP2_49CA27EAC641 | Alfajores De Maizena | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_4A04FF1CF1AB | Watermelon Curry (Matira) | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_4A7CC5A410F0 | Plantains In Coconut Milk | staple | staple | staple | blocked → consistent | owner 2026-10-23 |
| RCP2_4AFAD849C677 | Empanadas | snack | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_4B3B02F3D728 | Roti Canai (Malaysian Style) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_4CE4FA69CB3E | Pan-fried hake, white bean & chorizo broth | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_4DF11493A5F5 | Lemon Chicken Soup With Quinoa | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_4E9F363F8876 | Gnocchi | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_4EC013060AE0 | Luscious Layers | one_bowl | None | vegetable, staple | blocked → blocked |  |
| RCP2_4F7893458243 | Baked Sweet Potatoes With West African-Style Peanut Sauce | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_50567B7B0B2C | Kumpir | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_507B9CC45AC6 | Spanish Rice | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_50FF85F5FDE0 | Breakfast Burritos | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_515EDCDA8064 | Cream Cheese Crescents(Hungarian Kifli) | snack | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_5216E8F6555E | Refritos (Refried Beans) | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_53FF54F0EB32 | Stir-Fry Venison | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_540A9A5CDB2A | Fried Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_543A1872318A | Texas Hash(Weight Watchers) | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_546DFF631ED4 | Cauliflower Au Gratin | soup | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_5497ED3C29EA | Soft Cornmeal Taco Shells | staple | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_54B440E380EB | Fry Bread For Navaho Tacos | one_bowl | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_561E7EDAC82C | Cuban Black Beans | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_56684132208E | Ricotta Gnocchi | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_57A5EE0626CD | Texas Chili Con Carne | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_57E2F87CA748 | Grandma'S Sweet And Sauerkraut | soup | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_57F7D87302B2 | California Quiche Lorraine | staple | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_59209F8AE7D0 | South African Vetkoek | snack | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_5954131C04AC | Scrumpets | snack | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_59D318263C91 | Mahshy Bandora (Stuffed Tomatoes)(Lebanese) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_5A5EBBE90C92 | Injera | staple | staple | staple | grey → consistent | owner 2026-10-23 |
| RCP2_5B8603D2B433 | Italian Cottage Cheese | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_5C1AF74A7B55 | Šúĺlance s Makom | snack | None | soup, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_5C8F72777948 | Spatzle | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_5CAF86FF5D5D | Potato Borek | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_5D77EC59057C | Creamy Polenta With Parmesan And Mozzarella | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_5D84F859E558 | English Popovers | breakfast | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_5ED49FFCF6D4 | Spanish Rice | staple | one_bowl | one_bowl | blocked → blocked |  |
| RCP2_5F3868736164 | Homemade Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_5F632D436B4E | Ramen Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_5FDC54ED6B2B | Sauerkraut | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_5FECAA2C747F | Super Easy Pad Thai | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_5FFD99ABD34E | Italian Gnocchi | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_607A6AFD87B4 | Chivito uruguayo | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_614D0DC32132 | Meatballs | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_616382D3CF7F | Rabbit Stew | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_628A7F873ED3 | Mexican Higado Tacos | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_62BE75BD23E4 | Zucchini Souffle | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_6336ACA2F9AE | Japanese Tamago Egg | breakfast | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_634CE564B1EE | Middle Eastern Burgers | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_634F7CFF5B86 | Mexican Low-Fat Pinto Beans | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_641ABD3FC590 | Bavarian Cabbage | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_644A347C7523 | Jane Cody'S Awesome Stir Fry | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_646039848924 | Crumb-Coated Spaetzle | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_6466F4F7BF0A | Indian Tacos | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_64DBD7C2EF10 | Guadalajaran Jalisco Mexican Rice | staple | staple | staple | consistent → consistent |  |
| RCP2_65C7BEB7FEFD | Riyadh Rice - Middle Eastern Favourite! | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_66540AABF0E0 | Thai Sweet Potato Stew | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_66AD2CDBCB53 | Guatemalan Black Beans (Frijoles Parados) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_66CDC4D02656 | Napa Cabbage with Dried Shrimp | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_66D9A8C454B3 | Scottish Shortbread (For A Tea Party) | dessert | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_67A66B53DE3C | Slow Cooker Chicken Curry With Quinoa | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_686557404CA1 | Tacos | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_6AD2450270A2 | Russian Wafers | snack | None | one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_6AE2F530BFEE | Microwave Quick Lasagna | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_6B3C9AD9D6E0 | Chinese Eggs | breakfast | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_6C1E6D9E70BE | Polenta(Microwave) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_6CFCB11F79B9 | Thai Curry Pork Lettuce Wraps (Nam Prik Ong) | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_6D9B39CCD991 | Malaysian Roti Canai (Kinda Like A Pancake) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_6E65362F51A9 | Beef Fajitas | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_6E757674305D | Danish Dumplings | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_70B47600544A | Ramen Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_7123F2300609 | Ethiopian Cheese | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_722E5F335AD4 | Greek Shortbread | dessert | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_7248F8960BF1 | Spanish Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_74EFF106FE7B | Pizza Stuffed Potatoes (Twice Baked) | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_75BFE1C39E34 | Taco Casserole | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_765D954B952B | Cheese Dumplings For Soup | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_76DAFDABA87D | Simply English Bubble & Squeak | staple | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_7767F8C932A9 | Frijoles Negros- Crock Pot Mexican Black Beans | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_778D3F74C3CF | Bohemian Bread Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_7791CF2A7CDD | Polenta | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_7803F1FEB333 | Shredded Beef Chimichangas | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_783368D92192 | Tempura | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_7877BC0F4362 | Indian Fry Bread | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_793CD2DF1D24 | 3 Cheese Lasagne(St. Rose Student Recipe) | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_7B354C6F9480 | Sauerkraut Dumplings(Hungarian Recipe) | one_bowl | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_7DCEB197520A | Korean Steamed Egg Custard | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_7EC289C20A2A | Savory Sauerkraut Casserole | one_bowl | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_7EE413539148 | Pork Banh Mi Wraps | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_7F94EA2E2036 | Potato Gnocchi | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_805CCFE62BA7 | Lasagna | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_806075FC7BF8 | French Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_8109D39756EC | Pan De Sal - Filipino Bread Rolls | staple | None | one_bowl, breakfast, snack, dessert | blocked → blocked | ADR-0082/0085 |
| RCP2_81C30294D91B | Turkish Pogaca | snack | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_824A7E93FFE3 | Korean B.B.Q. | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_829671202485 | Potato Gnocchi | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_82DB38A4F424 | Stuffed Green Peppers | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_87713B74F837 | South African Meat Loaf | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_87B3FDF37675 | Dumplings(Italian Style) | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_87CBA929A2C6 | Spicy Thai One Pot | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_888730AE4624 | Tamagoyaki - Japanese Rolled Omelette | breakfast | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_88C46CBD6B93 | Chilean Chicken Stew With Pumpkin And Wild Rice | protein_main | one_bowl | one_bowl | blocked → blocked |  |
| RCP2_88FDB464A695 | Jang Jorim With Hard-Boiled Eggs (Korean Soy Beef Strips) | one_bowl | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_897B7AF05CB0 | Baked Zucchini With Rice And Feta | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_89F0058D53F5 | German Style Beans | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_89F7211E3608 | Chinese Sweet And Sour Spareribs Vegetarian | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_8C859FF10E5B | Coconut Baked Bananas (Or Plantains) | dessert | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_8C948ACDB0BC | Vietnamese Beef Curry | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_8CDACD3A0704 | Vietnamese Fried Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_8D12144D2014 | Pork Fajita Kabobs | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_8D376D61D13A | Slovak Easter Cheese (Cirak) | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_8F7B547C1808 | Banh Mi Hotdog | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_8F83C05E5E00 | Siopao (Filipino Steamed Buns) | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_8F8576285D7F | Fried Plantains | snack | staple | staple | grey → blocked | owner 2026-10-23 |
| RCP2_9150197BEBD9 | Japanese Marinated Soft Boiled Egg For Ramen (Ajitsuke Tamago) Recipe | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey | ADR-0082/0085, owner 2026-10-23 |
| RCP2_91E87A1057FC | Vegetarian Kenyan Curry | one_bowl | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_920C40633EDD | Egg Roll | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_92648ECC9FC9 | Hungarian Popovers(Kati Felfujtja) | breakfast | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_92D0966923D6 | Polenta | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_92F5CA7EC6D3 | Seven Hour Eggs - Korean Sauna | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_92FA53DECB5E | Mediterranean Chicken | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_956FD7177508 | Ramen Hot And Sour Soup | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_958B37782112 | Basic Souffle Recipe | breakfast | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_9723078749EF | Thai Chicken Pizza With Carrots And Cilantro | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_97D659CE8E07 | Japchae (Korean Glass Noodles) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_989AB5746A34 | Sage Polenta | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_98B58258E3BD | Gnocches(Italian Potato Pasta) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_9B204E51C88D | Potatoes Moussaka * | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_9C278A40B536 | Ethiopian Vegetable Bowl | one_bowl | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_9C51F36C16C2 | Meat Curry | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_9C9E0673ECB8 | Quickly Made Kolache | dessert | None | protein_main, one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_9CD7CD0DA72B | Whole Wheat Egg Noodles Or Spaghetti Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_9E095D1F1FB4 | Korean Fried Tofu Side Dish | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_A130BD59E2A1 | Gyro Casserole | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_A268F28D4812 | Tempeh “Bacon” | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_A26B07E48FE5 | Cheese Gnocchi | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_A31F833871D7 | Bread Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_A4661EEE5B7A | Fainá | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_A5E3A0513E4A | Pizza Meatballs | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_A660E279682A | Easy Potato Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_A7CE680FA0FD | Slovak Egg Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_A804E2F5468A | Meat Loaf(Published In Southern Living) | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_A84B4E56257C | Asian Wraps | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_A86E37A6C8F4 | Baked Tempeh | snack | protein_main | protein_main | blocked → blocked | ADR-0082/0085 |
| RCP2_A887D44E2FC0 | Sauerkraut pierogii | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_A96FC949077E | Moroccan Lentils And Couscous | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_A986B63ED3FF | Lo Mein Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_AAD369D32D4F | Spinach Quesadilla | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_ACE25C1DA124 | Welsh Rabbit | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_AFE6B5248965 | Moroccan Ksra | staple | None | staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_B12163C95EC7 | Tofu Stir Fry | sauce | None |  | incomplete → incomplete |  |
| RCP2_B237C38BB623 | Italian Pizza With Zucchini, Cherry Tomatoes And Mozzarella Chee | one_bowl | one_bowl | one_bowl | consistent → consistent | ADR-0082/0085 |
| RCP2_B2843B21CE46 | Steak Teriyaki | sauce | None |  | incomplete → incomplete |  |
| RCP2_B2E38830A727 | Scottish (Or English) Rarebit | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_B3B862477980 | Jamaican Grits Rice Cooker Optional | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_B3BCAE1F73A7 | Chop Suey | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_B3CA4D294329 | Khao Pad (Thai Fried Rice) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_B4D718862D00 | Mexican Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_B4F178FA5B73 | Hot Tamales | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_B4F2A550663D | "Spaghetti And Meat Sauce For 50" | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_B50E98C61A88 | Colombian Red Beans - Frijoles Colombianos | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_B6E9EAA502E0 | Dominican Chimichurri Burgers | protein_main | one_bowl | one_bowl | blocked → blocked |  |
| RCP2_B788087EF2A2 | Chicken Quesadillas With Tomato Salad | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_B7B25D1E360E | Couscous-And-Feta Cakes | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_B7C012C51A6D | Vietnamese Vegetable Baguette (Banh Mi) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_B8238A4718B6 | Potato And Parmesan Gnocchi | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_B89951CCB635 | Hearty French Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_B8E67A023CFD | Chtitha Batata (Algerian Potato Stew) | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_B941DA1AAB4A | Magdalena'S Empanadas | snack | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_B9A91EEFEF2B | Chinese Rice | staple | staple | staple | consistent → consistent |  |
| RCP2_BA25EE029647 | Brazilian Black Beans - Vegitarian | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_BA5501343E98 | Hungarian Kifliks | dessert | None | protein_main, one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_BA741817426B | Corn Souffle | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_BA95359C23B7 | Fried Polenta | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_BB79A09A52AC | Wonton Wrappers | snack | sauce | sauce | blocked → blocked | ADR-0082/0085 |
| RCP2_BBA025B49BA6 | Pierogi | snack | one_bowl | one_bowl | blocked → blocked |  |
| RCP2_BBD46E78E711 | Pupusas (El Salvadorean Tortilla) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_BC3A7EE10152 | Authentic Gazpacho - Southern Spain | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_BC729782E35F | Greek Egg Biscuits | snack | None | protein_main, one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_BE676A0D1F6F | Pressure-Cooker Asian Wraps | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_BE6A51BF97A6 | Sloppy Joes | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_BF6BCDCBD8C3 | Cabbage Casserole | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_C1E68B157F31 | Stuffed Lamb Tomatoes | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_C25D9C4D878B | Yorkshire Pudding | snack | staple | staple | blocked → blocked | ADR-0082/0085 |
| RCP2_C3B5C24F13AB | Tater Tot Beef Bake | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_C58164F6E689 | Cousin Judy'S Chow Mein | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_C7CFCE59ABE9 | Indian Potatoes With Cauliflower - Aloo Gobi | one_bowl | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_C7D3BB6B2788 | Easy Lasagne | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_C81AEF8EF1AC | Onion Creme Brulee | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_C8B5EA27D62D | Thai Chicken Tacos | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_C8B759477F8B | Gözleme (Turkish Flatbread) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_C8B86F1875A5 | Li'L Cheddar Meat Loaves | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_C8FFCB4AA279 | Fried Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_C94A3B3DAD51 | Grilled Steak Sandwiches With Chimichurri And Bell Peppers | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_CAE614EE3D95 | Italian Meatballs Pat'S Reciepe | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_CB386B8363E1 | Marilyn'S English Pasties | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_CB88A5A0DF4C | Africa-Bobotie | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_CC48BBF1CD0E | Moo Shu Pancakes | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_CEEA9D67A7EE | Basic Italian Cookies | dessert | None | protein_main, one_bowl, breakfast, snack, dessert | grey → grey | ADR-0082/0085 |
| RCP2_CEF5851EE683 | Enchilada Casserole | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_CF40179BCF86 | Easy Bobotie For Kid Chefs | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_D0F3CE9D133F | Hot Chicken Salad | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_D1A78AFA0C85 | Teenage Sloppy Joes | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_D1E77FB18316 | Lasagne | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_D2771697D5AB | Rolled Dumplings | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_D2B871893000 | Never-Fail Meat Loaf | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_D30FB234E549 | Rice And Sorghum Injera | staple | staple | staple | blocked → consistent | owner 2026-10-23 |
| RCP2_D453A4530ADE | Meat and Potatoes in Broth (Niku Jaga) | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_D4970386CD19 | Royal Broccoli Souffle | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_D57A6F473637 | Gnocchi | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_D698B2F5CB69 | French Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_D7BD0AAA0F99 | Greek-Style Couscous | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_D803B75A27D8 | Easy Cheese Lasagna | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_D82148B9AE3C | Broccoli Pizza | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_D86FDF8D821E | Sweet And Sour Cabbage | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_D875F1D29484 | Kalbi Venison | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_D8E98D9FFC37 | Tomatoes Provencale | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_DB61A80B71EF | Sinigang | soup | soup | soup | consistent → consistent |  |
| RCP2_DBE7700244BE | Morrocan Couscous With Green Beans | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_DBF17212D390 | Easy Mexican Sopes | snack | staple | staple | grey → blocked | owner 2026-10-23 |
| RCP2_DBFF4DB83EF2 | Butternut Squash Curry | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_DC882B3F674A | Banana Raita With Coconut | dessert | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_DD44C3D25E8E | Banh Mi Bo Kho | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_E091A77EFBE5 | Sauerkraut Auf Bayische Art(Bavarian Style Sauerkraut) | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_E20C08DE6172 | Polenta Gnocchi With Gorgonzola | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_E34384C91EB9 | Chinese Hand-Pulled Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_E3B3B3009341 | Teriyaki Steak | sauce | None |  | incomplete → incomplete |  |
| RCP2_E4454B4519B1 | Tempura | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_E5862A12458B | Potato Croquettes With Parmesan | snack | staple | staple | grey → blocked | owner 2026-10-23 |
| RCP2_E58EB09D4E0D | Cheese Stuffing For Manicotti | staple | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_E5A66F91CB58 | Meat Ball Casserole | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_E68974FE5EFE | West African Meat Kebabs | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_E6D5DE6253DA | Easy Manicotti | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_E729691E63DA | Sugar Free Cranberry Almond Biscotti | dessert | None | protein_main, staple, one_bowl, breakfast, snack, dessert | grey → grey |  |
| RCP2_E8D667BA918A | Fake Feta | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey | ADR-0082/0085, owner 2026-10-23 |
| RCP2_EA7BB1D1BA3A | Fried Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_EAAD839F9258 | Mushroom-Barley Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_EC29565337D3 | Dumpling Noodles | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_ED8C37EACE4D | Mock Feta Cheese ( Vegan Substitute ) | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey | ADR-0082/0085, owner 2026-10-23 |
| RCP2_EDF4D1848F6C | Mexican Rice | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_EE292ED1DADA | Potato-Apple Gratin | staple | None | staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_EEA0EE59804C | Putupap (South African Mealie Pap) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_EFA12409FC76 | Indian Raita (Cucumber Mix) | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_F015BE03BD1C | Bubble And Squeak | snack | vegetable | vegetable | blocked → blocked | ADR-0082/0085 |
| RCP2_F0A2E3140892 | Hearty French Onion Soup | soup | None | soup, one_bowl | grey → grey |  |
| RCP2_F12F72458249 | Bread Dumplings (Houskove Knedliky) | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_F14B2A2B76D7 | Teriyaki Rice Paper Salmon (Baked) | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_F19948BC59AA | Hungarian Goulash(Serves 6 To 8) | soup | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_F34E700C89B5 | Thai Red Curry | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_F36753718C88 | Chicken Thai Pizza | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_F480AAE0C111 | Sweet Potato & Pea Curry | one_bowl | staple | staple | blocked → blocked | owner 2026-10-23 |
| RCP2_F484CD172351 | Post Thanksgiving Turkey Casserole | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_F58B8FD2E4BB | Country Pâté Banh Mi | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_F5998F6963E8 | Sauerkraut pierogi | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_F62EDB215278 | Cheese Dumplings | snack | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_F79DA309FE66 | Big Mac | one_bowl | protein_main | protein_main | blocked → blocked |  |
| RCP2_F8E5BA1851FC | Quesadilla Casserole | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_F8F9D659EDAB | German Potato Salad With Cajun Sausage | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_F918B184F959 | Spaetzle | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_F96C60076A19 | Korean Noodles And Beef(Main Course From Abroad - Pungent Dish) | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_F9AC64939A2C | Welsh Rarebit | sauce | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | grey → grey |  |
| RCP2_FAC0F736C662 | Hoisin Chicken Wraps | one_bowl | one_bowl | one_bowl | consistent → consistent |  |
| RCP2_FAD4D33E3669 | Rice Paper Wrapped Fish | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_FB5F31874C8A | Fresh Ramen Egg Noodles From Scratch | staple | staple | staple | consistent → consistent | ADR-0082/0085 |
| RCP2_FBB45D25EC0B | Seriously Asian: Hooked On Udon Recipe | one_bowl | None | soup, staple, one_bowl, breakfast, snack, dessert, sauce, drink | blocked → grey |  |
| RCP2_FE6B12FA54B8 | Crackling Rice Paper-Wrapped Fish | protein_main | protein_main | protein_main | consistent → consistent |  |
| RCP2_FF3C50B5519E | Vietnamese "Banh Mi" Chicken Burger | one_bowl | one_bowl | one_bowl | consistent → consistent |  |

## Every catalog rule change against the base

Rule-owned changes refresh the tag file; frozen rows keep their model values. Pending human review.

| ID | Recipe | Course | Role before → after | Model options after | Frozen |
|---|---|---|---|---|---|
| RCP2_00A422F48FCC | Janssonin Kiusaus - Four Ingredient Finnish Potato Bake | main | None → staple |  | False |
| RCP2_011214D52B25 | Sweet Potato Souffle | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_011288A0DAAA | Hush Puppies | side | None → staple |  | True |
| RCP2_01D48A672ACA | Sweet Potato Noodle Curry | main | None → staple |  | True |
| RCP2_03DEE14CDC60 | Hush Puppies | side | None → staple |  | True |
| RCP2_09872DC5D6C3 | Hush Puppies | side | None → staple |  | False |
| RCP2_0ABBD7482788 | Platanos Fritos (Sauteed Plantains) | side | None → staple |  | False |
| RCP2_1770C1DCBF42 | Candied Yams | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_1E114667D956 | Cheesy Potato Lasagna | main | None → staple |  | True |
| RCP2_1E290BC51413 | Candied Yams | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_24CEEC832FB1 | Sweet Potato Souffle | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_2848D4DD38CE | Fufu | side | None → staple |  | True |
| RCP2_29A0BD36FF45 | Sweet Potato Praline | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_2C3763B662FD | Venezuelan Arepas With Sesame, Chia, And Flaxseeds | baked_good | None → staple |  | True |
| RCP2_2F5D13FF1C1A | Kentucky Hush Puppies | side | None → staple |  | True |
| RCP2_34DA1997D05C | Candied Yams | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_35A9C8C1762C | Gourmet Sweet Potato Souffle | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_402F11758D8C | Injera | baked_good | None → staple |  | True |
| RCP2_4098E2E0D1B8 | Yataklete Kilkil (Ethiopian Vegetable Stew) | main | None → staple |  | False |
| RCP2_472B6677B22B | Tofu Feta | side | protein_main → None | soup, breakfast, snack, dessert, sauce, drink | True |
| RCP2_4A7CC5A410F0 | Plantains In Coconut Milk | side | None → staple |  | True |
| RCP2_4F7893458243 | Baked Sweet Potatoes With West African-Style Peanut Sauce | main | None → staple |  | True |
| RCP2_50567B7B0B2C | Kumpir | main | None → staple |  | True |
| RCP2_5A5EBBE90C92 | Injera | baked_good | None → staple |  | True |
| RCP2_66540AABF0E0 | Thai Sweet Potato Stew | main | None → staple |  | True |
| RCP2_720FC24A521E | Aloo Matar | main | None → staple |  | False |
| RCP2_74EFF106FE7B | Pizza Stuffed Potatoes (Twice Baked) | main | None → staple |  | True |
| RCP2_8F8576285D7F | Fried Plantains | side | None → staple |  | True |
| RCP2_9150197BEBD9 | Japanese Marinated Soft Boiled Egg For Ramen (Ajitsuke Tamago) Recipe | side | protein_main → None | soup, breakfast, snack, dessert, sauce, drink | True |
| RCP2_B8E67A023CFD | Chtitha Batata (Algerian Potato Stew) | main | None → staple |  | True |
| RCP2_D30FB234E549 | Rice And Sorghum Injera | side | None → staple |  | True |
| RCP2_D63DBDEE3B0E | German Potato Salad | side | staple → None | soup, breakfast, snack, dessert, sauce, drink | False |
| RCP2_DBF17212D390 | Easy Mexican Sopes | main | None → staple |  | True |
| RCP2_DBFF4DB83EF2 | Butternut Squash Curry | main | None → staple |  | True |
| RCP2_E5862A12458B | Potato Croquettes With Parmesan | main | None → staple |  | True |
| RCP2_E8D667BA918A | Fake Feta | side | protein_main → None | soup, breakfast, snack, dessert, sauce, drink | True |
| RCP2_ED8C37EACE4D | Mock Feta Cheese ( Vegan Substitute ) | side | protein_main → None | soup, breakfast, snack, dessert, sauce, drink | True |
| RCP2_F480AAE0C111 | Sweet Potato & Pea Curry | main | None → staple |  | True |

## Fixed-seed sample of the changes (seed 20261023): pending human review

- RCP2_35A9C8C1762C
- RCP2_F480AAE0C111
- RCP2_29A0BD36FF45
- RCP2_E5862A12458B
- RCP2_50567B7B0B2C
- RCP2_34DA1997D05C
- RCP2_5A5EBBE90C92
- RCP2_00A422F48FCC
- RCP2_2C3763B662FD
- RCP2_011288A0DAAA
- RCP2_8F8576285D7F
- RCP2_E8D667BA918A
- RCP2_720FC24A521E
- RCP2_0ABBD7482788
- RCP2_1E290BC51413
- RCP2_2848D4DD38CE
- RCP2_D63DBDEE3B0E
- RCP2_4098E2E0D1B8
- RCP2_1E114667D956
- RCP2_4A7CC5A410F0
- RCP2_DBFF4DB83EF2
- RCP2_011214D52B25
- RCP2_74EFF106FE7B
- RCP2_D30FB234E549
- RCP2_9150197BEBD9
- RCP2_1770C1DCBF42
- RCP2_4F7893458243
- RCP2_66540AABF0E0
- RCP2_B8E67A023CFD
- RCP2_03DEE14CDC60
