from __future__ import annotations
import json
from pathlib import Path
import sys
from jsonschema import Draft202012Validator
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))
from estimate_residual_v4_2_error_dependence import one_way_icc  # noqa: E402
from admit_residual_obstruction_v4_2_shards import canonical, digest  # noqa: E402

REPORT = AI_ROOT / "eval/residual_obstruction_v4_2_error_dependence_v1.json"
SCHEMA = AI_ROOT / "schemas/residual_obstruction_v4_2_error_dependence_v1.schema.json"


def test_unequal_cluster_icc_detects_grouped_errors():
    groups = ["a"] * 8 + ["b"] * 12 + ["c"] * 10 + ["d"] * 14
    errors = np.asarray([1.0] * 8 + [0.0] * 36)
    result = one_way_icc(errors, groups)
    assert result["status"] == "ESTIMATED"
    assert result["minimum_group_size"] == 8
    assert result["maximum_group_size"] == 14
    assert result["icc_nonnegative_for_planning"] > 0.5


def test_too_few_groups_are_explicitly_unestimable():
    result = one_way_icc(np.asarray([0.0, 1.0, 0.0, 1.0]), ["a", "a", "b", "b"])
    assert result["status"] == "NOT_ESTIMABLE_FEWER_THAN_THREE_NONTRIVIAL_GROUPS"


def test_retained_dependence_report_is_bound_and_fail_closed():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(report)
    core = {k: v for k, v in report.items() if k != "report_sha256"}
    assert report["report_sha256"] == digest(canonical(core))
    rule = report["v5_pre_evaluation_dependence_rule"]
    assert rule["required_axes"] == [
        "scene_id",
        "device_and_target_id",
        "obstruction_asset_signature_sha256",
        "appearance_id",
    ]
    assert rule["required_multiway_interactions"] == [
        "device_and_target_id_x_obstruction_asset_signature_sha256"
    ]
    assert "TWO_WAY_MULTIWAY_CLUSTER_BOOTSTRAP_UCB" in rule["multiway_rule"]
    assert rule["safety_gates_may_change"] is False
    assert (
        report["mid_motion_arm_mask_gate"]["mid_motion_observation_authorized"] is False
    )
    assert report["evaluation_opened"] is False
    assert report["hardware_writes"] == report["physical_movements"] == 0
