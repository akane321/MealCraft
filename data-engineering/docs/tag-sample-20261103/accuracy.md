# Sample accuracy of recipe-tags-v1/llm-v3-20261103

Filled sample: SHA-256 `9123cf17ff95c5e9514c94da0a73e874c64a7255a269585ce1f5fafc9ee0a343`; drawn: `sample.json` (40 recipes, seed 20261103). Only rows marked 是 (checked in person) count; a value this script cannot read counts neither way and is listed for the reviewer to fill again.

| Stratum | Rows | Checked | Agree | Accuracy | Unchecked | Checked, no value | Unrecognized, refill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 表导入层 (`table`) | 95 | 95 | 50 | 52.6% | 0 | 0 | 0 |
| 合计 (`all`) | 95 | 95 | 50 | 52.6% | 0 | 0 | 0 |

| Field | Rows | Checked | Agree | Accuracy | Unchecked | Checked, no value | Unrecognized, refill |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `meal_role` | 40 | 40 | 15 | 37.5% | 0 | 0 | 0 |
| `contains_staple` | 40 | 40 | 25 | 62.5% | 0 | 0 | 0 |
| `protein_sources` | 15 | 15 | 10 | 66.7% | 0 | 0 | 0 |

无法识别，请重填: 0 rows.


Disagreements: 45.

- RCP2_05426F648B01 Pirishki: `meal_role` batch `snack`, reviewer `dessert`
- RCP2_244D8C7CC69D Baked Grits Souffle: `meal_role` batch `snack`, reviewer `one_bowl`
- RCP2_244D8C7CC69D Baked Grits Souffle: `contains_staple` batch `false`, reviewer `true`
- RCP2_3BBE43E93A1B Baked Beans: `meal_role` batch `sauce`, reviewer `staple`
- RCP2_3BBE43E93A1B Baked Beans: `contains_staple` batch `false`, reviewer `true`
- RCP2_3BBE43E93A1B Baked Beans: `protein_sources` batch `[]`, reviewer `legume,pork`
- RCP2_3F150B2A9B44 Luchi: `meal_role` batch `snack`, reviewer `staple`
- RCP2_3F150B2A9B44 Luchi: `contains_staple` batch `false`, reviewer `true`
- RCP2_418ABCCF343C Baked Eggplant Parmigiana: `meal_role` batch `sauce`, reviewer `null`
- RCP2_418ABCCF343C Baked Eggplant Parmigiana: `contains_staple` batch `false`, reviewer `null`
- RCP2_4CB46715223E Fruit Curry: `meal_role` batch `dessert`, reviewer `null`
- RCP2_4CB46715223E Fruit Curry: `contains_staple` batch `false`, reviewer `null`
- RCP2_4CB46715223E Fruit Curry: `protein_sources` batch `[]`, reviewer `null`
- RCP2_4DBEB5DF75A6 Spiced Apples: `meal_role` batch `dessert`, reviewer `sauce`
- RCP2_55D610F7F931 Garden Kabobs: `meal_role` batch `staple`, reviewer `one_bowl`
- RCP2_5BB20EB1E32E Sauteed Peppers: `meal_role` batch `sauce`, reviewer `vegetable`
- RCP2_607381EA69EE Bhatura: `meal_role` batch `snack`, reviewer `staple`
- RCP2_607381EA69EE Bhatura: `contains_staple` batch `false`, reviewer `true`
- RCP2_639FAA64235E Saloon "Hard Track" Pilot Crackers: `meal_role` batch `snack`, reviewer `staple`
- RCP2_639FAA64235E Saloon "Hard Track" Pilot Crackers: `contains_staple` batch `false`, reviewer `true`
- RCP2_6BBA70AC5E9E Grammie Bea'S Herbed Dumplings: `meal_role` batch `soup`, reviewer `staple`
- RCP2_6BBA70AC5E9E Grammie Bea'S Herbed Dumplings: `contains_staple` batch `false`, reviewer `true`
- RCP2_7160598B0E84 Spicy Rice And Vegetables: `meal_role` batch `one_bowl`, reviewer `staple`
- RCP2_87C0C08CAA11 French Wafers: `meal_role` batch `snack`, reviewer `dessert`
- RCP2_882366890116 Indiana Baked Beans: `meal_role` batch `soup`, reviewer `null`
- RCP2_882366890116 Indiana Baked Beans: `contains_staple` batch `false`, reviewer `null`
- RCP2_98EA656F2225 Sour Cream Cornbread: `meal_role` batch `one_bowl`, reviewer `snack`
- RCP2_98EA656F2225 Sour Cream Cornbread: `contains_staple` batch `true`, reviewer `false`
- RCP2_A6801EDDEF8F Halloumi Cheese Kebabs: `meal_role` batch `staple`, reviewer `one_bowl`
- RCP2_BA21C876BBC1 Hargadon'S Brown Soda Bread: `meal_role` batch `one_bowl`, reviewer `breakfast`
- RCP2_BA21C876BBC1 Hargadon'S Brown Soda Bread: `contains_staple` batch `true`, reviewer `false`
- RCP2_BDC0CEA53793 Texas Style Baked Beans: `meal_role` batch `sauce`, reviewer `staple`
- RCP2_BDC0CEA53793 Texas Style Baked Beans: `contains_staple` batch `false`, reviewer `true`
- RCP2_BDC0CEA53793 Texas Style Baked Beans: `protein_sources` batch `[]`, reviewer `legume`
- RCP2_CA5CC81FBE31 Easy Brazilian Feijao: `meal_role` batch `sauce`, reviewer `staple`
- RCP2_CA5CC81FBE31 Easy Brazilian Feijao: `contains_staple` batch `false`, reviewer `true`
- RCP2_CA5CC81FBE31 Easy Brazilian Feijao: `protein_sources` batch `[]`, reviewer `legume`
- RCP2_D0D00E0BE51C Apple Bean Bake: `meal_role` batch `dessert`, reviewer `staple`
- RCP2_D0D00E0BE51C Apple Bean Bake: `contains_staple` batch `false`, reviewer `true`
- RCP2_D0D00E0BE51C Apple Bean Bake: `protein_sources` batch `[]`, reviewer `legume`
- RCP2_D475737AA6A4 Kimchi Stuffing: `meal_role` batch `breakfast`, reviewer `sauce`
- RCP2_D5A2E336A0A4 Golden Cornbread: `meal_role` batch `breakfast`, reviewer `snack`
- RCP2_F1B3BFFB4BCE Double Cornbread: `meal_role` batch `breakfast`, reviewer `snack`
- RCP2_F1D4C2B4A839 Swedish Cardamom Braids: `meal_role` batch `breakfast`, reviewer `staple`
- RCP2_F1D4C2B4A839 Swedish Cardamom Braids: `contains_staple` batch `false`, reviewer `true`
