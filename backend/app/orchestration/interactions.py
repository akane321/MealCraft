from datetime import UTC, datetime

from app.agent.replies import people, say, word
from app.orchestration.contracts import (
    InteractionAnswer,
    InteractionOption,
    InteractionRequest,
    InteractionType,
)


class InteractionAnswerError(ValueError):
    pass


# The interaction whose options are things the household could have typed: an answer is sent as their message.
SAY_FIELD = "message"


def household_size_interaction(*, question_id: str, context_version: int, lang: str = "en") -> InteractionRequest:
    return InteractionRequest(
        type=InteractionType.SINGLE_SELECT,
        prompt=say("ask_people_short", lang),
        field_path="household_size",
        question_id=question_id,
        options=[
            InteractionOption(id=f"household_size_{size}", label=people(size, lang), value=size) for size in range(1, 5)
        ],
        allow_free_text=True,
        context_version=context_version,
    )


def pantry_quantity_interaction(
    *,
    ingredient_name: str,
    question_id: str,
    context_version: int,
    lang: str = "en",
) -> InteractionRequest:
    return InteractionRequest(
        type=InteractionType.QUANTITY_INPUT,
        prompt=say("ask_quantity_short", lang, name=word(ingredient_name, lang)),
        field_path=f"available_ingredients.{ingredient_name}.quantity",
        question_id=question_id,
        options=[InteractionOption(id="quantity_unknown", label=say("unknown_quantity", lang), value="unknown")],
        allow_free_text=True,
        context_version=context_version,
    )


def unmatched_term_interaction(
    *,
    term: str,
    meant_for: str,
    options: list[str],
    prompt: str,
    question_id: str,
    context_version: int,
    lang: str = "en",
) -> InteractionRequest:
    """Offer the catalog ingredients a word might mean. The field it was written into travels in the
    field path, so the answer lands as an exclusion or a pantry item without asking the model again."""
    return InteractionRequest(
        type=InteractionType.SINGLE_SELECT,
        prompt=prompt,
        field_path=f"unmatched.{meant_for}.{term}",
        question_id=question_id,
        options=[
            InteractionOption(id=f"ingredient_{option}", label=word(option, lang), value=option) for option in options
        ],
        allow_free_text=True,
        context_version=context_version,
    )


def say_interaction(
    *, prompt: str, options: list[tuple[str, str]], question_id: str, context_version: int
) -> InteractionRequest:
    """Choices the household can tap instead of typing: each sends its own sentence (`SAY_FIELD`)."""
    return InteractionRequest(
        type=InteractionType.QUICK_REPLY if options else InteractionType.FREE_TEXT,
        prompt=prompt,
        field_path=SAY_FIELD,
        question_id=question_id,
        options=[
            InteractionOption(id=f"say_{index}", label=label, value=text) for index, (label, text) in enumerate(options)
        ],
        allow_free_text=True,
        context_version=context_version,
    )


def validate_interaction_answer(
    request: InteractionRequest,
    answer: InteractionAnswer,
    *,
    current_context_version: int,
    current_plan_revision: int | None = None,
    now: datetime | None = None,
) -> list[object]:
    if answer.question_id != request.question_id:
        raise InteractionAnswerError("answer does not match the pending question")
    if answer.context_version != request.context_version or answer.context_version != current_context_version:
        raise InteractionAnswerError("answer belongs to a stale conversation context")
    if request.plan_revision is not None:
        if answer.plan_revision != request.plan_revision or answer.plan_revision != current_plan_revision:
            raise InteractionAnswerError("answer belongs to a stale plan revision")
    if request.expires_at is not None:
        checked_at = now or datetime.now(UTC)
        expires_at = request.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if checked_at >= expires_at:
            raise InteractionAnswerError("answer belongs to an expired interaction")

    options = {option.id: option.value for option in request.options}
    if len(answer.option_ids) != len(set(answer.option_ids)):
        raise InteractionAnswerError("duplicate option IDs are not allowed")
    unknown_ids = [option_id for option_id in answer.option_ids if option_id not in options]
    if unknown_ids:
        raise InteractionAnswerError(f"unknown option IDs: {', '.join(unknown_ids)}")
    if answer.free_text and not request.allow_free_text:
        raise InteractionAnswerError("free-text answers are not allowed for this interaction")
    if answer.free_text and answer.option_ids:
        raise InteractionAnswerError("choose an option or provide free text, not both")
    if request.type in {InteractionType.SINGLE_SELECT, InteractionType.QUICK_REPLY, InteractionType.CONFIRMATION}:
        if len(answer.option_ids) > 1:
            raise InteractionAnswerError("this interaction accepts at most one option")
    if not answer.option_ids and not (answer.free_text and answer.free_text.strip()):
        raise InteractionAnswerError("interaction answer cannot be empty")
    values = [options[option_id] for option_id in answer.option_ids]
    if answer.free_text:
        values.append(answer.free_text.strip())
    return values
