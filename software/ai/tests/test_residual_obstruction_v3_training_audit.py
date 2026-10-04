from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT / "eval"))

from audit_residual_obstruction_v3_training import (  # noqa: E402
    fit_identity_geometry_baseline,
    select_memorization_subset,
)


def test_identity_geometry_baseline_is_chance_when_every_target_has_same_base_rate():
    entries = []
    geometry = {
        "keyboard:A": [0.0, 0.0, 1.0, 7.0, 7.0, 0.0],
        "phone:key_a": [100.0, 50.0, 2.0, 3.0, 5.5, 1.0],
    }
    for device, target_id in (("keyboard", "A"), ("phone", "key_a")):
        for index in range(8):
            entries.append({
                "device": device,
                "target_id": target_id,
                "expected_decision": "VISIBLE" if index < 2 else "ABSTAIN",
            })
    result = fit_identity_geometry_baseline(entries, geometry)
    assert result["positive_rate"] == 0.75
    assert result["minimum_target_positive_rate"] == 0.75
    assert result["maximum_target_positive_rate"] == 0.75
    assert result["pooled_training_auc"] == 0.5
    assert result["minimum_probability"] == result["maximum_probability"]


def test_memorization_subset_is_deterministic_and_label_balanced():
    entries = [
        {
            "device": "keyboard",
            "target_id": f"K{index % 75}",
            "expected_decision": "VISIBLE" if index < 600 else "ABSTAIN",
            "observation_id": f"row-{index}",
        }
        for index in range(1200)
    ]
    first = select_memorization_subset(entries, 500, 19031)
    second = select_memorization_subset(entries, 500, 19031)
    assert np.array_equal(first, second)
    assert len(set(first.tolist())) == 500
    selected = [entries[index] for index in first]
    assert sum(row["expected_decision"] == "VISIBLE" for row in selected) == 250
    assert sum(row["expected_decision"] == "ABSTAIN" for row in selected) == 250


def test_retained_training_audit_and_visual_review_are_bound_and_zero_authority():
    audit_path = AI_ROOT / "eval" / "residual_obstruction_v3_training_audit_v1.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    audit_schema = json.loads(
        (AI_ROOT / "schemas" / "residual_obstruction_v3_training_audit_v1.schema.json").read_text()
    )
    Draft202012Validator(audit_schema).validate(audit)
    audit_core = {key: value for key, value in audit.items() if key != "report_sha256"}
    assert hashlib.sha256(
        json.dumps(audit_core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == audit["report_sha256"]

    review = json.loads(
        (AI_ROOT / "eval" / "residual_obstruction_v3_training_visual_review_v1.json").read_text()
    )
    review_schema = json.loads(
        (
            AI_ROOT
            / "schemas"
            / "residual_obstruction_v3_training_visual_review_v1.schema.json"
        ).read_text()
    )
    Draft202012Validator(review_schema).validate(review)
    review_core = {key: value for key, value in review.items() if key != "review_sha256"}
    assert hashlib.sha256(
        json.dumps(review_core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == review["review_sha256"]
    assert review["source_report_file_sha256"] == hashlib.sha256(audit_path.read_bytes()).hexdigest()
    assert audit["development_pixels_opened"] is False
    assert audit["evaluation_opened"] is False
    assert review["hardware_writes"] == review["physical_movements"] == 0
