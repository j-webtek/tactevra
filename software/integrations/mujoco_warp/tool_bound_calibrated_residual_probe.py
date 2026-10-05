"""Run the frozen MW2UC landing model on a tool-bound pose bundle.

This adapter changes neither the uncertainty composition nor absolute-target
scoring.  It validates the canonical tool binding, derives the exact legacy
input shape required by the frozen probe, and stamps the result with the
source tool configuration.  It has no transport or hardware interface.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nominal_target_uncertainty_probe as frozen


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_sources(
    workspace: Path, fixture_path: Path, pose_family_path: Path,
    tool_length_mm: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sys.path[:0] = [str(workspace / "software/ai"), str(workspace / "software/src")]
    from rocell_ai.first_motion_clearance_waypoints import (
        load_tool_bound_exact_clearance_fixture,
        validate_pose_bundle_tool_configuration,
    )
    from rocell_ai.tool_bound_exact_clearance import load_pose_family_result

    fixture = load_tool_bound_exact_clearance_fixture(fixture_path)
    family = load_pose_family_result(pose_family_path, fixture)
    profiles = [row for row in family["profiles"] if float(row["pose_bundle"][
        "tool_configuration"]["total_hand_tcp_to_tip_length_mm"]) == tool_length_mm]
    if len(profiles) != 4:
        raise ValueError("expected four exposure/radius profiles for tool length")
    bundles = [row["pose_bundle"] for row in profiles]
    for bundle in bundles:
        validate_pose_bundle_tool_configuration(bundle, bundle["tool_configuration"])
    pose_payloads = [bundle["poses"] for bundle in bundles]
    if any(rows != pose_payloads[0] for rows in pose_payloads[1:]):
        raise ValueError("same-length tool profiles do not share solved poses")
    reach = family["reach_by_length_mm"][str(float(tool_length_mm))]
    if reach["all_targets_reached"] is not True:
        raise ValueError("calibrated residual requires all targets reachable")
    return fixture, family, profiles[0]


def _legacy_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    poses = []
    for row in bundle["poses"]:
        xyz = row["contact_target_board_mm"]
        poses.append({
            "target_id": row["target_id"],
            "center_board_mm": [xyz["x"], xyz["y"], xyz["z"]],
            "nominal_keycap_half_extent_mm": [7.0, 7.0],
            "contact_target_board_mm": [xyz["x"], xyz["y"], xyz["z"]],
            "achieved_tip_board_mm": row["achieved_tip_board_mm"],
            "joint_positions_rad": row["joint_positions_rad"],
            "ik_position_error_mm": row["ik_position_error_mm"],
        })
    result = {
        "schema": "rocell.mujoco_warp_nominal_target_pose_bundle.v1",
        "status": "PASS_EXPLORATORY_POSE_SOURCE",
        "scope": "SYNTHETIC_UNMEASURED_RANK1_KEYBOARD_CONTACTS_ONLY",
        "target_count": len(poses),
        "target_ids": [row["target_id"] for row in poses],
        "joint_order": bundle["joint_order"],
        "layout_overlay": bundle["layout_overlay"],
        "poses": poses,
        "hardware_access": False,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
        "controller_commands": [],
        "limitations": [
            "compatibility view of a hash-bound tool-specific pose bundle",
            "safe extents are ignored by calibrated mode in favor of frozen 3/4 mm axes",
        ],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def run(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    fixture, family, profile = _load_sources(
        workspace, args.fixture.resolve(), args.pose_family.resolve(),
        float(args.tool_length_mm))
    bundle = profile["pose_bundle"]
    configuration = bundle["tool_configuration"]
    legacy = _legacy_bundle(bundle)
    virtual = json.loads(args.virtual_profile.read_text(encoding="utf-8"))
    virtual["study_input"]["route_tool_lengths_mm"]["keyboard"] = float(
        args.tool_length_mm)
    grid = fixture["calibrated_residual"]

    with tempfile.TemporaryDirectory(prefix="tactevra-tool-bound-") as directory:
        root = Path(directory)
        pose_path, virtual_path = root / "poses.json", root / "virtual.json"
        pose_path.write_bytes(_canonical(legacy))
        virtual_path.write_bytes(_canonical(virtual))
        frozen.EXPECTED["pose_bundle"] = _file_sha(pose_path)
        frozen.EXPECTED["virtual_profile"] = _file_sha(virtual_path)
        frozen.CALIBRATED_RANDOM_LEVELS_RAD = list(grid["random_joint_sigma_rad"])
        frozen.CALIBRATED_FIXED_SOURCE_MAGNITUDES_RAD = list(
            grid["fixed_source_magnitude_rad"])
        frozen.CALIBRATED_RESIDUAL_FRACTIONS = list(grid["residual_fraction"])
        frozen.CALIBRATED_HALF_WIDTHS_MM = list(grid["effective_safe_half_width_mm"])
        frozen.WORLDS_PER_TARGET = int(grid["worlds_per_target"])
        frozen.SEED = int(grid["seed"]) - 3
        raw_path = root / "raw.json"
        raw = frozen.run(SimpleNamespace(
            pose_bundle=pose_path,
            target_catalog=args.target_catalog,
            virtual_profile=virtual_path,
            mjcf=args.mjcf,
            device=args.device,
            mode="calibrated",
            output=raw_path,
        ))

    unsigned = dict(raw)
    unsigned.pop("receipt_sha256", None)
    unsigned["schema"] = "tactevra.tool_bound_calibrated_residual_result.v1"
    unsigned["fixture_sha256"] = fixture["fixture_sha256"]
    unsigned["pose_family_receipt_sha256"] = family["receipt_sha256"]
    unsigned["tool_configuration_sha256"] = bundle["tool_configuration_sha256"]
    unsigned["tool_configuration"] = configuration
    unsigned["source_tool_bound_pose_bundle_receipt_sha256"] = bundle[
        "receipt_sha256"]
    unsigned["limitations"] = list(raw["limitations"]) + [
        "tool-bound poses and length are synthetic and do not establish physical accuracy",
        "exposure and radius do not alter this point-tip joint uncertainty propagation",
    ]
    unsigned["receipt_sha256"] = _sha(unsigned)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(unsigned, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    return unsigned


def comparison_payload(result: dict[str, Any]) -> bytes:
    """Return device-independent bytes used for exact cross-GPU agreement."""

    payload = dict(result)
    for key in ("device", "stack", "receipt_sha256"):
        payload.pop(key, None)
    return _canonical(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--pose-family", type=Path, required=True)
    parser.add_argument("--target-catalog", type=Path, required=True)
    parser.add_argument("--virtual-profile", type=Path, required=True)
    parser.add_argument("--mjcf", type=Path, required=True)
    parser.add_argument("--tool-length-mm", type=float, choices=(110.0, 120.0),
                        required=True)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({
        "status": result["status"],
        "tool_configuration_sha256": result["tool_configuration_sha256"],
        "receipt_sha256": result["receipt_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
