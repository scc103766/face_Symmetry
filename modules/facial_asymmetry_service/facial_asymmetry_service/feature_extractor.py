from __future__ import annotations

import math
from typing import Any, Iterable, Mapping


LANDMARK = {
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

REGION_EDGES = {
    "lips": [
        (61, 146), (146, 91), (91, 181), (181, 84), (84, 17), (17, 314), (314, 405), (405, 321),
        (321, 375), (375, 291), (61, 185), (185, 40), (40, 39), (39, 37), (37, 0), (0, 267),
        (267, 269), (269, 270), (270, 409), (409, 291), (78, 95), (95, 88), (88, 178), (178, 87),
        (87, 14), (14, 317), (317, 402), (402, 318), (318, 324), (324, 308), (78, 191),
        (191, 80), (80, 81), (81, 82), (82, 13), (13, 312), (312, 311), (311, 310), (310, 415),
        (415, 308),
    ],
    "left_eye": [
        (263, 249), (249, 390), (390, 373), (373, 374), (374, 380), (380, 381), (381, 382),
        (382, 362), (263, 466), (466, 388), (388, 387), (387, 386), (386, 385), (385, 384),
        (384, 398), (398, 362),
    ],
    "right_eye": [
        (33, 7), (7, 163), (163, 144), (144, 145), (145, 153), (153, 154), (154, 155), (155, 133),
        (33, 246), (246, 161), (161, 160), (160, 159), (159, 158), (158, 157), (157, 173), (173, 133),
    ],
    "left_eyebrow": [(276, 283), (283, 282), (282, 295), (295, 285), (300, 293), (293, 334), (334, 296), (296, 336)],
    "right_eyebrow": [(46, 53), (53, 52), (52, 65), (65, 55), (70, 63), (63, 105), (105, 66), (66, 107)],
    "left_iris": [(474, 475), (475, 476), (476, 477), (477, 474)],
    "right_iris": [(469, 470), (470, 471), (471, 472), (472, 469)],
    "face_oval": [
        (10, 338), (338, 297), (297, 332), (332, 284), (284, 251), (251, 389), (389, 356),
        (356, 454), (454, 323), (323, 361), (361, 288), (288, 397), (397, 365), (365, 379),
        (379, 378), (378, 400), (400, 377), (377, 152), (152, 148), (148, 176), (176, 149),
        (149, 150), (150, 136), (136, 172), (172, 58), (58, 132), (132, 93), (93, 234),
        (234, 127), (127, 162), (162, 21), (21, 54), (54, 103), (103, 67), (67, 109), (109, 10),
    ],
}


def extract_features_from_detection(detection: Mapping[str, Any]) -> dict[str, float]:
    """Build the same MediaPipe-derived features used by the 62 rule."""

    features: dict[str, float] = {}
    raw_landmarks = detection.get("raw_landmarks") or []
    if isinstance(raw_landmarks, list) and len(raw_landmarks) >= 478:
        features.update(raw_landmark_features(raw_landmarks))
    blendshapes = detection.get("blendshapes") or {}
    if isinstance(blendshapes, Mapping):
        features.update(blendshape_features(blendshapes))
    matrices = detection.get("facial_transformation_matrixes") or []
    pose = detection.get("pose") or {}
    if isinstance(matrices, list) and isinstance(pose, Mapping):
        features.update(matrix_features(matrices, pose))
    return {
        name: value
        for name, value in sorted(features.items())
        if value is not None and math.isfinite(float(value))
    }


def raw_landmark_features(points: list[Mapping[str, Any]]) -> dict[str, float]:
    p = [(float(item["x"]), float(item["y"]), float(item.get("z", 0.0))) for item in points]
    scale = dist(p[LANDMARK["left_eye_outer"]], p[LANDMARK["right_eye_outer"]])
    if scale <= 1e-9:
        return {}
    midline = fitted_midline([p[LANDMARK["nose_bridge"]], p[LANDMARK["nose_tip"]], p[LANDMARK["chin"]]])
    signed = [signed_distance_2d(point, midline) / scale for point in p]

    features: dict[str, float] = {
        "raw_eye_distance": scale,
        "raw_mouth_corner_vertical_asym": abs(p[LANDMARK["left_mouth_corner"]][1] - p[LANDMARK["right_mouth_corner"]][1]) / scale,
        "raw_mouth_width": dist(p[LANDMARK["left_mouth_corner"]], p[LANDMARK["right_mouth_corner"]]) / scale,
        "raw_lip_opening": dist(p[LANDMARK["upper_lip_center"]], p[LANDMARK["lower_lip_center"]]) / scale,
        "raw_lip_midline_deviation": abs((signed[LANDMARK["upper_lip_center"]] + signed[LANDMARK["lower_lip_center"]]) / 2.0),
        "raw_nose_tip_midline_deviation": abs(signed[LANDMARK["nose_tip"]]),
        "raw_nostril_width_asym": abs(abs(signed[LANDMARK["left_nostril"]]) - abs(signed[LANDMARK["right_nostril"]])),
        "raw_cheek_width_asym": abs(abs(signed[LANDMARK["left_cheek"]]) - abs(signed[LANDMARK["right_cheek"]])),
        "raw_jaw_width_asym": abs(abs(signed[LANDMARK["left_jaw"]]) - abs(signed[LANDMARK["right_jaw"]])),
        "raw_eye_aperture_asym": abs(
            dist(p[LANDMARK["left_eye_upper"]], p[LANDMARK["left_eye_lower"]])
            - dist(p[LANDMARK["right_eye_upper"]], p[LANDMARK["right_eye_lower"]])
        )
        / scale,
        "raw_brow_inner_height_asym": abs(p[LANDMARK["left_brow_inner"]][1] - p[LANDMARK["right_brow_inner"]][1]) / scale,
        "raw_brow_outer_height_asym": abs(p[LANDMARK["left_brow_outer"]][1] - p[LANDMARK["right_brow_outer"]][1]) / scale,
    }

    features.update(pair_region_features("raw_eye_region", p, region_indices("left_eye"), region_indices("right_eye"), scale))
    features.update(pair_region_features("raw_eyebrow_region", p, region_indices("left_eyebrow"), region_indices("right_eyebrow"), scale))
    features.update(pair_region_features("raw_iris_region", p, region_indices("left_iris"), region_indices("right_iris"), scale))
    features.update(split_region_features("raw_lip_region", p, region_indices("lips"), signed, scale))
    features.update(split_region_features("raw_face_oval_region", p, region_indices("face_oval"), signed, scale))
    features.update(split_region_features("raw_all_mesh_region", p, range(len(p)), signed, scale))
    return features


def region_indices(name: str) -> list[int]:
    output: set[int] = set()
    for left, right in REGION_EDGES[name]:
        output.add(left)
        output.add(right)
    return sorted(output)


def pair_region_features(
    prefix: str,
    points: list[tuple[float, float, float]],
    left: Iterable[int],
    right: Iterable[int],
    scale: float,
) -> dict[str, float]:
    left_stats = point_stats([points[index] for index in left])
    right_stats = point_stats([points[index] for index in right])
    return {
        f"{prefix}_width_asym": ratio_abs_diff(left_stats["width"], right_stats["width"]),
        f"{prefix}_height_asym": ratio_abs_diff(left_stats["height"], right_stats["height"]),
        f"{prefix}_area_asym": ratio_abs_diff(left_stats["area"], right_stats["area"]),
        f"{prefix}_centroid_y_asym": abs(left_stats["cy"] - right_stats["cy"]) / scale,
        f"{prefix}_centroid_z_asym": abs(left_stats["cz"] - right_stats["cz"]) / scale,
        f"{prefix}_point_spread_asym": ratio_abs_diff(left_stats["spread"], right_stats["spread"]),
    }


def split_region_features(
    prefix: str,
    points: list[tuple[float, float, float]],
    indices: Iterable[int],
    signed: list[float],
    scale: float,
) -> dict[str, float]:
    left = [points[index] for index in indices if signed[index] > 0]
    right = [points[index] for index in indices if signed[index] < 0]
    if not left or not right:
        return {}
    left_stats = point_stats(left)
    right_stats = point_stats(right)
    return {
        f"{prefix}_width_asym": ratio_abs_diff(left_stats["width"], right_stats["width"]),
        f"{prefix}_height_asym": ratio_abs_diff(left_stats["height"], right_stats["height"]),
        f"{prefix}_area_asym": ratio_abs_diff(left_stats["area"], right_stats["area"]),
        f"{prefix}_centroid_y_asym": abs(left_stats["cy"] - right_stats["cy"]) / scale,
        f"{prefix}_centroid_z_asym": abs(left_stats["cz"] - right_stats["cz"]) / scale,
        f"{prefix}_point_spread_asym": ratio_abs_diff(left_stats["spread"], right_stats["spread"]),
    }


def point_stats(points: list[tuple[float, float, float]]) -> dict[str, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    cz = sum(zs) / len(zs)
    spread = sum(math.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) for x, y, z in points) / len(points)
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    return {"cx": cx, "cy": cy, "cz": cz, "width": width, "height": height, "area": width * height, "spread": spread}


def blendshape_features(blendshapes: Mapping[str, Any]) -> dict[str, float]:
    features: dict[str, float] = {}
    values = {str(name): float(value) for name, value in blendshapes.items()}
    for name, value in values.items():
        features["bs_" + safe_name(name)] = value

    paired_abs: list[float] = []
    mouth_abs: list[float] = []
    eye_abs: list[float] = []
    brow_abs: list[float] = []
    cheek_abs: list[float] = []
    nose_abs: list[float] = []
    for name, left_value in values.items():
        if not name.endswith("Left"):
            continue
        base = name[:-4]
        right_name = base + "Right"
        if right_name not in values:
            continue
        diff = left_value - values[right_name]
        abs_diff = abs(diff)
        key = "bsdiff_" + safe_name(base)
        features[key + "_signed_left_minus_right"] = diff
        features[key + "_abs"] = abs_diff
        paired_abs.append(abs_diff)
        target = (
            mouth_abs if base.startswith("mouth") else
            eye_abs if base.startswith("eye") else
            brow_abs if base.startswith("brow") else
            cheek_abs if base.startswith("cheek") else
            nose_abs if base.startswith("nose") else
            None
        )
        if target is not None:
            target.append(abs_diff)

    if "mouthLeft" in values and "mouthRight" in values:
        features["bsdiff_mouth_lateral_abs"] = abs(values["mouthLeft"] - values["mouthRight"])
    if "jawLeft" in values and "jawRight" in values:
        features["bsdiff_jaw_lateral_abs"] = abs(values["jawLeft"] - values["jawRight"])
    aggregate = {
        "bsdiff_all_mean_abs": paired_abs,
        "bsdiff_mouth_mean_abs": mouth_abs,
        "bsdiff_eye_mean_abs": eye_abs,
        "bsdiff_brow_mean_abs": brow_abs,
        "bsdiff_cheek_mean_abs": cheek_abs,
        "bsdiff_nose_mean_abs": nose_abs,
    }
    for name, values_list in aggregate.items():
        if values_list:
            features[name] = sum(values_list) / len(values_list)
            features[name.replace("mean", "max")] = max(values_list)
    return features


def matrix_features(matrices: list[Any], pose: Mapping[str, Any]) -> dict[str, float]:
    features: dict[str, float] = {}
    if pose:
        for key in ("yaw", "pitch", "roll"):
            if key in pose:
                value = float(pose[key])
                features[f"pose_{key}_deg"] = value
                features[f"pose_{key}_abs_deg"] = abs(value)
    if not matrices:
        return features
    matrix = matrices[0]
    if len(matrix) < 4 or len(matrix[0]) < 4:
        return features
    m = [[float(value) for value in row] for row in matrix]
    for i in range(4):
        for j in range(4):
            features[f"matrix_m{i}{j}"] = m[i][j]
    features["matrix_tx"] = m[0][3]
    features["matrix_ty"] = m[1][3]
    features["matrix_tz"] = m[2][3]
    features["matrix_abs_tx"] = abs(m[0][3])
    features["matrix_abs_ty"] = abs(m[1][3])
    features["matrix_abs_tz"] = abs(m[2][3])

    cols = [[m[0][i], m[1][i], m[2][i]] for i in range(3)]
    scales = [math.sqrt(sum(value * value for value in col)) for col in cols]
    for index, scale in enumerate(scales):
        features[f"matrix_scale_{index}"] = scale
    if all(scale > 1e-9 for scale in scales):
        r = [[m[row][col] / scales[col] for col in range(3)] for row in range(3)]
        features["matrix_roll_abs_deg"] = abs(math.degrees(math.atan2(r[1][0], r[0][0])))
        features["matrix_pitch_abs_deg"] = abs(math.degrees(math.atan2(-r[2][0], math.sqrt(r[2][1] ** 2 + r[2][2] ** 2))))
        features["matrix_yaw_abs_deg"] = abs(math.degrees(math.atan2(r[2][1], r[2][2])))
    return features


def safe_name(name: str) -> str:
    return name.strip("_").replace("-", "_")


def dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def fitted_midline(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    theta = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    dx = math.cos(theta)
    dy = math.sin(theta)
    a = -dy
    b = dx
    c = -(a * mx + b * my)
    norm = math.sqrt(a * a + b * b)
    return a / norm, b / norm, c / norm


def signed_distance_2d(point: tuple[float, float, float], line: tuple[float, float, float]) -> float:
    a, b, c = line
    return a * point[0] + b * point[1] + c


def ratio_abs_diff(a: float, b: float) -> float:
    denom = abs(a) + abs(b)
    if denom <= 1e-12:
        return 0.0
    return abs(a - b) / denom
