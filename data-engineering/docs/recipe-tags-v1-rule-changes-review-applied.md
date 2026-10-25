# 人工复核后的修正落实检查

由脚本核对当前标签与原审查包中人工确认的展示字段。原包的before/after仍是当时快照，不同意的字段使用corrected_values；不把修正算成规则原本判对。后续owner计量口径将质量单位面食按干重换算；受影响条目单列修订，不能声称原人工意见在新口径下仍全部一致。这不是独立盲审、总体准确率或模型批次放行。

已按当前口径核对：25项；其中2项按后续计量口径修订，不是新增人工盲审；未审核模型门禁：422项。

| 菜谱 | 当前口径的新值 | 原人工纠正字段 | 后续计量口径修订 |
|---|---|---|---|
| Marilyn'S English Pasties | {"meal_role": "one_bowl", "contains_staple": true} | — | — |
| Chinese Pork Chops | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Kid Friendly Jamaican Chicken | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Barbecue Beef | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Chicken Stir-Fry | {"meal_role": "one_bowl", "contains_staple": true} | — | {"meal_role": "one_bowl", "contains_staple": true} |
| Baked Macaroni And Cheese | {"meal_role": "one_bowl"} | — | — |
| Kalbi Beef Marinate (Flank Steak) | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Acorn Squash Stuffed With Italian Sausage & Penne | {"meal_role": "one_bowl", "contains_staple": true} | — | {"meal_role": "one_bowl", "contains_staple": true} |
| Mon-Doo(Korean Egg Rolls) | {"protein_sources": null} | — | — |
| Spanish Rice | {"meal_role": "staple", "contains_staple": true} | meal_role, contains_staple | — |
| Kim Bap (Korean Rice Rolls) | {"meal_role": "one_bowl"} | — | — |
| Chicken Curry | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Napa Cabbage with Dried Shrimp | {"protein_sources": []} | — | — |
| Beef Carnitas Tacos | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Mexican Crab Salad | {"protein_sources": ["fish"]} | protein_sources | — |
| Stuffed Green Peppers | {"meal_role": "protein_main", "contains_staple": false} | — | — |
| Chicken Teriyaki | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Pumpkin Fried Rice | {"meal_role": "one_bowl", "contains_staple": true} | meal_role, contains_staple | — |
| Parmesan Chicken | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — | — |
| Lo Mein | {"protein_sources": null} | — | — |
| Taco Meat Filling | {"meal_role": "sauce", "protein_sources": [], "flavor_tags": []} | — | — |
| Chicken Adobo | {"protein_sources": null} | — | — |
| Ravioli Bolognese | {"meal_role": "one_bowl", "contains_staple": true} | — | — |
| Korean Fusion Butternut Squash Soup | {"protein_sources": null} | protein_sources | — |
| Taco Filling (Ground Beef) | {"meal_role": "sauce", "protein_sources": [], "flavor_tags": []} | — | — |

当前标签SHA256：`4c09faf8a604dc4453f5dd16e984c11a5c19a976992b887bd31dce2ace92956a`
