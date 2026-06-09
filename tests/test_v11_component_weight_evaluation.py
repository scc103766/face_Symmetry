from __future__ import annotations

from scripts.evaluate_v11_component_weights import (
    COMPONENTS,
    add_normalized_components,
    bounded_normalize_weights,
    build_component_normalizers,
    build_patient_set_from_original_inputs,
    build_universal_feature_scores,
    component_for_feature,
    evaluate_candidate_schemes,
    make_threshold_scheme,
    split_rows,
)


def synthetic_split_rows() -> list[dict[str, str]]:
    return [
        {
            "patient_sample_id": patient_id,
            "label_group": "患病" if label == "1" else "不患病",
            "label_binary": label,
            "split": split,
        }
        for patient_id, label, split, _value in synthetic_specs()
    ]


def synthetic_core_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for patient_id, label, split, value in synthetic_specs():
        row = {
            "patient_sample_id": patient_id,
            "label_group": "患病" if label == "1" else "不患病",
            "label_binary": label,
            "split": split,
            "core_result": "synthetic",
            "included_roles_available": "6",
            "patient_weight_total": "1.000000",
            "top_positive_features": "raw_lip_midline_deviation",
            "v11_asymmetry_score": f"{value:.6f}",
            "v11_asymmetry_z": "0.000000",
        }
        for role in ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown"):
            row[f"{role}_available"] = "1"
            row[f"{role}_score"] = f"{value:.6f}"
            row[f"{role}_weight"] = "1.000000"
        rows.append(row)
    return rows


def synthetic_specs() -> list[tuple[str, str, str, float]]:
    specs = [
        ("p1", "1", "train", 0.90),
        ("p2", "0", "train", 0.20),
        ("p3", "1", "val", 0.85),
        ("p4", "0", "val", 0.10),
        ("p5", "1", "test", 0.80),
        ("p6", "0", "test", 0.10),
    ]
    return specs


def test_bounded_normalize_weights_respects_component_limits() -> None:
    weights = bounded_normalize_weights({component: index for index, component in enumerate(COMPONENTS)})

    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert all(0.05 <= weight <= 0.30 for weight in weights.values())


def test_patient_set_is_rebuilt_from_original_inputs() -> None:
    patient_set = build_patient_set_from_original_inputs(synthetic_split_rows(), synthetic_core_rows(), [])
    first = patient_set[0]

    assert "standalone_overall_score" in first
    assert "hb_proxy_grade_num_current" not in first
    assert "face_asymmetry_output_current" not in first
    assert all(row["core_row_available"] == "1" for row in patient_set)


def test_threshold_scheme_uses_normalized_rows_not_raw_rows() -> None:
    patient_set = build_patient_set_from_original_inputs(synthetic_split_rows(), synthetic_core_rows(), [])
    normalizers = build_component_normalizers(split_rows(patient_set, "train"))
    normalized = add_normalized_components(patient_set, normalizers)
    weights = {component: 1.0 / len(COMPONENTS) for component in COMPONENTS}
    scheme = make_threshold_scheme("uniform_weights", weights, split_rows(normalized, "val"))

    assert scheme["threshold"] > 0.0

    candidate_rows, _summary = evaluate_candidate_schemes(normalized, [scheme])
    test_row = next(row for row in candidate_rows if row["scheme"] == "uniform_weights" and row["evaluation_split"] == "test")
    assert test_row["tp"] == 1
    assert test_row["fp"] == 0


def test_universal_feature_scores_restore_split_from_patient_set() -> None:
    split_map = {patient_id: split for patient_id, _label, split, _value in [
        ("p1", "1", "train", 0.90),
        ("p2", "0", "train", 0.20),
        ("p3", "1", "val", 0.85),
        ("p4", "0", "val", 0.10),
        ("p5", "1", "test", 0.80),
        ("p6", "0", "test", 0.10),
    ]}
    feature_rows = []
    for patient_id, label, _split, value in [
        ("p1", "1", "train", 0.90),
        ("p2", "0", "train", 0.20),
        ("p3", "1", "val", 0.85),
        ("p4", "0", "val", 0.10),
        ("p5", "1", "test", 0.80),
        ("p6", "0", "test", 0.10),
    ]:
        feature_rows.append(
            {
                "sample_id": f"{patient_id}-front",
                "patient_sample_id": patient_id,
                "label_binary": label,
                "label_group": "患病" if label == "1" else "不患病",
                "media_role": "front",
                "detection_status": "detected",
                "raw_eyebrow_region_height_asym": f"{value:.6f}",
                "pose_roll": "10.0",
            }
        )

    rows = build_universal_feature_scores(feature_rows, split_map, min_label_count=1)
    eyebrow = next(row for row in rows if row["feature_name"] == "raw_eyebrow_region_height_asym")

    assert eyebrow["component_target"] == "brow_forehead_score"
    assert eyebrow["direction_consistency"] == "1.000000"
    assert float(eyebrow["universal_feature_score"]) > 0.0
    assert component_for_feature("raw_eyebrow_region_height_asym") == "brow_forehead_score"
