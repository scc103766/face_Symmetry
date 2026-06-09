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
RULE_TEST_DATASET = PROJECT_ROOT / "datasets" / "stroke_warning_app_rule_test_set_20260508"
OUTPUT_PREFIX = "52_old_all_core_threshold_rule_test"
CORE_FEATURES = (
    "bsdiff_mouthFrown_abs",
    "raw_all_mesh_region_point_spread_asym",
    "bsdiff_mouth_abs",
    "raw_lip_midline_deviation",
    "raw_mouth_corner_vertical_asym",
)
FEATURE_DESCRIPTIONS = {
    "bsdiff_mouthFrown_abs": "口角下拉/口部下垂 blendshape 左右差",
    "raw_all_mesh_region_point_spread_asym": "478 点全脸左右点云离散程度差",
    "bsdiff_mouth_abs": "口部横向/侧向 blendshape 左右差",
    "raw_lip_midline_deviation": "唇中心偏离面部中线程度",
    "raw_mouth_corner_vertical_asym": "左右口角垂直高度差",
}


def main() -> None:
    args = parse_args()
    old_dataset = args.old_dataset.resolve()
    test_dataset = args.test_dataset.resolve()
    old_roles = parse_roles(args.old_roles)
    test_roles = parse_roles(args.test_roles)
    output_prefix = args.output_prefix

    old_rows = load_old_image_rows(old_dataset, old_roles)
    test_rows = load_rule_test_image_rows(test_dataset, test_roles)
    patient_samples = load_patient_samples(test_dataset)

    threshold_rows, feature_sweep_rows = select_feature_thresholds(old_rows, test_rows)
    old_prediction_rows = build_image_prediction_rows(old_rows, threshold_rows)
    count_threshold_rows, count_sweep_rows = select_count_threshold(old_prediction_rows, test_rows, threshold_rows)
    count_threshold = int(count_threshold_rows[0]["selected_threshold"])
    apply_count_threshold(old_prediction_rows, count_threshold)

    image_prediction_rows = build_image_prediction_rows(test_rows, threshold_rows)
    apply_count_threshold(image_prediction_rows, count_threshold)
    patient_threshold_rows, patient_threshold_sweep_rows = select_patient_max_trigger_threshold(
        old_prediction_rows,
        image_prediction_rows,
    )
    patient_max_threshold = int(patient_threshold_rows[0]["selected_threshold"])
    patient_prediction_rows = build_patient_prediction_rows(
        image_prediction_rows,
        patient_samples,
        count_threshold,
        patient_max_threshold,
    )
    role_metric_rows = build_role_metric_rows(image_prediction_rows)
    summary = build_summary(
        old_dataset=old_dataset,
        test_dataset=test_dataset,
        old_roles=old_roles,
        test_roles=test_roles,
        old_rows=old_rows,
        test_rows=test_rows,
        threshold_rows=threshold_rows,
        count_threshold_row=count_threshold_rows[0],
        patient_threshold_row=patient_threshold_rows[0],
        image_prediction_rows=image_prediction_rows,
        patient_prediction_rows=patient_prediction_rows,
        role_metric_rows=role_metric_rows,
    )

    metadata_dir = test_dataset / "metadata"
    report_dir = test_dataset / "reports"
    write_csv(metadata_dir / f"{output_prefix}_feature_thresholds.csv", threshold_rows, feature_threshold_fields())
    write_csv(metadata_dir / f"{output_prefix}_feature_threshold_sweep.csv", feature_sweep_rows, feature_sweep_fields())
    write_csv(metadata_dir / f"{output_prefix}_count_threshold.csv", count_threshold_rows, count_threshold_fields())
    write_csv(metadata_dir / f"{output_prefix}_count_threshold_sweep.csv", count_sweep_rows, count_sweep_fields())
    write_csv(metadata_dir / f"{output_prefix}_patient_threshold.csv", patient_threshold_rows, patient_threshold_fields())
    write_csv(
        metadata_dir / f"{output_prefix}_patient_threshold_sweep.csv",
        patient_threshold_sweep_rows,
        patient_threshold_sweep_fields(),
    )
    write_csv(metadata_dir / f"{output_prefix}_image_predictions.csv", image_prediction_rows, image_prediction_fields())
    write_csv(metadata_dir / f"{output_prefix}_patient_predictions.csv", patient_prediction_rows, patient_prediction_fields())
    write_csv(metadata_dir / f"{output_prefix}_role_metrics.csv", role_metric_rows, role_metric_fields())
    write_json(metadata_dir / f"{output_prefix}_summary.json", summary)
    write_report(
        report_dir / f"{output_prefix}.md",
        summary,
        threshold_rows,
        count_threshold_rows[0],
        patient_threshold_rows[0],
        role_metric_rows,
        output_prefix,
    )

    print(f"Wrote {metadata_dir / f'{output_prefix}_feature_thresholds.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_feature_threshold_sweep.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_count_threshold.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_count_threshold_sweep.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_patient_threshold.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_patient_threshold_sweep.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_image_predictions.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_patient_predictions.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_role_metrics.csv'}")
    print(f"Wrote {metadata_dir / f'{output_prefix}_summary.json'}")
    print(f"Wrote {report_dir / f'{output_prefix}.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fit the five core face-asymmetry feature thresholds on every old-dataset image "
            "and test the rule on the stroke warning app rule test set."
        )
    )
    parser.add_argument("--old-dataset", type=Path, default=OLD_DATASET)
    parser.add_argument("--test-dataset", type=Path, default=RULE_TEST_DATASET)
    parser.add_argument("--old-roles", default="all", help="Comma-separated old media_role filter, or all.")
    parser.add_argument("--test-roles", default="all", help="Comma-separated test media_role filter, or all.")
    parser.add_argument("--output-prefix", default=OUTPUT_PREFIX)
    return parser.parse_args()


def parse_roles(value: str) -> tuple[str, ...] | None:
    if value.strip().lower() in {"", "all", "*"}:
        return None
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_old_image_rows(dataset: Path, roles: tuple[str, ...] | None) -> list[dict[str, Any]]:
    split_by_patient = {
        row["patient_sample_id"]: row.get("split", "")
        for row in read_csv(dataset / "metadata" / "05_patient_splits.csv")
    }
    rows = read_csv(dataset / "metadata" / "09_mediapipe_full_features.csv")
    return normalize_image_rows(rows, roles, source_dataset="old", split_by_patient=split_by_patient)


def load_rule_test_image_rows(dataset: Path, roles: tuple[str, ...] | None) -> list[dict[str, Any]]:
    rows = read_csv(dataset / "metadata" / "40_mediapipe_evidence_image_features.csv")
    return normalize_image_rows(rows, roles, source_dataset="rule_test", split_by_patient={})


def normalize_image_rows(
    rows: list[dict[str, str]],
    roles: tuple[str, ...] | None,
    *,
    source_dataset: str,
    split_by_patient: Mapping[str, str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    allowed_roles = None if roles is None else set(roles)
    for row in rows:
        if row.get("detection_status") != "detected":
            continue
        if allowed_roles is not None and row.get("media_role") not in allowed_roles:
            continue
        if row.get("label_binary") not in {"0", "1"}:
            continue
        values: dict[str, float] = {}
        missing = False
        for feature in CORE_FEATURES:
            value = to_float(row.get(feature))
            if value is None:
                missing = True
                break
            values[feature] = value
        if missing:
            continue
        patient_sample_id = row.get("patient_sample_id", "")
        output.append(
            {
                "source_dataset": source_dataset,
                "sample_id": row.get("sample_id", ""),
                "patient_sample_id": patient_sample_id,
                "patient_id": row.get("patient_id", ""),
                "label_group": row.get("label_group", ""),
                "label_binary": row.get("label_binary", ""),
                "media_role": row.get("media_role", ""),
                "detection_status": row.get("detection_status", ""),
                "split": split_by_patient.get(patient_sample_id, ""),
                "media_id": row.get("media_id", ""),
                "record_id": row.get("record_id", ""),
                "source_excel_row": row.get("source_excel_row", ""),
                **values,
            }
        )
    return output


def load_patient_samples(dataset: Path) -> list[dict[str, str]]:
    path = dataset / "metadata" / "patient_samples.csv"
    return read_csv(path) if path.exists() else []


def select_feature_thresholds(
    old_rows: list[Mapping[str, Any]], test_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    threshold_rows: list[dict[str, str]] = []
    sweep_rows: list[dict[str, str]] = []
    for feature in CORE_FEATURES:
        feature_sweep = feature_sweep_metrics(feature, old_rows, "old_all_fit")
        sweep_rows.extend(feature_sweep)
        selected = select_best_threshold(feature_sweep)
        threshold = float(selected["threshold"])
        old_metrics = feature_metrics(feature, threshold, old_rows, "old_all_fit")
        test_metrics = feature_metrics(feature, threshold, test_rows, "rule_test")
        threshold_rows.append(
            {
                "feature_name": feature,
                "description": FEATURE_DESCRIPTIONS[feature],
                "direction_rule": "value >= threshold => 患病/人脸不对称",
                "selected_threshold": fmt(threshold),
                **prefixed_metrics("old_all_fit", old_metrics),
                **prefixed_metrics("rule_test", test_metrics),
            }
        )
    return threshold_rows, sweep_rows


def build_image_prediction_rows(
    rows: list[Mapping[str, Any]],
    thresholds: list[Mapping[str, str]],
) -> list[dict[str, Any]]:
    threshold_by_feature = {row["feature_name"]: float(row["selected_threshold"]) for row in thresholds}
    output: list[dict[str, Any]] = []
    for row in rows:
        trigger_columns: dict[str, str] = {}
        triggered_features: list[str] = []
        for feature in CORE_FEATURES:
            triggered = float(row[feature]) >= threshold_by_feature[feature]
            trigger_columns[f"{feature}_threshold"] = fmt(threshold_by_feature[feature])
            trigger_columns[f"{feature}_triggered"] = "true" if triggered else "false"
            if triggered:
                triggered_features.append(feature)
        output.append(
            {
                **row,
                **{feature: fmt(float(row[feature])) for feature in CORE_FEATURES},
                **trigger_columns,
                "triggered_core_feature_count": str(len(triggered_features)),
                "triggered_core_features": ";".join(triggered_features),
            }
        )
    return output


def select_count_threshold(
    old_prediction_rows: list[Mapping[str, Any]],
    test_rows: list[Mapping[str, Any]],
    thresholds: list[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    candidates = list(range(1, len(CORE_FEATURES) + 1))
    sweep_rows = [count_metrics(threshold, old_prediction_rows, "old_all_fit") for threshold in candidates]
    selected = select_best_threshold(sweep_rows)
    threshold = int(float(selected["threshold"]))

    test_prediction_rows = build_image_prediction_rows(test_rows, thresholds)
    apply_count_threshold(test_prediction_rows, threshold)
    old_metrics = count_metrics(threshold, old_prediction_rows, "old_all_fit")
    test_metrics = image_prediction_metrics(test_prediction_rows, "rule_test")
    row = {
        "rule_name": "core_feature_trigger_count",
        "direction_rule": "triggered_core_feature_count >= threshold => 患病/人脸不对称",
        "selected_threshold": str(threshold),
        **prefixed_metrics("old_all_fit", old_metrics),
        **prefixed_metrics("rule_test", test_metrics),
    }
    return [row], sweep_rows


def apply_count_threshold(rows: list[dict[str, Any]], threshold: int) -> None:
    for row in rows:
        predicted = int(row["triggered_core_feature_count"]) >= threshold
        row["count_threshold"] = str(threshold)
        row["image_predicted_label_binary"] = "1" if predicted else "0"
        row["image_predicted_label_group"] = "患病" if predicted else "不患病"
        row["image_face_asymmetry_output"] = "人脸不对称" if predicted else "未见明显人脸不对称"
        row["image_confusion_type"] = confusion_type(row.get("label_binary", ""), row["image_predicted_label_binary"])
        row["image_threshold_reason"] = (
            f"{row['triggered_core_feature_count']}/{len(CORE_FEATURES)} 个核心特征达到旧数据全量图片阈值"
        )


def select_patient_max_trigger_threshold(
    old_prediction_rows: list[Mapping[str, Any]],
    test_prediction_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    candidates = list(range(1, len(CORE_FEATURES) + 1))
    sweep_rows = [
        patient_max_trigger_metrics(threshold, old_prediction_rows, "old_all_fit_patient")
        for threshold in candidates
    ]
    selected = select_best_threshold(sweep_rows)
    threshold = int(float(selected["threshold"]))
    old_metrics = patient_max_trigger_metrics(threshold, old_prediction_rows, "old_all_fit_patient")
    test_metrics = patient_max_trigger_metrics(threshold, test_prediction_rows, "rule_test_patient")
    row = {
        "rule_name": "patient_max_triggered_core_feature_count",
        "direction_rule": "patient max(triggered_core_feature_count) >= threshold => 患病/人脸不对称",
        "selected_threshold": str(threshold),
        **prefixed_metrics("old_all_fit", old_metrics),
        **prefixed_metrics("rule_test", test_metrics),
    }
    return [row], sweep_rows


def build_patient_prediction_rows(
    image_rows: list[Mapping[str, Any]],
    patient_samples: list[Mapping[str, str]],
    image_count_threshold: int,
    patient_max_threshold: int,
) -> list[dict[str, Any]]:
    rows_by_patient: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in image_rows:
        rows_by_patient[row["patient_sample_id"]].append(row)

    patient_order: list[str] = []
    base_by_patient: dict[str, Mapping[str, str]] = {}
    for row in patient_samples:
        patient_id = row.get("patient_sample_id", "")
        if not patient_id:
            continue
        patient_order.append(patient_id)
        base_by_patient[patient_id] = row
    for patient_id in rows_by_patient:
        if patient_id not in base_by_patient:
            patient_order.append(patient_id)

    output: list[dict[str, Any]] = []
    for patient_id in patient_order:
        patient_rows = rows_by_patient.get(patient_id, [])
        base = base_by_patient.get(patient_id, patient_rows[0] if patient_rows else {})
        label_binary = str(base.get("label_binary", patient_rows[0].get("label_binary", "") if patient_rows else ""))
        label_group = str(base.get("label_group", patient_rows[0].get("label_group", "") if patient_rows else ""))
        patient_number = str(base.get("patient_id", patient_rows[0].get("patient_id", "") if patient_rows else ""))

        if not patient_rows:
            output.append(
                {
                    "patient_sample_id": patient_id,
                    "patient_id": patient_number,
                    "label_group": label_group,
                    "label_binary": label_binary,
                    "prediction_status": "no_scored_image",
                    "image_count": "0",
                    "positive_image_count": "0",
                    "media_roles": "",
                    "positive_media_roles": "",
                    "max_triggered_core_feature_count": "",
                    "image_count_threshold": str(image_count_threshold),
                    "patient_max_triggered_threshold": str(patient_max_threshold),
                    "patient_predicted_label_binary": "",
                    "patient_predicted_label_group": "",
                    "patient_face_asymmetry_output": "无法判断",
                    "patient_confusion_type": "not_scored",
                    "patient_threshold_reason": "没有可评分的 MediaPipe detected 图片或核心特征缺失",
                    "triggered_core_features": "",
                    "positive_image_sample_ids": "",
                    **{f"{feature}_max": "" for feature in CORE_FEATURES},
                }
            )
            continue

        max_triggered = max(int(row["triggered_core_feature_count"]) for row in patient_rows)
        predicted = max_triggered >= patient_max_threshold
        positive_rows = [row for row in patient_rows if row["image_predicted_label_binary"] == "1"]
        triggered_features = sorted(
            {
                feature
                for row in patient_rows
                for feature in str(row.get("triggered_core_features", "")).split(";")
                if feature
            }
        )
        output.append(
            {
                "patient_sample_id": patient_id,
                "patient_id": patient_number,
                "label_group": label_group,
                "label_binary": label_binary,
                "prediction_status": "scored",
                "image_count": str(len(patient_rows)),
                "positive_image_count": str(len(positive_rows)),
                "media_roles": ";".join(sorted({row["media_role"] for row in patient_rows})),
                "positive_media_roles": ";".join(sorted({row["media_role"] for row in positive_rows})),
                "max_triggered_core_feature_count": str(max_triggered),
                "image_count_threshold": str(image_count_threshold),
                "patient_max_triggered_threshold": str(patient_max_threshold),
                "patient_predicted_label_binary": "1" if predicted else "0",
                "patient_predicted_label_group": "患病" if predicted else "不患病",
                "patient_face_asymmetry_output": "人脸不对称" if predicted else "未见明显人脸不对称",
                "patient_confusion_type": confusion_type(label_binary, "1" if predicted else "0"),
                "patient_threshold_reason": (
                    f"患者内最高图片触发 {max_triggered}/{len(CORE_FEATURES)} 个核心特征，"
                    f"患者级阈值为 {patient_max_threshold}"
                ),
                "triggered_core_features": ";".join(triggered_features),
                "positive_image_sample_ids": ";".join(row["sample_id"] for row in positive_rows),
                **{f"{feature}_max": fmt(max(float(row[feature]) for row in patient_rows)) for feature in CORE_FEATURES},
            }
        )
    return output


def build_role_metric_rows(image_rows: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for role in sorted({row["media_role"] for row in image_rows}):
        role_rows = [row for row in image_rows if row["media_role"] == role]
        metrics = image_prediction_metrics(role_rows, role)
        output.append({"media_role": role, **metrics})
    output.append({"media_role": "all", **image_prediction_metrics(image_rows, "all")})
    return output


def build_summary(
    *,
    old_dataset: Path,
    test_dataset: Path,
    old_roles: tuple[str, ...] | None,
    test_roles: tuple[str, ...] | None,
    old_rows: list[Mapping[str, Any]],
    test_rows: list[Mapping[str, Any]],
    threshold_rows: list[Mapping[str, str]],
    count_threshold_row: Mapping[str, str],
    patient_threshold_row: Mapping[str, str],
    image_prediction_rows: list[Mapping[str, Any]],
    patient_prediction_rows: list[Mapping[str, Any]],
    role_metric_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    image_metrics = image_prediction_metrics(image_prediction_rows, "rule_test_image")
    scored_patient_rows = [row for row in patient_prediction_rows if row["prediction_status"] == "scored"]
    patient_metrics = patient_prediction_metrics(scored_patient_rows, "rule_test_patient")
    nonpatient_patient_rows = [row for row in scored_patient_rows if row["label_binary"] == "0"]
    nonpatient_image_rows = [row for row in image_prediction_rows if row["label_binary"] == "0"]
    patient_false_positives = [row for row in nonpatient_patient_rows if row["patient_predicted_label_binary"] == "1"]
    image_false_positives = [row for row in nonpatient_image_rows if row["image_predicted_label_binary"] == "1"]
    not_scored_rows = [row for row in patient_prediction_rows if row["prediction_status"] != "scored"]
    return {
        "old_dataset": old_dataset.as_posix(),
        "test_dataset": test_dataset.as_posix(),
        "old_roles": "all" if old_roles is None else list(old_roles),
        "test_roles": "all" if test_roles is None else list(test_roles),
        "features": list(CORE_FEATURES),
        "threshold_policy": (
            "Use every old-dataset train+val+test detected image row as the threshold fitting base. "
            "Single-feature thresholds maximize Youden J on old image labels; ties use balanced accuracy, "
            "F1, precision, specificity, then higher threshold. The final image rule uses the fitted "
            "trigger-count threshold. The final patient rule separately fits a threshold on each old "
            "patient's max triggered feature count. New rule-test labels are used only for evaluation."
        ),
        "direction_rule": "All five core features use value >= threshold as positive because the chosen evidence assumes patient values are higher.",
        "old_image_count": len(old_rows),
        "old_patient_count": len({row["patient_sample_id"] for row in old_rows}),
        "old_label_counts": dict(sorted(Counter(row["label_group"] for row in old_rows).items())),
        "old_role_counts": dict(sorted(Counter(row["media_role"] for row in old_rows).items())),
        "test_image_count": len(test_rows),
        "test_patient_count_scored": len(scored_patient_rows),
        "test_patient_count_total": len(patient_prediction_rows),
        "test_patient_not_scored_count": len(not_scored_rows),
        "test_label_counts_images": dict(sorted(Counter(row["label_group"] for row in test_rows).items())),
        "test_role_counts": dict(sorted(Counter(row["media_role"] for row in test_rows).items())),
        "feature_thresholds": threshold_rows,
        "count_threshold": count_threshold_row,
        "patient_threshold": patient_threshold_row,
        "image_metrics": image_metrics,
        "patient_metrics": patient_metrics,
        "role_metrics": role_metric_rows,
        "nonpatient_patient_count": len(nonpatient_patient_rows),
        "nonpatient_patient_false_positive_count": len(patient_false_positives),
        "nonpatient_patient_false_positive_rate": fmt(safe_div(len(patient_false_positives), len(nonpatient_patient_rows))),
        "nonpatient_image_count": len(nonpatient_image_rows),
        "nonpatient_image_false_positive_count": len(image_false_positives),
        "nonpatient_image_false_positive_rate": fmt(safe_div(len(image_false_positives), len(nonpatient_image_rows))),
        "false_positive_patient_ids": [row["patient_sample_id"] for row in patient_false_positives],
        "not_scored_patient_ids": [row["patient_sample_id"] for row in not_scored_rows],
        "warning": "The positive class is the patient outcome label used as a face-asymmetry proxy. This is not a clinical diagnosis threshold.",
    }


def feature_sweep_metrics(feature: str, rows: list[Mapping[str, Any]], split_scope: str) -> list[dict[str, str]]:
    pairs = sorted(
        [(float(row[feature]), int(row["label_binary"])) for row in rows],
        key=lambda item: item[0],
        reverse=True,
    )
    if not pairs:
        return []
    total_pos = sum(1 for _, label in pairs if label == 1)
    total_neg = len(pairs) - total_pos
    patient_count = str(len({row["patient_sample_id"] for row in rows}))
    image_count = str(len(rows))
    output: list[dict[str, str]] = [
        {
            "feature_name": feature,
            "threshold": fmt(pairs[0][0] + 1e-12),
            "split_scope": split_scope,
            "patient_count": patient_count,
            "image_count": image_count,
            **binary_metrics_from_counts(0, 0, total_pos, total_neg),
        }
    ]
    tp = 0
    fp = 0
    index = 0
    while index < len(pairs):
        threshold = pairs[index][0]
        while index < len(pairs) and pairs[index][0] == threshold:
            if pairs[index][1] == 1:
                tp += 1
            else:
                fp += 1
            index += 1
        output.append(
            {
                "feature_name": feature,
                "threshold": fmt(threshold),
                "split_scope": split_scope,
                "patient_count": patient_count,
                "image_count": image_count,
                **binary_metrics_from_counts(tp, fp, total_pos, total_neg),
            }
        )
    return output


def feature_metrics(
    feature: str,
    threshold: float,
    rows: list[Mapping[str, Any]],
    split_scope: str,
) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows]
    values = [float(row[feature]) for row in rows]
    predicted = [value >= threshold for value in values]
    metrics = binary_metrics(labels, predicted)
    pos = [value for value, label in zip(values, labels) if label == 1]
    neg = [value for value, label in zip(values, labels) if label == 0]
    return {
        "feature_name": feature,
        "threshold": fmt(threshold),
        "split_scope": split_scope,
        "patient_count": str(len({row["patient_sample_id"] for row in rows})),
        "image_count": str(len(rows)),
        **metrics,
        "positive_mean": fmt(mean(pos)),
        "negative_mean": fmt(mean(neg)),
        "positive_median": fmt(percentile(sorted(pos), 0.5)),
        "negative_median": fmt(percentile(sorted(neg), 0.5)),
        "auc_positive_higher": fmt(auc(pos, neg)) if pos and neg else "",
        "cohens_d": fmt(cohens_d(pos, neg)) if pos and neg else "",
    }


def count_metrics(threshold: int, rows: list[Mapping[str, Any]], split_scope: str) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows]
    predicted = [int(row["triggered_core_feature_count"]) >= threshold for row in rows]
    return {
        "threshold": str(threshold),
        "split_scope": split_scope,
        "patient_count": str(len({row["patient_sample_id"] for row in rows})),
        "image_count": str(len(rows)),
        **binary_metrics(labels, predicted),
    }


def patient_max_trigger_metrics(threshold: int, rows: list[Mapping[str, Any]], split_scope: str) -> dict[str, str]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["patient_sample_id"]].append(row)
    labels: list[int] = []
    predicted: list[bool] = []
    for patient_rows in grouped.values():
        labels.append(int(patient_rows[0]["label_binary"]))
        max_triggered = max(int(row["triggered_core_feature_count"]) for row in patient_rows)
        predicted.append(max_triggered >= threshold)
    return {
        "threshold": str(threshold),
        "split_scope": split_scope,
        "patient_count": str(len(labels)),
        "image_count": "",
        **binary_metrics(labels, predicted),
    }


def image_prediction_metrics(rows: list[Mapping[str, Any]], split_scope: str) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows if row.get("image_predicted_label_binary") in {"0", "1"}]
    predicted = [row["image_predicted_label_binary"] == "1" for row in rows if row.get("image_predicted_label_binary") in {"0", "1"}]
    return {
        "split_scope": split_scope,
        "patient_count": str(len({row["patient_sample_id"] for row in rows})),
        "image_count": str(len(labels)),
        **binary_metrics(labels, predicted),
    }


def patient_prediction_metrics(rows: list[Mapping[str, Any]], split_scope: str) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows if row.get("patient_predicted_label_binary") in {"0", "1"}]
    predicted = [
        row["patient_predicted_label_binary"] == "1"
        for row in rows
        if row.get("patient_predicted_label_binary") in {"0", "1"}
    ]
    return {
        "split_scope": split_scope,
        "patient_count": str(len(labels)),
        "image_count": "",
        **binary_metrics(labels, predicted),
    }


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


def select_best_threshold(rows: list[Mapping[str, str]]) -> Mapping[str, str]:
    if not rows:
        raise ValueError("No threshold candidates were generated.")
    return max(
        rows,
        key=lambda row: (
            float(row["youden_j"]),
            float(row["balanced_accuracy"]),
            float(row["f1"]),
            float(row["precision"]),
            float(row["specificity"]),
            float(row["threshold"]),
        ),
    )


def confusion_type(label: str, predicted: str) -> str:
    if label == "1" and predicted == "1":
        return "TP"
    if label == "0" and predicted == "1":
        return "FP"
    if label == "0" and predicted == "0":
        return "TN"
    if label == "1" and predicted == "0":
        return "FN"
    return ""


def prefixed_metrics(prefix: str, row: Mapping[str, str]) -> dict[str, str]:
    excluded = {"feature_name", "threshold", "split_scope", "rule_name"}
    return {f"{prefix}_{key}": value for key, value in row.items() if key not in excluded}


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


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    threshold_rows: list[Mapping[str, str]],
    count_threshold_row: Mapping[str, str],
    patient_threshold_row: Mapping[str, str],
    role_metric_rows: list[Mapping[str, str]],
    output_prefix: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    patient_metrics = summary["patient_metrics"]
    image_metrics = summary["image_metrics"]
    lines = [
        "# 52 旧数据全量核心特征阈值在规则测试集上的验证",
        "",
        "## 阈值设定方法",
        "",
        "- 拟合基础：旧数据 `facesym_v1_all_images_no_gate_20260119` 中 `train + val + test` 的全部 MediaPipe detected 图片。",
        "- 测试数据：`stroke_warning_app_rule_test_set_20260508`，新数据标签只用于测试，不参与阈值拟合。",
        "- 方向：五个核心特征均按患者更高处理，规则为 `feature_value >= threshold => 患病/人脸不对称`。",
        "- 单特征阈值：在旧数据全部图片上最大化 Youden J；并列时依次比较 balanced accuracy、F1、precision、specificity 和更高阈值。",
        "- 最终图片级规则：先判断五个特征是否超过各自阈值，再用旧数据全量图片搜索 `triggered_core_feature_count` 阈值。",
        "- 最终患者级规则：把同一患者所有图片中的 `triggered_core_feature_count` 取最大值，再用旧数据全量患者搜索 `max_triggered_core_feature_count` 阈值。",
        "",
        "## 单特征阈值",
        "",
    ]
    lines.extend(
        markdown_table(
            [
                "feature",
                "threshold",
                "old_bacc",
                "old_precision",
                "old_recall",
                "old_specificity",
                "test_bacc",
                "test_precision",
                "test_recall",
                "test_specificity",
            ],
            [
                [
                    row["feature_name"],
                    row["selected_threshold"],
                    row["old_all_fit_balanced_accuracy"],
                    row["old_all_fit_precision"],
                    row["old_all_fit_recall"],
                    row["old_all_fit_specificity"],
                    row["rule_test_balanced_accuracy"],
                    row["rule_test_precision"],
                    row["rule_test_recall"],
                    row["rule_test_specificity"],
                ]
                for row in threshold_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 综合规则",
            "",
            f"- 旧数据全量拟合出的图片级阈值：`triggered_core_feature_count >= {count_threshold_row['selected_threshold']}`。",
            f"- 旧数据全量拟合出的患者级阈值：`max_triggered_core_feature_count >= {patient_threshold_row['selected_threshold']}`。",
            f"- 旧数据图片级：precision `{count_threshold_row['old_all_fit_precision']}`，recall `{count_threshold_row['old_all_fit_recall']}`，specificity `{count_threshold_row['old_all_fit_specificity']}`，balanced accuracy `{count_threshold_row['old_all_fit_balanced_accuracy']}`。",
            f"- 旧数据患者级：precision `{patient_threshold_row['old_all_fit_precision']}`，recall `{patient_threshold_row['old_all_fit_recall']}`，specificity `{patient_threshold_row['old_all_fit_specificity']}`，balanced accuracy `{patient_threshold_row['old_all_fit_balanced_accuracy']}`。",
            f"- 新数据图片级：precision `{image_metrics['precision']}`，recall `{image_metrics['recall']}`，specificity `{image_metrics['specificity']}`，balanced accuracy `{image_metrics['balanced_accuracy']}`；混淆矩阵 TP `{image_metrics['tp']}`、FP `{image_metrics['fp']}`、TN `{image_metrics['tn']}`、FN `{image_metrics['fn']}`。",
            f"- 新数据患者级：precision `{patient_metrics['precision']}`，recall `{patient_metrics['recall']}`，specificity `{patient_metrics['specificity']}`，balanced accuracy `{patient_metrics['balanced_accuracy']}`；混淆矩阵 TP `{patient_metrics['tp']}`、FP `{patient_metrics['fp']}`、TN `{patient_metrics['tn']}`、FN `{patient_metrics['fn']}`。",
            "",
            "## 不患病误判",
            "",
            f"- 患者级不患病样本：`{summary['nonpatient_patient_count']}`，被误判为患病：`{summary['nonpatient_patient_false_positive_count']}`，误判率 `{summary['nonpatient_patient_false_positive_rate']}`。",
            f"- 图片级不患病图片：`{summary['nonpatient_image_count']}`，被误判为患病：`{summary['nonpatient_image_false_positive_count']}`，误判率 `{summary['nonpatient_image_false_positive_rate']}`。",
            f"- 患者级误判 patient_sample_id：`{';'.join(summary['false_positive_patient_ids'])}`。",
            "",
            "## 按 role 的图片级测试",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["role", "image_count", "precision", "recall", "specificity", "balanced_accuracy", "tp", "fp", "tn", "fn"],
            [
                [
                    row["media_role"],
                    row["image_count"],
                    row["precision"],
                    row["recall"],
                    row["specificity"],
                    row["balanced_accuracy"],
                    row["tp"],
                    row["fp"],
                    row["tn"],
                    row["fn"],
                ]
                for row in role_metric_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 产物",
            "",
            f"- 单特征阈值：`metadata/{output_prefix}_feature_thresholds.csv`",
            f"- 单特征阈值搜索明细：`metadata/{output_prefix}_feature_threshold_sweep.csv`",
            f"- 图片级触发数量阈值：`metadata/{output_prefix}_count_threshold.csv`",
            f"- 图片级触发数量搜索明细：`metadata/{output_prefix}_count_threshold_sweep.csv`",
            f"- 患者级最大触发数量阈值：`metadata/{output_prefix}_patient_threshold.csv`",
            f"- 患者级最大触发数量搜索明细：`metadata/{output_prefix}_patient_threshold_sweep.csv`",
            f"- 新数据图片级预测：`metadata/{output_prefix}_image_predictions.csv`",
            f"- 新数据患者级预测：`metadata/{output_prefix}_patient_predictions.csv`",
            f"- 新数据 role 指标：`metadata/{output_prefix}_role_metrics.csv`",
            f"- JSON 摘要：`metadata/{output_prefix}_summary.json`",
            "",
            "## 限制",
            "",
            "该阈值使用患者 outcome 标签作为人脸不对称代理阳性。它可以用于当前规则测试集的技术信号验证，但不能表述为临床诊断阈值；后续若有人工面部不对称标签，应按人工标签重新校准。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return output


def feature_threshold_fields() -> list[str]:
    fields = ["feature_name", "description", "direction_rule", "selected_threshold"]
    for prefix in ("old_all_fit", "rule_test"):
        fields.extend(
            [
                f"{prefix}_patient_count",
                f"{prefix}_image_count",
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
                f"{prefix}_positive_mean",
                f"{prefix}_negative_mean",
                f"{prefix}_positive_median",
                f"{prefix}_negative_median",
                f"{prefix}_auc_positive_higher",
                f"{prefix}_cohens_d",
            ]
        )
    return fields


def feature_sweep_fields() -> list[str]:
    return [
        "feature_name",
        "threshold",
        "split_scope",
        "patient_count",
        "image_count",
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


def count_threshold_fields() -> list[str]:
    fields = ["rule_name", "direction_rule", "selected_threshold"]
    for prefix in ("old_all_fit", "rule_test"):
        fields.extend(
            [
                f"{prefix}_patient_count",
                f"{prefix}_image_count",
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


def count_sweep_fields() -> list[str]:
    return [
        "threshold",
        "split_scope",
        "patient_count",
        "image_count",
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


def patient_threshold_fields() -> list[str]:
    fields = ["rule_name", "direction_rule", "selected_threshold"]
    for prefix in ("old_all_fit", "rule_test"):
        fields.extend(
            [
                f"{prefix}_patient_count",
                f"{prefix}_image_count",
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


def patient_threshold_sweep_fields() -> list[str]:
    return count_sweep_fields()


def image_prediction_fields() -> list[str]:
    fields = [
        "sample_id",
        "patient_sample_id",
        "patient_id",
        "label_group",
        "label_binary",
        "media_role",
        "detection_status",
        "media_id",
        "record_id",
        "source_excel_row",
    ]
    for feature in CORE_FEATURES:
        fields.extend([feature, f"{feature}_threshold", f"{feature}_triggered"])
    fields.extend(
        [
            "triggered_core_feature_count",
            "triggered_core_features",
            "count_threshold",
            "image_predicted_label_binary",
            "image_predicted_label_group",
            "image_face_asymmetry_output",
            "image_confusion_type",
            "image_threshold_reason",
        ]
    )
    return fields


def patient_prediction_fields() -> list[str]:
    fields = [
        "patient_sample_id",
        "patient_id",
        "label_group",
        "label_binary",
        "prediction_status",
        "image_count",
        "positive_image_count",
        "media_roles",
        "positive_media_roles",
        "max_triggered_core_feature_count",
        "image_count_threshold",
        "patient_max_triggered_threshold",
        "patient_predicted_label_binary",
        "patient_predicted_label_group",
        "patient_face_asymmetry_output",
        "patient_confusion_type",
        "patient_threshold_reason",
        "triggered_core_features",
        "positive_image_sample_ids",
    ]
    fields.extend(f"{feature}_max" for feature in CORE_FEATURES)
    return fields


def role_metric_fields() -> list[str]:
    return [
        "media_role",
        "split_scope",
        "patient_count",
        "image_count",
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


if __name__ == "__main__":
    main()
