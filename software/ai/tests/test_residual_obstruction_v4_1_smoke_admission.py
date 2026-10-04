from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "software/ai/eval/admit_residual_obstruction_v4_1_smoke.py"
SPEC = importlib.util.spec_from_file_location("v4_1_smoke_admission", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rank_auc_is_tie_aware() -> None:
    assert MODULE.rank_auc([False, True], [0.0, 1.0]) == 1.0
    assert MODULE.rank_auc([False, True], [1.0, 0.0]) == 0.0
    assert MODULE.rank_auc([False, True], [0.5, 0.5]) == 0.5


def test_rank_auc_requires_two_classes() -> None:
    with pytest.raises(ValueError, match="both classes"):
        MODULE.rank_auc([True, True], [0.1, 0.2])


def test_retained_smoke_admission_is_strict_and_hash_bound() -> None:
    report = json.loads(
        (ROOT / "software/ai/eval/residual_obstruction_v4_1_smoke_admission_v1.json").read_text()
    )
    schema = json.loads(
        (ROOT / "software/ai/schemas/residual_obstruction_v4_1_smoke_admission_v1.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(report)
    core = {key: value for key, value in report.items() if key != "report_sha256"}
    assert report["report_sha256"] == hashlib.sha256(MODULE.canonical(core)).hexdigest()
    assert report["target_ids"] == ["F", "G", "H", "I"]
    assert report["evaluation_observation_count"] == 0
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
