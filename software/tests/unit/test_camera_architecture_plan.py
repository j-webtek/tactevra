from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from rocell.workcell import (
    CameraArchitecturePlanError,
    load_camera_architecture_plan,
)


WORKSPACE = Path(__file__).resolve().parents[3]
PLAN_PATH = WORKSPACE / "software/config/camera_architecture_plan_v2.json"
HISTORICAL_PLAN_PATH = WORKSPACE / "software/config/camera_architecture_plan.json"


def _document() -> dict[str, Any]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def _temporary_plan(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> Path:
    document = copy.deepcopy(_document())
    mutate(document)
    path = tmp_path / "camera_architecture_plan.json"
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def test_loads_selected_static_primary_plan_without_modifying_source() -> None:
    before = PLAN_PATH.read_bytes()
    document = _document()

    plan = load_camera_architecture_plan(WORKSPACE)

    assert PLAN_PATH.read_bytes() == before
    assert plan.source_path == PLAN_PATH.resolve()
    assert plan.source_sha256 == hashlib.sha256(before).hexdigest()
    assert plan.plan_id == "ROCELL-CAMERA-STATIC-PRIMARY-TRIPOD-002"
    assert (
        plan.decision_state
        == "CAMERA_AND_TRIPOD_SELECTED_PENDING_RECEIPT_AND_PHYSICAL_QUALIFICATION"
    )
    assert plan.primary_architecture == "static_overhead_eye_to_hand"
    assert plan.primary_optical_frame == "C_overhead_optical"
    assert plan.runtime_backend_preference == "usb_opencv"
    assert plan.overhead_route_selected
    assert plan.overhead_required_for_autonomous_descent
    assert plan.secondary_architecture == "arm_mounted_local_camera"
    assert plan.secondary_optical_frame == "C_arm"
    assert not plan.secondary_selected
    assert not plan.automatic_fallback_allowed
    assert plan.zero_physical_authority
    assert plan.board_size_mm == (610.0, 457.0)
    assert plan.provisional_required_coverage_mm == (670.0, 517.0)
    assert len(plan.fov_screen) == 6
    assert plan.open_blockers
    assert document["primary"]["exact_camera"] == (
        "Arducam B0477 catalog configuration (purchased; received-unit identity "
        "unverified)"
    )
    assert document["primary"]["exact_sensor"] == (
        "Sony IMX283 per supplier specification (unverified until receipt inspection)"
    )
    assert document["primary"]["exact_lens"] == (
        "included nominal 16 mm manual-focus C-mount lens per purchase listing "
        "(delivered configuration unverified)"
    )
    assert document["primary"]["commissioned_mode"] is None
    assert document["primary"]["persistent_usb_identity"] is None
    assert (
        document["optical_screening"]["state"]
        == "PURCHASED_PENDING_RECEIPT_INSPECTION"
    )
    assert document["primary"]["mount"]["type"] == (
        "independent commercial floor tripod"
    )
    assert document["primary"]["existing_support_candidates"][
        "commercial_floor_tripod_asin_b0csyb4yq2"
    ] == "SELECTED_UNQUALIFIED"


def test_explicit_historical_v1_plan_remains_readable() -> None:
    before = HISTORICAL_PLAN_PATH.read_bytes()

    plan = load_camera_architecture_plan(WORKSPACE, HISTORICAL_PLAN_PATH)

    assert HISTORICAL_PLAN_PATH.read_bytes() == before
    assert plan.plan_id == "ROCELL-CAMERA-STATIC-PRIMARY-001"
    assert plan.source_sha256 == hashlib.sha256(before).hexdigest()
    assert plan.zero_physical_authority


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("exact_camera", "Arducam B0477 received and verified"),
        ("exact_sensor", "Sony IMX283 physically verified"),
        ("exact_lens", "16 mm lens physically verified"),
        ("commissioned_mode", "5472x3648 YUY2 at 9 fps"),
        ("persistent_usb_identity", "camera-index-0"),
    ],
)
def test_rejects_unsubstantiated_received_or_commissioned_camera_claims(
    tmp_path: Path, field: str, value: str
) -> None:
    path = _temporary_plan(
        tmp_path,
        lambda document: document["primary"].update({field: value}),
    )

    with pytest.raises(CameraArchitecturePlanError, match=field):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize("change", ["remove", "add"])
def test_rejects_root_schema_drift(tmp_path: Path, change: str) -> None:
    def mutate(document: dict[str, Any]) -> None:
        if change == "remove":
            del document["visibility_contract"]
        else:
            document["unversioned_extension"] = True

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="fields differ"):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("physical_release_effect", "CONTACT_RELEASED"),
        ("live_motion_authority", True),
        ("contact_authority", True),
    ],
)
def test_rejects_any_physical_authority(
    tmp_path: Path, field: str, value: object
) -> None:
    path = _temporary_plan(
        tmp_path,
        lambda document: document["authority"].update({field: value}),
    )
    with pytest.raises(CameraArchitecturePlanError, match=field):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    ("path_parts", "value", "message"),
    [
        (("routes", "camera_overhead_primary", "selected"), False, "selected"),
        (
            ("routes", "camera_overhead_primary", "required_for_autonomous_descent"),
            False,
            "required_for_autonomous_descent",
        ),
        (("primary", "architecture"), "eye_on_moving_upper_arm", "architecture"),
        (("primary", "optical_frame"), "C_arm", "optical_frame"),
        (
            ("frame_contract", "primary_camera_frame"),
            "C_arm",
            "primary_camera_frame",
        ),
    ],
)
def test_rejects_non_overhead_primary_contract(
    tmp_path: Path,
    path_parts: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        cursor = document
        for part in path_parts[:-1]:
            cursor = cursor[part]
        cursor[path_parts[-1]] = value

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match=message):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ("routes", "automatic_fallback_allowed"),
        ("optional_secondary", "selected"),
    ],
)
def test_rejects_enabled_arm_camera_or_automatic_fallback(
    tmp_path: Path, container: str, field: str
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        target = (
            document["routes"]["camera_arm_secondary"]
            if container == "routes"
            else document["optional_secondary"]
        )
        target[field] = True

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match=field):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    ("field", "weakened_text"),
    [
        (
            "commissioning",
            "Some installed tags should usually be visible during commissioning.",
        ),
        (
            "startup",
            "Require all six tags but use them all interchangeably.",
        ),
        (
            "startup",
            "Require T0-T3 for pose and ignore K0/P0.",
        ),
        (
            "per_action",
            "Capture when convenient; missing or stale tags only produce a warning.",
        ),
        (
            "per_action",
            "Capture from a prequalified primary or recovery observation posture "
            "before descent. Missing, ambiguous, stale, or weakly distributed tags "
            "block descent.",
        ),
        (
            "occlusion_strategy",
            "Observe, approach, contact, and continue without retracting to observe.",
        ),
        (
            "recovery",
            "Blind continuation is allowed after a failed observation.",
        ),
        (
            "recovery",
            "Automatically substitute the secondary arm camera after primary loss.",
        ),
    ],
)
def test_rejects_weakened_visibility_and_recovery_contracts(
    tmp_path: Path,
    field: str,
    weakened_text: str,
) -> None:
    path = _temporary_plan(
        tmp_path,
        lambda document: document["visibility_contract"].update(
            {field: weakened_text}
        ),
    )

    with pytest.raises(
        CameraArchitecturePlanError,
        match=rf"visibility_contract\.{field}",
    ):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    "removed_step_fragment",
    [
        "prequalified clear observation posture",
        "arm and support settling",
        "uniquely fresh frame",
        "T0-T3",
        "retract to a clear observation posture",
        "reacquire vision and verify",
    ],
)
def test_rejects_missing_stop_look_retract_or_reobserve_step(
    tmp_path: Path,
    removed_step_fragment: str,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["runtime_sequence"] = [
            step
            for step in document["runtime_sequence"]
            if removed_step_fragment not in step
        ]

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="runtime_sequence"):
        load_camera_architecture_plan(tmp_path, path)


def test_rejects_reobserve_before_retract(tmp_path: Path) -> None:
    def mutate(document: dict[str, Any]) -> None:
        sequence = document["runtime_sequence"]
        sequence[-2], sequence[-1] = sequence[-1], sequence[-2]

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="runtime_sequence"):
        load_camera_architecture_plan(tmp_path, path)


def test_rejects_runtime_pose_check_without_all_six_tags(tmp_path: Path) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["runtime_sequence"][4] = (
            "solve board pose from T0-T3 and validate K0/P0 independently"
        )

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="runtime_sequence"):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    "required_fragment",
    [
        "physical camera identity",
        "camera intrinsics and distortion",
        "measured six-tag",
        "Wv_T_C_overhead_optical",
        "robot reference",
        "keyboard pose",
        "phone pose",
        "G_T_T tool TCP",
        "held-out end-to-end",
    ],
)
def test_rejects_missing_calibration_dependency_category(
    tmp_path: Path,
    required_fragment: str,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["calibration_dependencies"] = [
            item
            for item in document["calibration_dependencies"]
            if required_fragment not in item
        ]

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="calibration_dependencies"):
        load_camera_architecture_plan(tmp_path, path)


def test_rejects_weakened_overhead_extrinsic_dependency(tmp_path: Path) -> None:
    def mutate(document: dict[str, Any]) -> None:
        document["calibration_dependencies"][3] = (
            "static Wv_T_C_overhead_optical or an independently equivalent "
            "B_T_Wv registration"
        )

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="calibration_dependencies"):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    "required_fragment",
    [
        "persistent camera identity",
        "20 accepted varied ChArUco views",
        "all six tag tiles",
        "all-six-tag startup",
        "T0-T3 pose and K0/P0",
        "multi-frame pose stability",
        "outside every approved swept volume",
        "24-hour drift tests",
        "every keyboard and phone route",
        "zero descent or contact permits",
    ],
)
def test_rejects_missing_acceptance_gate_category(
    tmp_path: Path,
    required_fragment: str,
) -> None:
    def mutate(document: dict[str, Any]) -> None:
        field = "acceptance_gates_to_define_and_measure"
        document[field] = [
            item for item in document[field] if required_fragment not in item
        ]

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(
        CameraArchitecturePlanError,
        match="acceptance_gates_to_define_and_measure",
    ):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    "category",
    [
        "intrinsics",
        "static_extrinsic_and_visibility",
        "tag_map",
        "robot_registration",
        "device_maps",
        "tool_tcp",
    ],
)
def test_rejects_weakened_invalidation_category(
    tmp_path: Path,
    category: str,
) -> None:
    path = _temporary_plan(
        tmp_path,
        lambda document: document["invalidation_triggers"].update(
            {category: ["no invalidation required"]}
        ),
    )
    with pytest.raises(
        CameraArchitecturePlanError,
        match=rf"invalidation_triggers\.{category}",
    ):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize(
    "blockers",
    [[], [""], ["duplicate", "duplicate"]],
)
def test_rejects_empty_invalid_or_duplicate_blockers(
    tmp_path: Path, blockers: list[str]
) -> None:
    path = _temporary_plan(
        tmp_path,
        lambda document: document.update({"open_blockers": blockers}),
    )
    with pytest.raises(CameraArchitecturePlanError, match="open_blockers"):
        load_camera_architecture_plan(tmp_path, path)


@pytest.mark.parametrize("fault", ["height_order", "fov_order", "geometry"])
def test_rejects_unsound_optical_screening(tmp_path: Path, fault: str) -> None:
    def mutate(document: dict[str, Any]) -> None:
        rows = document["optical_screening"][
            "minimum_centered_perpendicular_fov_screen"
        ]
        if fault == "height_order":
            rows[1]["height_mm"] = rows[0]["height_mm"]
        elif fault == "fov_order":
            rows[1]["horizontal_deg"] = rows[0]["horizontal_deg"] + 1.0
        else:
            rows[2]["vertical_deg"] += 2.0

    path = _temporary_plan(tmp_path, mutate)
    with pytest.raises(CameraArchitecturePlanError, match="optical|FOV|coverage"):
        load_camera_architecture_plan(tmp_path, path)


def test_rejects_duplicate_nested_json_key(tmp_path: Path) -> None:
    original = PLAN_PATH.read_text(encoding="utf-8")
    duplicated = original.replace(
        '"planning_authority": true,',
        '"planning_authority": true,\n    "planning_authority": true,',
        1,
    )
    path = tmp_path / "duplicate.json"
    path.write_text(duplicated, encoding="utf-8")

    with pytest.raises(CameraArchitecturePlanError, match="duplicate key"):
        load_camera_architecture_plan(tmp_path, path)


def test_rejects_source_outside_workspace(tmp_path: Path) -> None:
    path = tmp_path / "outside.json"
    path.write_bytes(PLAN_PATH.read_bytes())

    with pytest.raises(CameraArchitecturePlanError, match="beneath the workspace"):
        load_camera_architecture_plan(WORKSPACE, path)
