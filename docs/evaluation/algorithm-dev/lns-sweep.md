# LNS developer sweep

Developer catalog recipes; synthetic products/prices; single-dish dinners; no held-out data. LNS starts from the same greedy seed. Native reference has a 30-second diagnostic limit; LNS repairs have no wall-clock cutoff. Member grouping uses existing unreviewed similarity policy.

LNS times include its greedy seed. Each configuration is measured once per seed. This is a small developer sweep, not repeated latency or product acceptance evidence.

| Recipes/dinners/members | Algorithm | Parameters | Member mean/min | Table kinds | Checkout S$ | Total ms | Matches full reference score |
|---|---|---|---|---|---|---|---|
| 8/7/2 | greedy | {} | 6.0/6 | 6 | 23.00 | 109.2 | True |
| 8/7/2 | beam | {"width": 8} | 6.0/6 | 6 | 23.00 | 384.2 | True |
| 8/7/2 | annealing | {"seed": 0, "steps": 50} | 6.0/6 | 6 | 23.00 | 110.1 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 0} | 6.0/6 | 6 | 23.00 | 294.6 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 1} | 6.0/6 | 6 | 23.00 | 348.1 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 0} | 6.0/6 | 6 | 23.00 | 571.9 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 1} | 6.0/6 | 6 | 23.00 | 558.9 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 0} | 6.0/6 | 6 | 23.00 | 359.9 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 1} | 6.0/6 | 6 | 23.00 | 314.6 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 0} | 6.0/6 | 6 | 23.00 | 767.4 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 1} | 6.0/6 | 6 | 23.00 | 687.7 | True |
| 16/7/6 | greedy | {} | 7.0/7 | 7 | 34.00 | 182.3 | True |
| 16/7/6 | beam | {"width": 8} | 7.0/7 | 7 | 34.00 | 1108.9 | True |
| 16/7/6 | annealing | {"seed": 0, "steps": 50} | 7.0/7 | 7 | 34.00 | 266.3 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 2, "seed": 0} | 7.0/7 | 7 | 34.00 | 550.2 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 2, "seed": 1} | 7.0/7 | 7 | 34.00 | 651.6 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 4, "seed": 0} | 7.0/7 | 7 | 34.00 | 897.9 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 4, "seed": 1} | 7.0/7 | 7 | 34.00 | 959.4 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 2, "seed": 0} | 7.0/7 | 7 | 34.00 | 700.0 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 2, "seed": 1} | 7.0/7 | 7 | 34.00 | 755.7 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 4, "seed": 0} | 7.0/7 | 7 | 34.00 | 1244.8 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 4, "seed": 1} | 7.0/7 | 7 | 34.00 | 1221.3 | True |
| 16/14/2 | greedy | {} | 8.0/8 | 8 | 52.00 | 437.3 | False |
| 16/14/2 | beam | {"width": 8} | 8.0/8 | 8 | 52.00 | 1412.3 | False |
| 16/14/2 | annealing | {"seed": 0, "steps": 50} | 8.0/8 | 8 | 50.00 | 514.6 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 0} | 8.0/8 | 8 | 50.00 | 842.2 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 1} | 8.0/8 | 8 | 47.00 | 810.8 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 0} | 8.0/8 | 8 | 50.00 | 1209.5 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 1} | 8.0/8 | 8 | 47.00 | 1185.7 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 0} | 9.0/9 | 9 | 42.00 | 931.5 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 1} | 8.0/8 | 8 | 46.00 | 999.7 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 0} | 9.0/9 | 9 | 34.00 | 1368.3 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 1} | 9.0/9 | 9 | 41.00 | 1425.0 | False |

Reference status, full score, environment and repair timings: [JSON](lns-sweep.json). The reference optimizes variety first; its price is not a global minimum-price claim. No production default is selected from these three cases.
