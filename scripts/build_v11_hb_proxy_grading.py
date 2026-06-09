#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"

INCLUDED_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")
KEY_DYNAMIC_ROLES = ("smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")

HB_GRADE_NAMES = {
    1: "Grade I 正常代理",
    2: "Grade II 轻度功能障碍代理",
    3: "Grade III 轻-中度功能障碍代理",
    4: "Grade IV 中度功能障碍代理",
    5: "Grade V 重度功能障碍代理",
    6: "Grade VI 完全瘫痪候选代理",
}

HB_GRADE_DESCRIPTORS = {
    1: {
        "resting_symmetry_label": "对称",
        "dynamic_symmetry_label": "对称",
        "eye_closure_label": "闭眼完整",
        "mouth_brow_motion_label": "眉额和笑容对称",
        "summary": "静息表现对称，动态表现对称。",
    },
    2: {
        "resting_symmetry_label": "粗略对称",
        "dynamic_symmetry_label": "轻微不对称",
        "eye_closure_label": "全力闭眼，轻柔用力可闭眼",
        "mouth_brow_motion_label": "轻度动态不对称",
        "summary": "静息粗略对称，动态轻微不对称。",
    },
    3: {
        "resting_symmetry_label": "粗略对称",
        "dynamic_symmetry_label": "轻度至中度不对称",
        "eye_closure_label": "只有全力以赴才能完全闭眼",
        "mouth_brow_motion_label": "轻度至中度动态不对称",
        "summary": "静息粗略对称，动态轻度至中度不对称。",
    },
    4: {
        "resting_symmetry_label": "粗略对称",
        "dynamic_symmetry_label": "中度不对称",
        "eye_closure_label": "闭眼不完全风险",
        "mouth_brow_motion_label": "眉毛中度抬高和笑容不对称",
        "summary": "静息仍可粗略对称，眉额/笑容中度不对称。",
    },
    5: {
        "resting_symmetry_label": "极度不对称",
        "dynamic_symmetry_label": "严重不对称",
        "eye_closure_label": "闭眼不完全风险",
        "mouth_brow_motion_label": "严重眉毛抬高和笑容不对称",
        "summary": "静息极度不对称，动态严重不对称。",
    },
    6: {
        "resting_symmetry_label": "极度不对称",
        "dynamic_symmetry_label": "无动态",
        "eye_closure_label": "闭眼不全风险",
        "mouth_brow_motion_label": "没有动态或动态极低",
        "summary": "静息极度不对称，动态基本缺失。",
    },
}

COMPONENT_WEIGHTS = {
    "resting_symmetry_score": 0.18,
    "eye_closure_score": 0.16,
    "brow_forehead_score": 0.18,
    "smile_mouth_score": 0.24,
    "gross_asymmetry_score": 0.16,
    "movement_absence_score": 0.08,
}

COMPONENT_LABELS = {
    "resting_symmetry_score": "静息对称性",
    "eye_closure_score": "闭眼完整性/眼裂对称",
    "brow_forehead_score": "眉额/皱眉动态",
    "smile_mouth_score": "微笑/示齿口部动态",
    "gross_asymmetry_score": "整体不对称",
    "movement_absence_score": "无运动风险",
    "quality_reliability_score": "质量可靠性",
}

METADATA_FIELDS = {
    "sample_id",
    "patient_sample_id",
    "label_group",
    "label_binary",
    "media_role",
    "detection_status",
    "split",
}
POSE_DISTANCE_FEATURE_PREFIXES = ("matrix_", "pose_")
POSE_DISTANCE_FEATURE_SUFFIXES = ("_centroid_z_asym",)
POSE_DISTANCE_FEATURE_TOKENS = ("yaw", "pitch", "roll", "scale", "distance", "bbox", "translation")
FACE_ASYMMETRY_GRADE_THRESHOLD = 5
FACE_ASYMMETRY_OUTPUT_LABEL = "人脸不对称"
FACE_ASYMMETRY_NOT_TRIGGERED_LABEL = "未触发Grade V+人脸不对称输出"

GRADE_V_PLUS_COMPONENT_FIELDS = (
    ("hb_resting_level", "resting_symmetry_score", "静息对称性"),
    ("hb_eye_closure_level", "eye_closure_score", "闭眼完整性/眼裂对称"),
    ("hb_brow_forehead_level", "brow_forehead_score", "眉额/皱眉动态"),
    ("hb_smile_mouth_level", "smile_mouth_score", "微笑/示齿口部动态"),
    ("hb_gross_asymmetry_level", "gross_asymmetry_score", "整体不对称"),
)
COMPONENT_LEVEL_LABELS = {
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

    split_rows = read_csv(required(metadata / "05_patient_splits.csv"))
    patient_core_rows = read_csv(required(metadata / "11_v11_role_aware_patient_core_results.csv"))
    image_score_rows = read_csv(required(metadata / "11_v11_role_aware_image_scores.csv"))
    full_feature_rows = read_csv(required(metadata / "09_mediapipe_full_features.csv"))
    feature_set_rows = read_csv(required(metadata / "11_v11_role_aware_feature_set.csv"))

    split_by_patient = {row["patient_sample_id"]: row for row in split_rows}
    core_by_patient = {row["patient_sample_id"]: row for row in patient_core_rows}
    feature_evidence = build_feature_evidence(image_score_rows)
    expression = build_expression_strengths(full_feature_rows, split_by_patient)
    median_weight = median(
        [
            value
            for row in patient_core_rows
            if row.get("split") in {"train", "val"}
            if (value := parse_float(row.get("patient_weight_total"))) is not None
        ]
    )

    base_records: list[dict[str, Any]] = []
    for patient_id in sorted(split_by_patient):
        split_row = split_by_patient[patient_id]
        core_row = core_by_patient.get(patient_id)
        components = build_components(core_row, expression.get(patient_id, {}), median_weight)
        base_records.append(
            {
                "patient_sample_id": patient_id,
                "label_group": split_row.get("label_group", core_row.get("label_group", "") if core_row else ""),
                "label_binary": split_row.get("label_binary", core_row.get("label_binary", "") if core_row else ""),
                "split": split_row.get("split", core_row.get("split", "") if core_row else ""),
                "core_row_available": "1" if core_row else "0",
                "components": components,
                "core_row": core_row or {},
            }
        )

    thresholds = build_thresholds(base_records)
    patient_grade_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    for base in base_records:
        grade_row, patient_components = build_patient_grade(base, thresholds, feature_evidence)
        patient_grade_rows.append(grade_row)
        component_rows.extend(patient_components)

    mediapipe_difference_rows = build_mediapipe_grade_differences(full_feature_rows, patient_grade_rows)
    grade_v_plus_asymmetry_rows = build_grade_v_plus_asymmetry_cases(patient_grade_rows)
    review_rows = build_manual_review_candidates(patient_grade_rows)
    evaluation = build_evaluation(
        patient_grade_rows,
        component_rows,
        thresholds,
        args,
        feature_set_rows,
        mediapipe_difference_rows,
    )

    write_csv(metadata / "12_v11_hb_proxy_patient_grades.csv", patient_grade_rows)
    write_csv(metadata / "12_v11_hb_proxy_component_scores.csv", component_rows)
    write_csv(metadata / "12_v11_hb_proxy_mediapipe_grade_differences.csv", mediapipe_difference_rows)
    write_csv(metadata / "12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv", grade_v_plus_asymmetry_rows)
    write_csv(metadata / "12_v11_hb_proxy_manual_review_candidates.csv", review_rows)
    write_json(metadata / "12_v11_hb_proxy_grade_evaluation.json", evaluation)
    write_report(
        reports / "14_v11_hb_proxy_grading_results.md",
        evaluation,
        patient_grade_rows,
        review_rows,
        grade_v_plus_asymmetry_rows,
    )

    print(f"Wrote {metadata / '12_v11_hb_proxy_patient_grades.csv'}")
    print(f"Wrote {metadata / '12_v11_hb_proxy_component_scores.csv'}")
    print(f"Wrote {metadata / '12_v11_hb_proxy_mediapipe_grade_differences.csv'}")
    print(f"Wrote {metadata / '12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv'}")
    print(f"Wrote {metadata / '12_v11_hb_proxy_grade_evaluation.json'}")
    print(f"Wrote {reports / '14_v11_hb_proxy_grading_results.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build House-Brackmann-style V1.1 proxy grading outputs.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing V1.1 metadata.")
    return parser.parse_args()


def required(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Required V1.1 input is missing: {path}")
    return path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    fixed = [
        "patient_sample_id",
        "label_group",
        "label_binary",
        "split",
        "component",
        "hb_proxy_grade",
        "hb_proxy_grade_num",
        "hb_proxy_grade_name",
        "face_asymmetry_output",
        "face_asymmetry_rule",
        "face_asymmetry_reason",
    ]
    fields = [field for field in fixed if field in fields] + [field for field in fields if field not in fixed]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_components(
    core_row: Mapping[str, str] | None,
    expression: Mapping[str, float],
    median_weight: float,
) -> dict[str, float | None]:
    if not core_row:
        return {
            "resting_symmetry_score": None,
            "eye_closure_score": None,
            "brow_forehead_score": None,
            "smile_mouth_score": None,
            "gross_asymmetry_score": None,
            "movement_absence_score": None,
            "quality_reliability_score": 0.0,
        }

    role_scores = {role: parse_float(core_row.get(f"{role}_score")) for role in INCLUDED_ROLES}
    resting = role_scores["front"]
    eye = role_scores["eyes_closed"]
    brow = weighted_mean([(role_scores["forehead_wrinkle"], 0.55), (role_scores["frown"], 0.45)])
    smile = weighted_mean([(role_scores["smile"], 0.55), (role_scores["teeth"], 0.45)])
    available_scores = [score for score in role_scores.values() if score is not None]
    gross = weighted_mean(
        [
            (parse_float(core_row.get("v11_asymmetry_score")), 0.55),
            (max(available_scores) if available_scores else None, 0.45),
        ]
    )
    dynamic_asymmetry = max([score for score in [eye, brow, smile] if score is not None] or [0.0])
    expression_strength = expression.get("dynamic_expression_strength")
    if expression_strength is None:
        movement_absence = None
    else:
        movement_absence = clamp((1.0 - expression_strength) * dynamic_asymmetry)

    available_roles = sum(1 for role in INCLUDED_ROLES if core_row.get(f"{role}_available") == "1")
    patient_weight = parse_float(core_row.get("patient_weight_total")) or 0.0
    weight_reliability = clamp(patient_weight / median_weight) if median_weight > 0 else 0.0
    quality_reliability = clamp(0.70 * (available_roles / len(INCLUDED_ROLES)) + 0.30 * weight_reliability)

    return {
        "resting_symmetry_score": resting,
        "eye_closure_score": eye,
        "brow_forehead_score": brow,
        "smile_mouth_score": smile,
        "gross_asymmetry_score": gross,
        "movement_absence_score": movement_absence,
        "quality_reliability_score": quality_reliability,
        "mouth_expression_strength": expression.get("mouth_expression_strength"),
        "brow_expression_strength": expression.get("brow_expression_strength"),
        "eye_blink_strength": expression.get("eye_blink_strength"),
        "dynamic_expression_strength": expression_strength,
    }


def build_thresholds(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    train_val = [record for record in records if record["split"] in {"train", "val"}]
    total_scores = [
        score
        for record in train_val
        if (score := overall_proxy_score(record["components"])) is not None
    ]
    grade_thresholds = quantiles(total_scores, [0.20, 0.40, 0.60, 0.78, 0.92])
    component_thresholds = {
        name: quantiles(
            [
                value
                for record in train_val
                if (value := record["components"].get(name)) is not None
            ],
            [0.40, 0.65, 0.85],
        )
        for name in COMPONENT_LABELS
        if name != "quality_reliability_score"
    }
    movement_scores = [
        value
        for record in train_val
        if (value := record["components"].get("movement_absence_score")) is not None
    ]
    score_span = (max(total_scores) - min(total_scores)) if total_scores else 1.0
    return {
        "source": "train+val quantiles from V1.1 HB proxy component score distribution",
        "grade_thresholds": grade_thresholds,
        "component_thresholds": component_thresholds,
        "movement_absence_high": quantile(movement_scores, 0.85) if movement_scores else 0.0,
        "score_span": score_span if score_span > 1e-9 else 1.0,
    }


def build_patient_grade(
    base: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    feature_evidence: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    components: Mapping[str, float | None] = base["components"]
    score = overall_proxy_score(components)
    grade_num = hb_grade_num(score, thresholds["grade_thresholds"]) if score is not None else None
    component_levels = {
        name: component_level(components.get(name), thresholds["component_thresholds"].get(name, []))
        for name in COMPONENT_LABELS
        if name != "quality_reliability_score"
    }
    reliability = components.get("quality_reliability_score") or 0.0
    confidence = grade_confidence(score, reliability, thresholds) if grade_num else 0.0
    missing_roles = [role for role in KEY_DYNAMIC_ROLES if base["core_row"].get(f"{role}_available") != "1"]
    reason_codes = reason_codes_for(base, components, component_levels, confidence, thresholds, missing_roles)
    needs_review = needs_manual_review(grade_num, confidence, reliability, missing_roles, reason_codes)

    component_rows = []
    for component, label in COMPONENT_LABELS.items():
        value = components.get(component)
        component_rows.append(
            {
                "patient_sample_id": base["patient_sample_id"],
                "label_group": base["label_group"],
                "label_binary": base["label_binary"],
                "split": base["split"],
                "component": component,
                "component_label": label,
                "component_score": fmt_optional(value),
                "component_level": "reliability" if component == "quality_reliability_score" else component_levels.get(component, "missing"),
                "component_source": component_source(component),
            }
        )

    grade_name = HB_GRADE_NAMES.get(grade_num or 0, "")
    descriptor = grade_descriptor_for(grade_num)
    evidence = feature_evidence.get(base["patient_sample_id"], {})
    row: dict[str, Any] = {
        "patient_sample_id": base["patient_sample_id"],
        "label_group": base["label_group"],
        "label_binary": base["label_binary"],
        "split": base["split"],
        "hb_proxy_grade": f"Grade {roman(grade_num)}" if grade_num else "",
        "hb_proxy_grade_num": grade_num or "",
        "hb_proxy_grade_name": grade_name,
        "hb_resting_symmetry_label": descriptor["resting_symmetry_label"],
        "hb_dynamic_symmetry_label": descriptor["dynamic_symmetry_label"],
        "hb_eye_closure_label": descriptor["eye_closure_label"],
        "hb_mouth_brow_motion_label": descriptor["mouth_brow_motion_label"],
        "hb_grade_descriptor": descriptor["summary"],
        "hb_grade_confidence": fmt(confidence),
        "hb_proxy_overall_score": fmt_optional(score),
        "hb_resting_level": component_levels.get("resting_symmetry_score", "missing"),
        "hb_eye_closure_level": component_levels.get("eye_closure_score", "missing"),
        "hb_brow_forehead_level": component_levels.get("brow_forehead_score", "missing"),
        "hb_smile_mouth_level": component_levels.get("smile_mouth_score", "missing"),
        "hb_gross_asymmetry_level": component_levels.get("gross_asymmetry_score", "missing"),
        "hb_movement_absence_flag": "1" if "movement_absence_risk" in reason_codes else "0",
        "hb_quality_reliability": fmt(reliability),
        "hb_needs_manual_review": "1" if needs_review else "0",
        "hb_reason_codes": ";".join(reason_codes),
        "binary_abnormal_grade_ii_plus": binary_grade(grade_num, 2),
        "binary_abnormal_grade_iii_plus": binary_grade(grade_num, 3),
        "binary_moderate_grade_iv_plus": binary_grade(grade_num, 4),
        "eye_closure_complete_proxy": fmt_optional(1.0 - components["eye_closure_score"] if components.get("eye_closure_score") is not None else None),
        "eye_closure_incomplete_risk": fmt_optional(components.get("eye_closure_score")),
        "eye_closure_asymmetry_score": fmt_optional(components.get("eye_closure_score")),
        "brow_elevation_asymmetry_score": fmt_optional(base["core_row"].get("forehead_wrinkle_score") if base["core_row"] else None),
        "forehead_motion_sufficiency": fmt_optional(components.get("brow_expression_strength")),
        "forehead_dynamic_abnormality_level": component_levels.get("brow_forehead_score", "missing"),
        "frown_brow_asymmetry_score": fmt_optional(base["core_row"].get("frown_score") if base["core_row"] else None),
        "glabella_motion_abnormality_level": component_levels.get("brow_forehead_score", "missing"),
        "resting_symmetry_score": fmt_optional(components.get("resting_symmetry_score")),
        "eye_closure_score": fmt_optional(components.get("eye_closure_score")),
        "brow_forehead_score": fmt_optional(components.get("brow_forehead_score")),
        "smile_mouth_score": fmt_optional(components.get("smile_mouth_score")),
        "gross_asymmetry_score": fmt_optional(components.get("gross_asymmetry_score")),
        "movement_absence_score": fmt_optional(components.get("movement_absence_score")),
        "quality_reliability_score": fmt_optional(components.get("quality_reliability_score")),
        "mouth_expression_strength": fmt_optional(components.get("mouth_expression_strength")),
        "brow_expression_strength": fmt_optional(components.get("brow_expression_strength")),
        "eye_blink_strength": fmt_optional(components.get("eye_blink_strength")),
        "dynamic_expression_strength": fmt_optional(components.get("dynamic_expression_strength")),
        "included_roles_available": base["core_row"].get("included_roles_available", "0"),
        "missing_hb_roles": ";".join(missing_roles),
        "v11_asymmetry_score": base["core_row"].get("v11_asymmetry_score", ""),
        "v11_core_result": base["core_row"].get("core_result", ""),
        "top_positive_features": base["core_row"].get("top_positive_features", ""),
        "hb_component_evidence": evidence.get("component_evidence", ""),
    }
    row.update(grade_v_plus_asymmetry_payload(row))
    return row, component_rows


def grade_descriptor_for(grade_num: int | None) -> dict[str, str]:
    if grade_num is None:
        return {
            "resting_symmetry_label": "无法判定",
            "dynamic_symmetry_label": "无法判定",
            "eye_closure_label": "无法判定",
            "mouth_brow_motion_label": "无法判定",
            "summary": "当前缺少足够证据生成 HB proxy 描述。",
        }
    return HB_GRADE_DESCRIPTORS[grade_num]


def grade_v_plus_asymmetry_payload(row: Mapping[str, Any]) -> dict[str, str]:
    grade_num = parse_int(row.get("hb_proxy_grade_num"))
    triggered = grade_num is not None and grade_num >= FACE_ASYMMETRY_GRADE_THRESHOLD
    if not triggered:
        return {
            "face_asymmetry_grade_v_plus_flag": "0",
            "face_asymmetry_output": FACE_ASYMMETRY_NOT_TRIGGERED_LABEL,
            "face_asymmetry_rule": f"hb_proxy_grade_num >= {FACE_ASYMMETRY_GRADE_THRESHOLD}",
            "face_asymmetry_reason": "",
            "face_asymmetry_reason_codes": "",
        }

    reasons = [
        f"{row.get('hb_proxy_grade', '')} 达到 Grade V+ 阈值",
        str(row.get("hb_grade_descriptor", "")),
    ]
    label_reasons = {
        "hb_resting_symmetry_label": "静息表现",
        "hb_dynamic_symmetry_label": "动态表现",
        "hb_eye_closure_label": "闭眼表现",
        "hb_mouth_brow_motion_label": "眉额/笑容表现",
    }
    for field, label in label_reasons.items():
        value = str(row.get(field, ""))
        if value and value not in {"对称", "粗略对称", "无法判定"}:
            reasons.append(f"{label}：{value}")

    for level_field, score_field, label in GRADE_V_PLUS_COMPONENT_FIELDS:
        level = str(row.get(level_field, ""))
        if level not in {"moderate", "severe"}:
            continue
        score = str(row.get(score_field, ""))
        level_label = COMPONENT_LEVEL_LABELS.get(level, level)
        score_text = f"，score={score}" if score else ""
        reasons.append(f"{label}为{level_label}{score_text}")

    if row.get("hb_movement_absence_flag") == "1":
        movement = str(row.get("movement_absence_score", ""))
        reasons.append(f"存在无运动风险，movement_absence_score={movement}" if movement else "存在无运动风险")

    feature_summary = compact_feature_summary(str(row.get("top_positive_features", "")))
    if feature_summary:
        reasons.append(f"主要MediaPipe/V1.1特征证据：{feature_summary}")

    return {
        "face_asymmetry_grade_v_plus_flag": "1",
        "face_asymmetry_output": FACE_ASYMMETRY_OUTPUT_LABEL,
        "face_asymmetry_rule": f"hb_proxy_grade_num >= {FACE_ASYMMETRY_GRADE_THRESHOLD}",
        "face_asymmetry_reason": "；".join(unique_nonempty(reasons)),
        "face_asymmetry_reason_codes": str(row.get("hb_reason_codes", "")),
    }


def compact_feature_summary(raw: str, limit: int = 8) -> str:
    features = [item.strip() for item in raw.replace(",", ";").split(";") if item.strip()]
    return ";".join(features[:limit])


def unique_nonempty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output


def overall_proxy_score(components: Mapping[str, float | None]) -> float | None:
    weighted = 0.0
    weight_total = 0.0
    for component, weight in COMPONENT_WEIGHTS.items():
        value = components.get(component)
        if value is None:
            continue
        weighted += weight * value
        weight_total += weight
    return clamp(weighted / weight_total) if weight_total else None


def hb_grade_num(score: float | None, thresholds: Iterable[float]) -> int | None:
    if score is None:
        return None
    grade = 1
    for threshold in thresholds:
        if score > threshold:
            grade += 1
    return max(1, min(6, grade))


def component_level(score: float | None, thresholds: Iterable[float]) -> str:
    if score is None:
        return "missing"
    t = list(thresholds)
    if len(t) < 3:
        return "unknown"
    if score <= t[0]:
        return "normal"
    if score <= t[1]:
        return "mild"
    if score <= t[2]:
        return "moderate"
    return "severe"


def grade_confidence(score: float | None, reliability: float, thresholds: Mapping[str, Any]) -> float:
    if score is None:
        return 0.0
    grade_thresholds = thresholds["grade_thresholds"]
    if not grade_thresholds:
        margin_score = 0.0
    else:
        nearest = min(abs(score - threshold) for threshold in grade_thresholds)
        margin_score = clamp(nearest / (thresholds["score_span"] * 0.12))
    return clamp(0.25 + 0.50 * reliability + 0.25 * margin_score)


def reason_codes_for(
    base: Mapping[str, Any],
    components: Mapping[str, float | None],
    component_levels: Mapping[str, str],
    confidence: float,
    thresholds: Mapping[str, Any],
    missing_roles: list[str],
) -> list[str]:
    codes = ["hb_proxy_not_clinical"]
    if base["core_row_available"] != "1":
        codes.append("missing_v11_patient_core_score")
    for role in missing_roles:
        codes.append(f"missing_role_{role}")
    for component, level in component_levels.items():
        if level == "severe":
            codes.append(f"severe_{component}")
        elif level == "moderate":
            codes.append(f"moderate_{component}")
    movement = components.get("movement_absence_score")
    if movement is not None and movement >= thresholds["movement_absence_high"]:
        codes.append("movement_absence_risk")
    reliability = components.get("quality_reliability_score") or 0.0
    if reliability < 0.65:
        codes.append("low_quality_reliability")
    if confidence < 0.55:
        codes.append("low_grade_confidence")
    return codes


def needs_manual_review(
    grade_num: int | None,
    confidence: float,
    reliability: float,
    missing_roles: list[str],
    reason_codes: list[str],
) -> bool:
    if grade_num is None:
        return True
    if missing_roles:
        return True
    if confidence < 0.55 or reliability < 0.65:
        return True
    if grade_num >= 5 and confidence < 0.70:
        return True
    if "movement_absence_risk" in reason_codes:
        return True
    return False


def build_expression_strengths(
    feature_rows: list[dict[str, str]],
    split_by_patient: Mapping[str, Mapping[str, str]],
) -> dict[str, dict[str, float]]:
    raw: dict[str, dict[str, float]] = defaultdict(dict)
    for row in feature_rows:
        patient_id = row["patient_sample_id"]
        role = row.get("media_role", "")
        if role in {"smile", "teeth"}:
            update_max(raw[patient_id], "mouth_raw", max_feature(row, MOUTH_EXPRESSION_FEATURES))
        elif role in {"forehead_wrinkle", "frown"}:
            update_max(raw[patient_id], "brow_raw", max_feature(row, BROW_EXPRESSION_FEATURES))
        elif role == "eyes_closed":
            update_max(raw[patient_id], "eye_raw", max_feature(row, EYE_CLOSURE_FEATURES))

    train_val = {
        patient_id: values
        for patient_id, values in raw.items()
        if split_by_patient.get(patient_id, {}).get("split") in {"train", "val"}
    }
    scales = {
        key: (
            quantile([values[key] for values in train_val.values() if key in values], 0.10),
            quantile([values[key] for values in train_val.values() if key in values], 0.90),
        )
        for key in ("mouth_raw", "brow_raw", "eye_raw")
    }
    output: dict[str, dict[str, float]] = {}
    for patient_id, values in raw.items():
        mouth = normalized(values.get("mouth_raw"), *scales["mouth_raw"])
        brow = normalized(values.get("brow_raw"), *scales["brow_raw"])
        eye = normalized(values.get("eye_raw"), *scales["eye_raw"])
        dynamic_values = [value for value in (mouth, brow, eye) if value is not None]
        output[patient_id] = {
            "mouth_expression_strength": mouth,
            "brow_expression_strength": brow,
            "eye_blink_strength": eye,
            "dynamic_expression_strength": max(dynamic_values) if dynamic_values else None,
        }
    return output


MOUTH_EXPRESSION_FEATURES = (
    "bs_mouthSmileLeft",
    "bs_mouthSmileRight",
    "bs_mouthStretchLeft",
    "bs_mouthStretchRight",
    "bs_mouthUpperUpLeft",
    "bs_mouthUpperUpRight",
    "bs_mouthLowerDownLeft",
    "bs_mouthLowerDownRight",
    "raw_lip_opening",
)
BROW_EXPRESSION_FEATURES = (
    "bs_browInnerUp",
    "bs_browOuterUpLeft",
    "bs_browOuterUpRight",
    "bs_browDownLeft",
    "bs_browDownRight",
    "bsdiff_brow_mean_abs",
)
EYE_CLOSURE_FEATURES = ("bs_eyeBlinkLeft", "bs_eyeBlinkRight", "bsdiff_eyeBlink_abs")


def max_feature(row: Mapping[str, str], fields: Iterable[str]) -> float | None:
    values = [value for field in fields if (value := parse_float(row.get(field))) is not None]
    return max(values) if values else None


def update_max(target: dict[str, float], key: str, value: float | None) -> None:
    if value is None:
        return
    if key not in target or value > target[key]:
        target[key] = value


def normalized(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    if high <= low + 1e-12:
        return 0.0
    return clamp((value - low) / (high - low))


def build_feature_evidence(image_score_rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in image_score_rows:
        grouped[row["patient_sample_id"]].append(row)
    output: dict[str, dict[str, str]] = {}
    for patient_id, rows in grouped.items():
        evidence_parts: list[str] = []
        for role in INCLUDED_ROLES:
            role_rows = [row for row in rows if row.get("media_role") == role]
            if not role_rows:
                continue
            best = max(role_rows, key=lambda item: parse_float(item.get("role_asymmetry_score")) or 0.0)
            features = [item for item in best.get("top_positive_features", "").split(";") if item][:3]
            if features:
                evidence_parts.append(f"{role}:{','.join(features)}")
        output[patient_id] = {"component_evidence": ";".join(evidence_parts)}
    return output


def build_manual_review_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        grade_num = parse_int(row.get("hb_proxy_grade_num"))
        label_binary = str(row.get("label_binary", ""))
        priority = "normal"
        reason: list[str] = []
        if row.get("hb_needs_manual_review") == "1":
            priority = "high"
            reason.append("needs_manual_review")
        if label_binary == "0" and grade_num is not None and grade_num >= 3:
            priority = "high"
            reason.append("non_disease_high_proxy_grade")
        if label_binary == "1" and grade_num is not None and grade_num <= 1:
            priority = "high"
            reason.append("disease_low_proxy_grade")
        if priority == "normal":
            continue
        candidates.append(
            {
                "patient_sample_id": row["patient_sample_id"],
                "label_group": row["label_group"],
                "label_binary": row["label_binary"],
                "split": row["split"],
                "review_priority": priority,
                "review_reason": ";".join(reason),
                "hb_proxy_grade": row["hb_proxy_grade"],
                "hb_proxy_grade_num": row["hb_proxy_grade_num"],
                "hb_grade_confidence": row["hb_grade_confidence"],
                "hb_reason_codes": row["hb_reason_codes"],
                "top_positive_features": row["top_positive_features"],
            }
        )
    return sorted(candidates, key=lambda row: (row["split"], row["label_group"], row["patient_sample_id"]))


def build_grade_v_plus_asymmetry_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for row in rows:
        if row.get("face_asymmetry_grade_v_plus_flag") != "1":
            continue
        cases.append(
            {
                "patient_sample_id": row["patient_sample_id"],
                "label_group": row["label_group"],
                "label_binary": row["label_binary"],
                "split": row["split"],
                "face_asymmetry_output": row["face_asymmetry_output"],
                "face_asymmetry_rule": row["face_asymmetry_rule"],
                "face_asymmetry_reason": row["face_asymmetry_reason"],
                "face_asymmetry_reason_codes": row["face_asymmetry_reason_codes"],
                "hb_proxy_grade": row["hb_proxy_grade"],
                "hb_proxy_grade_num": row["hb_proxy_grade_num"],
                "hb_proxy_grade_name": row["hb_proxy_grade_name"],
                "hb_grade_confidence": row["hb_grade_confidence"],
                "hb_grade_descriptor": row["hb_grade_descriptor"],
                "hb_resting_symmetry_label": row["hb_resting_symmetry_label"],
                "hb_dynamic_symmetry_label": row["hb_dynamic_symmetry_label"],
                "hb_eye_closure_label": row["hb_eye_closure_label"],
                "hb_mouth_brow_motion_label": row["hb_mouth_brow_motion_label"],
                "resting_symmetry_score": row["resting_symmetry_score"],
                "eye_closure_score": row["eye_closure_score"],
                "brow_forehead_score": row["brow_forehead_score"],
                "smile_mouth_score": row["smile_mouth_score"],
                "gross_asymmetry_score": row["gross_asymmetry_score"],
                "movement_absence_score": row["movement_absence_score"],
                "hb_needs_manual_review": row["hb_needs_manual_review"],
                "hb_reason_codes": row["hb_reason_codes"],
                "top_positive_features": row["top_positive_features"],
                "hb_component_evidence": row["hb_component_evidence"],
            }
        )
    return sorted(cases, key=lambda row: (row["split"], row["label_group"], row["patient_sample_id"]))


def build_mediapipe_grade_differences(
    feature_rows: list[dict[str, str]],
    grade_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grade_by_patient = {
        row["patient_sample_id"]: parse_int(row.get("hb_proxy_grade_num"))
        for row in grade_rows
        if parse_int(row.get("hb_proxy_grade_num")) is not None
    }
    if not feature_rows:
        return []
    feature_names = [name for name in feature_rows[0] if is_mediapipe_grade_feature(name)]
    patient_values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    patient_grade: dict[str, int] = {}
    for row in feature_rows:
        patient_id = row.get("patient_sample_id", "")
        grade = grade_by_patient.get(patient_id)
        role = row.get("media_role", "")
        if grade is None or role not in INCLUDED_ROLES:
            continue
        patient_grade[patient_id] = grade
        scopes = ("all_core_roles", role)
        for feature_name in feature_names:
            value = parse_float(row.get(feature_name))
            if value is None:
                continue
            for scope in scopes:
                patient_values[(scope, feature_name, patient_id)].append(value)

    grouped: dict[tuple[str, str], dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for (scope, feature_name, patient_id), values in patient_values.items():
        if not values:
            continue
        grouped[(scope, feature_name)][patient_grade[patient_id]].append(mean(values))

    rows: list[dict[str, Any]] = []
    for (scope, feature_name), values_by_grade in grouped.items():
        grade_means = {grade: mean(values) for grade, values in values_by_grade.items() if values}
        if len(grade_means) < 2:
            continue
        all_values = [value for values in values_by_grade.values() for value in values]
        overall_std = std(all_values)
        i_to_vi_delta = grade_means.get(6, 0.0) - grade_means.get(1, 0.0)
        adjacent = adjacent_deltas(grade_means)
        strongest_pair, strongest_delta = max(adjacent.items(), key=lambda item: abs(item[1])) if adjacent else ("", 0.0)
        correlation = grade_value_correlation(values_by_grade)
        rows.append(
            {
                "scope": scope,
                "feature_family": feature_family(feature_name),
                "feature_name": feature_name,
                "feature_source": feature_source(feature_name),
                "patient_count": sum(len(values) for values in values_by_grade.values()),
                "grade_i_n": len(values_by_grade.get(1, [])),
                "grade_ii_n": len(values_by_grade.get(2, [])),
                "grade_iii_n": len(values_by_grade.get(3, [])),
                "grade_iv_n": len(values_by_grade.get(4, [])),
                "grade_v_n": len(values_by_grade.get(5, [])),
                "grade_vi_n": len(values_by_grade.get(6, [])),
                "grade_i_mean": fmt_optional(grade_means.get(1)),
                "grade_ii_mean": fmt_optional(grade_means.get(2)),
                "grade_iii_mean": fmt_optional(grade_means.get(3)),
                "grade_iv_mean": fmt_optional(grade_means.get(4)),
                "grade_v_mean": fmt_optional(grade_means.get(5)),
                "grade_vi_mean": fmt_optional(grade_means.get(6)),
                "grade_i_to_vi_delta": fmt(i_to_vi_delta),
                "abs_i_to_vi_delta": fmt(abs(i_to_vi_delta)),
                "overall_std": fmt(overall_std),
                "standardized_i_to_vi_effect": fmt(i_to_vi_delta / overall_std if overall_std > 1e-12 else 0.0),
                "strongest_adjacent_transition": strongest_pair,
                "strongest_adjacent_delta": fmt(strongest_delta),
                "standardized_strongest_adjacent_delta": fmt(strongest_delta / overall_std if overall_std > 1e-12 else 0.0),
                "grade_value_correlation": fmt(correlation),
                "ranking_score": fmt(
                    max(
                        abs(i_to_vi_delta / overall_std) if overall_std > 1e-12 else 0.0,
                        abs(strongest_delta / overall_std) if overall_std > 1e-12 else 0.0,
                        abs(correlation),
                    )
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            -float(row["ranking_score"]),
            row["scope"],
            row["feature_family"],
            row["feature_name"],
        ),
    )


def is_mediapipe_grade_feature(name: str) -> bool:
    if name in METADATA_FIELDS:
        return False
    lowered = name.lower()
    if lowered.startswith(POSE_DISTANCE_FEATURE_PREFIXES):
        return False
    if lowered.endswith(POSE_DISTANCE_FEATURE_SUFFIXES):
        return False
    if any(token in lowered for token in POSE_DISTANCE_FEATURE_TOKENS):
        return False
    return name.startswith(("raw_", "bsdiff_", "bs_")) and name != "bs_neutral"


def feature_source(name: str) -> str:
    if name.startswith("raw_all_mesh_region_"):
        return "mediapipe_478_all_landmarks"
    if name.startswith("raw_"):
        return "mediapipe_478_region_or_semantic_landmarks"
    if name.startswith("bsdiff_"):
        return "mediapipe_blendshape_left_right_difference"
    if name.startswith("bs_"):
        return "mediapipe_blendshape_expression"
    return "unknown"


def feature_family(name: str) -> str:
    if name.startswith("raw_all_mesh_region_"):
        return "all_mesh"
    if name.startswith(("raw_lip_", "raw_mouth_", "bsdiff_mouth", "bs_mouth")):
        return "mouth"
    if name.startswith(("raw_eye_", "raw_iris_", "bsdiff_eye", "bs_eye")):
        return "eye"
    if name.startswith(("raw_brow_", "raw_eyebrow_", "bsdiff_brow", "bs_brow")):
        return "brow"
    if name.startswith(("raw_face_oval_", "raw_jaw_", "raw_cheek_")):
        return "contour"
    if name.startswith(("raw_nose_", "raw_nostril_", "bsdiff_nose", "bs_nose")):
        return "midline_nose"
    if name.startswith("bsdiff_") or name.startswith("bs_"):
        return "blendshape_other"
    return "other"


def adjacent_deltas(grade_means: Mapping[int, float]) -> dict[str, float]:
    output: dict[str, float] = {}
    for left, right in [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6)]:
        if left in grade_means and right in grade_means:
            output[f"Grade {roman(left)}->{roman(right)}"] = grade_means[right] - grade_means[left]
    return output


def grade_value_correlation(values_by_grade: Mapping[int, list[float]]) -> float:
    grades: list[float] = []
    values: list[float] = []
    for grade, grade_values in values_by_grade.items():
        for value in grade_values:
            grades.append(float(grade))
            values.append(value)
    return pearson(grades, values)


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    mean_x = mean(xs)
    mean_y = mean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if denom_x <= 1e-12 or denom_y <= 1e-12:
        return 0.0
    return numerator / (denom_x * denom_y)


def build_evaluation(
    grade_rows: list[dict[str, Any]],
    component_rows: list[dict[str, Any]],
    thresholds: Mapping[str, Any],
    args: argparse.Namespace,
    feature_set_rows: list[dict[str, str]],
    mediapipe_difference_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    scorable_rows = [row for row in grade_rows if str(row.get("hb_proxy_grade_num", ""))]
    return {
        "version": "v1.1_hb_proxy_grading",
        "dataset": args.dataset.as_posix(),
        "source_inputs": [
            "metadata/11_v11_role_aware_feature_set.csv",
            "metadata/11_v11_role_aware_image_scores.csv",
            "metadata/11_v11_role_aware_patient_core_results.csv",
            "metadata/09_mediapipe_full_features.csv",
            "metadata/05_patient_splits.csv",
        ],
        "warning": "HB proxy grade is a technical proxy derived from weak patient-outcome associations. It is not a clinical House-Brackmann diagnosis.",
        "patients": len(grade_rows),
        "scorable_patients": len(scorable_rows),
        "unscorable_patients": len(grade_rows) - len(scorable_rows),
        "component_weights": COMPONENT_WEIGHTS,
        "thresholds": thresholds,
        "feature_set": {
            "selected_features": len(feature_set_rows),
            "selected_by_role": count_by(feature_set_rows, "role"),
            "selected_by_type": count_by(feature_set_rows, "feature_type"),
        },
        "grade_distribution": grade_distribution(scorable_rows),
        "mean_grade_by_label": mean_grade_by_label(scorable_rows),
        "mean_component_by_label": mean_component_by_label(component_rows),
        "proxy_monotonicity": proxy_monotonicity(scorable_rows),
        "binary_metrics": {
            "grade_ii_plus": metrics_by_split(scorable_rows, 2),
            "grade_iii_plus": metrics_by_split(scorable_rows, 3),
            "grade_iv_plus": metrics_by_split(scorable_rows, 4),
            "grade_v_plus_face_asymmetry": metrics_by_split(scorable_rows, FACE_ASYMMETRY_GRADE_THRESHOLD),
        },
        "grade_v_plus_face_asymmetry": summarize_grade_v_plus_asymmetry(grade_rows),
        "manual_review": {
            "needs_manual_review": sum(1 for row in grade_rows if row.get("hb_needs_manual_review") == "1"),
            "needs_manual_review_by_split": count_by(
                [row for row in grade_rows if row.get("hb_needs_manual_review") == "1"],
                "split",
            ),
            "common_reason_codes": common_reason_codes(grade_rows),
        },
        "grade_descriptor_policy": HB_GRADE_DESCRIPTORS,
        "mediapipe_grade_differences": summarize_mediapipe_grade_differences(mediapipe_difference_rows),
        "manual_hb_label_status": "not_available",
        "manual_hb_label_metrics": "weighted kappa / ordinal MAE not computed because hb_grade_manual is not available.",
    }


def summarize_grade_v_plus_asymmetry(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    cases = [row for row in rows if row.get("face_asymmetry_grade_v_plus_flag") == "1"]
    return {
        "rule": f"hb_proxy_grade_num >= {FACE_ASYMMETRY_GRADE_THRESHOLD}",
        "output_label": FACE_ASYMMETRY_OUTPUT_LABEL,
        "output": "metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv",
        "case_count": len(cases),
        "case_count_by_grade": count_by(cases, "hb_proxy_grade"),
        "case_count_by_label": count_by(cases, "label_group"),
        "case_count_by_split": count_by(cases, "split"),
        "weak_supervision_validation": metrics_by_split(list(rows), FACE_ASYMMETRY_GRADE_THRESHOLD),
        "common_reason_codes": common_reason_codes(cases),
        "common_reason_terms": common_grade_v_plus_reason_terms(cases),
    }


def common_grade_v_plus_reason_terms(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        reason = str(row.get("face_asymmetry_reason", ""))
        for term in reason.split("；"):
            cleaned = term.strip()
            if cleaned:
                counter[cleaned] += 1
    return dict(counter.most_common(30))


def summarize_mediapipe_grade_differences(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    all_core = [row for row in rows if row.get("scope") == "all_core_roles"]
    return {
        "output": "metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv",
        "rows": len(rows),
        "all_core_role_rows": len(all_core),
        "feature_sources": count_by(rows, "feature_source"),
        "feature_families": count_by(rows, "feature_family"),
        "top_all_core_role_features": [
            compact_difference_row(row)
            for row in sorted(all_core, key=lambda item: -float(item["ranking_score"]))[:20]
        ],
        "top_role_specific_features": [
            compact_difference_row(row)
            for row in sorted(
                [row for row in rows if row.get("scope") != "all_core_roles"],
                key=lambda item: -float(item["ranking_score"]),
            )[:30]
        ],
    }


def compact_difference_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scope": row.get("scope", ""),
        "feature_family": row.get("feature_family", ""),
        "feature_name": row.get("feature_name", ""),
        "feature_source": row.get("feature_source", ""),
        "grade_i_mean": row.get("grade_i_mean", ""),
        "grade_vi_mean": row.get("grade_vi_mean", ""),
        "standardized_i_to_vi_effect": row.get("standardized_i_to_vi_effect", ""),
        "strongest_adjacent_transition": row.get("strongest_adjacent_transition", ""),
        "standardized_strongest_adjacent_delta": row.get("standardized_strongest_adjacent_delta", ""),
        "grade_value_correlation": row.get("grade_value_correlation", ""),
    }


def grade_distribution(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "overall": count_by(rows, "hb_proxy_grade"),
        "by_label": count_by_join(rows, ("label_group", "hb_proxy_grade")),
        "by_split": count_by_join(rows, ("split", "hb_proxy_grade")),
        "by_split_label": count_by_join(rows, ("split", "label_group", "hb_proxy_grade")),
    }


def mean_grade_by_label(rows: list[Mapping[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        grade = parse_float(row.get("hb_proxy_grade_num"))
        if grade is not None:
            grouped[str(row.get("label_group", ""))].append(grade)
    return {label: mean(values) for label, values in sorted(grouped.items()) if values}


def mean_component_by_label(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        value = parse_float(row.get("component_score"))
        if value is None:
            continue
        grouped[(str(row.get("label_group", "")), str(row.get("component", "")))].append(value)
    output: dict[str, dict[str, float]] = defaultdict(dict)
    for (label, component), values in sorted(grouped.items()):
        output[label][component] = mean(values)
    return dict(output)


def proxy_monotonicity(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    means = mean_grade_by_label(rows)
    diseased = means.get("患病")
    non_diseased = means.get("不患病")
    diff = diseased - non_diseased if diseased is not None and non_diseased is not None else None
    return {
        "diseased_mean_grade": diseased,
        "non_diseased_mean_grade": non_diseased,
        "diseased_minus_non_diseased": diff,
        "passes_proxy_check": bool(diff is not None and diff > 0),
        "interpretation": "Proxy check expects 患病 mean grade > 不患病 mean grade; this is not clinical validation.",
    }


def metrics_by_split(rows: list[Mapping[str, Any]], positive_grade_threshold: int) -> dict[str, Any]:
    output = {"all": binary_metrics(rows, positive_grade_threshold)}
    output.update(
        {
            split: binary_metrics([row for row in rows if row.get("split") == split], positive_grade_threshold)
            for split in ["train", "val", "test"]
        }
    )
    return output


def binary_metrics(rows: list[Mapping[str, Any]], positive_grade_threshold: int) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = str(row.get("label_binary", ""))
        grade = parse_int(row.get("hb_proxy_grade_num"))
        if truth not in {"0", "1"} or grade is None:
            skipped += 1
            continue
        pred = "1" if grade >= positive_grade_threshold else "0"
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
    balanced = (recall + specificity) / 2.0
    return {
        "patients": len(rows),
        "evaluated": evaluated,
        "skipped": skipped,
        "accuracy": accuracy,
        "balanced_accuracy": balanced,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def common_reason_codes(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        for code in str(row.get("hb_reason_codes", "")).split(";"):
            if code:
                counter[code] += 1
    return dict(counter.most_common(30))


def write_report(
    path: Path,
    evaluation: Mapping[str, Any],
    grade_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    grade_v_plus_asymmetry_rows: list[dict[str, Any]],
) -> None:
    lines = [
        "# 14 V1.1 HB Proxy Grading Results",
        "",
        "分析对象：`datasets/facesym_v1_all_images_no_gate_20260119`",
        "",
        "## 结论摘要",
        "",
        "本阶段把 V1.1 role-aware 患病/不患病弱关联分数拆成 House-Brackmann 风格组件，并输出 I-VI 级 `hb_proxy_grade`。该等级是技术代理分级，不是临床 House-Brackmann 诊断。",
        "",
        f"- 患者数：`{evaluation['patients']}`",
        f"- 可评分患者数：`{evaluation['scorable_patients']}`",
        f"- 需要人工复核：`{evaluation['manual_review']['needs_manual_review']}`",
        f"- Grade V+ 输出人脸不对称：`{evaluation['grade_v_plus_face_asymmetry']['case_count']}`",
        f"- 患病平均 grade：`{fmt_optional(evaluation['proxy_monotonicity']['diseased_mean_grade'])}`",
        f"- 不患病平均 grade：`{fmt_optional(evaluation['proxy_monotonicity']['non_diseased_mean_grade'])}`",
        f"- 单调性检查：`{'通过' if evaluation['proxy_monotonicity']['passes_proxy_check'] else '未通过'}`",
        "",
        "## 输出产物",
        "",
        "- `metadata/12_v11_hb_proxy_patient_grades.csv`",
        "- `metadata/12_v11_hb_proxy_component_scores.csv`",
        "- `metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv`",
        "- `metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv`",
        "- `metadata/12_v11_hb_proxy_manual_review_candidates.csv`",
        "- `metadata/12_v11_hb_proxy_grade_evaluation.json`",
        "",
        "## 等级语义指定",
        "",
        "| grade | 静息表现 | 动态表现 | 闭眼 | 眉额/笑容 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for grade in range(1, 7):
        descriptor = HB_GRADE_DESCRIPTORS[grade]
        lines.append(
            "| Grade {grade} | {rest} | {dynamic} | {eye} | {motion} |".format(
                grade=roman(grade),
                rest=descriptor["resting_symmetry_label"],
                dynamic=descriptor["dynamic_symmetry_label"],
                eye=descriptor["eye_closure_label"],
                motion=descriptor["mouth_brow_motion_label"],
            )
        )
    lines.extend(
        [
            "",
            "## HB Proxy 组件",
            "",
            "| component | weight | 含义 |",
            "| --- | ---: | --- |",
        ]
    )
    for component, weight in COMPONENT_WEIGHTS.items():
        lines.append(f"| `{component}` | {weight:.2f} | {COMPONENT_LABELS[component]} |")
    lines.extend(
        [
            "",
            "## 分位数阈值",
            "",
            f"- Grade thresholds: `{', '.join(fmt(value) for value in evaluation['thresholds']['grade_thresholds'])}`",
            f"- Threshold source: `{evaluation['thresholds']['source']}`",
            "",
            "## Grade 分布",
            "",
            "| grade | count |",
            "| --- | ---: |",
        ]
    )
    for grade, count in sorted(evaluation["grade_distribution"]["overall"].items()):
        lines.append(f"| {grade} | {count} |")
    lines.extend(
        [
            "",
            "## 患病/不患病平均等级",
            "",
            "| label | mean_grade |",
            "| --- | ---: |",
        ]
    )
    for label, value in evaluation["mean_grade_by_label"].items():
        lines.append(f"| {label} | {value:.6f} |")
    grade_v_plus = evaluation["grade_v_plus_face_asymmetry"]
    lines.extend(
        [
            "",
            "## Grade V+ 人脸不对称输出验证",
            "",
            f"验证规则：当 `{grade_v_plus['rule']}` 时，`face_asymmetry_output` 输出为 `{grade_v_plus['output_label']}`。该验证仍使用 `患病/不患病` patient outcome 作为弱监督检查，不代表人工面部不对称真值。",
            "",
            f"- 输出病例数：`{grade_v_plus['case_count']}`",
            f"- 输出清单：`{grade_v_plus['output']}`",
            f"- Grade V+ 患病/不患病分布：`{json.dumps(grade_v_plus['case_count_by_label'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "| split | accuracy | balanced_accuracy | precision | recall | specificity | TP | FP | TN | FN |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for split in ["all", "train", "val", "test"]:
        metrics = grade_v_plus["weak_supervision_validation"][split]
        lines.append(
            "| {split} | {accuracy:.6f} | {balanced_accuracy:.6f} | {precision:.6f} | {recall:.6f} | {specificity:.6f} | {tp} | {fp} | {tn} | {fn} |".format(
                split=split,
                **metrics,
            )
        )
    lines.extend(
        [
            "",
            "### Grade V+ 输出样本（前 80 条）",
            "",
            "| patient | split | label | grade | confidence | output | reason |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for row in grade_v_plus_asymmetry_rows[:80]:
        lines.append(
            f"| {row['patient_sample_id']} | {row['split']} | {row['label_group']} | {row['hb_proxy_grade']} | {row['hb_grade_confidence']} | {row['face_asymmetry_output']} | {row['face_asymmetry_reason']} |"
        )
    lines.extend(
        [
            "",
            "## MediaPipe 478 点等级差异",
            "",
            "该分析读取 `09_mediapipe_full_features.csv`，使用 `raw_*`、`bsdiff_*`、降权表情 `bs_*` 等 MediaPipe 派生特征；其中 `raw_all_mesh_region_*` 来自 0-477 全部关键点统计。`matrix_*`、`pose_*`、采集距离和深度代理特征不进入等级差异分析。",
            "",
            f"- 差异行数：`{evaluation['mediapipe_grade_differences']['rows']}`",
            f"- 全核心 role 差异行数：`{evaluation['mediapipe_grade_differences']['all_core_role_rows']}`",
            f"- 输出：`{evaluation['mediapipe_grade_differences']['output']}`",
            "",
            "### 全核心 role 差异 Top 20",
            "",
            "| feature | family | source | Grade I mean | Grade VI mean | std_effect I->VI | strongest transition | std_adjacent_delta | corr |",
            "| --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for row in evaluation["mediapipe_grade_differences"]["top_all_core_role_features"]:
        lines.append(
            "| {feature_name} | {feature_family} | {feature_source} | {grade_i_mean} | {grade_vi_mean} | {standardized_i_to_vi_effect} | {strongest_adjacent_transition} | {standardized_strongest_adjacent_delta} | {grade_value_correlation} |".format(**row)
        )
    lines.extend(
        [
            "",
            "### 分 role 差异 Top 30",
            "",
            "| scope | feature | family | source | Grade I mean | Grade VI mean | std_effect I->VI | strongest transition | std_adjacent_delta | corr |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
        ]
    )
    for row in evaluation["mediapipe_grade_differences"]["top_role_specific_features"]:
        lines.append(
            "| {scope} | {feature_name} | {feature_family} | {feature_source} | {grade_i_mean} | {grade_vi_mean} | {standardized_i_to_vi_effect} | {strongest_adjacent_transition} | {standardized_strongest_adjacent_delta} | {grade_value_correlation} |".format(**row)
        )
    lines.extend(
        [
            "",
            "## 派生二分类指标",
            "",
            "| rule | split | accuracy | balanced_accuracy | precision | recall | specificity | TP | FP | TN | FN |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for rule, split_payload in evaluation["binary_metrics"].items():
        for split in ["all", "train", "val", "test"]:
            metrics = split_payload[split]
            lines.append(
                "| {rule} | {split} | {accuracy:.6f} | {balanced_accuracy:.6f} | {precision:.6f} | {recall:.6f} | {specificity:.6f} | {tp} | {fp} | {tn} | {fn} |".format(
                    rule=rule,
                    split=split,
                    **metrics,
                )
            )
    lines.extend(
        [
            "",
            "## 常见 reason codes",
            "",
            "| reason | count |",
            "| --- | ---: |",
        ]
    )
    for reason, count in evaluation["manual_review"]["common_reason_codes"].items():
        lines.append(f"| `{reason}` | {count} |")
    lines.extend(
        [
            "",
            "## 人工复核候选样本（前 80 条）",
            "",
            "| patient | split | label | grade | confidence | reason |",
            "| --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for row in review_rows[:80]:
        lines.append(
            f"| {row['patient_sample_id']} | {row['split']} | {row['label_group']} | {row['hb_proxy_grade']} | {row['hb_grade_confidence']} | {row['review_reason']} |"
        )
    lines.extend(
        [
            "",
            "## 限制",
            "",
            "- 当前没有人工 HB 标签，不能计算 weighted kappa 或 ordinal MAE。",
            "- patient outcome 标签只用于代理单调性和派生二分类检查，不等同于面瘫/面部不对称真值。",
            "- Grade VI 是“完全瘫痪候选代理”，必须结合人工复核，不能单独作为临床结论。",
            "- MediaPipe 等级差异是基于 478 点派生统计特征的探索性差异分析，不等同于人工 HB 分级依据。",
            "- 当前 all-images/no-gate 数据的质量门控大多为 `not_run`，质量可靠性主要反映 role 可用性和 V1.1 权重覆盖。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def component_source(component: str) -> str:
    return {
        "resting_symmetry_score": "front_score",
        "eye_closure_score": "eyes_closed_score",
        "brow_forehead_score": "forehead_wrinkle_score + frown_score",
        "smile_mouth_score": "smile_score + teeth_score",
        "gross_asymmetry_score": "v11_asymmetry_score + max role score",
        "movement_absence_score": "low dynamic expression strength * dynamic asymmetry",
        "quality_reliability_score": "included_roles_available + patient_weight_total",
    }.get(component, "")


def binary_grade(grade_num: int | None, threshold: int) -> str:
    if grade_num is None:
        return ""
    return "1" if grade_num >= threshold else "0"


def roman(value: int | None) -> str:
    return {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}.get(value or 0, "")


def weighted_mean(items: Iterable[tuple[float | None, float]]) -> float | None:
    weighted = 0.0
    total = 0.0
    for value, weight in items:
        if value is None:
            continue
        weighted += value * weight
        total += weight
    return clamp(weighted / total) if total else None


def parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fmt(value: float) -> str:
    return f"{value:.6f}"


def fmt_optional(value: Any) -> str:
    parsed = parse_float(value)
    return "" if parsed is None else fmt(parsed)


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if not values:
        return 0.0
    value_mean = mean(values)
    return math.sqrt(sum((value - value_mean) ** 2 for value in values) / len(values))


def median(values: list[float]) -> float:
    return quantile(values, 0.50)


def quantiles(values: list[float], qs: Iterable[float]) -> list[float]:
    return [quantile(values, q) for q in qs]


def quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    q = clamp(q)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def count_by(rows: Iterable[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get(key, ""))] += 1
    return dict(sorted(counts.items()))


def count_by_join(rows: Iterable[Mapping[str, Any]], keys: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts["/".join(str(row.get(key, "")) for key in keys)] += 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    main()
