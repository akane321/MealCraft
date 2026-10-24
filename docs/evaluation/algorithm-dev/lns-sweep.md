# LNS developer sweep

Developer catalog recipes; synthetic products/prices; single-dish dinners; no held-out data. LNS starts from the same greedy seed. Native reference has a 30-second diagnostic limit; LNS repairs have no wall-clock cutoff. Member grouping uses existing unreviewed similarity policy.

LNS times include its greedy seed. Each configuration is measured once per seed. This is a small developer sweep, not repeated latency or product acceptance evidence.

| Recipes/dinners/members | Algorithm | Parameters | Member mean/min | Table kinds | Checkout S$ | Total ms | Matches full reference score |
|---|---|---|---|---|---|---|---|
| 8/7/2 | greedy | {} | 6.0/6 | 6 | 23.00 | 68.0 | True |
| 8/7/2 | beam | {"width": 8} | 6.0/6 | 6 | 23.00 | 376.6 | True |
| 8/7/2 | annealing | {"seed": 0, "steps": 50} | 6.0/6 | 6 | 23.00 | 135.1 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 0} | 6.0/6 | 6 | 23.00 | 299.8 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 1} | 6.0/6 | 6 | 23.00 | 284.3 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 0} | 6.0/6 | 6 | 23.00 | 484.2 | True |
| 8/7/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 1} | 6.0/6 | 6 | 23.00 | 548.3 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 0} | 6.0/6 | 6 | 23.00 | 299.0 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 1} | 6.0/6 | 6 | 23.00 | 363.8 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 0} | 6.0/6 | 6 | 23.00 | 722.6 | True |
| 8/7/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 1} | 6.0/6 | 6 | 23.00 | 629.2 | True |
| 16/7/6 | greedy | {} | 7.0/7 | 7 | 34.00 | 185.0 | True |
| 16/7/6 | beam | {"width": 8} | 7.0/7 | 7 | 34.00 | 1100.2 | True |
| 16/7/6 | annealing | {"seed": 0, "steps": 50} | 7.0/7 | 7 | 34.00 | 310.9 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 2, "seed": 0} | 7.0/7 | 7 | 34.00 | 517.3 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 2, "seed": 1} | 7.0/7 | 7 | 34.00 | 531.9 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 4, "seed": 0} | 7.0/7 | 7 | 34.00 | 992.1 | True |
| 16/7/6 | lns | {"destroy_size": 2, "iterations": 4, "seed": 1} | 7.0/7 | 7 | 34.00 | 892.9 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 2, "seed": 0} | 7.0/7 | 7 | 34.00 | 795.7 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 2, "seed": 1} | 7.0/7 | 7 | 34.00 | 720.7 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 4, "seed": 0} | 7.0/7 | 7 | 34.00 | 1325.6 | True |
| 16/7/6 | lns | {"destroy_size": 4, "iterations": 4, "seed": 1} | 7.0/7 | 7 | 34.00 | 1308.5 | True |
| 16/14/2 | greedy | {} | 8.0/8 | 8 | 52.00 | 443.6 | False |
| 16/14/2 | beam | {"width": 8} | 8.0/8 | 8 | 52.00 | 1466.2 | False |
| 16/14/2 | annealing | {"seed": 0, "steps": 50} | 8.0/8 | 8 | 50.00 | 511.2 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 0} | 8.0/8 | 8 | 50.00 | 782.6 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 2, "seed": 1} | 8.0/8 | 8 | 47.00 | 828.1 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 0} | 8.0/8 | 8 | 50.00 | 1089.4 | False |
| 16/14/2 | lns | {"destroy_size": 2, "iterations": 4, "seed": 1} | 8.0/8 | 8 | 47.00 | 1173.2 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 0} | 9.0/9 | 9 | 42.00 | 897.2 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 2, "seed": 1} | 8.0/8 | 8 | 46.00 | 958.1 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 0} | 9.0/9 | 9 | 34.00 | 1321.9 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 4, "seed": 1} | 9.0/9 | 9 | 41.00 | 1517.0 | False |

Reference status, full score, environment and repair timings: [JSON](lns-sweep.json). The reference optimizes variety first; its price is not a global minimum-price claim. No production default is selected from these three cases.
