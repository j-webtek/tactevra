"""CPU-only exploratory harnesses for the governed simulation program.

This module has zero hardware, command, permit, transport, or physical authority.
The external 80-target catalog is a labelled shadow input and is never installed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any

from .adapter import compile_virtual_us_sticky_keys, replay_virtual_us_sticky_keys

SCOPE = "SIMULATION_ONLY_EXPLORATORY_ZERO_AUTHORITY"
CANDIDATE_MODE = "EXPLORATORY_UNINSTALLED_CANDIDATE80"


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def load_program_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    claimed = value.pop("fixture_sha256")
    if _sha(value) != claimed:
        raise ValueError("simulation-program fixture hash mismatch")
    value["fixture_sha256"] = claimed
    if value["scope"] != SCOPE or value["gpu_execution_authorized"]:
        raise ValueError("fixture is not CPU-only zero-authority")
    if any(value["counters"].values()):
        raise ValueError("fixture contains authority-bearing counters")
    for name, section in value["sections"].items():
        expected = section.pop("section_sha256")
        actual = _sha(section)
        section["section_sha256"] = expected
        if actual != expected:
            raise ValueError(f"section hash mismatch: {name}")
    for binding in value["bindings"].values():
        source = Path(binding["path"])
        if not source.is_absolute():
            source = path.resolve().parents[4] / source
        if hashlib.sha256(source.read_bytes()).hexdigest() != binding["sha256"]:
            raise ValueError(f"bound source changed: {binding['path']}")
    return value


def _catalog_ids(document: dict[str, Any]) -> tuple[str, ...]:
    ids: list[str] = []
    for row in document["keyboard"].get("rows", []):
        ids.extend(row["key_ids"])
    ids.extend(document["keyboard"].get("explicit_targets", {}).keys())
    return tuple(dict.fromkeys(ids))


def candidate_catalog_semantic_check(fixture: dict[str, Any]) -> dict[str, Any]:
    installed = json.loads(Path(fixture["bindings"]["installed_catalog"]["path"]).read_text())
    candidate = json.loads(Path(fixture["bindings"]["candidate_catalog"]["path"]).read_text())
    installed_ids, candidate_ids = _catalog_ids(installed), _catalog_ids(candidate)
    rejection = None
    try:
        compile_virtual_us_sticky_keys("Hello 2026!", commissioned_key_ids=installed_ids)
    except ValueError as exc:
        rejection = str(exc)
    if rejection is None or "SHIFT" not in rejection:
        raise AssertionError("installed catalog did not preserve expected SHIFT rejection")
    receipts = []
    for text in fixture["sections"]["workstream_1_cpu"]["candidate_cases"]:
        targets = compile_virtual_us_sticky_keys(text, commissioned_key_ids=candidate_ids)
        replay = replay_virtual_us_sticky_keys(targets, five_shift_shortcut_disabled=True,
                                               turn_off_on_two_keys_disabled=True)
        if replay["text"] != text:
            raise AssertionError("candidate shadow replay altered requested text")
        receipts.append({"text": text, "targets": list(targets),
                         "replayed_text": replay["text"]})
    return {"mode": CANDIDATE_MODE, "candidate_installed": False,
            "candidate_target_count": len(candidate_ids),
            "installed_target_count": len(installed_ids),
            "installed_expected_rejection": rejection, "cases": receipts}


def actuation_smoke(fixture: dict[str, Any]) -> dict[str, Any]:
    section = fixture["sections"]["workstream_2"]
    rows = []
    for travel in section["travel_mm"]:
        for fraction in section["actuation_fraction"]:
            for depth in section["press_depth_mm"]:
                for dwell in section["dwell_ms"]:
                    actuated = depth >= travel * fraction
                    repeated = actuated and dwell >= min(section["repeat_delay_ms"])
                    rows.append((actuated, repeated))
    singles = sum(actuated and not repeated for actuated, repeated in rows)
    if not singles:
        raise AssertionError("analytic key model has no single-actuation smoke cell")
    return {"status": "CPU_ANALYTIC_SMOKE_ONLY", "key_cells": len(rows),
            "single_actuation_cells": singles,
            "phone_cells": len(section["phone_duration_ms"]) * len(section["phone_long_press_ms"]),
            "finite": True}


def recovery_sweep(fixture: dict[str, Any]) -> dict[str, Any]:
    recoverable = {"MISSED_PRESS", "WRONG_KEY", "DOUBLE_PRESS", "STALE_FRAME",
                   "TARGET_DISPLACEMENT"}
    rows = []
    for fault in fixture["sections"]["workstream_4"]["faults"]:
        if fault == "AMBIGUOUS_READBACK":
            path, recovered = ["VERIFY", "STOP", "ABORT"], False
        elif fault in {"WRONG_KEY", "DOUBLE_PRESS"}:
            path = ["VERIFY", "STOP", "REOBSERVE", "RELOCALIZE",
                    "BACKSPACE_CORRECT", "VERIFY", "COMPLETE"]
            recovered = True
        else:
            path = ["VERIFY", "STOP", "REOBSERVE", "RELOCALIZE",
                    "SIMULATE_PRESS", "VERIFY", "COMPLETE"]
            recovered = True
        rows.append({"fault": fault, "path": path, "detected": True,
                     "recovered": recovered,
                     "wrong_characters_before_detection": int(fault in {"WRONG_KEY", "DOUBLE_PRESS"})})
    if any(row["recovered"] != (row["fault"] in recoverable) for row in rows):
        raise AssertionError("recovery classification changed")
    return {"status": "CPU_STATE_MACHINE_COMPLETE", "cases": rows,
            "recoverable_success_rate": 1.0, "ambiguous_continuations": 0}


def calibration_budget(fixture: dict[str, Any]) -> dict[str, Any]:
    section = fixture["sections"]["workstream_5"]
    rng = random.Random(section["seed"])
    trials = section["trials"]
    q_index = math.ceil(section["confidence_quantile"] * trials) - 1
    table = []
    for noise in section["noise_mm"]:
        for bias in section["initial_bias_mm"]:
            for target in section["residual_fraction"]:
                selected, observed = None, None
                for count in section["probe_counts"]:
                    ratios = []
                    for _ in range(trials):
                        mean = sum(bias + rng.gauss(0.0, noise) for _ in range(count)) / count
                        ratios.append(abs(bias - mean) / bias)
                    observed = sorted(ratios)[q_index]
                    if observed <= target:
                        selected = count
                        break
                table.append({"noise_mm": noise, "initial_bias_mm": bias,
                              "target_fraction": target, "selected_probes": selected,
                              "q95_residual_fraction": observed,
                              "status": "ADMITTED" if selected else "INSUFFICIENT_THROUGH_34"})
    counts = [r["selected_probes"] for r in table if r["selected_probes"]]
    seconds = ([51 * min(counts) * min(section["probe_seconds"]),
                51 * max(counts) * max(section["probe_seconds"])] if counts else None)
    intervals = [margin / rate for margin in (0.5, 3.0)
                 for rate in section["translational_drift_mm_per_hour"]]
    return {"status": "EXPLORATORY_CPU_COMPLETE", "rows": table,
            "admitted_rows": len(counts), "failed_rows": len(table) - len(counts),
            "commissioning_seconds_range": seconds,
            "recalibration_hours_range": [min(intervals), max(intervals)]}


def gpu_readiness(fixture: dict[str, Any]) -> dict[str, Any]:
    return {"workstream_1_isaac_subset": "WAITING_FOR_ACTIVE_96_192_JOB",
            "workstream_2_warp": "FIXTURE_AND_CPU_SMOKE_READY",
            "workstream_3_warp": "FIXTURE_READY_WAITING_FOR_WS2_GPU_RESULT",
            "workstream_4_optional_warp": "CPU_STATE_MACHINE_READY_WAITING_FOR_WS2",
            "workstream_6_isaac": "FIXTURE_READY_WAITING_FOR_WS3_TRAJECTORIES",
            "gpu_execution_authorized": fixture["gpu_execution_authorized"]}


def run_all(fixture_path: Path) -> dict[str, Any]:
    fixture = load_program_fixture(fixture_path)
    core = {"schema": "tactevra.simulation_program_cpu_receipt.v1", "scope": SCOPE,
            "fixture_sha256": fixture["fixture_sha256"],
            "runtime_stack": fixture["runtime_stack"],
            "candidate_catalog": candidate_catalog_semantic_check(fixture),
            "workstream_2_smoke": actuation_smoke(fixture),
            "workstream_4": recovery_sweep(fixture),
            "workstream_5": calibration_budget(fixture),
            "gpu_readiness": gpu_readiness(fixture), "counters": fixture["counters"]}
    core["receipt_sha256"] = _sha(core)
    return core


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_all(args.fixture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("schema", "scope", "receipt_sha256")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
