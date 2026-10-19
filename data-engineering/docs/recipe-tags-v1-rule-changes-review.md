# 规则修复后的小范围复核（待人工确认）

本表只核对变动后的标签，不复写上一轮审查，也不宣称总体准确率。优先包含已知回归案例，其余由固定种子从变动菜谱中抽取。

同意某个新标签不表示原标签正确。未审核模型字段继续冻结；fresh_rule_proposal只是新规则建议，不是已放行的模型值。原料克重是release数据，不是另行实测。

变动菜谱：252；本次抽取：25；未审核模型门禁：422 → 422。

## 1. Spiedies (Kabobs) (RCP2_491808DE2CEB)

抽样方式：known regression；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 1/3 cup cooking oil（归一化 72.7 g）
- 1/2 cup vinegar（归一化 120.0 g）
- 2 teaspoons garlic powder（归一化 5.3 g）
- 1 teaspoon salt（归一化 6.1 g）
- 1/2 teaspoon black pepper（归一化 1.1 g）
- 1 teaspoon celery salt（归一化 3.6 g）
- 1 teaspoon garlic salt（归一化 6.0 g）
- 1 tablespoon parsley（归一化 3.8 g）
- 1 tablespoon rosemary（归一化 5.8 g）
- 1 bay leaf（归一化 0.2 g）
- 1 clove garlic（归一化 3.0 g）
- 5 lbs meat, cut into cubes (pork & chicken)（归一化 2268.0 g）

步骤证据：

Mix all ingredients and pour over meat.
Marinade in fridge for three days, stirring at least twice a day.
(This is important).
Remove meat from marinade; discard marinade.
Skewer meat and grill.
Serve with sliced Italian bread.
Cooked meat can be frozen and heated up.

人工意见：待确认。

## 2. Marilyn'S English Pasties (RCP2_CB386B8363E1)

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

人工意见：待确认。

## 3. Spicy Thai One Pot (RCP2_87CBA929A2C6)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 1 1/2 cups cold water（归一化 355.5 g）
- 2 tablespoons soy sauce（归一化 31.9 g）
- 1/4 teaspoon cayenne pepper（归一化 0.4 g）
- 1 lb meat, diced (chicken, beef, turkey, sausage... any will work)（归一化 453.6 g）
- 1 medium red bell pepper, seeded and chopped（归一化 120.0 g）
- 3/4 cup jasmine rice（归一化 138.8 g）
- 3 green onions, chopped (tops included)（归一化 45.0 g）
- 1 tablespoon minced cilantro（归一化 1.0 g）

步骤证据：

Combine water, soy sauce and cayenne pepper. Heat large wok or fry pan over high heat (Spray with cooking spray if using a "drier meat" like poultry). Add meat and stir fry for 4-5 minutes or until browned.
Add bell pepper. Stir fry for one more minute.
Mix in rice and soy sauce mixture. Bring to a boil, then reduce heat, cover and simmer for 20 minutes or until liquid is absorbed.
Mix in green onions and cilantro. Serve.

人工意见：待确认。

## 4. Cabbage And Beef Dish (RCP2_509FEF2160AC)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["beef"] | null |

原料证据：

- 1 lb. ground beef or turkey（归一化 453.6 g）
- 1 onion（归一化 110.0 g）
- 3 c. cabbage, shredded（归一化 267.0 g）
- 1 c. tomato soup（归一化 250.0 g）

步骤证据：

Brown ground beef or ground turkey and onion. Drain and season to taste. Spread in baking dish. Top with cabbage. Pour diluted tomato soup on top and cover. Bake at 350° for 1 hour. Makes 6 servings, 1/2 cup each.

人工意见：待确认。

## 5. Chappal Kebab (RCP2_F7D5083A01CE)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["beef"] | null |

原料证据：

- 1 tablespoon chickpea flour（归一化 5.8 g）
- 1 1/2 lbs ground beef (or ground lamb)（归一化 680.4 g）
- 6 -7 tablespoons cilantro, chopped（归一化 6.5 g）
- 2 -3 green chilies, chopped fine（归一化 112.5 g）
- 1 1/2 teaspoons cumin seeds（归一化 3.3 g）
- 1 1/2 teaspoons coriander seeds（归一化 1.4 g）
- 1 teaspoon ground black pepper（归一化 2.3 g）
- 1 1/4 teaspoons salt（归一化 7.6 g）
- 1/2 egg, beaten（归一化 25.0 g）
- 3 -4 tablespoons vegetable oil（归一化 47.7 g）

步骤证据：

Toast the cumin and coriander in a dry skillet until they start to pop, but take care not to burn them.
Put all ingredients into a big bowl and work it together with your hands, as if you were making a meatloaf. Once it has formed a workable mass, knead it for a few minutes to make the meat smoother.
Press into small patties, as thin as you can possibly make them. Mine are about five inches across when they're raw, but shrink a lot during cooking. I find pressing between two sheets of cling film (Saran Wrap or similar) helps me get a really fine patty in one piece.
Fry in a hot skillet in the vegetable oil until browned on both sides.

人工意见：待确认。

## 6. Khao Pad (Thai Fried Rice) (RCP2_B3CA4D294329)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 1 tablespoon vegetable oil（归一化 13.6 g）
- 1 tablespoon minced garlic（归一化 8.5 g）
- 2 eggs（归一化 100.0 g）
- 2 cups cooked rice, cooled（归一化 316.0 g）
- 1 tablespoon fish sauce（归一化 18.0 g）
- 1 tablespoon soy sauce（归一化 15.9 g）
- 1 cup cooked meat (e.g. shrimp, pork, chicken, etc.)（归一化 140.0 g）
- 2 teaspoons sugar（归一化 8.3 g）
- ½ teaspoon ground black pepper（归一化 1.1 g）
- Spring onion as desired, sliced（归一化 12.5 g）

步骤证据：

Heat up a frying pan or wok and add the oil, then the minced garlic. Stir fry until fragrant.
Add the eggs, and stir fry the eggs until cooked.
Add the rice and stir fry.
Season with fish sauce, soy sauce, and sugar, then continue frying until the rice is crumbly.
Add meat, pepper, and spring onions. Stir again until heated through, then transfer to a serving dish.

人工意见：待确认。

## 7. Chicken Adobo(Can Be Made With Pork Too) (RCP2_F5A97F6A48C9)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["chicken"] | null |

资料不完整：named pork but lists none。

原料证据：

- 3 lbs. chicken thighs, cut into serving pieces（归一化 1360.8 g）
- 1/2 c. white vinegar（归一化 120.0 g）
- 1/2 c. soy sauce（归一化 127.5 g）
- 1/4 c. peppercorns, crushed（归一化 28.0 g）
- 1 tsp. brown sugar（归一化 4.6 g）
- 5 garlic cloves, crushed（归一化 15.0 g）
- 3 bay leaves（归一化 0.6 g）
- salt, to taste（归一化 6.1 g）

步骤证据：

Combine all ingredients in a pan.
Cover and allow to marinate 1-3 hours.
Bring to a boil then lower heat and simmer for 30 minutes.
Uncover the pan and continue simmering an additional 15 minutes or until most of the liquid has evaporated and the chicken is light brown.
Serve with white rice.
Serves 4-6.

人工意见：待确认。

## 8. Cornish Finnish Michigan Pasties (RCP2_1BC59C8F7B88)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "one_bowl" |
| contains_staple | false | true |

原料证据：

- 4 1/2 cups all-purpose flour（归一化 562.5 g）
- 1 cup shortening（归一化 205.0 g）
- 1 1/4 cups ice water（归一化 296.2 g）
- 1 teaspoon salt（归一化 6.1 g）
- 5 1/2 cups thinly sliced potatoes（归一化 825.0 g）
- 2 carrots, shredded（归一化 122.0 g）
- 1 onion（归一化 110.0 g）
- 1/2 cup diced rutabaga（归一化 70.0 g）
- 1 1/2 lbs lean ground beef（归一化 680.4 g）
- 1/2 lb ground lean pork（归一化 226.8 g）
- 1 tablespoon salt（归一化 18.2 g）
- 1 teaspoon ground black pepper（归一化 2.3 g）
- 1 1/2 teaspoons msg (MSG)（归一化 6.2 g）
- 1 beef bouillon cube（归一化 4.0 g）
- 1/2 cup hot water（归一化 118.5 g）

步骤证据：

Whisk together flour and salt in a large bowl. Cut shortening. Make a well in the center of the mixture, and quickly stir in ice cold water. Form dough into a ball. Set aside.
Dissolve the bouillon cube in the hot water. Combine uncooked vegetables, uncooked meats, salt, pepper, monosodium glutamate (MSG), and bouillon.
Roll out pastry dough into 6 x 8 inch rectangles. Place about 1 1/2 cups of filling in the center of each rectangle. Bring 6 inch sides together, and seal. Cut a slit in the top of each pasty. Place on dull, not black, baking pans.
Bake at 425°F for 45 minutes.

人工意见：待确认。

## 9. Chicken & Noodle Laksa (RCP2_33694E3F32AF)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |
| protein_sources | ["chicken"] | null |

资料不完整：named chicken but lists none。

原料证据：

- 1/2 red chili（归一化 22.5 g）
- 2 stalks lemongrass（归一化 40.0 g）
- 4 garlic cloves（归一化 12.0 g）
- 1 inch ginger piece of（归一化 15.0 g）
- 8 ounces thai noodles（归一化 226.8 g）
- 1/2 onion large, finely chopped（归一化 55.0 g）

步骤证据：

Place the chili, lemongrass, garlic and ginger in a food processor or mortar and grind or bash to a rough paste.
Place the Pad Thai noodles in a large bowl and pour boiling water over the noodles. Allow to sit until pliable but still a bit firm to bite. This takes about 10 minutes. Drain the noodles.

人工意见：待确认。

## 10. Egg Filling For Pita Bread (RCP2_6E980A921C14)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "sauce" |
| protein_sources | ["egg"] | [] |
| flavor_tags | ["rich"] | [] |

原料证据：

- 3 oz. cream cheese（归一化 85.0 g）
- 1/4 c. mayonnaise（归一化 55.0 g）
- 3/4 tsp. dill weed（归一化 0.1 g）
- 1/2 tsp. salt（归一化 3.0 g）
- 1/2 tsp. dry mustard（归一化 1.0 g）
- 8 hard-boiled eggs, chopped fine（归一化 400.0 g）
- 1 c. ripe olives, sliced（归一化 135.0 g）
- 1/2 c. chopped celery（归一化 50.5 g）
- 2 Tbsp. chopped onion（归一化 20.0 g）

步骤证据：

Blend cream cheese, mayonnaise and seasonings.	Stir in remaining ingredients.
Regular bread may be used for a sandwich.

人工意见：待确认。

## 11. Thai Shrimp And Snow Peas (RCP2_7C5C5294C996)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | "protein_main" |
| contains_staple | true | false |

原料证据：

- 1/2 cup lemon juice（归一化 124.0 g）
- 1/4 cup soy sauce（归一化 63.8 g）
- 2 tablespoons brown sugar（归一化 27.5 g）
- 2 teaspoons fish sauce（归一化 12.0 g）
- 1 teaspoon red pepper flakes, or to taste（归一化 1.8 g）
- 1/2 teaspoon cornstarch, or as desired (optional)（归一化 1.3 g）
- 6 tablespoons olive oil, divided（归一化 81.0 g）
- 10 cloves garlic, minced（归一化 30.0 g）
- 2 jalapeno peppers, seeded and chopped（归一化 28.0 g）
- 10 whole black peppercorns（归一化 0.5 g）
- 2 onions, sliced（归一化 220.0 g）
- 2 (6 ounce) packages frozen sugar snap peas, thawed（归一化 340.0 g）
- 12 cherry tomatoes（归一化 1476.0 g）
- 1 yellow bell pepper, thinly sliced（归一化 120.0 g）
- 1 red bell pepper, thinly sliced（归一化 120.0 g）
- 1 green bell pepper, thinly sliced（归一化 120.0 g）
- 2 pounds fresh shrimp, peeled and deveined（归一化 907.2 g）
- 1/4 cup chopped fresh cilantro（归一化 4.0 g）
- 1/4 cup chopped fresh mint（归一化 10.0 g）
- 2 cups cooked long-grain rice（归一化 316.0 g）
- 1 cup fresh bean sprouts, or to taste（归一化 104.0 g）

步骤证据：

Bring lemon juice, soy sauce, brown sugar, fish sauce, red pepper flakes, and cornstarch to a simmer in a saucepan over medium heat until sauce is thickened, 3 to 5 minutes.
Heat 2 tablespoons olive oil in a non-stick skillet over medium heat. Add garlic, jalapeno peppers, and peppercorns; cook and stir until fragrant, 1 to 2 minutes. Add remaining olive oil, onions, snap peas, cherry tomatoes, yellow bell pepper, red bell pepper, and green bell pepper; cook and stir until peppers are tender, about 8 minutes. Add shrimp, cilantro, and mint; cook and stir until shrimp is bright pink on the outside and the meat is opaque, 2 to 3 minutes.
Place shrimp mixture on a serving platter with rice and bean sprouts; pour sauce on top.

人工意见：待确认。

## 12. Singapore Noodles (RCP2_4A61D1E39E99)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |
| protein_sources | ["pork"] | null |

原料证据：

- 1 lb ground pork (or beef or poultry)（归一化 453.6 g）
- 5 garlic cloves, minced（归一化 15.0 g）
- 3 teaspoons ground ginger（归一化 6.0 g）
- 1/4 teaspoon cayenne（归一化 0.4 g）
- 1 1/2 tablespoons curry powder（归一化 9.0 g）
- 1/3 cup green onion, slivered (or chopped)（归一化 33.3 g）
- 1/4 cup oyster sauce（归一化 67.5 g）
- 2 teaspoons soy sauce（归一化 10.6 g）
- 1 lb spaghetti（归一化 453.6 g）

步骤证据：

In a wok or large frying pan, scramble-fry pork with garlic, ginger, cayenne, curry, and green onion. (If you're not using lean meat, you may want to partially cook the meat by itself and then drain most of the fat before adding the other ingredients.).
Meanwhile, cook spaghetti according to package instructions.
Add oyster sauce and soy sauce to meat mixture and toss well to mix thoroughly.
Drain spaghetti and add to meat. Toss to mix and serve.

人工意见：待确认。

## 13. Lasagna Style Bow Tie Dish (RCP2_44870004D5FB)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 8 oz. bow tie pasta（归一化 226.8 g）
- 1 Tbsp. oil（归一化 13.6 g）
- 1 chopped onion（归一化 110.0 g）
- 1/2 lb. chopped meat（归一化 226.8 g）
- 14 oz. spaghetti sauce（归一化 396.9 g）
- 1 c. low-fat cottage cheese（归一化 226.0 g）
- 1 egg（归一化 50.0 g）
- 2 Tbsp. Parmesan cheese（归一化 12.5 g）
- 4 oz. Mozzarella cheese, grated（归一化 113.4 g）

步骤证据：

Preheat oven to 425°.
Grease an 8-inch square baking dish. Partially cook pasta 1/2 time required on package.
In skillet, heat oil.
Saute onion 1 minute.
Stir in ground meat.
Cook until browned.
Add spaghetti sauce and bring to boil.
Cover and cook 5 minutes.

人工意见：待确认。

## 14. Parmesan Chicken (RCP2_B11FE7812622)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["chicken"] | null |

资料不完整：named chicken but lists none。

原料证据：

- 1 c. Miracle Whip（归一化 220.0 g）
- 1/2 c. grated Parmesan cheese（归一化 50.0 g）
- 2 tsp. oregano（归一化 3.6 g）

步骤证据：

Spoon over 2 to 3 pounds chicken.
Bake 45 minutes at 375°. Serves 4 to 6.

人工意见：待确认。

## 15. Chicken Curry (RCP2_0447589B2FD3)

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

人工意见：待确认。

## 16. Pumpkin Fried Rice (RCP2_586E24DE73A6)

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

人工意见：待确认。

## 17. Satay (RCP2_21ADEFC9A0C2)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 2 Tbsp. curry powder（归一化 12.0 g）
- 2 Tbsp. sugar（归一化 25.0 g）
- 1/2 c. salad oil（归一化 109.0 g）
- 1/2 c. soy sauce（归一化 127.5 g）
- 4 cloves garlic, pressed（归一化 12.0 g）
- 2 to 3 lb. meat（归一化 1134.0 g）

步骤证据：

Mix first 5 ingredients in a bowl.
This makes an excellent marinade for any kind of meat, whether it's game or domestic. Marinate meat 4 hours or longer and then barbecue or stir-fry the meat.

人工意见：待确认。

## 18. Mexican Crab Salad (RCP2_010D47D8B41A)

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

人工意见：待确认。

## 19. Stuffed Green Peppers (RCP2_FAC00DA2B400)

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

人工意见：待确认。

## 20. Singapore Chicken Noodles (RCP2_7C8F0E835E9F)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | "protein_main" |
| contains_staple | true | false |

原料证据：

- 1 teaspoon olive oil（归一化 4.5 g）
- 2 chicken breasts, cut into strips（归一化 348.0 g）
- 1 red bell pepper, cut into strips（归一化 120.0 g）
- 4 baby corn（归一化 360.0 g）
- 1/2 cup chicken broth（归一化 118.3 g）
- 2 eggs, beaten（归一化 100.0 g）
- 2 tablespoons fresh cilantro, chopped（归一化 2.0 g）
- 2 teaspoons soy sauce（归一化 10.6 g）
- 3 ounces egg noodles (cooked according to packet instructions)（归一化 85.0 g）
- 1 tablespoon sesame oil（归一化 13.6 g）
- 1 dash Tabasco sauce（归一化 0.6 g）

步骤证据：

Heat the oil in a wok and stir-fry the chicken, pepper and baby sweetcorn. Add the chicken broth and stir until chicken is cooked through.
Add the eggs and stir until scrambled.
Add the cilantro, soy sauce, noodles, sesame oil and Tabasco.
Garnish with a handful of coriander to serve.

人工意见：待确认。

## 21. Israeli Kabobs (RCP2_4AC9B1A326C6)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["beef"] | null |

原料证据：

- 2 lbs ground beef (or lamb)（归一化 907.2 g）
- 1 minced onion（归一化 110.0 g）
- 1 teaspoon garlic powder（归一化 2.7 g）
- 1 teaspoon salt（归一化 6.1 g）
- fresh ground pepper（归一化 1.1 g）
- 1/2 cup fresh parsley, minced（归一化 30.0 g）
- 2 teaspoons of fresh mint (or dried)（归一化 1.7 g）
- 1 teaspoon allspice（归一化 1.9 g）
- 1 teaspoon cumin（归一化 2.2 g）
- 1/2 teaspoon ginger（归一化 1.0 g）
- 2 eggs, beaten（归一化 100.0 g）

步骤证据：

Combine ingedients in a large bowl and mix well.
Form into oblong patties (or mini-hamburger shapes).
Place patties onto sprayed broiler pan and place in oven.
Broil for about 10 minutes on each side.
Serve with hummus, pita and Israeli salad!
B'tayavon!

人工意见：待确认。

## 22. Tacos (RCP2_686557404CA1)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "one_bowl" | null |
| contains_staple | true | null |

**仍受模型门禁拦截；历史模型字段不作为新规则已核实事实。**

原料证据：

- 1 lb. ground meat（归一化 453.6 g）
- 1/2 tsp. garlic powder（归一化 1.3 g）
- 1/2 tsp. salt（归一化 3.0 g）
- 1/4 tsp. pepper（归一化 0.6 g）
- 1 c. mashed potatoes（归一化 210.0 g）
- 12 corn tortillas（归一化 540.0 g）

步骤证据：

Brown meat in skillet.
Add garlic, salt and pepper.
Add small amount of water and cook slowly until tender.
Add mashed potatoes and mix well with meat.
Warm tortillas in grease in skillet; remove and place 1 tablespoon of meat mixture on center of tortilla.
Fold over and pin with toothpick.
Fry taco in grease until brown; drain well on paper towel.
Serve with chopped onions, lettuce, canned, peeled green chili peppers and hot sauce.

人工意见：待确认。

## 23. Gochujang Pulled Pork In The Slow Cooker (RCP2_951E934B1396)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | null | "protein_main" |
| contains_staple | null | false |

原料证据：

- 2/3 cup gochujang (Korean hot pepper paste)（归一化 181.3 g）
- 1 large onion, thinly sliced（归一化 110.0 g）
- 1/2 cup apple cider vinegar（归一化 119.5 g）
- 1/2 cup chicken stock（归一化 118.3 g）
- 1/4 cup honey（归一化 84.0 g）
- 1/4 cup brown sugar（归一化 55.0 g）
- 2 tablespoons fresh ginger（归一化 12.0 g）
- 1 tablespoon soy sauce（归一化 15.9 g）
- 1 tablespoon yellow mustard（归一化 15.5 g）
- 3 cloves garlic, minced（归一化 9.0 g）
- 1 tablespoon ground cinnamon（归一化 7.8 g）
- 1 teaspoon salt（归一化 6.1 g）
- 5 sprigs thyme, stemmed（归一化 5.0 g）
- 1/2 teaspoon ground black pepper（归一化 1.1 g）
- 1 (4 pound) boneless pork shoulder roast, trimmed（归一化 1814.4 g）
- 1/4 cup butter, divided（归一化 56.8 g）
- 1 tablespoon all-purpose flour（归一化 7.8 g）
- 8 hamburger buns, split（归一化 344.0 g）
- 3 green onions, thinly sliced（归一化 45.0 g）

步骤证据：

Combine gochujang, onion, vinegar, chicken stock, honey, brown sugar, ginger, soy sauce, mustard, garlic, cinnamon, salt, thyme, and black pepper together in a large bowl and mix well.
Dredge pork in the gochujang sauce on all sides. Pour sauce into a slow cooker and add the pork. Spoon some of the sauce on top of the pork. Cover and cook on Low until pork roast shreds easily with a fork, about 8 hours.
Preheat oven to 350 degrees F (175 degrees C).
Place roast in a large bowl and shred the meat with 2 forks. Pour the sauce from the slow cooker into a pot over medium-high heat. Cover and bring to a boil. Uncover; reduce heat to a simmer.
Mix 1 tablespoon butter and flour in a small bowl; combine with the sauce in the pot and mix well. Cook until heated through and slightly thickened, about 5 minutes. Remove from heat and stir again.
Spread remaining 3 tablespoons butter over insides of buns. Place on a baking sheet.
Toast in the preheated oven until golden brown, 5 to 7 minutes.
Pour the sauce into the bowl with the shredded pork and mix. Top pork with green onions. Spoon pork over the toasted buns.

人工意见：待确认。

## 24. Herbed Cornish Pasties (RCP2_44A2C72808DA)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | "one_bowl" |
| contains_staple | false | true |

原料证据：

- 2 cups all-purpose flour（归一化 250.0 g）
- 1 teaspoon salt（归一化 6.1 g）
- 1/2 teaspoon dried basil（归一化 0.2 g）
- 1/2 teaspoon dried thyme（归一化 0.3 g）
- 1/2 cup shortening（归一化 102.5 g）
- 1/4 cup butter（归一化 56.8 g）
- 5 to 6 tablespoons ice water（归一化 81.5 g）
- 1 pound boneless beef chuck, cut into 1/2-inch cubes（归一化 453.6 g）
- 2 tablespoons canola oil, divided（归一化 27.2 g）
- 1 teaspoon salt（归一化 6.1 g）
- 1/8 teaspoon pepper（归一化 0.3 g）
- 2 tablespoons all-purpose flour（归一化 15.6 g）
- 1 cup water（归一化 237.0 g）
- 2 medium potatoes, peeled and diced（归一化 426.0 g）
- 1/2 cup diced carrot（归一化 64.0 g）
- 1/2 cup diced onion（归一化 80.0 g）
- 1 egg, lightly beaten（归一化 50.0 g）

步骤证据：

In a large bowl, combine the flour, salt, basil and thyme; cut in shortening and butter until crumbly. Add water, 1 tablespoon at a time, tossing lightly with a fork until mixture forms a ball. Cover and chill for at least 30 minutes.
Meanwhile, in a skillet, brown beef in 1 tablespoon oil until no longer pink; sprinkle with salt and pepper. Remove with a slotted spoon; set aside. Add remaining oil to skillet; gradually stir in flour until smooth. Cook and stir over medium heat for about 2-3 minutes or until lightly browned. Gradually add water; whisk until smooth.
Return beef to skillet. Reduce heat; cover and simmer for 20 minutes. Add the potatoes, carrot and onion. Cover and simmer for 25 minutes or until tender. Remove from the heat; cool.
Divide pastry into four equal portions. On a lightly floured surface, roll out one portion into a 9-in. circle. Mound 3/4 cup filling on half of circle. Moisten edges with water; fold dough over filling and press edges with a fork to seal.
Place on an ungreased
. Repeat with remaining pastry and filling. Cut three slits in top of each; brush with egg.
Bake at 400° for 25-30 minutes or until golden brown.

人工意见：待确认。

## 25. Cabbage Lasagna(Low-Fat Recipe) (RCP2_7FB565152BDB)

抽样方式：seeded random changed case；原菜类：main。

| 变动字段 | 原值 | 新值 |
|---|---|---|
| meal_role | "protein_main" | null |
| contains_staple | false | null |
| protein_sources | ["beef"] | null |

原料证据：

- 1 small head cabbage, shredded（归一化 100.0 g）
- 18 oz. tomato juice（归一化 510.3 g）
- 1 c. fresh mushrooms, sliced（归一化 70.0 g）
- 1/2 green pepper, diced（归一化 60.0 g）
- 1/4 c. onion, diced（归一化 40.0 g）
- 1 lb. lean ground beef or turkey（归一化 453.6 g）
- 1 c. low-fat cheese, shredded（归一化 113.0 g）

步骤证据：

Brown ground beef with onion and green pepper. Drain well. Add sauce.
In
a large casserole, sprayed with nonstick cooking spray, layer cabbage, meat, cheese and mushrooms.
Cover and bake at 350° until cabbage is tender, about 1 hour.
Great dish if you love cabbage.

人工意见：待确认。
