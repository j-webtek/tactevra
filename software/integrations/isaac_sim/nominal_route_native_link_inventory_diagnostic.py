"""Prepare and run one zero-motion native articulation inventory diagnostic.

ARM-292 builds the inert request.  Runtime use is a separate ARM-294 action
that requires an ARM-293 review and the exact authorization statement below.
The diagnostic initializes Isaac's native articulation but never steps physics,
submits joint state, invokes a route worker, or obtains hardware authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Protocol

from nominal_route_native_session_smoke import IsaacInertSmokeDriver


SCHEMA = "tactevra.isaac_lm4_native_link_inventory_request.v1"
REVIEW_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_review.v1"
RECEIPT_SCHEMA = "tactevra.isaac_lm4_native_link_inventory_receipt.v1"
EXACT_AUTHORIZATION = (
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


class NativeLinkInventoryError(RuntimeError):
    """Raised when lineage, inventory, or the zero-motion boundary changes."""


class NativeInventorySession(Protocol):
    def start_headless(self) -> None: ...
    def load_scene(self) -> None: ...
    def initialize_physics(self) -> None: ...
    def native_objects(self) -> Mapping[str, Any]: ...
    def shutdown(self) -> None: ...

    @property
    def physics_steps(self) -> int: ...


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


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    core = dict(document)
    core.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(core):
        raise NativeLinkInventoryError(f"{label} hash changed")
    return claimed


def _zero_authority() -> dict[str, Any]:
    return {
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


def _has_zero_authority(document: Mapping[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in _zero_authority().items())


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def build_request(
    *,
    diagnostic_source_sha256: str,
    session_source_sha256: str,
    proposed_output_directory: Path,
) -> dict[str, Any]:
    """Build the inert ARM-292 request without starting Isaac."""

    if not all(_digest(value) for value in (diagnostic_source_sha256, session_source_sha256)):
        raise NativeLinkInventoryError("source digest changed")
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "request_id": "arm292-native-link-inventory-request-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_LINK_INVENTORY_REVIEW",
        "runtime_action_id": "ARM-294",
        "required_authorization_statement": EXACT_AUTHORIZATION,
        "source_files_sha256": {
            "diagnostic_source": diagnostic_source_sha256,
            "session_source": session_source_sha256,
        },
        "expected_link_names": list(EXPECTED_LINK_NAMES),
        "expected_transform_count": len(EXPECTED_LINK_NAMES),
        "proposed_output_directory": str(proposed_output_directory),
        "output_must_be_absent": True,
        "single_use_by_output_exclusivity": True,
        "failure_retained_before_shutdown": True,
        "runtime_execution_admitted": False,
        "launch_admitted": False,
        "isaac_started": False,
        **_zero_authority(),
        "next_required_stage": "INDEPENDENTLY_REVIEW_ARM292_LINK_INVENTORY_REQUEST",
    }
    return {**core, "request_sha256": _sha(core)}


def _rows(value: Any) -> list[Any]:
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list):
        try:
            value = list(value)
        except TypeError as exc:
            raise NativeLinkInventoryError("native link transforms are not rows") from exc
    return value


def run_diagnostic(
    session: NativeInventorySession,
    request: Mapping[str, Any],
    review: Mapping[str, Any],
    *,
    authorization_statement: str,
    output_directory: Path,
    governed_attempt_directory: Path,
    current_source_files_sha256: Mapping[str, str],
) -> dict[str, Any]:
    """Run exactly one reviewed zero-motion inventory observation."""

    request_hash = _require_hash(request, "request_sha256", "ARM-292 request")
    _require_hash(review, "review_sha256", "ARM-293 review")
    source_files = request.get("source_files_sha256", {})
    if (
        request.get("schema") != SCHEMA
        or request.get("status")
        != "READY_FOR_INDEPENDENT_NATIVE_LINK_INVENTORY_REVIEW"
        or review.get("schema") != REVIEW_SCHEMA
        or review.get("status")
        != "ACCEPTED_FOR_EXACT_ARM294_ZERO_MOTION_AUTHORIZATION"
        or review.get("source_request_sha256") != request_hash
        or review.get("launch_admitted") is not True
        or request.get("required_authorization_statement") != EXACT_AUTHORIZATION
        or authorization_statement != EXACT_AUTHORIZATION
        or request.get("proposed_output_directory") != str(output_directory)
        or dict(current_source_files_sha256) != source_files
        or request.get("runtime_execution_admitted") is not False
        or request.get("launch_admitted") is not False
        or not _has_zero_authority(request)
        or not _has_zero_authority(review)
    ):
        raise NativeLinkInventoryError("ARM-294 diagnostic is not admitted")
    if output_directory.exists():
        raise NativeLinkInventoryError("diagnostic output exists; retry refused")
    if governed_attempt_directory.exists():
        raise NativeLinkInventoryError("governed route-attempt output already exists")

    output_directory.mkdir(parents=True, exist_ok=False)
    receipt_path = output_directory / "receipt.json"
    isaac_started = False
    try:
        session.start_headless()
        isaac_started = True
        session.load_scene()
        session.initialize_physics()
        native = dict(session.native_objects())
        if set(native) != {"articulation", "scene_query", "key_view", "root_view"}:
            raise NativeLinkInventoryError("native object inventory changed")
        if session.physics_steps != 0:
            raise NativeLinkInventoryError("diagnostic crossed zero-step boundary")
        articulation = native["articulation"]
        link_names = tuple(getattr(articulation, "link_names", ()))
        if link_names != EXPECTED_LINK_NAMES:
            raise NativeLinkInventoryError("native articulation link inventory changed")
        transforms = _rows(articulation.get_link_transforms())
        if len(transforms) != 1 or len(_rows(transforms[0])) != len(link_names):
            raise NativeLinkInventoryError("native link transform width changed")
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "PASS_NATIVE_LINK_INVENTORY_ZERO_MOTION",
            "diagnostic_id": output_directory.name,
            "source_request_sha256": request_hash,
            "source_review_sha256": review["review_sha256"],
            "source_files_sha256": dict(current_source_files_sha256),
            "link_names": list(link_names),
            "link_count": len(link_names),
            "transform_batch_count": len(transforms),
            "transform_count": len(_rows(transforms[0])),
            "governed_attempt_directory": str(governed_attempt_directory),
            "governed_attempt_directory_created": False,
            "isaac_started": isaac_started,
            **_zero_authority(),
        }
        _write_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        failure = {
            "schema": RECEIPT_SCHEMA,
            "status": "FAIL_NATIVE_LINK_INVENTORY_ZERO_MOTION_NO_RETRY",
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
            "source_request_sha256": request_hash,
            "governed_attempt_directory": str(governed_attempt_directory),
            "governed_attempt_directory_created": governed_attempt_directory.exists(),
            "isaac_started": isaac_started,
            **_zero_authority(),
        }
        _write_json(receipt_path, failure)
        raise
    finally:
        session.shutdown()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeLinkInventoryError(f"JSON document is not an object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    request_parser = subparsers.add_parser("build-request")
    request_parser.add_argument("--diagnostic-source", type=Path, required=True)
    request_parser.add_argument("--session-source", type=Path, required=True)
    request_parser.add_argument("--proposed-output-directory", type=Path, required=True)
    request_parser.add_argument("--output", type=Path, required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--request", type=Path, required=True)
    run_parser.add_argument("--review", type=Path, required=True)
    run_parser.add_argument("--authorization-statement", required=True)
    run_parser.add_argument("--robot-usd", type=Path, required=True)
    run_parser.add_argument("--layout", type=Path, required=True)
    run_parser.add_argument("--route", type=Path, required=True)
    run_parser.add_argument("--mechanics-profile", type=Path, required=True)
    run_parser.add_argument("--output-directory", type=Path, required=True)
    run_parser.add_argument("--governed-attempt-directory", type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve()
    session_source = source.with_name("nominal_route_native_session_smoke.py")
    if args.command == "build-request":
        result = build_request(
            diagnostic_source_sha256=_file_sha(args.diagnostic_source.resolve(strict=True)),
            session_source_sha256=_file_sha(args.session_source.resolve(strict=True)),
            proposed_output_directory=args.proposed_output_directory,
        )
        args.output.parent.mkdir(parents=True, exist_ok=False)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 0
    session = IsaacInertSmokeDriver(
        args.robot_usd,
        args.layout,
        args.route,
        mechanics_profile=args.mechanics_profile,
    )
    result = run_diagnostic(
        session,
        _load(args.request),
        _load(args.review),
        authorization_statement=args.authorization_statement,
        output_directory=args.output_directory,
        governed_attempt_directory=args.governed_attempt_directory,
        current_source_files_sha256={
            "diagnostic_source": _file_sha(source),
            "session_source": _file_sha(session_source),
        },
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
