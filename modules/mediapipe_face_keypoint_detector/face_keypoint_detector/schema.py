from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MEDIAPIPE_FACE_LANDMARKS: dict[str, int] = {
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


@dataclass(frozen=True)
class FaceKeypointDetection:
    image_id: str
    landmarks: dict[str, dict[str, float]]
    raw_landmarks: list[dict[str, float]]
    pose: dict[str, float]
    blendshapes: dict[str, float] = field(default_factory=dict)
    facial_transformation_matrixes: list[list[list[float]]] = field(default_factory=list)
    face_count: int = 1
    backend: str = "mediapipe_face_landmarker"
    detector_version: str = "mediapipe-tasks-face-landmarker"
    mapping_version: str = "facesymai-mediapipe-face-landmarker-map-v1"
    landmark_schema_version: str = "facesymai-mediapipe-keypoints-v1"

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
