# LNS developer sweep

Developer catalog recipes; synthetic products/prices; single-dish dinners; no held-out data. LNS starts from the same greedy seed. Native reference has a 30-second diagnostic limit; LNS repairs have no wall-clock cutoff. Member grouping uses existing unreviewed similarity policy.

LNS times include its greedy seed. Each configuration is measured once per seed. This is a small developer sweep, not repeated latency or product acceptance evidence.

| Recipes/dinners/members | Algorithm | Parameters | Member mean/min | Table kinds | Checkout S$ | Total ms | Matches full reference score |
|---|---|---|---|---|---|---|---|
| 16/14/2 | greedy | {} | 8.0/8 | 8 | 52.00 | 454.5 | False |
| 16/14/2 | beam | {"width": 8} | 8.0/8 | 8 | 52.00 | 1435.9 | False |
| 16/14/2 | annealing | {"seed": 0, "steps": 50} | 8.0/8 | 8 | 50.00 | 503.4 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 8, "seed": 0} | 9.0/9 | 9 | 35.00 | 2497.1 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 8, "seed": 1} | 10.0/10 | 10 | 41.00 | 2431.4 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 8, "seed": 2} | 10.0/10 | 10 | 36.00 | 2435.2 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 16, "seed": 0} | 9.0/9 | 9 | 35.00 | 4470.8 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 16, "seed": 1} | 10.0/10 | 10 | 37.00 | 4574.0 | False |
| 16/14/2 | lns | {"destroy_size": 4, "iterations": 16, "seed": 2} | 10.0/10 | 10 | 36.00 | 4507.5 | False |
| 16/14/2 | lns | {"destroy_size": 7, "iterations": 8, "seed": 0} | 9.0/9 | 9 | 35.00 | 4357.2 | False |
| 16/14/2 | lns | {"destroy_size": 7, "iterations": 8, "seed": 1} | 9.0/9 | 9 | 35.00 | 4736.8 | False |
| 16/14/2 | lns | {"destroy_size": 7, "iterations": 8, "seed": 2} | 9.0/9 | 9 | 35.00 | 4961.8 | False |
| 16/14/2 | lns | {"destroy_size": 7, "iterations": 16, "seed": 0} | 10.0/10 | 10 | 37.00 | 8659.3 | False |
| 16/14/2 | lns | {"destroy_size": 7, "iterations": 16, "seed": 1} | 10.0/10 | 10 | 35.00 | 8407.5 | True |
| 16/14/2 | lns | {"destroy_size": 7, "iterations": 16, "seed": 2} | 10.0/10 | 10 | 36.00 | 8295.5 | False |

Reference status, full score, environment and repair timings: [JSON](lns-extended.json). The reference optimizes variety first; its price is not a global minimum-price claim. No production default is selected from these three cases.
