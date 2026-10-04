"""Bounded HTTP snapshot adapter for a separately identified ESP camera.

This adapter never sends RoArm commands and never writes ESP camera settings.
It supports the read-only ``/status`` and ``/capture`` shape used by
Espressif's CameraWebServer example while keeping paths and header names
configurable for other firmware.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
from threading import RLock
import time
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
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
    StaleFrameError,
    TimestampQuality,
    jpeg_dimensions,
    positive_finite,
    positive_int,
    settings_digest,
)


class CameraHttpError(CameraCaptureError):
    """An ESP snapshot/status HTTP exchange failed without retry."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


_NO_REDIRECT_OPENER = build_opener(_NoRedirectHandler())


def _validate_text(name: str, value: object, *, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise CameraConfigurationError(f"{name} must be non-empty text")
    parsed = value.strip()
    if len(parsed) > maximum:
        raise CameraConfigurationError(f"{name} is too long")
    return parsed


def _validate_base_url(value: object) -> tuple[str, str]:
    text = _validate_text("base_url", value, maximum=4096).rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme not in ("http", "https"):
        raise CameraConfigurationError("base_url must use explicit http or https")
    if not parsed.hostname:
        raise CameraConfigurationError("base_url must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise CameraConfigurationError("base_url must not contain credentials")
    if parsed.query or parsed.fragment:
        raise CameraConfigurationError("base_url must not contain a query or fragment")
    try:
        parsed.port
    except ValueError as exc:
        raise CameraConfigurationError("base_url contains an invalid port") from exc
    normalized_path = parsed.path.rstrip("/")
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return origin, normalized_path


def _validate_endpoint(name: str, value: object, *, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    text = _validate_text(name, value, maximum=2048)
    parsed = urlsplit(text)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise CameraConfigurationError(f"{name} must be a path without query or fragment")
    if not parsed.path.startswith("/"):
        raise CameraConfigurationError(f"{name} must start with /")
    segments = [unquote(segment) for segment in parsed.path.split("/")]
    if any(segment in (".", "..") for segment in segments):
        raise CameraConfigurationError(f"{name} must not contain dot path segments")
    return parsed.path


def _header(headers: Any, name: str) -> str | None:
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is None:
            # Plain dictionaries used by deterministic fakes may be
            # case-sensitive, unlike real HTTPMessage instances.
            for key, candidate in getattr(headers, "items", lambda: ())():
                if str(key).lower() == name.lower():
                    value = candidate
                    break
        if value is not None:
            return str(value).strip()
    return None


def _json_without_duplicates(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CameraProbeError(f"ESP status contains duplicate field {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise CameraProbeError(f"ESP status contains nonfinite constant {value!r}")


class EspHttpCamera:
    """Read-only, one-request ESP JPEG snapshot source.

    ``X-Timestamp`` from Espressif's example is retained as device-local time.
    It is never relabeled as host monotonic time and therefore does not, by
    itself, synchronize a frame to RoArm feedback.
    """

    def __init__(
        self,
        base_url: str,
        *,
        identity: str,
        snapshot_path: str = "/capture",
        status_path: str | None = "/status",
        timeout_s: float = 2.0,
        max_capture_duration_s: float = 2.0,
        max_frame_bytes: int = 4 * 1024 * 1024,
        max_status_bytes: int = 64 * 1024,
        expected_width_px: int | None = None,
        expected_height_px: int | None = None,
        max_width_px: int = 8192,
        max_height_px: int = 8192,
        max_pixels: int = 40_000_000,
        max_freshness_tokens_per_epoch: int = 4096,
        source_timestamp_header: str | None = "X-Timestamp",
        source_sequence_header: str | None = None,
        freshness_token_header: str | None = "ETag",
        reject_cached_age: bool = True,
        urlopen: Callable[..., Any] | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
        capture_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._origin, self._base_path = _validate_base_url(base_url)
        self.identity = _validate_text("identity", identity)
        validated_snapshot_path = _validate_endpoint("snapshot_path", snapshot_path)
        assert validated_snapshot_path is not None
        self.snapshot_path = validated_snapshot_path
        self.status_path = _validate_endpoint("status_path", status_path, allow_none=True)
        self.timeout_s = positive_finite("timeout_s", timeout_s)
        self.max_capture_duration_s = positive_finite(
            "max_capture_duration_s", max_capture_duration_s
        )
        self.max_frame_bytes = positive_int("max_frame_bytes", max_frame_bytes)
        self.max_status_bytes = positive_int("max_status_bytes", max_status_bytes)
        if (expected_width_px is None) != (expected_height_px is None):
            raise CameraConfigurationError(
                "expected_width_px and expected_height_px must be set together"
            )
        self.expected_width_px = (
            positive_int("expected_width_px", expected_width_px)
            if expected_width_px is not None
            else None
        )
        self.expected_height_px = (
            positive_int("expected_height_px", expected_height_px)
            if expected_height_px is not None
            else None
        )
        self.max_width_px = positive_int("max_width_px", max_width_px)
        self.max_height_px = positive_int("max_height_px", max_height_px)
        self.max_pixels = positive_int("max_pixels", max_pixels)
        self.max_freshness_tokens_per_epoch = positive_int(
            "max_freshness_tokens_per_epoch", max_freshness_tokens_per_epoch
        )
        if self.expected_width_px is not None:
            assert self.expected_height_px is not None
            self._validate_resolution(self.expected_width_px, self.expected_height_px)
        self.source_timestamp_header = self._optional_header_name(
            "source_timestamp_header", source_timestamp_header
        )
        self.source_sequence_header = self._optional_header_name(
            "source_sequence_header", source_sequence_header
        )
        self.freshness_token_header = self._optional_header_name(
            "freshness_token_header", freshness_token_header
        )
        if not isinstance(reject_cached_age, bool):
            raise CameraConfigurationError("reject_cached_age must be boolean")
        self.reject_cached_age = reject_cached_age
        if urlopen is not None and not callable(urlopen):
            raise CameraConfigurationError("urlopen must be callable")
        if not callable(clock_ns):
            raise CameraConfigurationError("clock_ns must be callable")
        if capture_id_factory is not None and not callable(capture_id_factory):
            raise CameraConfigurationError("capture_id_factory must be callable")
        self._urlopen = urlopen or _NO_REDIRECT_OPENER.open
        self._clock_ns = clock_ns
        self._capture_id_factory = capture_id_factory or (lambda: uuid.uuid4().hex)
        self._is_open = False
        self._request_sequence = 0
        self._last_frame: FramePacket | None = None
        self._seen_freshness_tokens: set[str] = set()
        self._lock = RLock()
        self._settings_hash = settings_digest(
            {
                "backend": "esp_http_snapshot",
                "origin": self._origin,
                "base_path": self._base_path,
                "identity": self.identity,
                "snapshot_path": self.snapshot_path,
                "status_path": self.status_path,
                "expected_width_px": self.expected_width_px,
                "expected_height_px": self.expected_height_px,
                "max_freshness_tokens_per_epoch": self.max_freshness_tokens_per_epoch,
                "source_timestamp_header": self.source_timestamp_header,
                "source_sequence_header": self.source_sequence_header,
                "freshness_token_header": self.freshness_token_header,
            }
        )

    @staticmethod
    def _optional_header_name(name: str, value: object) -> str | None:
        if value is None:
            return None
        parsed = _validate_text(name, value, maximum=128)
        if any(character in parsed for character in "\r\n:"):
            raise CameraConfigurationError(f"{name} is not a valid HTTP header name")
        return parsed

    @property
    def base_url(self) -> str:
        return self._origin + self._base_path

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        """Enable explicit I/O; opening itself performs no network request."""

        with self._lock:
            if self._is_open:
                raise CameraStateError("ESP camera is already open")
            self._is_open = True
            self._last_frame = None
            self._seen_freshness_tokens.clear()

    def connect(self) -> None:
        self.open()

    def _require_open(self) -> None:
        if not self._is_open:
            raise CameraNotOpenError("ESP camera is not explicitly open")

    def _request_url(self, endpoint: str, request_ns: int) -> str:
        self._request_sequence += 1
        path = self._base_path + endpoint
        nonce = f"{self._request_sequence}-{request_ns}"
        return urlunsplit(
            (
                urlsplit(self._origin).scheme,
                urlsplit(self._origin).netloc,
                quote(unquote(path), safe="/%:@"),
                f"rocell_nonce={quote(nonce, safe='')}",
                "",
            )
        )

    @staticmethod
    def _response_status(response: Any) -> int:
        status = getattr(response, "status", None)
        if status is None:
            getter = getattr(response, "getcode", None)
            status = getter() if callable(getter) else None
        if isinstance(status, bool) or not isinstance(status, int):
            raise CameraHttpError("ESP HTTP response did not provide an integer status")
        return status

    @staticmethod
    def _close_response(response: Any) -> None:
        closer = getattr(response, "close", None)
        if callable(closer):
            closer()

    @staticmethod
    def _set_response_timeout(response: Any, remaining_s: float) -> None:
        # urllib's HTTPResponse wraps a buffered SocketIO. A socket timeout is
        # per recv, so reset it to the shrinking total budget before each read.
        socket = getattr(getattr(getattr(response, "fp", None), "raw", None),
                         "_sock", None)
        if socket is not None:
            socket.settimeout(remaining_s)

    def _fetch(
        self,
        endpoint: str,
        *,
        request_ns: int,
        maximum_bytes: int,
        accepted_content_types: tuple[str, ...],
    ) -> tuple[bytes, int, int, Any]:
        request_url = self._request_url(endpoint, request_ns)
        request = Request(
            request_url,
            headers={
                "Accept": ", ".join(accepted_content_types),
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
                "Connection": "close",
                "User-Agent": "rocell-camera/1",
            },
            method="GET",
        )
        response: Any = None
        try:
            deadline_ns = request_ns + int(self.max_capture_duration_s * 1e9)
            response = self._urlopen(
                request, timeout=min(self.timeout_s, self.max_capture_duration_s))
            if self._response_status(response) != 200:
                raise CameraHttpError("ESP HTTP endpoint did not return status 200")
            final_url_getter = getattr(response, "geturl", None)
            final_url = final_url_getter() if callable(final_url_getter) else request_url
            if final_url != request_url:
                raise CameraHttpError("ESP HTTP redirects are prohibited")

            headers = getattr(response, "headers", {})
            content_type = _header(headers, "Content-Type")
            if content_type is None:
                raise CameraHttpError("ESP HTTP response is missing Content-Type")
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type not in accepted_content_types:
                raise CameraHttpError(
                    f"ESP HTTP response has unsupported Content-Type {media_type!r}"
                )

            content_length_text = _header(headers, "Content-Length")
            content_length: int | None = None
            if content_length_text is not None:
                try:
                    content_length = int(content_length_text, 10)
                except ValueError as exc:
                    raise CameraHttpError("ESP HTTP Content-Length is invalid") from exc
                if content_length < 0:
                    raise CameraHttpError("ESP HTTP Content-Length is negative")
                if content_length > maximum_bytes:
                    raise FrameLimitError(
                        f"ESP HTTP response exceeds {maximum_bytes} bytes"
                    )

            if self.reject_cached_age:
                age_text = _header(headers, "Age")
                if age_text is not None:
                    try:
                        age = int(age_text, 10)
                    except ValueError as exc:
                        raise CameraHttpError("ESP HTTP Age header is invalid") from exc
                    if age > 0:
                        raise StaleFrameError("ESP HTTP response was served from a cache")
                    if age < 0:
                        raise CameraHttpError("ESP HTTP Age header is negative")

            chunks: list[bytes] = []
            total = 0
            first_byte_ns: int | None = None
            reader = getattr(response, "read1", None)
            if not callable(reader):
                reader = response.read
            while total <= maximum_bytes:
                remaining_ns = deadline_ns - self._clock_ns()
                if remaining_ns <= 0:
                    raise CameraHttpError("ESP HTTP response exceeded total duration")
                self._set_response_timeout(response, remaining_ns / 1e9)
                chunk = reader(min(64 * 1024, maximum_bytes + 1 - total))
                received_ns = self._clock_ns()
                if received_ns > deadline_ns:
                    raise CameraHttpError("ESP HTTP response exceeded total duration")
                if not isinstance(chunk, bytes):
                    raise CameraHttpError("ESP HTTP response body is not bytes")
                if not chunk:
                    break
                if first_byte_ns is None:
                    first_byte_ns = received_ns
                chunks.append(chunk)
                total += len(chunk)
            if first_byte_ns is None:
                raise CameraHttpError("ESP HTTP response body is empty")
            payload = b"".join(chunks)
            complete_ns = self._clock_ns()
            if len(payload) > maximum_bytes:
                raise FrameLimitError(
                    f"ESP HTTP response exceeds {maximum_bytes} bytes"
                )
            if content_length is not None and len(payload) != content_length:
                raise CameraHttpError(
                    "ESP HTTP response length does not match Content-Length"
                )
            return payload, first_byte_ns, complete_ns, headers
        except (StaleFrameError, FrameLimitError, CameraHttpError):
            raise
        except HTTPError as exc:
            raise CameraHttpError(f"ESP HTTP request failed with status {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CameraHttpError("ESP HTTP request failed or timed out") from exc
        finally:
            if response is not None:
                self._close_response(response)

    def _validate_resolution(self, width: int, height: int) -> None:
        if width > self.max_width_px or height > self.max_height_px:
            raise FrameLimitError(
                f"ESP frame resolution {width}x{height} exceeds dimension limits"
            )
        if width * height > self.max_pixels:
            raise FrameLimitError(
                f"ESP frame resolution {width}x{height} exceeds pixel limit"
            )
        if self.expected_width_px is not None and (
            width != self.expected_width_px or height != self.expected_height_px
        ):
            raise ResolutionMismatchError(
                "ESP frame resolution drifted from the configured mode: "
                f"{width}x{height} != "
                f"{self.expected_width_px}x{self.expected_height_px}"
            )

    @staticmethod
    def _parse_source_timestamp(value: str) -> int:
        try:
            seconds = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise CameraCaptureError("ESP source timestamp header is invalid") from exc
        if not seconds.is_finite() or seconds < 0:
            raise CameraCaptureError("ESP source timestamp must be finite and nonnegative")
        nanoseconds = seconds * Decimal(1_000_000_000)
        integral = nanoseconds.to_integral_value()
        if nanoseconds != integral:
            raise CameraCaptureError(
                "ESP source timestamp has precision finer than nanoseconds"
            )
        return int(integral)

    @staticmethod
    def _parse_source_sequence(value: str) -> int:
        try:
            sequence = int(value, 10)
        except ValueError as exc:
            raise CameraCaptureError("ESP source sequence header is invalid") from exc
        if sequence < 0:
            raise CameraCaptureError("ESP source sequence must be nonnegative")
        return sequence

    def probe(self) -> CameraStatus:
        """Read status, or one fallback snapshot; never write camera settings."""

        with self._lock:
            self._require_open()
            details: list[tuple[str, str]] = []
            width = self.expected_width_px
            height = self.expected_height_px
            if self.status_path is not None:
                request_ns = self._clock_ns()
                payload, _, complete_ns, _ = self._fetch(
                    self.status_path,
                    request_ns=request_ns,
                    maximum_bytes=self.max_status_bytes,
                    accepted_content_types=("application/json", "text/json"),
                )
                if complete_ns - request_ns > int(self.max_capture_duration_s * 1e9):
                    raise CameraProbeError("ESP status response exceeded the duration limit")
                try:
                    status = json.loads(
                        payload.decode("utf-8"),
                        parse_constant=_reject_json_constant,
                        object_pairs_hook=_json_without_duplicates,
                    )
                except UnicodeDecodeError as exc:
                    raise CameraProbeError("ESP status is not UTF-8 JSON") from exc
                except json.JSONDecodeError as exc:
                    raise CameraProbeError("ESP status is not valid JSON") from exc
                if not isinstance(status, dict):
                    raise CameraProbeError("ESP status must be a JSON object")
                for key in ("framesize", "quality"):
                    if key in status:
                        details.append((key, str(status[key])[:128]))
            else:
                # Firmware without a status endpoint is still genuinely probed:
                # fetch and structurally validate one bounded snapshot, but do
                # not install it as the freshness predecessor for capture().
                request_ns = self._clock_ns()
                payload, _, complete_ns, _ = self._fetch(
                    self.snapshot_path,
                    request_ns=request_ns,
                    maximum_bytes=self.max_frame_bytes,
                    accepted_content_types=("image/jpeg",),
                )
                if complete_ns - request_ns > int(self.max_capture_duration_s * 1e9):
                    raise CameraProbeError("ESP snapshot probe exceeded the duration limit")
                width, height = jpeg_dimensions(payload)
                self._validate_resolution(width, height)
                details.append(("probe_method", "snapshot"))
            return CameraStatus(
                backend="esp_http_snapshot",
                identity=self.identity,
                is_open=True,
                width_px=width,
                height_px=height,
                fps=None,
                settings_hash=self._settings_hash,
                timestamp_quality=TimestampQuality.UNQUALIFIED,
                persistent_identity=True,
                details=tuple(details),
            )

    def capture(self) -> FramePacket:
        """Fetch one fresh snapshot with no retry, redirect, or setting write."""

        with self._lock:
            self._require_open()
            request_ns = self._clock_ns()
            payload, first_byte_ns, complete_ns, headers = self._fetch(
                self.snapshot_path,
                request_ns=request_ns,
                maximum_bytes=self.max_frame_bytes,
                accepted_content_types=("image/jpeg",),
            )
            if complete_ns - request_ns > int(self.max_capture_duration_s * 1e9):
                raise StaleFrameError("ESP snapshot exceeded the configured freshness duration")
            width, height = jpeg_dimensions(payload)
            self._validate_resolution(width, height)

            source_timestamp_ns: int | None = None
            source_clock: str | None = None
            if self.source_timestamp_header is not None:
                timestamp_text = _header(headers, self.source_timestamp_header)
                if timestamp_text is not None:
                    source_timestamp_ns = self._parse_source_timestamp(timestamp_text)
                    source_clock = "esp_camera_device_local"

            source_sequence: int | None = None
            if self.source_sequence_header is not None:
                sequence_text = _header(headers, self.source_sequence_header)
                if sequence_text is not None:
                    source_sequence = self._parse_source_sequence(sequence_text)

            freshness_token: str | None = None
            if self.freshness_token_header is not None:
                freshness_token = _header(headers, self.freshness_token_header)
                if freshness_token == "":
                    freshness_token = None

            if source_sequence is not None:
                freshness_basis = "device_sequence"
            elif source_timestamp_ns is not None:
                freshness_basis = "device_local_timestamp"
            elif freshness_token is not None:
                freshness_basis = "http_freshness_token"
            else:
                freshness_basis = "nonce_and_host_request_receipt"
            quality = (
                TimestampQuality.DEVICE_EXPOSURE
                if source_timestamp_ns is not None
                else TimestampQuality.HOST_RECEIPT
            )
            capture_id = self._capture_id_factory()
            if not isinstance(capture_id, str):
                raise CameraCaptureError("capture_id_factory must return text")
            frame = FramePacket(
                capture_id=capture_id,
                jpeg_bytes=payload,
                width_px=width,
                height_px=height,
                source_sequence=source_sequence,
                source_timestamp_ns=source_timestamp_ns,
                source_clock=source_clock,
                host_request_ns=request_ns,
                host_first_byte_ns=first_byte_ns,
                host_complete_ns=complete_ns,
                settings_hash=self._settings_hash,
                timestamp_quality=quality,
                freshness_token=freshness_token,
                freshness_basis=freshness_basis,
            )
            self.verify_fresh_frame(frame, self._last_frame)
            if freshness_token is not None:
                # Tokens are opaque, so ordering cannot be inferred.  Retain a
                # bounded epoch-wide set to catch A/B/A replay, not just an
                # immediately repeated A/A response.
                if freshness_token in self._seen_freshness_tokens:
                    raise StaleFrameError("ESP HTTP freshness token was replayed")
                if (
                    len(self._seen_freshness_tokens)
                    >= self.max_freshness_tokens_per_epoch
                ):
                    raise FrameLimitError(
                        "ESP HTTP freshness-token history reached its epoch limit"
                    )
                self._seen_freshness_tokens.add(freshness_token)
            self._last_frame = frame
            return frame

    @staticmethod
    def verify_fresh_frame(current: FramePacket, previous: FramePacket | None) -> None:
        """Fail closed when any established source freshness evidence regresses.

        Identical JPEG bytes in a static scene are not, alone, proof that a
        response is stale.  Without a device sequence/timestamp/token, the
        packet retains only a nonce plus host request/receipt bracket.

        Source signals are optional because supported ESP firmware variants do
        not all emit the same headers.  Once a signal appears in an open camera
        epoch, however, its later disappearance is a downgrade and is rejected.
        Every signal shared by two frames is checked; an advancing sequence
        must not mask a repeated timestamp or freshness token.
        """

        if previous is None:
            return
        if current.host_request_ns < previous.host_complete_ns:
            raise StaleFrameError("ESP capture host brackets overlap or moved backward")

        if previous.source_sequence is not None:
            if current.source_sequence is None:
                raise StaleFrameError("ESP source sequence evidence disappeared")
            if current.source_sequence <= previous.source_sequence:
                raise StaleFrameError("ESP source sequence did not advance")

        if previous.source_timestamp_ns is not None:
            if current.source_timestamp_ns is None:
                raise StaleFrameError("ESP device-local timestamp evidence disappeared")
            # Comparing values from different device clock domains would create
            # a false freshness claim even when both integers happen to advance.
            if current.source_clock != previous.source_clock:
                raise StaleFrameError("ESP device-local timestamp clock changed")
            if current.source_timestamp_ns <= previous.source_timestamp_ns:
                raise StaleFrameError("ESP device-local timestamp did not advance")

        if previous.freshness_token is not None:
            if current.freshness_token is None:
                raise StaleFrameError("ESP HTTP freshness token evidence disappeared")
            if current.freshness_token == previous.freshness_token:
                raise StaleFrameError("ESP HTTP freshness token did not change")

    def close(self) -> None:
        """Disable I/O and forget the previous device-local freshness epoch."""

        with self._lock:
            self._is_open = False
            self._last_frame = None
            self._seen_freshness_tokens.clear()
