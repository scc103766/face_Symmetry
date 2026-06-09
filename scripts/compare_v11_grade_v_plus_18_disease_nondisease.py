#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.extract_v11_grade_v_plus_nondisease_review import (  # noqa: E402
    COMPONENTS,
    compact_features,
    count_by,
    enrich_case,
    group_image_scores,
    image_grid,
    md_cell,
    parse_float,
    read_csv,
    required,
    write_json,
)


DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    patient_grade_rows = read_csv(required(metadata / "12_v11_hb_proxy_patient_grades.csv"))
    grade_v_plus_rows = read_csv(required(metadata / "12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv"))
    image_score_rows = read_csv(required(metadata / "11_v11_role_aware_image_scores.csv"))
    keypoint_rows = read_csv(required(metadata / "03_keypoints.csv"))

    patient_by_id = {row["patient_sample_id"]: row for row in patient_grade_rows}
    keypoint_by_sample = {row["sample_id"]: row for row in keypoint_rows}
    image_scores_by_patient = group_image_scores(image_score_rows)

    enriched = [
        enrich_case(row, patient_by_id, image_scores_by_patient, keypoint_by_sample, dataset)
        for row in grade_v_plus_rows
    ]
    nondisease_cases = sorted(
        [row for row in enriched if row.get("label_binary") == "0" or row.get("label_group") == "不患病"],
        key=lambda row: (row.get("split", ""), row.get("hb_proxy_grade_num", ""), row.get("patient_sample_id", "")),
    )
    diseased_candidates = [
        row for row in enriched if row.get("label_binary") == "1" or row.get("label_group") == "患病"
    ]
    pairs = match_diseased_cases(nondisease_cases[:18], diseased_candidates)
    comparison_rows = build_comparison_rows(pairs)
    summary = summarize_pairs(pairs, comparison_rows)

    write_comparison_csv(metadata / "14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv", comparison_rows)
    write_json(metadata / "14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json", summary)
    write_report(reports / "16_v11_grade_v_plus_18_disease_nondisease_comparison.md", pairs, summary)

    print(f"Wrote {metadata / '14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv'}")
    print(f"Wrote {metadata / '14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json'}")
    print(f"Wrote {reports / '16_v11_grade_v_plus_18_disease_nondisease_comparison.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare 18 Grade V+ diseased and nondisease cases.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing V1.1 metadata.")
    return parser.parse_args()


def match_diseased_cases(
    nondisease_cases: list[Mapping[str, Any]],
    diseased_candidates: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    unused = list(diseased_candidates)
    pairs: list[dict[str, Any]] = []
    for index, nondisease in enumerate(nondisease_cases, start=1):
        selected, rule = select_match(nondisease, unused)
        unused.remove(selected)
        pairs.append(
            {
                "pair_id": f"pair_{index:02d}",
                "matching_rule": rule,
                "nondisease": nondisease,
                "diseased": selected,
            }
        )
    return pairs


def select_match(nondisease: Mapping[str, Any], candidates: list[Mapping[str, Any]]) -> tuple[Mapping[str, Any], str]:
    stages = [
        (
            "same_split_same_grade_closest_score",
            lambda row: row.get("split") == nondisease.get("split")
            and row.get("hb_proxy_grade_num") == nondisease.get("hb_proxy_grade_num"),
        ),
        ("same_grade_closest_score", lambda row: row.get("hb_proxy_grade_num") == nondisease.get("hb_proxy_grade_num")),
        ("same_split_closest_score", lambda row: row.get("split") == nondisease.get("split")),
        ("global_closest_score", lambda row: True),
    ]
    for rule, predicate in stages:
        eligible = [row for row in candidates if predicate(row)]
        if eligible:
            complete = [row for row in eligible if annotation_count(row) >= 6]
            if complete:
                eligible = complete
            return min(eligible, key=lambda row: match_distance(nondisease, row)), rule
    raise ValueError("No diseased candidate is available for matching.")


def annotation_count(row: Mapping[str, Any]) -> int:
    return len([item for item in str(row.get("annotation_paths", "")).split(";") if item])


def match_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> tuple[float, float, str]:
    left_score = parse_float(left.get("hb_proxy_overall_score")) or parse_float(left.get("gross_asymmetry_score")) or 0.0
    right_score = parse_float(right.get("hb_proxy_overall_score")) or parse_float(right.get("gross_asymmetry_score")) or 0.0
    left_confidence = parse_float(left.get("hb_grade_confidence")) or 0.0
    right_confidence = parse_float(right.get("hb_grade_confidence")) or 0.0
    return (abs(left_score - right_score), abs(left_confidence - right_confidence), str(right.get("patient_sample_id", "")))


def build_comparison_rows(pairs: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        nondisease = pair["nondisease"]
        diseased = pair["diseased"]
        rows.append(flatten_case(pair["pair_id"], "不患病对照", diseased["patient_sample_id"], pair["matching_rule"], nondisease))
        rows.append(flatten_case(pair["pair_id"], "患病匹配", nondisease["patient_sample_id"], pair["matching_rule"], diseased))
    return rows


def flatten_case(
    pair_id: str,
    comparison_group: str,
    matched_to_patient_id: str,
    matching_rule: str,
    case: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "pair_id": pair_id,
        "comparison_group": comparison_group,
        "matched_to_patient_sample_id": matched_to_patient_id,
        "matching_rule": matching_rule,
        "patient_sample_id": case.get("patient_sample_id", ""),
        "split": case.get("split", ""),
        "label_group": case.get("label_group", ""),
        "label_binary": case.get("label_binary", ""),
        "hb_proxy_grade": case.get("hb_proxy_grade", ""),
        "hb_proxy_grade_num": case.get("hb_proxy_grade_num", ""),
        "hb_grade_confidence": case.get("hb_grade_confidence", ""),
        "hb_proxy_overall_score": case.get("hb_proxy_overall_score", ""),
        "analysis_summary": case.get("analysis_summary", ""),
        "review_focus": case.get("review_focus", ""),
        "component_driver_labels": case.get("component_driver_labels", ""),
        "role_driver_labels": case.get("role_driver_labels", ""),
        "role_driver_names": ";".join(driver_name(item) for item in case.get("_role_driver_list", [])),
        "role_scores": case.get("role_scores", ""),
        "annotation_paths": case.get("annotation_paths", ""),
        "face_asymmetry_reason": case.get("face_asymmetry_reason", ""),
        "top_positive_features": case.get("top_positive_features", ""),
        "resting_symmetry_score": case.get("resting_symmetry_score", ""),
        "eye_closure_score": case.get("eye_closure_score", ""),
        "brow_forehead_score": case.get("brow_forehead_score", ""),
        "smile_mouth_score": case.get("smile_mouth_score", ""),
        "gross_asymmetry_score": case.get("gross_asymmetry_score", ""),
        "movement_absence_score": case.get("movement_absence_score", ""),
    }


def write_comparison_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "pair_id",
        "comparison_group",
        "matched_to_patient_sample_id",
        "matching_rule",
        "patient_sample_id",
        "split",
        "label_group",
        "label_binary",
        "hb_proxy_grade",
        "hb_proxy_grade_num",
        "hb_grade_confidence",
        "hb_proxy_overall_score",
        "analysis_summary",
        "review_focus",
        "component_driver_labels",
        "role_driver_labels",
        "role_driver_names",
        "role_scores",
        "annotation_paths",
        "face_asymmetry_reason",
        "top_positive_features",
        "resting_symmetry_score",
        "eye_closure_score",
        "brow_forehead_score",
        "smile_mouth_score",
        "gross_asymmetry_score",
        "movement_absence_score",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize_pairs(pairs: list[Mapping[str, Any]], comparison_rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    groups = {
        "不患病对照": [row for row in comparison_rows if row.get("comparison_group") == "不患病对照"],
        "患病匹配": [row for row in comparison_rows if row.get("comparison_group") == "患病匹配"],
    }
    return {
        "pair_count": len(pairs),
        "row_count": len(comparison_rows),
        "matching_rules": count_by(pairs, "matching_rule"),
        "group_counts": {group: len(rows) for group, rows in groups.items()},
        "by_group_split": {group: count_by(rows, "split") for group, rows in groups.items()},
        "by_group_grade": {group: count_by(rows, "hb_proxy_grade") for group, rows in groups.items()},
        "component_means": {group: component_means(rows) for group, rows in groups.items()},
        "component_mean_delta_diseased_minus_nondisease": component_mean_delta(groups["患病匹配"], groups["不患病对照"]),
        "top_component_drivers": {
            group: common_terms(rows, "component_driver_labels", limit=20) for group, rows in groups.items()
        },
        "top_role_drivers": {group: role_driver_counts(rows) for group, rows in groups.items()},
        "top_features": {group: feature_counts(rows) for group, rows in groups.items()},
        "outputs": {
            "csv": "metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv",
            "json": "metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json",
            "report": "reports/16_v11_grade_v_plus_18_disease_nondisease_comparison.md",
        },
        "interpretation_limit": "两组均为 Grade V+ 代理高等级样本；对比用于观察患病/不患病标签下的特征差异，不是临床诊断性能。",
    }


def component_means(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    output: dict[str, float] = {}
    for score_field, _level_field, label in COMPONENTS:
        values = [value for row in rows if (value := parse_float(row.get(score_field))) is not None]
        output[label] = sum(values) / len(values) if values else 0.0
    return output


def component_mean_delta(diseased_rows: list[Mapping[str, Any]], nondisease_rows: list[Mapping[str, Any]]) -> dict[str, float]:
    diseased = component_means(diseased_rows)
    nondisease = component_means(nondisease_rows)
    return {label: diseased.get(label, 0.0) - nondisease.get(label, 0.0) for label in diseased}


def common_terms(rows: list[Mapping[str, Any]], field: str, limit: int) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item in str(row.get(field, "")).split(";"):
            cleaned = item.strip()
            if cleaned:
                counter[cleaned.split("(")[0]] += 1
    return dict(counter.most_common(limit))


def role_driver_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item in str(row.get("role_driver_names", "")).split(";"):
            cleaned = item.strip()
            if cleaned:
                counter[cleaned] += 1
    return dict(counter.most_common(20))


def driver_name(value: str) -> str:
    return value.split("(", 1)[0].strip()


def feature_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for feature in compact_features(str(row.get("top_positive_features", "")), limit=12):
            counter[feature] += 1
    return dict(counter.most_common(30))


def write_report(path: Path, pairs: list[Mapping[str, Any]], summary: Mapping[str, Any]) -> None:
    lines = [
        "# 16 Grade V+ 患病与不患病 18 对照对比",
        "",
        "分析对象：`datasets/facesym_v1_all_images_no_gate_20260119`",
        "",
        "## 结论摘要",
        "",
        "本报告固定使用 18 例 `不患病` 但 Grade V+ 输出 `人脸不对称` 的病例作为对照组，并从 `患病` Grade V+ 病例中按 split、grade 和代理总分接近度挑取 18 例进行配对。两组均为代理高等级样本，因此本报告用于观察同为 Grade V+ 时的患病/不患病特征差异和人工复核重点。",
        "",
        f"- 配对数：`{summary['pair_count']}`",
        f"- 行数：`{summary['row_count']}`",
        f"- 匹配规则：`{json.dumps(summary['matching_rules'], ensure_ascii=False, sort_keys=True)}`",
        f"- 不患病 split：`{json.dumps(summary['by_group_split']['不患病对照'], ensure_ascii=False, sort_keys=True)}`",
        f"- 患病 split：`{json.dumps(summary['by_group_split']['患病匹配'], ensure_ascii=False, sort_keys=True)}`",
        f"- 不患病 grade：`{json.dumps(summary['by_group_grade']['不患病对照'], ensure_ascii=False, sort_keys=True)}`",
        f"- 患病 grade：`{json.dumps(summary['by_group_grade']['患病匹配'], ensure_ascii=False, sort_keys=True)}`",
        "- 输出 CSV：`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv`",
        "- 输出 JSON：`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json`",
        "",
        "## 组件均值对比",
        "",
        "| component | 不患病对照 mean | 患病匹配 mean | 患病-不患病 |",
        "| --- | ---: | ---: | ---: |",
    ]
    nondisease_means = summary["component_means"]["不患病对照"]
    diseased_means = summary["component_means"]["患病匹配"]
    deltas = summary["component_mean_delta_diseased_minus_nondisease"]
    for component in nondisease_means:
        lines.append(
            f"| {md_cell(component)} | {nondisease_means[component]:.6f} | {diseased_means[component]:.6f} | {deltas[component]:.6f} |"
        )

    lines.extend(group_reason_sections(summary))
    lines.extend(
        [
            "",
            "## 18 组逐对特征点图片对比",
            "",
            "每一组左侧是不患病 Grade V+ 对照，右侧是按 split/grade/代理分数接近度挑取的患病 Grade V+ 样本。每例展示 6 个核心 role 的 MediaPipe 特征点叠加图。",
            "",
        ]
    )
    for index, pair in enumerate(pairs, start=1):
        lines.extend(pair_section(index, pair))

    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- `患病/不患病` 是 patient outcome 标签，不是人工面部不对称真值。",
            "- 两组均已达到 Grade V+ 代理高等级，不能用本报告推断临床诊断性能。",
            "- 当前 all-images/no-gate 数据未运行质量门控，表情配合、采集角度、闭眼程度和图像质量都会影响代理分数。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def group_reason_sections(summary: Mapping[str, Any]) -> list[str]:
    lines = ["", "## 组内原因 Top 对比", ""]
    for title, key in [
        ("组件驱动", "top_component_drivers"),
        ("Role 驱动", "top_role_drivers"),
        ("高频特征", "top_features"),
    ]:
        lines.extend([f"### {title}", "", "| group | term | count |", "| --- | --- | ---: |"])
        for group in ["不患病对照", "患病匹配"]:
            for term, count in list(summary[key][group].items())[:15]:
                value = f"`{md_cell(term)}`" if title == "高频特征" else md_cell(term)
                lines.append(f"| {group} | {value} | {count} |")
        lines.append("")
    return lines


def pair_section(index: int, pair: Mapping[str, Any]) -> list[str]:
    nondisease = pair["nondisease"]
    diseased = pair["diseased"]
    return [
        f"### {index}. {pair['pair_id']} `{pair['matching_rule']}`",
        "",
        '<div style="display:grid; grid-template-columns:repeat(2, minmax(280px, 1fr)); gap:18px; align-items:start;">',
        case_panel("不患病对照", nondisease),
        case_panel("患病匹配", diseased),
        "</div>",
        "",
    ]


def case_panel(title: str, case: Mapping[str, Any]) -> str:
    safe_title = html.escape(title)
    patient = html.escape(str(case.get("patient_sample_id", "")))
    grade = html.escape(str(case.get("hb_proxy_grade", "")))
    split = html.escape(str(case.get("split", "")))
    confidence = html.escape(str(case.get("hb_grade_confidence", "")))
    analysis = html.escape(str(case.get("analysis_summary", "")))
    focus = html.escape(str(case.get("review_focus", "")))
    return "\n".join(
        [
            '<section style="border:1px solid #ddd; padding:10px;">',
            f"<h4>{safe_title}: {patient}</h4>",
            f"<p><strong>split</strong>: <code>{split}</code> | <strong>grade</strong>: <code>{grade}</code> | <strong>confidence</strong>: <code>{confidence}</code></p>",
            f"<p>{analysis}</p>",
            f"<p><strong>复核重点：</strong>{focus}</p>",
            image_grid(case.get("_role_images", [])),
            "</section>",
        ]
    )


if __name__ == "__main__":
    main()
