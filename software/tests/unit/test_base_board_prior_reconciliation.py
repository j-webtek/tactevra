from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/base_board_prior_reconciliation.py"
    spec = importlib.util.spec_from_file_location("arm245_reconciliation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _workorder():
    required = {
        "installation:base_and_factory_clamp": [
            "accepted_source_hash",
            "board_to_base_transform",
            "geometry_uncertainty_mm",
            "installed_clamp_footprint",
            "local_frame_envelope_primitives",
        ],
        "workcell:board_solid": [
            "accepted_source_hash",
            "flatness_or_bow_bound",
            "geometry_uncertainty_mm",
            "installed_board_pose",
            "local_frame_envelope_primitives",
        ],
    }
    core = {
        "schema": "tactevra.isaac_lm4_base_board_capture_workorder.v1",
        "status": "BLOCKED_OPERATOR_MEASUREMENTS_AND_REVIEW_REQUIRED",
        "required_acceptance_fields_by_body": required,
        "unfilled_acceptance_field_count": 10,
        "submission_completed": False,
        "physical_authority": False,
    }
    digest = hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**core, "workorder_sha256": digest}


def _inputs():
    return {
        "workorder": _workorder(),
        "frame_contract": _load("software/config/arm_frame_contract.json"),
        "board_plane": _load(
            "software/config/calibration_candidates/rc03_int_r1_fixed_board_plane_2026-10-17.json"
        ),
        "hardware_profile": _load("software/config/simulation_hardware_profile.json"),
        "nominal_scene": _load(
            "software/integrations/isaac_sim/evidence/rc03_nominal_rigid_scene_20260929.json"
        ),
    }


def _build():
    values = _inputs()
    return _module().build_reconciliation(
        **values,
        source_file_sha256={name: str(index) * 64 for index, name in enumerate(values, 1)},
    )


def test_arm245_preserves_all_fields_as_unaccepted() -> None:
    result = _build()

    assert result["status"] == "BLOCKED_INSTALLED_METROLOGY_STILL_REQUIRED"
    assert result["accepted_field_count"] == 0
    assert result["required_field_count"] == 10
    assert result["capture_reduction"]["fields_completed"] == 0
    assert result["submission_completed"] is False


def test_arm245_retains_three_explicit_comparison_priors() -> None:
    result = _build()

    priors = {row["prior_id"]: row for row in result["reusable_priors"]}
    assert priors["board_nominal_solid"]["value"]["maximum_B_mm"] == [610.0, 457.0, 0.0]
    assert priors["base_nominal_pose"]["value"]["translation_B_mm"] == [305.0, 457.0, 0.0]
    assert priors["clamp_rear_edge_x_span"]["value"]["x_range_B_mm"] == [225.0, 385.0]
    assert all("NOT_" in row["disposition"] for row in priors.values())


def test_arm245_does_not_confuse_image_fit_with_geometry_uncertainty() -> None:
    result = _build()

    assert result["semantic_support"]["fixed_camera_board_plane_fit_rms_mm"] > 0
    assert "not board geometry uncertainty" in result["semantic_support"]["disposition"]
    for body in result["field_dispositions"].values():
        assert body["geometry_uncertainty_mm"] == "MISSING_ACCEPTED_EVIDENCE"


def test_arm245_preserves_zero_authority() -> None:
    result = _build()

    assert result["measurement_manifest_modified"] is False
    assert result["installed_collision_profile_generated"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert result["controller_commands"] == []


@pytest.mark.parametrize("source", ["workorder", "frame_contract", "board_plane", "hardware_profile", "nominal_scene"])
def test_arm245_rejects_source_drift(source: str) -> None:
    module = _module()
    values = _inputs()
    if source == "workorder":
        values[source]["physical_authority"] = True
    elif source == "frame_contract":
        values[source]["frames"]["B"] = "different"
    elif source == "board_plane":
        values[source]["safe_for_open_loop_contact"] = True
    elif source == "hardware_profile":
        values[source]["simulation_only"] = False
    else:
        values[source]["physical_authority"] = True

    with pytest.raises(module.BaseBoardPriorReconciliationError):
        module.build_reconciliation(
            **values,
            source_file_sha256={name: "a" * 64 for name in values},
        )
