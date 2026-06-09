from __future__ import annotations

from pathlib import Path
from typing import Any

from .mediapipe_face_mesh import (
    MEDIAPIPE_FACE_MESH_LANDMARKS,
    FaceMeshDetection,
    MediaPipeUnavailableError,
)


class MediaPipeFaceLandmarkerDetector:
    """MediaPipe Tasks Face Landmarker adapter for static image detection."""

    def __init__(
        self,
        model_asset_path: Path,
        *,
        max_num_faces: int = 1,
        min_face_detection_confidence: float = 0.5,
        min_face_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        output_face_blendshapes: bool = True,
        output_facial_transformation_matrixes: bool = True,
    ) -> None:
        model_asset_path = model_asset_path.expanduser().resolve()
        if not model_asset_path.exists():
            raise FileNotFoundError(f"MediaPipe Face Landmarker model is missing: {model_asset_path}")

        try:
            import mediapipe as mp  # type: ignore[import-not-found]
            from mediapipe.tasks import python as mp_tasks  # type: ignore[import-not-found]
            from mediapipe.tasks.python import vision  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MediaPipeUnavailableError(
                "MediaPipe Tasks runtime is not available. Install `mediapipe` in the project environment."
            ) from exc

        self._mp = mp
        self._vision = vision
        self._model_asset_path = model_asset_path
        options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=str(model_asset_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=max_num_faces,
            min_face_detection_confidence=min_face_detection_confidence,
            min_face_presence_confidence=min_face_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=output_face_blendshapes,
            output_facial_transformation_matrixes=output_facial_transformation_matrixes,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)

    @property
    def model_asset_path(self) -> Path:
        return self._model_asset_path

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "MediaPipeFaceLandmarkerDetector":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def detect_image_path(self, image_path: Path, *, image_id: str | None = None) -> FaceMeshDetection | None:
        try:
            image = self._mp.Image.create_from_file(str(image_path))
            result = self._landmarker.detect(image)
        except (RuntimeError, OSError, ValueError):
            image_array = self._read_rgb_image_with_pillow(image_path)
            return self.detect_rgb_image(image_array, image_id=image_id or image_path.stem)
        if not result.face_landmarks:
            return None
        return self._to_detection(result, image_id=image_id or image_path.stem)

    def detect_rgb_image(self, image: Any, *, image_id: str) -> FaceMeshDetection | None:
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=image)
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return None
        return self._to_detection(result, image_id=image_id)

    def _to_detection(self, result: Any, *, image_id: str) -> FaceMeshDetection:
        face_landmarks = result.face_landmarks[0]
        raw_landmarks = [
            {"x": float(point.x), "y": float(point.y), "z": float(point.z), "confidence": 1.0}
            for point in face_landmarks
        ]
        named = {
            name: {
                "x": raw_landmarks[index]["x"],
                "y": raw_landmarks[index]["y"],
                "z": raw_landmarks[index]["z"],
                "confidence": raw_landmarks[index]["confidence"],
            }
            for name, index in MEDIAPIPE_FACE_MESH_LANDMARKS.items()
            if index < len(raw_landmarks)
        }
        detection = FaceMeshDetection(
            image_id=image_id,
            landmarks=named,
            raw_landmarks=raw_landmarks,
            pose=self._estimate_pose(named),
            blendshapes=self._blendshapes(result),
            facial_transformation_matrixes=self._transformation_matrixes(result),
            face_count=len(result.face_landmarks),
            backend="mediapipe_face_landmarker",
            detector_version=f"mediapipe-tasks-face-landmarker:{self._model_asset_path.name}",
            mapping_version="facesymai-mediapipe-face-landmarker-map-v1",
        )
        return detection

    def _read_rgb_image_with_pillow(self, image_path: Path) -> Any:
        import numpy as np
        from PIL import Image
        from PIL import ImageFile

        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(image_path) as image:
            return np.asarray(image.convert("RGB"))

    def _estimate_pose(self, landmarks: dict[str, dict[str, float]]) -> dict[str, float]:
        left = landmarks.get("left_eye_outer")
        right = landmarks.get("right_eye_outer")
        if left is None or right is None:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

        import math

        dx = float(left["x"]) - float(right["x"])
        dy = float(left["y"]) - float(right["y"])
        roll = math.degrees(math.atan2(dy, dx))
        return {"yaw": 0.0, "pitch": 0.0, "roll": roll}

    def _blendshapes(self, result: Any) -> dict[str, float]:
        if not result.face_blendshapes:
            return {}
        return {category.category_name: float(category.score) for category in result.face_blendshapes[0]}

    def _transformation_matrixes(self, result: Any) -> list[list[list[float]]]:
        return [matrix.astype(float).tolist() for matrix in result.facial_transformation_matrixes]
