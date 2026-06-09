from __future__ import annotations

import csv
from pathlib import Path

from facesymai.dataset_v1 import build_samples, resolve_label


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_resolve_binary_stroke_label() -> None:
    label = resolve_label({"是否患病": "是"})

    assert label.label_source == "是否患病"
    assert label.label_value == "是"
    assert label.label_binary == 1


def test_resolve_risk_level_label_without_binary_mapping() -> None:
    label = resolve_label({"风险等级": "紧急风险"})

    assert label.label_source == "风险等级"
    assert label.label_value == "紧急风险"
    assert label.label_binary is None


def test_build_samples_from_media_manifest(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    media_path = dataset / "media" / "images" / "record-1" / "front.jpg"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"image")
    write_csv(
        dataset / "metadata" / "records.csv",
        [
            {
                "record_id": "record-1",
                "是否患病": "否",
            }
        ],
    )
    write_csv(
        dataset / "metadata" / "media_manifest.csv",
        [
            {
                "media_id": "media-1",
                "record_id": "record-1",
                "media_role": "front",
                "media_type": "image",
                "local_path": "media/images/record-1/front.jpg",
                "download_status": "downloaded",
            }
        ],
    )

    samples = build_samples([dataset])

    assert len(samples) == 1
    assert samples[0].media_id == "media-1"
    assert samples[0].label.label_binary == 0
