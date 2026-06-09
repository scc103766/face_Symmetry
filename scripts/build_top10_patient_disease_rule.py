#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


OUTPUT_PREFIX = "61_top10_patient_disease_rule"
TOP_N = 10
REQUIRED_TRIGGER_COUNT = 5


def main() -> None:
    args = parse_args()
    old_dataset = args.old_dataset.resolve()
    new_dataset = args.new_dataset.resolve()
    output = args.output.resolve()
    metadata = output / "metadata"
    reports = output / "reports"

    rules = load_top_rules(metadata / "60_combined_disease_feature_recommended_distinct.csv", args.top_n)
    feature_names = sorted({rule["feature_name"] for rule in rules})
    old_rows = load_feature_rows(old_dataset / "metadata" / "09_mediapipe_full_features.csv", "old")
    new_rows = load_feature_rows(new_dataset / "metadata" / "40_mediapipe_evidence_image_features.csv", "new")
    patient_rows_by_scope = build_all_patient_rows(old_rows, new_rows, feature_names)

    threshold_rows = build_threshold_rows(rules, patient_rows_by_scope)
    prediction_rows, attribution_rows = build_patient_predictions(
        rules,
        threshold_rows,
        patient_rows_by_scope,
        args.required_trigger_count,
    )
    metric_rows = build_metric_rows(prediction_rows)
    summary = build_summary(
        old_dataset=old_dataset,
        new_dataset=new_dataset,
        rules=rules,
        threshold_rows=threshold_rows,
        prediction_rows=prediction_rows,
        attribution_rows=attribution_rows,
        metric_rows=metric_rows,
        required_trigger_count=args.required_trigger_count,
    )

    write_csv(metadata / f"{OUTPUT_PREFIX}_feature_thresholds.csv", threshold_rows, threshold_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_patient_predictions.csv", prediction_rows, prediction_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_patient_feature_attributions.csv", attribution_rows, attribution_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_metrics.csv", metric_rows, metric_fields())
    write_json(metadata / f"{OUTPUT_PREFIX}_summary.json", summary)
    write_report(reports / f"{OUTPUT_PREFIX}.md", summary, threshold_rows, metric_rows, prediction_rows)

    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_feature_thresholds.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_patient_predictions.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_patient_feature_attributions.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_metrics.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_summary.json'}")
    print(f"Wrote {reports / f'{OUTPUT_PREFIX}.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a patient-level disease tendency rule from the top 10 combined disease feature candidates."
    )
    parser.add_argument("--old-dataset", type=Path, default=OLD_DATASET)
    parser.add_argument("--new-dataset", type=Path, default=NEW_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--required-trigger-count", type=int, default=REQUIRED_TRIGGER_COUNT)
    return parser.parse_args()


def load_top_rules(path: Path, top_n: int) -> list[dict[str, str]]:
    rows = [
        row
        for row in read_csv(path)
        if row.get("candidate_grade") == "recommended" and row.get("combined_direction") == "patient_higher"
    ]
    if len(rows) < top_n:
        raise ValueError(f"Need {top_n} recommended patient-higher rules, found {len(rows)} in {path}.")
    output: list[dict[str, str]] = []
    for index, row in enumerate(rows[:top_n], start=1):
        rule = dict(row)
        rule["rule_id"] = str(index)
        output.append(rule)
    return output


def build_threshold_rows(
    rules: list[Mapping[str, str]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for rule in rules:
        key = (rule["role_scope"], rule["aggregation"])
        rows = patient_rows_by_scope[key]
        threshold = select_threshold(rows, rule["feature_name"], rule["combined_direction"])
        threshold_value = threshold["threshold"]
        output.append(
            {
                "rule_id": rule["rule_id"],
                "feature_name": rule["feature_name"],
                "feature_type": rule["feature_type"],
                "role_scope": rule["role_scope"],
                "role_scope_description": rule["role_scope_description"],
                "aggregation": rule["aggregation"],
                "direction": rule["combined_direction"],
                "threshold": threshold_value,
                "threshold_rule": threshold_rule(rule["feature_name"], rule["combined_direction"], threshold_value),
                "old_directional_auc": rule["old_directional_auc"],
                "new_directional_auc": rule["new_directional_auc"],
                "combined_directional_auc": rule["combined_directional_auc"],
                "stability_score": rule["stability_score"],
                **threshold,
            }
        )
    return output


def build_patient_predictions(
    rules: list[Mapping[str, str]],
    thresholds: list[Mapping[str, str]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    required_trigger_count: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    thresholds_by_rule = {row["rule_id"]: row for row in thresholds}
    patient_lookup_by_rule: dict[str, dict[str, Mapping[str, Any]]] = {}
    all_patient_ids: set[str] = set()
    base_rows: dict[str, Mapping[str, Any]] = {}
    for rule in rules:
        rows = patient_rows_by_scope[(rule["role_scope"], rule["aggregation"])]
        lookup = {row["patient_sample_id"]: row for row in rows}
        patient_lookup_by_rule[rule["rule_id"]] = lookup
        all_patient_ids.update(lookup)
        for patient_id, row in lookup.items():
            base_rows.setdefault(patient_id, row)

    prediction_rows: list[dict[str, str]] = []
    attribution_rows: list[dict[str, str]] = []
    for patient_id in sorted(all_patient_ids):
        base = base_rows[patient_id]
        triggered: list[str] = []
        nontriggered: list[str] = []
        missing: list[str] = []
        for rule in rules:
            threshold = thresholds_by_rule[rule["rule_id"]]
            source_row = patient_lookup_by_rule[rule["rule_id"]].get(patient_id)
            value = to_float(source_row.get(rule["feature_name"])) if source_row else None
            threshold_value = float(threshold["threshold"])
            is_triggered = value is not None and value >= threshold_value
            status = "triggered" if is_triggered else "not_triggered"
            if value is None:
                status = "missing"
            reason_item = feature_reason(rule, value, threshold_value, status)
            if status == "triggered":
                triggered.append(reason_item)
            elif status == "missing":
                missing.append(reason_item)
            else:
                nontriggered.append(reason_item)
            attribution_rows.append(
                {
                    "patient_sample_id": patient_id,
                    "source_dataset": base["dataset_key"],
                    "source_patient_sample_id": base["source_patient_sample_id"],
                    "label_group": base["label_group"],
                    "label_binary": base["label_binary"],
                    "rule_id": rule["rule_id"],
                    "feature_name": rule["feature_name"],
                    "role_scope": rule["role_scope"],
                    "aggregation": rule["aggregation"],
                    "direction": rule["combined_direction"],
                    "feature_value": "" if value is None else fmt(value),
                    "threshold": threshold["threshold"],
                    "triggered": "true" if is_triggered else "false",
                    "status": status,
                    "reason": reason_item,
                }
            )

        triggered_count = len(triggered)
        scored_count = len(rules) - len(missing)
        predicted = triggered_count >= required_trigger_count
        prediction_rows.append(
            {
                "patient_sample_id": patient_id,
                "source_dataset": base["dataset_key"],
                "source_patient_sample_id": base["source_patient_sample_id"],
                "label_group": base["label_group"],
                "label_binary": base["label_binary"],
                "rule_feature_count": str(len(rules)),
                "required_trigger_count": str(required_trigger_count),
                "scored_feature_count": str(scored_count),
                "missing_feature_count": str(len(missing)),
                "triggered_feature_count": str(triggered_count),
                "nontriggered_feature_count": str(len(nontriggered)),
                "predicted_label_binary": "1" if predicted else "0",
                "predicted_label_group": "患病" if predicted else "不患病",
                "patient_disease_rule_output": "患病倾向较高" if predicted else "未达到患病阈值",
                "confusion_type": confusion_type(base["label_binary"], "1" if predicted else "0"),
                "triggered_features": ";".join(triggered),
                "missing_features": ";".join(missing),
                "patient_decision_reason": patient_reason(triggered_count, required_trigger_count, triggered, missing),
            }
        )
    return prediction_rows, attribution_rows


def feature_reason(rule: Mapping[str, str], value: float | None, threshold: float, status: str) -> str:
    label = f"#{rule['rule_id']} {rule['feature_name']}[{rule['role_scope']}/{rule['aggregation']}]"
    if value is None:
        return f"{label}: 缺失，无法计入"
    sign = ">=" if status == "triggered" else "<"
    return f"{label}: {fmt(value)} {sign} {fmt(threshold)}"


def patient_reason(
    triggered_count: int,
    required_trigger_count: int,
    triggered: list[str],
    missing: list[str],
) -> str:
    if triggered_count >= required_trigger_count:
        return (
            f"触发 {triggered_count}/10 个特征，达到至少 {required_trigger_count} 个特征超过阈值的规则；"
            f"触发原因：{'; '.join(triggered)}"
        )
    reason = f"仅触发 {triggered_count}/10 个特征，未达到至少 {required_trigger_count} 个特征超过阈值的规则"
    if missing:
        reason += f"；缺失特征：{'; '.join(missing)}"
    return reason


def build_metric_rows(predictions: list[Mapping[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for dataset_scope, scope_rows in [
        ("combined", predictions),
        ("old", [row for row in predictions if row["source_dataset"] == "old"]),
        ("new", [row for row in predictions if row["source_dataset"] == "new"]),
    ]:
        labels = [int(row["label_binary"]) for row in scope_rows]
        predicted = [row["predicted_label_binary"] == "1" for row in scope_rows]
        metrics = binary_metrics(labels, predicted)
        rows.append(
            {
                "dataset_scope": dataset_scope,
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
    rules: list[Mapping[str, str]],
    threshold_rows: list[Mapping[str, str]],
    prediction_rows: list[Mapping[str, str]],
    attribution_rows: list[Mapping[str, str]],
    metric_rows: list[Mapping[str, str]],
    required_trigger_count: int,
) -> dict[str, Any]:
    positives = [row for row in prediction_rows if row["predicted_label_binary"] == "1"]
    false_positives = [row for row in prediction_rows if row["confusion_type"] == "FP"]
    return {
        "old_dataset": old_dataset.as_posix(),
        "new_dataset": new_dataset.as_posix(),
        "rule_definition": f"patient is predicted as diseased when at least {required_trigger_count} of {len(rules)} selected features are >= their thresholds",
        "top_feature_count": len(rules),
        "required_trigger_count": required_trigger_count,
        "patient_count": len(prediction_rows),
        "attribution_row_count": len(attribution_rows),
        "predicted_positive_count": len(positives),
        "false_positive_count": len(false_positives),
        "predicted_positive_by_dataset": dict(sorted(Counter(row["source_dataset"] for row in positives).items())),
        "thresholds": list(threshold_rows),
        "metrics": list(metric_rows),
        "input_format": input_format_spec(),
        "warning": "Labels are patient outcome weak labels. This rule is a technical disease-tendency rule, not a clinical diagnosis rule.",
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    threshold_rows: list[Mapping[str, str]],
    metric_rows: list[Mapping[str, str]],
    prediction_rows: list[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    positive_examples = [row for row in prediction_rows if row["predicted_label_binary"] == "1"][:12]
    lines = [
        "# 61 十个联合特征患者级患病判断规则",
        "",
        "## 规则",
        "",
        "- 特征来源：60 阶段两批数据联合筛选后的去重推荐特征前 10 个。",
        "- 单特征阈值：每个特征在旧数据 + 新数据患者级聚合结果上单独搜索阈值，最大化 Youden J。",
        f"- 患者级结论：同一患者 `{summary['top_feature_count']}` 个特征中，至少 `{summary['required_trigger_count']}` 个特征值达到或超过各自阈值，则输出 `患病倾向较高`。",
        "- 判断原因：逐患者输出触发了哪些特征、患者特征值、阈值和 role/聚合口径。",
        "",
        "## 十个特征阈值",
        "",
    ]
    lines.extend(
        markdown_table(
            [
                "id",
                "feature",
                "role_scope",
                "agg",
                "threshold",
                "combined_bacc",
                "combined_precision",
                "combined_recall",
                "combined_specificity",
            ],
            [
                [
                    row["rule_id"],
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["threshold"],
                    row["combined_balanced_accuracy"],
                    row["combined_precision"],
                    row["combined_recall"],
                    row["combined_specificity"],
                ]
                for row in threshold_rows
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
    lines.extend(
        [
            "",
            "## 患病判断原因示例",
            "",
        ]
    )
    if positive_examples:
        lines.extend(
            markdown_table(
                ["patient", "dataset", "truth", "triggered", "reason"],
                [
                    [
                        row["source_patient_sample_id"],
                        row["source_dataset"],
                        row["label_group"],
                        row["triggered_feature_count"],
                        row["patient_decision_reason"],
                    ]
                    for row in positive_examples
                ],
            )
        )
    else:
        lines.append("当前没有患者达到患病倾向规则。")
    lines.extend(
        [
            "",
            "## 患者输入图片规范",
            "",
            "- 输入单位：按患者组织图片；一次判断需要同一患者的一组静态人脸图片。",
            "- 必需 role：`smile_teeth`，或旧 V1 兼容格式中的 `smile` + `teeth`。十个规则中多数特征来自该口部动态口径，缺失会导致特征无法计入。",
            "- 推荐 role：`front_contour`/`front` + `smile_teeth`/`smile,teeth` + `eyes_right`。这是当前新测试集和旧 V1 数据最接近的规范组合。",
            "- 图片类型：`.jpg`、`.jpeg`、`.png` 静态图片；视频、舌像、病历、辅助检查图不作为该规则的规范输入。",
            "- 人脸要求：单张图片应有清晰可见的单人脸，正向或接近正向，无遮挡，光照足够，嘴部/眉眼区域可见。",
            "- 检测要求：必须能通过 MediaPipe Face Landmarker，输出 `478` 个 raw landmarks、`52` 个 blendshapes 和 facial transformation matrix；检测失败或核心特征缺失的图片不能用于对应特征计分。",
            "- 数据字段：推理入口至少需要 `patient_sample_id`、`media_role`、`image_path`；训练/验证数据额外需要 `label_group` 或 `label_binary`。",
            "",
            "## 产物",
            "",
            f"- 十个特征阈值：`metadata/{OUTPUT_PREFIX}_feature_thresholds.csv`",
            f"- 逐患者判断：`metadata/{OUTPUT_PREFIX}_patient_predictions.csv`",
            f"- 逐患者特征归因：`metadata/{OUTPUT_PREFIX}_patient_feature_attributions.csv`",
            f"- 指标：`metadata/{OUTPUT_PREFIX}_metrics.csv`",
            f"- JSON 摘要：`metadata/{OUTPUT_PREFIX}_summary.json`",
            "",
            "## 限制",
            "",
            "该规则使用患者 outcome 弱标签拟合，不是临床诊断规则。当前结论应表述为 `患病倾向较高` 或 `人脸不对称相关弱监督阳性证据较多`，不能表述为确诊。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value).replace("\n", " ") for value in row) + " |")
    return output


def threshold_fields() -> list[str]:
    fields = [
        "rule_id",
        "feature_name",
        "feature_type",
        "role_scope",
        "role_scope_description",
        "aggregation",
        "direction",
        "threshold",
        "threshold_rule",
        "old_directional_auc",
        "new_directional_auc",
        "combined_directional_auc",
        "stability_score",
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


def prediction_fields() -> list[str]:
    return [
        "patient_sample_id",
        "source_dataset",
        "source_patient_sample_id",
        "label_group",
        "label_binary",
        "rule_feature_count",
        "required_trigger_count",
        "scored_feature_count",
        "missing_feature_count",
        "triggered_feature_count",
        "nontriggered_feature_count",
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
        "direction",
        "feature_value",
        "threshold",
        "triggered",
        "status",
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
