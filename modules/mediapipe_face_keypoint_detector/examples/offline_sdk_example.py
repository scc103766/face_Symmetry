#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


SDK_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDK_ROOT))

from face_keypoint_detector import FaceKeypointDetectorSDK  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python examples/offline_sdk_example.py path/to/image.jpg", file=sys.stderr)
        return 2
    image_path = Path(sys.argv[1]).expanduser().resolve()
    with FaceKeypointDetectorSDK() as detector:
        result = detector.detect_image(image_path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") == "detected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
