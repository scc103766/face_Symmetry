from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .risk import FacialSymmetryRiskAnalyzer
from .schemas import FaceLandmarks


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze facial symmetry landmarks.")
    parser.add_argument("input", type=Path, help="JSON file containing landmarks")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args(argv)

    try:
        payload = load_json(args.input)
        face = FaceLandmarks.from_payload(payload)
        result = FacialSymmetryRiskAnalyzer().analyze(face)
    except Exception as exc:  # noqa: BLE001 - CLI should return clear JSON errors.
        error = {"error": type(exc).__name__, "message": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 1

    indent = 2 if args.pretty else None
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=indent))
    return 0
