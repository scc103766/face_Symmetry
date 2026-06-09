#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import secrets
import socket
import subprocess
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, quote, unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = PROJECT_ROOT / "datasets" / "facesym_v1_all_images_no_gate_20260119"
DEFAULT_PAGE = PROJECT_ROOT / "tools" / "face_asymmetry_label_tool.html"
TEMPLATE_NAME = "16_v11_face_asymmetry_review_label_template.csv"
LABEL_NAME = "16_v11_face_asymmetry_review_labels.csv"
CALIBRATION_SCRIPT = PROJECT_ROOT / "scripts" / "calibrate_v11_hb_proxy_with_review_labels.py"
CORE_ROLES = (
    ("front", "正脸静息", "front_annotation_path"),
    ("smile", "微笑", "smile_annotation_path"),
    ("teeth", "示齿", "teeth_annotation_path"),
    ("eyes_closed", "闭眼", "eyes_closed_annotation_path"),
    ("forehead_wrinkle", "抬眉/皱额", "forehead_wrinkle_annotation_path"),
    ("frown", "皱眉", "frown_annotation_path"),
)
LABEL_FIELDS = (
    "manual_face_asymmetry_label",
    "manual_asymmetry_grade",
    "quality_review_usable_for_calibration",
    "quality_review_label",
    "review_source",
    "reviewer_id",
    "review_date",
    "review_notes",
)
FIELD_ORDER = (
    "patient_sample_id",
    "split",
    "label_group",
    "label_binary",
    "hb_proxy_grade",
    "hb_proxy_grade_num",
    "face_asymmetry_output",
    "manual_face_asymmetry_label",
    "manual_asymmetry_grade",
    "quality_review_usable_for_calibration",
    "quality_review_label",
    "review_source",
    "reviewer_id",
    "review_date",
    "review_notes",
    "review_priority",
    "review_instruction",
)


def main() -> None:
    args = parse_args()
    dataset = args.dataset.resolve()
    page = args.page.resolve()
    metadata = dataset / "metadata"
    require_file(metadata / TEMPLATE_NAME)
    require_file(page)

    app = FaceAsymmetryLabelApp(dataset=dataset, page=page, access_token=args.access_token)
    handler = app.handler_class()
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host, port = server.server_address
    for url in access_urls(args.host, port, args.access_token, args.public_url):
        print(f"Face asymmetry label tool: {url}", flush=True)
    print(f"Labels save to: {metadata / LABEL_NAME}", flush=True)
    if is_remote_bind(args.host) and not args.access_token:
        print("WARNING: remote binding has no access token. Use --access-token when exposing outside a trusted LAN.", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local face-asymmetry manual label tool.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="Dataset root containing metadata and annotated images.")
    parser.add_argument("--page", type=Path, default=DEFAULT_PAGE, help="HTML page to serve.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    parser.add_argument("--access-token", default="", help="Optional token required for APIs and dataset image access.")
    parser.add_argument("--public-url", default="", help="Optional externally reachable base URL to print, for reverse proxy or port mapping.")
    return parser.parse_args()


def require_file(path: Path) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Required file is missing: {path}")
    return path


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


class FaceAsymmetryLabelApp:
    def __init__(self, dataset: Path, page: Path, access_token: str = "") -> None:
        self.dataset = dataset
        self.page = page
        self.access_token = access_token

    @property
    def metadata(self) -> Path:
        return self.dataset / "metadata"

    @property
    def template_path(self) -> Path:
        return self.metadata / TEMPLATE_NAME

    @property
    def labels_path(self) -> Path:
        return self.metadata / LABEL_NAME

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
        if parsed.path in {"/", "/tools/face_asymmetry_label_tool.html"}:
            self.send_file(request, self.page, "text/html; charset=utf-8")
            return
        if not self.authorized(request, parsed.query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        if parsed.path == "/api/cases":
            params = parse_qs(parsed.query)
            payload = self.case_payload(
                priority=first_param(params, "priority"),
                status=first_param(params, "status"),
                query=first_param(params, "q"),
            )
            send_json(request, 200, payload)
            return
        if parsed.path.startswith("/dataset/"):
            relative = unquote(parsed.path.removeprefix("/dataset/"))
            file_path = safe_join(self.dataset, relative)
            if file_path is None or not file_path.is_file():
                send_json(request, 404, {"error": "dataset file not found"})
                return
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_file(request, file_path, content_type)
            return
        send_json(request, 404, {"error": "not found"})

    def handle_post(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        if not self.authorized(request, parsed.query):
            send_json(request, 401, {"error": "unauthorized"})
            return
        if parsed.path == "/api/labels":
            try:
                payload = read_json_body(request)
                saved = save_label_payload(self.template_path, self.labels_path, payload)
            except ValueError as exc:
                send_json(request, 400, {"error": str(exc)})
                return
            send_json(request, 200, {"saved": saved, "summary": self.label_summary()})
            return
        if parsed.path == "/api/recalibrate":
            send_json(request, 200, run_recalibration(self.dataset, self.labels_path))
            return
        send_json(request, 404, {"error": "not found"})

    def send_file(self, request: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        request.send_response(200)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(data)))
        request.end_headers()
        request.wfile.write(data)

    def authorized(self, request: BaseHTTPRequestHandler, query: str) -> bool:
        if not self.access_token:
            return True
        params = parse_qs(query)
        supplied = request.headers.get("X-Label-Tool-Token", "") or first_param(params, "token")
        return secrets.compare_digest(supplied, self.access_token)

    def case_payload(self, priority: str = "", status: str = "", query: str = "") -> dict[str, Any]:
        template_rows, _fields = read_csv_with_fields(self.template_path)
        label_rows, _label_fields = read_csv_with_fields(self.labels_path) if self.labels_path.exists() else ([], [])
        labels_by_patient = {row["patient_sample_id"]: row for row in label_rows if row.get("patient_sample_id")}
        cases = [build_case(row, labels_by_patient.get(row["patient_sample_id"], {}), self.access_token) for row in template_rows]
        cases = filter_cases(cases, priority=priority, status=status, query=query)
        return {
            "dataset": self.dataset.as_posix(),
            "labels_path": self.labels_path.as_posix(),
            "total": len(template_rows),
            "filtered": len(cases),
            "summary": self.label_summary(template_rows=template_rows, label_rows=label_rows),
            "cases": cases,
        }

    def label_summary(
        self,
        template_rows: list[Mapping[str, str]] | None = None,
        label_rows: list[Mapping[str, str]] | None = None,
    ) -> dict[str, Any]:
        if template_rows is None:
            template_rows, _fields = read_csv_with_fields(self.template_path)
        if label_rows is None:
            label_rows, _label_fields = read_csv_with_fields(self.labels_path) if self.labels_path.exists() else ([], [])
        labels_by_patient = {row["patient_sample_id"]: row for row in label_rows if row.get("patient_sample_id")}
        labeled = rejected = positive = negative = 0
        for row in template_rows:
            label = labels_by_patient.get(row["patient_sample_id"], {})
            value = str(label.get("manual_face_asymmetry_label", "")).strip()
            quality = str(label.get("quality_review_usable_for_calibration", "")).strip()
            if value in {"0", "1"}:
                labeled += 1
                positive += int(value == "1")
                negative += int(value == "0")
            if quality == "0":
                rejected += 1
        return {
            "total": len(template_rows),
            "labeled": labeled,
            "positive": positive,
            "negative": negative,
            "quality_rejected": rejected,
            "unlabeled": max(len(template_rows) - labeled - rejected, 0),
            "label_file_exists": self.labels_path.exists(),
        }


def first_param(params: Mapping[str, list[str]], key: str) -> str:
    values = params.get(key, [])
    return values[0].strip() if values else ""


def safe_join(root: Path, relative: str) -> Path | None:
    candidate = (root / relative).resolve()
    root = root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def read_json_body(request: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(request.headers.get("Content-Length", "0"))
    data = request.rfile.read(length) if length else b"{}"
    try:
        payload = json.loads(data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    return payload


def read_csv_with_fields(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_csv(path: Path, rows: list[Mapping[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_case(template_row: Mapping[str, str], label_row: Mapping[str, str], access_token: str = "") -> dict[str, Any]:
    merged = dict(template_row)
    for field in LABEL_FIELDS:
        if label_row.get(field, "") != "":
            merged[field] = label_row.get(field, "")
    images = [
        {
            "role": role,
            "label": label,
            "path": merged.get(path_field, ""),
            "url": dataset_url(merged.get(path_field, ""), access_token),
        }
        for role, label, path_field in CORE_ROLES
    ]
    return {
        "patient_sample_id": merged.get("patient_sample_id", ""),
        "split": merged.get("split", ""),
        "label_group": merged.get("label_group", ""),
        "label_binary": merged.get("label_binary", ""),
        "hb_proxy_grade": merged.get("hb_proxy_grade", ""),
        "hb_proxy_grade_num": merged.get("hb_proxy_grade_num", ""),
        "face_asymmetry_output": merged.get("face_asymmetry_output", ""),
        "review_priority": merged.get("review_priority", ""),
        "face_asymmetry_reason": merged.get("face_asymmetry_reason", ""),
        "hb_reason_codes": merged.get("hb_reason_codes", ""),
        "scores": {
            "resting_symmetry_score": merged.get("resting_symmetry_score", ""),
            "eye_closure_score": merged.get("eye_closure_score", ""),
            "brow_forehead_score": merged.get("brow_forehead_score", ""),
            "smile_mouth_score": merged.get("smile_mouth_score", ""),
            "gross_asymmetry_score": merged.get("gross_asymmetry_score", ""),
            "movement_absence_score": merged.get("movement_absence_score", ""),
            "hb_proxy_overall_score": merged.get("hb_proxy_overall_score", ""),
            "hb_grade_confidence": merged.get("hb_grade_confidence", ""),
        },
        "label": {field: merged.get(field, "") for field in LABEL_FIELDS},
        "status": case_status(merged),
        "images": images,
    }


def dataset_url(relative_path: str, access_token: str = "") -> str:
    if not relative_path:
        return ""
    url = f"/dataset/{relative_path}"
    return append_token(url, access_token)


def append_token(url: str, access_token: str = "") -> str:
    if not access_token:
        return url
    delimiter = "&" if "?" in url else "?"
    return f"{url}{delimiter}token={quote(access_token)}"


def case_status(row: Mapping[str, str]) -> str:
    if str(row.get("quality_review_usable_for_calibration", "")).strip() == "0":
        return "quality_rejected"
    if str(row.get("manual_face_asymmetry_label", "")).strip() in {"0", "1"}:
        return "labeled"
    return "unlabeled"


def filter_cases(cases: list[dict[str, Any]], priority: str = "", status: str = "", query: str = "") -> list[dict[str, Any]]:
    output = cases
    if priority:
        output = [case for case in output if case["review_priority"] == priority]
    if status:
        output = [case for case in output if case["status"] == status]
    if query:
        lowered = query.lower()
        output = [
            case
            for case in output
            if lowered in case["patient_sample_id"].lower()
            or lowered in case["label_group"].lower()
            or lowered in case["review_priority"].lower()
        ]
    return output


def save_label_payload(template_path: Path, labels_path: Path, payload: Mapping[str, Any]) -> dict[str, str]:
    template_rows, template_fields = read_csv_with_fields(template_path)
    existing_rows, existing_fields = read_csv_with_fields(labels_path) if labels_path.exists() else ([], [])
    patient_id = str(payload.get("patient_sample_id", "")).strip()
    if not patient_id:
        raise ValueError("patient_sample_id is required")
    template_by_patient = {row["patient_sample_id"]: row for row in template_rows}
    if patient_id not in template_by_patient:
        raise ValueError(f"Unknown patient_sample_id: {patient_id}")
    existing_by_patient = {row["patient_sample_id"]: row for row in existing_rows if row.get("patient_sample_id")}
    updated_label = normalized_label_payload(payload)
    output_rows: list[dict[str, str]] = []
    for row in template_rows:
        merged = dict(row)
        existing = existing_by_patient.get(row["patient_sample_id"], {})
        for field in LABEL_FIELDS:
            merged[field] = existing.get(field, merged.get(field, ""))
        if row["patient_sample_id"] == patient_id:
            merged.update(updated_label)
        output_rows.append(merged)
    fieldnames = ordered_fields(template_fields, existing_fields, output_rows)
    write_csv(labels_path, output_rows, fieldnames)
    return {"patient_sample_id": patient_id, **updated_label}


def normalized_label_payload(payload: Mapping[str, Any]) -> dict[str, str]:
    label = normalize_choice(payload.get("manual_face_asymmetry_label"), {"0", "1", ""}, "manual_face_asymmetry_label")
    grade = normalize_grade(payload.get("manual_asymmetry_grade"))
    quality = normalize_choice(payload.get("quality_review_usable_for_calibration"), {"0", "1", ""}, "quality_review_usable_for_calibration")
    quality_label = text_field(payload.get("quality_review_label"), 80)
    if quality == "0" and not quality_label:
        quality_label = "人工复核不可用"
    return {
        "manual_face_asymmetry_label": label,
        "manual_asymmetry_grade": grade,
        "quality_review_usable_for_calibration": quality,
        "quality_review_label": quality_label,
        "review_source": text_field(payload.get("review_source") or "html_label_tool", 80),
        "reviewer_id": text_field(payload.get("reviewer_id"), 80),
        "review_date": text_field(payload.get("review_date") or date.today().isoformat(), 20),
        "review_notes": text_field(payload.get("review_notes"), 1000),
    }


def normalize_choice(value: Any, allowed: set[str], field: str) -> str:
    normalized = str(value if value is not None else "").strip()
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return normalized


def normalize_grade(value: Any) -> str:
    normalized = str(value if value is not None else "").strip()
    if normalized == "":
        return ""
    if normalized not in {"1", "2", "3", "4", "5", "6"}:
        raise ValueError("manual_asymmetry_grade must be blank or 1-6")
    return normalized


def text_field(value: Any, limit: int) -> str:
    return str(value if value is not None else "").replace("\r", " ").replace("\n", " ").strip()[:limit]


def ordered_fields(template_fields: list[str], existing_fields: list[str], rows: list[Mapping[str, str]]) -> list[str]:
    fields = list(dict.fromkeys([*FIELD_ORDER, *template_fields, *existing_fields, *[key for row in rows for key in row]]))
    return fields


def run_recalibration(dataset: Path, labels_path: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(CALIBRATION_SCRIPT),
        "--dataset",
        str(dataset),
        "--labels",
        str(labels_path),
    ]
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    summary_path = dataset / "metadata" / "16_v11_face_asymmetry_calibration_summary.json"
    summary: dict[str, Any] = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "summary": summary,
    }


def send_json(request: BaseHTTPRequestHandler, status: int, payload: Mapping[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    request.send_response(status)
    request.send_header("Content-Type", "application/json; charset=utf-8")
    request.send_header("Content-Length", str(len(body)))
    request.end_headers()
    request.wfile.write(body)


if __name__ == "__main__":
    main()
