from __future__ import annotations

from dataclasses import dataclass, field

from .geometry import Line2D, euclidean, ramp
from .schemas import FaceLandmarks, FeatureResult, Landmark


@dataclass(frozen=True)
class SymmetryFeatureConfig:
    midline_top: str = "nose_bridge"
    midline_bottom: str = "chin"
    midline_fit_points: tuple[str, ...] = (
        "nose_bridge",
        "nose_tip",
        "chin",
    )
    scale_left: str = "left_eye_outer"
    scale_right: str = "right_eye_outer"
    min_landmark_confidence: float = 0.5
    mirror_pairs: tuple[tuple[str, str, str], ...] = (
        ("left_eye_outer", "right_eye_outer", "eye_outer"),
        ("left_eye_inner", "right_eye_inner", "eye_inner"),
        ("left_brow_inner", "right_brow_inner", "brow_inner"),
        ("left_brow_outer", "right_brow_outer", "brow_outer"),
        ("left_mouth_corner", "right_mouth_corner", "mouth_corner"),
        ("left_nostril", "right_nostril", "nostril"),
        ("left_cheek", "right_cheek", "cheek"),
        ("left_jaw", "right_jaw", "jaw"),
    )
    midline_points: tuple[str, ...] = (
        "nose_tip",
        "upper_lip_center",
        "lower_lip_center",
    )
    feature_thresholds: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "global_mirror_error": (0.025, 0.12),
            "midline_deviation": (0.015, 0.08),
            "mouth_corner_vertical_asymmetry": (0.015, 0.09),
            "mouth_width_asymmetry": (0.025, 0.12),
            "lip_midline_deviation": (0.015, 0.08),
            "eye_aperture_asymmetry": (0.08, 0.40),
            "eye_corner_height_asymmetry": (0.015, 0.08),
            "brow_vertical_asymmetry": (0.020, 0.10),
            "brow_outer_vertical_asymmetry": (0.020, 0.10),
            "contour_mirror_error": (0.025, 0.14),
            "jaw_width_asymmetry": (0.025, 0.14),
        }
    )


class FacialSymmetryFeatureExtractor:
    def __init__(self, config: SymmetryFeatureConfig | None = None) -> None:
        self.config = config or SymmetryFeatureConfig()

    def extract(self, face: FaceLandmarks) -> tuple[list[FeatureResult], float, list[str]]:
        warnings: list[str] = []
        normalized_face, midline, scale = self._standardized_geometry(face)
        if scale <= 1e-9:
            raise ValueError("face scale is degenerate")

        features: list[FeatureResult] = []
        features.append(self._global_mirror_error(normalized_face, midline, scale))
        midline_feature = self._midline_deviation(normalized_face, midline, scale)
        if midline_feature:
            features.append(midline_feature)
        mouth_feature = self._vertical_pair_feature(
            normalized_face,
            midline,
            scale,
            "left_mouth_corner",
            "right_mouth_corner",
            "mouth_corner_vertical_asymmetry",
            "嘴角上下位置不对称，可能体现口角下垂或表情控制差异。",
        )
        if mouth_feature:
            features.append(mouth_feature)
        mouth_width_feature = self._distance_to_midline_pair_feature(
            normalized_face,
            midline,
            scale,
            "left_mouth_corner",
            "right_mouth_corner",
            "mouth_width_asymmetry",
            "左右口角到面部中线的横向距离不对称，提示口部牵拉或口型偏移。",
        )
        if mouth_width_feature:
            features.append(mouth_width_feature)
        lip_midline_feature = self._point_midline_feature(
            normalized_face,
            midline,
            scale,
            ("upper_lip_center", "lower_lip_center"),
            "lip_midline_deviation",
            "上下唇中点偏离鼻面中线，提示口部中心线偏移。",
        )
        if lip_midline_feature:
            features.append(lip_midline_feature)
        brow_feature = self._vertical_pair_feature(
            normalized_face,
            midline,
            scale,
            "left_brow_inner",
            "right_brow_inner",
            "brow_vertical_asymmetry",
            "眉部高度不对称，可能提示额面部肌群控制差异。",
        )
        if brow_feature:
            features.append(brow_feature)
        brow_outer_feature = self._vertical_pair_feature(
            normalized_face,
            midline,
            scale,
            "left_brow_outer",
            "right_brow_outer",
            "brow_outer_vertical_asymmetry",
            "眉尾高度不对称，补充眉部区域左右差异。",
        )
        if brow_outer_feature:
            features.append(brow_outer_feature)
        eye_feature = self._eye_aperture_feature(normalized_face)
        if eye_feature:
            features.append(eye_feature)
        eye_corner_feature = self._vertical_pair_feature(
            normalized_face,
            midline,
            scale,
            "left_eye_outer",
            "right_eye_outer",
            "eye_corner_height_asymmetry",
            "左右外眼角高度不对称，补充眼部静态对称性判断。",
        )
        if eye_corner_feature:
            features.append(eye_corner_feature)
        contour_feature = self._regional_mirror_error(
            normalized_face,
            midline,
            scale,
            (("left_cheek", "right_cheek"), ("left_jaw", "right_jaw")),
            "contour_mirror_error",
            "脸颊和下颌轮廓相对面部中线的镜像误差。",
        )
        if contour_feature:
            features.append(contour_feature)
        jaw_width_feature = self._distance_to_midline_pair_feature(
            normalized_face,
            midline,
            scale,
            "left_jaw",
            "right_jaw",
            "jaw_width_asymmetry",
            "左右下颌到面部中线的距离不对称，提示面部轮廓偏斜。",
        )
        if jaw_width_feature:
            features.append(jaw_width_feature)

        quality = self._quality(face, warnings)
        return features, quality, warnings

    def _midline(self, face: FaceLandmarks) -> Line2D:
        return Line2D.through(
            face.require(self.config.midline_top),
            face.require(self.config.midline_bottom),
        )

    def _scale(self, face: FaceLandmarks) -> float:
        return euclidean(face.require(self.config.scale_left), face.require(self.config.scale_right))

    def _standardized_geometry(self, face: FaceLandmarks) -> tuple[FaceLandmarks, Line2D, float]:
        original_midline = self._fitted_midline(face)
        original_scale = self._scale(face)
        if original_scale <= 1e-9:
            raise ValueError("face scale is degenerate")

        normalized = {
            name: Landmark(
                x=original_midline.signed_distance(point) / original_scale,
                y=original_midline.along(point) / original_scale,
                confidence=point.confidence,
            )
            for name, point in face.landmarks.items()
        }
        normalized_midline = Line2D.through(Landmark(0.0, 0.0), Landmark(0.0, 1.0))
        return FaceLandmarks(landmarks=normalized, pose=face.pose, image_id=face.image_id), normalized_midline, 1.0

    def _fitted_midline(self, face: FaceLandmarks) -> Line2D:
        top = face.require(self.config.midline_top)
        bottom = face.require(self.config.midline_bottom)
        points = [point for name in self.config.midline_fit_points if (point := face.get(name)) is not None]
        return Line2D.fit(points, orient_top=top, orient_bottom=bottom)

    def _severity(self, feature_name: str, value: float) -> float:
        low, high = self.config.feature_thresholds[feature_name]
        return ramp(value, low, high)

    def _global_mirror_error(
        self,
        face: FaceLandmarks,
        midline: Line2D,
        scale: float,
    ) -> FeatureResult:
        errors: list[float] = []
        missing: list[str] = []
        for left_name, right_name, _label in self.config.mirror_pairs:
            left = face.get(left_name)
            right = face.get(right_name)
            if left is None or right is None:
                missing.extend(name for name, point in [(left_name, left), (right_name, right)] if point is None)
                continue
            reflected_right = midline.reflect(right)
            errors.append(euclidean(left, reflected_right) / scale)
        if not errors:
            raise ValueError("no usable left/right landmark pairs")
        value = sum(errors) / len(errors)
        return FeatureResult(
            name="global_mirror_error",
            value=value,
            severity=self._severity("global_mirror_error", value),
            side=None,
            explanation="左右成对关键点相对面部中线的镜像误差。",
        )

    def _midline_deviation(
        self,
        face: FaceLandmarks,
        midline: Line2D,
        scale: float,
    ) -> FeatureResult | None:
        values: list[float] = []
        for name in self.config.midline_points:
            point = face.get(name)
            if point is not None:
                values.append(abs(midline.signed_distance(point)) / scale)
        if not values:
            return None
        value = sum(values) / len(values)
        return FeatureResult(
            name="midline_deviation",
            value=value,
            severity=self._severity("midline_deviation", value),
            side=None,
            explanation="鼻尖、唇中点等中线结构相对鼻梁-下巴中线的偏移。",
        )

    def _vertical_pair_feature(
        self,
        face: FaceLandmarks,
        midline: Line2D,
        scale: float,
        left_name: str,
        right_name: str,
        feature_name: str,
        explanation: str,
    ) -> FeatureResult | None:
        left = face.get(left_name)
        right = face.get(right_name)
        if left is None or right is None:
            return None
        left_along = midline.along(left)
        right_along = midline.along(right)
        signed = (left_along - right_along) / scale
        value = abs(signed)
        side = None if value < 1e-9 else ("left_lower" if signed > 0 else "right_lower")
        return FeatureResult(
            name=feature_name,
            value=value,
            severity=self._severity(feature_name, value),
            side=side,
            explanation=explanation,
        )

    def _distance_to_midline_pair_feature(
        self,
        face: FaceLandmarks,
        midline: Line2D,
        scale: float,
        left_name: str,
        right_name: str,
        feature_name: str,
        explanation: str,
    ) -> FeatureResult | None:
        left = face.get(left_name)
        right = face.get(right_name)
        if left is None or right is None:
            return None
        left_distance = abs(midline.signed_distance(left))
        right_distance = abs(midline.signed_distance(right))
        signed = (left_distance - right_distance) / scale
        value = abs(signed)
        side = None if value < 1e-9 else ("left_narrower" if signed < 0 else "right_narrower")
        return FeatureResult(
            name=feature_name,
            value=value,
            severity=self._severity(feature_name, value),
            side=side,
            explanation=explanation,
        )

    def _point_midline_feature(
        self,
        face: FaceLandmarks,
        midline: Line2D,
        scale: float,
        point_names: tuple[str, ...],
        feature_name: str,
        explanation: str,
    ) -> FeatureResult | None:
        signed_values: list[float] = []
        for name in point_names:
            point = face.get(name)
            if point is not None:
                signed_values.append(midline.signed_distance(point) / scale)
        if not signed_values:
            return None
        signed = sum(signed_values) / len(signed_values)
        value = abs(signed)
        side = None if value < 1e-9 else ("left_shift" if signed > 0 else "right_shift")
        return FeatureResult(
            name=feature_name,
            value=value,
            severity=self._severity(feature_name, value),
            side=side,
            explanation=explanation,
        )

    def _regional_mirror_error(
        self,
        face: FaceLandmarks,
        midline: Line2D,
        scale: float,
        pairs: tuple[tuple[str, str], ...],
        feature_name: str,
        explanation: str,
    ) -> FeatureResult | None:
        errors: list[float] = []
        width_differences: list[float] = []
        for left_name, right_name in pairs:
            left = face.get(left_name)
            right = face.get(right_name)
            if left is None or right is None:
                continue
            reflected_right = midline.reflect(right)
            errors.append(euclidean(left, reflected_right) / scale)
            width_differences.append((abs(midline.signed_distance(left)) - abs(midline.signed_distance(right))) / scale)
        if not errors:
            return None
        value = sum(errors) / len(errors)
        signed = sum(width_differences) / len(width_differences) if width_differences else 0.0
        side = None if abs(signed) < 1e-9 else ("left_narrower" if signed < 0 else "right_narrower")
        return FeatureResult(
            name=feature_name,
            value=value,
            severity=self._severity(feature_name, value),
            side=side,
            explanation=explanation,
        )

    def _eye_aperture_feature(self, face: FaceLandmarks) -> FeatureResult | None:
        left_upper = face.get("left_eye_upper")
        left_lower = face.get("left_eye_lower")
        right_upper = face.get("right_eye_upper")
        right_lower = face.get("right_eye_lower")
        if None in (left_upper, left_lower, right_upper, right_lower):
            return None
        assert left_upper and left_lower and right_upper and right_lower
        left_open = euclidean(left_upper, left_lower)
        right_open = euclidean(right_upper, right_lower)
        denom = max(left_open, right_open, 1e-9)
        signed = (left_open - right_open) / denom
        value = abs(signed)
        side = None if value < 1e-9 else ("left_smaller" if signed < 0 else "right_smaller")
        return FeatureResult(
            name="eye_aperture_asymmetry",
            value=value,
            severity=self._severity("eye_aperture_asymmetry", value),
            side=side,
            explanation="左右眼裂开合程度不对称，可能提示眼轮匝肌或闭眼控制差异。",
        )

    def _quality(self, face: FaceLandmarks, warnings: list[str]) -> float:
        confidences = [point.confidence for point in face.landmarks.values()]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        low_conf_count = sum(1 for value in confidences if value < self.config.min_landmark_confidence)
        if low_conf_count:
            warnings.append(f"{low_conf_count} 个关键点置信度低于 {self.config.min_landmark_confidence:.2f}")

        pose_penalty = 0.0
        if abs(face.pose.yaw) > 15:
            warnings.append("头部 yaw 角度较大，正脸对称性评分可信度下降")
            pose_penalty += min((abs(face.pose.yaw) - 15) / 30, 0.35)
        if abs(face.pose.pitch) > 15:
            warnings.append("头部 pitch 角度较大，局部特征评分可信度下降")
            pose_penalty += min((abs(face.pose.pitch) - 15) / 35, 0.25)
        if abs(face.pose.roll) > 20:
            warnings.append("头部 roll 角度较大，建议先进行姿态校正")
            pose_penalty += min((abs(face.pose.roll) - 20) / 40, 0.25)

        return max(0.0, min(1.0, avg_confidence - pose_penalty))
