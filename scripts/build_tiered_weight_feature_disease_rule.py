#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_v1_mediapipe_full_feature_differences import fmt  # noqa: E402
from scripts.build_stable_weighted_feature_disease_rule import (  # noqa: E402
    build_feature_weight_rows,
    build_patient_predictions,
    input_format_spec,
    markdown_table,
    safe_div,
)
from scripts.find_combined_disease_feature_candidates import (  # noqa: E402
    DEFAULT_OUTPUT,
    NEW_DATASET,
    OLD_DATASET,
    binary_metrics,
    build_all_patient_rows,
    load_feature_rows,
    read_csv,
    to_float,
    write_csv,
    write_json,
)


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "yolo_comparison_20260608"
DEFAULT_SPLITS = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119" / "metadata" / "05_patient_splits.csv"
DEFAULT_RULE62_PREDICTIONS = (
    DEFAULT_OUTPUT / "metadata" / "62_stable_weighted_feature_disease_rule_patient_predictions.csv"
)
DEFAULT_RULE62_WEIGHTS = DEFAULT_OUTPUT / "metadata" / "62_stable_weighted_feature_disease_rule_feature_weights.csv"
OPTIONAL_FEATURE_NAME = "raw_all_mesh_region_point_spread_asym"
SPLIT_ORDER = ("test", "val", "train", "combined")
METHOD_RULE62 = "facesymai_rule62"
METHOD_TIERED = "tiered_weight_v1"


def main() -> None:
    args = parse_args()
    old_dataset = args.old_dataset.resolve()
    new_dataset = args.new_dataset.resolve()
    source_metadata = args.source_metadata.resolve()
    output_dir = args.output_dir.resolve()

    recommended_rows = load_distinct_candidates(
        source_metadata / "60_combined_disease_feature_recommended_distinct.csv",
        args.feature_count,
    )
    optional_result = evaluate_optional_feature(
        source_metadata / "60_combined_disease_feature_all_metrics.csv",
        recommended_rows,
        args.optional_feature_name,
        args.optional_min_variants,
        args.optional_combined_auc_min,
    )
    selected_candidates = selected_candidate_rows(recommended_rows, optional_result)
    feature_names = sorted({row["feature_name"] for row in selected_candidates})

    old_image_rows = load_feature_rows(old_dataset / "metadata" / "09_mediapipe_full_features.csv", "old")
    new_image_rows = load_feature_rows(new_dataset / "metadata" / "40_mediapipe_evidence_image_features.csv", "new")
    patient_rows_by_scope = build_all_patient_rows(old_image_rows, new_image_rows, feature_names)

    feature_rows = build_feature_weight_rows(selected_candidates, patient_rows_by_scope, old_image_rows, new_image_rows)
    apply_tiered_weights(feature_rows, selected_candidates, args)
    prediction_rows, attribution_rows = build_patient_predictions(feature_rows, patient_rows_by_scope)
    threshold_row, score_sweep_rows = select_global_score_threshold(prediction_rows, args.threshold_step)
    apply_score_threshold(prediction_rows, float(threshold_row["score_threshold"]))

    split_lookup = load_split_lookup(args.patient_splits.resolve())
    enriched_rule62 = enrich_predictions_with_split(read_csv(args.rule62_predictions.resolve()), split_lookup)
    enriched_tiered = enrich_predictions_with_split(prediction_rows, split_lookup)
    comparison_rows = build_comparison_rows(enriched_rule62, enriched_tiered)
    disagreement = build_patient_disagreement(enriched_rule62, enriched_tiered)
    baseline_weights = load_baseline_weights(args.rule62_weights.resolve())
    feature_analysis = build_feature_analysis(feature_rows, baseline_weights)
    summary = build_summary(
        args=args,
        old_dataset=old_dataset,
        new_dataset=new_dataset,
        selected_candidates=selected_candidates,
        optional_result=optional_result,
        feature_analysis=feature_analysis,
        threshold_row=threshold_row,
        score_sweep_rows=score_sweep_rows,
        prediction_rows=prediction_rows,
        attribution_rows=attribution_rows,
        comparison_rows=comparison_rows,
        disagreement=disagreement,
        split_lookup=split_lookup,
    )

    write_json(output_dir / "tiered_feature_weight_analysis.json", summary)
    write_csv(output_dir / "tiered_weight_feature_weights.csv", feature_rows, feature_weight_fields())
    write_csv(output_dir / "tiered_weight_patient_predictions.csv", prediction_rows, prediction_fields())
    write_csv(output_dir / "tiered_weight_patient_feature_contributions.csv", attribution_rows, attribution_fields())
    write_csv(output_dir / "tiered_weight_score_threshold_sweep.csv", score_sweep_rows, score_sweep_fields())
    write_csv(output_dir / "tiered_weight_comparison.csv", comparison_rows, comparison_fields())
    write_report(
        output_dir / "tiered_weight_report.md",
        summary,
        feature_rows,
        comparison_rows,
        disagreement,
    )

    print(f"Wrote {display_path(output_dir / 'tiered_feature_weight_analysis.json')}")
    print(f"Wrote {display_path(output_dir / 'tiered_weight_patient_predictions.csv')}")
    print(f"Wrote {display_path(output_dir / 'tiered_weight_comparison.csv')}")
    print(f"Wrote {display_path(output_dir / 'tiered_weight_report.md')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build tiered feature weights on top of the Rule 62 stable weighted disease-tendency rule."
    )
    parser.add_argument("--old-dataset", type=Path, default=OLD_DATASET)
    parser.add_argument("--new-dataset", type=Path, default=NEW_DATASET)
    parser.add_argument("--source-metadata", type=Path, default=DEFAULT_OUTPUT / "metadata")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--patient-splits", type=Path, default=DEFAULT_SPLITS)
    parser.add_argument("--rule62-predictions", type=Path, default=DEFAULT_RULE62_PREDICTIONS)
    parser.add_argument("--rule62-weights", type=Path, default=DEFAULT_RULE62_WEIGHTS)
    parser.add_argument("--feature-count", type=int, default=21)
    parser.add_argument("--tier1-auc-min", type=float, default=0.57)
    parser.add_argument("--tier1-fp-rate-max", type=float, default=0.35)
    parser.add_argument("--tier2-volatility-min", type=float, default=0.70)
    parser.add_argument("--tier4-auc-drop-min", type=float, default=0.05)
    parser.add_argument("--tier4-fp-rate-min", type=float, default=0.55)
    parser.add_argument("--tier4-volatility-max", type=float, default=0.25)
    parser.add_argument("--tier1-multiplier", type=float, default=2.0)
    parser.add_argument("--tier2-multiplier", type=float, default=1.5)
    parser.add_argument("--tier3-multiplier", type=float, default=1.0)
    parser.add_argument("--tier4-multiplier", type=float, default=0.5)
    parser.add_argument("--optional-feature-name", default=OPTIONAL_FEATURE_NAME)
    parser.add_argument("--optional-min-variants", type=int, default=3)
    parser.add_argument("--optional-combined-auc-min", type=float, default=0.58)
    parser.add_argument("--threshold-step", type=float, default=0.0001)
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
        item["selection_source"] = "rule62_recommended_distinct"
        output.append(item)
    return output


def evaluate_optional_feature(
    all_metrics_path: Path,
    selected_rows: list[Mapping[str, str]],
    feature_name: str,
    min_variants: int,
    combined_auc_min: float,
) -> dict[str, Any]:
    variants = [
        dict(row)
        for row in read_csv(all_metrics_path)
        if row.get("feature_name") == feature_name and row.get("combined_direction") == "patient_higher"
    ]
    passing = [
        row
        for row in variants
        if (to_float(row.get("combined_directional_auc")) or 0.0) > combined_auc_min
    ]
    already_selected = any(row["feature_name"] == feature_name for row in selected_rows)
    best = max(
        variants,
        key=lambda row: (
            to_float(row.get("combined_directional_auc")) or 0.0,
            to_float(row.get("old_directional_auc")) or 0.0,
            to_float(row.get("new_directional_auc")) or 0.0,
        ),
        default=None,
    )
    eligible = len(passing) >= min_variants and best is not None and not already_selected
    reason = (
        f"{len(passing)} variants have combined_directional_auc > {combined_auc_min}; "
        f"required {min_variants}."
    )
    selected: dict[str, str] | None = None
    if eligible and best is not None:
        selected = dict(best)
        selected["candidate_grade"] = "task04_added_candidate"
        selected["stability_score"] = fmt(task04_stability_score(selected))
        selected["recommended_use"] = (
            "Task 04 optional high-Cohen's-d candidate; included because enough aggregation variants exceed the combined AUC gate."
        )
        selected["selection_source"] = "task04_optional_candidate"
    return {
        "feature_name": feature_name,
        "eligible": eligible,
        "included": selected is not None,
        "already_selected": already_selected,
        "min_variants_required": min_variants,
        "combined_auc_gate": fmt(combined_auc_min),
        "passing_variant_count": len(passing),
        "variant_count": len(variants),
        "reason": reason if not already_selected else f"{feature_name} already exists in the recommended distinct set.",
        "selected_variant": selected,
        "variants": [
            {
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "direction_consistent": row.get("direction_consistent", ""),
                "old_directional_auc": row.get("old_directional_auc", ""),
                "new_directional_auc": row.get("new_directional_auc", ""),
                "combined_directional_auc": row.get("combined_directional_auc", ""),
                "combined_cohens_d": row.get("combined_cohens_d", ""),
            }
            for row in sorted(
                variants,
                key=lambda item: to_float(item.get("combined_directional_auc")) or 0.0,
                reverse=True,
            )
        ],
    }


def task04_stability_score(row: Mapping[str, str]) -> float:
    old_auc = to_float(row.get("old_directional_auc")) or 0.0
    new_auc = to_float(row.get("new_directional_auc")) or 0.0
    combined_auc = to_float(row.get("combined_directional_auc")) or 0.0
    d_old = abs(to_float(row.get("old_cohens_d")) or 0.0)
    d_new = abs(to_float(row.get("new_cohens_d")) or 0.0)
    return (min(old_auc, new_auc) - 0.5) * 2.0 + (combined_auc - 0.5) + min(d_old, d_new, 0.75) * 0.25


def selected_candidate_rows(
    recommended_rows: list[dict[str, str]],
    optional_result: Mapping[str, Any],
) -> list[dict[str, str]]:
    rows = [dict(row) for row in recommended_rows]
    selected_optional = optional_result.get("selected_variant")
    if selected_optional:
        item = dict(selected_optional)
        item["rule_id"] = str(len(rows) + 1)
        rows.append(item)
    return rows


def apply_tiered_weights(
    feature_rows: list[dict[str, Any]],
    selected_candidates: list[Mapping[str, str]],
    args: argparse.Namespace,
) -> None:
    candidate_by_rule_id = {row["rule_id"]: row for row in selected_candidates}
    adjusted_total = 0.0
    for row in feature_rows:
        candidate = candidate_by_rule_id[row["rule_id"]]
        row["direction_consistent"] = candidate.get("direction_consistent", "")
        row["selection_source"] = candidate.get("selection_source", "")
        tier, multiplier, reason = assign_tier(row, args)
        adjusted_score = float(row["raw_weight_score"]) * multiplier
        row["tier"] = tier
        row["tier_multiplier"] = fmt(multiplier)
        row["tier_reason"] = reason
        row["tier_adjusted_weight_score"] = fmt(adjusted_score)
        adjusted_total += adjusted_score

    for row in feature_rows:
        weight = safe_div(float(row["tier_adjusted_weight_score"]), adjusted_total)
        row["feature_weight"] = fmt(weight)
        row["weight_grade"] = weight_grade(weight)


def assign_tier(row: Mapping[str, Any], args: argparse.Namespace) -> tuple[str, float, str]:
    old_auc = float(row["old_directional_auc"])
    new_auc = float(row["new_directional_auc"])
    fp_rate = float(row["nonpatient_false_positive_rate"])
    volatility = float(row["volatility_score"])
    direction_consistent = truthy(row.get("direction_consistent", "true"))
    auc_drop = abs(old_auc - new_auc)

    if (
        (auc_drop > args.tier4_auc_drop_min and old_auc > new_auc)
        or fp_rate > args.tier4_fp_rate_min
        or volatility < args.tier4_volatility_max
    ):
        reasons: list[str] = []
        if auc_drop > args.tier4_auc_drop_min and old_auc > new_auc:
            reasons.append(f"old-new AUC drop {fmt(auc_drop)} > {fmt(args.tier4_auc_drop_min)}")
        if fp_rate > args.tier4_fp_rate_min:
            reasons.append(f"nonpatient FP rate {row['nonpatient_false_positive_rate']} > {fmt(args.tier4_fp_rate_min)}")
        if volatility < args.tier4_volatility_max:
            reasons.append(f"volatility_score {row['volatility_score']} < {fmt(args.tier4_volatility_max)}")
        return "Tier 4: 弱特征", args.tier4_multiplier, "；".join(reasons)

    if old_auc >= args.tier1_auc_min and new_auc >= args.tier1_auc_min and fp_rate < args.tier1_fp_rate_max:
        return (
            "Tier 1: 核心特征",
            args.tier1_multiplier,
            (
                f"old_auc/new_auc >= {fmt(args.tier1_auc_min)} 且 "
                f"nonpatient FP rate {row['nonpatient_false_positive_rate']} < {fmt(args.tier1_fp_rate_max)}"
            ),
        )

    if volatility > args.tier2_volatility_min and direction_consistent:
        return (
            "Tier 2: 稳定特征",
            args.tier2_multiplier,
            f"volatility_score {row['volatility_score']} > {fmt(args.tier2_volatility_min)} 且方向一致",
        )

    return "Tier 3: 普通特征", args.tier3_multiplier, "未命中核心、稳定或弱特征条件"


def weight_grade(weight: float) -> str:
    if weight >= 0.075:
        return "very_high"
    if weight >= 0.055:
        return "high"
    if weight >= 0.035:
        return "medium"
    return "low"


def select_global_score_threshold(
    predictions: list[Mapping[str, str]],
    step: float,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    if step <= 0 or step > 1:
        raise ValueError("--threshold-step must be in (0, 1].")
    steps = int(round(1.0 / step))
    if not math.isclose(steps * step, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError("--threshold-step must evenly divide 1.0 for deterministic [0, 1] scanning.")

    sweep: list[dict[str, str]] = []
    labels = [int(row["label_binary"]) for row in predictions]
    scores = [float(row["weighted_disease_score"]) for row in predictions]
    for index in range(steps + 1):
        threshold = round(index * step, 10)
        predicted = [score >= threshold for score in scores]
        metrics = binary_metrics(labels, predicted)
        sweep.append(
            {
                "score_threshold": fmt(threshold),
                "patient_count": str(len(predictions)),
                **metrics,
            }
        )

    selected = max(
        sweep,
        key=lambda row: (
            float(row["balanced_accuracy"]),
            float(row["youden_j"]),
            float(row["f1"]),
            float(row["precision"]),
            float(row["specificity"]),
            float(row["score_threshold"]),
        ),
    )
    selected = dict(selected)
    selected["threshold_policy"] = "combined_grid_balanced_accuracy"
    selected["threshold_policy_description"] = (
        f"Scan score_threshold in [0, 1] by {fmt(step)} on combined patients; "
        "maximize balanced_accuracy, then Youden J, F1, precision, specificity, and higher threshold."
    )
    return selected, sweep


def apply_score_threshold(predictions: list[dict[str, str]], threshold: float) -> None:
    for row in predictions:
        predicted = float(row["weighted_disease_score"]) >= threshold
        row["score_threshold"] = fmt(threshold)
        row["predicted_label_binary"] = "1" if predicted else "0"
        row["predicted_label_group"] = "患病" if predicted else "不患病"
        row["patient_disease_rule_output"] = "患病倾向较高" if predicted else "未达到患病阈值"
        row["confusion_type"] = confusion_type(row["label_binary"], row["predicted_label_binary"])
        feature_count = row["feature_count"]
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


def load_split_lookup(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    by_sample = {row["patient_sample_id"]: row for row in rows if row.get("patient_sample_id")}
    by_patient_id = {row["patient_id"]: row for row in rows if row.get("patient_id")}
    return {"by_sample": by_sample, "by_patient_id": by_patient_id}


def enrich_predictions_with_split(
    rows: list[Mapping[str, str]],
    split_lookup: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        split = resolve_split(row, split_lookup)
        item["_evaluation_split"] = split
        output.append(item)
    return output


def resolve_split(row: Mapping[str, str], split_lookup: Mapping[str, Mapping[str, Mapping[str, str]]]) -> str:
    if row.get("source_dataset") == "new":
        return "test"
    source_patient = row.get("source_patient_sample_id", "")
    split_row = split_lookup["by_sample"].get(source_patient)
    if split_row:
        return split_row.get("split", "")
    patient_id = extract_patient_id(source_patient)
    if patient_id and patient_id in split_lookup["by_patient_id"]:
        return split_lookup["by_patient_id"][patient_id].get("split", "")
    raise ValueError(f"Cannot resolve train/val/test split for prediction row: {row.get('patient_sample_id')}")


def extract_patient_id(source_patient_sample_id: str) -> str:
    match = re.search(r"pid(\d+)", source_patient_sample_id)
    return match.group(1) if match else ""


def build_comparison_rows(
    rule62_rows: list[Mapping[str, str]],
    tiered_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for method, rows in [(METHOD_RULE62, rule62_rows), (METHOD_TIERED, tiered_rows)]:
        threshold = rows[0].get("score_threshold", "") if rows else ""
        for split in SPLIT_ORDER:
            split_rows = rows if split == "combined" else [row for row in rows if row.get("_evaluation_split") == split]
            metrics = metrics_from_prediction_rows(split_rows)
            output.append(
                {
                    "method": method,
                    "split": split,
                    "precision": metrics["precision"],
                    "recall": metrics["recall"],
                    "specificity": metrics["specificity"],
                    "f1": metrics["f1"],
                    "balanced_accuracy": metrics["balanced_accuracy"],
                    "youden_j": metrics["youden_j"],
                    "threshold": threshold,
                }
            )
    return output


def metrics_from_prediction_rows(rows: list[Mapping[str, str]]) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows]
    predicted = [row["predicted_label_binary"] == "1" for row in rows]
    return binary_metrics(labels, predicted)


def build_patient_disagreement(
    rule62_rows: list[Mapping[str, str]],
    tiered_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    rule62_by_patient = {row["patient_sample_id"]: row for row in rule62_rows}
    tiered_by_patient = {row["patient_sample_id"]: row for row in tiered_rows}
    rows: list[dict[str, str]] = []
    for patient_id in sorted(set(rule62_by_patient) & set(tiered_by_patient)):
        base = rule62_by_patient[patient_id]
        tiered = tiered_by_patient[patient_id]
        if base["predicted_label_binary"] == tiered["predicted_label_binary"]:
            category = "same_prediction"
        elif base["predicted_label_binary"] == "1" and tiered["predicted_label_binary"] == "0":
            category = "rule62_positive_tiered_negative"
        else:
            category = "rule62_negative_tiered_positive"
        rows.append(
            {
                "patient_sample_id": patient_id,
                "source_dataset": base["source_dataset"],
                "source_patient_sample_id": base["source_patient_sample_id"],
                "split": base.get("_evaluation_split", ""),
                "label_group": base["label_group"],
                "label_binary": base["label_binary"],
                "category": category,
                "rule62_score": base["weighted_disease_score"],
                "rule62_prediction": base["patient_disease_rule_output"],
                "tiered_score": tiered["weighted_disease_score"],
                "tiered_prediction": tiered["patient_disease_rule_output"],
                "rule62_triggered_feature_count": base["triggered_feature_count"],
                "tiered_triggered_feature_count": tiered["triggered_feature_count"],
            }
        )
    changed = [row for row in rows if row["category"] != "same_prediction"]
    return {
        "patient_count": len(rows),
        "changed_prediction_count": len(changed),
        "changed_prediction_rate": fmt(safe_div(len(changed), len(rows))),
        "category_counts": dict(sorted(Counter(row["category"] for row in rows).items())),
        "changed_by_split": nested_counts(changed, ("split", "category")),
        "changed_by_truth": nested_counts(changed, ("label_group", "category")),
        "examples": sorted(
            changed,
            key=lambda row: (
                row["split"],
                row["category"],
                row["label_group"],
                row["patient_sample_id"],
            ),
        )[:30],
    }


def nested_counts(rows: Iterable[Mapping[str, str]], fields: tuple[str, str]) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = defaultdict(dict)
    counter = Counter((row.get(fields[0], ""), row.get(fields[1], "")) for row in rows)
    for (first, second), count in sorted(counter.items()):
        output[first][second] = count
    return dict(output)


def load_baseline_weights(path: Path) -> dict[str, Mapping[str, str]]:
    rows = read_csv(path)
    return {weight_key(row): row for row in rows}


def build_feature_analysis(
    feature_rows: list[Mapping[str, Any]],
    baseline_weights: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in feature_rows:
        baseline = baseline_weights.get(weight_key(row))
        old_weight = float(baseline["feature_weight"]) if baseline else 0.0
        new_weight = float(row["feature_weight"])
        output.append(
            {
                "rule_id": row["rule_id"],
                "feature_name": row["feature_name"],
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "selection_source": row.get("selection_source", ""),
                "tier": row["tier"],
                "tier_multiplier": row["tier_multiplier"],
                "tier_reason": row["tier_reason"],
                "old_feature_weight": fmt(old_weight),
                "new_feature_weight": row["feature_weight"],
                "weight_delta": fmt(new_weight - old_weight),
                "weight_ratio": "" if old_weight <= 0 else fmt(new_weight / old_weight),
                "raw_weight_score": row["raw_weight_score"],
                "tier_adjusted_weight_score": row["tier_adjusted_weight_score"],
                "old_directional_auc": row["old_directional_auc"],
                "new_directional_auc": row["new_directional_auc"],
                "combined_directional_auc": row["combined_directional_auc"],
                "nonpatient_false_positive_rate": row["nonpatient_false_positive_rate"],
                "volatility_score": row["volatility_score"],
                "threshold": row["threshold"],
            }
        )
    return output


def weight_key(row: Mapping[str, Any]) -> str:
    return "|".join([str(row["feature_name"]), str(row["role_scope"]), str(row["aggregation"])])


def build_summary(
    *,
    args: argparse.Namespace,
    old_dataset: Path,
    new_dataset: Path,
    selected_candidates: list[Mapping[str, str]],
    optional_result: Mapping[str, Any],
    feature_analysis: list[Mapping[str, Any]],
    threshold_row: Mapping[str, str],
    score_sweep_rows: list[Mapping[str, str]],
    prediction_rows: list[Mapping[str, str]],
    attribution_rows: list[Mapping[str, str]],
    comparison_rows: list[Mapping[str, str]],
    disagreement: Mapping[str, Any],
    split_lookup: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> dict[str, Any]:
    comparison_lookup = {(row["method"], row["split"]): row for row in comparison_rows}
    combined_delta = metric_delta(
        comparison_lookup[(METHOD_RULE62, "combined")],
        comparison_lookup[(METHOD_TIERED, "combined")],
    )
    added = [row for row in feature_analysis if row.get("selection_source") == "task04_optional_candidate"]
    return {
        "method": METHOD_TIERED,
        "old_dataset": old_dataset.as_posix(),
        "new_dataset": new_dataset.as_posix(),
        "feature_count": len(selected_candidates),
        "patient_count": len(prediction_rows),
        "attribution_row_count": len(attribution_rows),
        "tier_parameters": {
            "tier1_auc_min": args.tier1_auc_min,
            "tier1_fp_rate_max": args.tier1_fp_rate_max,
            "tier2_volatility_min": args.tier2_volatility_min,
            "tier4_auc_drop_min": args.tier4_auc_drop_min,
            "tier4_fp_rate_min": args.tier4_fp_rate_min,
            "tier4_volatility_max": args.tier4_volatility_max,
            "tier1_multiplier": args.tier1_multiplier,
            "tier2_multiplier": args.tier2_multiplier,
            "tier3_multiplier": args.tier3_multiplier,
            "tier4_multiplier": args.tier4_multiplier,
        },
        "threshold_search": {
            "score_threshold": threshold_row["score_threshold"],
            "threshold_step": args.threshold_step,
            "policy": threshold_row["threshold_policy"],
            "policy_description": threshold_row["threshold_policy_description"],
            "best_metrics": dict(threshold_row),
            "sweep_row_count": len(score_sweep_rows),
        },
        "split_policy": {
            "old_dataset": "Resolve train/val/test from 05_patient_splits.csv generated with seed 20260520.",
            "new_dataset": "External 20260508 rule-test patients are assigned to test for split-level comparison.",
            "old_split_counts": dict(
                sorted(Counter(row["split"] for row in split_lookup["by_sample"].values()).items())
            ),
        },
        "feature_tiers": feature_analysis,
        "tier_counts": dict(sorted(Counter(row["tier"] for row in feature_analysis).items())),
        "weight_changes": feature_analysis,
        "included_features": [
            {
                "feature_name": row["feature_name"],
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "selection_source": row["selection_source"],
                "tier": row["tier"],
                "new_feature_weight": row["new_feature_weight"],
            }
            for row in feature_analysis
        ],
        "newly_added_features": added,
        "removed_features": [],
        "optional_candidate_evaluation": optional_result,
        "comparison": comparison_rows,
        "combined_balanced_accuracy_delta": combined_delta["balanced_accuracy_delta"],
        "combined_acceptance_passed": float(combined_delta["balanced_accuracy_delta"]) >= -1e-12,
        "patient_disagreement": disagreement,
        "input_format": input_format_spec(),
        "warning": "Labels are patient outcome weak labels. This is not a clinical diagnosis rule.",
    }


def metric_delta(baseline: Mapping[str, str], current: Mapping[str, str]) -> dict[str, str]:
    return {
        f"{metric}_delta": fmt(float(current[metric]) - float(baseline[metric]))
        for metric in ["precision", "recall", "specificity", "f1", "balanced_accuracy", "youden_j"]
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    feature_rows: list[Mapping[str, Any]],
    comparison_rows: list[Mapping[str, str]],
    disagreement: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    comparison_lookup = {(row["method"], row["split"]): row for row in comparison_rows}
    tiered_combined = comparison_lookup[(METHOD_TIERED, "combined")]
    rule62_combined = comparison_lookup[(METHOD_RULE62, "combined")]
    test_delta = metric_delta(
        comparison_lookup[(METHOD_RULE62, "test")],
        comparison_lookup[(METHOD_TIERED, "test")],
    )
    combined_delta = metric_delta(rule62_combined, tiered_combined)
    sorted_features = sorted(feature_rows, key=lambda row: float(row["feature_weight"]), reverse=True)
    lines = [
        "# Task 04 Tiered Feature Weight Disease Rule",
        "",
        "## 方法说明",
        "",
        "- 基础权重：沿用规则 62 的 `raw_weight_score`，即跨数据 AUC、combined AUC、非患者 specificity、图片波动稳定性、图片数的加权组合。",
        "- Tier 调整：先按 Tier 4 识别明显弱特征并降权，再按 Tier 1/2/3 分层；调整后重新归一化，总权重为 1.0。",
        "- 特征触发：与规则 62 一致，患者级聚合特征值 `>=` 单特征阈值时贡献该特征权重。",
        "- 阈值搜索：在 combined 全部患者上以 `0.0001` 步长扫描 `[0, 1]`，优先最大化 balanced accuracy，其次 Youden J、F1、precision。",
        "- split 说明：旧数据按 `05_patient_splits.csv` 的 `train/val/test`；20260508 新规则测试集作为外部 test 纳入 test 指标。",
        "",
        "## 特征分层详情",
        "",
    ]
    lines.extend(
        markdown_table(
            [
                "rank",
                "feature",
                "role",
                "agg",
                "tier",
                "multiplier",
                "new_weight",
                "old_auc",
                "new_auc",
                "fp_rate",
                "volatility",
            ],
            [
                [
                    index + 1,
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["tier"],
                    row["tier_multiplier"],
                    row["feature_weight"],
                    row["old_directional_auc"],
                    row["new_directional_auc"],
                    row["nonpatient_false_positive_rate"],
                    row["volatility_score"],
                ]
                for index, row in enumerate(sorted_features)
            ],
        )
    )
    lines.extend(["", "## 权重调整对比", ""])
    lines.extend(
        markdown_table(
            ["feature", "role", "agg", "old_weight", "new_weight", "delta", "ratio", "tier_reason"],
            [
                [
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    analysis_row["old_feature_weight"],
                    analysis_row["new_feature_weight"],
                    analysis_row["weight_delta"],
                    analysis_row["weight_ratio"],
                    row["tier_reason"],
                ]
                for row in sorted_features
                for analysis_row in [feature_analysis_lookup(summary, row)]
            ],
        )
    )
    lines.extend(["", "## 指标对比", ""])
    lines.extend(
        markdown_table(
            [
                "split",
                "rule62_bacc",
                "tiered_bacc",
                "bacc_delta",
                "rule62_precision",
                "tiered_precision",
                "precision_delta",
                "rule62_recall",
                "tiered_recall",
                "recall_delta",
                "rule62_specificity",
                "tiered_specificity",
                "specificity_delta",
                "threshold",
            ],
            [
                comparison_report_row(comparison_lookup, split)
                for split in SPLIT_ORDER
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Test 集详细结论",
            "",
            (
                f"- test balanced_accuracy delta: `{test_delta['balanced_accuracy_delta']}`；"
                f"precision delta: `{test_delta['precision_delta']}`；"
                f"recall delta: `{test_delta['recall_delta']}`；"
                f"specificity delta: `{test_delta['specificity_delta']}`。"
            ),
            (
                "- 结论："
                + (
                    "test 集 balanced accuracy 提升或持平，Tier 分层没有削弱测试集整体平衡表现。"
                    if float(test_delta["balanced_accuracy_delta"]) >= 0
                    else "test 集 balanced accuracy 下降，主要需要关注 Tier 4 降权后召回/特异性的交换关系。"
                )
            ),
            "",
            "## Combined 验收结论",
            "",
            (
                f"- combined balanced_accuracy: 规则62 `{rule62_combined['balanced_accuracy']}`，"
                f"tiered `{tiered_combined['balanced_accuracy']}`，差值 `{combined_delta['balanced_accuracy_delta']}`。"
            ),
            (
                "- 验收状态：通过，combined balanced_accuracy 未低于规则62。"
                if float(combined_delta["balanced_accuracy_delta"]) >= -1e-12
                else "- 验收状态：未通过，分层策略未带来 combined balanced_accuracy 改善；该参数组合不宜替换规则62。"
            ),
            "",
            "## 患者级不一致分析",
            "",
            f"- 预测变化患者数：`{disagreement['changed_prediction_count']}/{disagreement['patient_count']}`，变化率 `{disagreement['changed_prediction_rate']}`。",
            f"- 变化类型计数：`{json.dumps(disagreement['category_counts'], ensure_ascii=False, sort_keys=True)}`。",
            f"- 按 split 的变化：`{json.dumps(disagreement['changed_by_split'], ensure_ascii=False, sort_keys=True)}`。",
            f"- 按真实标签的变化：`{json.dumps(disagreement['changed_by_truth'], ensure_ascii=False, sort_keys=True)}`。",
            "",
        ]
    )
    examples = disagreement.get("examples", [])
    if examples:
        lines.extend(
            markdown_table(
                [
                    "patient",
                    "dataset",
                    "split",
                    "truth",
                    "change",
                    "rule62_score",
                    "tiered_score",
                    "rule62_pred",
                    "tiered_pred",
                ],
                [
                    [
                        row["source_patient_sample_id"],
                        row["source_dataset"],
                        row["split"],
                        row["label_group"],
                        row["category"],
                        row["rule62_score"],
                        row["tiered_score"],
                        row["rule62_prediction"],
                        row["tiered_prediction"],
                    ]
                    for row in examples[:20]
                ],
            )
        )
    else:
        lines.append("规则62与 tiered_weight_v1 没有患者级预测不一致。")
    optional = summary["optional_candidate_evaluation"]
    lines.extend(
        [
            "",
            "## 新纳入/剔除说明",
            "",
            (
                f"- `{optional['feature_name']}`：passing variants "
                f"{optional['passing_variant_count']}/{optional['variant_count']}，"
                f"纳入状态 `{optional['included']}`。{optional['reason']}"
            ),
            "- 本任务没有剔除规则62原有 21 个特征；弱特征通过 Tier 4 降权处理。",
            "",
            "## 产物",
            "",
            "- 分析摘要：`tiered_feature_weight_analysis.json`",
            "- 患者预测：`tiered_weight_patient_predictions.csv`",
            "- 指标对比：`tiered_weight_comparison.csv`",
            "- 本报告：`tiered_weight_report.md`",
            "",
            "## 限制",
            "",
            "该规则使用患者 outcome 弱标签拟合，只能作为技术判断与归因候选，不能作为临床诊断结论。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def feature_analysis_lookup(summary: Mapping[str, Any], row: Mapping[str, Any]) -> Mapping[str, Any]:
    key = weight_key(row)
    for item in summary["feature_tiers"]:
        if weight_key(item) == key:
            return item
    raise KeyError(key)


def comparison_report_row(
    comparison_lookup: Mapping[tuple[str, str], Mapping[str, str]],
    split: str,
) -> list[str]:
    rule62 = comparison_lookup[(METHOD_RULE62, split)]
    tiered = comparison_lookup[(METHOD_TIERED, split)]
    delta = metric_delta(rule62, tiered)
    return [
        split,
        rule62["balanced_accuracy"],
        tiered["balanced_accuracy"],
        delta["balanced_accuracy_delta"],
        rule62["precision"],
        tiered["precision"],
        delta["precision_delta"],
        rule62["recall"],
        tiered["recall"],
        delta["recall_delta"],
        rule62["specificity"],
        tiered["specificity"],
        delta["specificity_delta"],
        tiered["threshold"],
    ]


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


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


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


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
        "tier",
        "tier_multiplier",
        "tier_reason",
        "raw_weight_score",
        "tier_adjusted_weight_score",
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
        "direction_consistent",
        "selection_source",
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


def comparison_fields() -> list[str]:
    return [
        "method",
        "split",
        "precision",
        "recall",
        "specificity",
        "f1",
        "balanced_accuracy",
        "youden_j",
        "threshold",
    ]


if __name__ == "__main__":
    main()
