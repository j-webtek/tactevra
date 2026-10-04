"""Evaluate parked-pose observation evidence without granting arm authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_SCHEMA = AI_ROOT / "schemas" / "parked_pose_qualification_campaign_v1.schema.json"
RESULT_SCHEMA = AI_ROOT / "schemas" / "parked_pose_qualification_result_v1.schema.json"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_strict_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _validate(document: dict[str, Any], schema_path: Path, label: str) -> None:
    schema = load_strict_json(schema_path)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        where = ".".join(str(item) for item in first.absolute_path) or "$"
        raise ValueError(f"{label} schema validation failed at {where}: {first.message}")


def _binomial_cdf(k: int, n: int, probability: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if probability <= 0:
        return 1.0
    if probability >= 1:
        return 0.0
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    terms = [
        math.lgamma(n + 1) - math.lgamma(index + 1) - math.lgamma(n - index + 1)
        + index * log_p + (n - index) * log_q
        for index in range(k + 1)
    ]
    maximum = max(terms)
    log_total = maximum + math.log(math.fsum(math.exp(term - maximum) for term in terms))
    return 0.0 if log_total < -745 else min(1.0, math.exp(log_total))


def _inverse_binomial_cdf(k: int, n: int, target: float) -> float:
    low, high = 0.0, 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        if _binomial_cdf(k, n, midpoint) > target:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def exact_binomial_interval(successes: int, trials: int, confidence: float = 0.95) -> dict[str, float | int]:
    """Return the two-sided Clopper-Pearson interval."""
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("invalid binomial counts")
    if trials == 0:
        return {"events": successes, "trials": trials, "rate": 0.0, "lower_95": 0.0, "upper_95": 1.0}
    alpha = 1.0 - confidence
    lower = 0.0 if successes == 0 else _inverse_binomial_cdf(successes - 1, trials, 1.0 - alpha / 2.0)
    upper = 1.0 if successes == trials else _inverse_binomial_cdf(successes, trials, alpha / 2.0)
    return {
        "events": successes,
        "trials": trials,
        "rate": successes / trials,
        "lower_95": lower,
        "upper_95": upper,
    }


def _score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    visible = [
        row for row in rows
        if not row["known_self_occlusion"] and row["residual_obstruction"] == "NONE"
    ]
    known = [row for row in rows if row["known_self_occlusion"]]
    residual = [row for row in rows if row["residual_obstruction"] != "NONE"]
    false_stops = [row for row in visible if row["fused_decision"] == "ABSTAIN"]
    accepted_known = [row for row in known if row["fused_decision"] == "VISIBLE"]
    accepted_residual = [row for row in residual if row["fused_decision"] == "VISIBLE"]
    geometric_misses = [row for row in known if row["geometric_decision"] == "VISIBLE"]
    residual_misses = [row for row in residual if row["residual_decision"] == "VISIBLE"]
    return {
        "observation_count": len(rows),
        "visible_count": len(visible),
        "known_self_occlusion_count": len(known),
        "residual_obstruction_count": len(residual),
        "false_stops": exact_binomial_interval(len(false_stops), len(visible)),
        "accepted_known_self_occlusion_count": len(accepted_known),
        "accepted_residual_obstruction_count": len(accepted_residual),
        "geometric_path_missed_known_self_occlusion_count": len(geometric_misses),
        "residual_path_missed_obstruction_count": len(residual_misses),
        "accepted_known_self_occlusion_ids": [row["observation_id"] for row in accepted_known],
        "accepted_residual_obstruction_ids": [row["observation_id"] for row in accepted_residual],
    }


def missing_campaign_receipt() -> dict[str, Any]:
    core = {
        "schema": "rocell.ai_parked_pose_qualification_result.v1",
        "scope": "SUPERVISED_PARKED_OBSERVATION_EVIDENCE_ONLY",
        "status": "INCOMPLETE",
        "campaign_sha256": None,
        "criteria": {},
        "synthetic": _score([]),
        "physical": {
            **_score([]), "completed_cycle_count": 0, "session_count": 0,
            "maximum_park_repeatability_mm": None,
            "maximum_charuco_drift_mm": None,
        },
        "incomplete_reasons": ["campaign_not_collected"],
        "physical_deployment_qualified": False,
        "controller_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "collection_effects": {
            "hardware_write_count": 0, "physical_movement_count": 0,
            "authorization_evidence_sha256": None,
        },
        "limitations": [
            "No parked-pose campaign has been collected or evaluated.",
            "Evidence completion supports owner review of a supervised parked observation workflow only.",
        ],
    }
    result = {**core, "result_sha256": canonical_hash(core)}
    _validate(result, RESULT_SCHEMA, "result")
    return result


def evaluate(campaign_path: Path) -> dict[str, Any]:
    campaign = load_strict_json(campaign_path)
    _validate(campaign, CAMPAIGN_SCHEMA, "campaign")
    core = {key: value for key, value in campaign.items() if key != "campaign_sha256"}
    if canonical_hash(core) != campaign["campaign_sha256"]:
        raise ValueError("campaign SHA-256 mismatch")
    synthetic_rows = campaign["synthetic_observations"]
    physical_rows = campaign["physical_cycles"]
    identifiers = [row["observation_id"] for row in synthetic_rows + physical_rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate observation identity")
    if any(row["truth_mask_used_as_model_input"] for row in synthetic_rows):
        raise ValueError("synthetic truth masks cannot be model inputs")
    for row in synthetic_rows + physical_rows:
        expected_fused = (
            "ABSTAIN" if "ABSTAIN" in {row["geometric_decision"], row["residual_decision"]}
            else "VISIBLE"
        )
        if row["fused_decision"] != expected_fused:
            raise ValueError(f"fusion is not conservative OR: {row['observation_id']}")
    effects = campaign["collection_effects"]
    if physical_rows and (
        effects["physical_movement_count"] == 0
        or effects["authorization_evidence_sha256"] is None
    ):
        raise ValueError("physical rows require authorized collection effects")
    synthetic = _score(synthetic_rows)
    physical = _score(physical_rows)
    completed = [row for row in physical_rows if row["park_completed"] and row["settled_before_capture"]]
    sessions = {row["session_id"] for row in completed}
    physical.update({
        "completed_cycle_count": len(completed),
        "session_count": len(sessions),
        "maximum_park_repeatability_mm": max((row["park_repeatability_mm"] for row in completed), default=None),
        "maximum_charuco_drift_mm": max((row["charuco_drift_mm"] for row in completed), default=None),
    })
    requirements = campaign["requirements"]
    synthetic_lighting = {row["lighting_variant_id"] for row in synthetic_rows}
    synthetic_calibration = {row["calibration_perturbation_id"] for row in synthetic_rows}
    synthetic_obstructions = {row["residual_obstruction"] for row in synthetic_rows}
    physical_obstructions = {row["residual_obstruction"] for row in physical_rows}
    physical_lighting = {row["lighting_condition_id"] for row in physical_rows}
    criteria = {
        "synthetic_minimum_met": len(synthetic_rows) >= requirements["minimum_synthetic_observations"],
        "synthetic_lighting_coverage_met": set(requirements["required_lighting_variant_ids"]) <= synthetic_lighting,
        "synthetic_calibration_coverage_met": set(requirements["required_calibration_perturbation_ids"]) <= synthetic_calibration,
        "synthetic_visible_cases_present": synthetic["visible_count"] > 0,
        "synthetic_known_self_occlusion_cases_present": synthetic["known_self_occlusion_count"] > 0,
        "synthetic_residual_obstruction_coverage_met": set(requirements["required_synthetic_residual_obstructions"]) <= synthetic_obstructions,
        "synthetic_zero_accepted_known_self_occlusions": synthetic["accepted_known_self_occlusion_count"] == 0,
        "synthetic_all_residual_obstructions_abstained": synthetic["accepted_residual_obstruction_count"] == 0,
        "synthetic_geometric_path_detected_known_self_occlusions": synthetic["geometric_path_missed_known_self_occlusion_count"] == 0,
        "synthetic_residual_path_detected_obstructions": synthetic["residual_path_missed_obstruction_count"] == 0,
        "physical_minimum_completed_cycles_met": len(completed) >= requirements["minimum_physical_completed_cycles"],
        "physical_minimum_sessions_met": len(sessions) >= requirements["minimum_physical_sessions"],
        "physical_all_rows_completed_and_settled": len(completed) == len(physical_rows),
        "physical_visible_cases_present": physical["visible_count"] > 0,
        "physical_known_self_occlusion_cases_present": physical["known_self_occlusion_count"] > 0,
        "physical_residual_obstruction_coverage_met": set(requirements["required_physical_residual_obstructions"]) <= physical_obstructions,
        "physical_lighting_coverage_met": set(requirements["required_physical_lighting_condition_ids"]) <= physical_lighting,
        "physical_repeatability_within_bound": bool(completed) and physical["maximum_park_repeatability_mm"] <= requirements["maximum_park_repeatability_mm"],
        "physical_charuco_drift_within_bound": bool(completed) and physical["maximum_charuco_drift_mm"] <= requirements["maximum_charuco_drift_mm"],
        "physical_zero_accepted_known_self_occlusions": physical["accepted_known_self_occlusion_count"] == 0,
        "physical_all_residual_obstructions_abstained": physical["accepted_residual_obstruction_count"] == 0,
        "physical_geometric_path_detected_known_self_occlusions": physical["geometric_path_missed_known_self_occlusion_count"] == 0,
        "physical_residual_path_detected_obstructions": physical["residual_path_missed_obstruction_count"] == 0,
    }
    incomplete = [key for key, passed in criteria.items() if not passed]
    status = "EVIDENCE_COMPLETE_FOR_OWNER_REVIEW" if not incomplete else "INCOMPLETE"
    result_core = {
        "schema": "rocell.ai_parked_pose_qualification_result.v1",
        "scope": "SUPERVISED_PARKED_OBSERVATION_EVIDENCE_ONLY",
        "status": status,
        "campaign_sha256": campaign["campaign_sha256"],
        "criteria": criteria,
        "synthetic": synthetic,
        "physical": physical,
        "incomplete_reasons": incomplete,
        "physical_deployment_qualified": False,
        "controller_authority": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "collection_effects": effects,
        "limitations": [
            "Evidence completion is not deployment qualification or physical authority.",
            "This protocol is limited to supervised capture after a commissioned park and settle cycle.",
            "Thirty physical cycles cannot establish a two-percent population failure ceiling; exact intervals remain visible.",
        ],
    }
    result = {**result_core, "result_sha256": canonical_hash(result_core)}
    _validate(result, RESULT_SCHEMA, "result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(args.campaign) if args.campaign else missing_campaign_receipt()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(rendered.encode("utf-8"))
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
