"""One household sentence read into rules (layer 08): the rules' reading, the model's, and the fallback."""

import pytest

from app.agent.rule_sentences import (
    NAME_THE_PERSON,
    NO_DATES,
    NO_POLARITY,
    TIME_RANGE,
    OpenAIRuleReader,
    ParsedRule,
    ParsedRules,
    read_rule_sentence,
)
from app.schemas.household import RuleParseRequest

MEMBERS = [
    {"name": "Ann", "age_band": "adult"},
    {"name": "Ben", "age_band": "adult"},
    {"name": "Mei", "age_band": "child"},
    {"name": "Grandma", "age_band": "senior", "default_present": False},
    {"name": "Grandpa", "age_band": "senior", "default_present": False},
]
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WEEKEND = ["saturday", "sunday"]


def read(text, kind="presence", speaker="Ann", reader=None):
    return read_rule_sentence(RuleParseRequest(kind=kind, text=text, members=MEMBERS, speaker=speaker), reader)


PRESENCE = [
    ("孩子工作日午饭在学校吃", [("Mei", False, WEEKDAYS, ["lunch"])]),
    ("我周三晚上加班不回来", [("Ann", False, ["wednesday"], ["dinner"])]),
    ("周末我爸妈过来吃晚饭", [("Grandma", True, WEEKEND, ["dinner"]), ("Grandpa", True, WEEKEND, ["dinner"])]),
    ("I work late on Wednesday evenings", [("Ann", False, ["wednesday"], ["dinner"])]),
    (
        "my parents join us for dinner on weekends",
        [("Grandma", True, WEEKEND, ["dinner"]), ("Grandpa", True, WEEKEND, ["dinner"])],
    ),
    ("Mei has lunch at school on weekdays", [("Mei", False, WEEKDAYS, ["lunch"])]),
    (
        "The kids eat lunch at school, but at home on Fridays",
        [
            ("Mei", False, [], ["lunch"]),
            ("Mei", True, ["friday"], ["lunch"]),
        ],
    ),
    ("Ben eats out on Monday and Thursday nights", [("Ben", False, ["monday", "thursday"], ["dinner"])]),
    ("My husband travels Mon to Wed", [("Ben", False, ["monday", "tuesday", "wednesday"], [])]),
    ("老公周一到周三不在家吃晚饭", [("Ben", False, ["monday", "tuesday", "wednesday"], ["dinner"])]),
    ("Grandma comes over for lunch on Sundays", [("Grandma", True, ["sunday"], ["lunch"])]),
    ("爷爷奶奶星期天来吃午饭", [("Grandma", True, ["sunday"], ["lunch"]), ("Grandpa", True, ["sunday"], ["lunch"])]),
    ("I skip breakfast every day", [("Ann", False, [], ["breakfast"])]),
    # Negated "eat / join / home" is away, never a presence (review of layer 08 PR-1).
    ("Mei doesn't eat at home on weekdays", [("Mei", False, WEEKDAYS, [])]),
    ("Ben won't join us for dinner on Fridays", [("Ben", False, ["friday"], ["dinner"])]),
    ("Ben can't make it to dinner on Fridays", [("Ben", False, ["friday"], ["dinner"])]),
    ("Mei is not eating lunch at home on Mondays", [("Mei", False, ["monday"], ["lunch"])]),
    ("孩子周三不吃晚饭", [("Mei", False, ["wednesday"], ["dinner"])]),
]


@pytest.mark.parametrize(("text", "expected"), PRESENCE)
def test_presence_sentences(text, expected):
    result = read(text)
    assert result.issues == []
    assert result.provider == "rules" and result.fell_back is False
    assert [(r.member_name, r.present, r.weekdays, r.meal_types) for r in result.rules] == expected
    assert all(rule.source_text == text for rule in result.rules)


TIMES = [
    ("工作日晚饭30分钟以内，周末无所谓", [(WEEKDAYS, ["dinner"], 30), (WEEKEND, ["dinner"], 240)]),
    ("weekday dinners within half an hour", [(WEEKDAYS, ["dinner"], 30)]),
    ("Mon-Thu lunch under 20 mins", [(["monday", "tuesday", "wednesday", "thursday"], ["lunch"], 20)]),
    ("weekend dinners can take 1.5 hours", [(WEEKEND, ["dinner"], 90)]),
    ("平日早餐十五分钟", [(WEEKDAYS, ["breakfast"], 15)]),
    ("周末晚饭一个小时", [(WEEKEND, ["dinner"], 60)]),
    ("dinners within 45 minutes", [([], ["dinner"], 45)]),
]


@pytest.mark.parametrize(("text", "expected"), TIMES)
def test_cooking_time_sentences(text, expected):
    result = read(text, kind="cooking_time")
    assert result.issues == []
    assert [(r.weekdays, r.meal_types, r.max_minutes) for r in result.rules] == expected


def test_the_card_restates_from_the_template():
    assert [r.restatement for r in read("孩子工作日午饭在学校吃").rules] == [
        "Monday to Friday, lunch: Mei eats elsewhere."
    ]
    assert [r.restatement for r in read("my parents join us for dinner on weekends").rules] == [
        "Saturday and Sunday, dinner: Grandma eats at home.",
        "Saturday and Sunday, dinner: Grandpa eats at home.",
    ]
    assert [r.restatement for r in read("工作日晚饭30分钟以内，周末无所谓", kind="cooking_time").rules] == [
        "Monday to Friday, dinner: within 30 minutes.",
        "Saturday and Sunday, dinner: no cooking-time limit.",
    ]


@pytest.mark.parametrize(
    ("text", "kind", "issue"),
    [
        ("初一十五我们吃素", "presence", NO_DATES),
        ("Ann is away on 10 Nov", "presence", NO_DATES),
        ("Tom eats out on Fridays", "presence", NAME_THE_PERSON),
        ("奶奶星期天来吃午饭", "presence", NAME_THE_PERSON),  # two older members: which one?
        ("Mei on Fridays at lunch", "presence", NO_POLARITY),
        ("孩子不吃猪肉", "presence", NO_POLARITY),  # a food, not a meal: not an absence
        ("dinner within 300 minutes", "cooking_time", TIME_RANGE),
    ],
)
def test_what_it_cannot_read_it_says_and_never_guesses(text, kind, issue):
    result = read(text, kind=kind)
    assert issue in " ".join(result.issues)
    assert result.rules == []


def test_i_needs_a_speaker():
    assert read("I work late on Wednesdays", speaker=None).rules == []


class FakeModel:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.prompts = result, error, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.result


def test_the_model_reading_drops_invented_names_and_restates_from_the_template():
    model = FakeModel(
        ParsedRules(
            understood=True,
            rules=[
                ParsedRule(member_names=["Mei", "Tom"], present=False, weekdays=WEEKDAYS, meal_types=["lunch"]),
            ],
        )
    )
    result = read("孩子和Tom工作日午饭在学校吃", reader=OpenAIRuleReader(model))
    assert result.provider == "openai" and result.fell_back is False
    assert [(r.member_name, r.restatement) for r in result.rules] == [
        ("Mei", "Monday to Friday, lunch: Mei eats elsewhere.")
    ]
    assert any("Tom is not a member" in issue for issue in result.issues)
    assert "<sentence>孩子和Tom工作日午饭在学校吃</sentence>" in model.prompts[0]


def test_a_model_that_did_not_understand_says_why():
    model = FakeModel(ParsedRules(understood=False, rules=[], unclear_reason="That names a date."))
    result = read("初一吃素", reader=OpenAIRuleReader(model))
    assert result.rules == [] and result.issues == ["That names a date."]


def test_a_failing_model_falls_back_to_the_rules():
    result = read("孩子工作日午饭在学校吃", reader=OpenAIRuleReader(FakeModel(error=TimeoutError("slow"))))
    assert result.provider == "rules" and result.fell_back is True
    assert [(r.member_name, r.present) for r in result.rules] == [("Mei", False)]


# "And" splits a clause only where its parts say different things; otherwise one part's days would take the
# other's value ("weekday dinners within 30 minutes and weekends 90 minutes" read as every day's dinner in 30).
AND_TIMES = [
    (
        "weekday dinners within 30 minutes and weekends 90 minutes",
        [(WEEKDAYS, ["dinner"], 30), (WEEKEND, ["dinner"], 90)],
    ),
    (
        "weekday dinners within 30 minutes, weekends 90 minutes",
        [(WEEKDAYS, ["dinner"], 30), (WEEKEND, ["dinner"], 90)],
    ),
    (
        "weekday dinners within 30 minutes and weekends no limit",
        [(WEEKDAYS, ["dinner"], 30), (WEEKEND, ["dinner"], 240)],
    ),
    ("工作日晚饭30分钟内和周末90分钟", [(WEEKDAYS, ["dinner"], 30), (WEEKEND, ["dinner"], 90)]),
    ("工作日晚饭30分钟以内而周末无所谓", [(WEEKDAYS, ["dinner"], 30), (WEEKEND, ["dinner"], 240)]),
    # Nothing conflicts: the clause stays whole.
    ("weekday lunch and dinner within 30 minutes", [(WEEKDAYS, ["lunch", "dinner"], 30)]),
    (
        "weekday lunch and dinner within 30 minutes and weekends 90 minutes",
        [(WEEKDAYS, ["lunch", "dinner"], 30), (WEEKEND, ["lunch", "dinner"], 90)],
    ),
]


@pytest.mark.parametrize(("text", "expected"), AND_TIMES)
def test_and_splits_cooking_times_only_when_they_differ(text, expected):
    result = read(text, kind="cooking_time")
    assert result.issues == []
    assert [(r.weekdays, r.meal_types, r.max_minutes) for r in result.rules] == expected


AND_PRESENCE = [
    (
        "Mei eats at school on weekdays and at home on weekends",
        [("Mei", False, WEEKDAYS, []), ("Mei", True, WEEKEND, [])],
    ),
    ("孩子工作日在学校吃和周末在家吃", [("Mei", False, WEEKDAYS, []), ("Mei", True, WEEKEND, [])]),
    ("孩子工作日午饭在学校吃而周末在家吃", [("Mei", False, WEEKDAYS, ["lunch"]), ("Mei", True, WEEKEND, ["lunch"])]),
    # Nothing conflicts: the clause stays whole, as before.
    ("Ben eats out on Monday and Thursday nights", [("Ben", False, ["monday", "thursday"], ["dinner"])]),
    ("Ben and Mei are away on Fridays", [("Ben", False, ["friday"], []), ("Mei", False, ["friday"], [])]),
    ("孩子和Tom工作日午饭在学校吃", [("Mei", False, WEEKDAYS, ["lunch"])]),
    ("Ben works late and Mei eats at school on weekdays", [("Ben", False, WEEKDAYS, []), ("Mei", False, WEEKDAYS, [])]),
]


@pytest.mark.parametrize(("text", "expected"), AND_PRESENCE)
def test_and_splits_presence_only_when_away_meets_home(text, expected):
    result = read(text)
    assert result.issues == []
    assert [(r.member_name, r.present, r.weekdays, r.meal_types) for r in result.rules] == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A comma list of days: the first day is read, the rest is reported, never a wider rule.
        ("Mei works late on Mondays, Wednesdays and Fridays", [("Mei", False, ["monday"])]),
        # A part between an away and a home part could be either: reported, never guessed.
        (
            "Mei eats at school on Mondays and Tuesdays and at home on weekends",
            [("Mei", False, ["monday"]), ("Mei", True, WEEKEND)],
        ),
    ],
)
def test_a_part_it_cannot_place_is_reported_not_widened(text, expected):
    result = read(text)
    assert result.issues == [NO_POLARITY]
    assert [(r.member_name, r.present, r.weekdays) for r in result.rules] == expected
