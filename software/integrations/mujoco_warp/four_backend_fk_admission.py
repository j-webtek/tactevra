"""Admit direct 133-row Isaac/RoCell/MuJoCo/MuJoCo-Warp FK evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


EXPECTED_MW2F_FILE_SHA256 = "036581d32fddcfeaa0c0c32be9b9b6aa17cf1f644913816540ec8f0822e6bbc6"
EXPECTED_BUNDLE_FILE_SHA256 = "4aece6ef7c7194aea59af2263caff6d4a3be65273a5df92348bf796b7103bb8c"
EXPECTED_PROFILE_SHA256 = "38b348ace299140e5908cf367fc15f32b33bebe9b064d5efffe5dcf95f7b4634"
EXPECTED_USD_SHA256 = "a0ec437fb4d647f354007dc352a3af8b13576eaf4931d69d60a510bf235ebea2"
SAMPLE_COUNT = 133
ISAAC_REFERENCE_LIMIT_MM = 0.25
MUJOCO_ROCELL_LIMIT_MM = 0.1
WARP_MUJOCO_LIMIT_MM = 0.01


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_receipts(isaac: dict[str, Any], mw2f: dict[str, Any]) -> None:
    if isaac.get("schema") != "tactevra.isaac_joint_schedule_replay.v2":
        raise ValueError("Isaac receipt is not full-sample v2")
    unsigned = dict(isaac)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_bytes(unsigned)).hexdigest():
        raise ValueError("Isaac canonical receipt hash mismatch")
    if isaac.get("sample_count") != SAMPLE_COUNT or len(isaac.get("samples", [])) != SAMPLE_COUNT:
        raise ValueError("Isaac receipt does not contain exactly 133 samples")
    if [row.get("sequence") for row in isaac["samples"]] != list(range(SAMPLE_COUNT)):
        raise ValueError("Isaac sample order changed")
    bindings = isaac.get("source_bindings", {})
    if bindings.get("bundle_file_sha256") != EXPECTED_BUNDLE_FILE_SHA256:
        raise ValueError("Isaac schedule binding changed")
    if bindings.get("virtual_profile_sha256") != EXPECTED_PROFILE_SHA256:
        raise ValueError("Isaac profile binding changed")
    if bindings.get("robot_usd_sha256") != EXPECTED_USD_SHA256:
        raise ValueError("Isaac USD binding changed")
    if isaac.get("hardware_access") is not False or isaac.get("physical_authority") is not False:
        raise ValueError("Isaac receipt carries authority")
    if isaac.get("hardware_writes") != 0 or isaac.get("physical_movements") != 0:
        raise ValueError("Isaac receipt records physical activity")
    if isaac.get("physics_steps") != 0 or isaac.get("controller_commands") != []:
        raise ValueError("Isaac receipt crossed teleport-only scope")

    if mw2f.get("schema") != "rocell.mujoco_warp_schedule_fk_differential.v1":
        raise ValueError("unsupported MW2F receipt")
    unsigned = dict(mw2f)
    claimed = unsigned.pop("receipt_sha256", None)
    if claimed != hashlib.sha256(canonical_bytes(unsigned)).hexdigest():
        raise ValueError("MW2F canonical receipt hash mismatch")
    if mw2f.get("sample_count") != SAMPLE_COUNT or len(mw2f.get("rows", [])) != SAMPLE_COUNT:
        raise ValueError("MW2F receipt does not contain exactly 133 rows")
    if [row.get("sequence") for row in mw2f["rows"]] != list(range(SAMPLE_COUNT)):
        raise ValueError("MW2F row order changed")
    if mw2f.get("hardware_access") is not False or mw2f.get("physical_authority") is not False:
        raise ValueError("MW2F receipt carries authority")
    if mw2f.get("hardware_write_count") != 0 or mw2f.get("physical_movement_count") != 0:
        raise ValueError("MW2F receipt records physical activity")

    for isaac_row, mw2f_row in zip(isaac["samples"], mw2f["rows"], strict=True):
        if isaac_row["sequence"] != mw2f_row["sequence"]:
            raise ValueError("cross-backend sample order mismatch")
        if isaac_row["phase"] != mw2f_row["phase"] or isaac_row["target_id"] != mw2f_row["target_id"]:
            raise ValueError("cross-backend semantic row mismatch")
        vectors = [
            isaac_row.get("isaac_tool_tip_board_mm"),
            isaac_row.get("expected_tool_tip_board_mm"),
            mw2f_row.get("rocell_tip_board_mm"),
            mw2f_row.get("mujoco_tip_board_mm"),
            mw2f_row.get("mujoco_warp_tip_board_mm"),
        ]
        if any(
            not isinstance(vector, list)
            or len(vector) != 3
            or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise ValueError("cross-backend row contains invalid vector")


def admit(isaac: dict[str, Any], mw2f: dict[str, Any]) -> dict[str, Any]:
    validate_receipts(isaac, mw2f)

    def distance(left, right) -> float:
        return math.dist(left, right)

    rows = []
    for isaac_row, base in zip(isaac["samples"], mw2f["rows"], strict=True):
        isaac_tip = isaac_row["isaac_tool_tip_board_mm"]
        rows.append(
            {
                "sequence": base["sequence"],
                "phase": base["phase"],
                "target_id": base["target_id"],
                "isaac_vs_schedule_reference_mm": distance(
                    isaac_tip, base["schedule_reference_tip_board_mm"]
                ),
                "isaac_vs_rocell_mm": distance(isaac_tip, base["rocell_tip_board_mm"]),
                "isaac_vs_mujoco_mm": distance(isaac_tip, base["mujoco_tip_board_mm"]),
                "isaac_vs_mujoco_warp_mm": distance(
                    isaac_tip, base["mujoco_warp_tip_board_mm"]
                ),
            }
        )
    metrics = {
        key: max(row[key] for row in rows)
        for key in (
            "isaac_vs_schedule_reference_mm",
            "isaac_vs_rocell_mm",
            "isaac_vs_mujoco_mm",
            "isaac_vs_mujoco_warp_mm",
        )
    }
    gates = {
        "all_133_rows_exact_order": len(rows) == SAMPLE_COUNT,
        "isaac_vs_schedule_reference": metrics["isaac_vs_schedule_reference_mm"]
        <= ISAAC_REFERENCE_LIMIT_MM,
        "mujoco_vs_rocell": mw2f["metrics"]["maximum_mujoco_vs_rocell_mm"]
        <= MUJOCO_ROCELL_LIMIT_MM,
        "mujoco_warp_vs_mujoco": mw2f["metrics"]["maximum_mujoco_warp_vs_mujoco_mm"]
        <= WARP_MUJOCO_LIMIT_MM,
    }
    result: dict[str, Any] = {
        "schema": "rocell.four_backend_fk_admission.v1",
        "status": "PASS_KINEMATIC_ONLY" if all(gates.values()) else "FAIL",
        "scope": "SYNTHETIC_OFFLINE_TELEPORT_FK_ONLY",
        "source_file_sha256": {
            "isaac_full_sample_receipt": None,
            "mw2f_cuda0_receipt": EXPECTED_MW2F_FILE_SHA256,
        },
        "sample_count": SAMPLE_COUNT,
        "thresholds": {
            "isaac_vs_schedule_reference_mm": ISAAC_REFERENCE_LIMIT_MM,
            "mujoco_vs_rocell_mm": MUJOCO_ROCELL_LIMIT_MM,
            "mujoco_warp_vs_mujoco_mm": WARP_MUJOCO_LIMIT_MM,
            "direct_pairwise_isaac_diagnostics": "REPORTED_WITHOUT_NEW_POST_RESULT_GATE",
        },
        "metrics": metrics,
        "gates": gates,
        "rows": rows,
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physics_step_count": 0,
        "physical_authority": False,
        "limitations": [
            "meshless kinematic model and unmeasured synthetic placement/tool overlay",
            "joint teleport comparison without dynamics, collision, contact, controller, or hardware",
            "direct pairwise Isaac metrics are diagnostics under preexisting backend gates",
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--isaac-full", type=Path, required=True)
    parser.add_argument("--mw2f", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sha256(args.mw2f) != EXPECTED_MW2F_FILE_SHA256:
        raise ValueError("MW2F file SHA-256 mismatch")
    isaac = json.loads(args.isaac_full.read_text(encoding="utf-8"))
    mw2f = json.loads(args.mw2f.read_text(encoding="utf-8"))
    result = admit(isaac, mw2f)
    result["source_file_sha256"]["isaac_full_sample_receipt"] = sha256(args.isaac_full)
    result["receipt_sha256"] = hashlib.sha256(canonical_bytes(result)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "metrics": result["metrics"]}, sort_keys=True))
    return 0 if result["status"] == "PASS_KINEMATIC_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
