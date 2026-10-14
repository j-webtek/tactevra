"""Strict, read-only loading of the selected camera architecture plan.

The architecture plan records an approved direction, not a physical permit.
This module therefore validates the document and exposes its important typed
facts without changing the plan, a freeze, a calibration registry, or any
hardware state.  Exact field checks are intentional: incompatible document
changes require a schema revision rather than being silently ignored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


CAMERA_ARCHITECTURE_PLAN_SCHEMA_V1 = "rocell.camera_architecture_change_plan.v1"
CAMERA_ARCHITECTURE_PLAN_SCHEMA = "rocell.camera_architecture_change_plan.v2"
DEFAULT_CAMERA_ARCHITECTURE_PLAN = Path("software/config/camera_architecture_plan_v2.json")
MAX_CAMERA_ARCHITECTURE_PLAN_BYTES = 256 * 1024

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROOT_FIELDS = frozenset(
    {
        "schema",
        "schema_version",
        "plan_id",
        "decision_date",
        "decision_state",
        "decision",
        "authority",
        "supersession",
        "routes",
        "primary",
        "optional_secondary",
        "frame_contract",
        "runtime_sequence",
        "visibility_contract",
        "optical_screening",
        "calibration_dependencies",
        "acceptance_gates_to_define_and_measure",
        "invalidation_triggers",
        "software_migration",
        "open_blockers",
    }
)

# Safety-significant prose is an interface in this v1 planning schema.  Keep
# these statements exact so deleting a qualifier such as "independent",
# "without ... contact", or "no blind continuation" cannot leave a document
# that still validates merely because the replacement text is non-empty.
_VISIBILITY_CONTRACT = {
    "commissioning": (
        "All six installed tags must be visible and accepted throughout the "
        "complete commissioned overview dataset."
    ),
    "startup": (
        "With the arm in the primary clear observation posture, require all "
        "six tags; T0-T3 form the pose solve and K0/P0 remain independent checks."
    ),
    "per_action": (
        "Capture all six tags from a prequalified primary or recovery observation "
        "posture before descent. Missing, ambiguous, stale, or weakly distributed "
        "tags block descent."
    ),
    "occlusion_strategy": (
        "Observe while retracted, approach and contact, retract, then observe "
        "and verify."
    ),
    "recovery": (
        "Only a prequalified retreat to a second clear observation posture is "
        "allowed; there is no blind continuation or automatic secondary-camera "
        "substitution."
    ),
}

_RUNTIME_SEQUENCE = (
    "verify exact camera identity, mode, settings, calibration hashes, and static-support witness",
    "move only to a prequalified clear observation posture",
    "wait for measured arm and support settling",
    "flush bounded buffered frames and capture a uniquely fresh frame",
    "require all six tags, solve board pose from T0-T3, and validate K0/P0 independently",
    "validate device presence, seating, orientation, and target map",
    "bind the accepted observation and calibration hashes to the pending action occurrence",
    "optionally observe a top-visible tool marker and correct only above the proven clearance plane",
    "execute the short qualified approach and contact without assuming the target remains visible",
    "retract to a clear observation posture",
    "reacquire vision and verify the outcome through the independent computer or Android observer",
)

_CALIBRATION_DEPENDENCIES = (
    "physical camera identity, full native 3:2 mode, pixel format, driver, crop, and locked settings",
    "camera intrinsics and distortion at the exact lens, focus, aperture, resolution, and crop",
    "measured six-tag corner and optical-plane map in B",
    "static Wv_T_C_overhead_optical solved directly or derived from independently measured Wv_T_B plus simultaneous B_T_C_overhead_optical",
    "robot reference and independently bounded R_ctrl-to-Wv correlation",
    "keyboard pose, key polygons, key surface heights, and safe insets",
    "phone pose, screen plane, orientation, UI profile, homography, and safe insets",
    "route-specific G_T_T tool TCP, compliance, travel, and contact limits",
    "held-out end-to-end keyboard and phone validation",
)

_ACCEPTANCE_GATES = (
    "persistent camera identity and exact mode survive close, reopen, and reboot without silent crop or rescale",
    "intrinsic calibration uses at least 20 accepted varied ChArUco views and retains held-out residual evidence",
    "complete calibrated coverage contains all six tag tiles with border margin at both observation postures",
    "all-six-tag startup and route observation trials pass under the complete qualified lighting envelope",
    "T0-T3 pose and K0/P0 held-out checks pass independently",
    "multi-frame pose stability, latency, freshness, and settle-time limits are measured",
    "gantry, camera, cable, and lighting hardware remain outside every approved swept volume",
    "warm-up, arm cycling, cable disturbance, remove/reinstall, and 24-hour drift tests pass the allocated vision budget",
    "every keyboard and phone route has a qualified primary and recovery observation",
    "camera loss, stale replay, settings drift, tag loss/outlier, support movement, and board movement fault injections produce zero descent or contact permits",
)

_ACCEPTANCE_GATES_V2 = tuple(
    (
        "tripod, camera, tether, cable, and lighting hardware remain outside every approved swept volume"
        if item
        == "gantry, camera, cable, and lighting hardware remain outside every approved swept volume"
        else item
    )
    for item in _ACCEPTANCE_GATES
)

_INVALIDATION_TRIGGERS = {
    "intrinsics": (
        "camera, sensor, lens, focus, aperture, resolution, pixel format, ROI, crop, driver, or image orientation change",
    ),
    "static_extrinsic_and_visibility": (
        "gantry, crossbar, camera plate, fastener, camera, cable strain, or optical-axis disturbance",
        "collision or impact involving the support",
        "unexpected reference-witness, pose, or residual drift",
    ),
    "tag_map": ("tag movement, damage, replacement, laminate change, or board warp",),
    "robot_registration": (
        "arm clamp, base, reference procedure, servo, firmware, or controller-frame change",
    ),
    "device_maps": (
        "device removal or reseat, case/protector, station, orientation, layout, OS, or UI change",
    ),
    "tool_tcp": (
        "tool, tip, spring, cartridge, gripper seating, or compliance change",
    ),
}

_INVALIDATION_TRIGGERS_V2 = {
    **_INVALIDATION_TRIGGERS,
    "static_extrinsic_and_visibility": (
        "tripod, head, center column, camera plate, fastener, camera, tether, cable strain, floor contact, or optical-axis disturbance",
        "collision or impact involving the tripod or camera",
        "unexpected reference-witness, pose, or residual drift",
    ),
}


class CameraArchitecturePlanError(ValueError):
    """The camera architecture plan is missing, unsafe, or incompatible."""


def _reject_json_constant(value: str) -> None:
    raise CameraArchitecturePlanError(
        f"camera architecture plan contains invalid JSON constant {value!r}"
    )


def _object_without_duplicate_keys(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CameraArchitecturePlanError(
                f"camera architecture plan contains duplicate key {key!r}"
            )
        result[key] = value
    return result


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CameraArchitecturePlanError(f"{label} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = frozenset(value)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    raise CameraArchitecturePlanError(
        f"{label} fields differ: missing={missing}, unexpected={unexpected}"
    )


def _text(value: object, label: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise CameraArchitecturePlanError(f"{label} must be bounded clean text")
    return value


def _literal(value: object, expected: object, label: str) -> None:
    # Avoid bool/int equality (``True == 1``) weakening exact contracts.
    if type(value) is not type(expected) or value != expected:
        raise CameraArchitecturePlanError(f"{label} must equal {expected!r}")


def _null(value: object, label: str) -> None:
    if value is not None:
        raise CameraArchitecturePlanError(f"{label} must remain null while open")


def _number(value: object, label: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CameraArchitecturePlanError(f"{label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise CameraArchitecturePlanError(
            f"{label} must be finite and within [{minimum}, {maximum}]"
        )
    return parsed


def _text_list(
    value: object,
    label: str,
    *,
    minimum_items: int = 1,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CameraArchitecturePlanError(f"{label} must be an array")
    items = tuple(_text(item, f"{label}[{index}]") for index, item in enumerate(value))
    if len(items) < minimum_items:
        raise CameraArchitecturePlanError(
            f"{label} must contain at least {minimum_items} item(s)"
        )
    if len(items) != len(set(items)):
        raise CameraArchitecturePlanError(f"{label} must not contain duplicates")
    return items


def _numeric_pair(value: object, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise CameraArchitecturePlanError(f"{label} must be a two-value array")
    return (
        _number(value[0], f"{label}[0]", minimum=1.0, maximum=100_000.0),
        _number(value[1], f"{label}[1]", minimum=1.0, maximum=100_000.0),
    )


@dataclass(frozen=True, slots=True)
class OpticalFovScreen:
    """Minimum centered field of view at one proposed camera height."""

    height_mm: float
    horizontal_deg: float
    vertical_deg: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "height_mm",
            _number(self.height_mm, "height_mm", minimum=1.0, maximum=100_000.0),
        )
        for name in ("horizontal_deg", "vertical_deg"):
            object.__setattr__(
                self,
                name,
                _number(getattr(self, name), name, minimum=0.001, maximum=179.999),
            )
        if self.horizontal_deg <= self.vertical_deg:
            raise CameraArchitecturePlanError(
                "landscape optical screening requires horizontal FOV greater than vertical FOV"
            )


@dataclass(frozen=True, slots=True)
class CameraArchitecturePlan:
    """Validated, typed projection of the immutable planning document."""

    source_path: Path
    source_sha256: str
    plan_id: str
    decision_date: str
    decision_state: str
    planning_authority: bool
    simulation_authority: bool
    physical_release_effect: str
    live_motion_authority: bool
    contact_authority: bool
    primary_architecture: str
    primary_optical_frame: str
    runtime_backend_preference: str
    overhead_route_selected: bool
    overhead_required_for_autonomous_descent: bool
    secondary_architecture: str
    secondary_optical_frame: str
    secondary_selected: bool
    automatic_fallback_allowed: bool
    board_size_mm: tuple[float, float]
    provisional_required_coverage_mm: tuple[float, float]
    fov_screen: tuple[OpticalFovScreen, ...]
    open_blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        path = Path(self.source_path)
        if not path.is_absolute():
            raise CameraArchitecturePlanError("source_path must be absolute")
        object.__setattr__(self, "source_path", path)
        if (
            not isinstance(self.source_sha256, str)
            or _SHA256.fullmatch(self.source_sha256) is None
        ):
            raise CameraArchitecturePlanError("source_sha256 must be lowercase SHA-256")
        for field_name in (
            "plan_id",
            "decision_date",
            "decision_state",
            "physical_release_effect",
            "primary_architecture",
            "primary_optical_frame",
            "runtime_backend_preference",
            "secondary_architecture",
            "secondary_optical_frame",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(getattr(self, field_name), field_name),
            )
        for field_name in (
            "planning_authority",
            "simulation_authority",
            "live_motion_authority",
            "contact_authority",
            "overhead_route_selected",
            "overhead_required_for_autonomous_descent",
            "secondary_selected",
            "automatic_fallback_allowed",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise CameraArchitecturePlanError(f"{field_name} must be boolean")
        screens = tuple(self.fov_screen)
        if len(screens) < 2 or any(
            not isinstance(item, OpticalFovScreen) for item in screens
        ):
            raise CameraArchitecturePlanError(
                "fov_screen must contain at least two OpticalFovScreen entries"
            )
        object.__setattr__(self, "fov_screen", screens)
        blockers = tuple(self.open_blockers)
        if not blockers or len(blockers) != len(set(blockers)):
            raise CameraArchitecturePlanError(
                "open_blockers must be non-empty and unique"
            )
        object.__setattr__(self, "open_blockers", blockers)

    @property
    def zero_physical_authority(self) -> bool:
        return (
            self.physical_release_effect == "NONE"
            and not self.live_motion_authority
            and not self.contact_authority
        )


def _validate_authority(document: Mapping[str, Any]) -> None:
    expected = frozenset(
        {
            "planning_authority",
            "simulation_authority",
            "physical_release_effect",
            "live_motion_authority",
            "contact_authority",
            "note",
        }
    )
    _exact_fields(document, expected, "authority")
    _literal(document["planning_authority"], True, "authority.planning_authority")
    _literal(document["simulation_authority"], True, "authority.simulation_authority")
    _literal(
        document["physical_release_effect"], "NONE", "authority.physical_release_effect"
    )
    _literal(
        document["live_motion_authority"], False, "authority.live_motion_authority"
    )
    _literal(document["contact_authority"], False, "authority.contact_authority")
    _text(document["note"], "authority.note")


def _validate_supersession(document: Mapping[str, Any]) -> None:
    _exact_fields(
        document,
        frozenset(
            {
                "historical_freeze_retained",
                "next_freeze_id",
                "supersedes_when_promoted",
                "historical_artifacts_are_immutable",
            }
        ),
        "supersession",
    )
    _literal(
        document["historical_freeze_retained"],
        "ROCELL-PHASE0-RC03-INT-R1-FREEZE-009",
        "supersession.historical_freeze_retained",
    )
    _null(document["next_freeze_id"], "supersession.next_freeze_id")
    _text_list(
        document["supersedes_when_promoted"], "supersession.supersedes_when_promoted"
    )
    _literal(
        document["historical_artifacts_are_immutable"],
        True,
        "supersession.historical_artifacts_are_immutable",
    )


def _validate_routes(
    document: Mapping[str, Any], *, schema_version: int
) -> tuple[bool, bool, bool, bool]:
    _exact_fields(
        document,
        frozenset(
            {
                "camera_overhead_primary",
                "camera_arm_secondary",
                "legacy_camera_mast_optional",
            }
        ),
        "routes",
    )
    overhead = _mapping(
        document["camera_overhead_primary"], "routes.camera_overhead_primary"
    )
    _exact_fields(
        overhead,
        frozenset({"selected", "release_state", "required_for_autonomous_descent"}),
        "routes.camera_overhead_primary",
    )
    _literal(overhead["selected"], True, "routes.camera_overhead_primary.selected")
    _literal(
        overhead["release_state"],
        "SELECTED_UNQUALIFIED",
        "routes.camera_overhead_primary.release_state",
    )
    _literal(
        overhead["required_for_autonomous_descent"],
        True,
        "routes.camera_overhead_primary.required_for_autonomous_descent",
    )

    secondary = _mapping(
        document["camera_arm_secondary"], "routes.camera_arm_secondary"
    )
    _exact_fields(
        secondary,
        frozenset({"selected", "release_state", "automatic_fallback_allowed"}),
        "routes.camera_arm_secondary",
    )
    _literal(secondary["selected"], False, "routes.camera_arm_secondary.selected")
    _literal(
        secondary["release_state"],
        "UNSELECTED_PHASE_2_OPTION",
        "routes.camera_arm_secondary.release_state",
    )
    _literal(
        secondary["automatic_fallback_allowed"],
        False,
        "routes.camera_arm_secondary.automatic_fallback_allowed",
    )

    legacy = _mapping(
        document["legacy_camera_mast_optional"], "routes.legacy_camera_mast_optional"
    )
    _exact_fields(
        legacy,
        frozenset({"selected", "state", "note"}),
        "routes.legacy_camera_mast_optional",
    )
    _literal(legacy["selected"], False, "routes.legacy_camera_mast_optional.selected")
    expected_legacy_state = (
        "DEPRECATED_NAME_RETAINED_ONLY_UNTIL_SCHEMA_V2_MIGRATION"
        if schema_version == 1
        else "SUPERSEDED_HISTORICAL_ONLY"
    )
    _literal(
        legacy["state"], expected_legacy_state, "routes.legacy_camera_mast_optional.state"
    )
    _text(legacy["note"], "routes.legacy_camera_mast_optional.note")
    return True, True, False, False


def _validate_primary(
    document: Mapping[str, Any], *, schema_version: int
) -> tuple[str, str, str]:
    _exact_fields(
        document,
        frozenset(
            {
                "architecture",
                "optical_frame",
                "role",
                "runtime_backend_preference",
                "exact_camera",
                "exact_sensor",
                "exact_lens",
                "commissioned_mode",
                "persistent_usb_identity",
                "mount",
                "existing_support_candidates",
            }
        ),
        "primary",
    )
    _literal(
        document["architecture"], "static_overhead_eye_to_hand", "primary.architecture"
    )
    _literal(document["optical_frame"], "C_overhead_optical", "primary.optical_frame")
    _text(document["role"], "primary.role")
    _literal(
        document["runtime_backend_preference"],
        "usb_opencv",
        "primary.runtime_backend_preference",
    )
    expected_purchased_configuration = {
        "exact_camera": (
            "Arducam B0477 catalog configuration (purchased; received-unit "
            "identity unverified)"
        ),
        "exact_sensor": (
            "Sony IMX283 per supplier specification (unverified until receipt "
            "inspection)"
        ),
        "exact_lens": (
            "included nominal 16 mm manual-focus C-mount lens per purchase "
            "listing (delivered configuration unverified)"
        ),
    }
    for field_name, expected in expected_purchased_configuration.items():
        _literal(document[field_name], expected, f"primary.{field_name}")
    for field_name in ("commissioned_mode", "persistent_usb_identity"):
        _null(document[field_name], f"primary.{field_name}")

    mount = _mapping(document["mount"], "primary.mount")
    _exact_fields(
        mount,
        frozenset(
            {
                "type",
                "relationship_to_arm",
                "height_above_tag_plane_mm",
                "optical_axis_board_intersection_xy_mm",
                "roll_pitch_yaw_deg",
                "support_geometry",
                "camera_interface",
                "collision_geometry",
                "state",
            }
        ),
        "primary.mount",
    )
    _literal(
        mount["type"],
        (
            "rigid static overhead gantry or crossbar"
            if schema_version == 1
            else "independent commercial floor tripod"
        ),
        "primary.mount.type",
    )
    _literal(
        mount["relationship_to_arm"],
        (
            "fixed to the workcell, never to a moving robot link"
            if schema_version == 1
            else "independent floor support, never attached to the arm or board"
        ),
        "primary.mount.relationship_to_arm",
    )
    for field_name in (
        "height_above_tag_plane_mm",
        "optical_axis_board_intersection_xy_mm",
        "roll_pitch_yaw_deg",
        "support_geometry",
        "camera_interface",
        "collision_geometry",
    ):
        _null(mount[field_name], f"primary.mount.{field_name}")
    _literal(
        mount["state"],
        "OPEN_BLOCKING" if schema_version == 1 else "SELECTED_UNQUALIFIED_PENDING_RECEIPT",
        "primary.mount.state",
    )

    supports = _mapping(
        document["existing_support_candidates"], "primary.existing_support_candidates"
    )
    if schema_version == 1:
        expected_supports = {
            "paired_2020_mast_and_universal_plate": "CANDIDATE_ONLY_NOT_RELEASED",
            "commercial_bench_boom": "CANDIDATE_ONLY_NOT_RELEASED",
        }
    else:
        expected_supports = {
            "commercial_floor_tripod_asin_b0csyb4yq2": "SELECTED_UNQUALIFIED",
            "paired_2020_mast_and_universal_plate": "SUPERSEDED_DO_NOT_BUILD",
            "printable_portal_frame": "SUPERSEDED_DO_NOT_PRINT",
            "commercial_bench_boom": "UNSELECTED",
        }
    _exact_fields(
        supports, frozenset({*expected_supports, "note"}), "primary.existing_support_candidates"
    )
    for name, expected_value in expected_supports.items():
        _literal(supports[name], expected_value, f"primary.existing_support_candidates.{name}")
    _text(supports["note"], "primary.existing_support_candidates.note")
    return (
        document["architecture"],
        document["optical_frame"],
        document["runtime_backend_preference"],
    )


def _validate_secondary(document: Mapping[str, Any]) -> tuple[str, str, bool]:
    _exact_fields(
        document,
        frozenset(
            {
                "architecture",
                "optical_frame",
                "selected",
                "allowed_future_roles",
                "prohibited_roles",
                "separate_qualification_required",
            }
        ),
        "optional_secondary",
    )
    _literal(
        document["architecture"],
        "arm_mounted_local_camera",
        "optional_secondary.architecture",
    )
    _literal(document["optical_frame"], "C_arm", "optional_secondary.optical_frame")
    _literal(document["selected"], False, "optional_secondary.selected")
    _text_list(
        document["allowed_future_roles"], "optional_secondary.allowed_future_roles"
    )
    prohibited = _text_list(
        document["prohibited_roles"], "optional_secondary.prohibited_roles"
    )
    if "automatic fallback for a failed primary camera" not in prohibited:
        raise CameraArchitecturePlanError(
            "optional_secondary.prohibited_roles must prohibit automatic fallback"
        )
    _text_list(
        document["separate_qualification_required"],
        "optional_secondary.separate_qualification_required",
    )
    return document["architecture"], document["optical_frame"], False


def _validate_frame_contract(document: Mapping[str, Any]) -> None:
    expected_values = {
        "board_frame": "B",
        "vendor_world_frame": "Wv",
        "controller_frame": "R_ctrl",
        "primary_camera_frame": "C_overhead_optical",
        "optional_tool_marker_frame": "M",
        "tool_tip_frame": "T",
        "observed_transform": "C_overhead_optical_T_B(i)",
        "required_static_extrinsic": "Wv_T_C_overhead_optical",
        "runtime_board_registration": (
            "Wv_T_B(i) = Wv_T_C_overhead_optical * C_overhead_optical_T_B(i)"
        ),
        "controller_bridge": "R_ctrl_T_Wv remains separately measured and bounded",
    }
    _exact_fields(document, frozenset({*expected_values, "rule"}), "frame_contract")
    for field_name, expected in expected_values.items():
        _literal(document[field_name], expected, f"frame_contract.{field_name}")
    rule = _text(document["rule"], "frame_contract.rule")
    if (
        "do not establish robot pose" not in rule
        or "diagnostic evidence only" not in rule
    ):
        raise CameraArchitecturePlanError(
            "frame_contract.rule must preserve the board-only observation limitation"
        )


def _validate_visibility(document: Mapping[str, Any]) -> None:
    _exact_fields(
        document,
        frozenset(
            {
                "commissioning",
                "startup",
                "per_action",
                "occlusion_strategy",
                "recovery",
                "route_atlas_state",
            }
        ),
        "visibility_contract",
    )
    for field_name, expected in _VISIBILITY_CONTRACT.items():
        _literal(
            document[field_name],
            expected,
            f"visibility_contract.{field_name}",
        )
    _literal(
        document["route_atlas_state"],
        "OPEN_BLOCKING",
        "visibility_contract.route_atlas_state",
    )


def _validate_optical_screening(
    document: Mapping[str, Any],
) -> tuple[tuple[float, float], tuple[float, float], tuple[OpticalFovScreen, ...]]:
    _exact_fields(
        document,
        frozenset(
            {
                "board_size_mm",
                "provisional_required_coverage_mm",
                "coverage_margin_note",
                "preferred_sensor_aspect",
                "field_of_view_rule",
                "minimum_centered_perpendicular_fov_screen",
                "candidate_camera_body",
                "previous_wide_lens",
                "state",
            }
        ),
        "optical_screening",
    )
    board = _numeric_pair(document["board_size_mm"], "optical_screening.board_size_mm")
    coverage = _numeric_pair(
        document["provisional_required_coverage_mm"],
        "optical_screening.provisional_required_coverage_mm",
    )
    _literal(board, (610.0, 457.0), "optical_screening.board_size_mm")
    _literal(
        coverage, (670.0, 517.0), "optical_screening.provisional_required_coverage_mm"
    )
    if any(required <= physical for required, physical in zip(coverage, board)):
        raise CameraArchitecturePlanError(
            "provisional optical coverage must exceed the board in both dimensions"
        )
    _text(document["coverage_margin_note"], "optical_screening.coverage_margin_note")
    _literal(
        document["preferred_sensor_aspect"],
        "4:3 landscape",
        "optical_screening.preferred_sensor_aspect",
    )
    _text(document["field_of_view_rule"], "optical_screening.field_of_view_rule")
    _text(document["candidate_camera_body"], "optical_screening.candidate_camera_body")
    _text(document["previous_wide_lens"], "optical_screening.previous_wide_lens")
    _literal(
        document["state"],
        "PURCHASED_PENDING_RECEIPT_INSPECTION",
        "optical_screening.state",
    )

    raw_rows = document["minimum_centered_perpendicular_fov_screen"]
    if not isinstance(raw_rows, list) or len(raw_rows) < 2:
        raise CameraArchitecturePlanError(
            "optical FOV screen must contain at least two rows"
        )
    rows: list[OpticalFovScreen] = []
    for index, raw in enumerate(raw_rows):
        row = _mapping(raw, f"optical FOV row {index}")
        _exact_fields(
            row,
            frozenset({"height_mm", "horizontal_deg", "vertical_deg"}),
            f"optical FOV row {index}",
        )
        parsed = OpticalFovScreen(
            height_mm=row["height_mm"],
            horizontal_deg=row["horizontal_deg"],
            vertical_deg=row["vertical_deg"],
        )
        expected_horizontal = math.degrees(
            2.0 * math.atan(coverage[0] / (2.0 * parsed.height_mm))
        )
        expected_vertical = math.degrees(
            2.0 * math.atan(coverage[1] / (2.0 * parsed.height_mm))
        )
        if not math.isclose(parsed.horizontal_deg, expected_horizontal, abs_tol=0.11):
            raise CameraArchitecturePlanError(
                f"optical FOV row {index} horizontal value does not match coverage geometry"
            )
        if not math.isclose(parsed.vertical_deg, expected_vertical, abs_tol=0.11):
            raise CameraArchitecturePlanError(
                f"optical FOV row {index} vertical value does not match coverage geometry"
            )
        rows.append(parsed)
    for previous, current in zip(rows, rows[1:]):
        if current.height_mm <= previous.height_mm:
            raise CameraArchitecturePlanError(
                "optical screening heights must be strictly increasing"
            )
        if (
            current.horizontal_deg >= previous.horizontal_deg
            or current.vertical_deg >= previous.vertical_deg
        ):
            raise CameraArchitecturePlanError(
                "required optical FOV must strictly decrease as height increases"
            )
    return board, coverage, tuple(rows)


def _validate_supporting_sections(
    document: Mapping[str, Any], *, schema_version: int
) -> tuple[str, ...]:
    runtime_sequence = _text_list(document["runtime_sequence"], "runtime_sequence")
    _literal(runtime_sequence, _RUNTIME_SEQUENCE, "runtime_sequence")

    calibrations = _text_list(
        document["calibration_dependencies"], "calibration_dependencies"
    )
    _literal(
        calibrations,
        _CALIBRATION_DEPENDENCIES,
        "calibration_dependencies",
    )

    acceptance_gates = _text_list(
        document["acceptance_gates_to_define_and_measure"],
        "acceptance_gates_to_define_and_measure",
    )
    _literal(
        acceptance_gates,
        _ACCEPTANCE_GATES if schema_version == 1 else _ACCEPTANCE_GATES_V2,
        "acceptance_gates_to_define_and_measure",
    )

    _text_list(document["software_migration"], "software_migration")

    triggers = _mapping(document["invalidation_triggers"], "invalidation_triggers")
    expected_values = (
        _INVALIDATION_TRIGGERS
        if schema_version == 1
        else _INVALIDATION_TRIGGERS_V2
    )
    expected_triggers = frozenset(expected_values)
    _exact_fields(triggers, expected_triggers, "invalidation_triggers")
    for field_name in sorted(expected_triggers):
        values = _text_list(triggers[field_name], f"invalidation_triggers.{field_name}")
        _literal(
            values,
            expected_values[field_name],
            f"invalidation_triggers.{field_name}",
        )
    return _text_list(document["open_blockers"], "open_blockers")


def load_camera_architecture_plan(
    workspace: Path,
    plan_path: Path | None = None,
) -> CameraArchitecturePlan:
    """Load and validate the selected plan without modifying any source.

    ``plan_path`` may be absolute or relative to ``workspace``.  The resolved
    source must remain inside the workspace, including through symlinks.
    """

    root = Path(workspace).resolve(strict=True)
    requested = (
        DEFAULT_CAMERA_ARCHITECTURE_PLAN if plan_path is None else Path(plan_path)
    )
    candidate = requested if requested.is_absolute() else root / requested
    try:
        selected = candidate.resolve(strict=True)
    except OSError as exc:
        raise CameraArchitecturePlanError(
            f"camera architecture plan is unavailable: {candidate}"
        ) from exc
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise CameraArchitecturePlanError(
            "camera architecture plan must remain beneath the workspace"
        ) from exc
    if not selected.is_file():
        raise CameraArchitecturePlanError("camera architecture plan must be a file")
    try:
        with selected.open("rb") as stream:
            payload = stream.read(MAX_CAMERA_ARCHITECTURE_PLAN_BYTES + 1)
    except OSError as exc:
        raise CameraArchitecturePlanError(
            "camera architecture plan could not be read"
        ) from exc
    return parse_camera_architecture_plan_json(payload, source_path=selected)


def parse_camera_architecture_plan_json(
    payload: bytes, *, source_path: Path
) -> CameraArchitecturePlan:
    """Validate retained original bytes without resolving or reading any path."""

    if type(payload) is not bytes or not payload:
        raise CameraArchitecturePlanError(
            "camera architecture plan must be nonempty bytes"
        )
    if len(payload) > MAX_CAMERA_ARCHITECTURE_PLAN_BYTES:
        raise CameraArchitecturePlanError(
            f"camera architecture plan exceeds {MAX_CAMERA_ARCHITECTURE_PLAN_BYTES} bytes"
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CameraArchitecturePlanError(
            "camera architecture plan must be UTF-8"
        ) from exc
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except CameraArchitecturePlanError:
        raise
    except json.JSONDecodeError as exc:
        raise CameraArchitecturePlanError(
            f"camera architecture plan is not valid JSON: {exc.msg}"
        ) from exc
    root_document = _mapping(parsed, "camera architecture plan")
    _exact_fields(root_document, _ROOT_FIELDS, "camera architecture plan")
    schema = root_document["schema"]
    schema_version = root_document["schema_version"]
    if not (
        type(schema) is str
        and type(schema_version) is int
        and (schema, schema_version)
        in {
            (CAMERA_ARCHITECTURE_PLAN_SCHEMA_V1, 1),
            (CAMERA_ARCHITECTURE_PLAN_SCHEMA, 2),
        }
    ):
        raise CameraArchitecturePlanError(
            "schema and schema_version must identify camera architecture v1 or v2"
        )
    plan_id = _text(root_document["plan_id"], "plan_id")
    decision_date = _text(root_document["decision_date"], "decision_date")
    try:
        date.fromisoformat(decision_date)
    except ValueError as exc:
        raise CameraArchitecturePlanError(
            "decision_date must be an ISO-8601 calendar date"
        ) from exc
    decision_state = _text(root_document["decision_state"], "decision_state")
    _literal(
        decision_state,
        (
            "ARCHITECTURE_SELECTED_CAMERA_PURCHASED_PENDING_RECEIPT_INSPECTION"
            if schema_version == 1
            else "CAMERA_AND_TRIPOD_SELECTED_PENDING_RECEIPT_AND_PHYSICAL_QUALIFICATION"
        ),
        "decision_state",
    )
    _text(root_document["decision"], "decision")

    authority = _mapping(root_document["authority"], "authority")
    _validate_authority(authority)
    _validate_supersession(_mapping(root_document["supersession"], "supersession"))
    overhead_selected, overhead_required, secondary_selected, fallback_allowed = (
        _validate_routes(
            _mapping(root_document["routes"], "routes"),
            schema_version=schema_version,
        )
    )
    primary_architecture, primary_frame, backend = _validate_primary(
        _mapping(root_document["primary"], "primary"),
        schema_version=schema_version,
    )
    secondary_architecture, secondary_frame, secondary_selected_again = (
        _validate_secondary(
            _mapping(root_document["optional_secondary"], "optional_secondary")
        )
    )
    if secondary_selected_again != secondary_selected:
        raise CameraArchitecturePlanError(
            "optional secondary selection differs from its route selection"
        )
    _validate_frame_contract(
        _mapping(root_document["frame_contract"], "frame_contract")
    )
    _validate_visibility(
        _mapping(root_document["visibility_contract"], "visibility_contract")
    )
    board, coverage, screen = _validate_optical_screening(
        _mapping(root_document["optical_screening"], "optical_screening")
    )
    blockers = _validate_supporting_sections(
        root_document, schema_version=schema_version
    )

    result = CameraArchitecturePlan(
        source_path=source_path,
        source_sha256=hashlib.sha256(payload).hexdigest(),
        plan_id=plan_id,
        decision_date=decision_date,
        decision_state=decision_state,
        planning_authority=authority["planning_authority"],
        simulation_authority=authority["simulation_authority"],
        physical_release_effect=authority["physical_release_effect"],
        live_motion_authority=authority["live_motion_authority"],
        contact_authority=authority["contact_authority"],
        primary_architecture=primary_architecture,
        primary_optical_frame=primary_frame,
        runtime_backend_preference=backend,
        overhead_route_selected=overhead_selected,
        overhead_required_for_autonomous_descent=overhead_required,
        secondary_architecture=secondary_architecture,
        secondary_optical_frame=secondary_frame,
        secondary_selected=secondary_selected,
        automatic_fallback_allowed=fallback_allowed,
        board_size_mm=board,
        provisional_required_coverage_mm=coverage,
        fov_screen=screen,
        open_blockers=blockers,
    )
    if not result.zero_physical_authority:
        raise CameraArchitecturePlanError(
            "camera architecture plan must confer zero physical authority"
        )
    return result


__all__ = [
    "CAMERA_ARCHITECTURE_PLAN_SCHEMA",
    "CAMERA_ARCHITECTURE_PLAN_SCHEMA_V1",
    "DEFAULT_CAMERA_ARCHITECTURE_PLAN",
    "MAX_CAMERA_ARCHITECTURE_PLAN_BYTES",
    "CameraArchitecturePlan",
    "CameraArchitecturePlanError",
    "OpticalFovScreen",
    "load_camera_architecture_plan",
    "parse_camera_architecture_plan_json",
]
