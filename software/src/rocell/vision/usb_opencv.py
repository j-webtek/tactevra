"""Explicit OpenCV adapter for a separately identified USB camera.

``cv2`` is imported only by :meth:`UsbOpenCvCamera.open`.  Importing this
module or constructing the adapter cannot enumerate or open camera hardware.
"""

from __future__ import annotations

import importlib
import math
import string
from threading import RLock
import time
from typing import Any, Callable
import uuid

from .camera import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraNotOpenError,
    CameraOpenError,
    CameraProbeError,
    CameraStateError,
    CameraStatus,
    FrameLimitError,
    FramePacket,
    ResolutionMismatchError,
    TimestampQuality,
    jpeg_dimensions,
    positive_finite,
    positive_int,
    settings_digest,
)


OPENCV_ORIENTATION_PATTERN_VERSION = "rocell.opencv_orientation_pattern.v1"
OPENCV_TOP_LEFT_BGR_ORIENTATION = "TOP_LEFT_BGR_NO_MIRROR"
_ORIENTATION_SAMPLE_FRACTIONS = (
    (0.20, 0.20),
    (0.80, 0.20),
    (0.20, 0.80),
    (0.80, 0.80),
)
_ORIENTATION_COLORS_BGR = {
    "BLUE": (255.0, 0.0, 0.0),
    "GREEN": (0.0, 255.0, 0.0),
    "RED": (0.0, 0.0, 255.0),
    "YELLOW": (0.0, 255.0, 255.0),
    "CYAN": (255.0, 255.0, 0.0),
}
_EXPECTED_ORIENTATION_LABELS = ("BLUE", "GREEN", "RED", "YELLOW")


def verify_opencv_top_left_bgr_orientation(
    frame: Any,
    *,
    maximum_normalized_color_distance: float = 90.0,
) -> str:
    """Verify an asymmetric four-marker commissioning frame.

    The physical or displayed pattern has blue at top left, green at top right,
    red at bottom left, and yellow at bottom right.  OpenCV must deliver the
    decoded frame with a top-left row origin and BGR channel order.  This check
    is deliberately separate from camera opening: a commissioned workflow must
    place the known pattern in view and call this function on the actual decoded
    frame before ordinary captures are admitted.
    """

    shape = getattr(frame, "shape", None)
    if (
        not isinstance(shape, tuple)
        or len(shape) != 3
        or isinstance(shape[0], bool)
        or isinstance(shape[1], bool)
        or not isinstance(shape[0], int)
        or not isinstance(shape[1], int)
        or shape[0] < 16
        or shape[1] < 16
        or not isinstance(shape[2], int)
        or shape[2] < 3
    ):
        raise CameraProbeError("orientation pattern frame must be HxWx3+ with at least 16 pixels per axis")
    if (
        isinstance(maximum_normalized_color_distance, bool)
        or not isinstance(maximum_normalized_color_distance, (int, float))
        or not math.isfinite(float(maximum_normalized_color_distance))
        or not 0 < float(maximum_normalized_color_distance) < 255
    ):
        raise CameraConfigurationError(
            "maximum_normalized_color_distance must be finite and between 0 and 255"
        )

    height, width = shape[:2]
    radius = max(1, min(height, width) // 50)
    observed_labels: list[str] = []
    for x_fraction, y_fraction in _ORIENTATION_SAMPLE_FRACTIONS:
        center_x = round((width - 1) * x_fraction)
        center_y = round((height - 1) * y_fraction)
        totals = [0.0, 0.0, 0.0]
        count = 0
        for y in range(max(0, center_y - radius), min(height, center_y + radius + 1)):
            for x in range(max(0, center_x - radius), min(width, center_x + radius + 1)):
                pixel = frame[y, x]
                try:
                    channels = tuple(float(pixel[index]) for index in range(3))
                except (IndexError, TypeError, ValueError) as exc:
                    raise CameraProbeError("orientation pattern frame pixels must expose three numeric channels") from exc
                if any(not math.isfinite(value) or value < 0 or value > 255 for value in channels):
                    raise CameraProbeError("orientation pattern frame channels must be finite bytes")
                for index, value in enumerate(channels):
                    totals[index] += value
                count += 1
        mean = tuple(value / count for value in totals)
        peak = max(mean)
        if peak < 32:
            raise CameraProbeError("orientation marker is too dark to classify")
        normalized = tuple(value * 255.0 / peak for value in mean)
        distances = {
            label: math.sqrt(sum((actual - expected) ** 2 for actual, expected in zip(normalized, color)))
            for label, color in _ORIENTATION_COLORS_BGR.items()
        }
        label, distance = min(distances.items(), key=lambda item: item[1])
        if distance > float(maximum_normalized_color_distance):
            raise CameraProbeError("orientation marker color is outside the commissioned BGR pattern")
        observed_labels.append(label)

    observed = tuple(observed_labels)
    if observed == _EXPECTED_ORIENTATION_LABELS:
        return OPENCV_TOP_LEFT_BGR_ORIENTATION
    known_failures = {
        ("RED", "YELLOW", "BLUE", "GREEN"): "vertical flip",
        ("GREEN", "BLUE", "YELLOW", "RED"): "horizontal mirror",
        ("YELLOW", "RED", "GREEN", "BLUE"): "180-degree rotation",
        ("RED", "GREEN", "BLUE", "CYAN"): "RGB/BGR channel swap",
    }
    failure = known_failures.get(observed, "unexpected marker permutation")
    raise CameraProbeError(
        f"OpenCV orientation sentinel rejected {failure}: observed {observed!r}"
    )


def _validate_selector(value: object) -> int | str:
    if isinstance(value, bool):
        raise CameraConfigurationError("index_or_path must be an integer index or path")
    if isinstance(value, int):
        if value < 0:
            raise CameraConfigurationError("Camera index must be nonnegative")
        return value
    if isinstance(value, str) and value.strip() and "\x00" not in value:
        if len(value) > 4096:
            raise CameraConfigurationError("Camera device path is too long")
        return value
    raise CameraConfigurationError("index_or_path must be an integer index or path")


def _validate_pixel_format(value: object) -> str | None:
    """Validate an optional OpenCV/Video4Linux four-character pixel format.

    Camera vendors commonly spell the packed 4:2:2 format as ``YUY2`` while
    Video4Linux reports the same byte layout as ``YUYV``.  The configured value
    is retained verbatim for device negotiation; comparison normalizes that one
    well-defined alias only.
    """

    if value is None:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 4
        or any(character not in string.ascii_letters + string.digits for character in value)
    ):
        raise CameraConfigurationError(
            "pixel_format must be four ASCII letters/digits when provided"
        )
    return value.upper()


def _normalize_pixel_format(value: str) -> str:
    upper = value.upper()
    return "YUY2" if upper == "YUYV" else upper


def _decode_fourcc(value: float) -> str:
    """Decode a finite OpenCV FOURCC property into four printable characters."""

    if not math.isfinite(value) or value < 0:
        raise CameraProbeError(f"USB camera reported invalid pixel format: {value!r}")
    encoded = int(round(value))
    decoded = "".join(chr((encoded >> (8 * index)) & 0xFF) for index in range(4))
    if len(decoded) != 4 or any(character not in string.printable for character in decoded):
        raise CameraProbeError(
            f"USB camera reported undecodable pixel format FOURCC {encoded}"
        )
    return decoded


def _default_cv2_loader() -> Any:
    try:
        return importlib.import_module("cv2")
    except ImportError as exc:
        raise CameraOpenError(
            "OpenCV is required only for UsbOpenCvCamera; install it before opening"
        ) from exc


class UsbOpenCvCamera:
    """One configured OpenCV capture device with no fallback or retry.

    ``identity`` is an expected identity, never proof by itself.  A commissioned
    setup must also provide ``observed_identity_provider`` and set
    ``require_identity_match`` so the backend-observed descriptor/serial/path is
    compared before capture is accepted.
    """

    def __init__(
        self,
        index_or_path: int | str = 0,
        *,
        identity: str | None = None,
        width_px: int = 640,
        height_px: int = 480,
        fps: float = 30.0,
        pixel_format: str | None = None,
        backend: int | None = None,
        jpeg_quality: int = 95,
        max_jpeg_bytes: int = 8 * 1024 * 1024,
        fps_relative_tolerance: float = 0.05,
        cv2_loader: Callable[[], Any] | None = None,
        observed_identity_provider: Callable[[int | str], str | None] | None = None,
        require_identity_match: bool = False,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        capture_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.index_or_path = _validate_selector(index_or_path)
        if identity is not None:
            if not isinstance(identity, str) or not identity.strip() or "\x00" in identity:
                raise CameraConfigurationError("identity must be non-empty text when provided")
            if len(identity) > 1024:
                raise CameraConfigurationError("identity is too long")
            identity = identity.strip()
        self.identity = identity
        self.width_px = positive_int("width_px", width_px)
        self.height_px = positive_int("height_px", height_px)
        self.fps = positive_finite("fps", fps)
        self.pixel_format = _validate_pixel_format(pixel_format)
        if backend is not None and (
            isinstance(backend, bool) or not isinstance(backend, int) or backend < 0
        ):
            raise CameraConfigurationError("backend must be a nonnegative OpenCV backend integer")
        self.backend = backend
        if (
            isinstance(jpeg_quality, bool)
            or not isinstance(jpeg_quality, int)
            or not 1 <= jpeg_quality <= 100
        ):
            raise CameraConfigurationError("jpeg_quality must be an integer from 1 to 100")
        self.jpeg_quality = jpeg_quality
        self.max_jpeg_bytes = positive_int("max_jpeg_bytes", max_jpeg_bytes)
        tolerance = positive_finite("fps_relative_tolerance", fps_relative_tolerance)
        if tolerance >= 1:
            raise CameraConfigurationError("fps_relative_tolerance must be less than 1")
        self.fps_relative_tolerance = tolerance
        if cv2_loader is not None and not callable(cv2_loader):
            raise CameraConfigurationError("cv2_loader must be callable")
        if observed_identity_provider is not None and not callable(observed_identity_provider):
            raise CameraConfigurationError("observed_identity_provider must be callable")
        if not isinstance(require_identity_match, bool):
            raise CameraConfigurationError("require_identity_match must be boolean")
        if require_identity_match and identity is None:
            raise CameraConfigurationError(
                "require_identity_match needs an expected identity"
            )
        if not callable(clock_ns):
            raise CameraConfigurationError("clock_ns must be callable")
        if capture_id_factory is not None and not callable(capture_id_factory):
            raise CameraConfigurationError("capture_id_factory must be callable")
        self._cv2_loader = cv2_loader or _default_cv2_loader
        self._observed_identity_provider = observed_identity_provider
        self.require_identity_match = require_identity_match
        self._clock_ns = clock_ns
        self._capture_id_factory = capture_id_factory or (lambda: uuid.uuid4().hex)
        self._capture: Any = None
        self._cv2: Any = None
        self._observed_identity: str | None = None
        self._lock = RLock()
        self._settings_hash = settings_digest(
            {
                "backend": "usb_opencv",
                "index_or_path": self.index_or_path,
                "identity": self.identity,
                "require_identity_match": self.require_identity_match,
                "width_px": self.width_px,
                "height_px": self.height_px,
                "fps": self.fps,
                "pixel_format": self.pixel_format,
                "opencv_backend": self.backend,
                "jpeg_quality": self.jpeg_quality,
            }
        )

    @property
    def camera_index(self) -> int | str:
        """Compatibility name for the explicitly configured selector."""

        return self.index_or_path

    @property
    def is_open(self) -> bool:
        return self._capture is not None and bool(self._capture.isOpened())

    @property
    def configured_identity(self) -> str:
        if self.identity is not None:
            return self.identity
        return f"unverified-opencv-selector:{self.index_or_path}"

    def _observe_identity_unlocked(self) -> None:
        """Observe and compare identity without treating caller text as evidence."""

        provider = self._observed_identity_provider
        observed = None if provider is None else provider(self.index_or_path)
        if observed is not None:
            if not isinstance(observed, str) or not observed.strip() or "\x00" in observed:
                raise CameraOpenError("Observed USB camera identity is invalid")
            observed = observed.strip()
        if self.identity is not None and observed is not None and observed != self.identity:
            raise CameraOpenError(
                "Observed USB camera identity does not match the configured identity"
            )
        if self.require_identity_match and observed != self.identity:
            raise CameraOpenError("Persistent USB camera identity could not be verified")
        self._observed_identity = observed

    @staticmethod
    def _property(cv2_module: Any, name: str) -> int:
        value = getattr(cv2_module, name, None)
        if isinstance(value, bool) or not isinstance(value, int):
            raise CameraOpenError(f"OpenCV module does not provide integer {name}")
        return value

    def open(self) -> None:
        """Open and verify one configured device; never enumerate or fallback."""

        with self._lock:
            if self._capture is not None:
                raise CameraStateError("USB camera already has a capture; close it first")
            cv2_module = self._cv2_loader()
            video_capture = getattr(cv2_module, "VideoCapture", None)
            if not callable(video_capture):
                raise CameraOpenError("OpenCV module does not provide VideoCapture")
            capture: Any = None
            try:
                if self.backend is None:
                    capture = video_capture(self.index_or_path)
                else:
                    capture = video_capture(self.index_or_path, self.backend)
                if capture is None or not bool(capture.isOpened()):
                    raise CameraOpenError(
                        f"Could not open configured USB camera {self.configured_identity!r}"
                    )
                if self.pixel_format is not None:
                    fourcc_factory = getattr(cv2_module, "VideoWriter_fourcc", None)
                    if not callable(fourcc_factory):
                        raise CameraOpenError(
                            "OpenCV module cannot request the configured pixel format"
                        )
                    fourcc = fourcc_factory(*self.pixel_format)
                    if isinstance(fourcc, bool) or not isinstance(fourcc, int):
                        raise CameraOpenError(
                            "OpenCV returned an invalid configured pixel-format FOURCC"
                        )
                    capture.set(
                        self._property(cv2_module, "CAP_PROP_FOURCC"),
                        float(fourcc),
                    )
                capture.set(
                    self._property(cv2_module, "CAP_PROP_FRAME_WIDTH"),
                    float(self.width_px),
                )
                capture.set(
                    self._property(cv2_module, "CAP_PROP_FRAME_HEIGHT"),
                    float(self.height_px),
                )
                capture.set(self._property(cv2_module, "CAP_PROP_FPS"), self.fps)
                self._cv2 = cv2_module
                self._capture = capture
                self._observe_identity_unlocked()
                self._probe_unlocked()
            except Exception:
                self._capture = None
                self._cv2 = None
                self._observed_identity = None
                if capture is not None:
                    try:
                        capture.release()
                    except Exception:
                        pass
                raise

    def connect(self) -> None:
        """Alias retained for callers that name explicit lifecycle start connect."""

        self.open()

    def _require_open(self) -> Any:
        if not self.is_open:
            raise CameraNotOpenError("USB camera is not explicitly open")
        return self._capture

    def _probe_unlocked(self) -> CameraStatus:
        capture = self._require_open()
        cv2_module = self._cv2
        actual_width = float(
            capture.get(self._property(cv2_module, "CAP_PROP_FRAME_WIDTH"))
        )
        actual_height = float(
            capture.get(self._property(cv2_module, "CAP_PROP_FRAME_HEIGHT"))
        )
        actual_fps = float(capture.get(self._property(cv2_module, "CAP_PROP_FPS")))
        for name, value in (
            ("width", actual_width),
            ("height", actual_height),
            ("fps", actual_fps),
        ):
            if not math.isfinite(value) or value <= 0:
                raise CameraProbeError(f"USB camera reported invalid {name}: {value!r}")
        if not math.isclose(actual_width, self.width_px, rel_tol=0.0, abs_tol=0.5):
            raise CameraProbeError(
                f"USB camera width is {actual_width:g}, expected {self.width_px}"
            )
        if not math.isclose(actual_height, self.height_px, rel_tol=0.0, abs_tol=0.5):
            raise CameraProbeError(
                f"USB camera height is {actual_height:g}, expected {self.height_px}"
            )
        if not math.isclose(
            actual_fps,
            self.fps,
            rel_tol=self.fps_relative_tolerance,
            abs_tol=0.01,
        ):
            raise CameraProbeError(
                f"USB camera FPS is {actual_fps:g}, expected {self.fps:g}"
            )
        observed_pixel_format: str | None = None
        if self.pixel_format is not None:
            observed_pixel_format = _decode_fourcc(
                float(
                    capture.get(
                        self._property(cv2_module, "CAP_PROP_FOURCC")
                    )
                )
            )
            if _normalize_pixel_format(observed_pixel_format) != _normalize_pixel_format(
                self.pixel_format
            ):
                raise CameraProbeError(
                    "USB camera pixel format is "
                    f"{observed_pixel_format!r}, expected {self.pixel_format!r}"
                )
        return CameraStatus(
            backend="usb_opencv",
            identity=self._observed_identity or self.configured_identity,
            is_open=True,
            width_px=int(round(actual_width)),
            height_px=int(round(actual_height)),
            fps=actual_fps,
            settings_hash=self._settings_hash,
            timestamp_quality=TimestampQuality.HOST_RECEIPT,
            persistent_identity=(
                self.identity is not None and self._observed_identity == self.identity
            ),
            details=(
                ("selector", str(self.index_or_path)),
                ("expected_identity", self.identity or "NONE"),
                ("observed_identity", self._observed_identity or "UNOBSERVED"),
                ("configured_pixel_format", self.pixel_format or "UNSPECIFIED"),
                ("observed_pixel_format", observed_pixel_format or "UNOBSERVED"),
            ),
        )

    def probe(self) -> CameraStatus:
        with self._lock:
            return self._probe_unlocked()

    @staticmethod
    def _frame_shape(frame: Any) -> tuple[int, int]:
        shape = getattr(frame, "shape", None)
        if not isinstance(shape, tuple) or len(shape) not in (2, 3):
            raise CameraCaptureError("OpenCV frame has an unsupported shape")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in shape):
            raise CameraCaptureError("OpenCV frame shape must contain integers")
        height, width = shape[0], shape[1]
        if width <= 0 or height <= 0:
            raise CameraCaptureError("OpenCV frame has an empty resolution")
        if len(shape) == 3 and shape[2] not in (1, 3, 4):
            raise CameraCaptureError("OpenCV frame has an unsupported channel count")
        return width, height

    def capture(self) -> FramePacket:
        """Read and JPEG-encode exactly one frame with a host timing bracket."""

        with self._lock:
            capture = self._require_open()
            request_ns = self._clock_ns()
            success, frame = capture.read()
            first_byte_ns = self._clock_ns()
            if success is not True or frame is None:
                raise CameraCaptureError("USB camera did not return one frame")
            frame_width, frame_height = self._frame_shape(frame)
            if (frame_width, frame_height) != (self.width_px, self.height_px):
                raise ResolutionMismatchError(
                    "USB frame resolution drifted from the configured mode: "
                    f"{frame_width}x{frame_height} != {self.width_px}x{self.height_px}"
                )

            imencode = getattr(self._cv2, "imencode", None)
            if not callable(imencode):
                raise CameraCaptureError("OpenCV module does not provide imencode")
            quality_property = getattr(self._cv2, "IMWRITE_JPEG_QUALITY", None)
            try:
                if isinstance(quality_property, int) and not isinstance(quality_property, bool):
                    encoded_ok, encoded = imencode(
                        ".jpg", frame, [quality_property, self.jpeg_quality]
                    )
                else:
                    encoded_ok, encoded = imencode(".jpg", frame)
            except Exception as exc:
                raise CameraCaptureError("OpenCV JPEG encoding failed") from exc
            complete_ns = self._clock_ns()
            if encoded_ok is not True or encoded is None:
                raise CameraCaptureError("OpenCV did not encode the captured frame")
            try:
                jpeg_bytes = encoded.tobytes() if hasattr(encoded, "tobytes") else bytes(encoded)
            except Exception as exc:
                raise CameraCaptureError("OpenCV returned an invalid encoded frame") from exc
            if len(jpeg_bytes) > self.max_jpeg_bytes:
                raise FrameLimitError(
                    f"Encoded USB frame exceeds {self.max_jpeg_bytes} bytes"
                )
            encoded_width, encoded_height = jpeg_dimensions(jpeg_bytes)
            if (encoded_width, encoded_height) != (frame_width, frame_height):
                raise ResolutionMismatchError(
                    "OpenCV JPEG resolution differs from its decoded frame"
                )
            capture_id = self._capture_id_factory()
            if not isinstance(capture_id, str):
                raise CameraCaptureError("capture_id_factory must return text")
            return FramePacket(
                capture_id=capture_id,
                jpeg_bytes=jpeg_bytes,
                width_px=frame_width,
                height_px=frame_height,
                source_sequence=None,
                source_timestamp_ns=None,
                source_clock=None,
                host_request_ns=request_ns,
                host_first_byte_ns=first_byte_ns,
                host_complete_ns=complete_ns,
                settings_hash=self._settings_hash,
                timestamp_quality=TimestampQuality.HOST_RECEIPT,
                freshness_token=None,
                freshness_basis="opencv_read_host_bracket",
            )

    def close(self) -> None:
        """Release the capture without issuing any arm or camera-setting command."""

        with self._lock:
            capture = self._capture
            self._capture = None
            self._cv2 = None
            self._observed_identity = None
            if capture is not None:
                capture.release()
