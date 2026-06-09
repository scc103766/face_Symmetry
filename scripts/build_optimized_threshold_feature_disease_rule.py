#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_v1_mediapipe_full_feature_differences import fmt  # noqa: E402
from scripts.build_stable_weighted_feature_disease_rule import (  # noqa: E402
    attribution_fields,
    bounded,
    build_patient_predictions,
    feature_image_stability,
    markdown_table,
    prediction_fields,
    safe_div,
)
from scripts.find_combined_disease_feature_candidates import (  # noqa: E402
    DEFAULT_OUTPUT,
    NEW_DATASET,
    OLD_DATASET,
    apply_threshold_metrics,
    binary_metrics,
    build_all_patient_rows,
    load_feature_rows,
    percentile,
    read_csv,
    select_threshold,
    to_float,
    write_csv,
    write_json,
)


OUTPUT_PREFIX = "63_optimized_threshold_feature_disease_rule"
DEFAULT_FEATURE_COUNT = 21
NONPATIENT_REFERENCE_QUANTILE = 0.85
BOOTSTRAP_ROUNDS = 120
SPECIFICITY_FLOORS = (0.0, 0.50, 0.60, 0.70, 0.75, 0.80)
PRIMARY_SPECIFICITY_FLOOR = 0.50


def main() -> None:
    args = parse_args()
    old_dataset = args.old_dataset.resolve()
    new_dataset = args.new_dataset.resolve()
    output = args.output.resolve()
    metadata = output / "metadata"
    reports = output / "reports"

    distinct_candidates = load_distinct_candidates(
        metadata / "60_combined_disease_feature_recommended_distinct.csv",
        args.feature_count,
    )
    feature_names = [row["feature_name"] for row in distinct_candidates]
    old_image_rows = load_feature_rows(old_dataset / "metadata" / "09_mediapipe_full_features.csv", "old")
    new_image_rows = load_feature_rows(new_dataset / "metadata" / "40_mediapipe_evidence_image_features.csv", "new")
    patient_rows_by_scope = build_all_patient_rows(old_image_rows, new_image_rows, sorted(set(feature_names)))
    all_metric_rows = read_csv(metadata / "60_combined_disease_feature_all_metrics.csv")

    feature_rows, search_rows = build_optimized_feature_rows(
        distinct_candidates=distinct_candidates,
        all_metric_rows=all_metric_rows,
        patient_rows_by_scope=patient_rows_by_scope,
        old_image_rows=old_image_rows,
        new_image_rows=new_image_rows,
        nonpatient_reference_quantile=args.nonpatient_reference_quantile,
        bootstrap_rounds=args.bootstrap_rounds,
    )
    normalize_feature_weights(feature_rows)
    prediction_rows, attribution_rows = build_patient_predictions(feature_rows, patient_rows_by_scope)
    threshold_rows, threshold_sweep_rows = select_score_thresholds(prediction_rows)
    primary_threshold = float(threshold_rows[0]["score_threshold"])
    apply_score_threshold(prediction_rows, primary_threshold, len(feature_rows))
    metric_rows = build_metric_rows(prediction_rows)
    baseline_metric_rows = load_baseline_metric_rows(metadata / "62_stable_weighted_feature_disease_rule_metrics.csv")
    summary = build_summary(
        old_dataset=old_dataset,
        new_dataset=new_dataset,
        nonpatient_reference_quantile=args.nonpatient_reference_quantile,
        bootstrap_rounds=args.bootstrap_rounds,
        feature_rows=feature_rows,
        search_rows=search_rows,
        prediction_rows=prediction_rows,
        attribution_rows=attribution_rows,
        threshold_rows=threshold_rows,
        metric_rows=metric_rows,
        baseline_metric_rows=baseline_metric_rows,
    )

    write_csv(metadata / f"{OUTPUT_PREFIX}_feature_thresholds.csv", feature_rows, feature_threshold_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_role_scope_search.csv", search_rows, role_scope_search_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_score_threshold_policies.csv", threshold_rows, score_threshold_policy_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_score_threshold_sweep.csv", threshold_sweep_rows, score_threshold_sweep_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_patient_predictions.csv", prediction_rows, prediction_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_patient_feature_contributions.csv", attribution_rows, attribution_fields())
    write_csv(metadata / f"{OUTPUT_PREFIX}_metrics.csv", metric_rows, metric_fields())
    write_json(metadata / f"{OUTPUT_PREFIX}_summary.json", summary)
    write_report(
        reports / f"{OUTPUT_PREFIX}.md",
        summary,
        feature_rows,
        threshold_rows,
        metric_rows,
        baseline_metric_rows,
    )

    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_feature_thresholds.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_role_scope_search.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_score_threshold_policies.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_score_threshold_sweep.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_patient_predictions.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_patient_feature_contributions.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_metrics.csv'}")
    print(f"Wrote {metadata / f'{OUTPUT_PREFIX}_summary.json'}")
    print(f"Wrote {reports / f'{OUTPUT_PREFIX}.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build optimized role-specific, threshold-stability-screened, nonpatient-reference thresholds."
    )
    parser.add_argument("--old-dataset", type=Path, default=OLD_DATASET)
    parser.add_argument("--new-dataset", type=Path, default=NEW_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--feature-count", type=int, default=DEFAULT_FEATURE_COUNT)
    parser.add_argument("--nonpatient-reference-quantile", type=float, default=NONPATIENT_REFERENCE_QUANTILE)
    parser.add_argument("--bootstrap-rounds", type=int, default=BOOTSTRAP_ROUNDS)
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


def build_optimized_feature_rows(
    *,
    distinct_candidates: list[Mapping[str, str]],
    all_metric_rows: list[Mapping[str, str]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    old_image_rows: list[Mapping[str, str]],
    new_image_rows: list[Mapping[str, str]],
    nonpatient_reference_quantile: float,
    bootstrap_rounds: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    metric_rows_by_feature: dict[str, list[Mapping[str, str]]] = {}
    for row in all_metric_rows:
        metric_rows_by_feature.setdefault(row["feature_name"], []).append(row)

    selected_rows: list[dict[str, Any]] = []
    search_rows: list[dict[str, Any]] = []
    for candidate in distinct_candidates:
        feature = candidate["feature_name"]
        option_rows: list[dict[str, Any]] = []
        for metric_row in metric_rows_by_feature.get(feature, []):
            if not is_patient_higher_role_option(metric_row):
                continue
            scope = metric_row["role_scope"]
            aggregation = metric_row["aggregation"]
            patient_rows = patient_rows_by_scope[(scope, aggregation)]
            option = build_role_option_row(
                candidate=candidate,
                metric_row=metric_row,
                patient_rows=patient_rows,
                old_image_rows=old_image_rows,
                new_image_rows=new_image_rows,
                nonpatient_reference_quantile=nonpatient_reference_quantile,
                bootstrap_rounds=bootstrap_rounds,
            )
            option_rows.append(option)
            search_rows.append(option)
        if not option_rows:
            raise ValueError(f"No patient-higher role-specific option found for {feature}.")
        selected = max(
            option_rows,
            key=lambda row: (
                float(row["role_selection_score"]),
                row["role_scope"] != "all",
                float(row["threshold_stability_score"]),
                float(row["new_balanced_accuracy"]),
                float(row["old_balanced_accuracy"]),
            ),
        )
        selected = dict(selected)
        selected["selected_for_rule"] = "true"
        selected_rows.append(selected)
        for row in option_rows:
            row["selected_for_rule"] = "true" if is_same_role_option(row, selected) else "false"
    return selected_rows, search_rows


def is_same_role_option(row: Mapping[str, Any], selected: Mapping[str, Any]) -> bool:
    return (
        row["feature_name"] == selected["feature_name"]
        and row["role_scope"] == selected["role_scope"]
        and row["aggregation"] == selected["aggregation"]
        and row["threshold"] == selected["threshold"]
    )


def is_patient_higher_role_option(row: Mapping[str, str]) -> bool:
    return (
        row.get("direction_consistent") == "true"
        and row.get("combined_direction") == "patient_higher"
        and row.get("old_direction") == "patient_higher"
        and row.get("new_direction") == "patient_higher"
        and row.get("combined_mean_direction") == "patient_higher"
        and row.get("old_mean_direction") == "patient_higher"
        and row.get("new_mean_direction") == "patient_higher"
    )


def build_role_option_row(
    *,
    candidate: Mapping[str, str],
    metric_row: Mapping[str, str],
    patient_rows: list[dict[str, Any]],
    old_image_rows: list[Mapping[str, str]],
    new_image_rows: list[Mapping[str, str]],
    nonpatient_reference_quantile: float,
    bootstrap_rounds: int,
) -> dict[str, Any]:
    feature = candidate["feature_name"]
    scope = metric_row["role_scope"]
    aggregation = metric_row["aggregation"]
    threshold_info = optimized_feature_threshold(patient_rows, feature, nonpatient_reference_quantile)
    threshold = float(threshold_info["threshold"])
    image_stats = feature_image_stability(feature, scope, old_image_rows, new_image_rows, patient_rows)
    stability = bootstrap_threshold_stability(
        patient_rows,
        feature,
        nonpatient_reference_quantile,
        bootstrap_rounds,
        seed=stable_seed(feature, scope, aggregation),
    )
    old_specificity = float(threshold_info["old_specificity"])
    new_specificity = float(threshold_info["new_specificity"])
    combined_specificity = float(threshold_info["combined_specificity"])
    min_specificity = min(old_specificity, new_specificity, combined_specificity)
    min_auc = min(float(metric_row["old_directional_auc"]), float(metric_row["new_directional_auc"]))
    combined_auc = float(metric_row["combined_directional_auc"])
    avg_youden = (float(threshold_info["old_youden_j"]) + float(threshold_info["new_youden_j"])) / 2.0
    role_bonus = 0.03 if scope != "all" else 0.0
    role_selection_score = (
        0.25 * bounded((min_auc - 0.5) / 0.15)
        + 0.20 * bounded((combined_auc - 0.5) / 0.15)
        + 0.15 * bounded(min_specificity)
        + 0.15 * float(stability["threshold_stability_score"])
        + 0.15 * float(image_stats["volatility_score"])
        + 0.10 * bounded((avg_youden + 0.20) / 0.50)
        + role_bonus
    )
    stability_multiplier = threshold_stability_multiplier(float(stability["threshold_stability_score"]))
    raw_weight_score = role_selection_score * stability_multiplier
    row = {
        "rule_id": candidate["rule_id"],
        "feature_name": feature,
        "feature_type": candidate["feature_type"],
        "role_scope": scope,
        "role_scope_description": metric_row["role_scope_description"],
        "aggregation": aggregation,
        "original_role_scope": candidate["role_scope"],
        "original_aggregation": candidate["aggregation"],
        "direction": "patient_higher",
        "threshold": fmt(threshold),
        "threshold_policy": "max(combined_youden_threshold, old/new/combined_nonpatient_reference_quantile)",
        "nonpatient_reference_quantile": fmt(nonpatient_reference_quantile),
        "old_directional_auc": metric_row["old_directional_auc"],
        "new_directional_auc": metric_row["new_directional_auc"],
        "combined_directional_auc": metric_row["combined_directional_auc"],
        "directional_auc_min": fmt(min_auc),
        "role_selection_score": fmt(role_selection_score),
        "raw_weight_score": fmt(raw_weight_score),
        "threshold_stability_multiplier": fmt(stability_multiplier),
        "threshold_stability_grade": threshold_stability_grade(float(stability["threshold_stability_score"])),
        "nonpatient_false_positive_rate": fmt(1.0 - combined_specificity),
        "old_specificity": threshold_info["old_specificity"],
        "new_specificity": threshold_info["new_specificity"],
        "combined_specificity": threshold_info["combined_specificity"],
        **threshold_info,
        **stability,
        **{key: fmt(value) if isinstance(value, float) else str(value) for key, value in image_stats.items()},
    }
    return row


def optimized_feature_threshold(
    rows: list[Mapping[str, Any]],
    feature: str,
    nonpatient_reference_quantile: float,
) -> dict[str, str]:
    youden_metrics = select_threshold(rows, feature, "patient_higher")
    youden_threshold = float(youden_metrics["threshold"])
    old_nonpatient = values_for(rows, feature, dataset_key="old", label_binary="0")
    new_nonpatient = values_for(rows, feature, dataset_key="new", label_binary="0")
    combined_nonpatient = old_nonpatient + new_nonpatient
    old_reference = percentile(sorted(old_nonpatient), nonpatient_reference_quantile) if old_nonpatient else 0.0
    new_reference = percentile(sorted(new_nonpatient), nonpatient_reference_quantile) if new_nonpatient else 0.0
    combined_reference = (
        percentile(sorted(combined_nonpatient), nonpatient_reference_quantile) if combined_nonpatient else 0.0
    )
    reference_threshold = max(old_reference, new_reference, combined_reference)
    threshold = max(youden_threshold, reference_threshold)
    combined_metrics = apply_threshold_metrics(rows, feature, "patient_higher", threshold)
    old_metrics = apply_threshold_metrics([row for row in rows if row["dataset_key"] == "old"], feature, "patient_higher", threshold)
    new_metrics = apply_threshold_metrics([row for row in rows if row["dataset_key"] == "new"], feature, "patient_higher", threshold)
    return {
        "youden_threshold": fmt(youden_threshold),
        "old_nonpatient_reference_threshold": fmt(old_reference),
        "new_nonpatient_reference_threshold": fmt(new_reference),
        "combined_nonpatient_reference_threshold": fmt(combined_reference),
        "nonpatient_reference_threshold": fmt(reference_threshold),
        "threshold": fmt(threshold),
        **prefixed("combined", combined_metrics),
        **prefixed("old", old_metrics),
        **prefixed("new", new_metrics),
    }


def bootstrap_threshold_stability(
    rows: list[Mapping[str, Any]],
    feature: str,
    nonpatient_reference_quantile: float,
    rounds: int,
    seed: int,
) -> dict[str, str]:
    eligible = [row for row in rows if feature in row and to_float(row.get(feature)) is not None]
    if len(eligible) < 20:
        return {
            "threshold_bootstrap_rounds": "0",
            "threshold_bootstrap_valid_rounds": "0",
            "threshold_bootstrap_median": "",
            "threshold_bootstrap_iqr": "",
            "threshold_patient_median_gap_abs": "",
            "threshold_iqr_to_patient_gap": "",
            "threshold_stability_score": "0.000000",
        }
    rng = random.Random(seed)
    thresholds: list[float] = []
    for _ in range(rounds):
        sample = [eligible[rng.randrange(len(eligible))] for _ in range(len(eligible))]
        if len({row["label_binary"] for row in sample}) < 2:
            continue
        try:
            threshold = optimized_feature_threshold(sample, feature, nonpatient_reference_quantile)["threshold"]
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        if (value := to_float(threshold)) is not None:
            thresholds.append(value)
    positive_values = [float(row[feature]) for row in eligible if row.get("label_binary") == "1"]
    negative_values = [float(row[feature]) for row in eligible if row.get("label_binary") == "0"]
    threshold_iqr = iqr(thresholds)
    patient_gap = abs(median(positive_values) - median(negative_values))
    ratio = threshold_iqr / max(patient_gap, 1e-6)
    stability_score = 1.0 / (1.0 + min(ratio, 20.0))
    return {
        "threshold_bootstrap_rounds": str(rounds),
        "threshold_bootstrap_valid_rounds": str(len(thresholds)),
        "threshold_bootstrap_median": fmt(median(thresholds)),
        "threshold_bootstrap_iqr": fmt(threshold_iqr),
        "threshold_patient_median_gap_abs": fmt(patient_gap),
        "threshold_iqr_to_patient_gap": fmt(ratio),
        "threshold_stability_score": fmt(stability_score),
    }


def threshold_stability_multiplier(score: float) -> float:
    if score < 0.25:
        return 0.25
    if score < 0.50:
        return 0.70
    return 1.0


def threshold_stability_grade(score: float) -> str:
    if score < 0.25:
        return "screened_down"
    if score < 0.50:
        return "low"
    return "stable"


def stable_seed(*parts: str) -> int:
    return sum((index + 1) * ord(char) for index, text in enumerate(parts) for char in text)


def values_for(
    rows: list[Mapping[str, Any]],
    feature: str,
    *,
    dataset_key: str | None = None,
    label_binary: str | None = None,
) -> list[float]:
    output: list[float] = []
    for row in rows:
        if dataset_key is not None and row.get("dataset_key") != dataset_key:
            continue
        if label_binary is not None and row.get("label_binary") != label_binary:
            continue
        value = to_float(row.get(feature))
        if value is not None:
            output.append(value)
    return output


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


def select_score_thresholds(
    predictions: list[Mapping[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    sweep = build_score_threshold_sweep(predictions)
    policy_rows: list[dict[str, str]] = []
    for floor in SPECIFICITY_FLOORS:
        candidates = [
            row
            for row in sweep
            if float(row["old_specificity"]) + 1e-12 >= floor
            and float(row["new_specificity"]) + 1e-12 >= floor
        ]
        if not candidates:
            continue
        selected = max(
            candidates,
            key=lambda row: (
                float(row["average_old_new_youden_j"]),
                float(row["new_balanced_accuracy"]),
                float(row["combined_balanced_accuracy"]),
                float(row["combined_precision"]),
                float(row["score_threshold"]),
            ),
        )
        policy_rows.append(
            {
                "threshold_policy": (
                    "balanced_old_new_youden"
                    if floor == 0.0
                    else f"balanced_old_new_youden_with_old_new_specificity_floor_{fmt(floor)}"
                ),
                "specificity_floor": fmt(floor),
                "is_primary": "true" if abs(floor - PRIMARY_SPECIFICITY_FLOOR) < 1e-12 else "false",
                **selected,
            }
        )
    policy_rows.sort(key=lambda row: row["is_primary"] != "true")
    return policy_rows, sweep


def build_score_threshold_sweep(predictions: list[Mapping[str, str]]) -> list[dict[str, str]]:
    thresholds = sorted({float(row["weighted_disease_score"]) for row in predictions}, reverse=True)
    if thresholds:
        thresholds.insert(0, thresholds[0] + 1e-12)
    rows: list[dict[str, str]] = []
    for threshold in thresholds:
        combined = metrics_for_score_threshold(predictions, threshold)
        old = metrics_for_score_threshold([row for row in predictions if row["source_dataset"] == "old"], threshold)
        new = metrics_for_score_threshold([row for row in predictions if row["source_dataset"] == "new"], threshold)
        average_old_new_youden = (float(old["youden_j"]) + float(new["youden_j"])) / 2.0
        rows.append(
            {
                "score_threshold": fmt(threshold),
                "average_old_new_youden_j": fmt(average_old_new_youden),
                **prefixed("combined", combined),
                **prefixed("old", old),
                **prefixed("new", new),
            }
        )
    return rows


def metrics_for_score_threshold(rows: list[Mapping[str, str]], threshold: float) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows]
    predicted = [float(row["weighted_disease_score"]) >= threshold for row in rows]
    return {"patient_count": str(len(rows)), **binary_metrics(labels, predicted)}


def apply_score_threshold(predictions: list[dict[str, str]], threshold: float, feature_count: int) -> None:
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
                f"触发 {row['triggered_feature_count']}/{feature_count} 个特征，触发权重 {row['triggered_weight']}。"
                f"主要原因：{row['triggered_features']}"
            )
        else:
            row["patient_decision_reason"] = (
                f"加权得分 {row['weighted_disease_score']} < 阈值 {row['score_threshold']}；"
                f"仅触发 {row['triggered_feature_count']}/{feature_count} 个特征，触发权重 {row['triggered_weight']}。"
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


def load_baseline_metric_rows(path: Path) -> list[dict[str, str]]:
    return read_csv(path) if path.exists() else []


def build_summary(
    *,
    old_dataset: Path,
    new_dataset: Path,
    nonpatient_reference_quantile: float,
    bootstrap_rounds: int,
    feature_rows: list[Mapping[str, Any]],
    search_rows: list[Mapping[str, Any]],
    prediction_rows: list[Mapping[str, str]],
    attribution_rows: list[Mapping[str, str]],
    threshold_rows: list[Mapping[str, str]],
    metric_rows: list[Mapping[str, str]],
    baseline_metric_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    return {
        "old_dataset": old_dataset.as_posix(),
        "new_dataset": new_dataset.as_posix(),
        "feature_count": len(feature_rows),
        "role_scope_option_count": len(search_rows),
        "nonpatient_reference_quantile": nonpatient_reference_quantile,
        "bootstrap_rounds": bootstrap_rounds,
        "primary_score_threshold": threshold_rows[0]["score_threshold"] if threshold_rows else "",
        "primary_threshold_policy": threshold_rows[0]["threshold_policy"] if threshold_rows else "",
        "patient_count": len(prediction_rows),
        "attribution_row_count": len(attribution_rows),
        "method": {
            "role_specific_threshold": "Each feature searches all patient-higher role_scope + aggregation options and selects the best role-specific option.",
            "threshold_stability_screening": "Bootstrap optimized thresholds; unstable thresholds are down-weighted by threshold_stability_multiplier.",
            "nonpatient_reference_threshold": "Feature threshold is max(Youden threshold, old/new/combined nonpatient reference quantile).",
            "score_threshold": f"Primary score threshold maximizes average old/new Youden J with old/new specificity >= {PRIMARY_SPECIFICITY_FLOOR:.2f}; additional rows provide looser/stricter alternatives.",
        },
        "selected_role_scope_counts": role_scope_counts(feature_rows),
        "metrics": metric_rows,
        "baseline_62_metrics": baseline_metric_rows,
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    feature_rows: list[Mapping[str, Any]],
    threshold_rows: list[Mapping[str, str]],
    metric_rows: list[Mapping[str, str]],
    baseline_metric_rows: list[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_features = sorted(feature_rows, key=lambda row: float(row["feature_weight"]), reverse=True)
    lines = [
        "# 63 阈值优化后的稳定特征患病判断规则",
        "",
        "## 方法",
        "",
        "- role-specific 阈值：每个特征不固定沿用 60 阶段 role，而是在 `all`、`mouth_dynamic`、`front_like` 及 `max/mean/median` 中搜索旧/新方向一致且患者更高的口径，再选择综合分最高的口径。",
        f"- 非患者参考分布阈值：单特征阈值取 `max(Youden阈值, old/new/combined 非患者 P{int(float(summary['nonpatient_reference_quantile']) * 100)})`。",
        f"- 阈值稳定性筛选：每个候选口径 bootstrap {summary['bootstrap_rounds']} 次，按阈值 IQR / 患者-非患者中位数差距计算稳定分；不稳定特征会降权。",
        f"- 最终加权分主阈值：在 old/new specificity 均不低于 {PRIMARY_SPECIFICITY_FLOOR:.2f} 的候选中，最大化 old/new 两个数据集 Youden J 的平均值；同时输出更宽松/更严格的备选阈值。",
        f"- 当前主规则：`weighted_disease_score >= {summary['primary_score_threshold']}` 输出 `患病倾向较高`。",
        "",
        "## 与 62 阶段对比",
        "",
    ]
    lines.extend(comparison_table(metric_rows, baseline_metric_rows))
    lines.extend(["", "## 加权总分阈值备选", ""])
    lines.extend(
        markdown_table(
            [
                "policy",
                "threshold",
                "old_precision",
                "old_recall",
                "old_specificity",
                "new_precision",
                "new_recall",
                "new_specificity",
                "combined_bacc",
            ],
            [
                [
                    row["threshold_policy"],
                    row["score_threshold"],
                    row["old_precision"],
                    row["old_recall"],
                    row["old_specificity"],
                    row["new_precision"],
                    row["new_recall"],
                    row["new_specificity"],
                    row["combined_balanced_accuracy"],
                ]
                for row in threshold_rows
            ],
        )
    )
    lines.extend(["", "## 选中特征阈值与权重", ""])
    lines.extend(
        markdown_table(
            [
                "rank",
                "feature",
                "role",
                "agg",
                "threshold",
                "youden_threshold",
                "nonpatient_ref",
                "weight",
                "threshold_stability",
                "old_spec",
                "new_spec",
            ],
            [
                [
                    index + 1,
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["threshold"],
                    row["youden_threshold"],
                    row["nonpatient_reference_threshold"],
                    row["feature_weight"],
                    row["threshold_stability_score"],
                    row["old_specificity"],
                    row["new_specificity"],
                ]
                for index, row in enumerate(sorted_features)
            ],
        )
    )
    lines.extend(
        [
            "",
            "## 产物",
            "",
            f"- 特征阈值与权重：`metadata/{OUTPUT_PREFIX}_feature_thresholds.csv`",
            f"- role 口径搜索明细：`metadata/{OUTPUT_PREFIX}_role_scope_search.csv`",
            f"- 加权分阈值备选：`metadata/{OUTPUT_PREFIX}_score_threshold_policies.csv`",
            f"- 患者判断：`metadata/{OUTPUT_PREFIX}_patient_predictions.csv`",
            f"- 患者特征贡献：`metadata/{OUTPUT_PREFIX}_patient_feature_contributions.csv`",
            f"- 指标：`metadata/{OUTPUT_PREFIX}_metrics.csv`",
            f"- JSON 摘要：`metadata/{OUTPUT_PREFIX}_summary.json`",
            "",
            "## 解释限制",
            "",
            "当前标签仍是患者 outcome 弱标签，不是人工面部不对称标签；该规则只能作为技术判断与归因候选。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def comparison_table(metric_rows: list[Mapping[str, str]], baseline_metric_rows: list[Mapping[str, str]]) -> list[str]:
    baseline_by_scope = {row["dataset_scope"]: row for row in baseline_metric_rows}
    optimized_by_scope = {row["dataset_scope"]: row for row in metric_rows}
    rows: list[list[Any]] = []
    for scope in ("combined", "old", "new"):
        base = baseline_by_scope.get(scope, {})
        opt = optimized_by_scope.get(scope, {})
        rows.append(
            [
                scope,
                base.get("precision", ""),
                base.get("recall", ""),
                base.get("specificity", ""),
                opt.get("precision", ""),
                opt.get("recall", ""),
                opt.get("specificity", ""),
                opt.get("tp", ""),
                opt.get("fp", ""),
                opt.get("tn", ""),
                opt.get("fn", ""),
            ]
        )
    return markdown_table(
        [
            "dataset",
            "62_precision",
            "62_recall",
            "62_specificity",
            "63_precision",
            "63_recall",
            "63_specificity",
            "63_TP",
            "63_FP",
            "63_TN",
            "63_FN",
        ],
        rows,
    )


def role_scope_counts(feature_rows: list[Mapping[str, Any]]) -> dict[str, int]:
    output: dict[str, int] = {}
    for row in feature_rows:
        output[row["role_scope"]] = output.get(row["role_scope"], 0) + 1
    return dict(sorted(output.items()))


def prefixed(prefix: str, metrics: Mapping[str, str]) -> dict[str, str]:
    return {f"{prefix}_{key}": value for key, value in metrics.items()}


def median(values: list[float]) -> float:
    return percentile(sorted(values), 0.5) if values else 0.0


def iqr(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return percentile(ordered, 0.75) - percentile(ordered, 0.25)


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


def feature_threshold_fields() -> list[str]:
    fields = [
        "rule_id",
        "feature_name",
        "feature_type",
        "role_scope",
        "aggregation",
        "original_role_scope",
        "original_aggregation",
        "direction",
        "threshold",
        "youden_threshold",
        "nonpatient_reference_threshold",
        "old_nonpatient_reference_threshold",
        "new_nonpatient_reference_threshold",
        "combined_nonpatient_reference_threshold",
        "nonpatient_reference_quantile",
        "feature_weight",
        "weight_grade",
        "raw_weight_score",
        "role_selection_score",
        "threshold_stability_score",
        "threshold_stability_grade",
        "threshold_stability_multiplier",
        "threshold_bootstrap_iqr",
        "threshold_iqr_to_patient_gap",
        "nonpatient_false_positive_rate",
        "volatility_score",
        "image_count",
        "old_image_count",
        "new_image_count",
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
    fields.extend(["threshold_policy", "role_scope_description"])
    return fields


def role_scope_search_fields() -> list[str]:
    fields = feature_threshold_fields()
    fields.insert(1, "selected_for_rule")
    return fields


def score_threshold_policy_fields() -> list[str]:
    return [
        "threshold_policy",
        "specificity_floor",
        "is_primary",
        "score_threshold",
        "average_old_new_youden_j",
        *score_metric_fields("combined"),
        *score_metric_fields("old"),
        *score_metric_fields("new"),
    ]


def score_threshold_sweep_fields() -> list[str]:
    return [
        "score_threshold",
        "average_old_new_youden_j",
        *score_metric_fields("combined"),
        *score_metric_fields("old"),
        *score_metric_fields("new"),
    ]


def score_metric_fields(prefix: str) -> list[str]:
    return [
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
