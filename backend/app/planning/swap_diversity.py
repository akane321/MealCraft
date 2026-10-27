"""Local, deterministic near-dish evidence for replacement candidates.

Missing vectors do not prove difference and do not override existing eligibility
checks. This gate does not change product dish_kind or the planning objective.
"""

from app.planning.near_duplicate_groups import NearDuplicatePolicy, classify
from app.planning.recipe_pair_similarity import RecipePairIndex
from app.planning.recipe_similarity import recipe_key

SWAP_POLICY = NearDuplicatePolicy("peer-review-dev-v2", 0.2, 0.05, 0.75, fried_rice_cosine_min=0.64)


class SwapDiversity:
    def __init__(self, recipes):
        self.keys = {r.id: recipe_key(r) for r in recipes}
        # Different database rows may refer to the same catalog recipe.
        unique = {recipe_key(r): r for r in recipes}
        self.index = RecipePairIndex(list(unique.values()))
        self.cache = {}

    def verdict(self, left_id, right_id):
        left, right = self.keys[left_id], self.keys[right_id]
        if left == right:
            return "near"
        pair = tuple(sorted((left, right)))
        if pair not in self.cache:
            self.cache[pair] = classify(self.index.compare(*pair), SWAP_POLICY)
        return self.cache[pair]

    def near(self, left_id, right_id):
        return self.verdict(left_id, right_id) == "near"
