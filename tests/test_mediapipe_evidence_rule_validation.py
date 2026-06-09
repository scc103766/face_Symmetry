from __future__ import annotations

from scripts.validate_mediapipe_evidence_on_rule_test_set import (
    build_patient_feature_rows,
    support_status,
    validation_for_rows,
)


def test_support_status_uses_direction_and_auc_thresholds() -> None:
    assert support_status(True, 0.61) == "strong_supported"
    assert support_status(True, 0.56) == "supported"
    assert support_status(True, 0.51) == "weak_supported"
    assert support_status(True, 0.50) == "not_supported"
    assert support_status(False, 0.80) == "not_supported"


def test_patient_feature_rows_aggregate_mean_and_max_per_patient() -> None:
    rows = [
        {
            "patient_sample_id": "p1",
            "patient_id": "1",
            "label_group": "患病",
            "label_binary": "1",
            "media_role": "front_contour",
            "raw_lip_midline_deviation": "0.1",
        },
        {
            "patient_sample_id": "p1",
            "patient_id": "1",
            "label_group": "患病",
            "label_binary": "1",
            "media_role": "smile_teeth",
            "raw_lip_midline_deviation": "0.3",
        },
    ]

    aggregated = build_patient_feature_rows(rows, ("front_contour", "smile_teeth"))
    all_max = next(row for row in aggregated if row["role_scope"] == "all" and row["aggregation"] == "max")
    all_mean = next(row for row in aggregated if row["role_scope"] == "all" and row["aggregation"] == "mean")

    assert all_max["raw_lip_midline_deviation"] == "0.300000"
    assert all_mean["raw_lip_midline_deviation"] == "0.200000"
    assert all_max["image_count"] == "2"


def test_validation_for_rows_reports_patient_higher_support() -> None:
    rows = [
        {"label_binary": "1", "raw_lip_midline_deviation": str(value)}
        for value in [0.4, 0.5, 0.6, 0.7, 0.8]
    ] + [
        {"label_binary": "0", "raw_lip_midline_deviation": str(value)}
        for value in [0.1, 0.2, 0.3, 0.4, 0.5]
    ]

    validation = validation_for_rows("patient", "all", "max", rows)
    lip_row = next(row for row in validation if row["feature_name"] == "raw_lip_midline_deviation")

    assert lip_row["direction_matches_expected"] == "true"
    assert lip_row["support_status"] in {"supported", "strong_supported"}
