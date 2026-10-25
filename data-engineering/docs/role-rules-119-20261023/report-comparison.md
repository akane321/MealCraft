# Developer-report comparison

Baseline revision is recorded in review.json. No timing report was updated. These are developer regressions, not held-out capability or accuracy claims. This compares archived base reports with regenerated developer reports. It is not a separate fresh baseline replay or a single-rule ablation.

## full-default

Checks: PASS → PASS. JSON byte-identical.

### one-adult

Unchanged; checks PASS.

New selected titles: none.

No longer selected: none.

### four-with-vegetarian

Unchanged; checks PASS.

New selected titles: none.

No longer selected: none.

### six-tight-budget

Unchanged; checks PASS.

New selected titles: none.

No longer selected: none.

### two-no-oven-ten-days

Unchanged; checks PASS.

New selected titles: none.

No longer selected: none.

### seven-with-young-children

Unchanged; checks PASS.

New selected titles: none.

No longer selected: none.

## shared-dish

Checks: PASS → PASS. JSON changed.

### four-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} | {"Ann": 2044, "Ben": 7570, "Kai": 7570, "Mei": 7570} |
| recipe_pool_servable | 7565 | 7570 |

### two-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Lin": 2040, "Raj": 7565} | {"Lin": 2044, "Raj": 7570} |
| recipe_pool_servable | 7565 | 7570 |

### with-a-child

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 7565, "Ben": 7565, "Mei": 7108} | {"Ann": 7570, "Ben": 7570, "Mei": 7113} |
| recipe_pool_servable | 7565 | 7570 |

### weekday-lunch-away

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} | {"Ann": 2044, "Ben": 7570, "Kai": 7570, "Mei": 7570} |
| recipe_pool_servable | 7565 | 7570 |

### weekend-guest

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} | {"Ann": 2044, "Ben": 7570, "Kai": 7570, "Mei": 7570} |
| recipe_pool_servable | 7565 | 7570 |

### peanut-whole-household

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 7140, "Ben": 7140, "Kai": 7140, "Mei": 7140} | {"Ann": 7145, "Ben": 7145, "Kai": 7145, "Mei": 7145} |
| recipe_pool_servable | 7140 | 7145 |

### peanut-only-mei-avoids

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 7565, "Ben": 7565, "Kai": 7565, "Mei": 7140} | {"Ann": 7570, "Ben": 7570, "Kai": 7570, "Mei": 7145} |
| recipe_pool_servable | 7565 | 7570 |

### mixed-diets

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Ann": 2040, "Ben": 7565, "Kai": 4735, "Mei": 7565} | {"Ann": 2044, "Ben": 7570, "Kai": 4737, "Mei": 7570} |
| recipe_pool_servable | 7565 | 7570 |

### six-one-vegetarian

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| recipe_pool_by_member | {"Adult 1": 2040, "Adult 2": 7565, "Adult 3": 7565, "Adult 4": 7565, "Adult 5": 7565, "Adult 6": 7565} | {"Adult 1": 2044, "Adult 2": 7570, "Adult 3": 7570, "Adult 4": 7570, "Adult 5": 7570, "Adult 6": 7570} |
| recipe_pool_servable | 7565 | 7570 |

### tight-budget

Changed; checks PASS.

| Metric | Before | After |
|---|---|---|
| energy_attainment_by_member | {"Ann": 1.275, "Ben": 1.328, "Kai": 1.329, "Mei": 1.335} | {"Ann": 1.296, "Ben": 1.35, "Kai": 1.351, "Mei": 1.356} |
| lowest_energy_attainment | 1.275 | 1.296 |
| recipe_pool_by_member | {"Ann": 2040, "Ben": 7565, "Kai": 7565, "Mei": 7565} | {"Ann": 2044, "Ben": 7570, "Kai": 7570, "Mei": 7570} |
| recipe_pool_servable | 7565 | 7570 |

## household-rules

Checks: PASS → PASS. JSON byte-identical.

## legacy-dev

Checks: PASS → PASS. JSON byte-identical.
