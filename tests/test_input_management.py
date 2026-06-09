from __future__ import annotations

from pathlib import Path

from facesymai.input_management import StaticImageInput, StaticImageInputManager, canonicalize_role
from facesymai.quality import FaceBox, FrameQuality, QualityGateResult


class FakeQualityGate:
    def __init__(self, *, hard_reject: bool = False, quality_level: str = "pass") -> None:
        self.hard_reject = hard_reject
        self.quality_level = quality_level

    def evaluate_image(self, path: Path, *, role: str | None = None) -> QualityGateResult:
        width = 640
        height = 960
        brightness = 120.0
        if "wide" in path.name:
            width = 1200
        if "dark" in path.name:
            brightness = 25.0
        frame = FrameQuality(
            frame_index=0,
            frame_time_sec=0.0,
            width=width,
            height=height,
            face_count=1,
            face_box=FaceBox(160, 180, 300, 320),
            eye_count=2,
            metrics={
                "brightness_mean": brightness,
                "laplacian_variance": 180.0,
                "bad_exposure_ratio": 0.02,
                "left_right_brightness_delta": 8.0,
            },
            component_scores={},
            quality_score=0.9,
            quality_level=self.quality_level,
            hard_reject=self.hard_reject,
            reasons=[],
        )
        return QualityGateResult(
            path=path.as_posix(),
            media_type="image",
            quality_score=0.9,
            quality_level=self.quality_level,
            hard_reject=self.hard_reject,
            reasons=[],
            metrics={},
            frame_results=[frame],
        )

    def evaluate_media(self, path: Path, media_type: str | None = None, role: str | None = None) -> QualityGateResult:
        return QualityGateResult(
            path=path.as_posix(),
            media_type=media_type or "unknown",
            quality_score=0.0,
            quality_level="reject",
            hard_reject=True,
            reasons=[],
            metrics={},
        )


def test_role_aliases_are_canonicalized() -> None:
    assert canonicalize_role("正脸轮廓") == "front"
    assert canonicalize_role("微笑示齿") == "teeth"
    assert canonicalize_role("front_contour") == "front"


def test_static_input_manager_accepts_front_teeth_pair_with_extra_image() -> None:
    manager = StaticImageInputManager(quality_gate=FakeQualityGate())

    result = manager.validate(
        [
            StaticImageInput(path=Path("front.jpg"), role="front", patient_id="p1", capture_id="c1"),
            StaticImageInput(path=Path("teeth.jpg"), role="teeth", patient_id="p1", capture_id="c1"),
            StaticImageInput(path=Path("left.jpg"), role="left_profile", patient_id="p1", capture_id="c1"),
        ]
    )

    assert result.accepted is True
    assert result.input_level == "pass"
    assert [image.canonical_role for image in result.images][:2] == ["front", "teeth"]


def test_static_input_manager_rejects_missing_pair_role() -> None:
    manager = StaticImageInputManager(quality_gate=FakeQualityGate())

    result = manager.validate(
        [
            StaticImageInput(path=Path("front_1.jpg"), role="front"),
            StaticImageInput(path=Path("front_2.jpg"), role="front"),
        ]
    )

    assert result.accepted is False
    assert any(issue.code == "missing_required_pair_role" for issue in result.issues)


def test_static_input_manager_rejects_single_image() -> None:
    manager = StaticImageInputManager(quality_gate=FakeQualityGate())

    result = manager.validate([StaticImageInput(path=Path("front.jpg"), role="front")])

    assert result.accepted is False
    assert any(issue.code == "insufficient_static_images" for issue in result.issues)


def test_static_input_manager_flags_cross_patient_inputs() -> None:
    manager = StaticImageInputManager(quality_gate=FakeQualityGate())

    result = manager.validate(
        [
            StaticImageInput(path=Path("front.jpg"), role="front", patient_id="p1"),
            StaticImageInput(path=Path("teeth.jpg"), role="teeth", patient_id="p2"),
        ]
    )

    assert result.accepted is False
    assert any(issue.code == "mixed_patient_inputs" for issue in result.issues)


def test_static_input_manager_reviews_dimension_mismatch() -> None:
    manager = StaticImageInputManager(quality_gate=FakeQualityGate())

    result = manager.validate(
        [
            StaticImageInput(path=Path("front.jpg"), role="front"),
            StaticImageInput(path=Path("teeth_wide.jpg"), role="teeth"),
        ]
    )

    assert result.accepted is True
    assert result.input_level == "review"
    assert any(issue.code == "image_width_not_comparable" for issue in result.issues)
