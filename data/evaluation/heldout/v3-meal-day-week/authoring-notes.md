# Authoring notes: mdw-ho-001 to mdw-ho-060 (current after review round 2)

The episodes are generated from `specs.py` by `build.py`. `lib.py` holds the helpers and `conflicts.py` the conflict texts. `diag.py`, `nutprobe.py`, `trial.py` and `budgetsearch.py` are read-only probes over the packet files. `check.py` drew every pool and proved every label.

In these notes a role with courses side/salad is called a "side" (its role id is `vegetable`, as the format requires). A "?" marks an optional role. Budgets are shown with their per-person, per-planned-meal amount.

## Per episode

### shape_change (12, all feasible; 8 zh / 4 en)
- 001 zh, 4 people, dinner main+side+soup, no beef (including beef stock). Change: take the soup off every dinner, keeping the main and side.
- 002 zh, 2 people, one-dish lunch and one-main dinner. Change: add breakfast on Saturday and Sunday only.
- 003 en, 5 people, breakfast, one-dish lunch and dinner main+side+soup. Change: drop lunch Monday to Friday and keep the weekend lunches.
- 004 zh, 3 people, dinner main+side?, shellfish allergy. Change: add a soup to Wednesday and Friday dinners, appended after the optional side.
- 005 zh, 6 people, lunch main+side and dinner main+side+soup, 90 minutes. Change: lunch becomes the one-dish preset for the whole week.
- 006 en, 2 people, one-main dinner, 40 minutes. Change: add a side to every dinner; the two-dish meal must still fit 40 minutes.
- 007 zh, 5 people, dinner main+side+soup, peanut allergy. Change: add a second main to Saturday and Sunday dinners.
- 008 zh, 2 people, breakfast and dinner main+side?. Change: add lunch every day; no dishes are named, so the default one-dish preset applies.
- 009 en, 3 vegetarian flatmates, lunch main+side and dinner main+side?. Change: drop the lunch side on Tuesday and Thursday and keep those mains.
- 010 zh, 4 people, three meals. Change: drop Sunday breakfast only.
- 011 zh, 8 people, dinner two mains+side+soup. Change: Friday dinner becomes one main.
- 012 en, 4 people, one-dish lunch and dinner main+side+soup, egg allergy. Change: drop Saturday dinner.

### meals_per_day (9; 4 infeasible)
- 013 en, INFEASIBLE, 4 people, three meals with a main+side+soup dinner, 40 minutes a meal. No three-dish dinner fits in 40 minutes.
- 014 zh, 2 people, breakfast and dinner main+side?, egg, peanut and tree-nut allergies. Tests that the allergies apply at breakfast.
- 015 en, INFEASIBLE, 4 people, three meals, gluten and egg allergy. No breakfast in the pool fits.
- 016 zh, 3 people, breakfast and dinner, gluten and dairy allergies. Feasible, with thin breakfasts.
- 017 en, 6 people, three meals, gluten-free and dairy-free diet tags. Feasible; tests breakfasts that meet both tags.
- 018 zh, 2 people, breakfast and lunch main+side only, 40 minutes. "No pork" here means pork cuts, bacon and ham, processed foods that may contain pork (sausage, hot dog, pot stickers, canned baked beans), and liver and gelatin whatever their source; the request says so (肝和明胶不论来源都不吃).
- 019 en, 4 people, three meals, milk and egg allergy. Feasible on a few safe breakfasts.
- 020 zh, INFEASIBLE, 5 vegetarians, a helper cooks three meals with a main+side+soup dinner, 45 minutes. The one vegetarian main plus a soup and side need 59 minutes.
- 021 en, INFEASIBLE, 1 person, lunch main+side and one-main dinner, 20 minutes, no beef. No two-dish lunch fits in 20 minutes.

### composition (9; 4 infeasible)
- 022 en, 7 people, dinner two mains+two sides+soup, 120 minutes. Tests distinct dishes per role and portion shares.
- 023 zh, 4 people, dinner two mains+side+soup?, 60 minutes. The optional soup must never displace a required dish.
- 024 en, INFEASIBLE, 10 people, six-dish dinner (three mains, two sides, soup) in 60 minutes.
- 025 zh, 3 people, lunch main+side and dinner main+side+soup, all required.
- 026 zh, 3 vegetarians, dinner two different vegetarian mains+side. Vegetarian mains are scarce, so the test is distinctness.
- 027 en, INFEASIBLE, 5 people, one-dish lunch and dinner main+side+soup in 30 minutes.
- 028 zh, 8 people, one-dish lunch and dinner two mains+two sides+soup?, 90 minutes. Tests optional-role ordering on a large meal.
- 029 en, INFEASIBLE, 4 people, lunch main+side and dinner two mains+side+soup in 45 minutes.
- 030 zh, INFEASIBLE, 2 people, breakfast and dinner main+soup (no side), both required, 25 minutes. The main and soup need at least 33.5 minutes.

### budget (9, all feasible; each 15–25 % above the witness and ≥ S$2.50 per person per meal)
- 031 en, 4 people, dinner main+side+soup, S$85 (S$3.04 per person per meal). Tests whole-package pricing.
- 032 zh, 1 person working from home, one-dish lunch and dinner main+side?, S$56 (S$4.00). Lunch and dinner share one budget and share packages.
- 033 en, family of 4, dinner two mains+side+soup, S$100 (S$3.57). Tests scaling to four people without dropping the second main.
- 034 zh, family of 3, dinner main+side?, S$66 (S$3.14). Tests scaling to three people and choosing where the optional side fits the budget.
- 035 en, 1 person, three one-dish meals, S$75 (S$3.57). Tests sharing packages across the week.
- 036 zh, couple, dinner main+side+soup, no pork (cuts, bacon, ham and processed foods that may contain pork), S$47 (S$3.36).
- 037 en, 3 flatmates, dinner main+side+soup, joint kitty S$70 (S$3.33). The trap is reading the kitty as each person's share.
- 038 zh, a helper cooking for a family of 3, dinner two mains+side+soup, S$62 (S$2.95).
- 039 en, 3 vegetarian flatmates, one-dish lunch and one-main dinner, shared S$155 (S$3.69).

### safety_diet (9; 5 infeasible)
- 040 en, INFEASIBLE, 3 people, breakfast and dinner, dairy, egg and gluten allergy. No breakfast in the pool fits.
- 041 zh, INFEASIBLE, 4 people, Buddhist vegetarians avoiding the five pungent roots (each one listed), dinner main+side?. All three vegetarian mains in the pool use garlic or onion.
- 042 en, INFEASIBLE, 4-person vegan family with no mushrooms, one-dish lunch and dinner main+side?. No main in the pool is both vegan and mushroom-free.
- 043 zh, INFEASIBLE, vegan and gluten-free couple, dinner main+side+soup, 40 minutes. The only soup that is both vegan and gluten-free takes 60 minutes hands-on.
- 044 en, 4 people, three meals, peanut and tree-nut allergies, each named.
- 045 zh, 3 people, breakfast and dinner, fish and shellfish allergy including the sauces, no beef or beef stock.
- 046 en, 4 people, lunch main+side and dinner main+side+soup, sesame, soy and gluten allergies. Tests tamari and tofu as false "safe" swaps.
- 047 zh, 3 people, three meals, dairy-free diet tag, 羊肉 meaning both sheep and goat.
- 048 en, INFEASIBLE, 6 people, breakfast and dinner, gluten-free diet, egg and milk allergy, no mushrooms. No breakfast in the pool fits.

### nutrition_per_day (7, all feasible; each target is the household's own, with no illness or doctor)
- 049 en, 2 people, three meals, protein ≥ 60 g a day.
- 050 zh, 4 people, dinner main+side+soup, sodium ≤ 900 mg from the dinner.
- 051 en, 3 people, breakfast and dinner, 700 to 1,300 kcal.
- 052 zh, 2 people, three meals, sugar ≤ 40 g and sodium ≤ 2,000 mg.
- 053 en, 5 people, lunch main+side and dinner main+side?, protein ≥ 30 g and fat ≤ 40 g.
- 054 zh, 3 people, dinner main+side+soup, carbohydrate ≤ 45 g and sodium ≤ 1,200 mg, using the 0.6/0.4 shares.
- 055 en, 4 people, three meals with a three-dish dinner, carbohydrate ≤ 200 g and 1,000 to 2,000 kcal.

### variety (5, all feasible)
- 056 en, 3 people, three meals, no dish twice all week, breakfasts included.
- 057 zh, 5 people, dinner main+side+soup, no dish twice. Sides and soups are the easy repeats.
- 058 en, 2 people, breakfast and dinner, egg allergy, no repeats. Seven distinct egg-free breakfasts are needed.
- 059 zh, 4 people, one-dish lunch and dinner main+side?, no repeats including lunch-to-dinner reuse. "No pork" here means pork cuts, bacon, ham and processed foods that may contain pork. Liver and gelatin are not excluded, because the request does not mention them.
- 060 en, 6 people, dinner two different mains+side, 90 minutes, no repeats.

## Ambiguities and how I resolved them

1. **Honest labels.** 014, 016, 017 and 019 were first written as infeasible attempts and came out feasible; I kept them feasible. Seven of the 13 infeasible episodes fail on a time limit. Attempts to make a safety or meals-per-day episode fail without one (adding soy to 043, egg to 044 or 046, dairy to 014, a third vegetarian main to 026) came out feasible, and I left those episodes unchanged.
2. **"No beef"** includes `beef_or_turkey`, because turkey is not buyable, and beef broth, because each request says stock.
3. **"No pork"** follows rule 7: pork cuts, bacon, ham, sausage, hot dog, gyoza and baked_beans, and every request names these processed foods. Liver and gelatin are excluded only in 018, whose request says it avoids them whatever their source. Generic broth, bouillon and gravy mix are not excluded.
4. **五辛 (041)** is spelled out item by item. 韭菜 maps to `chives` and 韭葱 to `leek`. 羊肉 (047) is lamb, lamb_chop and goat.
5. **"Coeliac" in 015 and 048** is a safety statement, not a nutrition one, so rule 3 does not apply. The owner confirmed this in round 2.
6. **Budgets.** In 032 and 033 the cheapest proven week over the whole pool used a recipe marked not plannable, so the plannable-only week cost more. I chose the round-2 households so that the whole-pool week, the plannable-only week and the fixture-first pricing all fit the 15–25 % band and the S$2.50 floor. The `budgetsearch.py` output lists the options I considered.
7. **Relaxations.** For the no-main infeasibilities (041, 042) only `plan_shape` is offered. Asking the household to give up its diet is not a reasonable relaxation.
