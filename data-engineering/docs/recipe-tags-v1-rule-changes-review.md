# 规则修复后的小范围复核（部分人工确认）

本表只核对变动后的标签，不复写上一轮审查，也不宣称总体准确率。优先包含已知回归案例，其余由固定种子从变动菜谱中抽取。

同意某个新标签不表示原标签正确。未审核模型字段继续冻结；fresh_rule_proposal只是新规则建议，不是已放行的模型值。原料克重是release数据，不是另行实测。

变动菜谱：206；本次抽取：25；未审核模型门禁：422 → 422。

人工确认进度：20 / 25。2026-10-19，owner在第一组回复“这5项全部同意”，确认第1–5项；在第二组回复“西班牙米饭可判定为主食，其他全部同意”，确认第6–9项的新值并纠正第10项。2026-10-20，第三组回复“全部同意”，确认第11–14项的新值并同意纠正第15项仿蟹肉误判；第四组回复“全部同意”，确认第16、17、19、20项并纠正第18项南瓜蛋炒饭。其余5项仍待确认。JSON的`verdict=true`表示同意本次新值，包括“应保留未知”；`false`表示不同意本次新值，人工正确值写入该条note。两者均不表示整道菜所有字段已核验。整包`owner_confirmed`仍为false。不计算总体准确率，不执行模型批次放行。

## 1. Marilyn'S English Pasties (RCP2_CB386B8363E1)

抽样方式：known regression；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "one_bowl" |
| contains_staple | false | true |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 14 c. flour（归一化 1750.0 g）
- 2 Tbsp. salt（归一化 36.5 g）
- 2 lb. Crisco（归一化 907.2 g）
- 4 1/2 c. water（归一化 1066.5 g）
- 1 lb. onions, diced（归一化 453.6 g）
- 5 lb. meat, cut small (beef stew or chuck roast)（归一化 2268.0 g）
- 14 lb. potatoes（归一化 6350.3 g）
- 3 Tbsp. salt（归一化 54.8 g）
- 1 Tbsp. pepper（归一化 6.8 g）
- 1/4 c. grated rutabaga（归一化 35.0 g）

步骤证据：

For dough, mix first 3 ingredients.
Mix well.
Add water and mix as little as necessary and use as little flour as you can when rolling out the dough.
Bake at 400° for 10 minutes, then at 350° for 40 to 45 minutes until crust is golden brown.
Make a small slit in the top of each pastie.
When you remove from oven, put a little water oleo mixture into slit (1 teaspoon oleo and 1/2 teaspoon water for each pastie).
Let sit for a few minutes.

人工意见：owner已确认本次meal_role、contains_staple新值；完整面皮载体的餐食、自带主食。历史模型蛋白来源未获确认，模型门禁不变。

## 2. Chinese Pork Chops (RCP2_AA52264E15D0)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["pork"] | null |

资料不完整：named pork but lists none。

原料证据：

- 2 c. hot water（归一化 474.0 g）
- 2 chicken bouillon cubes（归一化 8.0 g）
- 1/2 c. catsup（归一化 136.0 g）
- 1 c. honey（归一化 336.0 g）
- 1 1/2 tsp. salt（归一化 9.1 g）
- 1/2 tsp. ginger（归一化 1.0 g）
- 1/2 tsp. Accent（归一化 2.1 g）
- 1/2 tsp. soy sauce（归一化 2.7 g）

步骤证据：

Marinate 8 to 10 pork chops in sauce overnight.
Place pork chops in shallow roasting pan and pour sauce over them.
Bake 1 1/2 hours at 325°.
Serve over hot buttered rice.

人工意见：owner已确认本次三个新值应保留未知；猪排缺项、资料不完整，暂不用于规划，不凭标题补肉。

## 3. Kid Friendly Jamaican Chicken (RCP2_631314414D3C)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["chicken"] | null |

资料不完整：named chicken but lists none。

原料证据：

- 2 tablespoons light brown sugar（归一化 27.5 g）
- 1 1/2 teaspoons salt（归一化 9.1 g）
- 1/2 teaspoon ground black pepper（归一化 1.1 g）
- 1/2 teaspoon ground paprika（归一化 1.1 g）
- 1/2 teaspoon ground allspice（归一化 0.9 g）
- 1/4 teaspoon garlic powder（归一化 0.7 g）
- 1/4 teaspoon onion powder（归一化 0.6 g）
- 1/8 teaspoon ground cayenne pepper, as desired for additional spice（归一化 0.2 g）
- 1/8 teaspoon ground cinnamon（归一化 0.3 g）

步骤证据：

Mix all ingredients in a small bowl, set aside. Place boneless, skinless chicken breasts between sheets of plastic wrap or in large plastic bags and pound thin. Chicken breasts should be 1/2 thick or less. Rub chicken with olive oil on both sides. Sprinkle on seasoning. Place in skillet that has been pre-heated to medium-high and sprayed with non-stick cooking oil. Cook for 4 to 5 minutes per side or until done. Slice into 1/4 cubes or strips or leave whole as desired.

人工意见：owner已确认本次三个新值应保留未知；鸡胸肉缺项、资料不完整，暂不用于规划，不凭标题补肉。

## 4. Barbecue Beef (RCP2_DA28B246E699)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["beef"] | null |

资料不完整：named beef but lists none。

原料证据：

- 2 onions, diced（归一化 220.0 g）
- 1 pt. catsup（归一化 544.0 g）
- 1 Tbsp. Worcestershire sauce（归一化 17.0 g）
- 1 Tbsp. vinegar（归一化 15.0 g）
- 2 Tbsp. mustard（归一化 31.0 g）
- 1 tsp. cinnamon（归一化 2.6 g）
- 2 Tbsp. sugar（归一化 25.0 g）
- 1 1/2 c. beef stock（归一化 360.0 g）

步骤证据：

Season and brown roast.
Cook until done. Shred roast into small pieces.
Add remaining ingredients. Simmer 30 minutes or until mixture is thick.
Serve over toasted buns.
Yields 12 servings.

人工意见：owner已确认本次三个新值应保留未知；烤肉缺项、资料不完整，暂不用于规划，牛高汤不等于已列出牛肉。

## 5. Chicken Stir-Fry (RCP2_1D97F9CF9C30)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | "protein_main" |
| contains_staple | true | false |

原料证据：

- 1 (20 oz.) pineapple chunks（归一化 567.0 g）
- 1 lb. chicken breasts（归一化 453.6 g）
- 2 cloves garlic（归一化 6.0 g）
- 1 tsp. ginger（归一化 2.0 g）
- 2 Tbsp. vegetable oil（归一化 27.2 g）
- 2 medium carrots（归一化 122.0 g）
- 1 pepper（归一化 0.1 g）
- 4 oz. cooked spaghetti（归一化 113.4 g）
- 3 onions（归一化 330.0 g）
- 1/3 c. pineapple juice（归一化 83.3 g）
- 1/3 c. soy sauce（归一化 85.0 g）
- 1 Tbsp. cornstarch（归一化 8.0 g）
- 1 Tbsp. sesame oil（归一化 13.6 g）

步骤证据：

Drain pineapple.
Reserve 1/3 cup of juice.
Slice chicken in strips.
Stir-fry with garlic and ginger in oil.
Add pineapple, carrots, onions and pepper.
Steam for 2 to 3 minutes.
Stir in spaghetti.

人工意见：owner已确认本次meal_role、contains_staple新值；按既定占比规则，约113克熟意面不足以让鸡肉蔬果菜承担主食，归肉类主菜。不代表其余字段已核验。

## 6. Baked Macaroni And Cheese (RCP2_3B3606EBC933)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "staple" | "one_bowl" |

原料证据：

- 2 Tbsp. margarine（归一化 28.4 g）
- 2 Tbsp. flour（归一化 15.6 g）
- 1 tsp. salt（归一化 6.1 g）
- 1 tsp. mustard（归一化 5.2 g）
- 2 1/2 c. milk（归一化 610.0 g）
- 2 c. macaroni, cooked（归一化 280.0 g）
- 2 c. shredded cheese（归一化 226.0 g）
- 1/4 c. buttered bread crumbs（归一化 31.2 g）

步骤证据：

In saucepan, melt margarine. Blend in flour, salt and mustard. Add milk and heat, stirring constantly. The sauce will thicken a little.
Add 1 1/2 cups cheese, stirring often. Add macaroni with sauce. Top with remaining cheese, bread crumbs and a pinch of paprika.
Bake at 350° for 1/2 hour.
Makes 4 to 6 servings.

人工意见：owner已确认本次meal_role新值；奶酪焗通心粉是自带主食的完整餐食。不代表其余字段已核验。

## 7. Kalbi Beef Marinate (Flank Steak) (RCP2_80E876686DA8)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["beef"] | null |

资料不完整：named beef but lists none。

原料证据：

- 1/2 cup soy sauce（归一化 127.5 g）
- 1/4 cup water（归一化 59.2 g）
- 4 clove garlic, minced（归一化 12.0 g）
- 1 teaspoon ginger, minced（归一化 2.0 g）
- 1/2 cup brown sugar（归一化 110.0 g）
- 1/4 cup sesame oil（归一化 54.5 g）
- 2 tablespoon sesame seeds, toasted（归一化 18.0 g）
- 1 1/2 tablespoon chili paste（归一化 22.5 g）
- 5 Green onions, chopped（归一化 75.0 g）
- 1/2 cup Saki wine（归一化 118.5 g）

步骤证据：

Combine all ingredients except ribs in a 1 gallon ziplock bag. add flank steak and seal bag, squeezing out excess air. Work sauce into ribs by kneading bag
Marinate for 8 hours. Remove from zip lock and grill for 6 minutes each side.

人工意见：owner已确认本次三个新值应保留未知；原料未列出牛排及其用量，资料不完整，暂不用于规划。

## 8. Acorn Squash Stuffed With Italian Sausage & Penne (RCP2_961449012D5D)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | "protein_main" |
| contains_staple | true | false |

原料证据：

- 2 medium acorn squash, halved and cleaned（归一化 900.0 g）
- 1/2 lb Italian sausage, casings removed（归一化 226.8 g）
- 1/2 cup onion, sliced（归一化 80.0 g）
- 2 cups pasta sauce（归一化 490.0 g）
- 1/2 lb penne, cooked（归一化 226.8 g）
- 1/4 lb mozzarella cheese, shredded（归一化 113.4 g）

步骤证据：

Preheat the oven to 350 degrees F.
Season the squash with olive oil, salt and pepper. Place on a baking sheet, flesh side up and add 1/2 cup water to the pan. Cover with alluminum foil and bake until tender, about 1 hour. Remove from the oven and cool completely.
In a large saute pan, over medium heat, brown the sausage and onions, about 6 to 8 minutes.
In a large mixing bowl, toss the sausage and onions with the pasta sauce, pasta, and cheese. Season with salt and pepper. Mix well.
Spoon the pasta mixture into the cavity of each squash. Place the filled squashes on a baking sheet and place in the oven.
Bake until the squash is heated through and the cheese melts, about 20 minutes.

人工意见：owner已确认本次meal_role、contains_staple新值；按既定占比规则，227克熟意面不足以让这道香肠酿南瓜承担主食，归需另配主食的主菜。不代表其余字段已核验。

## 9. Mon-Doo(Korean Egg Rolls) (RCP2_557753E022A8)

抽样方式：seeded random changed case；原菜类：snack_appetizer。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| protein_sources | ["pork"] | null |

原料证据：

- egg roll wrappers (available at Oriental market)（归一化 450.0 g）
- 2 lb. pork or beef, cooked and cut into very small pieces（归一化 907.2 g）
- 1 c. green onions, chopped fine（归一化 100.0 g）
- 2 c. cabbage, shredded（归一化 178.0 g）
- 2 c. mushrooms, chopped small（归一化 140.0 g）
- 1 Tbsp. soy sauce（归一化 15.9 g）
- 1/4 tsp. garlic powder（归一化 0.7 g）
- 2 Tbsp. sesame seed oil (use 100% not blend)（归一化 27.2 g）

步骤证据：

Brown meat, onions and mushrooms in 2 tablespoons sesame seed oil.
Season according to taste with soy sauce and garlic powder. Place a small amount into the middle of egg roll wrapper.
Roll and seal wrapper by wetting finger with a little water (egg roll wrappers will seal tight).
Fry egg rolls in sesame seed oil or deep fry.
Can be frozen and microwaved when needed.

人工意见：owner已确认本次protein_sources新值应保留未知；“猪肉或牛肉”不等于已确定选择，也不等于两者都存在，不据此保证适合忌口家庭。

## 10. Spanish Rice (RCP2_4F1F492DB38E)

抽样方式：seeded random changed case；原菜类：side。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "staple" | null |
| contains_staple | true | null |

原料证据：

- 1 green pepper, chopped（归一化 120.0 g）
- 1 tomato, chopped（归一化 123.0 g）
- 1 onion, chopped（归一化 110.0 g）
- 2 Tbsp. butter（归一化 28.4 g）
- 2 c. cooked rice（归一化 316.0 g）
- 1/3 c. water（归一化 79.0 g）
- 1/2 tsp. salt（归一化 3.0 g）
- 1/4 tsp. pepper（归一化 0.6 g）

步骤证据：

Cook green pepper, tomato and onion in hot butter until tender.
Stir in cooked rice, water, salt and pepper.
Heat through, stirring occasionally.
Serves 6.

人工意见：owner不同意本次两个null值，明确判为主食。人工正确值为meal_role=staple、contains_staple=true。上表保留当时的规则输出，不能把人工纠正算成规则原本判对；正式标签修正待本轮复核后实施，不因此调整全局阈值。

## 11. Kim Bap (Korean Rice Rolls) (RCP2_D666EF442FE4)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "staple" | "one_bowl" |

原料证据：

- 4 cups hot cooked rice（归一化 632.0 g）
- 1 teaspoon rice vinegar（归一化 5.4 g）
- 1/2 teaspoon soy sauce（归一化 2.7 g）
- 1/2 teaspoon dark sesame oil（归一化 2.3 g）
- 4 sheets kim fresh seaweed（归一化 8.0 g）
- 1 small carrot, julienned（归一化 61.0 g）
- 2 eggs, beaten（归一化 100.0 g）
- 10 ounces frozen spinach, thawed and drained（归一化 283.5 g）
- 1/2 teaspoon sesame oil（归一化 2.3 g）
- 1/2 teaspoon soy sauce（归一化 2.7 g）
- 4 slices pickled yellow radishes（归一化 40.0 g）
- 1 tablespoon sesame seeds, toasted（归一化 9.0 g）

步骤证据：

Let rice cool a bit.
Meanwhile, mix the rice with the vinegar, soy sauce, and sesame oil.
Fry eggs as if it were a pancake.
Cut egg into strips.
Mix spinach with sesame oil and soy sauce.
To assemble, put rice on a bamboo roller (I do not have one and it works fine, just not as pretty).
Spread rice over 2/3 of the sheet, lay carrots, spinach, and egg on top.
Sprinkle with sesame seeds and roll like a jelly roll.
Cut into 1/2 inch rounds.
You can adapt this to your own tastes, some people put imitation crab meat in them, I put marinated soy bean sprouts and cucumbers in mine, etc.

人工意见：owner已确认本次meal_role新值one_bowl；熟饭、鸡蛋和蔬菜组成完整饭卷餐食，不只是单纯主食。不代表其余字段已核验。

## 12. Chicken Curry (RCP2_0447589B2FD3)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["chicken"] | null |

资料不完整：named chicken but lists none。

原料证据：

- 1/2 c. onion, chopped（归一化 80.0 g）
- 1/2 c. diced apple, peeled（归一化 55.0 g）
- 6 Tbsp. oleo（归一化 85.1 g）
- 8 oz. sliced mushrooms（归一化 226.8 g）
- 2 c. water chestnuts, sliced（归一化 280.0 g）
- 4 Tbsp. flour（归一化 31.2 g）
- 2 Tbsp. curry powder（归一化 12.0 g）
- 1/2 tsp. sugar（归一化 2.1 g）
- 1/4 tsp. ground ginger（归一化 0.5 g）
- 1 tsp. salt（归一化 6.1 g）
- 3/4 c. chicken broth（归一化 177.4 g）
- 1 c. evaporated milk（归一化 252.0 g）

步骤证据：

Saute onion, apple, oleo, mushrooms and water chestnuts until tender.
Add
the remaining ingredients in order (flour, curry powder, sugar, ginger, salt, chicken broth and evaporated milk). Cook
about
15 minutes on medium heat until thickened.
Add 3 cups diced, cooked chicken.
Let set for 24 hours in refrigerator. Heat and serve over hot rice.

人工意见：owner已确认本次三个新值应保留未知；步骤要求3杯熟鸡肉但原料未列，资料不完整，暂不用于规划，鸡汤不能代替缺失鸡肉。

## 13. Napa Cabbage with Dried Shrimp (RCP2_66CDC4D02656)

抽样方式：seeded random changed case；原菜类：side。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| protein_sources | ["shellfish"] | [] |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 2 tablespoons Dried Shrimp（归一化 21.2 g）
- 3/4 cup Boiling Water（归一化 177.8 g）
- 1 head Napa Cabbage（归一化 908.0 g）
- 2 tablespoons Peanut Oil（归一化 27.0 g）
- 4 Chopped Scallions（归一化 60.0 g）
- 1 tablespoon Ginger（归一化 6.0 g）
- 1 tablespoon Soy Sauce（归一化 15.9 g）
- 1 tablespoon Water（归一化 14.8 g）
- 2 tsp Cornstarch（归一化 5.3 g）
- 1 tsp Kosher Salt（归一化 6.1 g）
- 1/2 tsp Pepper（归一化 1.1 g）

步骤证据：

Dried shrimp gives this Chinese dish a punch of salty umami flavor. You can find it at an Asian grocery store in the frozen or refrigerated section. Look for small-sized dried shrimp, about a 1/4-inch in size. If you use medium or large dried shrimp, hydrate the shrimp with more water (1 cup for medium-sized shrimp, 1 1/4 cup for large) and for longer time (45 to 60 minutes), then chop it up into smaller 1/4-inch chunks. To make this recipe vegetarian, omit the dried shrimp and use four or five dried shiitake mushrooms, rehydrated, and sliced thin.
Rehydrate the dried shrimp:
Place the dried shrimp in a small bowl and pour the boiling water over it. Cover with a small plate and let sit for 30 minutes so the shrimp can rehydrate. The shrimp will be lighter in color and plump up slightly.
Prep the cabbage:
Meanwhile, split the napa cabbage in half lengthwise. Rinse the cabbage and shake it dry. Cut out the core of the cabbage and discard.
Set out two large bowls. Cut the remaining cabbage into 1-inch pieces, putting the thicker white pieces at the bottom of the cabbage into one bowl and the top thinner leafy green pieces into the other bowl.
Drain the shrimp:
Once the shrimp has rehydrated, drain it and discard the liquid.
Cook the shrimp and cabbage:
In a large wok or skillet over high heat add the peanut oil, swirling it around to coat the pan.
Heat until the oil looks shimmering hot, then carefully add the scallions, ginger, and rehydrated shrimp, paying specially attention as the wet ingredients may cause the hot oil to splatter. Toss with a spatula until the scallions are bright green and the entire mixture is fragrant, about 1 minute.
Add the thicker white part of the napa cabbage to the pan and lower the heat to medium high. Continue to cook and stir for 3 to 4 minutes, or until the edges of the cabbage pieces start to look slightly translucent but the center of the cabbage pieces are still opaque white.
Reduce the heat to medium low and add the leafy green pieces of cabbage into the pan. Cook until the leaves are wilted, about 2 minutes.
Make a cornstarch slurry:
In a small bowl, combine the soy sauce, cold water, and cornstarch, stirring to make a slurry. Then pour over the cabbage and continue to cook and stir until a sauce has thickened slightly to the consistency of whole milk.
Season the stir fry:
Season the stir fry with salt and pepper, then taste and add more salt and pepper if you wish. The cabbage will be translucent and silky looking, with specks of dried shrimp all over.

人工意见：owner已确认本次主要蛋白来源新值为空列表；虾米只作少量配料，仍含虾，虾过敏必须排除。本轮不认可冻结的旧模型主食角色，也不改变其模型门禁。

## 14. Beef Carnitas Tacos (RCP2_28626CFF47A0)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |
| protein_sources | ["beef"] | null |

资料不完整：named beef but lists none。

原料证据：

- 2 cups chopped plum tomato (about 2 medium)（归一化 360.0 g）
- 1/3 cup chopped onion（归一化 53.3 g）
- 1/4 cup diced peeled avocado（归一化 37.5 g）
- 2 tablespoons minced fresh cilantro（归一化 2.0 g）
- 1 tablespoon fresh lime juice（归一化 15.1 g）
- 1/8 teaspoon salt（归一化 0.8 g）
- 1/8 teaspoon freshly ground black pepper（归一化 0.3 g）
- 8 (6-inch) corn tortillas（归一化 360.0 g）
- 1 lime, cut into 8 wedges（归一化 67.0 g）

步骤证据：

Combine first 7 ingredients in a medium bowl; toss well. Warm tortillas according to package directions. Spoon 1/4 cup Beef Carnitas onto each tortilla; top each with about 3 tablespoons avocado mixture. Fold in half; serve with lime wedges.
This recipe was updated for the November, 2012 25th anniversary issue.
MyRecipes is working with
, the Partnership for a Healthier America, and USDA's MyPlate to give anyone looking for healthier options access to a trove of recipes that will help them create healthy, tasty plates. For more information about creating a healthy plate, visit
.

人工意见：owner已确认本次三个新值应保留未知；步骤要求的牛肉馅及用量缺失，资料不完整，暂不用于规划，不凭标题补肉。

## 15. Mexican Crab Salad (RCP2_010D47D8B41A)

抽样方式：seeded random changed case；原菜类：salad。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| protein_sources | ["fish"] | ["shellfish"] |

原料证据：

- 1 small head lettuce（归一化 10.0 g）
- 2 Tbsp. medium salsa（归一化 31.2 g）
- 3/4 c. sour cream（归一化 172.5 g）
- 1/2 c. black olives（归一化 67.5 g）
- 1/2 c. green onions（归一化 50.0 g）
- 2 c. tortilla chips, crushed（归一化 56.0 g）
- 2 tomatoes（归一化 246.0 g）
- 1 c. shredded Cheddar cheese（归一化 113.0 g）
- 8 oz. imitation crab meat, chunked（归一化 226.8 g）

步骤证据：

Blend salsa and sour cream.
Set aside.
Chop lettuce, olives, onions, tomatoes and crab meat.
Toss together.
Add cheese and chips.
Toss with the sour cream mixture.
Chill.
Enjoy!

人工意见：owner同意纠正规则误判，不接受本次shellfish新值。原料明确为仿蟹肉，按现有食材库归鱼类，人工正确值为protein_sources=["fish"]；不能凭crab一词当成真蟹，也不能据此保证具体产品的全部过敏原已核实。上表保留当时规则输出；正式规则和标签修正待本轮复核后实施。

## 16. Stuffed Green Peppers (RCP2_FAC00DA2B400)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | "protein_main" |
| contains_staple | true | false |

原料证据：

- 4 green peppers（归一化 480.0 g）
- 3/4 lb. ground beef（归一化 340.2 g）
- 1/2 c. cooked rice（归一化 79.0 g）
- 1 small egg（归一化 50.0 g）
- 1/4 c. water（归一化 59.2 g）
- 1 Tbsp. minced onion（归一化 10.0 g）
- 1 tsp. salt（归一化 6.1 g）
- 1/4 tsp. pepper（归一化 0.6 g）
- 1 c. tomato soup（归一化 250.0 g）

步骤证据：

Wash and clean peppers.
Combine remaining ingredients except tomato soup and mix thoroughly.
Fill pepper shells lightly with meat mixture.
Place on rack in cooker; add soup.
Pressure cook at 15 pounds pressure for 10 minutes.
Reduce pressure.
Serves 4.

人工意见：owner已确认本次meal_role、contains_staple新值；牛肉酿青椒的79克熟饭只是少量填馅，归需另配主食的肉类主菜。不代表其余字段已核验。

## 17. Chicken Teriyaki (RCP2_975C4431AA56)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["chicken"] | null |

资料不完整：named chicken but lists none。

原料证据：

- 1/2 c. soy sauce（归一化 127.5 g）
- 1/4 c. salad oil（归一化 54.5 g）
- 2 Tbsp. molasses（归一化 40.0 g）
- 2 tsp. ground ginger（归一化 4.0 g）
- 6 cloves garlic（归一化 18.0 g）

步骤证据：

Mix all ingredients and pour over chicken.
Marinate in refrigerator at least 1 hour.
Grill over medium hot grill.

人工意见：owner已确认本次三个新值应保留未知；原料只有腌料而缺鸡肉，资料不完整，暂不用于规划，不凭菜名补肉。

## 18. Pumpkin Fried Rice (RCP2_586E24DE73A6)

抽样方式：seeded random changed case；原菜类：side。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "staple" | null |
| contains_staple | true | null |

原料证据：

- 1/2 whole Large Onion, Chopped（归一化 55.0 g）
- 1 cup Canned Pumpkin（归一化 245.0 g）
- 2 cups Cooked White Rice（归一化 316.0 g）
- 2 whole Eggs, Beaten（归一化 100.0 g）
- 2 Tablespoons Soy Sauce（归一化 31.9 g）

步骤证据：

1. Spray a medium to large size skillet with oil and heat over medium-high.
2. Cook onion in oil until slightly softened.
3. Add pumpkin and rice and stir well.
4. Push rice to one side of the pan and pour beaten eggs onto exposed skillet surface.
5. Let cook slightly and stir in such a way that the eggs are scrambled.
6. Stir rice mixture into eggs and sprinkle with soy. Stir and let cook a few more minutes.
7. Remove from heat and enjoy!

人工意见：owner同意纠正本次两个null值。316克熟饭、245克南瓜和100克鸡蛋混炒，可作为自带主食的完整餐食；人工正确值为meal_role=one_bowl、contains_staple=true。上表保留当时的规则输出，不把纠正算成规则原本判对；正式修正待本轮复核后实施，不因此调整全局阈值。

## 19. Parmesan Chicken (RCP2_7B87DB0F6AFE)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["chicken", "egg"] | null |

资料不完整：named chicken but lists none。

原料证据：

- 1 egg（归一化 50.0 g）
- 1 Tbsp. milk（归一化 15.2 g）
- 1/2 c. Parmesan cheese（归一化 50.0 g）
- 1/4 c. flour（归一化 31.2 g）
- 1 tsp. paprika（归一化 2.3 g）
- 1/2 tsp. salt（归一化 3.0 g）
- 1/8 tsp. pepper（归一化 0.3 g）

步骤证据：

Mix dry ingredients in plastic baggie.
Mix egg and milk.
Dip chicken in egg and milk, then place in baggie; shake well.
Place in pan.
Pour 1/2 stick melted butter over.
Bake at 350° for 1 hour uncovered.

人工意见：owner已确认本次三个新值应保留未知；步骤所需鸡肉缺项、资料不完整，暂不用于规划，裹料里的鸡蛋不能代替缺失鸡肉。

## 20. Lo Mein (RCP2_C4333C1C5043)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| protein_sources | ["beef"] | null |

原料证据：

- 1 lb. egg noodles (Asian lo mein noodles- fresh or dried)（归一化 453.6 g）
- 5 T soy sauce (or Oyster Sauce)（归一化 79.7 g）
- 6 T oil（归一化 81.8 g）
- 1 egg（归一化 50.0 g）
- 3 cups Napa cabbage, finely shredded（归一化 267.0 g）
- 1/2 c bamboo shoots, shredded（归一化 65.5 g）
- 1 cup cooked beef, pork or chicken (shredded)（归一化 135.0 g）
- 2 t cornstarch（归一化 5.3 g）
- 1/2 t salt（归一化 3.0 g）
- 3 stalks scallions, washed and cut into 1" pieces.（归一化 45.0 g）

步骤证据：

Cook noodles in boiling salt water until al dente. Rinse under cold water. Drain.
Mix 2 T soy sauce with noodles and set aside. (You can use Oyster Sauce)
Stir any of the beef, pork or chicken in 1 T oil. Mix 1/2 t salt and 1 t cornstarch. Add this to the stir-fry. Remove it from the pan and set it aside. Add 3 T oil to wok and stir-fry cabbage ,and bamboo shoots. Add meat mixture to wok. Mix well. Beat egg and add it slowly to wok on top of everything. Add noodles. Toss until noodles are blended in with everything. Add 3 T Oyster sauce or soy sauce. You can add the scallions as garnish or throw them into the stir fry to cook them.

人工意见：owner已确认本次protein_sources新值应保留未知；“熟牛肉、猪肉或鸡肉”未确定选哪一种，不能直接认定牛肉，也不据此保证适合忌口家庭。

## 21. Taco Meat Filling (RCP2_4FBC8094CB72)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "sauce" |
| protein_sources | ["beef"] | [] |
| flavor_tags | ["rich"] | [] |

原料证据：

- 1 lb. ground beef（归一化 453.6 g）
- 1/2 c. chopped onion（归一化 80.0 g）
- 1 c. (8 oz.) tomato sauce（归一化 245.0 g）
- 1 tsp. chili powder（归一化 2.7 g）
- 3/4 tsp. salt（归一化 4.6 g）
- 1/2 tsp. garlic salt（归一化 3.0 g）

步骤证据：

Brown beef in skillet, stirring until crumbly; drain excess fat.
Stir in remaining ingredients; simmer, covered, for 10 minutes.
Makes filling for 8 taco shells.

人工意见：待确认。

## 22. Chicken Adobo (RCP2_9E72C3378CDE)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| protein_sources | ["chicken"] | null |

原料证据：

- 3 lbs Chicken, whole, disjointed & cut into serving pieces (or in combination with pork shoulder, 2" cubes)（归一化 1360.8 g）
- 1/2 cup Vinegar, cane（归一化 120.0 g）
- 1/3 cup Soy sauce, dark（归一化 85.0 g）
- 8 cloves Garlic, peeled, crushed（归一化 24.0 g）
- 1/2 tsp Peppercorn, black,whole,cracked（归一化 1.2 g）
- 2 each Bay leaves（归一化 0.4 g）
- 21/2 Tbsp Olive oil, pure（归一化 141.8 g）
- 3 cloves Garlic, peeled, chopped（归一化 9.0 g）

步骤证据：

1. Combine the chicken with the vinegar, soy sauce, crushed garlic, peppercorns, and bay leaves together in a saucepan. stir to evenly coat(May be marinated up to 8 hours or overnight in the refrigerator ).
2. Over medium heat, let it come to a simmer. Cover with a lid and lower heat for a gentle simmer, stirring occassionally. The chicken will release a lot of liquid.
3. When the chicken is barely cooked through. Remove the pieces, draining and shaking off as much liquid as possible. Reserve the stewing liquid.
4. Heat a heavy gauge saute pan large enough to accomodate all the chicken pieces. Add the oil and swirl to evenly coat. Add the garlic and cook over medium heat until golden, constantly stirring to avoid burning. Remove the garlic and set aside.
5. Pan fry the chicken pieces in the garlic-infused oil over medium to high heat to get a deep brown sear. Turn to sear on all sides. Be careful with hot oil splattering. Some of the chicken pieces will stick to the bottom of the pan if the chicken was not drained well of its stewing liquid.
6. Once all the chicken pieces are seared, add the reserved stewing liquid and the sauteed garlic with the chicken in the pan. Let the liquid reduce over medium heat until slightly thickened.
7. Serve with steamed rice.
OPTIONS:
*You may add the sauteed garlic as garnish in a serving dish instead of being part of the sauce.
**Add finely minced/pureed chicken livers in the end of cooking as a thickener and flavor enhancer.
***For color, infuse annato seeds in the olive oil before sauteeing the garlic.

人工意见：待确认。

## 23. Ravioli Bolognese (RCP2_616F0B3CE6CC)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "one_bowl" |
| contains_staple | false | true |

原料证据：

- 2 1/2 cups all purpose flour（归一化 312.5 g）
- 3 eggs（归一化 150.0 g）
- 3 tablespoons olive oil（归一化 40.5 g）
- 1 onion peeled and finely diced（归一化 110.0 g）
- 2 cloves garlic peeled and finely chopped（归一化 6.0 g）
- 3 carrots peeled and finely diced（归一化 183.0 g）
- 3 celery stalks trimmed and finely diced（归一化 120.0 g）
- 1 pound ground beef（归一化 453.6 g）
- 1 tablespoon tomato paste（归一化 16.4 g）
- 15 ounces peeled tomatoes（归一化 425.2 g）
- 1 bay leaf（归一化 0.2 g）
- 1/2 cup vegetable stock（归一化 119.5 g）
- 1 tablespoon Parmesan grated（归一化 6.2 g）
- 2 tablespoons heavy cream（归一化 29.8 g）

步骤证据：

Mix flour, eggs, 1 tbsp oil and 1 pinch of salt to a smooth dough, cover and leave for 1 hour to rest.
Heat remaining oil in a pan and fry onion until soft. Add beef, carrots, celery and garlic and fry over medium heat. Add tomato paste, tomatoes and bay leaf. Season to taste. Simmer for 30 mins, uncovered, until liquid is reduced. Season and leave to cool slightly.
Roll out dough thinly on a floured surface, and divide into 4 sheets. Press one of the sheets into a non-stick ravioli tray and fill the pockets with Bolognese sauce. Brush the edges of the sheet with water. Press another sheet on top and trim excess dough. Cut out the ravioli and repeat with remaining 2 sheets. (Makes about 24 ravioli.)
Boil salted water and cook the ravioli for 6 minutes. Meanwhile, heat remaining Bolognese with the stock, stir in Parmesan and cream. Divide ravioli onto 4 plates and top each serving with sauce.

人工意见：待确认。

## 24. Korean Fusion Butternut Squash Soup (RCP2_0DA06DF48EDB)

抽样方式：seeded random changed case；原菜类：soup。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| protein_sources | ["pork"] | ["chicken"] |

原料证据：

- 1 butternut squash (split and roasted for 1 hour @ 350f or until fork tender)（归一化 800.0 g）
- 6 cups chicken stock (can substitute vegetable stock)（归一化 1419.6 g）
- 2 medium carrots (grated)（归一化 122.0 g）
- 1 small onion (diced)（归一化 110.0 g）
- 1 celery rib (diced)（归一化 40.0 g）
- 1 sprig marjoram（归一化 0.1 g）
- 6 garlic cloves (smashed)（归一化 18.0 g）
- 3 bay leaves（归一化 0.6 g）
- 2 tablespoons soybean paste (Korean Doenjang)（归一化 31.2 g）
- 3 Italian sausages (I use Turkey, can substitute vegan alternative)（归一化 255.0 g）
- 1 king oyster mushroom (Diced)（归一化 18.0 g）
- 6 garlic cloves (minced)（归一化 18.0 g）
- 2 tablespoons red pepper paste (Korean Gochujang)（归一化 34.0 g）
- 1 tablespoon sesame oil（归一化 13.6 g）
- 1 1/2 cups water（归一化 355.5 g）

步骤证据：

Place stock, garlic, bay leaves, and marjoram into your soup pot and bring just up to a low boil for about 15 minutes, then reduce heat to simmer. Scoop out marjoram, garlic and bay leaves prior to adding next ingredients to the pot.
While stock is coming up to temperature saute the Mirepoix vegetables in sesame oil until they begin to caramelize. Then transfer to the stock pot. Scoop the roasted butternut squash out of the squash skins and add to the pot as well. Now, bring heat up on pot and maintain a high simmer, just below boiling.
Just prior to serving add Korean soybean paste then blend until smooth with an immersion blender (alternately you can transfer to a VitaMix or other blender).
In a small bowl, wisk together the water, hot pepper paste and sesame oil.
Remove skins from sausage and place in a saute pan and cook until most of the pink is gone and the pork is crumbled. Next add the mushroom, garlic and pepper paste mixture and bring pan to a boil. Reduce heat and continue to cook until most of the liquid is reduced.
Serving: 	Ladle soup into bowls and top with garnish and serve.

人工意见：待确认。

## 25. Taco Filling (Ground Beef) (RCP2_0FFB8C985C34)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "sauce" |
| protein_sources | ["beef"] | [] |
| flavor_tags | ["rich"] | [] |

原料证据：

- 1 lb ground beef（归一化 453.6 g）
- 1 medium onion, chopped（归一化 110.0 g）
- 1 tablespoon oregano（归一化 5.4 g）
- 2 teaspoons cumin（归一化 4.4 g）
- 1 teaspoon garlic powder（归一化 2.7 g）

步骤证据：

Brown ground beef with onion drain.
Add other ingredients.
Simmer add more seasoning to taste.
This can be a little dry.
This is not Health Food!
I have added a little cooking oil to the Mix.
Add salt and pepper.
Add ground beef to your favorite Taco shells.
Top with cheese, sour cream, lettuce, tomato, etc.
Enjoy!

人工意见：待确认。
