from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
BINDING_SOURCE = INTEGRATION / "nominal_route_arm299_launch_binding.py"
REVIEW_SOURCE = INTEGRATION / "nominal_route_arm299_launch_binding_review.py"


def _load(name: str, path: Path):
    if str(INTEGRATION) not in sys.path:
        sys.path.insert(0, str(INTEGRATION))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BINDING = _load("arm299_launch_binding", BINDING_SOURCE)
REVIEW = _load("arm299_launch_binding_review", REVIEW_SOURCE)


def _documents(monkeypatch):
    runtime = {
        key: str(index).zfill(64)
        for index, key in enumerate(BINDING.RUNTIME_SOURCE_FILES, 1)
    }
    claimant_core = {
        "schema": BINDING.CLAIMANT_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_ARM299_CLAIMANT_REVIEW",
        "required_authorization_statement": BINDING.EXACT_AUTHORIZATION,
        "runtime_sources_sha256": runtime,
        "proposed_output_directory": r"C:\artifacts\arm299-attempt",
        "fresh_eula_receipt": r"C:\artifacts\arm299-eula\receipt.json",
        "fresh_memory_receipt": r"C:\artifacts\arm299-memory\receipt.json",
        **BINDING.ZERO_AUTHORITY,
        "worker_invoked": False,
        "joint_positions_submitted": False,
    }
    claimant = {**claimant_core, "claimant_sha256": BINDING._sha(claimant_core)}
    claimant_file = json.dumps(claimant, sort_keys=True).encode()
    claimant_file_sha = BINDING.hashlib.sha256(claimant_file).hexdigest()
    review_core = {
        "schema": BINDING.REVIEW_SCHEMA,
        "status": "ACCEPTED_FOR_EXACT_ARM299_ONE_ATTEMPT_AUTHORIZATION",
        "source_claimant_sha256": claimant["claimant_sha256"],
        "source_claimant_file_sha256": claimant_file_sha,
        "required_authorization_statement": BINDING.EXACT_AUTHORIZATION,
        **BINDING.ZERO_AUTHORITY,
        "worker_invoked": False,
        "joint_positions_submitted": False,
        "launch_admitted": True,
    }
    review = {
        **review_core,
        "claimant_review_sha256": BINDING._sha(review_core),
    }
    review_file = json.dumps(review, sort_keys=True).encode()
    review_file_sha = BINDING.hashlib.sha256(review_file).hexdigest()
    monkeypatch.setattr(
        BINDING, "EXPECTED_CLAIMANT_SHA256", claimant["claimant_sha256"]
    )
    monkeypatch.setattr(BINDING, "EXPECTED_CLAIMANT_FILE_SHA256", claimant_file_sha)
    monkeypatch.setattr(
        BINDING, "EXPECTED_REVIEW_SHA256", review["claimant_review_sha256"]
    )
    monkeypatch.setattr(BINDING, "EXPECTED_REVIEW_FILE_SHA256", review_file_sha)
    return claimant, review, claimant_file_sha, review_file_sha, runtime


def _build(monkeypatch):
    claimant, review, claimant_file_sha, review_file_sha, runtime = _documents(
        monkeypatch
    )
    source_sha = BINDING._file_sha(BINDING_SOURCE)
    binding = BINDING.build_launch_binding(
        claimant,
        review,
        claimant_file_sha256=claimant_file_sha,
        review_file_sha256=review_file_sha,
        interpreter_path=Path(BINDING.QUALIFIED_ISAAC_PYTHON),
        interpreter_file_sha256=BINDING.EXPECTED_INTERPRETER_SHA256,
        repository_commit=BINDING.EXPECTED_REPOSITORY_COMMIT,
        runtime_source_files_sha256=runtime,
        binding_source_file_sha256=source_sha,
    )
    return binding, claimant, review, claimant_file_sha, review_file_sha, runtime


def test_binding_is_inert_and_pins_reproducible_launch(monkeypatch):
    binding, _, _, _, _, runtime = _build(monkeypatch)

    assert binding["status"] == "READY_FOR_INDEPENDENT_ARM299_LAUNCH_BINDING_REVIEW"
    assert binding["runtime_sources_sha256"] == runtime
    assert binding["qualified_interpreter"]["path"] == BINDING.QUALIFIED_ISAAC_PYTHON
    assert (
        binding["fresh_gate_policy"]["both_receipts_retained_before_attempt_claim"]
        is True
    )
    assert binding["terminalization_policy"]["no_automatic_retry"] is True
    assert binding["launch_admitted"] is False
    assert binding["attempt_claimed"] is False
    assert binding["physics_steps"] == 0


def test_binding_rejects_repository_or_runtime_drift(monkeypatch):
    claimant, review, claimant_file_sha, review_file_sha, runtime = _documents(
        monkeypatch
    )
    kwargs = {
        "claimant_file_sha256": claimant_file_sha,
        "review_file_sha256": review_file_sha,
        "interpreter_path": Path(BINDING.QUALIFIED_ISAAC_PYTHON),
        "interpreter_file_sha256": BINDING.EXPECTED_INTERPRETER_SHA256,
        "repository_commit": "f" * 40,
        "runtime_source_files_sha256": runtime,
        "binding_source_file_sha256": BINDING._file_sha(BINDING_SOURCE),
    }
    with pytest.raises(BINDING.Arm299LaunchBindingError, match="source contract"):
        BINDING.build_launch_binding(claimant, review, **kwargs)
    kwargs["repository_commit"] = BINDING.EXPECTED_REPOSITORY_COMMIT
    kwargs["runtime_source_files_sha256"] = {**runtime, "physics_worker": "f" * 64}
    with pytest.raises(BINDING.Arm299LaunchBindingError, match="source contract"):
        BINDING.build_launch_binding(claimant, review, **kwargs)


def test_binding_rejects_interpreter_drift(monkeypatch):
    claimant, review, claimant_file_sha, review_file_sha, runtime = _documents(
        monkeypatch
    )
    with pytest.raises(BINDING.Arm299LaunchBindingError, match="source contract"):
        BINDING.build_launch_binding(
            claimant,
            review,
            claimant_file_sha256=claimant_file_sha,
            review_file_sha256=review_file_sha,
            interpreter_path=Path(r"C:\other\python.exe"),
            interpreter_file_sha256=BINDING.EXPECTED_INTERPRETER_SHA256,
            repository_commit=BINDING.EXPECTED_REPOSITORY_COMMIT,
            runtime_source_files_sha256=runtime,
            binding_source_file_sha256=BINDING._file_sha(BINDING_SOURCE),
        )


def test_arm299_claimant_authority_shape_is_exact(monkeypatch):
    claimant, review, _, _, _ = _documents(monkeypatch)

    assert BINDING._claimant_zero_authority(claimant, launch_admitted=None)
    assert BINDING._claimant_zero_authority(review, launch_admitted=True)

    claimant["launch_admitted"] = False
    assert not BINDING._claimant_zero_authority(claimant, launch_admitted=None)
    claimant.pop("launch_admitted")
    claimant["attempt_consumed"] = True
    assert not BINDING._claimant_zero_authority(claimant, launch_admitted=None)


def test_independent_review_accepts_exact_inert_binding(monkeypatch):
    binding, claimant, review, claimant_file_sha, review_file_sha, runtime = _build(
        monkeypatch
    )
    binding_bytes = json.dumps(binding, sort_keys=True).encode()
    receipt = REVIEW.review_launch_binding(
        binding,
        claimant,
        review,
        binding_file_sha256=REVIEW.hashlib.sha256(binding_bytes).hexdigest(),
        claimant_file_sha256=claimant_file_sha,
        claimant_review_file_sha256=review_file_sha,
        binding_source_bytes=BINDING_SOURCE.read_bytes(),
        interpreter_file_sha256=REVIEW.EXPECTED_INTERPRETER_SHA256,
        repository_commit=REVIEW.EXPECTED_REPOSITORY_COMMIT,
        runtime_source_files_sha256=runtime,
    )

    assert receipt["status"] == "ACCEPTED_FOR_ARM299_LAUNCHER_IMPLEMENTATION"
    assert receipt["static_review"] == {
        "simulator_and_transport_imports_absent": True,
        "simulator_motion_and_transport_calls_absent": True,
        "builder_only_materialization": True,
    }
    assert receipt["launch_admitted"] is False
    assert receipt["attempt_claimed"] is False


def test_static_review_rejects_simulator_and_motion_calls():
    with pytest.raises(
        REVIEW.Arm299LaunchBindingReviewError,
        match="simulator, motion, or transport",
    ):
        REVIEW._review_source(b"import isaacsim\nworld.play()\nworld.step()\n")
