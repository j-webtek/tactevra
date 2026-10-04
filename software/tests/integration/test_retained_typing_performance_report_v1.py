from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.typing_performance_report_v1 import (
    REQUIRED_SCENARIOS,
    SCHEMA,
    STATUS,
)


ROOT = Path(__file__).resolve().parents[3]
REPORT = ROOT / "software/ai/eval/typing_performance_report_v1.json"
REPORT_FILE_SHA256 = (
    "024c5111810e9d0a5b67ea78389d2c7e5d19041ba31960fb3fcb495be98f74f6"
)
REPORT_CONTENT_SHA256 = (
    "a43a25056cff135d8756fbe7b15160b7a9ad0b49964e21e0c16a6c5eb2df291c"
)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def test_retained_pc8_report_is_hash_bound_complete_and_zero_authority():
    raw = REPORT.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REPORT_FILE_SHA256
    assert raw == raw.rstrip(b"\n") + b"\n"
    report = json.loads(raw)
    content_hash = report.pop("typing_performance_report_sha256")
    assert content_hash == REPORT_CONTENT_SHA256
    assert hashlib.sha256(_canonical(report)).hexdigest() == content_hash

    assert report["schema"] == SCHEMA
    assert report["status"] == STATUS
    assert report["evidence_class"] == "SYNTHETIC_OFFLINE_ONLY"
    assert tuple(report["scenario_order"]) == REQUIRED_SCENARIOS
    assert report["sample_count"] == 450
    assert all(
        report["scenarios"][scenario]["iterations"] == 50
        for scenario in REQUIRED_SCENARIOS
    )
    assert report["scenarios"]["FORCED_REJECTION"] == {
        "iterations": 50,
        "total_cpu_ns": report["scenarios"]["FORCED_REJECTION"][
            "total_cpu_ns"
        ],
        "predicted_route_duration_ns": report["scenarios"][
            "FORCED_REJECTION"
        ]["predicted_route_duration_ns"],
        "admitted": 0,
        "rejected": 50,
    }
    assert all(report["resources"]["ceilings_passed"].values())
    assert report["cache"]["cold_misses"] == 50
    assert report["cache"]["warm_hits"] == 50
    assert report["route_comparison"]["direct_hover_predicted_p50_ns"] < (
        report["route_comparison"]["park_baseline_predicted_p50_ns"]
    )
    assert report["controller_commands"] == []
    assert report["hardware_commands_generated"] == 0
    assert report["hardware_access"] is False
    assert report["physical_authority"] is False
    assert report["simulation_timing_is_physical_claim"] is False
    assert report["measured_typing_speed_claimed"] is False
