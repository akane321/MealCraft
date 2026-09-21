"""Search-side diversity guards and bounded soft terms for explicit packets."""

from collections import Counter

# Each entire horizon receives at most this much reward (or variety penalty).
# Part of planning-diversity-v1, not a user-controlled unbounded multiplier.
MAX_DIVERSITY_CONTRIBUTION = 0.10


def permits_extension(problem, previous, recipe_id):
    policy = problem.diversity_policy
    if policy is None:
        return True
    if recipe_id in previous:
        return False
    roles = policy.classifications.get(recipe_id)
    # Missing roles remain searchable, but independent validation is indeterminate.
    # Rejecting them here could turn missing evidence into a false infeasibility.
    if roles is None:
        return True
    prior = [policy.classifications.get(chosen) for chosen in previous]
    if prior and prior[-1] is not None:
        if set(roles.primary_proteins.values()) & set(prior[-1].primary_proteins.values()):
            return False
    cores = {core for item in policy.classifications.values() for core in item.core_ingredient_ids}
    recipes = {r.recipe_id: r for r in problem.recipes}
    counts = Counter(i for chosen in previous for i in {x.ingredient_id for x in recipes[chosen].ingredients} & cores)
    present = {i.ingredient_id for i in recipes[recipe_id].ingredients} & cores
    return all(counts[core] < policy.max_slots_per_core_ingredient for core in present)


def diversity_loss(problem, previous, recipe_id):
    policy = problem.diversity_policy
    if policy is None:
        return previous.count(recipe_id) * 0.10 + (0.35 if previous and previous[-1] == recipe_id else 0.0)
    roles = policy.classifications.get(recipe_id)
    if roles is None:
        return 0.0
    prior = [policy.classifications.get(chosen) for chosen in previous]
    used_cores = {core for item in prior if item is not None for core in item.core_ingredient_ids}
    variety = len(set(roles.core_ingredient_ids) & used_cores) / len(roles.core_ingredient_ids)
    # A core anywhere in the packet cannot masquerade as a rewarded garnish.
    all_cores = {core for item in policy.classifications.values() for core in item.core_ingredient_ids}
    recipes = {r.recipe_id: r for r in problem.recipes}
    noncore = {i.ingredient_id for i in recipes[recipe_id].ingredients} - all_cores
    used_noncore = {
        i.ingredient_id for chosen in previous if chosen in policy.classifications for i in recipes[chosen].ingredients
    } - all_cores
    overlap = len(noncore & used_noncore) / len(noncore) if noncore else 0.0
    return (
        MAX_DIVERSITY_CONTRIBUTION
        / len(problem.slots)
        * (policy.diversity_penalty * variety - policy.overlap_reward_weight * overlap)
    )
