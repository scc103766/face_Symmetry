from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from facesymai import FaceLandmarks, FacialSymmetryRiskAnalyzer, Landmark


ROOT = Path(__file__).resolve().parents[1]


def load_face(name: str) -> FaceLandmarks:
    payload = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
    return FaceLandmarks.from_payload(payload)


def test_symmetric_face_scores_low() -> None:
    result = FacialSymmetryRiskAnalyzer().analyze(load_face("landmarks_symmetric.json"))

    assert result.risk_level == "low"
    assert result.advisory_confidence < 0.25
    assert result.input_quality > 0.9
    assert result.symmetry.overall_symmetry_score > 90
    assert set(result.attributes) == {"mouth", "eye", "brow", "midline", "contour"}
    assert all(0 <= item.score <= 1 for item in result.attributes.values())


def test_mouth_droop_face_scores_higher_than_symmetric_face() -> None:
    analyzer = FacialSymmetryRiskAnalyzer()
    symmetric = analyzer.analyze(load_face("landmarks_symmetric.json"))
    droop = analyzer.analyze(load_face("landmarks_mouth_droop.json"))

    assert droop.advisory_confidence > symmetric.advisory_confidence
    assert droop.symmetry.overall_symmetry_score < symmetric.symmetry.overall_symmetry_score
    assert droop.attributes["mouth"].score > symmetric.attributes["mouth"].score
    assert droop.attributes["mouth"].side == "left"
    assert any(item.feature == "mouth_corner_vertical_asymmetry" for item in droop.top_contributions)


def test_analysis_payload_contains_static_v1_symmetry_contract() -> None:
    result = FacialSymmetryRiskAnalyzer().analyze(load_face("landmarks_mouth_droop.json")).to_dict()

    assert "symmetry" in result
    assert "attributes" in result
    assert "stroke_warning_auxiliary" in result
    assert result["symmetry"]["affected_side"] in {"left", "right", "bilateral", "uncertain"}
    for component in ["mouth", "eye", "brow", "midline", "contour"]:
        attribute = result["attributes"][component]
        assert {"score", "symmetry_score", "side", "confidence", "features", "feature_severities"} <= set(attribute)


def test_symmetry_features_are_stable_after_scale_translation_and_light_roll() -> None:
    analyzer = FacialSymmetryRiskAnalyzer()
    original = analyzer.analyze(load_face("landmarks_mouth_droop.json"))
    transformed = analyzer.analyze(transform_face(load_face("landmarks_mouth_droop.json"), scale=2.4, degrees=8.0, dx=12.0, dy=-7.0))

    assert transformed.symmetry.overall_symmetry_score == pytest.approx(original.symmetry.overall_symmetry_score, abs=1e-6)
    assert transformed.symmetry.affected_side == original.symmetry.affected_side
    for component in ["mouth", "eye", "brow", "midline", "contour"]:
        assert transformed.attributes[component].score == pytest.approx(original.attributes[component].score, abs=1e-6)


def test_missing_required_landmark_raises_clear_error() -> None:
    payload = json.loads((ROOT / "examples" / "landmarks_symmetric.json").read_text(encoding="utf-8"))
    del payload["landmarks"]["chin"]

    with pytest.raises(ValueError, match="missing required landmark: chin"):
        FacialSymmetryRiskAnalyzer().analyze(FaceLandmarks.from_payload(payload))


def transform_face(face: FaceLandmarks, *, scale: float, degrees: float, dx: float, dy: float) -> FaceLandmarks:
    radians = math.radians(degrees)
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    transformed = {}
    for name, point in face.landmarks.items():
        x = scale * (point.x * cos_v - point.y * sin_v) + dx
        y = scale * (point.x * sin_v + point.y * cos_v) + dy
        transformed[name] = Landmark(x=x, y=y, confidence=point.confidence)
    return FaceLandmarks(landmarks=transformed, pose=face.pose, image_id=face.image_id)
