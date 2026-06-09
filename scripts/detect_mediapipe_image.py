#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.landmarks import (  # noqa: E402
    MediaPipeFaceLandmarkerDetector,
    MediaPipeFaceMeshDetector,
    MediaPipeUnavailableError,
    draw_landmarker_overlay,
)
from facesymai.quality import QualityGate, infer_media_type  # noqa: E402
from facesymai.risk import FacialSymmetryRiskAnalyzer  # noqa: E402
from facesymai.schemas import FaceLandmarks  # noqa: E402


BACKENDS = ("auto", "face_landmarker", "face_mesh")
MODEL_ENV_VAR = "FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect FaceSymAi landmarks from local images with MediaPipe.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Image file(s) or directories to process.")
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
    parser.add_argument("--output", type=Path, default=None, help="Output JSON file for one image or directory for many images.")
    parser.add_argument("--recursive", action="store_true", help="Recurse into input directories.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--annotated-output", type=Path, default=None, help="Directory for landmark overlay images.")
    parser.add_argument("--include-quality", action="store_true", help="Include the current image quality gate result.")
    parser.add_argument("--include-analysis", action="store_true", help="Run the current symmetry risk analyzer on detected landmarks.")
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    parser.add_argument("--allow-multiple-faces", action="store_true", help="Do not mark multi-face detections as rejected.")
    parser.add_argument("--fail-on-no-face", action="store_true", help="Return non-zero when any image has no detected face.")
    return parser.parse_args(argv)


def iter_images(inputs: Iterable[Path], *, recursive: bool) -> list[Path]:
    images: list[Path] = []
    for raw_path in inputs:
        path = raw_path.expanduser()
        if path.is_dir():
            candidates = path.rglob("*") if recursive else path.iterdir()
            images.extend(item for item in candidates if item.is_file() and infer_media_type(item) == "image")
        elif path.is_file():
            if infer_media_type(path) != "image":
                raise ValueError(f"unsupported image file: {path}")
            images.append(path)
        else:
            raise FileNotFoundError(f"input does not exist: {path}")
    return sorted({item.resolve() for item in images})


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


def detect_one(
    detector: Any,
    image_path: Path,
    *,
    detector_backend: str,
    annotated_output: Path | None,
    include_quality: bool,
    include_analysis: bool,
    allow_multiple_faces: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": {"path": image_path.as_posix(), "image_id": image_path.stem},
        "runtime": {"backend": detector_backend},
    }
    try:
        detection = detector.detect_image_path(image_path, image_id=image_path.stem)
        if detection is None:
            payload.update({"status": "no_face", "detection": None})
        else:
            detection_payload = detection.to_dict()
            face_count = int(detection_payload.get("face_count") or 1)
            status = "multiple_faces" if face_count > 1 and not allow_multiple_faces else "detected"
            payload.update({"status": status, "detection": detection_payload})
            if annotated_output is not None:
                annotation_path = annotation_path_for(annotated_output, image_path)
                payload["annotation"] = draw_landmarker_overlay(image_path, detection_payload, annotation_path)
            if include_analysis and status == "detected":
                face = FaceLandmarks.from_payload(detection_payload)
                payload["analysis"] = FacialSymmetryRiskAnalyzer().analyze(face).to_dict()

        if include_quality:
            payload["quality"] = QualityGate().evaluate_image(image_path).to_dict()
    except Exception as exc:  # noqa: BLE001 - CLI records per-image failures.
        payload.update({"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}})
    return payload


def output_path_for(output: Path, image_path: Path, *, force_directory: bool) -> Path:
    if output.suffix.lower() == ".json" and not force_directory:
        return output
    digest = hashlib.sha1(image_path.as_posix().encode("utf-8")).hexdigest()[:10]
    return output / f"{image_path.stem}__{digest}.json"


def annotation_path_for(output: Path, image_path: Path) -> Path:
    digest = hashlib.sha1(image_path.as_posix().encode("utf-8")).hexdigest()[:10]
    return output / f"{image_path.stem}__{digest}.jpg"


def write_outputs(results: list[dict[str, Any]], output: Path | None, *, pretty: bool) -> None:
    indent = 2 if pretty else None
    if output is None:
        data: Any = results[0] if len(results) == 1 else {"results": results}
        print(json.dumps(data, ensure_ascii=False, indent=indent, sort_keys=True))
        return

    output = output.expanduser().resolve()
    if len(results) == 1 and output.suffix.lower() == ".json":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results[0], ensure_ascii=False, indent=indent, sort_keys=True) + "\n", encoding="utf-8")
        return

    output.mkdir(parents=True, exist_ok=True)
    for result in results:
        image_path = Path(result["input"]["path"])
        target = output_path_for(output, image_path, force_directory=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=indent, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "total": len(results),
        "status_counts": {
            status: sum(1 for item in results if item.get("status") == status)
            for status in sorted({str(item.get("status")) for item in results})
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        images = iter_images(args.inputs, recursive=args.recursive)
        if not images:
            raise ValueError("no supported image files found")
        detector, detector_backend = create_detector(args)
    except Exception as exc:  # noqa: BLE001 - clear CLI error.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        results = [
            detect_one(
                detector,
                image,
                detector_backend=detector_backend,
                annotated_output=args.annotated_output.expanduser().resolve() if args.annotated_output else None,
                include_quality=args.include_quality,
                include_analysis=args.include_analysis,
                allow_multiple_faces=args.allow_multiple_faces,
            )
            for image in images
        ]
    finally:
        detector.close()

    write_outputs(results, args.output, pretty=args.pretty)
    if any(result.get("status") == "failed" for result in results):
        return 1
    if args.fail_on_no_face and any(result.get("status") in {"no_face", "multiple_faces"} for result in results):
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MediaPipeUnavailableError as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
