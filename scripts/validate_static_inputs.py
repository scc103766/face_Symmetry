#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from facesymai.input_management import StaticImageInput, StaticImageInputManager  # noqa: E402


def parse_image_args(items: list[list[str]] | None) -> list[StaticImageInput]:
    inputs: list[StaticImageInput] = []
    for index, item in enumerate(items or [], start=1):
        role, path = item
        inputs.append(StaticImageInput(path=Path(path), role=role, image_id=f"{role}_{index:02d}"))
    return inputs


def parse_json(path: Path) -> list[StaticImageInput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        raw_inputs = payload.get("images", payload.get("inputs"))
    else:
        raw_inputs = payload
    if not isinstance(raw_inputs, list):
        raise ValueError("input JSON must be a list or an object containing `images`/`inputs`")
    return [StaticImageInput.from_payload(item) for item in raw_inputs]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate FaceSymAi V1 static image input set.")
    parser.add_argument(
        "--image",
        action="append",
        nargs=2,
        metavar=("ROLE", "PATH"),
        help="Static image input. Repeat for front, teeth, and optional extra images.",
    )
    parser.add_argument("--input-json", type=Path, help="JSON file containing image input objects.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON result.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        inputs = parse_json(args.input_json) if args.input_json else parse_image_args(args.image)
        result = StaticImageInputManager().validate(inputs)
    except Exception as exc:  # noqa: BLE001 - CLI returns JSON errors.
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
