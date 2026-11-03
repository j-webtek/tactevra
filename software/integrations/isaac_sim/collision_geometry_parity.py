"""Plan and compare zero-authority native/offline collision geometry captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


PLAN_SCHEMA = "tactevra.isaac_lm1_collision_geometry_parity_plan.v1"
CAPTURE_SCHEMA = "tactevra.isaac_lm1_collision_geometry_capture.v1"
REPORT_SCHEMA = "tactevra.isaac_lm1_collision_geometry_parity_report.v1"
SELECTION_SCHEMA = "tactevra.isaac_lm1_route_shape_v4_native_selection.v1"


class ParityContractError(ValueError):
    """Raised when parity evidence crosses its fixed zero-authority boundary."""


def _canonical_sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _verify_digest(document: dict[str, Any], field: str, label: str) -> str:
    claimed = document.get(field)
    unsigned = dict(document)
    unsigned.pop(field, None)
    if not isinstance(claimed, str) or claimed != _canonical_sha256(unsigned):
        raise ParityContractError(f"{label} hash mismatch")
    return claimed


def _require_zero_authority(document: dict[str, Any], label: str) -> None:
    physical_authority = document.get("physical_authority")
    if physical_authority is None:
        authority = document.get("authority")
        physical_authority = not (
            isinstance(authority, dict)
            and authority
            and all(value is False for value in authority.values())
        )
    commands = document.get("controller_commands", document.get("commands"))
    hardware_writes = document.get(
        "hardware_writes", document.get("hardware_write_count")
    )
    physical_movements = document.get(
        "physical_movements", document.get("physical_movement_count")
    )
    hardware_access = document.get("hardware_access")
    if hardware_access is None and physical_authority is False:
        hardware_access = False
    if (
        hardware_access is not False
        or physical_authority is not False
        or commands != []
        or hardware_writes != 0
        or physical_movements != 0
    ):
        raise ParityContractError(f"{label} authority boundary changed")


def _pair_key(pair: list[str]) -> tuple[str, str]:
    if (
        not isinstance(pair, list)
        or len(pair) != 2
        or not all(isinstance(item, str) and item for item in pair)
    ):
        raise ParityContractError("collision pair is invalid")
    return tuple(sorted(pair))


def _select_capture_samples(result: dict[str, Any]) -> list[dict[str, Any]]:
    samples = result.get("raw_native_samples")
    if not isinstance(samples, list) or not samples:
        raise ParityContractError("retained native samples are absent")
    ordered = sorted(samples, key=lambda item: item.get("sample_sequence", -1))
    if [item.get("sample_sequence") for item in ordered] != list(
        range(len(ordered))
    ):
        raise ParityContractError("retained native sample sequence changed")

    blocked = [
        item for item in ordered if item.get("physical_solid_blocker_pairs")
    ]
    if not blocked:
        raise ParityContractError("candidate has no physical blocker onset")
    first_onset = blocked[0]
    peak = min(
        blocked,
        key=lambda item: (
            -len(item["physical_solid_blocker_pairs"]),
            item["sample_sequence"],
        ),
    )
    later_clear = next(
        (
            item
            for item in ordered
            if item["sample_sequence"] > first_onset["sample_sequence"]
            and not item.get("physical_solid_blocker_pairs")
        ),
        None,
    )
    if later_clear is None:
        raise ParityContractError("candidate lacks a post-onset physical-clear sample")

    selected: dict[int, dict[str, Any]] = {}
    for role, sample in (
        ("FIRST_PHYSICAL_ONSET", first_onset),
        ("PEAK_PHYSICAL_PAIR_COUNT", peak),
        ("FIRST_PHYSICAL_CLEAR_AFTER_ONSET", later_clear),
    ):
        sequence = sample["sample_sequence"]
        entry = selected.setdefault(
            sequence,
            {
                "sample_sequence": sequence,
                "sample_id": sample["sample_id"],
                "source_segment_index": sample["source_segment_index"],
                "selection_roles": [],
                "physical_solid_blocker_pairs": sample.get(
                    "physical_solid_blocker_pairs", []
                ),
                "physical_primitive_pairs": [],
            },
        )
        entry["selection_roles"].append(role)
        physical_pairs = {
            _pair_key(pair) for pair in entry["physical_solid_blocker_pairs"]
        }
        primitive_pairs = []
        for primitive_pair in sample.get("raw_collision_primitive_pairs", []):
            body_pair = primitive_pair.get("body_pair")
            if _pair_key(body_pair) in physical_pairs:
                primitive_pairs.append(
                    {
                        "body_pair": body_pair,
                        "primitive_indices": primitive_pair["primitive_indices"],
                    }
                )
        entry["physical_primitive_pairs"] = sorted(
            primitive_pairs,
            key=lambda item: (item["body_pair"], item["primitive_indices"]),
        )
    return [selected[key] for key in sorted(selected)]


def build_capture_plan(
    selection: dict[str, Any],
    collision_candidate: dict[str, Any],
    requests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Fix the samples and canonical primitive representation before capture."""

    selection_hash = _verify_digest(selection, "selection_sha256", "selection")
    candidate_hash = _verify_digest(
        collision_candidate, "candidate_sha256", "collision candidate"
    )
    if (
        selection.get("schema") != SELECTION_SCHEMA
        or selection.get("status")
        != "INCOMPLETE_V4_NATIVE_REPLAY_NO_IMPROVEMENT_RETAINED"
        or selection.get("native_improvement_over_control") is not False
        or selection.get("selected_candidate_id") is not None
    ):
        raise ParityContractError("ARM-203 selection boundary changed")
    _require_zero_authority(selection, "selection")
    _require_zero_authority(collision_candidate, "collision candidate")

    results = selection.get("retained_results")
    if not isinstance(results, list) or len(results) != 2:
        raise ParityContractError("completed ARM-203 candidate coverage changed")
    captures = []
    for result in results:
        candidate_id = result.get("candidate_id")
        request = requests.get(candidate_id)
        if request is None:
            raise ParityContractError(f"request is absent for {candidate_id}")
        request_hash = _verify_digest(request, "request_sha256", "route request")
        if (
            request.get("route_shape_candidate_id") != candidate_id
            or result.get("native_receipt_schema")
            != "tactevra.isaac_lm1_robot_tcp_collision_diagnostic.v4"
            or result.get("station_route_predicate_applied") is not True
        ):
            raise ParityContractError(f"candidate binding changed for {candidate_id}")
        _require_zero_authority(request, "route request")
        capture_samples = _select_capture_samples(result)
        for sample in capture_samples:
            segment = sample["source_segment_index"]
            if not isinstance(segment, int) or not 0 <= segment < len(request["samples"]):
                raise ParityContractError("source segment is outside the route request")
            source = request["samples"][segment]
            destination = request["samples"][min(segment + 1, len(request["samples"]) - 1)]
            sample["source_phase"] = source["phase"]
            sample["destination_phase"] = destination["phase"]
            sample["target_id"] = destination.get("target_id") or source.get("target_id")
        captures.append(
            {
                "candidate_id": candidate_id,
                "request_sha256": request_hash,
                "native_receipt_sha256": result["native_receipt_sha256"],
                "capture_samples": capture_samples,
            }
        )

    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "status": "READY_FOR_ZERO_AUTHORITY_NATIVE_AND_OFFLINE_GEOMETRY_CAPTURE",
        "source_selection_sha256": selection_hash,
        "source_collision_candidate_sha256": candidate_hash,
        "candidate_captures": captures,
        "canonical_primitive_representation": {
            "length_unit": "mm",
            "matrix_layout": "ROW_MAJOR_4X4",
            "matrix_semantics": "CANONICAL_PRIMITIVE_LOCAL_TO_BOARD_WORLD",
            "rotation_semantics": "RIGHT_HANDED_ACTIVE",
            "primitive_key": ["body_id", "primitive_index"],
            "required_fields": [
                "body_id",
                "primitive_index",
                "kind",
                "half_extents_mm",
                "local_center_mm",
                "local_rotation_row_major",
                "world_matrix_row_major",
            ],
        },
        "comparison_tolerances": {
            "translation_mm": 0.001,
            "half_extent_mm": 0.000001,
            "rotation_matrix_element": 0.000001,
        },
        "geometry_mutated": False,
        "route_mutated": False,
        "placement_mutated": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def _capture_records(capture: dict[str, Any], source: str) -> dict[tuple[Any, ...], dict[str, Any]]:
    _verify_digest(capture, "capture_sha256", f"{source} capture")
    if capture.get("schema") != CAPTURE_SCHEMA or capture.get("source") != source:
        raise ParityContractError(f"{source} capture boundary changed")
    _require_zero_authority(capture, f"{source} capture")
    records: dict[tuple[Any, ...], dict[str, Any]] = {}
    for sample in capture.get("samples", []):
        candidate_id = sample.get("candidate_id")
        sequence = sample.get("sample_sequence")
        for primitive in sample.get("primitives", []):
            key = (
                candidate_id,
                sequence,
                primitive.get("body_id"),
                primitive.get("primitive_index"),
            )
            if key in records:
                raise ParityContractError(f"duplicate {source} primitive record")
            records[key] = primitive
    if not records:
        raise ParityContractError(f"{source} capture is empty")
    return records


def _maximum_delta(first: list[float], second: list[float]) -> float:
    if len(first) != len(second) or not first:
        return math.inf
    return max(abs(float(left) - float(right)) for left, right in zip(first, second))


def _systematic_findings(comparisons: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Separate a moving robot root from per-primitive geometry disagreement."""

    findings: list[dict[str, Any]] = []
    workcell = [item for item in comparisons if item["body_id"].startswith("workcell:")]
    if workcell and all(item["classification"] == "MATCH" for item in workcell):
        findings.append(
            {
                "classification": "STATIC_WORKCELL_PARITY_CONFIRMED",
                "primitive_comparison_count": len(workcell),
            }
        )

    robot = [item for item in comparisons if item["body_id"].startswith("robot:")]
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for item in robot:
        grouped.setdefault(
            (item["candidate_id"], item["sample_sequence"]), []
        ).append(item)
    coherent_offsets: list[dict[str, Any]] = []
    for (candidate_id, sample_sequence), items in sorted(grouped.items()):
        offsets = [
            item.get("translation_offset_native_minus_offline_mm") for item in items
        ]
        if not offsets or any(not isinstance(offset, list) for offset in offsets):
            continue
        component_spread = [
            max(float(offset[index]) for offset in offsets)
            - min(float(offset[index]) for offset in offsets)
            for index in range(3)
        ]
        # The native USD/PhysX bridge is single precision.  A 0.05 mm spread
        # is tight enough to distinguish a shared root displacement from local
        # collision-primitive placement error without pretending micrometre
        # precision at the installed-workcell scale.
        if max(component_spread) <= 0.05:
            mean = [
                sum(float(offset[index]) for offset in offsets) / len(offsets)
                for index in range(3)
            ]
            coherent_offsets.append(
                {
                    "candidate_id": candidate_id,
                    "sample_sequence": sample_sequence,
                    "robot_primitive_count": len(items),
                    "mean_translation_offset_native_minus_offline_mm": mean,
                    "maximum_component_spread_mm": max(component_spread),
                }
            )
    if coherent_offsets:
        findings.append(
            {
                "classification": "ROBOT_RIGID_TRANSLATION_OFFSET_BY_SAMPLE",
                "samples": coherent_offsets,
            }
        )

    root_z_drift = bool(
        workcell
        and all(item["classification"] == "MATCH" for item in workcell)
        and len(coherent_offsets) == len(grouped)
        and coherent_offsets
        and all(
            abs(item["mean_translation_offset_native_minus_offline_mm"][0]) <= 0.05
            and abs(item["mean_translation_offset_native_minus_offline_mm"][1]) <= 0.05
            and item["mean_translation_offset_native_minus_offline_mm"][2] < -0.05
            for item in coherent_offsets
        )
    )
    conclusion = {
        "primary_classification": (
            "NATIVE_ROBOT_ROOT_Z_DRIFT"
            if root_z_drift
            else "PRIMITIVE_GEOMETRY_PARITY_DISCREPANCY"
        ),
        "retained_native_collision_conclusion_usable_for_fixed_base_route_comparison": (
            not root_z_drift
        ),
        "required_next_action": (
            "REPLAY_WITH_FIXED_BASE_AND_ROOT_POSE_INVARIANT"
            if root_z_drift
            else "RESOLVE_REPORTED_PRIMITIVE_DISCREPANCIES"
        ),
    }
    return findings, conclusion


def compare_captures(
    plan: dict[str, Any],
    native_capture: dict[str, Any],
    offline_capture: dict[str, Any],
) -> dict[str, Any]:
    """Compare two captures without allowing missing primitives to disappear."""

    plan_hash = _verify_digest(plan, "plan_sha256", "parity plan")
    if plan.get("schema") != PLAN_SCHEMA:
        raise ParityContractError("parity plan schema changed")
    native = _capture_records(native_capture, "NATIVE_PHYSX")
    offline = _capture_records(offline_capture, "OFFLINE_OBB")
    native_hash = native_capture["capture_sha256"]
    offline_hash = offline_capture["capture_sha256"]
    if (
        native_capture.get("source_plan_sha256") != plan_hash
        or offline_capture.get("source_plan_sha256") != plan_hash
    ):
        raise ParityContractError("capture plan binding changed")

    translation_limit = plan["comparison_tolerances"]["translation_mm"]
    extent_limit = plan["comparison_tolerances"]["half_extent_mm"]
    rotation_limit = plan["comparison_tolerances"]["rotation_matrix_element"]
    comparisons = []
    classifications: set[str] = set()
    for key in sorted(set(native) | set(offline)):
        native_item = native.get(key)
        offline_item = offline.get(key)
        if native_item is None or offline_item is None:
            classification = "COVERAGE_MISMATCH"
            details = {"native_present": native_item is not None, "offline_present": offline_item is not None}
        else:
            required = plan["canonical_primitive_representation"]["required_fields"]
            if any(field not in native_item or field not in offline_item for field in required):
                raise ParityContractError("capture primitive representation is incomplete")
            if native_item["kind"] != offline_item["kind"]:
                classification = "GEOMETRY_KIND_MISMATCH"
                details = {}
            else:
                extent_delta = _maximum_delta(
                    native_item["half_extents_mm"], offline_item["half_extents_mm"]
                )
                native_matrix = native_item["world_matrix_row_major"]
                offline_matrix = offline_item["world_matrix_row_major"]
                if len(native_matrix) != 16 or len(offline_matrix) != 16:
                    raise ParityContractError("world matrix shape changed")
                translation_delta = max(
                    abs(float(native_matrix[index]) - float(offline_matrix[index]))
                    for index in (3, 7, 11)
                )
                rotation_indices = (0, 1, 2, 4, 5, 6, 8, 9, 10)
                rotation_delta = max(
                    abs(float(native_matrix[index]) - float(offline_matrix[index]))
                    for index in rotation_indices
                )
                details = {
                    "maximum_half_extent_delta_mm": extent_delta,
                    "maximum_translation_delta_mm": translation_delta,
                    "maximum_rotation_element_delta": rotation_delta,
                    "translation_offset_native_minus_offline_mm": [
                        float(native_matrix[index]) - float(offline_matrix[index])
                        for index in (3, 7, 11)
                    ],
                }
                if extent_delta > extent_limit:
                    classification = "GEOMETRY_DIMENSION_MISMATCH"
                elif translation_delta > translation_limit:
                    classification = "WORLD_TRANSLATION_MISMATCH"
                elif rotation_delta > rotation_limit:
                    classification = "WORLD_ORIENTATION_MISMATCH"
                else:
                    classification = "MATCH"
        classifications.add(classification)
        comparisons.append(
            {
                "candidate_id": key[0],
                "sample_sequence": key[1],
                "body_id": key[2],
                "primitive_index": key[3],
                "classification": classification,
                **details,
            }
        )

    mismatch_count = sum(item["classification"] != "MATCH" for item in comparisons)
    systematic_findings, diagnostic_conclusion = _systematic_findings(comparisons)
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "PARITY_MATCH" if mismatch_count == 0 else "PARITY_DISCREPANCY_CLASSIFIED",
        "source_plan_sha256": plan_hash,
        "native_capture_sha256": native_hash,
        "offline_capture_sha256": offline_hash,
        "primitive_comparison_count": len(comparisons),
        "mismatch_count": mismatch_count,
        "classifications": sorted(classifications),
        "comparisons": comparisons,
        "systematic_findings": systematic_findings,
        "diagnostic_conclusion": diagnostic_conclusion,
        "geometry_mutated": False,
        "route_mutated": False,
        "placement_mutated": False,
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
        "gate_promotions": [],
    }
    report["report_sha256"] = _canonical_sha256(report)
    return report


def merge_captures(
    plan: dict[str, Any], captures: list[dict[str, Any]]
) -> dict[str, Any]:
    """Merge candidate-local native sidecars without changing their records."""

    plan_hash = _verify_digest(plan, "plan_sha256", "parity plan")
    if not captures:
        raise ParityContractError("no captures were supplied")
    samples = []
    source_receipts = []
    seen_candidates: set[str] = set()
    for capture in captures:
        records = _capture_records(capture, "NATIVE_PHYSX")
        if capture.get("source_plan_sha256") != plan_hash:
            raise ParityContractError("native capture plan binding changed")
        candidate_ids = {key[0] for key in records}
        if len(candidate_ids) != 1 or seen_candidates & candidate_ids:
            raise ParityContractError("native capture candidate coverage is invalid")
        seen_candidates.update(candidate_ids)
        samples.extend(capture["samples"])
        source_receipts.append(capture["source_native_receipt_sha256"])
    expected_candidates = {
        item["candidate_id"] for item in plan["candidate_captures"]
    }
    if seen_candidates != expected_candidates:
        raise ParityContractError("native capture candidate set is incomplete")
    merged: dict[str, Any] = {
        "schema": CAPTURE_SCHEMA,
        "source": "NATIVE_PHYSX",
        "source_plan_sha256": plan_hash,
        "source_native_receipt_sha256s": sorted(source_receipts),
        "samples": sorted(
            samples, key=lambda item: (item["candidate_id"], item["sample_sequence"])
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    merged["capture_sha256"] = _canonical_sha256(merged)
    return merged


def build_offline_capture(
    plan: dict[str, Any],
    collision_candidate: dict[str, Any],
    collision_requests: list[dict[str, Any]],
    workspace: Path,
) -> dict[str, Any]:
    """Reconstruct the primitive poses consumed by the portable OBB evaluator."""

    try:
        from rocell.application._pinned_model import load_pinned_urdf
        from rocell.application.context import load_simulation_context
        from rocell.geometry import JointPosition, RigidTransform, Rotation3, Vec3
        from rocell.kinematics import ARM_JOINT_NAMES
    except ImportError as exc:
        raise ParityContractError(
            "offline geometry runtime is unavailable; include software/src on PYTHONPATH"
        ) from exc

    plan_hash = _verify_digest(plan, "plan_sha256", "parity plan")
    candidate_hash = _verify_digest(
        collision_candidate, "candidate_sha256", "collision candidate"
    )
    if plan.get("source_collision_candidate_sha256") != candidate_hash:
        raise ParityContractError("offline collision candidate binding changed")
    request_by_source: dict[str, dict[str, Any]] = {}
    for request in collision_requests:
        _verify_digest(request, "request_sha256", "collision request")
        _require_zero_authority(request, "collision request")
        source_hash = request.get("source_request_sha256")
        if not isinstance(source_hash, str) or source_hash in request_by_source:
            raise ParityContractError("collision request source binding is invalid")
        request_by_source[source_hash] = request

    root = workspace.resolve(strict=True)
    context = load_simulation_context(
        root, root / "software/config/system_manifest.json"
    )
    model = load_pinned_urdf(
        context.scenario.model_path, context.scenario.model_sha256
    ).model
    remaining = set(model.movable_joint_names) - set(ARM_JOINT_NAMES)
    if len(remaining) != 1:
        raise ParityContractError("pinned robot gripper topology changed")
    gripper_joint = next(iter(remaining))
    fixed = model.joint("world_to_base_link")
    robot_bodies = collision_candidate.get("robot_bodies", [])
    physical_workcell_bodies = [
        body
        for body in collision_candidate.get("workcell_bodies", [])
        if not body.get("body_id", "").startswith("workcell:station:")
    ]

    samples = []
    for capture in plan["candidate_captures"]:
        request = request_by_source.get(capture["request_sha256"])
        if request is None:
            raise ParityContractError(
                f"collision request is absent for {capture['candidate_id']}"
            )
        matrix = request.get("robot_placement_matrix_row_major")
        if not isinstance(matrix, list) or len(matrix) != 16:
            raise ParityContractError("collision request placement matrix is invalid")
        board_t_base = RigidTransform(
            "board",
            "base_link",
            Rotation3(
                tuple(matrix[index] for index in (0, 1, 2, 4, 5, 6, 8, 9, 10))
            ),
            Vec3(matrix[3], matrix[7], matrix[11]),
        )
        board_t_world = board_t_base.compose(fixed.transform_at(None).inverse())
        bounded_by_sequence = {
            item["sample_sequence"]: item for item in request["bounded_samples"]
        }
        for selected_sample in capture["capture_samples"]:
            sequence = selected_sample["sample_sequence"]
            bounded = bounded_by_sequence.get(sequence)
            if bounded is None:
                raise ParityContractError("selected bounded sample is absent")
            positions = {
                name: JointPosition.radians(bounded["joint_positions_rad"][name])
                for name in ARM_JOINT_NAMES
            }
            positions[gripper_joint] = context.scenario.fixed_gripper_position
            base_transforms = model.forward_kinematics(positions)
            board_transforms = {
                frame: board_t_world.compose(transform)
                for frame, transform in base_transforms.items()
            }
            primitive_records = []
            for body in [*robot_bodies, *physical_workcell_bodies]:
                parent_transform = (
                    board_transforms[body["parent_frame"]]
                    if body in robot_bodies
                    else RigidTransform.identity("board")
                )
                for primitive_index, primitive in enumerate(body["primitives"]):
                    local = RigidTransform(
                        body["parent_frame"],
                        f"{body['body_id']}:primitive:{primitive_index}",
                        Rotation3(tuple(primitive["rotation_row_major"])),
                        Vec3.from_iterable(primitive["center_mm"]),
                    )
                    world = parent_transform.compose(local)
                    rotation = world.rotation.matrix
                    translation = world.translation_mm
                    primitive_records.append(
                        {
                            "body_id": body["body_id"],
                            "primitive_index": primitive_index,
                            "kind": primitive["kind"],
                            "half_extents_mm": primitive["half_extents_mm"],
                            "local_center_mm": primitive["center_mm"],
                            "local_rotation_row_major": primitive[
                                "rotation_row_major"
                            ],
                            "world_matrix_row_major": [
                                rotation[0],
                                rotation[1],
                                rotation[2],
                                translation.x,
                                rotation[3],
                                rotation[4],
                                rotation[5],
                                translation.y,
                                rotation[6],
                                rotation[7],
                                rotation[8],
                                translation.z,
                                0.0,
                                0.0,
                                0.0,
                                1.0,
                            ],
                        }
                    )
            samples.append(
                {
                    "candidate_id": capture["candidate_id"],
                    "sample_sequence": sequence,
                    "sample_id": bounded["sample_id"],
                    "primitives": sorted(
                        primitive_records,
                        key=lambda item: (item["body_id"], item["primitive_index"]),
                    ),
                }
            )
    result: dict[str, Any] = {
        "schema": CAPTURE_SCHEMA,
        "source": "OFFLINE_OBB",
        "source_plan_sha256": plan_hash,
        "source_collision_candidate_sha256": candidate_hash,
        "samples": sorted(
            samples, key=lambda item: (item["candidate_id"], item["sample_sequence"])
        ),
        "hardware_access": False,
        "physical_authority": False,
        "controller_commands": [],
        "hardware_writes": 0,
        "physical_movements": 0,
    }
    result["capture_sha256"] = _canonical_sha256(result)
    return result


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.resolve(strict=True).read_bytes())


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build-plan", action="store_true")
    mode.add_argument("--compare", action="store_true")
    mode.add_argument("--merge-captures", action="store_true")
    mode.add_argument("--build-offline-capture", action="store_true")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--collision-candidate", type=Path)
    parser.add_argument("--request", action="append", type=Path, default=[])
    parser.add_argument("--collision-request", action="append", type=Path, default=[])
    parser.add_argument("--capture", action="append", type=Path, default=[])
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--native-capture", type=Path)
    parser.add_argument("--offline-capture", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.build_plan:
        if args.selection is None or args.collision_candidate is None or not args.request:
            parser.error("--build-plan requires selection, collision candidate, and requests")
        loaded_requests = [_load(path) for path in args.request]
        requests = {
            request["route_shape_candidate_id"]: request
            for request in loaded_requests
        }
        result = build_capture_plan(_load(args.selection), _load(args.collision_candidate), requests)
    elif args.merge_captures:
        if args.plan is None or not args.capture:
            parser.error("--merge-captures requires a plan and captures")
        result = merge_captures(
            _load(args.plan), [_load(path) for path in args.capture]
        )
    elif args.build_offline_capture:
        if (
            args.plan is None
            or args.collision_candidate is None
            or not args.collision_request
        ):
            parser.error(
                "--build-offline-capture requires a plan, collision candidate, "
                "and collision requests"
            )
        result = build_offline_capture(
            _load(args.plan),
            _load(args.collision_candidate),
            [_load(path) for path in args.collision_request],
            args.workspace,
        )
    else:
        if args.plan is None or args.native_capture is None or args.offline_capture is None:
            parser.error("--compare requires plan, native capture, and offline capture")
        result = compare_captures(_load(args.plan), _load(args.native_capture), _load(args.offline_capture))
    _write(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
