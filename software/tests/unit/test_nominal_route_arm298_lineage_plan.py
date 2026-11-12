from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
PLAN_SOURCE = INTEGRATION / "nominal_route_arm298_lineage_plan.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_arm298_lineage_plan_review.py"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PLAN = _load_module("arm298_lineage_plan_test", PLAN_SOURCE)
REVIEW = _load_module("arm298_lineage_review_test", REVIEW_SOURCE)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _evidence(source_hashes: dict[str, str]):
    evaluation = {
        "canonical_boundary_position_error_mm": 0.0026,
        "canonical_boundary_sequence": 653,
        "canonical_rows_sha256": PLAN.EXPECTED_CANONICAL_ROWS_SHA256,
        "continuity_limit_rad": 0.05,
        "first_sequence": 654,
        "governed_row_count": 287,
        "last_sequence": 940,
        "maximum_adjacent_joint_step_rad": 0.0458,
        "maximum_adjacent_joint_step_sequence": 670,
        "maximum_position_error_mm": 0.003,
        "maximum_position_error_sequence": 669,
    }
    qualification_core = {
        "schema": PLAN.QUALIFICATION_SCHEMA,
        "status": "PASS_ARM298_CANONICAL_CONTINUITY_QUALIFICATION",
        "episode_id": "episode-ef340d0ad2740c118d87",
        "target_id": "SPACE",
        "evaluation": evaluation,
        "qualified_source_files_sha256": {
            key: source_hashes[key] for key in PLAN.QUALIFIED_SOURCE_KEYS
        },
        "arm297_replay_permitted": False,
        "arm298_attempt_authorized": False,
        "attempt_claimed": False,
        "attempt_consumed": False,
        "authorization_observed": False,
        "automatic_retry": False,
        "hardware_access": False,
        "hardware_writes": 0,
        "isaac_imported": False,
        "isaac_started": False,
        "joint_positions_submitted": False,
        "joint_targets_submitted": False,
        "key_contact": False,
        "physical_authority": False,
        "physical_movements": 0,
        "physics_steps": 0,
        "scene_loaded": False,
        "timeline_played": False,
        "trajectory_playback": False,
        "controller_commands": [],
        "wire_commands": [],
        "gate_promotions": [],
    }
    qualification = {
        **qualification_core,
        "qualification_sha256": PLAN._sha(qualification_core),
    }
    review_core = {
        "schema": PLAN.QUALIFICATION_REVIEW_SCHEMA,
        "status": "ACCEPTED_ARM298_CANONICAL_CONTINUITY_FOR_LINEAGE_PLANNING",
        "source_qualification_sha256": qualification["qualification_sha256"],
        "reproduced_evaluation": evaluation,
        "production_solver_reexecuted": True,
        "all_287_governed_rows_reproduced": True,
        "unchanged_continuity_limit_verified": True,
        "arm297_replay_permitted": False,
        "arm298_attempt_authorized": False,
        "next_required_stage": "BUILD_FRESH_ARM298_ROUTE_PHYSICS_LINEAGE_PLAN",
    }
    review = {
        **review_core,
        "qualification_review_sha256": PLAN._sha(review_core),
    }
    return qualification, review


def _build(tmp_path: Path, monkeypatch):
    sources = {}
    for key in PLAN.RUNTIME_SOURCE_KEYS:
        path = tmp_path / "sources" / f"{key}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {key}\n", encoding="utf-8")
        sources[key] = path
    source_hashes = {key: PLAN._file_sha(path) for key, path in sources.items()}
    qualification, qualification_review = _evidence(source_hashes)
    qualification_file = tmp_path / "qualification" / "receipt.json"
    review_file = tmp_path / "qualification-review" / "review.json"
    _write_json(qualification_file, qualification)
    _write_json(review_file, qualification_review)
    interpreter = tmp_path / "isaac" / "python.exe"
    interpreter.parent.mkdir()
    interpreter.write_bytes(b"qualified interpreter")

    for module in (PLAN, REVIEW):
        monkeypatch.setattr(
            module,
            "EXPECTED_QUALIFICATION_SHA256",
            qualification["qualification_sha256"],
        )
        monkeypatch.setattr(
            module,
            "EXPECTED_QUALIFICATION_FILE_SHA256",
            PLAN._file_sha(qualification_file),
        )
        monkeypatch.setattr(
            module,
            "EXPECTED_QUALIFICATION_REVIEW_SHA256",
            qualification_review["qualification_review_sha256"],
        )
        monkeypatch.setattr(
            module,
            "EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256",
            PLAN._file_sha(review_file),
        )
        monkeypatch.setattr(module, "EXPECTED_INTERPRETER_PATH", interpreter)
        monkeypatch.setattr(
            module, "EXPECTED_INTERPRETER_SHA256", PLAN._file_sha(interpreter)
        )

    future = tmp_path / "future"
    plan = PLAN.build_arm298_lineage_plan(
        qualification,
        qualification_review,
        qualification_file_sha256=PLAN._file_sha(qualification_file),
        review_file_sha256=PLAN._file_sha(review_file),
        plan_source_file_sha256=PLAN._file_sha(PLAN_SOURCE),
        runtime_sources_sha256=source_hashes,
        repository_commit=PLAN.EXPECTED_REPOSITORY_COMMIT,
        qualified_interpreter=interpreter,
        proposed_attempt_directory=(
            future / "arm298-nominal-route-physics-attempt-001"
        ).resolve(),
        proposed_eula_receipt=(
            future / "arm298-nominal-route-physics-eula-preflight-001" / "receipt.json"
        ).resolve(),
        proposed_memory_receipt=(
            future
            / "arm298-nominal-route-physics-memory-preflight-001"
            / "receipt.json"
        ).resolve(),
    )
    return plan, qualification_file, review_file, sources, interpreter


def test_arm298_plan_and_review_bind_qualified_lineage_without_authority(
    tmp_path, monkeypatch
):
    plan, qualification, qualification_review, sources, interpreter = _build(
        tmp_path, monkeypatch
    )
    plan_file = tmp_path / "plan" / "plan.json"
    _write_json(plan_file, plan)
    review = REVIEW.review_arm298_lineage_plan(
        plan,
        plan_file_sha256=REVIEW._file_sha(plan_file),
        plan_source=PLAN_SOURCE,
        qualification_file=qualification,
        qualification_review_file=qualification_review,
        runtime_sources=sources,
        qualified_interpreter=interpreter,
        review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
    )
    assert plan["required_authorization_statement"].startswith(
        "I authorize exactly one ARM-298"
    )
    assert plan["arm297_replay_permitted"] is False
    assert plan["attempt_claimed"] is False
    assert plan["physics_steps"] == 0
    assert review["status"] == ("ACCEPTED_ARM298_LINEAGE_FOR_CLAIMANT_CONSTRUCTION")
    assert review["proposed_attempt_directory_absent"] is True
    assert review["authorization_observed"] is False
    assert review["physical_authority"] is False


def test_arm298_plan_rejects_changed_continuity_evidence(tmp_path, monkeypatch):
    plan, qualification_file, review_file, sources, interpreter = _build(
        tmp_path, monkeypatch
    )
    del plan
    qualification = json.loads(qualification_file.read_text(encoding="utf-8"))
    qualification["evaluation"]["maximum_adjacent_joint_step_rad"] = 0.06
    unsigned = dict(qualification)
    unsigned.pop("qualification_sha256")
    qualification["qualification_sha256"] = PLAN._sha(unsigned)
    monkeypatch.setattr(
        PLAN, "EXPECTED_QUALIFICATION_SHA256", qualification["qualification_sha256"]
    )
    qualification_review = json.loads(review_file.read_text(encoding="utf-8"))
    with pytest.raises(PLAN.Arm298LineagePlanError, match="qualification boundary"):
        PLAN.build_arm298_lineage_plan(
            qualification,
            qualification_review,
            qualification_file_sha256=PLAN.EXPECTED_QUALIFICATION_FILE_SHA256,
            review_file_sha256=PLAN.EXPECTED_QUALIFICATION_REVIEW_FILE_SHA256,
            plan_source_file_sha256="a" * 64,
            runtime_sources_sha256={
                key: PLAN._file_sha(path) for key, path in sources.items()
            },
            repository_commit=PLAN.EXPECTED_REPOSITORY_COMMIT,
            qualified_interpreter=interpreter,
            proposed_attempt_directory=(
                tmp_path / "arm298-nominal-route-physics-attempt-001"
            ).resolve(),
            proposed_eula_receipt=(
                tmp_path
                / "arm298-nominal-route-physics-eula-preflight-001/receipt.json"
            ).resolve(),
            proposed_memory_receipt=(
                tmp_path
                / "arm298-nominal-route-physics-memory-preflight-001/receipt.json"
            ).resolve(),
        )


def test_arm298_review_rejects_runtime_source_drift(tmp_path, monkeypatch):
    plan, qualification, qualification_review, sources, interpreter = _build(
        tmp_path, monkeypatch
    )
    plan_file = tmp_path / "plan" / "plan.json"
    _write_json(plan_file, plan)
    sources["physics_worker"].write_text("# changed\n", encoding="utf-8")
    with pytest.raises(REVIEW.Arm298LineagePlanReviewError, match="source binding"):
        REVIEW.review_arm298_lineage_plan(
            plan,
            plan_file_sha256=REVIEW._file_sha(plan_file),
            plan_source=PLAN_SOURCE,
            qualification_file=qualification,
            qualification_review_file=qualification_review,
            runtime_sources=sources,
            qualified_interpreter=interpreter,
            review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
        )


def test_arm298_sources_have_no_simulation_or_hardware_authority():
    plan_source = PLAN_SOURCE.read_text(encoding="utf-8")
    assert "import isaacsim" not in plan_source
    assert "SimulationApp(" not in plan_source
    assert "serial.Serial" not in plan_source
    assert "run_one_attempt(" not in plan_source
    static = REVIEW._static_review(PLAN_SOURCE)
    assert static["runtime_motion_and_transport_calls_absent"] is True
