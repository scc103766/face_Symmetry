from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .quality import QualityGate, QualityGateResult, infer_media_type


ROLE_ALIASES = {
    "front": "front",
    "frontal": "front",
    "frontal_image": "front",
    "front_image": "front",
    "front_contour": "front",
    "resting_front": "front",
    "\u6b63\u9762": "front",
    "\u6b63\u8138": "front",
    "\u6b63\u8138\u8f6e\u5ed3": "front",
    "\u6b63\u9762\uff08url\u5730\u5740\uff09": "front",
    "teeth": "teeth",
    "teeth_image": "teeth",
    "smile_teeth": "teeth",
    "smile": "teeth",
    "\u793a\u9f7f": "teeth",
    "\u9732\u9f7f": "teeth",
    "\u5fae\u7b11\u793a\u9f7f": "teeth",
    "\u793a\u9f7f\uff08url\u5730\u5740\uff09": "teeth",
}


@dataclass(frozen=True)
class InputManagementConfig:
    min_static_images: int = 2
    required_pair_roles: tuple[str, str] = ("front", "teeth")
    allow_review_quality: bool = True
    max_width_delta_ratio: float = 0.45
    max_height_delta_ratio: float = 0.45
    max_brightness_delta: float = 70.0
    max_face_short_side_delta_ratio: float = 0.55
    version: str = "input-management-v1-static-pair"


@dataclass(frozen=True)
class StaticImageInput:
    path: Path
    role: str
    image_id: str | None = None
    patient_id: str | None = None
    capture_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "StaticImageInput":
        return cls(
            path=Path(str(payload["path"])),
            role=str(payload.get("role", "")),
            image_id=none_if_empty(payload.get("image_id")),
            patient_id=none_if_empty(payload.get("patient_id")),
            capture_id=none_if_empty(payload.get("capture_id")),
        )


@dataclass(frozen=True)
class InputIssue:
    code: str
    severity: str
    message: str
    image_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        row = {"code": self.code, "severity": self.severity, "message": self.message}
        if self.image_id:
            row["image_id"] = self.image_id
        return row


@dataclass(frozen=True)
class ManagedImage:
    image_id: str
    path: str
    role: str
    canonical_role: str
    patient_id: str | None
    capture_id: str | None
    quality: QualityGateResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "path": self.path,
            "role": self.role,
            "canonical_role": self.canonical_role,
            "patient_id": self.patient_id,
            "capture_id": self.capture_id,
            "quality": self.quality.to_dict(),
        }


@dataclass(frozen=True)
class StaticInputSetResult:
    input_mode: str
    accepted: bool
    input_level: str
    issues: list[InputIssue]
    images: list[ManagedImage]
    pair_roles: tuple[str, str]
    comparable_metrics: dict[str, Any]
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_mode": self.input_mode,
            "accepted": self.accepted,
            "input_level": self.input_level,
            "issues": [issue.to_dict() for issue in self.issues],
            "images": [image.to_dict() for image in self.images],
            "pair_roles": list(self.pair_roles),
            "comparable_metrics": self.comparable_metrics,
            "version": self.version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


class StaticImageInputManager:
    def __init__(self, quality_gate: QualityGate | None = None, config: InputManagementConfig | None = None) -> None:
        self.quality_gate = quality_gate or QualityGate()
        self.config = config or InputManagementConfig()

    def validate(self, inputs: Iterable[StaticImageInput | Mapping[str, Any]]) -> StaticInputSetResult:
        normalized_inputs = [
            item if isinstance(item, StaticImageInput) else StaticImageInput.from_payload(item)
            for item in inputs
        ]
        issues: list[InputIssue] = []
        managed_images: list[ManagedImage] = []

        if len(normalized_inputs) < self.config.min_static_images:
            issues.append(
                InputIssue(
                    "insufficient_static_images",
                    "reject",
                    f"V1 至少需要 {self.config.min_static_images} 张静态图片，并且必须包含正脸图和露齿图。",
                )
            )

        patient_ids = {item.patient_id for item in normalized_inputs if item.patient_id}
        capture_ids = {item.capture_id for item in normalized_inputs if item.capture_id}
        if len(patient_ids) > 1:
            issues.append(InputIssue("mixed_patient_inputs", "reject", "同一组输入包含多个 patient_id，不能作为可比较样本。"))
        if len(capture_ids) > 1:
            issues.append(InputIssue("mixed_capture_inputs", "review", "同一组输入来自多个 capture_id，可比性下降。"))

        for index, item in enumerate(normalized_inputs, start=1):
            image_id = item.image_id or f"image_{index:02d}"
            role = item.role.strip()
            canonical_role = canonicalize_role(role)
            if infer_media_type(item.path) != "image":
                quality = self.quality_gate.evaluate_media(item.path, media_type=infer_media_type(item.path), role=canonical_role)
                issues.append(InputIssue("non_static_image_input", "reject", "输入管理 V1 只接受静态图片。", image_id=image_id))
            else:
                quality = self.quality_gate.evaluate_image(item.path, role=canonical_role)

            if quality.hard_reject:
                issues.append(InputIssue("image_quality_rejected", "reject", "单张图片未通过质量门控。", image_id=image_id))
            elif quality.quality_level == "review":
                severity = "review" if self.config.allow_review_quality else "reject"
                issues.append(InputIssue("image_quality_review", severity, "单张图片质量一般，应降权或人工复核。", image_id=image_id))

            managed_images.append(
                ManagedImage(
                    image_id=image_id,
                    path=item.path.resolve().as_posix(),
                    role=role,
                    canonical_role=canonical_role,
                    patient_id=item.patient_id,
                    capture_id=item.capture_id,
                    quality=quality,
                )
            )

        roles = [image.canonical_role for image in managed_images]
        for required_role in self.config.required_pair_roles:
            if required_role not in roles:
                issues.append(
                    InputIssue(
                        "missing_required_pair_role",
                        "reject",
                        f"缺少 V1 必需成对输入角色: {required_role}。",
                    )
                )

        comparable_metrics = self._check_comparability(managed_images, issues)
        hard_reject = any(issue.severity == "reject" for issue in issues)
        needs_review = any(issue.severity == "review" for issue in issues)
        input_level = "reject" if hard_reject else "review" if needs_review else "pass"
        return StaticInputSetResult(
            input_mode="static_image_set",
            accepted=input_level in {"pass", "review"},
            input_level=input_level,
            issues=issues,
            images=managed_images,
            pair_roles=self.config.required_pair_roles,
            comparable_metrics=comparable_metrics,
            version=self.config.version,
        )

    def _check_comparability(self, images: list[ManagedImage], issues: list[InputIssue]) -> dict[str, Any]:
        comparable = [image for image in images if image.quality.frame_results]
        role_to_image = {image.canonical_role: image for image in comparable}
        required = [role_to_image.get(role) for role in self.config.required_pair_roles]
        if any(image is None for image in required):
            return {}

        front, teeth = required
        assert front is not None and teeth is not None
        front_frame = front.quality.frame_results[0]
        teeth_frame = teeth.quality.frame_results[0]
        metrics: dict[str, Any] = {
            "front_image_id": front.image_id,
            "teeth_image_id": teeth.image_id,
            "width_delta_ratio": delta_ratio(front_frame.width, teeth_frame.width),
            "height_delta_ratio": delta_ratio(front_frame.height, teeth_frame.height),
            "brightness_delta": abs(
                front_frame.metrics.get("brightness_mean", 0.0) - teeth_frame.metrics.get("brightness_mean", 0.0)
            ),
        }
        if front_frame.face_box and teeth_frame.face_box:
            metrics["face_short_side_delta_ratio"] = delta_ratio(front_frame.face_box.short_side, teeth_frame.face_box.short_side)

        if metrics["width_delta_ratio"] > self.config.max_width_delta_ratio:
            issues.append(InputIssue("image_width_not_comparable", "review", "正脸图和露齿图宽度差异较大，可比性下降。"))
        if metrics["height_delta_ratio"] > self.config.max_height_delta_ratio:
            issues.append(InputIssue("image_height_not_comparable", "review", "正脸图和露齿图高度差异较大，可比性下降。"))
        if metrics["brightness_delta"] > self.config.max_brightness_delta:
            issues.append(InputIssue("image_lighting_not_comparable", "review", "正脸图和露齿图亮度差异较大，可比性下降。"))
        if metrics.get("face_short_side_delta_ratio", 0.0) > self.config.max_face_short_side_delta_ratio:
            issues.append(InputIssue("face_scale_not_comparable", "review", "正脸图和露齿图人脸尺度差异较大，可比性下降。"))
        return metrics


def canonicalize_role(role: str) -> str:
    normalized = re.sub(r"\s+", "_", role.strip().lower())
    return ROLE_ALIASES.get(normalized, normalized)


def delta_ratio(left: float, right: float) -> float:
    denominator = max(abs(left), abs(right), 1e-9)
    return abs(left - right) / denominator


def none_if_empty(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None
