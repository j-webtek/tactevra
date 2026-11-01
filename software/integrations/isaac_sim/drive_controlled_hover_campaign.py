"""Aggregate independent LM0A Isaac receipts into repeatability evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


INPUT_SCHEMA = "tactevra.isaac_lm0_drive_controlled_hover.v1"
OUTPUT_SCHEMA = "tactevra.isaac_lm0_drive_controlled_hover_campaign.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_trial(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    trial = json.loads(raw)
    if trial.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"{path}: unsupported LM0A receipt schema")
    claimed = trial.get("receipt_sha256")
    unsigned = dict(trial)
    unsigned.pop("receipt_sha256", None)
    if not isinstance(claimed, str) or claimed != _digest(_canonical(unsigned)):
        raise ValueError(f"{path}: receipt digest mismatch")
    if trial.get("status") != "PASS":
        raise ValueError(f"{path}: trial did not pass")
    if (
        trial.get("hardware_access") is not False
        or trial.get("physical_authority") is not False
        or trial.get("hardware_writes") != 0
        or trial.get("physical_movements") != 0
        or trial.get("controller_commands") != []
    ):
        raise ValueError(f"{path}: trial crossed the zero-hardware-authority boundary")
    if trial.get("state_teleports_after_initialization") != 0:
        raise ValueError(f"{path}: trial used a post-initialization state teleport")
    error = trial.get("maximum_final_joint_error_rad")
    threshold = trial.get("threshold_rad")
    if not isinstance(error, (int, float)) or not math.isfinite(error):
        raise ValueError(f"{path}: invalid final joint error")
    if not isinstance(threshold, (int, float)) or error > threshold:
        raise ValueError(f"{path}: final joint error exceeds its threshold")
    return trial, _digest(raw)


def build_campaign(
    paths: list[Path], *, minimum_trials: int, maximum_error_spread_rad: float
) -> dict[str, Any]:
    if minimum_trials < 2 or len(paths) < minimum_trials:
        raise ValueError(f"at least {minimum_trials} independent trial receipts are required")
    if maximum_error_spread_rad < 0 or not math.isfinite(maximum_error_spread_rad):
        raise ValueError("maximum error spread must be finite and nonnegative")
    loaded = [(path, *load_trial(path)) for path in paths]
    first = loaded[0][1]
    invariant_fields = ("source_bindings", "physics_steps", "target", "threshold_rad")
    for path, trial, _ in loaded[1:]:
        for field in invariant_fields:
            if trial.get(field) != first.get(field):
                raise ValueError(f"{path}: {field} differs from the first trial")
    errors = [float(trial["maximum_final_joint_error_rad"]) for _, trial, _ in loaded]
    spread = max(errors) - min(errors)
    if spread > maximum_error_spread_rad:
        raise ValueError(
            f"maximum final-error spread {spread} exceeds {maximum_error_spread_rad} rad"
        )
    trial_receipts = [
        {
            "ordinal": index,
            "input_name": path.name,
            "file_sha256": file_sha256,
            "receipt_sha256": trial["receipt_sha256"],
            "maximum_final_joint_error_rad": trial["maximum_final_joint_error_rad"],
        }
        for index, (path, trial, file_sha256) in enumerate(loaded, start=1)
    ]
    result: dict[str, Any] = {
        "schema": OUTPUT_SCHEMA,
        "status": "PASS_REPEATABLE_GRAVITY_OFF_DRIVE_CONTROL",
        "evidence_class": "PROVISIONAL_GRAVITY_OFF_DRIVE_CONTROL_REPEATABILITY",
        "trial_count": len(loaded),
        "minimum_trial_count": minimum_trials,
        "trial_receipts": trial_receipts,
        "shared_source_bindings": first["source_bindings"],
        "physics_steps_per_trial": first["physics_steps"],
        "target": first["target"],
        "threshold_rad": first["threshold_rad"],
        "minimum_final_joint_error_rad": min(errors),
        "maximum_final_joint_error_rad": max(errors),
        "final_joint_error_spread_rad": spread,
        "maximum_allowed_error_spread_rad": maximum_error_spread_rad,
        "unique_trial_receipt_count": len({trial["receipt_sha256"] for _, trial, _ in loaded}),
        "byte_identical_trial_outputs": len({file_sha256 for _, _, file_sha256 in loaded}) == 1,
        "state_teleports_after_initialization": 0,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "limitations": [
            "three_trial_campaign_only",
            "gravity_disabled",
            "provisional_mass_inertia_and_drive_parameters",
            "no_collision_or_contact_geometry",
            "not_physical_timing_torque_safety_or_repeatability_evidence",
        ],
    }
    result["campaign_receipt_sha256"] = _digest(_canonical(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--minimum-trials", type=int, default=3)
    parser.add_argument("--maximum-error-spread-rad", type=float, default=1e-9)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status-output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.status_output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = build_campaign(
            args.receipts,
            minimum_trials=args.minimum_trials,
            maximum_error_spread_rad=args.maximum_error_spread_rad,
        )
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.status_output.write_text(
            json.dumps(
                {"status": result["status"], "campaign_receipt_sha256": result["campaign_receipt_sha256"]},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return 0
    except BaseException as exc:
        args.status_output.write_text(
            json.dumps({"status": "ERROR", "type": type(exc).__name__, "message": str(exc)}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
