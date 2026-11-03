"""Canonical single-component ablations exposed to evaluation orchestration.

These names describe evaluation conditions, not product configuration.  A run
may select one condition at a time while the normal product path keeps every
component enabled.
"""

from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict

AblationCondition = Literal[
    "retrieval_off",
    "rule_only_parser",
    "independent_validator_off",
    "repair_off",
    "diversity_off",
    "local_improvement_off",
]

ABLATION_CONDITIONS: tuple[AblationCondition, ...] = get_args(AblationCondition)


class AblationConfiguration(BaseModel):
    """Machine-readable condition recorded beside an evaluation arm."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: AblationCondition

    @property
    def parser_provider(self) -> Literal["fixture"] | None:
        return "fixture" if self.condition == "rule_only_parser" else None

    @property
    def retrieval_enabled(self) -> bool:
        return self.condition != "retrieval_off"

    @property
    def independent_validator_enabled(self) -> bool:
        return self.condition != "independent_validator_off"

    @property
    def repair_enabled(self) -> bool:
        return self.condition != "repair_off"

    @property
    def diversity_enabled(self) -> bool:
        return self.condition != "diversity_off"

    @property
    def local_improvement_enabled(self) -> bool:
        return self.condition != "local_improvement_off"


def ablation_descriptors() -> list[dict[str, str]]:
    """Where each condition is executed, for sealed/developer run manifests."""

    runners = {
        "retrieval_off": ("planning-components", "retrieval_off"),
        "rule_only_parser": ("agent-benchmark", "fixture"),
        "independent_validator_off": ("planning-final-gate", "final_gate_off"),
        "repair_off": ("planning-components", "repair_off"),
        "diversity_off": ("planning-components", "diversity_off"),
        "local_improvement_off": ("developer-planning", "local_improvement=False"),
    }
    return [
        {"condition": condition, "evaluation": runners[condition][0], "setting": runners[condition][1]}
        for condition in ABLATION_CONDITIONS
    ]
