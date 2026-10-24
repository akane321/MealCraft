# Household LNS developer comparison

Synthetic three-recipe households, synthetic packages/prices, 7/14 dinners; couple with alternating attendance, six adults including a vegetarian, and two-dish couple dinners. One run per configuration; grouping is the algorithm near-duplicate policy, not product dish_kind. No held-out inputs; no product latency or real-price acceptance claim.

Times include seed construction. Native reference uses a 30-second diagnostic limit; LNS repairs have no wall-clock cutoff. Only proven references are compared. This small recipe pool tests household semantics, not catalog-scale performance.

| Household | Dinners | Algorithm | Parameters | Member mean/min | Table kinds | S$ | ms | Full score match |
|---|---|---|---|---|---|---|---|---|
| couple | 7 | DiversityAwareGreedyPlanner | {} | 1.5/1 | 2 | 12.0 | 15.0 | True |
| couple | 7 | GraspPlanner | {} | 1.5/1 | 2 | 12.0 | 77.9 | True |
| couple | 7 | LocalSearchPlanner | {} | 1.5/1 | 2 | 12.0 | 17.4 | True |
| couple | 7 | SharedObjectiveBeamPlanner | {'width': 8} | 1.5/1 | 2 | 12.0 | 51.0 | True |
| couple | 7 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 1.5/1 | 2 | 12.0 | 32.5 | True |
| couple | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 1.5/1 | 2 | 12.0 | 354.7 | True |
| couple | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 1.5/1 | 2 | 12.0 | 386.9 | True |
| couple | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 1.5/1 | 2 | 12.0 | 388.7 | True |
| couple | 14 | DiversityAwareGreedyPlanner | {} | 1.5/1 | 2 | 24.0 | 30.5 | False |
| couple | 14 | GraspPlanner | {} | 1.5/1 | 2 | 24.0 | 262.1 | False |
| couple | 14 | LocalSearchPlanner | {} | 1.5/1 | 2 | 22.0 | 48.6 | True |
| couple | 14 | SharedObjectiveBeamPlanner | {'width': 8} | 1.5/1 | 2 | 24.0 | 162.6 | False |
| couple | 14 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 1.5/1 | 2 | 22.0 | 59.7 | False |
| couple | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 1.5/1 | 2 | 22.0 | 406.5 | True |
| couple | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 1.5/1 | 2 | 22.0 | 448.4 | True |
| couple | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 1.5/1 | 2 | 22.0 | 420.0 | True |
| six | 7 | DiversityAwareGreedyPlanner | {} | 1.0/1 | 1 | 42.0 | 43.6 | True |
| six | 7 | GraspPlanner | {} | 1.0/1 | 1 | 42.0 | 116.5 | True |
| six | 7 | LocalSearchPlanner | {} | 1.0/1 | 1 | 42.0 | 21.0 | True |
| six | 7 | SharedObjectiveBeamPlanner | {'width': 8} | 1.0/1 | 1 | 42.0 | 65.3 | True |
| six | 7 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 1.0/1 | 1 | 42.0 | 61.5 | True |
| six | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 1.0/1 | 1 | 42.0 | 417.1 | True |
| six | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 1.0/1 | 1 | 42.0 | 378.4 | True |
| six | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 1.0/1 | 1 | 42.0 | 414.2 | True |
| six | 14 | DiversityAwareGreedyPlanner | {} | 1.0/1 | 1 | 84.0 | 45.1 | True |
| six | 14 | GraspPlanner | {} | 1.0/1 | 1 | 84.0 | 364.1 | True |
| six | 14 | LocalSearchPlanner | {} | 1.0/1 | 1 | 84.0 | 73.6 | True |
| six | 14 | SharedObjectiveBeamPlanner | {'width': 8} | 1.0/1 | 1 | 84.0 | 245.0 | True |
| six | 14 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 1.0/1 | 1 | 84.0 | 137.0 | True |
| six | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 1.0/1 | 1 | 84.0 | 458.1 | True |
| six | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 1.0/1 | 1 | 84.0 | 495.6 | True |
| six | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 1.0/1 | 1 | 84.0 | 445.9 | True |
| shared | 7 | DiversityAwareGreedyPlanner | {} | 1.5/1 | 2 | 14.0 | 40.5 | True |
| shared | 7 | GraspPlanner | {} | 1.5/1 | 2 | 14.0 | 393.3 | True |
| shared | 7 | LocalSearchPlanner | {} | 1.5/1 | 2 | 14.0 | 83.2 | True |
| shared | 7 | SharedObjectiveBeamPlanner | {'width': 8} | 1.5/1 | 2 | 14.0 | 229.8 | True |
| shared | 7 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 1.5/1 | 2 | 14.0 | 91.9 | True |
| shared | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 1.5/1 | 2 | 14.0 | 407.4 | True |
| shared | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 1.5/1 | 2 | 14.0 | 504.1 | True |
| shared | 7 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 1.5/1 | 2 | 14.0 | 413.3 | True |
| shared | 14 | DiversityAwareGreedyPlanner | {} | 1.5/1 | 2 | 28.0 | 137.8 | True |
| shared | 14 | GraspPlanner | {} | 1.5/1 | 2 | 28.0 | 1126.6 | True |
| shared | 14 | LocalSearchPlanner | {} | 1.5/1 | 2 | 28.0 | 386.4 | True |
| shared | 14 | SharedObjectiveBeamPlanner | {'width': 8} | 1.5/1 | 2 | 28.0 | 819.9 | True |
| shared | 14 | AnnealingPlanner | {'steps': 50, 'seed': 0} | 1.5/1 | 2 | 28.0 | 281.6 | True |
| shared | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 0} | 1.5/1 | 2 | 28.0 | 1477.5 | True |
| shared | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 1} | 1.5/1 | 2 | 28.0 | 590.2 | True |
| shared | 14 | LargeNeighborhoodPlanner | {'iterations': 4, 'destroy_size': 4, 'seed': 2} | 1.5/1 | 2 | 28.0 | 642.7 | True |

Machine, source, exact scores and repair outcomes: [JSON](member-lns.json).
