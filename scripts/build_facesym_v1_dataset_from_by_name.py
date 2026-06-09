#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.landmarks import MediaPipeFaceLandmarkerDetector, draw_landmarker_overlay  # noqa: E402
from facesymai.quality import QualityGate  # noqa: E402
from facesymai.risk import FacialSymmetryRiskAnalyzer  # noqa: E402
from facesymai.schemas import FaceLandmarks  # noqa: E402


DEFAULT_SOURCE = PROJECT_ROOT / "datasets" / "stroke_patient_outcome_by_name_20260119"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119"
DEFAULT_MODEL = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"
DEFAULT_ROLES = "front,smile,teeth"
FEATURE_NAMES = (
    "global_mirror_error",
    "midline_deviation",
    "mouth_corner_vertical_asymmetry",
    "mouth_width_asymmetry",
    "lip_midline_deviation",
    "eye_aperture_asymmetry",
    "eye_corner_height_asymmetry",
    "brow_vertical_asymmetry",
    "brow_outer_vertical_asymmetry",
    "contour_mirror_error",
    "jaw_width_asymmetry",
)
COMPONENT_NAMES = (
    "mouth",
    "eye",
    "brow",
    "midline",
    "contour",
)
MANIFEST_FIELDS = [
    "sample_id",
    "patient_sample_id",
    "patient_id",
    "patient_name",
    "label_group",
    "label_binary",
    "record_id",
    "sex",
    "age",
    "primary_label_field",
    "primary_label_value",
    "stroke_onset_label",
    "disease_label",
    "media_role",
    "media_id",
    "source_media_path",
    "organized_path",
    "bytes",
    "sha256",
]
QUALITY_FIELDS = [
    "sample_id",
    "patient_sample_id",
    "label_group",
    "media_role",
    "quality_level",
    "quality_score",
    "accepted_for_scoring",
    "hard_reject",
    "reason_codes",
    "width",
    "height",
    "face_count",
    "face_short_side",
    "laplacian_variance",
    "brightness_mean",
    "bad_exposure_ratio",
]
QUARANTINED_FIELDS = [
    "sample_id",
    "patient_sample_id",
    "patient_name",
    "label_group",
    "media_role",
    "quality_level",
    "quality_score",
    "accepted_for_scoring",
    "hard_reject",
    "reason_codes",
    "width",
    "height",
    "face_count",
    "organized_path",
    "source_media_path",
]
KEYPOINT_FIELDS = [
    "sample_id",
    "patient_sample_id",
    "label_group",
    "media_role",
    "detection_status",
    "face_count",
    "raw_landmarks",
    "semantic_landmarks",
    "blendshapes",
    "transformation_matrixes",
    "keypoints_path",
    "annotation_path",
    "error",
]
IMAGE_FEATURE_FIELDS = [
    "sample_id",
    "patient_sample_id",
    "label_group",
    "label_binary",
    "media_role",
    "detection_status",
    "quality_level",
    "quality_score",
    "quality_accepted",
    "overall_symmetry_score",
    "overall_asymmetry_severity",
    "affected_side",
    "advisory_confidence",
    "raw_score",
    "risk_level",
    "input_quality",
    "warnings",
    "feature_error",
    *[f"{name}_score" for name in COMPONENT_NAMES],
    *[f"{name}_symmetry_score" for name in COMPONENT_NAMES],
    *[f"{name}_side" for name in COMPONENT_NAMES],
    *[f"{name}_confidence" for name in COMPONENT_NAMES],
    *[f"{name}_value" for name in FEATURE_NAMES],
    *[f"{name}_severity" for name in FEATURE_NAMES],
]


@dataclass(frozen=True)
class StagePaths:
    output: Path
    metadata: Path
    reports: Path
    keypoints: Path
    annotated: Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FaceSymAi V1 static-image dataset from the by-name patient dataset.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="By-name patient outcome dataset root.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output dataset directory.")
    parser.add_argument("--roles", default=DEFAULT_ROLES, help="Comma-separated image roles for V1.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="MediaPipe Face Landmarker .task model.")
    parser.add_argument("--seed", type=int, default=20260520, help="Deterministic patient split seed.")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Patient-level train split ratio.")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Patient-level validation split ratio.")
    parser.add_argument("--limit-patients-per-label", type=int, default=None, help="Optional smoke-test limit per label group.")
    parser.add_argument("--skip-annotations", action="store_true", help="Skip annotated landmark image generation.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N images.")
    return parser.parse_args(argv)


def paths_for(output: Path) -> StagePaths:
    return StagePaths(
        output=output,
        metadata=output / "metadata",
        reports=output / "reports",
        keypoints=output / "keypoints",
        annotated=output / "annotated",
    )


def parse_roles(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_report(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# " + title + "\n\n" + "\n".join(lines).rstrip() + "\n", encoding="utf-8")


def label_binary(label_group: str) -> str:
    if label_group == "患病":
        return "1"
    if label_group == "不患病":
        return "0"
    return ""


def build_manifest(source: Path, roles: set[str], limit_patients_per_label: int | None) -> list[dict[str, str]]:
    media_index = read_csv(source / "metadata" / "media_index.csv")
    if limit_patients_per_label is not None:
        allowed_patients: set[str] = set()
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in read_csv(source / "metadata" / "patient_samples.csv"):
            grouped[row["label_group"]].append(row["patient_sample_id"])
        for label, ids in grouped.items():
            allowed_patients.update(sorted(ids)[:limit_patients_per_label])
    else:
        allowed_patients = set()

    manifest: list[dict[str, str]] = []
    for row in media_index:
        if row.get("media_type") != "image":
            continue
        if row.get("media_role") not in roles:
            continue
        if allowed_patients and row.get("patient_sample_id") not in allowed_patients:
            continue

        organized_path = source / row["organized_path"]
        sample_id = "__".join([row["patient_sample_id"], row["media_role"], row["media_id"]])
        manifest.append(
            {
                "sample_id": sample_id,
                "patient_sample_id": row["patient_sample_id"],
                "patient_id": row["patient_id"],
                "patient_name": row["patient_name"],
                "label_group": row["label_group"],
                "label_binary": label_binary(row["label_group"]),
                "record_id": row["record_id"],
                "sex": row["sex"],
                "age": row["age"],
                "primary_label_field": row["primary_label_field"],
                "primary_label_value": row["primary_label_value"],
                "stroke_onset_label": row["stroke_onset_label"],
                "disease_label": row["disease_label"],
                "media_role": row["media_role"],
                "media_id": row["media_id"],
                "source_media_path": row["source_media_path"],
                "organized_path": organized_path.as_posix(),
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
        )
    return sorted(manifest, key=lambda item: (item["label_group"], item["patient_sample_id"], item["media_role"], item["sample_id"]))


def summarize_counts(rows: list[Mapping[str, Any]], keys: tuple[str, ...]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        label = "/".join(str(row.get(key, "")) for key in keys)
        counter[label] += 1
    return dict(sorted(counter.items()))


def manifest_stage(manifest: list[dict[str, str]], paths: StagePaths, roles: set[str], source: Path) -> None:
    write_csv(paths.metadata / "01_manifest.csv", manifest, MANIFEST_FIELDS)
    summary = {
        "source_dataset": source.resolve().as_posix(),
        "roles": sorted(roles),
        "images": len(manifest),
        "patients": len({row["patient_sample_id"] for row in manifest}),
        "patients_by_label": summarize_counts(unique_patient_rows(manifest), ("label_group",)),
        "images_by_label": summarize_counts(manifest, ("label_group",)),
        "images_by_role": summarize_counts(manifest, ("media_role",)),
        "images_by_label_role": summarize_counts(manifest, ("label_group", "media_role")),
    }
    write_json(paths.metadata / "01_manifest_summary.json", summary)
    write_report(
        paths.reports / "01_manifest.md",
        "01 Manifest",
        [
            f"- Source dataset: `{summary['source_dataset']}`",
            f"- Roles: `{', '.join(summary['roles'])}`",
            f"- Patients: `{summary['patients']}`",
            f"- Images: `{summary['images']}`",
            "- Selected image list: `metadata/01_manifest.csv`",
            f"- Patients by label: `{json.dumps(summary['patients_by_label'], ensure_ascii=False, sort_keys=True)}`",
            f"- Images by label/role: `{json.dumps(summary['images_by_label_role'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "This stage selects V1 static-image roles from the by-name patient outcome dataset. It does not modify source files.",
            "",
            "## Selected Images",
            "",
            *manifest_image_table(manifest),
        ],
    )


def unique_patient_rows(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        seen.setdefault(str(row["patient_sample_id"]), row)
    return list(seen.values())


def manifest_image_table(rows: list[dict[str, str]]) -> list[str]:
    return markdown_table(
        ["sample_id", "patient", "label", "role", "bytes", "image"],
        [
            [
                row["sample_id"],
                row["patient_sample_id"],
                row["label_group"],
                row["media_role"],
                row["bytes"],
                relative_to_project(Path(row["organized_path"])),
            ]
            for row in rows
        ],
    )


def quality_stage(manifest: list[dict[str, str]], paths: StagePaths, progress_every: int) -> list[dict[str, str]]:
    gate = QualityGate()
    rows: list[dict[str, str]] = []
    for index, row in enumerate(manifest, start=1):
        result = gate.evaluate_image(Path(row["organized_path"]), role=row["media_role"])
        payload = result.to_dict()
        frame = payload["frame_results"][0] if payload["frame_results"] else {}
        metrics = payload.get("metrics", {})
        reasons = payload.get("reasons", [])
        rows.append(
            {
                "sample_id": row["sample_id"],
                "patient_sample_id": row["patient_sample_id"],
                "patient_name": row["patient_name"],
                "label_group": row["label_group"],
                "media_role": row["media_role"],
                "quality_level": payload["quality_level"],
                "quality_score": f"{float(payload['quality_score']):.6f}",
                "accepted_for_scoring": str(bool(payload["accepted_for_scoring"])).lower(),
                "hard_reject": str(bool(payload["hard_reject"])).lower(),
                "reason_codes": "|".join(reason["code"] for reason in reasons),
                "width": str(frame.get("width", "")),
                "height": str(frame.get("height", "")),
                "face_count": "" if frame.get("face_count") is None else str(frame.get("face_count")),
                "face_short_side": _fmt(metrics.get("face_short_side")),
                "laplacian_variance": _fmt(metrics.get("laplacian_variance")),
                "brightness_mean": _fmt(metrics.get("brightness_mean")),
                "bad_exposure_ratio": _fmt(metrics.get("bad_exposure_ratio")),
                "organized_path": row["organized_path"],
                "source_media_path": row["source_media_path"],
            }
        )
        if progress_every and (index % progress_every == 0 or index == len(manifest)):
            print(f"quality progress: {index}/{len(manifest)}", flush=True)
    quarantined_rows = [
        row
        for row in rows
        if row["accepted_for_scoring"] == "false" or row["hard_reject"] == "true"
    ]
    write_csv(paths.metadata / "02_quality_gate.csv", rows, QUALITY_FIELDS)
    write_csv(paths.metadata / "02_quarantined_images.csv", quarantined_rows, QUARANTINED_FIELDS)
    summary = {
        "images": len(rows),
        "quarantined_images": len(quarantined_rows),
        "quality_level_counts": dict(Counter(row["quality_level"] for row in rows)),
        "accepted_for_scoring": dict(Counter(row["accepted_for_scoring"] for row in rows)),
        "reason_code_counts": dict(Counter(code for row in rows for code in row["reason_codes"].split("|") if code)),
        "quality_by_label_role": summarize_counts(rows, ("label_group", "media_role", "quality_level")),
        "quarantined_by_label_role": summarize_counts(quarantined_rows, ("label_group", "media_role")),
    }
    write_json(paths.metadata / "02_quality_gate_summary.json", summary)
    quarantined_table = quarantined_image_table(quarantined_rows)
    write_report(
        paths.reports / "02_quality_gate.md",
        "02 Quality Gate",
        [
            f"- Images evaluated: `{summary['images']}`",
            f"- Quality levels: `{json.dumps(summary['quality_level_counts'], ensure_ascii=False, sort_keys=True)}`",
            f"- Accepted for scoring: `{json.dumps(summary['accepted_for_scoring'], ensure_ascii=False, sort_keys=True)}`",
            f"- Quarantined images: `{summary['quarantined_images']}`",
            "- Quarantined image list: `metadata/02_quarantined_images.csv`",
            f"- Reason codes: `{json.dumps(summary['reason_code_counts'], ensure_ascii=False, sort_keys=True)}`",
            f"- Quarantined by label/role: `{json.dumps(summary['quarantined_by_label_role'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "Current quality gate is a V1 heuristic with OpenCV Haar proxy face detection. MediaPipe detection remains the landmark availability source of truth.",
            "",
            "## Quarantined Images",
            "",
            "A quarantined image has `accepted_for_scoring=false` or `hard_reject=true` and is excluded from V1 scoring inputs until reviewed.",
            "",
            *quarantined_table,
        ],
    )
    return rows


def quarantined_image_table(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["No images were quarantined."]

    table = [
        "| sample_id | patient | label | role | quality | score | reasons | image |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        table.append(
            "| {sample_id} | {patient} | {label} | {role} | {quality} | {score} | {reasons} | {image} |".format(
                sample_id=_md_cell(row["sample_id"]),
                patient=_md_cell(row["patient_sample_id"]),
                label=_md_cell(row["label_group"]),
                role=_md_cell(row["media_role"]),
                quality=_md_cell(row["quality_level"]),
                score=_md_cell(row["quality_score"]),
                reasons=_md_cell(row["reason_codes"].replace("|", ", ")),
                image=_md_cell(relative_to_project(Path(row["organized_path"]))),
            )
        )
    return table


def keypoint_stage(
    manifest: list[dict[str, str]],
    paths: StagePaths,
    model: Path,
    skip_annotations: bool,
    progress_every: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with MediaPipeFaceLandmarkerDetector(model, max_num_faces=2) as detector:
        for index, row in enumerate(manifest, start=1):
            keypoint_path = paths.keypoints / row["label_group"] / row["patient_sample_id"] / f"{row['sample_id']}.json"
            annotation_path = paths.annotated / row["label_group"] / row["patient_sample_id"] / f"{row['sample_id']}.jpg"
            output_row = {
                "sample_id": row["sample_id"],
                "patient_sample_id": row["patient_sample_id"],
                "label_group": row["label_group"],
                "media_role": row["media_role"],
                "detection_status": "",
                "face_count": "",
                "raw_landmarks": "",
                "semantic_landmarks": "",
                "blendshapes": "",
                "transformation_matrixes": "",
                "keypoints_path": "",
                "annotation_path": "",
                "error": "",
            }
            try:
                detection = detector.detect_image_path(Path(row["organized_path"]), image_id=row["sample_id"])
                if detection is None:
                    output_row["detection_status"] = "no_face"
                else:
                    payload = {
                        "sample": row,
                        "detection": detection.to_dict(),
                    }
                    keypoint_path.parent.mkdir(parents=True, exist_ok=True)
                    keypoint_path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    if not skip_annotations:
                        annotation = draw_landmarker_overlay(Path(row["organized_path"]), payload["detection"], annotation_path)
                        output_row["annotation_path"] = relative_to_output(Path(annotation["path"]), paths.output)
                    output_row["detection_status"] = "detected"
                    output_row["face_count"] = str(payload["detection"].get("face_count", ""))
                    output_row["raw_landmarks"] = str(len(payload["detection"].get("raw_landmarks") or []))
                    output_row["semantic_landmarks"] = str(len(payload["detection"].get("landmarks") or {}))
                    output_row["blendshapes"] = str(len(payload["detection"].get("blendshapes") or {}))
                    output_row["transformation_matrixes"] = str(len(payload["detection"].get("facial_transformation_matrixes") or []))
                    output_row["keypoints_path"] = relative_to_output(keypoint_path, paths.output)
            except Exception as exc:  # noqa: BLE001 - record sample-level failure and continue.
                output_row["detection_status"] = "failed"
                output_row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(output_row)
            if progress_every and (index % progress_every == 0 or index == len(manifest)):
                print(f"keypoint progress: {index}/{len(manifest)}", flush=True)
    write_csv(paths.metadata / "03_keypoints.csv", rows, KEYPOINT_FIELDS)
    summary = {
        "images": len(rows),
        "status_counts": dict(Counter(row["detection_status"] for row in rows)),
        "status_by_label_role": summarize_counts(rows, ("label_group", "media_role", "detection_status")),
        "raw_landmark_counts": sorted({int(row["raw_landmarks"]) for row in rows if row["raw_landmarks"]}),
        "blendshape_counts": sorted({int(row["blendshapes"]) for row in rows if row["blendshapes"]}),
        "transformation_matrix_counts": sorted({int(row["transformation_matrixes"]) for row in rows if row["transformation_matrixes"]}),
        "annotations_written": sum(1 for row in rows if row["annotation_path"]),
    }
    write_json(paths.metadata / "03_keypoints_summary.json", summary)
    write_report(
        paths.reports / "03_keypoints.md",
        "03 MediaPipe Keypoints",
        [
            f"- Images processed: `{summary['images']}`",
            f"- Detection statuses: `{json.dumps(summary['status_counts'], ensure_ascii=False, sort_keys=True)}`",
            "- Detection detail list: `metadata/03_keypoints.csv`",
            f"- Raw landmark counts: `{summary['raw_landmark_counts']}`",
            f"- Blendshape counts: `{summary['blendshape_counts']}`",
            f"- Transformation matrix counts: `{summary['transformation_matrix_counts']}`",
            f"- Annotated images written: `{summary['annotations_written']}`",
            "",
            "Detected samples contain MediaPipe Face Landmarker output converted to the FaceSymAi schema plus optional visual overlays.",
            "",
            "## Detection Details",
            "",
            *keypoint_detail_table(rows),
        ],
    )
    return rows


def keypoint_detail_table(rows: list[dict[str, str]]) -> list[str]:
    return markdown_table(
        [
            "sample_id",
            "patient",
            "label",
            "role",
            "status",
            "faces",
            "raw",
            "semantic",
            "keypoints",
            "annotation",
            "error",
        ],
        [
            [
                row["sample_id"],
                row["patient_sample_id"],
                row["label_group"],
                row["media_role"],
                row["detection_status"],
                row["face_count"],
                row["raw_landmarks"],
                row["semantic_landmarks"],
                row["keypoints_path"],
                row["annotation_path"],
                row["error"],
            ]
            for row in rows
        ],
    )


def image_feature_stage(
    manifest: list[dict[str, str]],
    quality_rows: list[dict[str, str]],
    keypoint_rows: list[dict[str, str]],
    paths: StagePaths,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    manifest_by_id = {row["sample_id"]: row for row in manifest}
    quality_by_id = {row["sample_id"]: row for row in quality_rows}
    keypoint_by_id = {row["sample_id"]: row for row in keypoint_rows}
    analyzer = FacialSymmetryRiskAnalyzer()
    image_rows: list[dict[str, str]] = []

    for sample_id, row in manifest_by_id.items():
        quality = quality_by_id.get(sample_id, {})
        keypoint = keypoint_by_id.get(sample_id, {})
        image_row = {
            "sample_id": sample_id,
            "patient_sample_id": row["patient_sample_id"],
            "label_group": row["label_group"],
            "label_binary": row["label_binary"],
            "media_role": row["media_role"],
            "detection_status": keypoint.get("detection_status", ""),
            "quality_level": quality.get("quality_level", ""),
            "quality_score": quality.get("quality_score", ""),
            "quality_accepted": quality.get("accepted_for_scoring", ""),
            "overall_symmetry_score": "",
            "overall_asymmetry_severity": "",
            "affected_side": "",
            "advisory_confidence": "",
            "raw_score": "",
            "risk_level": "",
            "input_quality": "",
            "warnings": "",
            "feature_error": "",
            **{f"{name}_score": "" for name in COMPONENT_NAMES},
            **{f"{name}_symmetry_score": "" for name in COMPONENT_NAMES},
            **{f"{name}_side": "" for name in COMPONENT_NAMES},
            **{f"{name}_confidence": "" for name in COMPONENT_NAMES},
            **{f"{name}_value": "" for name in FEATURE_NAMES},
            **{f"{name}_severity": "" for name in FEATURE_NAMES},
        }
        if keypoint.get("detection_status") == "detected" and keypoint.get("keypoints_path"):
            try:
                payload = json.loads((paths.output / keypoint["keypoints_path"]).read_text(encoding="utf-8"))
                face = FaceLandmarks.from_payload(payload["detection"])
                result = analyzer.analyze(face)
                result_payload = result.to_dict()
                symmetry = result_payload["symmetry"]
                image_row["overall_symmetry_score"] = _fmt(symmetry["overall_symmetry_score"])
                image_row["overall_asymmetry_severity"] = _fmt(symmetry["overall_asymmetry_severity"])
                image_row["affected_side"] = symmetry["affected_side"]
                image_row["advisory_confidence"] = _fmt(result_payload["advisory_confidence"])
                image_row["raw_score"] = _fmt(result_payload["raw_score"])
                image_row["risk_level"] = result_payload["risk_level"]
                image_row["input_quality"] = _fmt(result_payload["input_quality"])
                image_row["warnings"] = "|".join(result_payload["warnings"])
                for name, attribute in result_payload["attributes"].items():
                    image_row[f"{name}_score"] = _fmt(attribute["score"])
                    image_row[f"{name}_symmetry_score"] = _fmt(attribute["symmetry_score"])
                    image_row[f"{name}_side"] = attribute["side"]
                    image_row[f"{name}_confidence"] = _fmt(attribute["confidence"])
                for feature in result_payload["features"]:
                    name = feature["name"]
                    image_row[f"{name}_value"] = _fmt(feature["value"])
                    image_row[f"{name}_severity"] = _fmt(feature["severity"])
            except Exception as exc:  # noqa: BLE001 - record row-level feature extraction failure.
                image_row["feature_error"] = f"{type(exc).__name__}: {exc}"
        image_rows.append(image_row)

    write_csv(paths.metadata / "04_image_features.csv", image_rows, IMAGE_FEATURE_FIELDS)
    patient_rows = aggregate_patient_features(image_rows, manifest)
    patient_fields = patient_feature_fields(patient_rows)
    write_csv(paths.metadata / "04_patient_features.csv", patient_rows, patient_fields)
    summary = {
        "image_rows": len(image_rows),
        "patient_rows": len(patient_rows),
        "feature_ready_images": sum(1 for row in image_rows if row["advisory_confidence"]),
        "feature_errors": dict(Counter(row["feature_error"] for row in image_rows if row["feature_error"])),
        "patients_by_label": summarize_counts(patient_rows, ("label_group",)),
        "feature_ready_images_by_label_role": summarize_counts(
            [row for row in image_rows if row["advisory_confidence"]],
            ("label_group", "media_role"),
        ),
    }
    write_json(paths.metadata / "04_features_summary.json", summary)
    write_report(
        paths.reports / "04_features.md",
        "04 Face Symmetry Features",
        [
            f"- Image feature rows: `{summary['image_rows']}`",
            f"- Patient feature rows: `{summary['patient_rows']}`",
            f"- Feature-ready images: `{summary['feature_ready_images']}`",
            "- Image feature detail list: `metadata/04_image_features.csv`",
            "- Patient feature detail list: `metadata/04_patient_features.csv`",
            f"- Feature errors: `{json.dumps(summary['feature_errors'], ensure_ascii=False, sort_keys=True)}`",
            f"- Feature-ready images by label/role: `{json.dumps(summary['feature_ready_images_by_label_role'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "Image-level features are computed from standardized FaceSymAi semantic landmarks: fitted midline alignment, light roll correction, and eye-distance scale normalization. Patient-level features aggregate role-specific values without mixing patients.",
            "",
            "## Image Feature Details",
            "",
            *image_feature_detail_table(image_rows),
            "",
            "## Patient Feature Details",
            "",
            *patient_feature_detail_table(patient_rows),
        ],
    )
    return image_rows, patient_rows


def image_feature_detail_table(rows: list[dict[str, str]]) -> list[str]:
    return markdown_table(
        [
            "sample_id",
            "patient",
            "label",
            "role",
            "detect",
            "quality",
            "accepted",
            "overall_symmetry",
            "affected",
            "score",
            "risk",
            "mouth",
            "eye",
            "brow",
            "midline",
            "contour",
            "warnings",
            "error",
        ],
        [
            [
                row["sample_id"],
                row["patient_sample_id"],
                row["label_group"],
                row["media_role"],
                row["detection_status"],
                row["quality_level"],
                row["quality_accepted"],
                row["overall_symmetry_score"],
                row["affected_side"],
                row["advisory_confidence"],
                row["risk_level"],
                row["mouth_score"],
                row["eye_score"],
                row["brow_score"],
                row["midline_score"],
                row["contour_score"],
                row["warnings"].replace("|", ", "),
                row["feature_error"],
            ]
            for row in rows
        ],
    )


def patient_feature_detail_table(rows: list[dict[str, str]]) -> list[str]:
    return markdown_table(
        [
            "patient",
            "name",
            "label",
            "roles",
            "v1_score",
            "front_overall",
            "front_score",
            "front_mouth",
            "front_eye",
            "front_brow",
            "front_midline",
            "front_contour",
            "smile_overall",
            "smile_score",
            "teeth_overall",
            "teeth_score",
            "teeth_mouth",
        ],
        [
            [
                row["patient_sample_id"],
                row["patient_name"],
                row["label_group"],
                row["roles_available"],
                row["v1_symmetry_score"],
                row.get("front_overall_symmetry_score", ""),
                row.get("front_advisory_confidence", ""),
                row.get("front_mouth_score", ""),
                row.get("front_eye_score", ""),
                row.get("front_brow_score", ""),
                row.get("front_midline_score", ""),
                row.get("front_contour_score", ""),
                row.get("smile_overall_symmetry_score", ""),
                row.get("smile_advisory_confidence", ""),
                row.get("teeth_overall_symmetry_score", ""),
                row.get("teeth_advisory_confidence", ""),
                row.get("teeth_mouth_score", ""),
            ]
            for row in rows
        ],
    )


def aggregate_patient_features(image_rows: list[dict[str, str]], manifest: list[dict[str, str]]) -> list[dict[str, str]]:
    patient_info: dict[str, dict[str, str]] = {}
    for row in manifest:
        patient_info.setdefault(
            row["patient_sample_id"],
            {
                "patient_sample_id": row["patient_sample_id"],
                "patient_id": row["patient_id"],
                "patient_name": row["patient_name"],
                "label_group": row["label_group"],
                "label_binary": row["label_binary"],
                "sex": row["sex"],
                "age": row["age"],
            },
        )

    grouped: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in image_rows:
        grouped[row["patient_sample_id"]][row["media_role"]] = row

    patient_rows: list[dict[str, str]] = []
    roles = sorted({row["media_role"] for row in image_rows})
    for patient_id in sorted(patient_info):
        output = dict(patient_info[patient_id])
        available_scores: list[float] = []
        role_count = 0
        for role in roles:
            role_row = grouped.get(patient_id, {}).get(role)
            prefix = f"{role}_"
            if role_row is None:
                output[prefix + "available"] = "false"
                continue
            output[prefix + "available"] = "true"
            role_count += 1
            for key in [
                "detection_status",
                "quality_level",
                "quality_score",
                "quality_accepted",
                "overall_symmetry_score",
                "overall_asymmetry_severity",
                "affected_side",
                "advisory_confidence",
                "raw_score",
                "risk_level",
                "input_quality",
            ]:
                output[prefix + key] = role_row.get(key, "")
            for component in COMPONENT_NAMES:
                for key in ["score", "symmetry_score", "side", "confidence"]:
                    output[prefix + component + "_" + key] = role_row.get(component + "_" + key, "")
            for feature in FEATURE_NAMES:
                output[prefix + feature + "_value"] = role_row.get(feature + "_value", "")
                output[prefix + feature + "_severity"] = role_row.get(feature + "_severity", "")
            if role_row.get("advisory_confidence"):
                available_scores.append(float(role_row["advisory_confidence"]))

        output["roles_available"] = str(role_count)
        output["v1_symmetry_score"] = _fmt(max(available_scores)) if available_scores else ""
        output["v1_score_source"] = "max_role_advisory_confidence" if available_scores else ""
        patient_rows.append(output)
    return patient_rows


def patient_feature_fields(rows: list[dict[str, str]]) -> list[str]:
    fixed = [
        "patient_sample_id",
        "patient_id",
        "patient_name",
        "label_group",
        "label_binary",
        "sex",
        "age",
        "roles_available",
        "v1_symmetry_score",
        "v1_score_source",
    ]
    other = sorted({key for row in rows for key in row if key not in fixed})
    return fixed + other


def split_stage(patient_rows: list[dict[str, str]], paths: StagePaths, seed: int, train_ratio: float, val_ratio: float) -> list[dict[str, str]]:
    rng = random.Random(seed)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in patient_rows:
        grouped[row["label_group"]].append(row)

    split_rows: list[dict[str, str]] = []
    for label, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda item: item["patient_sample_id"])
        rng.shuffle(rows)
        n = len(rows)
        train_n = round(n * train_ratio)
        val_n = round(n * val_ratio)
        for index, row in enumerate(rows):
            if index < train_n:
                split = "train"
            elif index < train_n + val_n:
                split = "val"
            else:
                split = "test"
            split_rows.append(
                {
                    "patient_sample_id": row["patient_sample_id"],
                    "patient_id": row["patient_id"],
                    "patient_name": row["patient_name"],
                    "label_group": row["label_group"],
                    "label_binary": row["label_binary"],
                    "split": split,
                    "v1_symmetry_score": row.get("v1_symmetry_score", ""),
                    "seed": str(seed),
                }
            )
    split_rows = sorted(split_rows, key=lambda item: (item["split"], item["label_group"], item["patient_sample_id"]))
    write_csv(
        paths.metadata / "05_patient_splits.csv",
        split_rows,
        ["patient_sample_id", "patient_id", "patient_name", "label_group", "label_binary", "split", "v1_symmetry_score", "seed"],
    )
    summary = {
        "seed": seed,
        "train_ratio": train_ratio,
        "val_ratio": val_ratio,
        "test_ratio": max(0.0, 1.0 - train_ratio - val_ratio),
        "patients": len(split_rows),
        "split_counts": summarize_counts(split_rows, ("split",)),
        "split_label_counts": summarize_counts(split_rows, ("split", "label_group")),
    }
    write_json(paths.metadata / "05_patient_splits_summary.json", summary)
    write_report(
        paths.reports / "05_patient_splits.md",
        "05 Patient Splits",
        [
            f"- Seed: `{seed}`",
            f"- Patients: `{summary['patients']}`",
            "- Patient split detail list: `metadata/05_patient_splits.csv`",
            f"- Split counts: `{json.dumps(summary['split_counts'], ensure_ascii=False, sort_keys=True)}`",
            f"- Split/label counts: `{json.dumps(summary['split_label_counts'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "Splits are patient-level and stratified by label group to avoid image-level leakage.",
            "",
            "## Patient Split Details",
            "",
            *patient_split_detail_table(split_rows),
        ],
    )
    return split_rows


def patient_split_detail_table(rows: list[dict[str, str]]) -> list[str]:
    return markdown_table(
        ["patient", "name", "label", "split", "v1_score", "seed"],
        [
            [
                row["patient_sample_id"],
                row["patient_name"],
                row["label_group"],
                row["split"],
                row["v1_symmetry_score"],
                row["seed"],
            ]
            for row in rows
        ],
    )


def baseline_stage(patient_rows: list[dict[str, str]], split_rows: list[dict[str, str]], paths: StagePaths) -> None:
    patient_by_id = {row["patient_sample_id"]: row for row in patient_rows}
    split_by_id = {row["patient_sample_id"]: row["split"] for row in split_rows}
    val_rows = [row for row in patient_rows if split_by_id.get(row["patient_sample_id"]) == "val" and row.get("v1_symmetry_score")]
    threshold = choose_threshold(val_rows)
    prediction_rows: list[dict[str, str]] = []
    for split_row in split_rows:
        patient = patient_by_id[split_row["patient_sample_id"]]
        score_text = patient.get("v1_symmetry_score", "")
        if not score_text:
            pred = ""
        else:
            pred = "1" if float(score_text) >= threshold else "0"
        prediction_rows.append(
            {
                **split_row,
                "v1_symmetry_score": score_text,
                "threshold": _fmt(threshold),
                "predicted_positive": pred,
                "confusion_cell": confusion_cell(split_row["label_binary"], pred),
            }
        )
    fields = [
        "patient_sample_id",
        "patient_id",
        "patient_name",
        "label_group",
        "label_binary",
        "split",
        "v1_symmetry_score",
        "threshold",
        "predicted_positive",
        "confusion_cell",
        "seed",
    ]
    write_csv(paths.metadata / "06_baseline_predictions.csv", prediction_rows, fields)
    metrics = {
        split: compute_binary_metrics([row for row in prediction_rows if row["split"] == split])
        for split in ["train", "val", "test"]
    }
    summary = {
        "baseline": "max role advisory_confidence threshold",
        "threshold_source": "validation split",
        "threshold": threshold,
        "metrics": metrics,
        "warning": "This evaluates a face-symmetry baseline against patient outcome labels. It is not a clinical diagnosis metric.",
    }
    write_json(paths.metadata / "06_baseline_evaluation.json", summary)
    write_report(
        paths.reports / "06_baseline_evaluation.md",
        "06 Baseline Evaluation",
        [
            "- Baseline: `max(front/smile/teeth advisory_confidence) >= threshold`",
            "- Threshold source: validation split",
            f"- Threshold: `{threshold:.6f}`",
            "- Prediction detail list: `metadata/06_baseline_predictions.csv`",
            "",
            "| split | patients | precision | recall | specificity | tp | fp | tn | fn |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            *[
                "| {split} | {patients} | {precision:.6f} | {recall:.6f} | {specificity:.6f} | {tp} | {fp} | {tn} | {fn} |".format(
                    split=split,
                    **metrics[split],
                )
                for split in ["train", "val", "test"]
            ],
            "",
            "This is a technical baseline against the available outcome labels. It should be used to inspect signal and failure modes, not as a diagnostic claim.",
            "",
            "## Prediction Details",
            "",
            *baseline_prediction_detail_table(prediction_rows),
        ],
    )


def baseline_prediction_detail_table(rows: list[dict[str, str]]) -> list[str]:
    return markdown_table(
        ["patient", "name", "split", "label", "truth", "score", "threshold", "pred", "cell"],
        [
            [
                row["patient_sample_id"],
                row["patient_name"],
                row["split"],
                row["label_group"],
                row["label_binary"],
                row["v1_symmetry_score"],
                row["threshold"],
                row["predicted_positive"],
                row["confusion_cell"],
            ]
            for row in rows
        ],
    )


def confusion_cell(truth: str, pred: str) -> str:
    if truth not in {"0", "1"} or pred not in {"0", "1"}:
        return "skipped"
    if truth == "1" and pred == "1":
        return "tp"
    if truth == "0" and pred == "1":
        return "fp"
    if truth == "0" and pred == "0":
        return "tn"
    return "fn"


def choose_threshold(rows: list[dict[str, str]]) -> float:
    scores = sorted({float(row["v1_symmetry_score"]) for row in rows if row.get("v1_symmetry_score")})
    if not scores:
        return 0.5
    best = (scores[0], -1.0, -1.0)
    for threshold in scores:
        metrics = compute_binary_metrics(
            [
                {
                    "label_binary": row["label_binary"],
                    "predicted_positive": "1" if float(row["v1_symmetry_score"]) >= threshold else "0",
                }
                for row in rows
            ]
        )
        f1 = metrics["f1"]
        precision = metrics["precision"]
        if (f1, precision) > (best[1], best[2]):
            best = (threshold, f1, precision)
    return float(best[0])


def compute_binary_metrics(rows: list[Mapping[str, str]]) -> dict[str, Any]:
    tp = fp = tn = fn = skipped = 0
    for row in rows:
        truth = row.get("label_binary")
        pred = row.get("predicted_positive")
        if truth not in {"0", "1"} or pred not in {"0", "1"}:
            skipped += 1
            continue
        if truth == "1" and pred == "1":
            tp += 1
        elif truth == "0" and pred == "1":
            fp += 1
        elif truth == "0" and pred == "0":
            tn += 1
        elif truth == "1" and pred == "0":
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "patients": len(rows),
        "evaluated": tp + fp + tn + fn,
        "skipped": skipped,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def write_pipeline_summary(paths: StagePaths) -> None:
    stage_files = [
        "01_manifest_summary.json",
        "02_quality_gate_summary.json",
        "03_keypoints_summary.json",
        "04_features_summary.json",
        "05_patient_splits_summary.json",
        "06_baseline_evaluation.json",
    ]
    summaries = {
        name: json.loads((paths.metadata / name).read_text(encoding="utf-8"))
        for name in stage_files
        if (paths.metadata / name).exists()
    }
    write_json(paths.metadata / "pipeline_summary.json", summaries)
    write_report(
        paths.output / "README.md",
        "FaceSymAi V1 By-Name Dataset",
        [
            "This dataset is derived from `datasets/stroke_patient_outcome_by_name_20260119` for V1 static-image facial symmetry analysis.",
            "",
            "## Stages",
            "",
            "1. `01_manifest`: select V1 static-image roles.",
            "2. `02_quality_gate`: record current image quality gate output.",
            "3. `03_keypoints`: run MediaPipe Face Landmarker and write landmark overlays.",
            "4. `04_features`: compute image-level and patient-level FaceSymAi features, including overall symmetry and five component attributes.",
            "5. `05_patient_splits`: create deterministic patient-level train/val/test splits.",
            "6. `06_baseline_evaluation`: evaluate the current rule baseline against available outcome labels.",
            "",
            "## Important",
            "",
            "The label is patient outcome (`患病`/`不患病`), not a direct facial-asymmetry ground truth label. Metrics are technical signal checks and must not be described as diagnostic performance.",
        ],
    )


def relative_to_output(path: Path, output: Path) -> str:
    try:
        return path.relative_to(output).as_posix()
    except ValueError:
        return path.as_posix()


def relative_to_project(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    if not rows:
        return ["No rows."]

    table = [
        "| " + " | ".join(_md_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    for row in rows:
        table.append("| " + " | ".join(_md_cell(value) for value in row) + " |")
    return table


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    paths = paths_for(output)
    for directory in [paths.metadata, paths.reports, paths.keypoints, paths.annotated]:
        directory.mkdir(parents=True, exist_ok=True)

    roles = parse_roles(args.roles)
    manifest = build_manifest(source, roles, args.limit_patients_per_label)
    manifest_stage(manifest, paths, roles, source)
    quality_rows = quality_stage(manifest, paths, args.progress_every)
    keypoint_rows = keypoint_stage(manifest, paths, args.model.expanduser().resolve(), args.skip_annotations, args.progress_every)
    _image_rows, patient_rows = image_feature_stage(manifest, quality_rows, keypoint_rows, paths)
    split_rows = split_stage(patient_rows, paths, args.seed, args.train_ratio, args.val_ratio)
    baseline_stage(patient_rows, split_rows, paths)
    write_pipeline_summary(paths)
    print(json.dumps({"output": output.as_posix(), "images": len(manifest), "patients": len(patient_rows)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
