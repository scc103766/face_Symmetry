from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Landmark:
    x: float
    y: float
    confidence: float = 1.0

    @classmethod
    def from_value(cls, value: Any) -> "Landmark":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(
                x=float(value["x"]),
                y=float(value["y"]),
                confidence=float(value.get("confidence", value.get("score", 1.0))),
            )
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            confidence = float(value[2]) if len(value) >= 3 else 1.0
            return cls(x=float(value[0]), y=float(value[1]), confidence=confidence)
        raise TypeError(f"Unsupported landmark value: {value!r}")

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "confidence": self.confidence}


@dataclass(frozen=True)
class Pose:
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0

    @classmethod
    def from_value(cls, value: Any) -> "Pose":
        if value is None:
            return cls()
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(
                yaw=float(value.get("yaw", 0.0)),
                pitch=float(value.get("pitch", 0.0)),
                roll=float(value.get("roll", 0.0)),
            )
        raise TypeError(f"Unsupported pose value: {value!r}")

    def to_dict(self) -> dict[str, float]:
        return {"yaw": self.yaw, "pitch": self.pitch, "roll": self.roll}


@dataclass(frozen=True)
class FaceLandmarks:
    landmarks: Mapping[str, Landmark]
    pose: Pose = field(default_factory=Pose)
    image_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "FaceLandmarks":
        raw_landmarks = payload.get("landmarks", payload)
        if not isinstance(raw_landmarks, Mapping):
            raise TypeError("landmarks must be a mapping")
        return cls(
            landmarks={str(k): Landmark.from_value(v) for k, v in raw_landmarks.items()},
            pose=Pose.from_value(payload.get("pose")),
            image_id=payload.get("image_id"),
        )

    def get(self, name: str) -> Landmark | None:
        return self.landmarks.get(name)

    def require(self, name: str) -> Landmark:
        point = self.get(name)
        if point is None:
            raise MissingLandmarkError(name)
        return point


class MissingLandmarkError(ValueError):
    def __init__(self, landmark_name: str) -> None:
        super().__init__(f"missing required landmark: {landmark_name}")
        self.landmark_name = landmark_name


@dataclass(frozen=True)
class FeatureResult:
    name: str
    value: float
    severity: float
    side: str | None
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "severity": self.severity,
            "side": self.side,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class Contribution:
    feature: str
    severity: float
    weight: float
    contribution: float
    side: str | None
    explanation: str
    region: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "feature": self.feature,
            "severity": self.severity,
            "weight": self.weight,
            "contribution": self.contribution,
            "side": self.side,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class SymmetrySummary:
    overall_symmetry_score: float
    overall_asymmetry_severity: float
    affected_side: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_symmetry_score": self.overall_symmetry_score,
            "overall_asymmetry_severity": self.overall_asymmetry_severity,
            "affected_side": self.affected_side,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ComponentSymmetryAttribute:
    name: str
    score: float
    symmetry_score: float
    side: str
    confidence: float
    features: Mapping[str, float]
    feature_severities: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "symmetry_score": self.symmetry_score,
            "side": self.side,
            "confidence": self.confidence,
            "features": dict(self.features),
            "feature_severities": dict(self.feature_severities),
        }


@dataclass(frozen=True)
class AnalysisResult:
    advisory_confidence: float
    raw_score: float
    risk_level: str
    input_quality: float
    symmetry: SymmetrySummary
    attributes: Mapping[str, ComponentSymmetryAttribute]
    features: list[FeatureResult]
    top_contributions: list[Contribution]
    warnings: list[str]
    recommended_action: str
    disclaimer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisory_confidence": self.advisory_confidence,
            "raw_score": self.raw_score,
            "risk_level": self.risk_level,
            "input_quality": self.input_quality,
            "symmetry": self.symmetry.to_dict(),
            "attributes": {key: value.to_dict() for key, value in self.attributes.items()},
            "features": [item.to_dict() for item in self.features],
            "top_contributions": [item.to_dict() for item in self.top_contributions],
            "stroke_warning_auxiliary": {
                "warning_score": self.advisory_confidence,
                "level": self.risk_level,
                "medical_boundary": "auxiliary_warning_not_diagnosis",
            },
            "warnings": list(self.warnings),
            "recommended_action": self.recommended_action,
            "disclaimer": self.disclaimer,
        }
