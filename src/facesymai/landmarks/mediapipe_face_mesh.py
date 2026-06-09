from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MEDIAPIPE_FACE_MESH_LANDMARKS: dict[str, int] = {
    "nose_bridge": 168,
    "nose_tip": 1,
    "chin": 152,
    "left_eye_outer": 263,
    "left_eye_inner": 362,
    "left_eye_upper": 386,
    "left_eye_lower": 374,
    "right_eye_outer": 33,
    "right_eye_inner": 133,
    "right_eye_upper": 159,
    "right_eye_lower": 145,
    "left_brow_inner": 336,
    "left_brow_outer": 276,
    "right_brow_inner": 107,
    "right_brow_outer": 46,
    "left_mouth_corner": 291,
    "right_mouth_corner": 61,
    "upper_lip_center": 13,
    "lower_lip_center": 14,
    "left_nostril": 327,
    "right_nostril": 98,
    "left_cheek": 454,
    "right_cheek": 234,
    "left_jaw": 365,
    "right_jaw": 136,
}


class MediaPipeUnavailableError(RuntimeError):
    """Raised when the optional MediaPipe runtime is not installed."""


@dataclass(frozen=True)
class FaceMeshDetection:
    image_id: str
    landmarks: dict[str, dict[str, float]]
    raw_landmarks: list[dict[str, float]]
    pose: dict[str, float]
    blendshapes: dict[str, float] = field(default_factory=dict)
    facial_transformation_matrixes: list[list[list[float]]] = field(default_factory=list)
    face_count: int = 1
    backend: str = "mediapipe_face_mesh"
    detector_version: str = "mediapipe-solutions-face-mesh"
    mapping_version: str = "facesymai-mediapipe-face-mesh-map-v1"
    landmark_schema_version: str = "facesymai-landmarks-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "detector": self.backend,
            "detector_version": self.detector_version,
            "mapping_version": self.mapping_version,
            "landmark_schema_version": self.landmark_schema_version,
            "face_count": self.face_count,
            "landmarks": self.landmarks,
            "raw_landmarks": self.raw_landmarks,
            "pose": self.pose,
            "blendshapes": self.blendshapes,
            "facial_transformation_matrixes": self.facial_transformation_matrixes,
            "backend": self.backend,
        }


class MediaPipeFaceMeshDetector:
    """Thin MediaPipe FaceMesh adapter for FaceSymAi keypoint extraction.

    MediaPipe is intentionally imported lazily because this project keeps it as
    an optional runtime dependency. Install the package or build it from the
    cloned `third_party/mediapipe` tree before running this detector.
    """

    def __init__(
        self,
        *,
        static_image_mode: bool = True,
        max_num_faces: int = 1,
        refine_landmarks: bool = True,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        try:
            import cv2  # type: ignore[import-not-found]
            import mediapipe as mp  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MediaPipeUnavailableError(
                "MediaPipe runtime is not available. Install `mediapipe` in the "
                "project environment or build it from `third_party/mediapipe`."
            ) from exc
        if not hasattr(mp, "solutions"):
            raise MediaPipeUnavailableError(
                "The installed MediaPipe package does not expose `mp.solutions.face_mesh`. "
                "Use MediaPipe Face Landmarker with a `.task` model instead."
            )

        self._cv2 = cv2
        self._mp = mp
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=static_image_mode,
            max_num_faces=max_num_faces,
            refine_landmarks=refine_landmarks,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def close(self) -> None:
        self._mesh.close()

    def __enter__(self) -> "MediaPipeFaceMeshDetector":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def detect_image_path(self, image_path: Path, *, image_id: str | None = None) -> FaceMeshDetection | None:
        image = self._cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"unable to read image: {image_path}")
        return self.detect_bgr_image(image, image_id=image_id or image_path.stem)

    def detect_bgr_image(self, image: Any, *, image_id: str) -> FaceMeshDetection | None:
        rgb = self._cv2.cvtColor(image, self._cv2.COLOR_BGR2RGB)
        results = self._mesh.process(rgb)
        if not results.multi_face_landmarks:
            return None

        face_count = len(results.multi_face_landmarks)
        face = results.multi_face_landmarks[0]
        raw_landmarks = [
            {"x": float(point.x), "y": float(point.y), "z": float(point.z), "confidence": 1.0}
            for point in face.landmark
        ]
        named = {
            name: {
                "x": raw_landmarks[index]["x"],
                "y": raw_landmarks[index]["y"],
                "confidence": raw_landmarks[index]["confidence"],
            }
            for name, index in MEDIAPIPE_FACE_MESH_LANDMARKS.items()
            if index < len(raw_landmarks)
        }
        return FaceMeshDetection(
            image_id=image_id,
            landmarks=named,
            raw_landmarks=raw_landmarks,
            pose=self._estimate_pose(named),
            face_count=face_count,
        )

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
