import pytest

from app.agent.parser import RuleBasedConstraintParser
from app.schemas.agent import AgentConstraintState


def parse(message: str):
    return RuleBasedConstraintParser().parse(
        message, current=AgentConstraintState(), acknowledged_unknowns=[], history=[]
    )


@pytest.mark.parametrize(
    ("message", "size", "weekly"),
    [
        ("Dinners for two this week, around S$90", 2, 90),
        ("Dinners for two this week, around S$90. We still have brown rice at home.", 2, 90),
        ("Cooking for a family of four, weekly budget 120", 4, 120),
        ("Three people, S$15 per meal this week", 3, None),
        ("for 2 people", 2, None),
        ("Something with twos and threes", None, None),
    ],
)
def test_household_size_and_weekly_budget_in_words(message, size, weekly) -> None:
    extraction = parse(message)
    assert extraction.household_size == size
    assert extraction.weekly_budget_sgd == weekly
