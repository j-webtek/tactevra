"""Consolidated, CPU-only first-motion rehearsal.

The module has no transport, permit, controller endpoint, or hardware adapter.
It binds one candidate configuration across A-F, runs the strict in-memory T102
runtime, and recomputes continuous key/tool clearance for the selected path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.arm.all_joint_command import all_joint_command
from rocell_ai.cpu_contact_and_ws3 import (
    _load_geometry,
    _nearest_key_distance,
    run_stage_ef_contact_screen,
)
from rocell_ai.first_motion_clearance_waypoints import (
    _hand_board_transform,
    _tip_xyz,
)
from rocell_ai.first_motion_controller_emulator import (
    InMemoryT102Controller,
    _baseline_joints,
    _execute_strict_runtime_path,
    _range_samples,
    load_emulator_fixture,
    load_first_motion_fixture,
)
from rocell_ai.first_motion_drills import (
    load_independent_observation_fixture,
    run_independent_observation_drills,
    run_wrong_model_drills,
)
from rocell_ai.tool_bound_exact_clearance import (
    _component_shapes,
    _key_boxes,
    _swept_collider_and_aabb,
    _translated_transform,
)

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
COUNTERS = {
    "gpu_job_count": 0,
    "hardware_write_count": 0,
    "physical_movement_count": 0,
    "real_command_count": 0,
    "permit_count": 0,
    "transport_count": 0,
}


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _resolve(workspace: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else workspace / path


def _verify_bound(binding: dict[str, str], workspace: Path) -> Path:
    path = _resolve(workspace, binding["path"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != binding["sha256"]:
        raise ValueError(f"bound input changed: {binding['path']}")
    return path


def _load_bound(binding: dict[str, str], workspace: Path) -> dict[str, Any]:
    path = _verify_bound(binding, workspace)
    return json.loads(path.read_text(encoding="utf-8"))


def load_consolidated_fixture(path: Path, *, workspace: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    unsigned = dict(document)
    claimed = unsigned.pop("fixture_sha256", None)
    if claimed != _sha(unsigned):
        raise ValueError("consolidated fixture hash mismatch")
    if document.get("schema") != "tactevra.first_motion_consolidated_fixture.v1":
        raise ValueError("unexpected consolidated fixture schema")
    if document.get("scope") != SCOPE or document.get("physical_authority") is not False:
        raise ValueError("consolidated fixture is not zero authority")
    if any(document["counters"].values()):
        raise ValueError("consolidated fixture contains nonzero counters")
    for name in ("configuration", "decision_rules", "emulator"):
        section = dict(document[name])
        section_hash = section.pop("section_sha256", None)
        if section_hash != _sha(section):
            raise ValueError(f"consolidated section changed: {name}")
    for binding in document["bindings"].values():
        _verify_bound(binding, workspace)
    return document


def _require_configuration(row: dict[str, Any], configuration_sha256: str) -> None:
    if row.get("configuration_sha256") != configuration_sha256:
        raise ValueError("stage configuration mismatch")


def _station_contact_count(document: dict[str, Any]) -> int:
    total = 0
    def visit(value: object, path: tuple[str, ...] = ()) -> None:
        nonlocal total
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, (*path, str(key)))
        elif isinstance(value, (int, float)) and any(
                "station" in part.lower() for part in path):
            total += int(value)
    visit(document.get("stage_c", {}))
    visit(document.get("stage_e_f", {}))
    return total


def _continuous_stage_c(
    contact_fixture: dict[str, Any], consolidated: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    exact_fixture, pose_family, world = _load_geometry(
        contact_fixture, workspace=workspace)
    config = consolidated["configuration"]
    park_screen = _load_bound(consolidated["bindings"]["park_screen"], workspace)
    park_row = next(row for row in park_screen["top_candidates"]
                    if row["pose_id"] == config["park_pose_id"])
    park = tuple(park_row["joint_positions_rad"][name]
                 for name in world.pose_bundle["joint_order"])
    rows = []
    global_minimum = float("inf")
    for profile in pose_family["profiles"]:
        bundle = profile["pose_bundle"]
        tool = bundle["tool_configuration"]
        length = float(tool["total_hand_tcp_to_tip_length_mm"])
        components = _component_shapes(exact_fixture, workspace, tool)
        boxes = {
            (width, thickness): _key_boxes(bundle, width, thickness)
            for width in (11.0, 15.0) for thickness in (2.0, 8.0)
        }
        park_tip = _tip_xyz(world, park, length)
        for pose in bundle["poses"]:
            xyz = pose["contact_target_board_mm"]
            hover = (float(xyz["x"]), float(xyz["y"]),
                     float(xyz["z"]) + float(config["hover_height_mm"]))
            target_joints = tuple(float(v) for v in pose["joint_positions_rad"])
            final_transform = _hand_board_transform(world, target_joints)
            safe_z = max(float(config["transit_height_board_z_mm"]),
                         park_tip[2], hover[2])
            tips = (
                park_tip,
                (park_tip[0], park_tip[1], safe_z),
                (hover[0], hover[1], safe_z),
                hover,
            )
            transforms = tuple(_translated_transform(
                final_transform, tip, length) for tip in tips)
            minimum = float("inf")
            limiting = None
            for phase_index, phase in enumerate(("RISE", "TRANSIT", "DESCEND")):
                for component in components:
                    swept, swept_aabb = _swept_collider_and_aabb(
                        component["vertices"], transforms[phase_index],
                        transforms[phase_index + 1], margin_mm=component["margin_mm"])
                    for keys in boxes.values():
                        distance, key_id = _nearest_key_distance(
                            swept, swept_aabb, keys,
                            requested_target_id="__NONE__",
                            component=component["component"])
                        if distance < minimum:
                            minimum = distance
                            limiting = {"phase": phase, "component": component["component"],
                                        "key_id": key_id}
            global_minimum = min(global_minimum, minimum)
            rows.append({
                "configuration_sha256": config["section_sha256"],
                "target_id": pose["target_id"],
                "tool_configuration_sha256": profile["tool_configuration_sha256"],
                "minimum_key_clearance_mm": minimum,
                "limiting_case": limiting,
                "decision": "PASS" if minimum > 0.0 else "STOP",
            })
    return {
        "configuration_sha256": config["section_sha256"],
        "method": config["exact_swept_distance_method"],
        "row_count": len(rows),
        "target_count": len({row["target_id"] for row in rows}),
        "minimum_key_clearance_mm": global_minimum,
        "stop_count": sum(row["decision"] == "STOP" for row in rows),
        "rows": rows,
    }


def _aggregate_trace(stage: str, traces: list[list[dict[str, Any]]],
                     config_hash: str) -> dict[str, Any]:
    sample_count = len(traces[0])
    samples = []
    for index in range(sample_count):
        rows = [trace[index] for trace in traces]
        samples.append({
            "sample_index": index,
            "time_ms_range": [min(row["time_ms"] for row in rows),
                              max(row["time_ms"] for row in rows)],
            "joint_position_rad_min": [min(row["measured_joints_rad"][j]
                                            for row in rows) for j in range(6)],
            "joint_position_rad_max": [max(row["measured_joints_rad"][j]
                                            for row in rows) for j in range(6)],
        })
    envelope = {"stage": stage, "configuration_sha256": config_hash,
                "prediction_count": len(traces), "samples": samples,
                "physical_accuracy_claim": False}
    envelope["envelope_sha256"] = _sha(envelope)
    return envelope


def _telemetry_envelopes(
    fixture: dict[str, Any], emulator_fixture: dict[str, Any],
    pose_family: dict[str, Any], park_screen: dict[str, Any],
) -> list[dict[str, Any]]:
    config_hash = fixture["configuration"]["section_sha256"]
    baseline = _baseline_joints(emulator_fixture)
    park_row = next(row for row in park_screen["top_candidates"]
                    if row["pose_id"] == "halton-0573")
    park = tuple(park_row["joint_positions_rad"][name]
                 for name in pose_family["profiles"][0]["pose_bundle"]["joint_order"])
    poses = {row["target_id"]: tuple(row["joint_positions_rad"])
             for row in pose_family["profiles"][0]["pose_bundle"]["poses"]}
    def six(values: tuple[float, ...]) -> tuple[float, ...]:
        if len(values) == 5:
            return (*values, baseline[5])
        if len(values) != 6:
            raise ValueError("stage target must contain five arm joints or six T102 joints")
        return values
    targets = {
        "A": tuple([baseline[0] + 0.005, *baseline[1:]]),
        "B": six(park), "C": six(poses["G"]), "D": six(poses["G"]),
        "E": six(poses["G"]), "F": six(poses["GRAVE"]),
    }
    envelopes = []
    for stage_index, stage in enumerate("ABCDEF"):
        traces = []
        for sample_index, sample in enumerate(_range_samples(
                emulator_fixture["controller_emulator"])):
            controller = InMemoryT102Controller(
                baseline, sample, seed=1907100 + stage_index * 100 + sample_index)
            command = all_joint_command(targets[stage], speed=sample.speed_setting,
                                        acceleration=sample.acceleration_setting)
            plant, runtime, _ = _execute_strict_runtime_path(
                emulator_fixture, controller, command,
                case_id=f"consolidated:{stage}:{sample.sample_id}")
            if runtime["runtime_status"] != "TERMINAL_NO_RETRY":
                raise ValueError("emulator runtime did not close terminally")
            traces.append(plant["telemetry"])
        envelopes.append(_aggregate_trace(stage, traces, config_hash))
    return envelopes


def run_consolidated_rehearsal(
    fixture: dict[str, Any], *, workspace: Path,
) -> dict[str, Any]:
    config_hash = fixture["configuration"]["section_sha256"]
    contact_fixture_path = _resolve(
        workspace, fixture["bindings"]["cpu_contact_fixture"]["path"])
    from rocell_ai.cpu_contact_and_ws3 import load_cpu_contact_fixture
    contact_fixture = load_cpu_contact_fixture(contact_fixture_path, workspace=workspace)
    pose_family = _load_bound(fixture["bindings"]["pose_family"], workspace)
    ef = run_stage_ef_contact_screen(contact_fixture, workspace=workspace)
    stage_c = _continuous_stage_c(contact_fixture, fixture, workspace=workspace)
    passive = _load_bound(fixture["bindings"]["passive_stage_result"], workspace)
    tray = _load_bound(fixture["bindings"]["tray_result"], workspace)
    cad = _load_bound(fixture["bindings"]["target_cad_result"], workspace)
    emulator_fixture = load_emulator_fixture(_resolve(
        workspace, fixture["bindings"]["emulator_fixture"]["path"]))
    park_screen = _load_bound(fixture["bindings"]["park_screen"], workspace)
    envelopes = _telemetry_envelopes(
        fixture, emulator_fixture, pose_family, park_screen)
    tray_row = next(row for row in tray["pad_contact_screen"]
                    if row["mode"] == fixture["configuration"]["stage_d_mode"])
    passive_by_stage = {row["stage"]: row for row in passive["stage_results"]}
    stage_rows = [
        {"stage": "A", "configuration_sha256": config_hash,
         "status": "SATISFIED_SIMULATION_ONLY" if passive_by_stage["A"]["clear"] else "STOP"},
        {"stage": "B", "configuration_sha256": config_hash,
         "status": "SATISFIED_SIMULATION_ONLY" if passive["clearance_waypoint_results"]["B"]["clear"] else "STOP"},
        {"stage": "C", "configuration_sha256": config_hash,
         "status": "SATISFIED_SIMULATION_ONLY" if stage_c["stop_count"] == 0 and _station_contact_count(cad) == 0 else "STOP"},
        {"stage": "D", "configuration_sha256": config_hash,
         "status": "SATISFIED_SIMULATION_ONLY" if tray_row["status"] == "CLEAR_EXPLORATORY_DISCRETE" else "STOP"},
        {"stage": "E", "configuration_sha256": config_hash,
         "status": "SATISFIED_SIMULATION_ONLY" if ef["decision"] == "PASS_EXPLORATORY_STAGE_EF_EXACT_CONTACT" else "STOP"},
        {"stage": "F", "configuration_sha256": config_hash,
         "status": "SATISFIED_SIMULATION_ONLY" if ef["decision"] == "PASS_EXPLORATORY_STAGE_EF_EXACT_CONTACT" else "STOP"},
    ]
    for row in stage_rows:
        _require_configuration(row, config_hash)
    readiness = load_first_motion_fixture(_resolve(
        workspace, fixture["bindings"]["readiness_fixture"]["path"]))
    observation = load_independent_observation_fixture(_resolve(
        workspace, fixture["bindings"]["observation_fixture"]["path"]))
    wrong = run_wrong_model_drills(readiness)
    observers = run_independent_observation_drills(observation, wrong)
    result = {
        "schema": "tactevra.first_motion_consolidated_result.v1",
        "scope": SCOPE, "fixture_sha256": fixture["fixture_sha256"],
        "configuration_sha256": config_hash,
        "stage_results": stage_rows,
        "stages_satisfied_simulation_only": [row["stage"] for row in stage_rows
                                               if row["status"] == "SATISFIED_SIMULATION_ONLY"],
        "first_stop_stage": next((row["stage"] for row in stage_rows
                                  if row["status"] == "STOP"), None),
        "stage_c_exact_sweep": stage_c,
        "stage_ef": {key: ef[key] for key in (
            "decision", "target_count", "row_count", "pass_row_count",
            "global_minimum_non_target_clearance_mm", "receipt_sha256")},
        "station_cad_contact_count": _station_contact_count(cad),
        "stage_d_tray_status": tray_row["status"],
        "telemetry_envelopes": envelopes,
        "predicted_telemetry_sample_count": sum(len(row["samples"]) for row in envelopes),
        "wrong_model": {"case_count": wrong["case_count"],
                        "original_gap_count": wrong["gap_count"],
                        "receipt_sha256": wrong["receipt_sha256"]},
        "independent_observers": {key: observers[key] for key in (
            "decision", "original_gap_count", "consequential_some_or_all_count",
            "undetected_consequential_count", "receipt_sha256")},
        "decision": "PASS_ALL_STAGES_SIMULATION_ONLY_PHYSICAL_BLOCKED"
                    if all(row["status"] == "SATISFIED_SIMULATION_ONLY"
                           for row in stage_rows)
                    and observers["undetected_consequential_count"] == 0
                    else "STOP_CONSOLIDATED_SIMULATION",
        "official_readiness": "NOT_READY_FOR_FIRST_POWERED_MOTION",
        **COUNTERS, "physical_authority": False,
        "limitations": fixture["limitations"],
    }
    result["receipt_sha256"] = _sha(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = load_consolidated_fixture(args.fixture, workspace=args.workspace)
    result = run_consolidated_rehearsal(fixture, workspace=args.workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": result["decision"],
                      "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_consolidated_fixture", "run_consolidated_rehearsal"]
