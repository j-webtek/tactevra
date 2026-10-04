from __future__ import annotations

from collections import deque
from io import BytesIO
from pathlib import Path
import sys
import unittest


SOFTWARE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SOFTWARE_ROOT / "src"))

from rocell.vision import (  # noqa: E402
    CameraCaptureError,
    CameraConfigurationError,
    CameraHttpError,
    CameraNotOpenError,
    CameraOpenError,
    CameraProbeError,
    CameraSource,
    EspHttpCamera,
    FrameLimitError,
    MockCamera,
    ResolutionMismatchError,
    StaleFrameError,
    TimestampQuality,
    UsbOpenCvCamera,
    OPENCV_TOP_LEFT_BGR_ORIENTATION,
    verify_opencv_top_left_bgr_orientation,
    jpeg_dimensions,
)


def minimal_jpeg(width: int = 640, height: int = 480) -> bytes:
    # SOF0 with one component is sufficient for the boundary's structural
    # parser.  Pixel decoding is deliberately outside these dependency-free
    # tests and is performed by OpenCV in real USB capture.
    sof_payload = (
        b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    return b"\xff\xd8\xff\xc0" + (len(sof_payload) + 2).to_bytes(2, "big") + sof_payload + b"\xff\xd9"


class TickClock:
    def __init__(self, start: int = 100, step: int = 10) -> None:
        self.value = start - step
        self.step = step

    def __call__(self) -> int:
        self.value += self.step
        return self.value


class FakeFrame:
    def __init__(self, width: int = 640, height: int = 480, channels: int = 3) -> None:
        self.shape = (height, width, channels)


class OrientationPatternFrame:
    def __init__(self, labels: tuple[str, str, str, str], *, rgb_storage: bool = False) -> None:
        self.shape = (40, 60, 3)
        self._pixels = [[[0, 0, 0] for _ in range(60)] for _ in range(40)]
        colors = {
            "BLUE": (255, 0, 0),
            "GREEN": (0, 255, 0),
            "RED": (0, 0, 255),
            "YELLOW": (0, 255, 255),
        }
        for (x_fraction, y_fraction), label in zip(
            ((0.20, 0.20), (0.80, 0.20), (0.20, 0.80), (0.80, 0.80)),
            labels,
        ):
            center_x = round((self.shape[1] - 1) * x_fraction)
            center_y = round((self.shape[0] - 1) * y_fraction)
            color = colors[label]
            if rgb_storage:
                color = tuple(reversed(color))
            for y in range(center_y - 1, center_y + 2):
                for x in range(center_x - 1, center_x + 2):
                    self._pixels[y][x] = list(color)

    def __getitem__(self, key: tuple[int, int]) -> list[int]:
        y, x = key
        return self._pixels[y][x]


class FakeEncoded:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def tobytes(self) -> bytes:
        return self.payload


class FakeVideoCapture:
    def __init__(
        self,
        reads: list[tuple[bool, object | None]] | None = None,
        *,
        width: float = 640,
        height: float = 480,
        fps: float = 30,
        pixel_format: str = "YUY2",
        honor_sets: bool = True,
        initially_open: bool = True,
    ) -> None:
        self.opened = initially_open
        self.reads = deque(reads or [(True, FakeFrame())])
        self.properties = {
            3: width,
            4: height,
            5: fps,
            6: float(
                sum(ord(character) << (8 * index) for index, character in enumerate(pixel_format))
            ),
        }
        self.honor_sets = honor_sets
        self.set_calls: list[tuple[int, float]] = []
        self.read_count = 0
        self.release_count = 0

    def isOpened(self) -> bool:
        return self.opened

    def set(self, property_id: int, value: float) -> bool:
        self.set_calls.append((property_id, value))
        if self.honor_sets:
            self.properties[property_id] = value
        return self.honor_sets

    def get(self, property_id: int) -> float:
        return self.properties[property_id]

    def read(self) -> tuple[bool, object | None]:
        self.read_count += 1
        if not self.reads:
            return False, None
        return self.reads.popleft()

    def release(self) -> None:
        self.release_count += 1
        self.opened = False


class FakeCv2:
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_PROP_FPS = 5
    CAP_PROP_FOURCC = 6
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self, capture: FakeVideoCapture) -> None:
        self.capture = capture
        self.video_capture_args: list[tuple[object, ...]] = []
        self.encode_calls: list[tuple[str, object, object]] = []
        self.encode_ok = True

    def VideoCapture(self, *args: object) -> FakeVideoCapture:
        self.video_capture_args.append(args)
        return self.capture

    @staticmethod
    def VideoWriter_fourcc(*characters: str) -> int:
        if len(characters) != 4:
            raise ValueError("FOURCC requires four characters")
        return sum(
            ord(character) << (8 * index)
            for index, character in enumerate(characters)
        )

    def imencode(
        self, suffix: str, frame: object, parameters: object = None
    ) -> tuple[bool, FakeEncoded | None]:
        self.encode_calls.append((suffix, frame, parameters))
        if not self.encode_ok:
            return False, None
        height, width = frame.shape[:2]
        return True, FakeEncoded(minimal_jpeg(width, height))


class FakeHttpResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str,
        headers: dict[str, str] | None = None,
        status: int = 200,
        final_url: str | None = None,
        ignore_read_limit: bool = False,
    ) -> None:
        self._stream = BytesIO(body)
        self._body = body
        self.status = status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.final_url = final_url
        self.request_url: str | None = None
        self.closed = False
        self.ignore_read_limit = ignore_read_limit

    def geturl(self) -> str:
        return self.final_url or self.request_url or ""

    def read(self, maximum: int = -1) -> bytes:
        if self.ignore_read_limit and maximum >= 0:
            return self._stream.read()
        return self._stream.read(maximum)

    def close(self) -> None:
        self.closed = True


class FakeUrlOpen:
    def __init__(self, responses: list[FakeHttpResponse | Exception]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[object, float]] = []

    def __call__(self, request: object, *, timeout: float) -> FakeHttpResponse:
        self.calls.append((request, timeout))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        response.request_url = request.full_url
        return response


class CameraRecordTests(unittest.TestCase):
    def test_jpeg_parser_rejects_non_jpeg_and_truncation(self) -> None:
        self.assertEqual(jpeg_dimensions(minimal_jpeg(320, 240)), (320, 240))
        with self.assertRaisesRegex(CameraCaptureError, "missing SOI"):
            jpeg_dimensions(b"<html>failure</html>")
        with self.assertRaisesRegex(CameraCaptureError, "missing EOI"):
            jpeg_dimensions(minimal_jpeg()[:-2])


class UsbOpenCvCameraTests(unittest.TestCase):
    def test_opencv_orientation_sentinel_accepts_top_left_bgr_pattern(self) -> None:
        frame = OrientationPatternFrame(("BLUE", "GREEN", "RED", "YELLOW"))

        result = verify_opencv_top_left_bgr_orientation(frame)

        self.assertEqual(result, OPENCV_TOP_LEFT_BGR_ORIENTATION)

    def test_opencv_orientation_sentinel_rejects_vertical_flip(self) -> None:
        frame = OrientationPatternFrame(("RED", "YELLOW", "BLUE", "GREEN"))

        with self.assertRaisesRegex(CameraProbeError, "vertical flip"):
            verify_opencv_top_left_bgr_orientation(frame)

    def test_opencv_orientation_sentinel_rejects_horizontal_mirror(self) -> None:
        frame = OrientationPatternFrame(("GREEN", "BLUE", "YELLOW", "RED"))

        with self.assertRaisesRegex(CameraProbeError, "horizontal mirror"):
            verify_opencv_top_left_bgr_orientation(frame)

    def test_opencv_orientation_sentinel_rejects_rotation(self) -> None:
        frame = OrientationPatternFrame(("YELLOW", "RED", "GREEN", "BLUE"))

        with self.assertRaisesRegex(CameraProbeError, "180-degree rotation"):
            verify_opencv_top_left_bgr_orientation(frame)

    def test_opencv_orientation_sentinel_rejects_rgb_channel_order(self) -> None:
        frame = OrientationPatternFrame(
            ("BLUE", "GREEN", "RED", "YELLOW"), rgb_storage=True
        )

        with self.assertRaisesRegex(CameraProbeError, "RGB/BGR channel swap"):
            verify_opencv_top_left_bgr_orientation(frame)

    def test_opencv_orientation_sentinel_rejects_malformed_frame(self) -> None:
        with self.assertRaisesRegex(CameraProbeError, "HxWx3"):
            verify_opencv_top_left_bgr_orientation(FakeFrame(width=8, height=8))

    def test_usb_adapter_is_lazy_then_probes_and_captures_one_frame(self) -> None:
        capture = FakeVideoCapture([(True, FakeFrame())])
        fake_cv2 = FakeCv2(capture)
        loader_count = 0

        def loader() -> FakeCv2:
            nonlocal loader_count
            loader_count += 1
            return fake_cv2

        camera = UsbOpenCvCamera(
            "/dev/v4l/by-id/usb-test",
            identity="usb:1234:5678:serial-1",
            width_px=640,
            height_px=480,
            fps=30,
            cv2_loader=loader,
            observed_identity_provider=lambda selector: "usb:1234:5678:serial-1",
            require_identity_match=True,
            clock_ns=TickClock(),
            capture_id_factory=lambda: "usb-capture-1",
        )
        self.assertIsInstance(camera, CameraSource)
        self.assertEqual(loader_count, 0)
        self.assertFalse(camera.is_open)
        with self.assertRaises(CameraNotOpenError):
            camera.capture()

        camera.open()
        self.assertEqual(loader_count, 1)
        self.assertEqual(fake_cv2.video_capture_args, [("/dev/v4l/by-id/usb-test",)])
        status = camera.probe()
        self.assertEqual(status.backend, "usb_opencv")
        self.assertEqual(status.identity, "usb:1234:5678:serial-1")
        self.assertTrue(status.persistent_identity)
        self.assertEqual((status.width_px, status.height_px, status.fps), (640, 480, 30.0))

        packet = camera.capture()
        self.assertEqual(packet.capture_id, "usb-capture-1")
        self.assertEqual((packet.width_px, packet.height_px), (640, 480))
        self.assertEqual(
            (packet.host_request_ns, packet.host_first_byte_ns, packet.host_complete_ns),
            (100, 110, 120),
        )
        self.assertIsNone(packet.source_timestamp_ns)
        self.assertEqual(packet.timestamp_quality, TimestampQuality.HOST_RECEIPT)
        self.assertEqual(packet.freshness_basis, "opencv_read_host_bracket")
        self.assertEqual(capture.read_count, 1)
        self.assertEqual(len(fake_cv2.encode_calls), 1)
        camera.close()
        self.assertEqual(capture.release_count, 1)
        self.assertFalse(camera.is_open)

    def test_usb_expected_identity_is_not_misreported_as_observed_evidence(self) -> None:
        capture = FakeVideoCapture()
        camera = UsbOpenCvCamera(
            "/dev/v4l/by-id/usb-test",
            identity="expected-serial",
            cv2_loader=lambda: FakeCv2(capture),
        )

        camera.open()
        status = camera.probe()

        self.assertFalse(status.persistent_identity)
        self.assertEqual(status.identity, "expected-serial")
        self.assertIn(("observed_identity", "UNOBSERVED"), status.details)
        camera.close()

    def test_usb_identity_mismatch_fails_open_and_releases_capture(self) -> None:
        capture = FakeVideoCapture()
        camera = UsbOpenCvCamera(
            "/dev/v4l/by-id/usb-test",
            identity="expected-serial",
            observed_identity_provider=lambda selector: "different-serial",
            require_identity_match=True,
            cv2_loader=lambda: FakeCv2(capture),
        )

        with self.assertRaisesRegex(CameraOpenError, "does not match"):
            camera.open()

        self.assertEqual(capture.release_count, 1)
        self.assertFalse(camera.is_open)

    def test_usb_mode_mismatch_fails_open_and_releases_capture(self) -> None:
        capture = FakeVideoCapture(width=800, honor_sets=False)
        camera = UsbOpenCvCamera(
            0,
            width_px=640,
            height_px=480,
            fps=30,
            cv2_loader=lambda: FakeCv2(capture),
        )
        with self.assertRaisesRegex(CameraProbeError, "width"):
            camera.open()
        self.assertEqual(capture.release_count, 1)
        self.assertFalse(camera.is_open)

    def test_usb_requests_and_verifies_exact_pixel_format(self) -> None:
        capture = FakeVideoCapture()
        camera = UsbOpenCvCamera(
            0,
            pixel_format="YUY2",
            cv2_loader=lambda: FakeCv2(capture),
        )

        camera.open()
        status = camera.probe()

        fourcc = FakeCv2.VideoWriter_fourcc("Y", "U", "Y", "2")
        self.assertIn((FakeCv2.CAP_PROP_FOURCC, float(fourcc)), capture.set_calls)
        self.assertIn(("configured_pixel_format", "YUY2"), status.details)
        self.assertIn(("observed_pixel_format", "YUY2"), status.details)
        camera.close()

    def test_usb_accepts_video4linux_yuyv_alias_for_vendor_yuy2(self) -> None:
        capture = FakeVideoCapture(pixel_format="YUYV", honor_sets=False)
        camera = UsbOpenCvCamera(
            0,
            pixel_format="YUY2",
            cv2_loader=lambda: FakeCv2(capture),
        )

        camera.open()
        status = camera.probe()

        self.assertIn(("observed_pixel_format", "YUYV"), status.details)
        camera.close()

    def test_usb_pixel_format_mismatch_fails_open_and_releases_capture(self) -> None:
        capture = FakeVideoCapture(pixel_format="YUY2", honor_sets=False)
        camera = UsbOpenCvCamera(
            0,
            pixel_format="MJPG",
            cv2_loader=lambda: FakeCv2(capture),
        )

        with self.assertRaisesRegex(CameraProbeError, "pixel format"):
            camera.open()

        self.assertEqual(capture.release_count, 1)
        self.assertFalse(camera.is_open)

    def test_usb_rejects_malformed_pixel_format_before_importing_opencv(self) -> None:
        with self.assertRaisesRegex(CameraConfigurationError, "pixel_format"):
            UsbOpenCvCamera(0, pixel_format="YUY2 ")

    def test_usb_failed_read_is_not_retried_or_reopened(self) -> None:
        capture = FakeVideoCapture([(False, None), (True, FakeFrame())])
        fake_cv2 = FakeCv2(capture)
        loader_count = 0

        def loader() -> FakeCv2:
            nonlocal loader_count
            loader_count += 1
            return fake_cv2

        camera = UsbOpenCvCamera(0, cv2_loader=loader)
        camera.open()
        with self.assertRaisesRegex(CameraCaptureError, "did not return"):
            camera.capture()
        self.assertEqual(capture.read_count, 1)
        self.assertEqual(loader_count, 1)
        self.assertTrue(camera.is_open)

    def test_usb_rejects_invalid_selector_and_capture_resolution_drift(self) -> None:
        with self.assertRaises(CameraConfigurationError):
            UsbOpenCvCamera(True)
        with self.assertRaises(CameraConfigurationError):
            UsbOpenCvCamera(-1)
        capture = FakeVideoCapture([(True, FakeFrame(width=320, height=240))])
        camera = UsbOpenCvCamera(0, cv2_loader=lambda: FakeCv2(capture))
        camera.open()
        with self.assertRaises(ResolutionMismatchError):
            camera.capture()
        self.assertEqual(capture.read_count, 1)


class EspHttpCameraTests(unittest.TestCase):
    @staticmethod
    def _camera_for_capture_headers(
        header_sets: list[dict[str, str]],
    ) -> tuple[EspHttpCamera, FakeUrlOpen]:
        jpeg = minimal_jpeg()
        responses = [
            FakeHttpResponse(
                jpeg,
                content_type="image/jpeg",
                headers={"Content-Length": str(len(jpeg)), **headers},
            )
            for headers in header_sets
        ]
        fake_open = FakeUrlOpen(responses)
        camera = EspHttpCamera(
            "http://192.0.2.20",
            identity="esp-freshness-adversarial",
            status_path=None,
            expected_width_px=640,
            expected_height_px=480,
            source_sequence_header="X-Sequence",
            urlopen=fake_open,
            clock_ns=TickClock(),
        )
        camera.open()
        return camera, fake_open

    def test_esp_probe_and_capture_are_read_only_bounded_requests(self) -> None:
        status_body = b'{"framesize":5,"quality":10}'
        status_response = FakeHttpResponse(
            status_body,
            content_type="application/json",
            headers={"Content-Length": str(len(status_body))},
        )
        jpeg = minimal_jpeg(640, 480)
        capture_response = FakeHttpResponse(
            jpeg,
            content_type="image/jpeg",
            headers={
                "Content-Length": str(len(jpeg)),
                "X-Timestamp": "12.000000001",
                "X-Sequence": "41",
                "ETag": '"frame-41"',
                "Age": "0",
            },
        )
        fake_open = FakeUrlOpen([status_response, capture_response])
        camera = EspHttpCamera(
            "http://192.0.2.10",
            identity="esp32-cam-mac:001122334455",
            expected_width_px=640,
            expected_height_px=480,
            source_sequence_header="X-Sequence",
            urlopen=fake_open,
            clock_ns=TickClock(start=1_000, step=10),
            capture_id_factory=lambda: "esp-capture-1",
        )
        self.assertIsInstance(camera, CameraSource)
        self.assertEqual(fake_open.calls, [])
        with self.assertRaises(CameraNotOpenError):
            camera.capture()
        camera.open()
        self.assertEqual(fake_open.calls, [])

        status = camera.probe()
        self.assertEqual(status.backend, "esp_http_snapshot")
        self.assertEqual(dict(status.details), {"framesize": "5", "quality": "10"})
        frame = camera.capture()
        self.assertEqual(frame.capture_id, "esp-capture-1")
        self.assertEqual(frame.source_sequence, 41)
        self.assertEqual(frame.source_timestamp_ns, 12_000_000_001)
        self.assertEqual(frame.source_clock, "esp_camera_device_local")
        self.assertEqual(frame.timestamp_quality, TimestampQuality.DEVICE_EXPOSURE)
        self.assertEqual(frame.freshness_basis, "device_sequence")
        self.assertEqual(len(fake_open.calls), 2)

        for request, timeout in fake_open.calls:
            self.assertEqual(request.method, "GET")
            self.assertEqual(timeout, 2.0)
            self.assertIn("rocell_nonce=", request.full_url)
            headers = {key.lower(): value for key, value in request.header_items()}
            self.assertIn("no-cache", headers["cache-control"])
            self.assertNotIn("/control", request.full_url)
        self.assertIn("/status?", fake_open.calls[0][0].full_url)
        self.assertIn("/capture?", fake_open.calls[1][0].full_url)
        self.assertTrue(status_response.closed)
        self.assertTrue(capture_response.closed)

    def test_esp_rejects_repeated_device_timestamp_without_retry(self) -> None:
        jpeg = minimal_jpeg()
        responses = [
            FakeHttpResponse(
                jpeg,
                content_type="image/jpeg",
                headers={"X-Timestamp": "1.25", "Content-Length": str(len(jpeg))},
            ),
            FakeHttpResponse(
                jpeg,
                content_type="image/jpeg",
                headers={"X-Timestamp": "1.25", "Content-Length": str(len(jpeg))},
            ),
        ]
        fake_open = FakeUrlOpen(responses)
        camera = EspHttpCamera(
            "http://192.0.2.11",
            identity="esp-test",
            status_path=None,
            expected_width_px=640,
            expected_height_px=480,
            freshness_token_header=None,
            urlopen=fake_open,
            clock_ns=TickClock(),
        )
        camera.open()
        camera.capture()
        with self.assertRaisesRegex(StaleFrameError, "timestamp did not advance"):
            camera.capture()
        self.assertEqual(len(fake_open.calls), 2)

    def test_esp_checks_every_available_freshness_signal(self) -> None:
        baseline = {
            "X-Sequence": "10",
            "X-Timestamp": "1.000000000",
            "ETag": '"frame-10"',
        }
        contradictions = (
            (
                {
                    "X-Sequence": "11",
                    "X-Timestamp": "1.000000000",
                    "ETag": '"frame-11"',
                },
                "timestamp did not advance",
            ),
            (
                {
                    "X-Sequence": "10",
                    "X-Timestamp": "2.000000000",
                    "ETag": '"frame-11"',
                },
                "sequence did not advance",
            ),
            (
                {
                    "X-Sequence": "11",
                    "X-Timestamp": "2.000000000",
                    "ETag": '"frame-10"',
                },
                "freshness token did not change",
            ),
            (
                {
                    "X-Sequence": "9",
                    "X-Timestamp": "2.000000000",
                    "ETag": '"frame-11"',
                },
                "sequence did not advance",
            ),
            (
                {
                    "X-Sequence": "11",
                    "X-Timestamp": "0.999999999",
                    "ETag": '"frame-11"',
                },
                "timestamp did not advance",
            ),
        )
        for current_headers, message in contradictions:
            with self.subTest(message=message, headers=current_headers):
                camera, fake_open = self._camera_for_capture_headers(
                    [baseline, current_headers]
                )
                camera.capture()
                with self.assertRaisesRegex(StaleFrameError, message):
                    camera.capture()
                self.assertEqual(len(fake_open.calls), 2)

    def test_esp_rejects_disappearing_established_freshness_evidence(self) -> None:
        baseline = {
            "X-Sequence": "20",
            "X-Timestamp": "2.000000000",
            "ETag": '"frame-20"',
        }
        omissions = (
            (
                {
                    "X-Timestamp": "3.000000000",
                    "ETag": '"frame-21"',
                },
                "sequence evidence disappeared",
            ),
            (
                {"X-Sequence": "21", "ETag": '"frame-21"'},
                "timestamp evidence disappeared",
            ),
            (
                {"X-Sequence": "21", "X-Timestamp": "3.000000000"},
                "freshness token evidence disappeared",
            ),
        )
        for current_headers, message in omissions:
            with self.subTest(message=message):
                camera, _ = self._camera_for_capture_headers(
                    [baseline, current_headers]
                )
                camera.capture()
                with self.assertRaisesRegex(StaleFrameError, message):
                    camera.capture()

    def test_esp_optional_freshness_evidence_can_upgrade_but_not_downgrade(self) -> None:
        camera, fake_open = self._camera_for_capture_headers(
            [
                {},
                {
                    "X-Sequence": "30",
                    "X-Timestamp": "3.000000000",
                    "ETag": '"frame-30"',
                },
                {},
            ]
        )

        first = camera.capture()
        upgraded = camera.capture()
        self.assertIsNone(first.source_sequence)
        self.assertEqual(upgraded.source_sequence, 30)
        with self.assertRaisesRegex(StaleFrameError, "sequence evidence disappeared"):
            camera.capture()
        self.assertEqual(len(fake_open.calls), 3)

    def test_esp_rejects_exact_replay_and_keeps_last_accepted_frame(self) -> None:
        first = {
            "X-Sequence": "40",
            "X-Timestamp": "4.000000000",
            "ETag": '"frame-40"',
        }
        replay = dict(first)
        recovered = {
            "X-Sequence": "41",
            "X-Timestamp": "4.000000001",
            "ETag": '"frame-41"',
        }
        camera, _ = self._camera_for_capture_headers([first, replay, recovered])

        accepted = camera.capture()
        with self.assertRaisesRegex(StaleFrameError, "sequence did not advance"):
            camera.capture()
        # A rejected response must not become the comparison baseline.  This
        # next frame advances relative to the last frame actually accepted.
        next_accepted = camera.capture()
        self.assertEqual((accepted.source_sequence, next_accepted.source_sequence), (40, 41))

    def test_esp_rejects_nonadjacent_freshness_token_replay(self) -> None:
        camera, fake_open = self._camera_for_capture_headers(
            [
                {"ETag": '"token-a"'},
                {"ETag": '"token-b"'},
                {"ETag": '"token-a"'},
            ]
        )

        camera.capture()
        camera.capture()
        with self.assertRaisesRegex(StaleFrameError, "token was replayed"):
            camera.capture()
        self.assertEqual(len(fake_open.calls), 3)

    def test_esp_freshness_token_history_is_bounded_and_epoch_scoped(self) -> None:
        jpeg = minimal_jpeg()
        response_headers = (
            {"ETag": '"token-a"'},
            {"ETag": '"token-b"'},
            {"ETag": '"token-c"'},
            {"ETag": '"token-c"'},
        )
        fake_open = FakeUrlOpen(
            [
                FakeHttpResponse(jpeg, content_type="image/jpeg", headers=headers)
                for headers in response_headers
            ]
        )
        camera = EspHttpCamera(
            "http://192.0.2.22",
            identity="esp-token-bound",
            status_path=None,
            source_timestamp_header=None,
            max_freshness_tokens_per_epoch=2,
            urlopen=fake_open,
            clock_ns=TickClock(),
        )
        camera.open()
        camera.capture()
        camera.capture()
        with self.assertRaisesRegex(FrameLimitError, "history reached"):
            camera.capture()

        # Reopening is an explicit new epoch, so its first source token has no
        # predecessor and may start from any device value.
        camera.close()
        camera.open()
        reopened = camera.capture()
        self.assertEqual(reopened.freshness_token, '"token-c"')

    def test_esp_rejects_cached_frame_before_accepting_body(self) -> None:
        jpeg = minimal_jpeg()
        response = FakeHttpResponse(
            jpeg,
            content_type="image/jpeg",
            headers={"Age": "1", "Content-Length": str(len(jpeg))},
        )
        fake_open = FakeUrlOpen([response])
        camera = EspHttpCamera(
            "http://192.0.2.21",
            identity="esp-cache-replay",
            status_path=None,
            urlopen=fake_open,
            clock_ns=TickClock(),
        )
        camera.open()

        with self.assertRaisesRegex(StaleFrameError, "served from a cache"):
            camera.capture()
        self.assertEqual(len(fake_open.calls), 1)
        self.assertTrue(response.closed)

    def test_esp_probe_uses_one_snapshot_when_status_endpoint_is_absent(self) -> None:
        jpeg = minimal_jpeg(320, 240)
        fake_open = FakeUrlOpen([FakeHttpResponse(jpeg, content_type="image/jpeg")])
        camera = EspHttpCamera(
            "http://192.0.2.15",
            identity="esp-snapshot-probe",
            status_path=None,
            expected_width_px=320,
            expected_height_px=240,
            urlopen=fake_open,
            clock_ns=TickClock(),
        )
        camera.open()
        status = camera.probe()
        self.assertEqual((status.width_px, status.height_px), (320, 240))
        self.assertEqual(dict(status.details), {"probe_method": "snapshot"})
        self.assertEqual(len(fake_open.calls), 1)
        self.assertIn("/capture?", fake_open.calls[0][0].full_url)

    def test_identical_pixels_without_source_evidence_are_not_called_stale(self) -> None:
        jpeg = minimal_jpeg()
        fake_open = FakeUrlOpen(
            [
                FakeHttpResponse(jpeg, content_type="image/jpeg"),
                FakeHttpResponse(jpeg, content_type="image/jpeg"),
            ]
        )
        camera = EspHttpCamera(
            "http://192.0.2.12",
            identity="esp-no-source-clock",
            status_path=None,
            source_timestamp_header=None,
            freshness_token_header=None,
            urlopen=fake_open,
            clock_ns=TickClock(),
        )
        camera.open()
        first = camera.capture()
        second = camera.capture()
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(second.timestamp_quality, TimestampQuality.HOST_RECEIPT)
        self.assertEqual(second.freshness_basis, "nonce_and_host_request_receipt")

    def test_esp_strict_content_length_type_redirect_and_resolution_limits(self) -> None:
        jpeg = minimal_jpeg()
        cases = (
            (
                FakeHttpResponse(b"<html>no</html>", content_type="text/html"),
                CameraHttpError,
            ),
            (
                FakeHttpResponse(
                    jpeg,
                    content_type="image/jpeg",
                    headers={"Content-Length": "9999"},
                ),
                FrameLimitError,
            ),
            (
                FakeHttpResponse(jpeg[:-2], content_type="image/jpeg"),
                CameraCaptureError,
            ),
            (
                FakeHttpResponse(
                    jpeg,
                    content_type="image/jpeg",
                    final_url="http://192.0.2.99/capture",
                ),
                CameraHttpError,
            ),
        )
        for response, expected_error in cases:
            with self.subTest(error=expected_error.__name__):
                fake_open = FakeUrlOpen([response])
                camera = EspHttpCamera(
                    "http://192.0.2.13",
                    identity="esp-limits",
                    status_path=None,
                    max_frame_bytes=1024,
                    urlopen=fake_open,
                )
                camera.open()
                with self.assertRaises(expected_error):
                    camera.capture()
                self.assertEqual(len(fake_open.calls), 1)
                self.assertTrue(response.closed)

        mismatch_response = FakeHttpResponse(jpeg, content_type="image/jpeg")
        mismatch = EspHttpCamera(
            "http://192.0.2.14",
            identity="esp-resolution",
            status_path=None,
            expected_width_px=320,
            expected_height_px=240,
            urlopen=FakeUrlOpen([mismatch_response]),
        )
        mismatch.open()
        with self.assertRaises(ResolutionMismatchError):
            mismatch.capture()

    def test_esp_configuration_rejects_ambiguous_or_credentialed_urls(self) -> None:
        for invalid_url in (
            "192.0.2.1",
            "ftp://192.0.2.1",
            "http://user:pass@192.0.2.1",
            "http://192.0.2.1/#fragment",
        ):
            with self.subTest(url=invalid_url):
                with self.assertRaises(CameraConfigurationError):
                    EspHttpCamera(invalid_url, identity="esp")
        with self.assertRaises(CameraConfigurationError):
            EspHttpCamera("http://192.0.2.1", identity="esp", snapshot_path="capture")


class MockCameraTests(unittest.TestCase):
    def test_mock_is_explicit_deterministic_and_allows_static_frames(self) -> None:
        jpeg = minimal_jpeg(320, 240)
        camera = MockCamera(
            [jpeg, jpeg],
            clock_ns=TickClock(),
            identity="mock-static",
        )
        self.assertIsInstance(camera, CameraSource)
        with self.assertRaises(CameraNotOpenError):
            camera.probe()
        camera.open()
        self.assertEqual((camera.probe().width_px, camera.probe().height_px), (320, 240))
        first = camera.capture()
        second = camera.capture()
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual((first.capture_id, second.capture_id), ("mock-static:1", "mock-static:2"))
        self.assertEqual(camera.pending_frame_count, 0)
        with self.assertRaises(CameraCaptureError):
            camera.capture()
        camera.close()
        self.assertFalse(camera.is_open)


if __name__ == "__main__":
    unittest.main()
