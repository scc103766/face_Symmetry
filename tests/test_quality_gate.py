from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from facesymai.quality import QualityGate, QualityGateConfig, infer_media_type


def save_rgb(path: Path, image: np.ndarray) -> None:
    Image.fromarray(image.astype(np.uint8), mode="RGB").save(path)


def test_quality_gate_rejects_too_small_image_without_face_requirement(tmp_path: Path) -> None:
    image_path = tmp_path / "small.jpg"
    save_rgb(image_path, np.full((120, 120, 3), 128, dtype=np.uint8))
    gate = QualityGate(QualityGateConfig(require_face_detection=False))

    result = gate.evaluate_image(image_path)

    assert result.quality_level == "reject"
    assert result.hard_reject is True
    assert any(reason.code == "image_too_small" for reason in result.reasons)


def test_quality_gate_rejects_blurry_flat_image_without_face_requirement(tmp_path: Path) -> None:
    image_path = tmp_path / "flat.jpg"
    save_rgb(image_path, np.full((320, 320, 3), 128, dtype=np.uint8))
    gate = QualityGate(QualityGateConfig(require_face_detection=False))

    result = gate.evaluate_image(image_path)

    assert result.quality_level == "reject"
    assert any(reason.code == "image_blurry" for reason in result.reasons)


def test_quality_gate_passes_sharp_reasonably_lit_pattern_without_face_requirement(tmp_path: Path) -> None:
    image_path = tmp_path / "sharp.png"
    pattern = np.indices((320, 320)).sum(axis=0) % 2
    image = np.where(pattern[..., None] == 0, 40, 220).astype(np.uint8)
    image = np.repeat(image, 3, axis=2)
    save_rgb(image_path, image)
    gate = QualityGate(QualityGateConfig(require_face_detection=False))

    result = gate.evaluate_image(image_path)

    assert result.quality_level in {"pass", "review"}
    assert result.hard_reject is False
    assert result.quality_score > 0.58


def test_infer_media_type() -> None:
    assert infer_media_type(Path("a.jpg")) == "image"
    assert infer_media_type(Path("a.mp4")) == "video"
    assert infer_media_type(Path("a.txt")) == "unknown"
