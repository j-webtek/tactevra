"""Hash-bound, non-starting preflight for the ARM-257 native Isaac binding."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PREFLIGHT_SCHEMA = "tactevra.isaac_lm4_native_sweep_binding_preflight.v2"
BACKEND_SCHEMA = "tactevra.isaac_lm4_nominal_route_physics_backend.v1"
ASSESSMENT_SCHEMA = "tactevra.isaac_lm4_runtime_capability_assessment.v1"
SPHERE_PROFILE_SCHEMA = "tactevra.isaac_lm4_link_sphere_profile.v1"
PROOF_POLICY_SCHEMA = "tactevra.isaac_lm4_continuous_clearance_pair_policy.v1"
PROOF_REVIEW_SCHEMA = "tactevra.isaac_lm4_native_sweep_proof_input_review.v1"
EXPECTED_URDF_SHA256 = (
    "a565718e7d74b07702802cf41eb9549a6e38e50b5e80aa9b887ab1ae3d0d8190"
)
EXPECTED_PROOF_REVIEW_FILE_SHA256 = (
    "e395e84d4e0dc991025db73cf071ebaabc0e4bd73c461140bc7a1c12e0c5d97a"
)
EXPECTED_PROOF_REVIEW_SHA256 = (
    "aff177aee0fa1bba98d607eddfb7aae90f9c65b515e91da6fec4714c9eddd4b5"
)
EXPECTED_SPHERE_PROFILE_SHA256 = (
    "6150688561f6069efcf26ba0b843f8cf04542af7cfd357f02c35b799bc7aed3e"
)
EXPECTED_PROOF_POLICY_SHA256 = (
    "8bce70dd4498ca3da3687a4d43cfddac82422ec80ff68aa330496590ac71efc4"
)
REQUIRED_LINKS = (
    "robot:base_link",
    "robot:link1",
    "robot:link2",
    "robot:link3",
    "robot:link4",
    "robot:link5",
    "robot:gripper",
)


class NativeBindingPreflightError(ValueError):
    """Raised when a pinned source identity is malformed or drifts."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_hash(value: Mapping[str, Any], key: str, label: str) -> str:
    claimed = value.get(key)
    unsigned = dict(value)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeBindingPreflightError(f"{label} hash mismatch")
    return claimed


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise NativeBindingPreflightError(f"{label} digest is invalid")
    return value.lower()


def _sphere_profile_ready(profile: Mapping[str, Any] | None) -> bool:
    if profile is None:
        return False
    spheres = profile.get("link_spheres")
    return (
        profile.get("schema") == SPHERE_PROFILE_SCHEMA
        and profile.get("status") == "CERTIFIED_FOR_SIMULATION_CONTINUOUS_CLEARANCE"
        and profile.get("source_urdf_sha256") == EXPECTED_URDF_SHA256
        and isinstance(spheres, list)
        and {row.get("link_name") for row in spheres if isinstance(row, Mapping)}
        == set(REQUIRED_LINKS)
        and all(
            isinstance(row.get("radius_mm"), (int, float))
            and not isinstance(row.get("radius_mm"), bool)
            and row["radius_mm"] > 0
            and isinstance(row.get("local_center_mm"), list)
            and len(row["local_center_mm"]) == 3
            for row in spheres
            if isinstance(row, Mapping)
        )
    )


def _proof_policy_ready(policy: Mapping[str, Any] | None) -> bool:
    if policy is None:
        return False
    pairs = policy.get("accepted_exclusion_pairs")
    return (
        policy.get("schema") == PROOF_POLICY_SCHEMA
        and policy.get("status") == "ACCEPTED_FOR_SIMULATION_CONTINUOUS_CLEARANCE"
        and policy.get("source_urdf_sha256") == EXPECTED_URDF_SHA256
        and isinstance(pairs, list)
        and policy.get("physical_authority") is False
        and policy.get("hardware_access") is False
    )


def _reviewed_proof_inputs(
    review: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None, dict[str, str]]:
    if review is None:
        return None, None, {}
    review_hash = _require_hash(review, "review_sha256", "ARM-260 proof-input review")
    if (
        review.get("schema") != PROOF_REVIEW_SCHEMA
        or review.get("status") != "ACCEPTED_FOR_NATIVE_BINDING_IMPLEMENTATION"
        or review.get("certified_inputs_emitted") is not True
        or review.get("native_binding_admitted") is not False
        or review.get("launch_admitted") is not False
        or review.get("attempt_consumed") is not False
    ):
        raise NativeBindingPreflightError("ARM-260 proof-input review contract changed")
    profile = review.get("certified_sphere_profile")
    policy = review.get("accepted_pair_policy")
    if not isinstance(profile, Mapping) or not isinstance(policy, Mapping):
        raise NativeBindingPreflightError("ARM-260 certified proof inputs are missing")
    profile_hash = _require_hash(profile, "profile_sha256", "certified sphere profile")
    policy_hash = _require_hash(policy, "policy_sha256", "accepted pair policy")
    if (
        review_hash != EXPECTED_PROOF_REVIEW_SHA256
        or profile_hash != EXPECTED_SPHERE_PROFILE_SHA256
        or policy_hash != EXPECTED_PROOF_POLICY_SHA256
    ):
        raise NativeBindingPreflightError("certified proof-input identity changed")
    if profile.get("source_proposal_sha256") != policy.get("source_proposal_sha256"):
        raise NativeBindingPreflightError("certified proof-input proposal identities differ")
    return profile, policy, {
        "arm260_review_sha256": review_hash,
        "certified_sphere_profile_sha256": profile_hash,
        "accepted_pair_policy_sha256": policy_hash,
    }


def build_preflight(
    backend: Mapping[str, Any],
    capability: Mapping[str, Any],
    diagnostic_pair_policy: Mapping[str, Any],
    *,
    backend_file_sha256: str,
    capability_file_sha256: str,
    arm257_source_sha256: str,
    api_stub_sha256: str,
    urdf_sha256: str,
    geometry_prior_sha256: str,
    diagnostic_pair_policy_file_sha256: str,
    proof_input_review: Mapping[str, Any] | None = None,
    proof_input_review_file_sha256: str | None = None,
) -> dict[str, Any]:
    """Assess native-binding readiness without importing or starting Isaac."""

    backend_hash = _require_hash(backend, "backend_sha256", "ARM-255 backend")
    capability_hash = _require_hash(
        capability, "assessment_sha256", "ARM-256 assessment"
    )
    if (
        backend.get("schema") != BACKEND_SCHEMA
        or capability.get("schema") != ASSESSMENT_SCHEMA
        or capability.get("status")
        != "READY_TO_IMPLEMENT_CONSERVATIVE_SWEPT_ENVELOPE_ADAPTER"
        or capability.get("source_backend_sha256") != backend_hash
        or capability.get("required_adapter_strategy", {}).get("name")
        != "CONSERVATIVE_BOUNDING_SPHERE_INTERVAL_SWEEPS"
        or diagnostic_pair_policy.get("schema")
        != "tactevra.isaac_lm1_collision_pair_policy.v1"
        or diagnostic_pair_policy.get("status")
        != "ACCEPTED_FOR_ZERO_AUTHORITY_DIAGNOSTIC_ONLY"
        or diagnostic_pair_policy.get("limitations") is None
    ):
        raise NativeBindingPreflightError("native binding source contract changed")
    digests = {
        "arm255_backend_file_sha256": _digest(backend_file_sha256, "backend file"),
        "arm256_capability_file_sha256": _digest(
            capability_file_sha256, "capability file"
        ),
        "arm257_core_source_sha256": _digest(arm257_source_sha256, "ARM-257 source"),
        "isaac_api_stub_sha256": _digest(api_stub_sha256, "Isaac API stub"),
        "governed_urdf_sha256": _digest(urdf_sha256, "governed URDF"),
        "geometry_prior_file_sha256": _digest(geometry_prior_sha256, "geometry prior"),
        "diagnostic_pair_policy_file_sha256": _digest(
            diagnostic_pair_policy_file_sha256, "diagnostic pair policy"
        ),
    }
    if digests["governed_urdf_sha256"] != EXPECTED_URDF_SHA256:
        raise NativeBindingPreflightError("governed URDF identity changed")

    sphere_profile, proof_pair_policy, proof_hashes = _reviewed_proof_inputs(
        proof_input_review
    )
    if proof_input_review is not None:
        if proof_input_review_file_sha256 is None:
            raise NativeBindingPreflightError(
                "ARM-260 proof-input review file digest is missing"
            )
        review_file_hash = _digest(
            proof_input_review_file_sha256, "ARM-260 proof-input review file"
        )
        if review_file_hash != EXPECTED_PROOF_REVIEW_FILE_SHA256:
            raise NativeBindingPreflightError(
                "ARM-260 proof-input review file identity changed"
            )
        digests["arm260_proof_input_review_file_sha256"] = review_file_hash

    blockers: list[str] = []
    if not _sphere_profile_ready(sphere_profile):
        blockers.append("CERTIFIED_LINK_SPHERE_PROFILE_MISSING")
    if not _proof_policy_ready(proof_pair_policy):
        blockers.append("CONTINUOUS_CLEARANCE_PAIR_POLICY_MISSING")
    core: dict[str, Any] = {
        "schema": PREFLIGHT_SCHEMA,
        "preflight_id": "arm261-native-sweep-binding-readiness-001",
        "status": (
            "READY_TO_IMPLEMENT_NATIVE_BINDING"
            if not blockers
            else "BLOCKED_PENDING_CERTIFIED_PROOF_INPUTS"
        ),
        "source_backend_sha256": backend_hash,
        "source_capability_assessment_sha256": capability_hash,
        "source_digests": digests,
        "certified_proof_inputs": proof_hashes,
        "required_native_calls": [
            "articulation_forward_kinematics",
            "scene_query.sweep_sphere_any",
            "moving_self_collision_query",
        ],
        "required_link_names": list(REQUIRED_LINKS),
        "blockers": blockers,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "trajectory_playback": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": (
            "BUILD_AND_REVIEW_CERTIFIED_LINK_SPHERE_PROFILE_AND_PROOF_PAIR_POLICY"
            if blockers
            else "IMPLEMENT_HASH_PINNED_NATIVE_ISAAC_BINDING"
        ),
        "limitations": (
            [
                "diagnostic_pair_policy_is_not_promoted_to_continuous_clearance_proof",
                "certified_proof_inputs_are_not_yet_available_to_the_native_binding",
                "preflight_imports_no_isaac_module_and_consumes_no_route_attempt",
            ]
            if blockers
            else [
                "certification_is_limited_to_the_pinned_upstream_simulation_model",
                "installed_tool_clamp_cable_and_optional_camera_geometry_are_excluded",
                "native_binding_still_requires_implementation_and_independent_review",
                "preflight_imports_no_isaac_module_and_consumes_no_route_attempt",
            ]
        ),
    }
    return {**core, "preflight_sha256": _sha(core)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeBindingPreflightError(f"{path} must contain an object")
    return value


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--capability", type=Path, required=True)
    parser.add_argument("--diagnostic-pair-policy", type=Path, required=True)
    parser.add_argument("--arm257-source", type=Path, required=True)
    parser.add_argument("--api-stub", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--geometry-prior", type=Path, required=True)
    parser.add_argument("--proof-input-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof_input_review = (
        _load(args.proof_input_review) if args.proof_input_review is not None else None
    )
    result = build_preflight(
        _load(args.backend),
        _load(args.capability),
        _load(args.diagnostic_pair_policy),
        backend_file_sha256=_file_sha(args.backend),
        capability_file_sha256=_file_sha(args.capability),
        arm257_source_sha256=_file_sha(args.arm257_source),
        api_stub_sha256=_file_sha(args.api_stub),
        urdf_sha256=_file_sha(args.urdf),
        geometry_prior_sha256=_file_sha(args.geometry_prior),
        diagnostic_pair_policy_file_sha256=_file_sha(args.diagnostic_pair_policy),
        proof_input_review=proof_input_review,
        proof_input_review_file_sha256=(
            _file_sha(args.proof_input_review)
            if args.proof_input_review is not None
            else None
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
