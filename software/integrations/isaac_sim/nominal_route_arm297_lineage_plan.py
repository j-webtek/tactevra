"""Build the inert ARM-297 nominal route-physics lineage plan.

The plan binds the independently accepted ARM-296 constructor-completeness
evidence to the corrected production runtime sources and three absent outputs
reserved for a future, separately reviewed and separately authorized attempt.
It imports no Isaac or transport module and grants no launch, attempt, motion,
hardware, or physical authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "tactevra.isaac_lm4_arm297_route_physics_lineage_plan.v1"
GATE_SCHEMA = "tactevra.isaac_lm4_constructor_completeness_gate.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_constructor_completeness_gate_review.v1"
EXPECTED_GATE_SHA256 = (
    "e240eae3f47edeeca8d4010889440bce89d0a10f495793cc286e5b47d290650b"
)
EXPECTED_GATE_FILE_SHA256 = (
    "6c81aa58affb57218fd88ca38ea977a62c5aa305f0f4dad9a007fd6625a7a2c1"
)
EXPECTED_REVIEW_SHA256 = (
    "9649483e22931a982c865ce209d24ed12446373375a6f2c4522c349dcaaac003"
)
EXPECTED_REVIEW_FILE_SHA256 = (
    "f6ec2f7b7aa84df312057e532062f2938b6b4bce1a56891a1aae5d832ec27e4d"
)
EXPECTED_ARM295_STATUS_SHA256 = (
    "7490b9e2bac3d3adf0146ca08e6a61a542bd4d8952329d68e8bfeb12970da1b8"
)
EXPECTED_CORRECTED_BINDING_SHA256 = (
    "2d93fe5647e3596fded4c3f8ba7e33f7c89a495f76fcf69620327588eb2d1fe7"
)
RUNTIME_SOURCE_KEYS = (
    "complete_runtime_composition",
    "concrete_native_attempt_binding",
    "constructor_completeness_gate",
    "constructor_completeness_gate_review",
    "native_root_path_correction",
    "native_runtime_factory",
    "native_runtime_worker_integration",
    "native_sweep_binding",
    "physics_backend",
    "physics_worker",
)
EXACT_AUTHORIZATION = (
    "I authorize exactly one ARM-297 recovered nominal SPACE route-physics "
    "simulation attempt for episode-ef340d0ad2740c118d87, with no automatic "
    "retry, no trajectory playback, and no hardware or physical authority."
)
ZERO_AUTHORITY = {
    "authorization_observed": False,
    "attempt_claimed": False,
    "attempt_consumed": False,
    "claimant_constructed": False,
    "launch_admitted": False,
    "worker_invoked": False,
    "backend_invoked": False,
    "isaac_imported": False,
    "isaac_started": False,
    "scene_loaded": False,
    "timeline_played": False,
    "physics_steps": 0,
    "runtime_methods_called": [],
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


class Arm297LineagePlanError(ValueError):
    """Raised when accepted evidence or the proposed lineage changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise Arm297LineagePlanError("lineage input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise Arm297LineagePlanError(f"required input unavailable: {path}") from exc


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value.lower()
    )


def _require_hash(
    document: Mapping[str, Any], key: str, label: str
) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise Arm297LineagePlanError(f"{label} hash changed")
    return claimed


def _validate_evidence(
    gate: Mapping[str, Any], review: Mapping[str, Any]
) -> tuple[str, str]:
    gate_hash = _require_hash(gate, "gate_sha256", "ARM-296 gate")
    review_hash = _require_hash(
        review, "gate_review_sha256", "ARM-296 gate review"
    )
    if (
        gate.get("schema") != GATE_SCHEMA
        or gate_hash != EXPECTED_GATE_SHA256
        or gate.get("status")
        != "PASS_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS"
        or gate.get("source_arm295_status_sha256")
        != EXPECTED_ARM295_STATUS_SHA256
        or gate.get("source_corrected_binding_sha256")
        != EXPECTED_CORRECTED_BINDING_SHA256
        or gate.get("former_failure_stage") != "construct_runtime"
        or gate.get("former_failure_crossed") is not True
        or gate.get("runtime_type") != "CompleteRuntimeComposition"
        or gate.get("shared_solver_identity_verified") is not True
        or gate.get("baseline_reads") != {"key_view": 1, "root_view": 1}
        or gate.get("protocol_calls")
        != {"articulation": [], "scene_query": []}
        or gate.get("attempt_consumed") is not False
        or gate.get("isaac_imported") is not False
        or gate.get("isaac_started") is not False
        or gate.get("physics_steps") != 0
        or gate.get("runtime_methods_called") != []
        or gate.get("trajectory_playback") is not False
        or gate.get("joint_targets_submitted") is not False
        or gate.get("hardware_access") is not False
        or gate.get("physical_authority") is not False
    ):
        raise Arm297LineagePlanError("ARM-296 gate boundary changed")
    if (
        review.get("schema") != REVIEW_SCHEMA
        or review_hash != EXPECTED_REVIEW_SHA256
        or review.get("status")
        != "ACCEPTED_CORRECTED_RUNTIME_CONSTRUCTOR_COMPLETENESS"
        or review.get("source_gate_sha256") != gate_hash
        or review.get("former_arm295_constructor_failure_crossed") is not True
        or review.get("production_solver_and_runtime_components_verified")
        is not True
        or review.get("shared_solver_identity_verified") is not True
        or review.get("attempt_consumed") is not False
        or review.get("isaac_started") is not False
        or review.get("physics_steps") != 0
        or review.get("runtime_methods_called") != []
        or review.get("trajectory_playback") is not False
        or review.get("joint_targets_submitted") is not False
        or review.get("hardware_access") is not False
        or review.get("physical_authority") is not False
        or review.get("next_required_stage")
        != "PLAN_NEW_SEPARATELY_AUTHORIZED_NOMINAL_ROUTE_SIMULATION_LINEAGE"
    ):
        raise Arm297LineagePlanError("ARM-296 review boundary changed")
    return gate_hash, review_hash


def build_arm297_lineage_plan(
    gate: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    gate_file_sha256: str,
    review_file_sha256: str,
    plan_source_file_sha256: str,
    runtime_sources_sha256: Mapping[str, str],
    proposed_attempt_directory: Path,
    proposed_eula_receipt: Path,
    proposed_memory_receipt: Path,
) -> dict[str, Any]:
    """Freeze ARM-297 inputs and absent outputs without constructing a claimant."""

    gate_hash, review_hash = _validate_evidence(gate, review)
    if gate_file_sha256 != EXPECTED_GATE_FILE_SHA256:
        raise Arm297LineagePlanError("ARM-296 gate file changed")
    if review_file_sha256 != EXPECTED_REVIEW_FILE_SHA256:
        raise Arm297LineagePlanError("ARM-296 review file changed")
    digests = (
        plan_source_file_sha256,
        *runtime_sources_sha256.values(),
    )
    if not all(_digest(value) for value in digests):
        raise Arm297LineagePlanError("lineage source digest changed")
    if set(runtime_sources_sha256) != set(RUNTIME_SOURCE_KEYS):
        raise Arm297LineagePlanError("runtime source inventory changed")
    if (
        runtime_sources_sha256.get("concrete_native_attempt_binding")
        != EXPECTED_CORRECTED_BINDING_SHA256
    ):
        raise Arm297LineagePlanError("corrected binding source changed")

    paths = (
        proposed_attempt_directory,
        proposed_eula_receipt,
        proposed_memory_receipt,
    )
    if (
        not all(path.is_absolute() for path in paths)
        or len({str(path) for path in paths}) != len(paths)
        or proposed_attempt_directory.name
        != "arm297-nominal-route-physics-attempt-001"
        or proposed_eula_receipt.parent.name
        != "arm297-nominal-route-physics-eula-preflight-001"
        or proposed_memory_receipt.parent.name
        != "arm297-nominal-route-physics-memory-preflight-001"
        or proposed_eula_receipt.name != "receipt.json"
        or proposed_memory_receipt.name != "receipt.json"
        or any(path.exists() for path in paths)
        or proposed_eula_receipt.parent.exists()
        or proposed_memory_receipt.parent.exists()
    ):
        raise Arm297LineagePlanError("fresh ARM-297 output boundary changed")

    core: dict[str, Any] = {
        "schema": SCHEMA,
        "plan_id": "arm297-recovered-nominal-route-physics-lineage-plan-001",
        "status": "READY_FOR_INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW",
        "case_id": "nominal-fixture-baseline",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "source_arm296_gate_sha256": gate_hash,
        "source_arm296_gate_file_sha256": gate_file_sha256,
        "source_arm296_review_sha256": review_hash,
        "source_arm296_review_file_sha256": review_file_sha256,
        "plan_source_file_sha256": plan_source_file_sha256,
        "runtime_sources_sha256": dict(sorted(runtime_sources_sha256.items())),
        "superseded_attempts": [
            "ARM-253",
            "ARM-280",
            "ARM-284",
            "ARM-289",
            "ARM-295",
        ],
        "superseded_authorizations_reusable": False,
        "arm295_replay_permitted": False,
        "arm296_is_attempt_authority": False,
        "proposed_attempt_directory": str(proposed_attempt_directory),
        "proposed_eula_receipt": str(proposed_eula_receipt),
        "proposed_memory_receipt": str(proposed_memory_receipt),
        "fresh_eula_preflight_required": True,
        "fresh_memory_preflight_required": True,
        "preflights_must_precede_attempt_claim": True,
        "terminal_status_must_precede_simulator_shutdown": True,
        "claimant_review_required_before_authorization": True,
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "authorization_reusable": False,
        **ZERO_AUTHORITY,
        "next_required_stage": "INDEPENDENT_ARM297_LINEAGE_PLAN_REVIEW",
        "limitations": [
            "plan_does_not_construct_a_claimant_or_collect_live_preflights",
            "plan_does_not_accept_or_reuse_authorization",
            "plan_does_not_create_any_governed_output_directory",
            "plan_does_not_start_isaac_or_invoke_runtime_or_backend",
            "simulation_cannot_authorize_hardware_or_physical_motion",
        ],
    }
    return {**core, "plan_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise Arm297LineagePlanError(
            f"required JSON unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise Arm297LineagePlanError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-receipt", type=Path, required=True)
    parser.add_argument("--gate-review", type=Path, required=True)
    parser.add_argument("--runtime-source", action="append", nargs=2, required=True)
    parser.add_argument("--proposed-attempt-directory", type=Path, required=True)
    parser.add_argument("--proposed-eula-receipt", type=Path, required=True)
    parser.add_argument("--proposed-memory-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime_sources = {key: Path(value) for key, value in args.runtime_source}
    if set(runtime_sources) != set(RUNTIME_SOURCE_KEYS):
        raise Arm297LineagePlanError("runtime source inventory changed")
    result = build_arm297_lineage_plan(
        _load(args.gate_receipt),
        _load(args.gate_review),
        gate_file_sha256=_file_sha(args.gate_receipt),
        review_file_sha256=_file_sha(args.gate_review),
        plan_source_file_sha256=_file_sha(Path(__file__).resolve()),
        runtime_sources_sha256={
            key: _file_sha(path.resolve(strict=True))
            for key, path in runtime_sources.items()
        },
        proposed_attempt_directory=args.proposed_attempt_directory,
        proposed_eula_receipt=args.proposed_eula_receipt,
        proposed_memory_receipt=args.proposed_memory_receipt,
    )
    if args.output.exists():
        raise Arm297LineagePlanError("lineage output exists; overwrite refused")
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
