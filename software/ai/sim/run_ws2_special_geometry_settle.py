"""Prove stabilized-key neighborhood compilation and settling on MuJoCo Warp."""

from __future__ import annotations
import argparse
import json
from pathlib import Path

from ai.sim import run_ws2_stage_a_vectorized_throughput as throughput
from integrations.mujoco_warp import key_press_physics_probe as probe

ROOT = Path(__file__).resolve().parents[3]


def run(fixture_path: Path, target_id: str, device: str) -> dict:
    fixture = throughput.load_fixture(fixture_path)
    campaign, execution, staged, mechanism, physical = throughput.load_bound(fixture)
    if (
        target_id
        not in mechanism["mechanism_classes"]["STABILIZED_UNMEASURED"]["target_ids"]
    ):
        raise ValueError("settle proof is limited to declared stabilized targets")
    neighborhood = next(
        row for row in physical["neighborhoods"] if row["target_id"] == target_id
    )
    rows = probe.stage_a_vectorized_ordinary_batch_rows(
        campaign, staged, target_id=target_id
    )
    control = {
        "fixture_sha256": fixture["fixture_sha256"],
        "control": {
            "control_id": f"{target_id.lower()}-stabilized-geometry-settle",
            "control_kind": "ACTUATION",
            "target_id": target_id,
            "profile_id": fixture["smoke"]["profile_id"],
            "tip_id": fixture["smoke"]["tip_id"],
            "scenario_id": rows[0]["scenario_id"],
            "base_recipe_index": rows[0]["recipe_index"],
            "landing_sample_indices": [row["landing_sample_index"] for row in rows],
            "batch_rows": rows,
            "vectorized_world_controls": True,
            "recipe_override": {},
            "tool_compliance_model": "SERIES_QUASISTATIC",
            "tool_compliance_options": throughput.compliance_options(staged),
            "physical_keycap_half_extent_mm": fixture["smoke"][
                "physical_keycap_half_extent_mm"
            ],
            "physical_neighborhood": neighborhood["members"],
            "target_joint_index": neighborhood["target_joint_index"],
            "switch_closure_window_ms": fixture["smoke"]["switch_closure_window_ms"],
        },
    }
    receipt = probe.run_smoke_worker(
        campaign, execution, workspace=ROOT, device_name=device, control=control
    )
    result = {
        "schema": "tactevra.ws2_special_geometry_settle.v1",
        "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "target_id": target_id,
        "device": device,
        "mechanism_class": neighborhood["mechanism_class"],
        "neighborhood_signature_sha256": neighborhood["signature_sha256"],
        "member_count": len(neighborhood["members"]),
        "world_count": len(receipt["rows"]),
        "settle_pass": receipt["settle_pass"],
        "finite": receipt["finite"],
        "overflow_zero": receipt["overflow_zero"],
        "row_payload_sha256": throughput.value_sha(receipt["rows"]),
        "wall_elapsed_seconds": receipt["wall_elapsed_seconds"],
        "status": "PASS"
        if receipt["settle_pass"] and receipt["finite"] and receipt["overflow_zero"]
        else "STOP",
        "hardware_write_count": 0,
        "physical_movement_count": 0,
        "physical_authority": False,
    }
    result["receipt_sha256"] = throughput.value_sha(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--target", choices=("ENTER", "SPACE"), required=True)
    parser.add_argument("--device", choices=("cuda:0", "cuda:1"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.fixture, args.target, args.device)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    main()
