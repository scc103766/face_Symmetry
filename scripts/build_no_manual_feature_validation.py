#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

CORE_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
ACTION_ROLES = ("smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
REFERENCE_SPLITS = ("train",)
CALIBRATION_SPLITS = ("val",)
EVALUATION_SPLITS = ("train", "val", "test", "all")
SPECIFICITY_TARGETS = (0.85, 0.90, 0.95)
EPSILON = 1e-9

POSE_DISTANCE_FEATURE_PREFIXES = ("matrix_", "pose_")
POSE_DISTANCE_FEATURE_SUFFIXES = ("_centroid_z_asym",)
POSE_DISTANCE_FEATURE_TOKENS = ("yaw", "pitch", "roll", "scale", "distance", "bbox", "translation")

LANDMARK = {
    "left_eye_outer": 263,
    "right_eye_outer": 33,
    "left_eye_upper": 386,
    "left_eye_lower": 374,
    "right_eye_upper": 159,
    "right_eye_lower": 145,
    "left_brow_inner": 336,
    "left_brow_outer": 276,
    "right_brow_inner": 107,
    "right_brow_outer": 46,
    "left_mouth_corner": 291,
    "right_mouth_corner": 61,
    "upper_lip_center": 13,
    "lower_lip_center": 14,
    "nose_bridge": 168,
    "nose_tip": 1,
    "chin": 152,
}


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    split_rows = read_csv(required(metadata / "05_patient_splits.csv"))
    feature_rows = add_split_to_feature_rows(read_csv(required(metadata / "09_mediapipe_full_features.csv")), split_rows)
    hb_rows = read_csv(required(metadata / "12_v11_hb_proxy_patient_grades.csv"))
    keypoint_rows = read_csv(required(metadata / "03_keypoints.csv"))

    feature_names = selected_feature_names(feature_rows)
    reference_patients = reference_patient_ids(feature_rows, args.reference_splits, args.min_reference_roles)
    reference_stats = build_reference_stats(
        feature_rows,
        feature_names,
        reference_patients,
        args.reference_splits,
        args.min_reference_n,
        args.max_pose_abs_deg,
    )
    image_feature_z_rows, image_role_scores = build_image_feature_z_rows(feature_rows, reference_stats, args.top_k, args.z_cap)
    patient_outlier_rows = build_patient_outlier_scores(split_rows, image_role_scores)

    delta_rows = build_delta_motion_features(dataset, keypoint_rows, split_rows)
    delta_reference_stats = build_delta_reference_stats(
        delta_rows,
        args.reference_splits,
        args.min_delta_reference_n,
    )
    delta_patient_rows = build_delta_patient_scores(split_rows, delta_rows, delta_reference_stats, args.top_k, args.z_cap)

    threshold_rows, summary = build_threshold_sweep(
        split_rows,
        hb_rows,
        patient_outlier_rows,
        delta_patient_rows,
        args.calibration_splits,
        args.specificity_targets,
    )
    summary.update(
        {
            "dataset": dataset.name,
            "feature_count": len(feature_names),
            "z_cap": args.z_cap,
            "normal_reference_patient_count": len(reference_patients),
            "normal_reference_stats_rows": len(reference_stats),
            "image_feature_z_rows": len(image_feature_z_rows),
            "patient_outlier_rows": len(patient_outlier_rows),
            "delta_motion_rows": len(delta_rows),
            "delta_reference_stats_rows": len(delta_reference_stats),
            "delta_patient_rows": len(delta_patient_rows),
            "outputs": {
                "normal_reference_stats": "metadata/30_no_manual_normal_reference_stats.csv",
                "image_feature_z_scores": "metadata/30_no_manual_image_feature_z_scores.csv",
                "patient_outlier_scores": "metadata/30_no_manual_patient_outlier_scores.csv",
                "delta_motion_features": "metadata/31_no_manual_delta_motion_features.csv",
                "delta_motion_reference_stats": "metadata/31_no_manual_delta_motion_reference_stats.csv",
                "delta_motion_patient_scores": "metadata/31_no_manual_delta_motion_patient_scores.csv",
                "threshold_sweep": "metadata/32_no_manual_threshold_sweep.csv",
                "summary_json": "metadata/32_no_manual_validation_summary.json",
                "summary_report": "reports/32_no_manual_validation_summary.md",
            },
        }
    )

    write_csv(metadata / "30_no_manual_normal_reference_stats.csv", list(reference_stats.values()))
    write_csv(metadata / "30_no_manual_image_feature_z_scores.csv", image_feature_z_rows)
    write_csv(metadata / "30_no_manual_patient_outlier_scores.csv", patient_outlier_rows)
    write_csv(metadata / "31_no_manual_delta_motion_features.csv", delta_rows)
    write_csv(metadata / "31_no_manual_delta_motion_reference_stats.csv", list(delta_reference_stats.values()))
    write_csv(metadata / "31_no_manual_delta_motion_patient_scores.csv", delta_patient_rows)
    write_csv(metadata / "32_no_manual_threshold_sweep.csv", threshold_rows)
    write_json(metadata / "32_no_manual_validation_summary.json", summary)
    write_report(reports / "32_no_manual_validation_summary.md", summary, threshold_rows)

    print(f"Wrote {metadata / '30_no_manual_normal_reference_stats.csv'}")
    print(f"Wrote {metadata / '30_no_manual_image_feature_z_scores.csv'}")
    print(f"Wrote {metadata / '30_no_manual_patient_outlier_scores.csv'}")
    print(f"Wrote {metadata / '31_no_manual_delta_motion_features.csv'}")
    print(f"Wrote {metadata / '31_no_manual_delta_motion_reference_stats.csv'}")
    print(f"Wrote {metadata / '31_no_manual_delta_motion_patient_scores.csv'}")
    print(f"Wrote {metadata / '32_no_manual_threshold_sweep.csv'}")
    print(f"Wrote {metadata / '32_no_manual_validation_summary.json'}")
    print(f"Wrote {reports / '32_no_manual_validation_summary.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build no-manual-label feature validation outputs from MediaPipe feature tables."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing metadata outputs.")
    parser.add_argument("--top-k", type=int, default=5, help="Top positive z-scores to average for role scores.")
    parser.add_argument("--z-cap", type=float, default=10.0, help="Clip positive z-scores at this value for scoring.")
    parser.add_argument("--min-reference-roles", type=int, default=6, help="Required detected core roles for reference patients.")
    parser.add_argument("--min-reference-n", type=int, default=20, help="Minimum image count per role-feature reference stat.")
    parser.add_argument("--min-delta-reference-n", type=int, default=20, help="Minimum patient count per action-feature delta stat.")
    parser.add_argument(
        "--max-pose-abs-deg",
        type=float,
        default=20.0,
        help="Maximum abs yaw/pitch/roll for normal reference rows.",
    )
    parser.add_argument(
        "--reference-splits",
        nargs="+",
        default=list(REFERENCE_SPLITS),
        choices=("train", "val", "test"),
        help="Splits used to build non-disease normal reference stats.",
    )
    parser.add_argument(
        "--calibration-splits",
        nargs="+",
        default=list(CALIBRATION_SPLITS),
        choices=("train", "val", "test"),
        help="Splits used to fix specificity thresholds.",
    )
    parser.add_argument(
        "--specificity-targets",
        nargs="+",
        type=float,
        default=list(SPECIFICITY_TARGETS),
        help="Specificity targets for threshold calibration.",
    )
    return parser.parse_args()


def required(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Required input is missing: {path}")
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row if not str(key).startswith("_")})
    preferred = [
        "patient_sample_id",
        "sample_id",
        "label_group",
        "label_binary",
        "split",
        "media_role",
        "action_role",
        "feature_name",
        "feature_family",
        "method",
        "score_name",
        "specificity_target",
        "evaluation_split",
    ]
    fields = [field for field in preferred if field in fields] + [field for field in fields if field not in preferred]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def add_split_to_feature_rows(
    feature_rows: list[dict[str, str]],
    split_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    split_by_patient = {row["patient_sample_id"]: row for row in split_rows}
    output: list[dict[str, str]] = []
    for row in feature_rows:
        split_row = split_by_patient.get(row.get("patient_sample_id", ""))
        copied = dict(row)
        if split_row:
            copied["split"] = split_row.get("split", "")
            copied["label_group"] = copied.get("label_group") or split_row.get("label_group", "")
            copied["label_binary"] = copied.get("label_binary") or split_row.get("label_binary", "")
        output.append(copied)
    return output


def selected_feature_names(rows: list[Mapping[str, str]]) -> list[str]:
    if not rows:
        return []
    metadata_fields = {"sample_id", "patient_sample_id", "label_group", "label_binary", "split", "media_role", "detection_status"}
    return sorted(name for name in rows[0] if name not in metadata_fields and is_magnitude_evidence_feature(name))


def is_magnitude_evidence_feature(name: str) -> bool:
    if is_pose_or_distance_feature(name):
        return False
    if name.startswith("raw_") and ("asym" in name or "deviation" in name):
        return True
    if not name.startswith("bsdiff_"):
        return False
    if name.endswith("_signed_left_minus_right"):
        return False
    return name.endswith("_abs") or name.endswith("_mean_abs") or name.endswith("_max_abs") or name.endswith("_lateral_abs")


def is_pose_or_distance_feature(name: str) -> bool:
    lowered = name.lower()
    if lowered.startswith(POSE_DISTANCE_FEATURE_PREFIXES):
        return True
    if lowered.endswith(POSE_DISTANCE_FEATURE_SUFFIXES):
        return True
    if lowered.startswith(("bs_", "bsdiff_")):
        return False
    return any(token in lowered for token in POSE_DISTANCE_FEATURE_TOKENS)


def reference_patient_ids(
    rows: list[Mapping[str, str]],
    reference_splits: Sequence[str],
    min_reference_roles: int,
) -> set[str]:
    roles_by_patient: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("label_binary") != "0" or row.get("split") not in reference_splits:
            continue
        role = row.get("media_role", "")
        if row.get("detection_status") == "detected" and role in CORE_ROLES:
            roles_by_patient[row.get("patient_sample_id", "")].add(role)
    return {
        patient_id
        for patient_id, roles in roles_by_patient.items()
        if patient_id and len(roles.intersection(CORE_ROLES)) >= min_reference_roles
    }


def build_reference_stats(
    rows: list[Mapping[str, str]],
    feature_names: Sequence[str],
    reference_patients: set[str],
    reference_splits: Sequence[str],
    min_reference_n: int,
    max_pose_abs_deg: float,
) -> dict[tuple[str, str], dict[str, Any]]:
    values_by_key: dict[tuple[str, str], list[float]] = defaultdict(list)
    patients_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in rows:
        patient_id = row.get("patient_sample_id", "")
        role = row.get("media_role", "")
        if patient_id not in reference_patients or row.get("split") not in reference_splits or role not in CORE_ROLES:
            continue
        if not is_quality_reference_row(row, max_pose_abs_deg):
            continue
        for feature_name in feature_names:
            value = parse_float(row.get(feature_name))
            if value is None:
                continue
            key = (role, feature_name)
            values_by_key[key].append(value)
            patients_by_key[key].add(patient_id)

    output: dict[tuple[str, str], dict[str, Any]] = {}
    for key, values in sorted(values_by_key.items()):
        if len(values) < min_reference_n:
            continue
        role, feature_name = key
        ordered = sorted(values)
        med = median(values)
        mad_value = median(abs(value - med) for value in values)
        robust_sigma = max(1.4826 * mad_value, EPSILON)
        output[key] = {
            "media_role": role,
            "feature_name": feature_name,
            "feature_family": feature_family(feature_name),
            "reference_n": len(values),
            "reference_patient_n": len(patients_by_key[key]),
            "reference_splits": ";".join(reference_splits),
            "median": fmt(med),
            "mad": fmt(mad_value),
            "robust_sigma": fmt(robust_sigma),
            "p75": fmt(percentile(ordered, 0.75)),
            "p90": fmt(percentile(ordered, 0.90)),
            "p95": fmt(percentile(ordered, 0.95)),
            "p975": fmt(percentile(ordered, 0.975)),
            "p99": fmt(percentile(ordered, 0.99)),
            "max": fmt(max(values)),
            "_values": values,
        }
    return output


def is_quality_reference_row(row: Mapping[str, str], max_pose_abs_deg: float) -> bool:
    if row.get("detection_status") != "detected":
        return False
    for field in ("pose_yaw_abs_deg", "pose_pitch_abs_deg", "pose_roll_abs_deg", "matrix_yaw_abs_deg", "matrix_pitch_abs_deg", "matrix_roll_abs_deg"):
        value = parse_float(row.get(field))
        if value is not None and value > max_pose_abs_deg:
            return False
    return True


def build_image_feature_z_rows(
    rows: list[Mapping[str, str]],
    reference_stats: Mapping[tuple[str, str], Mapping[str, Any]],
    top_k: int,
    z_cap: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    z_rows: list[dict[str, Any]] = []
    by_image: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        role = row.get("media_role", "")
        if role not in CORE_ROLES or row.get("detection_status") != "detected":
            continue
        for (stat_role, feature_name), stat in reference_stats.items():
            if stat_role != role:
                continue
            value = parse_float(row.get(feature_name))
            if value is None:
                continue
            median_ref = parse_float(stat.get("median")) or 0.0
            robust_sigma = parse_float(stat.get("robust_sigma")) or EPSILON
            z = (value - median_ref) / robust_sigma
            positive_z = max(0.0, z)
            clipped_positive_z = min(positive_z, z_cap)
            percentile_rank = percentile_rank_for(value, stat.get("_values", []))
            z_row = {
                "sample_id": row.get("sample_id", ""),
                "patient_sample_id": row.get("patient_sample_id", ""),
                "label_group": row.get("label_group", ""),
                "label_binary": row.get("label_binary", ""),
                "split": row.get("split", ""),
                "media_role": role,
                "feature_name": feature_name,
                "feature_family": stat.get("feature_family", feature_family(feature_name)),
                "feature_value": fmt(value),
                "reference_median": stat.get("median", ""),
                "reference_mad": stat.get("mad", ""),
                "reference_robust_sigma": stat.get("robust_sigma", ""),
                "feature_z": fmt(z),
                "positive_outlier_z": fmt(positive_z),
                "clipped_positive_outlier_z": fmt(clipped_positive_z),
                "abnormality_percentile": fmt(percentile_rank),
            }
            z_rows.append(z_row)
            by_image[row.get("sample_id", "")].append(z_row)

    image_scores: list[dict[str, Any]] = []
    for sample_id, feature_z_rows in by_image.items():
        if not feature_z_rows:
            continue
        first = feature_z_rows[0]
        scored = sorted(
            ((parse_float(item["clipped_positive_outlier_z"]) or 0.0, item["feature_name"]) for item in feature_z_rows),
            reverse=True,
        )
        top_values = [value for value, _ in scored[:top_k]]
        image_scores.append(
            {
                "sample_id": sample_id,
                "patient_sample_id": first["patient_sample_id"],
                "label_group": first["label_group"],
                "label_binary": first["label_binary"],
                "split": first["split"],
                "media_role": first["media_role"],
                "role_specific_outlier_score": fmt(mean(top_values)),
                "role_specific_outlier_max": fmt(max(top_values) if top_values else 0.0),
                "top_outlier_features": ";".join(name for _, name in scored[:top_k]),
                "scored_feature_count": len(feature_z_rows),
            }
        )
    return z_rows, image_scores


def build_patient_outlier_scores(
    split_rows: list[Mapping[str, str]],
    image_role_scores: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    split_by_patient = {row["patient_sample_id"]: row for row in split_rows}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in image_role_scores:
        grouped[str(row.get("patient_sample_id", ""))].append(row)

    output: list[dict[str, Any]] = []
    for patient_id in sorted(split_by_patient):
        split_row = split_by_patient[patient_id]
        role_scores: dict[str, float] = {}
        role_features: dict[str, str] = {}
        for role in CORE_ROLES:
            role_rows = [row for row in grouped.get(patient_id, []) if row.get("media_role") == role]
            if not role_rows:
                continue
            best = max(role_rows, key=lambda item: parse_float(item.get("role_specific_outlier_score")) or 0.0)
            role_scores[role] = parse_float(best.get("role_specific_outlier_score")) or 0.0
            role_features[role] = str(best.get("top_outlier_features", ""))
        score_values = list(role_scores.values())
        max_score = max(score_values) if score_values else 0.0
        mean_score = mean(score_values)
        top2_score = mean(sorted(score_values, reverse=True)[:2])
        combined = 0.50 * top2_score + 0.30 * max_score + 0.20 * mean_score
        row = {
            "patient_sample_id": patient_id,
            "label_group": split_row.get("label_group", ""),
            "label_binary": split_row.get("label_binary", ""),
            "split": split_row.get("split", ""),
            "roles_available": len(role_scores),
            "max_role_outlier_score": fmt(max_score),
            "mean_role_outlier_score": fmt(mean_score),
            "top2_role_outlier_score": fmt(top2_score),
            "normal_reference_outlier_score": fmt(combined),
            "top_role": max(role_scores, key=role_scores.get) if role_scores else "",
            "top_outlier_features_by_role": ";".join(f"{role}:{features}" for role, features in role_features.items() if features),
        }
        for role in CORE_ROLES:
            row[f"{role}_outlier_score"] = fmt(role_scores[role]) if role in role_scores else ""
        output.append(row)
    return output


def build_delta_motion_features(
    dataset: Path,
    keypoint_rows: list[Mapping[str, str]],
    split_rows: list[Mapping[str, str]],
) -> list[dict[str, Any]]:
    split_by_patient = {row["patient_sample_id"]: row for row in split_rows}
    selected = select_keypoint_rows_by_patient_role(keypoint_rows)
    output: list[dict[str, Any]] = []
    for patient_id in sorted(split_by_patient):
        front_row = selected.get((patient_id, "front"))
        if not front_row:
            continue
        front_points = read_raw_points(dataset, front_row)
        if not front_points:
            continue
        front_scale = face_scale(front_points)
        if front_scale <= EPSILON:
            continue
        for action_role in ACTION_ROLES:
            action_row = selected.get((patient_id, action_role))
            if not action_row:
                continue
            action_points = read_raw_points(dataset, action_row)
            if not action_points:
                continue
            action_scale = face_scale(action_points)
            scale = mean([front_scale, action_scale])
            if scale <= EPSILON:
                continue
            split_row = split_by_patient[patient_id]
            features = delta_features_for_role(front_points, action_points, action_role, scale)
            if not features:
                continue
            output.append(
                {
                    "patient_sample_id": patient_id,
                    "label_group": split_row.get("label_group", ""),
                    "label_binary": split_row.get("label_binary", ""),
                    "split": split_row.get("split", ""),
                    "action_role": action_role,
                    "front_sample_id": front_row.get("sample_id", ""),
                    "action_sample_id": action_row.get("sample_id", ""),
                    **{name: fmt(value) for name, value in sorted(features.items())},
                }
            )
    return output


def select_keypoint_rows_by_patient_role(rows: list[Mapping[str, str]]) -> dict[tuple[str, str], Mapping[str, str]]:
    selected: dict[tuple[str, str], Mapping[str, str]] = {}
    for row in sorted(rows, key=lambda item: str(item.get("sample_id", ""))):
        if row.get("detection_status") != "detected" or row.get("raw_landmarks") != "478":
            continue
        role = row.get("media_role", "")
        if role not in (*CORE_ROLES,):
            continue
        key = (row.get("patient_sample_id", ""), role)
        selected.setdefault(key, row)
    return selected


def read_raw_points(dataset: Path, row: Mapping[str, str]) -> list[tuple[float, float, float]]:
    keypoints_path = row.get("keypoints_path", "")
    if not keypoints_path:
        return []
    payload = json.loads((dataset / keypoints_path).read_text(encoding="utf-8"))
    raw = ((payload.get("detection") or {}).get("raw_landmarks") or [])
    if len(raw) < 478:
        return []
    return [(float(item["x"]), float(item["y"]), float(item.get("z", 0.0))) for item in raw]


def delta_features_for_role(
    front: list[tuple[float, float, float]],
    action: list[tuple[float, float, float]],
    action_role: str,
    scale: float,
) -> dict[str, float]:
    features: dict[str, float] = {}
    if action_role in {"smile", "teeth", "frown"}:
        left_motion = dist(action[LANDMARK["left_mouth_corner"]], front[LANDMARK["left_mouth_corner"]]) / scale
        right_motion = dist(action[LANDMARK["right_mouth_corner"]], front[LANDMARK["right_mouth_corner"]]) / scale
        left_y_delta = (action[LANDMARK["left_mouth_corner"]][1] - front[LANDMARK["left_mouth_corner"]][1]) / scale
        right_y_delta = (action[LANDMARK["right_mouth_corner"]][1] - front[LANDMARK["right_mouth_corner"]][1]) / scale
        features["delta_mouth_corner_motion_asym"] = ratio_abs_diff(left_motion, right_motion)
        features["delta_mouth_corner_vertical_motion_asym"] = ratio_abs_diff(left_y_delta, right_y_delta)
        features["movement_absence_mouth"] = 1.0 / (1.0 + max(abs(left_motion), abs(right_motion)))
        features["delta_lip_midline_deviation"] = abs(lip_midline_deviation(action, scale) - lip_midline_deviation(front, scale))
        features["delta_lip_opening_asym"] = abs(lip_opening(action) - lip_opening(front)) / scale
    if action_role == "eyes_closed":
        left_front = eye_aperture(front, "left") / scale
        right_front = eye_aperture(front, "right") / scale
        left_action = eye_aperture(action, "left") / scale
        right_action = eye_aperture(action, "right") / scale
        left_closure = left_front - left_action
        right_closure = right_front - right_action
        features["delta_eye_closure_asym"] = ratio_abs_diff(left_closure, right_closure)
        features["movement_absence_eyes_closed"] = 1.0 / (1.0 + max(abs(left_closure), abs(right_closure)))
    if action_role == "forehead_wrinkle":
        left_raise = brow_y(front, "left") - brow_y(action, "left")
        right_raise = brow_y(front, "right") - brow_y(action, "right")
        left_raise /= scale
        right_raise /= scale
        features["delta_brow_raise_asym"] = ratio_abs_diff(left_raise, right_raise)
        features["delta_eyebrow_region_height_asym"] = abs(left_raise - right_raise)
        features["movement_absence_forehead_wrinkle"] = 1.0 / (1.0 + max(abs(left_raise), abs(right_raise)))
    if action_role == "frown":
        left_frown = brow_y(action, "left") - brow_y(front, "left")
        right_frown = brow_y(action, "right") - brow_y(front, "right")
        left_frown /= scale
        right_frown /= scale
        features["delta_frown_brow_asym"] = ratio_abs_diff(left_frown, right_frown)
        features["movement_absence_frown"] = 1.0 / (1.0 + max(abs(left_frown), abs(right_frown)))
    return features


def build_delta_reference_stats(
    delta_rows: list[Mapping[str, Any]],
    reference_splits: Sequence[str],
    min_reference_n: int,
) -> dict[tuple[str, str], dict[str, Any]]:
    feature_names = sorted(
        {
            key
            for row in delta_rows
            for key in row
            if key.startswith(("delta_", "movement_absence_"))
        }
    )
    values_by_key: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in delta_rows:
        if row.get("label_binary") != "0" or row.get("split") not in reference_splits:
            continue
        action_role = str(row.get("action_role", ""))
        for feature_name in feature_names:
            value = parse_float(row.get(feature_name))
            if value is not None:
                values_by_key[(action_role, feature_name)].append(value)

    output: dict[tuple[str, str], dict[str, Any]] = {}
    for key, values in sorted(values_by_key.items()):
        if len(values) < min_reference_n:
            continue
        action_role, feature_name = key
        ordered = sorted(values)
        med = median(values)
        mad_value = median(abs(value - med) for value in values)
        robust_sigma = max(1.4826 * mad_value, EPSILON)
        output[key] = {
            "action_role": action_role,
            "feature_name": feature_name,
            "feature_family": feature_family(feature_name),
            "reference_n": len(values),
            "reference_splits": ";".join(reference_splits),
            "median": fmt(med),
            "mad": fmt(mad_value),
            "robust_sigma": fmt(robust_sigma),
            "p90": fmt(percentile(ordered, 0.90)),
            "p95": fmt(percentile(ordered, 0.95)),
            "p99": fmt(percentile(ordered, 0.99)),
            "max": fmt(max(values)),
            "_values": values,
        }
    return output


def build_delta_patient_scores(
    split_rows: list[Mapping[str, str]],
    delta_rows: list[Mapping[str, Any]],
    delta_reference_stats: Mapping[tuple[str, str], Mapping[str, Any]],
    top_k: int,
    z_cap: float,
) -> list[dict[str, Any]]:
    split_by_patient = {row["patient_sample_id"]: row for row in split_rows}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in delta_rows:
        grouped[str(row.get("patient_sample_id", ""))].append(row)

    output: list[dict[str, Any]] = []
    for patient_id in sorted(split_by_patient):
        split_row = split_by_patient[patient_id]
        action_scores: dict[str, float] = {}
        top_features: dict[str, str] = {}
        for row in grouped.get(patient_id, []):
            action_role = str(row.get("action_role", ""))
            scored: list[tuple[float, str]] = []
            for (stat_role, feature_name), stat in delta_reference_stats.items():
                if stat_role != action_role:
                    continue
                value = parse_float(row.get(feature_name))
                if value is None:
                    continue
                median_ref = parse_float(stat.get("median")) or 0.0
                robust_sigma = parse_float(stat.get("robust_sigma")) or EPSILON
                scored.append((min(max(0.0, (value - median_ref) / robust_sigma), z_cap), feature_name))
            if not scored:
                continue
            scored = sorted(scored, reverse=True)
            action_scores[action_role] = mean(value for value, _ in scored[:top_k])
            top_features[action_role] = ";".join(name for _, name in scored[:top_k])
        values = list(action_scores.values())
        max_score = max(values) if values else 0.0
        mean_score = mean(values)
        top2_score = mean(sorted(values, reverse=True)[:2])
        combined = 0.50 * top2_score + 0.30 * max_score + 0.20 * mean_score
        row_out = {
            "patient_sample_id": patient_id,
            "label_group": split_row.get("label_group", ""),
            "label_binary": split_row.get("label_binary", ""),
            "split": split_row.get("split", ""),
            "delta_roles_available": len(action_scores),
            "max_delta_motion_score": fmt(max_score),
            "mean_delta_motion_score": fmt(mean_score),
            "top2_delta_motion_score": fmt(top2_score),
            "delta_motion_outlier_score": fmt(combined),
            "top_delta_role": max(action_scores, key=action_scores.get) if action_scores else "",
            "top_delta_features_by_role": ";".join(f"{role}:{features}" for role, features in top_features.items() if features),
        }
        for role in ACTION_ROLES:
            row_out[f"{role}_delta_motion_score"] = fmt(action_scores[role]) if role in action_scores else ""
        output.append(row_out)
    return output


def build_threshold_sweep(
    split_rows: list[Mapping[str, str]],
    hb_rows: list[Mapping[str, str]],
    patient_outlier_rows: list[Mapping[str, Any]],
    delta_patient_rows: list[Mapping[str, Any]],
    calibration_splits: Sequence[str],
    specificity_targets: Sequence[float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    patients = build_patient_score_table(split_rows, hb_rows, patient_outlier_rows, delta_patient_rows)
    threshold_rows: list[dict[str, Any]] = []

    grade_specs = (
        ("current_grade_iii_plus", "hb_proxy_grade_num", 3.0),
        ("current_grade_iv_plus", "hb_proxy_grade_num", 4.0),
        ("current_grade_v_plus", "hb_proxy_grade_num", 5.0),
    )
    for method, score_name, threshold in grade_specs:
        for split in EVALUATION_SPLITS:
            scoped = split_scope(patients, split)
            threshold_rows.append(format_threshold_metrics(method, score_name, "", threshold, split, scoped))

    score_methods = (
        ("normal_reference_outlier", "normal_reference_outlier_score"),
        ("normal_reference_max_role", "max_role_outlier_score"),
        ("normal_reference_mean_role", "mean_role_outlier_score"),
        ("normal_reference_top2_role", "top2_role_outlier_score"),
        ("delta_motion_outlier", "delta_motion_outlier_score"),
        ("combined_static_delta", "combined_static_delta_score"),
    )
    calibration_rows = [row for row in patients if row.get("split") in calibration_splits]
    fallback_calibration_rows = [row for row in patients if row.get("split") in {"train", "val"}]
    if not has_negative(calibration_rows):
        calibration_rows = fallback_calibration_rows
    for method, score_name in score_methods:
        for target in specificity_targets:
            threshold = threshold_for_specificity(calibration_rows, score_name, target)
            for split in EVALUATION_SPLITS:
                scoped = split_scope(patients, split)
                threshold_rows.append(format_threshold_metrics(method, score_name, target, threshold, split, scoped))

    summary = summarize_threshold_rows(threshold_rows, patients, calibration_splits)
    return threshold_rows, summary


def build_patient_score_table(
    split_rows: list[Mapping[str, str]],
    hb_rows: list[Mapping[str, str]],
    patient_outlier_rows: list[Mapping[str, Any]],
    delta_patient_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    hb_by_patient = {row["patient_sample_id"]: row for row in hb_rows}
    outlier_by_patient = {row["patient_sample_id"]: row for row in patient_outlier_rows}
    delta_by_patient = {row["patient_sample_id"]: row for row in delta_patient_rows}
    output: list[dict[str, Any]] = []
    for split_row in split_rows:
        patient_id = split_row["patient_sample_id"]
        hb = hb_by_patient.get(patient_id, {})
        outlier = outlier_by_patient.get(patient_id, {})
        delta = delta_by_patient.get(patient_id, {})
        normal = parse_float(outlier.get("normal_reference_outlier_score")) or 0.0
        delta_score = parse_float(delta.get("delta_motion_outlier_score")) or 0.0
        output.append(
            {
                "patient_sample_id": patient_id,
                "label_group": split_row.get("label_group", ""),
                "label_binary": split_row.get("label_binary", ""),
                "split": split_row.get("split", ""),
                "hb_proxy_grade_num": hb.get("hb_proxy_grade_num", ""),
                "normal_reference_outlier_score": fmt(normal),
                "max_role_outlier_score": outlier.get("max_role_outlier_score", ""),
                "mean_role_outlier_score": outlier.get("mean_role_outlier_score", ""),
                "top2_role_outlier_score": outlier.get("top2_role_outlier_score", ""),
                "delta_motion_outlier_score": fmt(delta_score),
                "combined_static_delta_score": fmt(0.50 * normal + 0.50 * delta_score),
            }
        )
    return output


def threshold_for_specificity(rows: list[Mapping[str, Any]], score_name: str, specificity_target: float) -> float:
    negatives = sorted(
        value
        for row in rows
        if row.get("label_binary") == "0"
        if (value := parse_float(row.get(score_name))) is not None
    )
    if not negatives:
        return math.inf
    index = math.ceil(len(negatives) * specificity_target) - 1
    index = max(0, min(index, len(negatives) - 1))
    return math.nextafter(negatives[index], math.inf)


def format_threshold_metrics(
    method: str,
    score_name: str,
    specificity_target: float | str,
    threshold: float,
    evaluation_split: str,
    rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    metrics = binary_metrics(rows, score_name, threshold)
    return {
        "method": method,
        "score_name": score_name,
        "specificity_target": fmt(specificity_target) if isinstance(specificity_target, float) else specificity_target,
        "threshold": fmt(threshold) if math.isfinite(threshold) else "inf",
        "evaluation_split": evaluation_split,
        **metrics,
    }


def binary_metrics(rows: list[Mapping[str, Any]], score_name: str, threshold: float) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        score = parse_float(row.get(score_name))
        if truth not in {"0", "1"} or score is None or not math.isfinite(threshold):
            skipped += 1
            continue
        pred = score >= threshold
        if truth == "1" and pred:
            tp += 1
        elif truth == "1" and not pred:
            fn += 1
        elif truth == "0" and pred:
            fp += 1
        elif truth == "0" and not pred:
            tn += 1
    evaluated = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    accuracy = (tp + tn) / evaluated if evaluated else 0.0
    balanced_accuracy = (recall + specificity) / 2.0 if evaluated else 0.0
    return {
        "patients": evaluated,
        "skipped": skipped,
        "accuracy": fmt(accuracy),
        "balanced_accuracy": fmt(balanced_accuracy),
        "precision": fmt(precision),
        "recall": fmt(recall),
        "specificity": fmt(specificity),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def summarize_threshold_rows(
    threshold_rows: list[Mapping[str, Any]],
    patients: list[Mapping[str, Any]],
    calibration_splits: Sequence[str],
) -> dict[str, Any]:
    test_rows = [row for row in threshold_rows if row.get("evaluation_split") == "test"]
    preferred = [row for row in test_rows if row.get("specificity_target") == "0.900000"]
    candidates = preferred or test_rows
    best = max(
        candidates,
        key=lambda row: (
            parse_float(row.get("balanced_accuracy")) or 0.0,
            parse_float(row.get("recall")) or 0.0,
            parse_float(row.get("specificity")) or 0.0,
        ),
        default={},
    )
    return {
        "patient_count": len(patients),
        "patients_by_split": dict(sorted(Counter(str(row.get("split", "")) for row in patients).items())),
        "calibration_splits": list(calibration_splits),
        "best_test_row_at_specificity_0_90_or_overall": dict(best),
        "interpretation_limit": (
            "本阶段不使用人工轻微不对称标签；specificity 由不患病代理正常样本固定，"
            "recall 是 patient outcome 弱标签召回，不是人工面部不对称真值召回。"
        ),
    }


def write_report(path: Path, summary: Mapping[str, Any], threshold_rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 32 无人工轻微不对称标注特征验证汇总",
        "",
        f"分析对象：`datasets/{summary['dataset']}`",
        "",
        "## 产物",
        "",
    ]
    for label, output in summary.get("outputs", {}).items():
        lines.append(f"- `{label}`：`{output}`")
    lines.extend(
        [
            "",
            "## 样本与特征覆盖",
            "",
            f"- 患者数：`{summary.get('patient_count')}`",
            f"- split 分布：`{json.dumps(summary.get('patients_by_split', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- 正常参考患者数：`{summary.get('normal_reference_patient_count')}`",
            f"- 正常参考统计行数：`{summary.get('normal_reference_stats_rows')}`",
            f"- 单图 z-score 行数：`{summary.get('image_feature_z_rows')}`",
            f"- 动作差异行数：`{summary.get('delta_motion_rows')}`",
            f"- 动作差异参考统计行数：`{summary.get('delta_reference_stats_rows')}`",
            "",
            "## Test Split 阈值对比",
            "",
        ]
    )
    test_rows = [row for row in threshold_rows if row.get("evaluation_split") == "test"]
    lines.extend(
        markdown_table(
            ["method", "target", "threshold", "patients", "precision", "recall", "specificity", "balanced_accuracy", "TP", "FP", "TN", "FN"],
            [
                [
                    row.get("method", ""),
                    row.get("specificity_target", ""),
                    row.get("threshold", ""),
                    row.get("patients", ""),
                    row.get("precision", ""),
                    row.get("recall", ""),
                    row.get("specificity", ""),
                    row.get("balanced_accuracy", ""),
                    row.get("tp", ""),
                    row.get("fp", ""),
                    row.get("tn", ""),
                    row.get("fn", ""),
                ]
                for row in test_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 当前推荐读取方式",
            "",
            "- `30_no_manual_normal_reference_stats.csv` 用于复核不患病高质量样本的 role-feature 正常范围。",
            "- `30_no_manual_patient_outlier_scores.csv` 给出静态 MediaPipe 特征相对正常分布的患者级异常分。",
            "- `31_no_manual_delta_motion_features.csv` 给出 `front -> action role` 的客观动作差异。",
            "- `32_no_manual_threshold_sweep.csv` 在固定 specificity 下比较当前 Grade III+/IV+/V+、正常分布 outlier、动作差异和组合分数。",
            "",
            "## 解释限制",
            "",
            str(summary.get("interpretation_limit", "")),
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def split_scope(rows: list[Mapping[str, Any]], split: str) -> list[Mapping[str, Any]]:
    if split == "all":
        return rows
    return [row for row in rows if row.get("split") == split]


def has_negative(rows: list[Mapping[str, Any]]) -> bool:
    return any(row.get("label_binary") == "0" for row in rows)


def feature_family(name: str) -> str:
    lowered = name.lower()
    if "mouth" in lowered or "lip" in lowered:
        return "mouth"
    if "brow" in lowered or "forehead" in lowered:
        return "brow"
    if "eye" in lowered or "iris" in lowered:
        return "eye"
    if "all_mesh" in lowered:
        return "all_mesh"
    if "face_oval" in lowered or "jaw" in lowered or "cheek" in lowered:
        return "contour"
    if "nose" in lowered or "nostril" in lowered:
        return "nose"
    if lowered.startswith("bsdiff_") or lowered.startswith("bs_"):
        return "blendshape_other"
    return "other"


def face_scale(points: list[tuple[float, float, float]]) -> float:
    return dist(points[LANDMARK["left_eye_outer"]], points[LANDMARK["right_eye_outer"]])


def lip_midline_deviation(points: list[tuple[float, float, float]], scale: float) -> float:
    midline = fitted_midline([points[LANDMARK["nose_bridge"]], points[LANDMARK["nose_tip"]], points[LANDMARK["chin"]]])
    upper = signed_distance_2d(points[LANDMARK["upper_lip_center"]], midline) / scale
    lower = signed_distance_2d(points[LANDMARK["lower_lip_center"]], midline) / scale
    return abs((upper + lower) / 2.0)


def lip_opening(points: list[tuple[float, float, float]]) -> float:
    return dist(points[LANDMARK["upper_lip_center"]], points[LANDMARK["lower_lip_center"]])


def eye_aperture(points: list[tuple[float, float, float]], side: str) -> float:
    if side == "left":
        return dist(points[LANDMARK["left_eye_upper"]], points[LANDMARK["left_eye_lower"]])
    return dist(points[LANDMARK["right_eye_upper"]], points[LANDMARK["right_eye_lower"]])


def brow_y(points: list[tuple[float, float, float]], side: str) -> float:
    if side == "left":
        return (points[LANDMARK["left_brow_inner"]][1] + points[LANDMARK["left_brow_outer"]][1]) / 2.0
    return (points[LANDMARK["right_brow_inner"]][1] + points[LANDMARK["right_brow_outer"]][1]) / 2.0


def fitted_midline(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    dx = math.cos(theta)
    dy = math.sin(theta)
    a = -dy
    b = dx
    c = -(a * mx + b * my)
    norm = math.sqrt(a * a + b * b)
    return a / norm, b / norm, c / norm


def signed_distance_2d(point: tuple[float, float, float], line: tuple[float, float, float]) -> float:
    a, b, c = line
    return a * point[0] + b * point[1] + c


def dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def ratio_abs_diff(a: float, b: float) -> float:
    denom = abs(a) + abs(b)
    if denom <= EPSILON:
        return 0.0
    return abs(a - b) / denom


def percentile_rank_for(value: float, reference_values: Any) -> float:
    values = sorted(float(item) for item in reference_values)
    if not values:
        return 0.0
    less_or_equal = sum(1 for item in values if item <= value)
    return less_or_equal / len(values)


def parse_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def median(values: Iterable[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return 0.0
    return percentile(ordered, 0.5)


def mean(values: Iterable[float]) -> float:
    values_list = list(values)
    if not values_list:
        return 0.0
    return sum(values_list) / len(values_list)


def percentile(ordered_values: Sequence[float], q: float) -> float:
    ordered = list(ordered_values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def fmt(value: Any) -> str:
    parsed = parse_float(value)
    if parsed is None:
        return ""
    return f"{parsed:.6f}"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return output


if __name__ == "__main__":
    main()
