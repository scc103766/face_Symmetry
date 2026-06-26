from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping

try:
    from .feature_extractor import LANDMARK, REGION_EDGES
except ImportError:  # pragma: no cover - used when imported as top-level module by 18432 API.
    from feature_extractor import LANDMARK, REGION_EDGES


SIDE_VIEW_GAZE_THRESHOLD = 0.5

TEETH_LIP_GAP_OPEN_THRESHOLD = 0.06
TEETH_LIP_GAP_SECONDARY_THRESHOLD = 0.075
TEETH_LIP_GAP_CLEAR_THRESHOLD = 0.11
TEETH_MOUTH_STRETCH_SECONDARY_THRESHOLD = 0.80
TEETH_MOUTH_STRETCH_CLEAR_THRESHOLD = 0.90
TEETH_LIP_AREA_THRESHOLD = 0.035
TEETH_LIP_GAP_CALIBRATED_THRESHOLD = 0.055
TEETH_MOUTH_STRETCH_CALIBRATED_THRESHOLD = 0.55
TEETH_LIP_AREA_CALIBRATED_THRESHOLD = 0.026
TEETH_JAW_OPEN_TIE_BREAK_THRESHOLD = 0.04
TEETH_COLOR_THRESHOLD = 0.20
TEETH_COLOR_RESCUE_THRESHOLD = 0.30
TEETH_COLOR_VETO_THRESHOLD = 0.075
TEETH_COLOR_RESCUE_LIP_GAP_THRESHOLD = 0.045
TEETH_COLOR_RESCUE_LIP_AREA_THRESHOLD = 0.022
TEETH_COLOR_VETO_LIP_GAP_THRESHOLD = 0.065
TEETH_COLOR_VETO_LIP_AREA_THRESHOLD = 0.030
TEETH_COLOR_VETO_JAW_OPEN_THRESHOLD = 0.08
TEETH_EDGE_RESCUE_LIP_GAP_THRESHOLD = 0.055
TEETH_EDGE_RESCUE_LIP_AREA_THRESHOLD = 0.026
TEETH_EDGE_RESCUE_REGION_COUNT_MAX = 3
TEETH_COMBINED_RESCUE_THRESHOLD = 0.86
TEETH_S_THRESHOLD = 100
TEETH_V_THRESHOLD = 100
DARK_V_THRESHOLD = 80
LIP_S_THRESHOLD = 65
MOUTH_COLOR_MIN_PIXEL_COUNT = 20
MIN_TOOTH_EDGE_REGION_AREA = 5
EDGE_RESCUE_THRESHOLD = 0.55
POSE_CALIBRATION = {
    "frontal": 1.0,
    "slight_turn": 0.80,
    "moderate_turn": 0.65,
}

INNER_LIP_INDICES = [
    78,
    191,
    80,
    81,
    82,
    13,
    312,
    311,
    310,
    415,
    308,
    324,
    318,
    402,
    317,
    14,
    87,
    178,
    88,
    95,
]


@dataclass(frozen=True)
class TeethExposureResult:
    detected: bool
    mouth_state: str
    confidence: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SideViewResult:
    detected: bool
    direction: str
    yaw_angle: float
    level: str
    confidence: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


def detect_side_view(detection: dict[str, Any]) -> SideViewResult:
    """Detect eye gaze direction (侧视 = 眼球侧视) from blendshapes.

    Uses eyeLookIn/Out blendshapes. Both eyes coordinated → gaze direction.
    Left gaze: eyeLookOutLeft + eyeLookInRight (both point left)
    Right gaze: eyeLookInLeft + eyeLookOutRight (both point right)
    """

    blendshapes = detection.get("blendshapes") or {}
    if not isinstance(blendshapes, Mapping):
        return _missing_gaze_result()

    try:
        eye_look_out_left = float(blendshapes.get("eyeLookOutLeft", 0))
        eye_look_in_left = float(blendshapes.get("eyeLookInLeft", 0))
        eye_look_out_right = float(blendshapes.get("eyeLookOutRight", 0))
        eye_look_in_right = float(blendshapes.get("eyeLookInRight", 0))
    except (TypeError, ValueError):
        return _missing_gaze_result()

    # Coordinated gaze scores
    gaze_left = eye_look_out_left + eye_look_in_right   # both eyes contributing to "look left"
    gaze_right = eye_look_in_left + eye_look_out_right  # both eyes contributing to "look right"
    gaze_diff = gaze_left - gaze_right

    abs_diff = abs(gaze_diff)
    if abs_diff > SIDE_VIEW_GAZE_THRESHOLD * 2.0:
        detected = True
        level = "extreme"
    elif abs_diff > SIDE_VIEW_GAZE_THRESHOLD:
        detected = True
        level = "moderate"
    else:
        detected = False
        level = "frontal"

    direction = "left" if gaze_diff > 0 else "right" if gaze_diff < 0 else "center"
    if not detected:
        direction = "center"

    # Confidence: linear mapping from |gaze_diff| to [0,1], capped at extreme threshold
    side_confidence = _clamp01(abs_diff / (SIDE_VIEW_GAZE_THRESHOLD * 2.0))

    return SideViewResult(
        detected=detected,
        direction=direction,
        yaw_angle=round(gaze_diff, 4),
        level=level,
        confidence=round(side_confidence, 4),
        details={
            "gaze_left": round(gaze_left, 4),
            "gaze_right": round(gaze_right, 4),
            "gaze_diff": round(gaze_diff, 4),
            "eyeLookOutLeft": eye_look_out_left,
            "eyeLookInLeft": eye_look_in_left,
            "eyeLookOutRight": eye_look_out_right,
            "eyeLookInRight": eye_look_in_right,
            "threshold": SIDE_VIEW_GAZE_THRESHOLD,
            "method": "eye_gaze_blendshape",
        },
    )


def detect_teeth_exposure(detection: dict[str, Any], image_path: str | None = None) -> TeethExposureResult:
    """Detect teeth exposure from lip geometry, with jawOpen as a boundary tie-breaker."""

    landmarks = detection.get("landmarks") or {}
    raw_landmarks = detection.get("raw_landmarks") or []
    mouth_features = _analyze_mouth_region(image_path, raw_landmarks) if image_path is not None else None
    color_features = _mouth_feature_group(mouth_features, "color")
    edge_features = _mouth_feature_group(mouth_features, "edge")
    pose_level = str(mouth_features.get("pose_level", "frontal")) if mouth_features is not None else "frontal"
    try:
        pose_factor = float(mouth_features.get("pose_factor", 1.0)) if mouth_features is not None else 1.0
    except (TypeError, ValueError):
        pose_factor = 1.0
    scale = _distance_between_named(landmarks, raw_landmarks, "left_eye_outer", "right_eye_outer")
    jaw_open = _jaw_open(detection.get("blendshapes") or {})

    if scale <= 1e-9:
        details = {
            "lip_gap": 0.0,
            "mouth_stretch": 0.0,
            "lip_area": 0.0,
            "scale": scale,
            "jawOpen": jaw_open,
            "error": "invalid_eye_scale",
        }
        if image_path is not None:
            details["color_features"] = color_features
            details["edge_features"] = edge_features
            details["pose_level"] = pose_level
            details["pose_factor"] = pose_factor
        return TeethExposureResult(
            detected=False,
            mouth_state="mouth_closed",
            confidence=0.0,
            details=details,
        )

    lip_gap = _distance_between_named(landmarks, raw_landmarks, "upper_lip_center", "lower_lip_center") / scale
    mouth_stretch = _distance_between_named(landmarks, raw_landmarks, "left_mouth_corner", "right_mouth_corner") / scale
    lip_area = _inner_lip_area(raw_landmarks, scale)
    tie_break_used = False
    clear_geometry_detected = False

    if lip_gap > TEETH_LIP_GAP_CLEAR_THRESHOLD and mouth_stretch > TEETH_MOUTH_STRETCH_CLEAR_THRESHOLD:
        detected = True
        mouth_state = "teeth_visible"
        clear_geometry_detected = True
    elif (
        lip_gap > TEETH_LIP_GAP_SECONDARY_THRESHOLD
        and mouth_stretch > TEETH_MOUTH_STRETCH_SECONDARY_THRESHOLD
        and lip_area > TEETH_LIP_AREA_THRESHOLD
    ):
        detected = True
        mouth_state = "teeth_visible"
    elif (
        lip_gap > TEETH_LIP_GAP_CALIBRATED_THRESHOLD
        and mouth_stretch > TEETH_MOUTH_STRETCH_CALIBRATED_THRESHOLD
        and lip_area > TEETH_LIP_AREA_CALIBRATED_THRESHOLD
    ):
        detected = True
        mouth_state = "teeth_visible"
    elif _teeth_geometry_near_boundary(lip_gap, mouth_stretch, lip_area) and jaw_open > TEETH_JAW_OPEN_TIE_BREAK_THRESHOLD:
        detected = True
        mouth_state = "teeth_visible"
        tie_break_used = True
    elif lip_gap > TEETH_LIP_GAP_OPEN_THRESHOLD:
        detected = False
        mouth_state = "mouth_open_no_teeth"
    else:
        detected = False
        mouth_state = "mouth_closed"

    if color_features is not None and color_features["mouth_pixel_count"] >= MOUTH_COLOR_MIN_PIXEL_COUNT:
        teeth_color_score = float(color_features["teeth_color_score"])
        edge_score = _safe_float(edge_features, "tooth_edge_score") if edge_features is not None else 0.0
        region_count = int(_safe_float(edge_features, "tooth_region_count")) if edge_features is not None else 0
        effective_color_rescue = TEETH_COLOR_RESCUE_THRESHOLD * pose_factor
        effective_color_veto = TEETH_COLOR_VETO_THRESHOLD * pose_factor
        effective_edge_rescue = EDGE_RESCUE_THRESHOLD * pose_factor
        effective_combined_rescue = TEETH_COMBINED_RESCUE_THRESHOLD * pose_factor
        color_rescue_candidate = (
            lip_gap > TEETH_COLOR_RESCUE_LIP_GAP_THRESHOLD
            and lip_area > TEETH_COLOR_RESCUE_LIP_AREA_THRESHOLD
        )
        edge_rescue_candidate = (
            lip_gap > TEETH_EDGE_RESCUE_LIP_GAP_THRESHOLD
            and lip_area > TEETH_EDGE_RESCUE_LIP_AREA_THRESHOLD
        )
        color_veto_candidate = (
            lip_gap < TEETH_COLOR_VETO_LIP_GAP_THRESHOLD
            or lip_area < TEETH_COLOR_VETO_LIP_AREA_THRESHOLD
            or jaw_open < TEETH_COLOR_VETO_JAW_OPEN_THRESHOLD
        )
        color_rescue = (
            not detected
            and color_rescue_candidate
            and teeth_color_score > effective_color_rescue
        )
        edge_rescue_ready = (
            edge_rescue_candidate
            and edge_score > effective_edge_rescue
            and region_count <= TEETH_EDGE_RESCUE_REGION_COUNT_MAX
        )
        combined_rescue = (
            not detected
            and color_rescue_candidate
            and (teeth_color_score + edge_score) / 2.0 > effective_combined_rescue
            and region_count <= TEETH_EDGE_RESCUE_REGION_COUNT_MAX
        )
        if color_rescue or combined_rescue:
            detected = True
            mouth_state = "teeth_visible"
            tie_break_used = True
        elif (
            detected
            and color_veto_candidate
            and teeth_color_score < effective_color_veto
            and not clear_geometry_detected
        ):
            detected = False
            mouth_state = "mouth_open_no_teeth"
            tie_break_used = True
        if not detected and edge_rescue_ready:
            detected = True
            mouth_state = "teeth_visible"
            tie_break_used = True

    confidence = _clamp01(
        ((lip_gap / TEETH_LIP_GAP_CLEAR_THRESHOLD) + (mouth_stretch / TEETH_MOUTH_STRETCH_CLEAR_THRESHOLD)) / 2.0
    )
    details = {
        "lip_gap": lip_gap,
        "mouth_stretch": mouth_stretch,
        "lip_area": lip_area,
        "scale": scale,
        "jawOpen": jaw_open,
        "tie_break_used": tie_break_used,
    }
    if image_path is not None:
        details["color_features"] = color_features
        details["edge_features"] = edge_features
        details["pose_level"] = pose_level
        details["pose_factor"] = pose_factor
    return TeethExposureResult(
        detected=detected,
        mouth_state=mouth_state,
        confidence=confidence,
        details=details,
    )


def _missing_gaze_result() -> SideViewResult:
    return SideViewResult(
        detected=False,
        direction="center",
        yaw_angle=0.0,
        level="frontal",
        details={"error": "missing_blendshapes"},
    )


def _missing_side_geometry_result(error: str) -> SideViewResult:
    return SideViewResult(
        detected=False,
        direction="center",
        yaw_angle=0.0,
        level="frontal",
        details={
            "oval_width_ratio": 0.0,
            "eye_width_ratio": 0.0,
            "nostril_ratio": 0.0,
            "face_width": 0.0,
            "face_height": 0.0,
            "side_score": 1.0,
            "error": error,
        },
    )


def _region_raw_points(raw_landmarks: Any, region_name: str) -> list[tuple[float, float]]:
    if not isinstance(raw_landmarks, list):
        return []
    points: list[tuple[float, float]] = []
    indices = sorted({idx for edge in REGION_EDGES[region_name] for idx in edge})
    for index in indices:
        point = _raw_point(raw_landmarks, index)
        if point is not None:
            points.append(point)
    return points


def _inner_lip_area(raw_landmarks: Any, scale: float) -> float:
    lip_points = _region_raw_points(raw_landmarks, "lips")
    if len(lip_points) < 3 or scale <= 1e-9:
        return 0.0
    ys = sorted(point[1] for point in lip_points)
    low = _quantile(ys, 0.25)
    high = _quantile(ys, 0.75)
    inner_points = [point for point in lip_points if low <= point[1] <= high]
    return _convex_hull_area(inner_points) / (scale * scale)


def _analyze_mouth_region(
    image_path: str,
    raw_landmarks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Analyze color, edge, and pose features for the inner mouth region."""

    mouth_region = _crop_mouth_region(image_path, raw_landmarks)
    if mouth_region is None:
        return None

    color_features = _teeth_color_score(mouth_region["mouth_pixels_hsv"])
    edge_features = _teeth_edge_features(mouth_region["mouth_crop_bgr"], mouth_region["mouth_crop_hsv"])
    pose_level = _face_pose_level(raw_landmarks)
    pose_factor = POSE_CALIBRATION.get(pose_level, 1.0)
    return {
        "color": color_features,
        "edge": edge_features,
        "pose_level": pose_level,
        "pose_factor": pose_factor,
    }


def _analyze_mouth_color(image_path: str, raw_landmarks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Analyze HSV color evidence inside the inner lip polygon."""

    mouth_features = _analyze_mouth_region(image_path, raw_landmarks)
    if mouth_features is None:
        return None
    color_features = _mouth_feature_group(mouth_features, "color")
    return color_features


def _crop_mouth_interior(
    image_path: str,
    raw_landmarks: list[dict[str, Any]],
    padding: int = 2,
) -> Any | None:
    mouth_region = _crop_mouth_region(image_path, raw_landmarks, padding=padding)
    if mouth_region is None:
        return None
    return mouth_region["mouth_pixels_hsv"]


def _crop_mouth_region(
    image_path: str,
    raw_landmarks: list[dict[str, Any]],
    padding: int = 2,
) -> dict[str, Any] | None:
    import cv2
    import numpy as np

    img = cv2.imread(image_path)
    if img is None:
        return None
    height, width = img.shape[:2]
    inner_points = _inner_lip_pixel_points(raw_landmarks, width, height)
    if len(inner_points) < 4:
        return None

    xs = [point[0] for point in inner_points]
    ys = [point[1] for point in inner_points]
    x_min = max(min(xs) - padding, 0)
    y_min = max(min(ys) - padding, 0)
    x_max = min(max(xs) + padding + 1, width)
    y_max = min(max(ys) + padding + 1, height)
    if x_max <= x_min or y_max <= y_min:
        return None

    crop = img[y_min:y_max, x_min:x_max]
    local_points = np.array([[(x - x_min, y - y_min) for x, y in inner_points]], dtype=np.int32)
    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, local_points, 255)

    mouth_pixels = crop[mask == 255]
    if len(mouth_pixels) < MOUTH_COLOR_MIN_PIXEL_COUNT:
        return None
    mouth_pixels_bgr = mouth_pixels.reshape(-1, 1, 3)
    masked_crop = crop.copy()
    masked_crop[mask == 0] = 0
    crop_hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    crop_hsv[mask == 0] = 0
    return {
        "mouth_crop_bgr": crop,
        "mouth_crop_hsv": crop_hsv,
        "mouth_pixels_hsv": cv2.cvtColor(mouth_pixels_bgr, cv2.COLOR_BGR2HSV),
    }


def _inner_lip_pixel_points(raw_landmarks: Any, width: int, height: int) -> list[tuple[int, int]]:
    if not isinstance(raw_landmarks, list):
        return []
    points: list[tuple[int, int]] = []
    for index in INNER_LIP_INDICES:
        if index >= len(raw_landmarks):
            continue
        point = _mapping_point(raw_landmarks[index])
        if point is None:
            continue
        x = min(max(int(point[0] * width), 0), max(width - 1, 0))
        y = min(max(int(point[1] * height), 0), max(height - 1, 0))
        points.append((x, y))
    return points


def _teeth_color_score(mouth_pixels_hsv: Any) -> dict[str, Any]:
    import cv2
    import numpy as np

    _h_ch, s_ch, v_ch = cv2.split(mouth_pixels_hsv)
    s_flat = s_ch.flatten().astype(np.float32)
    v_flat = v_ch.flatten().astype(np.float32)
    total = len(s_flat)
    if total == 0:
        return {
            "teeth_ratio": 0.0,
            "dark_ratio": 0.0,
            "lip_ratio": 0.0,
            "mouth_pixel_count": 0,
            "teeth_color_score": 0.0,
        }

    teeth_mask = (s_flat < TEETH_S_THRESHOLD) & (v_flat > TEETH_V_THRESHOLD)
    dark_mask = v_flat < DARK_V_THRESHOLD
    lip_mask = s_flat > LIP_S_THRESHOLD

    teeth_ratio = float(np.sum(teeth_mask) / total)
    dark_ratio = float(np.sum(dark_mask) / total)
    lip_ratio = float(np.sum(lip_mask) / total)
    teeth_color_score = teeth_ratio * (1.0 - dark_ratio)

    return {
        "teeth_ratio": round(teeth_ratio, 4),
        "dark_ratio": round(dark_ratio, 4),
        "lip_ratio": round(lip_ratio, 4),
        "mouth_pixel_count": int(total),
        "teeth_color_score": round(teeth_color_score, 4),
    }


def _teeth_edge_features(mouth_crop_bgr: Any, mouth_pixels_hsv: Any) -> dict[str, Any]:
    import cv2
    import numpy as np

    if mouth_crop_bgr is None or mouth_pixels_hsv is None or mouth_crop_bgr.size == 0:
        return _empty_teeth_edge_features()

    _h_ch, s_ch, v_ch = cv2.split(mouth_pixels_hsv)
    teeth_mask = (s_ch < TEETH_S_THRESHOLD) & (v_ch > TEETH_V_THRESHOLD)
    mouth_roi_width = max(int(mouth_crop_bgr.shape[1]), 1)

    num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        teeth_mask.astype(np.uint8), connectivity=8
    )
    if num_labels > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        widths = stats[1:, cv2.CC_STAT_WIDTH]
        max_idx = int(np.argmax(areas))
        max_width_norm = float(widths[max_idx] / mouth_roi_width)
        region_count = int(np.sum(areas >= MIN_TOOTH_EDGE_REGION_AREA))
    else:
        max_width_norm = 0.0
        region_count = 0

    gray = cv2.cvtColor(mouth_crop_bgr, cv2.COLOR_BGR2GRAY)
    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    significant_teeth = teeth_mask > 0
    if bool(np.any(significant_teeth)):
        grad_values = np.abs(grad_x)[significant_teeth]
    else:
        grad_values = np.array([], dtype=np.float64)
    edge_gradient_max = float(np.max(grad_values)) / 255.0 if grad_values.size else 0.0

    width_ok = 1.0 if max_width_norm > 0.30 else max_width_norm / 0.30
    if region_count <= 0:
        count_ok = 0.0
    elif region_count <= 2:
        count_ok = 1.0
    else:
        count_ok = max(0.0, 1.0 - (region_count - 2) * 0.3)
    grad_ok = 1.0 if edge_gradient_max > 0.15 else edge_gradient_max / 0.15
    tooth_edge_score = _clamp01((width_ok + count_ok + grad_ok) / 3.0)

    return {
        "max_tooth_region_width": round(_clamp01(max_width_norm), 4),
        "tooth_region_count": region_count,
        "edge_gradient_max": round(_clamp01(edge_gradient_max), 4),
        "tooth_edge_score": round(tooth_edge_score, 4),
    }


def _empty_teeth_edge_features() -> dict[str, Any]:
    return {
        "max_tooth_region_width": 0.0,
        "tooth_region_count": 0,
        "edge_gradient_max": 0.0,
        "tooth_edge_score": 0.0,
    }


def _face_pose_level(raw_landmarks: list[dict[str, Any]]) -> str:
    face_points = _region_raw_points(raw_landmarks, "face_oval")
    if len(face_points) < 4:
        return "frontal"

    xs = [point[0] for point in face_points]
    ys = [point[1] for point in face_points]
    face_w = max(xs) - min(xs)
    face_h = max(ys) - min(ys)
    if face_h <= 1e-9:
        return "frontal"

    ratio = face_w / face_h
    if ratio > 0.60:
        return "frontal"
    if ratio > 0.45:
        return "slight_turn"
    return "moderate_turn"


def _mouth_feature_group(mouth_features: Any, name: str) -> dict[str, Any] | None:
    if not isinstance(mouth_features, Mapping):
        return None
    value = mouth_features.get(name)
    return value if isinstance(value, dict) else None


def _safe_float(features: Mapping[str, Any], key: str) -> float:
    try:
        return float(features.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _eye_width_ratio(landmarks: Any, raw_landmarks: Any, face_height: float) -> float:
    eye_width = _horizontal_distance_between_named(landmarks, raw_landmarks, "left_eye_outer", "right_eye_outer")
    if face_height <= 1e-9:
        return 1.0
    return eye_width / face_height


def _nostril_ratio(landmarks: Any, raw_landmarks: Any, face_width: float) -> float:
    nostril_width = _horizontal_distance_between_named(landmarks, raw_landmarks, "left_nostril", "right_nostril")
    if face_width <= 1e-9:
        return 1.0
    return nostril_width / face_width


def _z_delta_ratio(landmarks: Any, raw_landmarks: Any, first_name: str, second_name: str, scale: float) -> float:
    first = _named_point_3d(landmarks, raw_landmarks, first_name)
    second = _named_point_3d(landmarks, raw_landmarks, second_name)
    if first is None or second is None or scale <= 1e-9:
        return 0.0
    return abs(first[2] - second[2]) / scale


def _nose_center_x_ratio(landmarks: Any, raw_landmarks: Any, scale: float) -> float:
    nose_tip = _named_point_3d(landmarks, raw_landmarks, "nose_tip")
    left_cheek = _named_point_3d(landmarks, raw_landmarks, "left_cheek")
    right_cheek = _named_point_3d(landmarks, raw_landmarks, "right_cheek")
    if nose_tip is None or left_cheek is None or right_cheek is None or scale <= 1e-9:
        return 0.0
    cheek_center_x = (left_cheek[0] + right_cheek[0]) / 2.0
    return abs(nose_tip[0] - cheek_center_x) / scale


def _horizontal_distance_between_named(landmarks: Any, raw_landmarks: Any, first_name: str, second_name: str) -> float:
    first = _named_point(landmarks, raw_landmarks, first_name)
    second = _named_point(landmarks, raw_landmarks, second_name)
    if first is None or second is None:
        return 0.0
    return abs(first[0] - second[0])


def _distance_between_named(landmarks: Any, raw_landmarks: Any, first_name: str, second_name: str) -> float:
    first = _named_point(landmarks, raw_landmarks, first_name)
    second = _named_point(landmarks, raw_landmarks, second_name)
    if first is None or second is None:
        return 0.0
    return math.dist(first, second)


def _named_point(landmarks: Any, raw_landmarks: Any, name: str) -> tuple[float, float] | None:
    if isinstance(landmarks, Mapping):
        point = _mapping_point(landmarks.get(name))
        if point is not None:
            return point
    index = LANDMARK.get(name)
    if index is None:
        return None
    return _raw_point(raw_landmarks, index)


def _named_point_3d(landmarks: Any, raw_landmarks: Any, name: str) -> tuple[float, float, float] | None:
    if isinstance(landmarks, Mapping):
        point = _mapping_point_3d(landmarks.get(name))
        if point is not None:
            return point
    index = LANDMARK.get(name)
    if index is None:
        return None
    return _raw_point_3d(raw_landmarks, index)


def _raw_point(raw_landmarks: Any, index: int) -> tuple[float, float] | None:
    if not isinstance(raw_landmarks, list) or index >= len(raw_landmarks):
        return None
    return _mapping_point(raw_landmarks[index])


def _raw_point_3d(raw_landmarks: Any, index: int) -> tuple[float, float, float] | None:
    if not isinstance(raw_landmarks, list) or index >= len(raw_landmarks):
        return None
    return _mapping_point_3d(raw_landmarks[index])


def _mapping_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return (float(value["x"]), float(value["y"]))
    except (KeyError, TypeError, ValueError):
        return None


def _mapping_point_3d(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return (float(value["x"]), float(value["y"]), float(value.get("z", 0.0) or 0.0))
    except (KeyError, TypeError, ValueError):
        return None


def _jaw_open(blendshapes: Any) -> float:
    if not isinstance(blendshapes, Mapping):
        return 0.0
    try:
        return float(blendshapes.get("jawOpen", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _teeth_geometry_near_boundary(lip_gap: float, mouth_stretch: float, lip_area: float) -> bool:
    return (
        TEETH_LIP_GAP_SECONDARY_THRESHOLD * 0.9 <= lip_gap <= TEETH_LIP_GAP_CLEAR_THRESHOLD * 1.1
        and mouth_stretch >= TEETH_MOUTH_STRETCH_SECONDARY_THRESHOLD * 0.9
        and lip_area >= TEETH_LIP_AREA_THRESHOLD * 0.9
    )


def _quantile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _convex_hull_area(points: list[tuple[float, float]]) -> float:
    """Monotone chain convex hull area."""

    if len(points) < 3:
        return 0.0
    points = sorted(set(points))
    if len(points) < 3:
        return 0.0

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    area = 0.0
    for index in range(len(hull)):
        next_index = (index + 1) % len(hull)
        area += hull[index][0] * hull[next_index][1]
        area -= hull[next_index][0] * hull[index][1]
    return abs(area) / 2.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _mock_detection() -> dict[str, Any]:
    raw_landmarks = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(478)]
    for index in {idx for edge in REGION_EDGES["face_oval"] for idx in edge}:
        raw_landmarks[index] = {"x": 0.42 + (index % 7) * 0.01, "y": 0.25 + (index % 11) * 0.04, "z": 0.0}
    raw_landmarks[LANDMARK["left_eye_outer"]] = {"x": 0.60, "y": 0.38, "z": 0.0}
    raw_landmarks[LANDMARK["right_eye_outer"]] = {"x": 0.40, "y": 0.38, "z": 0.0}
    raw_landmarks[LANDMARK["left_nostril"]] = {"x": 0.52, "y": 0.48, "z": 0.0}
    raw_landmarks[LANDMARK["right_nostril"]] = {"x": 0.48, "y": 0.48, "z": 0.0}
    for index in {idx for edge in REGION_EDGES["lips"] for idx in edge}:
        raw_landmarks[index] = {"x": 0.45 + (index % 5) * 0.025, "y": 0.57 + (index % 4) * 0.025, "z": 0.0}
    raw_landmarks[LANDMARK["left_mouth_corner"]] = {"x": 0.63, "y": 0.62, "z": 0.0}
    raw_landmarks[LANDMARK["right_mouth_corner"]] = {"x": 0.37, "y": 0.62, "z": 0.0}
    raw_landmarks[LANDMARK["upper_lip_center"]] = {"x": 0.50, "y": 0.58, "z": 0.0}
    raw_landmarks[LANDMARK["lower_lip_center"]] = {"x": 0.50, "y": 0.62, "z": 0.0}
    return {
        "raw_landmarks": raw_landmarks,
        "landmarks": {
            "nose_tip": raw_landmarks[LANDMARK["nose_tip"]],
            "left_eye_outer": raw_landmarks[LANDMARK["left_eye_outer"]],
            "right_eye_outer": raw_landmarks[LANDMARK["right_eye_outer"]],
            "left_nostril": raw_landmarks[LANDMARK["left_nostril"]],
            "right_nostril": raw_landmarks[LANDMARK["right_nostril"]],
            "left_mouth_corner": raw_landmarks[LANDMARK["left_mouth_corner"]],
            "right_mouth_corner": raw_landmarks[LANDMARK["right_mouth_corner"]],
            "upper_lip_center": raw_landmarks[LANDMARK["upper_lip_center"]],
            "lower_lip_center": raw_landmarks[LANDMARK["lower_lip_center"]],
        },
        "blendshapes": {"jawOpen": 0.08},
    }


if __name__ == "__main__":
    mock_detection = _mock_detection()
    print("teeth_exposure:", detect_teeth_exposure(mock_detection))
    print("side_view:", detect_side_view(mock_detection))
