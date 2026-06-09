#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_v1_mediapipe_full_feature_differences import auc, cohens_d, fmt  # noqa: E402


DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"
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
    dataset = args.dataset.resolve()
    image_rows = load_image_rows(dataset, parse_roles(args.roles))
    threshold_rows, sweep_rows = select_feature_thresholds(image_rows)
    prediction_rows = build_prediction_rows(image_rows, threshold_rows)
    count_threshold_rows, count_sweep_rows = select_count_threshold(prediction_rows)
    apply_count_threshold(prediction_rows, count_threshold_rows[0])
    summary = build_summary(dataset, image_rows, threshold_rows, count_threshold_rows[0], prediction_rows)

    metadata = dataset / "metadata"
    reports = dataset / "reports"
    write_csv(metadata / "51_old_core_feature_image_thresholds.csv", threshold_rows, feature_threshold_fields())
    write_csv(metadata / "51_old_core_feature_image_threshold_sweep.csv", sweep_rows, feature_sweep_fields())
    write_csv(metadata / "51_old_core_feature_count_threshold.csv", count_threshold_rows, count_threshold_fields())
    write_csv(metadata / "51_old_core_feature_count_threshold_sweep.csv", count_sweep_rows, count_sweep_fields())
    write_csv(metadata / "51_old_core_feature_image_predictions.csv", prediction_rows, image_prediction_fields())
    write_json(metadata / "51_old_core_feature_image_threshold_summary.json", summary)
    write_report(reports / "51_old_core_feature_image_thresholds.md", summary, threshold_rows, count_threshold_rows[0])

    print(f"Wrote {metadata / '51_old_core_feature_image_thresholds.csv'}")
    print(f"Wrote {metadata / '51_old_core_feature_image_threshold_sweep.csv'}")
    print(f"Wrote {metadata / '51_old_core_feature_count_threshold.csv'}")
    print(f"Wrote {metadata / '51_old_core_feature_count_threshold_sweep.csv'}")
    print(f"Wrote {metadata / '51_old_core_feature_image_predictions.csv'}")
    print(f"Wrote {metadata / '51_old_core_feature_image_threshold_summary.json'}")
    print(f"Wrote {reports / '51_old_core_feature_image_thresholds.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find image-level thresholds for the five old-dataset patient-higher core face-asymmetry features."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Old FaceSymAi all-images dataset root.")
    parser.add_argument(
        "--roles",
        default="all",
        help="Comma-separated media_role filter, or 'all' for every detected image row.",
    )
    return parser.parse_args()


def parse_roles(value: str) -> tuple[str, ...] | None:
    if value.strip().lower() in {"", "all", "*"}:
        return None
    return tuple(item.strip() for item in value.split(",") if item.strip())


def load_image_rows(dataset: Path, roles: tuple[str, ...] | None) -> list[dict[str, Any]]:
    split_rows = read_csv(dataset / "metadata" / "05_patient_splits.csv")
    split_by_patient = {row["patient_sample_id"]: row["split"] for row in split_rows}
    feature_rows = read_csv(dataset / "metadata" / "09_mediapipe_full_features.csv")
    output: list[dict[str, Any]] = []
    allowed_roles = None if roles is None else set(roles)
    for row in feature_rows:
        if row.get("detection_status") != "detected":
            continue
        if allowed_roles is not None and row.get("media_role") not in allowed_roles:
            continue
        if row.get("label_binary") not in {"0", "1"}:
            continue
        if row.get("patient_sample_id") not in split_by_patient:
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
        output.append(
            {
                "sample_id": row["sample_id"],
                "patient_sample_id": row["patient_sample_id"],
                "label_group": row["label_group"],
                "label_binary": row["label_binary"],
                "media_role": row["media_role"],
                "split": split_by_patient[row["patient_sample_id"]],
                **values,
            }
        )
    return output


def select_feature_thresholds(rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    threshold_rows: list[dict[str, str]] = []
    sweep_rows: list[dict[str, str]] = []
    train_val = [row for row in rows if row["split"] in {"train", "val"}]
    test = [row for row in rows if row["split"] == "test"]
    for feature in CORE_FEATURES:
        feature_sweep = feature_sweep_metrics(feature, train_val, "train_val")
        sweep_rows.extend(feature_sweep)
        selected = select_best_threshold(feature_sweep)
        selected_threshold = float(selected["threshold"])
        train_metrics = feature_metrics(feature, selected_threshold, train_val, "train_val")
        test_metrics = feature_metrics(feature, selected_threshold, test, "test")
        all_metrics = feature_metrics(feature, selected_threshold, rows, "all")
        threshold_rows.append(
            {
                "feature_name": feature,
                "description": FEATURE_DESCRIPTIONS[feature],
                "direction_rule": "value >= threshold => 患者/人脸不对称",
                "selected_threshold": fmt(selected_threshold),
                **prefixed_metrics("train_val", train_metrics),
                **prefixed_metrics("test", test_metrics),
                **prefixed_metrics("all", all_metrics),
            }
        )
    return threshold_rows, sweep_rows


def build_prediction_rows(
    rows: list[Mapping[str, Any]],
    thresholds: list[Mapping[str, str]],
) -> list[dict[str, Any]]:
    threshold_by_feature = {row["feature_name"]: float(row["selected_threshold"]) for row in thresholds}
    output: list[dict[str, Any]] = []
    for row in rows:
        predicted_by_feature: dict[str, str] = {}
        triggered = 0
        for feature in CORE_FEATURES:
            is_triggered = float(row[feature]) >= threshold_by_feature[feature]
            if is_triggered:
                triggered += 1
            predicted_by_feature[f"{feature}_threshold"] = fmt(threshold_by_feature[feature])
            predicted_by_feature[f"{feature}_triggered"] = "true" if is_triggered else "false"
        output.append(
            {
                **row,
                **{feature: fmt(float(row[feature])) for feature in CORE_FEATURES},
                **predicted_by_feature,
                "triggered_core_feature_count": str(triggered),
                "triggered_core_features": ";".join(feature for feature in CORE_FEATURES if predicted_by_feature[f"{feature}_triggered"] == "true"),
            }
        )
    return output


def select_count_threshold(rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    train_val = [row for row in rows if row["split"] in {"train", "val"}]
    test = [row for row in rows if row["split"] == "test"]
    candidates = list(range(1, len(CORE_FEATURES) + 1))
    sweep_rows = [count_metrics(threshold, train_val, "train_val") for threshold in candidates]
    selected = select_best_threshold(sweep_rows)
    selected_threshold = int(float(selected["threshold"]))
    train_metrics = count_metrics(selected_threshold, train_val, "train_val")
    test_metrics = count_metrics(selected_threshold, test, "test")
    all_metrics = count_metrics(selected_threshold, rows, "all")
    row = {
        "rule_name": "core_feature_trigger_count",
        "direction_rule": "triggered_core_feature_count >= threshold => 患者/人脸不对称",
        "selected_threshold": str(selected_threshold),
        **prefixed_metrics("train_val", train_metrics),
        **prefixed_metrics("test", test_metrics),
        **prefixed_metrics("all", all_metrics),
    }
    return [row], sweep_rows


def apply_count_threshold(rows: list[dict[str, Any]], threshold_row: Mapping[str, str]) -> None:
    threshold = int(float(threshold_row["selected_threshold"]))
    for row in rows:
        predicted = int(row["triggered_core_feature_count"]) >= threshold
        row["count_threshold"] = str(threshold)
        row["image_predicted_label_binary"] = "1" if predicted else "0"
        row["image_predicted_label_group"] = "患病" if predicted else "不患病"
        row["image_face_asymmetry_output"] = "人脸不对称" if predicted else "未见明显人脸不对称"
        row["image_threshold_reason"] = (
            f"{row['triggered_core_feature_count']}/{len(CORE_FEATURES)} 个核心特征达到图片级阈值"
        )


def feature_metrics(
    feature: str,
    threshold: float,
    rows: list[Mapping[str, Any]],
    split_scope: str,
    *,
    include_distribution: bool = True,
) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows]
    values = [float(row[feature]) for row in rows]
    predicted = [value >= threshold for value in values]
    metrics = binary_metrics(labels, predicted)
    output = {
        "feature_name": feature,
        "threshold": fmt(threshold),
        "split_scope": split_scope,
        "patient_count": str(len({row["patient_sample_id"] for row in rows})),
        "image_count": str(len(rows)),
        **metrics,
    }
    if not include_distribution:
        output.update(
            {
                "positive_mean": "",
                "negative_mean": "",
                "positive_median": "",
                "negative_median": "",
                "auc_positive_higher": "",
                "cohens_d": "",
            }
        )
        return output
    pos = [value for value, label in zip(values, labels) if label == 1]
    neg = [value for value, label in zip(values, labels) if label == 0]
    output.update(
        {
            "positive_mean": fmt(mean(pos)),
            "negative_mean": fmt(mean(neg)),
            "positive_median": fmt(percentile(sorted(pos), 0.5)),
            "negative_median": fmt(percentile(sorted(neg), 0.5)),
            "auc_positive_higher": fmt(auc(pos, neg)) if pos and neg else "",
            "cohens_d": fmt(cohens_d(pos, neg)) if pos and neg else "",
        }
    )
    return output


def feature_sweep_metrics(feature: str, rows: list[Mapping[str, Any]], split_scope: str) -> list[dict[str, str]]:
    pairs = sorted(
        [(float(row[feature]), int(row["label_binary"])) for row in rows],
        key=lambda item: item[0],
        reverse=True,
    )
    total_pos = sum(1 for _, label in pairs if label == 1)
    total_neg = len(pairs) - total_pos
    patient_count = str(len({row["patient_sample_id"] for row in rows}))
    image_count = str(len(rows))
    output: list[dict[str, str]] = []

    if not pairs:
        return []

    output.append(
        {
            "feature_name": feature,
            "threshold": fmt(pairs[0][0] + 1e-12),
            "split_scope": split_scope,
            "patient_count": patient_count,
            "image_count": image_count,
            **binary_metrics_from_counts(0, 0, total_pos, total_neg),
            "positive_mean": "",
            "negative_mean": "",
            "positive_median": "",
            "negative_median": "",
            "auc_positive_higher": "",
            "cohens_d": "",
        }
    )

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
                "positive_mean": "",
                "negative_mean": "",
                "positive_median": "",
                "negative_median": "",
                "auc_positive_higher": "",
                "cohens_d": "",
            }
        )
    return output


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


def threshold_candidates(values: Iterable[float]) -> list[float]:
    ordered = sorted(set(values))
    if not ordered:
        return [0.0]
    candidates = [max(0.0, ordered[0] - 1e-12), ordered[-1] + 1e-12]
    candidates.extend(ordered)
    candidates.extend((left + right) / 2.0 for left, right in zip(ordered, ordered[1:]))
    return sorted(set(candidates))


def select_best_threshold(rows: list[Mapping[str, str]]) -> Mapping[str, str]:
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


def prefixed_metrics(prefix: str, row: Mapping[str, str]) -> dict[str, str]:
    excluded = {"feature_name", "threshold", "split_scope"}
    return {f"{prefix}_{key}": value for key, value in row.items() if key not in excluded}


def build_summary(
    dataset: Path,
    image_rows: list[Mapping[str, Any]],
    threshold_rows: list[Mapping[str, str]],
    count_threshold_row: Mapping[str, str],
    prediction_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    counts = Counter(row["split"] for row in image_rows)
    role_counts = Counter(row["media_role"] for row in image_rows)
    output_counts = Counter(row["image_face_asymmetry_output"] for row in prediction_rows)
    return {
        "dataset": dataset.as_posix(),
        "unit": "image-level detected face row",
        "features": list(CORE_FEATURES),
        "threshold_policy": "Select feature thresholds on train+val image rows by max Youden J; ties use balanced accuracy, F1, precision, specificity, then higher threshold. Evaluate on test image rows with patient-level split to avoid patient leakage.",
        "direction_rule": "All five old-dataset core features use value >= threshold as positive because their patient group values are higher.",
        "image_count": len(image_rows),
        "patient_count": len({row["patient_sample_id"] for row in image_rows}),
        "split_image_counts": dict(sorted(counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "feature_thresholds": threshold_rows,
        "count_threshold": count_threshold_row,
        "output_counts": dict(sorted(output_counts.items())),
        "warning": "The positive class is the patient outcome label used as a proxy for face asymmetry. Thresholds are not clinical diagnosis thresholds.",
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    threshold_rows: list[Mapping[str, str]],
    count_threshold_row: Mapping[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 51 旧数据五个核心特征图片级阈值查找",
        "",
        "## 阈值设定方法",
        "",
        "- 单位：旧数据 `09_mediapipe_full_features.csv` 中每一张 MediaPipe detected 人脸图片。",
        "- 标签：图片继承患者 `患病/不患病` 标签；这里把 `患病` 当作人脸不对称代理阳性。",
        "- 方向：这 5 个特征在旧数据中均为患者更高，因此单特征规则统一为 `feature_value >= threshold => 患病/人脸不对称`。",
        "- 阈值选择：使用患者级 split，`train+val` 图片上搜索阈值并最大化 Youden J；并列时依次比较 balanced accuracy、F1、precision、specificity 和更高阈值。",
        "- 验证：最终阈值在 `test` 图片上评估，避免同一患者图片同时参与阈值选择和测试。",
        "",
        "## 单特征阈值",
        "",
    ]
    lines.extend(
        markdown_table(
            [
                "feature",
                "threshold",
                "train_bacc",
                "train_precision",
                "train_recall",
                "train_specificity",
                "test_bacc",
                "test_precision",
                "test_recall",
                "test_specificity",
            ],
            [
                [
                    row["feature_name"],
                    row["selected_threshold"],
                    row["train_val_balanced_accuracy"],
                    row["train_val_precision"],
                    row["train_val_recall"],
                    row["train_val_specificity"],
                    row["test_balanced_accuracy"],
                    row["test_precision"],
                    row["test_recall"],
                    row["test_specificity"],
                ]
                for row in threshold_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 综合图片级判断",
            "",
            "单特征阈值会产生 5 个触发标记。为了给每张人脸一个最终判断，再搜索 `triggered_core_feature_count` 的阈值。",
            "",
            f"- 综合规则：`triggered_core_feature_count >= {count_threshold_row['selected_threshold']}` => `人脸不对称`。",
            f"- train+val precision `{count_threshold_row['train_val_precision']}`，recall `{count_threshold_row['train_val_recall']}`，specificity `{count_threshold_row['train_val_specificity']}`，balanced accuracy `{count_threshold_row['train_val_balanced_accuracy']}`。",
            f"- test precision `{count_threshold_row['test_precision']}`，recall `{count_threshold_row['test_recall']}`，specificity `{count_threshold_row['test_specificity']}`，balanced accuracy `{count_threshold_row['test_balanced_accuracy']}`。",
            "",
            "## 产物",
            "",
            "- 单特征阈值：`metadata/51_old_core_feature_image_thresholds.csv`",
            "- 单特征阈值搜索明细：`metadata/51_old_core_feature_image_threshold_sweep.csv`",
            "- 综合触发数量阈值：`metadata/51_old_core_feature_count_threshold.csv`",
            "- 综合触发数量搜索明细：`metadata/51_old_core_feature_count_threshold_sweep.csv`",
            "- 每张人脸图片级预测：`metadata/51_old_core_feature_image_predictions.csv`",
            "- JSON 摘要：`metadata/51_old_core_feature_image_threshold_summary.json`",
            "",
            "## 限制",
            "",
            "这是基于患者 outcome 标签的图片级弱监督阈值，不能等同于人工面部不对称标签或临床诊断阈值。若后续有人工人脸不对称标签，应重新用人工标签校准阈值。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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


def feature_threshold_fields() -> list[str]:
    fields = ["feature_name", "description", "direction_rule", "selected_threshold"]
    for prefix in ("train_val", "test", "all"):
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
        "positive_mean",
        "negative_mean",
        "positive_median",
        "negative_median",
        "auc_positive_higher",
        "cohens_d",
    ]


def count_threshold_fields() -> list[str]:
    fields = ["rule_name", "direction_rule", "selected_threshold"]
    for prefix in ("train_val", "test", "all"):
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


def image_prediction_fields() -> list[str]:
    fields = [
        "sample_id",
        "patient_sample_id",
        "label_group",
        "label_binary",
        "media_role",
        "split",
        "triggered_core_feature_count",
        "count_threshold",
        "image_predicted_label_binary",
        "image_predicted_label_group",
        "image_face_asymmetry_output",
        "image_threshold_reason",
        "triggered_core_features",
    ]
    for feature in CORE_FEATURES:
        fields.extend([feature, f"{feature}_threshold", f"{feature}_triggered"])
    return fields


if __name__ == "__main__":
    main()
