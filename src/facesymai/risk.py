from __future__ import annotations

from dataclasses import dataclass, field

from .features import FacialSymmetryFeatureExtractor
from .geometry import clamp, sigmoid
from .schemas import AnalysisResult, ComponentSymmetryAttribute, Contribution, FaceLandmarks, FeatureResult, SymmetrySummary


DISCLAIMER = (
    "本结果仅用于脑卒中/面瘫预警的辅助解释与风险提示，不能替代临床诊断。"
    "如出现突发面瘫、肢体无力、言语异常、意识改变等症状，应立即按急救流程处理。"
)


@dataclass(frozen=True)
class RiskModelConfig:
    intercept: float = -2.2
    quality_gate: float = 0.45
    side_threshold: float = 0.08
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "global_mirror_error": 1.5,
            "midline_deviation": 1.0,
            "mouth_corner_vertical_asymmetry": 2.4,
            "mouth_width_asymmetry": 1.4,
            "lip_midline_deviation": 1.2,
            "eye_aperture_asymmetry": 1.6,
            "eye_corner_height_asymmetry": 0.9,
            "brow_vertical_asymmetry": 1.2,
            "brow_outer_vertical_asymmetry": 0.8,
            "contour_mirror_error": 0.8,
            "jaw_width_asymmetry": 0.7,
        }
    )
    overall_weights: dict[str, float] = field(
        default_factory=lambda: {
            "mouth": 0.30,
            "global_mirror": 0.20,
            "midline": 0.18,
            "eye": 0.12,
            "brow": 0.10,
            "contour": 0.10,
        }
    )
    component_feature_weights: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            "mouth": {
                "mouth_corner_vertical_asymmetry": 0.45,
                "mouth_width_asymmetry": 0.30,
                "lip_midline_deviation": 0.25,
            },
            "eye": {
                "eye_aperture_asymmetry": 0.70,
                "eye_corner_height_asymmetry": 0.30,
            },
            "brow": {
                "brow_vertical_asymmetry": 0.60,
                "brow_outer_vertical_asymmetry": 0.40,
            },
            "midline": {
                "midline_deviation": 0.75,
                "lip_midline_deviation": 0.25,
            },
            "contour": {
                "contour_mirror_error": 0.65,
                "jaw_width_asymmetry": 0.35,
            },
        }
    )


class FacialSymmetryRiskAnalyzer:
    def __init__(
        self,
        feature_extractor: FacialSymmetryFeatureExtractor | None = None,
        config: RiskModelConfig | None = None,
    ) -> None:
        self.feature_extractor = feature_extractor or FacialSymmetryFeatureExtractor()
        self.config = config or RiskModelConfig()

    def analyze(self, face: FaceLandmarks) -> AnalysisResult:
        features, input_quality, warnings = self.feature_extractor.extract(face)
        feature_by_name = {feature.name: feature for feature in features}
        attributes = self._component_attributes(feature_by_name, input_quality)
        symmetry = self._symmetry_summary(feature_by_name, attributes, input_quality)

        logit = self.config.intercept
        contributions: list[Contribution] = []
        for feature in features:
            weight = self.config.weights.get(feature.name, 0.0)
            contribution = weight * feature.severity
            logit += contribution
            contributions.append(
                Contribution(
                    feature=feature.name,
                    severity=feature.severity,
                    weight=weight,
                    contribution=contribution,
                    side=feature.side,
                    explanation=feature.explanation,
                    region=self._region_for_feature(feature.name),
                )
            )

        raw_score = sigmoid(logit)
        advisory_confidence = clamp(raw_score * input_quality)
        if input_quality < self.config.quality_gate:
            warnings.append(
                f"输入质量 {input_quality:.2f} 低于建议阈值 {self.config.quality_gate:.2f}，"
                "结果只能作为低可信参考"
            )

        top_contributions = [
            item
            for item in sorted(contributions, key=lambda item: item.contribution, reverse=True)
            if item.contribution > 0
        ][:5]

        return AnalysisResult(
            advisory_confidence=advisory_confidence,
            raw_score=raw_score,
            risk_level=self._risk_level(advisory_confidence),
            input_quality=input_quality,
            symmetry=symmetry,
            attributes=attributes,
            features=features,
            top_contributions=top_contributions,
            warnings=warnings,
            recommended_action=self._recommended_action(advisory_confidence, input_quality),
            disclaimer=DISCLAIMER,
        )

    def _component_attributes(
        self,
        feature_by_name: dict[str, FeatureResult],
        input_quality: float,
    ) -> dict[str, ComponentSymmetryAttribute]:
        attributes: dict[str, ComponentSymmetryAttribute] = {}
        for component, feature_weights in self.config.component_feature_weights.items():
            available = {
                name: feature_by_name[name]
                for name in feature_weights
                if name in feature_by_name
            }
            weight_total = sum(feature_weights[name] for name in available)
            if weight_total > 0:
                score = sum(feature_weights[name] * available[name].severity for name in available) / weight_total
            else:
                score = 0.0
            confidence = input_quality * (len(available) / max(len(feature_weights), 1))
            attributes[component] = ComponentSymmetryAttribute(
                name=component,
                score=clamp(score),
                symmetry_score=100.0 * (1.0 - clamp(score)),
                side=self._component_side(available.values()),
                confidence=clamp(confidence),
                features={name: available[name].value for name in available},
                feature_severities={name: available[name].severity for name in available},
            )
        return attributes

    def _symmetry_summary(
        self,
        feature_by_name: dict[str, FeatureResult],
        attributes: dict[str, ComponentSymmetryAttribute],
        input_quality: float,
    ) -> SymmetrySummary:
        weighted = 0.0
        total_weight = 0.0
        for component, weight in self.config.overall_weights.items():
            if component == "global_mirror":
                feature = feature_by_name.get("global_mirror_error")
                severity = feature.severity if feature else 0.0
            else:
                severity = attributes[component].score if component in attributes else 0.0
            weighted += weight * severity
            total_weight += weight
        overall_severity = clamp(weighted / total_weight if total_weight else 0.0)
        return SymmetrySummary(
            overall_symmetry_score=100.0 * (1.0 - overall_severity),
            overall_asymmetry_severity=overall_severity,
            affected_side=self._overall_side(attributes),
            confidence=input_quality,
        )

    def _component_side(self, features: object) -> str:
        side_scores = {"left": 0.0, "right": 0.0}
        for feature in features:
            if not isinstance(feature, FeatureResult):
                continue
            side = self._normalized_side(feature.side)
            if side in side_scores:
                side_scores[side] += feature.severity
        return self._side_from_scores(side_scores)

    def _overall_side(self, attributes: dict[str, ComponentSymmetryAttribute]) -> str:
        side_scores = {"left": 0.0, "right": 0.0}
        for component, attribute in attributes.items():
            side = attribute.side
            weight = self.config.overall_weights.get(component, 0.0)
            if side in side_scores:
                side_scores[side] += weight * attribute.score
        return self._side_from_scores(side_scores)

    def _side_from_scores(self, side_scores: dict[str, float]) -> str:
        left = side_scores["left"]
        right = side_scores["right"]
        if left >= self.config.side_threshold and right >= self.config.side_threshold and abs(left - right) < self.config.side_threshold:
            return "bilateral"
        if left - right >= self.config.side_threshold:
            return "left"
        if right - left >= self.config.side_threshold:
            return "right"
        return "uncertain"

    def _normalized_side(self, side: str | None) -> str | None:
        if side is None:
            return None
        if side.startswith("left_"):
            return "left"
        if side.startswith("right_"):
            return "right"
        return None

    def _region_for_feature(self, feature_name: str) -> str | None:
        for component, feature_weights in self.config.component_feature_weights.items():
            if feature_name in feature_weights:
                return component
        if feature_name == "global_mirror_error":
            return "global_mirror"
        return None

    def _risk_level(self, confidence: float) -> str:
        if confidence >= 0.75:
            return "high"
        if confidence >= 0.50:
            return "elevated"
        if confidence >= 0.25:
            return "watch"
        return "low"

    def _recommended_action(self, confidence: float, input_quality: float) -> str:
        if input_quality < self.config.quality_gate:
            return "建议重新采集正脸、光照稳定、无遮挡的人脸图像或视频后再评估。"
        if confidence >= 0.75:
            return "建议将该结果作为强预警解释项，并结合 FAST/BE-FAST、肢体、言语和病史信息立即复核。"
        if confidence >= 0.50:
            return "建议作为脑卒中预警参考信号，结合其他症状与业务规则进行人工或临床复核。"
        if confidence >= 0.25:
            return "存在轻度不对称信号，建议结合历史基线、重采样和其他预警特征判断。"
        return "当前未见明显面部对称性异常信号；仍需结合其他脑卒中预警信息。"
