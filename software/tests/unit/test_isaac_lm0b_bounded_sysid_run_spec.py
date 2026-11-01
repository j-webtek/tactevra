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


def test_retained_aligned_chirp_spec_covers_all_drive_terms():
    evidence = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    payload = json.loads(
        (evidence / "aligned_chirp_sysid_run_spec_20261101.json").read_text(encoding="utf-8")
    )
    MODULE.validate_bounded_payload(payload, campaign="aligned-chirp-12")
    assert len(payload["parameters"]["selected"]) == 12
    assert [chunk["role"] for chunk in payload["telemetry"]["chunks"]] == [
        "train",
        "train",
        "train",
        "train",
        "train",
        "validation",
    ]
    assert payload["telemetry"]["command_alignment_seconds"] == MODULE.CHIRP_ALIGNMENT_SECONDS
    assert payload["outputs"]["apply_parameters_to_usd"] is False


def test_retained_aligned_chirp_receipts_are_hash_bound_and_nonphysical():
    evidence = ROOT / "software" / "integrations" / "isaac_sim" / "evidence"
    spec_receipt = json.loads(
        (evidence / "aligned_chirp_sysid_run_spec_receipt_20261101.json").read_text(
            encoding="utf-8"
        )
    )
    claimed = spec_receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(spec_receipt))
    assert spec_receipt["campaign"] == "aligned-chirp-12"
    assert spec_receipt["parameter_count"] == 12
    assert spec_receipt["observable_dof_indices"] == [0, 1, 2, 3, 4, 5]
    assert spec_receipt["weak_dof_indices_excluded"] == []
    assert spec_receipt["command_alignment_seconds"] == MODULE.CHIRP_ALIGNMENT_SECONDS

    solve_receipt = json.loads(
        (evidence / "aligned_chirp_sysid_solve_rehearsal_20261101.json").read_text(
            encoding="utf-8"
        )
    )
    claimed = solve_receipt.pop("receipt_sha256")
    assert claimed == MODULE._digest(MODULE._canonical(solve_receipt))
    assert solve_receipt["status"] == "PASS_ALIGNED_CHIRP_SYSID_REHEARSAL_WITH_WARNINGS"
    assert solve_receipt["selected_candidate"]["accepted"] is True
    assert solve_receipt["identifiability"]["identifiable_count"] == 12
    assert solve_receipt["identifiability"]["weak_excitation_dof_indices"] == []
    assert solve_receipt["validation"]["chunk_count"] == 1
    assert solve_receipt["tuning_assessment"]["status"] == "warn"
    assert solve_receipt["parameters_written"] is False
    assert solve_receipt["stage_saved"] is False
