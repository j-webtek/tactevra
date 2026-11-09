"""Compose the reviewed native sweep binding into the backend clearance API.

ARM-265 implements only the import-safe continuous-clearance portion of the
ARM-255 runtime protocol. Runtime objects are supplied by a separately admitted
worker; this module cannot import or start Isaac, load a scene, or consume an
attempt. Its CLI emits a definition for independent review and never constructs
the runtime adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from nominal_route_conservative_sweep_adapter import check_continuous_clearance
from nominal_route_native_sweep_binding import NativeIsaacConservativeSweepBinding


ADAPTER_SCHEMA = "tactevra.isaac_lm4_native_clearance_adapter.v1"
ADAPTER_REVIEW_SCHEMA = "tactevra.isaac_lm4_native_clearance_adapter_review.v1"
PREFLIGHT_SCHEMA = "tactevra.isaac_lm4_native_binding_integration_preflight.v1"
BINDING_SCHEMA = "tactevra.isaac_lm4_native_conservative_sweep_binding.v1"
BINDING_REVIEW_SCHEMA = (
    "tactevra.isaac_lm4_native_conservative_sweep_binding_review.v1"
)

EXPECTED_PREFLIGHT_SHA256 = (
    "e87de97b9c6ab066113f8eff8ad55712d134e073da035f4d447f3ee941914e69"
)
EXPECTED_BINDING_SHA256 = (
    "3fc667eabeddee46833c3d181bca1d438a9eb874d51a72565a5b083d110495fc"
)
EXPECTED_BINDING_REVIEW_SHA256 = (
    "a271316bf5deb863fdb67832a1291158a8292f7950a2e8a8c1b8189b2ef10b91"
)
EXPECTED_PREFLIGHT_FILE_SHA256 = (
    "af8c7e59d8edb1f2c137b4f032f37ae0d1df03282dd43fa02474ac8164d0ff4a"
)
EXPECTED_BINDING_FILE_SHA256 = (
    "e620ae81b082a6a1ce957af4b2419464a6d87f5c5c790cf99bc0f8987448c3da"
)
EXPECTED_BINDING_REVIEW_FILE_SHA256 = (
    "b13a1de38086c865040b81e49045ec3405b6d1b9c12876bec7a3fe45416d7620"
)
EXPECTED_PROOF_SOURCE_SHA256 = (
    "481f2e1e09b9ca45471e130e9022f4ff021b97cc6e72ce5b12f4dd2572b3a433"
)
EXPECTED_BINDING_SOURCE_SHA256 = (
    "a1c49cf0c982df91fe9d07dde7ee9bef3463ecbe4c58ce79d7eec91a66440ebe"
)


class NativeClearanceAdapterError(ValueError):
    """Raised when adapter definition or runtime composition changes."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NativeClearanceAdapterError("adapter input is not canonical JSON") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(document: Mapping[str, Any], key: str, label: str) -> str:
    claimed = document.get(key)
    unsigned = dict(document)
    unsigned.pop(key, None)
    if not isinstance(claimed, str) or claimed != _sha(unsigned):
        raise NativeClearanceAdapterError(f"{label} hash changed")
    return claimed


def _zero_authority(document: Mapping[str, Any]) -> bool:
    return (
        document.get("launch_admitted") is False
        and document.get("attempt_consumed") is False
        and document.get("hardware_access") is False
        and document.get("hardware_writes") == 0
        and document.get("physical_authority") is False
        and document.get("physical_movements") == 0
        and document.get("controller_commands") == []
        and document.get("wire_commands") == []
        and document.get("gate_promotions") == []
    )


def build_adapter_definition(
    preflight: Mapping[str, Any],
    binding: Mapping[str, Any],
    binding_review: Mapping[str, Any],
    *,
    preflight_file_sha256: str,
    binding_file_sha256: str,
    binding_review_file_sha256: str,
    proof_source_file_sha256: str,
    binding_source_file_sha256: str,
    adapter_source_file_sha256: str,
) -> dict[str, Any]:
    """Build a reviewable definition without constructing runtime objects."""

    preflight_hash = _require_hash(
        preflight, "integration_preflight_sha256", "ARM-264 preflight"
    )
    binding_hash = _require_hash(binding, "binding_sha256", "ARM-262 binding")
    review_hash = _require_hash(
        binding_review, "binding_review_sha256", "ARM-263 review"
    )
    if (
        preflight.get("schema") != PREFLIGHT_SCHEMA
        or preflight.get("status")
        != "READY_TO_IMPLEMENT_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER"
        or preflight_hash != EXPECTED_PREFLIGHT_SHA256
        or preflight.get("source_binding_sha256") != binding_hash
        or preflight.get("source_binding_review_sha256") != review_hash
        or preflight.get("next_required_stage")
        != "IMPLEMENT_AND_INDEPENDENTLY_REVIEW_ZERO_AUTHORITY_NATIVE_CLEARANCE_ADAPTER"
        or binding.get("schema") != BINDING_SCHEMA
        or binding.get("status") != "READY_FOR_INDEPENDENT_NATIVE_BINDING_REVIEW"
        or binding_hash != EXPECTED_BINDING_SHA256
        or binding_review.get("schema") != BINDING_REVIEW_SCHEMA
        or binding_review.get("status")
        != "ACCEPTED_FOR_NATIVE_BINDING_INTEGRATION"
        or review_hash != EXPECTED_BINDING_REVIEW_SHA256
        or binding_review.get("source_binding_sha256") != binding_hash
        or preflight_file_sha256 != EXPECTED_PREFLIGHT_FILE_SHA256
        or binding_file_sha256 != EXPECTED_BINDING_FILE_SHA256
        or binding_review_file_sha256 != EXPECTED_BINDING_REVIEW_FILE_SHA256
        or proof_source_file_sha256 != EXPECTED_PROOF_SOURCE_SHA256
        or binding_source_file_sha256 != EXPECTED_BINDING_SOURCE_SHA256
        or preflight.get("source_files_sha256", {}).get(
            "conservative_sweep_adapter_source"
        )
        != proof_source_file_sha256
        or preflight.get("source_files_sha256", {}).get("native_binding_source")
        != binding_source_file_sha256
        or binding.get("source_files_sha256", {}).get("binding_source")
        != binding_source_file_sha256
        or not isinstance(adapter_source_file_sha256, str)
        or len(adapter_source_file_sha256) != 64
        or preflight.get("runtime_construction_admitted_by_source_review") is not True
        or preflight.get("integration_adapter_implemented") is not False
        or preflight.get("integration_execution_admitted") is not False
        or preflight.get("verified_integration_surface", {}).get(
            "clearance_margin_mm"
        )
        != 0.5
        or preflight.get("verified_integration_surface", {}).get(
            "certified_exclusion_pair_count"
        )
        != 6
        or len(binding.get("accepted_exclusion_pairs", [])) != 6
        or not _zero_authority(preflight)
        or not _zero_authority(binding)
        or not _zero_authority(binding_review)
    ):
        raise NativeClearanceAdapterError(
            "native clearance adapter lineage or boundary changed"
        )

    core: dict[str, Any] = {
        "schema": ADAPTER_SCHEMA,
        "adapter_id": "arm265-zero-authority-native-clearance-adapter-001",
        "status": "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW",
        "source_preflight_sha256": preflight_hash,
        "source_binding_sha256": binding_hash,
        "source_binding_review_sha256": review_hash,
        "source_files_sha256": {
            "arm264_preflight": preflight_file_sha256,
            "arm262_binding": binding_file_sha256,
            "arm263_binding_review": binding_review_file_sha256,
            "arm257_proof_source": proof_source_file_sha256,
            "arm262_binding_source": binding_source_file_sha256,
            "arm265_adapter_source": adapter_source_file_sha256,
        },
        "backend_method": "check_continuous_clearance",
        "clearance_margin_mm": 0.5,
        "maximum_subdivision_depth": 12,
        "accepted_exclusion_pairs": binding["accepted_exclusion_pairs"],
        "environment_only_scene_required": True,
        "robot_collision_query_shapes_enabled": False,
        "indeterminate_disposition": "FAIL_CLOSED",
        "adapter_implemented": True,
        "adapter_review_admitted": False,
        "integration_execution_admitted": False,
        "launch_admitted": False,
        "attempt_consumed": False,
        "isaac_started": False,
        "scene_loaded": False,
        "trajectory_playback": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
        "next_required_stage": "INDEPENDENTLY_REVIEW_NATIVE_CLEARANCE_ADAPTER",
        "limitations": [
            "definition_cli_does_not_construct_the_adapter_or_import_isaac",
            "adapter_provides_continuous_clearance_only",
            "canonical_ik_tool_key_metrics_and_root_drift_remain_separate_dependencies",
            "installed_tool_clamp_cable_and_optional_camera_geometry_remain_excluded",
            "adapter_cannot_authorize_launch_attempt_hardware_or_physical_motion",
        ],
    }
    return {**core, "adapter_sha256": _sha(core)}


class NativeClearanceRuntimeAdapter:
    """Reviewed ARM-255 clearance method over the ARM-262 native binding."""

    def __init__(
        self,
        definition: Mapping[str, Any],
        *,
        adapter_review: Mapping[str, Any],
        binding_definition: Mapping[str, Any],
        binding_review: Mapping[str, Any],
        articulation: Any,
        scene_query: Any,
        environment_only_scene: bool,
        robot_collision_query_shapes_enabled: bool,
    ) -> None:
        adapter_hash = _require_hash(definition, "adapter_sha256", "ARM-265 adapter")
        _require_hash(
            adapter_review, "adapter_review_sha256", "ARM-265 adapter review"
        )
        binding_hash = _require_hash(
            binding_definition, "binding_sha256", "ARM-262 binding"
        )
        binding_review_hash = _require_hash(
            binding_review, "binding_review_sha256", "ARM-263 review"
        )
        if (
            definition.get("schema") != ADAPTER_SCHEMA
            or definition.get("status")
            != "READY_FOR_INDEPENDENT_NATIVE_CLEARANCE_ADAPTER_REVIEW"
            or definition.get("adapter_implemented") is not True
            or definition.get("adapter_review_admitted") is not False
            or definition.get("integration_execution_admitted") is not False
            or definition.get("launch_admitted") is not False
            or definition.get("attempt_consumed") is not False
            or definition.get("source_binding_sha256") != binding_hash
            or definition.get("source_binding_review_sha256") != binding_review_hash
            or adapter_review.get("schema") != ADAPTER_REVIEW_SCHEMA
            or adapter_review.get("status")
            != "ACCEPTED_FOR_ZERO_AUTHORITY_RUNTIME_COMPOSITION"
            or adapter_review.get("source_adapter_sha256") != adapter_hash
            or adapter_review.get("runtime_integration_admitted") is not True
            or adapter_review.get("launch_admitted") is not False
            or adapter_review.get("attempt_consumed") is not False
            or adapter_review.get("hardware_access") is not False
            or adapter_review.get("physical_authority") is not False
            or environment_only_scene is not True
            or robot_collision_query_shapes_enabled is not False
        ):
            raise NativeClearanceAdapterError(
                "native clearance runtime composition is not admissible"
            )
        self._runtime = NativeIsaacConservativeSweepBinding(
            binding_definition,
            binding_review=binding_review,
            articulation=articulation,
            scene_query=scene_query,
            environment_only_scene=environment_only_scene,
            robot_collision_query_shapes_enabled=robot_collision_query_shapes_enabled,
        )
        self._excluded_pairs = tuple(
            tuple(pair) for pair in definition["accepted_exclusion_pairs"]
        )
        self._margin_mm = float(definition["clearance_margin_mm"])
        self._max_depth = int(definition["maximum_subdivision_depth"])

    def check_continuous_clearance(
        self,
        *,
        start_sequence: int,
        end_sequence: int,
        start_joint_targets_rad: Sequence[float],
        end_joint_targets_rad: Sequence[float],
    ) -> Mapping[str, object]:
        return check_continuous_clearance(
            self._runtime,
            start_sequence=start_sequence,
            end_sequence=end_sequence,
            start_joint_targets_rad=start_joint_targets_rad,
            end_joint_targets_rad=end_joint_targets_rad,
            reviewed_excluded_pairs=self._excluded_pairs,
            clearance_margin_mm=self._margin_mm,
            max_depth=self._max_depth,
        )


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise NativeClearanceAdapterError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--binding-review", type=Path, required=True)
    parser.add_argument("--proof-source", type=Path, required=True)
    parser.add_argument("--binding-source", type=Path, required=True)
    parser.add_argument("--adapter-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_adapter_definition(
        _load(args.preflight),
        _load(args.binding),
        _load(args.binding_review),
        preflight_file_sha256=_file_sha(args.preflight),
        binding_file_sha256=_file_sha(args.binding),
        binding_review_file_sha256=_file_sha(args.binding_review),
        proof_source_file_sha256=_file_sha(args.proof_source),
        binding_source_file_sha256=_file_sha(args.binding_source),
        adapter_source_file_sha256=_file_sha(args.adapter_source),
    )
    args.output.parent.mkdir(parents=True, exist_ok=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
