from __future__ import annotations

from scripts.build_v11_hb_proxy_grading import (
    binary_metrics,
    build_grade_v_plus_asymmetry_cases,
    build_mediapipe_grade_differences,
    build_patient_grade,
    grade_descriptor_for,
    grade_v_plus_asymmetry_payload,
    hb_grade_num,
)


def test_hb_grade_num_uses_ordered_thresholds() -> None:
    thresholds = [0.2, 0.4, 0.6, 0.8, 0.9]

    assert hb_grade_num(0.10, thresholds) == 1
    assert hb_grade_num(0.45, thresholds) == 3
    assert hb_grade_num(0.95, thresholds) == 6


def test_missing_dynamic_role_forces_manual_review() -> None:
    base = {
        "patient_sample_id": "patient-1",
        "label_group": "患病",
        "label_binary": "1",
        "split": "test",
        "core_row_available": "1",
        "core_row": {
            "front_available": "1",
            "smile_available": "1",
            "teeth_available": "1",
            "eyes_closed_available": "0",
            "forehead_wrinkle_available": "1",
            "frown_available": "1",
            "included_roles_available": "5",
            "v11_asymmetry_score": "0.72",
        },
        "components": {
            "resting_symmetry_score": 0.60,
            "eye_closure_score": None,
            "brow_forehead_score": 0.70,
            "smile_mouth_score": 0.75,
            "gross_asymmetry_score": 0.72,
            "movement_absence_score": 0.20,
            "quality_reliability_score": 0.85,
        },
    }
    thresholds = {
        "grade_thresholds": [0.20, 0.40, 0.55, 0.70, 0.85],
        "component_thresholds": {
            "resting_symmetry_score": [0.30, 0.50, 0.70],
            "eye_closure_score": [0.30, 0.50, 0.70],
            "brow_forehead_score": [0.30, 0.50, 0.70],
            "smile_mouth_score": [0.30, 0.50, 0.70],
            "gross_asymmetry_score": [0.30, 0.50, 0.70],
            "movement_absence_score": [0.10, 0.20, 0.30],
        },
        "movement_absence_high": 0.30,
        "score_span": 0.80,
    }

    row, component_rows = build_patient_grade(base, thresholds, {})

    assert row["hb_needs_manual_review"] == "1"
    assert "missing_role_eyes_closed" in row["hb_reason_codes"]
    assert row["hb_eye_closure_level"] == "missing"
    assert len(component_rows) >= 6


def test_binary_metrics_from_grade_threshold() -> None:
    rows = [
        {"label_binary": "1", "hb_proxy_grade_num": 3},
        {"label_binary": "1", "hb_proxy_grade_num": 1},
        {"label_binary": "0", "hb_proxy_grade_num": 4},
        {"label_binary": "0", "hb_proxy_grade_num": 1},
    ]

    metrics = binary_metrics(rows, 3)

    assert metrics["tp"] == 1
    assert metrics["fn"] == 1
    assert metrics["fp"] == 1
    assert metrics["tn"] == 1
    assert metrics["balanced_accuracy"] == 0.5


def test_grade_descriptor_maps_hb_symmetry_terms() -> None:
    assert grade_descriptor_for(1)["resting_symmetry_label"] == "对称"
    assert grade_descriptor_for(2)["resting_symmetry_label"] == "粗略对称"
    assert grade_descriptor_for(6)["resting_symmetry_label"] == "极度不对称"
    assert grade_descriptor_for(6)["dynamic_symmetry_label"] == "无动态"
    assert grade_descriptor_for(None)["resting_symmetry_label"] == "无法判定"


def test_grade_v_plus_outputs_face_asymmetry_with_reason() -> None:
    row = {
        "patient_sample_id": "patient-1",
        "label_group": "患病",
        "label_binary": "1",
        "split": "test",
        "hb_proxy_grade": "Grade V",
        "hb_proxy_grade_num": 5,
        "hb_proxy_grade_name": "Grade V 重度功能障碍代理",
        "hb_grade_confidence": "0.880000",
        "hb_grade_descriptor": "静息极度不对称，动态严重不对称。",
        "hb_resting_symmetry_label": "极度不对称",
        "hb_dynamic_symmetry_label": "严重不对称",
        "hb_eye_closure_label": "闭眼不完全风险",
        "hb_mouth_brow_motion_label": "严重眉毛抬高和笑容不对称",
        "hb_resting_level": "severe",
        "hb_eye_closure_level": "moderate",
        "hb_brow_forehead_level": "severe",
        "hb_smile_mouth_level": "severe",
        "hb_gross_asymmetry_level": "severe",
        "forehead_dynamic_abnormality_level": "severe",
        "glabella_motion_abnormality_level": "severe",
        "resting_symmetry_score": "0.900000",
        "eye_closure_score": "0.650000",
        "brow_forehead_score": "0.820000",
        "smile_mouth_score": "0.850000",
        "gross_asymmetry_score": "0.880000",
        "movement_absence_score": "0.400000",
        "hb_movement_absence_flag": "1",
        "hb_needs_manual_review": "0",
        "hb_reason_codes": "hb_proxy_not_clinical;severe_smile_mouth_score",
        "top_positive_features": "raw_mouth_corner_vertical_asym;raw_all_mesh_region_centroid_y_asym",
        "hb_component_evidence": "",
    }

    payload = grade_v_plus_asymmetry_payload(row)
    row.update(payload)
    cases = build_grade_v_plus_asymmetry_cases([row, {"hb_proxy_grade_num": 4, "face_asymmetry_grade_v_plus_flag": "0"}])

    assert payload["face_asymmetry_grade_v_plus_flag"] == "1"
    assert payload["face_asymmetry_output"] == "人脸不对称"
    assert "达到 Grade V+ 阈值" in payload["face_asymmetry_reason"]
    assert "静息表现：极度不对称" in payload["face_asymmetry_reason"]
    assert "微笑/示齿口部动态为严重" in payload["face_asymmetry_reason"]
    assert "整体不对称为严重" in payload["face_asymmetry_reason"]
    assert "raw_all_mesh_region_centroid_y_asym" in payload["face_asymmetry_reason"]
    assert len(cases) == 1


def test_mediapipe_grade_differences_use_landmarks_and_exclude_pose_distance() -> None:
    grade_rows = [
        {"patient_sample_id": "patient-1", "hb_proxy_grade_num": 1},
        {"patient_sample_id": "patient-2", "hb_proxy_grade_num": 6},
    ]
    feature_rows = [
        {
            "patient_sample_id": "patient-1",
            "sample_id": "patient-1-front",
            "label_group": "不患病",
            "label_binary": "0",
            "media_role": "front",
            "detection_status": "detected",
            "raw_all_mesh_region_centroid_y_asym": "0.100000",
            "bs_mouth_smile_left": "0.200000",
            "matrix_scale": "999.000000",
            "pose_roll": "3.000000",
            "raw_eye_distance": "1.000000",
        },
        {
            "patient_sample_id": "patient-2",
            "sample_id": "patient-2-front",
            "label_group": "患病",
            "label_binary": "1",
            "media_role": "front",
            "detection_status": "detected",
            "raw_all_mesh_region_centroid_y_asym": "0.500000",
            "bs_mouth_smile_left": "0.700000",
            "matrix_scale": "1000.000000",
            "pose_roll": "4.000000",
            "raw_eye_distance": "2.000000",
        },
    ]

    rows = build_mediapipe_grade_differences(feature_rows, grade_rows)

    all_core_all_mesh = next(
        row
        for row in rows
        if row["scope"] == "all_core_roles" and row["feature_name"] == "raw_all_mesh_region_centroid_y_asym"
    )
    feature_names = {row["feature_name"] for row in rows}
    assert all_core_all_mesh["feature_source"] == "mediapipe_478_all_landmarks"
    assert all_core_all_mesh["grade_i_mean"] == "0.100000"
    assert all_core_all_mesh["grade_vi_mean"] == "0.500000"
    assert all_core_all_mesh["standardized_i_to_vi_effect"] == "2.000000"
    assert "matrix_scale" not in feature_names
    assert "pose_roll" not in feature_names
    assert "raw_eye_distance" not in feature_names
