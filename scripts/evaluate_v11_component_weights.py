#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.build_v11_hb_proxy_grading import (  # noqa: E402
    COMPONENT_LABELS as HB_COMPONENT_LABELS,
    COMPONENT_WEIGHTS as HB_COMPONENT_WEIGHTS,
    build_components,
    build_expression_strengths,
    feature_family,
    feature_source,
    is_mediapipe_grade_feature,
    overall_proxy_score,
)


DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

COMPONENTS = (
    "resting_symmetry_score",
    "eye_closure_score",
    "brow_forehead_score",
    "smile_mouth_score",
    "gross_asymmetry_score",
    "movement_absence_score",
)
CORE_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
FEATURE_SCOPES = ("all_core_roles", *CORE_ROLES)
SPLITS = ("train", "val", "test", "all")
MIN_SPECIFICITY_TARGET = 0.85
MAX_COMPONENT_WEIGHT = 0.30
MIN_COMPONENT_WEIGHT = 0.05
BETA_FOR_RECALL = 2.0


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    split_config_rows = read_csv(required(metadata / "05_patient_splits.csv"))
    patient_core_rows = read_csv(required(metadata / "11_v11_role_aware_patient_core_results.csv"))
    full_feature_rows = read_csv(required(metadata / "09_mediapipe_full_features.csv"))

    patient_set = build_patient_set_from_original_inputs(split_config_rows, patient_core_rows, full_feature_rows)
    train_rows = split_rows(patient_set, "train")
    train_val_rows = split_rows(patient_set, "train_val")
    normalizers = build_component_normalizers(train_rows if train_rows else train_val_rows)
    normalized_rows = add_normalized_components(patient_set, normalizers)
    normalized_train_rows = split_rows(normalized_rows, "train")
    normalized_train_val_rows = split_rows(normalized_rows, "train_val")
    normalized_val_rows = split_rows(normalized_rows, "val")
    threshold_rows = normalized_val_rows if has_both_labels(normalized_val_rows) else normalized_train_val_rows
    component_effect_rows = build_component_effect_rows(normalized_rows)
    component_utilities = build_component_utilities(component_effect_rows)
    universal_feature_rows = build_universal_feature_scores(full_feature_rows, patient_split_map(normalized_rows))

    schemes = build_candidate_schemes(
        normalized_rows,
        component_utilities,
        threshold_rows,
        normalized_train_rows if normalized_train_rows else normalized_train_val_rows,
    )
    candidate_rows, candidate_summary = evaluate_candidate_schemes(normalized_rows, schemes)
    summary = build_summary(
        normalized_rows,
        component_effect_rows,
        universal_feature_rows,
        candidate_summary,
        component_utilities,
        normalizers,
    )

    write_csv(metadata / "19_component_weight_evaluation_patient_set.csv", normalized_rows)
    write_csv(metadata / "19_component_weight_universal_feature_scores.csv", universal_feature_rows)
    write_csv(metadata / "19_component_weight_candidates.csv", candidate_rows)
    write_json(metadata / "19_component_weight_evaluation_summary.json", summary)
    write_report(reports / "19_component_weight_evaluation.md", summary, component_effect_rows, candidate_rows, universal_feature_rows)

    print(f"Wrote {metadata / '19_component_weight_evaluation_patient_set.csv'}")
    print(f"Wrote {metadata / '19_component_weight_universal_feature_scores.csv'}")
    print(f"Wrote {metadata / '19_component_weight_candidates.csv'}")
    print(f"Wrote {metadata / '19_component_weight_evaluation_summary.json'}")
    print(f"Wrote {reports / '19_component_weight_evaluation.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate and calibrate V1.1 HB proxy component weights.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing V1.1 metadata.")
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
        "label_group",
        "label_binary",
        "split",
        "standalone_overall_score",
        "scheme",
        "evaluation_split",
        "component",
        "component_label",
        "feature_name",
        "component_target",
        "universal_feature_score",
    ]
    fields = [field for field in preferred if field in fields] + [field for field in fields if field not in preferred]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_patient_set_from_original_inputs(
    split_config_rows: list[Mapping[str, Any]],
    patient_core_rows: list[Mapping[str, Any]],
    full_feature_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    split_by_patient = {
        str(row.get("patient_sample_id", "")): row
        for row in split_config_rows
        if row.get("patient_sample_id")
    }
    core_by_patient = {
        str(row.get("patient_sample_id", "")): row
        for row in patient_core_rows
        if row.get("patient_sample_id")
    }
    expression = build_expression_strengths(list(full_feature_rows), split_by_patient)
    median_weight = median(
        value
        for row in patient_core_rows
        if row.get("split") in {"train", "val"}
        if (value := parse_float(row.get("patient_weight_total"))) is not None
    )
    output: list[dict[str, Any]] = []
    for patient_id in sorted(split_by_patient):
        split_row = split_by_patient[patient_id]
        core_row = core_by_patient.get(patient_id)
        components = build_components(core_row, expression.get(patient_id, {}), median_weight)
        missing_roles = [
            role
            for role in CORE_ROLES
            if not core_row or core_row.get(f"{role}_available") != "1"
        ]
        item = {
            "patient_sample_id": patient_id,
            "label_group": split_row.get("label_group", core_row.get("label_group", "") if core_row else ""),
            "label_binary": split_row.get("label_binary", core_row.get("label_binary", "") if core_row else ""),
            "split": split_row.get("split", core_row.get("split", "") if core_row else ""),
            "core_row_available": "1" if core_row else "0",
            "quality_reliability_score": fmt_optional(components.get("quality_reliability_score")),
            "included_roles_available": core_row.get("included_roles_available", "0") if core_row else "0",
            "missing_hb_roles": ";".join(missing_roles),
            "top_positive_features": core_row.get("top_positive_features", "") if core_row else "",
            "standalone_overall_score": fmt_optional(overall_proxy_score(components)),
            "mouth_expression_strength": fmt_optional(components.get("mouth_expression_strength")),
            "brow_expression_strength": fmt_optional(components.get("brow_expression_strength")),
            "eye_blink_strength": fmt_optional(components.get("eye_blink_strength")),
            "dynamic_expression_strength": fmt_optional(components.get("dynamic_expression_strength")),
        }
        for component in COMPONENTS:
            item[component] = fmt_optional(components.get(component))
        output.append(item)
    return output


def build_component_normalizers(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    normalizers: dict[str, dict[str, Any]] = {}
    for component in COMPONENTS:
        values = sorted(value for row in rows if (value := parse_float(row.get(component))) is not None)
        if not values:
            normalizers[component] = {"values": [], "p99": 1.0, "median": 0.0, "mad": 1.0}
            continue
        median_value = quantile(values, 0.50)
        mad = median([abs(value - median_value) for value in values]) or 1e-6
        normalizers[component] = {
            "values": values,
            "p99": quantile(values, 0.99),
            "median": median_value,
            "mad": mad,
        }
    return normalizers


def add_normalized_components(
    rows: list[Mapping[str, Any]],
    normalizers: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for component in COMPONENTS:
            value = parse_float(row.get(component))
            if value is None:
                item[f"{component}_norm"] = ""
                item[f"{component}_capped"] = ""
                continue
            normalizer = normalizers[component]
            capped = min(value, float(normalizer["p99"]))
            item[f"{component}_capped"] = fmt(capped)
            item[f"{component}_norm"] = fmt(empirical_cdf(capped, normalizer.get("values", [])))
        output.append(item)
    return output


def build_component_effect_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for component in COMPONENTS:
        split_stats = {
            split: component_effect(split_rows(rows, split), component)
            for split in SPLITS
        }
        all_direction = direction(split_stats["all"]["diseased_minus_nondisease"])
        for split in SPLITS:
            stats = split_stats[split]
            output.append(
                {
                    "component": component,
                    "component_label": HB_COMPONENT_LABELS[component],
                    "split": split,
                    "diseased_n": stats["diseased_n"],
                    "nondisease_n": stats["nondisease_n"],
                    "diseased_mean": fmt_optional(stats["diseased_mean"]),
                    "nondisease_mean": fmt_optional(stats["nondisease_mean"]),
                    "diseased_minus_nondisease": fmt(stats["diseased_minus_nondisease"]),
                    "standardized_effect": fmt(stats["standardized_effect"]),
                    "auc": fmt(stats["auc"]),
                    "direction": direction(stats["diseased_minus_nondisease"]),
                    "direction_matches_all": str(direction(stats["diseased_minus_nondisease"]) == all_direction).lower(),
                    "nondisease_high_rate": fmt(stats["nondisease_high_rate"]),
                    "diseased_high_rate": fmt(stats["diseased_high_rate"]),
                }
            )
    return output


def component_effect(rows: list[Mapping[str, Any]], component: str) -> dict[str, Any]:
    pos = [value for row in rows if row.get("label_binary") == "1" if (value := parse_float(row.get(component))) is not None]
    neg = [value for row in rows if row.get("label_binary") == "0" if (value := parse_float(row.get(component))) is not None]
    pos_mean = mean(pos) if pos else None
    neg_mean = mean(neg) if neg else None
    delta = (pos_mean or 0.0) - (neg_mean or 0.0) if pos and neg else 0.0
    pooled = math.sqrt((std(pos) ** 2 + std(neg) ** 2) / 2.0) if pos and neg else 0.0
    threshold = quantile(pos + neg, 0.85) if pos or neg else 0.0
    return {
        "diseased_n": len(pos),
        "nondisease_n": len(neg),
        "diseased_mean": pos_mean,
        "nondisease_mean": neg_mean,
        "diseased_minus_nondisease": delta,
        "standardized_effect": delta / pooled if pooled > 1e-12 else 0.0,
        "auc": roc_auc(pos, neg),
        "diseased_high_rate": sum(1 for value in pos if value >= threshold) / len(pos) if pos else 0.0,
        "nondisease_high_rate": sum(1 for value in neg if value >= threshold) / len(neg) if neg else 0.0,
    }


def build_component_utilities(component_rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    rows_by_component: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in component_rows:
        rows_by_component[str(row["component"])][str(row["split"])] = row

    utilities: dict[str, dict[str, Any]] = {}
    for component in COMPONENTS:
        split_payload = rows_by_component[component]
        all_row = split_payload.get("all", {})
        auc = parse_float(all_row.get("auc")) or 0.5
        effect = max(0.0, parse_float(all_row.get("standardized_effect")) or 0.0)
        false_positive_penalty = parse_float(all_row.get("nondisease_high_rate")) or 0.0
        valid_splits = [split_payload.get(split, {}) for split in ("train", "val", "test")]
        direction_hits = sum(1 for row in valid_splits if row.get("direction") == "diseased_higher")
        split_stability = direction_hits / len(valid_splits) if valid_splits else 0.0
        utility = max(0.0, auc - 0.5) * effect * split_stability * (1.0 - false_positive_penalty)
        utilities[component] = {
            "component": component,
            "component_label": HB_COMPONENT_LABELS[component],
            "auc": fmt(auc),
            "effect": fmt(effect),
            "split_stability": fmt(split_stability),
            "false_positive_penalty": fmt(false_positive_penalty),
            "component_utility": fmt(utility),
        }
    return utilities


def build_universal_feature_scores(
    feature_rows: list[Mapping[str, Any]],
    split_by_patient: Mapping[str, str],
    *,
    min_label_count: int = 10,
) -> list[dict[str, Any]]:
    if not feature_rows:
        return []
    feature_names = [name for name in feature_rows[0] if is_mediapipe_grade_feature(name)]
    prelim: list[dict[str, Any]] = []
    for scope in FEATURE_SCOPES:
        scoped_rows = [
            row for row in feature_rows
            if scope == "all_core_roles" and row.get("media_role") in CORE_ROLES
            or scope != "all_core_roles" and row.get("media_role") == scope
        ]
        for feature_name in feature_names:
            patient_values = patient_mean_values(scoped_rows, feature_name, split_by_patient)
            stats_by_split = {
                split: label_effect_for_patient_values(patient_values, split, min_label_count)
                for split in SPLITS
            }
            all_stats = stats_by_split["all"]
            if all_stats["diseased_n"] < min_label_count or all_stats["nondisease_n"] < min_label_count:
                continue
            directions = [direction(stats_by_split[split]["delta"]) for split in ("train", "val", "test")]
            direction_consistency = sum(1 for item in directions if item == "diseased_higher") / len(directions)
            effect_strength = max(0.0, all_stats["standardized_effect"])
            false_positive_penalty = all_stats["nondisease_high_rate"]
            universal_score = direction_consistency * effect_strength * max(0.0, all_stats["auc"] - 0.5) * (1.0 - false_positive_penalty)
            prelim.append(
                {
                    "scope": scope,
                    "feature_name": feature_name,
                    "feature_family": feature_family(feature_name),
                    "feature_source": feature_source(feature_name),
                    "component_target": component_for_feature(feature_name),
                    "direction_consistency": fmt(direction_consistency),
                    "split_stability": fmt(direction_consistency),
                    "role_stability": "0.000000",
                    "effect_size_strength": fmt(effect_strength),
                    "false_positive_penalty": fmt(false_positive_penalty),
                    "quality_robustness": "1.000000",
                    "universal_feature_score": fmt(universal_score),
                    "all_diseased_mean": fmt_optional(all_stats["diseased_mean"]),
                    "all_nondisease_mean": fmt_optional(all_stats["nondisease_mean"]),
                    "all_effect": fmt(all_stats["standardized_effect"]),
                    "all_auc": fmt(all_stats["auc"]),
                    "train_direction": directions[0],
                    "val_direction": directions[1],
                    "test_direction": directions[2],
                }
            )
    role_stability = role_stability_by_feature(prelim)
    for row in prelim:
        stability = role_stability.get(row["feature_name"], 0.0)
        base_score = parse_float(row["universal_feature_score"]) or 0.0
        row["role_stability"] = fmt(stability)
        row["universal_feature_score"] = fmt(base_score * max(stability, 0.25))
    return sorted(prelim, key=lambda row: (-(parse_float(row["universal_feature_score"]) or 0.0), row["scope"], row["feature_name"]))


def patient_mean_values(
    rows: list[Mapping[str, Any]],
    feature_name: str,
    split_by_patient: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    values_by_patient: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        patient_id = str(row.get("patient_sample_id", ""))
        value = parse_float(row.get(feature_name))
        if not patient_id or value is None:
            continue
        values_by_patient[patient_id].append(value)
        grouped.setdefault(
            patient_id,
            {
                "patient_sample_id": patient_id,
                "label_binary": row.get("label_binary", ""),
                "label_group": row.get("label_group", ""),
                "split": row.get("split", "") or split_by_patient.get(patient_id, ""),
            },
        )
    for patient_id, values in values_by_patient.items():
        grouped[patient_id]["value"] = mean(values)
    return grouped


def patient_split_map(rows: list[Mapping[str, Any]]) -> dict[str, str]:
    return {
        str(row.get("patient_sample_id", "")): str(row.get("split", ""))
        for row in rows
        if row.get("patient_sample_id")
    }


def label_effect_for_patient_values(
    patient_values: Mapping[str, Mapping[str, Any]],
    split: str,
    min_label_count: int,
) -> dict[str, Any]:
    rows = [
        row for row in patient_values.values()
        if "value" in row and (split == "all" or row.get("split") == split)
    ]
    pos = [float(row["value"]) for row in rows if row.get("label_binary") == "1"]
    neg = [float(row["value"]) for row in rows if row.get("label_binary") == "0"]
    if len(pos) < min_label_count or len(neg) < min_label_count:
        return {
            "diseased_n": len(pos),
            "nondisease_n": len(neg),
            "diseased_mean": None,
            "nondisease_mean": None,
            "delta": 0.0,
            "standardized_effect": 0.0,
            "auc": 0.5,
            "nondisease_high_rate": 1.0,
        }
    pos_mean = mean(pos)
    neg_mean = mean(neg)
    pooled = math.sqrt((std(pos) ** 2 + std(neg) ** 2) / 2.0)
    threshold = quantile(pos + neg, 0.85)
    return {
        "diseased_n": len(pos),
        "nondisease_n": len(neg),
        "diseased_mean": pos_mean,
        "nondisease_mean": neg_mean,
        "delta": pos_mean - neg_mean,
        "standardized_effect": (pos_mean - neg_mean) / pooled if pooled > 1e-12 else 0.0,
        "auc": roc_auc(pos, neg),
        "nondisease_high_rate": sum(1 for value in neg if value >= threshold) / len(neg),
    }


def role_stability_by_feature(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["scope"] in CORE_ROLES:
            grouped[str(row["feature_name"])].append(row)
    stability: dict[str, float] = {}
    for feature_name, feature_rows in grouped.items():
        if not feature_rows:
            stability[feature_name] = 0.0
            continue
        hits = sum(1 for row in feature_rows if row.get("train_direction") == "diseased_higher" or row.get("val_direction") == "diseased_higher" or row.get("test_direction") == "diseased_higher")
        stability[feature_name] = hits / len(feature_rows)
    return stability


def component_for_feature(feature_name: str) -> str:
    name = feature_name.lower()
    if any(token in name for token in ("mouth", "lip", "smile", "jawopen", "jaw_open")):
        return "smile_mouth_score"
    if any(token in name for token in ("brow", "forehead", "frown")):
        return "brow_forehead_score"
    if any(token in name for token in ("eye", "iris", "blink")):
        return "eye_closure_score"
    if any(token in name for token in ("all_mesh", "face_oval", "jaw", "cheek", "contour")):
        return "gross_asymmetry_score"
    return "resting_symmetry_score"


def build_candidate_schemes(
    rows: list[Mapping[str, Any]],
    component_utilities: Mapping[str, Mapping[str, Any]],
    threshold_rows: list[Mapping[str, Any]],
    train_rows: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    current_weights = {component: float(HB_COMPONENT_WEIGHTS[component]) for component in COMPONENTS}
    equal_weights = {component: 1.0 / len(COMPONENTS) for component in COMPONENTS}
    utility_scores = {
        component: parse_float(component_utilities[component]["component_utility"]) or 0.0
        for component in COMPONENTS
    }
    utility_weights = bounded_normalize_weights(utility_scores)
    logistic_weights = fit_constrained_logistic_weights(train_rows)
    current_scheme = make_threshold_scheme("current_fixed_weights", current_weights, threshold_rows)
    current_threshold_metrics = binary_metrics(threshold_rows, current_scheme["predicate"])
    min_candidate_precision = current_threshold_metrics["precision"]

    schemes = [
        current_scheme,
        make_threshold_scheme("uniform_weights", equal_weights, threshold_rows, min_precision=min_candidate_precision),
        make_threshold_scheme("utility_weighted", utility_weights, threshold_rows, min_precision=min_candidate_precision),
        make_threshold_scheme("constrained_logistic_weights", logistic_weights, threshold_rows, min_precision=min_candidate_precision),
        make_threshold_scheme("two_component_gate", utility_weights, threshold_rows, uses_two_component_gate=True, min_precision=min_candidate_precision),
    ]
    for scheme in schemes:
        scheme["weights_json"] = json.dumps(scheme["weights"], ensure_ascii=False, sort_keys=True)
    return schemes


def make_threshold_scheme(
    scheme_name: str,
    weights: Mapping[str, float],
    threshold_rows: list[Mapping[str, Any]],
    *,
    uses_two_component_gate: bool = False,
    min_precision: float = 0.0,
) -> dict[str, Any]:
    threshold = choose_threshold(
        threshold_rows,
        weights,
        uses_two_component_gate=uses_two_component_gate,
        min_precision=min_precision,
    )
    return {
        "scheme": scheme_name,
        "weights": dict(weights),
        "threshold": threshold,
        "score_field": "",
        "predicate": lambda row, weights=dict(weights), threshold=threshold, uses_two_component_gate=uses_two_component_gate: (
            weighted_norm_score(row, weights) >= threshold
            and (not uses_two_component_gate or abnormal_component_count(row) >= 2)
        ),
        "uses_two_component_gate": uses_two_component_gate,
    }


def choose_threshold(
    rows: list[Mapping[str, Any]],
    weights: Mapping[str, float],
    *,
    uses_two_component_gate: bool,
    min_precision: float = 0.0,
    min_specificity: float = MIN_SPECIFICITY_TARGET,
) -> float:
    scored = [(weighted_norm_score(row, weights), row) for row in rows if row.get("label_binary") in {"0", "1"}]
    if not scored:
        return 1.0
    candidates = sorted({score for score, _row in scored}, reverse=True)
    best: tuple[tuple[float, float, float, float], float] | None = None
    relaxed: tuple[tuple[float, float, float, float], float] | None = None
    for threshold in candidates:
        metrics = binary_metrics(
            rows,
            lambda row, threshold=threshold: weighted_norm_score(row, weights) >= threshold
            and (not uses_two_component_gate or abnormal_component_count(row) >= 2),
        )
        strict_ok = metrics["specificity"] >= min_specificity and metrics["precision"] >= min_precision
        score = (metrics["recall"], metrics["balanced_accuracy"], metrics["precision"], -threshold)
        relaxed_score = (metrics["fbeta"], metrics["balanced_accuracy"], metrics["precision"], -threshold)
        if strict_ok and (best is None or score > best[0]):
            best = (score, threshold)
        if metrics["specificity"] >= min_specificity and (relaxed is None or relaxed_score > relaxed[0]):
            relaxed = (relaxed_score, threshold)
    if best:
        return best[1]
    if relaxed:
        return relaxed[1]
    return max(candidates)


def evaluate_candidate_schemes(
    rows: list[Mapping[str, Any]],
    schemes: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output: list[dict[str, Any]] = []
    baseline_scheme = next(
        (scheme for scheme in schemes if scheme.get("scheme") == "current_fixed_weights"),
        schemes[0] if schemes else None,
    )
    if baseline_scheme is None:
        return output, {"baseline": {}, "best_candidate": None, "acceptance_policy": {}}
    baseline_predicate = baseline_scheme["predicate"]
    baseline_metrics = {
        split: binary_metrics(split_rows(rows, split), baseline_predicate)
        for split in ("train_val", "test", "all")
    }
    for split, metrics in baseline_metrics.items():
        scoped = split_rows(rows, split)
        metrics["auroc"] = score_auc(scoped, baseline_scheme)
        metrics["auprc"] = score_auprc(scoped, baseline_scheme)
    best_candidate: dict[str, Any] | None = None
    for scheme in schemes:
        predicate = scheme["predicate"]
        weights = scheme["weights"]
        for split in ("train", "val", "train_val", "test", "all"):
            scoped = split_rows(rows, split)
            scores = [scheme_score(row, scheme) for row in scoped if row.get("label_binary") in {"0", "1"}]
            metrics = binary_metrics(scoped, predicate)
            metrics["auroc"] = score_auc(scoped, scheme)
            metrics["auprc"] = score_auprc(scoped, scheme)
            contributions = component_contributions(scoped, predicate, weights)
            output.append(
                {
                    "scheme": scheme["scheme"],
                    "evaluation_split": split,
                    "threshold": fmt_optional(scheme.get("threshold")),
                    "weights_json": scheme.get("weights_json", json.dumps(weights, ensure_ascii=False, sort_keys=True)),
                    "uses_two_component_gate": str(bool(scheme.get("uses_two_component_gate"))).lower(),
                    "score_min": fmt(min(scores) if scores else 0.0),
                    "score_max": fmt(max(scores) if scores else 0.0),
                    "score_mean": fmt(mean(scores) if scores else 0.0),
                    **format_metrics(metrics),
                    "component_contribution_distribution": json.dumps(contributions, ensure_ascii=False, sort_keys=True),
                }
            )
        if scheme["scheme"] != baseline_scheme["scheme"]:
            test_scoped = split_rows(rows, "test")
            test_metrics = binary_metrics(test_scoped, predicate)
            test_metrics["auroc"] = score_auc(test_scoped, scheme)
            test_metrics["auprc"] = score_auprc(test_scoped, scheme)
            baseline = baseline_metrics["test"]
            acceptable = (
                test_metrics["recall"] >= baseline["recall"]
                and test_metrics["specificity"] >= MIN_SPECIFICITY_TARGET
                and test_metrics["precision"] >= max(0.0, baseline["precision"] - 0.05)
            )
            ranking = (acceptable, test_metrics["recall"] - baseline["recall"], test_metrics["balanced_accuracy"], test_metrics["precision"])
            if best_candidate is None or ranking > best_candidate["ranking"]:
                best_candidate = {
                    "ranking": ranking,
                    "scheme": scheme["scheme"],
                    "threshold": fmt_optional(scheme.get("threshold")),
                    "weights": scheme["weights"],
                    "test_metrics": format_metrics(test_metrics),
                    "acceptable": acceptable,
                }
    return output, {
        "baseline": {split: format_metrics(metrics) for split, metrics in baseline_metrics.items()},
        "best_candidate": strip_ranking(best_candidate),
        "acceptance_policy": {
            "must_not_reduce_test_recall": True,
            "min_test_specificity": MIN_SPECIFICITY_TARGET,
            "allowed_precision_drop": 0.05,
            "max_component_weight": MAX_COMPONENT_WEIGHT,
            "min_component_weight": MIN_COMPONENT_WEIGHT,
        },
    }


def strip_ranking(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    output = dict(payload)
    output.pop("ranking", None)
    output["weights"] = {key: fmt(value) for key, value in output.get("weights", {}).items()}
    return output


def format_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "patients": metrics["patients"],
        "evaluated": metrics["evaluated"],
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
        "f1": fmt(metrics["f1"]),
        "fbeta": fmt(metrics["fbeta"]),
        "auroc": fmt(metrics.get("auroc", 0.0)),
        "auprc": fmt(metrics.get("auprc", 0.0)),
    }


def binary_metrics(rows: list[Mapping[str, Any]], predicate: Callable[[Mapping[str, Any]], bool]) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        if truth not in {"0", "1"}:
            skipped += 1
            continue
        pred = bool(predicate(row))
        if truth == "1" and pred:
            tp += 1
        elif truth == "0" and pred:
            fp += 1
        elif truth == "0" and not pred:
            tn += 1
        elif truth == "1" and not pred:
            fn += 1
    evaluated = tp + fp + tn + fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    accuracy = (tp + tn) / evaluated if evaluated else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    beta2 = BETA_FOR_RECALL ** 2
    fbeta = (1 + beta2) * precision * recall / (beta2 * precision + recall) if beta2 * precision + recall else 0.0
    return {
        "patients": len(rows),
        "evaluated": evaluated,
        "skipped": skipped,
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
        "f1": f1,
        "fbeta": fbeta,
    }


def fit_constrained_logistic_weights(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    weights = {component: 1.0 / len(COMPONENTS) for component in COMPONENTS}
    train = [row for row in rows if row.get("label_binary") in {"0", "1"}]
    if not train:
        return weights
    learning_rate = 0.20
    for _ in range(300):
        gradient = {component: 0.0 for component in COMPONENTS}
        for row in train:
            y = 1.0 if row.get("label_binary") == "1" else 0.0
            score = weighted_norm_score(row, weights)
            pred = 1.0 / (1.0 + math.exp(-6.0 * (score - 0.5)))
            for component in COMPONENTS:
                value = parse_float(row.get(f"{component}_norm"))
                if value is not None:
                    gradient[component] += (pred - y) * value
        raw = {
            component: weights[component] - learning_rate * gradient[component] / len(train)
            for component in COMPONENTS
        }
        weights = bounded_normalize_weights(raw)
    return weights


def bounded_normalize_weights(
    scores: Mapping[str, float],
    *,
    min_weight: float = MIN_COMPONENT_WEIGHT,
    max_weight: float = MAX_COMPONENT_WEIGHT,
) -> dict[str, float]:
    if min_weight * len(COMPONENTS) > 1.0 or max_weight * len(COMPONENTS) < 1.0:
        raise ValueError("Infeasible component weight bounds.")
    positives = {component: max(0.0, float(scores.get(component, 0.0))) for component in COMPONENTS}
    if sum(positives.values()) <= 1e-12:
        positives = {component: 1.0 for component in COMPONENTS}
    weights = {component: min_weight for component in COMPONENTS}
    remaining_mass = 1.0 - min_weight * len(COMPONENTS)
    active = set(COMPONENTS)
    while active and remaining_mass > 1e-12:
        active_total = sum(positives[component] for component in active)
        if active_total <= 1e-12:
            share = remaining_mass / len(active)
            for component in list(active):
                addition = min(share, max_weight - weights[component])
                weights[component] += addition
            break
        changed = False
        for component in list(active):
            proposed = remaining_mass * positives[component] / active_total
            if weights[component] + proposed > max_weight:
                remaining_mass -= max_weight - weights[component]
                weights[component] = max_weight
                active.remove(component)
                changed = True
        if not changed:
            for component in active:
                weights[component] += remaining_mass * positives[component] / active_total
            remaining_mass = 0.0
    total = sum(weights.values())
    return {component: weights[component] / total for component in COMPONENTS}


def weighted_norm_score(row: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    total = 0.0
    weight_total = 0.0
    for component, weight in weights.items():
        value = parse_float(row.get(f"{component}_norm"))
        if value is None:
            continue
        total += weight * value
        weight_total += weight
    return total / weight_total if weight_total > 1e-12 else 0.0


def scheme_score(row: Mapping[str, Any], scheme: Mapping[str, Any]) -> float:
    score_field = scheme.get("score_field")
    if score_field:
        return parse_float(row.get(str(score_field))) or 0.0
    return weighted_norm_score(row, scheme["weights"])


def abnormal_component_count(row: Mapping[str, Any]) -> int:
    return sum(1 for component in COMPONENTS if (parse_float(row.get(f"{component}_norm")) or 0.0) >= 0.65)


def component_contributions(
    rows: list[Mapping[str, Any]],
    predicate: Callable[[Mapping[str, Any]], bool],
    weights: Mapping[str, float],
) -> dict[str, str]:
    selected = [row for row in rows if predicate(row)]
    if not selected:
        return {component: fmt(0.0) for component in COMPONENTS}
    contributions = {}
    for component in COMPONENTS:
        values = [
            float(weights.get(component, 0.0)) * (parse_float(row.get(f"{component}_norm")) or 0.0)
            for row in selected
        ]
        contributions[component] = fmt(mean(values))
    return contributions


def score_auc(rows: list[Mapping[str, Any]], scheme: Mapping[str, Any]) -> float:
    pos = [scheme_score(row, scheme) for row in rows if row.get("label_binary") == "1"]
    neg = [scheme_score(row, scheme) for row in rows if row.get("label_binary") == "0"]
    return roc_auc(pos, neg)


def score_auprc(rows: list[Mapping[str, Any]], scheme: Mapping[str, Any]) -> float:
    scored = sorted(
        [(scheme_score(row, scheme), 1 if row.get("label_binary") == "1" else 0) for row in rows if row.get("label_binary") in {"0", "1"}],
        key=lambda item: item[0],
        reverse=True,
    )
    positives = sum(label for _score, label in scored)
    if positives == 0:
        return 0.0
    tp = fp = 0
    prev_recall = 0.0
    area = 0.0
    for _score, label in scored:
        if label:
            tp += 1
        else:
            fp += 1
        recall = tp / positives
        precision = tp / (tp + fp)
        area += precision * (recall - prev_recall)
        prev_recall = recall
    return area


def build_summary(
    rows: list[Mapping[str, Any]],
    component_effect_rows: list[Mapping[str, Any]],
    universal_feature_rows: list[Mapping[str, Any]],
    candidate_summary: Mapping[str, Any],
    component_utilities: Mapping[str, Mapping[str, Any]],
    normalizers: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    top_universal = universal_feature_rows[:20]
    component_utility_rows = sorted(
        component_utilities.values(),
        key=lambda row: -(parse_float(row["component_utility"]) or 0.0),
    )
    recommendation = "keep_current_weights"
    best = candidate_summary.get("best_candidate") or {}
    if best.get("acceptable"):
        recommendation = "review_candidate_before_replacing_weights"
    return {
        "question": "组件权重是否应根据患病/不患病普适差异重新校准",
        "answer": (
            "已从 05_patient_splits、09_mediapipe_full_features 和 11_v11_role_aware_patient_core_results "
            "独立重建组件权重测评测试集与候选权重；当前输出不直接改写主流程，只有候选方案在锁定 "
            "test 集满足召回提升且 precision/specificity 约束后，才建议人工复核后接入。"
        ),
        "recommendation": recommendation,
        "input_scope": {
            "patient_split": "metadata/05_patient_splits.csv",
            "mediapipe_features": "metadata/09_mediapipe_full_features.csv",
            "patient_core": "metadata/11_v11_role_aware_patient_core_results.csv",
            "excluded_previous_results": [
                "metadata/12_v11_hb_proxy_patient_grades.csv",
                "metadata/12_v11_hb_proxy_component_scores.csv",
            ],
        },
        "components": list(COMPONENTS),
        "current_weights": {component: fmt(HB_COMPONENT_WEIGHTS[component]) for component in COMPONENTS},
        "normalization": {
            component: {
                "p99": fmt(payload["p99"]),
                "median": fmt(payload["median"]),
                "mad": fmt(payload["mad"]),
            }
            for component, payload in normalizers.items()
        },
        "component_utilities": component_utility_rows,
        "candidate_evaluation": candidate_summary,
        "top_universal_features": top_universal,
        "leave_one_component_out_delta": leave_one_component_out(rows),
        "outputs": {
            "patient_set": "metadata/19_component_weight_evaluation_patient_set.csv",
            "universal_feature_scores": "metadata/19_component_weight_universal_feature_scores.csv",
            "candidate_weights": "metadata/19_component_weight_candidates.csv",
            "summary": "metadata/19_component_weight_evaluation_summary.json",
            "report": "reports/19_component_weight_evaluation.md",
        },
        "interpretation_limits": [
            "患病/不患病仍是 patient outcome 弱监督标签，不是人工面部不对称真值。",
            "本阶段只生成候选权重和验收指标，不自动替换 V1.1 HB proxy 主规则。",
            "若候选权重提升 recall 但显著增加不患病高分病例，应继续保留当前规则或增加 gate。",
        ],
    }


def leave_one_component_out(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    base_weights = {component: float(HB_COMPONENT_WEIGHTS[component]) for component in COMPONENTS}
    threshold_rows = split_rows(rows, "val") if has_both_labels(split_rows(rows, "val")) else split_rows(rows, "train_val")
    base_threshold = choose_threshold(threshold_rows, base_weights, uses_two_component_gate=False)
    base_metrics = binary_metrics(split_rows(rows, "test"), lambda row: weighted_norm_score(row, base_weights) >= base_threshold)
    output: dict[str, dict[str, str]] = {}
    for removed in COMPONENTS:
        weights = bounded_normalize_weights({component: (0.0 if component == removed else base_weights[component]) for component in COMPONENTS})
        threshold = choose_threshold(threshold_rows, weights, uses_two_component_gate=False)
        metrics = binary_metrics(split_rows(rows, "test"), lambda row, weights=weights, threshold=threshold: weighted_norm_score(row, weights) >= threshold)
        output[removed] = {
            "test_precision_delta": fmt(metrics["precision"] - base_metrics["precision"]),
            "test_recall_delta": fmt(metrics["recall"] - base_metrics["recall"]),
            "test_specificity_delta": fmt(metrics["specificity"] - base_metrics["specificity"]),
            "test_balanced_accuracy_delta": fmt(metrics["balanced_accuracy"] - base_metrics["balanced_accuracy"]),
        }
    return output


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    component_effect_rows: list[Mapping[str, Any]],
    candidate_rows: list[Mapping[str, Any]],
    universal_feature_rows: list[Mapping[str, Any]],
) -> None:
    lines = [
        "# 19 组件权重测评测试集与权重校准",
        "",
        "分析对象：`datasets/facesym_v1_all_images_no_gate_20260119`",
        "",
        "模块口径：直接读取 `metadata/05_patient_splits.csv`、`metadata/09_mediapipe_full_features.csv`、`metadata/11_v11_role_aware_patient_core_results.csv` 后重建组件；不读取 `metadata/12_v11_hb_proxy_patient_grades.csv` 或 `metadata/12_v11_hb_proxy_component_scores.csv`，避免在既有分级结果上叠加测评。",
        "",
        "## 结论",
        "",
        str(summary["answer"]),
        "",
        f"- 推荐：`{summary['recommendation']}`",
        "- 本阶段不自动替换 `build_v11_hb_proxy_grading.py` 中的主流程权重。",
        "",
        "## 当前组件权重",
        "",
        "| component | 当前权重 | 含义 |",
        "| --- | ---: | --- |",
    ]
    for component in COMPONENTS:
        lines.append(f"| `{component}` | {summary['current_weights'][component]} | {HB_COMPONENT_LABELS[component]} |")
    lines.extend(
        [
            "",
            "## 组件弱监督差异",
            "",
            "| component | split | diseased_mean | nondisease_mean | delta | effect | auc | nondisease_high_rate | direction |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for row in component_effect_rows:
        if row["split"] not in {"all", "test"}:
            continue
        lines.append(
            "| `{component}` | {split} | {diseased_mean} | {nondisease_mean} | {diseased_minus_nondisease} | {standardized_effect} | {auc} | {nondisease_high_rate} | {direction} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## 候选权重指标",
            "",
            "| scheme | split | threshold | precision | recall | specificity | F2 | AUROC | AUPRC | TP | FP | TN | FN |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in candidate_rows:
        if row["evaluation_split"] not in {"test", "all"}:
            continue
        lines.append(
            "| {scheme} | {evaluation_split} | {threshold} | {precision} | {recall} | {specificity} | {fbeta} | {auroc} | {auprc} | {tp} | {fp} | {tn} | {fn} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Top 普适差异特征",
            "",
            "| score | scope | feature | family | target_component | effect | auc | direction_consistency | role_stability |",
            "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in universal_feature_rows[:30]:
        lines.append(
            "| {universal_feature_score} | {scope} | `{feature_name}` | {feature_family} | `{component_target}` | {all_effect} | {all_auc} | {direction_consistency} | {role_stability} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## 防止单项支配的约束",
            "",
            f"- 候选权重约束：`weight_i >= {MIN_COMPONENT_WEIGHT}`，`weight_i <= {MAX_COMPONENT_WEIGHT}`，`sum(weight_i)=1`。",
            "- 候选评分使用 train 分布的经验分位数归一化，并对每个组件按 P99 截尾。",
            "- `two_component_gate` 方案要求至少两个组件达到有效异常证据后才允许进入高等级候选。",
            "- 报告输出 `leave_one_component_out_delta`，用于检查移除单个组件后 test 指标是否剧烈变化。",
            "",
            "## 输出文件",
            "",
        ]
    )
    for label, output_path in summary["outputs"].items():
        lines.append(f"- `{label}`: `{output_path}`")
    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- 当前标签仍为 patient outcome 弱监督标签，不等同于人工面部不对称真值。",
            "- 如果候选权重提升 recall 但显著降低 specificity，应保留当前权重或增加质量/多组件 gate。",
            "- 该报告只提供候选权重测评结果，不代表临床诊断性能。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def split_rows(rows: list[Mapping[str, Any]], split: str) -> list[Mapping[str, Any]]:
    if split == "all":
        return rows
    if split == "train_val":
        return [row for row in rows if row.get("split") in {"train", "val"}]
    return [row for row in rows if row.get("split") == split]


def has_both_labels(rows: list[Mapping[str, Any]]) -> bool:
    labels = {row.get("label_binary") for row in rows}
    return "0" in labels and "1" in labels


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def median(values: Iterable[float]) -> float:
    values = sorted(values)
    return quantile(values, 0.5) if values else 0.0


def std(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    value_mean = mean(values)
    return math.sqrt(sum((value - value_mean) ** 2 for value in values) / len(values))


def quantile(values: Iterable[float], q: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    pos = (len(values) - 1) * q
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return values[int(pos)]
    return values[lower] * (upper - pos) + values[upper] * (pos - lower)


def empirical_cdf(value: float, values: Iterable[float]) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    return sum(1 for item in values if item <= value) / len(values)


def roc_auc(pos: list[float], neg: list[float]) -> float:
    if not pos or not neg:
        return 0.5
    wins = ties = 0.0
    for p_value in pos:
        for n_value in neg:
            if p_value > n_value:
                wins += 1.0
            elif p_value == n_value:
                ties += 1.0
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def direction(value: float) -> str:
    if value > 1e-12:
        return "diseased_higher"
    if value < -1e-12:
        return "nondisease_higher"
    return "zero"


def fmt(value: Any) -> str:
    parsed = parse_float(value)
    return "0.000000" if parsed is None else f"{parsed:.6f}"


def fmt_optional(value: Any) -> str:
    parsed = parse_float(value)
    return "" if parsed is None else fmt(parsed)


if __name__ == "__main__":
    main()
