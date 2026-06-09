from __future__ import annotations

from pathlib import Path

from facesymai.landmarks.mediapipe_face_landmarker import MediaPipeFaceLandmarkerDetector


def test_detect_image_path_falls_back_when_mediapipe_file_reader_fails(tmp_path: Path, monkeypatch) -> None:
    detector = MediaPipeFaceLandmarkerDetector.__new__(MediaPipeFaceLandmarkerDetector)
    image_path = tmp_path / "truncated.jpg"
    image_path.write_bytes(b"not-a-complete-image")
    rgb_image = object()
    fallback_result = object()
    captured: dict[str, object] = {}

    class FailingImage:
        @staticmethod
        def create_from_file(_path: str) -> object:
            raise OSError("Truncated File Read")

    class FakeMediaPipe:
        Image = FailingImage

    detector._mp = FakeMediaPipe()
    monkeypatch.setattr(detector, "_read_rgb_image_with_pillow", lambda path: rgb_image)

    def fake_detect_rgb_image(image: object, *, image_id: str) -> object:
        captured["image"] = image
        captured["image_id"] = image_id
        return fallback_result

    monkeypatch.setattr(detector, "detect_rgb_image", fake_detect_rgb_image)

    result = detector.detect_image_path(image_path, image_id="sample-1")

    assert result is fallback_result
    assert captured == {"image": rgb_image, "image_id": "sample-1"}
