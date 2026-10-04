"""Strict PC0 qualification-basis loader for pre-camera typing work.

The retained basis freezes synthetic fixtures, identities, resource ceilings,
and status vocabulary.  Loading it creates no controller or physical authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping


SCHEMA = "rocell.pre_camera_typing_qualification_basis.v1"
DEFAULT_BASIS = Path("software/config/pre_camera_typing_qualification_basis_v1.json")
MAXIMUM_BASIS_BYTES = 64 * 1024
EXPECTED_FIXTURES = (
    "type-robot",
    "type-book",
    "type-qaz",
    "type-plm",
    "repeat-punctuation",
    "space",
    "enter",
    "same-key-repeat",
)
EXPECTED_PIN_ROLES = (
    "model_motion_batch_v2_schema",
    "synthetic_target_catalog",
    "pinned_arm_model",
    "frozen_system_manifest",
    "zero_write_controller_profile_schema",
)


class PreCameraTypingQualificationBasisV1Error(ValueError):
    """The retained PC0 basis is malformed, crossed, or no longer reproducible."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PreCameraTypingQualificationBasisV1Error(
                f"duplicate JSON member: {key}"
            )
        result[key] = value
    return result


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256_text(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreCameraTypingQualificationBasisV1Error(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise PreCameraTypingQualificationBasisV1Error(
            f"{label} must contain exactly {sorted(expected)}"
        )


def _bounded_id(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 128
    ):
        raise PreCameraTypingQualificationBasisV1Error(
            f"{label} must be bounded nonempty unpadded text"
        )
    return value


def _positive_number(value: object, label: str, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreCameraTypingQualificationBasisV1Error(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not 0.0 < result <= maximum:
        raise PreCameraTypingQualificationBasisV1Error(
            f"{label} must be finite in (0, {maximum}]"
        )
    return result


@dataclass(frozen=True, slots=True)
class PinnedSourceV1:
    role: str
    path: str
    sha256: str

    def __post_init__(self) -> None:
        _bounded_id(self.role, "pinned source role")
        _sha256_text(self.sha256, f"{self.role}.sha256")
        candidate = PurePosixPath(self.path)
        if (
            not self.path
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "\\" in self.path
            or len(candidate.parts) < 2
        ):
            raise PreCameraTypingQualificationBasisV1Error(
                f"{self.role}.path must be a safe workspace-relative POSIX path"
            )


@dataclass(frozen=True, slots=True)
class CanonicalTypingFixtureV1:
    fixture_id: str
    input_text: str
    expected_target_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _bounded_id(self.fixture_id, "fixture_id")
        if not isinstance(self.input_text, str) or not 1 <= len(self.input_text) <= 128:
            raise PreCameraTypingQualificationBasisV1Error(
                "input_text must contain 1 through 128 characters"
            )
        if not self.expected_target_ids or len(self.expected_target_ids) > 128:
            raise PreCameraTypingQualificationBasisV1Error(
                "expected_target_ids must contain 1 through 128 targets"
            )
        for target in self.expected_target_ids:
            _bounded_id(target, "expected target")


@dataclass(frozen=True, slots=True)
class PreCameraTypingQualificationBasisV1:
    document: Mapping[str, Any]
    pinned_sources: tuple[PinnedSourceV1, ...]
    fixtures: tuple[CanonicalTypingFixtureV1, ...]
    basis_sha256: str


def parse_pre_camera_typing_qualification_basis_v1(
    document: Mapping[str, Any],
) -> PreCameraTypingQualificationBasisV1:
    if not isinstance(document, Mapping):
        raise PreCameraTypingQualificationBasisV1Error("basis must be an object")
    expected_top = {
        "schema",
        "basis_id",
        "evidence_class",
        "physical_release_effect",
        "authority",
        "pinned_sources",
        "fixture_identities",
        "cartesian_policy",
        "synthetic_joint_dynamics_profile",
        "zero_write_controller_profile",
        "canonical_fixtures",
        "outcome_codes",
        "benchmark_policy",
    }
    _exact_keys(document, expected_top, "basis")
    if document["schema"] != SCHEMA:
        raise PreCameraTypingQualificationBasisV1Error("unsupported basis schema")
    _bounded_id(document["basis_id"], "basis_id")
    if document["evidence_class"] != "SYNTHETIC_OFFLINE_ONLY":
        raise PreCameraTypingQualificationBasisV1Error(
            "basis must remain SYNTHETIC_OFFLINE_ONLY"
        )
    if document["physical_release_effect"] != "NONE":
        raise PreCameraTypingQualificationBasisV1Error(
            "basis must have no physical release effect"
        )

    authority = document["authority"]
    expected_authority = {
        "controller_startup",
        "transport_open",
        "controller_write",
        "movement",
        "torque_change",
        "firmware_installation",
    }
    if not isinstance(authority, Mapping):
        raise PreCameraTypingQualificationBasisV1Error("authority must be an object")
    _exact_keys(authority, expected_authority, "authority")
    if any(value is not False for value in authority.values()):
        raise PreCameraTypingQualificationBasisV1Error(
            "every PC0 authority flag must be false"
        )

    source_documents = document["pinned_sources"]
    if not isinstance(source_documents, list):
        raise PreCameraTypingQualificationBasisV1Error("pinned_sources must be a list")
    pinned_sources: list[PinnedSourceV1] = []
    for item in source_documents:
        if not isinstance(item, Mapping):
            raise PreCameraTypingQualificationBasisV1Error(
                "each pinned source must be an object"
            )
        _exact_keys(item, {"role", "path", "sha256"}, "pinned source")
        pinned_sources.append(PinnedSourceV1(**item))
    if tuple(item.role for item in pinned_sources) != EXPECTED_PIN_ROLES:
        raise PreCameraTypingQualificationBasisV1Error(
            "pinned source roles or order differ from the PC0 contract"
        )

    identities = document["fixture_identities"]
    expected_identity_keys = {
        "calibration_fixture_id",
        "calibration_fixture_sha256",
        "joint_dynamics_profile_id",
        "joint_dynamics_profile_sha256",
        "controller_encoding_profile_id",
        "controller_encoding_profile_sha256",
    }
    if not isinstance(identities, Mapping):
        raise PreCameraTypingQualificationBasisV1Error(
            "fixture_identities must be an object"
        )
    _exact_keys(identities, expected_identity_keys, "fixture_identities")
    for key, value in identities.items():
        if key.endswith("_sha256"):
            _sha256_text(value, key)
        else:
            identifier = _bounded_id(value, key)
            digest_key = key.removesuffix("_id") + "_sha256"
            if hashlib.sha256(identifier.encode("utf-8")).hexdigest() != identities[digest_key]:
                raise PreCameraTypingQualificationBasisV1Error(
                    f"{digest_key} does not bind {key}"
                )

    cartesian = document["cartesian_policy"]
    if not isinstance(cartesian, Mapping):
        raise PreCameraTypingQualificationBasisV1Error(
            "cartesian_policy must be an object"
        )
    _exact_keys(
        cartesian,
        {
            "policy_id",
            "maximum_cartesian_step_mm",
            "maximum_velocity_mm_s",
            "maximum_acceleration_mm_s2",
            "maximum_jerk_mm_s3",
            "hover_settle_ms",
            "contact_dwell_ms",
        },
        "cartesian_policy",
    )
    _bounded_id(cartesian["policy_id"], "cartesian_policy.policy_id")
    for key, maximum in (
        ("maximum_cartesian_step_mm", 100.0),
        ("maximum_velocity_mm_s", 2_000.0),
        ("maximum_acceleration_mm_s2", 20_000.0),
        ("maximum_jerk_mm_s3", 200_000.0),
    ):
        _positive_number(cartesian[key], f"cartesian_policy.{key}", maximum)
    for key in ("hover_settle_ms", "contact_dwell_ms"):
        value = cartesian[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
            raise PreCameraTypingQualificationBasisV1Error(
                f"cartesian_policy.{key} must be an integer in [0, 10000]"
            )

    dynamics = document["synthetic_joint_dynamics_profile"]
    if not isinstance(dynamics, Mapping):
        raise PreCameraTypingQualificationBasisV1Error(
            "synthetic_joint_dynamics_profile must be an object"
        )
    if dynamics.get("source_kind") != "SYNTHETIC_OFFLINE":
        raise PreCameraTypingQualificationBasisV1Error(
            "joint dynamics profile must remain synthetic"
        )
    if dynamics.get("physical_tracking_qualification") is not False:
        raise PreCameraTypingQualificationBasisV1Error(
            "synthetic profile cannot claim physical tracking qualification"
        )
    joint_order = dynamics.get("joint_order")
    if joint_order != ["base", "shoulder", "elbow", "wrist_pitch", "wrist_roll"]:
        raise PreCameraTypingQualificationBasisV1Error(
            "synthetic joint order differs from the canonical arm order"
        )
    for key, maximum in (
        ("maximum_velocity_rad_s", 100.0),
        ("maximum_acceleration_rad_s2", 1_000.0),
        ("maximum_jerk_rad_s3", 10_000.0),
    ):
        values = dynamics.get(key)
        if not isinstance(values, list) or len(values) != len(joint_order):
            raise PreCameraTypingQualificationBasisV1Error(
                f"{key} must align exactly with joint_order"
            )
        for index, value in enumerate(values):
            _positive_number(value, f"{key}[{index}]", maximum)
    _positive_number(
        dynamics.get("maximum_time_scale_factor"),
        "maximum_time_scale_factor",
        1_000.0,
    )

    controller = document["zero_write_controller_profile"]
    if not isinstance(controller, Mapping):
        raise PreCameraTypingQualificationBasisV1Error(
            "zero_write_controller_profile must be an object"
        )
    if (
        controller.get("source_kind") != "SYNTHETIC_OFFLINE"
        or controller.get("command_type") != 102
        or controller.get("transport_enabled") is not False
        or controller.get("interpolation_mode")
        != "HOST_SCHEDULED_T102_WAYPOINTS_V1"
    ):
        raise PreCameraTypingQualificationBasisV1Error(
            "zero-write controller profile crossed its synthetic boundary"
        )

    fixture_documents = document["canonical_fixtures"]
    if not isinstance(fixture_documents, list):
        raise PreCameraTypingQualificationBasisV1Error(
            "canonical_fixtures must be a list"
        )
    fixtures: list[CanonicalTypingFixtureV1] = []
    for item in fixture_documents:
        if not isinstance(item, Mapping):
            raise PreCameraTypingQualificationBasisV1Error(
                "each canonical fixture must be an object"
            )
        _exact_keys(
            item,
            {"fixture_id", "input_text", "expected_target_ids"},
            "canonical fixture",
        )
        fixtures.append(
            CanonicalTypingFixtureV1(
                fixture_id=item["fixture_id"],
                input_text=item["input_text"],
                expected_target_ids=tuple(item["expected_target_ids"]),
            )
        )
    if tuple(item.fixture_id for item in fixtures) != EXPECTED_FIXTURES:
        raise PreCameraTypingQualificationBasisV1Error(
            "fixture identities or order differ from the PC0 contract"
        )

    outcomes = document["outcome_codes"]
    if (
        not isinstance(outcomes, list)
        or not outcomes
        or len(outcomes) != len(set(outcomes))
        or any(not isinstance(item, str) or not item for item in outcomes)
    ):
        raise PreCameraTypingQualificationBasisV1Error(
            "outcome_codes must be unique nonempty strings"
        )
    required_outcomes = {
        "PASS_SYNTHETIC_OFFLINE",
        "BLOCKED_MEASURED_INSTALLED_PROFILE_REQUIRED",
        "BLOCKED_FRESH_OBSERVED_STATE_REQUIRED",
        "OUTCOME_UNCERTAIN_RETRY_FORBIDDEN",
    }
    if not required_outcomes.issubset(outcomes):
        raise PreCameraTypingQualificationBasisV1Error(
            "outcome_codes omit required PC0 terminal states"
        )

    benchmark = document["benchmark_policy"]
    if not isinstance(benchmark, Mapping):
        raise PreCameraTypingQualificationBasisV1Error(
            "benchmark_policy must be an object"
        )
    if benchmark.get("reported_percentiles") != [50, 95, 99]:
        raise PreCameraTypingQualificationBasisV1Error(
            "benchmark percentiles must be [50, 95, 99]"
        )
    if benchmark.get("simulation_timing_is_physical_claim") is not False:
        raise PreCameraTypingQualificationBasisV1Error(
            "simulation timing cannot be a physical performance claim"
        )
    for key in (
        "minimum_iterations",
        "maximum_actions_per_batch",
        "maximum_screening_samples",
        "maximum_serialized_artifact_bytes",
        "maximum_peak_process_memory_mib",
        "planning_cpu_p95_ms_ceiling",
    ):
        value = benchmark.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise PreCameraTypingQualificationBasisV1Error(
                f"benchmark_policy.{key} must be a positive integer"
            )

    frozen = json.loads(_canonical(document))
    return PreCameraTypingQualificationBasisV1(
        document=MappingProxyType(frozen),
        pinned_sources=tuple(pinned_sources),
        fixtures=tuple(fixtures),
        basis_sha256=_digest(frozen),
    )


def verify_pre_camera_typing_pins_v1(
    basis: PreCameraTypingQualificationBasisV1,
    workspace_root: Path,
) -> None:
    root = workspace_root.resolve(strict=True)
    for pin in basis.pinned_sources:
        candidate = (root / Path(*PurePosixPath(pin.path).parts)).resolve(strict=True)
        if root not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
            raise PreCameraTypingQualificationBasisV1Error(
                f"{pin.role} does not resolve to a regular workspace file"
            )
        if candidate.stat().st_size > 16 * 1024 * 1024:
            raise PreCameraTypingQualificationBasisV1Error(
                f"{pin.role} exceeds the bounded source size"
            )
        observed = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if observed != pin.sha256:
            raise PreCameraTypingQualificationBasisV1Error(
                f"{pin.role} source hash differs from the PC0 pin"
            )


def load_pre_camera_typing_qualification_basis_v1(
    workspace_root: Path,
    path: Path = DEFAULT_BASIS,
) -> PreCameraTypingQualificationBasisV1:
    root = workspace_root.resolve(strict=True)
    candidate = (root / path).resolve(strict=True)
    if root not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
        raise PreCameraTypingQualificationBasisV1Error(
            "basis must resolve to a regular workspace file"
        )
    raw = candidate.read_bytes()
    if len(raw) > MAXIMUM_BASIS_BYTES:
        raise PreCameraTypingQualificationBasisV1Error("basis exceeds maximum size")
    try:
        document = json.loads(raw, object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreCameraTypingQualificationBasisV1Error(
            "basis is not strict UTF-8 JSON"
        ) from exc
    basis = parse_pre_camera_typing_qualification_basis_v1(document)
    verify_pre_camera_typing_pins_v1(basis, root)
    return basis


__all__ = [
    "DEFAULT_BASIS",
    "EXPECTED_FIXTURES",
    "EXPECTED_PIN_ROLES",
    "PreCameraTypingQualificationBasisV1",
    "PreCameraTypingQualificationBasisV1Error",
    "load_pre_camera_typing_qualification_basis_v1",
    "parse_pre_camera_typing_qualification_basis_v1",
    "verify_pre_camera_typing_pins_v1",
]
