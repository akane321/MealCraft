# 人工复核后的修正落实检查

由脚本核对当前标签与原审查包中人工确认的展示字段。原包的before/after仍是当时快照，不同意的字段使用corrected_values；不把修正算成规则原本判对。这不是独立盲审、总体准确率或模型批次放行。

已核验并落实：25项；未审核模型门禁：422项。

| 菜谱 | 已核对字段的新值 | 人工纠正字段 |
|---|---|---|
| Marilyn'S English Pasties | {"meal_role": "one_bowl", "contains_staple": true} | — |
| Chinese Pork Chops | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Kid Friendly Jamaican Chicken | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Barbecue Beef | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Chicken Stir-Fry | {"meal_role": "protein_main", "contains_staple": false} | — |
| Baked Macaroni And Cheese | {"meal_role": "one_bowl"} | — |
| Kalbi Beef Marinate (Flank Steak) | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Acorn Squash Stuffed With Italian Sausage & Penne | {"meal_role": "protein_main", "contains_staple": false} | — |
| Mon-Doo(Korean Egg Rolls) | {"protein_sources": null} | — |
| Spanish Rice | {"meal_role": "staple", "contains_staple": true} | meal_role, contains_staple |
| Kim Bap (Korean Rice Rolls) | {"meal_role": "one_bowl"} | — |
| Chicken Curry | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Napa Cabbage with Dried Shrimp | {"protein_sources": []} | — |
| Beef Carnitas Tacos | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Mexican Crab Salad | {"protein_sources": ["fish"]} | protein_sources |
| Stuffed Green Peppers | {"meal_role": "protein_main", "contains_staple": false} | — |
| Chicken Teriyaki | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Pumpkin Fried Rice | {"meal_role": "one_bowl", "contains_staple": true} | meal_role, contains_staple |
| Parmesan Chicken | {"meal_role": null, "contains_staple": null, "protein_sources": null} | — |
| Lo Mein | {"protein_sources": null} | — |
| Taco Meat Filling | {"meal_role": "sauce", "protein_sources": [], "flavor_tags": []} | — |
| Chicken Adobo | {"protein_sources": null} | — |
| Ravioli Bolognese | {"meal_role": "one_bowl", "contains_staple": true} | — |
| Korean Fusion Butternut Squash Soup | {"protein_sources": null} | protein_sources |
| Taco Filling (Ground Beef) | {"meal_role": "sauce", "protein_sources": [], "flavor_tags": []} | — |

当前标签SHA256：`046629cf82a096d00e3d83acb53b708bafab98f9db479251fba6713dee66d1fc`
