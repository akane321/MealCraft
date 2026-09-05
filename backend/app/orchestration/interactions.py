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
            InteractionOption(id=f"household_size_{size}", label=f"{size} people", value=size) for size in range(1, 5)
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
) -> list[object]:
    if answer.question_id != request.question_id:
        raise InteractionAnswerError("answer does not match the pending question")
    if answer.context_version != request.context_version or answer.context_version != current_context_version:
        raise InteractionAnswerError("answer belongs to a stale conversation context")
    if request.plan_revision is not None:
        if answer.plan_revision != request.plan_revision or answer.plan_revision != current_plan_revision:
            raise InteractionAnswerError("answer belongs to a stale plan revision")

    options = {option.id: option.value for option in request.options}
    unknown_ids = [option_id for option_id in answer.option_ids if option_id not in options]
    if unknown_ids:
        raise InteractionAnswerError(f"unknown option IDs: {', '.join(unknown_ids)}")
    if answer.free_text and not request.allow_free_text:
        raise InteractionAnswerError("free-text answers are not allowed for this interaction")
    if request.type in {InteractionType.SINGLE_SELECT, InteractionType.QUICK_REPLY, InteractionType.CONFIRMATION}:
        if len(answer.option_ids) > 1:
            raise InteractionAnswerError("this interaction accepts at most one option")
    return [options[option_id] for option_id in answer.option_ids]
