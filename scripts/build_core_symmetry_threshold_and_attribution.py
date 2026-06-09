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

from scripts.analyze_v1_mediapipe_full_feature_differences import auc, cohens_d, fmt, is_asymmetry_candidate  # noqa: E402


OLD_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"
NEW_DATASET = PROJECT_ROOT / "datasets" / "stroke_warning_app_rule_test_set_20260508"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "core_symmetry_threshold_attribution_20260529"

CORE_FEATURES = (
    "bsdiff_mouthFrown_abs",
    "raw_all_mesh_region_point_spread_asym",
    "bsdiff_mouth_abs",
    "raw_lip_midline_deviation",
    "raw_mouth_corner_vertical_asym",
)

CORE_FEATURE_DESCRIPTIONS = {
    "bsdiff_mouthFrown_abs": "口角下拉/口部下垂 blendshape 左右差",
    "raw_all_mesh_region_point_spread_asym": "478 点全脸左右点云离散程度差",
    "bsdiff_mouth_abs": "口部横向/侧向 blendshape 左右差",
    "raw_lip_midline_deviation": "唇中心偏离面部中线程度",
    "raw_mouth_corner_vertical_asym": "左右口角垂直高度差",
}

DATASET_CONFIGS = (
    {
        "dataset_key": "old_20260119",
        "dataset_name": "facesym_v1_all_images_no_gate_20260119",
        "dataset_path": OLD_DATASET,
        "feature_csv": OLD_DATASET / "metadata" / "09_mediapipe_full_features.csv",
        "role_scope": "smile_or_teeth",
        "roles": ("smile", "teeth"),
    },
    {
        "dataset_key": "new_20260508",
        "dataset_name": "stroke_warning_app_rule_test_set_20260508",
        "dataset_path": NEW_DATASET,
        "feature_csv": NEW_DATASET / "metadata" / "40_mediapipe_evidence_image_features.csv",
        "role_scope": "smile_teeth",
        "roles": ("smile_teeth",),
    },
)


def main() -> None:
    args = parse_args()
    output = args.output.resolve()
    dataset_configs = list(DATASET_CONFIGS)
    patient_records, feature_records = load_patient_records(dataset_configs)
    reference_stats = build_reference_stats(patient_records)
    score_patient_records(patient_records, reference_stats, args.max_contribution)
    reference_stat_rows = build_reference_stat_rows(reference_stats)
    threshold_rows = build_threshold_sweep(patient_records)
    selected_threshold = select_threshold(threshold_rows, args.min_specificity)
    apply_threshold(patient_records, selected_threshold)

    supporting_feature_rows = build_supporting_feature_analysis(feature_records, patient_records)
    supporting_feature_rows_for_attribution = [
        row for row in supporting_feature_rows
        if row["attribution_candidate"] == "true"
    ]
    attribution_rows = build_attribution_rows(
        patient_records,
        supporting_feature_rows_for_attribution,
        reference_stats,
        args.max_supporting_attributions,
    )
    summary = build_summary(
        output,
        dataset_configs,
        patient_records,
        threshold_rows,
        selected_threshold,
        reference_stat_rows,
        supporting_feature_rows,
        attribution_rows,
        args.max_contribution,
        args.min_specificity,
    )

    metadata = output / "metadata"
    reports = output / "reports"
    write_csv(metadata / "50_core_symmetry_patient_scores.csv", patient_records, patient_score_fields())
    write_csv(
        metadata / "50_core_symmetry_patient_face_asymmetry_outputs.csv",
        patient_records,
        patient_face_asymmetry_output_fields(),
    )
    write_csv(metadata / "50_core_symmetry_feature_reference_stats.csv", reference_stat_rows, reference_stat_fields())
    write_csv(metadata / "50_core_symmetry_threshold_sweep.csv", threshold_rows, threshold_fields())
    write_csv(metadata / "50_core_symmetry_supporting_feature_analysis.csv", supporting_feature_rows, supporting_feature_fields())
    write_csv(metadata / "50_core_symmetry_high_asymmetry_attributions.csv", attribution_rows, attribution_fields())
    write_json(metadata / "50_core_symmetry_threshold_summary.json", summary)
    write_report(reports / "50_core_symmetry_threshold_and_attribution.md", summary, patient_records, supporting_feature_rows)

    print(f"Wrote {metadata / '50_core_symmetry_patient_scores.csv'}")
    print(f"Wrote {metadata / '50_core_symmetry_patient_face_asymmetry_outputs.csv'}")
    print(f"Wrote {metadata / '50_core_symmetry_feature_reference_stats.csv'}")
    print(f"Wrote {metadata / '50_core_symmetry_threshold_sweep.csv'}")
    print(f"Wrote {metadata / '50_core_symmetry_supporting_feature_analysis.csv'}")
    print(f"Wrote {metadata / '50_core_symmetry_high_asymmetry_attributions.csv'}")
    print(f"Wrote {metadata / '50_core_symmetry_threshold_summary.json'}")
    print(f"Wrote {reports / '50_core_symmetry_threshold_and_attribution.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a two-dataset core symmetry threshold and high-asymmetry attribution report."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output root for threshold and attribution artifacts.")
    parser.add_argument(
        "--max-contribution",
        type=float,
        default=6.0,
        help="Upper cap for one feature's normalized contribution to the core asymmetry score.",
    )
    parser.add_argument(
        "--max-supporting-attributions",
        type=int,
        default=5,
        help="Maximum non-core supporting attribution features emitted per high-asymmetry patient.",
    )
    parser.add_argument(
        "--min-specificity",
        type=float,
        default=0.75,
        help="Minimum combined specificity required when selecting the high-asymmetry threshold.",
    )
    return parser.parse_args()


def load_patient_records(configs: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    patient_records: list[dict[str, Any]] = []
    feature_records: dict[str, dict[str, float]] = {}
    for config in configs:
        rows = [
            row for row in read_csv(config["feature_csv"])
            if row.get("detection_status") == "detected"
            and row.get("label_binary") in {"0", "1"}
            and row.get("media_role") in set(config["roles"])
        ]
        candidate_features = sorted(
            field for field in rows[0].keys()
            if is_supporting_candidate_feature(field) and any(to_float(row.get(field)) is not None for row in rows)
        ) if rows else []
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[row["patient_sample_id"]].append(row)
        for patient_sample_id, patient_rows in sorted(grouped.items()):
            record, feature_values = patient_record_from_rows(config, patient_sample_id, patient_rows, candidate_features)
            if record is None:
                continue
            record["_supporting_feature_values"] = feature_values
            patient_records.append(record)
            feature_records[record["record_key"]] = feature_values
    return patient_records, feature_records


def patient_record_from_rows(
    config: Mapping[str, Any],
    patient_sample_id: str,
    rows: list[Mapping[str, str]],
    candidate_features: list[str],
) -> tuple[dict[str, Any] | None, dict[str, float]]:
    first = rows[0]
    feature_values: dict[str, float] = {}
    peak_sources: dict[str, str] = {}
    for feature in sorted(set(candidate_features) | set(CORE_FEATURES)):
        value, source = max_feature_value(rows, feature)
        if value is not None:
            feature_values[feature] = value
            peak_sources[feature] = source
    if any(feature not in feature_values for feature in CORE_FEATURES):
        return None, {}

    record_key = f"{config['dataset_key']}::{patient_sample_id}"
    record: dict[str, Any] = {
        "record_key": record_key,
        "dataset_key": config["dataset_key"],
        "dataset_name": config["dataset_name"],
        "dataset_path": Path(config["dataset_path"]).as_posix(),
        "role_scope": config["role_scope"],
        "source_roles": ",".join(config["roles"]),
        "patient_sample_id": patient_sample_id,
        "patient_id": first.get("patient_id", ""),
        "label_group": first.get("label_group", ""),
        "label_binary": first.get("label_binary", ""),
        "image_count": str(len(rows)),
        "roles_present": ",".join(sorted({row.get("media_role", "") for row in rows if row.get("media_role")})),
    }
    for feature in CORE_FEATURES:
        record[feature] = fmt(feature_values[feature])
        record[f"{feature}_peak_source"] = peak_sources.get(feature, "")
    return record, feature_values


def max_feature_value(rows: list[Mapping[str, str]], feature: str) -> tuple[float | None, str]:
    best_value: float | None = None
    best_source = ""
    for row in rows:
        value = to_float(row.get(feature))
        if value is None:
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_source = f"{row.get('media_role', '')}:{row.get('sample_id', '')}"
    return best_value, best_source


def build_reference_stats(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    stats: dict[str, dict[str, dict[str, Any]]] = {}
    for dataset_key in sorted({record["dataset_key"] for record in records}):
        dataset_rows = [record for record in records if record["dataset_key"] == dataset_key]
        nondisease_rows = [record for record in dataset_rows if record["label_binary"] == "0"] or dataset_rows
        disease_rows = [record for record in dataset_rows if record["label_binary"] == "1"] or dataset_rows
        stats[dataset_key] = {}
        for feature in CORE_FEATURES:
            nondisease_values = [float(record[feature]) for record in nondisease_rows if record.get(feature) not in {"", None}]
            disease_values = [float(record[feature]) for record in disease_rows if record.get(feature) not in {"", None}]
            nondisease_stats = robust_stats(nondisease_values)
            disease_stats = robust_stats(disease_values)
            stats[dataset_key][feature] = {
                "nondisease": nondisease_stats,
                "disease": disease_stats,
                "nondisease_n": len(nondisease_values),
                "disease_n": len(disease_values),
                "median_delta_disease_minus_nondisease": disease_stats["median"] - nondisease_stats["median"],
                "mean_delta_disease_minus_nondisease": disease_stats["mean"] - nondisease_stats["mean"],
                "robust_feature_active": disease_stats["median"] > nondisease_stats["median"],
            }
    return stats


def build_reference_stat_rows(stats: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for dataset_key, feature_stats in sorted(stats.items()):
        for feature, refs in feature_stats.items():
            nondisease = refs["nondisease"]
            disease = refs["disease"]
            rows.append(
                {
                    "dataset_key": dataset_key,
                    "feature_name": feature,
                    "description": CORE_FEATURE_DESCRIPTIONS[feature],
                    "nondisease_n": str(refs["nondisease_n"]),
                    "disease_n": str(refs["disease_n"]),
                    "nondisease_median": fmt(nondisease["median"]),
                    "nondisease_iqr": fmt(nondisease["iqr"]),
                    "nondisease_mean": fmt(nondisease["mean"]),
                    "disease_median": fmt(disease["median"]),
                    "disease_iqr": fmt(disease["iqr"]),
                    "disease_mean": fmt(disease["mean"]),
                    "median_delta_disease_minus_nondisease": fmt(refs["median_delta_disease_minus_nondisease"]),
                    "mean_delta_disease_minus_nondisease": fmt(refs["mean_delta_disease_minus_nondisease"]),
                    "robust_feature_active": "true" if refs["robust_feature_active"] else "false",
                }
            )
    return rows


def score_patient_records(records: list[dict[str, Any]], stats: Mapping[str, Mapping[str, Mapping[str, Any]]], cap: float) -> None:
    for record in records:
        contributions: list[tuple[str, float]] = []
        active_contributions: list[tuple[str, float]] = []
        above_reference_count = 0
        for feature in CORE_FEATURES:
            value = float(record[feature])
            refs = stats[record["dataset_key"]][feature]
            nondisease = refs["nondisease"]
            disease = refs["disease"]
            delta = refs["median_delta_disease_minus_nondisease"]
            active = bool(refs["robust_feature_active"])
            nondisease_contribution = max(0.0, (value - nondisease["median"]) / nondisease["scale"])
            disease_contribution = max(0.0, (value - disease["median"]) / disease["scale"])
            interpolation = 0.0 if not active or delta <= 1e-12 else (value - nondisease["median"]) / delta
            contribution = min(cap, max(0.0, interpolation)) if active else 0.0
            if value > nondisease["median"]:
                above_reference_count += 1
            record[f"{feature}_robust_feature_active"] = "true" if active else "false"
            record[f"{feature}_nondisease_reference_median"] = fmt(nondisease["median"])
            record[f"{feature}_nondisease_reference_iqr"] = fmt(nondisease["iqr"])
            record[f"{feature}_disease_reference_median"] = fmt(disease["median"])
            record[f"{feature}_disease_reference_iqr"] = fmt(disease["iqr"])
            record[f"{feature}_disease_minus_nondisease_median"] = fmt(delta)
            record[f"{feature}_nondisease_robust_contribution"] = fmt(min(cap, nondisease_contribution))
            record[f"{feature}_disease_robust_contribution"] = fmt(min(cap, disease_contribution))
            record[f"{feature}_disease_interpolation"] = fmt(interpolation)
            record[f"{feature}_disease_interpolation_contribution"] = fmt(contribution)
            contributions.append((feature, contribution))
            if active:
                active_contributions.append((feature, contribution))
        score_source = active_contributions or contributions
        score = sum(value for _, value in score_source) / len(score_source)
        record["core_asymmetry_score"] = fmt(score)
        record["core_feature_count_above_nondisease_median"] = str(above_reference_count)
        record["core_active_feature_count"] = str(len(active_contributions))
        record["top_core_attributions"] = format_top_features(active_contributions, CORE_FEATURE_DESCRIPTIONS, limit=len(CORE_FEATURES))


def build_threshold_sweep(records: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    scores = sorted({float(record["core_asymmetry_score"]) for record in records})
    candidates = threshold_candidates(scores)
    rows: list[dict[str, str]] = []
    for threshold in candidates:
        rows.append(metrics_for_threshold("combined", records, threshold))
        for dataset_key in sorted({record["dataset_key"] for record in records}):
            scoped = [record for record in records if record["dataset_key"] == dataset_key]
            rows.append(metrics_for_threshold(dataset_key, scoped, threshold))
    return rows


def threshold_candidates(scores: list[float]) -> list[float]:
    if not scores:
        return []
    output: list[float] = [max(0.0, scores[0] - 1e-9)]
    output.extend(scores)
    output.extend((left + right) / 2.0 for left, right in zip(scores, scores[1:]))
    output.append(scores[-1] + 1e-9)
    return sorted(set(output))


def metrics_for_threshold(scope: str, records: Iterable[Mapping[str, Any]], threshold: float) -> dict[str, str]:
    tp = fp = tn = fn = 0
    count = 0
    for record in records:
        count += 1
        label = record["label_binary"] == "1"
        predicted = float(record["core_asymmetry_score"]) >= threshold
        if predicted and label:
            tp += 1
        elif predicted and not label:
            fp += 1
        elif not predicted and not label:
            tn += 1
        else:
            fn += 1
    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    specificity = safe_div(tn, tn + fp)
    f1 = safe_div(2 * precision * recall, precision + recall)
    balanced_accuracy = (recall + specificity) / 2.0
    return {
        "scope": scope,
        "threshold": fmt(threshold),
        "patient_count": str(count),
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


def select_threshold(rows: list[Mapping[str, str]], min_specificity: float) -> float:
    combined = [row for row in rows if row["scope"] == "combined"]
    if not combined:
        return 0.0
    eligible = [row for row in combined if float(row["specificity"]) >= min_specificity]
    if eligible:
        combined = eligible
    best = max(
        combined,
        key=lambda row: (
            float(row["youden_j"]),
            float(row["balanced_accuracy"]),
            float(row["f1"]),
            float(row["precision"]),
            float(row["specificity"]),
            float(row["threshold"]),
        ),
    )
    return float(best["threshold"])


def apply_threshold(records: list[dict[str, Any]], threshold: float) -> None:
    for record in records:
        high = float(record["core_asymmetry_score"]) >= threshold
        record["selected_threshold"] = fmt(threshold)
        record["high_asymmetry"] = "true" if high else "false"
        record["face_asymmetry_binary"] = "1" if high else "0"
        record["face_asymmetry_output"] = "人脸不对称" if high else "未见明显人脸不对称"
        record["face_asymmetry_level"] = "人脸不对称性较高" if high else "未达到较高不对称阈值"
        record["face_asymmetry_decision_rule"] = (
            "默认患病标签代表人脸不对称代理阳性；当 core_asymmetry_score >= selected_threshold 时输出人脸不对称。"
        )
        record["face_asymmetry_reason"] = face_asymmetry_reason(record)


def face_asymmetry_reason(record: Mapping[str, Any]) -> str:
    score = record["core_asymmetry_score"]
    threshold = record["selected_threshold"]
    active_count = record.get("core_active_feature_count", "")
    top = record.get("top_core_attributions", "")
    if record.get("high_asymmetry") == "true":
        if top:
            return f"core_asymmetry_score={score} >= {threshold}; {active_count} 个患病更高稳健核心特征参与判断，主要归因为 {top}。"
        return f"core_asymmetry_score={score} >= {threshold}; 达到人脸不对称阈值。"
    if top:
        return f"core_asymmetry_score={score} < {threshold}; 未达到人脸不对称阈值，当前升高特征为 {top}。"
    return f"core_asymmetry_score={score} < {threshold}; 活跃核心特征未形成足够的人脸不对称证据。"


def build_supporting_feature_analysis(
    feature_records: Mapping[str, Mapping[str, float]],
    patient_records: list[Mapping[str, Any]],
) -> list[dict[str, str]]:
    high_keys = {record["record_key"] for record in patient_records if record.get("high_asymmetry") == "true"}
    normal_keys = {record["record_key"] for record in patient_records if record.get("high_asymmetry") != "true"}
    feature_names = sorted({feature for values in feature_records.values() for feature in values})
    rows: list[dict[str, str]] = []
    for feature in feature_names:
        high_values = [feature_records[key][feature] for key in high_keys if feature in feature_records.get(key, {})]
        normal_values = [feature_records[key][feature] for key in normal_keys if feature in feature_records.get(key, {})]
        if len(high_values) < 10 or len(normal_values) < 10:
            continue
        high_stats = basic_stats(high_values)
        normal_stats = basic_stats(normal_values)
        normal_reference = robust_stats(normal_values)
        score_auc = auc(high_values, normal_values)
        effect = cohens_d(high_values, normal_values)
        attribution_candidate = high_stats["mean"] > normal_stats["mean"] and score_auc >= 0.60
        rows.append(
            {
                "feature_name": feature,
                "feature_family": feature_family(feature),
                "is_core_feature": "true" if feature in CORE_FEATURES else "false",
                "high_asymmetry_n": str(len(high_values)),
                "normal_n": str(len(normal_values)),
                "high_asymmetry_mean": fmt(high_stats["mean"]),
                "normal_mean": fmt(normal_stats["mean"]),
                "mean_diff_high_minus_normal": fmt(high_stats["mean"] - normal_stats["mean"]),
                "high_asymmetry_median": fmt(high_stats["median"]),
                "normal_median": fmt(normal_stats["median"]),
                "normal_iqr": fmt(normal_reference["iqr"]),
                "cohens_d": fmt(effect),
                "auc_high_asymmetry_higher": fmt(score_auc),
                "direction": "高不对称更高" if high_stats["mean"] > normal_stats["mean"] else "未升高",
                "attribution_candidate": "true" if attribution_candidate else "false",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["attribution_candidate"] != "true",
            row["is_core_feature"] != "true",
            -float(row["auc_high_asymmetry_higher"]),
            -abs(float(row["cohens_d"])),
            row["feature_name"],
        ),
    )


def build_attribution_rows(
    patient_records: list[Mapping[str, Any]],
    supporting_features: list[Mapping[str, str]],
    reference_stats: Mapping[str, Mapping[str, Mapping[str, Any]]],
    max_supporting: int,
) -> list[dict[str, str]]:
    supporting_by_name = {row["feature_name"]: row for row in supporting_features}
    selected_supporting_names = [
        row["feature_name"] for row in supporting_features
        if row["feature_name"] not in CORE_FEATURES
    ][:max_supporting]
    rows: list[dict[str, str]] = []
    for record in patient_records:
        if record.get("high_asymmetry") != "true":
            continue
        for feature in CORE_FEATURES:
            refs = reference_stats[record["dataset_key"]][feature]
            if not refs["robust_feature_active"]:
                continue
            rows.append(
                {
                    "record_key": record["record_key"],
                    "dataset_key": record["dataset_key"],
                    "patient_sample_id": record["patient_sample_id"],
                    "patient_id": record.get("patient_id", ""),
                    "label_group": record["label_group"],
                    "core_asymmetry_score": record["core_asymmetry_score"],
                    "feature_name": feature,
                    "attribution_source": "core_threshold_feature",
                    "feature_family": feature_family(feature),
                    "description": CORE_FEATURE_DESCRIPTIONS[feature],
                    "feature_value": record[feature],
                    "reference_value": (
                        f"non={fmt(refs['nondisease']['median'])};"
                        f"disease={fmt(refs['disease']['median'])}"
                    ),
                    "nondisease_reference_value": fmt(refs["nondisease"]["median"]),
                    "disease_reference_value": fmt(refs["disease"]["median"]),
                    "feature_interpolation": record[f"{feature}_disease_interpolation"],
                    "contribution_score": record[f"{feature}_disease_interpolation_contribution"],
                    "robust_feature_active": record[f"{feature}_robust_feature_active"],
                    "peak_source": record.get(f"{feature}_peak_source", ""),
                    "support_auc": supporting_by_name.get(feature, {}).get("auc_high_asymmetry_higher", ""),
                    "support_cohens_d": supporting_by_name.get(feature, {}).get("cohens_d", ""),
                }
            )
        feature_values = record.get("_supporting_feature_values")
        if not isinstance(feature_values, dict):
            continue
        for feature in selected_supporting_names:
            value = feature_values.get(feature)
            support = supporting_by_name[feature]
            if value is None or value <= float(support["normal_median"]):
                continue
            rows.append(
                {
                    "record_key": record["record_key"],
                    "dataset_key": record["dataset_key"],
                    "patient_sample_id": record["patient_sample_id"],
                    "patient_id": record.get("patient_id", ""),
                    "label_group": record["label_group"],
                    "core_asymmetry_score": record["core_asymmetry_score"],
                    "feature_name": feature,
                    "attribution_source": "supporting_asymmetry_feature",
                    "feature_family": feature_family(feature),
                    "description": "高不对称组中同步升高的候选不对称特征",
                    "feature_value": fmt(value),
                    "reference_value": support["normal_median"],
                    "nondisease_reference_value": support["normal_median"],
                    "disease_reference_value": "",
                    "feature_interpolation": "",
                    "contribution_score": fmt(min(6.0, max(0.0, (value - float(support["normal_median"])) / max(float(support["normal_iqr"]), 1e-9)))),
                    "robust_feature_active": "",
                    "peak_source": "",
                    "support_auc": support["auc_high_asymmetry_higher"],
                    "support_cohens_d": support["cohens_d"],
                }
            )
    return rows


def build_summary(
    output: Path,
    dataset_configs: list[Mapping[str, Any]],
    patient_records: list[Mapping[str, Any]],
    threshold_rows: list[Mapping[str, str]],
    selected_threshold: float,
    reference_stat_rows: list[Mapping[str, str]],
    supporting_feature_rows: list[Mapping[str, str]],
    attribution_rows: list[Mapping[str, str]],
    max_contribution: float,
    min_specificity: float,
) -> dict[str, Any]:
    selected_metrics = {
        row["scope"]: row
        for row in threshold_rows
        if abs(float(row["threshold"]) - selected_threshold) <= 1e-9
    }
    high_records = [row for row in patient_records if row.get("high_asymmetry") == "true"]
    high_counts = Counter((row["dataset_key"], row["label_group"]) for row in high_records)
    total_counts = Counter((row["dataset_key"], row["label_group"]) for row in patient_records)
    best_by_scope: dict[str, Mapping[str, str]] = {}
    for scope in sorted({row["scope"] for row in threshold_rows}):
        scoped = [row for row in threshold_rows if row["scope"] == scope]
        eligible = [row for row in scoped if float(row["specificity"]) >= min_specificity]
        if eligible:
            scoped = eligible
        best_by_scope[scope] = max(
            scoped,
            key=lambda row: (
                float(row["youden_j"]),
                float(row["balanced_accuracy"]),
                float(row["f1"]),
                float(row["precision"]),
                float(row["specificity"]),
                float(row["threshold"]),
            ),
        )
    return {
        "output": output.as_posix(),
        "core_features": list(CORE_FEATURES),
        "core_feature_descriptions": CORE_FEATURE_DESCRIPTIONS,
        "core_reference_stats": reference_stat_rows,
        "active_core_features_by_dataset": {
            dataset_key: [
                row["feature_name"] for row in reference_stat_rows
                if row["dataset_key"] == dataset_key and row["robust_feature_active"] == "true"
            ]
            for dataset_key in sorted({row["dataset_key"] for row in reference_stat_rows})
        },
        "datasets": [
            {
                "dataset_key": config["dataset_key"],
                "dataset_name": config["dataset_name"],
                "dataset_path": Path(config["dataset_path"]).as_posix(),
                "feature_csv": Path(config["feature_csv"]).as_posix(),
                "role_scope": config["role_scope"],
                "roles": list(config["roles"]),
            }
            for config in dataset_configs
        ],
        "score_formula": (
            "For each dataset and core feature, build robust non-disease and disease reference distributions. "
            "Keep only features where disease median is higher than non-disease median. "
            "Feature interpolation=(patient_max_value-nondisease_median)/(disease_median-nondisease_median), "
            f"clipped to [0,{max_contribution:.1f}]; core_asymmetry_score is the mean of active feature interpolations."
        ),
        "threshold_policy": (
            "Selected from combined two-dataset patient scores with combined specificity >= "
            f"{min_specificity:.2f}, then max Youden J; ties use balanced accuracy, F1, precision, specificity, then higher threshold."
        ),
        "minimum_specificity": fmt(min_specificity),
        "selected_threshold": fmt(selected_threshold),
        "metrics_at_selected_threshold": selected_metrics,
        "best_threshold_by_scope": best_by_scope,
        "patient_count": len(patient_records),
        "high_asymmetry_patient_count": len(high_records),
        "counts_by_dataset_label": {
            f"{dataset_key}/{label}": count
            for (dataset_key, label), count in sorted(total_counts.items())
        },
        "high_asymmetry_counts_by_dataset_label": {
            f"{dataset_key}/{label}": count
            for (dataset_key, label), count in sorted(high_counts.items())
        },
        "supporting_attribution_feature_count": sum(1 for row in supporting_feature_rows if row["attribution_candidate"] == "true"),
        "top_supporting_attribution_features": [
            row for row in supporting_feature_rows
            if row["attribution_candidate"] == "true"
        ][:20],
        "attribution_row_count": len(attribution_rows),
        "warning": "The threshold is calibrated against weak patient outcome labels, not manual facial-asymmetry labels. It is an auxiliary risk/asymmetry flag, not a clinical diagnosis.",
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    patient_records: list[Mapping[str, Any]],
    supporting_feature_rows: list[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    high_records = [row for row in patient_records if row.get("high_asymmetry") == "true"]
    lines = [
        "# 50 核心对称特征阈值与归因分析",
        "",
        "## 目标",
        "",
        "基于当前已确认“患病更高”的 5 个 MediaPipe 派生关键点特征，在旧数据和新数据的口部动作 role 上寻找一个统一阈值。高于该阈值时，输出 `人脸不对称性较高`，并把导致得分升高的核心特征与同步升高的候选不对称特征作为归因。",
        "",
        "## 数据范围",
        "",
    ]
    for dataset in summary["datasets"]:
        lines.append(
            f"- `{dataset['dataset_name']}`：role_scope=`{dataset['role_scope']}`，roles=`{', '.join(dataset['roles'])}`，输入=`{dataset['feature_csv']}`。"
        )
    lines.extend(
        [
            "",
            "## 评分公式",
            "",
            "- 每个数据集分别建立 `不患病` 和 `患病` 两套稳健参考分布，降低两批数据采集差异造成的批次偏移。",
            "- 每个核心特征先做患者级 role 内 `max` 聚合。",
            "- 只保留 `患病中位数 > 不患病中位数` 的稳健特征；默认方向为患病者更高。",
            "- 单特征插值：`(患者特征值 - 不患病中位数) / (患病中位数 - 不患病中位数)`；`0` 近似不患病稳健中心，`1` 近似患病稳健中心，高于 `1` 表示超过患病稳健中心。",
            "- 单特征插值贡献截断到 `[0, 6.0]`，`core_asymmetry_score` 为活跃稳健特征的插值贡献均值。",
            "",
            "## 患病更高稳健特征",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["dataset", "feature", "non_median", "disease_median", "delta", "active"],
            [
                [
                    row["dataset_key"],
                    row["feature_name"],
                    row["nondisease_median"],
                    row["disease_median"],
                    row["median_delta_disease_minus_nondisease"],
                    row["robust_feature_active"],
                ]
                for row in summary["core_reference_stats"]
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 阈值结论",
            "",
            f"- 统一阈值：`core_asymmetry_score >= {summary['selected_threshold']}` 判定为 `人脸不对称性较高`。",
            "- 患者级输出字段：`face_asymmetry_output=人脸不对称/未见明显人脸不对称`，其中 `患病` 标签作为默认人脸不对称代理阳性来选择阈值。",
            f"- 阈值选择：先要求两批数据合并特异性 `>= {summary['minimum_specificity']}`，再最大化 Youden J；并列时依次比较 balanced accuracy、F1、precision、specificity 和更高阈值。",
            "",
        ]
    )
    lines.extend(metrics_table(summary["metrics_at_selected_threshold"]))
    lines.extend(
        [
            "",
            "## 高不对称输出规模",
            "",
            f"- 可评分患者：`{summary['patient_count']}`",
            f"- 高不对称患者：`{summary['high_asymmetry_patient_count']}`",
            f"- 高不对称按数据集/标签分布：`{json.dumps(summary['high_asymmetry_counts_by_dataset_label'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "## 核心归因特征",
            "",
        ]
    )
    lines.extend(core_feature_table())
    lines.extend(
        [
            "",
            "## 支撑归因特征",
            "",
            "下面这些是 `bsdiff_*`、`raw_*asym`、`raw_*deviation` 中，在高不对称组同步升高且 `AUC >= 0.60` 的候选特征。它们用于解释高不对称输出，不是独立诊断规则。",
            "",
        ]
    )
    top_supporting = [row for row in supporting_feature_rows if row["attribution_candidate"] == "true"][:20]
    lines.extend(
        markdown_table(
            ["feature", "family", "core", "high_mean", "normal_mean", "diff", "d", "auc"],
            [
                [
                    row["feature_name"],
                    row["feature_family"],
                    row["is_core_feature"],
                    row["high_asymmetry_mean"],
                    row["normal_mean"],
                    row["mean_diff_high_minus_normal"],
                    row["cohens_d"],
                    row["auc_high_asymmetry_higher"],
                ]
                for row in top_supporting
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 高不对称样本示例",
            "",
        ]
    )
    examples = sorted(high_records, key=lambda row: -float(row["core_asymmetry_score"]))[:20]
    lines.extend(
        markdown_table(
            ["dataset", "patient", "label", "score", "top_core_attributions"],
            [
                [
                    row["dataset_key"],
                    row["patient_sample_id"],
                    row["label_group"],
                    row["core_asymmetry_score"],
                    row["top_core_attributions"],
                ]
                for row in examples
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 产物",
            "",
            "- 患者级评分：`metadata/50_core_symmetry_patient_scores.csv`",
            "- 患者级人脸不对称判断输出：`metadata/50_core_symmetry_patient_face_asymmetry_outputs.csv`",
            "- 患病/不患病双参考分布：`metadata/50_core_symmetry_feature_reference_stats.csv`",
            "- 阈值搜索：`metadata/50_core_symmetry_threshold_sweep.csv`",
            "- 支撑归因特征分析：`metadata/50_core_symmetry_supporting_feature_analysis.csv`",
            "- 高不对称样本归因明细：`metadata/50_core_symmetry_high_asymmetry_attributions.csv`",
            "- JSON 摘要：`metadata/50_core_symmetry_threshold_summary.json`",
            "",
            "## 限制",
            "",
            "- 当前阈值使用的是 `患病/不患病` 弱监督标签，不是人工面部不对称标签；因此只能作为辅助不对称风险提示。",
            "- 新数据全 role 混合口径此前只有 2/5 核心特征通过，因此本轮阈值只使用新数据 `smile_teeth`，旧数据使用 `smile/teeth` 合并口径。",
            "- 输入必须满足 MediaPipe 关键点输出要求：`detected`、478 个 raw landmarks、mouth 左右 blendshape 完整，并能完成中线和眼距归一化。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def metrics_table(metrics: Mapping[str, Mapping[str, str]]) -> list[str]:
    rows = []
    for scope in ("combined", "old_20260119", "new_20260508"):
        row = metrics.get(scope)
        if row:
            rows.append([scope, row["patient_count"], row["tp"], row["fp"], row["tn"], row["fn"], row["precision"], row["recall"], row["specificity"], row["f1"], row["youden_j"]])
    return markdown_table(["scope", "n", "tp", "fp", "tn", "fn", "precision", "recall", "specificity", "f1", "youden_j"], rows)


def core_feature_table() -> list[str]:
    return markdown_table(
        ["feature", "归因含义"],
        [[feature, CORE_FEATURE_DESCRIPTIONS[feature]] for feature in CORE_FEATURES],
    )


def robust_stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    mean = sum(values) / len(values) if values else 0.0
    median = percentile(ordered, 0.5)
    p25 = percentile(ordered, 0.25)
    p75 = percentile(ordered, 0.75)
    p10 = percentile(ordered, 0.10)
    p90 = percentile(ordered, 0.90)
    iqr = p75 - p25
    scale = iqr if iqr > 1e-12 else p90 - p10
    if scale <= 1e-12:
        scale = max(max(ordered) - min(ordered), 1e-9) if ordered else 1e-9
    return {"mean": mean, "median": median, "p25": p25, "p75": p75, "p90": p90, "iqr": iqr, "scale": scale}


def basic_stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    mean = sum(values) / len(values)
    return {"mean": mean, "median": percentile(ordered, 0.5)}


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


def feature_family(feature: str) -> str:
    if feature.startswith("bsdiff_mouth"):
        return "mouth_blendshape"
    if feature.startswith("bsdiff_eye"):
        return "eye_blendshape"
    if feature.startswith("bsdiff_brow"):
        return "brow_blendshape"
    if feature.startswith("raw_lip") or feature.startswith("raw_mouth"):
        return "mouth_landmark"
    if feature.startswith("raw_eye") or feature.startswith("raw_iris"):
        return "eye_landmark"
    if feature.startswith("raw_eyebrow") or feature.startswith("raw_brow"):
        return "brow_landmark"
    if feature.startswith("raw_face_oval") or feature.startswith("raw_jaw") or feature.startswith("raw_cheek"):
        return "face_contour_landmark"
    if feature.startswith("raw_all_mesh"):
        return "all_mesh_landmark"
    return "other_asymmetry"


def is_supporting_candidate_feature(feature: str) -> bool:
    if "_signed_" in feature:
        return False
    return is_asymmetry_candidate(feature)


def format_top_features(
    contributions: list[tuple[str, float]],
    descriptions: Mapping[str, str],
    *,
    limit: int,
) -> str:
    selected = [(feature, value) for feature, value in sorted(contributions, key=lambda item: -item[1]) if value > 0]
    return "; ".join(f"{feature}={value:.3f}({descriptions.get(feature, '')})" for feature, value in selected[:limit])


def safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(output):
        return None
    return output


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    public_rows = [public_row(row) for row in rows]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(public_rows)


def public_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not str(key).startswith("_")}


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


def patient_score_fields() -> list[str]:
    fields = [
        "record_key",
        "dataset_key",
        "dataset_name",
        "role_scope",
        "source_roles",
        "patient_sample_id",
        "patient_id",
        "label_group",
        "label_binary",
        "image_count",
        "roles_present",
        "core_asymmetry_score",
        "selected_threshold",
        "high_asymmetry",
        "face_asymmetry_binary",
        "face_asymmetry_output",
        "face_asymmetry_level",
        "face_asymmetry_decision_rule",
        "face_asymmetry_reason",
        "core_active_feature_count",
        "core_feature_count_above_nondisease_median",
        "top_core_attributions",
    ]
    for feature in CORE_FEATURES:
        fields.extend(
            [
                feature,
                f"{feature}_robust_feature_active",
                f"{feature}_nondisease_reference_median",
                f"{feature}_nondisease_reference_iqr",
                f"{feature}_disease_reference_median",
                f"{feature}_disease_reference_iqr",
                f"{feature}_disease_minus_nondisease_median",
                f"{feature}_nondisease_robust_contribution",
                f"{feature}_disease_robust_contribution",
                f"{feature}_disease_interpolation",
                f"{feature}_disease_interpolation_contribution",
                f"{feature}_peak_source",
            ]
        )
    return fields


def patient_face_asymmetry_output_fields() -> list[str]:
    fields = [
        "record_key",
        "dataset_key",
        "dataset_name",
        "role_scope",
        "source_roles",
        "patient_sample_id",
        "patient_id",
        "label_group",
        "label_binary",
        "core_asymmetry_score",
        "selected_threshold",
        "face_asymmetry_binary",
        "face_asymmetry_output",
        "face_asymmetry_level",
        "face_asymmetry_reason",
        "face_asymmetry_decision_rule",
        "core_active_feature_count",
        "core_feature_count_above_nondisease_median",
        "top_core_attributions",
    ]
    for feature in CORE_FEATURES:
        fields.extend(
            [
                feature,
                f"{feature}_robust_feature_active",
                f"{feature}_nondisease_reference_median",
                f"{feature}_disease_reference_median",
                f"{feature}_disease_minus_nondisease_median",
                f"{feature}_disease_interpolation",
                f"{feature}_disease_interpolation_contribution",
                f"{feature}_peak_source",
            ]
        )
    return fields


def reference_stat_fields() -> list[str]:
    return [
        "dataset_key",
        "feature_name",
        "description",
        "nondisease_n",
        "disease_n",
        "nondisease_median",
        "nondisease_iqr",
        "nondisease_mean",
        "disease_median",
        "disease_iqr",
        "disease_mean",
        "median_delta_disease_minus_nondisease",
        "mean_delta_disease_minus_nondisease",
        "robust_feature_active",
    ]


def threshold_fields() -> list[str]:
    return [
        "scope",
        "threshold",
        "patient_count",
        "tp",
        "fp",
        "tn",
        "fn",
        "precision",
        "recall",
        "specificity",
        "f1",
        "balanced_accuracy",
        "youden_j",
    ]


def supporting_feature_fields() -> list[str]:
    return [
        "feature_name",
        "feature_family",
        "is_core_feature",
        "high_asymmetry_n",
        "normal_n",
        "high_asymmetry_mean",
        "normal_mean",
        "mean_diff_high_minus_normal",
        "high_asymmetry_median",
        "normal_median",
        "normal_iqr",
        "cohens_d",
        "auc_high_asymmetry_higher",
        "direction",
        "attribution_candidate",
    ]


def attribution_fields() -> list[str]:
    return [
        "record_key",
        "dataset_key",
        "patient_sample_id",
        "patient_id",
        "label_group",
        "core_asymmetry_score",
        "feature_name",
        "attribution_source",
        "feature_family",
        "description",
        "feature_value",
        "reference_value",
        "nondisease_reference_value",
        "disease_reference_value",
        "feature_interpolation",
        "contribution_score",
        "robust_feature_active",
        "peak_source",
        "support_auc",
        "support_cohens_d",
    ]


if __name__ == "__main__":
    main()
