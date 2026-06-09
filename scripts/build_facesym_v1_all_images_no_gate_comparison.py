#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import build_facesym_v1_dataset_from_by_name as base  # noqa: E402
from facesymai.risk import FacialSymmetryRiskAnalyzer  # noqa: E402
from facesymai.schemas import FaceLandmarks  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"
QUALITY_SKIPPED_FIELDS = [
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
    "face_short_side",
    "laplacian_variance",
    "brightness_mean",
    "bad_exposure_ratio",
    "organized_path",
    "source_media_path",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a no-manifest-filter/no-quality-gate comparison dataset from all patient images."
    )
    parser.add_argument("--source", type=Path, default=base.DEFAULT_SOURCE, help="By-name patient outcome dataset root.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output comparison dataset directory.")
    parser.add_argument("--model", type=Path, default=base.DEFAULT_MODEL, help="MediaPipe Face Landmarker .task model.")
    parser.add_argument("--roles", default="", help="Optional comma-separated role filter. Empty means all image roles.")
    parser.add_argument("--seed", type=int, default=20260520, help="Deterministic patient split seed.")
    parser.add_argument("--train-ratio", type=float, default=0.70, help="Patient-level train split ratio.")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Patient-level validation split ratio.")
    parser.add_argument("--limit-patients-per-label", type=int, default=None, help="Optional smoke-test limit per label group.")
    parser.add_argument("--skip-annotations", action="store_true", help="Skip annotated landmark image generation.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N images.")
    return parser.parse_args(argv)


def build_all_image_index(
    source: Path,
    roles: set[str],
    limit_patients_per_label: int | None,
) -> list[dict[str, str]]:
    media_index = base.read_csv(source / "metadata" / "media_index.csv")
    allowed_patients = allowed_patient_ids(source, limit_patients_per_label)

    rows: list[dict[str, str]] = []
    for row in media_index:
        if row.get("media_type") != "image":
            continue
        if roles and row.get("media_role") not in roles:
            continue
        if allowed_patients and row.get("patient_sample_id") not in allowed_patients:
            continue

        organized_path = source / row["organized_path"]
        sample_id = "__".join([row["patient_sample_id"], row["media_role"], row["media_id"]])
        rows.append(
            {
                "sample_id": sample_id,
                "patient_sample_id": row["patient_sample_id"],
                "patient_id": row["patient_id"],
                "patient_name": row["patient_name"],
                "label_group": row["label_group"],
                "label_binary": base.label_binary(row["label_group"]),
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
    return sorted(rows, key=lambda item: (item["label_group"], item["patient_sample_id"], item["media_role"], item["sample_id"]))


def allowed_patient_ids(source: Path, limit_patients_per_label: int | None) -> set[str]:
    if limit_patients_per_label is None:
        return set()
    grouped: dict[str, list[str]] = {}
    for row in base.read_csv(source / "metadata" / "patient_samples.csv"):
        grouped.setdefault(row["label_group"], []).append(row["patient_sample_id"])
    allowed: set[str] = set()
    for patient_ids in grouped.values():
        allowed.update(sorted(patient_ids)[:limit_patients_per_label])
    return allowed


def all_images_stage(rows: list[dict[str, str]], paths: base.StagePaths, roles: set[str], source: Path) -> None:
    base.write_csv(paths.metadata / "01_all_images.csv", rows, base.MANIFEST_FIELDS)
    per_patient_counts = Counter(row["patient_sample_id"] for row in rows)
    summary = {
        "source_dataset": source.resolve().as_posix(),
        "selection": "all media_index rows where media_type=image; no V1 role manifest filtering",
        "optional_role_filter": sorted(roles),
        "images": len(rows),
        "patients": len(per_patient_counts),
        "patients_by_label": base.summarize_counts(base.unique_patient_rows(rows), ("label_group",)),
        "images_by_label": base.summarize_counts(rows, ("label_group",)),
        "images_by_role": base.summarize_counts(rows, ("media_role",)),
        "images_by_label_role": base.summarize_counts(rows, ("label_group", "media_role")),
        "images_per_patient_min": min(per_patient_counts.values()) if per_patient_counts else 0,
        "images_per_patient_max": max(per_patient_counts.values()) if per_patient_counts else 0,
    }
    base.write_json(paths.metadata / "01_all_images_summary.json", summary)
    base.write_report(
        paths.reports / "01_all_images.md",
        "01 All Images Index",
        [
            f"- Source dataset: `{summary['source_dataset']}`",
            "- Selection: all `media_type=image` rows from `metadata/media_index.csv`; no V1 role manifest filtering.",
            f"- Optional role filter: `{json.dumps(summary['optional_role_filter'], ensure_ascii=False)}`",
            f"- Patients: `{summary['patients']}`",
            f"- Images: `{summary['images']}`",
            "- All-image detail list: `metadata/01_all_images.csv`",
            f"- Patients by label: `{json.dumps(summary['patients_by_label'], ensure_ascii=False, sort_keys=True)}`",
            f"- Images by role: `{json.dumps(summary['images_by_role'], ensure_ascii=False, sort_keys=True)}`",
            f"- Images by label/role: `{json.dumps(summary['images_by_label_role'], ensure_ascii=False, sort_keys=True)}`",
            f"- Images per patient min/max: `{summary['images_per_patient_min']}` / `{summary['images_per_patient_max']}`",
            "",
            "This comparison stage intentionally does not apply the V1 `front,smile,teeth` manifest filter.",
            "",
            "## All Images",
            "",
            *base.manifest_image_table(rows),
        ],
    )


def quality_gate_skipped_stage(rows: list[dict[str, str]], paths: base.StagePaths) -> list[dict[str, str]]:
    skipped_rows: list[dict[str, str]] = []
    for row in rows:
        skipped_rows.append(
            {
                "sample_id": row["sample_id"],
                "patient_sample_id": row["patient_sample_id"],
                "patient_name": row["patient_name"],
                "label_group": row["label_group"],
                "media_role": row["media_role"],
                "quality_level": "not_run",
                "quality_score": "",
                "accepted_for_scoring": "not_applicable",
                "hard_reject": "false",
                "reason_codes": "quality_gate_skipped",
                "width": "",
                "height": "",
                "face_count": "",
                "face_short_side": "",
                "laplacian_variance": "",
                "brightness_mean": "",
                "bad_exposure_ratio": "",
                "organized_path": row["organized_path"],
                "source_media_path": row["source_media_path"],
            }
        )

    base.write_csv(paths.metadata / "02_quality_gate_skipped.csv", skipped_rows, QUALITY_SKIPPED_FIELDS)
    summary = {
        "images": len(skipped_rows),
        "quality_gate": "skipped",
        "excluded_by_quality_gate": 0,
        "reason": "comparison group intentionally disables manifest quality filtering",
        "images_by_label_role": base.summarize_counts(skipped_rows, ("label_group", "media_role")),
    }
    base.write_json(paths.metadata / "02_quality_gate_skipped_summary.json", summary)
    base.write_report(
        paths.reports / "02_quality_gate_skipped.md",
        "02 Quality Gate Skipped",
        [
            f"- Images carried forward: `{summary['images']}`",
            "- Quality gate: `skipped`",
            "- Excluded by quality gate: `0`",
            "- Row detail list: `metadata/02_quality_gate_skipped.csv`",
            f"- Images by label/role: `{json.dumps(summary['images_by_label_role'], ensure_ascii=False, sort_keys=True)}`",
            "",
            "This comparison group intentionally does not run image quality scoring and does not quarantine any image before MediaPipe detection.",
            "",
            "## Carried-Forward Images",
            "",
            *base.markdown_table(
                ["sample_id", "patient", "label", "role", "quality", "accepted", "image"],
                [
                    [
                        row["sample_id"],
                        row["patient_sample_id"],
                        row["label_group"],
                        row["media_role"],
                        row["quality_level"],
                        row["accepted_for_scoring"],
                        base.relative_to_project(Path(row["organized_path"])),
                    ]
                    for row in skipped_rows
                ],
            ),
        ],
    )
    return skipped_rows


def image_feature_stage_all_images(
    manifest: list[dict[str, str]],
    quality_rows: list[dict[str, str]],
    keypoint_rows: list[dict[str, str]],
    paths: base.StagePaths,
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
            **{f"{name}_score": "" for name in base.COMPONENT_NAMES},
            **{f"{name}_symmetry_score": "" for name in base.COMPONENT_NAMES},
            **{f"{name}_side": "" for name in base.COMPONENT_NAMES},
            **{f"{name}_confidence": "" for name in base.COMPONENT_NAMES},
            **{f"{name}_value": "" for name in base.FEATURE_NAMES},
            **{f"{name}_severity": "" for name in base.FEATURE_NAMES},
        }
        if keypoint.get("detection_status") == "detected" and keypoint.get("keypoints_path"):
            try:
                payload = json.loads((paths.output / keypoint["keypoints_path"]).read_text(encoding="utf-8"))
                face = FaceLandmarks.from_payload(payload["detection"])
                result_payload = analyzer.analyze(face).to_dict()
                symmetry = result_payload["symmetry"]
                image_row["overall_symmetry_score"] = base._fmt(symmetry["overall_symmetry_score"])
                image_row["overall_asymmetry_severity"] = base._fmt(symmetry["overall_asymmetry_severity"])
                image_row["affected_side"] = symmetry["affected_side"]
                image_row["advisory_confidence"] = base._fmt(result_payload["advisory_confidence"])
                image_row["raw_score"] = base._fmt(result_payload["raw_score"])
                image_row["risk_level"] = result_payload["risk_level"]
                image_row["input_quality"] = base._fmt(result_payload["input_quality"])
                image_row["warnings"] = "|".join(result_payload["warnings"])
                for name, attribute in result_payload["attributes"].items():
                    image_row[f"{name}_score"] = base._fmt(attribute["score"])
                    image_row[f"{name}_symmetry_score"] = base._fmt(attribute["symmetry_score"])
                    image_row[f"{name}_side"] = attribute["side"]
                    image_row[f"{name}_confidence"] = base._fmt(attribute["confidence"])
                for feature in result_payload["features"]:
                    name = feature["name"]
                    image_row[f"{name}_value"] = base._fmt(feature["value"])
                    image_row[f"{name}_severity"] = base._fmt(feature["severity"])
            except Exception as exc:  # noqa: BLE001 - record row-level feature extraction failure.
                image_row["feature_error"] = f"{type(exc).__name__}: {exc}"
        image_rows.append(image_row)

    base.write_csv(paths.metadata / "04_image_features.csv", image_rows, base.IMAGE_FEATURE_FIELDS)
    patient_rows = aggregate_patient_features_all_images(image_rows, manifest)
    base.write_csv(paths.metadata / "04_patient_features.csv", patient_rows, patient_feature_fields_all_images(patient_rows))
    summary = {
        "image_rows": len(image_rows),
        "patient_rows": len(patient_rows),
        "feature_ready_images": sum(1 for row in image_rows if row["advisory_confidence"]),
        "feature_errors": dict(Counter(row["feature_error"] for row in image_rows if row["feature_error"])),
        "patients_by_label": base.summarize_counts(patient_rows, ("label_group",)),
        "feature_ready_images_by_label_role": base.summarize_counts(
            [row for row in image_rows if row["advisory_confidence"]],
            ("label_group", "media_role"),
        ),
        "patient_score_source": "max_image_advisory_confidence_no_quality_gate",
    }
    base.write_json(paths.metadata / "04_features_summary.json", summary)
    base.write_report(
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
            f"- Patient score source: `{summary['patient_score_source']}`",
            "",
            "Image-level features are computed for every MediaPipe-detected image in the all-image comparison set. Patient-level features keep all image rows and aggregate the patient score from the maximum image-level advisory confidence without quality-gate exclusion.",
            "",
            "## Image Feature Details",
            "",
            *base.image_feature_detail_table(image_rows),
            "",
            "## Patient Feature Details",
            "",
            *patient_feature_detail_table_all_images(patient_rows),
        ],
    )
    return image_rows, patient_rows


def aggregate_patient_features_all_images(
    image_rows: list[dict[str, str]],
    manifest: list[dict[str, str]],
) -> list[dict[str, str]]:
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

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in image_rows:
        grouped.setdefault(row["patient_sample_id"], []).append(row)

    roles = sorted({row["media_role"] for row in image_rows})
    patient_rows: list[dict[str, str]] = []
    for patient_id in sorted(patient_info):
        output = dict(patient_info[patient_id])
        patient_images = grouped.get(patient_id, [])
        scored_images = [row for row in patient_images if row.get("advisory_confidence")]
        best_image = best_by_advisory_confidence(scored_images)

        output["images_available"] = str(len(patient_images))
        output["detected_images"] = str(sum(1 for row in patient_images if row.get("detection_status") == "detected"))
        output["feature_ready_images"] = str(len(scored_images))
        output["roles_available"] = str(len({row["media_role"] for row in patient_images}))
        output["v1_symmetry_score"] = best_image.get("advisory_confidence", "") if best_image else ""
        output["v1_score_source"] = "max_image_advisory_confidence_no_quality_gate" if best_image else ""
        output["v1_score_sample_id"] = best_image.get("sample_id", "") if best_image else ""
        output["v1_score_media_role"] = best_image.get("media_role", "") if best_image else ""
        output["v1_score_affected_side"] = best_image.get("affected_side", "") if best_image else ""
        output["v1_score_risk_level"] = best_image.get("risk_level", "") if best_image else ""
        output["v1_score_overall_symmetry_score"] = best_image.get("overall_symmetry_score", "") if best_image else ""

        for role in roles:
            role_rows = [row for row in patient_images if row["media_role"] == role]
            prefix = f"{role}_"
            output[prefix + "available"] = str(bool(role_rows)).lower()
            output[prefix + "image_count"] = str(len(role_rows))
            output[prefix + "feature_ready_count"] = str(sum(1 for row in role_rows if row.get("advisory_confidence")))
            role_best = best_by_advisory_confidence([row for row in role_rows if row.get("advisory_confidence")])
            if role_best is None and role_rows:
                role_best = sorted(role_rows, key=lambda item: item["sample_id"])[0]
            if role_best is None:
                continue
            output[prefix + "best_sample_id"] = role_best.get("sample_id", "")
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
                output[prefix + key] = role_best.get(key, "")
            for component in base.COMPONENT_NAMES:
                for key in ["score", "symmetry_score", "side", "confidence"]:
                    output[prefix + component + "_" + key] = role_best.get(component + "_" + key, "")
            for feature in base.FEATURE_NAMES:
                output[prefix + feature + "_value"] = role_best.get(feature + "_value", "")
                output[prefix + feature + "_severity"] = role_best.get(feature + "_severity", "")
        patient_rows.append(output)
    return patient_rows


def best_by_advisory_confidence(rows: Iterable[dict[str, str]]) -> dict[str, str] | None:
    usable = [row for row in rows if row.get("advisory_confidence")]
    if not usable:
        return None
    return max(usable, key=lambda row: (float(row["advisory_confidence"]), row["sample_id"]))


def patient_feature_fields_all_images(rows: list[dict[str, str]]) -> list[str]:
    fixed = [
        "patient_sample_id",
        "patient_id",
        "patient_name",
        "label_group",
        "label_binary",
        "sex",
        "age",
        "images_available",
        "detected_images",
        "feature_ready_images",
        "roles_available",
        "v1_symmetry_score",
        "v1_score_source",
        "v1_score_sample_id",
        "v1_score_media_role",
        "v1_score_affected_side",
        "v1_score_risk_level",
        "v1_score_overall_symmetry_score",
    ]
    other = sorted({key for row in rows for key in row if key not in fixed})
    return fixed + other


def patient_feature_detail_table_all_images(rows: list[dict[str, str]]) -> list[str]:
    return base.markdown_table(
        [
            "patient",
            "name",
            "label",
            "images",
            "detected",
            "feature_ready",
            "roles",
            "v1_score",
            "score_role",
            "score_sample",
            "overall_symmetry",
            "affected",
            "risk",
        ],
        [
            [
                row["patient_sample_id"],
                row["patient_name"],
                row["label_group"],
                row["images_available"],
                row["detected_images"],
                row["feature_ready_images"],
                row["roles_available"],
                row["v1_symmetry_score"],
                row["v1_score_media_role"],
                row["v1_score_sample_id"],
                row["v1_score_overall_symmetry_score"],
                row["v1_score_affected_side"],
                row["v1_score_risk_level"],
            ]
            for row in rows
        ],
    )


def baseline_stage_all_images(
    patient_rows: list[dict[str, str]],
    split_rows: list[dict[str, str]],
    paths: base.StagePaths,
) -> None:
    patient_by_id = {row["patient_sample_id"]: row for row in patient_rows}
    split_by_id = {row["patient_sample_id"]: row["split"] for row in split_rows}
    val_rows = [
        row
        for row in patient_rows
        if split_by_id.get(row["patient_sample_id"]) == "val" and row.get("v1_symmetry_score")
    ]
    threshold = base.choose_threshold(val_rows)
    prediction_rows: list[dict[str, str]] = []
    for split_row in split_rows:
        patient = patient_by_id[split_row["patient_sample_id"]]
        score_text = patient.get("v1_symmetry_score", "")
        pred = "" if not score_text else ("1" if float(score_text) >= threshold else "0")
        prediction_rows.append(
            {
                **split_row,
                "v1_symmetry_score": score_text,
                "threshold": base._fmt(threshold),
                "predicted_positive": pred,
                "confusion_cell": base.confusion_cell(split_row["label_binary"], pred),
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
    base.write_csv(paths.metadata / "06_baseline_predictions.csv", prediction_rows, fields)
    metrics = {
        split: base.compute_binary_metrics([row for row in prediction_rows if row["split"] == split])
        for split in ["train", "val", "test"]
    }
    summary = {
        "baseline": "max all-image advisory_confidence threshold, no manifest role filter, no quality gate",
        "threshold_source": "validation split",
        "threshold": threshold,
        "metrics": metrics,
        "warning": "This evaluates a face-symmetry comparison baseline against patient outcome labels. It is not a clinical diagnosis metric.",
    }
    base.write_json(paths.metadata / "06_baseline_evaluation.json", summary)
    base.write_report(
        paths.reports / "06_baseline_evaluation.md",
        "06 Baseline Evaluation",
        [
            "- Baseline: `max(all image advisory_confidence) >= threshold`",
            "- Manifest role filter: `disabled`",
            "- Quality gate: `disabled`",
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
            "This is a technical comparison baseline against the available outcome labels. It should be used to inspect signal and failure modes, not as a diagnostic claim.",
            "",
            "## Prediction Details",
            "",
            *base.baseline_prediction_detail_table(prediction_rows),
        ],
    )


def write_pipeline_summary_all_images(paths: base.StagePaths) -> None:
    stage_files = [
        "01_all_images_summary.json",
        "02_quality_gate_skipped_summary.json",
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
    base.write_json(paths.metadata / "pipeline_summary.json", summaries)
    base.write_report(
        paths.output / "README.md",
        "FaceSymAi V1 All-Images No-Gate Comparison Dataset",
        [
            "This comparison dataset is derived from `datasets/stroke_patient_outcome_by_name_20260119`.",
            "",
            "## Stages",
            "",
            "1. `01_all_images`: read all `media_type=image` rows from the by-name dataset, without the V1 `front,smile,teeth` manifest filter.",
            "2. `02_quality_gate_skipped`: explicitly skip quality gate and carry all images forward.",
            "3. `03_keypoints`: run MediaPipe Face Landmarker and write landmark overlays.",
            "4. `04_features`: compute image-level FaceSymAi features and patient-level max-image aggregation.",
            "5. `05_patient_splits`: create deterministic patient-level train/val/test splits.",
            "6. `06_baseline_evaluation`: evaluate the current rule baseline against available outcome labels.",
            "",
            "## Important",
            "",
            "This is a comparison group. It intentionally includes non-V1 and non-face-oriented image roles such as profiles, eyes-closed, frown, forehead wrinkle, tongue images, auxiliary exam images, and medical record images. The label is patient outcome (`患病`/`不患病`), not a direct facial-asymmetry ground truth label. Metrics are technical signal checks and must not be described as diagnostic performance.",
        ],
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source = args.source.expanduser().resolve()
    output = args.output.expanduser().resolve()
    paths = base.paths_for(output)
    for directory in [paths.metadata, paths.reports, paths.keypoints, paths.annotated]:
        directory.mkdir(parents=True, exist_ok=True)

    roles = base.parse_roles(args.roles) if args.roles else set()
    all_images = build_all_image_index(source, roles, args.limit_patients_per_label)
    all_images_stage(all_images, paths, roles, source)
    quality_rows = quality_gate_skipped_stage(all_images, paths)
    keypoint_rows = base.keypoint_stage(
        all_images,
        paths,
        args.model.expanduser().resolve(),
        args.skip_annotations,
        args.progress_every,
    )
    _image_rows, patient_rows = image_feature_stage_all_images(all_images, quality_rows, keypoint_rows, paths)
    split_rows = base.split_stage(patient_rows, paths, args.seed, args.train_ratio, args.val_ratio)
    baseline_stage_all_images(patient_rows, split_rows, paths)
    write_pipeline_summary_all_images(paths)
    print(
        json.dumps(
            {
                "output": output.as_posix(),
                "images": len(all_images),
                "patients": len(patient_rows),
                "quality_gate": "skipped",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
