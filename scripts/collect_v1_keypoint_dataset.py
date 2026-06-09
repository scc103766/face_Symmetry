#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.dataset_v1 import V1Sample, build_samples, write_csv, write_jsonl  # noqa: E402
from facesymai.landmarks import (  # noqa: E402
    MediaPipeFaceLandmarkerDetector,
    MediaPipeFaceMeshDetector,
    MediaPipeUnavailableError,
)


DEFAULT_DATASETS = [
    PROJECT_ROOT / "datasets" / "stroke_media_dataset_20260119",
    PROJECT_ROOT / "datasets" / "stroke_warning_app_media_dataset_20260508",
]
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "v1_keypoint_dataset"
BACKENDS = ("auto", "face_landmarker", "face_mesh")
MODEL_ENV_VAR = "FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"

SAMPLE_FIELDS = [
    "sample_id",
    "source_dataset",
    "record_id",
    "media_id",
    "media_role",
    "media_type",
    "source_media_path",
    "frame_index",
    "frame_time_sec",
    "label_source",
    "label_value",
    "label_binary",
    "detection_status",
    "keypoints_path",
    "error",
]


def parse_roles(value: str | None) -> set[str] | None:
    if not value:
        return None
    roles = {item.strip() for item in value.split(",") if item.strip()}
    return roles or None


def read_first_video_frame(path: Path) -> Any:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for video frame extraction") from exc

    capture = cv2.VideoCapture(str(path))
    try:
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"unable to read first frame from video: {path}")
        return frame
    finally:
        capture.release()


def detect_sample(detector: Any, sample: V1Sample) -> tuple[str, dict[str, Any] | None, str]:
    try:
        if sample.media_type == "image":
            detection = detector.detect_image_path(sample.source_media_path, image_id=sample.sample_id)
        elif sample.media_type == "video":
            frame = read_first_video_frame(sample.source_media_path)
            if hasattr(detector, "detect_bgr_image"):
                detection = detector.detect_bgr_image(frame, image_id=sample.sample_id)
            else:
                import cv2  # type: ignore[import-not-found]

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                detection = detector.detect_rgb_image(rgb, image_id=sample.sample_id)
        else:
            return "skipped", None, f"unsupported media_type: {sample.media_type}"

        if detection is None:
            return "no_face", None, ""
        return "detected", detection.to_dict(), ""
    except Exception as exc:  # noqa: BLE001 - record per-sample failure and continue.
        return "failed", None, f"{type(exc).__name__}: {exc}"


def write_keypoints(output_root: Path, sample: V1Sample, payload: dict[str, Any]) -> Path:
    relative = Path("keypoints") / sample.source_dataset / f"{sample.sample_id}.json"
    path = output_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_readme(output_root: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# FaceSymAi V1 Keypoint Dataset",
        "",
        "This dataset is generated from the downloaded media manifests and MediaPipe landmarks.",
        "",
        f"- Samples indexed: `{summary['samples_indexed']}`",
        f"- Detection status: `{json.dumps(summary['detection_status'], ensure_ascii=False, sort_keys=True)}`",
        f"- Detector backend: `{summary['detector_backend']}`",
        f"- Media types: `{json.dumps(summary['media_types'], ensure_ascii=False, sort_keys=True)}`",
        f"- Labels: `{json.dumps(summary['labels'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Layout",
        "",
        "- `metadata/v1_samples.csv`: one row per image or sampled video frame.",
        "- `metadata/v1_summary.json`: aggregate counts and source dataset roots.",
        "- `metadata/v1_keypoints.jsonl`: detected keypoint payloads, one line per detected sample.",
        "- `keypoints/<source_dataset>/<sample_id>.json`: per-sample keypoint payload.",
        "",
        "## Notes",
        "",
        "- V1 samples use the first frame for each video.",
        "- Source media remains in the original dataset folders; this V1 folder stores indexes and keypoints.",
        "- Metadata inherits sensitive source fields indirectly through IDs and labels; handle it as restricted data.",
    ]
    (output_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect FaceSymAi V1 keypoint dataset from media manifests.")
    parser.add_argument(
        "--dataset-root",
        action="append",
        type=Path,
        dest="dataset_roots",
        help="Dataset root containing metadata/records.csv and metadata/media_manifest.csv. Repeatable.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output V1 dataset directory.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N eligible media samples.")
    parser.add_argument("--roles", default=None, help="Comma-separated media roles to include.")
    parser.add_argument("--no-images", action="store_true", help="Exclude image media.")
    parser.add_argument("--no-videos", action="store_true", help="Exclude video media.")
    parser.add_argument("--dry-run", action="store_true", help="Only build the V1 sample index; do not run MediaPipe.")
    parser.add_argument(
        "--backend",
        choices=BACKENDS,
        default="auto",
        help="Use Face Landmarker when a model is available; otherwise auto attempts the legacy FaceMesh fallback.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help=f"MediaPipe Face Landmarker .task model path. Defaults to {DEFAULT_MODEL_PATH}; can also be set via {MODEL_ENV_VAR}.",
    )
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    parser.add_argument("--progress-every", type=int, default=100, help="Print progress every N samples.")
    return parser.parse_args(argv)


def resolve_model_path(args: argparse.Namespace) -> Path | None:
    if args.model is not None:
        return args.model.expanduser().resolve()
    env_value = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    if DEFAULT_MODEL_PATH.exists():
        return DEFAULT_MODEL_PATH.resolve()
    return None


def create_detector(args: argparse.Namespace) -> tuple[Any, str]:
    model_path = resolve_model_path(args)
    if args.backend in {"auto", "face_landmarker"} and model_path is not None:
        return (
            MediaPipeFaceLandmarkerDetector(
                model_path,
                max_num_faces=max(1, args.max_faces),
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=True,
            ),
            "face_landmarker",
        )
    if args.backend == "face_landmarker":
        raise FileNotFoundError(
            f"Face Landmarker requires a .task model. Pass --model or set {MODEL_ENV_VAR}."
        )
    return MediaPipeFaceMeshDetector(static_image_mode=True, max_num_faces=max(1, args.max_faces)), "face_mesh"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    dataset_roots = args.dataset_roots or [path for path in DEFAULT_DATASETS if path.exists()]
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    samples = build_samples(
        dataset_roots,
        include_images=not args.no_images,
        include_videos=not args.no_videos,
        roles=parse_roles(args.roles),
        limit=args.limit,
    )

    rows: list[dict[str, str]] = []
    keypoint_rows: list[dict[str, Any]] = []
    detector: Any | None = None
    detector_backend = "dry_run"
    try:
        if not args.dry_run:
            detector, detector_backend = create_detector(args)

        for index, sample in enumerate(samples, start=1):
            if args.dry_run:
                status, payload, error = "indexed", None, ""
            else:
                assert detector is not None
                status, payload, error = detect_sample(detector, sample)

            keypoints_path = None
            if payload is not None:
                payload = {
                    "sample": {
                        "sample_id": sample.sample_id,
                        "source_dataset": sample.source_dataset,
                        "record_id": sample.record_id,
                        "media_id": sample.media_id,
                        "media_role": sample.media_role,
                        "media_type": sample.media_type,
                        "source_media_path": sample.source_media_path.as_posix(),
                        "frame_index": sample.frame_index,
                        "frame_time_sec": sample.frame_time_sec,
                        **sample.label.to_dict(),
                    },
                    "keypoints": payload,
                }
                keypoints_path = write_keypoints(output_root, sample, payload)
                keypoint_rows.append(payload)

            rows.append(sample.metadata_row(output_root, status, keypoints_path, error))
            if args.progress_every and (index % args.progress_every == 0 or index == len(samples)):
                print(f"v1 collection progress: {index}/{len(samples)}", flush=True)
    except MediaPipeUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if detector is not None:
            detector.close()

    write_csv(output_root / "metadata" / "v1_samples.csv", rows, SAMPLE_FIELDS)
    write_jsonl(output_root / "metadata" / "v1_keypoints.jsonl", keypoint_rows)

    summary = {
        "samples_indexed": len(samples),
        "keypoints_written": len(keypoint_rows),
        "detector_backend": detector_backend,
        "source_datasets": [str(path.resolve()) for path in dataset_roots],
        "detection_status": dict(Counter(row["detection_status"] for row in rows)),
        "media_types": dict(Counter(row["media_type"] for row in rows)),
        "media_roles": dict(Counter(row["media_role"] for row in rows)),
        "labels": dict(Counter(row["label_value"] for row in rows)),
    }
    (output_root / "metadata" / "v1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_readme(output_root, summary)
    print(json.dumps({"output": str(output_root), **summary}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
