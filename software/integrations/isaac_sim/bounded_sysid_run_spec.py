"""Build the first bounded, validation-aware Isaac SysID run specification.

This utility uses Isaac Sim's installed SysID recipe and schema APIs.  It then
narrows the generated manipulator parameter space to the eight drive terms that
the retained sensitivity rehearsal found observable.  It never accesses robot
hardware and it never modifies the source or derived USD stage.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA = "tactevra.isaac_lm0b_bounded_sysid_run_spec.v1"
OBSERVABLE_DOF_INDICES = (0, 1, 2, 3)
OBSERVABLE_PARAMETER_TYPES = ("joint_stiffness", "joint_damping")
CHUNK_PLAN = (
    {"name": "H excitation", "role": "train", "excitation": "custom", "start": 2.0083333333333333, "end": 4.0, "weight": 1.0},
    {"name": "1 excitation", "role": "train", "excitation": "custom", "start": 4.008333333333334, "end": 6.0, "weight": 1.0},
    {"name": "PERIOD holdout", "role": "validation", "excitation": "custom", "start": 6.008333333333334, "end": 7.991666666666666, "weight": 1.0},
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_bounded_payload(payload: dict[str, Any]) -> None:
    """Enforce the project-specific boundary on an official SysIdRunSpec payload."""
    selected = payload["parameters"]["selected"]
    addresses = [(row["param_type"], int(row["dof_index"])) for row in selected]
    expected = [
        (parameter_type, dof_index)
        for dof_index in OBSERVABLE_DOF_INDICES
        for parameter_type in OBSERVABLE_PARAMETER_TYPES
    ]
    if addresses != expected:
        raise ValueError(f"bounded parameter addresses differ: {addresses!r}")
    chunks = payload["telemetry"]["chunks"]
    if chunks != list(CHUNK_PLAN):
        raise ValueError("bounded telemetry chunks differ from the governed train/validation split")
    if payload["residuals"]["torque_weight"] != 0.0:
        raise ValueError("uncalibrated torque must not contribute to this fit")
    if payload["outputs"]["apply_parameters_to_usd"] is not False:
        raise ValueError("first bounded rehearsal must not apply parameters to USD")
    if payload["solver"]["max_iterations"] > 3 or payload["solver"]["max_rollout_steps"] > 240:
        raise ValueError("first bounded rehearsal exceeded its solver budget")


def summarize_solve_result(result: dict[str, Any], *, result_sha256: str, run_spec_sha256: str) -> dict[str, Any]:
    """Reduce NVIDIA's verbose solve report to the retained project receipt."""
    selected = result["selected_status"]
    assessment = result["tuning_assessment"]
    check = result["extra"]["check_report"]
    verdicts = check["parameter_verdicts"]
    if result["parameters_written"] is not False:
        raise ValueError("bounded rehearsal unexpectedly wrote parameters")
    if selected.get("accepted") is not True or selected.get("source") != "last_accepted":
        raise ValueError("bounded rehearsal produced no accepted candidate")
    if len(verdicts) != 8 or any(row.get("verdict") != "identifiable" for row in verdicts):
        raise ValueError("bounded rehearsal did not retain eight identifiable terms")
    validation = result["validation_summary"]["overall"]
    receipt = {
        "schema": "tactevra.isaac_lm0b_bounded_sysid_rehearsal.v1",
        "status": "PASS_BOUNDED_SYSID_REHEARSAL_WITH_WARNINGS",
        "hardware_access": False,
        "physical_authority": False,
        "parameters_written": False,
        "stage_saved": bool(result["extra"].get("stage_saved", False)),
        "selected_candidate": {
            "source": selected["source"],
            "iteration": int(selected["iteration"]),
            "accepted": bool(selected["accepted"]),
            "training_normalized_cost": float(selected["cost"]),
            "theta": [float(value) for value in selected["theta"]],
        },
        "validation": {
            "chunk_count": int(result["validation_summary"]["count"]),
            "normalized_cost": float(validation["normalized_cost"]),
            "position_rmse_rad": float(validation["position_rmse"]),
            "velocity_rmse_rad_s": float(validation["velocity_rmse"]),
        },
        "identifiability": {
            "selected_count": len(verdicts),
            "identifiable_count": sum(row.get("verdict") == "identifiable" for row in verdicts),
            "weak_excitation_dof_indices": check["telemetry_quality"]["weak_excitation_joint_indices"],
            "condition": float(check["presolve"]["condition"]),
        },
        "tuning_assessment": {
            "status": assessment["status"],
            "issue_codes": [row["code"] for row in assessment["issues"]],
            "validation_to_training_cost_ratio": float(
                assessment["metrics"]["validation_to_training_cost_ratio"]
            ),
        },
        "limitations": [
            "simulation-generated telemetry is not physical robot telemetry",
            "stiffness and damping columns remain highly correlated",
            "DOF indices 4 and 5 lack sufficient excitation",
            "no calibrated link-side torque is available for inertial fitting",
            "candidate parameters are not applied to the USD",
        ],
        "bindings": {
            "run_spec_sha256": run_spec_sha256,
            "nvidia_solve_report_sha256": result_sha256,
        },
    }
    receipt["receipt_sha256"] = _digest(_canonical(receipt))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--telemetry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    parser.add_argument("--solve-result", type=Path)
    parser.add_argument("--solve-receipt", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    app = None
    try:
        stage = args.stage.resolve(strict=True)
        telemetry = args.telemetry.resolve(strict=True)

        from isaacsim import SimulationApp

        app = SimulationApp({"headless": True, "multi_gpu": False})
        # The SysID extension is separately packaged from the top-level
        # ``isaacsim`` namespace.  Standalone scripts must expose that package
        # root just as NVIDIA's own headless SysID entry points do.
        extension_root = (
            Path(sys.executable).resolve().parents[1]
            / "Lib"
            / "site-packages"
            / "isaacsim"
            / "exts"
            / "isaacsim.robot_setup.sysid"
        )
        if not extension_root.is_dir():
            raise RuntimeError(f"installed SysID extension not found: {extension_root}")
        sys.path.insert(0, str(extension_root))
        import isaacsim

        package_root = str(extension_root / "isaacsim")
        if package_root not in isaacsim.__path__:
            isaacsim.__path__.append(package_root)
        importlib.invalidate_caches()
        from isaacsim.robot_setup.sysid.ingest import load_trajectory
        from isaacsim.robot_setup.sysid.ingest.config_types import TrajectoryLoadConfig
        from isaacsim.robot_setup.sysid.preset_loader import load_builtin_parameter_preset
        from isaacsim.robot_setup.sysid.recipes import synthesize_run_spec_from_quickstart
        from isaacsim.robot_setup.sysid.run_spec import SysIdRunSpec
        from isaacsim.robot_setup.sysid.schema_validation import (
            raise_for_schema_errors,
            validate_sysid_run_spec_payload,
        )
        from isaacsim.robot_setup.sysid.trajectory_segments import TelemetryChunkRunSpec

        trajectory = load_trajectory(TrajectoryLoadConfig.csv(str(telemetry)))
        recipe = load_builtin_parameter_preset("manipulator")
        spec, notes = synthesize_run_spec_from_quickstart(
            robot_prim_path="/roarm_m3",
            telemetry_path=str(telemetry),
            recipe=recipe,
            stage_path=str(stage),
            trajectory=trajectory,
            num_joints=6,
            num_links=7,
        )
        by_address = {(row.param_type, row.dof_index): row for row in spec.parameters.selected}
        spec.parameters.selected = [
            by_address[(parameter_type, dof_index)]
            for dof_index in OBSERVABLE_DOF_INDICES
            for parameter_type in OBSERVABLE_PARAMETER_TYPES
        ]
        spec.telemetry.chunks = [TelemetryChunkRunSpec.from_dict(row) for row in CHUNK_PLAN]
        spec.telemetry.auto_split = False
        spec.solver.max_iterations = 3
        spec.solver.max_rollout_steps = 240
        spec.residuals.position_weight = 1.0
        spec.residuals.velocity_weight = 0.5
        spec.residuals.torque_weight = 0.0
        spec.residuals.end_effector_pose_weight = 0.0
        spec.residuals.contact_force_weight = 0.0
        spec.outputs.apply_parameters_to_usd = False
        spec.outputs.write_usd_provenance = False
        spec.outputs.export_provenance_sidecar = False
        spec.outputs.compute_parameter_confidence = False

        payload = spec.to_dict()
        validate_bounded_payload(payload)
        roundtrip = SysIdRunSpec.from_dict(payload).to_dict()
        if roundtrip != payload:
            raise RuntimeError("official SysIdRunSpec roundtrip changed the bounded payload")
        issues = validate_sysid_run_spec_payload(payload)
        raise_for_schema_errors(issues, context="Bounded run specification")
        output_raw = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
        args.output.write_bytes(output_raw)

        receipt = {
            "schema": SCHEMA,
            "status": "PASS_BOUNDED_SYSID_RUN_SPEC",
            "hardware_access": False,
            "physical_authority": False,
            "source_usd_modified": False,
            "parameter_count": len(spec.parameters.selected),
            "observable_dof_indices": list(OBSERVABLE_DOF_INDICES),
            "parameter_types": list(OBSERVABLE_PARAMETER_TYPES),
            "train_chunk_count": 2,
            "validation_chunk_count": 1,
            "stationary_park_excluded": True,
            "weak_dof_indices_excluded": [4, 5],
            "uncalibrated_torque_excluded": True,
            "solver_budget": {"max_iterations": 3, "max_rollout_steps": 240},
            "official_schema_issue_count": len(issues),
            "official_recipe": "manipulator",
            "official_recipe_notes": notes,
            "bindings": {
                "stage_sha256": _digest(stage.read_bytes()),
                "telemetry_sha256": _digest(telemetry.read_bytes()),
                "run_spec_sha256": _digest(output_raw),
            },
        }
        receipt["receipt_sha256"] = _digest(_canonical(receipt))
        args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if bool(args.solve_result) != bool(args.solve_receipt):
            raise ValueError("--solve-result and --solve-receipt must be supplied together")
        if args.solve_result is not None and args.solve_receipt is not None:
            solve_raw = args.solve_result.resolve(strict=True).read_bytes()
            solve_receipt = summarize_solve_result(
                json.loads(solve_raw),
                result_sha256=_digest(solve_raw),
                run_spec_sha256=_digest(output_raw),
            )
            args.solve_receipt.parent.mkdir(parents=True, exist_ok=True)
            args.solve_receipt.write_text(
                json.dumps(solve_receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        args.status_output.write_text(json.dumps({"status": receipt["status"]}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        args.status_output.write_text(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())
