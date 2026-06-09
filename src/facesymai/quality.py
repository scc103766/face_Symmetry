from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".3gp"}


@dataclass(frozen=True)
class QualityGateConfig:
    min_image_short_side: int = 256
    min_face_short_side: int = 180
    recommended_face_short_side: int = 256
    min_laplacian_variance: float = 45.0
    good_laplacian_variance: float = 140.0
    min_brightness: float = 35.0
    max_brightness: float = 220.0
    good_min_brightness: float = 70.0
    good_max_brightness: float = 190.0
    max_bad_exposure_ratio: float = 0.35
    good_bad_exposure_ratio: float = 0.08
    max_left_right_brightness_delta: float = 55.0
    good_left_right_brightness_delta: float = 25.0
    max_video_duration_sec: float = 30.0
    min_video_duration_sec: float = 0.3
    max_file_bytes: int = 350 * 1024 * 1024
    video_sample_count: int = 3
    pass_threshold: float = 0.78
    review_threshold: float = 0.58
    require_face_detection: bool = True
    require_single_face: bool = True
    block_on_eye_detection: bool = False
    face_detector_backend: str = "opencv_haar"
    version: str = "quality-v1-opencv-heuristic"


@dataclass(frozen=True)
class QualityReason:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "message": self.message}


@dataclass(frozen=True)
class FaceBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def short_side(self) -> int:
        return min(self.width, self.height)

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class FrameQuality:
    frame_index: int
    frame_time_sec: float
    width: int
    height: int
    face_count: int | None
    face_box: FaceBox | None
    eye_count: int | None
    metrics: dict[str, float]
    component_scores: dict[str, float]
    quality_score: float
    quality_level: str
    hard_reject: bool
    reasons: list[QualityReason]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "frame_time_sec": self.frame_time_sec,
            "width": self.width,
            "height": self.height,
            "face_count": self.face_count,
            "face_box": self.face_box.to_dict() if self.face_box else None,
            "eye_count": self.eye_count,
            "metrics": self.metrics,
            "component_scores": self.component_scores,
            "quality_score": self.quality_score,
            "quality_level": self.quality_level,
            "hard_reject": self.hard_reject,
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


@dataclass(frozen=True)
class QualityGateResult:
    path: str
    media_type: str
    quality_score: float
    quality_level: str
    hard_reject: bool
    reasons: list[QualityReason]
    metrics: dict[str, float | str]
    frame_results: list[FrameQuality] = field(default_factory=list)
    version: str = "quality-v1-opencv-heuristic"

    @property
    def accepted_for_scoring(self) -> bool:
        return self.quality_level in {"pass", "review"} and not self.hard_reject

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "media_type": self.media_type,
            "quality_score": self.quality_score,
            "quality_level": self.quality_level,
            "hard_reject": self.hard_reject,
            "accepted_for_scoring": self.accepted_for_scoring,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "metrics": self.metrics,
            "frame_results": [frame.to_dict() for frame in self.frame_results],
            "version": self.version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)


class OpenCVHaarFaceDetector:
    def __init__(self) -> None:
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("OpenCV is not installed") from exc

        self.cv2 = cv2
        base = Path(cv2.data.haarcascades)
        face_path = base / "haarcascade_frontalface_default.xml"
        eye_path = base / "haarcascade_eye.xml"
        self.face_cascade = cv2.CascadeClassifier(str(face_path))
        self.eye_cascade = cv2.CascadeClassifier(str(eye_path))
        if self.face_cascade.empty():
            raise RuntimeError(f"OpenCV face cascade is unavailable: {face_path}")
        if self.eye_cascade.empty():
            self.eye_cascade = None

    def detect_faces(self, gray: np.ndarray) -> list[FaceBox]:
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(64, 64),
        )
        boxes = [FaceBox(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]
        return sorted(boxes, key=lambda box: box.area, reverse=True)

    def detect_eyes(self, gray: np.ndarray, face_box: FaceBox) -> int | None:
        if self.eye_cascade is None:
            return None
        x, y, w, h = face_box.x, face_box.y, face_box.width, face_box.height
        upper_face = gray[y : y + max(1, int(h * 0.62)), x : x + w]
        eyes = self.eye_cascade.detectMultiScale(
            upper_face,
            scaleFactor=1.08,
            minNeighbors=4,
            minSize=(18, 18),
        )
        return int(len(eyes))


class QualityGate:
    def __init__(self, config: QualityGateConfig | None = None) -> None:
        self.config = config or QualityGateConfig()
        self._face_detector: OpenCVHaarFaceDetector | None = None
        self._face_detector_error: str | None = None

    def evaluate_media(self, path: Path, media_type: str | None = None, role: str | None = None) -> QualityGateResult:
        path = path.resolve()
        detected_type = media_type or infer_media_type(path)
        if detected_type == "image":
            return self.evaluate_image(path, role=role)
        if detected_type == "video":
            return self.evaluate_video(path, role=role)
        return self._reject(path, detected_type, "unsupported_media_type", f"不支持的媒体类型: {path.suffix}")

    def evaluate_image(self, path: Path, *, role: str | None = None) -> QualityGateResult:
        if not path.exists():
            return self._reject(path, "image", "file_missing", "文件不存在")
        file_error = self._file_level_error(path, "image")
        if file_error:
            return self._reject(path, "image", file_error[0], file_error[1])

        try:
            image = load_image_rgb(path)
        except Exception as exc:  # noqa: BLE001 - returned as gate result
            return self._reject(path, "image", "image_unreadable", f"图片无法读取: {exc}")

        frame = self._evaluate_frame(image, 0, 0.0, role=role)
        return QualityGateResult(
            path=path.as_posix(),
            media_type="image",
            quality_score=frame.quality_score,
            quality_level=frame.quality_level,
            hard_reject=frame.hard_reject,
            reasons=frame.reasons,
            metrics={"file_bytes": path.stat().st_size, **frame.metrics},
            frame_results=[frame],
            version=self.config.version,
        )

    def evaluate_video(self, path: Path, *, role: str | None = None) -> QualityGateResult:
        if not path.exists():
            return self._reject(path, "video", "file_missing", "文件不存在")
        file_error = self._file_level_error(path, "video")
        if file_error:
            return self._reject(path, "video", file_error[0], file_error[1])

        try:
            frames, info = sample_video_frames(path, self.config.video_sample_count)
        except Exception as exc:  # noqa: BLE001 - returned as gate result
            return self._reject(path, "video", "video_unreadable", f"视频无法读取: {exc}")

        reasons: list[QualityReason] = []
        duration = float(info.get("duration_sec", 0.0))
        frame_count = int(info.get("frame_count", 0))
        fps = float(info.get("fps", 0.0))
        if frame_count <= 0:
            reasons.append(QualityReason("video_no_frames", "reject", "视频没有可读取帧"))
        if duration and duration < self.config.min_video_duration_sec:
            reasons.append(QualityReason("video_too_short", "reject", "视频时长过短"))
        if duration > self.config.max_video_duration_sec:
            reasons.append(QualityReason("video_too_long", "reject", "视频时长超过 V1 输入限制"))

        frame_results = [
            self._evaluate_frame(image, frame_index, frame_time_sec, role=role)
            for frame_index, frame_time_sec, image in frames
        ]
        if not frame_results:
            reasons.append(QualityReason("video_no_sampled_frames", "reject", "视频无法抽取质量检测帧"))

        reject_frame_count = sum(1 for frame in frame_results if frame.hard_reject)
        pass_or_review_count = sum(1 for frame in frame_results if frame.quality_level in {"pass", "review"})
        if frame_results and pass_or_review_count == 0:
            reasons.append(QualityReason("video_all_frames_rejected", "reject", "抽样帧全部未通过质量门控"))
        elif reject_frame_count:
            reasons.append(QualityReason("video_some_frames_rejected", "warn", "部分视频抽样帧质量不达标"))

        hard_reject = any(reason.severity == "reject" for reason in reasons)
        if frame_results:
            quality_score = sum(frame.quality_score for frame in frame_results) / len(frame_results)
        else:
            quality_score = 0.0
        quality_level = self._level(quality_score, hard_reject)
        return QualityGateResult(
            path=path.as_posix(),
            media_type="video",
            quality_score=quality_score,
            quality_level=quality_level,
            hard_reject=hard_reject,
            reasons=reasons + flatten_reasons(frame_results),
            metrics={
                "file_bytes": path.stat().st_size,
                "duration_sec": duration,
                "fps": fps,
                "frame_count": frame_count,
                "sampled_frames": len(frame_results),
                "rejected_sampled_frames": reject_frame_count,
            },
            frame_results=frame_results,
            version=self.config.version,
        )

    def _evaluate_frame(self, image: np.ndarray, frame_index: int, frame_time_sec: float, *, role: str | None) -> FrameQuality:
        height, width = image.shape[:2]
        gray = to_gray_uint8(image)
        metrics = compute_image_metrics(gray)
        reasons: list[QualityReason] = []
        component_scores: dict[str, float] = {
            "resolution": clamp01(min(width, height) / self.config.min_image_short_side),
            "sharpness": ramp(metrics["laplacian_variance"], self.config.min_laplacian_variance, self.config.good_laplacian_variance),
            "brightness": brightness_score(metrics["brightness_mean"], self.config.good_min_brightness, self.config.good_max_brightness),
            "exposure": 1.0 - ramp(metrics["bad_exposure_ratio"], self.config.good_bad_exposure_ratio, self.config.max_bad_exposure_ratio),
            "illumination_balance": 1.0
            - ramp(
                metrics["left_right_brightness_delta"],
                self.config.good_left_right_brightness_delta,
                self.config.max_left_right_brightness_delta,
            ),
        }

        face_count: int | None = None
        face_box: FaceBox | None = None
        eye_count: int | None = None
        if min(width, height) < self.config.min_image_short_side:
            reasons.append(QualityReason("image_too_small", "reject", "图片短边低于 V1 最小输入尺寸"))
        if metrics["laplacian_variance"] < self.config.min_laplacian_variance:
            reasons.append(QualityReason("image_blurry", "reject", "图片清晰度不足，建议重采"))
        if not (self.config.min_brightness <= metrics["brightness_mean"] <= self.config.max_brightness):
            reasons.append(QualityReason("bad_brightness", "reject", "图片亮度严重异常"))
        if metrics["bad_exposure_ratio"] > self.config.max_bad_exposure_ratio:
            reasons.append(QualityReason("bad_exposure", "reject", "图片过曝或欠曝比例过高"))
        if metrics["left_right_brightness_delta"] > self.config.max_left_right_brightness_delta:
            reasons.append(QualityReason("uneven_lighting", "warn", "左右光照差异较大，结果可信度下降"))

        detector = self._get_face_detector()
        face_required = self.config.require_face_detection
        if detector is None:
            if face_required:
                reasons.append(QualityReason("face_detector_unavailable", "reject", self._face_detector_error or "人脸检测器不可用"))
                component_scores["face_size"] = 0.0
                component_scores["occlusion_proxy"] = 0.0
            else:
                component_scores["face_count"] = 1.0
                component_scores["face_size"] = 1.0
                component_scores["occlusion_proxy"] = 1.0
        else:
            faces = detector.detect_faces(gray)
            face_count = len(faces)
            if faces:
                face_box = faces[0]
                metrics["face_short_side"] = float(face_box.short_side)
                component_scores["face_size"] = clamp01(face_box.short_side / self.config.recommended_face_short_side)
                if face_required and face_box.short_side < self.config.min_face_short_side:
                    reasons.append(QualityReason("face_too_small", "reject", "人脸框短边过小，无法稳定分析"))
                eye_count = detector.detect_eyes(gray, face_box)
                if eye_count is not None:
                    metrics["eye_count"] = float(eye_count)
                    component_scores["occlusion_proxy"] = 1.0 if eye_count >= 2 else 0.65 if eye_count == 1 else 0.25
                    if face_required and eye_count < 1:
                        severity = "reject" if self.config.block_on_eye_detection else "warn"
                        reasons.append(QualityReason("core_region_occlusion_proxy", severity, "眼部核心区域疑似不可见或遮挡"))
            else:
                component_scores["face_size"] = 0.0 if face_required else 1.0
                component_scores["occlusion_proxy"] = 0.0 if face_required else 1.0

            component_scores["face_count"] = 1.0 if not face_required or face_count == 1 else 0.0
            if face_required and self.config.require_single_face:
                if face_count == 0:
                    reasons.append(QualityReason("no_face", "reject", "未检测到有效单人脸"))
                elif face_count > 1:
                    reasons.append(QualityReason("multiple_faces", "reject", "检测到多人脸，V1 只接受单人脸输入"))

        if role and role in {"teeth", "smile_teeth"}:
            reasons.append(QualityReason("teeth_compliance_proxy", "info", "露齿合规 V1 当前仅做基础质量门控，精确口部合规需关键点检测"))

        quality_score = weighted_mean(
            component_scores,
            {
                "resolution": 0.12,
                "sharpness": 0.18,
                "brightness": 0.14,
                "exposure": 0.14,
                "illumination_balance": 0.08,
                "face_count": 0.20,
                "face_size": 0.10,
                "occlusion_proxy": 0.04,
            },
        )
        hard_reject = any(reason.severity == "reject" for reason in reasons)
        return FrameQuality(
            frame_index=frame_index,
            frame_time_sec=frame_time_sec,
            width=width,
            height=height,
            face_count=face_count,
            face_box=face_box,
            eye_count=eye_count,
            metrics=metrics,
            component_scores=component_scores,
            quality_score=quality_score,
            quality_level=self._level(quality_score, hard_reject),
            hard_reject=hard_reject,
            reasons=reasons,
        )

    def _get_face_detector(self) -> OpenCVHaarFaceDetector | None:
        if self.config.face_detector_backend != "opencv_haar":
            self._face_detector_error = f"unsupported face detector backend: {self.config.face_detector_backend}"
            return None
        if self._face_detector is not None:
            return self._face_detector
        if self._face_detector_error is not None:
            return None
        try:
            self._face_detector = OpenCVHaarFaceDetector()
            return self._face_detector
        except Exception as exc:  # noqa: BLE001 - converted into gate result
            self._face_detector_error = str(exc)
            return None

    def _file_level_error(self, path: Path, media_type: str) -> tuple[str, str] | None:
        if path.stat().st_size <= 0:
            return "empty_file", "文件为空"
        if path.stat().st_size > self.config.max_file_bytes:
            return "file_too_large", "文件超过 V1 最大输入大小"
        suffix = path.suffix.lower()
        if media_type == "image" and suffix not in IMAGE_EXTENSIONS:
            return "unsupported_image_format", f"不支持的图片格式: {suffix}"
        if media_type == "video" and suffix not in VIDEO_EXTENSIONS:
            return "unsupported_video_format", f"不支持的视频格式: {suffix}"
        return None

    def _reject(self, path: Path, media_type: str, code: str, message: str) -> QualityGateResult:
        return QualityGateResult(
            path=path.as_posix(),
            media_type=media_type,
            quality_score=0.0,
            quality_level="reject",
            hard_reject=True,
            reasons=[QualityReason(code, "reject", message)],
            metrics={},
            version=self.config.version,
        )

    def _level(self, score: float, hard_reject: bool) -> str:
        if hard_reject:
            return "reject"
        if score >= self.config.pass_threshold:
            return "pass"
        if score >= self.config.review_threshold:
            return "review"
        return "reject"


def infer_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def load_image_rgb(path: Path) -> np.ndarray:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow is required to read images") from exc

    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def sample_video_frames(path: Path, sample_count: int) -> tuple[list[tuple[int, float, np.ndarray]], dict[str, float]]:
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("OpenCV is required to read videos") from exc

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError("VideoCapture could not open file")
    try:
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        duration = frame_count / fps if frame_count > 0 and fps > 0 else 0.0
        if frame_count <= 0:
            return [], {"frame_count": 0, "fps": fps, "duration_sec": duration}

        if sample_count <= 1 or frame_count == 1:
            indices = [0]
        else:
            indices = sorted({int(round(value)) for value in np.linspace(0, frame_count - 1, num=min(sample_count, frame_count))})

        frames: list[tuple[int, float, np.ndarray]] = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append((index, index / fps if fps > 0 else 0.0, rgb))
        return frames, {"frame_count": frame_count, "fps": fps, "duration_sec": duration}
    finally:
        capture.release()


def to_gray_uint8(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        gray = image
    else:
        gray = np.dot(image[..., :3], [0.299, 0.587, 0.114])
    return np.asarray(np.clip(gray, 0, 255), dtype=np.uint8)


def compute_image_metrics(gray: np.ndarray) -> dict[str, float]:
    brightness = float(np.mean(gray))
    dark_ratio = float(np.mean(gray <= 10))
    bright_ratio = float(np.mean(gray >= 245))
    bad_exposure_ratio = dark_ratio + bright_ratio
    height, width = gray.shape[:2]
    midpoint = max(1, width // 2)
    left_mean = float(np.mean(gray[:, :midpoint]))
    right_mean = float(np.mean(gray[:, midpoint:])) if midpoint < width else left_mean
    return {
        "brightness_mean": brightness,
        "dark_pixel_ratio": dark_ratio,
        "bright_pixel_ratio": bright_ratio,
        "bad_exposure_ratio": bad_exposure_ratio,
        "left_right_brightness_delta": abs(left_mean - right_mean),
        "laplacian_variance": laplacian_variance(gray),
    }


def laplacian_variance(gray: np.ndarray) -> float:
    try:
        import cv2  # type: ignore[import-not-found]

        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except ImportError:
        arr = gray.astype(np.float32)
        center = arr[1:-1, 1:-1] * -4.0
        lap = center + arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:]
        return float(np.var(lap)) if lap.size else 0.0


def flatten_reasons(frames: list[FrameQuality]) -> list[QualityReason]:
    by_code: dict[str, QualityReason] = {}
    for frame in frames:
        for reason in frame.reasons:
            if reason.severity == "info":
                continue
            by_code.setdefault(reason.code, reason)
    return list(by_code.values())


def ramp(value: float, low: float, high: float) -> float:
    if high <= low:
        return 1.0 if value >= high else 0.0
    return clamp01((value - low) / (high - low))


def clamp01(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))


def brightness_score(value: float, good_min: float, good_max: float) -> float:
    if good_min <= value <= good_max:
        return 1.0
    if value < good_min:
        return ramp(value, 0.0, good_min)
    return 1.0 - ramp(value, good_max, 255.0)


def weighted_mean(values: dict[str, float], weights: dict[str, float]) -> float:
    numerator = 0.0
    denominator = 0.0
    for key, value in values.items():
        weight = weights.get(key, 0.0)
        if weight <= 0:
            continue
        numerator += clamp01(value) * weight
        denominator += weight
    return numerator / denominator if denominator else 0.0
