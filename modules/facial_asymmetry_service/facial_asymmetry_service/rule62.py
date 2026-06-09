from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


OUTPUT_PREFIX = "62_stable_weighted_feature_disease_rule"
ROLE_SCOPES = {
    "all": {"front", "front_contour", "smile", "teeth", "smile_teeth", "eyes_closed", "eyes_right", "forehead_wrinkle", "frown", "unknown"},
    "mouth_dynamic": {"smile", "teeth", "smile_teeth"},
    "front_like": {"front", "front_contour"},
}
DEFAULT_RULE_DIR = Path("datasets") / "combined_disease_feature_candidates_20260529" / "metadata"


@dataclass(frozen=True)
class Rule62Feature:
    rule_id: str
    feature_name: str
    feature_type: str
    role_scope: str
    aggregation: str
    direction: str
    threshold: float
    feature_weight: float
    weight_grade: str
    threshold_rule: str
    role_scope_description: str


@dataclass(frozen=True)
class Rule62Config:
    features: list[Rule62Feature]
    score_threshold: float
    score_threshold_policy: str
    score_threshold_policy_description: str
    feature_weights_path: Path
    score_threshold_path: Path

    def summary(self) -> dict[str, Any]:
        return {
            "rule_name": "62_stable_weighted_feature_disease_rule",
            "feature_count": len(self.features),
            "score_threshold": round_float(self.score_threshold),
            "score_threshold_policy": self.score_threshold_policy,
            "score_threshold_policy_description": self.score_threshold_policy_description,
            "feature_weights_path": self.feature_weights_path.as_posix(),
            "score_threshold_path": self.score_threshold_path.as_posix(),
            "decision_rule": f"weighted_disease_score >= {self.score_threshold:.6f} => 人脸不对称性较高",
            "confidence_note": "face_asymmetry_confidence 使用 62 规则的加权证据分，不是临床诊断概率。",
        }


def load_rule62_config(rule_dir: Path) -> Rule62Config:
    feature_weights_path = rule_dir / f"{OUTPUT_PREFIX}_feature_weights.csv"
    score_threshold_path = rule_dir / f"{OUTPUT_PREFIX}_score_threshold.csv"
    if not feature_weights_path.exists():
        raise FileNotFoundError(f"missing 62 feature weights: {feature_weights_path}")
    if not score_threshold_path.exists():
        raise FileNotFoundError(f"missing 62 score threshold: {score_threshold_path}")

    with feature_weights_path.open("r", encoding="utf-8-sig", newline="") as handle:
        feature_rows = list(csv.DictReader(handle))
    features = [
        Rule62Feature(
            rule_id=str(row["rule_id"]),
            feature_name=row["feature_name"],
            feature_type=row["feature_type"],
            role_scope=row["role_scope"],
            aggregation=row["aggregation"],
            direction=row["direction"],
            threshold=float(row["threshold"]),
            feature_weight=float(row["feature_weight"]),
            weight_grade=row["weight_grade"],
            threshold_rule=row["threshold_rule"],
            role_scope_description=row.get("role_scope_description", ""),
        )
        for row in feature_rows
    ]

    with score_threshold_path.open("r", encoding="utf-8-sig", newline="") as handle:
        threshold_rows = list(csv.DictReader(handle))
    if not threshold_rows:
        raise ValueError(f"empty 62 score threshold file: {score_threshold_path}")
    threshold_row = threshold_rows[0]
    return Rule62Config(
        features=features,
        score_threshold=float(threshold_row["score_threshold"]),
        score_threshold_policy=threshold_row.get("threshold_policy", ""),
        score_threshold_policy_description=threshold_row.get("threshold_policy_description", ""),
        feature_weights_path=feature_weights_path,
        score_threshold_path=score_threshold_path,
    )


def evaluate_rule62(image_rows: list[Mapping[str, Any]], config: Rule62Config) -> dict[str, Any]:
    detected_rows = [
        row
        for row in image_rows
        if row.get("status") == "detected" and isinstance(row.get("features"), Mapping)
    ]
    attributions: list[dict[str, Any]] = []
    score = 0.0
    scored_weight = 0.0
    triggered_weight = 0.0

    for feature in config.features:
        scoped_rows = [
            row
            for row in detected_rows
            if role_matches(str(row.get("media_role") or "unknown"), feature.role_scope)
        ]
        values = feature_values(scoped_rows, feature.feature_name)
        value = aggregate_values(values, feature.aggregation) if values else None
        triggered = value is not None and value >= feature.threshold
        contribution = feature.feature_weight if triggered else 0.0
        if value is not None:
            scored_weight += feature.feature_weight
        if triggered:
            score += contribution
            triggered_weight += feature.feature_weight

        attributions.append(
            {
                "rule_id": feature.rule_id,
                "feature_name": feature.feature_name,
                "role_scope": feature.role_scope,
                "aggregation": feature.aggregation,
                "direction": feature.direction,
                "feature_value": None if value is None else round_float(value),
                "threshold": round_float(feature.threshold),
                "triggered": triggered,
                "feature_weight": round_float(feature.feature_weight),
                "weighted_contribution": round_float(contribution),
                "weight_grade": feature.weight_grade,
                "scope_image_count": len(scoped_rows),
                "feature_value_image_count": len(values),
                "supporting_image_values": [
                    {
                        "image_id": item["image_id"],
                        "media_role": item["media_role"],
                        "value": round_float(item["value"]),
                    }
                    for item in values[:50]
                ],
                "reason": attribution_reason(feature, value, triggered),
            }
        )

    triggered_rows = [row for row in attributions if row["triggered"]]
    missing_rows = [row for row in attributions if row["feature_value"] is None]
    predicted = bool(detected_rows) and score >= config.score_threshold
    status = "ok" if detected_rows else "no_valid_detection"
    output = "人脸不对称性较高" if predicted else "未达到高置信人脸不对称阈值"
    if not detected_rows:
        output = "无法判断"

    analysis = {
        "status": status,
        "face_asymmetry_output": output,
        "face_asymmetry_confidence": round_float(score),
        "confidence_percent": round_float(score * 100.0),
        "confidence_interpretation": "62 规则的加权证据分，范围 0-1；不是临床诊断概率。",
        "weighted_disease_score": round_float(score),
        "score_threshold": round_float(config.score_threshold),
        "score_margin": round_float(score - config.score_threshold),
        "predicted_high_asymmetry": predicted,
        "feature_count": len(config.features),
        "triggered_feature_count": len(triggered_rows),
        "missing_feature_count": len(missing_rows),
        "scored_weight": round_float(scored_weight),
        "triggered_weight": round_float(triggered_weight),
        "detected_image_count": len(detected_rows),
        "role_counts": role_counts(detected_rows),
        "reason_description": decision_reason(score, config.score_threshold, triggered_rows, missing_rows, bool(detected_rows)),
        "top_triggered_features": sort_attributions(triggered_rows),
        "non_triggered_available_features": sort_attributions(
            [row for row in attributions if row["feature_value"] is not None and not row["triggered"]]
        ),
        "missing_features": sort_attributions(missing_rows),
        "feature_attributions": sort_attributions(attributions),
    }
    return analysis


def feature_values(scoped_rows: list[Mapping[str, Any]], feature_name: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for row in scoped_rows:
        features = row.get("features")
        if not isinstance(features, Mapping) or feature_name not in features:
            continue
        value = to_float(features.get(feature_name))
        if value is None:
            continue
        values.append(
            {
                "image_id": str(row.get("image_id") or ""),
                "media_role": str(row.get("media_role") or "unknown"),
                "value": value,
            }
        )
    return values


def aggregate_values(values: list[Mapping[str, Any]], aggregation: str) -> float:
    numeric = sorted(float(item["value"]) for item in values)
    if aggregation == "max":
        return max(numeric)
    if aggregation == "mean":
        return sum(numeric) / len(numeric)
    if aggregation == "median":
        index = len(numeric) // 2
        if len(numeric) % 2:
            return numeric[index]
        return (numeric[index - 1] + numeric[index]) / 2.0
    raise ValueError(f"unsupported aggregation: {aggregation}")


def role_matches(media_role: str, role_scope: str) -> bool:
    role = normalize_role(media_role)
    if role_scope == "all":
        return True
    return role in ROLE_SCOPES.get(role_scope, set())


def normalize_role(role: str) -> str:
    return role.strip().lower().replace("-", "_").replace(" ", "_") or "unknown"


def role_counts(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = normalize_role(str(row.get("media_role") or "unknown"))
        counts[role] = counts.get(role, 0) + 1
    return dict(sorted(counts.items()))


def sort_attributions(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in sorted(
            rows,
            key=lambda item: (
                -float(item.get("weighted_contribution") or 0.0),
                -float(item.get("feature_weight") or 0.0),
                str(item.get("rule_id") or ""),
            ),
        )
    ]


def attribution_reason(feature: Rule62Feature, value: float | None, triggered: bool) -> str:
    if value is None:
        return (
            f"未得到 {feature.role_scope}/{feature.aggregation} 范围内的 {feature.feature_name}；"
            "通常是输入 role 缺失、图片未检测到人脸，或 MediaPipe 输出不完整。"
        )
    relation = ">=" if triggered else "<"
    conclusion = "计入人脸不对称证据" if triggered else "未计入人脸不对称证据"
    return (
        f"{feature.feature_name}={value:.6f} {relation} 阈值 {feature.threshold:.6f}，"
        f"权重 {feature.feature_weight:.6f}，{conclusion}。"
    )


def decision_reason(
    score: float,
    threshold: float,
    triggered_rows: list[Mapping[str, Any]],
    missing_rows: list[Mapping[str, Any]],
    has_detection: bool,
) -> str:
    if not has_detection:
        return "没有可用的人脸关键点检测结果，无法计算 62 规则的人脸不对称置信度。"
    top = sorted(triggered_rows, key=lambda row: float(row["feature_weight"]), reverse=True)[:5]
    top_text = "；".join(
        f"#{row['rule_id']} {row['feature_name']}={row['feature_value']}>=阈值{row['threshold']} 权重{row['feature_weight']}"
        for row in top
    )
    if score >= threshold:
        return (
            f"加权不对称置信度 {score:.6f} >= 阈值 {threshold:.6f}；"
            f"触发 {len(triggered_rows)}/21 个稳定特征。主要原因：{top_text}"
        )
    suffix = f"主要已触发特征：{top_text}" if top_text else "没有触发足够的 62 稳定特征。"
    if missing_rows:
        suffix += f" 缺失 {len(missing_rows)} 个特征，请检查是否提供了 smile_teeth/smile/teeth 等规范 role 图片。"
    return (
        f"加权不对称置信度 {score:.6f} < 阈值 {threshold:.6f}；"
        f"仅触发 {len(triggered_rows)}/21 个稳定特征。{suffix}"
    )


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def round_float(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def input_format_spec() -> dict[str, Any]:
    return {
        "accepted_files": [".jpg", ".jpeg", ".png"],
        "analysis_unit": "一次服务调用中的一张或多张图片会被视为同一名受试者/同一次采集。",
        "minimum_image_count": 2,
        "maximum_image_count": 10,
        "recommended_image_count": "2-4",
        "required_roles": [],
        "recommended_roles_ranked": [
            {
                "rank": 1,
                "role": "smile_teeth",
                "aliases": ["smile", "teeth"],
                "description": "露齿微笑/微笑/示齿图片；62 规则中 10/21 个患者更高稳定特征来自 mouth_dynamic scope。",
                "evidence_scope": "mouth_dynamic",
                "feature_coverage": "10/21",
            },
            {
                "rank": 2,
                "role": "front_contour",
                "aliases": ["front"],
                "description": "正脸/面部轮廓静态图；可支持 all scope 的整体面部几何和左右差证据。",
                "evidence_scope": "all",
                "feature_coverage": "11/21",
            },
            {
                "rank": 3,
                "role": "eyes_right",
                "aliases": ["eyes_closed", "forehead_wrinkle", "frown"],
                "description": "其他清晰单人脸动作图；不强制，但可增加 all scope 聚合证据。",
                "evidence_scope": "all",
                "feature_coverage": "11/21",
            },
        ],
        "minimum_required_roles": [],
        "recommended_extra_roles": [],
        "required_keypoint_output": "图片必须能被 MediaPipe Face Landmarker 检出人脸，并输出 478 个 raw landmarks、blendshapes 和 facial_transformation_matrixes。",
        "recommended_roles": [
            "优先 smile_teeth 或旧数据 smile/teeth：露齿微笑/口部动态图片，是 62 规则中 mouth_dynamic 患病更高特征的主要来源。",
            "其次 front 或 front_contour：正脸/面部轮廓静态图，可支持 all scope 的整体面部几何证据。",
            "可补充 eyes_right、eyes_closed、forehead_wrinkle、frown 或其他清晰单人脸图片；动作不强制限制，但未知 role 只能参与 all scope。",
        ],
        "role_assignment": "服务可从文件名识别 front_contour、smile_teeth、front、smile、teeth、eyes_right、eyes_closed、forehead_wrinkle、frown；不能从文件名识别时请用 --role 或 --image-role 指定。",
        "minimum_practical_input": "最少 2 张、最多 10 张。动作不强制限制；但如果没有 smile_teeth/smile/teeth，mouth_dynamic 的 10 个稳定特征会缺失，置信度会偏保守。",
        "clinical_warning": "该输出是基于当前数据集弱标签得到的人脸不对称证据，不应作为临床诊断结论。",
    }
