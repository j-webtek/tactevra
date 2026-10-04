from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))

from estimate_residual_v4_2_scene_icc import (  # noqa: E402
    binary_one_way_icc,
    with_delete_one_sensitivity,
)
from admit_residual_obstruction_v4_2_shards import canonical, digest  # noqa: E402

REPORT = AI_ROOT / "eval/residual_obstruction_v4_2_scene_icc_v1.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v4_2_scene_icc_v1.schema.json"


def test_icc_detects_scene_clustered_binary_errors() -> None:
    groups = [f"scene_{i}" for i in range(8) for _ in range(20)]
    errors = np.asarray([
        1.0 if scene in {0, 1} else 0.0
        for scene in range(8) for _ in range(20)
    ])
    result = with_delete_one_sensitivity(errors, groups)
    assert result["scene_count"] == 8
    assert result["icc_nonnegative_for_planning"] > 0.5
    assert len(result["delete_one_scene"]) == 8


def test_icc_rejects_unequal_clusters() -> None:
    with pytest.raises(ValueError, match="equal"):
        binary_one_way_icc(np.asarray([0.0, 1.0, 0.0, 1.0, 0.0]), ["a", "a", "b", "b", "c"])


def test_retained_scene_icc_is_valid_bound_and_fail_closed() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retained = json.loads(REPORT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(retained)
    core = {key: value for key, value in retained.items() if key != "report_sha256"}
    assert retained["report_sha256"] == digest(canonical(core))
    assert retained["source"]["reconstructed_development_probability_sha256"] == (
        "2ad7d47922c8e37573e34028346d6bfd3ab240c7c6179b3b88ca7098a0f87f6b"
    )
    assert retained["planning_recommendation"]["reestimate_from_v5_development"] is True
    assert retained["planning_recommendation"]["safety_gates_may_change"] is False
    assert retained["renderer_pre_results_amendment"]["failed_smoke_a_preserved"] is True
    assert retained["evaluation_opened"] is False
    assert retained["hardware_writes"] == retained["physical_movements"] == 0
