"""Tests for static-camera collision evidence intake of the entry bridge."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


AI_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = AI_DIR.parents[1]
sys.path[:0] = [str(AI_DIR), str(AI_DIR.parent / "src")]

from rocell.simulation.collision import CollisionBindingMode  # noqa: E402
import rocell_ai.current_start_entry_collision_intake as subject  # noqa: E402


def _bridge() -> dict:
    return {
        "status": "REFERENCE_ENTRY_BRIDGE_SAMPLED_COLLISION_EVIDENCE_REQUIRED",
        "report_sha256": "a" * 64,
        "sample_count": 35,
        "frozen_hypothesis": {"tool_case_id": "bare-jaw-reference"},
    }


def test_intake_uses_static_camera_roster_and_remains_zero_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requirements = (
        SimpleNamespace(
            body_id="robot:link1", binding_mode=CollisionBindingMode.RIGID_FRAME
        ),
        SimpleNamespace(
            body_id="installation:static_camera_cable",
            binding_mode=CollisionBindingMode.STATIC_ROOT,
        ),
    )
    contract = SimpleNamespace(
        requirements=requirements,
        content_hash="b" * 64,
        to_dict=lambda: {"contract_id": "static-overhead"},
    )
    audit = SimpleNamespace(to_dict=lambda: {"diagnostic_ready": False})
    context = SimpleNamespace(
        scenario=SimpleNamespace(model_path=Path("model"), model_sha256="c" * 64),
        scene=object(),
    )
    monkeypatch.setattr(subject, "run_entry_bridge", lambda *args, **kwargs: _bridge())
    monkeypatch.setattr(subject, "load_static_simulation_context", lambda path: context)
    monkeypatch.setattr(
        subject,
        "load_pinned_urdf",
        lambda *args: SimpleNamespace(model=object(), sha256="d" * 64),
    )
    monkeypatch.setattr(
        subject,
        "build_roarm_m3_static_overhead_collision_contract",
        lambda *args: contract,
    )
    monkeypatch.setattr(subject, "audit_collision_geometry", lambda value: audit)
    monkeypatch.setattr(
        subject, "static_simulation_context_hashes", lambda value: {"bundle": "e" * 64}
    )

    report = subject.run(
        {}, workspace=WORKSPACE, profile_path=WORKSPACE / "profile.json"
    )

    assert report["status"] == subject.STATUS
    assert report["entry_bridge_sample_count"] == 35
    assert report["entry_bridge_adjacent_segment_count"] == 34
    assert report["required_configuration_body_ids"] == []
    assert report["required_configuration_geometry_binding_count"] == 0
    assert report["required_configuration_sweep_envelope_count"] == 0
    assert (
        report["static_camera_profile_separation"]["arm_camera_body_ids_present"]
        is False
    )
    assert report["collision_screening_executed"] is False
    assert report["physical_execution_authorized"] is False
    assert report["controller_commands"] == []
    assert report["transport_writes"] == 0


def test_intake_requires_reviewed_entry_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = _bridge()
    bridge["status"] = "OTHER"
    monkeypatch.setattr(subject, "run_entry_bridge", lambda *args, **kwargs: bridge)
    with pytest.raises(ValueError, match="reviewed entry bridge"):
        subject.run({}, workspace=WORKSPACE, profile_path=WORKSPACE / "profile.json")
