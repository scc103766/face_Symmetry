from __future__ import annotations

from scripts.calibrate_v11_hb_proxy_with_review_labels import (
    COMPONENT_WEIGHTS,
    calibrated_score,
    calibrate_from_labels,
    candidate_weights,
    load_review_labels,
    normalize_weights,
    parse_label_value,
)


def test_parse_label_value_accepts_manual_review_terms() -> None:
    assert parse_label_value("不对称") == 1
    assert parse_label_value("阳性") == 1
    assert parse_label_value("对称") == 0
    assert parse_label_value("阴性") == 0
    assert parse_label_value("无法判断") is None


def test_load_review_labels_skips_quality_rejected_rows() -> None:
    patient_rows = [
        {"patient_sample_id": "p1"},
        {"patient_sample_id": "p2"},
        {"patient_sample_id": "p3"},
    ]
    label_rows = [
        {"patient_sample_id": "p1", "manual_face_asymmetry_label": "不对称"},
        {"patient_sample_id": "p2", "review_face_asymmetry_label": "对称"},
        {"patient_sample_id": "p3", "manual_face_asymmetry_label": "1", "quality_review_usable_for_calibration": "0"},
        {"patient_sample_id": "unknown", "manual_face_asymmetry_label": "1"},
    ]

    labels = load_review_labels(label_rows, patient_rows)

    assert labels["p1"]["manual_face_asymmetry_label"] == 1
    assert labels["p2"]["manual_face_asymmetry_label"] == 0
    assert "p3" not in labels
    assert "unknown" not in labels


def test_candidate_weights_include_normalized_base_weights() -> None:
    base = normalize_weights(COMPONENT_WEIGHTS)
    candidates = candidate_weights()

    assert base in candidates
    assert all(abs(sum(weights.values()) - 1.0) < 0.000001 for weights in candidates)


def test_calibrate_from_labels_selects_threshold_and_reports_metrics() -> None:
    patient_rows = []
    labeled = {}
    for idx in range(12):
        positive = idx >= 6
        score = "0.900000" if positive else "0.100000"
        patient_id = f"p{idx}"
        patient_rows.append(
            {
                "patient_sample_id": patient_id,
                "split": "test" if idx in {4, 5, 10, 11} else "train",
                "hb_proxy_grade_num": "5" if positive else "2",
                "resting_symmetry_score": score,
                "eye_closure_score": score,
                "brow_forehead_score": score,
                "smile_mouth_score": score,
                "gross_asymmetry_score": score,
                "movement_absence_score": score,
            }
        )
        labeled[patient_id] = {"manual_face_asymmetry_label": int(positive)}

    calibration = calibrate_from_labels(patient_rows, labeled)

    assert calibration["status"] == "calibrated"
    assert calibration["config"]["binary_threshold"] >= 0.89
    assert calibration["metrics"]["calibrated"]["all_labeled"]["balanced_accuracy"] == "1.000000"
    assert calibration["metrics"]["current_grade_v_plus"]["all_labeled"]["precision"] == "1.000000"


def test_calibrated_score_ignores_missing_component_values() -> None:
    weights = normalize_weights({"resting_symmetry_score": 1.0, "eye_closure_score": 1.0})
    row = {"resting_symmetry_score": "0.600000", "eye_closure_score": ""}

    assert calibrated_score(row, weights) == 0.6
