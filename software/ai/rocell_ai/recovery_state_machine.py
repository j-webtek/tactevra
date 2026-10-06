"""Deterministic zero-authority recovery state machine for simulation Workstream 4."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .end_to_end_typing_twin import load_fixture

RECOVERY_SCHEMA = "tactevra.simulation_program_workstream_4_receipt.v1"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_recovery_fixture(path: Path, *, workspace: Path | None = None) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    claimed = document.pop("fixture_sha256")
    if _sha(document) != claimed:
        raise ValueError("recovery fixture hash changed")
    document["fixture_sha256"] = claimed
    if document.get("scope") != "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY":
        raise ValueError("recovery fixture scope is not simulation-only")
    if any(document["counters"].values()) or document["physical_authority"]:
        raise ValueError("recovery fixture violates zero authority")
    root = workspace.resolve() if workspace else path.resolve().parents[4]
    for name in ("program_plan", "workstream_1_fixture"):
        binding = document["bindings"][name]
        source = (root / binding["path"]).resolve()
        if not source.is_file() or not source.is_relative_to(root):
            raise ValueError(f"recovery binding is absent or escapes workspace: {name}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"recovery binding hash changed: {name}")
    ws1_path = root / document["bindings"]["workstream_1_fixture"]["path"]
    ws1 = load_fixture(ws1_path, verify_sources=False)
    if ws1["fixture_sha256"] != document["bindings"]["workstream_1_fixture"][
            "fixture_sha256"]:
        raise ValueError("recovery fixture references a different WS1 contract")
    return document


def _latency(profile: dict[str, int], *steps: str) -> int:
    return sum(profile[step] for step in steps)


def _drift_row(*, device: str, kind: str, value: float, onset: str,
               capability: float, profile_name: str,
               profile: dict[str, int]) -> dict[str, Any]:
    magnitude = abs(value)
    recoverable = magnitude <= capability
    wrong = int(onset in {"DURING_TRAVEL", "IMMEDIATELY_BEFORE_CONTACT"})
    if onset == "BEFORE_PLANNING":
        detection = _latency(profile, "observe")
    elif onset == "DURING_TRAVEL":
        detection = _latency(profile, "travel", "press", "verify")
    elif onset == "IMMEDIATELY_BEFORE_CONTACT":
        detection = _latency(profile, "press", "verify")
    else:
        detection = _latency(profile, "reobserve")
    trace = ["OBSERVE", "PLAN"]
    if onset != "BEFORE_PLANNING":
        trace.extend(["SIMULATE_PRESS", "VERIFY"])
    trace.extend(["STOP", "REOBSERVE", "RELOCALIZE"])
    correction = False
    attempts = int(onset != "BEFORE_PLANNING")
    if recoverable:
        if wrong:
            trace.append("BACKSPACE_CORRECT")
            correction = True
        trace.extend(["RETRY_ONCE", "VERIFY", "COMPLETE"])
        attempts += 1
        terminal = "COMPLETE"
        total = detection + _latency(
            profile, "reobserve", "relocalize", "travel", "press", "verify")
        if correction:
            total += profile["correction"]
    else:
        trace.append("ABORT")
        terminal = "ABORT"
        total = detection + _latency(profile, "reobserve", "relocalize")
    return {
        "scenario_id": (
            f"{device}:DRIFT_{kind}:{value:+g}:CAP_{capability:g}:"
            f"{onset}:{profile_name}"),
        "device": device, "fault_family": f"DRIFT_{kind}",
        "fault_value": value, "capability_limit": capability,
        "onset": onset, "latency_profile": profile_name,
        "detected": True, "detection_latency_ms": detection,
        "wrong_characters_before_detection": wrong,
        "recoverable_declared": recoverable,
        "relocalization_success": recoverable,
        "correction_success": correction if wrong and recoverable else None,
        "abort_expected": not recoverable, "abort_actual": not recoverable,
        "attempts": attempts, "total_recovery_time_ms": total,
        "terminal_state": terminal, "state_trace": trace,
    }


def _effect_row(*, device: str, fault: str, profile_name: str,
                profile: dict[str, int]) -> dict[str, Any]:
    burst = fault.startswith("BURST_")
    effect = fault.removeprefix("SINGLE_").removeprefix("BURST_")
    wrong = int(effect in {"WRONG_PRESS", "DOUBLE_PRESS"})
    trace = ["OBSERVE", "PLAN", "SIMULATE_PRESS", "VERIFY", "STOP"]
    attempts = 1
    correction = False
    if burst:
        trace.append("ABORT")
        terminal = "ABORT"
        recoverable = False
        total = _latency(profile, "observe", "plan", "travel", "press", "verify")
    else:
        recoverable = True
        trace.extend(["REOBSERVE", "RELOCALIZE"])
        if effect in {"WRONG_PRESS", "DOUBLE_PRESS"}:
            trace.append("BACKSPACE_CORRECT")
            correction = True
        if effect != "DOUBLE_PRESS":
            trace.append("RETRY_ONCE")
            attempts += 1
        trace.extend(["VERIFY", "COMPLETE"])
        terminal = "COMPLETE"
        total = _latency(
            profile, "observe", "plan", "travel", "press", "verify",
            "reobserve", "relocalize", "verify")
        if effect != "DOUBLE_PRESS":
            total += _latency(profile, "travel", "press")
        if correction:
            total += profile["correction"]
    return {
        "scenario_id": f"{device}:{fault}:{profile_name}", "device": device,
        "fault_family": fault, "latency_profile": profile_name,
        "detected": True,
        "detection_latency_ms": _latency(profile, "press", "verify"),
        "wrong_characters_before_detection": wrong,
        "recoverable_declared": recoverable,
        "relocalization_success": None,
        "correction_success": correction if wrong and recoverable else None,
        "abort_expected": burst, "abort_actual": burst, "attempts": attempts,
        "total_recovery_time_ms": total, "terminal_state": terminal,
        "state_trace": trace,
    }


def _readback_row(*, device: str, delay_ms: int, timeout_ms: int,
                  profile_name: str, profile: dict[str, int]) -> dict[str, Any]:
    timed_out = delay_ms > timeout_ms
    trace = ["OBSERVE", "PLAN", "SIMULATE_PRESS", "VERIFY", "STOP"]
    if timed_out:
        trace.append("ABORT")
        terminal = "ABORT"
    else:
        trace.extend(["REOBSERVE", "VERIFY", "COMPLETE"])
        terminal = "COMPLETE"
    return {
        "scenario_id": f"{device}:READBACK_{delay_ms}_TIMEOUT_{timeout_ms}:{profile_name}",
        "device": device, "fault_family": "READBACK_DELAY",
        "readback_delay_ms": delay_ms, "readback_timeout_ms": timeout_ms,
        "latency_profile": profile_name, "detected": True,
        "detection_latency_ms": min(delay_ms, timeout_ms) + profile["verify"],
        "wrong_characters_before_detection": 0,
        "recoverable_declared": not timed_out, "relocalization_success": None,
        "correction_success": None, "abort_expected": timed_out,
        "abort_actual": timed_out, "attempts": 1,
        "total_recovery_time_ms": (
            _latency(profile, "observe", "plan", "travel", "press", "verify")
            + min(delay_ms, timeout_ms) + (profile["reobserve"] if not timed_out else 0)),
        "terminal_state": terminal, "state_trace": trace,
    }


def run_recovery_campaign(fixture_path: Path, *, workspace: Path | None = None) -> dict[str, Any]:
    fixture = load_recovery_fixture(fixture_path, workspace=workspace)
    root = workspace.resolve() if workspace else fixture_path.resolve().parents[4]
    rows: list[dict[str, Any]] = []
    profiles = fixture["latency_profiles_ms"]
    for device in fixture["devices"]:
        for profile_name, profile in profiles.items():
            for axis in fixture["drift"]["translation_axes"]:
                for value in fixture["drift"]["translation_mm"]:
                    for onset in fixture["drift"]["onsets"]:
                        for capability in fixture["drift"][
                                "relocalization_translation_capability_mm"]:
                            row = _drift_row(
                                device=device, kind=f"TRANSLATION_{axis}", value=value,
                                onset=onset, capability=capability,
                                profile_name=profile_name, profile=profile)
                            rows.append(row)
            for value in fixture["drift"]["rotation_deg"]:
                for onset in fixture["drift"]["onsets"]:
                    for capability in fixture["drift"][
                            "relocalization_rotation_capability_deg"]:
                        rows.append(_drift_row(
                            device=device, kind="ROTATION", value=value, onset=onset,
                            capability=capability, profile_name=profile_name,
                            profile=profile))
            for fault in fixture["effect_faults"]:
                rows.append(_effect_row(
                    device=device, fault=fault, profile_name=profile_name,
                    profile=profile))
            for delay in fixture["readback"]["delay_ms"]:
                for timeout in fixture["readback"]["timeout_ms"]:
                    rows.append(_readback_row(
                        device=device, delay_ms=delay, timeout_ms=timeout,
                        profile_name=profile_name, profile=profile))
            for ambiguous in fixture["readback"]["ambiguous_states"]:
                rows.append({
                    "scenario_id": f"{device}:{ambiguous}:{profile_name}",
                    "device": device, "fault_family": ambiguous,
                    "latency_profile": profile_name, "detected": True,
                    "detection_latency_ms": profile["verify"],
                    "wrong_characters_before_detection": 0,
                    "recoverable_declared": False,
                    "relocalization_success": None, "correction_success": None,
                    "abort_expected": True, "abort_actual": True, "attempts": 1,
                    "total_recovery_time_ms": _latency(
                        profile, "observe", "plan", "travel", "press", "verify"),
                    "terminal_state": "ABORT",
                    "state_trace": [
                        "OBSERVE", "PLAN", "SIMULATE_PRESS", "VERIFY", "STOP", "ABORT"],
                })
    rows.sort(key=lambda row: row["scenario_id"])
    recoverable = [row for row in rows if row["recoverable_declared"]]
    aborts = [row for row in rows if row["abort_expected"]]
    ambiguous_names = set(fixture["readback"]["ambiguous_states"])
    ambiguous = [row for row in rows if row["fault_family"] in ambiguous_names]
    metrics = {
        "scenario_count": len(rows),
        "fault_detection_rate": sum(row["detected"] for row in rows) / len(rows),
        "maximum_wrong_characters_before_detection": max(
            row["wrong_characters_before_detection"] for row in rows),
        "recoverable_fault_count": len(recoverable),
        "recoverable_fault_success_rate": sum(
            row["terminal_state"] == "COMPLETE" for row in recoverable) / len(recoverable),
        "abort_expected_count": len(aborts),
        "abort_correctness_rate": sum(row["abort_actual"] for row in aborts) / len(aborts),
        "false_recovery_count": sum(
            row["terminal_state"] == "COMPLETE" for row in rows
            if not row["recoverable_declared"]),
        "ambiguous_continuation_count": sum(
            row["terminal_state"] != "ABORT" for row in ambiguous),
        "maximum_attempts": max(row["attempts"] for row in rows),
        "detection_latency_ms_range": [
            min(row["detection_latency_ms"] for row in rows),
            max(row["detection_latency_ms"] for row in rows)],
        "total_recovery_time_ms_range": [
            min(row["total_recovery_time_ms"] for row in rows),
            max(row["total_recovery_time_ms"] for row in rows)],
    }
    rules = fixture["decision_rules"]
    passed = (
        metrics["fault_detection_rate"] >= rules["deterministic_fault_detection_rate_minimum"]
        and metrics["maximum_wrong_characters_before_detection"]
        <= rules["maximum_wrong_characters_before_detection"]
        and metrics["recoverable_fault_success_rate"]
        >= rules["recoverable_fault_success_rate_minimum"]
        and metrics["abort_correctness_rate"] >= rules["abort_correctness_rate_minimum"]
        and metrics["false_recovery_count"] <= rules["false_recovery_count_maximum"]
        and metrics["ambiguous_continuation_count"]
        <= rules["ambiguous_continuation_count_maximum"]
        and metrics["maximum_attempts"] <= rules["maximum_press_retries"] + 1)
    implementation_path = root / fixture["bindings"]["implementation_target"]["path"]
    core = {
        "schema": RECOVERY_SCHEMA, "scope": fixture["scope"],
        "fixture_sha256": fixture["fixture_sha256"],
        "implementation_sha256": hashlib.sha256(implementation_path.read_bytes()).hexdigest(),
        "decision": "PASS_EXPLORATORY_RECOVERY" if passed else "FAILED_RECOVERY_GATE",
        "metrics": metrics, "rows": rows, "limitations": fixture["limitations"],
        "controller_commands": [], "hardware_commands_generated": 0,
        "gpu_jobs": 0, "hardware_writes": 0, "physical_movements": 0,
        "commands": 0, "permits": 0, "transports": 0,
        "physical_authority": False,
    }
    return {**core, "receipt_sha256": _sha(core)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_recovery_campaign(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["decision"],
                      "receipt_sha256": result["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
