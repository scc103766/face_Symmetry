from __future__ import annotations

import math

from scripts.build_no_manual_feature_validation import (
    LANDMARK,
    build_reference_stats,
    delta_features_for_role,
    selected_feature_names,
    threshold_for_specificity,
)


def test_selected_feature_names_keep_magnitude_evidence_and_exclude_pose_distance() -> None:
    rows = [
        {
            "sample_id": "s1",
            "patient_sample_id": "p1",
            "label_group": "不患病",
            "label_binary": "0",
            "media_role": "front",
            "detection_status": "detected",
            "raw_mouth_corner_vertical_asym": "0.1",
            "raw_eye_distance": "0.2",
            "pose_yaw_abs_deg": "3.0",
            "matrix_scale_0": "1.0",
            "bsdiff_mouthFrown_abs": "0.3",
            "bsdiff_mouthFrown_signed_left_minus_right": "-0.2",
        }
    ]

    names = selected_feature_names(rows)

    assert "raw_mouth_corner_vertical_asym" in names
    assert "bsdiff_mouthFrown_abs" in names
    assert "raw_eye_distance" not in names
    assert "pose_yaw_abs_deg" not in names
    assert "matrix_scale_0" not in names
    assert "bsdiff_mouthFrown_signed_left_minus_right" not in names


def test_reference_stats_use_median_mad_for_non_disease_reference_rows() -> None:
    rows = [
        {
            "patient_sample_id": f"p{i}",
            "label_binary": "0",
            "split": "train",
            "media_role": "front",
            "detection_status": "detected",
            "raw_mouth_corner_vertical_asym": str(value),
        }
        for i, value in enumerate([1.0, 2.0, 3.0, 4.0, 100.0], start=1)
    ]

    stats = build_reference_stats(
        rows,
        ["raw_mouth_corner_vertical_asym"],
        {f"p{i}" for i in range(1, 6)},
        ["train"],
        min_reference_n=5,
        max_pose_abs_deg=20.0,
    )

    row = stats[("front", "raw_mouth_corner_vertical_asym")]
    assert row["median"] == "3.000000"
    assert row["mad"] == "1.000000"
    assert row["robust_sigma"] == "1.482600"


def test_threshold_for_specificity_uses_next_value_to_keep_equal_scores_negative() -> None:
    rows = [
        {"label_binary": "0", "score": "1.0"},
        {"label_binary": "0", "score": "2.0"},
        {"label_binary": "0", "score": "3.0"},
        {"label_binary": "0", "score": "4.0"},
    ]

    threshold = threshold_for_specificity(rows, "score", 0.75)

    assert threshold > 3.0
    assert threshold < 4.0


def test_delta_mouth_corner_motion_asym_compares_front_to_action_role() -> None:
    front = [(0.0, 0.0, 0.0) for _ in range(478)]
    action = [(0.0, 0.0, 0.0) for _ in range(478)]
    front[LANDMARK["right_eye_outer"]] = (0.0, 0.0, 0.0)
    front[LANDMARK["left_eye_outer"]] = (1.0, 0.0, 0.0)
    action[LANDMARK["right_eye_outer"]] = (0.0, 0.0, 0.0)
    action[LANDMARK["left_eye_outer"]] = (1.0, 0.0, 0.0)
    for points in (front, action):
        points[LANDMARK["nose_bridge"]] = (0.5, 0.0, 0.0)
        points[LANDMARK["nose_tip"]] = (0.5, 0.5, 0.0)
        points[LANDMARK["chin"]] = (0.5, 1.0, 0.0)
        points[LANDMARK["upper_lip_center"]] = (0.5, 0.8, 0.0)
        points[LANDMARK["lower_lip_center"]] = (0.5, 0.9, 0.0)
    front[LANDMARK["left_mouth_corner"]] = (1.0, 1.0, 0.0)
    front[LANDMARK["right_mouth_corner"]] = (0.0, 1.0, 0.0)
    action[LANDMARK["left_mouth_corner"]] = (1.0, 2.0, 0.0)
    action[LANDMARK["right_mouth_corner"]] = (0.0, 1.5, 0.0)

    features = delta_features_for_role(front, action, "smile", scale=1.0)

    assert math.isclose(features["delta_mouth_corner_motion_asym"], 1.0 / 3.0, rel_tol=1e-6)
    assert math.isclose(features["delta_mouth_corner_vertical_motion_asym"], 1.0 / 3.0, rel_tol=1e-6)
