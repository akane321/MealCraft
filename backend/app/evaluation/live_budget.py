"""Hard stop for starting paid requests in bounded live developer evaluations."""

MAX_BUDGET_USD = 5.0


class EvaluationBudget:
    """Track measured spend and stop starting requests at the configured ceiling."""

    def __init__(self, limit_usd: float = MAX_BUDGET_USD) -> None:
        if limit_usd <= 0:
            raise ValueError("budget limit must be positive")
        self.limit_usd = limit_usd
        self.spent_usd = 0.0

    @property
    def can_start_request(self) -> bool:
        return self.spent_usd < self.limit_usd

    def record(self, cost: float | None) -> None:
        if cost is None:
            raise ValueError("cannot continue a paid evaluation with unknown model pricing")
        self.spent_usd += cost
