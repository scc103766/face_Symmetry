#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.quality import QualityGate, QualityGateConfig, QualityGateResult, infer_media_type  # noqa: E402


DEFAULT_SOURCE = PROJECT_ROOT / "datasets" / "stroke_patient_outcome_by_name_20260119"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "stroke_patient_outcome_quality_gated_20260119"

REPORT_FIELDS = [
    "source_index",
    "label_group",
    "patient_sample_id",
    "patient_name",
    "record_id",
    "media_id",
    "media_role",
    "media_type",
    "source_path",
    "gated_path",
    "placement",
    "quality_score",
    "quality_level",
    "hard_reject",
    "accepted_for_scoring",
    "reason_codes",
    "reason_messages",
    "width",
    "height",
    "face_count",
    "face_short_side",
    "eye_count",
    "laplacian_variance",
    "brightness_mean",
    "bad_exposure_ratio",
    "left_right_brightness_delta",
    "duration_sec",
    "fps",
    "frame_count",
    "sampled_frames",
    "quality_json",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def detect_index(source: Path) -> tuple[Path, str]:
    candidates = [
        (source / "metadata" / "media_index.csv", "organized"),
        (source / "metadata" / "media_manifest.csv", "manifest"),
    ]
    for path, index_type in candidates:
        if path.exists():
            return path, index_type
    raise FileNotFoundError(f"no media index found under {source}/metadata")


def source_path_for_row(source: Path, row: dict[str, str], index_type: str) -> Path:
    if row.get("source_media_path"):
        return Path(row["source_media_path"])
    key = "organized_path" if index_type == "organized" else "local_path"
    return source / row.get(key, "")


def organized_relative(row: dict[str, str], source_path: Path) -> Path:
    if row.get("organized_path"):
        return Path(row["organized_path"])
    label = row.get("label_group") or "未分组"
    patient = row.get("patient_sample_id") or row.get("record_id") or "unknown_sample"
    media_type = row.get("media_type") or infer_media_type(source_path)
    type_dir = "images" if media_type == "image" else "videos" if media_type == "video" else "unknown"
    return Path(label) / patient / type_dir / source_path.name


def place_file(source_path: Path, output_path: Path, mode: str) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size == source_path.stat().st_size:
        return "exists"
    if output_path.exists() or output_path.is_symlink():
        output_path.unlink()
    if mode == "none":
        return ""
    if mode == "copy":
        shutil.copy2(source_path, output_path)
        return "copy"
    if mode == "symlink":
        output_path.symlink_to(source_path)
        return "symlink"
    try:
        os.link(source_path, output_path)
        return "hardlink"
    except OSError:
        shutil.copy2(source_path, output_path)
        return "copy"


def reason_codes(result: QualityGateResult) -> str:
    return "|".join(reason.code for reason in result.reasons)


def reason_messages(result: QualityGateResult) -> str:
    return "|".join(reason.message for reason in result.reasons)


def first_frame_metric(result: QualityGateResult, key: str) -> str:
    if not result.frame_results:
        return ""
    value = result.frame_results[0].metrics.get(key)
    if value is None:
        return ""
    return f"{value:.6g}"


def first_frame_value(result: QualityGateResult, attr: str) -> str:
    if not result.frame_results:
        return ""
    value = getattr(result.frame_results[0], attr)
    if value is None:
        return ""
    return str(value)


def face_short_side(result: QualityGateResult) -> str:
    if not result.frame_results or result.frame_results[0].face_box is None:
        return ""
    return str(result.frame_results[0].face_box.short_side)


def summary_payload(rows: list[dict[str, str]], source: Path, output: Path, config: QualityGateConfig) -> dict[str, Any]:
    return {
        "source_dataset": source.as_posix(),
        "output_dataset": output.as_posix(),
        "quality_gate_version": config.version,
        "media_files": len(rows),
        "quality_levels": dict(Counter(row["quality_level"] for row in rows)),
        "accepted_for_scoring": sum(1 for row in rows if row["accepted_for_scoring"] == "true"),
        "hard_reject": sum(1 for row in rows if row["hard_reject"] == "true"),
        "media_types": dict(Counter(row["media_type"] for row in rows)),
        "label_groups": dict(Counter(row["label_group"] for row in rows if row["label_group"])),
        "top_reasons": dict(Counter(code for row in rows for code in row["reason_codes"].split("|") if code).most_common(20)),
        "placements": dict(Counter(row["placement"] for row in rows if row["placement"])),
    }


def write_readme(output: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Stroke Patient Outcome Quality-Gated Inputs",
        "",
        f"- Source dataset: `{summary['source_dataset']}`",
        f"- Quality gate version: `{summary['quality_gate_version']}`",
        f"- Media files checked: `{summary['media_files']}`",
        f"- Quality levels: `{json.dumps(summary['quality_levels'], ensure_ascii=False, sort_keys=True)}`",
        f"- Accepted for scoring: `{summary['accepted_for_scoring']}`",
        f"- Hard rejects: `{summary['hard_reject']}`",
        "",
        "## Layout",
        "",
        "- `accepted/`: media that passed quality gate and can enter scoring.",
        "- `review/`: media that is usable but should carry lower confidence or manual review.",
        "- `rejected/`: media blocked by hard quality or compliance reasons.",
        "- `metadata/quality_gate_report.csv`: one row per checked media file.",
        "- `metadata/quality_gate_summary.json`: aggregate counts and top rejection reasons.",
        "- `metadata/rejected_inputs.csv`: blocked inputs only.",
        "",
        "## Gate Scope",
        "",
        "V1 checks file readability, extension, size, image resolution, video duration, sampled frame readability, single-face proxy via OpenCV Haar, face size, blur, brightness, exposure, left/right lighting balance, and a coarse eye visibility proxy.",
        "",
        "This is an input quality and compliance gate, not a medical diagnosis or full legal compliance certification.",
    ]
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run FaceSymAi V1 quality gate over image/video inputs.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Dataset root with media_index.csv or media_manifest.csv.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Quality-gated output root.")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows.")
    parser.add_argument("--mode", choices=["hardlink", "copy", "symlink", "none"], default="hardlink")
    parser.add_argument("--no-face-required", action="store_true", help="Do not hard reject when face detection is unavailable.")
    parser.add_argument("--block-on-eye-detection", action="store_true", help="Hard reject if eye proxy detects no visible eyes.")
    parser.add_argument("--video-sample-count", type=int, default=3, help="Number of frames to sample per video.")
    parser.add_argument("--progress-every", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source = args.source.resolve()
    output = args.output.resolve()
    index_path, index_type = detect_index(source)
    media_rows = read_csv(index_path)
    if args.limit is not None:
        media_rows = media_rows[: args.limit]

    config = QualityGateConfig(
        require_face_detection=not args.no_face_required,
        block_on_eye_detection=args.block_on_eye_detection,
        video_sample_count=args.video_sample_count,
    )
    gate = QualityGate(config)
    report_rows: list[dict[str, str]] = []

    for index, row in enumerate(media_rows, start=1):
        source_path = source_path_for_row(source, row, index_type)
        media_type = row.get("media_type") or infer_media_type(source_path)
        result = gate.evaluate_media(source_path, media_type=media_type, role=row.get("media_role"))
        bucket = "accepted" if result.quality_level == "pass" else "review" if result.quality_level == "review" else "rejected"
        relative = organized_relative(row, source_path)
        gated_path = output / bucket / relative
        placement = ""
        if source_path.exists():
            placement = place_file(source_path, gated_path, args.mode)
        report_rows.append(
            {
                "source_index": str(index),
                "label_group": row.get("label_group", ""),
                "patient_sample_id": row.get("patient_sample_id", ""),
                "patient_name": row.get("patient_name", ""),
                "record_id": row.get("record_id", ""),
                "media_id": row.get("media_id", ""),
                "media_role": row.get("media_role", ""),
                "media_type": media_type,
                "source_path": source_path.as_posix(),
                "gated_path": gated_path.relative_to(output).as_posix(),
                "placement": placement,
                "quality_score": f"{result.quality_score:.6f}",
                "quality_level": result.quality_level,
                "hard_reject": "true" if result.hard_reject else "false",
                "accepted_for_scoring": "true" if result.accepted_for_scoring else "false",
                "reason_codes": reason_codes(result),
                "reason_messages": reason_messages(result),
                "width": first_frame_value(result, "width"),
                "height": first_frame_value(result, "height"),
                "face_count": first_frame_value(result, "face_count"),
                "face_short_side": face_short_side(result),
                "eye_count": first_frame_value(result, "eye_count"),
                "laplacian_variance": first_frame_metric(result, "laplacian_variance"),
                "brightness_mean": first_frame_metric(result, "brightness_mean"),
                "bad_exposure_ratio": first_frame_metric(result, "bad_exposure_ratio"),
                "left_right_brightness_delta": first_frame_metric(result, "left_right_brightness_delta"),
                "duration_sec": str(result.metrics.get("duration_sec", "")),
                "fps": str(result.metrics.get("fps", "")),
                "frame_count": str(result.metrics.get("frame_count", "")),
                "sampled_frames": str(result.metrics.get("sampled_frames", "")),
                "quality_json": json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True),
            }
        )
        if args.progress_every and (index % args.progress_every == 0 or index == len(media_rows)):
            print(f"quality gate progress: {index}/{len(media_rows)}", flush=True)

    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "metadata" / "quality_gate_report.csv", report_rows, REPORT_FIELDS)
    write_csv(
        output / "metadata" / "rejected_inputs.csv",
        [row for row in report_rows if row["quality_level"] == "reject"],
        REPORT_FIELDS,
    )
    summary = summary_payload(report_rows, source, output, config)
    (output / "metadata" / "quality_gate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_readme(output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
