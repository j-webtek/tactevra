from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _module():
    path = ROOT / "software/integrations/isaac_sim/base_board_context_evidence_pack.py"
    spec = importlib.util.spec_from_file_location("arm247_context", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _kit():
    template = {
        "schema": "tactevra.isaac_lm4_base_board_raw_observation.v1",
        "source_capture_kit_sha256": None,
        "evidence_sources": [],
        "instrument_identity": None,
        "instrument_resolution_mm": None,
        "coordinate_frame": "B",
        "observer": None,
        "reviewer": None,
        "reviewer_decision": "PENDING",
        "board": {
            "accepted_source_hash": None,
            "frame_B_registration_verified": None,
            "width_mm": None,
        },
        "base_and_factory_clamp": {"accepted_source_hash": None},
    }
    core = {
        "schema": "tactevra.isaac_lm4_base_board_raw_capture_kit.v1",
        "status": "BLOCKED_RAW_OBSERVATIONS_AND_REVIEW_REQUIRED",
        "nominal_values_may_fill_observations": False,
        "raw_observation_template": template,
        "submission_completed": False,
        "physical_authority": False,
    }
    return {**core, "capture_kit_sha256": _sha(core)}


def _png(path: Path, width: int, height: int, suffix: bytes = b"") -> Path:
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + suffix
    )
    return path


def test_arm247_retains_photos_but_does_not_promote_them(tmp_path: Path) -> None:
    module = _module()
    first = _png(tmp_path / "ruler.png", 2880, 3840)
    second = _png(tmp_path / "board.png", 1920, 1080, b"distinct")

    result = module.build_context_evidence_pack(
        _kit(),
        [("ruler_context", first), ("board_context", second)],
        reference_root=tmp_path,
    )
    reversed_result = module.build_context_evidence_pack(
        _kit(),
        [("board_context", second), ("ruler_context", first)],
        reference_root=tmp_path,
    )

    assert result["status"] == "BLOCKED_PRECISION_METROLOGY_AND_INDEPENDENT_REVIEW_REQUIRED"
    assert result["retained_context_evidence_count"] == 2
    assert result["accepted_measurement_source_count"] == 0
    assert result["completed_measurement_field_count"] == 0
    assert result["context_evidence_may_fill_measurements"] is False
    assert result["observation_draft"]["board"]["accepted_source_hash"] is None
    assert result["observation_draft"]["evidence_sources"][0]["source_reference"] == "board.png"
    assert result["physical_authority"] is False
    assert reversed_result == result
    unsigned = dict(result)
    claimed = unsigned.pop("evidence_pack_sha256")
    assert claimed == _sha(unsigned)


@pytest.mark.parametrize("fault", ["category", "duplicate", "non_image", "tamper"])
def test_arm247_rejects_invalid_or_ambiguous_evidence(
    tmp_path: Path, fault: str
) -> None:
    module = _module()
    first = _png(tmp_path / "one.png", 10, 20)
    evidence = [("setup_context", first)]
    kit = _kit()
    if fault == "category":
        evidence = [("measured", first)]
    elif fault == "duplicate":
        evidence.append(("board_context", first))
    elif fault == "non_image":
        first.write_text("not an image")
    else:
        kit["physical_authority"] = True

    with pytest.raises(module.BaseBoardContextEvidenceError):
        module.build_context_evidence_pack(kit, evidence, reference_root=tmp_path)
