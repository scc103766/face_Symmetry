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
from .action_detector import (
    detect_side_view,
    detect_teeth_exposure,
)
from .rule62 import DEFAULT_RULE_DIR, load_rule62_config, normalize_role


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PAGE = PROJECT_ROOT / "modules" / "facial_asymmetry_service" / "web_upload.html"
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "tmp" / "facial_asymmetry_service_uploads"
MIN_IMAGE_COUNT = 2
MAX_IMAGE_COUNT = 25
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
# 21 项稳定特征的中文临床解读，覆盖所有 62 规则特征。
FEATURE_INTERPRETATIONS: dict[str, dict[str, str]] = {
    # --- 口部动态特征 (mouth_dynamic scope, 7 项) ---
    "bsdiff_mouth_abs": {
        "title": "双侧口角垂直方向动作幅度差",
        "description": "微笑或露齿时，左右口角上提幅度不一致，可能表现为一侧口角活动不足或口角高度不齐。",
        "group": "mouth_corner",
    },
    "bsdiff_mouth_lateral_abs": {
        "title": "双侧口角水平方向动作幅度差",
        "description": "微笑或露齿时，左右口角向外牵拉幅度不一致，可能表现为一侧口角外展不足。",
        "group": "mouth_corner",
    },
    "raw_mouth_corner_vertical_asym": {
        "title": "静息状态下口角垂直高度差",
        "description": "自然状态下左右口角高度不对称，可能表现为一侧口角低于对侧。",
        "group": "mouth_corner",
    },
    "bsdiff_mouthFrown_abs": {
        "title": "双侧降口角动作幅度差",
        "description": "左右口角下垂动作幅度不一致，可对应一侧口角控制较弱或表情动作不协调。",
        "group": "mouth_corner",
    },
    "raw_lip_midline_deviation": {
        "title": "唇部中线偏移",
        "description": "上下唇中心相对面部中线出现偏移，可能表现为口唇向一侧偏斜。",
        "group": "lip_midline",
    },
    "bsdiff_all_mean_abs": {
        "title": "口部整体动作平均不对称度",
        "description": "口部动态表情的整体左右不对称程度，综合反映口周肌肉群运动的协调性。",
        "group": "mouth_corner",
    },
    # --- 眼周特征 (6 项) ---
    "raw_iris_region_point_spread_asym": {
        "title": "虹膜区域点分布不对称",
        "description": "左右虹膜区域关键点分布不一致，可能表现为一侧眼球位置或眼裂形态不同。",
        "group": "eye_aperture",
    },
    "raw_iris_region_area_asym": {
        "title": "虹膜区域面积不对称",
        "description": "左右虹膜可见区域面积不一致，可能提示一侧眼裂开合程度不同。",
        "group": "eye_aperture",
    },
    "raw_iris_region_centroid_y_asym": {
        "title": "虹膜区域质心垂直不对称",
        "description": "左右虹膜中心垂直位置不一致，可能表现为一侧眼球位置偏高或偏低。",
        "group": "eye_aperture",
    },
    "raw_eye_region_point_spread_asym": {
        "title": "眼周区域点分布不对称",
        "description": "左右眼周关键点分布形态不一致，可能表现为一侧眼周区域大小或形态差异。",
        "group": "eye_aperture",
    },
    "raw_eye_region_centroid_y_asym": {
        "title": "眼周区域质心垂直不对称",
        "description": "左右眼周区域中心垂直位置不一致，可能表现为一侧眼部整体位置偏高或偏低。",
        "group": "eye_aperture",
    },
    "bsdiff_eyeLookDown_abs": {
        "title": "双侧下视动作幅度差",
        "description": "左右眼下视动作幅度不一致，可能提示眼外肌运动不协调。",
        "group": "eye_aperture",
    },
    # --- 眉部特征 (6 项) ---
    "raw_eyebrow_region_height_asym": {
        "title": "眉部区域高度不对称",
        "description": "左右眉部区域高度不一致，可能表现为一侧眉部位置偏低或偏高。",
        "group": "brow_height",
    },
    "raw_eyebrow_region_point_spread_asym": {
        "title": "眉部区域点分布不对称",
        "description": "左右眉部关键点分布形态不一致，可能表现为一侧眉形或眉部张力不同。",
        "group": "brow_height",
    },
    "raw_eyebrow_region_area_asym": {
        "title": "眉部区域面积不对称",
        "description": "左右眉部可见区域面积不一致，可能提示眉眼区域整体形态差异。",
        "group": "brow_height",
    },
    "raw_eyebrow_region_centroid_y_asym": {
        "title": "眉部区域质心垂直不对称",
        "description": "左右眉部中心垂直位置不一致，可能表现为一侧眉毛整体偏低或偏高。",
        "group": "brow_height",
    },
    "raw_brow_outer_height_asym": {
        "title": "眉外侧高度不对称",
        "description": "左右眉外侧高度不一致，可能表现为一侧眉梢下垂或上挑。",
        "group": "brow_height",
    },
    "bsdiff_browDown_abs": {
        "title": "双侧降眉动作幅度差",
        "description": "左右皱眉或降眉动作幅度不一致，可能提示额眉部运动不协调。",
        "group": "brow_height",
    },
    # --- 面部轮廓特征 (3 项) ---
    "raw_face_oval_region_centroid_y_asym": {
        "title": "面部轮廓质心垂直不对称",
        "description": "左右面部轮廓区域的质心垂直位置不一致，可能表现为一侧脸颊下垂或面部轮廓偏斜。",
        "group": "face_contour",
    },
    "raw_face_oval_region_height_asym": {
        "title": "面部轮廓区域高度不对称",
        "description": "左右面部轮廓区域高度不一致，可能表现为一侧脸部整体偏低。",
        "group": "face_contour",
    },
    "raw_all_mesh_region_height_asym": {
        "title": "整体面部网格区域高度不对称",
        "description": "整体面部网格左右高度分布不一致，综合反映面部形态左右差异。",
        "group": "face_contour",
    },
}
REGION_LABELS = {
    "mouth_corner": "口角运动区",
    "lip_midline": "唇部中线区",
    "eye_aperture": "眼裂/眼周区",
    "brow_height": "眉额区",
    "face_contour": "面部轮廓区",
    "unknown": "其他区域",
}


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
        if parsed.path == "/keypoint":
            self._handle_keypoint(request, parsed.query)
            return
        if parsed.path == "/ceshi":
            self._handle_ceshi(request, parsed.query)
            return
        if parsed.path == "/louyachi":
            self._handle_louyachi(request, parsed.query)
            return
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
            send_json(request, 400, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP service returns structured error.
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)})
            return
        send_json(request, 200, report)

    def _handle_keypoint(self, request: BaseHTTPRequestHandler, query: str) -> None:
        if not self.authorized(request, query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        try:
            detection, error_response, _upload_path = self._detect_single_face(request)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP service returns structured error.
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)})
            return
        if error_response is not None:
            send_json(request, 200, error_response)
            return
        send_json(request, 200, {"status": "detected", "detection": detection.to_dict()})

    def _handle_ceshi(self, request: BaseHTTPRequestHandler, query: str) -> None:
        if not self.authorized(request, query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        try:
            detection, error_response, _upload_path = self._detect_single_face(request)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP service returns structured error.
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)})
            return
        if error_response is not None:
            send_json(request, 200, error_response)
            return

        detection_payload = detection.to_dict()
        side_view = detect_side_view(detection_payload)
        send_json(
            request,
            200,
            {
                "status": "detected",
                "side_view": {
                    "detected": side_view.detected,
                    "direction": side_view.direction,
                    "yaw_angle": round(side_view.yaw_angle, 2),
                    "level": side_view.level,
                    "confidence": side_view.confidence,
                    "details": side_view.details,
                },
            },
        )

    def _handle_louyachi(self, request: BaseHTTPRequestHandler, query: str) -> None:
        if not self.authorized(request, query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        try:
            detection, error_response, upload_path = self._detect_single_face(request)
        except ValueError as exc:
            send_json(request, 400, {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - HTTP service returns structured error.
            send_json(request, 500, {"error": type(exc).__name__, "message": str(exc)})
            return
        if error_response is not None:
            send_json(request, 200, error_response)
            return

        teeth_exposure = detect_teeth_exposure(detection.to_dict(), image_path=str(upload_path))
        send_json(
            request,
            200,
            {
                "status": "detected",
                "teeth_exposure": {
                    "detected": teeth_exposure.detected,
                    "mouth_state": teeth_exposure.mouth_state,
                    "confidence": round(teeth_exposure.confidence, 4),
                    "details": teeth_exposure.details,
                },
            },
        )

    def _detect_single_face(self, request: BaseHTTPRequestHandler) -> tuple[Any, dict[str, Any] | None, Path | None]:
        """Read one uploaded image and run MediaPipe face detection."""

        uploads = self.read_uploads(request)
        if not uploads:
            raise ValueError("请上传一张图片。")
        upload = uploads[0]
        with self.detector_lock:
            detection = self.detector.detect_image_path(upload.path)
        if detection is None:
            return None, {"status": "no_face"}, upload.path
        return detection, None, upload.path

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
                role = infer_role_from_filename(Path(original_name)) or role_from_field(field_name) or "unknown"
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
                # Auto-infer role from action detection when filename gives no role
                if upload.media_role == "unknown":
                    detection = public_result.get("detection") or {}
                    if isinstance(detection, dict) and detection.get("status") == "detected":
                        inferred = _infer_role_from_detection(detection, str(upload.path))
                        if inferred != "unknown":
                            public_result["input"]["media_role"] = inferred
                            feature_row["media_role"] = inferred
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
        public_report = build_public_report(report)
        technical_output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output_path.write_text(json.dumps(public_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return public_report


def role_from_field(field_name: str) -> str | None:
    normalized = normalize_role(field_name)
    return FIELD_ROLES.get(normalized)


def _infer_role_from_detection(detection: dict[str, Any], image_path: str) -> str:
    """Infer media_role from action detection results when filename gives no role."""
    try:
        side = detect_side_view(detection)
        teeth = detect_teeth_exposure(detection, image_path=image_path)
    except Exception:
        return "unknown"

    if side.detected and side.direction in ("left", "right"):
        return "eyes_right"
    if teeth.detected and teeth.mouth_state == "teeth_visible":
        return "smile_teeth"
    return "front"


def validate_uploads(uploads: list[UploadedImage], *, max_images: int) -> None:
    if len(uploads) < MIN_IMAGE_COUNT:
        raise ValueError("同一人至少需要 2 张图片；动作不强制限制，但推荐包含露齿微笑/微笑/示齿。")
    if len(uploads) > max_images:
        raise ValueError(f"同一人最多上传 {max_images} 张图片。")


def build_public_report(report: Mapping[str, Any]) -> dict[str, Any]:
    analysis = dict(report.get("analysis") or {})
    feature_results = feature_region_results(analysis)
    top_attributions = feature_results[:5]
    region_results = region_weight_distribution(feature_results)
    confidence = float(analysis.get("face_asymmetry_confidence") or 0.0)
    output = str(analysis.get("face_asymmetry_output") or "无法判断")
    detected_count = int(analysis.get("detected_image_count") or 0)
    input_count = int(report.get("input_count") or 0)
    return {
        "service": report.get("service"),
        "service_version": report.get("service_version"),
        "status": report.get("status"),
        "input_count": input_count,
        "status_counts": report.get("status_counts") or {},
        "analysis": {
            "face_asymmetry_output": output,
            "face_asymmetry_confidence": round(confidence, 6),
            "confidence_percent": round(confidence * 100.0, 2),
            "confidence_level": confidence_level(confidence),
            "detected_image_count": detected_count,
            "uploaded_image_count": input_count,
            "predicted_high_asymmetry": bool(analysis.get("predicted_high_asymmetry")),
            "weighted_disease_score": analysis.get("weighted_disease_score"),
            "score_threshold": analysis.get("score_threshold"),
            "score_margin": analysis.get("score_margin"),
            "triggered_feature_count": int(analysis.get("triggered_feature_count") or 0),
            "total_rule_count": int(analysis.get("feature_count") or len(feature_results) or 21),
            "region_results": region_results,
            "top_attributions": top_attributions,
            "feature_region_results": feature_results,
        },
        "images": [public_image_result(item) for item in report.get("images") or []],
    }


def feature_region_results(analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    """返回 21 个稳定特征的区域分类结果，按归因强度排序。"""
    attributions = list(analysis.get("feature_attributions") or [])
    sorted_attrs = sorted(
        attributions,
        key=lambda item: (
            -float(bool(item.get("triggered"))),
            -float(item.get("medical_priority_contribution") or 0.0),
            -float(item.get("weighted_contribution") or 0.0),
            -float(item.get("medical_priority_evidence_score") or 0.0),
            -float(item.get("evidence_score") or 0.0),
            -float(item.get("medical_priority_score") or 0.0),
            -float(item.get("feature_weight") or 0.0),
            str(item.get("rule_id") or ""),
        ),
    )
    total_weight = sum(float(item.get("feature_weight") or 0.0) for item in sorted_attrs) or 1.0
    results: list[dict[str, Any]] = []
    for rank, attr in enumerate(sorted_attrs, start=1):
        feature_name = str(attr.get("feature_name") or "")
        interpretation = FEATURE_INTERPRETATIONS.get(feature_name, {})
        region = interpretation.get("group", "unknown")
        supporting = attr.get("supporting_image_values") or []
        roles = sorted(
            {
                role_label(str(value.get("media_role") or "unknown"))
                for value in supporting
            }
        )
        image_ids = sorted(
            {
                str(value.get("image_id") or "")
                for value in supporting
                if value.get("image_id")
            }
        )
        feature_weight = float(attr.get("feature_weight") or 0.0)
        contribution = float(attr.get("weighted_contribution") or 0.0)
        medical_priority_contribution = float(attr.get("medical_priority_contribution") or 0.0)
        evidence_score = float(attr.get("evidence_score") or 0.0)
        medical_priority_evidence_score = float(attr.get("medical_priority_evidence_score") or 0.0)
        results.append(
            {
                "rank": rank,
                "feature_name": feature_name,
                "region": region,
                "region_label": REGION_LABELS.get(region, REGION_LABELS["unknown"]),
                "title": interpretation.get("title", feature_name),
                "physiological_meaning": interpretation.get("description", ""),
                "feature_value": attr.get("feature_value"),
                "threshold": attr.get("threshold"),
                "triggered": bool(attr.get("triggered")),
                "feature_weight": round(feature_weight, 6),
                "feature_weight_percent": round(feature_weight / total_weight * 100.0, 2),
                "weighted_contribution": round(contribution, 6),
                "medical_priority_contribution": round(medical_priority_contribution, 6),
                "evidence_score": round(evidence_score, 6),
                "medical_priority_evidence_score": round(medical_priority_evidence_score, 6),
                "evidence_ratio": attr.get("evidence_ratio"),
                "weight_grade": attr.get("weight_grade"),
                "medical_priority_score": attr.get("medical_priority_score"),
                "medical_priority_label": attr.get("medical_priority_label"),
                "medical_priority_multiplier": attr.get("medical_priority_multiplier"),
                "calibration": {
                    "combined_directional_auc": attr.get("combined_directional_auc"),
                    "nonpatient_false_positive_rate": attr.get("nonpatient_false_positive_rate"),
                    "volatility_score": attr.get("volatility_score"),
                    "medical_priority_score": attr.get("medical_priority_score"),
                    "medical_priority_multiplier": attr.get("medical_priority_multiplier"),
                },
                "observed_in": roles,
                "supporting_image_ids": image_ids,
                "supporting_image_count": len(image_ids),
            }
        )
    return results


def region_weight_distribution(feature_results: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    total_weight = sum(float(item.get("feature_weight") or 0.0) for item in feature_results) or 1.0
    total_contribution = sum(float(item.get("weighted_contribution") or 0.0) for item in feature_results) or 1.0
    total_medical_priority_contribution = sum(float(item.get("medical_priority_contribution") or 0.0) for item in feature_results) or 1.0
    for item in feature_results:
        region = str(item.get("region") or "unknown")
        bucket = grouped.setdefault(
            region,
            {
                "region": region,
                "region_label": REGION_LABELS.get(region, REGION_LABELS["unknown"]),
                "feature_count": 0,
                "triggered_feature_count": 0,
                "total_feature_weight": 0.0,
                "triggered_weight": 0.0,
                "medical_priority_triggered_weight": 0.0,
                "feature_names": [],
            },
        )
        weight = float(item.get("feature_weight") or 0.0)
        contribution = float(item.get("weighted_contribution") or 0.0)
        medical_priority_contribution = float(item.get("medical_priority_contribution") or 0.0)
        bucket["feature_count"] += 1
        bucket["total_feature_weight"] += weight
        bucket["triggered_weight"] += contribution
        bucket["medical_priority_triggered_weight"] += medical_priority_contribution
        bucket["feature_names"].append(str(item.get("feature_name") or ""))
        if item.get("triggered"):
            bucket["triggered_feature_count"] += 1
    output: list[dict[str, Any]] = []
    for bucket in grouped.values():
        weight = float(bucket["total_feature_weight"])
        contribution = float(bucket["triggered_weight"])
        medical_priority_contribution = float(bucket["medical_priority_triggered_weight"])
        output.append(
            {
                "region": bucket["region"],
                "region_label": bucket["region_label"],
                "feature_count": bucket["feature_count"],
                "triggered_feature_count": bucket["triggered_feature_count"],
                "total_feature_weight": round(weight, 6),
                "feature_weight_percent": round(weight / total_weight * 100.0, 2),
                "triggered_weight": round(contribution, 6),
                "triggered_weight_percent": round(contribution / total_contribution * 100.0, 2) if total_contribution > 0 else 0.0,
                "medical_priority_triggered_weight": round(medical_priority_contribution, 6),
                "medical_priority_triggered_weight_percent": round(
                    medical_priority_contribution / total_medical_priority_contribution * 100.0, 2
                ) if total_medical_priority_contribution > 0 else 0.0,
                "feature_names": bucket["feature_names"],
            }
        )
    return sorted(
        output,
        key=lambda item: (
            -float(item["medical_priority_triggered_weight"]),
            -float(item["triggered_weight"]),
            -float(item["total_feature_weight"]),
            str(item["region"]),
        ),
    )


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
        "analysis_unit": f"一次上传的 {MIN_IMAGE_COUNT} 到 {max_images} 张图片会作为同一人的一组证据合并分析。",
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
