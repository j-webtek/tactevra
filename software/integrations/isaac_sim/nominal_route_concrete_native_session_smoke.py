"""Run one bounded concrete-session settle with no trajectory or joint targets."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol

from nominal_route_native_root_path_correction import corrected_native_metadata
from nominal_route_native_session_smoke import (
    IsaacInertSmokeDriver,
    InertSmokeError,
    _write_json,
)


SCHEMA = "tactevra.isaac_lm4_concrete_native_session_settle.v1"
EXPECTED_SETTLE_STEPS = 30


class ConcreteSession(Protocol):
    def start_headless(self) -> None: ...
    def load_scene(self) -> None: ...
    def initialize_physics(self) -> None: ...
    def settle_scene(self) -> None: ...
    def native_objects(self) -> Mapping[str, Any]: ...
    def shutdown(self) -> None: ...

    @property
    def physics_steps(self) -> int: ...


class ConcreteSessionSmokeError(RuntimeError):
    """Raised when concrete lifecycle or bounded settle acceptance changes."""


def _pose(view: Any) -> tuple[list[float], list[float]]:
    poses = view.get_world_poses()
    if not isinstance(poses, (list, tuple)) or len(poses) != 2:
        raise ConcreteSessionSmokeError("root pose result changed")

    def row(value: Any, size: int) -> list[float]:
        if hasattr(value, "numpy"):
            value = value.numpy()
        if hasattr(value, "tolist"):
            value = value.tolist()
        if (
            not isinstance(value, list)
            or len(value) != 1
            or not isinstance(value[0], (list, tuple))
            or len(value[0]) != size
        ):
            raise ConcreteSessionSmokeError("root pose shape changed")
        result = [float(item) for item in value[0]]
        if not all(math.isfinite(item) for item in result):
            raise ConcreteSessionSmokeError("root pose must be finite")
        return result

    return row(poses[0], 3), row(poses[1], 4)


def _zero_authority(physics_steps: int = 0) -> dict[str, Any]:
    return {
        "attempt_consumed": False,
        "worker_invoked": False,
        "backend_invoked": False,
        "timeline_played": False,
        "physics_steps": physics_steps,
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


def run_concrete_settle_smoke(
    session: ConcreteSession,
    *,
    output_directory: Path,
    governed_attempt_directory: Path,
) -> dict[str, Any]:
    """Execute one concrete lifecycle and retain bounded settle evidence."""
    if output_directory.exists():
        raise ConcreteSessionSmokeError("settle smoke output exists; retry refused")
    if governed_attempt_directory.exists():
        raise ConcreteSessionSmokeError("governed attempt directory already exists")
    output_directory.mkdir(parents=True, exist_ok=False)
    receipt_path = output_directory / "receipt.json"
    try:
        session.start_headless()
        session.load_scene()
        session.initialize_physics()
        native = dict(session.native_objects())
        if set(native) != {"articulation", "scene_query", "key_view", "root_view"}:
            raise ConcreteSessionSmokeError("native session object set changed")
        if getattr(native["root_view"], "prim_path", None) != corrected_native_metadata()[
            "root_prim_path"
        ]:
            raise ConcreteSessionSmokeError("concrete root identity changed")
        before_position, before_quaternion = _pose(native["root_view"])
        session.settle_scene()
        after_position, after_quaternion = _pose(native["root_view"])
        translation_drift_m = max(
            abs(after - before)
            for after, before in zip(after_position, before_position, strict=True)
        )
        quaternion_dot = abs(
            sum(
                after * before
                for after, before in zip(
                    after_quaternion, before_quaternion, strict=True
                )
            )
        )
        if (
            session.physics_steps != EXPECTED_SETTLE_STEPS
            or translation_drift_m > 5e-6
            or abs(quaternion_dot - 1.0) > 1e-6
        ):
            raise ConcreteSessionSmokeError("bounded settle acceptance failed")
        receipt = {
            "schema": SCHEMA,
            "status": "PASS_CONCRETE_NATIVE_SESSION_BOUNDED_SETTLE",
            "smoke_id": output_directory.name,
            "native_metadata": corrected_native_metadata(),
            "root_before": {
                "position_m": before_position,
                "quaternion_wxyz": before_quaternion,
            },
            "root_after": {
                "position_m": after_position,
                "quaternion_wxyz": after_quaternion,
            },
            "maximum_translation_drift_m": translation_drift_m,
            "quaternion_absolute_dot": quaternion_dot,
            "governed_attempt_directory": str(governed_attempt_directory),
            "governed_attempt_directory_created": False,
            **_zero_authority(session.physics_steps),
        }
        _write_json(receipt_path, receipt)
        return receipt
    except Exception as exc:
        failure = {
            "schema": SCHEMA,
            "status": "FAIL_CONCRETE_NATIVE_SESSION_BOUNDED_SETTLE",
            "failure_type": type(exc).__name__,
            "failure_message": str(exc),
            "governed_attempt_directory": str(governed_attempt_directory),
            "governed_attempt_directory_created": governed_attempt_directory.exists(),
            **_zero_authority(session.physics_steps),
        }
        _write_json(receipt_path, failure)
        raise
    finally:
        session.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot-usd", type=Path, required=True)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--route", type=Path, required=True)
    parser.add_argument("--mechanics-profile", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--governed-attempt-directory", type=Path, required=True)
    args = parser.parse_args()
    session = IsaacInertSmokeDriver(
        args.robot_usd,
        args.layout,
        args.route,
        mechanics_profile=args.mechanics_profile,
    )
    receipt = run_concrete_settle_smoke(
        session,
        output_directory=args.output_directory,
        governed_attempt_directory=args.governed_attempt_directory,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InertSmokeError as exc:
        raise SystemExit(str(exc)) from exc
