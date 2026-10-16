"""Offline bridge from model coordinates to a screened nominal motion request.

This module deliberately stops before IK-to-controller compilation because the
physical calibration registry and controller-frame correlation are not commissioned.
It never imports a transport and cannot write to hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from rocell.models import Interaction, ModelMotionProposal, Point3Mm
from rocell.targets import NominalTargetCatalog, load_nominal_target_catalog


class ModelMotionBridgeError(ValueError):
    """A valid model proposal cannot enter the deterministic planning boundary."""


_RETAINED_SESSION = Path("software/config/live_camera_feedback_session_20261015.json")
_RETAINED_OVERLAY = Path("software/ai/eval/b0477_keyboard_overlay_20261016.json")
_TOOL_PROFILES = Path("software/config/tool_attachment_profiles.json")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_without_duplicate_keys,
        parse_constant=lambda item: (_ for _ in ()).throw(
            ModelMotionBridgeError(f"nonfinite JSON constant {item!r}")
        ),
    )
    if not isinstance(value, Mapping):
        raise ModelMotionBridgeError(f"{path} must contain a JSON object")
    return value


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelMotionBridgeError(f"{label} must be an object")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelMotionBridgeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ModelMotionBridgeError(f"{label} must be finite")
    return result


def compile_retained_keyboard_hover_draft(
    workspace: Path,
    target_id: str,
    *,
    expected_workcell_epoch_id: str,
    expected_attachment_profile: str = "BARE_JAW",
    expected_overlay_sha256: str | None = None,
    expected_reference_frame_sha256: str | None = None,
    interaction: Interaction | str = Interaction.HOVER,
) -> dict[str, Any]:
    """Bind the retained keyboard observation into an unsent HOVER draft.

    This is deliberately a pre-ingress artifact.  Retained evidence has no
    freshness lease, arm-to-board correlation, qualified TCP, IK result, or
    route screening, so the result cannot be admitted or encoded for a
    controller.  The function reads files only and imports no transport.
    """

    root = Path(workspace)
    session_path = root / _RETAINED_SESSION
    overlay_path = root / _RETAINED_OVERLAY
    tool_profiles_path = root / _TOOL_PROFILES
    session = _read_json(session_path)
    overlay = _read_json(overlay_path)
    tool_profiles = _read_json(tool_profiles_path)

    try:
        requested_interaction = Interaction(interaction)
    except ValueError as exc:
        raise ModelMotionBridgeError("retained draft interaction is invalid") from exc
    if requested_interaction is not Interaction.HOVER:
        raise ModelMotionBridgeError("retained draft permits HOVER only; descent/contact is blocked")

    epoch = _mapping(session.get("workcell_epoch"), "session workcell_epoch")
    epoch_id = epoch.get("epoch_id")
    if epoch_id != expected_workcell_epoch_id:
        raise ModelMotionBridgeError("retained workcell epoch is stale or mismatched")
    if overlay.get("workcell_epoch_id") != epoch_id:
        raise ModelMotionBridgeError("overlay and session workcell epochs differ")

    camera = _mapping(session.get("camera_baseline"), "session camera_baseline")
    overlay_binding = _mapping(camera.get("keyboard_overlay"), "session keyboard_overlay")
    overlay_sha256 = _file_sha256(overlay_path)
    if overlay_binding.get("artifact_sha256") != overlay_sha256:
        raise ModelMotionBridgeError("session keyboard overlay hash is not the retained artifact")
    if expected_overlay_sha256 is not None and expected_overlay_sha256 != overlay_sha256:
        raise ModelMotionBridgeError("expected keyboard overlay hash is stale or mismatched")
    if overlay.get("status") != "READ_ONLY_IMAGE_OVERLAY_REVIEWED_NOT_MOTION_AUTHORITY":
        raise ModelMotionBridgeError("overlay is not in the reviewed read-only state")

    inputs = _mapping(overlay.get("inputs"), "overlay inputs")
    reference_frame = _mapping(inputs.get("reference_frame"), "overlay reference frame")
    frame_sha256 = reference_frame.get("sha256")
    if frame_sha256 != overlay_binding.get("reference_frame_sha256"):
        raise ModelMotionBridgeError("retained frame hash differs between session and overlay")
    if expected_reference_frame_sha256 is not None \
            and expected_reference_frame_sha256 != frame_sha256:
        raise ModelMotionBridgeError("expected retained frame hash is stale or mismatched")

    bound_files = {
        "annotation_sha256": root / str(inputs.get("annotation_path")),
        "board_registration_sha256": root / str(inputs.get("board_registration_path")),
        "target_profile_sha256": root / str(inputs.get("target_profile_path")),
    }
    for digest_field, path in bound_files.items():
        if not path.is_file() or inputs.get(digest_field) != _file_sha256(path):
            raise ModelMotionBridgeError(f"overlay {digest_field} is stale or mismatched")
    board_registration_sha256 = str(inputs["board_registration_sha256"])
    registration = _mapping(camera.get("fixed_board_planar_registration"),
                            "session board registration")
    if registration.get("artifact_sha256") != board_registration_sha256:
        raise ModelMotionBridgeError("session and overlay board registrations differ")

    arm = _mapping(session.get("arm_baseline"), "session arm_baseline")
    if arm.get("attachment_profile") != expected_attachment_profile:
        raise ModelMotionBridgeError("active attachment profile is stale or mismatched")
    if expected_attachment_profile != "BARE_JAW":
        raise ModelMotionBridgeError("retained keyboard draft is qualified only for BARE_JAW")
    profile_id = arm.get("profile_id")
    profiles = tool_profiles.get("profiles")
    if not isinstance(profiles, list):
        raise ModelMotionBridgeError("tool attachment profiles must be an array")
    selected = next((item for item in profiles if isinstance(item, Mapping)
                     and item.get("profile_id") == profile_id), None)
    if selected is None or selected.get("attachment_profile") != expected_attachment_profile:
        raise ModelMotionBridgeError("active tool profile is missing or belongs to another attachment")
    if selected.get("contact_authorized") is not False:
        raise ModelMotionBridgeError("retained draft requires a noncontact tool profile")
    tool_profiles_sha256 = _file_sha256(tool_profiles_path)
    selected_profile_sha256 = hashlib.sha256(_canonical(selected)).hexdigest()

    geometry = _mapping(overlay.get("keyboard_geometry"), "overlay keyboard_geometry")
    targets = _mapping(geometry.get("projected_targets"), "overlay projected_targets")
    if geometry.get("target_count") != 46 or len(targets) != 46:
        raise ModelMotionBridgeError("retained overlay must contain all 46 reviewed targets")
    target = _mapping(targets.get(target_id), f"overlay target {target_id!r}")
    local_xy = target.get("image_fitted_center_keyboard_xy_mm")
    if not isinstance(local_xy, list) or len(local_xy) != 2:
        raise ModelMotionBridgeError("retained target lacks an image-fitted center")
    local_x = _number(local_xy[0], "target local x")
    local_y = _number(local_xy[1], "target local y")
    housing = geometry.get("housing_dimensions_mm")
    if not isinstance(housing, list) or len(housing) != 3:
        raise ModelMotionBridgeError("keyboard housing dimensions are missing")
    if not 0.0 <= local_x <= _number(housing[0], "housing width") \
            or not 0.0 <= local_y <= _number(housing[1], "housing depth"):
        raise ModelMotionBridgeError("retained target lies outside the keyboard housing")

    translation = overlay_binding.get("dimension_constrained_front_left_board_xy_mm")
    if not isinstance(translation, list) or len(translation) != 2:
        raise ModelMotionBridgeError("keyboard board translation is missing")
    yaw_deg = _number(overlay_binding.get("dimension_constrained_yaw_deg"), "keyboard yaw")
    yaw = math.radians(yaw_deg)
    board_x = _number(translation[0], "keyboard board x") \
        + math.cos(yaw) * local_x - math.sin(yaw) * local_y
    board_y = _number(translation[1], "keyboard board y") \
        + math.sin(yaw) * local_x + math.cos(yaw) * local_y

    target_catalog = _read_json(bound_files["target_profile_sha256"])
    keyboard_profile = _mapping(target_catalog.get("keyboard"), "target keyboard profile")
    surface_z = _number(keyboard_profile.get("target_plane_z_board_mm"),
                        "keyboard target plane z")
    planar_review_bound = _number(overlay_binding.get("additive_review_bound_mm"),
                                  "overlay additive review bound")
    jaw_uncertainty = _number(arm.get("rigid_jaw_clearance_uncertainty_mm"),
                              "jaw clearance uncertainty")
    clearance = round(planar_review_bound + jaw_uncertainty, 4)

    bindings = {
        "workcell_epoch_id": epoch_id,
        "retained_frame_sha256": frame_sha256,
        "overlay_sha256": overlay_sha256,
        "annotation_sha256": inputs["annotation_sha256"],
        "board_registration_sha256": board_registration_sha256,
        "target_catalog_sha256": inputs["target_profile_sha256"],
        "tool_profiles_sha256": tool_profiles_sha256,
        "selected_tool_profile_sha256": selected_profile_sha256,
        "attachment_profile": expected_attachment_profile,
        "profile_id": profile_id,
    }
    proposal_seed = hashlib.sha256(_canonical({"bindings": bindings,
                                               "target_id": target_id})).hexdigest()
    proposal = ModelMotionProposal.from_mapping({
        "schema": "rocell.model_motion_proposal.v1",
        "proposal_id": f"retained-hover-{target_id.lower()}-{proposal_seed[:16]}",
        "device": "keyboard",
        "target_id": target_id,
        "coordinate_frame": "board",
        "target_mm": {"x": board_x, "y": board_y, "z": surface_z},
        "interaction": "HOVER",
        "approach_clearance_mm": clearance,
        "speed_class": "SLOW",
        "confidence": 0.0,
        "source": {
            "model_id": "retained-reviewed-image-centers-v1",
            "frame_id": Path(str(reference_frame.get("path"))).name,
            "image_sha256": frame_sha256,
        },
    })
    hover = {"frame": "board", "x": board_x, "y": board_y,
             "z": surface_z + clearance}
    report: dict[str, Any] = {
        "schema": "rocell.retained_keyboard_hover_draft.v1",
        "status": "UNSENT_RETAINED_EVIDENCE_HOVER_DRAFT_BLOCKED_FROM_INGRESS",
        "bindings": bindings,
        "proposal": proposal.to_dict(),
        "proposal_sha256": proposal.proposal_sha256,
        "requested_waypoints": [{"phase": "HOVER_DESTINATION", "point_mm": hover}],
        "clearance": {
            "approach_clearance_mm": clearance,
            "overlay_planar_review_bound_mm": planar_review_bound,
            "jaw_clearance_uncertainty_mm": jaw_uncertainty,
            "rule": "ADDITIVE_REVIEW_BOUND_PLUS_JAW_CLEARANCE_UNCERTAINTY",
        },
        "admission_blockers": [
            "Retained frame has no current freshness lease",
            "Camera-to-board mapping is planar and has no qualified Z calibration",
            "Board-to-arm transform and bare-jaw TCP are not commissioned for this target",
            "No inverse kinematics, route, collision, or controller dispatch checks ran",
        ],
        "next_required_gate": "CALIBRATED_BARE_JAW_ROUTE_SCREENING_WITHOUT_DISPATCH",
        "controller_commands": [],
        "transport_writes": 0,
        "hardware_access": False,
        "physical_authority": False,
        "descent_authorized": False,
        "contact_authorized": False,
        "autonomous_retry_authorized": False,
    }
    return {**report, "draft_sha256": hashlib.sha256(_canonical(report)).hexdigest()}


def _board_target(
    proposal: ModelMotionProposal,
    catalog: NominalTargetCatalog,
) -> Point3Mm:
    if proposal.target.frame == "board":
        return proposal.target
    return catalog.local_to_board(proposal.target, device=proposal.device.value)


def compile_model_motion_proposal(
    proposal: ModelMotionProposal,
    catalog: NominalTargetCatalog,
    *,
    minimum_confidence: float = 0.9,
    plane_tolerance_mm: float = 1e-6,
) -> dict[str, Any]:
    """Validate one model coordinate against the frozen nominal device map.

    The resulting waypoints are board-frame planning requests. They are not joint
    targets or controller commands. A later calibrated planner may consume this
    artifact without allowing the model to access the transport.
    """

    if not isinstance(proposal, ModelMotionProposal):
        raise TypeError("proposal must be a ModelMotionProposal")
    if not isinstance(catalog, NominalTargetCatalog):
        raise TypeError("catalog must be a NominalTargetCatalog")
    if isinstance(minimum_confidence, bool) or not isinstance(minimum_confidence, (int, float)):
        raise TypeError("minimum_confidence must be numeric")
    threshold = float(minimum_confidence)
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("minimum_confidence must be in [0, 1]")
    if proposal.confidence < threshold:
        raise ModelMotionBridgeError(
            f"proposal confidence {proposal.confidence} is below {threshold}"
        )

    nominal = catalog.resolve(proposal.device.value, proposal.target_id)
    board = _board_target(proposal, catalog)
    left, front, right, rear = nominal.safe_rectangle_board_mm
    if not (left <= board.x <= right and front <= board.y <= rear):
        raise ModelMotionBridgeError(
            "model coordinate is outside the named target's nominal safe rectangle"
        )
    if abs(board.z - nominal.center.z) > plane_tolerance_mm:
        raise ModelMotionBridgeError(
            "model coordinate does not lie on the named target's nominal surface plane"
        )

    surface = {"frame": "board", "x": board.x, "y": board.y, "z": board.z}
    hover = {
        "frame": "board",
        "x": board.x,
        "y": board.y,
        "z": board.z + proposal.approach_clearance_mm,
    }
    if proposal.interaction is Interaction.HOVER:
        waypoints = [{"phase": "HOVER_DESTINATION", "point_mm": hover}]
    else:
        waypoints = [
            {"phase": "APPROACH", "point_mm": hover},
            {"phase": "CONTACT_CANDIDATE", "point_mm": surface},
            {"phase": "RETRACT", "point_mm": hover},
        ]

    report: dict[str, Any] = {
        "schema": "rocell.model_motion_candidate.v1",
        "status": "ACCEPTED_OFFLINE_NOMINAL_REQUIRES_CALIBRATED_PLANNER",
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.proposal_sha256,
        "target_catalog_sha256": catalog.content_sha256,
        "source": proposal.source.to_dict(),
        "device": proposal.device.value,
        "target_id": proposal.target_id,
        "interaction": proposal.interaction.value,
        "speed_class": proposal.speed_class.value,
        "confidence": proposal.confidence,
        "minimum_confidence": threshold,
        "proposed_surface_target_board_mm": surface,
        "nominal_target_center_board_mm": {
            "frame": "board",
            "x": nominal.center.x,
            "y": nominal.center.y,
            "z": nominal.center.z,
        },
        "nominal_delta_mm": {
            "x": board.x - nominal.center.x,
            "y": board.y - nominal.center.y,
            "z": board.z - nominal.center.z,
        },
        "nominal_safe_rectangle_board_mm": [left, front, right, rear],
        "requested_waypoints": waypoints,
        "planner_handoff": {
            "required_next_stage": "CALIBRATED_IK_AND_FULL_ROUTE_SCREENING",
            "coordinate_frame": "board",
            "controller_frame_correlation_required": True,
            "tool_transform_required": True,
        },
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
        "limitations": [
            "Nominal target map is synthetic and unmeasured",
            "No physical device-placement transform is commissioned",
            "No board-to-controller correlation is commissioned",
            "No IK, full-arm collision, cable, timing, or smoothness screening performed",
        ],
    }
    return {
        **report,
        "candidate_sha256": hashlib.sha256(_canonical(report)).hexdigest(),
    }


def compile_mapping(
    value: object,
    *,
    workspace: Path,
    minimum_confidence: float = 0.9,
) -> dict[str, Any]:
    proposal = ModelMotionProposal.from_mapping(value)
    catalog = load_nominal_target_catalog(Path(workspace))
    return compile_model_motion_proposal(
        proposal,
        catalog,
        minimum_confidence=minimum_confidence,
    )


def _without_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelMotionBridgeError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--proposal", type=Path)
    source.add_argument("--retained-keyboard-target")
    parser.add_argument("--minimum-confidence", type=float, default=0.9)
    parser.add_argument("--workcell-epoch-id")
    args = parser.parse_args(argv)
    if args.retained_keyboard_target is not None:
        if not args.workcell_epoch_id:
            parser.error("--workcell-epoch-id is required for a retained keyboard target")
        report = compile_retained_keyboard_hover_draft(
            args.workspace, args.retained_keyboard_target,
            expected_workcell_epoch_id=args.workcell_epoch_id)
    else:
        document = json.loads(
            args.proposal.read_text(encoding="utf-8"),
            object_pairs_hook=_without_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ModelMotionBridgeError(f"nonfinite JSON constant {value!r}")
            ),
        )
        report = compile_mapping(
            document,
            workspace=args.workspace,
            minimum_confidence=args.minimum_confidence,
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess use
    raise SystemExit(main())
