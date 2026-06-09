from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from .detector import MediaPipeFaceLandmarkerDetector
from .visualization import draw_landmarker_overlay


MODULE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = MODULE_ROOT.parents[1] if len(MODULE_ROOT.parents) > 1 else MODULE_ROOT
MODEL_ENV_VAR = "FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL"
MODULE_MODEL_PATH = MODULE_ROOT / "models" / "face_landmarker.task"
PROJECT_MODEL_PATH = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"


def default_model_path() -> Path:
    env_value = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    if MODULE_MODEL_PATH.exists():
        return MODULE_MODEL_PATH.resolve()
    return PROJECT_MODEL_PATH.resolve()


class FaceKeypointDetectorSDK:
    """Offline SDK facade for MediaPipe Face Landmarker detection."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        max_num_faces: int = 2,
        min_face_detection_confidence: float = 0.5,
        min_face_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self.model_path = Path(model_path).expanduser().resolve() if model_path else default_model_path()
        self.detector = MediaPipeFaceLandmarkerDetector(
            self.model_path,
            max_num_faces=max(1, max_num_faces),
            min_face_detection_confidence=min_face_detection_confidence,
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def close(self) -> None:
        self.detector.close()

    def __enter__(self) -> "FaceKeypointDetectorSDK":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def detect_image(
        self,
        image_path: str | Path,
        *,
        image_id: str | None = None,
        allow_multiple_faces: bool = False,
        annotated_output: str | Path | None = None,
    ) -> dict[str, Any]:
        path = Path(image_path).expanduser().resolve()
        payload: dict[str, Any] = {
            "input": {"path": path.as_posix(), "image_id": image_id or path.stem},
            "runtime": {
                "backend": "mediapipe_face_landmarker",
                "model": self.model_path.as_posix(),
            },
        }
        try:
            detection = self.detector.detect_image_path(path, image_id=image_id or path.stem)
            if detection is None:
                payload.update({"status": "no_face", "detection": None})
                return payload

            detection_payload = detection.to_dict()
            face_count = int(detection_payload.get("face_count") or 1)
            status = "multiple_faces" if face_count > 1 and not allow_multiple_faces else "detected"
            payload.update({"status": status, "detection": detection_payload})
            if annotated_output is not None:
                output_path = Path(annotated_output).expanduser().resolve()
                if output_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    output_path = output_path / f"{path.stem}.jpg"
                payload["annotation"] = draw_landmarker_overlay(path, detection_payload, output_path)
        except Exception as exc:  # noqa: BLE001 - SDK returns structured per-image errors.
            payload.update({"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}})
        return payload

    def detect_images(
        self,
        image_paths: Iterable[str | Path],
        *,
        allow_multiple_faces: bool = False,
        annotated_output_dir: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        output_dir = Path(annotated_output_dir).expanduser().resolve() if annotated_output_dir else None
        return [
            self.detect_image(
                path,
                allow_multiple_faces=allow_multiple_faces,
                annotated_output=(output_dir / f"{Path(path).stem}.jpg") if output_dir else None,
            )
            for path in image_paths
        ]
