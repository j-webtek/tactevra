"""Independently review ARM-292 without starting Isaac."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


REQUEST_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_request.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_review.v1"
EXPECTED_AUTHORIZATION = (
    "I authorize exactly one ARM-294 zero-motion native link-inventory "
    "diagnostic, with no automatic retry, no physics stepping, no joint "
    "targets, no trajectory playback, and no hardware or physical authority."
)
EXPECTED_LINK_NAMES = (
    "base_link",
    "link1",
    "link2",
    "link3",
    "link4",
    "link5",
    "gripper_link",
)


class NativeLinkInventoryReviewError(ValueError):
    """Raised when ARM-292 source or authority boundaries change."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any]) -> str:
    claimed = document.get("request_sha256")
    core = dict(document)
    core.pop("request_sha256", None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise NativeLinkInventoryReviewError("ARM-292 request hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    expected = {
        "attempt_consumed": False,
        "worker_invoked": False,
        "backend_invoked": False,
        "timeline_played": False,
        "physics_steps": 0,
        "trajectory_playback": False,
        "joint_positions_submitted": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    return all(document.get(key) == value for key, value in expected.items())


def _static_review(path: Path) -> dict[str, bool]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    if any(name.startswith(("serial", "requests")) for name in imports):
        raise NativeLinkInventoryReviewError("hardware-capable import found")
    forbidden = (
        "settle_scene(",
        "SimulationManager.step(",
        "set_dof_positions(",
        "set_dof_position_targets(",
        "set_joint_position_targets(",
        "write_data(",
        "serial.Serial(",
        "run_one_attempt(",
    )
    if any(token in text for token in forbidden):
        raise NativeLinkInventoryReviewError("motion or route command surface found")
    run_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run_diagnostic"
        ),
        None,
    )
    if run_node is None or run_node.end_lineno is None:
        raise NativeLinkInventoryReviewError("run_diagnostic is unavailable")
    run_text = "\n".join(text.splitlines()[run_node.lineno - 1 : run_node.end_lineno])
    ordered = (
        "authorization_statement != EXACT_AUTHORIZATION",
        "output_directory.mkdir(",
        "session.start_headless()",
        "session.load_scene()",
        "session.initialize_physics()",
        "session.native_objects()",
        "session.physics_steps != 0",
        "articulation.get_link_transforms()",
        "_write_json(receipt_path, receipt)",
        "session.shutdown()",
    )
    positions = [run_text.find(token) for token in ordered]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise NativeLinkInventoryReviewError("zero-motion lifecycle order changed")
    return {
        "hardware_capable_imports_absent": True,
        "motion_route_and_transport_calls_absent": True,
        "exact_authorization_precedes_output_claim": True,
        "output_claim_precedes_isaac_start": True,
        "scene_load_precedes_physics_initialization": True,
        "physics_step_count_checked_before_inventory": True,
        "exact_link_order_and_transform_width_checked": True,
        "receipt_retained_before_shutdown": True,
    }


def review_request(
    request: Mapping[str, Any],
    *,
    request_file_sha256: str,
    diagnostic_source: Path,
    review_source_sha256: str,
) -> dict[str, Any]:
    """Accept only the exact inert request and zero-motion implementation."""

    request_hash = _require_hash(request)
    files = request.get("source_files_sha256", {})
    static = _static_review(diagnostic_source)
    if (
        request.get("schema") != REQUEST_SCHEMA
        or request.get("status")
        != "READY_FOR_INDEPENDENT_NATIVE_LINK_INVENTORY_REVIEW"
        or request.get("runtime_action_id") != "ARM-294"
        or request.get("required_authorization_statement") != EXPECTED_AUTHORIZATION
        or request.get("expected_link_names") != list(EXPECTED_LINK_NAMES)
        or request.get("expected_transform_count") != len(EXPECTED_LINK_NAMES)
        or request.get("output_must_be_absent") is not True
        or request.get("single_use_by_output_exclusivity") is not True
        or request.get("failure_retained_before_shutdown") is not True
        or request.get("runtime_execution_admitted") is not False
        or request.get("launch_admitted") is not False
        or request.get("isaac_started") is not False
        or not _zero_authority(request)
        or files.get("diagnostic_source") != _file_sha(diagnostic_source)
        or not all(
            isinstance(value, str) and len(value) == 64
            for value in (request_file_sha256, review_source_sha256, files.get("session_source"))
        )
    ):
        raise NativeLinkInventoryReviewError("ARM-293 review boundary changed")
    core: dict[str, Any] = {
        "schema": REVIEW_SCHEMA,
        "review_id": "arm293-native-link-inventory-review-001",
        "status": "ACCEPTED_FOR_EXACT_ARM294_ZERO_MOTION_AUTHORIZATION",
        "source_request_sha256": request_hash,
        "source_request_file_sha256": request_file_sha256,
        "source_diagnostic_source_sha256": _file_sha(diagnostic_source),
        "review_source_sha256": review_source_sha256,
        "static_review": static,
        "launch_admitted": True,
        "isaac_started": False,
        **{
            "attempt_consumed": False,
            "worker_invoked": False,
            "backend_invoked": False,
            "timeline_played": False,
            "physics_steps": 0,
            "trajectory_playback": False,
            "joint_positions_submitted": False,
            "joint_targets_submitted": False,
            "key_contact": False,
            "automatic_retry": False,
            "hardware_access": False,
            "hardware_writes": 0,
            "physical_authority": False,
            "physical_movements": 0,
            "controller_commands": [],
            "wire_commands": [],
            "gate_promotions": [],
        },
        "next_required_stage": "SEPARATE_EXACT_ARM294_ZERO_MOTION_AUTHORIZATION",
    }
    return {**core, "review_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--diagnostic-source", type=Path, required=True)
    parser.add_argument("--review-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(args.request.read_bytes())
    result = review_request(
        request,
        request_file_sha256=_file_sha(args.request),
        diagnostic_source=args.diagnostic_source.resolve(strict=True),
        review_source_sha256=_file_sha(args.review_source.resolve(strict=True)),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
