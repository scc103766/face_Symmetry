#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119"

CORE_ROLES = ("front", "smile", "teeth", "eyes_closed", "forehead_wrinkle", "frown")

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
    "nose": [
        (168, 6), (6, 197), (197, 195), (195, 5), (5, 4), (4, 1), (1, 19), (19, 94), (94, 2),
        (98, 97), (97, 2), (2, 326), (326, 327), (327, 294), (294, 278), (278, 344),
        (344, 440), (440, 275), (275, 4), (4, 45), (45, 220), (220, 115), (115, 48),
        (48, 64), (64, 98),
    ],
}


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    metadata = dataset / "metadata"
    reports = dataset / "reports"

    keypoint_rows = read_csv(metadata / "03_keypoints.csv")
    feature_rows = extract_rows(dataset, keypoint_rows)
    write_csv(metadata / "09_mediapipe_full_features.csv", feature_rows)

    diff_rows = summarize_differences(feature_rows)
    write_csv(metadata / "09_mediapipe_feature_differences.csv", diff_rows)

    summary = build_summary(feature_rows, diff_rows, dataset.name)
    write_json(metadata / "09_mediapipe_feature_differences_summary.json", summary)
    write_report(reports / "09_mediapipe_full_feature_differences.md", summary, diff_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze disease/non-disease feature differences from full MediaPipe V1 outputs.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="FaceSymAi V1 dataset root.")
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    fixed = [
        "sample_id",
        "patient_sample_id",
        "label_group",
        "label_binary",
        "media_role",
        "detection_status",
        "feature_name",
        "role",
    ]
    fields = [field for field in fixed if field in fields] + [field for field in fields if field not in fixed]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def extract_rows(dataset: Path, keypoint_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in keypoint_rows:
        if row.get("detection_status") != "detected" or not row.get("keypoints_path"):
            continue
        payload = json.loads((dataset / row["keypoints_path"]).read_text(encoding="utf-8"))
        detection = payload.get("detection") or {}
        sample = payload.get("sample") or {}
        raw_landmarks = detection.get("raw_landmarks") or []
        blendshapes = detection.get("blendshapes") or {}
        matrices = detection.get("facial_transformation_matrixes") or []
        if len(raw_landmarks) < 478:
            continue

        features: dict[str, float] = {}
        features.update(raw_landmark_features(raw_landmarks))
        features.update(blendshape_features(blendshapes))
        features.update(matrix_features(matrices, detection.get("pose") or {}))

        output: dict[str, Any] = {
            "sample_id": row["sample_id"],
            "patient_sample_id": row["patient_sample_id"],
            "label_group": row["label_group"],
            "label_binary": row.get("label_binary") or sample.get("label_binary") or label_binary(row["label_group"]),
            "media_role": row["media_role"],
            "detection_status": row["detection_status"],
        }
        output.update({name: fmt(value) for name, value in sorted(features.items()) if value is not None and math.isfinite(value)})
        rows.append(output)
    return rows


def label_binary(label_group: str) -> str:
    if label_group == "患病":
        return "1"
    if label_group == "不患病":
        return "0"
    return ""


def raw_landmark_features(points: list[dict[str, float]]) -> dict[str, float]:
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


def pair_region_features(prefix: str, points: list[tuple[float, float, float]], left: Iterable[int], right: Iterable[int], scale: float) -> dict[str, float]:
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


def blendshape_features(blendshapes: dict[str, Any]) -> dict[str, float]:
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


def matrix_features(matrices: list[Any], pose: dict[str, Any]) -> dict[str, float]:
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
    # Least-squares 2D line ax + by + c = 0 through nose bridge, nose tip and chin.
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
    # Normal vector.
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


def summarize_differences(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_names = sorted(
        key for key in rows[0]
        if key not in {"sample_id", "patient_sample_id", "label_group", "label_binary", "media_role", "detection_status"}
    )
    output: list[dict[str, Any]] = []
    roles = ["all", *sorted({str(row["media_role"]) for row in rows})]
    for role in roles:
        role_rows = rows if role == "all" else [row for row in rows if row["media_role"] == role]
        if role not in {"all", *CORE_ROLES}:
            continue
        for feature_name in feature_names:
            pos = [float(row[feature_name]) for row in role_rows if row.get("label_binary") == "1" and row.get(feature_name) not in {"", None}]
            neg = [float(row[feature_name]) for row in role_rows if row.get("label_binary") == "0" and row.get(feature_name) not in {"", None}]
            if len(pos) < 10 or len(neg) < 10:
                continue
            pos_stats = summary_stats(pos)
            neg_stats = summary_stats(neg)
            effect = cohens_d(pos, neg)
            score_auc = auc(pos, neg)
            output.append(
                {
                    "role": role,
                    "feature_name": feature_name,
                    "positive_n": len(pos),
                    "negative_n": len(neg),
                    "positive_mean": fmt(pos_stats["mean"]),
                    "negative_mean": fmt(neg_stats["mean"]),
                    "mean_diff_positive_minus_negative": fmt(pos_stats["mean"] - neg_stats["mean"]),
                    "positive_median": fmt(pos_stats["median"]),
                    "negative_median": fmt(neg_stats["median"]),
                    "cohens_d": fmt(effect),
                    "auc_positive_higher": fmt(score_auc),
                    "separation_auc": fmt(max(score_auc, 1.0 - score_auc)),
                    "direction": "患病更高" if pos_stats["mean"] > neg_stats["mean"] else "不患病更高",
                }
            )
    return sorted(output, key=lambda row: (row["role"], -float(row["separation_auc"]), -abs(float(row["cohens_d"])), row["feature_name"]))


def summary_stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "mean": sum(values) / len(values),
        "median": percentile(ordered, 0.5),
        "sd": math.sqrt(sum((value - sum(values) / len(values)) ** 2 for value in values) / len(values)),
    }


def percentile(ordered: list[float], q: float) -> float:
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def cohens_d(pos: list[float], neg: list[float]) -> float:
    pos_mean = sum(pos) / len(pos)
    neg_mean = sum(neg) / len(neg)
    pos_sd = math.sqrt(sum((value - pos_mean) ** 2 for value in pos) / len(pos))
    neg_sd = math.sqrt(sum((value - neg_mean) ** 2 for value in neg) / len(neg))
    pooled = math.sqrt((pos_sd * pos_sd + neg_sd * neg_sd) / 2.0)
    if pooled <= 1e-12:
        return 0.0
    return (pos_mean - neg_mean) / pooled


def auc(pos: list[float], neg: list[float]) -> float:
    combined = sorted([(value, 1) for value in pos] + [(value, 0) for value in neg], key=lambda item: item[0])
    ranks: list[tuple[float, int]] = []
    index = 0
    while index < len(combined):
        end = index + 1
        while end < len(combined) and combined[end][0] == combined[index][0]:
            end += 1
        avg_rank = (index + 1 + end) / 2.0
        for item_index in range(index, end):
            ranks.append((avg_rank, combined[item_index][1]))
        index = end
    rank_sum_pos = sum(rank for rank, label in ranks if label == 1)
    n_pos = len(pos)
    n_neg = len(neg)
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def build_summary(feature_rows: list[dict[str, Any]], diff_rows: list[dict[str, Any]], dataset_name: str) -> dict[str, Any]:
    counts: dict[str, int] = defaultdict(int)
    for row in feature_rows:
        counts["images"] += 1
        counts[f"label/{row['label_group']}"] += 1
        counts[f"role/{row['media_role']}"] += 1
        counts[f"label_role/{row['label_group']}/{row['media_role']}"] += 1
    strongest_by_role: dict[str, list[dict[str, Any]]] = {}
    for role in ["all", *CORE_ROLES]:
        rows = [row for row in diff_rows if row["role"] == role]
        strongest_by_role[role] = rows[:20]
    return {
        "dataset": dataset_name,
        "feature_rows": len(feature_rows),
        "feature_columns": len(feature_rows[0]) if feature_rows else 0,
        "counts": dict(sorted(counts.items())),
        "strongest_by_role": strongest_by_role,
        "warning": "Outcome labels are patient-level disease labels, not direct facial-asymmetry labels. Differences indicate weak association, not diagnostic performance.",
    }


def write_report(path: Path, summary: dict[str, Any], diff_rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 09 MediaPipe 全量输出特征差异分析",
        "",
        f"分析对象：`datasets/{summary['dataset']}`",
        "",
        "## 结论",
        "",
        "当前 V1 需要明确：人脸对称性与 `患病/不患病` 是弱关联，而不是一一对应。患病组整体上存在更高的不对称倾向，但当前 patient outcome 标签不是直接面瘫或人脸不对称标签，因此这些差异只能作为特征发现和后续标注/建模依据。",
        "",
        "本轮分析从现有 MediaPipe Face Landmarker 输出中抽取：",
        "",
        "- `478` 个 raw landmarks 的区域几何和左右不对称特征。",
        "- `52` 个 blendshape 原始分数和 Left/Right 配对差异。",
        "- `1` 个 facial transformation matrix 的位移、尺度和近似姿态特征。",
        "",
        "## 产物",
        "",
        "- Image-level feature rows: `metadata/09_mediapipe_full_features.csv`",
        "- Feature difference summary: `metadata/09_mediapipe_feature_differences.csv`",
        "- JSON summary: `metadata/09_mediapipe_feature_differences_summary.json`",
        "",
        "## 样本覆盖",
        "",
        f"- Feature-ready detected images: `{summary['feature_rows']}`",
        f"- Feature columns: `{summary['feature_columns']}`",
        f"- Counts: `{json.dumps(summary['counts'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## 差异最强特征",
        "",
    ]
    for role in ["all", *CORE_ROLES]:
        rows = [row for row in diff_rows if row["role"] == role][:12]
        lines.append(f"### role = `{role}`")
        lines.append("")
        lines.extend(markdown_table(
            ["feature", "direction", "pos_mean", "neg_mean", "diff", "d", "auc", "sep_auc"],
            [
                [
                    row["feature_name"],
                    row["direction"],
                    row["positive_mean"],
                    row["negative_mean"],
                    row["mean_diff_positive_minus_negative"],
                    row["cohens_d"],
                    row["auc_positive_higher"],
                    row["separation_auc"],
                ]
                for row in rows
            ],
        ))
        lines.append("")
    lines.extend(
        [
            "## 排除姿态/尺度后的对称性候选特征",
            "",
            "上表中的 matrix 平移、`raw_eye_distance` 等特征更多反映采集距离、脸框尺度或姿态差异，应优先作为质量/姿态控制变量。下面只保留 `raw_*asym/deviation` 和 `bsdiff_*` 这类更接近人脸左右差异的候选特征。",
            "",
        ]
    )
    for role in ["all", *CORE_ROLES]:
        rows = [row for row in diff_rows if row["role"] == role and is_asymmetry_candidate(row["feature_name"])][:12]
        lines.append(f"### asymmetry candidates, role = `{role}`")
        lines.append("")
        lines.extend(markdown_table(
            ["feature", "direction", "pos_mean", "neg_mean", "diff", "d", "auc", "sep_auc"],
            [
                [
                    row["feature_name"],
                    row["direction"],
                    row["positive_mean"],
                    row["negative_mean"],
                    row["mean_diff_positive_minus_negative"],
                    row["cohens_d"],
                    row["auc_positive_higher"],
                    row["separation_auc"],
                ]
                for row in rows
            ],
        ))
        lines.append("")
    lines.extend(
        [
            "## 特征使用建议",
            "",
            "1. `blendshape` 差异更适合表达动态表情控制差异，尤其是 smile/teeth 中的口部、眼部和眉部 Left/Right 配对差。",
            "2. `raw_landmarks` 应优先用于区域化几何差异：嘴唇、眼裂、眉毛、脸颊/下颌、鼻唇沟和中线偏移，而不是只保留 25 个语义点。",
            "3. `transformation matrix` 和 pose 类特征应首先作为质量/姿态控制变量，避免 yaw/roll/translation 差异被模型误学成疾病差异。",
            "4. 后续 V1.1 建议把这些候选特征与人工不对称标注对齐，再筛选稳定单调的特征进入主评分。",
            "",
            "## 注意",
            "",
            "这些统计是基于 patient outcome 标签的弱关联分析。若某些 matrix/pose 或表情强度特征显示较大差异，必须先判断它是采集姿态、role 执行差异，还是实际面部运动差异，不能直接解释为疾病因果特征。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def is_asymmetry_candidate(feature_name: str) -> bool:
    if feature_name.startswith("bsdiff_"):
        return True
    return feature_name.startswith("raw_") and ("asym" in feature_name or "deviation" in feature_name)


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        output.append("| " + " | ".join(str(value) for value in row) + " |")
    return output


def fmt(value: float) -> str:
    return f"{value:.6f}"


if __name__ == "__main__":
    main()
