from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backend():
    return _load_module(
        "arm255_backend",
        ROOT / "software/integrations/isaac_sim/nominal_route_physics_backend.py",
    )


def _worker_test_module():
    return _load_module(
        "arm254_test_fixtures_for_arm255",
        ROOT / "software/tests/unit/test_nominal_route_physics_worker.py",
    )


def _bundle(tmp_path: Path):
    backend = _backend()
    worker_test = _worker_test_module()
    _, preparation, _, _, _, route, _ = worker_test._bundle(tmp_path)
    arm251 = worker_test._arm251_fixtures()
    correction = arm251._inputs()["correction_plan"]
    route["joint_targets"] = [
        {
            "action_index": 0 if sequence >= 654 else None,
            "joint_position_target_rad": [sequence / 100_000.0] * 4 + [0.0, 0.0],
            "phase": (
                "TRANSIT"
                if 654 <= sequence <= 900
                else "HOVER"
                if 901 <= sequence <= 940
                else "CONTACT"
                if sequence == 941
                else "PARK"
            ),
            "phase_endpoint": False,
            "sequence": sequence,
            "source_target_sequence": sequence // 20,
            "target_id": "SPACE",
            "time_from_start_ns": (sequence + 1) * 8_333_333,
        }
        for sequence in range(1416)
    ]
    route.pop("plan_sha256")
    route["plan_sha256"] = worker_test._worker()._sha(route)
    correction["source_corrected_plan_sha256"] = route["plan_sha256"]
    correction.pop("plan_sha256")
    correction["plan_sha256"] = worker_test._worker()._sha(correction)
    definition = backend.build_backend_definition(
        preparation,
        route,
        correction,
        source_files_sha256=worker_test.SOURCE_HASHES,
        runtime_bindings_sha256=worker_test.RUNTIME_HASHES,
        backend_source_file_sha256="f" * 64,
    )
    output = tmp_path / "claimed-attempt"
    output.mkdir()
    (output / "status.json").write_text(
        json.dumps(
            {
                "status": "ATTEMPT_CLAIMED_BACKEND_PENDING",
                "attempt_count": 1,
                "automatic_retry": False,
                "hardware_access": False,
                "physical_authority": False,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return backend, worker_test, definition, route, correction, output


def _accepted_review(backend, definition):
    core = {
        "schema": backend.BACKEND_REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_ONE_SEPARATELY_AUTHORIZED_SIMULATION_ATTEMPT",
        "source_backend_sha256": definition["backend_sha256"],
        "reviewed_runtime_adapter_sha256": "e" * 64,
        "continuous_clearance_protocol_accepted": True,
        "launch_admitted": True,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_authority": False,
        "physical_movements": 0,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    return {**core, "backend_review_sha256": backend._sha(core)}


class PassingRuntime:
    def regenerate_row(self, *, source_row, previous_joint_targets_rad):
        return {
            "sequence": source_row["sequence"],
            "accepted": True,
            "determinate": True,
            "position_error_mm": 0.001,
            "joint_position_target_rad": source_row["joint_position_target_rad"],
        }

    def check_continuous_clearance(
        self,
        *,
        start_sequence,
        end_sequence,
        start_joint_targets_rad,
        end_joint_targets_rad,
    ):
        return {
            "start_sequence": start_sequence,
            "end_sequence": end_sequence,
            "continuous": True,
            "determinate": True,
            "minimum_clearance_mm": 1.25,
            "colliding_body_pair": None,
        }

    def measure_tool_key(self, *, sequence, joint_targets_rad, phase):
        return {
            "sequence": sequence,
            "determinate": True,
            "tool_key_clearance_mm": 1.0,
            "key_displacement_mm": 0.0,
        }

    def root_drift(self):
        return {"determinate": True, "translation_mm": 0.0, "rotation_deg": 0.0}


def test_arm255_builds_hash_bound_nonstarting_backend_definition(
    tmp_path: Path,
) -> None:
    _, _, definition, *_ = _bundle(tmp_path)

    assert definition["status"] == (
        "READY_FOR_INDEPENDENT_BACKEND_AND_RUNTIME_ADAPTER_REVIEW"
    )
    assert definition["regeneration_window"] == {
        "first_sequence": 654,
        "last_sequence": 940,
        "row_count": 287,
        "canonical_boundary_sequence": 653,
        "boundary_inclusive_clearance_segment_count": 288,
    }
    assert definition["runtime_protocol"]["continuous_clearance"] == (
        "CONTINUOUS_QUERY_NOT_DISCRETE_SAMPLING"
    )
    assert definition["isaac_runtime_adapter_implemented_by_core"] is False
    assert definition["isaac_execution_authorized"] is False
    assert definition["hardware_access"] is False
    assert definition["physical_authority"] is False


def test_arm255_import_has_no_isaac_runtime_side_effect() -> None:
    source = (
        ROOT / "software/integrations/isaac_sim/nominal_route_physics_backend.py"
    ).read_text(encoding="utf-8")

    assert "from isaacsim import" not in source
    assert "SimulationApp(" not in source


def test_arm255_executes_exact_contract_through_reviewable_runtime(
    tmp_path: Path,
) -> None:
    backend, _, definition, route, _, output = _bundle(tmp_path)

    result = backend.execute_backend(
        definition,
        route,
        backend_review=_accepted_review(backend, definition),
        output_directory=output,
        runtime=PassingRuntime(),
    )

    assert result["status"] == "PASS_NOMINAL_SIMULATION_ONLY"
    assert result["canonical_boundary_sequence"] == 653
    assert result["canonical_boundary_position_error_mm"] == 0.001
    assert result["regenerated_row_count"] == 287
    assert result["canonical_ik_row_count"] == 287
    assert result["continuous_clearance_segment_count"] == 288
    assert result["tool_key_metric_row_count"] == 287
    assert result["trajectory_playback"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False
    assert set(result["output_file_sha256"]) == {
        "regenerated_joint_targets.jsonl",
        "canonical_ik.jsonl",
        "continuous_clearance.jsonl",
        "tool_key_metrics.jsonl",
    }
    status = json.loads((output / "status.json").read_bytes())
    assert status["status"] == "PASS_RETAINED_NO_RETRY"
    assert status["attempt_count"] == 1
    assert status["automatic_retry"] is False
    assert (
        len((output / "regenerated_joint_targets.jsonl").read_text().splitlines())
        == 287
    )
    assert len((output / "continuous_clearance.jsonl").read_text().splitlines()) == 288


def test_arm255_canonicalizes_start_boundary_before_continuity_gate(
    tmp_path: Path,
) -> None:
    backend, _, definition, route, _, output = _bundle(tmp_path)

    class ShiftedCanonicalBranchRuntime(PassingRuntime):
        def regenerate_row(self, *, source_row, previous_joint_targets_rad):
            sequence = source_row["sequence"]
            return {
                "sequence": sequence,
                "accepted": True,
                "determinate": True,
                "position_error_mm": 0.001,
                "joint_position_target_rad": [
                    1.0 + sequence / 100_000.0
                ] * 4 + [0.0, 0.0],
            }

    result = backend.execute_backend(
        definition,
        route,
        backend_review=_accepted_review(backend, definition),
        output_directory=output,
        runtime=ShiftedCanonicalBranchRuntime(),
    )

    assert result["status"] == "PASS_NOMINAL_SIMULATION_ONLY"
    assert result["canonical_boundary_sequence"] == 653
    first = json.loads(
        (output / "regenerated_joint_targets.jsonl").read_text().splitlines()[0]
    )
    assert first["sequence"] == 654
    assert first["joint_position_target_rad"][0] == pytest.approx(1.00654)


def test_arm255_rejects_discrete_clearance_claim(tmp_path: Path) -> None:
    backend, _, definition, route, _, output = _bundle(tmp_path)

    class DiscreteRuntime(PassingRuntime):
        def check_continuous_clearance(self, **kwargs):
            result = super().check_continuous_clearance(**kwargs)
            result["continuous"] = False
            return result

    with pytest.raises(backend.NominalRoutePhysicsBackendError, match="continuous"):
        backend.execute_backend(
            definition,
            route,
            backend_review=_accepted_review(backend, definition),
            output_directory=output,
            runtime=DiscreteRuntime(),
        )
    assert not (output / "result.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("tool_key_clearance_mm", 0.49),
        ("key_displacement_mm", 0.051),
    ],
)
def test_arm255_rejects_tool_key_limit_failure(
    tmp_path: Path, field: str, value: float
) -> None:
    backend, _, definition, route, _, output = _bundle(tmp_path)

    class MetricFailure(PassingRuntime):
        def measure_tool_key(self, **kwargs):
            result = super().measure_tool_key(**kwargs)
            result[field] = value
            return result

    with pytest.raises(backend.NominalRoutePhysicsBackendError, match="tool/key"):
        backend.execute_backend(
            definition,
            route,
            backend_review=_accepted_review(backend, definition),
            output_directory=output,
            runtime=MetricFailure(),
        )


def test_arm255_rejects_indeterminate_root_drift(tmp_path: Path) -> None:
    backend, _, definition, route, _, output = _bundle(tmp_path)

    class IndeterminateDrift(PassingRuntime):
        def root_drift(self):
            return {
                "determinate": False,
                "translation_mm": 0.0,
                "rotation_deg": 0.0,
            }

    with pytest.raises(backend.NominalRoutePhysicsBackendError, match="root drift"):
        backend.execute_backend(
            definition,
            route,
            backend_review=_accepted_review(backend, definition),
            output_directory=output,
            runtime=IndeterminateDrift(),
        )


def test_arm255_rejects_unreviewed_runtime_or_invalid_claim(tmp_path: Path) -> None:
    backend, _, definition, route, _, output = _bundle(tmp_path)
    review = _accepted_review(backend, definition)

    changed = {**review, "launch_admitted": False}
    with pytest.raises(backend.NominalRoutePhysicsBackendError):
        backend.execute_backend(
            definition,
            route,
            backend_review=changed,
            output_directory=output,
            runtime=PassingRuntime(),
        )
    (output / "status.json").write_text(
        json.dumps({"status": "ATTEMPT_CLAIMED_BACKEND_PENDING"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(backend.NominalRoutePhysicsBackendError):
        backend.execute_backend(
            definition,
            route,
            backend_review=review,
            output_directory=output,
            runtime=PassingRuntime(),
        )


def test_arm255_rejects_worker_or_source_drift(tmp_path: Path) -> None:
    backend, worker_test, _, route, correction, _ = _bundle(tmp_path)
    _, preparation, *_ = worker_test._bundle(tmp_path / "other")
    changed = copy.deepcopy(preparation)
    changed["backend_contract"]["regenerated_row_count"] = 286
    changed.pop("worker_sha256")
    changed["worker_sha256"] = worker_test._worker()._sha(changed)

    with pytest.raises(backend.NominalRoutePhysicsBackendError):
        backend.build_backend_definition(
            changed,
            route,
            correction,
            source_files_sha256=worker_test.SOURCE_HASHES,
            runtime_bindings_sha256=worker_test.RUNTIME_HASHES,
            backend_source_file_sha256="f" * 64,
        )
