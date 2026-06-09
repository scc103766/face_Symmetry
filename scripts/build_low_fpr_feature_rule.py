#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analyze_v1_mediapipe_full_feature_differences import fmt  # noqa: E402
from scripts.build_stable_weighted_feature_disease_rule import (  # noqa: E402
    confusion_type,
    markdown_table,
)
from scripts.find_combined_disease_feature_candidates import (  # noqa: E402
    binary_metrics,
    build_all_patient_rows,
    load_feature_rows,
    percentile,
    read_csv,
    to_float,
    write_csv,
)


DEFAULT_SOURCE_METADATA = PROJECT_ROOT / "datasets" / "combined_disease_feature_candidates_20260529" / "metadata"
DEFAULT_OLD_FEATURE_VALUES = (
    PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119" / "metadata" / "09_mediapipe_full_features.csv"
)
DEFAULT_NEW_FEATURE_VALUES = (
    PROJECT_ROOT
    / "datasets"
    / "stroke_warning_app_rule_test_set_20260508"
    / "metadata"
    / "40_mediapipe_evidence_image_features.csv"
)
DEFAULT_PATIENT_SPLITS = (
    PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119" / "metadata" / "05_patient_splits.csv"
)
DEFAULT_RULE62_PREDICTIONS = DEFAULT_SOURCE_METADATA / "62_stable_weighted_feature_disease_rule_patient_predictions.csv"
DEFAULT_RULE62_WEIGHTS = DEFAULT_SOURCE_METADATA / "62_stable_weighted_feature_disease_rule_feature_weights.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "datasets" / "yolo_comparison_20260608"

METHOD_RULE62 = "facesymai_rule62"
METHOD_AND = "low_fpr_and_3"
METHOD_WEIGHTED = "low_fpr_weighted"
SPLIT_ORDER = ("test", "val", "train", "combined")
TAIL_QUANTILES = (("P99", 0.99), ("P995", 0.995), ("P999", 0.999))
EPSILON = 1e-12


def main() -> None:
    args = parse_args()
    paths = {
        "60_all_metrics": args.source_metadata / "60_combined_disease_feature_all_metrics.csv",
        "60_candidates": args.source_metadata / "60_combined_disease_feature_candidates.csv",
        "old_feature_values": args.old_feature_values,
        "new_feature_values": args.new_feature_values,
        "patient_splits": args.patient_splits,
        "rule62_predictions": args.rule62_predictions,
        "rule62_weights": args.rule62_weights,
    }
    require_paths(paths)

    all_metric_rows = read_csv(paths["60_all_metrics"])
    candidate_rows = read_csv(paths["60_candidates"])
    feature_names = sorted({row["feature_name"] for row in all_metric_rows})

    old_image_rows = load_feature_rows(paths["old_feature_values"], "old")
    new_image_rows = load_feature_rows(paths["new_feature_values"], "new")
    patient_rows_by_scope = build_all_patient_rows(old_image_rows, new_image_rows, feature_names)

    tail_rows = build_tail_rows(
        all_metric_rows,
        candidate_rows,
        patient_rows_by_scope,
        patient_above_p99_rate_min=args.patient_above_p99_rate_min,
        tail_ratio_min=args.tail_ratio_min,
        cross_data_p99_relative_diff_max=args.cross_data_p99_relative_diff_max,
    )
    selected_rows, and_feature_rows = build_selected_feature_rows(
        tail_rows,
        rule62_weight_rows=read_csv(paths["rule62_weights"]),
        fallback_feature_count=args.and_feature_count,
        tier1_auc_min=args.tier1_auc_min,
        tier1_fp_rate_max=args.tier1_fp_rate_max,
    )

    split_lookup = load_split_lookup(paths["patient_splits"])
    rule62_predictions = enrich_predictions_with_split(read_csv(paths["rule62_predictions"]), split_lookup)

    and_predictions, and_variant = build_and_predictions(
        and_feature_rows,
        patient_rows_by_scope,
        combined_fp_max=args.combined_fp_max,
    )
    weighted_predictions, weighted_variant, weighted_features = build_weighted_predictions(
        selected_rows,
        patient_rows_by_scope,
        combined_fp_max=args.combined_fp_max,
    )

    enriched_and = enrich_predictions_with_split(and_predictions, split_lookup)
    enriched_weighted = enrich_predictions_with_split(weighted_predictions, split_lookup)
    comparison_rows = build_comparison_rows(rule62_predictions, enriched_and, enriched_weighted)
    summary = build_summary(
        args=args,
        paths=paths,
        old_image_rows=old_image_rows,
        new_image_rows=new_image_rows,
        all_metric_rows=all_metric_rows,
        tail_rows=tail_rows,
        selected_rows=selected_rows,
        and_variant=and_variant,
        weighted_variant=weighted_variant,
        weighted_features=weighted_features,
        comparison_rows=comparison_rows,
    )

    output_dir = args.output_dir
    write_csv(output_dir / "low_fpr_tail_features.csv", tail_rows, tail_feature_fields())
    write_csv(output_dir / "low_fpr_selected_features.csv", selected_rows, selected_feature_fields())
    write_csv(output_dir / "low_fpr_patient_predictions.csv", enriched_and + enriched_weighted, prediction_fields())
    write_csv(output_dir / "low_fpr_comparison.csv", comparison_rows, comparison_fields())
    write_report(output_dir / "low_fpr_report.md", summary, tail_rows, selected_rows, comparison_rows)

    print(f"Wrote {display_path(output_dir / 'low_fpr_tail_features.csv')}")
    print(f"Wrote {display_path(output_dir / 'low_fpr_selected_features.csv')}")
    print(f"Wrote {display_path(output_dir / 'low_fpr_patient_predictions.csv')}")
    print(f"Wrote {display_path(output_dir / 'low_fpr_comparison.csv')}")
    print(f"Wrote {display_path(output_dir / 'low_fpr_report.md')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build extremely low false-positive feature rules from 60-stage tail distributions."
    )
    parser.add_argument("--source-metadata", type=Path, default=DEFAULT_SOURCE_METADATA)
    parser.add_argument("--old-feature-values", type=Path, default=DEFAULT_OLD_FEATURE_VALUES)
    parser.add_argument("--new-feature-values", type=Path, default=DEFAULT_NEW_FEATURE_VALUES)
    parser.add_argument("--patient-splits", type=Path, default=DEFAULT_PATIENT_SPLITS)
    parser.add_argument("--rule62-predictions", type=Path, default=DEFAULT_RULE62_PREDICTIONS)
    parser.add_argument("--rule62-weights", type=Path, default=DEFAULT_RULE62_WEIGHTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--patient-above-p99-rate-min", type=float, default=0.15)
    parser.add_argument("--tail-ratio-min", type=float, default=1.5)
    parser.add_argument("--cross-data-p99-relative-diff-max", type=float, default=0.30)
    parser.add_argument("--combined-fp-max", type=int, default=1)
    parser.add_argument("--and-feature-count", type=int, default=3)
    parser.add_argument("--tier1-auc-min", type=float, default=0.57)
    parser.add_argument("--tier1-fp-rate-max", type=float, default=0.35)
    return parser.parse_args()


def require_paths(paths: Mapping[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input paths:\n" + "\n".join(missing))


def build_tail_rows(
    all_metric_rows: list[Mapping[str, str]],
    candidate_rows: list[Mapping[str, str]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    *,
    patient_above_p99_rate_min: float,
    tail_ratio_min: float,
    cross_data_p99_relative_diff_max: float,
) -> list[dict[str, Any]]:
    grade_lookup = candidate_grade_lookup(candidate_rows)
    rows: list[dict[str, Any]] = []
    for metric in all_metric_rows:
        scope = metric["role_scope"]
        aggregation = metric["aggregation"]
        feature = metric["feature_name"]
        key = (scope, aggregation)
        patient_rows = patient_rows_by_scope.get(key, [])
        values = grouped_feature_values(patient_rows, feature)
        combined_positive = values[("combined", "1")]
        combined_negative = values[("combined", "0")]
        old_negative = values[("old", "0")]
        new_negative = values[("new", "0")]
        old_positive = values[("old", "1")]
        new_positive = values[("new", "1")]

        nonpatient_p99 = tail_percentile(combined_negative, 0.99)
        nonpatient_p995 = tail_percentile(combined_negative, 0.995)
        nonpatient_p999 = tail_percentile(combined_negative, 0.999)
        nonpatient_max = max(combined_negative) if combined_negative else None
        patient_p90 = tail_percentile(combined_positive, 0.90)
        patient_p99 = tail_percentile(combined_positive, 0.99)
        tail_ratio = safe_ratio(patient_p90, nonpatient_p99)

        old_p99 = tail_percentile(old_negative, 0.99)
        new_p99 = tail_percentile(new_negative, 0.99)
        p99_relative_diff = relative_diff(old_p99, new_p99)
        cross_consistent = (
            p99_relative_diff is not None and p99_relative_diff <= cross_data_p99_relative_diff_max
        )
        patient_above_p99_rate = rate_above(combined_positive, nonpatient_p99)
        patient_above_p995_rate = rate_above(combined_positive, nonpatient_p995)
        patient_above_p999_rate = rate_above(combined_positive, nonpatient_p999)
        strict_pass = (
            metric.get("combined_direction") == "patient_higher"
            and patient_above_p99_rate >= patient_above_p99_rate_min
            and tail_ratio is not None
            and tail_ratio >= tail_ratio_min
            and cross_consistent
        )

        row = {
            "role_scope": scope,
            "role_scope_description": metric.get("role_scope_description", ""),
            "aggregation": aggregation,
            "feature_type": metric.get("feature_type", ""),
            "feature_name": feature,
            "candidate_grade": grade_lookup.get(metric_key(metric), ""),
            "combined_direction": metric.get("combined_direction", ""),
            "old_direction": metric.get("old_direction", ""),
            "new_direction": metric.get("new_direction", ""),
            "direction_consistent": metric.get("direction_consistent", ""),
            "old_directional_auc": metric.get("old_directional_auc", ""),
            "new_directional_auc": metric.get("new_directional_auc", ""),
            "combined_directional_auc": metric.get("combined_directional_auc", ""),
            "combined_patient_n": str(len(combined_positive) + len(combined_negative)),
            "combined_patient_n_with_feature": str(len(combined_positive) + len(combined_negative)),
            "combined_positive_n": str(len(combined_positive)),
            "combined_negative_n": str(len(combined_negative)),
            "old_negative_n": str(len(old_negative)),
            "new_negative_n": str(len(new_negative)),
            "nonpatient_P99": fmt_optional(nonpatient_p99),
            "nonpatient_P995": fmt_optional(nonpatient_p995),
            "nonpatient_P999": fmt_optional(nonpatient_p999),
            "nonpatient_max": fmt_optional(nonpatient_max),
            "old_nonpatient_P99": fmt_optional(old_p99),
            "new_nonpatient_P99": fmt_optional(new_p99),
            "old_patient_above_old_P99_rate": fmt(rate_above(old_positive, old_p99)),
            "new_patient_above_new_P99_rate": fmt(rate_above(new_positive, new_p99)),
            "cross_data_p99_relative_diff": fmt_optional(p99_relative_diff),
            "cross_data_tail_consistent": "true" if cross_consistent else "false",
            "patient_P90": fmt_optional(patient_p90),
            "patient_P99": fmt_optional(patient_p99),
            "patient_above_P99_rate": fmt(patient_above_p99_rate),
            "patient_above_P995_rate": fmt(patient_above_p995_rate),
            "patient_above_P999_rate": fmt(patient_above_p999_rate),
            "tail_separation_ratio": fmt_optional(tail_ratio),
            "combined_fp_at_P99": str(count_at_or_above(combined_negative, nonpatient_p99)),
            "combined_fp_at_P995": str(count_at_or_above(combined_negative, nonpatient_p995)),
            "combined_fp_at_P999": str(count_at_or_above(combined_negative, nonpatient_p999)),
            "combined_fp_rate_at_P99": fmt(rate_at_or_above(combined_negative, nonpatient_p99)),
            "combined_fp_rate_at_P995": fmt(rate_at_or_above(combined_negative, nonpatient_p995)),
            "combined_fp_rate_at_P999": fmt(rate_at_or_above(combined_negative, nonpatient_p999)),
            "strict_filter_pass": "true" if strict_pass else "false",
            "filter_failure_reasons": filter_failure_reasons(
                metric=metric,
                patient_above_p99_rate=patient_above_p99_rate,
                patient_above_p99_rate_min=patient_above_p99_rate_min,
                tail_ratio=tail_ratio,
                tail_ratio_min=tail_ratio_min,
                cross_consistent=cross_consistent,
            ),
            "_tail_ratio_value": tail_ratio if tail_ratio is not None else -1.0,
            "_patient_above_p99_value": patient_above_p99_rate,
        }
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row["strict_filter_pass"] == "true",
            row["combined_direction"] == "patient_higher",
            float(row["_tail_ratio_value"]),
            float(row["_patient_above_p99_value"]),
            to_float(row.get("combined_directional_auc")) or 0.0,
        ),
        reverse=True,
    )
    for index, row in enumerate(rows, start=1):
        row["tail_rank"] = str(index)
    return rows


def candidate_grade_lookup(candidate_rows: list[Mapping[str, str]]) -> dict[str, str]:
    return {metric_key(row): row.get("candidate_grade", "") for row in candidate_rows}


def metric_key(row: Mapping[str, str]) -> str:
    return "|".join([row.get("role_scope", ""), row.get("aggregation", ""), row.get("feature_name", "")])


def grouped_feature_values(
    rows: list[Mapping[str, Any]],
    feature: str,
) -> dict[tuple[str, str], list[float]]:
    output = {
        ("combined", "0"): [],
        ("combined", "1"): [],
        ("old", "0"): [],
        ("old", "1"): [],
        ("new", "0"): [],
        ("new", "1"): [],
    }
    for row in rows:
        label = row.get("label_binary")
        dataset_key = row.get("dataset_key")
        if label not in {"0", "1"} or dataset_key not in {"old", "new"}:
            continue
        value = to_float(row.get(feature))
        if value is None:
            continue
        output[("combined", label)].append(value)
        output[(dataset_key, label)].append(value)
    return output


def tail_percentile(values: list[float], q: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    if math.isclose(q, 0.99) and len(ordered) < 100 and len(ordered) >= 2:
        return ordered[-2]
    return percentile(ordered, q)


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if abs(denominator) <= EPSILON:
        return None
    return numerator / denominator


def relative_diff(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    denominator = max(abs(a), abs(b), EPSILON)
    return abs(a - b) / denominator


def rate_above(values: list[float], threshold: float | None) -> float:
    if threshold is None or not values:
        return 0.0
    return sum(1 for value in values if value > threshold) / len(values)


def count_at_or_above(values: list[float], threshold: float | None) -> int:
    if threshold is None:
        return 0
    return sum(1 for value in values if value >= threshold)


def rate_at_or_above(values: list[float], threshold: float | None) -> float:
    return 0.0 if not values else count_at_or_above(values, threshold) / len(values)


def fmt_optional(value: float | None) -> str:
    return "" if value is None or not math.isfinite(value) else fmt(value)


def filter_failure_reasons(
    *,
    metric: Mapping[str, str],
    patient_above_p99_rate: float,
    patient_above_p99_rate_min: float,
    tail_ratio: float | None,
    tail_ratio_min: float,
    cross_consistent: bool,
) -> str:
    reasons: list[str] = []
    if metric.get("combined_direction") != "patient_higher":
        reasons.append("combined_direction is not patient_higher")
    if patient_above_p99_rate < patient_above_p99_rate_min:
        reasons.append(f"patient_above_P99_rate {fmt(patient_above_p99_rate)} < {fmt(patient_above_p99_rate_min)}")
    if tail_ratio is None:
        reasons.append("tail_separation_ratio unavailable")
    elif tail_ratio < tail_ratio_min:
        reasons.append(f"tail_separation_ratio {fmt(tail_ratio)} < {fmt(tail_ratio_min)}")
    if not cross_consistent:
        reasons.append("cross_data_tail_consistent is false")
    return "; ".join(reasons)


def build_selected_feature_rows(
    tail_rows: list[dict[str, Any]],
    *,
    rule62_weight_rows: list[Mapping[str, str]],
    fallback_feature_count: int,
    tier1_auc_min: float,
    tier1_fp_rate_max: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    strict_rows = [row for row in tail_rows if row["strict_filter_pass"] == "true"]
    and_rows = unique_feature_rows(strict_rows, fallback_feature_count)
    selection_mode = "strict_s1"
    if len(and_rows) < fallback_feature_count:
        needed = fallback_feature_count - len(and_rows)
        fallback_pool = [
            row
            for row in tail_rows
            if row["combined_direction"] == "patient_higher"
            and row["cross_data_tail_consistent"] == "true"
            and row not in and_rows
        ]
        and_rows.extend(unique_feature_rows(fallback_pool, needed, existing={row["feature_name"] for row in and_rows}))
        selection_mode = "fallback_top_tail"

    tier1_keys = {
        metric_key(row)
        for row in rule62_weight_rows
        if (to_float(row.get("old_directional_auc")) or 0.0) >= tier1_auc_min
        and (to_float(row.get("new_directional_auc")) or 0.0) >= tier1_auc_min
        and (to_float(row.get("nonpatient_false_positive_rate")) or 1.0) < tier1_fp_rate_max
    }
    selected_by_key: dict[str, dict[str, Any]] = {}
    for row in and_rows:
        item = dict(row)
        item["selected_for_and_3"] = "true"
        item["selected_for_weighted"] = "true" if metric_key(item) in tier1_keys else "false"
        item["selection_group"] = selection_mode if item["strict_filter_pass"] != "true" else "strict_s1"
        item["selection_reason"] = (
            "通过严格 S1 筛选，进入 AND 候选。"
            if item["strict_filter_pass"] == "true"
            else "严格 S1 不足 3 个时，按 patient_higher + cross-data consistent + tail ratio 排序补足 AND 评估。"
        )
        selected_by_key[metric_key(item)] = item

    for row in tail_rows:
        key = metric_key(row)
        if key not in tier1_keys:
            continue
        item = selected_by_key.get(key, dict(row))
        item["selected_for_and_3"] = item.get("selected_for_and_3", "false")
        item["selected_for_weighted"] = "true"
        item["selection_group"] = merge_selection_group(item.get("selection_group", ""), "scheme_b_tier1_core")
        item["selection_reason"] = merge_selection_reason(
            item.get("selection_reason", ""),
            f"Rule 62 Tier 1 core: old/new AUC >= {fmt(tier1_auc_min)} and nonpatient FP rate < {fmt(tier1_fp_rate_max)}.",
        )
        selected_by_key[key] = item

    selected_rows = sorted(
        selected_by_key.values(),
        key=lambda row: (
            row.get("selected_for_and_3") == "true",
            row.get("selected_for_weighted") == "true",
            float(row["_tail_ratio_value"]),
        ),
        reverse=True,
    )
    for index, row in enumerate(selected_rows, start=1):
        row["selection_rank"] = str(index)
    return selected_rows, and_rows


def unique_feature_rows(
    rows: list[dict[str, Any]],
    limit: int,
    *,
    existing: set[str] | None = None,
) -> list[dict[str, Any]]:
    seen = set(existing or set())
    output: list[dict[str, Any]] = []
    for row in rows:
        feature = row["feature_name"]
        if feature in seen:
            continue
        seen.add(feature)
        output.append(row)
        if len(output) >= limit:
            break
    return output


def merge_selection_group(current: str, extra: str) -> str:
    parts = [part for part in current.split(";") if part]
    if extra not in parts:
        parts.append(extra)
    return ";".join(parts)


def merge_selection_reason(current: str, extra: str) -> str:
    return extra if not current else f"{current} {extra}"


def build_and_predictions(
    feature_rows: list[Mapping[str, Any]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    *,
    combined_fp_max: int,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not feature_rows:
        raise ValueError("No feature rows available for AND rule evaluation.")

    variants: list[dict[str, Any]] = []
    for quantile_name, _ in TAIL_QUANTILES:
        predictions = and_predictions_for_quantile(feature_rows, patient_rows_by_scope, quantile_name)
        combined_metrics = metrics_from_prediction_rows(predictions)
        variants.append(
            {
                "method": METHOD_AND,
                "quantile": quantile_name,
                "predictions": predictions,
                "metrics": combined_metrics,
                "rule": and_rule_description(feature_rows, quantile_name),
            }
        )
    selected = select_low_fpr_variant(variants, combined_fp_max)
    predictions = selected["predictions"]
    for row in predictions:
        row["method"] = METHOD_AND
        row["threshold_rule"] = selected["rule"]
    return predictions, selected


def and_predictions_for_quantile(
    feature_rows: list[Mapping[str, Any]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    quantile_name: str,
) -> list[dict[str, str]]:
    lookups, base_rows = patient_lookups(feature_rows, patient_rows_by_scope)
    patient_ids = sorted(base_rows)
    predictions: list[dict[str, str]] = []
    for patient_id in patient_ids:
        triggered: list[str] = []
        missing: list[str] = []
        for row in feature_rows:
            value = to_float(lookups[metric_key(row)].get(patient_id, {}).get(row["feature_name"]))
            threshold = to_float(row.get(f"nonpatient_{quantile_name}"))
            if value is None or threshold is None:
                missing.append(row["feature_name"])
                continue
            if value >= threshold:
                triggered.append(f"{row['feature_name']}={fmt(value)}>=nonpatient_{quantile_name} {fmt(threshold)}")
        predicted = len(triggered) == len(feature_rows) and not missing
        base = base_rows[patient_id]
        predictions.append(
            prediction_row(
                method=METHOD_AND,
                base=base,
                score=1.0 if predicted else len(triggered) / len(feature_rows),
                threshold=1.0,
                predicted=predicted,
                triggered_feature_count=len(triggered),
                triggered_features=";".join(triggered),
                missing_features=";".join(missing),
                reason=(
                    f"AND {quantile_name}: 触发 {len(triggered)}/{len(feature_rows)} 个特征；"
                    f"{'满足全部条件' if predicted else '未满足全部条件'}。"
                ),
                threshold_rule=and_rule_description(feature_rows, quantile_name),
            )
        )
    return predictions


def and_rule_description(feature_rows: list[Mapping[str, Any]], quantile_name: str) -> str:
    parts = [
        f"{row['feature_name']}[{row['role_scope']}/{row['aggregation']}] >= {row.get(f'nonpatient_{quantile_name}', '')}"
        for row in feature_rows
    ]
    return f"AND {quantile_name}: " + " AND ".join(parts)


def build_weighted_predictions(
    selected_rows: list[Mapping[str, Any]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    *,
    combined_fp_max: int,
) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, Any]]]:
    core_rows = [dict(row) for row in selected_rows if row.get("selected_for_weighted") == "true"]
    if not core_rows:
        raise ValueError("No Tier 1 core feature rows available for weighted rule evaluation.")

    variants: list[dict[str, Any]] = []
    selected_feature_variants: dict[str, list[dict[str, Any]]] = {}
    for quantile_name, _ in TAIL_QUANTILES:
        weighted_features = weighted_feature_rows(core_rows, quantile_name)
        predictions, threshold_row = weighted_predictions_for_quantile(
            weighted_features,
            patient_rows_by_scope,
            combined_fp_max=combined_fp_max,
        )
        selected_feature_variants[quantile_name] = weighted_features
        variants.append(
            {
                "method": METHOD_WEIGHTED,
                "quantile": quantile_name,
                "predictions": predictions,
                "metrics": threshold_row,
                "score_threshold": threshold_row["score_threshold"],
                "rule": weighted_rule_description(weighted_features, threshold_row["score_threshold"], quantile_name),
            }
        )
    selected = select_low_fpr_variant(variants, combined_fp_max)
    predictions = selected["predictions"]
    for row in predictions:
        row["method"] = METHOD_WEIGHTED
        row["threshold_rule"] = selected["rule"]
    return predictions, selected, selected_feature_variants[selected["quantile"]]


def weighted_feature_rows(core_rows: list[dict[str, Any]], quantile_name: str) -> list[dict[str, Any]]:
    ratios = [max(to_float(row.get("tail_separation_ratio")) or 0.0, EPSILON) for row in core_rows]
    total = sum(ratios) or 1.0
    output: list[dict[str, Any]] = []
    for row, ratio in zip(core_rows, ratios):
        item = dict(row)
        item["weighted_quantile"] = quantile_name
        item["weighted_threshold"] = item.get(f"nonpatient_{quantile_name}", "")
        item["weighted_feature_weight"] = fmt(ratio / total)
        output.append(item)
    return output


def weighted_predictions_for_quantile(
    feature_rows: list[Mapping[str, Any]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
    *,
    combined_fp_max: int,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    lookups, base_rows = patient_lookups(feature_rows, patient_rows_by_scope)
    score_rows: list[dict[str, Any]] = []
    for patient_id in sorted(base_rows):
        triggered: list[str] = []
        missing: list[str] = []
        score = 0.0
        for row in feature_rows:
            value = to_float(lookups[metric_key(row)].get(patient_id, {}).get(row["feature_name"]))
            threshold = to_float(row.get("weighted_threshold"))
            weight = to_float(row.get("weighted_feature_weight")) or 0.0
            if value is None or threshold is None:
                missing.append(row["feature_name"])
                continue
            if value >= threshold:
                score += weight
                triggered.append(
                    f"{row['feature_name']}={fmt(value)}>=阈值{fmt(threshold)} 权重{fmt(weight)}"
                )
        score_rows.append(
            {
                "patient_id": patient_id,
                "base": base_rows[patient_id],
                "score": score,
                "triggered_features": ";".join(triggered),
                "missing_features": ";".join(missing),
                "triggered_feature_count": len(triggered),
            }
        )

    threshold_row = select_weighted_score_threshold(score_rows, combined_fp_max)
    threshold = float(threshold_row["score_threshold"])
    predictions: list[dict[str, str]] = []
    for row in score_rows:
        predicted = row["score"] >= threshold
        predictions.append(
            prediction_row(
                method=METHOD_WEIGHTED,
                base=row["base"],
                score=row["score"],
                threshold=threshold,
                predicted=predicted,
                triggered_feature_count=row["triggered_feature_count"],
                triggered_features=row["triggered_features"],
                missing_features=row["missing_features"],
                reason=(
                    f"核心加权得分 {fmt(row['score'])} "
                    f"{'>=' if predicted else '<'} 阈值 {fmt(threshold)}；"
                    f"触发 {row['triggered_feature_count']}/{len(feature_rows)} 个核心特征。"
                ),
                threshold_rule="",
            )
        )
    return predictions, threshold_row


def select_weighted_score_threshold(rows: list[Mapping[str, Any]], combined_fp_max: int) -> dict[str, str]:
    labels = [int(row["base"]["label_binary"]) for row in rows]
    scores = [float(row["score"]) for row in rows]
    candidates = sorted(set(scores + [max(scores or [0.0]) + 1e-6]), reverse=True)
    sweep: list[dict[str, str]] = []
    for threshold in candidates:
        predicted = [score >= threshold for score in scores]
        metrics = binary_metrics(labels, predicted)
        sweep.append({"score_threshold": fmt(threshold), "patient_count": str(len(rows)), **metrics})
    eligible = [row for row in sweep if int(row["fp"]) <= combined_fp_max]
    if eligible:
        selected = max(
            eligible,
            key=lambda row: (
                float(row["recall"]),
                float(row["precision"]),
                float(row["specificity"]),
                float(row["f1"]),
                float(row["score_threshold"]),
            ),
        )
    else:
        selected = min(
            sweep,
            key=lambda row: (
                int(row["fp"]),
                -float(row["recall"]),
                -float(row["precision"]),
                -float(row["specificity"]),
            ),
        )
    return dict(selected)


def weighted_rule_description(
    feature_rows: list[Mapping[str, Any]],
    score_threshold: str,
    quantile_name: str,
) -> str:
    parts = [
        (
            f"{row['feature_name']}[{row['role_scope']}/{row['aggregation']}] "
            f">= {row['weighted_threshold']} * weight {row['weighted_feature_weight']}"
        )
        for row in feature_rows
    ]
    return f"{quantile_name} weighted score >= {score_threshold}: " + "; ".join(parts)


def patient_lookups(
    feature_rows: list[Mapping[str, Any]],
    patient_rows_by_scope: Mapping[tuple[str, str], list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, Mapping[str, Any]]], dict[str, Mapping[str, Any]]]:
    lookups: dict[str, dict[str, Mapping[str, Any]]] = {}
    base_rows: dict[str, Mapping[str, Any]] = {}
    for feature_row in feature_rows:
        key = (feature_row["role_scope"], feature_row["aggregation"])
        rows = patient_rows_by_scope[key]
        lookup = {row["patient_sample_id"]: row for row in rows}
        lookups[metric_key(feature_row)] = lookup
        for patient_id, row in lookup.items():
            base_rows.setdefault(patient_id, row)
    return lookups, base_rows


def prediction_row(
    *,
    method: str,
    base: Mapping[str, Any],
    score: float,
    threshold: float,
    predicted: bool,
    triggered_feature_count: int,
    triggered_features: str,
    missing_features: str,
    reason: str,
    threshold_rule: str,
) -> dict[str, str]:
    predicted_label = "1" if predicted else "0"
    return {
        "method": method,
        "patient_sample_id": str(base["patient_sample_id"]),
        "source_dataset": str(base["dataset_key"]),
        "source_patient_sample_id": str(base["source_patient_sample_id"]),
        "split": "",
        "label_group": str(base["label_group"]),
        "label_binary": str(base["label_binary"]),
        "score": fmt(score),
        "score_threshold": fmt(threshold),
        "predicted_label_binary": predicted_label,
        "predicted_label_group": "患病" if predicted else "不患病",
        "patient_disease_rule_output": "患病倾向较高" if predicted else "未达到患病阈值",
        "confusion_type": confusion_type(str(base["label_binary"]), predicted_label),
        "triggered_feature_count": str(triggered_feature_count),
        "triggered_features": triggered_features,
        "missing_features": missing_features,
        "patient_decision_reason": reason,
        "threshold_rule": threshold_rule,
    }


def select_low_fpr_variant(variants: list[dict[str, Any]], combined_fp_max: int) -> dict[str, Any]:
    eligible = [variant for variant in variants if int(variant["metrics"]["fp"]) <= combined_fp_max]
    if eligible:
        selected = max(
            eligible,
            key=lambda variant: (
                float(variant["metrics"]["recall"]),
                float(variant["metrics"]["precision"]),
                float(variant["metrics"]["specificity"]),
                float(variant["metrics"]["f1"]),
                quantile_rank(variant["quantile"]),
            ),
        )
    else:
        selected = min(
            variants,
            key=lambda variant: (
                int(variant["metrics"]["fp"]),
                -float(variant["metrics"]["recall"]),
                -float(variant["metrics"]["precision"]),
                -quantile_rank(variant["quantile"]),
            ),
        )
    selected = dict(selected)
    selected["low_fpr_constraint_pass"] = str(int(selected["metrics"]["fp"]) <= combined_fp_max).lower()
    selected["combined_fp_max"] = str(combined_fp_max)
    return selected


def quantile_rank(name: str) -> int:
    return {"P99": 1, "P995": 2, "P999": 3}.get(name, 0)


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
        item["split"] = resolve_split(row, split_lookup)
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
    raise ValueError(f"Cannot resolve split for prediction row: {row.get('patient_sample_id')}")


def extract_patient_id(source_patient_sample_id: str) -> str:
    match = re.search(r"pid(\d+)", source_patient_sample_id)
    return match.group(1) if match else ""


def build_comparison_rows(
    rule62_rows: list[Mapping[str, str]],
    and_rows: list[Mapping[str, str]],
    weighted_rows: list[Mapping[str, str]],
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for method, rows in [(METHOD_RULE62, rule62_rows), (METHOD_AND, and_rows), (METHOD_WEIGHTED, weighted_rows)]:
        threshold_rule = comparison_threshold_rule(method, rows)
        for split in SPLIT_ORDER:
            split_rows = list(rows) if split == "combined" else [row for row in rows if row.get("split") == split]
            metrics = metrics_from_prediction_rows(split_rows)
            fp = int(metrics["fp"])
            tn = int(metrics["tn"])
            output.append(
                {
                    "method": method,
                    "split": split,
                    "patient_count": str(len(split_rows)),
                    "tp_count": metrics["tp"],
                    "fp_count": metrics["fp"],
                    "tn_count": metrics["tn"],
                    "fn_count": metrics["fn"],
                    "fp_rate": fmt(safe_div(fp, fp + tn)),
                    "recall": metrics["recall"],
                    "precision": metrics["precision"],
                    "specificity": metrics["specificity"],
                    "f1": metrics["f1"],
                    "threshold/rule": threshold_rule,
                }
            )
    return output


def comparison_threshold_rule(method: str, rows: list[Mapping[str, str]]) -> str:
    if not rows:
        return ""
    if method == METHOD_RULE62:
        threshold = rows[0].get("score_threshold", "")
        return threshold or "0.612826"
    return rows[0].get("threshold_rule", "")


def metrics_from_prediction_rows(rows: list[Mapping[str, str]]) -> dict[str, str]:
    labels = [int(row["label_binary"]) for row in rows]
    predicted = [row["predicted_label_binary"] == "1" for row in rows]
    return binary_metrics(labels, predicted)


def safe_div(numerator: float, denominator: float) -> float:
    return 0.0 if denominator <= 0 else numerator / denominator


def build_summary(
    *,
    args: argparse.Namespace,
    paths: Mapping[str, Path],
    old_image_rows: list[Mapping[str, str]],
    new_image_rows: list[Mapping[str, str]],
    all_metric_rows: list[Mapping[str, str]],
    tail_rows: list[Mapping[str, Any]],
    selected_rows: list[Mapping[str, Any]],
    and_variant: Mapping[str, Any],
    weighted_variant: Mapping[str, Any],
    weighted_features: list[Mapping[str, Any]],
    comparison_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    strict_rows = [row for row in tail_rows if row["strict_filter_pass"] == "true"]
    comparison_lookup = {(row["method"], row["split"]): row for row in comparison_rows}
    low_fpr_methods = [
        comparison_lookup[(method, "combined")]
        for method in (METHOD_AND, METHOD_WEIGHTED)
        if int(comparison_lookup[(method, "combined")]["fp_count"]) <= args.combined_fp_max
    ]
    best_low_fpr = max(
        low_fpr_methods,
        key=lambda row: (float(row["recall"]), float(row["precision"]), -int(row["fp_count"])),
        default=None,
    )
    return {
        "inputs": {name: path.as_posix() for name, path in paths.items()},
        "output_dir": args.output_dir.as_posix(),
        "old_detected_image_rows": len(old_image_rows),
        "new_detected_image_rows": len(new_image_rows),
        "old_detected_patient_count": len({row["patient_sample_id"] for row in old_image_rows}),
        "new_detected_patient_count": len({row["patient_sample_id"] for row in new_image_rows}),
        "all_metric_row_count": len(all_metric_rows),
        "tail_row_count": len(tail_rows),
        "strict_filter": {
            "patient_above_P99_rate_min": args.patient_above_p99_rate_min,
            "tail_ratio_min": args.tail_ratio_min,
            "cross_data_p99_relative_diff_max": args.cross_data_p99_relative_diff_max,
            "strict_pass_count": len(strict_rows),
        },
        "top_tail_features": [
            {
                "feature_name": row["feature_name"],
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "tail_separation_ratio": row["tail_separation_ratio"],
                "patient_above_P99_rate": row["patient_above_P99_rate"],
                "cross_data_tail_consistent": row["cross_data_tail_consistent"],
            }
            for row in tail_rows[:10]
        ],
        "selected_features": [
            {
                "feature_name": row["feature_name"],
                "role_scope": row["role_scope"],
                "aggregation": row["aggregation"],
                "selection_group": row.get("selection_group", ""),
                "strict_filter_pass": row["strict_filter_pass"],
                "selected_for_and_3": row.get("selected_for_and_3", ""),
                "selected_for_weighted": row.get("selected_for_weighted", ""),
            }
            for row in selected_rows
        ],
        "and_variant": {
            "quantile": and_variant["quantile"],
            "low_fpr_constraint_pass": and_variant["low_fpr_constraint_pass"],
            "combined_metrics": and_variant["metrics"],
            "rule": and_variant["rule"],
        },
        "weighted_variant": {
            "quantile": weighted_variant["quantile"],
            "score_threshold": weighted_variant.get("score_threshold", ""),
            "low_fpr_constraint_pass": weighted_variant["low_fpr_constraint_pass"],
            "combined_metrics": weighted_variant["metrics"],
            "rule": weighted_variant["rule"],
            "features": [
                {
                    "feature_name": row["feature_name"],
                    "role_scope": row["role_scope"],
                    "aggregation": row["aggregation"],
                    "threshold": row["weighted_threshold"],
                    "weight": row["weighted_feature_weight"],
                    "tail_separation_ratio": row["tail_separation_ratio"],
                }
                for row in weighted_features
            ],
        },
        "comparison": comparison_rows,
        "best_low_fpr_method": best_low_fpr,
        "warning": "Labels are patient outcome weak labels. These metrics are technical comparisons, not clinical diagnostic performance.",
    }


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    tail_rows: list[Mapping[str, Any]],
    selected_rows: list[Mapping[str, Any]],
    comparison_rows: list[Mapping[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    strict_count = summary["strict_filter"]["strict_pass_count"]
    comparison_lookup = {(row["method"], row["split"]): row for row in comparison_rows}
    rule62_combined = comparison_lookup[(METHOD_RULE62, "combined")]
    and_combined = comparison_lookup[(METHOD_AND, "combined")]
    weighted_combined = comparison_lookup[(METHOD_WEIGHTED, "combined")]
    best = summary["best_low_fpr_method"]
    lines = [
        "# Task 05 极低误检率尾部特征规则",
        "",
        "## 输入与口径",
        "",
        f"- 60 阶段全量特征组合：`{summary['tail_row_count']}` 行。",
        f"- 旧数据 detected 图片：`{summary['old_detected_image_rows']}`，患者：`{summary['old_detected_patient_count']}`。",
        f"- 新数据 detected 图片：`{summary['new_detected_image_rows']}`，患者：`{summary['new_detected_patient_count']}`。",
        "- 旧数据 split 来自 `05_patient_splits.csv`；新数据作为外部 test 纳入 test 分片。",
        "- 指标基于患者 outcome 弱标签，只能作为技术规则对比。",
        "",
        "## S1 尾部特征分析",
        "",
        (
            f"- 严格筛选条件：`patient_above_P99_rate >= {fmt(summary['strict_filter']['patient_above_P99_rate_min'])}`、"
            f"`tail_separation_ratio >= {fmt(summary['strict_filter']['tail_ratio_min'])}`、"
            f"`cross_data_tail_consistent == True`。"
        ),
        f"- 严格通过特征数：`{strict_count}`。",
    ]
    if strict_count == 0:
        lines.append(
            "- 当前数据没有出现“患病 P90 超过非患病 P99 1.5 倍”的极端尾部区域；方案 A 使用 top-tail fallback 仅用于完成可复核的低 FP 对比。"
        )
    lines.extend(["", "### Top Tail Features", ""])
    lines.extend(
        markdown_table(
            [
                "rank",
                "feature",
                "role",
                "agg",
                "direction",
                "tail_ratio",
                "patient>P99",
                "nonpatient_P99",
                "fp@P99",
                "consistent",
                "strict",
            ],
            [
                [
                    row["tail_rank"],
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["combined_direction"],
                    row["tail_separation_ratio"],
                    row["patient_above_P99_rate"],
                    row["nonpatient_P99"],
                    row["combined_fp_at_P99"],
                    row["cross_data_tail_consistent"],
                    row["strict_filter_pass"],
                ]
                for row in tail_rows[:12]
            ],
        )
    )
    lines.extend(["", "## S2/S3 规则构建", ""])
    lines.extend(
        markdown_table(
            [
                "feature",
                "role",
                "agg",
                "strict",
                "for_AND",
                "for_weighted",
                "tail_ratio",
                "P99",
                "P995",
                "P999",
                "selection",
            ],
            [
                [
                    row["feature_name"],
                    row["role_scope"],
                    row["aggregation"],
                    row["strict_filter_pass"],
                    row.get("selected_for_and_3", ""),
                    row.get("selected_for_weighted", ""),
                    row["tail_separation_ratio"],
                    row["nonpatient_P99"],
                    row["nonpatient_P995"],
                    row["nonpatient_P999"],
                    row.get("selection_group", ""),
                ]
                for row in selected_rows
            ],
        )
    )
    lines.extend(
        [
            "",
            "## S4 指标对比",
            "",
            "- FP count 是首要指标；FP rate 按 `FP / (TN + FP)` 计算。",
            f"- 规则 62 combined：FP `{rule62_combined['fp_count']}`，recall `{rule62_combined['recall']}`，precision `{rule62_combined['precision']}`。",
            f"- AND 方案 combined：FP `{and_combined['fp_count']}`，recall `{and_combined['recall']}`，precision `{and_combined['precision']}`。",
            f"- Weighted 方案 combined：FP `{weighted_combined['fp_count']}`，recall `{weighted_combined['recall']}`，precision `{weighted_combined['precision']}`。",
            "",
        ]
    )
    lines.extend(
        markdown_table(
            [
                "method",
                "split",
                "patients",
                "TP",
                "FP",
                "TN",
                "FN",
                "fp_rate",
                "recall",
                "precision",
                "specificity",
                "f1",
            ],
            [
                [
                    row["method"],
                    row["split"],
                    row["patient_count"],
                    row["tp_count"],
                    row["fp_count"],
                    row["tn_count"],
                    row["fn_count"],
                    row["fp_rate"],
                    row["recall"],
                    row["precision"],
                    row["specificity"],
                    row["f1"],
                ]
                for row in comparison_rows
            ],
        )
    )
    lines.extend(["", "## 与规则 62 的 combined 差值", ""])
    lines.extend(
        markdown_table(
            ["method", "FP_delta", "recall_delta", "precision_delta", "specificity_delta"],
            [
                delta_row(rule62_combined, and_combined),
                delta_row(rule62_combined, weighted_combined),
            ],
        )
    )
    lines.extend(["", "## 结论", ""])
    if best:
        fp_rate = float(best["fp_rate"])
        literal_per_mille = fp_rate <= 0.001
        lines.extend(
            [
                (
                    f"- 在 `combined FP <= 1` 约束下，最佳正预测方案为 `{best['method']}`："
                    f"FP `{best['fp_count']}`，recall `{best['recall']}`，precision `{best['precision']}`。"
                ),
                (
                    "- 按验收口径 `FP <= 1`：达到。"
                    if int(best["fp_count"]) <= 1
                    else "- 按验收口径 `FP <= 1`：未达到。"
                ),
                (
                    "- 按字面 `FP rate <= 0.001`：达到。"
                    if literal_per_mille
                    else "- 按字面 `FP rate <= 0.001`：未达到；当前非患病样本量下 1 个 FP 的 rate 高于 0.001，除非 FP 为 0。"
                ),
            ]
        )
    else:
        lines.append("- 没有方案在 combined 上达到 `FP <= 1`。")
    lines.extend(
        [
            "",
            "## 产物",
            "",
            "- `low_fpr_tail_features.csv`：S1 全量尾部扫描。",
            "- `low_fpr_selected_features.csv`：严格筛选和规则选用特征。",
            "- `low_fpr_patient_predictions.csv`：方案 A/B 患者级预测。",
            "- `low_fpr_comparison.csv`：规则 62、AND、Weighted 的 split 指标对比。",
            "",
            "## 限制",
            "",
            "这里的 `患病/不患病` 是患者 outcome 弱标签，不是人工面部不对称标签，也不是临床诊断标签。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def delta_row(baseline: Mapping[str, str], current: Mapping[str, str]) -> list[str]:
    return [
        current["method"],
        str(int(current["fp_count"]) - int(baseline["fp_count"])),
        fmt(float(current["recall"]) - float(baseline["recall"])),
        fmt(float(current["precision"]) - float(baseline["precision"])),
        fmt(float(current["specificity"]) - float(baseline["specificity"])),
    ]


def tail_feature_fields() -> list[str]:
    return [
        "tail_rank",
        "role_scope",
        "role_scope_description",
        "aggregation",
        "feature_type",
        "feature_name",
        "candidate_grade",
        "combined_direction",
        "old_direction",
        "new_direction",
        "direction_consistent",
        "old_directional_auc",
        "new_directional_auc",
        "combined_directional_auc",
        "combined_patient_n",
        "combined_patient_n_with_feature",
        "combined_positive_n",
        "combined_negative_n",
        "old_negative_n",
        "new_negative_n",
        "nonpatient_P99",
        "nonpatient_P995",
        "nonpatient_P999",
        "nonpatient_max",
        "old_nonpatient_P99",
        "new_nonpatient_P99",
        "old_patient_above_old_P99_rate",
        "new_patient_above_new_P99_rate",
        "cross_data_p99_relative_diff",
        "cross_data_tail_consistent",
        "patient_P90",
        "patient_P99",
        "patient_above_P99_rate",
        "patient_above_P995_rate",
        "patient_above_P999_rate",
        "tail_separation_ratio",
        "combined_fp_at_P99",
        "combined_fp_at_P995",
        "combined_fp_at_P999",
        "combined_fp_rate_at_P99",
        "combined_fp_rate_at_P995",
        "combined_fp_rate_at_P999",
        "strict_filter_pass",
        "filter_failure_reasons",
    ]


def selected_feature_fields() -> list[str]:
    return [
        "selection_rank",
        "selection_group",
        "selection_reason",
        "selected_for_and_3",
        "selected_for_weighted",
        *tail_feature_fields(),
    ]


def prediction_fields() -> list[str]:
    return [
        "method",
        "patient_sample_id",
        "source_dataset",
        "source_patient_sample_id",
        "split",
        "label_group",
        "label_binary",
        "score",
        "score_threshold",
        "predicted_label_binary",
        "predicted_label_group",
        "patient_disease_rule_output",
        "confusion_type",
        "triggered_feature_count",
        "triggered_features",
        "missing_features",
        "patient_decision_reason",
        "threshold_rule",
    ]


def comparison_fields() -> list[str]:
    return [
        "method",
        "split",
        "patient_count",
        "tp_count",
        "fp_count",
        "tn_count",
        "fn_count",
        "fp_rate",
        "recall",
        "precision",
        "specificity",
        "f1",
        "threshold/rule",
    ]


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    main()
