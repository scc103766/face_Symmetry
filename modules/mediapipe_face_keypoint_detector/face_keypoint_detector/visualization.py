from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFile, ImageFont


ImageFile.LOAD_TRUNCATED_IMAGES = True


SEMANTIC_CONNECTIONS: tuple[tuple[str, str], ...] = (
    ("right_eye_outer", "right_eye_upper"),
    ("right_eye_upper", "right_eye_inner"),
    ("right_eye_inner", "right_eye_lower"),
    ("right_eye_lower", "right_eye_outer"),
    ("left_eye_inner", "left_eye_upper"),
    ("left_eye_upper", "left_eye_outer"),
    ("left_eye_outer", "left_eye_lower"),
    ("left_eye_lower", "left_eye_inner"),
    ("right_brow_inner", "right_brow_outer"),
    ("left_brow_inner", "left_brow_outer"),
    ("right_mouth_corner", "upper_lip_center"),
    ("upper_lip_center", "left_mouth_corner"),
    ("left_mouth_corner", "lower_lip_center"),
    ("lower_lip_center", "right_mouth_corner"),
    ("nose_bridge", "nose_tip"),
    ("nose_tip", "upper_lip_center"),
    ("upper_lip_center", "lower_lip_center"),
    ("lower_lip_center", "chin"),
    ("right_nostril", "nose_tip"),
    ("nose_tip", "left_nostril"),
    ("right_jaw", "right_cheek"),
    ("right_cheek", "chin"),
    ("chin", "left_cheek"),
    ("left_cheek", "left_jaw"),
)


def draw_landmarker_overlay(
    image_path: Path,
    detection: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    """Draw MediaPipe Face Landmarker normalized output onto the source image."""

    with Image.open(image_path) as image:
        canvas = image.convert("RGB")

    width, height = canvas.size
    draw = ImageDraw.Draw(canvas, "RGBA")
    raw_landmarks = _points_from_landmarks(detection.get("raw_landmarks", []), width, height)
    semantic_landmarks = {
        name: _point_to_xy(point, width, height)
        for name, point in dict(detection.get("landmarks") or {}).items()
    }
    semantic_landmarks = {name: point for name, point in semantic_landmarks.items() if point is not None}

    raw_radius = max(1, round(min(width, height) / 420))
    semantic_radius = max(raw_radius + 2, round(min(width, height) / 150))
    line_width = max(1, round(min(width, height) / 300))

    bbox = _draw_raw_points(draw, raw_landmarks, raw_radius)
    if bbox is not None:
        draw.rectangle(bbox, outline=(255, 210, 0, 210), width=max(1, line_width))

    _draw_semantic_connections(draw, semantic_landmarks, line_width)
    _draw_semantic_points(draw, semantic_landmarks, semantic_radius)
    _draw_header(draw, detection, width, len(raw_landmarks), len(semantic_landmarks))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_kwargs: dict[str, Any] = {}
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        save_kwargs["quality"] = 92
    canvas.save(output_path, **save_kwargs)
    return {
        "path": output_path.as_posix(),
        "raw_landmarks_drawn": len(raw_landmarks),
        "semantic_landmarks_drawn": len(semantic_landmarks),
        "face_bbox_pixels": _bbox_to_dict(bbox),
    }


def _points_from_landmarks(raw_landmarks: Any, width: int, height: int) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    if not isinstance(raw_landmarks, list):
        return points
    for point in raw_landmarks:
        xy = _point_to_xy(point, width, height)
        if xy is not None:
            points.append(xy)
    return points


def _point_to_xy(point: Any, width: int, height: int) -> tuple[int, int] | None:
    if not isinstance(point, Mapping):
        return None
    try:
        x = float(point["x"])
        y = float(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-0.25 <= x <= 1.25 and -0.25 <= y <= 1.25):
        return None
    px = round(max(0.0, min(1.0, x)) * (width - 1))
    py = round(max(0.0, min(1.0, y)) * (height - 1))
    return int(px), int(py)


def _draw_raw_points(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[int, int]],
    radius: int,
) -> tuple[int, int, int, int] | None:
    if not points:
        return None
    for x, y in points:
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(0, 230, 255, 170),
            outline=(0, 70, 90, 210),
        )
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def _draw_semantic_connections(
    draw: ImageDraw.ImageDraw,
    semantic_landmarks: Mapping[str, tuple[int, int]],
    line_width: int,
) -> None:
    for start, end in SEMANTIC_CONNECTIONS:
        if start in semantic_landmarks and end in semantic_landmarks:
            draw.line(
                (semantic_landmarks[start], semantic_landmarks[end]),
                fill=(255, 95, 40, 230),
                width=line_width,
            )


def _draw_semantic_points(
    draw: ImageDraw.ImageDraw,
    semantic_landmarks: Mapping[str, tuple[int, int]],
    radius: int,
) -> None:
    for name, (x, y) in semantic_landmarks.items():
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=_semantic_color(name),
            outline=(20, 20, 20, 230),
            width=1,
        )


def _draw_header(
    draw: ImageDraw.ImageDraw,
    detection: Mapping[str, Any],
    width: int,
    raw_count: int,
    semantic_count: int,
) -> None:
    text = (
        f"{detection.get('detector', 'mediapipe')} | "
        f"faces={detection.get('face_count', '')} | "
        f"raw={raw_count} | semantic={semantic_count}"
    )
    font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = min(width - 16, bbox[2] - bbox[0] + 12)
    text_height = bbox[3] - bbox[1] + 10
    draw.rectangle((8, 8, 8 + text_width, 8 + text_height), fill=(0, 0, 0, 155))
    draw.text((14, 13), text, fill=(255, 255, 255, 245), font=font)


def _semantic_color(name: str) -> tuple[int, int, int, int]:
    if "eye" in name:
        return 80, 180, 255, 235
    if "brow" in name:
        return 180, 130, 255, 235
    if "mouth" in name or "lip" in name:
        return 255, 90, 90, 235
    if "nose" in name or "nostril" in name:
        return 255, 210, 70, 235
    if "chin" in name or "jaw" in name or "cheek" in name:
        return 70, 235, 150, 235
    return 255, 255, 255, 235


def _bbox_to_dict(bbox: tuple[int, int, int, int] | None) -> dict[str, int] | None:
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}
