#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_by_name_20260119"
DEFAULT_MANIFEST = DEFAULT_DATASET / "metadata" / "01_manifest.csv"
DEFAULT_SPLITS = DEFAULT_DATASET / "metadata" / "05_patient_splits.csv"
DEFAULT_MODEL = PROJECT_ROOT / "third_party" / "stroke_detection_yolo" / "best.pt"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "yolo_comparison_20260608"

OUTPUT_FIELDS = [
    "patient_id",
    "image_path",
    "role",
    "split",
    "patient_label",
    "yolo_detections",
    "yolo_eye_max_severity",
    "yolo_mouth_max_severity",
    "yolo_any_stroke",
    "yolo_error",
]

SEVERITY_RANK = {
    "none": 0,
    "normal": 1,
    "weak": 2,
    "mid": 3,
    "severe": 4,
}

CLASS_TO_PART_SEVERITY = {
    "normaleye": ("eye", "normal"),
    "normalmouth": ("mouth", "normal"),
    "strokeeyemid": ("eye", "mid"),
    "strokeeyesevere": ("eye", "severe"),
    "strokeeyeweak": ("eye", "weak"),
    "strokemouthmid": ("mouth", "mid"),
    "strokemouthsevere": ("mouth", "severe"),
    "strokemouthweak": ("mouth", "weak"),
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the third-party YOLO stroke detector on the FaceSymAi V1 dataset.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST, help="FaceSymAi V1 manifest CSV.")
    parser.add_argument("--splits", type=Path, default=DEFAULT_SPLITS, help="Patient split CSV.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="YOLO model .pt file.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Output directory for predictions and summary.")
    parser.add_argument("--conf", type=float, default=0.25, help="YOLO confidence threshold.")
    parser.add_argument("--device", default="cpu", help="YOLO device. Default is cpu to avoid GPU memory contention.")
    parser.add_argument("--limit", type=int, default=None, help="Optional image limit for smoke tests.")
    parser.add_argument("--progress-every", type=int, default=50, help="Print progress every N images.")
    return parser.parse_args(argv)


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


def configure_logging(output_dir: Path) -> logging.Logger:
    output_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("run_yolo_on_v1_test_set")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(output_dir / "run.log", mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def normalize_class_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def resolve_image_path(value: str, manifest: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path

    candidates = [
        PROJECT_ROOT / path,
        manifest.parent.parent / path,
        manifest.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def load_split_map(path: Path) -> dict[str, str]:
    split_rows = read_csv(path)
    split_by_patient_sample_id: dict[str, str] = {}
    for row in split_rows:
        patient_sample_id = row.get("patient_sample_id", "")
        split = row.get("split", "")
        if patient_sample_id and split:
            split_by_patient_sample_id[patient_sample_id] = split
    return split_by_patient_sample_id


def validate_inputs(manifest: Path, splits: Path, model: Path) -> None:
    for path in (manifest, splits, model):
        if not path.exists():
            raise FileNotFoundError(path)


def load_manifest_rows(manifest: Path, splits: Path, limit: int | None) -> list[dict[str, str]]:
    manifest_rows = read_csv(manifest)
    if limit is not None:
        manifest_rows = manifest_rows[:limit]

    split_by_patient_sample_id = load_split_map(splits)
    missing_split = sorted(
        {
            row.get("patient_sample_id", "")
            for row in manifest_rows
            if row.get("patient_sample_id", "") not in split_by_patient_sample_id
        }
    )
    if missing_split:
        sample = ", ".join(missing_split[:10])
        raise ValueError(f"{len(missing_split)} patient_sample_id values are missing from split CSV: {sample}")

    for row in manifest_rows:
        row["split"] = split_by_patient_sample_id[row["patient_sample_id"]]
    return manifest_rows


def class_name_for(names: Any, class_id: int) -> str:
    if isinstance(names, Mapping):
        return str(names.get(class_id, class_id))
    if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)


def scalar(value: Any) -> float:
    if hasattr(value, "item"):
        return float(value.item())
    return float(value)


def extract_detections(result: Any) -> list[dict[str, Any]]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or getattr(boxes, "cls", None) is None or getattr(boxes, "conf", None) is None:
        return []

    names = getattr(result, "names", {})
    detections: list[dict[str, Any]] = []
    for class_value, conf_value in zip(boxes.cls, boxes.conf):
        class_id = int(scalar(class_value))
        detections.append(
            {
                "class": class_name_for(names, class_id),
                "conf": round(scalar(conf_value), 6),
            }
        )
    return detections


def summarize_severity(detections: list[dict[str, Any]]) -> tuple[str, str, bool]:
    max_by_part = {"eye": "none", "mouth": "none"}
    any_stroke = False

    for detection in detections:
        class_name = str(detection.get("class", ""))
        normalized = normalize_class_name(class_name)
        if normalized.startswith("stroke"):
            any_stroke = True

        part_severity = CLASS_TO_PART_SEVERITY.get(normalized)
        if not part_severity:
            continue
        part, severity = part_severity
        if SEVERITY_RANK[severity] > SEVERITY_RANK[max_by_part[part]]:
            max_by_part[part] = severity

    return max_by_part["eye"], max_by_part["mouth"], any_stroke


def prediction_row(
    manifest_row: Mapping[str, str],
    image_path: Path,
    detections: list[dict[str, Any]],
    error: str,
) -> dict[str, str]:
    eye_severity, mouth_severity, any_stroke = summarize_severity(detections)
    return {
        "patient_id": manifest_row.get("patient_id", ""),
        "image_path": image_path.as_posix(),
        "role": manifest_row.get("media_role", ""),
        "split": manifest_row.get("split", ""),
        "patient_label": manifest_row.get("label_group", ""),
        "yolo_detections": json.dumps(detections, ensure_ascii=False, separators=(",", ":")),
        "yolo_eye_max_severity": eye_severity,
        "yolo_mouth_max_severity": mouth_severity,
        "yolo_any_stroke": "True" if any_stroke else "False",
        "yolo_error": error or "none",
    }


def run_predictions(args: argparse.Namespace, logger: logging.Logger) -> tuple[list[dict[str, str]], dict[str, Any]]:
    validate_inputs(args.manifest, args.splits, args.model)

    logger.info("Loading manifest: %s", args.manifest)
    manifest_rows = load_manifest_rows(args.manifest, args.splits, args.limit)
    logger.info("Loaded %s images", len(manifest_rows))
    logger.info("Loading YOLO model: %s", args.model)

    try:
        from ultralytics import YOLO
    except Exception as exc:  # pragma: no cover - environment failure path
        raise RuntimeError("failed to import ultralytics.YOLO") from exc

    model = YOLO(str(args.model))
    started = time.time()
    output_rows: list[dict[str, str]] = []

    for index, manifest_row in enumerate(manifest_rows, start=1):
        image_source = manifest_row.get("organized_path") or manifest_row.get("image_path") or manifest_row.get("source_media_path")
        image_path = resolve_image_path(image_source, args.manifest)
        detections: list[dict[str, Any]] = []
        error = ""

        try:
            if not image_source:
                raise ValueError("manifest row has no organized_path/image_path/source_media_path")
            if not image_path.exists():
                raise FileNotFoundError(image_path)
            results = model.predict(source=str(image_path), conf=args.conf, device=args.device, verbose=False)
            if not results:
                raise RuntimeError("YOLO returned no results")
            detections = extract_detections(results[0])
        except Exception as exc:  # Keep one bad image from aborting the comparison run.
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("Failed image %s patient=%s role=%s error=%s", image_path, manifest_row.get("patient_id", ""), manifest_row.get("media_role", ""), error)

        output_rows.append(prediction_row(manifest_row, image_path, detections, error))

        if args.progress_every and index % args.progress_every == 0:
            logger.info("Processed %s/%s images", index, len(manifest_rows))

    elapsed = time.time() - started
    summary = build_summary(args, manifest_rows, output_rows, elapsed)
    return output_rows, summary


def build_summary(
    args: argparse.Namespace,
    manifest_rows: list[dict[str, str]],
    output_rows: list[dict[str, str]],
    elapsed_seconds: float,
) -> dict[str, Any]:
    class_distribution: Counter[str] = Counter()
    error_distribution: Counter[str] = Counter()
    total_detections = 0
    empty_detection_count = 0
    failed_images: list[dict[str, str]] = []

    for row in output_rows:
        detections = json.loads(row["yolo_detections"])
        total_detections += len(detections)
        if row["yolo_error"] == "none" and not detections:
            empty_detection_count += 1
        class_distribution.update(str(item.get("class", "")) for item in detections)
        if row["yolo_error"] != "none":
            error_distribution.update([row["yolo_error"]])
            failed_images.append(
                {
                    "patient_id": row["patient_id"],
                    "image_path": row["image_path"],
                    "role": row["role"],
                    "split": row["split"],
                    "patient_label": row["patient_label"],
                    "yolo_error": row["yolo_error"],
                }
            )

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "model_path": args.model.resolve().as_posix(),
        "manifest_path": args.manifest.resolve().as_posix(),
        "splits_path": args.splits.resolve().as_posix(),
        "output_csv": (args.output_dir / "yolo_per_image_predictions.csv").resolve().as_posix(),
        "run_log": (args.output_dir / "run.log").resolve().as_posix(),
        "conf": args.conf,
        "device": args.device,
        "limit": args.limit,
        "total_images": len(output_rows),
        "manifest_images_before_limit": len(read_csv(args.manifest)),
        "success_count": sum(1 for row in output_rows if row["yolo_error"] == "none"),
        "failure_count": sum(1 for row in output_rows if row["yolo_error"] != "none"),
        "empty_detection_count": empty_detection_count,
        "failed_images": failed_images,
        "total_detections": total_detections,
        "any_stroke_images": sum(1 for row in output_rows if row["yolo_any_stroke"] == "True"),
        "class_distribution": dict(sorted(class_distribution.items())),
        "error_distribution": dict(sorted(error_distribution.items())),
        "images_by_split": dict(sorted(Counter(row["split"] for row in output_rows).items())),
        "images_by_role": dict(sorted(Counter(row["role"] for row in output_rows).items())),
        "images_by_patient_label": dict(sorted(Counter(row["patient_label"] for row in output_rows).items())),
        "eye_max_severity_distribution": dict(sorted(Counter(row["yolo_eye_max_severity"] for row in output_rows).items())),
        "mouth_max_severity_distribution": dict(sorted(Counter(row["yolo_mouth_max_severity"] for row in output_rows).items())),
        "patients": len({row.get("patient_sample_id", "") for row in manifest_rows}),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logger = configure_logging(args.output_dir)
    logger.info("Starting YOLO V1 comparison run")
    logger.info("Arguments: %s", vars(args))

    try:
        output_rows, summary = run_predictions(args, logger)
        write_csv(args.output_dir / "yolo_per_image_predictions.csv", output_rows, OUTPUT_FIELDS)
        write_json(args.output_dir / "yolo_run_summary.json", summary)
    except Exception:
        logger.exception("YOLO V1 comparison run failed")
        return 1

    logger.info(
        "Finished YOLO V1 comparison run: total=%s success=%s failure=%s detections=%s elapsed_seconds=%s",
        summary["total_images"],
        summary["success_count"],
        summary["failure_count"],
        summary["total_detections"],
        summary["elapsed_seconds"],
    )
    logger.info("Wrote CSV: %s", args.output_dir / "yolo_per_image_predictions.csv")
    logger.info("Wrote summary: %s", args.output_dir / "yolo_run_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
