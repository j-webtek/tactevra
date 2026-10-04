"""Freeze the real-camera residual pilot before any physical capture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
SCHEMA = AI_ROOT / "schemas" / "residual_obstruction_physical_pilot_v1.schema.json"


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
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(remedy_path: Path, source_commit: str) -> dict[str, Any]:
    remedy = load_json(remedy_path)
    invariants = remedy["invariants"]
    if remedy["status"] != "PHYSICAL_PILOT_REQUIRED_BEFORE_SUCCESSOR_SELECTION":
        raise ValueError("source remedy classification is not awaiting a physical pilot")
    if not invariants["v4_2_rejected"] or invariants["v5_selected"]:
        raise ValueError("source does not preserve rejection before v5 selection")
    if invariants["evaluation_opened"] or invariants["lighting_limit_guessed"]:
        raise ValueError("source opened evaluation or guessed lighting")
    if not invariants["cable_detector_backstop_required"]:
        raise ValueError("cable detection must remain a required backstop")

    core = {
        "schema": "tactevra.ai_residual_obstruction_physical_pilot.v1",
        "scope": "DEENERGIZED_REAL_CAMERA_MEASUREMENT_AND_ESCROW_PLAN_NO_QUALIFICATION",
        "status": "READY_FOR_DEENERGIZED_CAPTURE",
        "source_commit": source_commit,
        "remedy_file_sha256": file_hash(remedy_path),
        "remedy_report_sha256": remedy["report_sha256"],
        "supersedes_pilot_fields_only": {
            "source_evidence_id": "E-20261002-AI-528",
            "preserved_source_artifact": True,
            "replaced_coverage_fractions": [0.2, 0.4, 0.6],
            "reason": "Separate clearly visible, ambiguity-boundary, and clearly obstructed real cases before capture.",
        },
        "coverage_contract": [
            {"nominal_fraction": 0.10, "role": "CLEARLY_VISIBLE", "expected_decision": "VISIBLE", "primary_metric_included": True},
            {"nominal_fraction": 0.20, "role": "BOUNDARY_PROBE", "expected_decision": "EITHER_REPORTED", "primary_metric_included": False},
            {"nominal_fraction": 0.30, "role": "CLEARLY_OBSTRUCTED", "expected_decision": "ABSTAIN", "primary_metric_included": True},
            {"nominal_fraction": 0.60, "role": "CLEARLY_OBSTRUCTED", "expected_decision": "ABSTAIN", "primary_metric_included": True},
        ],
        "boundary_scoring": {
            "boundary_fraction": 0.20,
            "either_visible_or_abstain_accepted": True,
            "rows_retained": True,
            "rows_reported_separately": True,
            "strict_visible_and_strict_abstain_counterfactuals_reported": True,
            "silent_exclusion_prohibited": True,
        },
        "coverage_measurement": {
            "methods_required": ["MEASURED_PLACEMENT_TEMPLATE", "INDEPENDENT_HAND_ANNOTATED_MASK"],
            "safe_region_source": "HASH_BOUND_TARGET_MAP",
            "mask_and_template_artifacts_retained": True,
            "annotator_blind_to_model_score": True,
            "maximum_absolute_method_disagreement": 0.05,
            "disagreement_decision": "LABEL_UNRESOLVED_RETAIN_AND_REPORT_NO_MODEL_METRIC",
            "target_center_coverage_forces_abstain_label": True,
        },
        "data_use": {
            "measurement_session_ids": ["physical_pilot_measurement_01", "physical_pilot_measurement_02"],
            "escrow_session_ids": ["physical_pilot_escrow_01"],
            "measurement_rows_may_select_remedy": True,
            "measurement_rows_may_train_model": False,
            "escrow_rows_may_select_remedy": False,
            "escrow_rows_may_train_model": False,
            "escrow_pixels_opened": False,
            "escrow_open_rule": "ONLY_AFTER_CANDIDATE_REPRESENTATION_CHECKPOINT_AND_THRESHOLD_ARE_FROZEN",
            "future_real_training_requires_separate_capture": True,
        },
        "capture_safety": {
            "arm_deenergized_during_every_capture": True,
            "servo_power_isolated_and_verified": True,
            "controller_command_channel_disconnected": True,
            "park_pose_established_before_capture_phase": True,
            "capture_phase_robot_movement_count": 0,
            "capture_phase_hardware_write_count": 0,
            "hand_case_requires_verified_energy_isolation": True,
            "energized_capture_decision": "INVALID_RETAIN_AND_REPORT_DO_NOT_USE",
        },
        "capture_matrix": {
            "target_ids": remedy["physical_pilot"]["target_ids"],
            "observation_types": remedy["physical_pilot"]["required_observation_types"],
            "lighting_samples": remedy["physical_pilot"]["required_lighting_samples"],
            "lighting_descriptor_fields": remedy["physical_pilot"]["lighting_descriptor_fields"],
            "maximum_relative_lighting_drift": None,
            "minimum_sessions": 3,
            "original_bytes_and_hashes_required": True,
            "charuco_fixture_and_reference_bindings_required": True,
        },
        "preserved_invariants": {
            "v4_2_rejected": True,
            "v4_2_gates_changed": False,
            "cable_detection_required": True,
            "lighting_limit_guessed": False,
            "v5_selected": False,
            "evaluation_opened": False,
        },
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
        "limitations": [
            "This predeclaration contains no physical pixels or measurements.",
            "Boundary probes are reported separately and cannot be hidden from results.",
            "Escrow remains unopened and no pilot row is authorized for training.",
            "The capture plan does not qualify the camera, model, deployment, or execution.",
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
    parser.add_argument("--remedy-classification", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.remedy_classification, args.source_commit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
