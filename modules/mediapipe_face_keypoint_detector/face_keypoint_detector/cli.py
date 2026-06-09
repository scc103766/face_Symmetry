from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

from .detector import MediaPipeFaceLandmarkerDetector, MediaPipeUnavailableError
from .sdk import MODEL_ENV_VAR, default_model_path
from .visualization import draw_landmarker_overlay


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reusable MediaPipe Face Landmarker keypoint detection module.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Image file(s) or directories to process.")
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help=f"Face Landmarker .task model. Defaults to module-local models/face_landmarker.task; can also be set via {MODEL_ENV_VAR}.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Output JSON file for one image or directory for many images.")
    parser.add_argument("--recursive", action="store_true", help="Recurse into input directories.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--annotated-output", type=Path, default=None, help="Directory for landmark overlay images.")
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    parser.add_argument("--allow-multiple-faces", action="store_true", help="Keep multi-face detections as detected.")
    parser.add_argument("--fail-on-no-face", action="store_true", help="Return non-zero when any image has no detected face.")
    return parser.parse_args(argv)


def iter_images(inputs: Iterable[Path], *, recursive: bool) -> list[Path]:
    images: list[Path] = []
    for raw_path in inputs:
        path = raw_path.expanduser()
        if path.is_dir():
            candidates = path.rglob("*") if recursive else path.iterdir()
            images.extend(item for item in candidates if item.is_file() and is_supported_image(item))
        elif path.is_file():
            if not is_supported_image(path):
                raise ValueError(f"unsupported image file: {path}")
            images.append(path)
        else:
            raise FileNotFoundError(f"input does not exist: {path}")
    return sorted({item.resolve() for item in images})


def is_supported_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def resolve_model_path(args: argparse.Namespace) -> Path:
    if args.model is not None:
        return args.model.expanduser().resolve()
    return default_model_path()


def detect_one(
    detector: MediaPipeFaceLandmarkerDetector,
    image_path: Path,
    *,
    model_path: Path,
    annotated_output: Path | None,
    allow_multiple_faces: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input": {"path": image_path.as_posix(), "image_id": image_path.stem},
        "runtime": {
            "backend": "mediapipe_face_landmarker",
            "model": model_path.as_posix(),
        },
    }
    try:
        detection = detector.detect_image_path(image_path, image_id=image_path.stem)
        if detection is None:
            payload.update({"status": "no_face", "detection": None})
            return payload

        detection_payload = detection.to_dict()
        face_count = int(detection_payload.get("face_count") or 1)
        status = "multiple_faces" if face_count > 1 and not allow_multiple_faces else "detected"
        payload.update({"status": status, "detection": detection_payload})
        if annotated_output is not None:
            annotation_path = annotation_path_for(annotated_output, image_path)
            payload["annotation"] = draw_landmarker_overlay(image_path, detection_payload, annotation_path)
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
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        images = iter_images(args.inputs, recursive=args.recursive)
        if not images:
            raise ValueError("no supported image files found")
        model_path = resolve_model_path(args)
        detector = MediaPipeFaceLandmarkerDetector(model_path, max_num_faces=max(1, args.max_faces))
    except Exception as exc:  # noqa: BLE001 - clear CLI error.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        results = [
            detect_one(
                detector,
                image,
                model_path=model_path,
                annotated_output=args.annotated_output.expanduser().resolve() if args.annotated_output else None,
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
