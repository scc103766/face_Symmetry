from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

from .feature_extractor import extract_features_from_detection
from .rule62 import DEFAULT_RULE_DIR, input_format_spec, load_rule62_config, normalize_role, evaluate_rule62


PROJECT_ROOT = Path(__file__).resolve().parents[3]
KEYPOINT_MODULE_ROOT = PROJECT_ROOT / "modules" / "mediapipe_face_keypoint_detector"
sys.path.insert(0, str(KEYPOINT_MODULE_ROOT))

from face_keypoint_detector.detector import MediaPipeFaceLandmarkerDetector, MediaPipeUnavailableError  # noqa: E402
from face_keypoint_detector.visualization import draw_landmarker_overlay  # noqa: E402


MODEL_ENV_VAR = "FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "mediapipe" / "face_landmarker.task"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ROLE_TOKENS = (
    "front_contour",
    "smile_teeth",
    "forehead_wrinkle",
    "eyes_closed",
    "eyes_right",
    "front",
    "smile",
    "teeth",
    "frown",
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rule 62 facial asymmetry analysis service for one subject/session.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Image file(s) or directories for one subject/session.")
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help=f"MediaPipe Face Landmarker .task model. Defaults to {DEFAULT_MODEL_PATH}; can also be set via {MODEL_ENV_VAR}.",
    )
    parser.add_argument(
        "--rule-dir",
        type=Path,
        default=DEFAULT_RULE_DIR,
        help="Directory containing 62_stable_weighted_feature_disease_rule_* CSV files.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Output JSON file, or directory for analysis.json.")
    parser.add_argument("--recursive", action="store_true", help="Recurse into input directories.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    parser.add_argument("--annotated-output", type=Path, default=None, help="Directory for MediaPipe landmark overlay images.")
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    parser.add_argument("--allow-multiple-faces", action="store_true", help="Use first face when MediaPipe detects multiple faces.")
    parser.add_argument("--fail-on-no-face", action="store_true", help="Return non-zero when any image has no usable face.")
    parser.add_argument(
        "--role",
        default=None,
        help="Override role for all images, for example smile_teeth or front_contour.",
    )
    parser.add_argument(
        "--image-role",
        action="append",
        default=[],
        help="Per-image role override as PATH=role. Can be repeated.",
    )
    parser.add_argument(
        "--default-role",
        default="unknown",
        help="Role used when filename inference and --image-role do not provide one.",
    )
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
    env_value = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return DEFAULT_MODEL_PATH.resolve()


def resolve_rule_dir(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (PROJECT_ROOT / expanded).resolve()


def parse_image_roles(items: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"--image-role must be PATH=role, got: {item}")
        path_text, role = item.split("=", 1)
        image_path = Path(path_text).expanduser().resolve()
        mapping[image_path.as_posix()] = normalize_role(role)
    return mapping


def media_role_for_image(
    image_path: Path,
    *,
    global_role: str | None,
    image_roles: Mapping[str, str],
    default_role: str,
) -> str:
    if global_role:
        return normalize_role(global_role)
    resolved = image_path.resolve().as_posix()
    if resolved in image_roles:
        return image_roles[resolved]
    inferred = infer_role_from_filename(image_path)
    return inferred or normalize_role(default_role)


def infer_role_from_filename(path: Path) -> str | None:
    text = path.as_posix().lower().replace("-", "_").replace(" ", "_")
    for token in ROLE_TOKENS:
        if token in text:
            return token
    return None


def analyze_one(
    detector: MediaPipeFaceLandmarkerDetector,
    image_path: Path,
    *,
    media_role: str,
    model_path: Path,
    rule_feature_names: set[str],
    annotated_output: Path | None,
    allow_multiple_faces: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    image_id = image_path.stem
    public_result: dict[str, Any] = {
        "input": {
            "path": image_path.as_posix(),
            "image_id": image_id,
            "media_role": media_role,
        },
        "runtime": {
            "backend": "mediapipe_face_landmarker",
            "model": model_path.as_posix(),
        },
    }
    feature_row: dict[str, Any] = {
        "image_id": image_id,
        "media_role": media_role,
        "status": "failed",
        "features": {},
    }
    try:
        detection = detector.detect_image_path(image_path, image_id=image_id)
        if detection is None:
            public_result.update({"status": "no_face", "detection_summary": None})
            feature_row["status"] = "no_face"
            return public_result, feature_row

        detection_payload = detection.to_dict()
        face_count = int(detection_payload.get("face_count") or 1)
        status = "multiple_faces" if face_count > 1 and not allow_multiple_faces else "detected"
        public_result["status"] = status
        public_result["detection_summary"] = detection_summary(detection_payload)
        if annotated_output is not None:
            annotation_path = annotation_path_for(annotated_output, image_path)
            public_result["annotation"] = draw_landmarker_overlay(image_path, detection_payload, annotation_path)
        if status != "detected":
            feature_row["status"] = status
            return public_result, feature_row

        features = extract_features_from_detection(detection_payload)
        feature_row.update({"status": "detected", "features": features})
        public_result["feature_summary"] = {
            "total_feature_count": len(features),
            "rule_feature_value_count": sum(1 for name in rule_feature_names if name in features),
        }
        public_result["rule_feature_values"] = {
            name: round(float(features[name]), 6)
            for name in sorted(rule_feature_names)
            if name in features
        }
    except Exception as exc:  # noqa: BLE001 - service records per-image failures.
        public_result.update({"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}})
        feature_row["status"] = "failed"
    return public_result, feature_row


def detection_summary(detection: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "face_count": int(detection.get("face_count") or 0),
        "raw_landmark_count": len(detection.get("raw_landmarks") or []),
        "semantic_landmark_count": len(detection.get("landmarks") or {}),
        "blendshape_count": len(detection.get("blendshapes") or {}),
        "facial_transformation_matrix_count": len(detection.get("facial_transformation_matrixes") or []),
        "detector": detection.get("detector") or detection.get("backend"),
        "detector_version": detection.get("detector_version"),
        "landmark_schema_version": detection.get("landmark_schema_version"),
    }


def annotation_path_for(output: Path, image_path: Path) -> Path:
    digest = hashlib.sha1(image_path.as_posix().encode("utf-8")).hexdigest()[:10]
    return output / f"{image_path.stem}__{digest}.jpg"


def build_report(
    *,
    image_results: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    model_path: Path,
    rule_config: Any,
) -> dict[str, Any]:
    analysis = evaluate_rule62(feature_rows, rule_config)
    status_counts = {
        status: sum(1 for item in image_results if item.get("status") == status)
        for status in sorted({str(item.get("status")) for item in image_results})
    }
    return {
        "service": "facial_asymmetry_service_rule62",
        "service_version": "v1",
        "status": "analyzed",
        "runtime": {
            "keypoint_module": "modules/mediapipe_face_keypoint_detector",
            "model": model_path.as_posix(),
        },
        "rule": rule_config.summary(),
        "input_format": input_format_spec(),
        "input_count": len(image_results),
        "status_counts": status_counts,
        "analysis": analysis,
        "images": image_results,
    }


def write_report(report: Mapping[str, Any], output: Path | None, *, pretty: bool) -> None:
    indent = 2 if pretty else None
    text = json.dumps(report, ensure_ascii=False, indent=indent, sort_keys=True) + "\n"
    if output is None:
        print(text, end="")
        return
    output = output.expanduser().resolve()
    target = output if output.suffix.lower() == ".json" else output / "analysis.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        images = iter_images(args.inputs, recursive=args.recursive)
        if not images:
            raise ValueError("no supported image files found")
        image_roles = parse_image_roles(args.image_role)
        model_path = resolve_model_path(args)
        rule_config = load_rule62_config(resolve_rule_dir(args.rule_dir))
        detector = MediaPipeFaceLandmarkerDetector(model_path, max_num_faces=max(1, args.max_faces))
    except Exception as exc:  # noqa: BLE001 - clear CLI/service bootstrap error.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    rule_feature_names = {feature.feature_name for feature in rule_config.features}
    image_results: list[dict[str, Any]] = []
    feature_rows: list[dict[str, Any]] = []
    annotated_output = args.annotated_output.expanduser().resolve() if args.annotated_output else None
    try:
        for image in images:
            media_role = media_role_for_image(
                image,
                global_role=args.role,
                image_roles=image_roles,
                default_role=args.default_role,
            )
            public_result, feature_row = analyze_one(
                detector,
                image,
                media_role=media_role,
                model_path=model_path,
                rule_feature_names=rule_feature_names,
                annotated_output=annotated_output,
                allow_multiple_faces=args.allow_multiple_faces,
            )
            image_results.append(public_result)
            feature_rows.append(feature_row)
    finally:
        detector.close()

    report = build_report(
        image_results=image_results,
        feature_rows=feature_rows,
        model_path=model_path,
        rule_config=rule_config,
    )
    write_report(report, args.output, pretty=args.pretty)
    if any(result.get("status") == "failed" for result in image_results):
        return 1
    if args.fail_on_no_face and any(result.get("status") in {"no_face", "multiple_faces"} for result in image_results):
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MediaPipeUnavailableError as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
