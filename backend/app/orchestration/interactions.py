from datetime import UTC, datetime

from app.orchestration.contracts import (
    InteractionAnswer,
    InteractionOption,
    InteractionRequest,
    InteractionType,
)


class InteractionAnswerError(ValueError):
    pass


def household_size_interaction(*, question_id: str, context_version: int) -> InteractionRequest:
    return InteractionRequest(
        type=InteractionType.SINGLE_SELECT,
        prompt="How many people should this plan serve?",
        field_path="household_size",
        question_id=question_id,
        options=[
            InteractionOption(
                id=f"household_size_{size}",
                label=f"{size} {'person' if size == 1 else 'people'}",
                value=size,
            )
            for size in range(1, 5)
        ],
        allow_free_text=True,
        context_version=context_version,
    )


def pantry_quantity_interaction(
    *,
    ingredient_name: str,
    question_id: str,
    context_version: int,
) -> InteractionRequest:
    display_name = ingredient_name.replace("_", " ")
    return InteractionRequest(
        type=InteractionType.QUANTITY_INPUT,
        prompt=(
            f"How much {display_name} do you already have? "
            "Enter a quantity and unit, or choose unknown to use it only for ranking."
        ),
        field_path=f"available_ingredients.{ingredient_name}.quantity",
        question_id=question_id,
        options=[InteractionOption(id="quantity_unknown", label="I don't know", value="unknown")],
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
