from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.diagnose_residual_obstruction_v2 import REPORT_SCHEMA  # noqa: E402
from sim.render_residual_obstruction_v2 import canonical, load_bound, sha256_bytes  # noqa: E402


REPORT = AI_ROOT / "eval" / "residual_obstruction_v2_diagnostic_v1.json"
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_v2_diagnostic_v1.schema.json"


def test_retained_diagnostic_is_strict_reproducible_and_zero_authority():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report = load_bound(REPORT, REPORT_SCHEMA, "report_sha256")
    Draft202012Validator(schema).validate(report)
    core = {key: value for key, value in report.items() if key != "report_sha256"}
    assert report["report_sha256"] == sha256_bytes(canonical(core))
    assert report["target_separation"]["locally_separable_count"] == 0
    assert report["target_separation"]["nonseparable_count"] == 75
    assert report["checkpoint_changed"] is False
    assert report["threshold_changed"] is False
    assert report["evaluation_opened"] is False
    assert report["hardware_writes"] == 0
    assert report["physical_movements"] == 0
    assert report["physical_authority"] is False


def test_report_rejects_tampered_canonical_hash(tmp_path):
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    report["pairwise_auc"] = 1.0
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        load_bound(path, REPORT_SCHEMA, "report_sha256")
