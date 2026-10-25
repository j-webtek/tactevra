"""Deterministic source archive for the isolated position-vector child."""

from __future__ import annotations

import io
from pathlib import Path
import zipfile

from rocell.application.physical_onboarding_durability import PublicationMode, publish_bytes

from .owned_arm_feedback_package import (
    MAX_FILE_BYTES,
    MAX_PACKAGE_BYTES,
    _WORKSPACE,
    _archive,
    _read,
)
from .powered_feedback_native_package import expected_archive as shared_archive


CHILD = Path(__file__).with_name("_calibrated_position_vector_native_child.py")
EXTRA = (
    "application/calibrated_position_vector_feedback_execution.py",
    "arm/feedback_profile.py",
    "arm/position_vector_calibration.py",
    "calibration/position_vector_campaign.py",
    "providers/windows/calibrated_position_vector_binding.py",
    "providers/windows/calibrated_position_vector_native_composition.py",
    "providers/windows/calibrated_position_vector_owned_protocol.py",
    "providers/windows/calibrated_position_vector_serial_adapter.py",
    "providers/windows/calibrated_position_vector_serial_api.py",
)


def expected_archive() -> bytes:
    with zipfile.ZipFile(io.BytesIO(shared_archive())) as source:
        entries = {name: source.read(name) for name in source.namelist()}
    # The workspace calibration package initializer imports the complete
    # offline calibration suite. The child gets a deliberately inert namespace
    # initializer and only the position-vector module listed below.
    entries["rocell/calibration/__init__.py"] = b'"""Isolated calibration namespace."""\n'
    for name in EXTRA:
        entries["rocell/" + name] = _read(
            _WORKSPACE / "software/src/rocell" / name, MAX_FILE_BYTES
        )
    return _archive(entries)


def prepare(directory: Path) -> Path:
    return publish_bytes(
        directory,
        "calibrated-position-vector-native.zip",
        expected_archive(),
        mode=PublicationMode.IMMUTABLE,
        maximum_bytes=MAX_PACKAGE_BYTES,
    )


__all__ = ["CHILD", "EXTRA", "expected_archive", "prepare"]
