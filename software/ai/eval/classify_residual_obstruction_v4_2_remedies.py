"""Classify residual-v4.2 remedies without selecting a successor."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_v4_2_remedy_classification_v1.schema.json"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def canonical_hash(value: Any) -> str:
    data = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify(robustness_path: Path, audit_path: Path, source_commit: str) -> dict[str, Any]:
    robustness = load_json(robustness_path)
    audit = load_json(audit_path)
    if robustness["status"] != "FAILED_DEVELOPMENT_GATES":
        raise ValueError("v4.2 must be a preserved development rejection")
    if robustness["selected_threshold"] is not None or robustness["development_gate_met"]:
        raise ValueError("rejected v4.2 cannot have an installed threshold")
    if robustness["evaluation_opened"] or audit["evaluation_opened"]:
        raise ValueError("classification requires unopened evaluation")
    if robustness["fixture_bundle_sha256"] != audit["fixture_bundle_sha256"]:
        raise ValueError("source fixture mismatch")
    if robustness["checkpoint_sha256"] != audit["checkpoint_sha256"]:
        raise ValueError("source checkpoint mismatch")
    if robustness["candidate_workcell_mitigation"] != (
        "PROHIBIT_CABLE_ROUTING_ACROSS_KEYBOARD_OR_PHONE_INTERACTION_SURFACES"
    ):
        raise ValueError("unexpected cable workcell mitigation")

    core = {
        "schema": "tactevra.ai_residual_obstruction_v4_2_remedy_classification.v1",
        "scope": "SYNTHETIC_FAILURE_CLASSIFICATION_AND_PHYSICAL_PILOT_PLAN_NO_QUALIFICATION",
        "status": "PHYSICAL_PILOT_REQUIRED_BEFORE_SUCCESSOR_SELECTION",
        "source_commit": source_commit,
        "robustness_file_sha256": file_hash(robustness_path),
        "robustness_report_sha256": robustness["report_sha256"],
        "hard_case_audit_file_sha256": file_hash(audit_path),
        "hard_case_audit_report_sha256": audit["report_sha256"],
        "invariants": {
            "v4_2_rejected": True,
            "v4_2_gates_changed": False,
            "cable_cases_removed_from_required_detection": False,
            "cable_detector_backstop_required": True,
            "evaluation_opened": False,
            "v5_selected": False,
            "lighting_limit_guessed": False,
        },
        "observed_failure_drivers": [
            {
                "priority": 1,
                "driver": "LOW_CONTRAST_DARK_CABLE",
                "evidence": "Rubber cable supplies eight of the ten lowest obstruction scores; the least-bad threshold misses 144 of 4800 cable rows.",
            },
            {
                "priority": 2,
                "driver": "REFERENCE_OBSERVATION_LIGHTING_MISMATCH",
                "evidence": "The least-bad threshold has an 8.7222% warm-side false-stop rate and visible clear/adjacent hard cases show strong photometric change.",
            },
            {
                "priority": 3,
                "driver": "PHONE_TARGET_LOCAL_OVERLAP",
                "evidence": "Seven phone targets have negative robust quantile margins; phone:key_a is worst at -0.3130623579.",
            },
        ],
        "candidate_remedies": [
            {
                "rank": 1,
                "category": "MODEL_INPUT",
                "remedy": "EDGE_OR_TEXTURE_DIFFERENCE_CHANNELS",
                "decision": "MEASURE_WITH_PHYSICAL_PILOT_BEFORE_SELECTION",
                "reason": "Directly exposes low-contrast boundaries that RGB intensity differencing can suppress.",
            },
            {
                "rank": 2,
                "category": "MODEL_INPUT",
                "remedy": "HIGHER_TARGET_CONTEXT_RESOLUTION",
                "decision": "MEASURE_WITH_PHYSICAL_PILOT_BEFORE_SELECTION",
                "reason": "Tests whether thin cables occupy too few pixels in the current 96-by-96 representation.",
            },
            {
                "rank": 3,
                "category": "DATA",
                "remedy": "DARK_OBSTRUCTOR_HARD_EXAMPLE_WEIGHTING",
                "decision": "DEFER_UNTIL_REAL_MISS_AND_FALSE_STOP_TRADEOFF_IS_MEASURED",
                "reason": "It is inexpensive but may exchange cable misses for additional clear-target false stops.",
            },
            {
                "rank": 4,
                "category": "WORKCELL_RULE",
                "remedy": "PROHIBIT_CABLE_ROUTING_ACROSS_KEYBOARD_OR_PHONE_INTERACTION_SURFACES",
                "decision": "RETAIN_AS_FREQUENCY_REDUCTION_ONLY",
                "reason": "Commissioning reduces expected cable exposure while the detector remains the required backstop for dropped or shifted cables.",
            },
        ],
        "physical_pilot": {
            "purpose": "MEASURE_REMEDY_RELEVANCE_NOT_QUALIFY_DEPLOYMENT",
            "minimum_sessions": 3,
            "target_ids": [
                "keyboard:EQUAL", "keyboard:F", "keyboard:G", "keyboard:H", "keyboard:I",
                "phone:key_a", "phone:key_b", "phone:key_c", "phone:key_period",
            ],
            "required_observation_types": [
                "CLEAR_REFERENCE", "CLEAR_REPEAT", "DARK_CABLE", "TRANSLUCENT_CABLE", "HAND",
            ],
            "dark_cable_coverage_fractions": [0.2, 0.4, 0.6],
            "required_lighting_samples": [
                "MEASURED_LOW", "MEASURED_NOMINAL", "MEASURED_HIGH",
            ],
            "lighting_descriptor_fields": ["luminance", "red_green_ratio", "blue_green_ratio"],
            "maximum_relative_lighting_drift": None,
            "lighting_range_rule": "DERIVE_FROM_ACCEPTED_REAL_CAMERA_REFERENCE_VALIDITY_SAMPLES_BEFORE_SUCCESSOR_PREDECLARATION",
            "retain_original_image_bytes": True,
            "retain_reference_and_observation_hashes": True,
            "parked_pose_and_settle_required": True,
            "charuco_and_fixture_bindings_required": True,
        },
        "successor_decision_rule": {
            "edge_texture_first": True,
            "resolution_second": True,
            "hard_example_weighting_third": True,
            "compare_against_unchanged_rgb_difference_baseline": True,
            "cable_detection_remains_in_scope": True,
            "training_and_test_lighting_must_fit_measured_runtime_admission_envelope": True,
            "freeze_before_new_development_results": True,
        },
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "No physical pilot images or measured lighting envelope exist in this artifact.",
            "The plan does not select v5, change v4.2, open evaluation, or qualify deployment.",
            "Physical collection may require separately authorized park movements and must report their effects in the physical campaign.",
        ],
    }
    result = {**core, "report_sha256": canonical_hash(core)}
    schema = load_json(SCHEMA)
    errors = sorted(Draft202012Validator(schema).iter_errors(result), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ValueError(f"schema validation failed at {list(first.path)}: {first.message}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--robustness", type=Path, required=True)
    parser.add_argument("--hard-case-audit", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = classify(args.robustness, args.hard_case_audit, args.source_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
