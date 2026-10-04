import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "software" / "ai" / "eval" / "classify_residual_obstruction_v4_2_remedies.py"
SPEC = importlib.util.spec_from_file_location("v42_remedies", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
ROBUSTNESS = ROOT / "software" / "ai" / "eval" / "residual_obstruction_v4_2_robustness_v1.json"
AUDIT = ROOT / "software" / "ai" / "eval" / "residual_obstruction_v4_2_hard_case_audit_v1.json"
COMMIT = "80d4804c250f4a822c717e6c4bc2b87048d0079e"


def test_classification_preserves_rejection_and_requires_physical_pilot():
    result = MODULE.classify(ROBUSTNESS, AUDIT, COMMIT)
    assert result["status"] == "PHYSICAL_PILOT_REQUIRED_BEFORE_SUCCESSOR_SELECTION"
    assert result["invariants"] == {
        "v4_2_rejected": True,
        "v4_2_gates_changed": False,
        "cable_cases_removed_from_required_detection": False,
        "cable_detector_backstop_required": True,
        "evaluation_opened": False,
        "v5_selected": False,
        "lighting_limit_guessed": False,
    }
    assert result["physical_pilot"]["maximum_relative_lighting_drift"] is None
    assert result["candidate_remedies"][0]["remedy"] == "EDGE_OR_TEXTURE_DIFFERENCE_CHANNELS"
    assert result["candidate_remedies"][1]["remedy"] == "HIGHER_TARGET_CONTEXT_RESOLUTION"
    assert result["hardware_writes"] == result["physical_movements"] == 0
    assert result["physical_authority"] is False


def test_classification_rejects_changed_failed_result(tmp_path):
    changed = copy.deepcopy(json.loads(ROBUSTNESS.read_text(encoding="utf-8")))
    changed["selected_threshold"] = 0.55
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot have an installed threshold"):
        MODULE.classify(path, AUDIT, COMMIT)


def test_classification_rejects_opened_evaluation(tmp_path):
    changed = copy.deepcopy(json.loads(AUDIT.read_text(encoding="utf-8")))
    changed["evaluation_opened"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="unopened evaluation"):
        MODULE.classify(ROBUSTNESS, path, COMMIT)
