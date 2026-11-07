from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from rocell.application.collision_readiness import assess_current_collision_readiness
from rocell.application.context import load_simulation_context
from rocell.simulation.collision import CollisionAttachmentProfile


ROOT = Path(__file__).resolve().parents[3]
SYSTEM_MANIFEST = ROOT / "software/config/system_manifest.json"


def _module():
    path = (
        ROOT
        / "software/integrations/isaac_sim/installed_measurement_gap_matrix.py"
    )
    spec = importlib.util.spec_from_file_location("arm239_gap_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _arm238_module():
    path = (
        ROOT
        / "software/integrations/isaac_sim/installed_collision_measurement_intake.py"
    )
    spec = importlib.util.spec_from_file_location("arm238_intake_for_arm239", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _plan() -> dict[str, object]:
    core: dict[str, object] = {
        "schema": (
            "tactevra.isaac_lm4_state_policy_lifted_route_geometry_intake_plan.v1"
        ),
        "status": "BLOCKED_PENDING_HASH_BOUND_INSTALLED_GEOMETRY",
        "target_id": "SPACE",
        "known_provisional_target_surface": {
            "coordinate_frame": "board",
            "center_board_xy_mm": [224.0, 112.0],
            "half_extent_xy_mm": [48.0, 7.0],
            "target_plane_z_board_mm": 21.0,
            "volume_complete": False,
            "accepted_measured": False,
            "source_state": "SYNTHETIC_BOUNDED_PRIOR_NOT_PRODUCT_SPECIFICATION",
        },
        "corrected_cartesian_route_materialized": False,
        "physical_authority": False,
        "next_required_stage": (
            "BUILD_HASH_BOUND_INSTALLED_COLLISION_MEASUREMENT_MANIFEST"
        ),
    }
    return {**core, "plan_sha256": _sha(core)}


def _inputs():
    arm238 = _arm238_module()
    profile = CollisionAttachmentProfile.STYLUS_ATTACHMENT
    context = load_simulation_context(ROOT, SYSTEM_MANIFEST)
    readiness = assess_current_collision_readiness(
        context, attachment_profile=profile
    )
    manifest, _, receipt = arm238.build_intake_package(
        _plan(),
        readiness,
        attachment_profile=profile,
        captured_at_utc="2026-11-07T21:15:00Z",
        reference_artifacts=[{
            "reference_id": f"photo/{index}.jpg",
            "sha256": f"{index:064x}",
            "byte_count": index,
            "classification": "REFERENCE_ONLY_NOT_ACCEPTED_MEASUREMENT",
        } for index in range(1, 13)],
    )
    return (
        manifest,
        receipt,
        _json(ROOT / "active-project/RoCell_v0_3/config/measurement_record.json"),
        _json(ROOT / "active-project/RoCell_v0_3/config/workcell_layout.json"),
        _json(ROOT / "software/config/arm_frame_contract.json"),
    )


def _report():
    module = _module()
    return module.build_measurement_gap_matrix(
        *_inputs(),
        source_files=[{
            "source_id": "test",
            "sha256": "a" * 64,
            "classification": "AUDIT_INPUT_NOT_ACCEPTED_MEASUREMENT",
        }],
    )


def test_arm239_preserves_all_pending_rows_and_zero_authority() -> None:
    report = _report()

    assert report["status"] == "BLOCKED_NO_ACCEPTED_MEASUREMENT_PROMOTIONS"
    assert report["required_body_count"] == 19
    assert report["accepted_body_count"] == 0
    assert report["pending_body_count"] == 19
    assert len(report["body_gap_matrix"]) == 19
    assert all(
        row["accepted_measurement_available"] is False
        for row in report["body_gap_matrix"]
    )
    assert report["nominal_values_promoted_to_measurement"] is False
    assert report["reference_photos_promoted_to_measurement"] is False
    assert report["measurement_manifest_modified"] is False
    assert report["isaac_started"] is False
    assert report["hardware_access"] is False
    assert report["physical_authority"] is False
    assert report["controller_commands"] == []


def test_arm239_retains_nominal_values_only_as_capture_priors() -> None:
    report = _report()
    priors = {row["prior_id"]: row for row in report["candidate_priors"]}

    assert priors["layout_board_nominal"]["values"] == {
        "width_mm": 610.0,
        "depth_mm": 457.0,
        "thickness_mm": 18.0,
    }
    assert priors["layout_keyboard_nominal"]["values"]["nominal_size"] == [
        315.0,
        147.0,
        21.0,
    ]
    assert priors["board_measurement_gate"]["gate_status"] == "NOT_TESTED"
    assert priors["keyboard_measurement_gate"]["gate_status"] == "NOT_TESTED"
    assert priors["keyboard_measurement_gate"][
        "populated_recorded_fields"
    ] == []
    assert all(
        "NOT_ACCEPTED_MEASUREMENT" in row["classification"]
        or row["classification"]
        in {
            "PHYSICAL_GATE_NOT_ACCEPTED_FOR_ICQ1",
            "FRAME_CONVENTION_NOT_GEOMETRY_MEASUREMENT",
            "MODEL_GEOMETRY_PENDING_PHYSICAL_VERIFICATION",
        }
        for row in priors.values()
    )


def test_arm239_separates_static_tool_target_and_sampled_cable_gaps() -> None:
    report = _report()
    rows = {row["body_id"]: row for row in report["body_gap_matrix"]}

    assert "flatness_or_bow_bound" in rows["workcell:board_solid"][
        "missing_acceptance_fields"
    ]
    assert "depressed_space_key_envelope" in rows["workcell:keyboard"][
        "missing_acceptance_fields"
    ]
    assert "stylus_projection_mm" in rows["attachment:contact_tool"][
        "missing_acceptance_fields"
    ]
    assert rows["attachment:moving_camera_cable"]["binding_mode"] == (
        "CONFIGURATION_SAMPLED"
    )
    assert "configuration_sampled_swept_envelope" in rows[
        "attachment:moving_camera_cable"
    ]["missing_acceptance_fields"]


def test_arm239_rejects_tampered_arm238_receipt() -> None:
    module = _module()
    manifest, receipt, measurements, layout, frames = _inputs()
    tampered = copy.deepcopy(receipt)
    tampered["attachment_profile"] = "no_attachment"

    with pytest.raises(
        module.InstalledMeasurementGapMatrixError,
        match="lineage changed",
    ):
        module.build_measurement_gap_matrix(
            manifest,
            tampered,
            measurements,
            layout,
            frames,
            source_files=[],
        )


def test_arm239_fails_closed_for_unreviewed_body() -> None:
    module = _module()
    manifest, receipt, measurements, layout, frames = _inputs()
    manifest = copy.deepcopy(manifest)
    manifest["body_measurements"][0]["body_id"] = "unknown:new-body"
    # Rehashing is intentionally unnecessary: lineage verification rejects it first.
    with pytest.raises(module.InstalledMeasurementGapMatrixError):
        module.build_measurement_gap_matrix(
            manifest,
            receipt,
            measurements,
            layout,
            frames,
            source_files=[],
        )
