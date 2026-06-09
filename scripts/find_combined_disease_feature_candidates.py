#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_v1_mediapipe_full_feature_differences import auc, cohens_d, fmt  # noqa: E402


OLD_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"
NEW_DATASET = PROJECT_ROOT / "datasets" / "stroke_warning_app_rule_test_set_20260508"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "combined_disease_feature_candidates_20260529"

METADATA_FIELDS = {
    "sample_id",
    "patient_sample_id",
    "patient_id",
    "label_group",
    "label_binary",
    "media_role",
    "detection_status",
    "split",
    "media_id",
    "record_id",
    "source_excel_row",
}
POSE_DISTANCE_PREFIXES = ("matrix_", "pose_")
POSE_DISTANCE_TOKENS = ("yaw", "pitch", "roll", "distance", "scale", "width", "opening")
EXCLUDED_EXPRESSION_FEATURES = {"bs_neutral"}

ROLE_SCOPES = {
    "all": {
        "old": None,
        "new": None,
        "description": "两批数据全部 detected 图片；旧数据 role 更多，新数据只有 front_contour/smile_teeth/eyes_right。",
    },
    "mouth_dynamic": {
        "old": {"smile", "teeth"},
        "new": {"smile_teeth"},
        "description": "口部动态对齐口径；旧数据 smile+teeth 对齐新数据 smile_teeth。",
    },
    "front_like": {
        "old": {"front"},
        "new": {"front_contour"},
        "description": "正脸/轮廓对齐口径；旧数据 front 对齐新数据 front_contour。",
    },
}
AGGREGATIONS = ("max", "mean", "median")


def main() -> None:
    args = parse_args()
    old_dataset = args.old_dataset.resolve()
    new_dataset = args.new_dataset.resolve()
    output = args.output.resolve()
    metadata = output / "metadata"
    reports = output / "reports"

    old_rows = load_feature_rows(old_dataset / "metadata" / "09_mediapipe_full_features.csv", "old")
    new_rows = load_feature_rows(new_dataset / "metadata" / "40_mediapipe_evidence_image_features.csv", "new")
    features = common_candidate_features(old_rows, new_rows)

    patient_rows_by_scope = build_all_patient_rows(old_rows, new_rows, features)
    metric_rows = build_metric_rows(patient_rows_by_scope, features)
    candidate_rows = select_candidate_rows(metric_rows)
    distinct_candidate_rows = distinct_best_candidates(candidate_rows)
    threshold_rows = build_threshold_rows(candidate_rows, patient_rows_by_scope)
    summary = build_summary(
        old_dataset=old_dataset,
        new_dataset=new_dataset,
        output=output,
        old_rows=old_rows,
        new_rows=new_rows,
        features=features,
        patient_rows_by_scope=patient_rows_by_scope,
        metric_rows=metric_rows,
        candidate_rows=candidate_rows,
        distinct_candidate_rows=distinct_candidate_rows,
        threshold_rows=threshold_rows,
    )

    write_csv(metadata / "60_combined_disease_feature_all_metrics.csv", metric_rows, all_metric_fields())
    write_csv(metadata / "60_combined_disease_feature_candidates.csv", candidate_rows, candidate_fields())
    write_csv(
        metadata / "60_combined_disease_feature_recommended_distinct.csv",
        distinct_candidate_rows,
        candidate_fields(),
    )
    write_csv(metadata / "60_combined_disease_feature_thresholds.csv", threshold_rows, threshold_fields())
    write_json(metadata / "60_combined_disease_feature_summary.json", summary)
    write_report(reports / "60_combined_disease_feature_candidates.md", summary, candidate_rows, threshold_rows)

    print(f"Wrote {metadata / '60_combined_disease_feature_all_metrics.csv'}")
    print(f"Wrote {metadata / '60_combined_disease_feature_candidates.csv'}")
    print(f"Wrote {metadata / '60_combined_disease_feature_recommended_distinct.csv'}")
    print(f"Wrote {metadata / '60_combined_disease_feature_thresholds.csv'}")
    print(f"Wrote {metadata / '60_combined_disease_feature_summary.json'}")
    print(f"Wrote {reports / '60_combined_disease_feature_candidates.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find MediaPipe feature candidates that separate diseased and non-diseased patients across old and new datasets."
    )
    parser.add_argument("--old-dataset", type=Path, default=OLD_DATASET)
    parser.add_argument("--new-dataset", type=Path, default=NEW_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def load_feature_rows(path: Path, dataset_key: str) -> list[dict[str, str]]:
    rows = read_csv(path)
    output: list[dict[str, str]] = []
    for row in rows:
        if row.get("detection_status") != "detected":
            continue
        if row.get("label_binary") not in {"0", "1"}:
            continue
        row = dict(row)
        row["dataset_key"] = dataset_key
        output.append(row)
    return output


def common_candidate_features(old_rows: list[Mapping[str, str]], new_rows: list[Mapping[str, str]]) -> list[str]:
    old_fields = set(old_rows[0]) if old_rows else set()
    new_fields = set(new_rows[0]) if new_rows else set()
    output: list[str] = []
    for feature in sorted((old_fields & new_fields) - METADATA_FIELDS - {"dataset_key"}):
        feature_type = feature_type_for(feature)
        if feature_type and has_numeric_values(old_rows, feature) and has_numeric_values(new_rows, feature):
            output.append(feature)
    return output


def feature_type_for(feature: str) -> str:
    if is_asymmetry_feature(feature):
        return "asymmetry"
    if is_expression_feature(feature):
        return "expression_blendshape"
    return ""


def is_asymmetry_feature(feature: str) -> bool:
    if is_pose_or_distance_feature(feature):
        return False
    if "_signed_" in feature:
        return False
    if feature.startswith("bsdiff_") and feature.endswith("_abs"):
        return True
    return feature.startswith("raw_") and ("asym" in feature or "deviation" in feature)


def is_expression_feature(feature: str) -> bool:
    return feature.startswith("bs_") and feature not in EXCLUDED_EXPRESSION_FEATURES


def is_pose_or_distance_feature(feature: str) -> bool:
    lowered = feature.lower()
    if lowered.startswith(POSE_DISTANCE_PREFIXES):
        return True
    if lowered.startswith(("bs_", "bsdiff_")):
        return False
    return any(token in lowered for token in POSE_DISTANCE_TOKENS)


def has_numeric_values(rows: list[Mapping[str, str]], feature: str) -> bool:
    return any(to_float(row.get(feature)) is not None for row in rows)


def build_all_patient_rows(
    old_rows: list[Mapping[str, str]],
    new_rows: list[Mapping[str, str]],
    features: list[str],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    output: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for scope, config in ROLE_SCOPES.items():
        scoped_old = filter_roles(old_rows, config["old"])
        scoped_new = filter_roles(new_rows, config["new"])
        for aggregation in AGGREGATIONS:
            old_patient_rows = aggregate_patient_rows("old", scoped_old, features, aggregation)
            new_patient_rows = aggregate_patient_rows("new", scoped_new, features, aggregation)
            output[(scope, aggregation)] = old_patient_rows + new_patient_rows
    return output


def filter_roles(rows: list[Mapping[str, str]], roles: set[str] | None) -> list[Mapping[str, str]]:
    if roles is None:
        return list(rows)
    return [row for row in rows if row.get("media_role") in roles]


def aggregate_patient_rows(
    dataset_key: str,
    rows: list[Mapping[str, str]],
    features: list[str],
    aggregation: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["patient_sample_id"]].append(row)

    output: list[dict[str, Any]] = []
    for patient_sample_id, patient_rows in grouped.items():
        result: dict[str, Any] = {
            "dataset_key": dataset_key,
            "patient_sample_id": f"{dataset_key}:{patient_sample_id}",
            "source_patient_sample_id": patient_sample_id,
            "label_group": patient_rows[0]["label_group"],
            "label_binary": patient_rows[0]["label_binary"],
            "image_count": len(patient_rows),
            "media_roles": ";".join(sorted({row.get("media_role", "") for row in patient_rows})),
        }
        for feature in features:
            values = [value for row in patient_rows if (value := to_float(row.get(feature))) is not None]
            if values:
                result[feature] = aggregate(values, aggregation)
        output.append(result)
    return output


def aggregate(values: list[float], aggregation: str) -> float:
    if aggregation == "max":
        return max(values)
    if aggregation == "mean":
        return sum(values) / len(values)
    if aggregation == "median":
        return percentile(sorted(values), 0.5)
    raise ValueError(f"Unsupported aggregation: {aggregation}")


def build_metric_rows(
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    features: list[str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for (scope, aggregation), patient_rows in sorted(patient_rows_by_scope.items()):
        for feature in features:
            combined_metrics = feature_metrics(patient_rows, feature, "combined")
            old_metrics = feature_metrics([row for row in patient_rows if row["dataset_key"] == "old"], feature, "old")
            new_metrics = feature_metrics([row for row in patient_rows if row["dataset_key"] == "new"], feature, "new")
            direction_consistent = (
                old_metrics["direction"] == new_metrics["direction"]
                and old_metrics["mean_direction"] == new_metrics["mean_direction"]
                and old_metrics["direction"] in {"patient_higher", "nonpatient_higher"}
            )
            directional_auc_min = min(
                float(old_metrics["directional_auc"] or 0),
                float(new_metrics["directional_auc"] or 0),
            )
            mean_diff_abs_min = min(
                abs(float(old_metrics["mean_diff"] or 0)),
                abs(float(new_metrics["mean_diff"] or 0)),
            )
            row = {
                "role_scope": scope,
                "role_scope_description": ROLE_SCOPES[scope]["description"],
                "aggregation": aggregation,
                "feature_type": feature_type_for(feature),
                "feature_name": feature,
                "direction_consistent": "true" if direction_consistent else "false",
                "recommended_feature_surface": "true" if is_recommended_feature_surface(feature) else "false",
                "directional_auc_min": fmt(directional_auc_min),
                "mean_diff_abs_min": fmt(mean_diff_abs_min),
                **prefixed("combined", combined_metrics),
                **prefixed("old", old_metrics),
                **prefixed("new", new_metrics),
            }
            rows.append(row)
    return rows


def feature_metrics(rows: list[Mapping[str, Any]], feature: str, dataset_scope: str) -> dict[str, str]:
    pairs = [(float(row[feature]), row["label_binary"]) for row in rows if feature in row and to_float(row.get(feature)) is not None]
    pos = [value for value, label in pairs if label == "1"]
    neg = [value for value, label in pairs if label == "0"]
    if not pos or not neg:
        return empty_metrics(dataset_scope)
    auc_pos = auc(pos, neg)
    direction = "patient_higher" if auc_pos >= 0.5 else "nonpatient_higher"
    mean_diff = mean(pos) - mean(neg)
    median_diff = percentile(sorted(pos), 0.5) - percentile(sorted(neg), 0.5)
    mean_direction = "patient_higher" if mean_diff >= 0 else "nonpatient_higher"
    d = cohens_d(pos, neg)
    return {
        "dataset_scope": dataset_scope,
        "patient_count": str(len({row["patient_sample_id"] for row in rows if feature in row})),
        "positive_n": str(len(pos)),
        "negative_n": str(len(neg)),
        "positive_mean": fmt(mean(pos)),
        "negative_mean": fmt(mean(neg)),
        "positive_median": fmt(percentile(sorted(pos), 0.5)),
        "negative_median": fmt(percentile(sorted(neg), 0.5)),
        "mean_diff": fmt(mean_diff),
        "median_diff": fmt(median_diff),
        "cohens_d": fmt(d),
        "auc_patient_higher": fmt(auc_pos),
        "direction": direction,
        "mean_direction": mean_direction,
        "directional_auc": fmt(max(auc_pos, 1.0 - auc_pos)),
    }


def empty_metrics(dataset_scope: str) -> dict[str, str]:
    return {
        "dataset_scope": dataset_scope,
        "patient_count": "0",
        "positive_n": "0",
        "negative_n": "0",
        "positive_mean": "",
        "negative_mean": "",
        "positive_median": "",
        "negative_median": "",
        "mean_diff": "",
        "median_diff": "",
        "cohens_d": "",
        "auc_patient_higher": "",
        "direction": "",
        "mean_direction": "",
        "directional_auc": "",
    }


def is_recommended_feature_surface(feature: str) -> bool:
    return feature_type_for(feature) == "asymmetry" and "_signed_" not in feature


def select_candidate_rows(metric_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in metric_rows:
        old_auc = to_float(row["old_directional_auc"]) or 0.0
        new_auc = to_float(row["new_directional_auc"]) or 0.0
        combined_auc = to_float(row["combined_directional_auc"]) or 0.0
        old_n = min(int(row["old_positive_n"]), int(row["old_negative_n"]))
        new_n = min(int(row["new_positive_n"]), int(row["new_negative_n"]))
        consistent = row["direction_consistent"] == "true"
        if old_n < 20 or new_n < 20 or not consistent:
            continue
        if min(old_auc, new_auc) < 0.53 or combined_auc < 0.55:
            continue

        feature_type = row["feature_type"]
        recommended_surface = row["recommended_feature_surface"] == "true"
        if recommended_surface and min(old_auc, new_auc) >= 0.55 and combined_auc >= 0.57:
            grade = "recommended"
        elif recommended_surface:
            grade = "candidate"
        else:
            grade = "reference_only"

        stability_score = (
            (min(old_auc, new_auc) - 0.5) * 2.0
            + (combined_auc - 0.5)
            + min(abs(to_float(row["old_cohens_d"]) or 0.0), abs(to_float(row["new_cohens_d"]) or 0.0), 0.75) * 0.25
        )
        candidate = dict(row)
        candidate["candidate_grade"] = grade
        candidate["stability_score"] = fmt(stability_score)
        candidate["recommended_use"] = recommended_use(row, grade)
        output.append(candidate)

    return sorted(
        output,
        key=lambda row: (
            grade_rank(row["candidate_grade"]),
            float(row["stability_score"]),
            float(row["directional_auc_min"]),
            float(row["combined_directional_auc"]),
        ),
        reverse=True,
    )


def distinct_best_candidates(candidate_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best_by_feature: dict[str, dict[str, str]] = {}
    for row in candidate_rows:
        if row["candidate_grade"] != "recommended":
            continue
        key = row["feature_name"]
        current = best_by_feature.get(key)
        if current is None or distinct_sort_key(row) > distinct_sort_key(current):
            best_by_feature[key] = row
    return sorted(best_by_feature.values(), key=distinct_sort_key, reverse=True)


def distinct_sort_key(row: Mapping[str, str]) -> tuple[float, float, float, int]:
    return (
        float(row["stability_score"]),
        float(row["directional_auc_min"]),
        float(row["combined_directional_auc"]),
        1 if row["role_scope"] == "mouth_dynamic" else 0,
    )


def grade_rank(grade: str) -> int:
    return {"recommended": 3, "candidate": 2, "reference_only": 1}.get(grade, 0)


def recommended_use(row: Mapping[str, str], grade: str) -> str:
    direction = row["combined_direction"]
    if grade == "reference_only":
        return "仅作参考：该特征不是优先推荐的左右差异/对称性表面，可能反映表情执行或采集差异。"
    if direction == "patient_higher":
        return "可作为患病更高的候选阳性证据。"
    return "可作为不患病更高的候选阴性证据；用于降低阳性判断置信度更合适。"


def build_threshold_rows(
    candidate_rows: list[dict[str, str]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for candidate in candidate_rows[:80]:
        key = (candidate["role_scope"], candidate["aggregation"])
        patient_rows = patient_rows_by_scope[key]
        direction = candidate["combined_direction"]
        threshold_row = select_threshold(patient_rows, candidate["feature_name"], direction)
        rows.append(
            {
                "candidate_grade": candidate["candidate_grade"],
                "role_scope": candidate["role_scope"],
                "aggregation": candidate["aggregation"],
                "feature_type": candidate["feature_type"],
                "feature_name": candidate["feature_name"],
                "direction": direction,
                "threshold": threshold_row["threshold"],
                "threshold_rule": threshold_rule(candidate["feature_name"], direction, threshold_row["threshold"]),
                "stability_score": candidate["stability_score"],
                "old_directional_auc": candidate["old_directional_auc"],
                "new_directional_auc": candidate["new_directional_auc"],
                "combined_directional_auc": candidate["combined_directional_auc"],
                **threshold_row,
            }
        )
    return rows


def select_threshold(rows: list[Mapping[str, Any]], feature: str, direction: str) -> dict[str, str]:
    pairs = sorted(
        [
            (float(row[feature]), int(row["label_binary"]), row["dataset_key"])
            for row in rows
            if feature in row and to_float(row.get(feature)) is not None
        ],
        key=lambda item: item[0],
        reverse=direction == "patient_higher",
    )
    if not pairs:
        return {}
    total_pos = sum(1 for _, label, _ in pairs if label == 1)
    total_neg = len(pairs) - total_pos
    candidates: list[dict[str, str]] = []
    tp = fp = 0
    candidates.append({"threshold": fmt(pairs[0][0] + (1e-12 if direction == "patient_higher" else -1e-12)), **binary_metrics_from_counts(0, 0, total_pos, total_neg)})
    index = 0
    while index < len(pairs):
        threshold = pairs[index][0]
        while index < len(pairs) and pairs[index][0] == threshold:
            if pairs[index][1] == 1:
                tp += 1
            else:
                fp += 1
            index += 1
        candidates.append({"threshold": fmt(threshold), **binary_metrics_from_counts(tp, fp, total_pos, total_neg)})
    selected = max(
        candidates,
        key=lambda row: (
            float(row["youden_j"]),
            float(row["balanced_accuracy"]),
            float(row["f1"]),
            float(row["precision"]),
            float(row["specificity"]),
        ),
    )
    threshold = float(selected["threshold"])
    combined_metrics = apply_threshold_metrics(rows, feature, direction, threshold)
    old_metrics = apply_threshold_metrics([row for row in rows if row["dataset_key"] == "old"], feature, direction, threshold)
    new_metrics = apply_threshold_metrics([row for row in rows if row["dataset_key"] == "new"], feature, direction, threshold)
    return {
        "threshold": fmt(threshold),
        **prefixed_threshold("combined", combined_metrics),
        **prefixed_threshold("old", old_metrics),
        **prefixed_threshold("new", new_metrics),
    }


def apply_threshold_metrics(
    rows: list[Mapping[str, Any]],
    feature: str,
    direction: str,
    threshold: float,
) -> dict[str, str]:
    labels: list[int] = []
    predicted: list[bool] = []
    for row in rows:
        value = to_float(row.get(feature))
        if value is None:
            continue
        labels.append(int(row["label_binary"]))
        predicted.append(value >= threshold if direction == "patient_higher" else value <= threshold)
    return {"patient_count": str(len(labels)), **binary_metrics(labels, predicted)}


def binary_metrics(labels: list[int], predicted: list[bool]) -> dict[str, str]:
    tp = fp = tn = fn = 0
    for label, pred in zip(labels, predicted):
        if pred and label == 1:
            tp += 1
        elif pred and label == 0:
            fp += 1
        elif not pred and label == 0:
            tn += 1
        else:
            fn += 1
    return binary_metrics_from_counts(tp, fp, tp + fn, tn + fp)


def binary_metrics_from_counts(tp: int, fp: int, total_pos: int, total_neg: int) -> dict[str, str]:
    fn = total_pos - tp
    tn = total_neg - fp
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    specificity = safe_div(tn, tn + fp)
    f1 = safe_div(2 * precision * recall, precision + recall)
    balanced_accuracy = (recall + specificity) / 2.0
    return {
        "tp": str(tp),
        "fp": str(fp),
        "tn": str(tn),
        "fn": str(fn),
        "precision": fmt(precision),
        "recall": fmt(recall),
        "specificity": fmt(specificity),
        "f1": fmt(f1),
        "balanced_accuracy": fmt(balanced_accuracy),
        "youden_j": fmt(recall + specificity - 1.0),
    }


def threshold_rule(feature: str, direction: str, threshold: str) -> str:
    if direction == "patient_higher":
        return f"{feature} >= {threshold} => 患病倾向更高"
    return f"{feature} <= {threshold} => 患病倾向更高"


def build_summary(
    *,
    old_dataset: Path,
    new_dataset: Path,
    output: Path,
    old_rows: list[Mapping[str, str]],
    new_rows: list[Mapping[str, str]],
    features: list[str],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    metric_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    distinct_candidate_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
) -> dict[str, Any]:
    counts_by_grade = Counter(row["candidate_grade"] for row in candidate_rows)
    top_recommended = [row for row in candidate_rows if row["candidate_grade"] == "recommended"][:20]
    return {
        "old_dataset": old_dataset.as_posix(),
        "new_dataset": new_dataset.as_posix(),
        "output": output.as_posix(),
        "unit": "patient-level aggregation; image rows are aggregated before feature screening",
        "old_detected_image_count": len(old_rows),
        "new_detected_image_count": len(new_rows),
        "old_detected_patient_count": len({row["patient_sample_id"] for row in old_rows}),
        "new_detected_patient_count": len({row["patient_sample_id"] for row in new_rows}),
        "common_candidate_feature_count": len(features),
        "metric_row_count": len(metric_rows),
        "candidate_count": len(candidate_rows),
        "distinct_recommended_feature_count": len(distinct_candidate_rows),
        "candidate_count_by_grade": dict(sorted(counts_by_grade.items())),
        "role_scopes": {scope: config["description"] for scope, config in ROLE_SCOPES.items()},
        "selection_policy": (
            "Find common MediaPipe numeric candidate features, exclude pose/scale/distance fields, aggregate images by patient, "
            "then keep features whose old and new datasets have consistent direction and at least weak directional AUC in both datasets."
        ),
        "recommended_policy": "recommended = asymmetry/deviation feature surface, old/new min directional AUC >= 0.55, combined directional AUC >= 0.57.",
        "top_recommended_features": [
            {
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "feature_name": row["feature_name"],
                "direction": row["combined_direction"],
                "old_directional_auc": row["old_directional_auc"],
                "new_directional_auc": row["new_directional_auc"],
                "combined_directional_auc": row["combined_directional_auc"],
                "stability_score": row["stability_score"],
            }
            for row in top_recommended
        ],
        "top_distinct_recommended_features": [
            {
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "feature_name": row["feature_name"],
                "direction": row["combined_direction"],
                "old_directional_auc": row["old_directional_auc"],
                "new_directional_auc": row["new_directional_auc"],
                "combined_directional_auc": row["combined_directional_auc"],
                "stability_score": row["stability_score"],
            }
            for row in distinct_candidate_rows[:20]
        ],
        "top_thresholds": threshold_rows[:20],
        "warning": "Labels are patient outcome weak labels, not clinical diagnosis or manual facial-asymmetry labels.",
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    candidate_rows: list[dict[str, str]],
    threshold_rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    recommended = [row for row in candidate_rows if row["candidate_grade"] == "recommended"]
    candidate = [row for row in candidate_rows if row["candidate_grade"] == "candidate"]
    reference = [row for row in candidate_rows if row["candidate_grade"] == "reference_only"]
    distinct_recommended = distinct_best_candidates(candidate_rows)
    top_patient_higher = [row for row in recommended if row["combined_direction"] == "patient_higher"][:25]
    top_nonpatient_higher = [row for row in recommended if row["combined_direction"] == "nonpatient_higher"][:15]
    lines = [
        "# 60 两批数据联合寻找患病/不患病判断特征",
        "",
        "## 方法",
        "",
        "- 输入旧数据：`datasets/facesym_v1_all_images_no_gate_20260119/metadata/09_mediapipe_full_features.csv`。",
        "- 输入新数据：`datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_image_features.csv`。",
        "- 单位：先按患者聚合，再做特征筛选；避免把同一患者多张图片当成独立样本。",
        "- role scope：`all`、`mouth_dynamic`、`front_like`；其中 `mouth_dynamic` 为旧数据 `smile+teeth` 对齐新数据 `smile_teeth`。",
        "- 聚合方式：`max`、`mean`、`median`。",
        "- 屏蔽：姿态、位移、尺度、距离、开口宽度等容易受拍摄条件影响的字段，不作为候选。",
        "- 入选要求：旧数据和新数据方向一致；两个数据集 directional AUC 均至少弱高于随机；推荐级还要求特征属于左右差异/对称性表面。",
        "",
        "## 结果摘要",
        "",
        f"- 旧数据 detected 图片 `{summary['old_detected_image_count']}`，患者 `{summary['old_detected_patient_count']}`。",
        f"- 新数据 detected 图片 `{summary['new_detected_image_count']}`，患者 `{summary['new_detected_patient_count']}`。",
        f"- 共同候选特征 `{summary['common_candidate_feature_count']}`。",
        f"- 推荐级特征组合 `{len(recommended)}`，候选级 `{len(candidate)}`，仅参考 `{len(reference)}`。",
        f"- 去重后的推荐特征 `{len(distinct_recommended)}` 个。",
        "",
        "## 去重后的推荐特征",
        "",
    ]
    lines.extend(
        markdown_table(
            [
                "rank",
                "feature",
                "role_scope",
                "agg",
                "direction",
                "old_auc",
                "new_auc",
                "combined_auc",
                "score",
            ],
            [
                [
                    index + 1,
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["combined_direction"],
                    row["old_directional_auc"],
                    row["new_directional_auc"],
                    row["combined_directional_auc"],
                    row["stability_score"],
                ]
                for index, row in enumerate(distinct_recommended[:25])
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 推荐优先使用：患病更高特征组合",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            [
                "rank",
                "role_scope",
                "agg",
                "feature",
                "old_auc",
                "new_auc",
                "combined_auc",
                "old_diff",
                "new_diff",
                "score",
            ],
            [
                [
                    index + 1,
                    row["role_scope"],
                    row["aggregation"],
                    row["feature_name"],
                    row["old_directional_auc"],
                    row["new_directional_auc"],
                    row["combined_directional_auc"],
                    row["old_mean_diff"],
                    row["new_mean_diff"],
                    row["stability_score"],
                ]
                for index, row in enumerate(top_patient_higher[:20])
            ],
        )
    )
    lines.extend(["", "## 可作为阴性参考：不患病更高特征", ""])
    lines.extend(
        markdown_table(
            ["rank", "role_scope", "agg", "feature", "old_auc", "new_auc", "combined_auc", "old_diff", "new_diff"],
            [
                [
                    index + 1,
                    row["role_scope"],
                    row["aggregation"],
                    row["feature_name"],
                    row["old_directional_auc"],
                    row["new_directional_auc"],
                    row["combined_directional_auc"],
                    row["old_mean_diff"],
                    row["new_mean_diff"],
                ]
                for index, row in enumerate(top_nonpatient_higher[:12])
            ],
        )
    )
    lines.extend(["", "## 单特征阈值参考", ""])
    lines.extend(
        markdown_table(
            [
                "rank",
                "grade",
                "role_scope",
                "agg",
                "feature",
                "rule",
                "combined_bacc",
                "combined_precision",
                "combined_recall",
                "combined_specificity",
            ],
            [
                [
                    index + 1,
                    row["candidate_grade"],
                    row["role_scope"],
                    row["aggregation"],
                    row["feature_name"],
                    row["threshold_rule"],
                    row["combined_balanced_accuracy"],
                    row["combined_precision"],
                    row["combined_recall"],
                    row["combined_specificity"],
                ]
                for index, row in enumerate(threshold_rows[:25])
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 产物",
            "",
            "- 全量指标：`metadata/60_combined_disease_feature_all_metrics.csv`",
            "- 筛选候选：`metadata/60_combined_disease_feature_candidates.csv`",
            "- 去重推荐：`metadata/60_combined_disease_feature_recommended_distinct.csv`",
            "- 单特征阈值：`metadata/60_combined_disease_feature_thresholds.csv`",
            "- JSON 摘要：`metadata/60_combined_disease_feature_summary.json`",
            "",
            "## 解释限制",
            "",
            "这里的 `患病/不患病` 是患者 outcome 弱标签，不是人工面部不对称标签，也不是临床诊断标签。推荐特征只能作为技术判断和归因候选；真正上线前仍需要人工面部不对称标签或独立冻结测试集复核。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def prefixed(prefix: str, metrics: Mapping[str, str]) -> dict[str, str]:
    excluded = {"dataset_scope"}
    return {f"{prefix}_{key}": value for key, value in metrics.items() if key not in excluded}


def prefixed_threshold(prefix: str, metrics: Mapping[str, str]) -> dict[str, str]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def percentile(ordered: list[float], q: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def to_float(value: Any) -> float | None:
    if value in {"", None}:
        return None
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    return output if math.isfinite(output) else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return output


def all_metric_fields() -> list[str]:
    fields = [
        "role_scope",
        "role_scope_description",
        "aggregation",
        "feature_type",
        "feature_name",
        "direction_consistent",
        "recommended_feature_surface",
        "directional_auc_min",
        "mean_diff_abs_min",
    ]
    for prefix in ("combined", "old", "new"):
        fields.extend(metric_field_names(prefix))
    return fields


def metric_field_names(prefix: str) -> list[str]:
    return [
        f"{prefix}_patient_count",
        f"{prefix}_positive_n",
        f"{prefix}_negative_n",
        f"{prefix}_positive_mean",
        f"{prefix}_negative_mean",
        f"{prefix}_positive_median",
        f"{prefix}_negative_median",
        f"{prefix}_mean_diff",
        f"{prefix}_median_diff",
        f"{prefix}_cohens_d",
        f"{prefix}_auc_patient_higher",
        f"{prefix}_direction",
        f"{prefix}_mean_direction",
        f"{prefix}_directional_auc",
    ]


def candidate_fields() -> list[str]:
    return [
        "candidate_grade",
        "stability_score",
        "recommended_use",
        *all_metric_fields(),
    ]


def threshold_fields() -> list[str]:
    fields = [
        "candidate_grade",
        "role_scope",
        "aggregation",
        "feature_type",
        "feature_name",
        "direction",
        "threshold",
        "threshold_rule",
        "stability_score",
        "old_directional_auc",
        "new_directional_auc",
        "combined_directional_auc",
    ]
    for prefix in ("combined", "old", "new"):
        fields.extend(
            [
                f"{prefix}_patient_count",
                f"{prefix}_tp",
                f"{prefix}_fp",
                f"{prefix}_tn",
                f"{prefix}_fn",
                f"{prefix}_precision",
                f"{prefix}_recall",
                f"{prefix}_specificity",
                f"{prefix}_f1",
                f"{prefix}_balanced_accuracy",
                f"{prefix}_youden_j",
            ]
        )
    return fields


if __name__ == "__main__":
    main()
