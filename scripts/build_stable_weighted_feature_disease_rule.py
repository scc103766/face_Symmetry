#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_v1_mediapipe_full_feature_differences import fmt  # noqa: E402
from scripts.find_combined_disease_feature_candidates import (  # noqa: E402
    DEFAULT_OUTPUT,
    NEW_DATASET,
    OLD_DATASET,
    ROLE_SCOPES,
    binary_metrics,
    build_all_patient_rows,
    load_feature_rows,
    read_csv,
    select_threshold,
    threshold_rule,
    to_float,
    write_csv,
    write_json,
)


OUTPUT_PREFIX = "62_stable_weighted_feature_disease_rule"
DEFAULT_FEATURE_COUNT = 21
SCORE_THRESHOLD_POLICY = "combined_patient_level_max_youden"
SCORE_THRESHOLD_POLICY_DESCRIPTION = (
    "在旧+新全部患者级加权得分上搜索阈值，按 Youden J、balanced accuracy、F1、precision、specificity、"
    "score_threshold 依次择优。"
)


def main() -> None:
    args = parse_args()
    old_dataset = args.old_dataset.resolve()
    new_dataset = args.new_dataset.resolve()
    output = args.output.resolve()
    metadata = output / "metadata"
    reports = output / "reports"

    candidate_rows = load_distinct_candidates(
        metadata / "60_combined_disease_feature_recommended_distinct.csv",
        args.feature_count,
    )
    feature_names = sorted({row["feature_name"] for row in candidate_rows})
    old_image_rows = load_feature_rows(old_dataset / "metadata" / "09_mediapipe_full_features.csv", "old")
    new_image_rows = load_feature_rows(new_dataset / "metadata" / "40_mediapipe_evidence_image_features.csv", "new")
    patient_rows_by_scope = build_all_patient_rows(old_image_rows, new_image_rows, feature_names)

    feature_rows = build_feature_weight_rows(candidate_rows, patient_rows_by_scope, old_image_rows, new_image_rows)
    normalize_feature_weights(feature_rows)
    prediction_rows, attribution_rows = build_patient_predictions(feature_rows, patient_rows_by_scope)
    score_threshold_rows, score_sweep_rows = select_score_threshold(prediction_rows)
    apply_score_threshold(prediction_rows, float(score_threshold_rows[0]["score_threshold"]))
    metric_rows = build_metric_rows(prediction_rows)
    summary = build_summary(
        old_dataset=old_dataset,
        new_dataset=new_dataset,
        feature_rows=feature_rows,
        prediction_rows=prediction_rows,
        attribution_rows=attribution_rows,
        score_threshold_rows=score_threshold_rows,
        metric_rows=metric_rows,
    )

    write_csv(metadata / f"{OUTPUT_PREFIX}_feature_weights.csv", feature_rows, feature_weight_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_score_threshold.csv", score_threshold_rows, score_threshold_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_score_threshold_sweep.csv", score_sweep_rows, score_sweep_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_patient_predictions.csv", prediction_rows, prediction_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_patient_feature_contributions.csv", attribution_rows, attribution_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_metrics.csv", metric_rows, metric_fields())
    write_json(metadata / f"{OUTPUT_PREFIX}_summary.json", summary)
    write_report(
        reports / f"{OUTPUT_PREFIX}.md",
        summary,
        feature_rows,
        score_threshold_rows[0],
        metric_rows,
        prediction_rows,
    )

    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_feature_weights.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_score_threshold.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_score_threshold_sweep.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_patient_predictions.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_patient_feature_contributions.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_metrics.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_summary.json'}")
    print(f"Wrote {reports / f'{OUTPUT_PREFIX}.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a stable weighted patient-level disease tendency rule from distinct recommended features."
    )
    parser.add_argument("--old-dataset", type=Path, default=OLD_DATASET)
    parser.add_argument("--new-dataset", type=Path, default=NEW_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--feature-count", type=int, default=DEFAULT_FEATURE_COUNT)
    return parser.parse_args()


def load_distinct_candidates(path: Path, feature_count: int) -> list[dict[str, str]]:
    rows = [
        row
        for row in read_csv(path)
        if row.get("candidate_grade") == "recommended" and row.get("combined_direction") == "patient_higher"
    ]
    if len(rows) < feature_count:
        raise ValueError(f"Need {feature_count} recommended patient-higher features, found {len(rows)} in {path}.")
    output: list[dict[str, str]] = []
    for index, row in enumerate(rows[:feature_count], start=1):
        item = dict(row)
        item["rule_id"] = str(index)
        output.append(item)
    return output


def build_feature_weight_rows(
    candidates: list[Mapping[str, str]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    old_image_rows: list[Mapping[str, str]],
    new_image_rows: list[Mapping[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        feature = candidate["feature_name"]
        scope = candidate["role_scope"]
        aggregation = candidate["aggregation"]
        patient_rows = patient_rows_by_scope[(scope, aggregation)]
        threshold_metrics = select_threshold(patient_rows, feature, candidate["combined_direction"])
        threshold = float(threshold_metrics["threshold"])
        image_stats = feature_image_stability(feature, scope, old_image_rows, new_image_rows, patient_rows)
        old_specificity = float(threshold_metrics["old_specificity"])
        new_specificity = float(threshold_metrics["new_specificity"])
        combined_specificity = float(threshold_metrics["combined_specificity"])
        min_specificity = min(old_specificity, new_specificity, combined_specificity)
        min_auc = min(float(candidate["old_directional_auc"]), float(candidate["new_directional_auc"]))
        combined_auc = float(candidate["combined_directional_auc"])
        separation_score = bounded((min_auc - 0.5) / 0.15)
        combined_auc_score = bounded((combined_auc - 0.5) / 0.15)
        nonpatient_score = bounded(min_specificity)
        volatility_score = image_stats["volatility_score"]
        row = {
            "rule_id": candidate["rule_id"],
            "feature_name": feature,
            "feature_type": candidate["feature_type"],
            "role_scope": scope,
            "role_scope_description": candidate["role_scope_description"],
            "aggregation": aggregation,
            "direction": candidate["combined_direction"],
            "threshold": fmt(threshold),
            "threshold_rule": threshold_rule(feature, candidate["combined_direction"], fmt(threshold)),
            "old_directional_auc": candidate["old_directional_auc"],
            "new_directional_auc": candidate["new_directional_auc"],
            "combined_directional_auc": candidate["combined_directional_auc"],
            "directional_auc_min": fmt(min_auc),
            "old_specificity": threshold_metrics["old_specificity"],
            "new_specificity": threshold_metrics["new_specificity"],
            "combined_specificity": threshold_metrics["combined_specificity"],
            "nonpatient_false_positive_rate": fmt(1.0 - combined_specificity),
            "stability_score_from_60": candidate["stability_score"],
            "separation_score": fmt(separation_score),
            "combined_auc_score": fmt(combined_auc_score),
            "nonpatient_specificity_score": fmt(nonpatient_score),
            **{key: fmt(value) if isinstance(value, float) else str(value) for key, value in image_stats.items()},
            **threshold_metrics,
        }
        raw_weight = (
            0.30 * separation_score
            + 0.20 * combined_auc_score
            + 0.25 * nonpatient_score
            + 0.15 * volatility_score
        )
        row["raw_weight_score"] = fmt(raw_weight)
        rows.append(row)

    max_count_score = max(float(row["image_count_score"]) for row in rows) if rows else 1.0
    for row in rows:
        count_score = safe_div(float(row["image_count_score"]), max_count_score)
        raw_weight = float(row["raw_weight_score"]) + 0.10 * count_score
        row["image_count_score"] = fmt(count_score)
        row["raw_weight_score"] = fmt(raw_weight)
    return rows


def feature_image_stability(
    feature: str,
    scope: str,
    old_image_rows: list[Mapping[str, str]],
    new_image_rows: list[Mapping[str, str]],
    patient_rows: list[Mapping[str, Any]],
) -> dict[str, Any]:
    old_scoped = filter_scope_rows(old_image_rows, ROLE_SCOPES[scope]["old"])
    new_scoped = filter_scope_rows(new_image_rows, ROLE_SCOPES[scope]["new"])
    combined_scoped = old_scoped + new_scoped
    values = [value for row in combined_scoped if (value := to_float(row.get(feature))) is not None]
    old_values = [value for row in old_scoped if (value := to_float(row.get(feature))) is not None]
    new_values = [value for row in new_scoped if (value := to_float(row.get(feature))) is not None]
    pos_patient = [float(row[feature]) for row in patient_rows if row.get("label_binary") == "1" and feature in row]
    neg_patient = [float(row[feature]) for row in patient_rows if row.get("label_binary") == "0" and feature in row]

    ordered = sorted(values)
    median = percentile(ordered, 0.5)
    q10 = percentile(ordered, 0.1)
    q25 = percentile(ordered, 0.25)
    q75 = percentile(ordered, 0.75)
    q90 = percentile(ordered, 0.9)
    iqr = q75 - q25
    robust_cv = iqr / max(abs(median), 1e-6)
    patient_gap = abs(percentile(sorted(pos_patient), 0.5) - percentile(sorted(neg_patient), 0.5))
    volatility_ratio = iqr / max(patient_gap, 1e-6)
    cv_score = 1.0 / (1.0 + min(robust_cv, 20.0))
    gap_volatility_score = 1.0 / (1.0 + min(volatility_ratio, 20.0))
    volatility_score = 0.35 * cv_score + 0.65 * gap_volatility_score
    image_count_score = math.log1p(len(values))
    return {
        "image_count": len(values),
        "old_image_count": len(old_values),
        "new_image_count": len(new_values),
        "image_mean": mean(values),
        "image_std": std(values),
        "image_p10": q10,
        "image_p25": q25,
        "image_median": median,
        "image_p75": q75,
        "image_p90": q90,
        "image_iqr": iqr,
        "patient_median_gap_abs": patient_gap,
        "image_robust_cv": robust_cv,
        "volatility_ratio_iqr_to_patient_gap": volatility_ratio,
        "volatility_score": volatility_score,
        "image_count_score": image_count_score,
    }


def normalize_feature_weights(rows: list[dict[str, Any]]) -> None:
    total = sum(float(row["raw_weight_score"]) for row in rows)
    for row in rows:
        weight = safe_div(float(row["raw_weight_score"]), total)
        row["feature_weight"] = fmt(weight)
        if weight >= 0.055:
            grade = "high"
        elif weight >= 0.045:
            grade = "medium"
        else:
            grade = "low"
        row["weight_grade"] = grade


def build_patient_predictions(
    feature_rows: list[Mapping[str, Any]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    lookups: dict[str, dict[str, Mapping[str, Any]]] = {}
    all_patient_ids: set[str] = set()
    base_rows: dict[str, Mapping[str, Any]] = {}
    for feature_row in feature_rows:
        rows = patient_rows_by_scope[(feature_row["role_scope"], feature_row["aggregation"])]
        lookup = {row["patient_sample_id"]: row for row in rows}
        lookups[feature_row["rule_id"]] = lookup
        all_patient_ids.update(lookup)
        for patient_id, row in lookup.items():
            base_rows.setdefault(patient_id, row)

    predictions: list[dict[str, str]] = []
    attributions: list[dict[str, str]] = []
    for patient_id in sorted(all_patient_ids):
        base = base_rows[patient_id]
        triggered: list[str] = []
        missing: list[str] = []
        score = 0.0
        scored_weight = 0.0
        triggered_weight = 0.0
        for feature_row in feature_rows:
            source = lookups[feature_row["rule_id"]].get(patient_id)
            value = to_float(source.get(feature_row["feature_name"])) if source else None
            threshold = float(feature_row["threshold"])
            weight = float(feature_row["feature_weight"])
            triggered_flag = value is not None and value >= threshold
            contribution = weight if triggered_flag else 0.0
            if value is None:
                missing.append(f"#{feature_row['rule_id']} {feature_row['feature_name']}")
            else:
                scored_weight += weight
            score += contribution
            if triggered_flag:
                triggered_weight += weight
                triggered.append(
                    f"#{feature_row['rule_id']} {feature_row['feature_name']}={fmt(value)}>=阈值{feature_row['threshold']} 权重{feature_row['feature_weight']}"
                )
            attributions.append(
                {
                    "patient_sample_id": patient_id,
                    "source_dataset": base["dataset_key"],
                    "source_patient_sample_id": base["source_patient_sample_id"],
                    "label_group": base["label_group"],
                    "label_binary": base["label_binary"],
                    "rule_id": feature_row["rule_id"],
                    "feature_name": feature_row["feature_name"],
                    "role_scope": feature_row["role_scope"],
                    "aggregation": feature_row["aggregation"],
                    "feature_value": "" if value is None else fmt(value),
                    "threshold": feature_row["threshold"],
                    "triggered": "true" if triggered_flag else "false",
                    "feature_weight": feature_row["feature_weight"],
                    "weighted_contribution": fmt(contribution),
                    "weight_grade": feature_row["weight_grade"],
                    "volatility_score": feature_row["volatility_score"],
                    "nonpatient_false_positive_rate": feature_row["nonpatient_false_positive_rate"],
                    "reason": attribution_reason(feature_row, value, triggered_flag),
                }
            )
        predictions.append(
            {
                "patient_sample_id": patient_id,
                "source_dataset": base["dataset_key"],
                "source_patient_sample_id": base["source_patient_sample_id"],
                "label_group": base["label_group"],
                "label_binary": base["label_binary"],
                "feature_count": str(len(feature_rows)),
                "triggered_feature_count": str(len(triggered)),
                "missing_feature_count": str(len(missing)),
                "scored_weight": fmt(scored_weight),
                "triggered_weight": fmt(triggered_weight),
                "weighted_disease_score": fmt(score),
                "triggered_features": ";".join(triggered),
                "missing_features": ";".join(missing),
                "patient_decision_reason": "",
            }
        )
    return predictions, attributions


def select_score_threshold(predictions: list[Mapping[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    pairs = sorted(
        [(float(row["weighted_disease_score"]), int(row["label_binary"])) for row in predictions],
        key=lambda item: item[0],
        reverse=True,
    )
    total_pos = sum(1 for _, label in pairs if label == 1)
    total_neg = len(pairs) - total_pos
    sweep: list[dict[str, str]] = []
    sweep.append(
        {
            "score_threshold": fmt(pairs[0][0] + 1e-12),
            "patient_count": str(len(pairs)),
            **binary_metrics_from_counts(0, 0, total_pos, total_neg),
        }
    )
    tp = fp = 0
    index = 0
    while index < len(pairs):
        threshold = pairs[index][0]
        while index < len(pairs) and pairs[index][0] == threshold:
            if pairs[index][1] == 1:
                tp += 1
            else:
                fp += 1
            index += 1
        sweep.append(
            {
                "score_threshold": fmt(threshold),
                "patient_count": str(len(pairs)),
                **binary_metrics_from_counts(tp, fp, total_pos, total_neg),
            }
        )
    selected = max(
        sweep,
        key=lambda row: (
            float(row["youden_j"]),
            float(row["balanced_accuracy"]),
            float(row["f1"]),
            float(row["precision"]),
            float(row["specificity"]),
            float(row["score_threshold"]),
        ),
    )
    selected = dict(selected)
    selected["threshold_policy"] = SCORE_THRESHOLD_POLICY
    selected["threshold_policy_description"] = SCORE_THRESHOLD_POLICY_DESCRIPTION
    return [selected], sweep


def apply_score_threshold(predictions: list[dict[str, str]], threshold: float) -> None:
    for row in predictions:
        predicted = float(row["weighted_disease_score"]) >= threshold
        row["score_threshold"] = fmt(threshold)
        row["predicted_label_binary"] = "1" if predicted else "0"
        row["predicted_label_group"] = "患病" if predicted else "不患病"
        row["patient_disease_rule_output"] = "患病倾向较高" if predicted else "未达到患病阈值"
        row["confusion_type"] = confusion_type(row["label_binary"], row["predicted_label_binary"])
        if predicted:
            row["patient_decision_reason"] = (
                f"加权得分 {row['weighted_disease_score']} >= 阈值 {row['score_threshold']}；"
                f"触发 {row['triggered_feature_count']}/21 个特征，触发权重 {row['triggered_weight']}。"
                f"主要原因：{row['triggered_features']}"
            )
        else:
            row["patient_decision_reason"] = (
                f"加权得分 {row['weighted_disease_score']} < 阈值 {row['score_threshold']}；"
                f"仅触发 {row['triggered_feature_count']}/21 个特征，触发权重 {row['triggered_weight']}。"
            )


def build_metric_rows(predictions: list[Mapping[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for scope, scope_rows in [
        ("combined", predictions),
        ("old", [row for row in predictions if row["source_dataset"] == "old"]),
        ("new", [row for row in predictions if row["source_dataset"] == "new"]),
    ]:
        labels = [int(row["label_binary"]) for row in scope_rows]
        predicted = [row["predicted_label_binary"] == "1" for row in scope_rows]
        metrics = binary_metrics(labels, predicted)
        rows.append(
            {
                "dataset_scope": scope,
                "patient_count": str(len(scope_rows)),
                **metrics,
                "predicted_positive_count": str(sum(1 for row in scope_rows if row["predicted_label_binary"] == "1")),
                "predicted_negative_count": str(sum(1 for row in scope_rows if row["predicted_label_binary"] == "0")),
                "actual_positive_count": str(sum(1 for row in scope_rows if row["label_binary"] == "1")),
                "actual_negative_count": str(sum(1 for row in scope_rows if row["label_binary"] == "0")),
            }
        )
    return rows


def build_summary(
    *,
    old_dataset: Path,
    new_dataset: Path,
    feature_rows: list[Mapping[str, Any]],
    prediction_rows: list[Mapping[str, str]],
    attribution_rows: list[Mapping[str, str]],
    score_threshold_rows: list[Mapping[str, str]],
    metric_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    positives = [row for row in prediction_rows if row["predicted_label_binary"] == "1"]
    false_positives = [row for row in prediction_rows if row["confusion_type"] == "FP"]
    return {
        "old_dataset": old_dataset.as_posix(),
        "new_dataset": new_dataset.as_posix(),
        "rule_definition": "Use all distinct recommended features. Each feature has its own threshold and stability/nonpatient-aware weight; disease tendency is predicted from weighted triggered score.",
        "feature_count": len(feature_rows),
        "score_threshold": score_threshold_rows[0]["score_threshold"],
        "score_threshold_policy": score_threshold_rows[0]["threshold_policy"],
        "score_threshold_policy_description": score_threshold_rows[0]["threshold_policy_description"],
        "patient_count": len(prediction_rows),
        "attribution_row_count": len(attribution_rows),
        "predicted_positive_count": len(positives),
        "false_positive_count": len(false_positives),
        "predicted_positive_by_dataset": dict(sorted(Counter(row["source_dataset"] for row in positives).items())),
        "weight_policy": {
            "separation_score": "old/new min directional AUC, scaled above random baseline",
            "combined_auc_score": "combined directional AUC, scaled above random baseline",
            "nonpatient_specificity_score": "minimum old/new/combined specificity at the feature threshold",
            "volatility_score": "image-level robust volatility penalty from IQR, robust CV, and patient median gap",
            "image_count_score": "log image count factor",
        },
        "top_high_weight_features": [
            {
                "feature_name": row["feature_name"],
                "feature_weight": row["feature_weight"],
                "weight_grade": row["weight_grade"],
                "volatility_score": row["volatility_score"],
                "nonpatient_false_positive_rate": row["nonpatient_false_positive_rate"],
                "threshold": row["threshold"],
            }
            for row in sorted(feature_rows, key=lambda item: float(item["feature_weight"]), reverse=True)[:10]
        ],
        "metrics": metric_rows,
        "input_format": input_format_spec(),
        "warning": "Labels are patient outcome weak labels. This is not a clinical diagnosis rule.",
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    feature_rows: list[Mapping[str, Any]],
    score_threshold: Mapping[str, str],
    metric_rows: list[Mapping[str, str]],
    predictions: list[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_features = sorted(feature_rows, key=lambda row: float(row["feature_weight"]), reverse=True)
    positive_examples = [row for row in predictions if row["predicted_label_binary"] == "1"][:10]
    lines = [
        "# 62 稳定性加权特征患病判断规则",
        "",
        "## 方法",
        "",
        "- 特征来源：60 阶段去重后的 21 个推荐特征。",
        "- 单特征阈值：每个特征在两批数据的患者级聚合值上搜索阈值。",
        "- 不患病表现：每个特征都计算旧/新/合并 specificity 和不患病误判率，非患者中越少超过阈值权重越高。",
        "- 图片波动性：在对应 role scope 的所有图片上计算 IQR、robust CV、IQR/患者中位数差距；波动越大权重越低。",
        "- 图片总数：图片数越多，证据稳定性越高，权重有小幅增加。",
        "- 权重公式：`0.30*跨数据AUC稳定分 + 0.20*合并AUC分 + 0.25*非患者specificity分 + 0.15*图片波动稳定分 + 0.10*图片数分`，之后归一化为总和 1。",
        "- 特征触发：仅使用理论和数据上均表现为患者更高的特征；患者级特征值 `>=` 单特征阈值时贡献该特征权重。",
        "- 患者判断：所有特征按权重累计，触发特征的权重相加得到 `weighted_disease_score`。",
        f"- 加权总分阈值选择：{score_threshold['threshold_policy_description']}",
        f"- 当前加权总分阈值：`weighted_disease_score >= {score_threshold['score_threshold']}` 输出 `患病倾向较高`。",
        "",
        "## 特征权重",
        "",
    ]
    lines.extend(
        markdown_table(
            [
                "rank",
                "feature",
                "role",
                "agg",
                "threshold",
                "weight",
                "grade",
                "nonpatient_fp_rate",
                "volatility_score",
                "image_count",
            ],
            [
                [
                    index + 1,
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["threshold"],
                    row["feature_weight"],
                    row["weight_grade"],
                    row["nonpatient_false_positive_rate"],
                    row["volatility_score"],
                    row["image_count"],
                ]
                for index, row in enumerate(sorted_features)
            ],
        )
    )
    lines.extend(["", "## 患者级表现", ""])
    lines.extend(
        markdown_table(
            ["dataset", "patients", "TP", "FP", "TN", "FN", "precision", "recall", "specificity", "bacc"],
            [
                [
                    row["dataset_scope"],
                    row["patient_count"],
                    row["tp"],
                    row["fp"],
                    row["tn"],
                    row["fn"],
                    row["precision"],
                    row["recall"],
                    row["specificity"],
                    row["balanced_accuracy"],
                ]
                for row in metric_rows
            ],
        )
    )
    lines.extend(["", "## 判断原因示例", ""])
    if positive_examples:
        lines.extend(
            markdown_table(
                ["patient", "dataset", "truth", "score", "triggered", "reason"],
                [
                    [
                        row["source_patient_sample_id"],
                        row["source_dataset"],
                        row["label_group"],
                        row["weighted_disease_score"],
                        row["triggered_feature_count"],
                        row["patient_decision_reason"],
                    ]
                    for row in positive_examples
                ],
            )
        )
    else:
        lines.append("当前没有患者达到加权患病阈值。")
    lines.extend(
        [
            "",
            "## 规范输入图片格式",
            "",
            "- 输入单位：同一患者的一组静态人脸图片。",
            "- 必需 role：`smile_teeth`，或旧 V1 兼容格式的 `smile + teeth`；多数高权重特征来自口部动态口径。",
            "- 推荐 role：`front_contour/front + smile_teeth/smile,teeth + eyes_right`。",
            "- 文件格式：`.jpg`、`.jpeg`、`.png`。",
            "- 排除：视频、舌像、病历图、辅助检查图。",
            "- 单图要求：清晰单人脸，正向或接近正向，嘴部、眉眼区域无遮挡，光照足够。",
            "- MediaPipe 要求：必须能输出 `478` 个 raw landmarks、`52` 个 blendshapes、至少 1 个 facial transformation matrix。",
            "- 推理字段：至少包含 `patient_sample_id`、`media_role`、`image_path`；训练验证时额外包含 `label_binary` 或 `label_group`。",
            "",
            "## 产物",
            "",
            f"- 特征权重：`metadata/{OUTPUT_PREFIX}_feature_weights.csv`",
            f"- 加权分阈值：`metadata/{OUTPUT_PREFIX}_score_threshold.csv`",
            f"- 患者判断：`metadata/{OUTPUT_PREFIX}_patient_predictions.csv`",
            f"- 患者特征贡献：`metadata/{OUTPUT_PREFIX}_patient_feature_contributions.csv`",
            f"- 指标：`metadata/{OUTPUT_PREFIX}_metrics.csv`",
            f"- JSON 摘要：`metadata/{OUTPUT_PREFIX}_summary.json`",
            "",
            "## 限制",
            "",
            "该规则使用患者 outcome 弱标签拟合，只能作为技术判断与归因候选，不能作为临床诊断结论。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def filter_scope_rows(rows: list[Mapping[str, str]], roles: set[str] | None) -> list[Mapping[str, str]]:
    if roles is None:
        return rows
    return [row for row in rows if row.get("media_role") in roles]


def attribution_reason(feature_row: Mapping[str, Any], value: float | None, triggered: bool) -> str:
    if value is None:
        return f"{feature_row['feature_name']} 缺失，未计入"
    op = ">=" if triggered else "<"
    return (
        f"{feature_row['feature_name']}={fmt(value)} {op} 阈值{feature_row['threshold']}；"
        f"权重{feature_row['feature_weight']}，波动分{feature_row['volatility_score']}，"
        f"不患病误判率{feature_row['nonpatient_false_positive_rate']}"
    )


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


def input_format_spec() -> dict[str, Any]:
    return {
        "unit": "patient image set",
        "required_roles": ["smile_teeth"],
        "legacy_compatible_roles": ["smile", "teeth"],
        "recommended_roles": ["front_contour/front", "smile_teeth or smile+teeth", "eyes_right"],
        "image_extensions": [".jpg", ".jpeg", ".png"],
        "excluded_inputs": ["video", "tongue image", "medical record image", "auxiliary exam image"],
        "mediapipe_required_outputs": {
            "raw_landmarks": 478,
            "blendshapes": 52,
            "facial_transformation_matrixes": ">=1",
        },
        "minimum_inference_fields": ["patient_sample_id", "media_role", "image_path"],
        "validation_label_fields": ["label_group", "label_binary"],
    }


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


def bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if not values:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((value - m) ** 2 for value in values) / len(values))


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


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value).replace("\n", " ") for value in row) + " |")
    return output


def feature_weight_fields() -> list[str]:
    fields = [
        "rule_id",
        "feature_name",
        "feature_type",
        "role_scope",
        "aggregation",
        "direction",
        "threshold",
        "feature_weight",
        "weight_grade",
        "raw_weight_score",
        "separation_score",
        "combined_auc_score",
        "nonpatient_specificity_score",
        "nonpatient_false_positive_rate",
        "volatility_score",
        "image_count_score",
        "image_count",
        "old_image_count",
        "new_image_count",
        "image_mean",
        "image_std",
        "image_median",
        "image_iqr",
        "patient_median_gap_abs",
        "image_robust_cv",
        "volatility_ratio_iqr_to_patient_gap",
        "old_directional_auc",
        "new_directional_auc",
        "combined_directional_auc",
        "old_specificity",
        "new_specificity",
        "combined_specificity",
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
    fields.extend(["threshold_rule", "role_scope_description"])
    return fields


def score_threshold_fields() -> list[str]:
    return [
        "threshold_policy",
        "threshold_policy_description",
        "score_threshold",
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


def score_sweep_fields() -> list[str]:
    return [
        "score_threshold",
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


def prediction_fields() -> list[str]:
    return [
        "patient_sample_id",
        "source_dataset",
        "source_patient_sample_id",
        "label_group",
        "label_binary",
        "feature_count",
        "triggered_feature_count",
        "missing_feature_count",
        "scored_weight",
        "triggered_weight",
        "weighted_disease_score",
        "score_threshold",
        "predicted_label_binary",
        "predicted_label_group",
        "patient_disease_rule_output",
        "confusion_type",
        "triggered_features",
        "missing_features",
        "patient_decision_reason",
    ]


def attribution_fields() -> list[str]:
    return [
        "patient_sample_id",
        "source_dataset",
        "source_patient_sample_id",
        "label_group",
        "label_binary",
        "rule_id",
        "feature_name",
        "role_scope",
        "aggregation",
        "feature_value",
        "threshold",
        "triggered",
        "feature_weight",
        "weighted_contribution",
        "weight_grade",
        "volatility_score",
        "nonpatient_false_positive_rate",
        "reason",
    ]


def metric_fields() -> list[str]:
    return [
        "dataset_scope",
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
        "predicted_positive_count",
        "predicted_negative_count",
        "actual_positive_count",
        "actual_negative_count",
    ]


if __name__ == "__main__":
    main()
