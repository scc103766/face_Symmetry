#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.dataset_v1 import V1Sample, build_samples  # noqa: E402
from facesymai.landmarks import MediaPipeFaceLandmarkerDetector, draw_landmarker_overlay  # noqa: E402


DEFAULT_DATASETS = [
    PROJECT_ROOT / "datasets" / "stroke_media_dataset_20260119",
    PROJECT_ROOT / "datasets" / "stroke_warning_app_media_dataset_20260508",
]
DEFAULT_MODEL = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"
DEFAULT_OUTPUT = PROJECT_ROOT / "tmp" / "mediapipe_landmarker_dataset_test"
DEFAULT_ROLES = "front,smile,teeth,front_contour,smile_teeth"
CSV_FIELDS = [
    "source_dataset",
    "media_role",
    "sample_id",
    "source_media_path",
    "status",
    "face_count",
    "raw_landmarks",
    "semantic_landmarks",
    "blendshapes",
    "transformation_matrixes",
    "detection_path",
    "annotation_path",
    "error",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a MediaPipe Face Landmarker usability test on current datasets.")
    parser.add_argument(
        "--dataset-root",
        action="append",
        type=Path,
        dest="dataset_roots",
        help="Dataset root containing metadata/records.csv and metadata/media_manifest.csv. Repeatable.",
    )
    parser.add_argument("--roles", default=DEFAULT_ROLES, help="Comma-separated image roles to include.")
    parser.add_argument("--limit-per-role", type=int, default=5, help="Samples to run for each dataset/role pair.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory under the project tmp folder.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="MediaPipe Face Landmarker .task model.")
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    return parser.parse_args(argv)


def parse_roles(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


def select_samples(samples: list[V1Sample], *, limit_per_role: int) -> list[V1Sample]:
    selected: list[V1Sample] = []
    grouped: dict[tuple[str, str], list[V1Sample]] = defaultdict(list)
    for sample in samples:
        grouped[(sample.source_dataset, sample.media_role)].append(sample)
    for key in sorted(grouped):
        selected.extend(sorted(grouped[key], key=lambda item: item.sample_id)[:limit_per_role])
    return selected


def relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def detect_sample(
    detector: MediaPipeFaceLandmarkerDetector,
    sample: V1Sample,
    output_root: Path,
) -> dict[str, str]:
    detection_path = output_root / "detections" / sample.source_dataset / f"{sample.sample_id}.json"
    annotation_path = output_root / "annotated" / sample.source_dataset / f"{sample.sample_id}.jpg"
    row = {
        "source_dataset": sample.source_dataset,
        "media_role": sample.media_role,
        "sample_id": sample.sample_id,
        "source_media_path": sample.source_media_path.as_posix(),
        "status": "",
        "face_count": "",
        "raw_landmarks": "",
        "semantic_landmarks": "",
        "blendshapes": "",
        "transformation_matrixes": "",
        "detection_path": "",
        "annotation_path": "",
        "error": "",
    }
    try:
        detection = detector.detect_image_path(sample.source_media_path, image_id=sample.sample_id)
        if detection is None:
            row["status"] = "no_face"
            return row

        payload = {
            "sample": {
                "sample_id": sample.sample_id,
                "source_dataset": sample.source_dataset,
                "record_id": sample.record_id,
                "media_id": sample.media_id,
                "media_role": sample.media_role,
                "media_type": sample.media_type,
                "source_media_path": sample.source_media_path.as_posix(),
                **sample.label.to_dict(),
            },
            "detection": detection.to_dict(),
        }
        detection_path.parent.mkdir(parents=True, exist_ok=True)
        detection_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        annotation = draw_landmarker_overlay(sample.source_media_path, payload["detection"], annotation_path)

        row["status"] = "detected"
        row["face_count"] = str(payload["detection"].get("face_count", ""))
        row["raw_landmarks"] = str(len(payload["detection"].get("raw_landmarks") or []))
        row["semantic_landmarks"] = str(len(payload["detection"].get("landmarks") or {}))
        row["blendshapes"] = str(len(payload["detection"].get("blendshapes") or {}))
        row["transformation_matrixes"] = str(len(payload["detection"].get("facial_transformation_matrixes") or []))
        row["detection_path"] = relative_or_absolute(detection_path, output_root)
        row["annotation_path"] = relative_or_absolute(Path(annotation["path"]), output_root)
        return row
    except Exception as exc:  # noqa: BLE001 - record per-sample failure and continue.
        row["status"] = "failed"
        row["error"] = f"{type(exc).__name__}: {exc}"
        return row


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]], selected: list[V1Sample], args: argparse.Namespace) -> dict[str, Any]:
    return {
        "dataset_roots": [path.resolve().as_posix() for path in (args.dataset_roots or DEFAULT_DATASETS) if path.exists()],
        "roles": sorted(parse_roles(args.roles)),
        "limit_per_role": args.limit_per_role,
        "model": args.model.resolve().as_posix(),
        "samples_selected": len(selected),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "by_dataset_role": {
            f"{dataset}/{role}": dict(Counter(row["status"] for row in rows if row["source_dataset"] == dataset and row["media_role"] == role))
            for dataset, role in sorted({(row["source_dataset"], row["media_role"]) for row in rows})
        },
        "detected_raw_landmarks_counts": sorted({int(row["raw_landmarks"]) for row in rows if row["raw_landmarks"]}),
        "detected_blendshape_counts": sorted({int(row["blendshapes"]) for row in rows if row["blendshapes"]}),
        "detected_transformation_matrix_counts": sorted({int(row["transformation_matrixes"]) for row in rows if row["transformation_matrixes"]}),
    }


def write_summary_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# MediaPipe Face Landmarker Dataset Smoke Test",
        "",
        f"- Samples selected: `{summary['samples_selected']}`",
        f"- Status counts: `{json.dumps(summary['status_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- Roles: `{', '.join(summary['roles'])}`",
        f"- Limit per dataset/role: `{summary['limit_per_role']}`",
        f"- Model: `{summary['model']}`",
        f"- Raw landmark counts: `{summary['detected_raw_landmarks_counts']}`",
        f"- Blendshape counts: `{summary['detected_blendshape_counts']}`",
        f"- Transformation matrix counts: `{summary['detected_transformation_matrix_counts']}`",
        "",
        "## By Dataset And Role",
        "",
        "| dataset/role | statuses |",
        "| --- | --- |",
    ]
    for key, counts in sorted(summary["by_dataset_role"].items()):
        lines.append(f"| `{key}` | `{json.dumps(counts, ensure_ascii=False, sort_keys=True)}` |")
    lines.extend(
        [
            "",
            "## Output Layout",
            "",
            "- `metadata/results.csv`: per-sample status and output paths.",
            "- `metadata/summary.json`: machine-readable aggregate summary.",
            "- `detections/<dataset>/<sample_id>.json`: raw Face Landmarker payload converted to FaceSymAi schema.",
            "- `annotated/<dataset>/<sample_id>.jpg`: source image with 478 raw landmarks and semantic landmarks overlaid.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    dataset_roots = args.dataset_roots or [path for path in DEFAULT_DATASETS if path.exists()]
    output_root = args.output.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    samples = build_samples(
        dataset_roots,
        include_images=True,
        include_videos=False,
        roles=parse_roles(args.roles),
    )
    selected = select_samples(samples, limit_per_role=max(1, args.limit_per_role))

    rows: list[dict[str, str]] = []
    with MediaPipeFaceLandmarkerDetector(args.model, max_num_faces=max(1, args.max_faces)) as detector:
        for index, sample in enumerate(selected, start=1):
            rows.append(detect_sample(detector, sample, output_root))
            print(f"landmarker smoke progress: {index}/{len(selected)}", flush=True)

    write_csv(output_root / "metadata" / "results.csv", rows)
    summary = summarize(rows, selected, args)
    (output_root / "metadata" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_summary_markdown(output_root / "README.md", summary)
    print(json.dumps({"output": output_root.as_posix(), **summary}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
