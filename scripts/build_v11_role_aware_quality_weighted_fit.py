#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

ROLE_CONFIG: dict[str, dict[str, Any]] = {
    "front": {
        "weight": 1.00,
        "group": "static",
        "purpose": "中线、轮廓、眼眉静态、口角静息高度",
    },
    "smile": {
        "weight": 1.15,
        "group": "mouth_dynamic",
        "purpose": "口角高度变化、口宽变化、唇中线偏移",
    },
    "teeth": {
        "weight": 1.15,
        "group": "mouth_dynamic",
        "purpose": "露齿时口角、口宽、唇中线、上下唇轮廓",
    },
    "eyes_closed": {
        "weight": 0.90,
        "group": "eye_dynamic",
        "purpose": "闭眼完整性、眼裂/上下眼睑对称",
    },
    "forehead_wrinkle": {
        "weight": 0.85,
        "group": "brow_dynamic",
        "purpose": "抬眉/皱额对称性、额纹区域运动",
    },
    "frown": {
        "weight": 0.85,
        "group": "brow_dynamic",
        "purpose": "眉间/眉部运动对称性",
    },
}
INCLUDED_ROLES = tuple(ROLE_CONFIG)
EXCLUDED_ROLES = (
    "left_profile",
    "right_profile",
    "tongue_surface",
    "tongue_bottom",
    "medical_record",
    "auxiliary_exam_image",
)
EXCLUDED_EXPRESSION_FEATURES = {"bs_neutral"}
DEFAULT_EXPRESSION_WEIGHT_MULTIPLIER = 0.35
DEFAULT_EXPRESSION_MAX_ROLE_WEIGHT_SHARE = 0.25
METADATA_FIELDS = {
    "sample_id",
    "patient_sample_id",
    "label_group",
    "label_binary",
    "media_role",
    "detection_status",
    "split",
    "quality_level",
    "quality_score",
    "quality_accepted",
    "quality_hard_reject",
    "quality_reason_codes",
    "input_quality",
}
POSE_DISTANCE_FEATURE_PREFIXES = ("matrix_", "pose_")
POSE_DISTANCE_FEATURE_SUFFIXES = ("_centroid_z_asym",)
POSE_DISTANCE_FEATURE_TOKENS = (
    "yaw",
    "pitch",
    "roll",
    "scale",
    "distance",
    "bbox",
    "face_size",
    "image_size",
    "translation",
)


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    feature_rows = read_csv(metadata / "09_mediapipe_full_features.csv")
    split_rows = read_csv(metadata / "05_patient_splits.csv")
    image_feature_rows = read_optional_csv(metadata / "04_image_features.csv")
    quality_rows = read_optional_csv(metadata / "02_quality_gate.csv") + read_optional_csv(metadata / "02_quality_gate_skipped.csv")

    split_by_patient = {row["patient_sample_id"]: row["split"] for row in split_rows}
    image_meta = build_image_meta(image_feature_rows, quality_rows)
    for row in feature_rows:
        row["split"] = split_by_patient.get(row["patient_sample_id"], "")
        row.update(image_meta.get(row["sample_id"], {}))

    screened_features = summarize_screened_features(feature_rows)
    feature_set = build_feature_set(
        feature_rows,
        args.min_auc,
        args.min_weight,
        args.expression_weight_multiplier,
        args.expression_max_role_weight_share,
    )
    image_scores = score_images(feature_rows, feature_set)
    patient_scores = score_patients(image_scores)
    predictions, threshold = choose_predictions(patient_scores)
    evaluation = build_evaluation(feature_set, image_scores, patient_scores, predictions, threshold, args, screened_features)

    write_csv(metadata / "11_v11_role_aware_feature_set.csv", feature_set)
    write_csv(metadata / "11_v11_role_aware_image_scores.csv", image_scores)
    write_csv(metadata / "11_v11_role_aware_patient_core_results.csv", patient_scores)
    write_csv(metadata / "11_v11_role_aware_predictions.csv", predictions)
    write_json(metadata / "11_v11_role_aware_evaluation.json", evaluation)
    write_report(reports / "11_v11_role_aware_quality_weighted_fit.md", evaluation, feature_set)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build V1.1 role-aware quality-weighted facial asymmetry fit.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing all V1.1 roles.")
    parser.add_argument("--min-auc", type=float, default=0.53, help="Minimum train AUC where diseased values are higher.")
    parser.add_argument("--min-weight", type=float, default=0.001, help="Minimum feature weight after weak association weighting.")
    parser.add_argument(
        "--expression-weight-multiplier",
        type=float,
        default=DEFAULT_EXPRESSION_WEIGHT_MULTIPLIER,
        help="Down-weight multiplier for raw MediaPipe blendshape expression coefficients.",
    )
    parser.add_argument(
        "--expression-max-role-weight-share",
        type=float,
        default=DEFAULT_EXPRESSION_MAX_ROLE_WEIGHT_SHARE,
        help="Maximum share of per-role feature weight that raw expression coefficients may occupy.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_optional_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return read_csv(path)


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    fixed = [
        "patient_sample_id",
        "sample_id",
        "label_group",
        "label_binary",
        "split",
        "media_role",
        "role",
        "feature_type",
        "feature_name",
    ]
    fields = [field for field in fixed if field in fields] + [field for field in fields if field not in fixed]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_image_meta(image_feature_rows: list[dict[str, str]], quality_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    for row in image_feature_rows:
        meta.setdefault(row["sample_id"], {}).update(
            {
                "quality_level": row.get("quality_level", ""),
                "quality_score": row.get("quality_score", ""),
                "quality_accepted": row.get("quality_accepted", ""),
                "input_quality": row.get("input_quality", ""),
            }
        )
    for row in quality_rows:
        meta.setdefault(row["sample_id"], {}).update(
            {
                "quality_level": row.get("quality_level", meta.get(row["sample_id"], {}).get("quality_level", "")),
                "quality_score": row.get("quality_score", meta.get(row["sample_id"], {}).get("quality_score", "")),
                "quality_accepted": row.get("accepted_for_scoring", meta.get(row["sample_id"], {}).get("quality_accepted", "")),
                "quality_hard_reject": row.get("hard_reject", ""),
                "quality_reason_codes": row.get("reason_codes", ""),
            }
        )
    return meta


def is_asymmetry_candidate_feature(name: str) -> bool:
    if name.startswith("bsdiff_"):
        return True
    return name.startswith("raw_") and ("asym" in name or "deviation" in name)


def is_expression_feature(name: str) -> bool:
    return name.startswith("bs_") and name not in EXCLUDED_EXPRESSION_FEATURES


def is_pose_or_distance_feature(name: str) -> bool:
    lowered = name.lower()
    if lowered.startswith(POSE_DISTANCE_FEATURE_PREFIXES):
        return True
    if lowered.endswith(POSE_DISTANCE_FEATURE_SUFFIXES):
        return True
    if lowered.startswith(("bs_", "bsdiff_")):
        return False
    return any(token in lowered for token in POSE_DISTANCE_FEATURE_TOKENS)


def is_asymmetry_feature(name: str) -> bool:
    return is_asymmetry_candidate_feature(name) and not is_pose_or_distance_feature(name)


def feature_type_for(name: str) -> str:
    if is_asymmetry_feature(name):
        return "asymmetry"
    if is_expression_feature(name):
        return "expression_blendshape"
    return ""


def summarize_screened_features(rows: list[dict[str, str]]) -> dict[str, Any]:
    feature_names = sorted(key for key in rows[0] if key not in METADATA_FIELDS)
    asymmetry_candidates_before_screen = [name for name in feature_names if is_asymmetry_candidate_feature(name)]
    expression_candidates = [name for name in feature_names if is_expression_feature(name)]
    blocked_features = [name for name in feature_names if is_pose_or_distance_feature(name)]
    blocked_scoring_candidates = [
        name for name in asymmetry_candidates_before_screen
        if is_pose_or_distance_feature(name)
    ]
    eligible_scoring_candidates = [
        name for name in asymmetry_candidates_before_screen
        if not is_pose_or_distance_feature(name)
    ] + expression_candidates
    return {
        "pose_distance_screen": {
            "policy": "hard_exclude_from_v11_scoring",
            "blocked_prefixes": list(POSE_DISTANCE_FEATURE_PREFIXES),
            "blocked_suffixes": list(POSE_DISTANCE_FEATURE_SUFFIXES),
            "blocked_tokens": list(POSE_DISTANCE_FEATURE_TOKENS),
            "available_feature_count": len(feature_names),
            "blocked_available_feature_count": len(blocked_features),
            "blocked_available_feature_examples": blocked_features[:40],
            "asymmetry_candidates_before_screen": len(asymmetry_candidates_before_screen),
            "expression_candidates": len(expression_candidates),
            "eligible_scoring_candidates_after_screen": len(eligible_scoring_candidates),
            "blocked_scoring_candidate_count": len(blocked_scoring_candidates),
            "blocked_scoring_candidate_names": blocked_scoring_candidates,
        }
    }


def build_feature_set(
    rows: list[dict[str, str]],
    min_auc: float,
    min_weight: float,
    expression_weight_multiplier: float,
    expression_max_role_weight_share: float,
) -> list[dict[str, Any]]:
    candidate_features = sorted((key, feature_type_for(key)) for key in rows[0] if feature_type_for(key))
    train_rows = [row for row in rows if row.get("split") == "train" and row.get("media_role") in INCLUDED_ROLES]
    output: list[dict[str, Any]] = []
    for role in INCLUDED_ROLES:
        role_rows = [row for row in train_rows if row["media_role"] == role]
        for feature_name, feature_type in candidate_features:
            pos = values_for(role_rows, feature_name, "1")
            neg = values_for(role_rows, feature_name, "0")
            if len(pos) < 20 or len(neg) < 20:
                continue
            pos_mean = mean(pos)
            neg_mean = mean(neg)
            if pos_mean <= neg_mean:
                continue
            auc_value = auc_positive_higher(pos, neg)
            if auc_value < min_auc:
                continue
            effect = cohens_d(pos, neg)
            all_values = pos + neg
            train_mean = mean(all_values)
            train_std = std(all_values)
            if train_std <= 1e-12:
                continue
            weight = (auc_value - 0.5) * max(0.05, min(abs(effect), 0.75))
            feature_weight_multiplier = 1.0
            if feature_type == "expression_blendshape":
                feature_weight_multiplier = expression_weight_multiplier
                weight *= expression_weight_multiplier
            if weight < min_weight:
                continue
            output.append(
                {
                    "role": role,
                    "role_group": ROLE_CONFIG[role]["group"],
                    "feature_type": feature_type,
                    "feature_name": feature_name,
                    "positive_n": len(pos),
                    "negative_n": len(neg),
                    "positive_mean": fmt(pos_mean),
                    "negative_mean": fmt(neg_mean),
                    "mean_diff_positive_minus_negative": fmt(pos_mean - neg_mean),
                    "train_mean": fmt(train_mean),
                    "train_std": fmt(train_std),
                    "cohens_d": fmt(effect),
                    "auc_positive_higher": fmt(auc_value),
                    "feature_weight_before_expression_cap": fmt(weight),
                    "feature_weight": fmt(weight),
                    "feature_weight_multiplier": fmt(feature_weight_multiplier),
                    "expression_cap_scale": fmt(1.0),
                    "selection_rule": f"positive_mean>negative_mean && train_auc>={min_auc:.2f} && pre_cap_weight>={min_weight:.3f}",
                }
            )
    apply_expression_weight_cap(output, expression_max_role_weight_share)
    return sorted(output, key=lambda row: (row["role"], row["feature_type"], -float(row["feature_weight"]), row["feature_name"]))


def apply_expression_weight_cap(rows: list[dict[str, Any]], max_share: float) -> None:
    max_share = max(0.0, min(0.95, max_share))
    for role in INCLUDED_ROLES:
        role_rows = [row for row in rows if row["role"] == role]
        asymmetry_total = sum(float(row["feature_weight"]) for row in role_rows if row["feature_type"] == "asymmetry")
        expression_rows = [row for row in role_rows if row["feature_type"] == "expression_blendshape"]
        expression_total = sum(float(row["feature_weight"]) for row in expression_rows)
        if not expression_rows or expression_total <= 0:
            continue
        if asymmetry_total <= 0 or max_share <= 0:
            scale = 0.0
        else:
            max_expression_total = (max_share / (1.0 - max_share)) * asymmetry_total
            scale = min(1.0, max_expression_total / expression_total)
        for row in expression_rows:
            row["expression_cap_scale"] = fmt(scale)
            row["feature_weight"] = fmt(float(row["feature_weight"]) * scale)


def values_for(rows: list[dict[str, str]], feature_name: str, label_binary: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        if row.get("label_binary") != label_binary:
            continue
        value = parse_float(row.get(feature_name))
        if value is not None:
            values.append(value)
    return values


def score_images(rows: list[dict[str, str]], feature_set: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for feature in feature_set:
        feature_by_role[feature["role"]].append(feature)

    output: list[dict[str, Any]] = []
    for row in rows:
        role = row.get("media_role", "")
        if role in EXCLUDED_ROLES:
            continue
        if role not in INCLUDED_ROLES:
            continue
        selected = feature_by_role.get(role, [])
        quality_weight = quality_weight_for(row)
        weighted_sum = 0.0
        weight_total = 0.0
        contributions: list[tuple[float, str]] = []
        for feature in selected:
            value = parse_float(row.get(feature["feature_name"]))
            if value is None:
                continue
            z = (value - float(feature["train_mean"])) / float(feature["train_std"])
            z = max(-3.0, min(3.0, z))
            feature_weight = float(feature["feature_weight"])
            contribution = z * feature_weight
            weighted_sum += contribution
            weight_total += feature_weight
            contributions.append((contribution, feature["feature_name"]))
        role_z = weighted_sum / weight_total if weight_total > 0 else 0.0
        image_weight = quality_weight * ROLE_CONFIG[role]["weight"] * weight_total
        output.append(
            {
                "sample_id": row["sample_id"],
                "patient_sample_id": row["patient_sample_id"],
                "label_group": row["label_group"],
                "label_binary": row["label_binary"],
                "split": row.get("split", ""),
                "media_role": role,
                "role_group": ROLE_CONFIG[role]["group"],
                "role_weight": fmt(float(ROLE_CONFIG[role]["weight"])),
                "quality_level": row.get("quality_level", ""),
                "quality_score": row.get("quality_score", ""),
                "quality_accepted": row.get("quality_accepted", ""),
                "input_quality": row.get("input_quality", ""),
                "quality_weight": fmt(quality_weight),
                "feature_terms": len(contributions),
                "feature_weight_total": fmt(weight_total),
                "image_weight": fmt(image_weight),
                "role_asymmetry_z": fmt(role_z),
                "role_asymmetry_score": fmt(sigmoid(role_z)),
                "top_positive_features": ";".join(name for _value, name in sorted(contributions, reverse=True)[:5]),
            }
        )
    return output


def quality_weight_for(row: Mapping[str, str]) -> float:
    hard_reject = str(row.get("quality_hard_reject", "")).lower()
    if hard_reject == "true":
        return 0.0
    quality_score = parse_float(row.get("quality_score"))
    if quality_score is not None and quality_score > 0:
        base = quality_score
    else:
        input_quality = parse_float(row.get("input_quality"))
        base = input_quality if input_quality is not None and input_quality > 0 else 1.0
    level = str(row.get("quality_level", ""))
    if level == "reject":
        base *= 0.35
    elif level == "review":
        base *= 0.70
    elif level in {"not_run", "", "not_applicable"}:
        base *= 1.0
    return max(0.0, min(1.0, base))


def score_patients(image_scores: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in image_scores:
        grouped[row["patient_sample_id"]].append(row)
    output: list[dict[str, Any]] = []
    for patient_id, rows in sorted(grouped.items()):
        weighted_sum = 0.0
        weight_total = 0.0
        role_presence: dict[str, str] = {}
        role_scores: dict[str, str] = {}
        role_weights: dict[str, float] = {}
        top_features: list[str] = []
        for role in INCLUDED_ROLES:
            role_rows = [row for row in rows if row["media_role"] == role and float(row["image_weight"]) > 0]
            role_presence[role] = "1" if role_rows else "0"
            if not role_rows:
                role_scores[role] = ""
                role_weights[role] = 0.0
                continue
            role_weight_sum = sum(float(row["image_weight"]) for row in role_rows)
            role_z = sum(float(row["role_asymmetry_z"]) * float(row["image_weight"]) for row in role_rows) / role_weight_sum
            role_scores[role] = fmt(sigmoid(role_z))
            role_weights[role] = role_weight_sum
            weighted_sum += role_z * role_weight_sum
            weight_total += role_weight_sum
            for row in sorted(role_rows, key=lambda item: float(item["role_asymmetry_score"]), reverse=True)[:1]:
                top_features.extend([item for item in row.get("top_positive_features", "").split(";") if item][:3])
        patient_z = weighted_sum / weight_total if weight_total > 0 else 0.0
        first = rows[0]
        result: dict[str, Any] = {
            "patient_sample_id": patient_id,
            "label_group": first["label_group"],
            "label_binary": first["label_binary"],
            "split": first["split"],
            "included_roles_available": sum(1 for value in role_presence.values() if value == "1"),
            "patient_weight_total": fmt(weight_total),
            "v11_asymmetry_z": fmt(patient_z),
            "v11_asymmetry_score": fmt(sigmoid(patient_z)),
            "core_result": core_result(sigmoid(patient_z)),
            "top_positive_features": ";".join(top_features[:12]),
        }
        for role in INCLUDED_ROLES:
            result[f"{role}_available"] = role_presence[role]
            result[f"{role}_score"] = role_scores[role]
            result[f"{role}_weight"] = fmt(role_weights[role])
        output.append(result)
    return output


def core_result(score: float) -> str:
    if score >= 0.65:
        return "high_asymmetry_fit"
    if score >= 0.55:
        return "elevated_asymmetry_fit"
    if score >= 0.45:
        return "watch_asymmetry_fit"
    return "low_asymmetry_fit"


def choose_predictions(patient_scores: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    val_rows = [row for row in patient_scores if row["split"] == "val"]
    thresholds = sorted({float(row["v11_asymmetry_score"]) for row in val_rows})
    threshold = 0.5 if not thresholds else max(
        thresholds,
        key=lambda item: (
            binary_metrics(val_rows, item)["balanced_accuracy"],
            binary_metrics(val_rows, item)["precision"],
            binary_metrics(val_rows, item)["recall"],
        ),
    )
    predictions: list[dict[str, Any]] = []
    for row in patient_scores:
        pred = "1" if float(row["v11_asymmetry_score"]) >= threshold else "0"
        predictions.append(
            {
                **row,
                "threshold": fmt(threshold),
                "predicted_positive": pred,
                "confusion_cell": confusion_cell(row["label_binary"], pred),
            }
        )
    return predictions, threshold


def build_evaluation(
    feature_set: list[dict[str, Any]],
    image_scores: list[dict[str, Any]],
    patient_scores: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    threshold: float,
    args: argparse.Namespace,
    screened_features: Mapping[str, Any],
) -> dict[str, Any]:
    metrics = {split: binary_metrics([row for row in predictions if row["split"] == split], None) for split in ["train", "val", "test"]}
    aucs = {split: patient_auc([row for row in patient_scores if row["split"] == split]) for split in ["train", "val", "test"]}
    return {
        "version": "v1.1_role_aware_quality_weighted_asymmetry_fit",
        "dataset": args.dataset.as_posix(),
        "score_definition": "Positive-only disease-higher asymmetry features from MediaPipe 478 landmarks and 52 blendshapes, role-aware and quality-weighted.",
        "included_roles": ROLE_CONFIG,
        "excluded_roles": list(EXCLUDED_ROLES),
        **screened_features,
        "feature_selection": {
            "candidate_rule": "bsdiff_* OR raw_* containing asym/deviation, plus disease-higher raw bs_* expression coefficients as capped weak-supervision features; pose/distance/depth-proxy features are excluded",
            "direction_rule": "positive_mean > negative_mean on train split",
            "split_for_selection": "train",
            "min_auc_positive_higher": args.min_auc,
            "min_feature_weight": args.min_weight,
            "expression_weight_multiplier": args.expression_weight_multiplier,
            "expression_max_role_weight_share": args.expression_max_role_weight_share,
            "selected_features": len(feature_set),
            "selected_by_role": count_by(feature_set, "role"),
            "selected_by_type": count_by(feature_set, "feature_type"),
            "selected_by_role_and_type": count_by_join(feature_set, ("role", "feature_type")),
        },
        "quality_weighting": "quality_score if available, else input_quality, else 1.0; reject/review levels are down-weighted. In all-images/no-gate data most quality levels are not_run.",
        "threshold_source": "validation split, maximize balanced accuracy then precision then recall",
        "threshold": threshold,
        "metrics": metrics,
        "auc": aucs,
        "operating_points": build_operating_points(patient_scores),
        "image_scores": len(image_scores),
        "patient_scores": len(patient_scores),
        "warning": "This fits patient outcome with weak facial-asymmetry associations. It is not direct facial palsy ground truth and not a clinical diagnosis metric.",
    }


def build_operating_points(patient_scores: list[dict[str, Any]]) -> dict[str, Any]:
    val_rows = [row for row in patient_scores if row["split"] == "val"]
    thresholds = sorted({float(row["v11_asymmetry_score"]) for row in val_rows})
    strategies = {
        "balanced_accuracy": lambda m: (m["balanced_accuracy"], m["precision"], m["recall"]),
        "recall_ge_0.90": lambda m: (m["specificity"], m["precision"], m["balanced_accuracy"]) if m["recall"] >= 0.90 else None,
        "specificity_ge_0.50": lambda m: (m["recall"], m["precision"], m["balanced_accuracy"]) if m["specificity"] >= 0.50 else None,
    }
    output: dict[str, Any] = {}
    for name, scorer in strategies.items():
        candidates: list[tuple[tuple[float, ...], float]] = []
        for threshold in thresholds:
            score = scorer(binary_metrics(val_rows, threshold))
            if score is not None:
                candidates.append((score, threshold))
        if not candidates:
            output[name] = {"available": False}
            continue
        threshold = max(candidates, key=lambda item: item[0])[1]
        output[name] = {
            "available": True,
            "threshold": threshold,
            "val": binary_metrics([row for row in patient_scores if row["split"] == "val"], threshold),
            "test": binary_metrics([row for row in patient_scores if row["split"] == "test"], threshold),
        }
    return output


def binary_metrics(rows: list[Mapping[str, Any]], threshold: float | None) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        if threshold is None:
            pred = str(row.get("predicted_positive", ""))
        else:
            pred = "1" if float(row["v11_asymmetry_score"]) >= threshold else "0"
        if truth not in {"0", "1"} or pred not in {"0", "1"}:
            skipped += 1
            continue
        if truth == "1" and pred == "1":
            tp += 1
        elif truth == "0" and pred == "1":
            fp += 1
        elif truth == "0" and pred == "0":
            tn += 1
        elif truth == "1" and pred == "0":
            fn += 1
    evaluated = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    accuracy = (tp + tn) / evaluated if evaluated else 0.0
    balanced = (recall + specificity) / 2.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "patients": len(rows),
        "evaluated": evaluated,
        "skipped": skipped,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def patient_auc(rows: list[Mapping[str, Any]]) -> float:
    pos = [float(row["v11_asymmetry_score"]) for row in rows if row.get("label_binary") == "1"]
    neg = [float(row["v11_asymmetry_score"]) for row in rows if row.get("label_binary") == "0"]
    if not pos or not neg:
        return 0.0
    return auc_positive_higher(pos, neg)


def confusion_cell(truth: str, pred: str) -> str:
    if truth == "1" and pred == "1":
        return "tp"
    if truth == "0" and pred == "1":
        return "fp"
    if truth == "0" and pred == "0":
        return "tn"
    if truth == "1" and pred == "0":
        return "fn"
    return "skipped"


def parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def std(values: list[float]) -> float:
    m = mean(values)
    return math.sqrt(sum((value - m) ** 2 for value in values) / len(values))


def cohens_d(pos: list[float], neg: list[float]) -> float:
    pooled = math.sqrt((std(pos) ** 2 + std(neg) ** 2) / 2.0)
    return (mean(pos) - mean(neg)) / pooled if pooled > 1e-12 else 0.0


def auc_positive_higher(pos: list[float], neg: list[float]) -> float:
    combined = sorted([(value, 1) for value in pos] + [(value, 0) for value in neg], key=lambda item: item[0])
    rank_sum_pos = 0.0
    index = 0
    while index < len(combined):
        end = index + 1
        while end < len(combined) and combined[end][0] == combined[index][0]:
            end += 1
        avg_rank = (index + 1 + end) / 2.0
        for item_index in range(index, end):
            if combined[item_index][1] == 1:
                rank_sum_pos += avg_rank
        index = end
    n_pos = len(pos)
    n_neg = len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def count_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row[key])] += 1
    return dict(sorted(counts.items()))


def count_by_join(rows: Iterable[Mapping[str, Any]], keys: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts["/".join(str(row[key]) for key in keys)] += 1
    return dict(sorted(counts.items()))


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def write_report(path: Path, evaluation: Mapping[str, Any], feature_set: list[dict[str, Any]]) -> None:
    top_features = sorted(feature_set, key=lambda row: float(row["feature_weight"]), reverse=True)
    top_expression_features = sorted(
        [row for row in feature_set if row.get("feature_type") == "expression_blendshape"],
        key=lambda row: float(row["feature_weight"]),
        reverse=True,
    )
    lines = [
        "# 11 V1.1 Role-Aware 质量加权面部对称性拟合区分",
        "",
        "分析对象：`datasets/facesym_v1_all_images_no_gate_20260119`",
        "",
        "## 目标",
        "",
        "本版本将 09 中 train split 内 `患病均值 > 不患病均值` 且具备弱区分力的对称性候选特征，作为“更容易不对称”的特征点集合。然后按 role-aware 规则纳入 front/smile/teeth/eyes_closed/forehead_wrinkle/frown，排除 profile/tongue/medical/auxiliary，做质量加权患者级聚合，得到 V1.1 患病与不患病患者的面部对称性拟合区分分数。",
        "",
        "## Role-Aware 规则",
        "",
        "| role | 是否进主评分 | 权重 | 作用 |",
        "| --- | --- | ---: | --- |",
    ]
    for role, config in ROLE_CONFIG.items():
        lines.append(f"| {role} | 是 | {config['weight']:.2f} | {config['purpose']} |")
    for role in EXCLUDED_ROLES:
        lines.append(f"| {role} | 否 | 0.00 | 只用于姿态/质量分析或必须排除 |")
    lines.extend(
        [
            "",
            "## 评分口径",
            "",
            "- 候选特征：`bsdiff_*`，以及包含 `asym/deviation` 的 `raw_*` 特征。",
            "- 采集距离/姿态相关特征硬屏蔽，不进入评分；包括 `matrix_*`、`pose_*`、`yaw/pitch/roll`、`scale/distance`、以及深度代理 `*_centroid_z_asym`。",
            "- 新增 raw `bs_*` 表情系数弱监督项：只纳入 train split 中患病更高的表情系数，并乘以较低权重。",
            f"- 表情系数权重倍率：`{evaluation['feature_selection']['expression_weight_multiplier']:.2f}`；每个 role 中表情系数总权重占比上限：`{evaluation['feature_selection']['expression_max_role_weight_share']:.2f}`。",
            "- 只保留 train split 中 `患病均值 > 不患病均值` 的特征。",
            f"- 特征入选阈值：train AUC >= `{evaluation['feature_selection']['min_auc_positive_higher']:.2f}`，pre-cap feature weight >= `{evaluation['feature_selection']['min_feature_weight']:.3f}`。",
            "- 每张图按特征 z-score 加权得到 role-level asymmetry score。",
            "- 每张图再乘以 role weight 和 quality weight。",
            "- 患者级分数按 front/smile/teeth/eyes_closed/forehead_wrinkle/frown 加权聚合。",
            "",
            *v11_detail_appendix(),
            "",
            "## 采集距离/姿态特征屏蔽",
            "",
            f"- 可用 MediaPipe 特征数：`{evaluation['pose_distance_screen']['available_feature_count']}`",
            f"- 屏蔽的采集距离/姿态相关特征数：`{evaluation['pose_distance_screen']['blocked_available_feature_count']}`",
            f"- 原本可能进入 `asym/deviation` 候选、但被屏蔽的特征数：`{evaluation['pose_distance_screen']['blocked_scoring_candidate_count']}`",
            f"- 原始 `bs_*` 表情候选数：`{evaluation['pose_distance_screen']['expression_candidates']}`",
            f"- 屏蔽后仍可进入 V1.1 弱关联筛选的候选数：`{evaluation['pose_distance_screen']['eligible_scoring_candidates_after_screen']}`",
            f"- 被屏蔽的评分候选：`{', '.join(evaluation['pose_distance_screen']['blocked_scoring_candidate_names']) or '无'}`",
            "",
            "## 产物",
            "",
            "- Feature set: `metadata/11_v11_role_aware_feature_set.csv`",
            "- Image scores: `metadata/11_v11_role_aware_image_scores.csv`",
            "- Patient core results: `metadata/11_v11_role_aware_patient_core_results.csv`",
            "- Predictions: `metadata/11_v11_role_aware_predictions.csv`",
            "- Evaluation JSON: `metadata/11_v11_role_aware_evaluation.json`",
            "",
            "## 特征数量",
            "",
            f"- Selected features: `{evaluation['feature_selection']['selected_features']}`",
            f"- Selected by role: `{json.dumps(evaluation['feature_selection']['selected_by_role'], ensure_ascii=False, sort_keys=True)}`",
            f"- Selected by type: `{json.dumps(evaluation['feature_selection']['selected_by_type'], ensure_ascii=False, sort_keys=True)}`",
            f"- Selected by role/type: `{json.dumps(evaluation['feature_selection']['selected_by_role_and_type'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "## 阈值与评估",
            "",
            f"- Threshold source: `{evaluation['threshold_source']}`",
            f"- Threshold: `{evaluation['threshold']:.6f}`",
            "",
            "| split | patients | accuracy | balanced_accuracy | precision | recall | specificity | auc | tp | fp | tn | fn |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for split in ["train", "val", "test"]:
        metrics = evaluation["metrics"][split]
        lines.append(
            "| {split} | {patients} | {accuracy:.6f} | {balanced_accuracy:.6f} | {precision:.6f} | {recall:.6f} | {specificity:.6f} | {auc:.6f} | {tp} | {fp} | {tn} | {fn} |".format(
                split=split,
                auc=evaluation["auc"][split],
                **metrics,
            )
        )
    lines.extend(
        [
            "",
            "## 操作阈值",
            "",
            "| strategy | threshold | val_precision | val_recall | val_specificity | test_precision | test_recall | test_specificity | test_balanced_accuracy |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for name, payload in evaluation["operating_points"].items():
        if not payload.get("available"):
            continue
        val_metrics = payload["val"]
        test_metrics = payload["test"]
        lines.append(
            "| {name} | {threshold:.6f} | {val_precision:.6f} | {val_recall:.6f} | {val_specificity:.6f} | {test_precision:.6f} | {test_recall:.6f} | {test_specificity:.6f} | {test_balanced_accuracy:.6f} |".format(
                name=name,
                threshold=payload["threshold"],
                val_precision=val_metrics["precision"],
                val_recall=val_metrics["recall"],
                val_specificity=val_metrics["specificity"],
                test_precision=test_metrics["precision"],
                test_recall=test_metrics["recall"],
                test_specificity=test_metrics["specificity"],
                test_balanced_accuracy=test_metrics["balanced_accuracy"],
            )
        )
    lines.extend(
        [
            "",
            "## 权重最高的患病更高特征",
            "",
            *feature_table(top_features[:40]),
            "",
            "## 患病更高的表情弱监督特征",
            "",
            *feature_table(top_expression_features[:40]),
            "",
            "## 限制",
            "",
            "- 当前 all-images/no-gate 数据的 quality gate 大多为 `not_run`，因此质量权重主要回退到 `input_quality/1.0`。后续应对 V1.1 角色补跑真实质量门控。",
            "- 该版本是 patient outcome 标签下的弱关联拟合，不是直接面瘫/不对称人工标签训练出的模型。",
            "- raw `bs_*` 表情系数只作为弱监督辅助项，已降权并限制 role 内占比；它不能替代左右对称性特征。",
            "- matrix/姿态/采集距离/深度代理特征已从主评分硬屏蔽；它们后续应作为质量门控和采集偏差控制变量，而不是不对称性得分项。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def v11_detail_appendix() -> list[str]:
    return [
        "## V1.1 输入矩阵与特征映射",
        "",
        "V1.1 的评分输入不是原图像素，而是 `09_mediapipe_full_features.csv` 中每张图的一行 MediaPipe 派生特征。该矩阵由四类信息组成：",
        "",
        "| 输入来源 | 原始 MediaPipe 输出 | 进入 09 矩阵的列 | V1.1 是否评分 | 说明 |",
        "| --- | --- | --- | --- | --- |",
        "| 478 raw landmarks | 每个 landmark 的 `x/y/z` | `raw_*` | 部分进入 | 只使用左右几何差异、中线偏移、区域统计；姿态/距离代理项被屏蔽 |",
        "| 52 blendshapes | 表情系数 | `bs_*` | 降权进入 | 作为患病更高的表情弱监督项，排除 `bs_neutral` |",
        "| 52 blendshape 左右配对差 | 由 `Left/Right` 表情系数相减 | `bsdiff_*` | 进入 | 作为表情运动左右不对称特征 |",
        "| transformation matrix / pose | 4x4 matrix、yaw/pitch/roll、translation、scale | `matrix_*`、`pose_*` | 不进入 | 只可作为质量、姿态、采集距离控制变量 |",
        "",
        "### 直接使用的语义关键点",
        "",
        "这些点直接参与单点、两点距离、中线和部件级几何特征计算。坐标来自 MediaPipe 478 点 raw landmarks，编号为 MediaPipe landmark index。",
        "",
        "| 语义点 | index | 用途 | 映射到 09 特征列 |",
        "| --- | ---: | --- | --- |",
        "| nose_bridge | 168 | 拟合面部中线 | 所有 `*_midline_deviation`、左右分区 region 特征 |",
        "| nose_tip | 1 | 拟合面部中线、鼻尖中线偏移 | `raw_nose_tip_midline_deviation` |",
        "| chin | 152 | 拟合面部中线、脸廓区域 | `raw_face_oval_region_*`、所有中线相关特征 |",
        "| left_eye_outer | 263 | 归一化尺度、左眼区域 | `raw_eye_distance`、`raw_eye_region_*` |",
        "| right_eye_outer | 33 | 归一化尺度、右眼区域 | `raw_eye_distance`、`raw_eye_region_*` |",
        "| left_eye_inner | 362 | 左眼区域 | `raw_eye_region_*` |",
        "| right_eye_inner | 133 | 右眼区域 | `raw_eye_region_*` |",
        "| left_eye_upper / lower | 386 / 374 | 左眼裂高度 | `raw_eye_aperture_asym`、`raw_eye_region_*` |",
        "| right_eye_upper / lower | 159 / 145 | 右眼裂高度 | `raw_eye_aperture_asym`、`raw_eye_region_*` |",
        "| left_brow_inner / outer | 336 / 276 | 左眉高度、眉部区域 | `raw_brow_inner_height_asym`、`raw_brow_outer_height_asym`、`raw_eyebrow_region_*` |",
        "| right_brow_inner / outer | 107 / 46 | 右眉高度、眉部区域 | `raw_brow_inner_height_asym`、`raw_brow_outer_height_asym`、`raw_eyebrow_region_*` |",
        "| left_mouth_corner | 291 | 左口角高度、口宽、唇部区域 | `raw_mouth_corner_vertical_asym`、`raw_mouth_width`、`raw_lip_region_*` |",
        "| right_mouth_corner | 61 | 右口角高度、口宽、唇部区域 | `raw_mouth_corner_vertical_asym`、`raw_mouth_width`、`raw_lip_region_*` |",
        "| upper_lip_center / lower_lip_center | 13 / 14 | 唇中线偏移、张口程度 | `raw_lip_midline_deviation`、`raw_lip_opening`、`raw_lip_region_*` |",
        "| left_nostril / right_nostril | 327 / 98 | 鼻翼左右宽度差 | `raw_nostril_width_asym` |",
        "| left_cheek / right_cheek | 454 / 234 | 面颊宽度差、脸廓区域 | `raw_cheek_width_asym`、`raw_face_oval_region_*` |",
        "| left_jaw / right_jaw | 365 / 136 | 下颌宽度差、脸廓区域 | `raw_jaw_width_asym`、`raw_face_oval_region_*` |",
        "",
        "### 部件区域关键点集合",
        "",
        "区域特征不是只看一个点，而是把区域内多个 landmark 做左右统计。`width/height/area/centroid_y/point_spread` 这些列都来自对应区域的点云统计；`centroid_z` 被 V1.1 屏蔽，因为它更容易混入采集深度和头部姿态。",
        "",
        "| 区域 | 使用的 landmark index | 映射到 09 特征列 | V1.1 用途 |",
        "| --- | --- | --- | --- |",
        "| lips | `0, 13, 14, 17, 37, 39, 40, 61, 78, 80, 81, 82, 84, 87, 88, 91, 95, 146, 178, 181, 185, 191, 267, 269, 270, 291, 308, 310, 311, 312, 314, 317, 318, 321, 324, 375, 402, 405, 409, 415` | `raw_lip_region_*` | 唇部左右区域高度、中心线、点云扩散差异 |",
        "| left_eye | `249, 263, 362, 373, 374, 380, 381, 382, 384, 385, 386, 387, 388, 390, 398, 466` | `raw_eye_region_*` | 左眼裂、眼部区域形态 |",
        "| right_eye | `7, 33, 133, 144, 145, 153, 154, 155, 157, 158, 159, 160, 161, 163, 173, 246` | `raw_eye_region_*` | 右眼裂、眼部区域形态 |",
        "| left_eyebrow | `276, 282, 283, 285, 293, 295, 296, 300, 334, 336` | `raw_eyebrow_region_*` | 左眉区域高度、面积、曲线分布 |",
        "| right_eyebrow | `46, 52, 53, 55, 63, 65, 66, 70, 105, 107` | `raw_eyebrow_region_*` | 右眉区域高度、面积、曲线分布 |",
        "| left_iris | `474, 475, 476, 477` | `raw_iris_region_*` | 左虹膜区域统计，辅助眼部对称性 |",
        "| right_iris | `469, 470, 471, 472` | `raw_iris_region_*` | 右虹膜区域统计，辅助眼部对称性 |",
        "| face_oval | `10, 21, 54, 58, 67, 93, 103, 109, 127, 132, 136, 148, 149, 150, 152, 162, 172, 176, 234, 251, 284, 288, 297, 323, 332, 338, 356, 361, 365, 377, 378, 379, 389, 397, 400, 454` | `raw_face_oval_region_*` | 下颌、面颊、脸廓左右形态差异 |",
        "| all_mesh | `0-477` 全部 raw landmarks | `raw_all_mesh_region_*` | 全面网格左右统计差异 |",
        "",
        "### 特征矩阵列到 landmark 的映射方式",
        "",
        "| 09 矩阵列模式 | 来源关键点/系数 | 计算含义 | V1.1 状态 |",
        "| --- | --- | --- | --- |",
        "| `raw_lip_midline_deviation` | 13、14，与中线 168/1/152 | 上下唇中心到拟合面部中线的平均绝对偏移 | 入选评分 |",
        "| `raw_nose_tip_midline_deviation` | 1，与中线 168/1/152 | 鼻尖到拟合面部中线的绝对偏移 | 入选评分 |",
        "| `raw_mouth_corner_vertical_asym` | 291、61 | 左右口角 y 坐标差，按眼外角距离归一化 | 入选评分 |",
        "| `raw_eye_aperture_asym` | 386/374 与 159/145 | 左右眼裂高度差，按眼外角距离归一化 | 入选评分 |",
        "| `raw_brow_inner_height_asym` | 336、107 | 左右内眉高度差，按眼外角距离归一化 | 入选评分 |",
        "| `raw_brow_outer_height_asym` | 276、46 | 左右外眉高度差，按眼外角距离归一化 | 入选评分 |",
        "| `raw_nostril_width_asym` | 327、98，与中线 168/1/152 | 左右鼻翼到中线距离的绝对差 | 入选评分 |",
        "| `raw_cheek_width_asym` | 454、234，与中线 168/1/152 | 左右面颊到中线距离的绝对差 | 入选评分 |",
        "| `raw_jaw_width_asym` | 365、136，与中线 168/1/152 | 左右下颌到中线距离的绝对差 | 入选评分 |",
        "| `raw_eye_region_width/height/area/centroid_y/point_spread_asym` | left_eye vs right_eye 点集 | 左右眼部区域包围盒、中心 y、点云扩散差异 | 入选评分，`centroid_z` 屏蔽 |",
        "| `raw_eyebrow_region_width/height/area/centroid_y/point_spread_asym` | left_eyebrow vs right_eyebrow 点集 | 左右眉部区域形态差异 | 入选评分，`centroid_z` 屏蔽 |",
        "| `raw_iris_region_width/height/area/centroid_y/point_spread_asym` | left_iris vs right_iris 点集 | 左右虹膜区域形态差异 | 入选评分，`centroid_z` 屏蔽 |",
        "| `raw_lip_region_width/height/area/centroid_y/point_spread_asym` | lips 点集按中线切左右 | 唇部左右区域统计差异 | 部分入选评分，`centroid_z` 屏蔽 |",
        "| `raw_face_oval_region_width/height/area/centroid_y/point_spread_asym` | face_oval 点集按中线切左右 | 脸廓左右区域统计差异 | 入选评分，`centroid_z` 屏蔽 |",
        "| `raw_all_mesh_region_width/height/area/centroid_y/point_spread_asym` | 0-477 全点按中线切左右 | 全面网格左右区域统计差异 | 入选评分，`centroid_z` 屏蔽 |",
        "| `bsdiff_*_abs` | MediaPipe blendshape `*Left` 与 `*Right` | 左右表情系数绝对差 | 入选评分 |",
        "| `bsdiff_*_signed_left_minus_right` | MediaPipe blendshape `*Left - *Right` | 左右表情系数有方向差 | 部分入选评分 |",
        "| `bsdiff_*_mean_abs/max_abs` | 一组左右配对 blendshape | 眼/眉/口/鼻等组内平均或最大左右差 | 入选评分 |",
        "| `bs_*` | MediaPipe 52 表情系数 | 单侧或全局表情强度 | 仅作为降权弱监督项 |",
        "| `matrix_*`、`pose_*`、`raw_eye_distance`、`*_centroid_z_asym` | transformation matrix、pose、采集尺度/深度代理 | 姿态、距离、深度或采集条件 | 硬屏蔽，不参与评分 |",
        "",
        "### 分数计算链路",
        "",
        "1. `03_keypoints.csv` 定位到每张图的 MediaPipe JSON；只保留 `detection_status=detected` 且 raw landmarks 数量至少 478 的图像。",
        "2. `09_mediapipe_full_features.csv` 把每张图展开成一行特征矩阵，包含 `raw_*`、`bs_*`、`bsdiff_*`、`matrix_*`、`pose_*`。",
        "3. V1.1 只在 train split 上选择 `患病均值 > 不患病均值`、`AUC >= 0.53`、`weight >= 0.001` 的弱关联项。",
        "4. 图像级分数：每个入选特征按 train mean/std 做 z-score，截断到 `[-3, 3]`，乘以 feature weight 后求加权均值。",
        "5. 表情弱监督项：raw `bs_*` 先乘 `0.35`，再限制每个 role 内总权重最多占 `25%`。",
        "6. role 图像权重：`image_weight = quality_weight * role_weight * feature_weight_total`。",
        "7. 患者级分数：对 front/smile/teeth/eyes_closed/forehead_wrinkle/frown 的图像级 z-score 做权重聚合，再用 sigmoid 转成 `v11_asymmetry_score`。",
        "8. 阈值：在 validation split 上选择 balanced accuracy 最大，其次 precision、recall 的阈值。",
        "",
        "### 能否映射回人脸特征矩阵",
        "",
        "可以。映射分三层：",
        "",
        "- 直接列映射：`11_v11_role_aware_feature_set.csv` 的每一行都有 `role + feature_name`，`feature_name` 就是 `09_mediapipe_full_features.csv` 中的列名。",
        "- landmark/区域映射：所有 `raw_*` 列可以按上面的语义点或区域点集映射回 478 点面网格；例如 `raw_lip_midline_deviation` 映射到 13/14 与 168/1/152，`raw_eye_region_*` 映射到 left_eye/right_eye 点集。",
        "- blendshape 映射：`bs_*` 和 `bsdiff_*` 不对应单个 landmark，而对应 MediaPipe Face Landmarker 输出的表情系数空间；它们可以映射到“口、眼、眉、鼻、颌”等表情组，但不能精确还原成某一个 raw landmark。",
        "",
        "因此，V1.1 的 raw 几何特征可以画回 478 点面网格；blendshape 特征适合画成部件级权重或表情组权重；matrix/pose 特征虽然在 09 矩阵里存在，但 V1.1 不允许它们进入人脸对称性主评分。",
    ]


def feature_table(rows: list[dict[str, Any]]) -> list[str]:
    output = [
        "| role | type | feature | pos_mean | neg_mean | diff | d | auc | weight |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        output.append(
            "| {role} | {feature_type} | {feature_name} | {positive_mean} | {negative_mean} | {mean_diff_positive_minus_negative} | {cohens_d} | {auc_positive_higher} | {feature_weight} |".format(**row)
        )
    return output


if __name__ == "__main__":
    main()
