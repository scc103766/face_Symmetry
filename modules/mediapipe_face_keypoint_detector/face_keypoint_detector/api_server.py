from __future__ import annotations

import argparse
import cgi
import hashlib
import json
import re
import secrets
import socket
import sys
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, urlparse

from .cli import IMAGE_EXTENSIONS
from .sdk import FaceKeypointDetectorSDK, default_model_path


_FACIAL_SERVICE_DIR = Path(__file__).resolve().parents[2] / "facial_asymmetry_service" / "facial_asymmetry_service"
if str(_FACIAL_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_FACIAL_SERVICE_DIR))

from action_detector import (  # noqa: E402
    detect_side_view,
    detect_teeth_exposure,
)


MODULE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPLOAD_DIR = MODULE_ROOT / "tmp" / "api_uploads"
ACTION_HTML_PATH = MODULE_ROOT / "action_detect.html"


@dataclass(frozen=True)
class UploadedImage:
    path: Path
    original_filename: str
    field_name: str
    relative_path: str = ""


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve MediaPipe Face Keypoint Detector API.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host.")
    parser.add_argument("--port", type=int, default=18131, help="Bind port.")
    parser.add_argument("--model", type=Path, default=None, help="Face Landmarker .task model.")
    parser.add_argument("--upload-dir", type=Path, default=DEFAULT_UPLOAD_DIR, help="Upload directory.")
    parser.add_argument("--access-token", default="", help="Optional access token.")
    parser.add_argument("--public-url", default="", help="Optional public URL.")
    parser.add_argument("--max-upload-mb", type=int, default=25, help="Max upload size MB.")
    parser.add_argument("--max-faces", type=int, default=2, help="Max faces to detect.")
    parser.add_argument("--allow-multiple-faces", action="store_true", help="Allow multi-face.")
    return parser.parse_args(argv)


class FaceKeypointDetectorApi:
    def __init__(self, *, model_path, upload_dir, access_token, max_upload_mb, max_faces, allow_multiple_faces):
        self.sdk = FaceKeypointDetectorSDK(model_path, max_num_faces=max_faces)
        self.model_path = self.sdk.model_path
        self.upload_dir = upload_dir
        self.access_token = access_token
        self.max_upload_bytes = max(1, max_upload_mb) * 1024 * 1024
        self.allow_multiple_faces = allow_multiple_faces

    def close(self):
        self.sdk.close()

    def handler_class(self):
        app = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                app.handle_get(self)
            def do_POST(self):
                app.handle_post(self)
            def log_message(self, format, *args):
                sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))
        return Handler

    def handle_get(self, request):
        parsed = urlparse(request.path)
        if parsed.path in {"/", "/api/health"}:
            if not self.authorized(request, parsed.query):
                send_json(request, 401, {"error": "unauthorized"})
                return
            send_json(request, 200, {
                "service": "mediapipe_face_keypoint_detector", "status": "ok",
                "model": self.model_path.as_posix(),
                "endpoints": {
                    "health": "GET /api/health",
                    "detect": "POST /api/detect multipart/form-data",
                    "detect_folder": "POST /api/detect-folder application/json",
                    "keypoint": "POST /keypoint multipart/form-data",
                    "ceshi": "POST /ceshi multipart/form-data (side_view)",
                    "louyachi": "POST /louyachi multipart/form-data (teeth_exposure)",
                    "action_page": "GET /action (Web UI)",
                    "action_post": "POST /action multipart/form-data (combined detection)",
                },
                "input": input_spec(),
            })
            return
        if parsed.path == "/action":
            if not self.authorized(request, parsed.query):
                send_json(request, 401, {"error": "unauthorized"})
                return
            if ACTION_HTML_PATH.exists():
                send_file(request, ACTION_HTML_PATH, "text/html; charset=utf-8")
            else:
                send_json(request, 404, {"error": "action_detect.html not found"})
            return
        if parsed.path == "/api/input-spec":
            if not self.authorized(request, parsed.query):
                send_json(request, 401, {"error": "unauthorized"})
                return
            send_json(request, 200, input_spec())
            return
        send_json(request, 404, {"error": "not found"})

    def handle_post(self, request):
        parsed = urlparse(request.path)
        if parsed.path == "/keypoint":
            self._handle_keypoint(request, parsed.query); return
        if parsed.path == "/ceshi":
            self._handle_ceshi(request, parsed.query); return
        if parsed.path == "/louyachi":
            self._handle_louyachi(request, parsed.query); return
        if parsed.path == "/action":
            self._handle_action(request, parsed.query); return
        if parsed.path not in {"/api/detect", "/api/detect-folder"}:
            send_json(request, 404, {"error": "not found"}); return
        if not self.authorized(request, parsed.query):
            send_json(request, 401, {"error": "unauthorized"}); return
        try:
            if parsed.path == "/api/detect-folder":
                image_dir, recursive = self.read_folder_request(request, parsed.query)
                images = self.collect_folder_images(image_dir, recursive=recursive)
                payload = self.detect_folder_images(images, image_dir=image_dir, recursive=recursive)
            else:
                uploads = self.read_uploads(request)
                payload = self.detect_uploads(uploads)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc), "input": input_spec()}); return
        except Exception as exc:
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)}); return
        send_json(request, 200, payload)

    def _handle_keypoint(self, request, query):
        try:
            detection_payload, error_response, _ = self._detect_single_face(request, query)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)}); return
        except Exception as exc:
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)}); return
        if error_response is not None:
            send_json(request, int(error_response["http_status"]), error_response["payload"]); return
        send_json(request, 200, {"status": "detected", "detection": detection_payload})

    def _handle_ceshi(self, request, query):
        try:
            detection_payload, error_response, _ = self._detect_single_face(request, query)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)}); return
        except Exception as exc:
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)}); return
        if error_response is not None:
            send_json(request, int(error_response["http_status"]), error_response["payload"]); return
        side_view = detect_side_view(detection_payload)
        send_json(request, 200, {
            "status": "detected",
            "side_view": {
                "detected": side_view.detected,
                "direction": side_view.direction,
                "yaw_angle": round(side_view.yaw_angle, 2),
                "level": side_view.level,
                "confidence": side_view.confidence,
                "details": side_view.details,
            },
        })

    def _handle_louyachi(self, request, query):
        try:
            detection_payload, error_response, upload_path = self._detect_single_face(request, query)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)}); return
        except Exception as exc:
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)}); return
        if error_response is not None:
            send_json(request, int(error_response["http_status"]), error_response["payload"]); return
        teeth_exposure = detect_teeth_exposure(detection_payload, image_path=str(upload_path))
        send_json(request, 200, {
            "status": "detected",
            "teeth_exposure": {
                "detected": teeth_exposure.detected,
                "mouth_state": teeth_exposure.mouth_state,
                "confidence": round(teeth_exposure.confidence, 4),
                "details": teeth_exposure.details,
            },
        })

    def _handle_action(self, request, query):
        try:
            detection_payload, error_response, upload_path = self._detect_single_face(request, query)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)}); return
        except Exception as exc:
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)}); return
        if error_response is not None:
            send_json(request, int(error_response["http_status"]), error_response["payload"]); return
        image_path = str(upload_path) if upload_path is not None else None
        side_view = detect_side_view(detection_payload)
        teeth_exposure = detect_teeth_exposure(detection_payload, image_path=image_path)
        send_json(request, 200, {
            "status": "detected",
            "keypoint": {
                "landmarks": detection_payload.get("landmarks"),
                "blendshapes": detection_payload.get("blendshapes"),
            },
            "side_view": {
                "detected": side_view.detected,
                "direction": side_view.direction,
                "level": side_view.level,
                "confidence": side_view.confidence,
            },
            "teeth_exposure": {
                "detected": teeth_exposure.detected,
                "mouth_state": teeth_exposure.mouth_state,
                "confidence": round(teeth_exposure.confidence, 4),
            },
        })

    def _detect_single_face(self, request, query):
        if not self.authorized(request, query):
            return None, {"http_status": 401, "payload": {"error": "unauthorized"}}, None
        uploads = self.read_uploads(request)
        upload = uploads[0]
        result = self.sdk.detect_image(upload.path)
        status = str(result.get("status") or "")
        if status == "no_face":
            return None, {"http_status": 200, "payload": {"status": "no_face"}}, upload.path
        detection_payload = result.get("detection")
        if not isinstance(detection_payload, dict):
            return None, {"http_status": 200, "payload": {"status": status or "failed", "error": result.get("error")}}, upload.path
        return detection_payload, None, upload.path

    def authorized(self, request, query):
        if not self.access_token: return True
        params = parse_qs(query)
        supplied = first(params.get("token")) or request.headers.get("X-Access-Token", "")
        return secrets.compare_digest(str(supplied), self.access_token)

    def read_uploads(self, request):
        content_type = request.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("请使用 multipart/form-data 上传图片。")
        environ = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": request.headers.get("Content-Length", "0")}
        form = cgi.FieldStorage(fp=request.rfile, headers=request.headers, environ=environ)
        request_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(4)
        target_dir = self.upload_dir / request_id
        target_dir.mkdir(parents=True, exist_ok=True)
        uploads = []
        for field_name in sorted(form.keys()):
            items = form[field_name]
            item_list = items if isinstance(items, list) else [items]
            for item in item_list:
                filename = str(getattr(item, "filename", "") or "").strip()
                if not filename: continue
                original_name = Path(filename).name
                suffix = Path(original_name).suffix.lower()
                if suffix not in IMAGE_EXTENSIONS:
                    raise ValueError(f"不支持的图片格式：{original_name}。")
                data = item.file.read(self.max_upload_bytes + 1)
                if len(data) > self.max_upload_bytes:
                    raise ValueError(f"图片超过大小限制：{original_name}。")
                if not data:
                    raise ValueError(f"上传图片为空：{original_name}。")
                digest = hashlib.sha1(data).hexdigest()[:10]
                path = target_dir / safe_upload_name(original_name, field_name, digest)
                path.write_bytes(data)
                uploads.append(UploadedImage(path=path, original_filename=original_name, field_name=field_name))
        if not uploads: raise ValueError("没有收到有效图片。")
        return uploads

    def read_folder_request(self, request, query):
        values = parse_qs(query)
        content_type = request.headers.get("Content-Type", "")
        content_length = int(request.headers.get("Content-Length", "0") or "0")
        if "application/json" in content_type:
            raw = request.rfile.read(content_length) if content_length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON 格式错误：{exc.msg}。") from exc
            if not isinstance(payload, dict): raise ValueError("JSON 请求体必须是对象。")
            for key, value in payload.items(): values[str(key)] = [str(value)]
        elif "application/x-www-form-urlencoded" in content_type:
            raw = request.rfile.read(content_length).decode("utf-8") if content_length else ""
            for key, value in parse_qs(raw).items(): values[key] = value
        elif "multipart/form-data" in content_type:
            environ = {"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": request.headers.get("Content-Length", "0")}
            form = cgi.FieldStorage(fp=request.rfile, headers=request.headers, environ=environ)
            for key in form.keys():
                item = form[key]
                item_list = item if isinstance(item, list) else [item]
                for field in item_list:
                    filename = str(getattr(field, "filename", "") or "").strip()
                    if filename: continue
                    values.setdefault(key, []).append(str(getattr(field, "value", "") or ""))
        elif content_length:
            raise ValueError("文件夹检测请使用 application/json、application/x-www-form-urlencoded 或 multipart/form-data。")
        raw_dir = first(values.get("image_dir")) or first(values.get("folder")) or first(values.get("path")) or first(values.get("directory"))
        if not raw_dir: raise ValueError("请提供 image_dir。")
        recursive = parse_bool(first(values.get("recursive")), default=True)
        return Path(raw_dir).expanduser().resolve(), recursive

    def collect_folder_images(self, image_dir, *, recursive):
        if not image_dir.exists(): raise ValueError(f"文件夹不存在：{image_dir.as_posix()}。")
        if not image_dir.is_dir(): raise ValueError(f"image_dir 不是文件夹：{image_dir.as_posix()}。")
        candidates = image_dir.rglob("*") if recursive else image_dir.iterdir()
        images = [path.resolve() for path in candidates if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
        images = sorted(dict.fromkeys(images))
        if not images: raise ValueError(f"文件夹下没有支持的图片：{image_dir.as_posix()}。")
        return [UploadedImage(path=path, original_filename=path.name, field_name="folder", relative_path=path.relative_to(image_dir).as_posix()) for path in images]

    def detect_uploads(self, uploads):
        upload_dir = uploads[0].path.parent
        return self.detect_images(uploads, source={"type": "upload", "upload_dir": upload_dir.as_posix()}, result_dir=upload_dir)

    def detect_folder_images(self, images, *, image_dir, recursive):
        return self.detect_images(images, source={"type": "folder", "image_dir": image_dir.as_posix(), "recursive": recursive})

    def detect_images(self, images, *, source, result_dir=None):
        results = []
        if result_dir is None:
            request_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(4)
            result_dir = self.upload_dir / request_id
        result_dir.mkdir(parents=True, exist_ok=True)
        for upload in images:
            result = self.sdk.detect_image(upload.path, allow_multiple_faces=self.allow_multiple_faces)
            result["input"]["original_filename"] = upload.original_filename
            result["input"]["upload_field"] = upload.field_name
            if upload.relative_path: result["input"]["relative_path"] = upload.relative_path
            results.append(result)
        analysis_path = result_dir / "detections.json"
        payload = {
            "service": "mediapipe_face_keypoint_detector", "status": "ok",
            "model": self.model_path.as_posix(), "source": source,
            "input_count": len(images),
            "status_counts": {status: sum(1 for r in results if r.get("status") == status) for status in sorted({str(r.get("status")) for r in results})},
            "results": results,
            "output": {"request_dir": result_dir.as_posix(), "analysis_path": analysis_path.as_posix()},
            "upload": {"request_dir": result_dir.as_posix(), "analysis_path": analysis_path.as_posix()},
        }
        analysis_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload


def input_spec():
    return {
        "accepted_files": sorted(IMAGE_EXTENSIONS), "max_images": None, "image_count_limit": "unlimited",
        "field_name": "任意字段名均可；推荐使用 images，可重复上传多张。",
        "folder_detection": {"endpoint": "POST /api/detect-folder", "body": {"image_dir": "/path/to/images", "recursive": True}, "recursive_default": True},
        "output": ["status: detected/no_face/multiple_faces/failed", "detection.raw_landmarks: 478 个 MediaPipe 原始关键点", "detection.landmarks: FaceSymAi 语义关键点映射", "detection.blendshapes: Face Landmarker blendshape 分数", "detection.facial_transformation_matrixes: 面部变换矩阵"],
    }


def safe_upload_name(original_name, field_name, digest):
    original = Path(original_name).name
    suffix = Path(original).suffix.lower()
    stem = Path(original).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    if not stem: stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", field_name).strip("._") or "image"
    return f"{stem}__{digest}{suffix}"


def send_json(request, status, payload):
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    request.send_response(status)
    request.send_header("Content-Type", "application/json; charset=utf-8")
    request.send_header("Content-Length", str(len(data)))
    request.end_headers()
    request.wfile.write(data)


def send_file(request, path, content_type):
    data = path.read_bytes()
    request.send_response(200)
    request.send_header("Content-Type", content_type)
    request.send_header("Content-Length", str(len(data)))
    request.end_headers()
    request.wfile.write(data)


def first(values):
    if not values: return ""
    return values[0]


def parse_bool(value, *, default):
    text = str(value or "").strip().lower()
    if not text: return default
    if text in {"1", "true", "yes", "y", "on"}: return True
    if text in {"0", "false", "no", "n", "off"}: return False
    return default


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    model_path = (args.model or default_model_path()).resolve()
    app = FaceKeypointDetectorApi(model_path=model_path, upload_dir=args.upload_dir, access_token=args.access_token, max_upload_mb=args.max_upload_mb, max_faces=args.max_faces, allow_multiple_faces=args.allow_multiple_faces)
    server = ThreadingHTTPServer((args.host, args.port), app.handler_class())
    try:
        addr = server.server_address
        print(f"Face Keypoint Detector API listening on http://{addr[0]}:{addr[1]}")
        if args.public_url: print(f"Public URL: {args.public_url}")
        server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        app.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
