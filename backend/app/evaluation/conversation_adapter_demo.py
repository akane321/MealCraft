"""Generate only invented conversation-apparatus evidence, never load episode files."""

import argparse
import json
from pathlib import Path

from app.evaluation.conversation_adapter import (
    CONFIRMATION_MESSAGE,
    VERSION,
    ConversationHarness,
    PlanDish,
    PlanMeal,
    PlanOutput,
    RuntimeConfig,
    UnifiedOutput,
)


def synthetic_report() -> dict:
    config = RuntimeConfig(anchor_date="2031-02-03")  # invented developer example, NOT a registered run date
    harness = ConversationHarness(config)

    def respond(message, history, instructions):
        if message == "Wait for my confirmation.":
            return UnifiedOutput(awaiting_confirmation=True)
        previous_name = history[-1].output.plan.meals[0].dishes[0].name if message == "Change that dish." else None
        return UnifiedOutput(
            plan=PlanOutput(
                meals=[
                    PlanMeal(
                        date="2031-02-04",
                        meal_type="dinner",
                        dishes=[PlanDish(name=f"Changed {previous_name}" if previous_name else "Invented bean bowl")],
                    )
                ]
            )
        )

    cases = (
        ("single-turn", ["Plan an invented dinner."]),
        ("confirmation", ["Wait for my confirmation."]),
        ("own-prior-turn", ["Plan an invented dinner.", "Change that dish."]),
    )
    results = [
        {"synthetic_case": name, "result": harness.run("synthetic-stub", turns, respond).model_dump(mode="json")}
        for name, turns in cases
    ]
    return {
        "version": VERSION,
        "scope": "Invented stub conversations only; no product end-to-end or formal evaluation claim",
        "registration": "pending independent neutrality review and preregistration",
        "runtime": config.model_dump(mode="json"),
        "shared_instructions": harness.instructions,
        "confirmation_message": CONFIRMATION_MESSAGE,
        "confirmation_counts": dict(harness.confirmation_counts),
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(synthetic_report(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
