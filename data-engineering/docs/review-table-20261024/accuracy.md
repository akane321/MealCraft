# Sample accuracy of recipe-tags-v1/review-table-20261024

Filled sample: SHA-256 `15b2d33b0fc77f9ac770ee8a6f5d24eedf0f8f1b1d2f721fd952fa1e3645b7c0`; drawn: `sample.json` (46 recipes, seed 20261024). Only rows marked 是 (checked in person) count; a value this script cannot read counts neither way and is listed for the reviewer to fill again.

| Stratum | Rows | Checked | Agree | Accuracy | Unchecked | Checked, no value | Unrecognized, refill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 表导入层 (`table`) | 60 | 60 | 48 | 80.0% | 0 | 0 | 0 |
| 规则已定层 (`rule_decided`) | 32 | 32 | 28 | 87.5% | 0 | 0 | 0 |
| 规则已定：规则值等于模型原值 (`rule_equals_model`) | 17 | 17 | 17 | 100.0% | 0 | 0 | 0 |
| 规则已定：规则值不同于模型原值 (`rule_differs_from_model`) | 15 | 15 | 11 | 73.3% | 0 | 0 | 0 |
| 合计 (`all`) | 92 | 92 | 76 | 82.6% | 0 | 0 | 0 |

| Field | Rows | Checked | Agree | Accuracy | Unchecked | Checked, no value | Unrecognized, refill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `meal_role` | 41 | 41 | 30 | 73.2% | 0 | 0 | 0 |
| `contains_staple` | 41 | 41 | 37 | 90.2% | 0 | 0 | 0 |
| `protein_sources` | 10 | 10 | 9 | 90.0% | 0 | 0 | 0 |

无法识别，请重填: 0 rows.


Disagreements: 16.

- RCP2_1729D7258E04 Egg Filling For Sushi: `meal_role` batch `sauce`, reviewer `snack`
- RCP2_1729D7258E04 Egg Filling For Sushi: `protein_sources` batch `[]`, reviewer `egg`
- RCP2_290971CF4730 Mexican Wedding Rings: `meal_role` batch `snack`, reviewer `dessert`
- RCP2_49CA27EAC641 Alfajores De Maizena: `meal_role` batch `snack`, reviewer `dessert`
- RCP2_75BFE1C39E34 Taco Casserole: `meal_role` batch `sauce`, reviewer `staple`
- RCP2_75BFE1C39E34 Taco Casserole: `contains_staple` batch `false`, reviewer `true`
- RCP2_8F83C05E5E00 Siopao (Filipino Steamed Buns): `meal_role` batch `sauce`, reviewer `staple`
- RCP2_8F83C05E5E00 Siopao (Filipino Steamed Buns): `contains_staple` batch `false`, reviewer `true`
- RCP2_A887D44E2FC0 Sauerkraut pierogii: `meal_role` batch `snack`, reviewer `staple`
- RCP2_A887D44E2FC0 Sauerkraut pierogii: `contains_staple` batch `false`, reviewer `true`
- RCP2_BBA025B49BA6 Pierogi: `meal_role` batch `one_bowl`, reviewer `staple`
- RCP2_C81AEF8EF1AC Onion Creme Brulee: `meal_role` batch `vegetable`, reviewer `snack`
- RCP2_E8D667BA918A Fake Feta: `meal_role` batch `sauce`, reviewer `snack`
- RCP2_ED8C37EACE4D Mock Feta Cheese ( Vegan Substitute ): `meal_role` batch `sauce`, reviewer `snack`
- RCP2_F9AC64939A2C Welsh Rarebit: `meal_role` batch `sauce`, reviewer `staple`
- RCP2_F9AC64939A2C Welsh Rarebit: `contains_staple` batch `false`, reviewer `true`
