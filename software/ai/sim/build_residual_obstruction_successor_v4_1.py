"""Correct the unrendered v4 predeclaration using retained diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SCHEMA = "tactevra.ai_residual_obstruction_successor_fixture.v4_1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _bound(path: Path, schema: str, field: str) -> tuple[dict, bytes]:
    raw = path.resolve(strict=True).read_bytes()
    value = json.loads(raw)
    if value.get("schema") != schema:
        raise ValueError("schema mismatch")
    core = {key: item for key, item in value.items() if key != field}
    if value.get(field) != digest(canonical(core)):
        raise ValueError("canonical hash mismatch")
    return value, raw


def build(v4_path: Path, diagnostic_path: Path, power_path: Path) -> dict:
    v4, v4_bytes = _bound(v4_path, "tactevra.ai_residual_obstruction_successor_fixture.v4", "bundle_sha256")
    diagnostic, diagnostic_bytes = _bound(diagnostic_path, "tactevra.ai_residual_v3_memorization_diagnostic.v1", "report_sha256")
    power, power_bytes = _bound(power_path, "tactevra.ai_residual_v4_gate_power.v1", "receipt_sha256")
    if v4["images_generated"] or v4["training_started"] or v4["development_opened"] or v4["evaluation_opened"]:
        raise ValueError("v4 was already consumed")
    if diagnostic["legacy_control"]["gate_met"] is not False or diagnostic["spatial_control"]["gate_met"] is not True:
        raise ValueError("memorization diagnosis does not support spatial correction")
    if diagnostic["opposite_label_similarity"]["exact_opposite_label_rgb_duplicate_count"] != 0:
        raise ValueError("opposite-label duplicates remain unresolved")
    corrected = {key: value for key, value in v4.items() if key not in {"schema", "bundle_sha256", "source", "reference_contract", "training_plan", "development_gate", "limitations"}}
    source = {
        **v4["source"],
        "superseded_v4_file_sha256": digest(v4_bytes),
        "superseded_v4_bundle_sha256": v4["bundle_sha256"],
        "memorization_diagnostic_file_sha256": digest(diagnostic_bytes),
        "memorization_diagnostic_report_sha256": diagnostic["report_sha256"],
        "gate_power_file_sha256": digest(power_bytes),
        "gate_power_receipt_sha256": power["receipt_sha256"],
    }
    reference = {
        **v4["reference_contract"],
        "reference_lighting_seed_independent_of_observation": True,
        "reference_lighting_varies_across_scene_target_groups": True,
        "reference_observation_lighting_mismatch_required_in_training": True,
        "photometric_normalization_precedes_difference": True,
    }
    training = {
        **v4["training_plan"],
        "spatial_pool_operator": "DETERMINISTIC_FIXED_AVERAGE_POOL_4X4_TO_6X6",
        "photometric_normalization": {
            "algorithm": "PER_CROP_P05_P95_LUMINANCE_AND_CHANNEL_MEAN_NORMALIZATION",
            "fit_required": False,
            "applied_to_reference_and_observation_independently": True,
            "normalized_absolute_difference_computed_afterward": True,
            "raw_difference_channel_prohibited": True,
        },
    }
    core = {
        "schema": SCHEMA,
        "source": source,
        **corrected,
        "reference_contract": reference,
        "training_plan": training,
        "development_gate": power["recommended_gate"] | {
            "confidence_level": 0.95,
            "base_scene_cluster_bootstrap_resamples": 5000,
            "base_scene_cluster_bootstrap_seed": 19200,
            "worst_appearance_must_pass": True,
            "worst_variant_family_must_pass": True,
            "evaluation_must_remain_unopened": True,
        },
        "limitations": [
            "This v4.1 fixture supersedes the unrendered v4 fixture and remains synthetic",
            "Photometric normalization reduces but cannot eliminate physical lighting mismatch",
            "The spatial control proves finite-sample capacity, not generalization",
            "Evaluation identities remain frozen and unrendered until development passes",
            "No controller command, motion policy, permit, transport, or physical authority is included",
        ],
    }
    return {**core, "bundle_sha256": digest(canonical(core))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v4", type=Path, required=True)
    parser.add_argument("--memorization-diagnostic", type=Path, required=True)
    parser.add_argument("--gate-power", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.v4, args.memorization_diagnostic, args.gate_power)
    args.output.write_bytes(canonical(result) + b"\n")
    print(json.dumps({"bundle_sha256": result["bundle_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
