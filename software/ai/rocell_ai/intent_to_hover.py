"""Continuous, zero-authority request-to-hover simulation composition.

The module connects existing contracts.  It does not define a press recipe,
permit, transport, controller endpoint, or physical writer.  A target-bearing
typing action is admitted through the unchanged v2 CONTACT boundary, while the
mission policy stops at the pre-contact hover point.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Iterable

from rocell.application.context import load_simulation_context
from rocell.application.model_motion_ingress_v2 import (
    MeasuredTargetRegionV2,
    TrustedLocalizationQualificationV2,
    ingest_model_motion_batch_v2,
    revalidate_model_motion_ingress_v2,
)
from rocell.arm.all_joint_command import all_joint_command
from rocell.models import (
    ActionPlan,
    Device,
    Interaction,
    ModelMotionBatchV2,
    ModelMotionProposalV2,
    MotionCapabilityV2,
    MotionEvidenceV2,
    MotionGeometryV2,
    MotionUncertaintyV2,
    Point3Mm,
    PressKey,
    ProposalDevice,
    UncertaintyBoundType,
    decode_model_motion_batch_v2_json,
)

from .first_motion_clearance_waypoints import _solve_seeded, _tip_xyz
from .first_motion_consolidated import _continuous_stage_c
from .first_motion_controller_emulator import (
    InMemoryT102Controller,
    _execute_strict_runtime_path,
    _range_samples,
    load_emulator_fixture,
)
from .first_motion_drills import (
    load_independent_observation_fixture,
    run_independent_observation_drills,
    run_wrong_model_drills,
)
from .cpu_contact_and_ws3 import _load_geometry, load_cpu_contact_fixture
from . import SCHEMA_ID
from .contract import validate_proposal
from .precision_adapter_v2 import PoseModelOutputV2, PrecisionAdapterResultV2
from .precision_observation import build as build_precision
from .scene_observation import canonical_hash
from .visual_observation import MODEL_SCHEMA, validate as validate_prediction


SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
COUNTERS = {
    "hardware_write_count": 0,
    "physical_movement_count": 0,
    "real_command_count": 0,
    "permit_count": 0,
    "transport_count": 0,
}
_HOVER_TARGET = re.compile(
    r"^(?:please\s+)?(?:hover\s+over|move\s+to)\s+(?:the\s+)?(?:key\s+)?"
    r"([A-Za-z0-9][A-Za-z0-9._-]{0,63})\s*[.!]?\s*$",
    re.I,
)


def propose_hover_target(
    *, request_id: str, request: str, observation: dict[str, Any]
) -> dict[str, str]:
    """Parse only the bounded hover grammar without changing the typing policy."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be nonempty")
    if not isinstance(request, str) or not isinstance(observation, dict):
        raise TypeError("request and observation are required")
    observation_ref = observation.get("ref")
    if not isinstance(observation_ref, str) or not observation_ref.strip():
        raise ValueError("observation.ref must be nonempty")
    if observation.get("fresh") is not True:
        raise ValueError("stale observation")
    match = _HOVER_TARGET.fullmatch(request.strip())
    if match is None:
        raise ValueError("request is outside the bounded hover grammar")
    value = {
        "schema": SCHEMA_ID,
        "request_id": request_id,
        "observation_ref": observation_ref,
        "decision": "hover_target",
        "device": "keyboard",
        "target_id": match.group(1).upper(),
    }
    validate_proposal(value)
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(workspace: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else workspace / path


def load_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256", None)
    if claimed != _sha(document):
        raise ValueError("intent-to-hover fixture hash mismatch")
    document["fixture_sha256"] = claimed
    if document.get("schema") != "tactevra.intent_to_hover_fixture.v1":
        raise ValueError("unsupported intent-to-hover fixture")
    if (
        document.get("scope") != SCOPE
        or document.get("physical_authority") is not False
    ):
        raise ValueError("fixture is not zero-authority simulation")
    if any(document["counters"].values()):
        raise ValueError("fixture contains nonzero counters")
    for binding in document["bindings"].values():
        source = _resolve(workspace, binding["path"])
        if _file_sha(source) != binding["sha256"]:
            raise ValueError(f"bound input changed: {binding['path']}")
    return document


def compile_hover_request(
    request: str,
    *,
    request_id: str,
    observation_ref: str,
    commissioned_targets: Iterable[str],
    profile_id: str,
) -> tuple[dict[str, str], ActionPlan]:
    proposal = propose_hover_target(
        request_id=request_id,
        request=request,
        observation={"ref": observation_ref, "fresh": True},
    )
    if proposal["decision"] != "hover_target":
        raise ValueError(
            f"request did not produce HOVER_TARGET: {proposal['decision']}"
        )
    target_id = proposal["target_id"]
    if target_id not in frozenset(commissioned_targets):
        raise ValueError(f"unknown commissioned keyboard target {target_id!r}")
    plan = ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id=profile_id,
        text=request,
        actions=(PressKey(target_id),),
        required_calibrations=("board_fiducials", "keyboard_fixture", "keyboard_tcp"),
    )
    return proposal, plan


def compile_hover_batch(
    target_ids: tuple[str, ...],
    *,
    request_id: str,
    profile_id: str,
) -> ActionPlan:
    if (
        not target_ids
        or len(target_ids) > 64
        or len(set(target_ids)) != len(target_ids)
    ):
        raise ValueError("hover batch targets must be 1..64 unique identifiers")
    return ActionPlan.from_text(
        device=Device.KEYBOARD,
        profile_id=profile_id,
        text="hover-batch:" + ",".join(target_ids),
        actions=tuple(PressKey(target_id) for target_id in target_ids),
        required_calibrations=("board_fiducials", "keyboard_fixture", "keyboard_tcp"),
    )


def _qualification(
    fixture: dict[str, Any],
    target_ids: tuple[str, ...],
    *,
    model_sha256: str,
    catalog_sha256: str,
) -> dict[str, Any]:
    observation = fixture["observation"]
    core = {
        "schema": "rocell.ai_localization_qualification.v0",
        "model_sha256": model_sha256,
        "target_catalog_sha256": catalog_sha256,
        "domain_id": observation["domain_id"],
        "calibration_dataset_sha256": _sha(
            {"fixture": fixture["fixture_sha256"], "split": "synthetic-calibration"}
        ),
        "evaluation_dataset_sha256": _sha(
            {"fixture": fixture["fixture_sha256"], "split": "synthetic-evaluation"}
        ),
        "coverage_probability": observation["coverage_probability"],
        "error_bound_mm": observation["synthetic_fiducial_planar_error_bound_mm"],
        "target_ids": list(target_ids),
        "scope": "SYNTHETIC_OFFLINE_ONLY",
    }
    return {**core, "qualification_sha256": canonical_hash(core)}


def adapt_fiducial_observation(
    fixture: dict[str, Any],
    isaac: dict[str, Any],
    *,
    target_ids: tuple[str, ...],
    catalog: Any,
    now_epoch_ms: int,
) -> PrecisionAdapterResultV2:
    observation = fixture["observation"]
    if isaac.get("schema") != "tactevra.intent_to_hover_isaac_observation.v1":
        raise ValueError("Isaac observation schema mismatch")
    unsigned = dict(isaac)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("Isaac observation receipt hash mismatch")
    if isaac.get("fixture_sha256") != fixture["fixture_sha256"]:
        raise ValueError("Isaac observation uses another fixture")
    visible = frozenset(isaac["visible_fiducial_ids"])
    required = frozenset(
        (*observation["required_world_tags"], observation["required_station_tag"])
    )
    if not required.issubset(visible):
        raise ValueError("fiducial_occluded")
    if float(isaac["tray_shift_mm"]) > float(
        observation["tray_shift_abstain_threshold_mm"]
    ):
        raise ValueError("tray_shifted")
    calibrated_at = int(isaac["calibrated_at_epoch_ms"])
    if now_epoch_ms - calibrated_at > int(observation["maximum_frame_age_ms"]):
        raise ValueError("stale_calibration")

    model_sha = _sha(
        {
            "adapter": "fiducial-plus-catalog-v1",
            "map": fixture["bindings"]["fiducial_map"]["sha256"],
        }
    )
    targets = {
        target_id: {
            "center_board_mm": [
                catalog.keyboard_targets[target_id].center.x,
                catalog.keyboard_targets[target_id].center.y,
                catalog.keyboard_targets[target_id].center.z,
            ]
        }
        for target_id in target_ids
    }
    prediction_core = {
        "schema": MODEL_SCHEMA,
        "frame_id": isaac["frame_id"],
        "device": "keyboard",
        "coordinate_frame": "board",
        "coordinate_unit": "mm",
        "source": "SYNTHETIC_IMAGE_MODEL_PREDICTION",
        "target_catalog_sha256": catalog.content_sha256,
        "image_sha256": isaac["image_sha256"],
        "model_sha256": model_sha,
        "targets": targets,
    }
    prediction = {
        **prediction_core,
        "observation_sha256": canonical_hash(prediction_core),
    }
    validate_prediction(
        prediction, device="keyboard", catalog_sha256=catalog.content_sha256
    )
    qualification = _qualification(
        fixture,
        target_ids,
        model_sha256=model_sha,
        catalog_sha256=catalog.content_sha256,
    )
    precision = build_precision(
        prediction,
        domain_id=observation["domain_id"],
        qualification_sha256=qualification["qualification_sha256"],
    )
    output = PoseModelOutputV2(
        model_id="fiducial-geometry-v1",
        model_sha256=model_sha,
        frame_id=isaac["frame_id"],
        image_sha256=isaac["image_sha256"],
        normalized_pose=(0.0, 0.0, 0.0),
        evaluated_at_epoch_ms=isaac["captured_at_epoch_ms"],
        observation_confidence=0.999,
    )
    return PrecisionAdapterResultV2(
        precision_observation=MappingProxyType(precision),
        qualification=MappingProxyType(qualification),
        evaluation_bundle_sha256=_sha(
            {"fixture": fixture["fixture_sha256"], "kind": "fiducial-exploratory"}
        ),
        model_output=output,
        domain_id=observation["domain_id"],
        required_target_ids=target_ids,
        diagnostics=("synthetic_fiducial_geometry_exploratory",),
    )


def _build_and_ingest(
    fixture: dict[str, Any],
    plan: ActionPlan,
    adapter: PrecisionAdapterResultV2,
    isaac: dict[str, Any],
    *,
    context: Any,
    request_id: str,
    now_epoch_ms: int,
) -> tuple[ModelMotionBatchV2, dict[str, Any], dict[str, Any]]:
    target_ids = tuple(action.key_id for action in plan.actions)
    qualification = dict(adapter.qualification or {})
    precision = dict(adapter.precision_observation)
    config_sha = fixture["motion"]["configuration_id"]
    capability_sha = _sha({"configuration": config_sha, "mode": "HOVER_ONLY"})
    placement_sha = _sha({"isaac": isaac["receipt_sha256"], "source": "fiducials"})
    board_sha = fixture["bindings"]["fiducial_map"]["sha256"]
    capability = MotionCapabilityV2(plan.profile_id, capability_sha)
    geometry = MotionGeometryV2(
        "board_mm_xy_plane_v2",
        "mm",
        board_sha,
        placement_sha,
        context.targets.content_sha256,
    )
    fusion_sha = _sha(
        {
            "fiducial": precision["observation_sha256"],
            "obstruction": isaac["residual_obstruction_sha256"],
        }
    )
    evidence = MotionEvidenceV2(
        capture_id=isaac["capture_id"],
        frame_id=isaac["frame_id"],
        image_sha256=isaac["image_sha256"],
        camera_identity_sha256=isaac["camera_identity_sha256"],
        capture_clock_domain_id="isaac-simulation-clock",
        model_id=adapter.model_output.model_id,
        model_sha256=adapter.model_output.model_sha256,
        scene_observation_sha256=isaac["scene_observation_sha256"],
        precision_observation_sha256=precision["observation_sha256"],
        fusion_decision_sha256=fusion_sha,
        scene_lease_id="intent-hover-scene-lease",
        scene_lease_issuer_id="simulation-only",
        scene_lease_sha256=_sha(
            {"fixture": fixture["fixture_sha256"], "expires": now_epoch_ms + 2_000}
        ),
        captured_at_epoch_ms=isaac["captured_at_epoch_ms"],
        evaluated_at_epoch_ms=isaac["captured_at_epoch_ms"],
        expires_at_epoch_ms=now_epoch_ms + 2_000,
    )
    uncertainty = MotionUncertaintyV2(
        UncertaintyBoundType.PLANAR_L2_DISK,
        qualification["error_bound_mm"],
        qualification["coverage_probability"],
        qualification["qualification_sha256"],
        adapter.evaluation_bundle_sha256,
        qualification["domain_id"],
        target_ids,
    )
    proposals = tuple(
        ModelMotionProposalV2(
            proposal_id=f"hover-{index}",
            action_index=index,
            device=ProposalDevice.KEYBOARD,
            target_id=target_id,
            target=Point3Mm(
                "board",
                *precision["prediction"]["targets"][target_id]["center_board_mm"],
            ),
            interaction=Interaction.CONTACT,
            observation_confidence=0.999,
        )
        for index, target_id in enumerate(target_ids)
    )
    batch = ModelMotionBatchV2(
        batch_id="hover-" + request_id,
        request_id=request_id,
        intent_plan_sha256=plan.plan_hash,
        device=ProposalDevice.KEYBOARD,
        capability=capability,
        geometry=geometry,
        evidence=evidence,
        uncertainty=uncertainty,
        proposals=proposals,
    )
    decoded = decode_model_motion_batch_v2_json(_canonical(batch.to_dict()))
    regions = {}
    for target_id in target_ids:
        region = context.targets.keyboard_targets[target_id]
        left, front, right, rear = region.safe_rectangle_board_mm
        regions[target_id] = MeasuredTargetRegionV2(
            target_id=target_id,
            coordinate_frame="board",
            coordinate_profile="board_mm_xy_plane_v2",
            board_frame_definition_sha256=board_sha,
            vertices_xy_mm=((left, front), (right, front), (right, rear), (left, rear)),
            surface_z_mm=region.center.z,
            surface_normal_error_bound_mm=0.05,
            placement_error_bound_mm=0.1,
            placement_observation_sha256=placement_sha,
            target_catalog_sha256=context.targets.content_sha256,
        )
    trusted = TrustedLocalizationQualificationV2(
        qualification_sha256=qualification["qualification_sha256"],
        model_id=evidence.model_id,
        model_sha256=evidence.model_sha256,
        evidence_method_sha256=adapter.evaluation_bundle_sha256,
        domain_id=qualification["domain_id"],
        target_catalog_sha256=context.targets.content_sha256,
        bound_type=UncertaintyBoundType.PLANAR_L2_DISK,
        error_bound_mm=qualification["error_bound_mm"],
        coverage_probability=qualification["coverage_probability"],
        target_ids=target_ids,
    )
    ingress = ingest_model_motion_batch_v2(
        decoded,
        plan,
        context,
        current_time_epoch_ms=now_epoch_ms,
        current_monotonic_ns=5_000_000_000,
        maximum_scene_age_ms=fixture["observation"]["maximum_frame_age_ms"],
        trusted_scene_lease_expires_at_epoch_ms=now_epoch_ms + 2_000,
        expected_capability_profile_id=capability.profile_id,
        expected_capability_profile_sha256=capability.profile_sha256,
        expected_capture_id=evidence.capture_id,
        expected_frame_id=evidence.frame_id,
        expected_image_sha256=evidence.image_sha256,
        expected_capture_clock_domain_id=evidence.capture_clock_domain_id,
        expected_camera_identity_sha256=evidence.camera_identity_sha256,
        expected_scene_lease_id=evidence.scene_lease_id,
        expected_scene_lease_issuer_id=evidence.scene_lease_issuer_id,
        expected_scene_lease_sha256=evidence.scene_lease_sha256,
        expected_scene_observation_sha256=evidence.scene_observation_sha256,
        expected_precision_observation_sha256=evidence.precision_observation_sha256,
        expected_fusion_decision_sha256=evidence.fusion_decision_sha256,
        expected_placement_observation_sha256=placement_sha,
        expected_board_frame_definition_sha256=board_sha,
        trusted_qualification=trusted,
        measured_target_regions=regions,
        minimum_observation_confidence=0.95,
    )
    fresh = revalidate_model_motion_ingress_v2(
        ingress,
        current_monotonic_ns=5_100_000_000,
        expected_capability_profile_sha256=capability.profile_sha256,
        active_scene_lease_sha256=evidence.scene_lease_sha256,
        active_placement_observation_sha256=placement_sha,
        active_target_catalog_sha256=context.targets.content_sha256,
    )
    return decoded, ingress, fresh


def _five(values: Iterable[float]) -> tuple[float, ...]:
    result = tuple(float(value) for value in values)
    if len(result) != 5:
        raise ValueError("five arm joints required")
    return result


def _refine_tip_solution(
    world: Any,
    joints: tuple[float, ...],
    target: tuple[float, float, float],
    tool_length_mm: float,
) -> tuple[float, ...]:
    """Numerically tighten an already-converged governed IK result."""
    import numpy as np
    from scipy.optimize import least_squares

    start = np.asarray(joints[:4], dtype=float)
    roll = float(joints[4])
    lower = np.asarray([-3.1416, -1.5708, -1.0, -1.5708])
    upper = np.asarray([3.1416, 1.5708, 2.95, 1.5708])

    def residual(value: Any) -> Any:
        tip = _tip_xyz(world, (*value.tolist(), roll), tool_length_mm)
        return np.asarray(tip, dtype=float) - np.asarray(target, dtype=float)

    solved = least_squares(
        residual,
        start,
        bounds=(lower, upper),
        xtol=1e-13,
        ftol=1e-13,
        gtol=1e-13,
        max_nfev=200,
    )
    refined = (*solved.x.tolist(), roll)
    if math.dist(_tip_xyz(world, refined, tool_length_mm), target) > 0.01:
        raise ValueError(
            "governed IK refinement did not reach the frozen hover tolerance"
        )
    return tuple(float(value) for value in refined)


def _plan_hover_joints(
    fixture: dict[str, Any],
    target_ids: tuple[str, ...],
    *,
    workspace: Path,
) -> tuple[list[dict[str, Any]], Any, dict[str, Any], tuple[float, ...]]:
    consolidated_path = _resolve(
        workspace, fixture["bindings"]["first_motion_configuration"]["path"]
    )
    consolidated = json.loads(consolidated_path.read_text(encoding="utf-8"))
    contact_path = _resolve(
        workspace, consolidated["bindings"]["cpu_contact_fixture"]["path"]
    )
    contact_fixture = load_cpu_contact_fixture(contact_path, workspace=workspace)
    _, pose_family, world = _load_geometry(contact_fixture, workspace=workspace)
    park_path = _resolve(workspace, consolidated["bindings"]["park_screen"]["path"])
    park_screen = json.loads(park_path.read_text(encoding="utf-8"))
    park_row = next(
        row for row in park_screen["top_candidates"] if row["pose_id"] == "halton-0573"
    )
    park = tuple(
        park_row["joint_positions_rad"][name]
        for name in world.pose_bundle["joint_order"]
    )
    pose_by_id = {
        row["target_id"]: row
        for row in pose_family["profiles"][0]["pose_bundle"]["poses"]
    }
    length = float(fixture["motion"]["tool_length_mm"])
    transit_z = float(fixture["motion"]["transit_height_board_z_mm"])
    hover_mm = float(fixture["motion"]["hover_height_mm"])
    current = _five(park)
    current_tip = _tip_xyz(world, current, length)
    rows: list[dict[str, Any]] = []
    for action_index, target_id in enumerate(target_ids):
        contact = pose_by_id[target_id]["contact_target_board_mm"]
        hover = (
            float(contact["x"]),
            float(contact["y"]),
            float(contact["z"]) + hover_mm,
        )
        points = (
            (current_tip[0], current_tip[1], max(transit_z, current_tip[2], hover[2])),
            (hover[0], hover[1], max(transit_z, current_tip[2], hover[2])),
            hover,
        )
        phases = ("RISE", "TRANSIT", "DESCEND_TO_HOVER")
        for phase, point in zip(phases, points, strict=True):
            solved = _solve_seeded(world, world.solver(length), point, current)
            if solved is None:
                raise ValueError(f"IK failed for {target_id} {phase}")
            solved = _refine_tip_solution(world, _five(solved), point, length)
            achieved = _tip_xyz(world, solved, length)
            rows.append(
                {
                    "action_index": action_index,
                    "target_id": target_id,
                    "phase": phase,
                    "requested_tip_board_mm": list(point),
                    "runtime_tip_board_mm": list(achieved),
                    "joint_positions_rad": list(solved),
                    "position_error_mm": math.dist(point, achieved),
                }
            )
            current = _five(solved)
        current_tip = _tip_xyz(world, current, length)
    return rows, world, consolidated, park


def _emulate_and_replay(
    fixture: dict[str, Any],
    joint_rows: list[dict[str, Any]],
    world: Any,
    park: tuple[float, ...],
    *,
    workspace: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    emulator = load_emulator_fixture(
        _resolve(workspace, fixture["bindings"]["controller_emulator_fixture"]["path"])
    )
    sample = _range_samples(emulator["controller_emulator"])[0]
    initial = (*park, 0.75)
    controller = InMemoryT102Controller(initial, sample, seed=20261010)
    encoded = []
    replay_rows = []
    try:
        import mujoco
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("bound MuJoCo environment is required") from exc
    model = mujoco.MjModel.from_xml_path(
        str(_resolve(workspace, fixture["bindings"]["robot_mjcf"]["path"]))
    )
    data = mujoco.MjData(model)
    hand_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "hand_tcp")
    profile = json.loads(
        _resolve(workspace, fixture["bindings"]["virtual_profile"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    board_t_world = np.asarray(
        profile["study_input"]["derived_solver_transform"]["matrix_row_major"],
        dtype=float,
    ).reshape(4, 4)
    length = float(fixture["motion"]["tool_length_mm"])
    maximum_delta = 0.0
    maximum_telemetry_delta = 0.0
    command_sequence = 0
    for row in joint_rows:
        requested = _five(row["joint_positions_rad"])
        command = all_joint_command(
            (*requested, 0.75),
            speed=sample.speed_setting,
            acceleration=sample.acceleration_setting,
        )
        plant, runtime, frame = _execute_strict_runtime_path(
            emulator,
            controller,
            command,
            case_id=f"intent-hover:{command_sequence}",
        )
        if runtime["runtime_status"] != "TERMINAL_NO_RETRY":
            raise ValueError("controller emulator did not terminate without retry")
        encoded.append(
            {
                "sequence": command_sequence,
                "action_index": row["action_index"],
                "target_id": row["target_id"],
                "phase": row["phase"],
                "wire_sha256": hashlib.sha256(frame.wire_bytes).hexdigest(),
                "wire_length": len(frame.wire_bytes),
                "t102_decoded": command,
                "runtime_report_sha256": runtime["runtime_report_sha256"],
            }
        )
        command_sequence += 1
        measured = tuple(float(v) for v in plant["measured_joints_rad"])
        commanded = tuple(float(v) for v in plant["target_joints_rad"])
        runtime_tip = _tip_xyz(world, commanded[:5], length)
        telemetry_tip = _tip_xyz(world, measured[:5], length)
        telemetry_delta = math.dist(runtime_tip, telemetry_tip)
        maximum_telemetry_delta = max(maximum_telemetry_delta, telemetry_delta)
        data.qpos[:] = commanded
        mujoco.mj_forward(model, data)
        position = np.asarray(data.xpos[hand_id], dtype=float) * 1000.0
        rotation = np.asarray(data.xmat[hand_id], dtype=float).reshape(3, 3)
        tip_world = position + rotation @ np.asarray([0.0, 0.0, -length])
        tip_board = (board_t_world @ np.concatenate((tip_world, [1.0])))[:3]
        delta = float(np.linalg.norm(tip_board - np.asarray(runtime_tip)))
        maximum_delta = max(maximum_delta, delta)
        replay_rows.append(
            {
                **{key: row[key] for key in ("action_index", "target_id", "phase")},
                "commanded_joints_rad": list(commanded),
                "measured_joints_rad": list(measured),
                "runtime_tip_board_mm": list(runtime_tip),
                "telemetry_tip_board_mm": list(telemetry_tip),
                "telemetry_vs_command_tip_error_mm": telemetry_delta,
                "mujoco_tip_board_mm": tip_board.tolist(),
                "mujoco_vs_runtime_tip_error_mm": delta,
            }
        )
    return replay_rows, {
        "encoded_commands": encoded,
        "encoded_command_count": len(encoded),
        "maximum_mujoco_vs_runtime_tip_error_mm": maximum_delta,
        "maximum_telemetry_vs_command_tip_error_mm": maximum_telemetry_delta,
        "ground_truth_semantics": "NOMINAL_DECODED_COMMAND_REPLAY",
        "real_transport_open_count": controller.transport_open_count,
        "hardware_write_count": controller.hardware_write_count,
        "physical_movement_count": controller.physical_movement_count,
        "physical_authority": controller.physical_authority,
    }


def _final_confirmations(
    target_ids: tuple[str, ...],
    replay: list[dict[str, Any]],
    context: Any,
    isaac: dict[str, Any],
    uncertainty_mm: float,
) -> list[dict[str, Any]]:
    endpoints = [row for row in replay if row["phase"] == "DESCEND_TO_HOVER"]
    if len(endpoints) != len(target_ids):
        raise ValueError("hover endpoint count differs from target order")
    confirmations = []
    projected = {row["target_id"]: row for row in isaac["target_projections"]}
    for target_id, endpoint in zip(target_ids, endpoints, strict=True):
        region = context.targets.keyboard_targets[target_id]
        tip = endpoint["mujoco_tip_board_mm"]
        xy_error = math.hypot(tip[0] - region.center.x, tip[1] - region.center.y)
        left, front, right, rear = region.safe_rectangle_board_mm
        inside = (
            left + uncertainty_mm <= tip[0] <= right - uncertainty_mm
            and front + uncertainty_mm <= tip[1] <= rear - uncertainty_mm
        )
        projection = projected[target_id]
        confirmations.append(
            {
                "target_id": target_id,
                "tool_tip_board_mm": tip,
                "target_center_board_mm": [
                    region.center.x,
                    region.center.y,
                    region.center.z,
                ],
                "ground_truth_xy_error_mm": xy_error,
                "uncertainty_disk_inside_safe_region": inside,
                "rendered_projection_inside_safe_region": projection[
                    "tool_projection_inside_safe_region"
                ],
                "rendered_tool_tip_pixel": projection["tool_tip_pixel"],
                "rendered_safe_polygon_pixel": projection["safe_polygon_pixel"],
            }
        )
    return confirmations


def _negative_cases(
    fixture: dict[str, Any],
    isaac: dict[str, Any],
    context: Any,
    *,
    now_epoch_ms: int,
) -> list[dict[str, str]]:
    target_ids = ("H",)
    cases = []
    variants = {
        "FIDUCIAL_OCCLUDED": {
            **isaac,
            "visible_fiducial_ids": ["T0", "T1", "T2", "K0"],
        },
        "TRAY_SHIFTED": {
            **isaac,
            "tray_shift_mm": fixture["observation"]["tray_shift_abstain_threshold_mm"]
            + 0.1,
        },
        "STALE_CALIBRATION": {
            **isaac,
            "calibrated_at_epoch_ms": now_epoch_ms
            - fixture["observation"]["stale_calibration_age_ms"],
        },
    }
    for case_id, value in variants.items():
        unsigned = dict(value)
        unsigned.pop("receipt_sha256", None)
        value["receipt_sha256"] = _sha(unsigned)
        try:
            adapt_fiducial_observation(
                fixture,
                value,
                target_ids=target_ids,
                catalog=context.targets,
                now_epoch_ms=now_epoch_ms,
            )
        except ValueError as exc:
            cases.append(
                {
                    "case_id": case_id,
                    "stage": "FIDUCIAL_PRECISION_ADAPTER",
                    "reason": str(exc),
                }
            )
        else:
            raise ValueError(f"{case_id} was falsely accepted")
    try:
        compile_hover_request(
            "Hover over UNKNOWNKEY",
            request_id="negative-unknown",
            observation_ref="negative",
            commissioned_targets=context.targets.keyboard_targets,
            profile_id=context.targets.keyboard_semantic_profile_id,
        )
    except ValueError as exc:
        cases.append(
            {
                "case_id": "UNKNOWN_KEY",
                "stage": "DETERMINISTIC_COMPILER",
                "reason": str(exc),
            }
        )
    else:
        raise ValueError("unknown key was falsely accepted")
    obstructed = isaac["residual_scores"]["obstructed_H"]
    if float(obstructed) < float(fixture["residual_obstruction"]["threshold"]):
        raise ValueError("obstruction positive control was falsely accepted")
    cases.append(
        {
            "case_id": "TARGET_OBSTRUCTED",
            "stage": "RESIDUAL_OBSTRUCTION",
            "reason": "score_at_or_above_threshold",
        }
    )
    return cases


def run(
    fixture: dict[str, Any],
    isaac: dict[str, Any],
    *,
    workspace: Path,
    context_workspace: Path | None = None,
) -> dict[str, Any]:
    context_root = (context_workspace or workspace).resolve()
    context = load_simulation_context(
        context_root, context_root / "software/config/system_manifest.json"
    )
    all_targets = tuple(context.targets.keyboard_targets)
    if len(all_targets) != fixture["positive_scenarios"]["all_target_count"]:
        raise ValueError(
            "active simulation catalog is not the frozen 51-target candidate"
        )
    now = int(isaac["captured_at_epoch_ms"]) + 100
    threshold = float(fixture["residual_obstruction"]["threshold"])
    if any(
        float(isaac["residual_scores"][f"clear_{target}"]) >= threshold
        for target in all_targets
    ):
        raise ValueError("clear target failed residual obstruction check")
    consolidated = json.loads(
        _resolve(
            workspace, fixture["bindings"]["first_motion_configuration"]["path"]
        ).read_text(encoding="utf-8")
    )
    contact_fixture = load_cpu_contact_fixture(
        _resolve(workspace, consolidated["bindings"]["cpu_contact_fixture"]["path"]),
        workspace=workspace,
    )
    clearance = _continuous_stage_c(contact_fixture, consolidated, workspace=workspace)
    if clearance["stop_count"]:
        raise ValueError("swept collision screen stopped hover planning")
    scenarios = []
    plans = []
    for index, target_id in enumerate(fixture["positive_scenarios"]["single_targets"]):
        intent, plan = compile_hover_request(
            f"Hover over {target_id}",
            request_id=f"single-{index}",
            observation_ref=isaac["frame_id"],
            commissioned_targets=all_targets,
            profile_id=context.targets.keyboard_semantic_profile_id,
        )
        plans.append((f"single-{target_id}", intent, plan))
    batch_plan = compile_hover_batch(
        all_targets,
        request_id="all-51",
        profile_id=context.targets.keyboard_semantic_profile_id,
    )
    plans.append(
        ("all-51", {"decision": "hover_target_batch", "target_count": 51}, batch_plan)
    )
    for scenario_id, intent, plan in plans:
        target_ids = tuple(action.key_id for action in plan.actions)
        adapter = adapt_fiducial_observation(
            fixture,
            isaac,
            target_ids=target_ids,
            catalog=context.targets,
            now_epoch_ms=now,
        )
        batch, ingress, fresh = _build_and_ingest(
            fixture,
            plan,
            adapter,
            isaac,
            context=context,
            request_id=scenario_id,
            now_epoch_ms=now,
        )
        joint_rows, world, consolidated, park = _plan_hover_joints(
            fixture,
            target_ids,
            workspace=workspace,
        )
        replay, controller = _emulate_and_replay(
            fixture,
            joint_rows,
            world,
            park,
            workspace=workspace,
        )
        confirmations = _final_confirmations(
            target_ids,
            replay,
            context,
            isaac,
            float(adapter.qualification["error_bound_mm"]),
        )
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "intent": intent,
                "ordered_target_ids": list(target_ids),
                "plan_sha256": plan.plan_hash,
                "precision_observation_sha256": adapter.precision_observation[
                    "observation_sha256"
                ],
                "batch_sha256": batch.batch_sha256,
                "ingress_sha256": ingress["ingress_sha256"],
                "preplanner_gate_sha256": fresh["preplanner_gate_sha256"],
                "joint_waypoint_count": len(joint_rows),
                "swept_collision_minimum_clearance_mm": clearance[
                    "minimum_key_clearance_mm"
                ],
                "controller": controller,
                "hover_confirmations": confirmations,
                "maximum_ground_truth_xy_error_mm": max(
                    row["ground_truth_xy_error_mm"] for row in confirmations
                ),
                "contact_sample_count": 0,
                "descent_below_hover_count": 0,
                "decision": "PASS_END_TO_END_HOVER_SIMULATION"
                if (
                    all(
                        row["uncertainty_disk_inside_safe_region"]
                        and row["rendered_projection_inside_safe_region"]
                        for row in confirmations
                    )
                    and max(row["ground_truth_xy_error_mm"] for row in confirmations)
                    <= fixture["motion"]["maximum_ground_truth_xy_error_mm"]
                    and controller["maximum_mujoco_vs_runtime_tip_error_mm"]
                    <= fixture["motion"]["maximum_mujoco_vs_runtime_tip_error_mm"]
                )
                else "FAIL_HOVER_CONFIRMATION",
            }
        )
    negatives = _negative_cases(fixture, isaac, context, now_epoch_ms=now)
    observation_fixture = load_independent_observation_fixture(
        _resolve(workspace, fixture["bindings"]["independent_observer_fixture"]["path"])
    )
    first_motion = json.loads(
        _resolve(
            workspace, fixture["bindings"]["first_motion_configuration"]["path"]
        ).read_text(encoding="utf-8")
    )
    readiness_path = _resolve(
        workspace, first_motion["bindings"]["readiness_fixture"]["path"]
    )
    from .first_motion_controller_emulator import load_first_motion_fixture

    readiness = load_first_motion_fixture(readiness_path)
    wrong = run_wrong_model_drills(readiness)
    observers = run_independent_observation_drills(observation_fixture, wrong)
    all_pass = (
        len(negatives) == 5
        and observers["undetected_consequential_count"] == 0
        and all(
            row["decision"] == "PASS_END_TO_END_HOVER_SIMULATION" for row in scenarios
        )
    )
    result = {
        "schema": "tactevra.intent_to_hover_result.v1",
        "scope": SCOPE,
        "fixture_sha256": fixture["fixture_sha256"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "negative_cases": negatives,
        "negative_correct_abstention_count": len(negatives),
        "wrong_model_drills": {
            "input_gap_count": len(wrong["gaps"]),
            "undetected_consequential_count": observers[
                "undetected_consequential_count"
            ],
            "decision": observers["decision"],
        },
        "isaac_observation_receipt_sha256": isaac["receipt_sha256"],
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "real_command_count": 0,
        "permit_count": 0,
        "transport_count": 0,
        "physical_authority": False,
        "decision": "PASS_CONTINUOUS_INTENT_TO_HOVER_SIMULATION"
        if all_pass
        else "FAIL_CONTINUOUS_INTENT_TO_HOVER_SIMULATION",
        "limitations": fixture["limitations"],
    }
    return {**result, "receipt_sha256": _sha(result)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--isaac-observation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--context-workspace", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    fixture = load_fixture(args.fixture, workspace=workspace)
    isaac = json.loads(args.isaac_observation.read_text(encoding="utf-8"))
    result = run(
        fixture,
        isaac,
        workspace=workspace,
        context_workspace=args.context_workspace,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "decision": result["decision"],
                "receipt_sha256": result["receipt_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["decision"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
