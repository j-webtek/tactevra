"""One-open Win32 facade for an owned calibrated position-vector child.

Construction and status are inert.  The admitted instance can load kernel32
only after the exact binding, current runtime, process identity, and original
deadline reproduce.  Cleanup remains available after the deadline once the
process may own native resources.
"""

from __future__ import annotations

import os
import time
from threading import Lock

from .calibrated_position_vector_binding import CalibratedPositionVectorBinding
from .nonpurging_serial_api import (
    NativeSerialError,
    WindowsNativeSerialApi,
    _validate_com_path,
)


class WindowsCalibratedPositionVectorSerialApi(WindowsNativeSerialApi):
    __slots__ = (
        "_expected_path",
        "_binding",
        "_open_attempted",
        "_open_lock",
        "_clock_ns",
    )

    def __init__(self, port_name: str) -> None:
        if type(port_name) is not str:
            raise NativeSerialError("EXACT_COM_PATH_REQUIRED", "calibrated_construction")
        self._expected_path = "\\\\.\\" + port_name
        _validate_com_path(self._expected_path)
        super().__init__()
        self._binding = None
        self._open_attempted = False
        self._open_lock = Lock()
        self._clock_ns = time.monotonic_ns

    @classmethod
    def from_owned_process(
        cls,
        binding: CalibratedPositionVectorBinding,
        *,
        current_runtime_sha256: str,
        owned_process_id: int,
        clock_ns=time.monotonic_ns,
    ) -> "WindowsCalibratedPositionVectorSerialApi":
        if (
            cls is not WindowsCalibratedPositionVectorSerialApi
            or type(binding) is not CalibratedPositionVectorBinding
            or type(current_runtime_sha256) is not str
            or type(owned_process_id) is not int
            or not callable(clock_ns)
        ):
            raise ValueError("exact owned calibrated serial composition required")
        binding.__post_init__()
        if owned_process_id != os.getpid():
            raise ValueError("owned process identity mismatch")
        if current_runtime_sha256 != binding.runtime_sha256:
            raise ValueError("owned runtime changed")
        if clock_ns() >= binding.expires_monotonic_ns:
            raise ValueError("calibrated serial admission expired")
        instance = cls(binding.identity.port_name)
        instance._binding = binding
        instance._clock_ns = clock_ns
        return instance

    @property
    def expected_path(self) -> str:
        return self._expected_path

    @property
    def admitted_request_sha256(self) -> str | None:
        if self._binding is None:
            return None
        import hashlib
        import json

        raw = json.dumps(
            dict(self._binding.request),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def status(self):
        if self._binding is None:
            return super().status()
        return {
            "native_api_loaded": self._dll is not None,
            "physical_hold": "CALIBRATED_FEEDBACK_REQUEST_ONLY",
            "calibrated_position_vector_admission": "OWNED_PROCESS_BINDING_MATCHED",
            "physical_authority": False,
        }

    def _require_fresh_open(self) -> None:
        if self._binding is None:
            raise NativeSerialError("CALIBRATED_ADMISSION_REQUIRED", "create_file")
        if self._clock_ns() >= self._binding.expires_monotonic_ns:
            raise NativeSerialError("CALIBRATED_ADMISSION_EXPIRED", "create_file")

    def _kernel(self):
        if self._binding is None:
            return super()._kernel()
        if self._dll is None:
            self._require_fresh_open()
        return self._load_kernel()

    def create_file(self, path: str) -> int:
        with self._open_lock:
            if self._open_attempted:
                raise NativeSerialError("ONE_USE_CALIBRATED_API", "create_file")
            self._open_attempted = True
            if path != self._expected_path:
                raise NativeSerialError("CALIBRATED_ENDPOINT_CHANGED", "create_file")
            self._require_fresh_open()
            return super().create_file(path)


__all__ = ["WindowsCalibratedPositionVectorSerialApi"]
