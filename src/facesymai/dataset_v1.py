from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


STROKE_YES_NO_FIELDS = (
    "\u662f\u5426\u60a3\u75c5",
    "\u8111\u5352\u4e2d\u662f\u5426\u75c5\u53d1",
)
RISK_LEVEL_FIELD = "\u98ce\u9669\u7b49\u7ea7"


@dataclass(frozen=True)
class LabelInfo:
    label_source: str
    label_value: str
    label_binary: int | None

    def to_dict(self) -> dict[str, str]:
        return {
            "label_source": self.label_source,
            "label_value": self.label_value,
            "label_binary": "" if self.label_binary is None else str(self.label_binary),
        }


@dataclass(frozen=True)
class V1Sample:
    sample_id: str
    source_dataset: str
    record_id: str
    media_id: str
    media_role: str
    media_type: str
    source_media_path: Path
    frame_index: int
    frame_time_sec: float
    label: LabelInfo

    def metadata_row(self, output_root: Path, detection_status: str, keypoints_path: Path | None, error: str) -> dict[str, str]:
        row = {
            "sample_id": self.sample_id,
            "source_dataset": self.source_dataset,
            "record_id": self.record_id,
            "media_id": self.media_id,
            "media_role": self.media_role,
            "media_type": self.media_type,
            "source_media_path": self.source_media_path.as_posix(),
            "frame_index": str(self.frame_index),
            "frame_time_sec": f"{self.frame_time_sec:.3f}",
            "detection_status": detection_status,
            "keypoints_path": "",
            "error": error,
        }
        row.update(self.label.to_dict())
        if keypoints_path is not None:
            row["keypoints_path"] = keypoints_path.relative_to(output_root).as_posix()
        return row


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def stable_sample_id(*parts: str) -> str:
    text = "__".join(part for part in parts if part)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{parts[0]}__{digest}"


def resolve_label(record: dict[str, str]) -> LabelInfo:
    for field in STROKE_YES_NO_FIELDS:
        value = record.get(field, "").strip()
        if value:
            if value == "\u662f":
                binary = 1
            elif value == "\u5426":
                binary = 0
            else:
                binary = None
            return LabelInfo(label_source=field, label_value=value, label_binary=binary)

    risk_level = record.get(RISK_LEVEL_FIELD, "").strip()
    if risk_level:
        return LabelInfo(label_source=RISK_LEVEL_FIELD, label_value=risk_level, label_binary=None)

    return LabelInfo(label_source="", label_value="", label_binary=None)


def discover_dataset_roots(paths: Iterable[Path]) -> list[Path]:
    roots: list[Path] = []
    for path in paths:
        root = path.resolve()
        if not (root / "metadata" / "records.csv").exists():
            raise FileNotFoundError(f"missing records.csv under dataset root: {root}")
        if not (root / "metadata" / "media_manifest.csv").exists():
            raise FileNotFoundError(f"missing media_manifest.csv under dataset root: {root}")
        roots.append(root)
    return roots


def build_samples(
    dataset_roots: Iterable[Path],
    *,
    include_images: bool = True,
    include_videos: bool = True,
    roles: set[str] | None = None,
    limit: int | None = None,
) -> list[V1Sample]:
    samples: list[V1Sample] = []
    for dataset_root in discover_dataset_roots(dataset_roots):
        records = {
            row["record_id"]: row
            for row in read_csv(dataset_root / "metadata" / "records.csv")
            if row.get("record_id")
        }
        media_rows = read_csv(dataset_root / "metadata" / "media_manifest.csv")
        source_dataset = dataset_root.name

        for media in media_rows:
            status = media.get("download_status", "")
            if status not in {"downloaded", "exists"}:
                continue
            media_type = media.get("media_type", "")
            if media_type == "image" and not include_images:
                continue
            if media_type == "video" and not include_videos:
                continue
            if roles is not None and media.get("media_role", "") not in roles:
                continue

            source_media_path = dataset_root / media.get("local_path", "")
            if not source_media_path.exists():
                continue

            record_id = media.get("record_id", "")
            sample_id = stable_sample_id(
                media.get("media_id", ""),
                source_dataset,
                record_id,
                source_media_path.as_posix(),
            )
            samples.append(
                V1Sample(
                    sample_id=sample_id,
                    source_dataset=source_dataset,
                    record_id=record_id,
                    media_id=media.get("media_id", ""),
                    media_role=media.get("media_role", ""),
                    media_type=media_type,
                    source_media_path=source_media_path,
                    frame_index=0,
                    frame_time_sec=0.0,
                    label=resolve_label(records.get(record_id, {})),
                )
            )
            if limit is not None and len(samples) >= limit:
                return samples
    return samples


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
