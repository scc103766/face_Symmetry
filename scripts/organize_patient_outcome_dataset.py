#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "datasets" / "stroke_media_dataset_20260119"
DEFAULT_OUTPUT = PROJECT_ROOT / "datasets" / "stroke_patient_outcome_by_name_20260119"

DEFAULT_LABEL_FIELDS = (
    "\u8111\u5352\u4e2d\u662f\u5426\u75c5\u53d1",
    "\u662f\u5426\u60a3\u75c5",
)
PATIENT_NAME_FIELD = "\u60a3\u8005\u59d3\u540d"
PATIENT_ID_FIELD = "\u60a3\u8005id"

MEDIA_INDEX_FIELDS = [
    "label_group",
    "patient_sample_id",
    "patient_name",
    "patient_id",
    "record_id",
    "source_excel_row",
    "sex",
    "age",
    "primary_label_field",
    "primary_label_value",
    "stroke_onset_label",
    "disease_label",
    "media_id",
    "media_role",
    "field_name",
    "media_type",
    "organized_path",
    "source_media_path",
    "link_mode",
    "bytes",
    "sha256",
]

PATIENT_INDEX_FIELDS = [
    "label_group",
    "patient_sample_id",
    "patient_name",
    "patient_id",
    "record_count",
    "media_count",
    "image_count",
    "video_count",
    "sex_values",
    "age_values",
    "record_ids",
    "source_excel_rows",
    "primary_label_field",
    "primary_label_values",
    "stroke_onset_labels",
    "disease_labels",
    "patient_dir",
]


@dataclass
class PatientSummary:
    label_group: str
    patient_sample_id: str
    patient_name: str
    patient_id: str
    patient_dir: Path
    record_ids: set[str] = field(default_factory=set)
    excel_rows: set[str] = field(default_factory=set)
    sex_values: set[str] = field(default_factory=set)
    age_values: set[str] = field(default_factory=set)
    primary_label_values: set[str] = field(default_factory=set)
    stroke_onset_labels: set[str] = field(default_factory=set)
    disease_labels: set[str] = field(default_factory=set)
    media_count: int = 0
    image_count: int = 0
    video_count: int = 0
    preview_paths: list[str] = field(default_factory=list)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean_path_part(value: str, fallback: str) -> str:
    text = (value or "").strip() or fallback
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("._ ")
    return text or fallback


def id_part(value: str, fallback: str) -> str:
    text = (value or "").strip()
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-")
    return text or fallback


def choose_label(record: dict[str, str], label_field: str | None) -> tuple[str, str]:
    if label_field:
        return label_field, record.get(label_field, "").strip()
    for field_name in DEFAULT_LABEL_FIELDS:
        value = record.get(field_name, "").strip()
        if value:
            return field_name, value
    return "", ""


def label_group(value: str) -> str:
    normalized = value.strip()
    if normalized == "\u662f":
        return "\u60a3\u75c5"
    if normalized == "\u5426":
        return "\u4e0d\u60a3\u75c5"
    return "\u672a\u5206\u7c7b"


def link_media(source: Path, target: Path, mode: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return "exists"
    if target.exists():
        target.unlink()

    if mode == "copy":
        shutil.copy2(source, target)
        return "copy"
    if mode == "symlink":
        target.symlink_to(source)
        return "symlink"

    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        shutil.copy2(source, target)
        return "copy"


def relative_to_output(path: Path, output_root: Path) -> str:
    return path.relative_to(output_root).as_posix()


def build_gallery_html(
    output_root: Path,
    patient_rows: list[dict[str, str]],
    media_rows: list[dict[str, str]],
    summary: dict[str, object],
) -> None:
    media_by_patient: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in media_rows:
        media_by_patient[row["patient_sample_id"]].append(row)

    label_counts = Counter(row["label_group"] for row in patient_rows)
    parts = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>脑卒中患者样本媒体浏览</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#f6f7f9;color:#1d232f}",
        "header{padding:24px 32px;background:#ffffff;border-bottom:1px solid #dde2ea;position:sticky;top:0;z-index:2}",
        "h1{font-size:24px;margin:0 0 12px}",
        ".stats{display:flex;gap:12px;flex-wrap:wrap}.stat{background:#eef2f7;border:1px solid #dde2ea;border-radius:6px;padding:8px 10px;font-size:14px}",
        "main{padding:24px 32px}.group{margin-bottom:28px}.group h2{font-size:20px;margin:0 0 12px}",
        "details.patient{background:#fff;border:1px solid #dde2ea;border-radius:8px;margin:10px 0;overflow:hidden}",
        "summary{cursor:pointer;padding:12px 14px;font-weight:650}",
        ".meta{padding:0 14px 12px;color:#546170;font-size:13px}",
        ".media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;padding:0 14px 14px}",
        ".media{border:1px solid #e1e6ef;border-radius:6px;background:#fbfcfe;overflow:hidden}.media img,.media video{display:block;width:100%;height:130px;object-fit:cover;background:#111}",
        ".caption{font-size:12px;line-height:1.35;padding:6px 8px;color:#384454;word-break:break-all}",
        "a{color:#0f5faf;text-decoration:none}a:hover{text-decoration:underline}",
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>脑卒中患者样本媒体浏览</h1>",
        '<div class="stats">',
    ]
    for key, value in summary.items():
        parts.append(f'<span class="stat">{html.escape(str(key))}: {html.escape(str(value))}</span>')
    for group, count in label_counts.items():
        parts.append(f'<span class="stat">{html.escape(group)}患者: {count}</span>')
    parts.extend(["</div>", "</header>", "<main>"])

    for group in ["\u60a3\u75c5", "\u4e0d\u60a3\u75c5", "\u672a\u5206\u7c7b"]:
        group_patients = [row for row in patient_rows if row["label_group"] == group]
        if not group_patients:
            continue
        parts.append(f'<section class="group"><h2>{html.escape(group)} ({len(group_patients)} 位患者)</h2>')
        for patient in group_patients:
            patient_media = media_by_patient[patient["patient_sample_id"]]
            title = (
                f'{patient["patient_name"]} | 图片 {patient["image_count"]} | '
                f'视频 {patient["video_count"]} | 记录 {patient["record_count"]}'
            )
            parts.append('<details class="patient">')
            parts.append(f"<summary>{html.escape(title)}</summary>")
            meta = (
                f'患者ID: {patient["patient_id"]} | 年龄: {patient["age_values"] or "-"} | '
                f'性别: {patient["sex_values"] or "-"} | 记录: {patient["record_ids"]}'
            )
            parts.append(f'<div class="meta">{html.escape(meta)}</div>')
            parts.append('<div class="media-grid">')
            for media in patient_media[:80]:
                rel = media["organized_path"]
                role = html.escape(media["media_role"])
                filename = html.escape(Path(rel).name)
                if media["media_type"] == "image":
                    preview = f'<a href="{html.escape(rel)}"><img loading="lazy" src="{html.escape(rel)}" alt="{role}"></a>'
                else:
                    preview = f'<video controls preload="metadata" src="{html.escape(rel)}"></video>'
                parts.append('<div class="media">')
                parts.append(preview)
                parts.append(f'<div class="caption">{role}<br>{filename}</div>')
                parts.append("</div>")
            if len(patient_media) > 80:
                parts.append(f'<div class="caption">该患者还有 {len(patient_media) - 80} 个媒体文件，详见 CSV 索引。</div>')
            parts.append("</div></details>")
        parts.append("</section>")

    parts.extend(["</main>", "</body>", "</html>"])
    (output_root / "index.html").write_text("\n".join(parts) + "\n", encoding="utf-8")


def organize_dataset(source_root: Path, output_root: Path, label_field: str | None, mode: str) -> dict[str, object]:
    records_path = source_root / "metadata" / "records.csv"
    media_path = source_root / "metadata" / "media_manifest.csv"
    if not records_path.exists() or not media_path.exists():
        raise FileNotFoundError(f"source dataset must contain metadata files under {source_root}")

    records = {row["record_id"]: row for row in read_csv(records_path)}
    media_items = read_csv(media_path)
    output_root.mkdir(parents=True, exist_ok=True)

    media_rows: list[dict[str, str]] = []
    patients: dict[str, PatientSummary] = {}
    link_modes = Counter()
    skipped = Counter()

    for media in media_items:
        if media.get("download_status") not in {"downloaded", "exists"}:
            skipped["download_status"] += 1
            continue
        record = records.get(media.get("record_id", ""))
        if record is None:
            skipped["missing_record"] += 1
            continue
        source_media = source_root / media.get("local_path", "")
        if not source_media.exists():
            skipped["missing_file"] += 1
            continue

        label_name, label_value = choose_label(record, label_field)
        group = label_group(label_value)
        patient_name = record.get(PATIENT_NAME_FIELD, "").strip() or f"unknown_row_{record.get('source_excel_row', '')}"
        patient_id = id_part(record.get(PATIENT_ID_FIELD, ""), record.get("source_excel_row", "unknown"))
        patient_sample_id = f"{clean_path_part(patient_name, 'unknown')}__pid{patient_id}"
        patient_dir = output_root / group / patient_sample_id
        type_dir = "images" if media.get("media_type") == "image" else "videos" if media.get("media_type") == "video" else "unknown"
        target = patient_dir / type_dir / media.get("filename", Path(source_media).name)
        link_mode = link_media(source_media, target, mode)
        link_modes[link_mode] += 1

        summary = patients.get(patient_sample_id)
        if summary is None:
            summary = PatientSummary(
                label_group=group,
                patient_sample_id=patient_sample_id,
                patient_name=patient_name,
                patient_id=patient_id,
                patient_dir=patient_dir,
            )
            patients[patient_sample_id] = summary

        summary.record_ids.add(record.get("record_id", ""))
        summary.excel_rows.add(record.get("source_excel_row", ""))
        summary.sex_values.add(record.get("\u6027\u522b", ""))
        summary.age_values.add(record.get("\u5e74\u9f84", ""))
        summary.primary_label_values.add(label_value)
        summary.stroke_onset_labels.add(record.get("\u8111\u5352\u4e2d\u662f\u5426\u75c5\u53d1", ""))
        summary.disease_labels.add(record.get("\u662f\u5426\u60a3\u75c5", ""))
        summary.media_count += 1
        if media.get("media_type") == "image":
            summary.image_count += 1
        elif media.get("media_type") == "video":
            summary.video_count += 1
        if len(summary.preview_paths) < 12:
            summary.preview_paths.append(relative_to_output(target, output_root))

        media_rows.append(
            {
                "label_group": group,
                "patient_sample_id": patient_sample_id,
                "patient_name": patient_name,
                "patient_id": patient_id,
                "record_id": record.get("record_id", ""),
                "source_excel_row": record.get("source_excel_row", ""),
                "sex": record.get("\u6027\u522b", ""),
                "age": record.get("\u5e74\u9f84", ""),
                "primary_label_field": label_name,
                "primary_label_value": label_value,
                "stroke_onset_label": record.get("\u8111\u5352\u4e2d\u662f\u5426\u75c5\u53d1", ""),
                "disease_label": record.get("\u662f\u5426\u60a3\u75c5", ""),
                "media_id": media.get("media_id", ""),
                "media_role": media.get("media_role", ""),
                "field_name": media.get("field_name", ""),
                "media_type": media.get("media_type", ""),
                "organized_path": relative_to_output(target, output_root),
                "source_media_path": source_media.as_posix(),
                "link_mode": link_mode,
                "bytes": media.get("bytes", ""),
                "sha256": media.get("sha256", ""),
            }
        )

    patient_rows: list[dict[str, str]] = []
    for summary in sorted(patients.values(), key=lambda item: (item.label_group, item.patient_name, item.patient_id)):
        patient_rows.append(
            {
                "label_group": summary.label_group,
                "patient_sample_id": summary.patient_sample_id,
                "patient_name": summary.patient_name,
                "patient_id": summary.patient_id,
                "record_count": str(len({item for item in summary.record_ids if item})),
                "media_count": str(summary.media_count),
                "image_count": str(summary.image_count),
                "video_count": str(summary.video_count),
                "sex_values": "|".join(sorted(item for item in summary.sex_values if item)),
                "age_values": "|".join(sorted(item for item in summary.age_values if item)),
                "record_ids": "|".join(sorted(item for item in summary.record_ids if item)),
                "source_excel_rows": "|".join(sorted(item for item in summary.excel_rows if item)),
                "primary_label_field": label_field or "auto",
                "primary_label_values": "|".join(sorted(item for item in summary.primary_label_values if item)),
                "stroke_onset_labels": "|".join(sorted(item for item in summary.stroke_onset_labels if item)),
                "disease_labels": "|".join(sorted(item for item in summary.disease_labels if item)),
                "patient_dir": relative_to_output(summary.patient_dir, output_root),
            }
        )

    write_csv(output_root / "metadata" / "patient_samples.csv", patient_rows, PATIENT_INDEX_FIELDS)
    write_csv(output_root / "metadata" / "media_index.csv", media_rows, MEDIA_INDEX_FIELDS)

    summary_payload = {
        "source_dataset": source_root.as_posix(),
        "output_dataset": output_root.as_posix(),
        "label_field": label_field or "auto",
        "patients": len(patient_rows),
        "media_files": len(media_rows),
        "images": sum(1 for row in media_rows if row["media_type"] == "image"),
        "videos": sum(1 for row in media_rows if row["media_type"] == "video"),
        "patient_groups": dict(Counter(row["label_group"] for row in patient_rows)),
        "media_groups": dict(Counter(row["label_group"] for row in media_rows)),
        "link_modes": dict(link_modes),
        "skipped": dict(skipped),
    }
    (output_root / "metadata" / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    build_gallery_html(output_root, patient_rows, media_rows, summary_payload)
    write_readme(output_root, summary_payload)
    return summary_payload


def write_readme(output_root: Path, summary: dict[str, object]) -> None:
    lines = [
        "# Stroke Patient Outcome Gallery",
        "",
        f"- Source dataset: `{summary['source_dataset']}`",
        f"- Label field: `{summary['label_field']}`",
        f"- Patients: `{summary['patients']}`",
        f"- Media files: `{summary['media_files']}`",
        f"- Images: `{summary['images']}`",
        f"- Videos: `{summary['videos']}`",
        f"- Patient groups: `{json.dumps(summary['patient_groups'], ensure_ascii=False, sort_keys=True)}`",
        f"- Link modes: `{json.dumps(summary['link_modes'], ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Layout",
        "",
        "- `患病/<患者姓名>__pid<患者id>/images/`: diseased patient images.",
        "- `患病/<患者姓名>__pid<患者id>/videos/`: diseased patient videos.",
        "- `不患病/<患者姓名>__pid<患者id>/images/`: non-diseased patient images.",
        "- `不患病/<患者姓名>__pid<患者id>/videos/`: non-diseased patient videos.",
        "- `metadata/patient_samples.csv`: one row per patient sample.",
        "- `metadata/media_index.csv`: one row per media file.",
        "- `index.html`: local gallery for visual browsing.",
        "",
        "## Notes",
        "",
        "- Patient folders include patient names because this dataset is intended for local controlled review.",
        "- Files are hard-linked by default to avoid duplicating the original media storage.",
        "- The default label is `脑卒中是否病发` when present; pass `--label-field 是否患病` to rebuild with the alternate field.",
    ]
    (output_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Organize downloaded stroke media by patient outcome and name.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Downloaded dataset root.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output organized gallery root.")
    parser.add_argument("--label-field", default=None, help="Binary label field to use; defaults to auto.")
    parser.add_argument(
        "--mode",
        choices=["hardlink", "copy", "symlink"],
        default="hardlink",
        help="How to place media files in the organized tree.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    summary = organize_dataset(args.source.resolve(), args.output.resolve(), args.label_field, args.mode)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
