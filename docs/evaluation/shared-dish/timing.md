# Shared dishes: wall time

> Wall time on the machine that generated it, so it differs by machine and is kept out of `latest.*`. The variety pass always runs every start (ADR-0080), so the plans do not depend on the machine. ADR-0079 sets how long is acceptable by how hard the request is: a simple request should still come back within about 4 s, and every household here has members with their own limits, so these are the complex requests it allows up to about 60 s. Only past that is a case marked over. The `merged` column shows how much of the time the shared-dish model added. A request is never cut short to meet either figure, and speed is the algorithm layer's to fix, never by dropping a rule or relaxing a limit (section 0.8).

Median of the shared arrangement: 33.42 s. Slowest: 159.84 s.

Over ~60 s: weekend-guest, six-one-vegetarian.

| Case | merged (s) | shared (s) | Against the ADR-0079 guidance |
|---|---:|---:|:---|
| `four-one-vegetarian` | 24.25 | 44.51 | within the guidance for a complex request |
| `two-one-vegetarian` | 5.55 | 8.37 | within the guidance for a complex request |
| `with-a-child` | 16.17 | 22.33 | within the guidance for a complex request |
| `weekday-lunch-away` | 22.1 | 45.56 | within the guidance for a complex request |
| `weekend-guest` | 54.36 | 130.77 | over ~60 s |
| `peanut-whole-household` | 20.14 | 18.04 | within the guidance for a complex request |
| `peanut-only-mei-avoids` | 12.78 | 16.35 | within the guidance for a complex request |
| `mixed-diets` | 7.58 | 17.75 | within the guidance for a complex request |
| `six-one-vegetarian` | 81.56 | 159.84 | over ~60 s |
| `tight-budget` | 44.8 | 59.01 | within the guidance for a complex request |

- `four-one-vegetarian` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `two-one-vegetarian` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `with-a-child` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `weekday-lunch-away` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `weekend-guest` (over ~60 s): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `peanut-whole-household` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `peanut-only-mei-avoids` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `mixed-diets` (within the guidance for a complex request): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `six-one-vegetarian` (over ~60 s): one beam search, which builds each meal's dish combinations and checks every one as a real meal (`meal_beam._meal_options` -> `meal_permitted` -> `real_meal_issues`): 40-75% of the run, a third to a half of it `member_coverage.member_can_eat` asked again for every member, dish and combination with nothing cached per member and recipe. Reading the candidates takes about 2.5 s, and topping the packet up for every member group (`product_path._packet_covering`, each ranked dish judged by the option this household cooks) about as long.

- `tight-budget` (within the guidance for a complex request): four beam searches and sixteen variety starts: no week the ranked search keeps is filled with no dish twice under its budget, so the three budget-led searches (`product_path.limit_led`, about 14% of the run) and the variety pass (`meal_beam.vary_within_budget`, about 72%) both run. Every swap the variety pass tries checks the meal's coverage again, so `member_can_eat` alone is about 35% (7.0 million calls). Upgrade path: cache the member checks per member and recipe, and share the meal checks between the four searches.

The last widening step of a meal's options (`meal_beam.MEAL_OPTION_WIDENING`, every eligible dish of every role) ran in no case above. Forced on every slot of `mixed-diets` (shared) it checked 177 combinations for a breakfast in 0.01 s and 32,549 for a three-role lunch in 2.1 s. A five-role dinner, a raw product of about 2e10 combinations (about 3 µs each, so hours unbounded), stopped at its budget of `meal_beam.LAST_STEP_COMBINATIONS` (262,144) in 0.35 s. Those were the top-ranked dishes of its first roles with every dish of the rest, and none made a meal, so forced alone that dinner would be refused, as the four-times step refused such a slot before.
