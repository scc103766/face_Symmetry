from __future__ import annotations

import argparse
import cgi
import hashlib
import json
import mimetypes
import os
import re
import secrets
import socket
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, urlparse

from .cli import (
    DEFAULT_MODEL_PATH,
    IMAGE_EXTENSIONS,
    MODEL_ENV_VAR,
    MediaPipeFaceLandmarkerDetector,
    analyze_one,
    build_report,
    infer_role_from_filename,
    resolve_rule_dir,
)
from .rule62 import DEFAULT_RULE_DIR, load_rule62_config, normalize_role


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PAGE = PROJECT_ROOT / "modules" / "facial_asymmetry_service" / "web_upload.html"
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "tmp" / "facial_asymmetry_service_uploads"
MIN_IMAGE_COUNT = 2
MAX_IMAGE_COUNT = 10
FIELD_ROLES = {
    "front": "front",
    "front_contour": "front_contour",
    "smile": "smile",
    "teeth": "teeth",
    "smile_teeth": "smile_teeth",
    "eyes_right": "eyes_right",
    "eyes_closed": "eyes_closed",
    "forehead_wrinkle": "forehead_wrinkle",
    "frown": "frown",
}
ROLE_LABELS = {
    "front": "正脸",
    "front_contour": "正脸/面部轮廓",
    "smile": "微笑",
    "teeth": "示齿",
    "smile_teeth": "露齿微笑",
    "eyes_right": "眼球右看",
    "eyes_closed": "闭眼",
    "forehead_wrinkle": "抬眉/皱额",
    "frown": "皱眉",
    "unknown": "未标注动作",
}
USER_FINDING_GROUPS = (
    {
        "key": "mouth_corner_pull",
        "title": "双侧口角夹角或牵拉幅度差",
        "description": "微笑、露齿或示齿时，左右口角上提、外拉或夹角变化不一致，可能表现为一侧口角活动不足或口角高度不齐。",
        "features": {"bsdiff_mouth_abs", "bsdiff_mouth_lateral_abs", "raw_mouth_corner_vertical_asym"},
    },
    {
        "key": "mouth_frown",
        "title": "双侧口角下垂动作差",
        "description": "左右口角下垂相关动作幅度不一致，可对应一侧口角控制较弱或表情动作不协调。",
        "features": {"bsdiff_mouthFrown_abs"},
    },
    {
        "key": "lip_midline",
        "title": "唇部中线偏移",
        "description": "上下唇中心相对面部中线出现偏移，可能表现为口唇向一侧偏斜。",
        "features": {"raw_lip_midline_deviation"},
    },
    {
        "key": "eye_aperture",
        "title": "双侧眼裂高度或眼周形态差",
        "description": "左右眼裂高度、眼周区域大小或眼周形态不一致，可能表现为一侧睁眼幅度、眼裂高度或眼周张力不同。",
        "features": {
            "raw_iris_region_point_spread_asym",
            "raw_iris_region_area_asym",
            "raw_eye_region_point_spread_asym",
            "raw_iris_region_centroid_y_asym",
            "raw_eye_region_centroid_y_asym",
            "bsdiff_eyeLookDown_abs",
        },
    },
    {
        "key": "brow_height",
        "title": "双侧眉部高度或动作幅度差",
        "description": "左右眉部高度、眉眼区域形态或皱眉/抬眉动作幅度不一致，可能提示额眉部运动不协调。",
        "features": {
            "raw_eyebrow_region_height_asym",
            "raw_eyebrow_region_point_spread_asym",
            "raw_eyebrow_region_area_asym",
            "raw_eyebrow_region_centroid_y_asym",
            "raw_brow_outer_height_asym",
            "bsdiff_browDown_abs",
        },
    },
    {
        "key": "face_contour",
        "title": "面部轮廓左右高度或位置差",
        "description": "面部轮廓、整体面部点位或左右面部高度分布不一致，可能表现为脸部一侧下垂或轮廓不对称。",
        "features": {
            "raw_face_oval_region_centroid_y_asym",
            "raw_face_oval_region_height_asym",
            "raw_all_mesh_region_height_asym",
        },
    },
)


@dataclass(frozen=True)
class UploadedImage:
    path: Path
    media_role: str
    original_filename: str
    field_name: str


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the Rule 62 facial asymmetry upload web service.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host. Defaults to 0.0.0.0 for LAN/external access.")
    parser.add_argument("--port", type=int, default=8790, help="Bind port.")
    parser.add_argument("--model", type=Path, default=None, help=f"MediaPipe Face Landmarker .task model. Defaults to {DEFAULT_MODEL_PATH}.")
    parser.add_argument("--rule-dir", type=Path, default=DEFAULT_RULE_DIR, help="Directory containing 62 rule CSV files.")
    parser.add_argument("--page", type=Path, default=DEFAULT_PAGE, help="HTML upload page.")
    parser.add_argument("--upload-dir", type=Path, default=DEFAULT_UPLOAD_DIR, help="Directory for uploaded images and JSON results.")
    parser.add_argument("--access-token", default="", help="Optional token required for APIs.")
    parser.add_argument("--public-url", default="", help="Optional externally reachable base URL to print.")
    parser.add_argument("--max-upload-mb", type=int, default=25, help="Maximum size per uploaded image.")
    parser.add_argument("--max-images", type=int, default=MAX_IMAGE_COUNT, help="Maximum images per analysis request.")
    parser.add_argument("--max-faces", type=int, default=2, help="Maximum faces to ask MediaPipe to return.")
    parser.add_argument("--allow-multiple-faces", action="store_true", help="Use first face when multiple faces are detected.")
    return parser.parse_args(argv)


def resolve_model_path(args: argparse.Namespace) -> Path:
    if args.model is not None:
        return args.model.expanduser().resolve()
    env_value = os.environ.get(MODEL_ENV_VAR, "").strip()
    if env_value:
        return Path(env_value).expanduser().resolve()
    return DEFAULT_MODEL_PATH.resolve()


class FacialAsymmetryWebApp:
    def __init__(
        self,
        *,
        model_path: Path,
        rule_dir: Path,
        page: Path,
        upload_dir: Path,
        access_token: str,
        max_upload_mb: int,
        max_images: int,
        max_faces: int,
        allow_multiple_faces: bool,
    ) -> None:
        self.model_path = model_path
        self.rule_config = load_rule62_config(rule_dir)
        self.page = page
        self.upload_dir = upload_dir
        self.access_token = access_token
        self.max_upload_bytes = max(1, max_upload_mb) * 1024 * 1024
        self.max_images = max(MIN_IMAGE_COUNT, max_images)
        self.allow_multiple_faces = allow_multiple_faces
        self.rule_feature_names = {feature.feature_name for feature in self.rule_config.features}
        self.detector = MediaPipeFaceLandmarkerDetector(model_path, max_num_faces=max(1, max_faces))
        self.detector_lock = threading.Lock()

    def close(self) -> None:
        self.detector.close()

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
        if parsed.path in {"/", "/upload"}:
            send_file(request, self.page, "text/html; charset=utf-8")
            return
        if parsed.path == "/api/input-spec":
            if not self.authorized(request, parsed.query):
                send_json(request, 401, {"error": "unauthorized"})
                return
            send_json(request, 200, public_input_spec(self.max_images))
            return
        send_json(request, 404, {"error": "not found"})

    def handle_post(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        if parsed.path != "/api/analyze":
            send_json(request, 404, {"error": "not found"})
            return
        if not self.authorized(request, parsed.query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        try:
            uploads = self.read_uploads(request)
            validate_uploads(uploads, max_images=self.max_images)
            report = self.analyze_uploads(uploads)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc), "input_requirements": public_input_spec(self.max_images)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP service returns structured error.
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)})
            return
        send_json(request, 200, report)

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
                role = role_from_field(field_name) or infer_role_from_filename(Path(original_name)) or "unknown"
                digest = hashlib.sha1(data).hexdigest()[:10]
                safe_name = safe_upload_name(original_name, field_name, role, digest)
                path = target_dir / safe_name
                path.write_bytes(data)
                uploads.append(
                    UploadedImage(
                        path=path,
                        media_role=normalize_role(role),
                        original_filename=original_name,
                        field_name=field_name,
                    )
                )
        return uploads

    def analyze_uploads(self, uploads: list[UploadedImage]) -> dict[str, Any]:
        image_results: list[dict[str, Any]] = []
        feature_rows: list[dict[str, Any]] = []
        with self.detector_lock:
            for upload in uploads:
                public_result, feature_row = analyze_one(
                    self.detector,
                    upload.path,
                    media_role=upload.media_role,
                    model_path=self.model_path,
                    rule_feature_names=self.rule_feature_names,
                    annotated_output=None,
                    allow_multiple_faces=self.allow_multiple_faces,
                )
                public_result["input"]["original_filename"] = upload.original_filename
                public_result["input"]["upload_field"] = upload.field_name
                image_results.append(public_result)
                feature_rows.append(feature_row)
        report = build_report(
            image_results=image_results,
            feature_rows=feature_rows,
            model_path=self.model_path,
            rule_config=self.rule_config,
        )
        output_path = uploads[0].path.parent / "analysis.json"
        technical_output_path = uploads[0].path.parent / "analysis_technical.json"
        public_report = build_public_report(report, max_images=self.max_images)
        public_report["upload"] = {
            "request_dir": uploads[0].path.parent.as_posix(),
            "analysis_path": output_path.as_posix(),
        }
        technical_output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output_path.write_text(json.dumps(public_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return public_report


def role_from_field(field_name: str) -> str | None:
    normalized = normalize_role(field_name)
    return FIELD_ROLES.get(normalized)


def validate_uploads(uploads: list[UploadedImage], *, max_images: int) -> None:
    if len(uploads) < MIN_IMAGE_COUNT:
        raise ValueError("同一人至少需要 2 张图片；动作不强制限制，但推荐包含露齿微笑/微笑/示齿。")
    if len(uploads) > max_images:
        raise ValueError(f"同一人最多上传 {max_images} 张图片。")


def build_public_report(report: Mapping[str, Any], *, max_images: int = MAX_IMAGE_COUNT) -> dict[str, Any]:
    analysis = dict(report.get("analysis") or {})
    findings = patient_findings(analysis)
    confidence = float(analysis.get("face_asymmetry_confidence") or 0.0)
    output = str(analysis.get("face_asymmetry_output") or "无法判断")
    detected_count = int(analysis.get("detected_image_count") or 0)
    input_count = int(report.get("input_count") or 0)
    return {
        "service": report.get("service"),
        "service_version": report.get("service_version"),
        "status": report.get("status"),
        "analysis_method": "基于多张图片的面部左右对称性综合分析",
        "input_count": input_count,
        "status_counts": report.get("status_counts") or {},
        "input_requirements": public_input_spec(max_images),
        "analysis": {
            "face_asymmetry_output": output,
            "face_asymmetry_confidence": round(confidence, 6),
            "confidence_percent": round(confidence * 100.0, 2),
            "confidence_level": confidence_level(confidence),
            "detected_image_count": detected_count,
            "uploaded_image_count": input_count,
            "predicted_high_asymmetry": bool(analysis.get("predicted_high_asymmetry")),
            "reason_description": patient_reason(analysis, findings),
            "findings": findings,
            "suggestion": patient_suggestion(analysis, findings),
            "medical_disclaimer": "该结果是面部对称性辅助分析，不是临床诊断结论；如有口角歪斜、言语含糊、肢体无力等症状，应及时就医。",
        },
        "images": [public_image_result(item) for item in report.get("images") or []],
    }


def patient_findings(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    attributions = [
        item
        for item in analysis.get("feature_attributions") or []
        if item.get("triggered")
    ]
    findings: list[dict[str, Any]] = []
    for group in USER_FINDING_GROUPS:
        related = [item for item in attributions if item.get("feature_name") in group["features"]]
        if not related:
            continue
        roles = sorted(
            {
                role_label(str(value.get("media_role") or "unknown"))
                for item in related
                for value in item.get("supporting_image_values") or []
            }
        )
        findings.append(
            {
                "name": group["title"],
                "description": group["description"],
                "evidence_level": "主要表现" if len(related) >= 2 else "辅助表现",
                "observed_in": roles,
                "supporting_image_count": len(
                    {
                        str(value.get("image_id") or "")
                        for item in related
                        for value in item.get("supporting_image_values") or []
                        if value.get("image_id")
                    }
                ),
            }
        )
    return findings


def patient_reason(analysis: Mapping[str, Any], findings: list[Mapping[str, Any]]) -> str:
    output = str(analysis.get("face_asymmetry_output") or "无法判断")
    confidence = float(analysis.get("face_asymmetry_confidence") or 0.0)
    detected_count = int(analysis.get("detected_image_count") or 0)
    if detected_count <= 0:
        return "本次上传图片未得到可用的人脸关键点结果，因此无法进行面部不对称分析。"
    finding_text = "、".join(str(item["name"]) for item in findings[:4])
    if not finding_text:
        finding_text = "未见明显的口角、眼裂、眉部或面部轮廓左右差异"
    if output == "人脸不对称性较高":
        return (
            f"系统综合 {detected_count} 张可识别人脸图片后，判断面部左右不对称性较高，"
            f"置信度约 {confidence * 100.0:.1f}%。主要观察到：{finding_text}。"
        )
    return (
        f"系统综合 {detected_count} 张可识别人脸图片后，未达到高不对称判断标准，"
        f"置信度约 {confidence * 100.0:.1f}%。本次主要观察结果为：{finding_text}。"
    )


def patient_suggestion(analysis: Mapping[str, Any], findings: list[Mapping[str, Any]]) -> str:
    if int(analysis.get("detected_image_count") or 0) <= 0:
        return "请重新上传清晰、光线充足、单人脸图片。"
    if analysis.get("predicted_high_asymmetry"):
        return "建议结合本人实际症状进行人工复核；若同时出现口角歪斜、言语不清、肢体无力或突发不适，应及时就医。"
    if not findings:
        return "本次图片未见明显高不对称表现；如仍有疑虑，可补充露齿微笑、微笑、示齿和正脸图片后再次分析。"
    return "本次未达到高不对称判断标准；如肉眼仍能看到口角或眼裂明显不对称，可补充更清晰的动作图片或进行人工复核。"


def confidence_level(confidence: float) -> str:
    if confidence >= 0.612826:
        return "较高"
    if confidence >= 0.35:
        return "中等"
    return "较低"


def public_image_result(item: Mapping[str, Any]) -> dict[str, Any]:
    input_payload = dict(item.get("input") or {})
    status = str(item.get("status") or "unknown")
    return {
        "filename": input_payload.get("original_filename") or Path(str(input_payload.get("path") or "")).name,
        "media_role": input_payload.get("media_role") or "unknown",
        "media_role_label": role_label(str(input_payload.get("media_role") or "unknown")),
        "status": status,
        "status_message": image_status_message(status),
    }


def role_label(role: str) -> str:
    return ROLE_LABELS.get(normalize_role(role), role or "未标注动作")


def image_status_message(status: str) -> str:
    return {
        "detected": "已识别人脸并纳入分析",
        "no_face": "未识别人脸，未纳入分析",
        "multiple_faces": "检测到多张人脸，未纳入分析",
        "failed": "图片处理失败，未纳入分析",
    }.get(status, "状态未知")


def public_input_spec(max_images: int = MAX_IMAGE_COUNT) -> dict[str, Any]:
    return {
        "accepted_files": [".jpg", ".jpeg", ".png"],
        "minimum_image_count": MIN_IMAGE_COUNT,
        "maximum_image_count": max_images,
        "role_required": False,
        "multiple_images_per_action": True,
        "analysis_unit": "一次上传的 2 到 10 张图片会作为同一人的一组证据合并分析。",
        "image_requirements": [
            "同一人。",
            "单人脸。",
            "面部清晰、光线充足、无遮挡或少遮挡。",
            "图片能被系统识别人脸；未识别人脸的图片不会纳入分析。",
        ],
        "recommended_images": [
            {
                "name": "露齿微笑/微笑/示齿",
                "reason": "用于观察双侧口角夹角、口角牵拉幅度和唇部中线是否左右不一致。",
                "examples": ["smile_teeth", "smile", "teeth"],
            },
            {
                "name": "正脸/面部轮廓",
                "reason": "用于观察静息状态下面部轮廓、双侧眼裂高度、眉部高度和唇部中线偏移。",
                "examples": ["front_contour", "front"],
            },
            {
                "name": "眼周/额眉动作",
                "reason": "用于补充观察双侧眼裂、闭眼、皱眉或抬眉动作是否对称。",
                "examples": ["eyes_right", "eyes_closed", "forehead_wrinkle", "frown"],
            },
        ],
        "warning": "该服务输出为面部对称性辅助分析，不是临床诊断结论。",
    }


def safe_upload_name(original_name: str, field_name: str, role: str, digest: str) -> str:
    original = Path(original_name).name
    suffix = Path(original).suffix.lower()
    stem = Path(original).stem
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    if not stem:
        stem = normalize_role(field_name) or "image"
    return f"{normalize_role(role)}__{stem}__{digest}{suffix}"


def send_file(request: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    if not path.exists():
        send_json(request, 404, {"error": "file not found"})
        return
    data = path.read_bytes()
    request.send_response(200)
    request.send_header("Content-Type", content_type)
    request.send_header("Content-Length", str(len(data)))
    request.end_headers()
    request.wfile.write(data)


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


def is_remote_bind(host: str) -> bool:
    return host in {"", "0.0.0.0", "::"} or (host != "localhost" and not host.startswith("127."))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    model_path = resolve_model_path(args)
    page = args.page.expanduser().resolve()
    rule_dir = resolve_rule_dir(args.rule_dir)
    upload_dir = args.upload_dir.expanduser().resolve()
    if not page.exists():
        raise FileNotFoundError(f"upload page is missing: {page}")

    app = FacialAsymmetryWebApp(
        model_path=model_path,
        rule_dir=rule_dir,
        page=page,
        upload_dir=upload_dir,
        access_token=args.access_token,
        max_upload_mb=args.max_upload_mb,
        max_images=args.max_images,
        max_faces=args.max_faces,
        allow_multiple_faces=args.allow_multiple_faces,
    )
    handler = app.handler_class()
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host, port = server.server_address
    print("FaceSymAi facial asymmetry service:", flush=True)
    for url in access_urls(args.host, port, args.access_token, args.public_url):
        print(f"  {url}", flush=True)
    print(f"Upload results save under: {upload_dir}", flush=True)
    if is_remote_bind(args.host) and not args.access_token:
        print("WARNING: remote binding has no access token. Use --access-token outside a trusted network.", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    finally:
        server.server_close()
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
