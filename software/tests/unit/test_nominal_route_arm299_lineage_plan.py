from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
PLAN_SOURCE = INTEGRATION / "nominal_route_arm299_lineage_plan.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_arm299_lineage_plan_review.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PLAN = _load("arm299_lineage_plan_test", PLAN_SOURCE)
REVIEW = _load("arm299_lineage_review_test", REVIEW_SOURCE)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _status() -> dict[str, object]:
    return {
        "attempt_count": 1,
        "automatic_retry": False,
        "error_message": (
            "'IsaacArticulationLinkView' object has no attribute "
            "'set_dof_positions'"
        ),
        "error_stage": "execute_backend",
        "error_type": "AttributeError",
        "hardware_access": False,
        "physical_authority": False,
        "status": "FAILED_RETAINED_NO_RETRY",
    }


def _fixture(tmp_path: Path, monkeypatch):
    status_file = tmp_path / "arm298" / "status.json"
    _write(status_file, _status())
    interpreter = tmp_path / "isaac" / "python.exe"
    interpreter.parent.mkdir()
    interpreter.write_bytes(b"qualified interpreter")
    sources: dict[str, Path] = {}
    for key in PLAN.RUNTIME_SOURCE_KEYS:
        path = tmp_path / "sources" / f"{key}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {key}\n", encoding="utf-8")
        sources[key] = path
    source_hashes = {key: PLAN._file_sha(path) for key, path in sources.items()}
    for module in (PLAN, REVIEW):
        monkeypatch.setattr(
            module, "EXPECTED_ARM298_STATUS_SHA256", PLAN._file_sha(status_file)
        )
        monkeypatch.setattr(
            module, "EXPECTED_WRAPPER_SHA256", source_hashes["native_session_wrapper"]
        )
    monkeypatch.setattr(PLAN, "EXPECTED_INTERPRETER_PATH", interpreter)
    monkeypatch.setattr(
        PLAN, "EXPECTED_INTERPRETER_SHA256", PLAN._file_sha(interpreter)
    )
    future = tmp_path / "future"
    plan = PLAN.build_arm299_lineage_plan(
        _status(),
        arm298_status_file_sha256=PLAN._file_sha(status_file),
        plan_source_file_sha256=PLAN._file_sha(PLAN_SOURCE),
        runtime_sources_sha256=source_hashes,
        repository_commit=PLAN.EXPECTED_REPOSITORY_COMMIT,
        qualified_interpreter=interpreter,
        proposed_attempt_directory=future / "arm299-attempt",
        proposed_eula_receipt=future / "arm299-eula" / "receipt.json",
        proposed_memory_receipt=future / "arm299-memory" / "receipt.json",
    )
    plan_file = tmp_path / "plan" / "plan.json"
    _write(plan_file, plan)
    return plan, plan_file, status_file, interpreter, sources


def test_arm299_plan_and_independent_review_are_inert(tmp_path, monkeypatch):
    plan, plan_file, status_file, interpreter, sources = _fixture(
        tmp_path, monkeypatch
    )
    review = REVIEW.review_arm299_lineage_plan(
        plan,
        plan_file_sha256=REVIEW._file_sha(plan_file),
        plan_source=PLAN_SOURCE,
        arm298_status_file=status_file,
        runtime_sources=sources,
        qualified_interpreter=interpreter,
        review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
    )
    assert review["status"] == "ACCEPTED_FOR_ARM299_CLAIMANT_CONSTRUCTION"
    assert review["fresh_outputs_verified_absent"] is True
    for key, value in PLAN.ZERO_AUTHORITY.items():
        assert plan[key] == value
        assert review[key] == value


def test_arm299_plan_rejects_changed_terminal_status(tmp_path, monkeypatch):
    plan, _, _, _, _ = _fixture(tmp_path, monkeypatch)
    changed = dict(plan["source_arm298_terminal_status"])
    changed["attempt_count"] = 2
    with pytest.raises(PLAN.Arm299LineagePlanError, match="terminal status"):
        PLAN.build_arm299_lineage_plan(
            changed,
            arm298_status_file_sha256=PLAN.EXPECTED_ARM298_STATUS_SHA256,
            plan_source_file_sha256=PLAN._file_sha(PLAN_SOURCE),
            runtime_sources_sha256=plan["runtime_sources_sha256"],
            repository_commit=PLAN.EXPECTED_REPOSITORY_COMMIT,
            qualified_interpreter=PLAN.EXPECTED_INTERPRETER_PATH,
            proposed_attempt_directory=tmp_path / "new-attempt",
            proposed_eula_receipt=tmp_path / "new-eula.json",
            proposed_memory_receipt=tmp_path / "new-memory.json",
        )


def test_arm299_plan_rejects_existing_future_output(tmp_path, monkeypatch):
    plan, _, status_file, interpreter, _ = _fixture(tmp_path, monkeypatch)
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    with pytest.raises(PLAN.Arm299LineagePlanError, match="distinct and absent"):
        PLAN.build_arm299_lineage_plan(
            _status(),
            arm298_status_file_sha256=PLAN._file_sha(status_file),
            plan_source_file_sha256=PLAN._file_sha(PLAN_SOURCE),
            runtime_sources_sha256=plan["runtime_sources_sha256"],
            repository_commit=PLAN.EXPECTED_REPOSITORY_COMMIT,
            qualified_interpreter=interpreter,
            proposed_attempt_directory=occupied,
            proposed_eula_receipt=tmp_path / "new-eula.json",
            proposed_memory_receipt=tmp_path / "new-memory.json",
        )


def test_arm299_review_rejects_runtime_source_tamper(tmp_path, monkeypatch):
    plan, plan_file, status_file, interpreter, sources = _fixture(
        tmp_path, monkeypatch
    )
    sources["physics_backend"].write_text("# changed\n", encoding="utf-8")
    with pytest.raises(REVIEW.Arm299LineageReviewError, match="runtime source"):
        REVIEW.review_arm299_lineage_plan(
            plan,
            plan_file_sha256=REVIEW._file_sha(plan_file),
            plan_source=PLAN_SOURCE,
            arm298_status_file=status_file,
            runtime_sources=sources,
            qualified_interpreter=interpreter,
            review_source_file_sha256=REVIEW._file_sha(REVIEW_SOURCE),
        )
