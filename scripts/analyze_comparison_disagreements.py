#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / "tmp" / "matplotlib"))

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "yolo_comparison_20260608"
DEFAULT_YOLO_PER_IMAGE = DEFAULT_OUTPUT_DIR / "yolo_per_image_predictions.csv"
DEFAULT_YOLO_PATIENTS = DEFAULT_OUTPUT_DIR / "yolo_patient_predictions.csv"
DEFAULT_COMPARISON_METRICS = DEFAULT_OUTPUT_DIR / "comparison_metrics.csv"
DEFAULT_FACE_RULE62_PATIENTS = (
    PROJECT_ROOT
    / "datasets"
    / "combined_disease_feature_candidates_20260529"
    / "metadata"
    / "62_stable_weighted_feature_disease_rule_patient_predictions.csv"
)
DEFAULT_FACE_RULE62_CONTRIBUTIONS = (
    PROJECT_ROOT
    / "datasets"
    / "combined_disease_feature_candidates_20260529"
    / "metadata"
    / "62_stable_weighted_feature_disease_rule_patient_feature_contributions.csv"
)
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119"
DEFAULT_SPLITS = DEFAULT_DATASET / "metadata" / "05_patient_splits.csv"
DEFAULT_MANIFEST = DEFAULT_DATASET / "metadata" / "01_manifest.csv"
DEFAULT_KEYPOINTS = DEFAULT_DATASET / "metadata" / "03_keypoints.csv"
DEFAULT_QUALITY_GATE = DEFAULT_DATASET / "metadata" / "02_quality_gate.csv"
DEFAULT_YOLO_MODEL = PROJECT_ROOT / "third_party" / "stroke_detection_yolo" / "best.pt"

YOLO_RULES = [
    "yolo_any_stroke_eye",
    "yolo_any_stroke_mouth",
    "yolo_any_stroke",
    "yolo_stroke_severe",
    "yolo_majority_stroke",
]
SPLIT_ORDER = ["train", "val", "test", "combined"]
ROLE_ORDER = ["front", "smile", "teeth"]
DISAGREEMENT_ORDER = [
    "yolo_fp_facesymai_tn",
    "yolo_fn_facesymai_tp",
    "yolo_tp_facesymai_fn",
    "yolo_tn_facesymai_fp",
]

DISAGREEMENT_FIELDS = [
    "patient_id",
    "patient_label",
    "split",
    "yolo_prediction",
    "facesymai_prediction",
    "disagreement_type",
    "analysis_reason",
    "analysis_reason_category",
    "yolo_rule",
    "yolo_image_count",
    "yolo_success_image_count",
    "yolo_error_image_count",
    "yolo_stroke_image_count",
    "yolo_stroke_eye_image_count",
    "yolo_stroke_mouth_image_count",
    "yolo_stroke_image_ratio",
    "yolo_detected_classes",
    "facesymai_weighted_disease_score",
    "facesymai_score_threshold",
    "facesymai_triggered_feature_count",
    "facesymai_triggered_weight",
    "facesymai_top_triggered_features",
    "quality_summary",
    "visualization_path",
]

VISUALIZATION_INDEX_FIELDS = [
    "patient_id",
    "patient_label",
    "split",
    "disagreement_type",
    "visualization_path",
    "roles_rendered",
    "note",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze qualitative disagreements between YOLO best patient rule and FaceSymAi rule 62."
    )
    parser.add_argument("--yolo-per-image", type=Path, default=DEFAULT_YOLO_PER_IMAGE)
    parser.add_argument("--yolo-patients", type=Path, default=DEFAULT_YOLO_PATIENTS)
    parser.add_argument("--comparison-metrics", type=Path, default=DEFAULT_COMPARISON_METRICS)
    parser.add_argument("--facesymai-rule62-patients", type=Path, default=DEFAULT_FACE_RULE62_PATIENTS)
    parser.add_argument("--facesymai-rule62-contributions", type=Path, default=DEFAULT_FACE_RULE62_CONTRIBUTIONS)
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--keypoints", type=Path, default=DEFAULT_KEYPOINTS)
    parser.add_argument("--quality-gate", type=Path, default=DEFAULT_QUALITY_GATE)
    parser.add_argument("--yolo-model", type=Path, default=DEFAULT_YOLO_MODEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--yolo-rule", default="", help="Override YOLO patient rule. Defaults to test-F1 best rule.")
    parser.add_argument("--sample-patients", type=int, default=20)
    parser.add_argument("--yolo-conf", type=float, default=0.25)
    parser.add_argument("--yolo-device", default="cpu")
    parser.add_argument(
        "--skip-yolo-rerun",
        action="store_true",
        help="Do not rerun YOLO for visualization bboxes; use class/conf labels from CSV only.",
    )
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


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def fmt_float(value: Any, digits: int = 6) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return ""


def patient_sort_key(value: str) -> tuple[int, Any]:
    return (0, int(value)) if str(value).isdigit() else (1, value)


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def label_to_binary(label: str) -> int:
    if label == "患病":
        return 1
    if label == "不患病":
        return 0
    raise ValueError(f"Unexpected patient label: {label!r}")


def binary_prediction_label(value: bool) -> str:
    return "患病倾向较高" if value else "未达到患病阈值"


def label_for_visual(value: str) -> str:
    return {"患病": "disease", "不患病": "non-disease"}.get(value, value)


def prediction_for_visual(value: str) -> str:
    return "positive" if value == "患病倾向较高" else "negative"


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return output


def metric_lookup(rows: Iterable[Mapping[str, str]]) -> dict[tuple[str, str], Mapping[str, str]]:
    return {(row["method"], row["split"]): row for row in rows}


def select_yolo_rule(metric_rows: list[Mapping[str, str]], override: str) -> str:
    if override:
        if override not in YOLO_RULES:
            raise ValueError(f"Unknown YOLO rule: {override}")
        return override
    test_rows = [row for row in metric_rows if row.get("split") == "test" and row.get("method") in YOLO_RULES]
    if not test_rows:
        raise ValueError("comparison_metrics.csv does not contain YOLO test rows")
    return max(
        test_rows,
        key=lambda row: (
            float(row.get("f1", 0) or 0),
            float(row.get("precision", 0) or 0),
            float(row.get("specificity", 0) or 0),
            float(row.get("recall", 0) or 0),
            row.get("method", ""),
        ),
    )["method"]


def load_split_map(path: Path) -> dict[str, dict[str, str]]:
    return {row["patient_id"]: row for row in read_csv(path) if row.get("patient_id")}


def load_yolo_patients(path: Path) -> dict[str, dict[str, str]]:
    return {row["patient_id"]: row for row in read_csv(path) if row.get("patient_id")}


def load_yolo_images(path: Path) -> dict[str, list[dict[str, str]]]:
    rows_by_patient: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(path):
        patient_id = row.get("patient_id", "")
        if patient_id:
            rows_by_patient[patient_id].append(row)
    for rows in rows_by_patient.values():
        rows.sort(key=lambda item: (ROLE_ORDER.index(item["role"]) if item.get("role") in ROLE_ORDER else 99, item.get("image_path", "")))
    return rows_by_patient


def extract_old_patient_id(source_patient_sample_id: str) -> str:
    match = re.search(r"pid(\d+)", source_patient_sample_id)
    if not match:
        raise ValueError(f"Cannot extract patient_id from {source_patient_sample_id!r}")
    return match.group(1)


def load_facesymai_rule62(path: Path, split_by_patient_id: Mapping[str, Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in read_csv(path):
        if row.get("source_dataset") != "old":
            continue
        patient_id = extract_old_patient_id(row.get("source_patient_sample_id", ""))
        split_row = split_by_patient_id.get(patient_id)
        if not split_row:
            continue
        if row.get("label_group") != split_row.get("label_group"):
            raise ValueError(
                f"FaceSymAi label mismatch for patient {patient_id}: "
                f"{row.get('label_group')} vs {split_row.get('label_group')}"
            )
        output[patient_id] = {
            **row,
            "patient_id": patient_id,
            "split": split_row.get("split", ""),
            "predicted": str(row.get("predicted_label_binary", "")).strip() == "1",
        }
    return output


def load_facesymai_contributions(path: Path) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in read_csv(path):
        if row.get("source_dataset") != "old":
            continue
        patient_id = extract_old_patient_id(row.get("source_patient_sample_id", ""))
        output[patient_id].append(row)
    for rows in output.values():
        rows.sort(
            key=lambda item: (
                parse_bool(item.get("triggered", "")),
                float(item.get("weighted_contribution", 0) or 0),
            ),
            reverse=True,
        )
    return output


def load_annotation_map(manifest_path: Path, keypoints_path: Path, dataset_root: Path) -> dict[str, str]:
    keypoint_by_sample = {row.get("sample_id", ""): row for row in read_csv(keypoints_path)}
    annotation_by_image: dict[str, str] = {}
    for row in read_csv(manifest_path):
        sample_id = row.get("sample_id", "")
        image_path = row.get("organized_path") or row.get("source_media_path", "")
        keypoint_row = keypoint_by_sample.get(sample_id)
        annotation_path = keypoint_row.get("annotation_path", "") if keypoint_row else ""
        if image_path and annotation_path:
            annotation_by_image[Path(image_path).resolve().as_posix()] = (dataset_root / annotation_path).resolve().as_posix()
    return annotation_by_image


def load_quality_summary(path: Path) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = defaultdict(lambda: {"counts": Counter(), "reasons": Counter(), "accepted": 0, "total": 0})
    for row in read_csv(path):
        patient_id = extract_old_patient_id(row.get("patient_sample_id", ""))
        summary = summaries[patient_id]
        summary["total"] += 1
        summary["counts"].update([row.get("quality_level", "unknown") or "unknown"])
        if parse_bool(row.get("accepted_for_scoring", "")):
            summary["accepted"] += 1
        reason_codes = [item for item in row.get("reason_codes", "").split("|") if item]
        summary["reasons"].update(reason_codes)
    return summaries


def compact_counter(counter: Counter[str]) -> str:
    return ";".join(f"{key}:{value}" for key, value in sorted(counter.items())) if counter else "none"


def quality_text(summary: Mapping[str, Any] | None) -> str:
    if not summary:
        return "quality_unknown"
    return (
        f"accepted {summary.get('accepted', 0)}/{summary.get('total', 0)}; "
        f"levels={compact_counter(summary.get('counts', Counter()))}; "
        f"reasons={compact_counter(summary.get('reasons', Counter()))}"
    )


def top_triggered_features(contributions: Iterable[Mapping[str, str]], limit: int = 3) -> str:
    triggered = [row for row in contributions if parse_bool(row.get("triggered", ""))]
    parts = []
    for row in triggered[:limit]:
        feature = row.get("feature_name", "")
        value = fmt_float(row.get("feature_value"))
        threshold = fmt_float(row.get("threshold"))
        contribution = fmt_float(row.get("weighted_contribution"))
        parts.append(f"{feature}={value}>={threshold} contrib={contribution}")
    return "; ".join(parts) if parts else "none"


def disagreement_type(yolo_pred: bool, facesym_pred: bool, patient_label: str) -> str:
    if yolo_pred and not facesym_pred and patient_label == "不患病":
        return "yolo_fp_facesymai_tn"
    if not yolo_pred and facesym_pred and patient_label == "患病":
        return "yolo_fn_facesymai_tp"
    if yolo_pred and not facesym_pred and patient_label == "患病":
        return "yolo_tp_facesymai_fn"
    if not yolo_pred and facesym_pred and patient_label == "不患病":
        return "yolo_tn_facesymai_fp"
    raise ValueError("Predictions are not a disagreement or label is invalid")


def reason_category(
    dtype: str,
    yolo_row: Mapping[str, str],
    face_row: Mapping[str, Any],
    quality_summary_row: Mapping[str, Any] | None,
) -> str:
    categories: list[str] = []
    if dtype == "yolo_fp_facesymai_tn":
        categories.append("YOLO过敏感/自然不对称误报")
    elif dtype == "yolo_fn_facesymai_tp":
        categories.append("YOLO漏检/类别覆盖不足")
    elif dtype == "yolo_tp_facesymai_fn":
        categories.append("FaceSymAi规则62保守漏判")
    elif dtype == "yolo_tn_facesymai_fp":
        categories.append("FaceSymAi几何特征过敏感")

    if int(yolo_row.get("yolo_error_image_count", "0") or 0) > 0:
        categories.append("YOLO图片读取失败影响")
    if int(yolo_row.get("yolo_stroke_mouth_image_count", "0") or 0) > 0:
        categories.append("YOLO口部stroke类触发")
    elif int(yolo_row.get("yolo_stroke_eye_image_count", "0") or 0) > 0:
        categories.append("YOLO眼部stroke类触发")
    if quality_summary_row and int(quality_summary_row.get("accepted", 0)) < int(quality_summary_row.get("total", 0)):
        categories.append("图片质量/门控问题")
    if float(face_row.get("weighted_disease_score", 0) or 0) < float(face_row.get("score_threshold", 0) or 0):
        categories.append("规则62得分未过阈值")
    else:
        categories.append("规则62多特征加权过阈值")
    return "；".join(dict.fromkeys(categories))


def build_analysis_reason(
    dtype: str,
    yolo_row: Mapping[str, str],
    face_row: Mapping[str, Any],
    top_features: str,
    quality_summary_row: Mapping[str, Any] | None,
) -> str:
    label = yolo_row.get("patient_label", "")
    yolo_images = yolo_row.get("image_count", "0")
    yolo_mouth = yolo_row.get("yolo_stroke_mouth_image_count", "0")
    yolo_eye = yolo_row.get("yolo_stroke_eye_image_count", "0")
    yolo_classes = yolo_row.get("yolo_detected_classes", "") or "none"
    score = fmt_float(face_row.get("weighted_disease_score"))
    threshold = fmt_float(face_row.get("score_threshold"))
    triggered = face_row.get("triggered_feature_count", "")
    q_text = quality_text(quality_summary_row)

    if dtype == "yolo_fp_facesymai_tn":
        return (
            f"真实标签为{label}；YOLO因 {yolo_mouth}/{yolo_images} 张口部stroke检测、"
            f"{yolo_eye}/{yolo_images} 张眼部stroke检测判阳性，类别汇总为 {yolo_classes}；"
            f"规则62得分 {score} < 阈值 {threshold}，仅触发 {triggered} 个特征。"
            f"倾向归因为YOLO对自然表情差异或轻度局部不对称过敏感；质量摘要：{q_text}。"
        )
    if dtype == "yolo_fn_facesymai_tp":
        return (
            f"真实标签为{label}；YOLO最优规则未检测到口部stroke阳性，眼部stroke图片数为 {yolo_eye}/{yolo_images}；"
            f"规则62得分 {score} >= 阈值 {threshold}，核心触发特征：{top_features}。"
            f"倾向归因为YOLO漏检或类别覆盖不足，FaceSymAi的几何/表情差异特征捕获到患者级不对称信号；质量摘要：{q_text}。"
        )
    if dtype == "yolo_tp_facesymai_fn":
        return (
            f"真实标签为{label}；YOLO因 {yolo_mouth}/{yolo_images} 张口部stroke检测判阳性，类别汇总为 {yolo_classes}；"
            f"规则62得分 {score} < 阈值 {threshold}，触发 {triggered} 个特征。"
            f"倾向归因为规则62高置信策略偏保守，弱化了召回；YOLO对局部口部异常更敏感；质量摘要：{q_text}。"
        )
    return (
        f"真实标签为{label}；YOLO最优规则未判阳性，类别汇总为 {yolo_classes}；"
        f"规则62得分 {score} >= 阈值 {threshold}，核心触发特征：{top_features}。"
        f"倾向归因为FaceSymAi几何特征对自然不对称、姿态或质量扰动较敏感；质量摘要：{q_text}。"
    )


def build_disagreement_rows(
    *,
    yolo_rule: str,
    yolo_patients: Mapping[str, Mapping[str, str]],
    face_patients: Mapping[str, Mapping[str, Any]],
    contributions: Mapping[str, list[dict[str, str]]],
    qualities: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    common_patient_ids = sorted(set(yolo_patients).intersection(face_patients), key=patient_sort_key)
    for patient_id in common_patient_ids:
        yolo_row = yolo_patients[patient_id]
        face_row = face_patients[patient_id]
        label = yolo_row.get("patient_label", "")
        if label_to_binary(label) != int(face_row.get("label_binary", "0") or 0):
            raise ValueError(f"Label mismatch between YOLO and FaceSymAi for patient {patient_id}")
        if yolo_row.get("split") != face_row.get("split"):
            raise ValueError(f"Split mismatch between YOLO and FaceSymAi for patient {patient_id}")

        yolo_pred = parse_bool(yolo_row.get(yolo_rule, ""))
        face_pred = bool(face_row.get("predicted"))
        if yolo_pred == face_pred:
            continue

        dtype = disagreement_type(yolo_pred, face_pred, label)
        top_features = top_triggered_features(contributions.get(patient_id, []))
        quality = qualities.get(patient_id)
        category = reason_category(dtype, yolo_row, face_row, quality)
        rows.append(
            {
                "patient_id": patient_id,
                "patient_label": label,
                "split": yolo_row.get("split", ""),
                "yolo_prediction": binary_prediction_label(yolo_pred),
                "facesymai_prediction": binary_prediction_label(face_pred),
                "disagreement_type": dtype,
                "analysis_reason": build_analysis_reason(dtype, yolo_row, face_row, top_features, quality),
                "analysis_reason_category": category,
                "yolo_rule": yolo_rule,
                "yolo_image_count": yolo_row.get("image_count", ""),
                "yolo_success_image_count": yolo_row.get("yolo_success_image_count", ""),
                "yolo_error_image_count": yolo_row.get("yolo_error_image_count", ""),
                "yolo_stroke_image_count": yolo_row.get("yolo_stroke_image_count", ""),
                "yolo_stroke_eye_image_count": yolo_row.get("yolo_stroke_eye_image_count", ""),
                "yolo_stroke_mouth_image_count": yolo_row.get("yolo_stroke_mouth_image_count", ""),
                "yolo_stroke_image_ratio": yolo_row.get("yolo_stroke_image_ratio", ""),
                "yolo_detected_classes": yolo_row.get("yolo_detected_classes", ""),
                "facesymai_weighted_disease_score": face_row.get("weighted_disease_score", ""),
                "facesymai_score_threshold": face_row.get("score_threshold", ""),
                "facesymai_triggered_feature_count": face_row.get("triggered_feature_count", ""),
                "facesymai_triggered_weight": face_row.get("triggered_weight", ""),
                "facesymai_top_triggered_features": top_features,
                "quality_summary": quality_text(quality),
                "visualization_path": "",
            }
        )
    return rows


def select_visualization_cases(rows: list[dict[str, Any]], sample_count: int) -> list[dict[str, Any]]:
    if sample_count <= 0:
        return []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["split"], row["disagreement_type"])].append(row)
    for values in grouped.values():
        values.sort(key=lambda item: patient_sort_key(item["patient_id"]))

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    split_priority = ["test", "val", "train"]
    while len(selected) < min(sample_count, len(rows)):
        advanced = False
        for split in split_priority:
            for dtype in DISAGREEMENT_ORDER:
                key = (split, dtype)
                while grouped.get(key) and grouped[key][0]["patient_id"] in seen:
                    grouped[key].pop(0)
                if grouped.get(key):
                    row = grouped[key].pop(0)
                    selected.append(row)
                    seen.add(row["patient_id"])
                    advanced = True
                    if len(selected) >= min(sample_count, len(rows)):
                        break
            if len(selected) >= min(sample_count, len(rows)):
                break
        if not advanced:
            break
    return selected


def load_image(path: Path) -> Any:
    import cv2
    import numpy as np

    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image(path: Path, image: Any) -> None:
    import cv2

    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix or ".jpg", image)
    if not ok:
        raise RuntimeError(f"Failed to encode image: {path}")
    encoded.tofile(str(path))


def blank_cell(text: str, width: int, height: int) -> Any:
    import cv2
    import numpy as np

    image = np.full((height, width, 3), 245, dtype=np.uint8)
    for index, line in enumerate(split_text_for_cv(text, 38)[:5]):
        cv2.putText(image, line, (14, 38 + index * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (60, 60, 60), 2, cv2.LINE_AA)
    return image


def split_text_for_cv(text: str, width: int) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def letterbox(image: Any, width: int, height: int) -> Any:
    import cv2
    import numpy as np

    if image is None:
        return blank_cell("missing image", width, height)
    h, w = image.shape[:2]
    if h <= 0 or w <= 0:
        return blank_cell("invalid image", width, height)
    scale = min(width / w, height / h)
    resized_w = max(1, int(w * scale))
    resized_h = max(1, int(h * scale))
    resized = cv2.resize(image, (resized_w, resized_h), interpolation=cv2.INTER_AREA)
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    x0 = (width - resized_w) // 2
    y0 = (height - resized_h) // 2
    canvas[y0 : y0 + resized_h, x0 : x0 + resized_w] = resized
    return canvas


def load_yolo_model(model_path: Path, skip: bool) -> Any:
    if skip:
        return None
    if not model_path.exists():
        return None
    try:
        from ultralytics import YOLO
    except Exception:
        return None
    try:
        return YOLO(str(model_path))
    except Exception:
        return None


def class_name_for(names: Any, class_id: int) -> str:
    if isinstance(names, Mapping):
        return str(names.get(class_id, class_id))
    if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)


def scalar(value: Any) -> float:
    if hasattr(value, "item"):
        return float(value.item())
    return float(value)


def rerun_yolo_boxes(model: Any, image_path: Path, conf: float, device: str) -> list[dict[str, Any]]:
    if model is None:
        return []
    results = model.predict(source=str(image_path), conf=conf, device=device, verbose=False)
    if not results:
        return []
    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None or getattr(boxes, "cls", None) is None:
        return []
    names = getattr(result, "names", {})
    detections: list[dict[str, Any]] = []
    xyxy_values = getattr(boxes, "xyxy", [])
    for xyxy, class_value, conf_value in zip(xyxy_values, boxes.cls, boxes.conf):
        class_id = int(scalar(class_value))
        coords = [round(scalar(value), 2) for value in xyxy]
        detections.append(
            {
                "class": class_name_for(names, class_id),
                "conf": round(scalar(conf_value), 6),
                "xyxy": coords,
            }
        )
    return detections


def parse_csv_detections(row: Mapping[str, str]) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(row.get("yolo_detections", "[]") or "[]")
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)]


def draw_yolo_overlay(image: Any, detections: list[Mapping[str, Any]], csv_detections: list[Mapping[str, Any]]) -> Any:
    import cv2

    overlay = image.copy()
    drawable = [item for item in detections if item.get("xyxy")]
    if drawable:
        for item in drawable:
            class_name = str(item.get("class", ""))
            conf = float(item.get("conf", 0) or 0)
            x1, y1, x2, y2 = [int(round(float(value))) for value in item["xyxy"]]
            is_stroke = class_name.lower().startswith("stroke")
            color = (35, 35, 225) if is_stroke else (40, 170, 40)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
            label = f"{class_name} {conf:.2f}"
            y_text = max(22, y1 - 8)
            cv2.rectangle(overlay, (x1, y_text - 20), (min(x1 + 250, overlay.shape[1] - 1), y_text + 6), color, -1)
            cv2.putText(overlay, label[:32], (x1 + 4, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2, cv2.LINE_AA)
        return overlay

    labels = [f"{item.get('class', '')} {float(item.get('conf', 0) or 0):.2f}" for item in csv_detections]
    text = "YOLO: " + ("; ".join(labels[:4]) if labels else "no detections")
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 42), (0, 0, 0), -1)
    cv2.putText(overlay, text[:80], (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return overlay


def choose_role_rows(patient_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_role: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in patient_rows:
        by_role[row.get("role", "")].append(row)
    chosen: list[dict[str, str]] = []
    for role in ROLE_ORDER:
        if by_role.get(role):
            chosen.append(by_role[role][0])
    if not chosen:
        chosen = patient_rows[:3]
    return chosen


def render_patient_visualization(
    *,
    case: Mapping[str, Any],
    yolo_image_rows: Mapping[str, list[dict[str, str]]],
    annotation_by_image: Mapping[str, str],
    yolo_model: Any,
    yolo_conf: float,
    yolo_device: str,
    output_dir: Path,
) -> tuple[str, str, str]:
    import cv2
    import numpy as np

    patient_id = case["patient_id"]
    role_rows = choose_role_rows(yolo_image_rows.get(patient_id, []))
    cell_w = 380
    cell_h = 360
    header_h = 120
    role_header_h = 38
    columns = ["Original", "YOLO boxes", "FaceSymAi landmarks"]
    total_w = cell_w * len(columns)
    total_h = header_h + max(1, len(role_rows)) * (role_header_h + cell_h)
    canvas = np.full((total_h, total_w, 3), 250, dtype=np.uint8)

    title = (
        f"Patient {patient_id} | {label_for_visual(case['patient_label'])} | split={case['split']} | "
        f"YOLO={prediction_for_visual(case['yolo_prediction'])} | FaceSymAi={prediction_for_visual(case['facesymai_prediction'])}"
    )
    cv2.putText(canvas, title[:118], (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (25, 25, 25), 2, cv2.LINE_AA)
    cv2.putText(canvas, str(case["disagreement_type"])[:80], (16, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (70, 70, 70), 2, cv2.LINE_AA)
    for col, name in enumerate(columns):
        cv2.putText(canvas, name, (col * cell_w + 16, header_h - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (20, 20, 20), 2, cv2.LINE_AA)

    roles_rendered: list[str] = []
    notes: list[str] = []
    for row_index, image_row in enumerate(role_rows):
        role = image_row.get("role", f"row{row_index + 1}")
        roles_rendered.append(role)
        y0 = header_h + row_index * (role_header_h + cell_h)
        cv2.rectangle(canvas, (0, y0), (total_w, y0 + role_header_h), (235, 238, 240), -1)
        cv2.putText(canvas, f"role={role}", (16, y0 + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (50, 50, 50), 2, cv2.LINE_AA)

        image_path = Path(image_row.get("image_path", ""))
        original = load_image(image_path)
        if original is None:
            notes.append(f"{role}:missing_original")
            original_cell = blank_cell("missing original", cell_w, cell_h)
            yolo_cell = blank_cell("missing original", cell_w, cell_h)
        else:
            original_cell = letterbox(original, cell_w, cell_h)
            try:
                yolo_boxes = rerun_yolo_boxes(yolo_model, image_path, yolo_conf, yolo_device)
            except Exception as exc:
                notes.append(f"{role}:yolo_rerun_failed:{type(exc).__name__}")
                yolo_boxes = []
            yolo_overlay = draw_yolo_overlay(original, yolo_boxes, parse_csv_detections(image_row))
            yolo_cell = letterbox(yolo_overlay, cell_w, cell_h)

        annotation_path = annotation_by_image.get(image_path.resolve().as_posix(), "")
        annotation = load_image(Path(annotation_path)) if annotation_path else None
        if annotation is None:
            notes.append(f"{role}:missing_facesymai_overlay")
        annotation_cell = letterbox(annotation, cell_w, cell_h)

        row_y = y0 + role_header_h
        for col, cell in enumerate([original_cell, yolo_cell, annotation_cell]):
            x0 = col * cell_w
            canvas[row_y : row_y + cell_h, x0 : x0 + cell_w] = cell
            cv2.rectangle(canvas, (x0, row_y), (x0 + cell_w - 1, row_y + cell_h - 1), (210, 210, 210), 1)

    filename = f"patient_{patient_id}_{case['disagreement_type']}.jpg"
    output_path = output_dir / filename
    save_image(output_path, canvas)
    return display_path(output_path), ",".join(roles_rendered), ";".join(notes) if notes else "ok"


def generate_visualizations(
    *,
    rows: list[dict[str, Any]],
    selected_cases: list[dict[str, Any]],
    yolo_image_rows: Mapping[str, list[dict[str, str]]],
    annotation_by_image: Mapping[str, str],
    yolo_model: Any,
    yolo_conf: float,
    yolo_device: str,
    output_dir: Path,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_image in output_dir.glob("patient_*.jpg"):
        old_image.unlink()
    row_by_patient = {row["patient_id"]: row for row in rows}
    index_rows: list[dict[str, Any]] = []
    for case in selected_cases:
        path, roles_rendered, note = render_patient_visualization(
            case=case,
            yolo_image_rows=yolo_image_rows,
            annotation_by_image=annotation_by_image,
            yolo_model=yolo_model,
            yolo_conf=yolo_conf,
            yolo_device=yolo_device,
            output_dir=output_dir,
        )
        row_by_patient[case["patient_id"]]["visualization_path"] = path
        index_rows.append(
            {
                "patient_id": case["patient_id"],
                "patient_label": case["patient_label"],
                "split": case["split"],
                "disagreement_type": case["disagreement_type"],
                "visualization_path": path,
                "roles_rendered": roles_rendered,
                "note": note,
            }
        )
    return index_rows


def count_by(rows: Iterable[Mapping[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update([str(row.get(key, ""))])
    return counter


def split_type_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, Counter[str]]:
    counts = {split: Counter() for split in SPLIT_ORDER}
    for row in rows:
        split = str(row.get("split", ""))
        dtype = str(row.get("disagreement_type", ""))
        counts.setdefault(split, Counter()).update([dtype])
        counts["combined"].update([dtype])
    return counts


def yolo_face_joint_counts(
    common_patient_ids: Iterable[str],
    yolo_patients: Mapping[str, Mapping[str, str]],
    face_patients: Mapping[str, Mapping[str, Any]],
    yolo_rule: str,
) -> Counter[str]:
    counter: Counter[str] = Counter()
    for patient_id in common_patient_ids:
        yolo_pred = parse_bool(yolo_patients[patient_id].get(yolo_rule, ""))
        face_pred = bool(face_patients[patient_id].get("predicted"))
        if yolo_pred and face_pred:
            counter.update(["both_positive"])
        elif yolo_pred and not face_pred:
            counter.update(["yolo_only_positive"])
        elif not yolo_pred and face_pred:
            counter.update(["facesymai_only_positive"])
        else:
            counter.update(["both_negative"])
    return counter


def metric_row_for(lookup: Mapping[tuple[str, str], Mapping[str, str]], method: str, split: str) -> Mapping[str, str]:
    row = lookup.get((method, split))
    if row is None:
        return {}
    return row


def build_final_report(
    *,
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    visualization_index: list[dict[str, Any]],
    metric_rows: list[Mapping[str, str]],
    yolo_rule: str,
    common_patient_count: int,
    joint_counts: Counter[str],
) -> list[str]:
    lookup = metric_lookup(metric_rows)
    type_counts = count_by(rows, "disagreement_type")
    reason_counts = count_by(rows, "analysis_reason_category")
    split_counts = split_type_counts(rows)
    yolo_test = metric_row_for(lookup, yolo_rule, "test")
    face_test = metric_row_for(lookup, "facesymai_rule62", "test")
    yolo_combined = metric_row_for(lookup, yolo_rule, "combined")
    face_combined = metric_row_for(lookup, "facesymai_rule62", "combined")

    one_sentence = (
        "FaceSymAi 规则62 更适合作为高置信、可解释的保守筛查信号；YOLO 最优规则更适合作为高召回补充，"
        "但其不患病误报和弱标签下 specificity 明显偏弱。"
    )

    lines = [
        "# FaceSymAi vs YOLO 中风面部不对称检测对比报告",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- YOLO 展示规则：`{yolo_rule}`（来自 #02 test split F1 最优规则）。",
        f"- 共同患者集合：{common_patient_count} 名旧 V1 患者；不一致患者：{len(rows)} 名。",
        f"- 抽样可视化：{len(visualization_index)} 名患者，目录 `{display_path(args.output_dir / 'comparison_visualizations')}`。",
        "- 重要边界：当前标签为 patient outcome 弱标签，不是人工标注的面部不对称或临床诊断标签；本文只表述技术信号对比。",
        "",
        "## 1. 执行摘要",
        "",
        f"- 一句话结论：{one_sentence}",
        f"- 在 test split 上，YOLO `{yolo_rule}` recall 为 {yolo_test.get('recall', '')}、F1 为 {yolo_test.get('f1', '')}；FaceSymAi 规则62 precision 为 {face_test.get('precision', '')}、specificity 为 {face_test.get('specificity', '')}。",
        f"- 两者预测不一致 {len(rows)}/{common_patient_count}，主要来自 YOLO 阳性而 FaceSymAi 阴性的病例（{joint_counts.get('yolo_only_positive', 0)} 名）。",
        "",
        "## 2. 方法论对比",
        "",
    ]
    lines.extend(
        markdown_table(
            ["维度", "FaceSymAi", "YOLO Stroke-Detection"],
            [
                ["方法", "MediaPipe 478点几何分析 + 21个稳定性加权特征", "YOLOv8 端到端目标检测"],
                ["输入语义", "面部动作/角色相关图片，强调正脸、微笑、露齿等结构化采集", "单张图片直接检测 normal/stroke 眼部和口部类别"],
                ["患者级聚合", "规则62 加权得分 `weighted_disease_score >= 0.612826`", f"#02 最优展示规则 `{yolo_rule}`"],
                ["输出解释", "可追溯到唇中线、口角、眼周、眉部、轮廓等特征贡献", "可解释为检测框类别和置信度，但缺少几何特征链路"],
                ["质量控制", "继承 V1 质量门控和 MediaPipe 检测状态", "本次 #01 推理不使用 FaceSymAi 质量门控"],
                ["主要风险", "阈值保守导致漏检，几何特征可能受姿态/自然不对称影响", "高召回规则容易把正常表情或轻度局部差异报成阳性"],
            ],
        )
    )

    lines.extend(["", "## 3. 定量指标对比", ""])
    lines.extend(
        markdown_table(
            ["method", "split", "precision", "recall", "specificity", "f1", "accuracy", "TP", "FP", "TN", "FN"],
            [
                [
                    row.get("method", method),
                    split,
                    row.get("precision", ""),
                    row.get("recall", ""),
                    row.get("specificity", ""),
                    row.get("f1", ""),
                    row.get("accuracy", ""),
                    row.get("tp", ""),
                    row.get("fp", ""),
                    row.get("tn", ""),
                    row.get("fn", ""),
                ]
                for method in [yolo_rule, "facesymai_rule62"]
                for split, row in [
                    ("test", metric_row_for(lookup, method, "test")),
                    ("combined", metric_row_for(lookup, method, "combined")),
                ]
            ],
        )
    )
    lines.extend(
        [
            "",
            "- 指标来自任务 #02 的 `comparison_metrics.csv`，在相同共同患者集合上计算。",
            "- test split 中 YOLO 的召回更高，FaceSymAi 的 precision、specificity 和 accuracy 更高。",
            "- combined 口径中 FaceSymAi precision/specificity 优势更明显，YOLO 保持 recall 优势。",
        ]
    )

    lines.extend(["", "## 4. 定性分析", ""])
    lines.extend(
        [
            "### 不一致案例统计",
            "",
            f"- 共同患者：{common_patient_count}",
            f"- 不一致患者：{len(rows)}",
            f"- 双方都判阳性：{joint_counts.get('both_positive', 0)}",
            f"- 仅 YOLO 判阳性：{joint_counts.get('yolo_only_positive', 0)}",
            f"- 仅 FaceSymAi 判阳性：{joint_counts.get('facesymai_only_positive', 0)}",
            f"- 双方都判阴性：{joint_counts.get('both_negative', 0)}",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            ["disagreement_type", "combined", "train", "val", "test"],
            [
                [
                    dtype,
                    split_counts["combined"].get(dtype, 0),
                    split_counts["train"].get(dtype, 0),
                    split_counts["val"].get(dtype, 0),
                    split_counts["test"].get(dtype, 0),
                ]
                for dtype in DISAGREEMENT_ORDER
                if type_counts.get(dtype, 0)
            ],
        )
    )

    lines.extend(["", "### 典型差异原因分类", ""])
    lines.extend(
        markdown_table(
            ["原因分类", "病例数"],
            [[reason, count] for reason, count in reason_counts.most_common()],
        )
    )
    lines.extend(
        [
            "",
            "- YOLO 阳性、FaceSymAi 阴性的病例最多，说明 YOLO `any mouth stroke` 类规则对局部口部检测更敏感，召回高但误报面更宽。",
            "- FaceSymAi 阳性、YOLO 阴性的病例较少，通常表现为多项几何特征加权过阈值，但 YOLO 没有口部 stroke 检测；这类案例更适合人工复核几何特征是否来自真实不对称还是姿态/质量扰动。",
            f"- 抽样图位于 `{display_path(args.output_dir / 'comparison_visualizations')}`；每张图按原图、YOLO bbox、FaceSymAi 关键点 overlay 三列展示。",
        ]
    )

    lines.extend(["", "## 5. 各维度优劣对比", ""])
    lines.extend(
        markdown_table(
            ["维度", "FaceSymAi", "YOLO", "说明"],
            [
                ["精度", "precision/specificity 更高", "recall/F1 更高", "FaceSymAi 适合高置信输出；YOLO 适合发现更多疑似病例"],
                ["可解释性", "强", "中", "FaceSymAi 可定位到稳定特征贡献；YOLO 主要解释为检测框类别"],
                ["鲁棒性", "依赖关键点质量和标准采集", "对输入流程简单但误报多", "FaceSymAi 有质量门控；YOLO 本轮未使用质量约束"],
                ["速度", "需要关键点、特征和患者级聚合", "单模型检测链路更短", "YOLO 纯推理更直接；FaceSymAi 提供更多结构化证据"],
                ["临床对齐度", "更接近面瘫/面部不对称观察项", "类别学习依赖训练集语义", "FaceSymAi 的口角、唇中线、眼周、眉部证据更便于复核"],
                ["部署难度", "中", "低到中", "FaceSymAi 模块多但可解释；YOLO 部署简单但需要误报控制和阈值策略"],
            ],
        )
    )

    lines.extend(
        [
            "",
            "## 6. 改进建议",
            "",
            "### FaceSymAi 可以从 YOLO 借鉴什么",
            "",
            "- 引入 YOLO 口部/眼部检测作为候选召回分支，优先覆盖规则62漏判但 YOLO口部明确阳性的患病病例。",
            "- 对规则62 的阴性高风险边界样本建立人工复核队列，尤其是 YOLO 阳性且口部 severe/mid 检测反复出现的患者。",
            "- 在可解释报告中加入局部检测证据截图，补充几何特征对业务方不直观的问题。",
            "",
            "### YOLO 方案的不足",
            "",
            "- 患者级 `any` 类规则过于宽松，test specificity 低，容易把不患病患者推成阳性。",
            "- #01 CSV 原始输出只保留 class/conf，未保存 bbox，后续复核必须重新推理才能复现框级可视化；建议未来保存 `xyxy` 和模型版本。",
            "- YOLO 检测框无法直接说明口角高度、唇中线偏移、眼周或眉部几何差异，临床解释链路弱于 FaceSymAi。",
            "- 本轮未接入质量门控，低质量、多人脸或动作不标准图片可能贡献误报。",
            "",
            "## 7. 结论",
            "",
            "FaceSymAi 规则62 和 YOLO 最优规则不是简单替代关系：FaceSymAi 更适合作为可解释、高 precision/high specificity 的主输出，YOLO 更适合作为高 recall 的辅助发现器。实际产品路径建议以 FaceSymAi 规则62 作为业务展示和高置信结论基线，把 YOLO 阳性但规则62 阴性的病例纳入复核或二阶段候选，而不是直接用 YOLO `any` 规则替代当前方案。所有结论仍受 patient outcome 弱标签限制，不能外推为临床诊断性能。",
        ]
    )
    return lines


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    metric_rows = read_csv(args.comparison_metrics)
    yolo_rule = select_yolo_rule(metric_rows, args.yolo_rule)

    split_by_patient_id = load_split_map(args.splits)
    yolo_patients = load_yolo_patients(args.yolo_patients)
    yolo_images = load_yolo_images(args.yolo_per_image)
    face_patients = load_facesymai_rule62(args.facesymai_rule62_patients, split_by_patient_id)
    contributions = load_facesymai_contributions(args.facesymai_rule62_contributions)
    qualities = load_quality_summary(args.quality_gate)
    annotation_by_image = load_annotation_map(args.manifest, args.keypoints, DEFAULT_DATASET)

    common_patient_ids = sorted(set(yolo_patients).intersection(face_patients), key=patient_sort_key)
    if not common_patient_ids:
        raise ValueError("No common patients between YOLO and FaceSymAi rule62")

    rows = build_disagreement_rows(
        yolo_rule=yolo_rule,
        yolo_patients=yolo_patients,
        face_patients=face_patients,
        contributions=contributions,
        qualities=qualities,
    )
    if not rows:
        raise ValueError("No disagreement cases found")

    visualization_cases = select_visualization_cases(rows, args.sample_patients)
    yolo_model = load_yolo_model(args.yolo_model, args.skip_yolo_rerun)
    visualization_index = generate_visualizations(
        rows=rows,
        selected_cases=visualization_cases,
        yolo_image_rows=yolo_images,
        annotation_by_image=annotation_by_image,
        yolo_model=yolo_model,
        yolo_conf=args.yolo_conf,
        yolo_device=args.yolo_device,
        output_dir=args.output_dir / "comparison_visualizations",
    )

    joint_counts = yolo_face_joint_counts(common_patient_ids, yolo_patients, face_patients, yolo_rule)
    final_report = build_final_report(
        args=args,
        rows=rows,
        visualization_index=visualization_index,
        metric_rows=metric_rows,
        yolo_rule=yolo_rule,
        common_patient_count=len(common_patient_ids),
        joint_counts=joint_counts,
    )

    disagreement_path = args.output_dir / "disagreement_cases.csv"
    visualization_index_path = args.output_dir / "comparison_visualizations" / "index.csv"
    report_path = args.output_dir / "final_comparison_report.md"
    write_csv(disagreement_path, rows, DISAGREEMENT_FIELDS)
    write_csv(visualization_index_path, visualization_index, VISUALIZATION_INDEX_FIELDS)
    write_markdown(report_path, final_report)

    print(f"YOLO rule: {yolo_rule}")
    print(f"Common patients: {len(common_patient_ids)}")
    print(f"Disagreement cases: {len(rows)}")
    print(f"Visualized patients: {len(visualization_index)}")
    print(f"Wrote {display_path(disagreement_path)}")
    print(f"Wrote {display_path(visualization_index_path)}")
    print(f"Wrote {display_path(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
