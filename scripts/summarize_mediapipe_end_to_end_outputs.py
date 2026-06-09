#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"
CORE_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
POSE_DISTANCE_FEATURE_PREFIXES = ("matrix_", "pose_")
POSE_DISTANCE_FEATURE_SUFFIXES = ("_centroid_z_asym",)
POSE_DISTANCE_FEATURE_TOKENS = ("yaw", "pitch", "roll", "scale", "distance", "bbox", "translation")


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    label_diff_rows = read_csv(required(metadata / "09_mediapipe_feature_differences.csv"))
    feature_set_rows = read_csv(required(metadata / "11_v11_role_aware_feature_set.csv"))
    prediction_rows = read_csv(required(metadata / "11_v11_role_aware_predictions.csv"))
    hb_grade_rows = read_csv(required(metadata / "12_v11_hb_proxy_patient_grades.csv"))
    grade_diff_rows = read_csv(required(metadata / "12_v11_hb_proxy_mediapipe_grade_differences.csv"))
    v11_evaluation = read_json(required(metadata / "11_v11_role_aware_evaluation.json"))
    hb_evaluation = read_json(required(metadata / "12_v11_hb_proxy_grade_evaluation.json"))
    pair_summary = read_optional_json(metadata / "14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json")

    top_label_differences = top_label_difference_rows(label_diff_rows, args.top_n)
    top_model_features = top_model_feature_rows(feature_set_rows, args.top_n)
    top_grade_differences = top_grade_difference_rows(grade_diff_rows, args.top_n)
    feature_summary_rows = build_feature_summary_rows(top_label_differences, top_model_features, top_grade_differences)
    patient_prediction_rows = build_prediction_rows(prediction_rows, hb_grade_rows)
    summary = build_summary(
        dataset,
        feature_summary_rows,
        patient_prediction_rows,
        v11_evaluation,
        hb_evaluation,
        pair_summary,
        args.top_n,
    )

    write_csv(metadata / "20_mediapipe_end_to_end_feature_differences.csv", feature_summary_rows)
    write_csv(metadata / "20_mediapipe_end_to_end_predictions.csv", patient_prediction_rows)
    write_json(metadata / "20_mediapipe_end_to_end_summary.json", summary)
    write_report(reports / "20_mediapipe_end_to_end_summary.md", summary, feature_summary_rows, patient_prediction_rows)

    print(f"Wrote {metadata / '20_mediapipe_end_to_end_feature_differences.csv'}")
    print(f"Wrote {metadata / '20_mediapipe_end_to_end_predictions.csv'}")
    print(f"Wrote {metadata / '20_mediapipe_end_to_end_summary.json'}")
    print(f"Wrote {reports / '20_mediapipe_end_to_end_summary.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize the MediaPipe end-to-end feature-difference and prediction outputs."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing generated metadata.")
    parser.add_argument("--top-n", type=int, default=12, help="Top rows per feature-difference section.")
    return parser.parse_args()


def required(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Required input is missing: {path}")
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    fixed = [
        "section",
        "rank",
        "role",
        "scope",
        "feature_name",
        "feature_family",
        "feature_source",
        "direction",
        "patient_sample_id",
        "label_group",
        "label_binary",
        "split",
        "predicted_label",
        "face_asymmetry_output",
        "hb_proxy_grade",
        "confusion_cell",
    ]
    fields = [field for field in fixed if field in fields] + [field for field in fields if field not in fixed]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def top_label_difference_rows(rows: list[dict[str, str]], top_n: int) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for role in ("all", *CORE_ROLES):
        candidates = [
            row
            for row in rows
            if row.get("role") == role
            if is_main_evidence_feature(row.get("feature_name", ""))
        ]
        ranked = sorted(
            candidates,
            key=lambda row: (
                parse_float(row.get("separation_auc")) or 0.0,
                abs(parse_float(row.get("cohens_d")) or 0.0),
            ),
            reverse=True,
        )
        output.extend(ranked[:top_n])
    return output


def top_model_feature_rows(rows: list[dict[str, str]], top_n: int) -> list[dict[str, str]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            parse_float(row.get("feature_weight")) or 0.0,
            parse_float(row.get("auc_positive_higher")) or 0.0,
            abs(parse_float(row.get("cohens_d")) or 0.0),
        ),
        reverse=True,
    )
    return ranked[:top_n]


def top_grade_difference_rows(rows: list[dict[str, str]], top_n: int) -> list[dict[str, str]]:
    all_core = [row for row in rows if row.get("scope") == "all_core_roles"]
    ranked = sorted(
        all_core,
        key=lambda row: (
            parse_float(row.get("ranking_score")) or 0.0,
            abs(parse_float(row.get("standardized_i_to_vi_effect")) or 0.0),
        ),
        reverse=True,
    )
    return ranked[:top_n]


def build_feature_summary_rows(
    top_label_differences: list[dict[str, str]],
    top_model_features: list[dict[str, str]],
    top_grade_differences: list[dict[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    role_rank: Counter[str] = Counter()
    for row in top_label_differences:
        role = row.get("role", "")
        role_rank[role] += 1
        output.append(
            {
                "section": "disease_vs_nondisease_main_evidence",
                "rank": role_rank[role],
                "role": role,
                "feature_name": row.get("feature_name", ""),
                "feature_family": feature_family(row.get("feature_name", "")),
                "direction": row.get("direction", ""),
                "positive_mean": row.get("positive_mean", ""),
                "negative_mean": row.get("negative_mean", ""),
                "mean_diff_positive_minus_negative": row.get("mean_diff_positive_minus_negative", ""),
                "cohens_d": row.get("cohens_d", ""),
                "auc_positive_higher": row.get("auc_positive_higher", ""),
                "separation_auc": row.get("separation_auc", ""),
                "positive_n": row.get("positive_n", ""),
                "negative_n": row.get("negative_n", ""),
            }
        )

    for index, row in enumerate(top_model_features, start=1):
        output.append(
            {
                "section": "prediction_model_top_weighted_features",
                "rank": index,
                "role": row.get("role", ""),
                "feature_name": row.get("feature_name", ""),
                "feature_family": feature_family(row.get("feature_name", "")),
                "feature_source": row.get("feature_type", ""),
                "direction": "患病更高",
                "positive_mean": row.get("positive_mean", ""),
                "negative_mean": row.get("negative_mean", ""),
                "mean_diff_positive_minus_negative": row.get("mean_diff_positive_minus_negative", ""),
                "cohens_d": row.get("cohens_d", ""),
                "auc_positive_higher": row.get("auc_positive_higher", ""),
                "feature_weight": row.get("feature_weight", ""),
                "feature_weight_multiplier": row.get("feature_weight_multiplier", ""),
                "expression_cap_scale": row.get("expression_cap_scale", ""),
            }
        )

    for index, row in enumerate(top_grade_differences, start=1):
        output.append(
            {
                "section": "hb_proxy_grade_i_to_vi_top_differences",
                "rank": index,
                "scope": row.get("scope", ""),
                "feature_name": row.get("feature_name", ""),
                "feature_family": row.get("feature_family", ""),
                "feature_source": row.get("feature_source", ""),
                "direction": "Grade VI 更高" if (parse_float(row.get("grade_i_to_vi_delta")) or 0.0) > 0 else "Grade I 更高",
                "grade_i_mean": row.get("grade_i_mean", ""),
                "grade_vi_mean": row.get("grade_vi_mean", ""),
                "grade_i_to_vi_delta": row.get("grade_i_to_vi_delta", ""),
                "standardized_i_to_vi_effect": row.get("standardized_i_to_vi_effect", ""),
                "strongest_adjacent_transition": row.get("strongest_adjacent_transition", ""),
                "standardized_strongest_adjacent_delta": row.get("standardized_strongest_adjacent_delta", ""),
                "grade_value_correlation": row.get("grade_value_correlation", ""),
                "ranking_score": row.get("ranking_score", ""),
                "patient_count": row.get("patient_count", ""),
            }
        )
    return output


def build_prediction_rows(
    prediction_rows: list[dict[str, str]],
    hb_grade_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    hb_by_patient = {row["patient_sample_id"]: row for row in hb_grade_rows}
    output: list[dict[str, Any]] = []
    for row in sorted(prediction_rows, key=lambda item: item["patient_sample_id"]):
        hb = hb_by_patient.get(row["patient_sample_id"], {})
        output.append(
            {
                "patient_sample_id": row.get("patient_sample_id", ""),
                "label_group": row.get("label_group", ""),
                "label_binary": row.get("label_binary", ""),
                "split": row.get("split", ""),
                "v11_asymmetry_score": row.get("v11_asymmetry_score", ""),
                "v11_asymmetry_z": row.get("v11_asymmetry_z", ""),
                "v11_threshold": row.get("threshold", ""),
                "predicted_positive": row.get("predicted_positive", ""),
                "predicted_label": "预测患病" if row.get("predicted_positive") == "1" else "预测不患病",
                "confusion_cell": row.get("confusion_cell", ""),
                "core_result": row.get("core_result", ""),
                "hb_proxy_grade": hb.get("hb_proxy_grade", ""),
                "hb_proxy_grade_num": hb.get("hb_proxy_grade_num", ""),
                "hb_proxy_overall_score": hb.get("hb_proxy_overall_score", ""),
                "hb_grade_confidence": hb.get("hb_grade_confidence", ""),
                "face_asymmetry_output": hb.get("face_asymmetry_output", ""),
                "resting_symmetry_score": hb.get("resting_symmetry_score", ""),
                "eye_closure_score": hb.get("eye_closure_score", ""),
                "brow_forehead_score": hb.get("brow_forehead_score", ""),
                "smile_mouth_score": hb.get("smile_mouth_score", ""),
                "gross_asymmetry_score": hb.get("gross_asymmetry_score", ""),
                "movement_absence_score": hb.get("movement_absence_score", ""),
                "included_roles_available": row.get("included_roles_available", hb.get("included_roles_available", "")),
                "top_positive_features": row.get("top_positive_features", hb.get("top_positive_features", "")),
                "face_asymmetry_reason": hb.get("face_asymmetry_reason", ""),
            }
        )
    return output


def build_summary(
    dataset: Path,
    feature_summary_rows: list[dict[str, Any]],
    patient_prediction_rows: list[dict[str, Any]],
    v11_evaluation: Mapping[str, Any],
    hb_evaluation: Mapping[str, Any],
    pair_summary: Mapping[str, Any],
    top_n: int,
) -> dict[str, Any]:
    predictions_by_split = {
        split: metrics_for_split([row for row in patient_prediction_rows if row.get("split") == split])
        for split in ("train", "val", "test")
    }
    predictions_by_split["all"] = metrics_for_split(patient_prediction_rows)
    hb_grade_counts = count_by(patient_prediction_rows, "hb_proxy_grade")
    face_output_counts = count_by(patient_prediction_rows, "face_asymmetry_output")
    return {
        "dataset": dataset.name,
        "top_n": top_n,
        "source_outputs": {
            "image_level_features": "metadata/09_mediapipe_full_features.csv",
            "disease_nondisease_feature_differences": "metadata/09_mediapipe_feature_differences.csv",
            "v11_predictions": "metadata/11_v11_role_aware_predictions.csv",
            "hb_proxy_patient_grades": "metadata/12_v11_hb_proxy_patient_grades.csv",
            "hb_proxy_mediapipe_grade_differences": "metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv",
            "grade_v_plus_pair_comparison": "metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv",
        },
        "generated_outputs": {
            "feature_differences_csv": "metadata/20_mediapipe_end_to_end_feature_differences.csv",
            "predictions_csv": "metadata/20_mediapipe_end_to_end_predictions.csv",
            "summary_json": "metadata/20_mediapipe_end_to_end_summary.json",
            "report": "reports/20_mediapipe_end_to_end_summary.md",
        },
        "feature_sections": count_by(feature_summary_rows, "section"),
        "patient_prediction_rows": len(patient_prediction_rows),
        "predictions_by_split": predictions_by_split,
        "hb_proxy_grade_counts": hb_grade_counts,
        "face_asymmetry_output_counts": face_output_counts,
        "v11_metrics": v11_evaluation.get("metrics", {}),
        "v11_auc": v11_evaluation.get("auc", {}),
        "v11_threshold": v11_evaluation.get("threshold", ""),
        "hb_grade_v_plus_metrics": grade_v_plus_metrics(hb_evaluation),
        "pair_comparison": {
            "pair_count": pair_summary.get("pair_count", 0),
            "component_mean_delta_diseased_minus_nondisease": pair_summary.get(
                "component_mean_delta_diseased_minus_nondisease", {}
            ),
            "top_features": pair_summary.get("top_features", {}),
        },
        "interpretation_limit": (
            "患病/不患病是 patient outcome 弱监督标签，不是人工面瘫或人脸不对称真值；"
            "本汇总用于算法证据复核和工程预测输出，不构成临床诊断。"
        ),
    }


def grade_v_plus_metrics(hb_evaluation: Mapping[str, Any]) -> dict[str, Any]:
    binary_metrics = hb_evaluation.get("binary_metrics", {})
    if "grade_v_plus_face_asymmetry" in binary_metrics:
        return binary_metrics["grade_v_plus_face_asymmetry"]
    derived = hb_evaluation.get("derived_binary_metrics", {})
    return derived.get("grade_v_plus_face_asymmetry", {})


def metrics_for_split(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        pred = str(row.get("predicted_positive", ""))
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
    balanced_accuracy = (recall + specificity) / 2.0 if evaluated else 0.0
    return {
        "patients": evaluated,
        "skipped": skipped,
        "accuracy": round(accuracy, 6),
        "balanced_accuracy": round(balanced_accuracy, 6),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "specificity": round(specificity, 6),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def count_by(rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = str(row.get(field, ""))
        counter[value or ""] += 1
    return dict(sorted(counter.items()))


def is_main_evidence_feature(name: str) -> bool:
    if is_pose_or_distance_feature(name):
        return False
    if name.startswith("bsdiff_"):
        return True
    if name.startswith("raw_") and ("asym" in name or "deviation" in name):
        return True
    return False


def is_pose_or_distance_feature(name: str) -> bool:
    lowered = name.lower()
    if lowered.startswith(POSE_DISTANCE_FEATURE_PREFIXES):
        return True
    if lowered.endswith(POSE_DISTANCE_FEATURE_SUFFIXES):
        return True
    if lowered.startswith(("bs_", "bsdiff_")):
        return False
    return any(token in lowered for token in POSE_DISTANCE_FEATURE_TOKENS)


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


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    feature_rows: list[Mapping[str, Any]],
    prediction_rows: list[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 20 MediaPipe 全流程特征差异与预测汇总",
        "",
        f"分析对象：`datasets/{summary['dataset']}`",
        "",
        "## 流程",
        "",
        "本报告按 `docs/algorithm/mediapipe-pair-and-feature-difference-processing.md` 汇总既有产物：",
        "",
        "1. `03_keypoints.csv` 与关键点 JSON 提供 MediaPipe 478 raw landmarks、52 blendshapes 和 transformation matrix。",
        "2. `09_mediapipe_full_features.csv` 展开 `raw_*`、`bs_*`、`bsdiff_*`、`matrix_*`、`pose_*` 图像级特征。",
        "3. `11_v11_role_aware_predictions.csv` 输出患者级患病/不患病弱监督预测。",
        "4. `12_v11_hb_proxy_patient_grades.csv` 输出 HB proxy I-VI 等级与 Grade V+ 人脸不对称结果。",
        "5. `14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv` 输出 Grade V+ 患病/不患病 18 对照分析。",
        "",
        "## 新增产物",
        "",
        "- 特征差异汇总：`metadata/20_mediapipe_end_to_end_feature_differences.csv`",
        "- 患者预测汇总：`metadata/20_mediapipe_end_to_end_predictions.csv`",
        "- JSON 摘要：`metadata/20_mediapipe_end_to_end_summary.json`",
        "",
        "## 预测结果",
        "",
        f"- V1.1 阈值：`{summary.get('v11_threshold')}`",
        f"- 患者级预测行数：`{summary.get('patient_prediction_rows')}`",
        f"- HB proxy 等级分布：`{json.dumps(summary.get('hb_proxy_grade_counts', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Grade V+ 人脸不对称输出分布：`{json.dumps(summary.get('face_asymmetry_output_counts', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "### V1.1 患病/不患病预测指标",
        "",
    ]
    lines.extend(
        markdown_table(
            ["split", "patients", "accuracy", "balanced_accuracy", "precision", "recall", "specificity", "TP", "FP", "TN", "FN"],
            [
                [
                    split,
                    row["patients"],
                    fmt(row["accuracy"]),
                    fmt(row["balanced_accuracy"]),
                    fmt(row["precision"]),
                    fmt(row["recall"]),
                    fmt(row["specificity"]),
                    row["tp"],
                    row["fp"],
                    row["tn"],
                    row["fn"],
                ]
                for split, row in ordered_metric_items(summary.get("predictions_by_split", {}))
            ],
        )
    )
    lines.extend(
        [
            "",
            "### Grade V+ 人脸不对称输出指标",
            "",
            "规则：`hb_proxy_grade_num >= 5` 输出 `人脸不对称`。该指标仍以 patient outcome 标签做弱监督检查。",
            "",
        ]
    )
    grade_metrics = summary.get("hb_grade_v_plus_metrics", {})
    if grade_metrics:
        lines.extend(
            markdown_table(
                ["split", "accuracy", "balanced_accuracy", "precision", "recall", "specificity", "TP", "FP", "TN", "FN"],
                [
                    [
                        split,
                        fmt(row.get("accuracy")),
                        fmt(row.get("balanced_accuracy")),
                        fmt(row.get("precision")),
                        fmt(row.get("recall")),
                        fmt(row.get("specificity")),
                        row.get("tp", row.get("TP", "")),
                        row.get("fp", row.get("FP", "")),
                        row.get("tn", row.get("TN", "")),
                        row.get("fn", row.get("FN", "")),
                    ]
                    for split, row in ordered_metric_items(grade_metrics)
                ],
            )
        )
    else:
        lines.append("未在 `12_v11_hb_proxy_grade_evaluation.json` 中找到 Grade V+ 指标。")

    lines.extend(
        [
            "",
            "## 最大特征差异项",
            "",
            "下列三组特征均已排除 `matrix_*`、`pose_*`、采集距离/姿态和 `*_centroid_z_asym` 等控制变量。",
            "",
            "### 患病/不患病主证据差异 Top",
            "",
        ]
    )
    disease_rows = [row for row in feature_rows if row.get("section") == "disease_vs_nondisease_main_evidence"]
    lines.extend(
        markdown_table(
            ["role", "rank", "feature", "direction", "pos_mean", "neg_mean", "diff", "d", "sep_auc"],
            [
                [
                    row.get("role", ""),
                    row.get("rank", ""),
                    row.get("feature_name", ""),
                    row.get("direction", ""),
                    row.get("positive_mean", ""),
                    row.get("negative_mean", ""),
                    row.get("mean_diff_positive_minus_negative", ""),
                    row.get("cohens_d", ""),
                    row.get("separation_auc", ""),
                ]
                for row in disease_rows
                if row.get("role") in {"all", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown"}
                if int(row.get("rank", 999)) <= 5
            ],
        )
    )
    lines.extend(["", "### 预测模型权重最高特征 Top", ""])
    model_rows = [row for row in feature_rows if row.get("section") == "prediction_model_top_weighted_features"]
    lines.extend(
        markdown_table(
            ["rank", "role", "feature", "family", "pos_mean", "neg_mean", "auc", "weight"],
            [
                [
                    row.get("rank", ""),
                    row.get("role", ""),
                    row.get("feature_name", ""),
                    row.get("feature_family", ""),
                    row.get("positive_mean", ""),
                    row.get("negative_mean", ""),
                    row.get("auc_positive_higher", ""),
                    row.get("feature_weight", ""),
                ]
                for row in model_rows[:12]
            ],
        )
    )
    lines.extend(["", "### HB Proxy Grade I-VI 差异 Top", ""])
    grade_rows = [row for row in feature_rows if row.get("section") == "hb_proxy_grade_i_to_vi_top_differences"]
    lines.extend(
        markdown_table(
            ["rank", "feature", "family", "Grade I", "Grade VI", "std_effect", "transition", "corr"],
            [
                [
                    row.get("rank", ""),
                    row.get("feature_name", ""),
                    row.get("feature_family", ""),
                    row.get("grade_i_mean", ""),
                    row.get("grade_vi_mean", ""),
                    row.get("standardized_i_to_vi_effect", ""),
                    row.get("strongest_adjacent_transition", ""),
                    row.get("grade_value_correlation", ""),
                ]
                for row in grade_rows[:12]
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 高分预测样本 Top 20",
            "",
        ]
    )
    high_score_rows = sorted(
        prediction_rows,
        key=lambda row: parse_float(row.get("v11_asymmetry_score")) or 0.0,
        reverse=True,
    )[:20]
    lines.extend(
        markdown_table(
            ["patient", "split", "label", "pred", "score", "grade", "face_output", "confusion"],
            [
                [
                    row.get("patient_sample_id", ""),
                    row.get("split", ""),
                    row.get("label_group", ""),
                    row.get("predicted_label", ""),
                    row.get("v11_asymmetry_score", ""),
                    row.get("hb_proxy_grade", ""),
                    row.get("face_asymmetry_output", ""),
                    row.get("confusion_cell", ""),
                ]
                for row in high_score_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            summary.get("interpretation_limit", ""),
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def ordered_metric_items(metrics: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    order = {"all": 0, "train": 1, "val": 2, "test": 3}
    return sorted(
        [(key, value) for key, value in metrics.items() if isinstance(value, Mapping)],
        key=lambda item: (order.get(item[0], 99), item[0]),
    )


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(item) for item in row) + " |")
    return output


def fmt(value: Any) -> str:
    parsed = parse_float(value)
    if parsed is None:
        return str(value if value is not None else "")
    return f"{parsed:.6f}"


if __name__ == "__main__":
    main()
