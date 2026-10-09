"""Interface labels stay English while selected messages retain their language."""

import re

from app.agent.limits import _option
from app.orchestration.interactions import household_size_interaction, say_interaction, typed_choice
from app.orchestration.runtime import variety_options, wish_options


def test_chinese_household_question_has_english_interface_and_stable_values():
    request = household_size_interaction(question_id="size", context_version=1, lang="zh")
    assert request.prompt == "Pick an option or type your answer"
    assert request.options[1].label == "2 people"
    assert request.options[1].value == 2
    assert request.options[1].id == "household_size_2"


def test_chinese_quick_replies_keep_message_language_but_not_label_language():
    for options in (wish_options("zh", planned=True), wish_options("zh", planned=False), variety_options("zh")):
        assert all(not re.search(r"[一-鿿]", label) for label, _ in options)
        assert all(re.search(r"[一-鿿]", value) for _, value in options)
        request = say_interaction(options=options, question_id="wish", context_version=1, lang="zh")
        assert typed_choice(request, options[0][1]) == options[0][1]


def test_budget_option_translates_people_in_label_only():
    label, value = _option("fewer_people_at", "zh", count=2, people="2人", amount=40)
    assert label == "2 people at S$40 a week"
    assert value == "2个人，一周40新币"
