"""One household sentence read into rules (layer 08): the rules' reading, the model's, and the fallback."""

import pytest

from app.agent.rule_sentences import (
    NAME_THE_PERSON,
    NO_DATES,
    NO_DAYS,
    NO_POLARITY,
    NO_TIME,
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
    # A day phrase said once, before or after both parts, covers both; never every day for one of them.
    (
        "lunch within 20 minutes and dinner within 45 minutes on weekdays",
        [(WEEKDAYS, ["lunch"], 20), (WEEKDAYS, ["dinner"], 45)],
    ),
    ("weekday lunch 20 minutes and dinner 45 minutes", [(WEEKDAYS, ["lunch"], 20), (WEEKDAYS, ["dinner"], 45)]),
    ("weekday breakfast 10 minutes and dinner 45 minutes", [(WEEKDAYS, ["breakfast"], 10), (WEEKDAYS, ["dinner"], 45)]),
    ("lunch within 20 minutes and dinner within 45 minutes", [([], ["lunch"], 20), ([], ["dinner"], 45)]),
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
    # Bare "home" is home.
    ("Mei is away on weekdays and home on weekends", [("Mei", False, WEEKDAYS, []), ("Mei", True, WEEKEND, [])]),
    ("I am home on weekends and away on weekdays", [("Ann", True, WEEKEND, []), ("Ann", False, WEEKDAYS, [])]),
    # Different people split too, even when both are away.
    (
        "Ben is away on weekdays and Mei is away on weekends",
        [("Ben", False, WEEKDAYS, []), ("Mei", False, WEEKEND, [])],
    ),
    (
        "Ben eats at work on weekdays and Mei eats at school on weekends",
        [("Ben", False, WEEKDAYS, []), ("Mei", False, WEEKEND, [])],
    ),
    # One day phrase covers both parts: lunch keeps the weekdays it was said with.
    (
        "Mei eats lunch at school and dinner at home on weekdays",
        [("Mei", False, WEEKDAYS, ["lunch"]), ("Mei", True, WEEKDAYS, ["dinner"])],
    ),
    ("孩子工作日午饭在学校吃和晚饭在家吃", [("Mei", False, WEEKDAYS, ["lunch"]), ("Mei", True, WEEKDAYS, ["dinner"])]),
    # Nothing conflicts: the clause stays whole, as before.
    ("Ben eats out on Monday and Thursday nights", [("Ben", False, ["monday", "thursday"], ["dinner"])]),
    ("Ben and Mei are away on Fridays", [("Ben", False, ["friday"], []), ("Mei", False, ["friday"], [])]),
    ("孩子和Tom工作日午饭在学校吃", [("Mei", False, WEEKDAYS, ["lunch"])]),
    ("Ben works late and Mei eats at school on weekdays", [("Ben", False, WEEKDAYS, []), ("Mei", False, WEEKDAYS, [])]),
]


@pytest.mark.parametrize(("text", "expected"), AND_PRESENCE)
def test_and_splits_presence_only_when_the_parts_differ(text, expected):
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
        # "Comes home late" could mean either.
        ("Ben comes home late on Fridays", []),
    ],
)
def test_a_part_it_cannot_place_is_reported_not_widened(text, expected):
    result = read(text)
    assert result.issues == [NO_POLARITY]
    assert [(r.member_name, r.present, r.weekdays) for r in result.rules] == expected


def test_a_part_without_days_between_different_days_is_reported_not_read_as_every_day():
    result = read("weekday dinners within 30 minutes and weekend lunch and dinner 90 minutes", kind="cooking_time")
    assert result.issues == [NO_DAYS, NO_TIME]
    assert [(r.weekdays, r.meal_types, r.max_minutes) for r in result.rules] == [(WEEKDAYS, ["dinner"], 30)]


# Review round 2 of #328: never a confirmable rule wider than the sentence; unsure parts are reported.
@pytest.mark.parametrize(
    "text",
    [
        "Grandma has a home-cooked dinner on Fridays",
        "Ben works from home on Fridays",
        "Ben has a home office on weekdays",
        "Ben likes home cooking on weekends",
        "Ben has home delivery on Fridays",
        "Mei brought homework home on Fridays",
        "Grandma brings home leftovers on Sundays",
        "Grandma goes home on Sundays",
    ],
)
def test_a_home_that_says_nothing_about_presence_is_reported(text):
    result = read(text)
    assert result.rules == [] and result.issues == [NO_POLARITY]


ROUND_2 = [
    # "<meal> out" is away, so the breakfast never joins the home part.
    (
        "Mei eats lunch at school and dinner at home and breakfast out on weekdays",
        [
            ("Mei", False, WEEKDAYS, ["lunch"]),
            ("Mei", True, WEEKDAYS, ["dinner"]),
            ("Mei", False, WEEKDAYS, ["breakfast"]),
        ],
        [],
    ),
    (
        "Ben eats lunch out and dinner at home on Fridays",
        [("Ben", False, ["friday"], ["lunch"]), ("Ben", True, ["friday"], ["dinner"])],
        [],
    ),
    # A trailing meal with no home or away is reported, never joined to the part before it.
    (
        "Mei eats lunch at school and dinner at home and breakfast on weekdays",
        [("Mei", False, WEEKDAYS, ["lunch"]), ("Mei", True, WEEKDAYS, ["dinner"])],
        [NO_POLARITY],
    ),
    # ...but a meal list continues: "for lunch and dinner".
    (
        "Mei eats at school on weekdays and at home for lunch and dinner on weekends",
        [("Mei", False, WEEKDAYS, []), ("Mei", True, WEEKEND, ["lunch", "dinner"])],
        [],
    ),
    # A part whose subject is no member never takes the previous part's people.
    ("Mei eats at school and Tilly eats at home on weekdays", [("Mei", False, WEEKDAYS, [])], [NAME_THE_PERSON]),
    (
        "Ben eats lunch at school and Mei eats dinner at home and Tilly eats breakfast out on weekdays",
        [("Ben", False, WEEKDAYS, ["lunch"]), ("Mei", True, WEEKDAYS, ["dinner"])],
        [NAME_THE_PERSON],
    ),
    (
        "Ben is away on Mondays and Mei is away on Tuesdays and Tilly is away on Wednesdays",
        [("Ben", False, ["monday"], []), ("Mei", False, ["tuesday"], [])],
        [NAME_THE_PERSON],
    ),
    ("Ben eats out on Mondays, Tilly joins us on Tuesdays", [("Ben", False, ["monday"], [])], [NAME_THE_PERSON]),
    # A name next to Chinese is still a name.
    ("我周一在学校吃而Ben周二在家吃", [("Ann", False, ["monday"], []), ("Ben", True, ["tuesday"], [])], []),
    # Home and away for the same days and meals cannot both hold.
    ("Mei eats at school and home on weekdays", [], [NO_POLARITY]),
    ("Mei is at home and at school on weekdays", [], [NO_POLARITY]),
    # Another person's part does not take the meals said for someone else.
    (
        "Ben eats lunch at school and dinner at home and Mei eats out on Fridays",
        [("Ben", False, ["friday"], ["lunch"]), ("Ben", True, ["friday"], ["dinner"]), ("Mei", False, ["friday"], [])],
        [],
    ),
    # A pronoun still refers back.
    (
        "Mei eats at school on weekdays. She eats at home on weekends.",
        [("Mei", False, WEEKDAYS, []), ("Mei", True, WEEKEND, [])],
        [],
    ),
]


@pytest.mark.parametrize(("text", "expected", "issues"), ROUND_2)
def test_and_parts_never_read_wider_than_said(text, expected, issues):
    result = read(text)
    assert result.issues == issues
    assert [(r.member_name, r.present, r.weekdays, r.meal_types) for r in result.rules] == expected


# Review round 3 of #328.
@pytest.mark.parametrize(
    "text",
    [
        # Someone else's home: the 's is a possessive, never "is home" (and never makes the owner home).
        "Ben eats at Mei's home on Fridays",
        "Ben is at his sister's home on Fridays",
        "Ben has dinner at his sister's home",
        "Ben is at his sister's home for dinner on Fridays",
        "Ben eats at the neighbour's home",
        "Mei eats at Grandma's home",
        # Working from home says nothing about meals, in Chinese as in English; nor does "comes home".
        "Ben在家办公",
        "Ben周三在家办公",
        "孩子周五在家上课",
        "Ben周五晚上在家加班",
        "Ben comes home on Fridays",
    ],
)
def test_a_home_that_is_not_theirs_or_says_nothing_is_reported(text):
    result = read(text)
    assert result.rules == [] and result.issues == [NO_POLARITY]


ROUND_3 = [
    # The contraction "Ben's home" is still home.
    ("Ben's home on Fridays", [("Ben", True, ["friday"], [])], []),
    # Pieces that pair their own days with meals or people never cross into a wider rule.
    (
        "Ben joins us for lunch on weekends and dinner on weekdays",
        [("Ben", True, WEEKEND, ["lunch"]), ("Ben", True, WEEKDAYS, ["dinner"])],
        [],
    ),
    (
        "Mei skips Monday lunch and Tuesday dinner",
        [("Mei", False, ["monday"], ["lunch"]), ("Mei", False, ["tuesday"], ["dinner"])],
        [],
    ),
    (
        "Mei is home for lunch on Monday and dinner on Tuesday",
        [("Mei", True, ["monday"], ["lunch"]), ("Mei", True, ["tuesday"], ["dinner"])],
        [],
    ),
    (
        "Ben is away on Mondays and Mei on Tuesdays",
        [("Ben", False, ["monday"], []), ("Mei", False, ["tuesday"], [])],
        [],
    ),
    ("I eat out on Mondays and Ben on Tuesdays", [("Ann", False, ["monday"], []), ("Ben", False, ["tuesday"], [])], []),
    (
        "Ben eats out on Mondays and Mei on Tuesdays and Ann on Wednesdays",
        [("Ben", False, ["monday"], []), ("Mei", False, ["tuesday"], []), ("Ann", False, ["wednesday"], [])],
        [],
    ),
    (
        "Ben is away on Fridays and so is Mei on Saturdays",
        [("Ben", False, ["friday"], []), ("Mei", False, ["saturday"], [])],
        [],
    ),
    ("Mei visits us on weekends and Ben on weekdays", [("Mei", True, WEEKEND, []), ("Ben", True, WEEKDAYS, [])], []),
    # A part that cannot be paired is reported, not guessed.
    (
        "Mei is home for lunch and dinner on Monday and breakfast on Tuesday",
        [("Mei", True, ["monday"], ["dinner"]), ("Mei", True, ["tuesday"], ["breakfast"])],
        [NO_DAYS],
    ),
    # A bare "<name> home on ..." is home.
    ("Mei home on weekdays and away on weekends", [("Mei", True, WEEKDAYS, []), ("Mei", False, WEEKEND, [])], []),
    (
        "Ben home on Fridays and away on Saturdays",
        [("Ben", True, ["friday"], []), ("Ben", False, ["saturday"], [])],
        [],
    ),
    # "out for dinner" is away.
    (
        "Ben is at home for lunch and out for dinner on Fridays",
        [("Ben", True, ["friday"], ["lunch"]), ("Ben", False, ["friday"], ["dinner"])],
        [],
    ),
    # A later part with its own person and no days could mean every day: reported, never given the first part's.
    ("Ben is home on Fridays and Mei is away", [("Ben", True, ["friday"], [])], [NO_DAYS]),
    ("Ben is away on weekdays and Mei is home", [("Ben", False, WEEKDAYS, [])], [NO_DAYS]),
]


@pytest.mark.parametrize(("text", "expected", "issues"), ROUND_3)
def test_paired_and_parts_read_as_said(text, expected, issues):
    result = read(text)
    assert result.issues == issues
    assert [(r.member_name, r.present, r.weekdays, r.meal_types) for r in result.rules] == expected


def test_paired_cooking_times_never_cross():
    result = read("weekend lunch and weekday dinner within 30 minutes", kind="cooking_time")
    assert result.issues == []
    assert [(r.weekdays, r.meal_types, r.max_minutes) for r in result.rules] == [
        (WEEKEND, ["lunch"], 30),
        (WEEKDAYS, ["dinner"], 30),
    ]


def test_an_unplaced_part_still_passes_its_meal_on():
    result = read(
        "Weekday lunch within 20 minutes and dinner within 45 minutes and weekends 90 minutes", kind="cooking_time"
    )
    assert result.issues == [NO_DAYS]
    assert [(r.weekdays, r.meal_types, r.max_minutes) for r in result.rules] == [
        (WEEKDAYS, ["lunch"], 20),
        (WEEKEND, ["dinner"], 90),
    ]
