# Household LNS developer comparison

30 developer catalog recipes with real quantities, diets and nutrients; synthetic prices. The developer projection treats all recipes as dinner/main, not their product meal roles. 7/14 dinners; different diets and alternating attendance; two-dish and six-adult scenarios. One run per configuration; unreviewed near-duplicate grouping, not product dish_kind. No held-out inputs or product acceptance claim.

Times include seed construction. Native reference uses a 30-second diagnostic limit; LNS repairs have no wall-clock cutoff. Only proven references are compared. The reference proves optimality only within the same generated meal options. Meal options are capped at 64 per slot; this is not a full-catalog optimum.

| Household | Dinners | Algorithm | Parameters | Member mean/min | Table kinds | S$ | ms | Full score match |
|---|---|---|---|---|---|---|---|---|
| couple | 7 | DiversityAwareGreedyPlanner | {} | 5.0/3 | 7 | 25.0 | 251.3 | None |
| couple | 7 | GraspPlanner | {} | 5.0/3 | 7 | 25.0 | 2439.9 | None |
| couple | 7 | LocalSearchPlanner | {} | 5.0/3 | 7 | 25.0 | 571.1 | None |
| couple | 7 | SharedObjectiveBeamPlanner | {'width': 8} | 5.0/3 | 7 | 25.0 | 1697.4 | None |
| couple | 7 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 5.0/3 | 7 | 25.0 | 311.4 | None |
| couple | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 5.0/3 | 7 | 26.0 | 3079.0 | None |
| couple | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 5.0/3 | 7 | 26.0 | 2459.0 | None |
| couple | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 5.0/3 | 7 | 26.0 | 2067.0 | None |
| couple | 14 | DiversityAwareGreedyPlanner | {} | 10.5/7 | 14 | 46.0 | 724.7 | None |
| couple | 14 | GraspPlanner | {} | 10.5/7 | 14 | 50.0 | 6833.2 | None |
| couple | 14 | LocalSearchPlanner | {} | 10.5/7 | 14 | 46.0 | 980.7 | None |
| couple | 14 | SharedObjectiveBeamPlanner | {'width': 8} | 10.5/7 | 14 | 46.0 | 1762.1 | None |
| couple | 14 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 10.5/7 | 14 | 44.0 | 848.6 | None |
| couple | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 10.5/7 | 14 | 42.0 | 2123.8 | None |
| couple | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 10.5/7 | 14 | 45.0 | 2106.9 | None |
| couple | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 10.5/7 | 14 | 43.0 | 2159.9 | None |
| six | 7 | DiversityAwareGreedyPlanner | {} | 7.0/7 | 7 | 32.0 | 522.0 | True |
| six | 7 | GraspPlanner | {} | 7.0/7 | 7 | 32.0 | 3212.2 | True |
| six | 7 | LocalSearchPlanner | {} | 7.0/7 | 7 | 32.0 | 653.0 | True |
| six | 7 | SharedObjectiveBeamPlanner | {'width': 8} | 7.0/7 | 7 | 32.0 | 2349.9 | True |
| six | 7 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 7.0/7 | 7 | 32.0 | 456.7 | True |
| six | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 7.0/7 | 7 | 32.0 | 2070.8 | True |
| six | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 7.0/7 | 7 | 32.0 | 1898.1 | True |
| six | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 7.0/7 | 7 | 32.0 | 2613.1 | True |
| six | 14 | DiversityAwareGreedyPlanner | {} | 11.0/11 | 11 | 64.0 | 900.6 | False |
| six | 14 | GraspPlanner | {} | 12.0/12 | 12 | 66.0 | 7624.8 | False |
| six | 14 | LocalSearchPlanner | {} | 11.0/11 | 11 | 64.0 | 2012.8 | False |
| six | 14 | SharedObjectiveBeamPlanner | {'width': 8} | 11.0/11 | 11 | 64.0 | 2439.2 | False |
| six | 14 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 11.0/11 | 11 | 57.0 | 1264.9 | False |
| six | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 12.0/12 | 12 | 51.0 | 2869.1 | False |
| six | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 13.0/13 | 13 | 57.0 | 3331.3 | False |
| six | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 12.0/12 | 12 | 54.0 | 2779.8 | False |
| shared | 7 | DiversityAwareGreedyPlanner | {} | 9.5/8 | 11 | 31.0 | 1321.3 | False |
| shared | 7 | GraspPlanner | {} | 9.5/8 | 11 | 31.0 | 10636.1 | False |
| shared | 7 | LocalSearchPlanner | {} | 9.5/8 | 11 | 31.0 | 1454.5 | False |
| shared | 7 | SharedObjectiveBeamPlanner | {'width': 8} | 9.5/8 | 11 | 31.0 | 2678.6 | False |
| shared | 7 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 9.5/8 | 11 | 31.0 | 1596.0 | False |
| shared | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 9.5/8 | 11 | 31.0 | 9476.2 | True |
| shared | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 9.5/8 | 11 | 31.0 | 8806.8 | True |
| shared | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 9.5/8 | 11 | 31.0 | 8390.8 | True |
| shared | 14 | DiversityAwareGreedyPlanner | {} | 13.0/11 | 15 | 59.0 | 4589.8 | False |
| shared | 14 | GraspPlanner | {} | 13.0/11 | 15 | 59.0 | 25139.5 | False |
| shared | 14 | LocalSearchPlanner | {} | 13.0/11 | 15 | 59.0 | 3529.8 | False |
| shared | 14 | SharedObjectiveBeamPlanner | {'width': 8} | 13.0/11 | 15 | 59.0 | 4394.6 | False |
| shared | 14 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 13.0/11 | 15 | 57.0 | 3321.6 | False |
| shared | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 15.0/13 | 17 | 54.0 | 7452.3 | False |
| shared | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 14.5/12 | 17 | 54.0 | 7544.3 | False |
| shared | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 15.0/13 | 17 | 52.0 | 7475.2 | False |

Machine, source, exact scores and repair outcomes: [JSON](member-catalog-30.json).
