import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "software" / "integrations" / "isaac_sim" / "bounded_sysid_run_spec.py"
SPEC = importlib.util.spec_from_file_location("bounded_sysid_run_spec", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_retained_bounded_sysid_spec_has_only_observable_drive_terms():
    evidence = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    payload = json.loads((evidence / "bounded_sysid_run_spec_20261101.json").read_text(encoding="utf-8"))
    MODULE.validate_bounded_payload(payload)
    assert len(payload["parameters"]["selected"]) == 8
    assert [chunk["role"] for chunk in payload["telemetry"]["chunks"]] == ["train", "train", "validation"]
    assert payload["outputs"]["compute_parameter_confidence"] is False


def test_retained_bounded_sysid_receipt_is_hash_bound_and_nonphysical():
    evidence = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    receipt = json.loads((evidence / "bounded_sysid_run_spec_receipt_20261101.json").read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS_BOUNDED_SYSID_RUN_SPEC"
    assert receipt["parameter_count"] == 8
    assert receipt["observable_dof_indices"] == [0, 1, 2, 3]
    assert receipt["weak_dof_indices_excluded"] == [4, 5]
    assert receipt["uncalibrated_torque_excluded"] is True
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
    run_spec = (evidence / "bounded_sysid_run_spec_20261101.json").read_bytes()
    assert receipt["bindings"]["run_spec_sha256"] == MODULE._digest(run_spec)


def test_retained_solve_rehearsal_is_accepted_but_not_applied():
    evidence = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    receipt = json.loads((evidence / "bounded_sysid_solve_rehearsal_20261101.json").read_text(encoding="utf-8"))
    claimed = receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(receipt))
    assert receipt["status"] == "PASS_BOUNDED_SYSID_REHEARSAL_WITH_WARNINGS"
    assert receipt["selected_candidate"]["accepted"] is True
    assert receipt["identifiability"]["identifiable_count"] == 8
    assert receipt["identifiability"]["weak_excitation_dof_indices"] == [4, 5]
    assert receipt["validation"]["chunk_count"] == 1
    assert receipt["tuning_assessment"]["status"] == "warn"
    assert receipt["parameters_written"] is False
    assert receipt["stage_saved"] is False
    assert receipt["hardware_access"] is False
    assert receipt["physical_authority"] is False
