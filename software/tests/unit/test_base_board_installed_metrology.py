from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module(name: str, filename: str):
    path = ROOT / "software/integrations/isaac_sim" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _pack():
    draft = {
        "schema": "tactevra.isaac_lm4_base_board_raw_observation.v1",
        "source_capture_kit_sha256": "c" * 64,
        "evidence_sources": [{"source_file_sha256": "e" * 64, "source_reference": "context.jpg"}],
        "instrument_identity": None,
        "instrument_resolution_mm": None,
        "coordinate_frame": "B",
        "observer": None,
        "reviewer": None,
        "reviewer_decision": "PENDING",
        "board": {},
        "base_and_factory_clamp": {},
    }
    core = {
        "schema": "tactevra.isaac_lm4_base_board_context_evidence_pack.v1",
        "status": "BLOCKED_PRECISION_METROLOGY_AND_INDEPENDENT_REVIEW_REQUIRED",
        "context_evidence_may_fill_measurements": False,
        "accepted_measurement_source_count": 0,
        "observation_draft": draft,
        "physical_authority": False,
    }
    return {**core, "evidence_pack_sha256": _sha(core)}


def _session(pack):
    return {
        "schema": "tactevra.isaac_lm4_base_board_installed_metrology_session.v1",
        "source_evidence_pack_sha256": pack["evidence_pack_sha256"],
        "instrument_identity": "steel rule and 0.1 mm dial gauge",
        "instrument_resolution_mm": 0.1,
        "observer": "operator one",
        "reviewer": "reviewer two",
        "reviewer_decision": "ACCEPTED_MEASURED",
        "frame_B_registration_verified": True,
        "readings_mm": {
            "board_width": [610.0, 610.1, 609.9],
            "board_depth": [457.0, 457.1, 456.9],
            "board_thickness": [18.0, 18.1, 17.9],
            "board_top_surface_deviation": [0.0, 0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0, -0.1],
            "base_origin_B": [[300.0, 400.0, 0.0], [300.1, 400.0, 0.0], [299.9, 400.0, 0.0]],
            "base_x_datum_B": [[400.0, 400.0, 0.0], [400.1, 400.0, 0.0], [399.9, 400.0, 0.0]],
            "base_y_datum_B": [[300.0, 500.0, 0.0], [300.1, 500.0, 0.0], [299.9, 500.0, 0.0]],
            "clamp_min_B": [[220.0, 390.0, -18.0], [220.1, 390.0, -18.0], [219.9, 390.0, -18.0]],
            "clamp_max_B": [[380.0, 457.0, 62.0], [380.1, 457.0, 62.0], [379.9, 457.0, 62.0]],
        },
    }


def test_arm248_builds_zero_authority_repeated_reading_protocol() -> None:
    module = _module("arm248", "base_board_installed_metrology.py")
    protocol = module.build_protocol(_pack())
    assert protocol["status"] == "BLOCKED_READINGS_AND_INDEPENDENT_REVIEW_REQUIRED"
    assert protocol["session_template"]["readings_mm"]["board_width"] == [None] * 3
    assert len(protocol["session_template"]["readings_mm"]["board_top_surface_deviation"]) == 9
    assert protocol["context_evidence_may_fill_readings"] is False
    assert protocol["physical_authority"] is False


def test_arm248_compiles_conservative_arm246_observation() -> None:
    module = _module("arm248", "base_board_installed_metrology.py")
    compiler = _module("arm246", "base_board_raw_capture_compiler.py")
    pack = _pack()
    result = module.compile_session(
        pack, _session(pack), session_file_sha256="a" * 64, session_reference="session.json"
    )
    assert result["board"]["width_mm"] == pytest.approx(610.0)
    assert result["board"]["flatness_or_bow_bound_mm"] == pytest.approx(0.3)
    assert result["board"]["geometry_uncertainty_mm"] == pytest.approx(0.2)
    assert result["base_and_factory_clamp"]["base_rotation_row_major"] == pytest.approx(
        [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    )
    assert result["board"]["accepted_source_hash"] == "a" * 64
    compiler._validate_observation(result, "c" * 64)


@pytest.mark.parametrize(
    "fault", ["pending", "same_reviewer", "frame", "count", "bounds", "collinear", "tamper"]
)
def test_arm248_rejects_unreviewed_or_invalid_sessions(fault: str) -> None:
    module = _module("arm248", "base_board_installed_metrology.py")
    pack = _pack()
    session = _session(pack)
    if fault == "pending":
        session["reviewer_decision"] = "PENDING"
    elif fault == "same_reviewer":
        session["reviewer"] = session["observer"]
    elif fault == "frame":
        session["frame_B_registration_verified"] = False
    elif fault == "count":
        session["readings_mm"]["board_width"] = [610.0]
    elif fault == "bounds":
        session["readings_mm"]["clamp_max_B"] = [[100.0, 100.0, 0.0]] * 3
    elif fault == "collinear":
        session["readings_mm"]["base_y_datum_B"] = copy.deepcopy(
            session["readings_mm"]["base_x_datum_B"]
        )
    else:
        pack["physical_authority"] = True
    with pytest.raises(module.BaseBoardInstalledMetrologyError):
        module.compile_session(
            pack, session, session_file_sha256="a" * 64, session_reference="session.json"
        )
