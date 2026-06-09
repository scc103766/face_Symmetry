#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.landmarks import MediaPipeFaceLandmarkerDetector  # noqa: E402
from scripts.analyze_v1_mediapipe_full_feature_differences import (  # noqa: E402
    auc,
    blendshape_features,
    cohens_d,
    fmt,
    matrix_features,
    raw_landmark_features,
    summary_stats,
)


DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "stroke_warning_app_rule_test_set_20260508"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"
DEFAULT_FACE_ROLES = ("front_contour", "smile_teeth", "eyes_right")
AGGREGATIONS = ("max", "mean")

EVIDENCE_FEATURES = {
    "bsdiff_mouthFrown_abs": "图片患病更高主证据：口部 frown blendshape 左右差",
    "raw_all_mesh_region_point_spread_asym": "图片患病更高主证据：全脸 478 点左右点云离散差",
    "bsdiff_mouth_abs": "图片患病更高主证据：口部 lateral blendshape 左右差",
    "raw_lip_midline_deviation": "图片患病更高主证据：唇中线偏移",
    "raw_mouth_corner_vertical_asym": "图片患病更高主证据：口角垂直高低差",
}

KEYPOINT_FIELDS = [
    "sample_id",
    "patient_sample_id",
    "patient_id",
    "label_group",
    "label_binary",
    "record_id",
    "media_id",
    "media_role",
    "source_excel_row",
    "detection_status",
    "face_count",
    "raw_landmarks",
    "blendshapes",
    "transformation_matrixes",
    "keypoints_path",
    "error",
]

PATIENT_FEATURE_FIELDS = [
    "patient_sample_id",
    "patient_id",
    "label_group",
    "label_binary",
    "role_scope",
    "aggregation",
    "image_count",
    *EVIDENCE_FEATURES.keys(),
]

VALIDATION_FIELDS = [
    "level",
    "role_scope",
    "aggregation",
    "feature_name",
    "evidence_group",
    "expected_direction",
    "positive_n",
    "negative_n",
    "positive_mean",
    "negative_mean",
    "mean_diff_positive_minus_negative",
    "positive_median",
    "negative_median",
    "cohens_d",
    "auc_positive_higher",
    "direction_matches_expected",
    "support_status",
]


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    roles = parse_roles(args.roles)
    media_rows = selected_media_rows(dataset, roles, args.limit)
    keypoint_rows, image_feature_rows = collect_or_load_features(dataset, media_rows, args)
    patient_feature_rows = build_patient_feature_rows(image_feature_rows, roles)
    validation_rows = build_validation_rows(image_feature_rows, patient_feature_rows, roles)
    summary = build_summary(dataset, roles, media_rows, keypoint_rows, image_feature_rows, patient_feature_rows, validation_rows)

    metadata = dataset / "metadata"
    reports = dataset / "reports"
    write_csv(metadata / "40_mediapipe_evidence_keypoints.csv", keypoint_rows, KEYPOINT_FIELDS)
    write_csv(metadata / "40_mediapipe_evidence_image_features.csv", image_feature_rows)
    write_csv(metadata / "40_mediapipe_evidence_patient_features.csv", patient_feature_rows, PATIENT_FEATURE_FIELDS)
    write_csv(metadata / "40_mediapipe_evidence_feature_validation.csv", validation_rows, VALIDATION_FIELDS)
    write_json(metadata / "40_mediapipe_evidence_validation_summary.json", summary)
    write_report(reports / "40_mediapipe_evidence_feature_validation.md", summary, validation_rows)

    print(f"Wrote {metadata / '40_mediapipe_evidence_keypoints.csv'}")
    print(f"Wrote {metadata / '40_mediapipe_evidence_image_features.csv'}")
    print(f"Wrote {metadata / '40_mediapipe_evidence_patient_features.csv'}")
    print(f"Wrote {metadata / '40_mediapipe_evidence_feature_validation.csv'}")
    print(f"Wrote {metadata / '40_mediapipe_evidence_validation_summary.json'}")
    print(f"Wrote {reports / '40_mediapipe_evidence_feature_validation.md'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate documented MediaPipe evidence features on the rule-labeled app test set.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Rule-labeled app test set root.")
    parser.add_argument("--roles", default=",".join(DEFAULT_FACE_ROLES), help="Comma-separated image roles to evaluate.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="MediaPipe Face Landmarker .task model.")
    parser.add_argument("--max-faces", type=int, default=1, help="Maximum faces to detect.")
    parser.add_argument("--force", action="store_true", help="Re-run MediaPipe even when a cached keypoint JSON exists.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N selected images.")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N images.")
    return parser.parse_args()


def parse_roles(value: str) -> tuple[str, ...]:
    roles = tuple(item.strip() for item in value.split(",") if item.strip())
    return roles or DEFAULT_FACE_ROLES


def selected_media_rows(dataset: Path, roles: tuple[str, ...], limit: int | None) -> list[dict[str, str]]:
    rows = [
        row
        for row in read_csv(dataset / "metadata" / "media_index.csv")
        if row.get("media_type") == "image" and row.get("media_role") in roles
    ]
    rows = [row for row in rows if (dataset / row.get("organized_path", "")).exists()]
    return rows[:limit] if limit is not None else rows


def collect_or_load_features(
    dataset: Path,
    media_rows: list[Mapping[str, str]],
    args: argparse.Namespace,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    keypoint_rows: list[dict[str, str]] = []
    feature_rows: list[dict[str, str]] = []
    detector: MediaPipeFaceLandmarkerDetector | None = None
    try:
        if any(args.force or not cached_keypoint_path(dataset, row).exists() for row in media_rows):
            detector = MediaPipeFaceLandmarkerDetector(
                args.model,
                max_num_faces=max(1, args.max_faces),
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            )
        for index, media in enumerate(media_rows, start=1):
            keypoint_row, detection = load_or_detect(dataset, media, detector, force=args.force)
            keypoint_rows.append(keypoint_row)
            if detection:
                feature_rows.append(image_feature_row(media, keypoint_row, detection))
            if args.progress_every and (index % args.progress_every == 0 or index == len(media_rows)):
                print(f"evidence validation progress: {index}/{len(media_rows)}", flush=True)
    finally:
        if detector is not None:
            detector.close()
    return keypoint_rows, feature_rows


def load_or_detect(
    dataset: Path,
    media: Mapping[str, str],
    detector: MediaPipeFaceLandmarkerDetector | None,
    *,
    force: bool,
) -> tuple[dict[str, str], dict[str, Any] | None]:
    sample_id = sample_id_for(media)
    keypoints_path = cached_keypoint_path(dataset, media)
    if keypoints_path.exists() and not force:
        payload = json.loads(keypoints_path.read_text(encoding="utf-8"))
        detection = payload.get("detection") or {}
        return keypoint_row(media, sample_id, "detected", keypoints_path.relative_to(dataset), detection, ""), detection

    if detector is None:
        raise RuntimeError("Detector was not initialized for an uncached sample.")
    try:
        detection_obj = detector.detect_image_path(dataset / media["organized_path"], image_id=sample_id)
        if detection_obj is None:
            return keypoint_row(media, sample_id, "no_face", None, {}, ""), None
        detection = detection_obj.to_dict()
        payload = {"sample": sample_payload(media, sample_id), "detection": detection}
        keypoints_path.parent.mkdir(parents=True, exist_ok=True)
        keypoints_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return keypoint_row(media, sample_id, "detected", keypoints_path.relative_to(dataset), detection, ""), detection
    except Exception as exc:  # noqa: BLE001 - keep per-image failure visible in metadata.
        return keypoint_row(media, sample_id, "failed", None, {}, f"{type(exc).__name__}: {exc}"), None


def sample_id_for(media: Mapping[str, str]) -> str:
    return "__".join(
        clean_part(part)
        for part in (
            media.get("patient_sample_id", ""),
            media.get("media_role", ""),
            media.get("media_id", ""),
        )
        if part
    )


def cached_keypoint_path(dataset: Path, media: Mapping[str, str]) -> Path:
    return (
        dataset
        / "keypoints"
        / "40_mediapipe_evidence"
        / clean_part(media.get("label_group", "unlabeled"))
        / clean_part(media.get("patient_sample_id", "patient"))
        / f"{sample_id_for(media)}.json"
    )


def clean_part(value: str) -> str:
    text = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value).strip())
    return text.strip("._") or "unknown"


def sample_payload(media: Mapping[str, str], sample_id: str) -> dict[str, str]:
    return {
        "sample_id": sample_id,
        "patient_sample_id": media.get("patient_sample_id", ""),
        "patient_id": media.get("patient_id", ""),
        "label_group": media.get("label_group", ""),
        "label_binary": media.get("label_binary", ""),
        "record_id": media.get("record_id", ""),
        "media_id": media.get("media_id", ""),
        "media_role": media.get("media_role", ""),
        "source_excel_row": media.get("source_excel_row", ""),
        "organized_path": media.get("organized_path", ""),
        "source_media_path": media.get("source_media_path", ""),
    }


def keypoint_row(
    media: Mapping[str, str],
    sample_id: str,
    status: str,
    relative_keypoints_path: Path | None,
    detection: Mapping[str, Any],
    error: str,
) -> dict[str, str]:
    return {
        "sample_id": sample_id,
        "patient_sample_id": media.get("patient_sample_id", ""),
        "patient_id": media.get("patient_id", ""),
        "label_group": media.get("label_group", ""),
        "label_binary": media.get("label_binary", ""),
        "record_id": media.get("record_id", ""),
        "media_id": media.get("media_id", ""),
        "media_role": media.get("media_role", ""),
        "source_excel_row": media.get("source_excel_row", ""),
        "detection_status": status,
        "face_count": str(detection.get("face_count", "")),
        "raw_landmarks": str(len(detection.get("raw_landmarks") or [])),
        "blendshapes": str(len(detection.get("blendshapes") or {})),
        "transformation_matrixes": str(len(detection.get("facial_transformation_matrixes") or [])),
        "keypoints_path": "" if relative_keypoints_path is None else relative_keypoints_path.as_posix(),
        "error": error,
    }


def image_feature_row(media: Mapping[str, str], keypoint: Mapping[str, str], detection: Mapping[str, Any]) -> dict[str, str]:
    features: dict[str, float] = {}
    raw_landmarks = detection.get("raw_landmarks") or []
    if len(raw_landmarks) >= 478:
        features.update(raw_landmark_features(raw_landmarks))
    features.update(blendshape_features(detection.get("blendshapes") or {}))
    features.update(matrix_features(detection.get("facial_transformation_matrixes") or [], detection.get("pose") or {}))
    row = {
        "sample_id": keypoint["sample_id"],
        "patient_sample_id": media.get("patient_sample_id", ""),
        "patient_id": media.get("patient_id", ""),
        "label_group": media.get("label_group", ""),
        "label_binary": media.get("label_binary", ""),
        "record_id": media.get("record_id", ""),
        "media_id": media.get("media_id", ""),
        "media_role": media.get("media_role", ""),
        "source_excel_row": media.get("source_excel_row", ""),
        "detection_status": keypoint["detection_status"],
    }
    row.update({name: fmt(value) for name, value in sorted(features.items()) if math.isfinite(value)})
    return row


def build_patient_feature_rows(feature_rows: list[Mapping[str, str]], roles: tuple[str, ...]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for role_scope in ("all", *roles):
        scoped_rows = feature_rows if role_scope == "all" else [row for row in feature_rows if row.get("media_role") == role_scope]
        grouped: dict[str, list[Mapping[str, str]]] = defaultdict(list)
        for row in scoped_rows:
            grouped[row["patient_sample_id"]].append(row)
        for aggregation in AGGREGATIONS:
            for patient_sample_id, rows in sorted(grouped.items()):
                first = rows[0]
                values = {
                    feature: aggregate([to_float(row.get(feature, "")) for row in rows], aggregation)
                    for feature in EVIDENCE_FEATURES
                }
                output.append(
                    {
                        "patient_sample_id": patient_sample_id,
                        "patient_id": first.get("patient_id", ""),
                        "label_group": first.get("label_group", ""),
                        "label_binary": first.get("label_binary", ""),
                        "role_scope": role_scope,
                        "aggregation": aggregation,
                        "image_count": str(len(rows)),
                        **{feature: "" if value is None else fmt(value) for feature, value in values.items()},
                    }
                )
    return output


def aggregate(values: Iterable[float | None], aggregation: str) -> float | None:
    clean = [value for value in values if value is not None and math.isfinite(value)]
    if not clean:
        return None
    if aggregation == "max":
        return max(clean)
    if aggregation == "mean":
        return sum(clean) / len(clean)
    raise ValueError(f"Unsupported aggregation: {aggregation}")


def to_float(value: str | None) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def build_validation_rows(
    image_feature_rows: list[Mapping[str, str]],
    patient_feature_rows: list[Mapping[str, str]],
    roles: tuple[str, ...],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for role_scope in ("all", *roles):
        image_rows = image_feature_rows if role_scope == "all" else [row for row in image_feature_rows if row.get("media_role") == role_scope]
        rows.extend(validation_for_rows("image", role_scope, "none", image_rows))
    for role_scope in ("all", *roles):
        for aggregation in AGGREGATIONS:
            scoped = [
                row
                for row in patient_feature_rows
                if row.get("role_scope") == role_scope and row.get("aggregation") == aggregation
            ]
            rows.extend(validation_for_rows("patient", role_scope, aggregation, scoped))
    return rows


def validation_for_rows(level: str, role_scope: str, aggregation: str, rows: list[Mapping[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for feature_name, evidence_group in EVIDENCE_FEATURES.items():
        pos = [float(row[feature_name]) for row in rows if row.get("label_binary") == "1" and row.get(feature_name) not in {"", None}]
        neg = [float(row[feature_name]) for row in rows if row.get("label_binary") == "0" and row.get(feature_name) not in {"", None}]
        if len(pos) < 5 or len(neg) < 5:
            continue
        pos_stats = summary_stats(pos)
        neg_stats = summary_stats(neg)
        score_auc = auc(pos, neg)
        direction_matches = pos_stats["mean"] > neg_stats["mean"]
        output.append(
            {
                "level": level,
                "role_scope": role_scope,
                "aggregation": aggregation,
                "feature_name": feature_name,
                "evidence_group": evidence_group,
                "expected_direction": "患病更高",
                "positive_n": str(len(pos)),
                "negative_n": str(len(neg)),
                "positive_mean": fmt(pos_stats["mean"]),
                "negative_mean": fmt(neg_stats["mean"]),
                "mean_diff_positive_minus_negative": fmt(pos_stats["mean"] - neg_stats["mean"]),
                "positive_median": fmt(pos_stats["median"]),
                "negative_median": fmt(neg_stats["median"]),
                "cohens_d": fmt(cohens_d(pos, neg)),
                "auc_positive_higher": fmt(score_auc),
                "direction_matches_expected": "true" if direction_matches else "false",
                "support_status": support_status(direction_matches, score_auc),
            }
        )
    return output


def support_status(direction_matches: bool, score_auc: float) -> str:
    if direction_matches and score_auc >= 0.60:
        return "strong_supported"
    if direction_matches and score_auc >= 0.55:
        return "supported"
    if direction_matches and score_auc > 0.50:
        return "weak_supported"
    return "not_supported"


def build_summary(
    dataset: Path,
    roles: tuple[str, ...],
    media_rows: list[Mapping[str, str]],
    keypoint_rows: list[Mapping[str, str]],
    image_feature_rows: list[Mapping[str, str]],
    patient_feature_rows: list[Mapping[str, str]],
    validation_rows: list[Mapping[str, str]],
) -> dict[str, Any]:
    primary_rows = [
        row
        for row in validation_rows
        if row["level"] == "patient" and row["role_scope"] == "all" and row["aggregation"] == "max"
    ]
    supported = [row for row in primary_rows if row["support_status"] in {"strong_supported", "supported", "weak_supported"}]
    return {
        "dataset": dataset.as_posix(),
        "roles_evaluated": list(roles),
        "source_label_policy": "患病 requires the same record to satisfy 风险等级=紧急风险 AND prior stroke positive AND family stroke positive; 不患病 requires low risk and all indicators normal.",
        "selected_image_count": len(media_rows),
        "detected_image_count": len(image_feature_rows),
        "patient_feature_row_count": len(patient_feature_rows),
        "detection_status": dict(sorted(Counter(row["detection_status"] for row in keypoint_rows).items())),
        "detected_by_label": dict(sorted(Counter(row["label_group"] for row in image_feature_rows).items())),
        "detected_by_role": dict(sorted(Counter(row["media_role"] for row in image_feature_rows).items())),
        "primary_level": "patient",
        "primary_role_scope": "all",
        "primary_aggregation": "max",
        "primary_supported_feature_count": len(supported),
        "primary_total_feature_count": len(primary_rows),
        "primary_support_rate": 0.0 if not primary_rows else len(supported) / len(primary_rows),
        "primary_rows": primary_rows,
        "warning": "This validates weak association on a rule-labeled test set. It supports feature usefulness when direction/AUC hold, but it is not clinical causality proof.",
    }


def write_report(path: Path, summary: Mapping[str, Any], validation_rows: list[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    primary_rows = list(summary["primary_rows"])
    supported = [row for row in primary_rows if row["support_status"] in {"strong_supported", "supported", "weak_supported"}]
    lines = [
        "# 40 MediaPipe 主证据特征在规则测试集上的有效性验证",
        "",
        f"测试集：`{summary['dataset']}`",
        "",
        "## 验证口径",
        "",
        "- 患病标签：同一条记录同时满足 `风险等级=紧急风险`、`曾经得过中风=是`、`家人得过脑卒中=有`。",
        "- 不患病标签：无阳性记录，且至少一条 `低风险` 全指标正常记录。",
        f"- 验证 role：`{', '.join(summary['roles_evaluated'])}`。",
        "- 主判断：患者级 `all` role 的 `max` 聚合，避免把同一患者多图当成独立样本。",
        "- 目标方向：文档中列为患病更高的主证据，在该测试集上也应表现为 `患病均值 > 不患病均值` 且 `AUC > 0.5`。",
        "",
        "## 结论",
        "",
        f"- 入选待检测图片：`{summary['selected_image_count']}`",
        f"- MediaPipe detected 图片：`{summary['detected_image_count']}`",
        f"- 检测状态：`{json.dumps(summary['detection_status'], ensure_ascii=False, sort_keys=True)}`",
        f"- 主证据支持数：`{summary['primary_supported_feature_count']}/{summary['primary_total_feature_count']}`",
        f"- 主证据支持率：`{summary['primary_support_rate']:.3f}`",
        "",
        "该结果只能证明这些特征在当前规则标签测试集上与 `患病/不患病` 反馈存在弱监督统计关联；不能证明临床因果，也不能替代人工面瘫/HB 标签验证。",
        "",
        "## 主判断：患者级 all + max",
        "",
    ]
    lines.extend(validation_table(primary_rows))
    lines.extend(
        [
            "",
            "## 按 role 的患者级 max 验证",
            "",
        ]
    )
    for role in summary["roles_evaluated"]:
        rows = [
            row
            for row in validation_rows
            if row["level"] == "patient" and row["role_scope"] == role and row["aggregation"] == "max"
        ]
        lines.append(f"### role = `{role}`")
        lines.append("")
        lines.extend(validation_table(rows))
        lines.append("")
    lines.extend(
        [
            "## 解读",
            "",
            "- `strong_supported`：方向为患病更高，且 AUC >= 0.60。",
            "- `supported`：方向为患病更高，且 AUC >= 0.55。",
            "- `weak_supported`：方向为患病更高，但 AUC 只略高于 0.50。",
            "- `not_supported`：方向不符合，或 AUC 没有超过随机区分。",
            "",
            "如果某个文档主证据在该测试集上未被支持，应优先检查 role 缺失、动作执行差异、采集姿态、三条件阳性标签过窄带来的样本变化，而不是直接删除该特征。",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def validation_table(rows: list[Mapping[str, str]]) -> list[str]:
    output = [
        "| feature | status | pos_n | neg_n | pos_mean | neg_mean | diff | d | auc |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        output.append(
            "| "
            + " | ".join(
                [
                    row["feature_name"],
                    row["support_status"],
                    row["positive_n"],
                    row["negative_n"],
                    row["positive_mean"],
                    row["negative_mean"],
                    row["mean_diff_positive_minus_negative"],
                    row["cohens_d"],
                    row["auc_positive_higher"],
                ]
            )
            + " |"
        )
    return output


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[Mapping[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = sorted({key for row in rows for key in row})
        fixed = ["sample_id", "patient_sample_id", "patient_id", "label_group", "label_binary", "media_role"]
        fields = [field for field in fixed if field in fields] + [field for field in fields if field not in fixed]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
