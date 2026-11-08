from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/base_board_raw_capture_compiler.py"
    spec = importlib.util.spec_from_file_location("arm246_compiler", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _templates():
    template = {
        "schema": "tactevra.isaac_lm4_capture_packet_submission.v1",
        "source_arm242_report_sha256": "1" * 64,
        "packet_id": "base_board_installation",
        "source_packet_sha256": "2" * 64,
        "profile_scope": ["no_attachment", "stylus_attachment"],
        "evidence_sources": [],
        "body_submissions": [
            {
                "body_id": "installation:base_and_factory_clamp",
                "parent_frame": "board",
                "binding_mode": "STATIC_ROOT",
                "acceptance_values": {
                    field: None
                    for field in [
                        "accepted_source_hash",
                        "board_to_base_transform",
                        "geometry_uncertainty_mm",
                        "installed_clamp_footprint",
                        "local_frame_envelope_primitives",
                    ]
                },
            },
            {
                "body_id": "workcell:board_solid",
                "parent_frame": "board",
                "binding_mode": "STATIC_ROOT",
                "acceptance_values": {
                    field: None
                    for field in [
                        "accepted_source_hash",
                        "flatness_or_bow_bound",
                        "geometry_uncertainty_mm",
                        "installed_board_pose",
                        "local_frame_envelope_primitives",
                    ]
                },
            },
        ],
        "instrument_identity": None,
        "instrument_resolution_mm": None,
        "coordinate_frame": None,
        "units": "mm",
        "reviewer": None,
        "reviewer_decision": "PENDING",
        "submission_sha256": None,
    }
    core = {
        "schema": "tactevra.isaac_lm4_capture_submission_templates.v1",
        "status": "BLOCKED_CAPTURE_SUBMISSIONS_REQUIRED",
        "submission_templates": [template],
        "template_count": 1,
    }
    return {**core, "templates_sha256": _sha(core)}


def _reconciliation():
    priors = [
        {"prior_id": "board", "disposition": "COMPARISON_TARGET_ONLY_NOT_MEASURED"},
        {"prior_id": "base", "disposition": "SEED_ONLY_NOT_MEASURED"},
        {"prior_id": "clamp", "disposition": "PARTIAL_NOT_MEASURED"},
    ]
    core = {
        "schema": "tactevra.isaac_lm4_base_board_prior_reconciliation.v1",
        "status": "BLOCKED_INSTALLED_METROLOGY_STILL_REQUIRED",
        "accepted_field_count": 0,
        "required_field_count": 10,
        "reusable_priors": priors,
        "submission_completed": False,
        "physical_authority": False,
    }
    return {**core, "reconciliation_sha256": _sha(core)}


def _kit():
    return _module().build_capture_kit(
        _templates(),
        _reconciliation(),
        templates_file_sha256="a" * 64,
        reconciliation_file_sha256="b" * 64,
    )


def _observation():
    kit = _kit()
    return kit, {
        "schema": "tactevra.isaac_lm4_base_board_raw_observation.v1",
        "source_capture_kit_sha256": kit["capture_kit_sha256"],
        "evidence_sources": [
            {"source_file_sha256": "e" * 64, "source_reference": "measurement record"}
        ],
        "instrument_identity": "unit-test caliper and straightedge",
        "instrument_resolution_mm": 0.1,
        "coordinate_frame": "B",
        "observer": "observer one",
        "reviewer": "reviewer two",
        "reviewer_decision": "ACCEPTED_MEASURED",
        "board": {
            "accepted_source_hash": "e" * 64,
            "frame_B_registration_verified": True,
            "width_mm": 610.2,
            "depth_mm": 456.8,
            "thickness_mm": 18.1,
            "flatness_or_bow_bound_mm": 0.7,
            "geometry_uncertainty_mm": 0.5,
        },
        "base_and_factory_clamp": {
            "accepted_source_hash": "e" * 64,
            "base_origin_B_mm": [305.2, 456.7, 0.1],
            "base_rotation_row_major": [0.0, 1.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, 1.0],
            "clamp_min_B_mm": [224.8, 405.0, -18.2],
            "clamp_max_B_mm": [385.4, 457.3, 62.0],
            "geometry_uncertainty_mm": 0.8,
        },
    }


def test_arm246_builds_blank_zero_authority_capture_kit() -> None:
    kit = _kit()

    assert kit["status"] == "BLOCKED_RAW_OBSERVATIONS_AND_REVIEW_REQUIRED"
    assert kit["nominal_values_may_fill_observations"] is False
    assert kit["raw_observation_template"]["board"]["width_mm"] is None
    assert kit["submission_completed"] is False
    assert kit["physical_authority"] is False


def test_arm246_compiles_reviewed_observation_deterministically() -> None:
    module = _module()
    kit, observation = _observation()
    result = module.compile_observation(_templates(), kit, observation)
    body = {row["body_id"]: row["acceptance_values"] for row in result["body_submissions"]}

    assert result["reviewer_decision"] == "ACCEPTED_MEASURED"
    assert body["workcell:board_solid"]["local_frame_envelope_primitives"][0][
        "half_extents_mm"
    ] == [305.1, 228.4, 9.05]
    assert body["installation:base_and_factory_clamp"]["installed_clamp_footprint"] == {
        "minimum_B_xy_mm": [224.8, 405.0],
        "maximum_B_xy_mm": [385.4, 457.3],
    }
    assert len(
        body["workcell:board_solid"]["local_frame_envelope_primitives"][0][
            "rotation_row_major"
        ]
    ) == 9
    unsigned = dict(result)
    claimed = unsigned.pop("submission_sha256")
    assert claimed == _sha(unsigned)


@pytest.mark.parametrize(
    "mutation",
    [
        "pending",
        "same_reviewer",
        "unknown_source",
        "unverified_frame",
        "bad_bounds",
        "bad_rotation",
    ],
)
def test_arm246_rejects_unaccepted_or_invalid_observations(mutation: str) -> None:
    module = _module()
    kit, observation = _observation()
    if mutation == "pending":
        observation["reviewer_decision"] = "PENDING"
    elif mutation == "same_reviewer":
        observation["reviewer"] = observation["observer"]
    elif mutation == "unknown_source":
        observation["board"]["accepted_source_hash"] = "f" * 64
    elif mutation == "unverified_frame":
        observation["board"]["frame_B_registration_verified"] = False
    elif mutation == "bad_bounds":
        observation["base_and_factory_clamp"]["clamp_max_B_mm"][0] = 100.0
    else:
        observation["base_and_factory_clamp"]["base_rotation_row_major"] = [1.0] * 9

    with pytest.raises(module.BaseBoardRawCaptureError):
        module.compile_observation(_templates(), kit, observation)


def test_arm246_rejects_tampered_lineage() -> None:
    module = _module()
    templates = copy.deepcopy(_templates())
    templates["submission_templates"][0]["profile_scope"] = []

    with pytest.raises(module.BaseBoardRawCaptureError):
        module.build_capture_kit(
            templates,
            _reconciliation(),
            templates_file_sha256="a" * 64,
            reconciliation_file_sha256="b" * 64,
        )
