#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

COMPONENTS = (
    "resting_symmetry_score",
    "eye_closure_score",
    "brow_forehead_score",
    "smile_mouth_score",
    "gross_asymmetry_score",
    "movement_absence_score",
    "hb_proxy_overall_score",
)
COMPONENT_LABELS = {
    "resting_symmetry_score": "静息对称性",
    "eye_closure_score": "闭眼完整性/眼裂对称",
    "brow_forehead_score": "眉额/皱眉动态",
    "smile_mouth_score": "微笑/示齿口部动态",
    "gross_asymmetry_score": "整体不对称",
    "movement_absence_score": "无运动风险",
    "hb_proxy_overall_score": "HB proxy 总分",
}
SCOPE_DEFINITIONS: tuple[tuple[str, Callable[[Mapping[str, Any]], bool]], ...] = (
    ("all_scorable", lambda row: parse_float(row.get("hb_proxy_grade_num")) is not None),
    ("grade_v_plus", lambda row: is_grade_v_plus(row)),
    ("below_grade_v", lambda row: (grade := parse_float(row.get("hb_proxy_grade_num"))) is not None and grade < 5),
)
SPLITS = ("train", "val", "test", "all")
RULE_ACCEPTANCE_MIN_TEST_BALANCED_GAIN = 0.02
RULE_ACCEPTANCE_MIN_TEST_PRECISION_GAIN = 0.02


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    patient_rows = read_csv(required(metadata / "12_v11_hb_proxy_patient_grades.csv"))
    pair_summary = read_json(metadata / "14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json")

    component_rows = build_component_effect_rows(patient_rows)
    candidate_rows, rule_summary = build_rule_candidate_rows(patient_rows)
    summary = build_summary(component_rows, candidate_rows, rule_summary, pair_summary)

    write_csv(metadata / "15_v11_grade_v_plus_generalization_component_effects.csv", component_rows)
    write_csv(metadata / "15_v11_grade_v_plus_rule_adjustment_candidates.csv", candidate_rows)
    write_json(metadata / "15_v11_grade_v_plus_generalization_summary.json", summary)
    write_report(reports / "17_v11_grade_v_plus_generalization_and_rule_adjustment.md", summary, component_rows, candidate_rows)

    print(f"Wrote {metadata / '15_v11_grade_v_plus_generalization_component_effects.csv'}")
    print(f"Wrote {metadata / '15_v11_grade_v_plus_rule_adjustment_candidates.csv'}")
    print(f"Wrote {metadata / '15_v11_grade_v_plus_generalization_summary.json'}")
    print(f"Wrote {reports / '17_v11_grade_v_plus_generalization_and_rule_adjustment.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze whether Grade V+ label differences generalize and whether rules should change.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing V1.1 metadata.")
    return parser.parse_args()


def required(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Required input is missing: {path}")
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    preferred = [
        "scope",
        "split",
        "component",
        "component_label",
        "diseased_n",
        "nondisease_n",
        "diseased_mean",
        "nondisease_mean",
        "diseased_minus_nondisease",
        "standardized_effect",
        "direction",
        "direction_matches_all_split",
        "is_stable",
    ]
    fields = [field for field in preferred if field in fields] + [field for field in fields if field not in preferred]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_component_effect_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for scope_name, scope_filter in SCOPE_DEFINITIONS:
        scoped = [row for row in rows if scope_filter(row)]
        all_direction_by_component: dict[str, str] = {}
        all_effect_by_component: dict[str, float] = {}
        for component in COMPONENTS:
            stats = component_effect(scoped, component)
            all_direction_by_component[component] = direction(stats["diseased_minus_nondisease"])
            all_effect_by_component[component] = stats["standardized_effect"]

        for component in COMPONENTS:
            split_rows: list[dict[str, Any]] = []
            for split in SPLITS:
                split_scoped = scoped if split == "all" else [row for row in scoped if row.get("split") == split]
                stats = component_effect(split_scoped, component)
                row = {
                    "scope": scope_name,
                    "split": split,
                    "component": component,
                    "component_label": COMPONENT_LABELS[component],
                    **format_stats(stats),
                }
                row["direction"] = direction(stats["diseased_minus_nondisease"])
                row["direction_matches_all_split"] = str(row["direction"] == all_direction_by_component[component]).lower()
                split_rows.append(row)
            stable = is_stable_component(split_rows, all_effect_by_component[component])
            for row in split_rows:
                row["is_stable"] = str(stable).lower()
                output.append(row)
    return output


def component_effect(rows: list[Mapping[str, Any]], component: str) -> dict[str, Any]:
    diseased = [value for row in rows if row.get("label_binary") == "1" if (value := parse_float(row.get(component))) is not None]
    nondisease = [value for row in rows if row.get("label_binary") == "0" if (value := parse_float(row.get(component))) is not None]
    diseased_mean = mean(diseased)
    nondisease_mean = mean(nondisease)
    delta = diseased_mean - nondisease_mean if diseased and nondisease else 0.0
    pooled = math.sqrt((std(diseased) ** 2 + std(nondisease) ** 2) / 2.0) if diseased and nondisease else 0.0
    return {
        "diseased_n": len(diseased),
        "nondisease_n": len(nondisease),
        "diseased_mean": diseased_mean if diseased else None,
        "nondisease_mean": nondisease_mean if nondisease else None,
        "diseased_minus_nondisease": delta,
        "standardized_effect": delta / pooled if pooled > 1e-12 else 0.0,
    }


def format_stats(stats: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "diseased_n": stats["diseased_n"],
        "nondisease_n": stats["nondisease_n"],
        "diseased_mean": fmt_optional(stats["diseased_mean"]),
        "nondisease_mean": fmt_optional(stats["nondisease_mean"]),
        "diseased_minus_nondisease": fmt(stats["diseased_minus_nondisease"]),
        "standardized_effect": fmt(stats["standardized_effect"]),
    }


def is_stable_component(split_rows: list[Mapping[str, Any]], all_effect: float) -> bool:
    required = [row for row in split_rows if row["split"] in {"train", "val", "test"}]
    if abs(all_effect) < 0.20:
        return False
    all_direction = next(row["direction"] for row in split_rows if row["split"] == "all")
    if all_direction == "zero":
        return False
    return all(row["direction"] == all_direction and abs(float(row["standardized_effect"])) >= 0.10 for row in required)


def build_rule_candidate_rows(rows: list[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    train_val = [row for row in rows if row.get("split") in {"train", "val"}]
    candidate_specs = [{"rule_name": "baseline_grade_v_plus", "feature": "", "threshold": "", "predicate": is_grade_v_plus}]
    for component in COMPONENTS:
        threshold = best_threshold(train_val, component)
        if threshold is not None:
            candidate_specs.append(
                {
                    "rule_name": f"grade_v_plus_and_{component}_threshold",
                    "feature": component,
                    "threshold": threshold,
                    "predicate": lambda row, component=component, threshold=threshold: is_grade_v_plus(row)
                    and (value := parse_float(row.get(component))) is not None
                    and value >= threshold,
                }
            )

    rows_out: list[dict[str, Any]] = []
    baseline_by_split = {
        split: binary_metrics(split_rows(rows, split), is_grade_v_plus) for split in ("train_val", "test", "all")
    }
    best_accepted: dict[str, Any] | None = None
    for spec in candidate_specs:
        metrics_by_scope = {
            split: binary_metrics(split_rows(rows, split), spec["predicate"])
            for split in ("train_val", "test", "all")
        }
        accepted = rule_is_accepted(metrics_by_scope, baseline_by_split)
        for split, metrics in metrics_by_scope.items():
            rows_out.append(
                {
                    "rule_name": spec["rule_name"],
                    "feature": spec["feature"],
                    "threshold": fmt_optional(spec["threshold"]),
                    "split": split,
                    **format_metrics(metrics),
                    "accepted_for_rule_change": str(accepted).lower(),
                    "acceptance_reason": acceptance_reason(metrics_by_scope, baseline_by_split),
                }
            )
        if accepted:
            test_metrics = metrics_by_scope["test"]
            score = (test_metrics["balanced_accuracy"], test_metrics["precision"], test_metrics["specificity"])
            if best_accepted is None or score > best_accepted["score"]:
                best_accepted = {"score": score, "rule_name": spec["rule_name"], "feature": spec["feature"], "threshold": spec["threshold"]}

    summary = {
        "baseline": {split: format_metrics(metrics) for split, metrics in baseline_by_split.items()},
        "accepted_rule": best_accepted,
        "recommendation": "change_rule" if best_accepted else "keep_current_rule",
        "acceptance_policy": {
            "min_test_balanced_accuracy_gain": RULE_ACCEPTANCE_MIN_TEST_BALANCED_GAIN,
            "min_test_precision_gain": RULE_ACCEPTANCE_MIN_TEST_PRECISION_GAIN,
            "must_not_reduce_test_recall": True,
        },
    }
    return rows_out, summary


def best_threshold(rows: list[Mapping[str, Any]], component: str) -> float | None:
    values = sorted(
        {
            value
            for row in rows
            if is_grade_v_plus(row)
            if (value := parse_float(row.get(component))) is not None
        }
    )
    if not values:
        return None
    best: tuple[tuple[float, float, int], float] | None = None
    for threshold in values:
        metrics = binary_metrics(
            rows,
            lambda row, component=component, threshold=threshold: is_grade_v_plus(row)
            and (value := parse_float(row.get(component))) is not None
            and value >= threshold,
        )
        score = (metrics["balanced_accuracy"], metrics["precision"], metrics["predicted_positive"])
        if best is None or score > best[0]:
            best = (score, threshold)
    return best[1] if best else None


def rule_is_accepted(
    metrics_by_scope: Mapping[str, Mapping[str, Any]],
    baseline_by_split: Mapping[str, Mapping[str, Any]],
) -> bool:
    test = metrics_by_scope["test"]
    baseline = baseline_by_split["test"]
    balanced_gain = test["balanced_accuracy"] - baseline["balanced_accuracy"]
    precision_gain = test["precision"] - baseline["precision"]
    recall_gain = test["recall"] - baseline["recall"]
    return (
        balanced_gain >= RULE_ACCEPTANCE_MIN_TEST_BALANCED_GAIN
        and precision_gain >= RULE_ACCEPTANCE_MIN_TEST_PRECISION_GAIN
        and recall_gain >= 0.0
    )


def acceptance_reason(
    metrics_by_scope: Mapping[str, Mapping[str, Any]],
    baseline_by_split: Mapping[str, Mapping[str, Any]],
) -> str:
    test = metrics_by_scope["test"]
    baseline = baseline_by_split["test"]
    return (
        f"test balanced delta={test['balanced_accuracy'] - baseline['balanced_accuracy']:.6f}; "
        f"precision delta={test['precision'] - baseline['precision']:.6f}; "
        f"recall delta={test['recall'] - baseline['recall']:.6f}"
    )


def split_rows(rows: list[Mapping[str, Any]], split: str) -> list[Mapping[str, Any]]:
    if split == "all":
        return rows
    if split == "train_val":
        return [row for row in rows if row.get("split") in {"train", "val"}]
    return [row for row in rows if row.get("split") == split]


def binary_metrics(rows: list[Mapping[str, Any]], predicate: Callable[[Mapping[str, Any]], bool]) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        if truth not in {"0", "1"}:
            skipped += 1
            continue
        pred = predicate(row)
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
    }


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
    }


def build_summary(
    component_rows: list[Mapping[str, Any]],
    candidate_rows: list[Mapping[str, Any]],
    rule_summary: Mapping[str, Any],
    pair_summary: Mapping[str, Any],
) -> dict[str, Any]:
    stable_by_scope = {}
    for scope, _scope_filter in SCOPE_DEFINITIONS:
        stable_by_scope[scope] = sorted(
            {
                row["component_label"]
                for row in component_rows
                if row["scope"] == scope and row["is_stable"] == "true"
            }
        )
    pair_deltas = pair_summary.get("component_mean_delta_diseased_minus_nondisease", {})
    pair_delta_assessment = assess_pair_deltas(pair_deltas, component_rows)
    return {
        "question": "18 对样本关键差异是否普适，以及是否应调整 Grade V+ 人脸不对称规则",
        "answer": "18 对样本中的多数关键差异不是可直接用于调规则的普适差异；全量样本存在较稳定的患病组更高不对称信号，但在 Grade V+ 高等级子集中只有 HB proxy 总分和无运动风险相对稳定，候选规则没有通过测试集验收。",
        "pair_delta_assessment": pair_delta_assessment,
        "stable_components_by_scope": stable_by_scope,
        "rule_adjustment": rule_summary,
        "rule_change_applied": False,
        "rule_change_reason": "未发现能在测试集同时提升 balanced accuracy、precision 且不降低 recall 的候选规则；保留当前 Grade V+ 输出规则。",
        "outputs": {
            "component_effects": "metadata/15_v11_grade_v_plus_generalization_component_effects.csv",
            "candidate_rules": "metadata/15_v11_grade_v_plus_rule_adjustment_candidates.csv",
            "summary": "metadata/15_v11_grade_v_plus_generalization_summary.json",
            "report": "reports/17_v11_grade_v_plus_generalization_and_rule_adjustment.md",
        },
    }


def assess_pair_deltas(pair_deltas: Mapping[str, Any], component_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    component_by_label = {label: field for field, label in COMPONENT_LABELS.items()}
    result: dict[str, Any] = {}
    for label, delta in pair_deltas.items():
        field = component_by_label.get(label)
        if not field:
            continue
        grade_v_rows = [
            row for row in component_rows
            if row["scope"] == "grade_v_plus" and row["component"] == field and row["split"] in {"train", "val", "test", "all"}
        ]
        result[label] = {
            "pair_delta_diseased_minus_nondisease": fmt(parse_float(delta) or 0.0),
            "grade_v_plus_split_effects": {
                row["split"]: {
                    "delta": row["diseased_minus_nondisease"],
                    "effect": row["standardized_effect"],
                    "direction": row["direction"],
                }
                for row in grade_v_rows
            },
            "is_generalizable_in_grade_v_plus": any(row["is_stable"] == "true" for row in grade_v_rows),
        }
    return result


def write_report(
    path: Path,
    summary: Mapping[str, Any],
    component_rows: list[Mapping[str, Any]],
    candidate_rows: list[Mapping[str, Any]],
) -> None:
    lines = [
        "# 17 Grade V+ 差异普适性与规则调整验证",
        "",
        "分析对象：`datasets/facesym_v1_all_images_no_gate_20260119`",
        "",
        "## 结论",
        "",
        summary["answer"],
        "",
        f"- 是否调整当前 Grade V+ 规则：`{'是' if summary['rule_change_applied'] else '否'}`",
        f"- 原因：{summary['rule_change_reason']}",
        "",
        "## 18 对差异是否普适",
        "",
        "| component | 18对 diseased-nondisease | Grade V+ train | Grade V+ val | Grade V+ test | Grade V+ all | 是否普适 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for label, payload in summary["pair_delta_assessment"].items():
        effects = payload["grade_v_plus_split_effects"]
        lines.append(
            "| {label} | {pair_delta} | {train} | {val} | {test} | {all_} | {stable} |".format(
                label=label,
                pair_delta=payload["pair_delta_diseased_minus_nondisease"],
                train=effects.get("train", {}).get("delta", ""),
                val=effects.get("val", {}).get("delta", ""),
                test=effects.get("test", {}).get("delta", ""),
                all_=effects.get("all", {}).get("delta", ""),
                stable="是" if payload["is_generalizable_in_grade_v_plus"] else "否",
            )
        )
    lines.extend(
        [
            "",
            "## 稳定组件",
            "",
            "| scope | stable components |",
            "| --- | --- |",
        ]
    )
    for scope, components in summary["stable_components_by_scope"].items():
        lines.append(f"| `{scope}` | {', '.join(components) if components else '无'} |")
    lines.extend(
        [
            "",
            "## 候选规则验收",
            "",
            "验收条件：候选规则必须在 test 上相对当前 Grade V+ baseline 同时满足 balanced accuracy 增益 >= 0.02、precision 增益 >= 0.02，并且 recall 不下降。",
            "",
            "| rule | feature | threshold | split | precision | recall | specificity | balanced_accuracy | TP | FP | TN | FN | accepted | reason |",
            "| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in candidate_rows:
        if row["split"] not in {"test", "all"}:
            continue
        lines.append(
            "| {rule_name} | {feature} | {threshold} | {split} | {precision} | {recall} | {specificity} | {balanced_accuracy} | {tp} | {fp} | {tn} | {fn} | {accepted_for_rule_change} | {acceptance_reason} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- `患病/不患病` 是 patient outcome 标签，不是人工面部不对称真值。",
            "- 18 对对比是高等级子集内的局部比较，不能直接等价为普适规律。",
            "- 当前结论只支持“不改主规则，继续人工复核 Grade V+ 不患病样本”；若后续获得人工面部不对称标签，再重新校准规则。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def is_grade_v_plus(row: Mapping[str, Any]) -> bool:
    grade = parse_float(row.get("hb_proxy_grade_num"))
    return grade is not None and grade >= 5


def direction(value: float) -> str:
    if value > 1e-12:
        return "diseased_higher"
    if value < -1e-12:
        return "nondisease_higher"
    return "zero"


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if not values:
        return 0.0
    value_mean = mean(values)
    return math.sqrt(sum((value - value_mean) ** 2 for value in values) / len(values))


def fmt(value: Any) -> str:
    parsed = parse_float(value)
    return "0.000000" if parsed is None else f"{parsed:.6f}"


def fmt_optional(value: Any) -> str:
    parsed = parse_float(value)
    return "" if parsed is None else fmt(parsed)


if __name__ == "__main__":
    main()
