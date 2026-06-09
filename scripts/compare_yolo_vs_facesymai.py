#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "yolo_comparison_20260608"
DEFAULT_YOLO_PREDICTIONS = DEFAULT_OUTPUT_DIR / "yolo_per_image_predictions.csv"
DEFAULT_FACE_RULE62_PREDICTIONS = (
    PROJECT_ROOT
    / "datasets"
    / "combined_disease_feature_candidates_20260529"
    / "metadata"
    / "62_stable_weighted_feature_disease_rule_patient_predictions.csv"
)
DEFAULT_FACE_RULE62_METRICS = (
    PROJECT_ROOT
    / "datasets"
    / "combined_disease_feature_candidates_20260529"
    / "metadata"
    / "62_stable_weighted_feature_disease_rule_metrics.csv"
)
DEFAULT_SPLITS = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119" / "metadata" / "05_patient_splits.csv"

YOLO_RULES = [
    "yolo_any_stroke_eye",
    "yolo_any_stroke_mouth",
    "yolo_any_stroke",
    "yolo_stroke_severe",
    "yolo_majority_stroke",
]
ALL_METHODS = YOLO_RULES + ["facesymai_rule62"]
SPLIT_ORDER = ["train", "val", "test", "combined"]
SEVERITY_RANK = {
    "none": 0,
    "normal": 1,
    "weak": 2,
    "mid": 3,
    "severe": 4,
}
SEVERITY_BY_RANK = {rank: severity for severity, rank in SEVERITY_RANK.items()}

YOLO_PATIENT_FIELDS = [
    "patient_id",
    "patient_label",
    "split",
    "yolo_any_stroke_eye",
    "yolo_any_stroke_mouth",
    "yolo_any_stroke",
    "yolo_stroke_severe",
    "yolo_majority_stroke",
    "image_count",
    "yolo_success_image_count",
    "yolo_error_image_count",
    "yolo_stroke_image_count",
    "yolo_stroke_eye_image_count",
    "yolo_stroke_mouth_image_count",
    "yolo_stroke_severe_image_count",
    "yolo_stroke_image_ratio",
    "yolo_total_detection_count",
    "yolo_stroke_detection_count",
    "yolo_eye_highest_severity",
    "yolo_mouth_highest_severity",
    "yolo_highest_severity",
    "yolo_detected_classes",
    "yolo_error_summary",
]

METRIC_FIELDS = [
    "method",
    "split",
    "precision",
    "recall",
    "specificity",
    "f1",
    "accuracy",
    "tp",
    "fp",
    "tn",
    "fn",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate YOLO image predictions to patient level and compare them with FaceSymAi rule 62."
    )
    parser.add_argument("--yolo-predictions", type=Path, default=DEFAULT_YOLO_PREDICTIONS)
    parser.add_argument("--facesymai-rule62-predictions", type=Path, default=DEFAULT_FACE_RULE62_PREDICTIONS)
    parser.add_argument("--facesymai-rule62-metrics", type=Path, default=DEFAULT_FACE_RULE62_METRICS)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def fmt(value: float) -> str:
    return f"{value:.6f}"


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def patient_sort_key(value: str) -> tuple[int, Any]:
    return (0, int(value)) if str(value).isdigit() else (1, value)


def bool_text(value: bool) -> str:
    return "True" if value else "False"


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def label_to_binary(label: str) -> int:
    if label == "患病":
        return 1
    if label == "不患病":
        return 0
    raise ValueError(f"Unexpected patient_label/label_group: {label!r}")


def normalize_class_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def safe_detections(value: str, patient_id: str, image_path: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid yolo_detections JSON for patient={patient_id} image={image_path}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"yolo_detections must be a list for patient={patient_id} image={image_path}")
    return [item for item in parsed if isinstance(item, dict)]


def max_severity(*values: str) -> str:
    rank = max(SEVERITY_RANK.get(str(value), 0) for value in values)
    return SEVERITY_BY_RANK[rank]


def detection_flags(detections: list[Mapping[str, Any]]) -> dict[str, Any]:
    classes = [str(item.get("class", "")) for item in detections]
    normalized = [normalize_class_name(value) for value in classes]
    stroke_classes = [value for value in normalized if value.startswith("stroke")]
    has_eye = any(value.startswith("strokeeye") for value in normalized)
    has_mouth = any(value.startswith("strokemouth") for value in normalized)
    has_severe = any(value in {"strokeeyesevere", "strokemouthsevere"} for value in normalized)
    return {
        "classes": classes,
        "has_stroke": bool(stroke_classes),
        "has_eye": has_eye,
        "has_mouth": has_mouth,
        "has_severe": has_severe,
        "stroke_detection_count": len(stroke_classes),
    }


def build_yolo_patient_predictions(
    rows: list[Mapping[str, str]],
    split_by_patient_id: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    by_patient: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        patient_id = str(row.get("patient_id", "")).strip()
        if not patient_id:
            raise ValueError("YOLO prediction row is missing patient_id")
        by_patient[patient_id].append(row)

    output: list[dict[str, Any]] = []
    for patient_id in sorted(by_patient, key=patient_sort_key):
        patient_rows = by_patient[patient_id]
        split_row = split_by_patient_id.get(patient_id)
        if not split_row:
            raise ValueError(f"YOLO patient {patient_id} is missing from split CSV")
        patient_label = split_row.get("label_group", "")
        split = split_row.get("split", "")

        class_counter: Counter[str] = Counter()
        error_counter: Counter[str] = Counter()
        image_count = len(patient_rows)
        success_count = 0
        stroke_images = 0
        eye_images = 0
        mouth_images = 0
        severe_images = 0
        total_detection_count = 0
        stroke_detection_count = 0
        eye_severity = "none"
        mouth_severity = "none"

        for row in patient_rows:
            detections = safe_detections(
                row.get("yolo_detections", "[]"),
                patient_id,
                row.get("image_path", ""),
            )
            flags = detection_flags(detections)
            class_counter.update(flags["classes"])
            total_detection_count += len(detections)
            stroke_detection_count += int(flags["stroke_detection_count"])
            if row.get("yolo_error", "none") == "none":
                success_count += 1
            else:
                error_counter.update([row.get("yolo_error", "")])
            if flags["has_stroke"]:
                stroke_images += 1
            if flags["has_eye"]:
                eye_images += 1
            if flags["has_mouth"]:
                mouth_images += 1
            if flags["has_severe"]:
                severe_images += 1
            eye_severity = max_severity(eye_severity, row.get("yolo_eye_max_severity", "none"))
            mouth_severity = max_severity(mouth_severity, row.get("yolo_mouth_max_severity", "none"))

        stroke_ratio = stroke_images / image_count if image_count else 0.0
        row = {
            "patient_id": patient_id,
            "patient_label": patient_label,
            "split": split,
            "yolo_any_stroke_eye": bool_text(eye_images > 0),
            "yolo_any_stroke_mouth": bool_text(mouth_images > 0),
            "yolo_any_stroke": bool_text(stroke_images > 0),
            "yolo_stroke_severe": bool_text(severe_images > 0),
            "yolo_majority_stroke": bool_text(stroke_ratio >= 0.5),
            "image_count": str(image_count),
            "yolo_success_image_count": str(success_count),
            "yolo_error_image_count": str(image_count - success_count),
            "yolo_stroke_image_count": str(stroke_images),
            "yolo_stroke_eye_image_count": str(eye_images),
            "yolo_stroke_mouth_image_count": str(mouth_images),
            "yolo_stroke_severe_image_count": str(severe_images),
            "yolo_stroke_image_ratio": fmt(stroke_ratio),
            "yolo_total_detection_count": str(total_detection_count),
            "yolo_stroke_detection_count": str(stroke_detection_count),
            "yolo_eye_highest_severity": eye_severity,
            "yolo_mouth_highest_severity": mouth_severity,
            "yolo_highest_severity": max_severity(eye_severity, mouth_severity),
            "yolo_detected_classes": ";".join(f"{key}:{value}" for key, value in sorted(class_counter.items())),
            "yolo_error_summary": "none"
            if not error_counter
            else ";".join(f"{key}:{value}" for key, value in sorted(error_counter.items())),
        }
        output.append(row)
    return output


def load_split_rows(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    by_patient_id: dict[str, dict[str, str]] = {}
    for row in rows:
        patient_id = str(row.get("patient_id", "")).strip()
        if patient_id:
            by_patient_id[patient_id] = row
    return by_patient_id


def yolo_split_mismatches(
    rows: Iterable[Mapping[str, str]],
    split_by_patient_id: Mapping[str, Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    label_mismatches: list[dict[str, str]] = []
    split_mismatches: list[dict[str, str]] = []
    for row in rows:
        patient_id = str(row.get("patient_id", "")).strip()
        split_row = split_by_patient_id.get(patient_id)
        if not split_row:
            continue
        if row.get("patient_label", "") != split_row.get("label_group", ""):
            label_mismatches.append(
                {
                    "patient_id": patient_id,
                    "image_path": row.get("image_path", ""),
                    "yolo_image_label": row.get("patient_label", ""),
                    "split_label": split_row.get("label_group", ""),
                }
            )
        if row.get("split", "") != split_row.get("split", ""):
            split_mismatches.append(
                {
                    "patient_id": patient_id,
                    "image_path": row.get("image_path", ""),
                    "yolo_image_split": row.get("split", ""),
                    "split": split_row.get("split", ""),
                }
            )
    return label_mismatches, split_mismatches


def load_facesymai_rule62_predictions(
    path: Path,
    split_by_patient_id: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in read_csv(path):
        if row.get("source_dataset") != "old":
            continue
        source_patient = row.get("source_patient_sample_id", "")
        match = re.search(r"pid(\d+)", source_patient)
        if not match:
            raise ValueError(f"Cannot extract patient_id from FaceSymAi rule62 row: {source_patient!r}")
        patient_id = match.group(1)
        split_row = split_by_patient_id.get(patient_id)
        if not split_row:
            raise ValueError(f"FaceSymAi rule62 old patient {patient_id} is missing from split CSV")
        if row.get("label_group") != split_row.get("label_group"):
            raise ValueError(
                f"Label mismatch for patient {patient_id}: rule62={row.get('label_group')} split={split_row.get('label_group')}"
            )
        output[patient_id] = {
            "patient_id": patient_id,
            "patient_sample_id": row.get("source_patient_sample_id", ""),
            "patient_label": row.get("label_group", ""),
            "label_binary": int(row.get("label_binary", "0")),
            "split": split_row.get("split", ""),
            "predicted": str(row.get("predicted_label_binary", "")).strip() == "1",
            "weighted_disease_score": row.get("weighted_disease_score", ""),
            "score_threshold": row.get("score_threshold", ""),
            "confusion_type": row.get("confusion_type", ""),
        }
    return output


def compute_metrics(labels: list[int], predictions: list[bool]) -> dict[str, Any]:
    if len(labels) != len(predictions):
        raise ValueError("labels and predictions have different lengths")
    tp = sum(1 for label, pred in zip(labels, predictions) if label == 1 and pred)
    fp = sum(1 for label, pred in zip(labels, predictions) if label == 0 and pred)
    tn = sum(1 for label, pred in zip(labels, predictions) if label == 0 and not pred)
    fn = sum(1 for label, pred in zip(labels, predictions) if label == 1 and not pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    accuracy = (tp + tn) / len(labels) if labels else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "accuracy": accuracy,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def build_metric_rows(
    yolo_patients: Mapping[str, Mapping[str, Any]],
    face_rule62: Mapping[str, Mapping[str, Any]],
    common_patient_ids: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for method in ALL_METHODS:
        for split in SPLIT_ORDER:
            selected = [
                patient_id
                for patient_id in common_patient_ids
                if split == "combined" or yolo_patients[patient_id]["split"] == split
            ]
            labels = [label_to_binary(yolo_patients[patient_id]["patient_label"]) for patient_id in selected]
            if method == "facesymai_rule62":
                predictions = [bool(face_rule62[patient_id]["predicted"]) for patient_id in selected]
            else:
                predictions = [parse_bool(yolo_patients[patient_id][method]) for patient_id in selected]
            metric = compute_metrics(labels, predictions)
            rows.append(
                {
                    "method": method,
                    "split": split,
                    "precision": fmt(metric["precision"]),
                    "recall": fmt(metric["recall"]),
                    "specificity": fmt(metric["specificity"]),
                    "f1": fmt(metric["f1"]),
                    "accuracy": fmt(metric["accuracy"]),
                    "tp": str(metric["tp"]),
                    "fp": str(metric["fp"]),
                    "tn": str(metric["tn"]),
                    "fn": str(metric["fn"]),
                }
            )
    return rows


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return output


def metric_lookup(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {(row["method"], row["split"]): row for row in rows}


def best_yolo_rule(metric_rows: list[Mapping[str, Any]]) -> str:
    test_rows = [row for row in metric_rows if row["split"] == "test" and row["method"] in YOLO_RULES]
    return max(
        test_rows,
        key=lambda row: (
            float(row["f1"]),
            float(row["precision"]),
            float(row["specificity"]),
            float(row["recall"]),
            row["method"],
        ),
    )["method"]


def split_label_counts(patient_rows: Iterable[Mapping[str, Any]]) -> dict[str, Counter[str]]:
    counts: dict[str, Counter[str]] = {split: Counter() for split in SPLIT_ORDER}
    for row in patient_rows:
        split = str(row["split"])
        label = str(row["patient_label"])
        counts.setdefault(split, Counter()).update([label])
        counts["combined"].update([label])
    return counts


def read_existing_rule62_old_metrics(path: Path) -> Mapping[str, str] | None:
    if not path.exists():
        return None
    for row in read_csv(path):
        if row.get("dataset_scope") == "old":
            return row
    return None


def compare_metric_value(left: Mapping[str, str], right: Mapping[str, str], key: str) -> str:
    left_value = float(left[key])
    right_value = float(right[key])
    if abs(left_value - right_value) < 1e-12:
        return "持平"
    return "YOLO 更高" if left_value > right_value else "FaceSymAi 规则62 更高"


def build_report(
    *,
    args: argparse.Namespace,
    yolo_image_rows: list[Mapping[str, str]],
    yolo_patient_rows: list[Mapping[str, Any]],
    face_rule62: Mapping[str, Mapping[str, Any]],
    common_patient_ids: list[str],
    missing_in_face: list[str],
    yolo_label_mismatches: list[Mapping[str, str]],
    yolo_split_mismatches_rows: list[Mapping[str, str]],
    metric_rows: list[Mapping[str, Any]],
    existing_rule62_old_metrics: Mapping[str, str] | None,
) -> list[str]:
    lookup = metric_lookup(metric_rows)
    best_rule = best_yolo_rule(metric_rows)
    best_test = lookup[(best_rule, "test")]
    face_test = lookup[("facesymai_rule62", "test")]
    yolo_counts = split_label_counts(yolo_patient_rows)
    common_patient_id_set = set(common_patient_ids)
    common_rows = [row for row in yolo_patient_rows if row["patient_id"] in common_patient_id_set]
    common_counts = split_label_counts(common_rows)
    image_error_count = sum(1 for row in yolo_image_rows if row.get("yolo_error", "none") != "none")

    lines = [
        "# YOLO 患者级聚合与 FaceSymAi 规则62 对比报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- YOLO 图片级输入：`{display_path(args.yolo_predictions)}`",
        f"- FaceSymAi 规则62 患者级输入：`{display_path(args.facesymai_rule62_predictions)}`",
        f"- 患者切分：`{display_path(args.splits)}`",
        "- 阳性标签：`patient_label == 患病`。",
        "- YOLO `yolo_majority_stroke` 使用 `yolo_stroke_image_count / image_count >= 0.5`，分母包含任务 #01 输出中的全部图片行；YOLO 失败图片计入图片数但不会计入 stroke 检测。",
        "",
        "## 数据概览",
        "",
        f"- YOLO 图片级记录：{len(yolo_image_rows)} 张图片；患者级聚合：{len(yolo_patient_rows)} 名患者。",
        f"- YOLO 图片级失败：{image_error_count} 张。",
        f"- FaceSymAi 规则62 旧 V1 患者级预测：{len(face_rule62)} 名患者。",
        f"- 对比指标统一使用共同患者：{len(common_patient_ids)} 名。",
        f"- 未进入规则62共同集合的 YOLO 患者：{len(missing_in_face)} 名"
        + (f"（{', '.join(missing_in_face)}）。" if missing_in_face else "。"),
        f"- YOLO 图片级标签与患者切分标签不一致：{len(yolo_label_mismatches)} 张；患者级指标统一按 `05_patient_splits.csv` 标签计算。",
        f"- YOLO 图片级 split 与患者切分 split 不一致：{len(yolo_split_mismatches_rows)} 张。",
        "",
        "### YOLO 全量患者标签分布",
        "",
    ]
    if yolo_label_mismatches:
        affected = sorted({row["patient_id"] for row in yolo_label_mismatches}, key=patient_sort_key)
        lines.extend(["", f"标签不一致影响患者：{', '.join(affected)}。", ""])
    lines.extend(
        markdown_table(
            ["split", "patients", "患病", "不患病"],
            [
                [
                    split,
                    sum(yolo_counts.get(split, Counter()).values()),
                    yolo_counts.get(split, Counter()).get("患病", 0),
                    yolo_counts.get(split, Counter()).get("不患病", 0),
                ]
                for split in SPLIT_ORDER
            ],
        )
    )
    lines.extend(["", "### 指标共同患者标签分布", ""])
    lines.extend(
        markdown_table(
            ["split", "patients", "患病", "不患病"],
            [
                [
                    split,
                    sum(common_counts.get(split, Counter()).values()),
                    common_counts.get(split, Counter()).get("患病", 0),
                    common_counts.get(split, Counter()).get("不患病", 0),
                ]
                for split in SPLIT_ORDER
            ],
        )
    )

    if existing_rule62_old_metrics:
        recomputed = lookup[("facesymai_rule62", "combined")]
        lines.extend(
            [
                "",
                "### 规则62交叉验证",
                "",
                "脚本从 `62_stable_weighted_feature_disease_rule_patient_predictions.csv` 逐患者重新计算规则62指标；"
                "与既有 `62_stable_weighted_feature_disease_rule_metrics.csv` 的 `old` 行对照如下。",
                "",
            ]
        )
        lines.extend(
            markdown_table(
                ["metric", "recomputed_old_common", "existing_old"],
                [
                    [metric, recomputed[metric], existing_rule62_old_metrics.get(metric, "")]
                    for metric in ["precision", "recall", "specificity", "f1", "tp", "fp", "tn", "fn"]
                ],
            )
        )

    lines.extend(["", "## YOLO 各聚合规则指标", ""])
    lines.extend(
        markdown_table(
            ["method", "split", "precision", "recall", "specificity", "f1", "accuracy", "TP", "FP", "TN", "FN"],
            [
                [
                    row["method"],
                    row["split"],
                    row["precision"],
                    row["recall"],
                    row["specificity"],
                    row["f1"],
                    row["accuracy"],
                    row["tp"],
                    row["fp"],
                    row["tn"],
                    row["fn"],
                ]
                for row in metric_rows
                if row["method"] in YOLO_RULES
            ],
        )
    )

    lines.extend(["", "## YOLO 最优规则 vs FaceSymAi 规则62", ""])
    lines.append(f"YOLO 展示最优规则按 test split 的 F1 选择；当前为 `{best_rule}`。该选择只用于报告对比，不作为重新调参或部署阈值选择。")
    lines.append("")
    lines.extend(
        markdown_table(
            ["method", "split", "precision", "recall", "specificity", "f1", "accuracy", "TP", "FP", "TN", "FN"],
            [
                [
                    row["method"],
                    row["split"],
                    row["precision"],
                    row["recall"],
                    row["specificity"],
                    row["f1"],
                    row["accuracy"],
                    row["tp"],
                    row["fp"],
                    row["tn"],
                    row["fn"],
                ]
                for method in [best_rule, "facesymai_rule62"]
                for row in [lookup[(method, split)] for split in SPLIT_ORDER]
            ],
        )
    )

    lines.extend(["", "## 初步分析", ""])
    comparisons = [
        f"- test precision：{compare_metric_value(best_test, face_test, 'precision')}（{best_rule}={best_test['precision']}，facesymai_rule62={face_test['precision']}）。",
        f"- test recall：{compare_metric_value(best_test, face_test, 'recall')}（{best_rule}={best_test['recall']}，facesymai_rule62={face_test['recall']}）。",
        f"- test specificity：{compare_metric_value(best_test, face_test, 'specificity')}（{best_rule}={best_test['specificity']}，facesymai_rule62={face_test['specificity']}）。",
        f"- test f1：{compare_metric_value(best_test, face_test, 'f1')}（{best_rule}={best_test['f1']}，facesymai_rule62={face_test['f1']}）。",
        f"- test accuracy：{compare_metric_value(best_test, face_test, 'accuracy')}（{best_rule}={best_test['accuracy']}，facesymai_rule62={face_test['accuracy']}）。",
    ]
    lines.extend(comparisons)
    lines.extend(
        [
            "",
            "- YOLO 的 `any` 与 `majority` 类规则只要图片中出现 stroke 类检测就容易判阳性，覆盖面宽，通常换来更高 recall，但会把较多不患病患者推成阳性，specificity 和 precision 受影响。",
            "- FaceSymAi 规则62 使用 21 个稳定性加权 MediaPipe 特征和固定加权阈值，阳性更保守，因此更偏向 precision/specificity；代价是 recall 较低。",
            "- 本对比仍使用 patient outcome 弱标签，只能解释为技术信号对比，不能表述为临床诊断性能。",
        ]
    )
    return lines


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    yolo_rows = read_csv(args.yolo_predictions)
    split_by_patient_id = load_split_rows(args.splits)
    yolo_label_mismatches, yolo_split_mismatches_rows = yolo_split_mismatches(yolo_rows, split_by_patient_id)
    yolo_patient_rows = build_yolo_patient_predictions(yolo_rows, split_by_patient_id)
    yolo_by_patient_id = {row["patient_id"]: row for row in yolo_patient_rows}
    face_rule62 = load_facesymai_rule62_predictions(args.facesymai_rule62_predictions, split_by_patient_id)

    common_patient_ids = sorted(
        set(yolo_by_patient_id).intersection(face_rule62),
        key=patient_sort_key,
    )
    missing_in_face = sorted(
        set(yolo_by_patient_id).difference(face_rule62),
        key=patient_sort_key,
    )
    if not common_patient_ids:
        raise ValueError("No common patients between YOLO predictions and FaceSymAi rule62 predictions")

    for patient_id in common_patient_ids:
        yolo_row = yolo_by_patient_id[patient_id]
        face_row = face_rule62[patient_id]
        if label_to_binary(yolo_row["patient_label"]) != int(face_row["label_binary"]):
            raise ValueError(f"Label mismatch between YOLO and FaceSymAi rule62 for patient {patient_id}")
        if yolo_row["split"] != face_row["split"]:
            raise ValueError(f"Split mismatch between YOLO and FaceSymAi rule62 for patient {patient_id}")

    metric_rows = build_metric_rows(yolo_by_patient_id, face_rule62, common_patient_ids)
    existing_rule62_old_metrics = read_existing_rule62_old_metrics(args.facesymai_rule62_metrics)
    report_lines = build_report(
        args=args,
        yolo_image_rows=yolo_rows,
        yolo_patient_rows=yolo_patient_rows,
        face_rule62=face_rule62,
        common_patient_ids=common_patient_ids,
        missing_in_face=missing_in_face,
        yolo_label_mismatches=yolo_label_mismatches,
        yolo_split_mismatches_rows=yolo_split_mismatches_rows,
        metric_rows=metric_rows,
        existing_rule62_old_metrics=existing_rule62_old_metrics,
    )

    yolo_patient_path = args.output_dir / "yolo_patient_predictions.csv"
    metrics_path = args.output_dir / "comparison_metrics.csv"
    report_path = args.output_dir / "comparison_report.md"
    write_csv(yolo_patient_path, yolo_patient_rows, YOLO_PATIENT_FIELDS)
    write_csv(metrics_path, metric_rows, METRIC_FIELDS)
    write_markdown(report_path, report_lines)

    print(f"Wrote {yolo_patient_path}")
    print(f"Wrote {metrics_path}")
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
