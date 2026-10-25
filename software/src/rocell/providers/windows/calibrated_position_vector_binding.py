"""Exact child-side binding for calibrated position-vector feedback.

This object joins the application request to the already reviewed controller,
a fresh identical controller identity, the installed calibration controller
binding, and one pinned child runtime.  It is inert: construction performs no
enumeration, serial access, process creation, or filesystem access.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

from rocell.application.physical_connection_contracts import (
    EvidenceOrigin,
    RoArmUsbSerialIdentity,
)
from .arm_feedback_worker import ReviewedControllerBinding
from .calibrated_position_vector_serial_adapter import (
    validate_position_vector_serial_request,
)


SCHEMA = "rocell.calibrated_position_vector_serial_binding.v1"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CONTROLLER_FIELDS = frozenset({"vid", "pid", "unit_serial", "firmware_sha256"})


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


@dataclass(frozen=True, slots=True)
class CalibratedPositionVectorBinding:
    """Immutable inputs admitted to one source-pinned native child."""

    reviewed_controller: ReviewedControllerBinding
    fresh_identity: RoArmUsbSerialIdentity
    request: Mapping[str, Any]
    controller_binding: Mapping[str, Any]
    installed_firmware_sha256: str
    runtime_sha256: str
    expires_monotonic_ns: int

    def __post_init__(self) -> None:
        if (
            type(self.reviewed_controller) is not ReviewedControllerBinding
            or type(self.fresh_identity) is not RoArmUsbSerialIdentity
        ):
            raise ValueError("exact reviewed and fresh controller identities required")
        self.reviewed_controller.__post_init__()
        if self.reviewed_controller.origin is not EvidenceOrigin.PHYSICAL_OBSERVATION:
            raise ValueError("physical reviewed controller binding required")
        if self.fresh_identity != self.reviewed_controller.identity:
            raise ValueError("fresh controller identity does not reproduce review")

        request = validate_position_vector_serial_request(self.request)
        controller = dict(self.controller_binding)
        if set(controller) != _CONTROLLER_FIELDS:
            raise ValueError("calibration controller binding fields are not exact")
        for name in ("vid", "pid", "unit_serial"):
            if not isinstance(controller[name], str) or not controller[name]:
                raise ValueError(f"controller {name} is invalid")
        _digest(controller["firmware_sha256"], "controller firmware_sha256")
        identity = self.fresh_identity
        if (
            controller["vid"].lower() != identity.vid.lower()
            or controller["pid"].lower() != identity.pid.lower()
            or controller["unit_serial"] != identity.unit_serial
        ):
            raise ValueError("calibration and reviewed controller bindings differ")

        _digest(self.installed_firmware_sha256, "installed_firmware_sha256")
        if controller["firmware_sha256"] != self.installed_firmware_sha256:
            raise ValueError("calibration and installed firmware bindings differ")
        _digest(self.runtime_sha256, "runtime_sha256")
        if (
            type(self.expires_monotonic_ns) is not int
            or not 0 < self.expires_monotonic_ns < 2**63
        ):
            raise ValueError("expires_monotonic_ns is invalid")
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "controller_binding", controller)

    @property
    def identity(self) -> RoArmUsbSerialIdentity:
        return self.fresh_identity

    @property
    def origin(self) -> EvidenceOrigin:
        return EvidenceOrigin.PHYSICAL_OBSERVATION

    @property
    def binding_sha256(self) -> str:
        document = {
            "schema": SCHEMA,
            "reviewed_controller_binding_sha256": self.reviewed_controller.binding_sha256,
            "fresh_identity_sha256": self.fresh_identity.identity_sha256,
            "request": dict(self.request),
            "controller_binding": dict(self.controller_binding),
            "installed_firmware_sha256": self.installed_firmware_sha256,
            "runtime_sha256": self.runtime_sha256,
            "expires_monotonic_ns": self.expires_monotonic_ns,
        }
        return hashlib.sha256(_canonical(document)).hexdigest()


__all__ = ["CalibratedPositionVectorBinding", "SCHEMA"]
