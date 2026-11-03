from app.evaluation.ablation_conditions import (
    ABLATION_CONDITIONS,
    AblationConfiguration,
    ablation_descriptors,
)


def test_all_six_ablation_conditions_have_one_reproducible_runner_mapping():
    assert ABLATION_CONDITIONS == (
        "retrieval_off",
        "rule_only_parser",
        "independent_validator_off",
        "repair_off",
        "diversity_off",
        "local_improvement_off",
    )
    descriptors = ablation_descriptors()
    assert [item["condition"] for item in descriptors] == list(ABLATION_CONDITIONS)
    assert all(item["evaluation"] and item["setting"] for item in descriptors)


def test_each_condition_disables_only_its_named_component():
    expected = {
        "retrieval_off": "retrieval_enabled",
        "independent_validator_off": "independent_validator_enabled",
        "repair_off": "repair_enabled",
        "diversity_off": "diversity_enabled",
        "local_improvement_off": "local_improvement_enabled",
    }
    for condition, attribute in expected.items():
        configuration = AblationConfiguration(condition=condition)
        assert getattr(configuration, attribute) is False
        assert configuration.parser_provider is None
    assert AblationConfiguration(condition="rule_only_parser").parser_provider == "fixture"
