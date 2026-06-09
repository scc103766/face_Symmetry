from __future__ import annotations

from scripts.analyze_v11_grade_v_plus_generalization import is_stable_component, rule_is_accepted


def test_rule_acceptance_requires_test_gain_without_recall_drop() -> None:
    baseline = {
        "test": {
            "balanced_accuracy": 0.50,
            "precision": 0.70,
            "recall": 0.20,
        }
    }
    candidate = {
        "test": {
            "balanced_accuracy": 0.54,
            "precision": 0.75,
            "recall": 0.19,
        }
    }

    assert not rule_is_accepted(candidate, baseline)


def test_stable_component_requires_same_split_direction() -> None:
    rows = [
        {"split": "train", "direction": "diseased_higher", "standardized_effect": "0.300000"},
        {"split": "val", "direction": "nondisease_higher", "standardized_effect": "-0.300000"},
        {"split": "test", "direction": "diseased_higher", "standardized_effect": "0.300000"},
        {"split": "all", "direction": "diseased_higher", "standardized_effect": "0.300000"},
    ]

    assert not is_stable_component(rows, 0.30)
