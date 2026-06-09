#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

CORE_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
ROLE_LABELS = {
    "front": "正脸静息",
    "smile": "微笑",
    "teeth": "示齿",
    "eyes_closed": "闭眼",
    "forehead_wrinkle": "抬眉/皱额",
    "frown": "皱眉",
}
COMPONENTS = (
    ("resting_symmetry_score", "hb_resting_level", "静息对称性"),
    ("eye_closure_score", "hb_eye_closure_level", "闭眼完整性/眼裂对称"),
    ("brow_forehead_score", "hb_brow_forehead_level", "眉额/皱眉动态"),
    ("smile_mouth_score", "hb_smile_mouth_level", "微笑/示齿口部动态"),
    ("gross_asymmetry_score", "hb_gross_asymmetry_level", "整体不对称"),
)
LEVEL_LABELS = {
    "normal": "正常",
    "mild": "轻度",
    "moderate": "中度",
    "severe": "严重",
    "missing": "缺失",
    "unknown": "未知",
}


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
    cases = [
        enrich_case(row, patient_by_id, image_scores_by_patient, keypoint_by_sample, dataset)
        for row in grade_v_plus_rows
        if row.get("label_binary") == "0" or row.get("label_group") == "不患病"
    ]
    cases = sorted(cases, key=lambda row: (row["split"], row["hb_proxy_grade_num"], row["patient_sample_id"]))

    summary = summarize_cases(cases)
    write_csv(metadata / "13_v11_hb_proxy_grade_v_plus_nondisease_cases.csv", cases)
    write_json(metadata / "13_v11_hb_proxy_grade_v_plus_nondisease_summary.json", summary)
    write_report(reports / "15_v11_grade_v_plus_nondisease_false_positive_review.md", cases, summary, dataset)

    print(f"Wrote {metadata / '13_v11_hb_proxy_grade_v_plus_nondisease_cases.csv'}")
    print(f"Wrote {metadata / '13_v11_hb_proxy_grade_v_plus_nondisease_summary.json'}")
    print(f"Wrote {reports / '15_v11_grade_v_plus_nondisease_false_positive_review.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract and review Grade V+ non-disease face-asymmetry cases.")
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
    fields = [
        "patient_sample_id",
        "split",
        "label_group",
        "label_binary",
        "hb_proxy_grade",
        "hb_proxy_grade_num",
        "hb_grade_confidence",
        "face_asymmetry_output",
        "analysis_summary",
        "review_focus",
        "top_component_driver",
        "top_role_driver",
        "component_driver_labels",
        "role_driver_labels",
        "annotation_paths",
        "role_scores",
        "face_asymmetry_reason",
        "face_asymmetry_reason_codes",
        "top_positive_features",
        "hb_component_evidence",
    ]
    extra_fields = sorted({key for row in rows for key in row if key not in fields})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields + extra_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def group_image_scores(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, str]]]:
    grouped: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        role = row.get("media_role", "")
        if role in CORE_ROLES:
            grouped[row["patient_sample_id"]][role].append(row)

    best_by_patient: dict[str, dict[str, dict[str, str]]] = {}
    for patient_id, roles in grouped.items():
        best_by_patient[patient_id] = {
            role: max(role_rows, key=lambda item: parse_float(item.get("role_asymmetry_score")) or -1.0)
            for role, role_rows in roles.items()
            if role_rows
        }
    return best_by_patient


def enrich_case(
    case: Mapping[str, str],
    patient_by_id: Mapping[str, Mapping[str, str]],
    image_scores_by_patient: Mapping[str, Mapping[str, Mapping[str, str]]],
    keypoint_by_sample: Mapping[str, Mapping[str, str]],
    dataset: Path,
) -> dict[str, Any]:
    patient_id = case["patient_sample_id"]
    patient = patient_by_id.get(patient_id, {})
    merged = {**patient, **case}
    best_role_scores = image_scores_by_patient.get(patient_id, {})
    role_images = role_image_payload(best_role_scores, keypoint_by_sample, dataset)
    component_drivers = component_driver_labels(merged)
    role_drivers = role_driver_labels(best_role_scores)
    feature_terms = compact_features(str(merged.get("top_positive_features", "")))

    analysis_parts = [
        "该患者 patient outcome 为不患病，但 Grade V+ 规则输出人脸不对称。",
        "不患病标签不是人工面部对称真值，可能存在真实面部不对称、表情配合差异或无质量门控输入放大。",
    ]
    if component_drivers:
        analysis_parts.append(f"主要组件驱动：{'；'.join(component_drivers[:5])}。")
    if role_drivers:
        analysis_parts.append(f"主要 role 驱动：{'；'.join(role_drivers[:4])}。")
    if feature_terms:
        analysis_parts.append(f"主要特征证据：{';'.join(feature_terms[:8])}。")

    review_focus = review_focus_for(component_drivers, role_drivers)
    return {
        **merged,
        "analysis_summary": "".join(analysis_parts),
        "review_focus": review_focus,
        "top_component_driver": component_drivers[0] if component_drivers else "",
        "top_role_driver": role_drivers[0] if role_drivers else "",
        "component_driver_labels": ";".join(component_drivers),
        "role_driver_labels": ";".join(role_drivers),
        "annotation_paths": ";".join(item["annotation_path"] for item in role_images if item["annotation_path"]),
        "role_scores": ";".join(
            f"{item['media_role']}={item['role_asymmetry_score']}" for item in role_images if item["role_asymmetry_score"]
        ),
        "_component_driver_list": component_drivers,
        "_role_driver_list": role_drivers,
        "_role_images": role_images,
    }


def role_image_payload(
    best_role_scores: Mapping[str, Mapping[str, str]],
    keypoint_by_sample: Mapping[str, Mapping[str, str]],
    dataset: Path,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for role in CORE_ROLES:
        score_row = best_role_scores.get(role, {})
        sample_id = score_row.get("sample_id", "")
        keypoint_row = keypoint_by_sample.get(sample_id, {})
        annotation_path = keypoint_row.get("annotation_path", "")
        full_path = dataset / annotation_path if annotation_path else None
        output.append(
            {
                "media_role": role,
                "role_label": ROLE_LABELS[role],
                "sample_id": sample_id,
                "role_asymmetry_score": score_row.get("role_asymmetry_score", ""),
                "top_positive_features": score_row.get("top_positive_features", ""),
                "annotation_path": annotation_path if full_path and full_path.exists() else "",
                "report_image_path": f"../{annotation_path}" if annotation_path and full_path and full_path.exists() else "",
            }
        )
    return output


def component_driver_labels(row: Mapping[str, Any]) -> list[str]:
    drivers: list[tuple[float, str]] = []
    for score_field, level_field, label in COMPONENTS:
        score = parse_float(row.get(score_field))
        level = str(row.get(level_field, ""))
        if level not in {"moderate", "severe"} and (score is None or score < 0.55):
            continue
        level_label = LEVEL_LABELS.get(level, level or "未知")
        score_text = f"{score:.6f}" if score is not None else ""
        rank = score if score is not None else 0.0
        drivers.append((rank, f"{label}{level_label}({score_text})"))
    movement = parse_float(row.get("movement_absence_score"))
    if row.get("hb_movement_absence_flag") == "1" or (movement is not None and movement >= 0.20):
        drivers.append((movement or 0.0, f"无运动风险({movement:.6f})" if movement is not None else "无运动风险"))
    return [label for _rank, label in sorted(drivers, key=lambda item: item[0], reverse=True)]


def role_driver_labels(best_role_scores: Mapping[str, Mapping[str, str]]) -> list[str]:
    drivers: list[tuple[float, str]] = []
    for role, row in best_role_scores.items():
        score = parse_float(row.get("role_asymmetry_score"))
        if score is None:
            continue
        top_features = compact_features(row.get("top_positive_features", ""), limit=3)
        feature_text = f"，证据={';'.join(top_features)}" if top_features else ""
        drivers.append((score, f"{ROLE_LABELS.get(role, role)}({score:.6f}{feature_text})"))
    ordered = sorted(drivers, key=lambda item: item[0], reverse=True)
    selected = [item for item in ordered if item[0] >= 0.55]
    if not selected:
        selected = ordered[:3]
    return [label for _score, label in selected]


def review_focus_for(component_drivers: list[str], role_drivers: list[str]) -> str:
    focus = [
        "先人工查看正脸静息是否确有结构性不对称",
        "再查看闭眼、抬眉/皱额、微笑/示齿是否存在配合不足或表情幅度差异",
    ]
    if any("无运动风险" in item for item in component_drivers):
        focus.append("重点确认是否为表情动作不到位导致的无运动风险")
    if role_drivers:
        focus.append(f"优先查看高分 role：{';'.join(role_drivers[:3])}")
    return "；".join(focus)


def compact_features(raw: str, limit: int = 8) -> list[str]:
    features = [item.strip() for item in raw.replace(",", ";").split(";") if item.strip()]
    output: list[str] = []
    seen: set[str] = set()
    for feature in features:
        if feature in seen:
            continue
        seen.add(feature)
        output.append(feature)
        if len(output) >= limit:
            break
    return output


def summarize_cases(cases: list[Mapping[str, Any]]) -> dict[str, Any]:
    component_counter: Counter[str] = Counter()
    role_counter: Counter[str] = Counter()
    feature_counter: Counter[str] = Counter()
    for case in cases:
        for item in case.get("_component_driver_list", []):
            if item:
                component_counter[item.split("(")[0]] += 1
        for item in case.get("_role_driver_list", []):
            if item:
                role_counter[item.split("(")[0]] += 1
        for feature in compact_features(str(case.get("top_positive_features", "")), limit=12):
            feature_counter[feature] += 1

    return {
        "dataset": DEFAULT_DATASET.as_posix(),
        "rule": "label_binary == 0 AND hb_proxy_grade_num >= 5",
        "case_count": len(cases),
        "by_split": count_by(cases, "split"),
        "by_grade": count_by(cases, "hb_proxy_grade"),
        "top_component_drivers": dict(component_counter.most_common(20)),
        "top_role_drivers": dict(role_counter.most_common(20)),
        "top_features": dict(feature_counter.most_common(30)),
        "outputs": {
            "csv": "metadata/13_v11_hb_proxy_grade_v_plus_nondisease_cases.csv",
            "json": "metadata/13_v11_hb_proxy_grade_v_plus_nondisease_summary.json",
            "report": "reports/15_v11_grade_v_plus_nondisease_false_positive_review.md",
        },
        "interpretation_limit": "不患病是 patient outcome 标签，不是人工面部对称真值；该清单应作为 Grade V+ 规则假阳性/标签口径差异复核集。",
    }


def write_report(path: Path, cases: list[Mapping[str, Any]], summary: Mapping[str, Any], dataset: Path) -> None:
    lines = [
        "# 15 Grade V+ 不患病人脸不对称复核",
        "",
        "分析对象：`datasets/facesym_v1_all_images_no_gate_20260119`",
        "",
        "## 结论摘要",
        "",
        "本报告从 `12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv` 中单独提取 patient outcome 为 `不患病`、但 `hb_proxy_grade_num >= 5` 且输出 `人脸不对称` 的病例。该清单用于复核 Grade V+ 规则的假阳性、标签口径差异和无质量门控输入影响。",
        "",
        f"- 不患病 Grade V+ 输出病例：`{summary['case_count']}`",
        f"- 按 split：`{json.dumps(summary['by_split'], ensure_ascii=False, sort_keys=True)}`",
        f"- 按 grade：`{json.dumps(summary['by_grade'], ensure_ascii=False, sort_keys=True)}`",
        "- 输出 CSV：`metadata/13_v11_hb_proxy_grade_v_plus_nondisease_cases.csv`",
        "- 输出 JSON：`metadata/13_v11_hb_proxy_grade_v_plus_nondisease_summary.json`",
        "",
        "## 原因聚合",
        "",
        "### 组件驱动 Top",
        "",
        "| component_driver | count |",
        "| --- | ---: |",
    ]
    for key, value in summary["top_component_drivers"].items():
        lines.append(f"| {md_cell(key)} | {value} |")
    lines.extend(
        [
            "",
            "### Role 驱动 Top",
            "",
            "| role_driver | count |",
            "| --- | ---: |",
        ]
    )
    for key, value in summary["top_role_drivers"].items():
        lines.append(f"| {md_cell(key)} | {value} |")
    lines.extend(
        [
            "",
            "### 高频特征证据 Top",
            "",
            "| feature | count |",
            "| --- | ---: |",
        ]
    )
    for key, value in summary["top_features"].items():
        lines.append(f"| `{md_cell(key)}` | {value} |")

    lines.extend(
        [
            "",
            "## 逐例复核与特征点图片",
            "",
            "图片为当前数据集已生成的 MediaPipe Face Landmarker 特征点叠加图。每例展示 6 个核心 role 的最高 role-asymmetry 样本；缺图说明对应 role 未检测或未生成叠加图。",
            "",
        ]
    )
    for index, case in enumerate(cases, start=1):
        lines.extend(patient_section(index, case))

    lines.extend(
        [
            "",
            "## 解释限制",
            "",
            "- `不患病` 是 patient outcome 标签，不是人工标注的面部对称真值。",
            "- 当前 all-images/no-gate 数据未运行质量门控；表情配合、闭眼程度、局部遮挡、头部姿态和采集差异都可能放大代理不对称分数。",
            "- 本报告用于人工复核和规则改进，不应作为临床诊断结论。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def patient_section(index: int, case: Mapping[str, Any]) -> list[str]:
    lines = [
        f"### {index}. {case['patient_sample_id']}",
        "",
        f"- split：`{case.get('split', '')}`；grade：`{case.get('hb_proxy_grade', '')}`；confidence：`{case.get('hb_grade_confidence', '')}`",
        f"- 输出：`{case.get('face_asymmetry_output', '')}`",
        f"- 分析：{case.get('analysis_summary', '')}",
        f"- 复核重点：{case.get('review_focus', '')}",
        f"- 原始原因：{case.get('face_asymmetry_reason', '')}",
        "",
        image_grid(case.get("_role_images", [])),
        "",
    ]
    return lines


def image_grid(role_images: Any) -> str:
    items = role_images if isinstance(role_images, list) else []
    parts = ['<div style="display:flex; flex-wrap:wrap; gap:10px; align-items:flex-start;">']
    for item in items:
        label = html.escape(str(item.get("role_label", "")))
        role = html.escape(str(item.get("media_role", "")))
        score = html.escape(str(item.get("role_asymmetry_score", "")))
        image_path = str(item.get("report_image_path", ""))
        features = html.escape(";".join(compact_features(str(item.get("top_positive_features", "")), limit=3)))
        caption = f"{label}<br><code>{role}</code><br>score={score}<br>{features}"
        parts.append('<figure style="width:180px; margin:0 0 12px 0;">')
        if image_path:
            safe_path = html.escape(image_path)
            parts.append(f'<a href="{safe_path}"><img loading="lazy" src="{safe_path}" alt="{label}" width="180"></a>')
        else:
            parts.append('<div style="width:180px; height:120px; border:1px solid #ccc; display:flex; align-items:center; justify-content:center;">缺图</div>')
        parts.append(f'<figcaption style="font-size:12px; line-height:1.35;">{caption}</figcaption>')
        parts.append("</figure>")
    parts.append("</div>")
    return "\n".join(parts)


def count_by(rows: Iterable[Mapping[str, Any]], field: str) -> dict[str, int]:
    counter = Counter(str(row.get(field, "")) for row in rows)
    return dict(sorted(counter.items()))


def md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


if __name__ == "__main__":
    main()
