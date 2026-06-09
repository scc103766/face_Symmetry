#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

COMPONENT_WEIGHTS = {
    "resting_symmetry_score": 0.18,
    "eye_closure_score": 0.16,
    "brow_forehead_score": 0.18,
    "smile_mouth_score": 0.24,
    "gross_asymmetry_score": 0.16,
    "movement_absence_score": 0.08,
}
COMPONENT_LABELS = {
    "resting_symmetry_score": "静息对称性",
    "eye_closure_score": "闭眼完整性/眼裂对称",
    "brow_forehead_score": "眉额/皱眉动态",
    "smile_mouth_score": "微笑/示齿口部动态",
    "gross_asymmetry_score": "整体不对称",
    "movement_absence_score": "无运动风险",
}
CORE_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
POSITIVE_LABELS = {"1", "true", "yes", "y", "是", "有", "阳性", "不对称", "asymmetry", "positive"}
NEGATIVE_LABELS = {"0", "false", "no", "n", "否", "无", "阴性", "对称", "normal", "negative"}
BAD_QUALITY_LABELS = {"0", "false", "no", "n", "否", "reject", "rejected", "不可用", "排除", "不合格"}
GOOD_QUALITY_LABELS = {"1", "true", "yes", "y", "是", "pass", "passed", "可用", "合格"}
LABEL_COLUMNS = (
    "manual_face_asymmetry_label",
    "review_face_asymmetry_label",
    "face_asymmetry_manual_label",
    "quality_gate_face_asymmetry_label",
)


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    patient_rows = read_csv(required(metadata / "12_v11_hb_proxy_patient_grades.csv"))
    keypoint_rows = read_csv(required(metadata / "03_keypoints.csv"))
    annotation_paths = annotation_paths_by_patient(keypoint_rows)

    template_rows = build_label_template(patient_rows, annotation_paths)
    label_rows = read_csv(args.labels.resolve()) if args.labels and args.labels.exists() else []
    labeled = load_review_labels(label_rows, patient_rows)
    calibration = calibrate_from_labels(patient_rows, labeled)
    prediction_rows = build_prediction_rows(patient_rows, labeled, calibration)
    summary = build_summary(template_rows, labeled, calibration, args.labels)

    write_csv(metadata / "16_v11_face_asymmetry_review_label_template.csv", template_rows)
    write_csv(metadata / "16_v11_face_asymmetry_calibrated_predictions.csv", prediction_rows)
    write_json(metadata / "16_v11_face_asymmetry_calibration_summary.json", summary)
    if calibration["status"] == "calibrated":
        write_json(metadata / "16_v11_face_asymmetry_calibration_config.json", calibration["config"])
    write_report(reports / "18_v11_face_asymmetry_review_label_calibration.md", summary, calibration)

    print(f"Wrote {metadata / '16_v11_face_asymmetry_review_label_template.csv'}")
    print(f"Wrote {metadata / '16_v11_face_asymmetry_calibrated_predictions.csv'}")
    print(f"Wrote {metadata / '16_v11_face_asymmetry_calibration_summary.json'}")
    if calibration["status"] == "calibrated":
        print(f"Wrote {metadata / '16_v11_face_asymmetry_calibration_config.json'}")
    print(f"Wrote {reports / '18_v11_face_asymmetry_review_label_calibration.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate V1.1 face asymmetry thresholds and weights from review labels.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing V1.1 metadata.")
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_DATASET / "metadata" / "16_v11_face_asymmetry_review_labels.csv",
        help="Filled manual/review label CSV. If missing, only the label template is generated.",
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
    fields = sorted({key for row in rows for key in row})
    preferred = [
        "patient_sample_id",
        "split",
        "label_group",
        "label_binary",
        "hb_proxy_grade",
        "hb_proxy_grade_num",
        "face_asymmetry_output",
        "manual_face_asymmetry_label",
        "manual_asymmetry_grade",
        "quality_review_usable_for_calibration",
        "quality_review_label",
        "review_source",
        "reviewer_id",
        "review_date",
        "review_notes",
        "review_priority",
        "review_instruction",
    ]
    fields = [field for field in preferred if field in fields] + [field for field in fields if field not in preferred]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def annotation_paths_by_patient(rows: list[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    output: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        role = row.get("media_role", "")
        if role in CORE_ROLES and row.get("annotation_path"):
            output[row["patient_sample_id"]][role] = row["annotation_path"]
    return output


def build_label_template(
    patient_rows: list[Mapping[str, str]],
    annotation_paths: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in patient_rows:
        patient_id = row["patient_sample_id"]
        role_paths = annotation_paths.get(patient_id, {})
        rows.append(
            {
                "patient_sample_id": patient_id,
                "split": row.get("split", ""),
                "label_group": row.get("label_group", ""),
                "label_binary": row.get("label_binary", ""),
                "hb_proxy_grade": row.get("hb_proxy_grade", ""),
                "hb_proxy_grade_num": row.get("hb_proxy_grade_num", ""),
                "hb_grade_confidence": row.get("hb_grade_confidence", ""),
                "face_asymmetry_output": row.get("face_asymmetry_output", ""),
                "manual_face_asymmetry_label": "",
                "manual_asymmetry_grade": "",
                "quality_review_usable_for_calibration": "",
                "quality_review_label": "",
                "review_source": "",
                "reviewer_id": "",
                "review_date": "",
                "review_notes": "",
                "review_priority": review_priority(row),
                "review_instruction": "填 manual_face_asymmetry_label: 1=人工确认人脸不对称, 0=人工确认未见明显不对称；若图片质量不可用，填 quality_review_usable_for_calibration=0。",
                "resting_symmetry_score": row.get("resting_symmetry_score", ""),
                "eye_closure_score": row.get("eye_closure_score", ""),
                "brow_forehead_score": row.get("brow_forehead_score", ""),
                "smile_mouth_score": row.get("smile_mouth_score", ""),
                "gross_asymmetry_score": row.get("gross_asymmetry_score", ""),
                "movement_absence_score": row.get("movement_absence_score", ""),
                "hb_proxy_overall_score": row.get("hb_proxy_overall_score", ""),
                "face_asymmetry_reason": row.get("face_asymmetry_reason", ""),
                "hb_reason_codes": row.get("hb_reason_codes", ""),
                "core_role_annotation_paths": ";".join(role_paths.get(role, "") for role in CORE_ROLES),
                "front_annotation_path": role_paths.get("front", ""),
                "smile_annotation_path": role_paths.get("smile", ""),
                "teeth_annotation_path": role_paths.get("teeth", ""),
                "eyes_closed_annotation_path": role_paths.get("eyes_closed", ""),
                "forehead_wrinkle_annotation_path": role_paths.get("forehead_wrinkle", ""),
                "frown_annotation_path": role_paths.get("frown", ""),
            }
        )
    return sorted(rows, key=lambda item: (priority_rank(item["review_priority"]), item["split"], item["label_group"], item["patient_sample_id"]))


def review_priority(row: Mapping[str, str]) -> str:
    grade = parse_int(row.get("hb_proxy_grade_num"))
    if row.get("label_binary") == "0" and grade is not None and grade >= 5:
        return "p0_grade_v_plus_nondisease_false_positive_review"
    if row.get("label_binary") == "1" and grade is not None and grade <= 2:
        return "p1_diseased_low_grade_review"
    if grade is not None and grade >= 5:
        return "p1_grade_v_plus_positive_review"
    if row.get("hb_needs_manual_review") == "1":
        return "p2_existing_manual_review_candidate"
    return "p3_stratified_calibration_background"


def priority_rank(priority: str) -> int:
    if priority.startswith("p0"):
        return 0
    if priority.startswith("p1"):
        return 1
    if priority.startswith("p2"):
        return 2
    return 3


def load_review_labels(
    label_rows: list[Mapping[str, str]],
    patient_rows: list[Mapping[str, str]],
) -> dict[str, dict[str, Any]]:
    patient_ids = {row["patient_sample_id"] for row in patient_rows}
    labeled: dict[str, dict[str, Any]] = {}
    for row in label_rows:
        patient_id = row.get("patient_sample_id", "")
        if patient_id not in patient_ids:
            continue
        label = parse_label_value(next((row.get(column, "") for column in LABEL_COLUMNS if row.get(column, "")), ""))
        if label is None:
            continue
        usable = parse_quality_usable(row)
        if usable is False:
            continue
        labeled[patient_id] = {
            "manual_face_asymmetry_label": label,
            "manual_asymmetry_grade": parse_int(row.get("manual_asymmetry_grade")),
            "quality_review_usable_for_calibration": "" if usable is None else int(usable),
            "quality_review_label": row.get("quality_review_label", ""),
            "review_source": row.get("review_source", ""),
            "reviewer_id": row.get("reviewer_id", ""),
            "review_date": row.get("review_date", ""),
            "review_notes": row.get("review_notes", ""),
        }
    return labeled


def parse_label_value(value: Any) -> int | None:
    normalized = str(value).strip().lower()
    if normalized in POSITIVE_LABELS:
        return 1
    if normalized in NEGATIVE_LABELS:
        return 0
    return None


def parse_quality_usable(row: Mapping[str, str]) -> bool | None:
    explicit = str(row.get("quality_review_usable_for_calibration", "")).strip().lower()
    if explicit in GOOD_QUALITY_LABELS:
        return True
    if explicit in BAD_QUALITY_LABELS:
        return False
    quality_label = str(row.get("quality_review_label", "")).strip().lower()
    if quality_label in BAD_QUALITY_LABELS:
        return False
    if quality_label in GOOD_QUALITY_LABELS:
        return True
    return None


def calibrate_from_labels(
    patient_rows: list[Mapping[str, str]],
    labeled: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [row for row in patient_rows if row["patient_sample_id"] in labeled]
    positives = sum(1 for row in rows if labeled[row["patient_sample_id"]]["manual_face_asymmetry_label"] == 1)
    negatives = sum(1 for row in rows if labeled[row["patient_sample_id"]]["manual_face_asymmetry_label"] == 0)
    if len(rows) < 10 or positives < 3 or negatives < 3:
        return {
            "status": "insufficient_labels",
            "labeled_patients": len(rows),
            "positive_labels": positives,
            "negative_labels": negatives,
            "minimum_required": {"labeled_patients": 10, "positive_labels": 3, "negative_labels": 3},
            "metrics": {},
            "config": {},
        }

    train_val = [row for row in rows if row.get("split") in {"train", "val"}]
    if not has_both_classes(train_val, labeled):
        train_val = rows
    best = best_weight_threshold(train_val, labeled)
    if best is None:
        return {
            "status": "insufficient_scores",
            "labeled_patients": len(rows),
            "positive_labels": positives,
            "negative_labels": negatives,
            "metrics": {},
            "config": {},
        }
    weights, threshold = best["weights"], best["threshold"]
    metrics = {
        split: binary_metrics(split_rows(rows, split), labeled, lambda row: calibrated_score(row, weights) >= threshold)
        for split in ("train", "val", "test", "train_val", "all_labeled")
    }
    baseline = {
        split: binary_metrics(split_rows(rows, split), labeled, current_grade_v_plus_prediction)
        for split in ("train", "val", "test", "train_val", "all_labeled")
    }
    return {
        "status": "calibrated",
        "labeled_patients": len(rows),
        "positive_labels": positives,
        "negative_labels": negatives,
        "selected_on": "train+val if both classes are available, otherwise all labeled rows",
        "config": {
            "version": "v11_face_asymmetry_review_label_calibration",
            "component_weights": weights,
            "binary_threshold": threshold,
            "label_source_columns": LABEL_COLUMNS,
            "prediction_rule": "calibrated_score >= binary_threshold",
        },
        "metrics": {
            "current_grade_v_plus": {split: format_metrics(payload) for split, payload in baseline.items()},
            "calibrated": {split: format_metrics(payload) for split, payload in metrics.items()},
        },
    }


def best_weight_threshold(
    rows: list[Mapping[str, str]],
    labeled: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for weights in candidate_weights():
        scored = [(row, calibrated_score(row, weights)) for row in rows]
        thresholds = sorted({score for _row, score in scored})
        for threshold in thresholds:
            metrics = binary_metrics(rows, labeled, lambda row, weights=weights, threshold=threshold: calibrated_score(row, weights) >= threshold)
            score = (metrics["balanced_accuracy"], metrics["precision"], metrics["recall"], -metrics["predicted_positive"])
            if best is None or score > best["score"]:
                best = {"score": score, "weights": weights, "threshold": threshold, "metrics": metrics}
    return best


def candidate_weights() -> list[dict[str, float]]:
    candidates: list[dict[str, float]] = [normalize_weights(COMPONENT_WEIGHTS)]
    multipliers = (0.5, 0.75, 1.25, 1.5, 2.0)
    for component in COMPONENT_WEIGHTS:
        for multiplier in multipliers:
            weights = dict(COMPONENT_WEIGHTS)
            weights[component] *= multiplier
            candidates.append(normalize_weights(weights))
    pairs = [
        ("eye_closure_score", "brow_forehead_score"),
        ("smile_mouth_score", "gross_asymmetry_score"),
        ("resting_symmetry_score", "gross_asymmetry_score"),
        ("eye_closure_score", "smile_mouth_score"),
        ("brow_forehead_score", "smile_mouth_score"),
    ]
    for left, right in pairs:
        weights = dict(COMPONENT_WEIGHTS)
        weights[left] *= 1.5
        weights[right] *= 1.5
        candidates.append(normalize_weights(weights))
    unique: dict[tuple[tuple[str, float], ...], dict[str, float]] = {}
    for weights in candidates:
        key = tuple(sorted((component, round(weight, 6)) for component, weight in weights.items()))
        unique[key] = weights
    return list(unique.values())


def normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    return {component: weight / total for component, weight in weights.items()}


def calibrated_score(row: Mapping[str, str], weights: Mapping[str, float]) -> float:
    weighted = 0.0
    total = 0.0
    for component, weight in weights.items():
        value = parse_float(row.get(component))
        if value is None:
            continue
        weighted += value * weight
        total += weight
    return weighted / total if total else 0.0


def current_grade_v_plus_prediction(row: Mapping[str, str]) -> bool:
    grade = parse_int(row.get("hb_proxy_grade_num"))
    return grade is not None and grade >= 5


def has_both_classes(rows: list[Mapping[str, str]], labeled: Mapping[str, Mapping[str, Any]]) -> bool:
    labels = {labeled[row["patient_sample_id"]]["manual_face_asymmetry_label"] for row in rows}
    return labels == {0, 1}


def split_rows(rows: list[Mapping[str, str]], split: str) -> list[Mapping[str, str]]:
    if split == "all_labeled":
        return rows
    if split == "train_val":
        return [row for row in rows if row.get("split") in {"train", "val"}]
    return [row for row in rows if row.get("split") == split]


def binary_metrics(
    rows: list[Mapping[str, str]],
    labeled: Mapping[str, Mapping[str, Any]],
    predicate: Callable[[Mapping[str, str]], bool],
) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for row in rows:
        truth = labeled[row["patient_sample_id"]]["manual_face_asymmetry_label"]
        pred = predicate(row)
        if truth == 1 and pred:
            tp += 1
        elif truth == 0 and pred:
            fp += 1
        elif truth == 0 and not pred:
            tn += 1
        elif truth == 1 and not pred:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    accuracy = (tp + tn) / len(rows) if rows else 0.0
    return {
        "patients": len(rows),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "predicted_positive": tp + fp,
        "accuracy": accuracy,
        "balanced_accuracy": (recall + specificity) / 2.0,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
    }


def format_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "patients": metrics["patients"],
        "predicted_positive": metrics["predicted_positive"],
        "tp": metrics["tp"],
        "fp": metrics["fp"],
        "tn": metrics["tn"],
        "fn": metrics["fn"],
        "accuracy": fmt(metrics["accuracy"]),
        "balanced_accuracy": fmt(metrics["balanced_accuracy"]),
        "precision": fmt(metrics["precision"]),
        "recall": fmt(metrics["recall"]),
        "specificity": fmt(metrics["specificity"]),
    }


def build_prediction_rows(
    patient_rows: list[Mapping[str, str]],
    labeled: Mapping[str, Mapping[str, Any]],
    calibration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    weights = calibration.get("config", {}).get("component_weights") or normalize_weights(COMPONENT_WEIGHTS)
    threshold = parse_float(calibration.get("config", {}).get("binary_threshold"))
    rows: list[dict[str, Any]] = []
    for row in patient_rows:
        patient_id = row["patient_sample_id"]
        score = calibrated_score(row, weights)
        pred = int(threshold is not None and score >= threshold)
        label_payload = labeled.get(patient_id, {})
        rows.append(
            {
                "patient_sample_id": patient_id,
                "split": row.get("split", ""),
                "label_group": row.get("label_group", ""),
                "label_binary": row.get("label_binary", ""),
                "manual_face_asymmetry_label": label_payload.get("manual_face_asymmetry_label", ""),
                "manual_asymmetry_grade": label_payload.get("manual_asymmetry_grade", ""),
                "quality_review_usable_for_calibration": label_payload.get("quality_review_usable_for_calibration", ""),
                "hb_proxy_grade": row.get("hb_proxy_grade", ""),
                "hb_proxy_grade_num": row.get("hb_proxy_grade_num", ""),
                "face_asymmetry_output": row.get("face_asymmetry_output", ""),
                "current_grade_v_plus_prediction": int(current_grade_v_plus_prediction(row)),
                "calibrated_face_asymmetry_score": fmt(score),
                "calibrated_face_asymmetry_prediction": pred if threshold is not None else "",
                "calibrated_threshold": fmt_optional(threshold),
                "calibration_status": calibration["status"],
            }
        )
    return rows


def build_summary(
    template_rows: list[Mapping[str, Any]],
    labeled: Mapping[str, Mapping[str, Any]],
    calibration: Mapping[str, Any],
    label_path: Path | None,
) -> dict[str, Any]:
    label_counts = Counter(payload["manual_face_asymmetry_label"] for payload in labeled.values())
    return {
        "status": calibration["status"],
        "label_file": label_path.as_posix() if label_path else "",
        "template_output": "metadata/16_v11_face_asymmetry_review_label_template.csv",
        "template_rows": len(template_rows),
        "labeled_patients": len(labeled),
        "label_counts": {str(key): value for key, value in sorted(label_counts.items())},
        "review_priority_distribution": dict(Counter(row["review_priority"] for row in template_rows)),
        "calibration": calibration,
        "instructions": [
            "Fill manual_face_asymmetry_label with 1 for confirmed face asymmetry and 0 for confirmed no obvious asymmetry.",
            "Fill quality_review_usable_for_calibration=0 for images that should be excluded from calibration because of quality, pose, occlusion, or failed review.",
            "Re-run this script with --labels pointing to the filled CSV to recalibrate component weights and binary threshold.",
        ],
    }


def write_report(path: Path, summary: Mapping[str, Any], calibration: Mapping[str, Any]) -> None:
    lines = [
        "# 18 V1.1 Face Asymmetry Review Label Calibration",
        "",
        "## 结论",
        "",
    ]
    if calibration["status"] == "calibrated":
        lines.extend(
            [
                "已读取人工/复核标签，并生成基于标签的组件权重和二分类阈值校准配置。",
                "",
                f"- 有效标签数：`{summary['labeled_patients']}`",
                f"- 标签分布：`{json.dumps(summary['label_counts'], ensure_ascii=False, sort_keys=True)}`",
                "- 校准配置：`metadata/16_v11_face_asymmetry_calibration_config.json`",
                "- 校准预测：`metadata/16_v11_face_asymmetry_calibrated_predictions.csv`",
                "",
                "## 校准权重",
                "",
                "| component | weight |",
                "| --- | ---: |",
            ]
        )
        for component, weight in calibration["config"]["component_weights"].items():
            lines.append(f"| {COMPONENT_LABELS[component]} | {weight:.6f} |")
        lines.extend(
            [
                "",
                f"- Binary threshold：`{calibration['config']['binary_threshold']:.6f}`",
                "",
                "## 指标对比",
                "",
                "| model | split | precision | recall | specificity | balanced_accuracy | TP | FP | TN | FN |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for model_name in ("current_grade_v_plus", "calibrated"):
            for split, metrics in calibration["metrics"][model_name].items():
                lines.append(
                    f"| {model_name} | {split} | {metrics['precision']} | {metrics['recall']} | {metrics['specificity']} | {metrics['balanced_accuracy']} | {metrics['tp']} | {metrics['fp']} | {metrics['tn']} | {metrics['fn']} |"
                )
    else:
        lines.extend(
            [
                "当前还没有足够的人工面部不对称标签或质量复核标签，未执行阈值/权重重校准。",
                "",
                f"- 标签文件：`{summary['label_file']}`",
                f"- 有效标签数：`{summary['labeled_patients']}`",
                f"- 标签分布：`{json.dumps(summary['label_counts'], ensure_ascii=False, sort_keys=True)}`",
                f"- 标注模板：`{summary['template_output']}`",
                f"- 模板行数：`{summary['template_rows']}`",
                "",
                "## 标注方式",
                "",
                "1. 打开 `metadata/16_v11_face_asymmetry_review_label_template.csv`。",
                "2. 对每个患者查看 6 个核心 role 的特征点图路径。",
                "3. 填写 `manual_face_asymmetry_label`：`1` 表示人工确认人脸不对称，`0` 表示人工确认未见明显不对称。",
                "4. 如果图片质量、姿态、遮挡或配合问题导致不可判定，填写 `quality_review_usable_for_calibration=0`。",
                "5. 将填好的文件保存为 `metadata/16_v11_face_asymmetry_review_labels.csv`，重新运行本脚本。",
            ]
        )
    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- 校准标签应是人工面部不对称或质量门控后的复核标签，不应继续使用 patient outcome 直接替代。",
            "- 标注量不足或单一类别标签不足时不会更新规则。",
            "- 生成的校准配置需要通过冻结测试集和人工审核后，再决定是否接入主分级脚本。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_int(value: Any) -> int | None:
    parsed = parse_float(value)
    return int(parsed) if parsed is not None else None


def fmt(value: float) -> str:
    return f"{value:.6f}"


def fmt_optional(value: Any) -> str:
    parsed = parse_float(value)
    return "" if parsed is None else fmt(parsed)


if __name__ == "__main__":
    main()
