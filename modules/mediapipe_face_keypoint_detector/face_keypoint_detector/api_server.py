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


MODULE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPLOAD_DIR = MODULE_ROOT / "tmp" / "api_uploads"


@dataclass(frozen=True)
class UploadedImage:
    path: Path
    original_filename: str
    field_name: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve MediaPipe Face Keypoint Detector API.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host. Defaults to 0.0.0.0 for LAN/external access.")
    parser.add_argument("--port", type=int, default=18131, help="Bind port.")
    parser.add_argument("--model", type=Path, default=None, help="Face Landmarker .task model. Defaults to module-local model.")
    parser.add_argument("--upload-dir", type=Path, default=DEFAULT_UPLOAD_DIR, help="Directory for uploaded images and JSON results.")
    parser.add_argument("--access-token", default="", help="Optional token required for APIs.")
    parser.add_argument("--public-url", default="", help="Optional externally reachable base URL to print.")
    parser.add_argument("--max-upload-mb", type=int, default=25, help="Maximum size per uploaded image.")
    parser.add_argument("--max-images", type=int, default=20, help="Maximum images per detection request.")
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    parser.add_argument("--allow-multiple-faces", action="store_true", help="Keep multi-face detections as detected.")
    return parser.parse_args(argv)


class FaceKeypointDetectorApi:
    def __init__(
        self,
        *,
        model_path: Path,
        upload_dir: Path,
        access_token: str,
        max_upload_mb: int,
        max_images: int,
        max_faces: int,
        allow_multiple_faces: bool,
    ) -> None:
        self.sdk = FaceKeypointDetectorSDK(model_path, max_num_faces=max_faces)
        self.model_path = self.sdk.model_path
        self.upload_dir = upload_dir
        self.access_token = access_token
        self.max_upload_bytes = max(1, max_upload_mb) * 1024 * 1024
        self.max_images = max(1, max_images)
        self.allow_multiple_faces = allow_multiple_faces

    def close(self) -> None:
        self.sdk.close()

    def handler_class(self) -> type[BaseHTTPRequestHandler]:
        app = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                app.handle_get(self)

            def do_POST(self) -> None:  # noqa: N802
                app.handle_post(self)

            def log_message(self, format: str, *args: Any) -> None:
                sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

        return Handler

    def handle_get(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        if parsed.path in {"/", "/api/health"}:
            if not self.authorized(request, parsed.query):
                send_json(request, 401, {"error": "unauthorized"})
                return
            send_json(
                request,
                200,
                {
                    "service": "mediapipe_face_keypoint_detector",
                    "status": "ok",
                    "model": self.model_path.as_posix(),
                    "endpoints": {
                        "health": "GET /api/health",
                        "detect": "POST /api/detect multipart/form-data",
                    },
                    "input": input_spec(self.max_images),
                },
            )
            return
        if parsed.path == "/api/input-spec":
            if not self.authorized(request, parsed.query):
                send_json(request, 401, {"error": "unauthorized"})
                return
            send_json(request, 200, input_spec(self.max_images))
            return
        send_json(request, 404, {"error": "not found"})

    def handle_post(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        if parsed.path != "/api/detect":
            send_json(request, 404, {"error": "not found"})
            return
        if not self.authorized(request, parsed.query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        try:
            uploads = self.read_uploads(request)
            if len(uploads) > self.max_images:
                raise ValueError(f"最多上传 {self.max_images} 张图片。")
            payload = self.detect_uploads(uploads)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc), "input": input_spec(self.max_images)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP service returns structured error.
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)})
            return
        send_json(request, 200, payload)

    def authorized(self, request: BaseHTTPRequestHandler, query: str) -> bool:
        if not self.access_token:
            return True
        params = parse_qs(query)
        supplied = first(params.get("token")) or request.headers.get("X-Access-Token", "")
        return secrets.compare_digest(str(supplied), self.access_token)

    def read_uploads(self, request: BaseHTTPRequestHandler) -> list[UploadedImage]:
        content_type = request.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise ValueError("请使用 multipart/form-data 上传图片。")
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": request.headers.get("Content-Length", "0"),
        }
        form = cgi.FieldStorage(fp=request.rfile, headers=request.headers, environ=environ)
        request_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + secrets.token_hex(4)
        target_dir = self.upload_dir / request_id
        target_dir.mkdir(parents=True, exist_ok=True)

        uploads: list[UploadedImage] = []
        for field_name in sorted(form.keys()):
            items = form[field_name]
            item_list = items if isinstance(items, list) else [items]
            for item in item_list:
                filename = str(getattr(item, "filename", "") or "").strip()
                if not filename:
                    continue
                original_name = Path(filename).name
                suffix = Path(original_name).suffix.lower()
                if suffix not in IMAGE_EXTENSIONS:
                    raise ValueError(f"不支持的图片格式：{original_name}。仅支持 jpg/jpeg/png。")
                data = item.file.read(self.max_upload_bytes + 1)
                if len(data) > self.max_upload_bytes:
                    raise ValueError(f"图片超过大小限制：{original_name}。")
                if not data:
                    raise ValueError(f"上传图片为空：{original_name}。")
                digest = hashlib.sha1(data).hexdigest()[:10]
                path = target_dir / safe_upload_name(original_name, field_name, digest)
                path.write_bytes(data)
                uploads.append(UploadedImage(path=path, original_filename=original_name, field_name=field_name))
        if not uploads:
            raise ValueError("没有收到有效图片。")
        return uploads

    def detect_uploads(self, uploads: list[UploadedImage]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for upload in uploads:
            result = self.sdk.detect_image(
                upload.path,
                allow_multiple_faces=self.allow_multiple_faces,
            )
            result["input"]["original_filename"] = upload.original_filename
            result["input"]["upload_field"] = upload.field_name
            results.append(result)
        payload = {
            "service": "mediapipe_face_keypoint_detector",
            "status": "ok",
            "model": self.model_path.as_posix(),
            "input_count": len(uploads),
            "status_counts": {
                status: sum(1 for item in results if item.get("status") == status)
                for status in sorted({str(item.get("status")) for item in results})
            },
            "results": results,
            "upload": {
                "request_dir": uploads[0].path.parent.as_posix(),
                "analysis_path": (uploads[0].path.parent / "detections.json").as_posix(),
            },
        }
        (uploads[0].path.parent / "detections.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload


def input_spec(max_images: int) -> dict[str, Any]:
    return {
        "accepted_files": sorted(IMAGE_EXTENSIONS),
        "max_images": max_images,
        "field_name": "任意字段名均可；推荐使用 images，可重复上传多张。",
        "output": [
            "status: detected/no_face/multiple_faces/failed",
            "detection.raw_landmarks: 478 个 MediaPipe 原始关键点",
            "detection.landmarks: FaceSymAi 语义关键点映射",
            "detection.blendshapes: Face Landmarker blendshape 分数",
            "detection.facial_transformation_matrixes: 面部变换矩阵",
        ],
    }


def safe_upload_name(original_name: str, field_name: str, digest: str) -> str:
    original = Path(original_name).name
    suffix = Path(original).suffix.lower()
    stem = Path(original).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    if not stem:
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", field_name).strip("._") or "image"
    return f"{stem}__{digest}{suffix}"


def send_json(request: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    request.send_response(status)
    request.send_header("Content-Type", "application/json; charset=utf-8")
    request.send_header("Content-Length", str(len(data)))
    request.end_headers()
    request.wfile.write(data)


def first(values: list[str] | None) -> str:
    if not values:
        return ""
    return values[0]


def access_urls(bind_host: str, port: int, access_token: str = "", public_url: str = "") -> list[str]:
    urls: list[str] = []
    if public_url:
        urls.append(append_token(public_url.rstrip("/") + "/", access_token))
    if bind_host in {"", "0.0.0.0", "::"}:
        urls.append(append_token(f"http://127.0.0.1:{port}/", access_token))
        for ip in lan_ipv4_addresses():
            urls.append(append_token(f"http://{ip}:{port}/", access_token))
    else:
        urls.append(append_token(f"http://{format_host_for_url(bind_host)}:{port}/", access_token))
    return list(dict.fromkeys(urls))


def append_token(url: str, access_token: str) -> str:
    if not access_token:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}token={quote(access_token)}"


def lan_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass
    return sorted(addresses)


def format_host_for_url(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    model_path = args.model.expanduser().resolve() if args.model else default_model_path()
    app = FaceKeypointDetectorApi(
        model_path=model_path,
        upload_dir=args.upload_dir.expanduser().resolve(),
        access_token=args.access_token,
        max_upload_mb=args.max_upload_mb,
        max_images=args.max_images,
        max_faces=args.max_faces,
        allow_multiple_faces=args.allow_multiple_faces,
    )
    handler = app.handler_class()
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host, port = server.server_address
    print("MediaPipe Face Keypoint Detector API:", flush=True)
    for url in access_urls(args.host, port, args.access_token, args.public_url):
        print(f"  {url}", flush=True)
    print(f"Upload results save under: {args.upload_dir.expanduser().resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()
        app.close()
    return 0
