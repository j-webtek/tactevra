from __future__ import annotations

import copy
import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _modules():
    claimant = importlib.import_module("nominal_route_physics_recovery_claimant")
    review = importlib.import_module("nominal_route_physics_recovery_claimant_review")
    return claimant, review


def _definition(tmp_path: Path):
    claimant, review = _modules()
    worker_core = {
        "schema": claimant.WORKER_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
        "source_request_sha256": "1" * 64,
        "proposed_output_directory": str(tmp_path / "attempt"),
        "attempt_ledger": {
            "maximum_attempt_count": 1,
            "attempts_consumed_by_preparation": 0,
            "automatic_retry": False,
        },
        "required_authorization_statement": claimant.WORKER_AUTHORIZATION,
        "isaac_execution_authorized": False,
        "isaac_started": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    worker = {**worker_core, "worker_sha256": claimant._sha(worker_core)}
    request_core = {
        "schema": claimant.RECOVERY_REQUEST_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_RECOVERY_CLAIMANT_REVIEW",
        "source_request_sha256": "1" * 64,
        "required_authorization_statement": claimant.EXACT_AUTHORIZATION,
        "old_authorization_reusable": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "claim_only_after_fresh_memory_preflight": True,
            "trajectory_playback": False,
            "hardware_or_physical_authority": False,
        },
        "proposed_output_directory": str(tmp_path / "attempt"),
    }
    request = {**request_core, "request_sha256": claimant._sha(request_core)}
    definition = claimant.build_claimant_definition(
        request,
        worker,
        recovery_request_file_sha256="2" * 64,
        worker_preparation_file_sha256="3" * 64,
        claimant_source_sha256="4" * 64,
        memory_preflight_source_sha256="5" * 64,
        worker_source_sha256="6" * 64,
    )
    source = INTEGRATION / "nominal_route_physics_recovery_claimant.py"
    definition["source_files_sha256"]["claimant_source"] = review._file_sha(source)
    definition.pop("claimant_sha256")
    definition["claimant_sha256"] = review._sha(definition)
    return review, definition, source


def test_arm282_accepts_exact_fail_before_claim_order(tmp_path: Path) -> None:
    review, definition, source = _definition(tmp_path)

    result = review.review_claimant(
        definition,
        definition_file_sha256="7" * 64,
        claimant_source=source,
        review_source_sha256="8" * 64,
    )

    assert result["status"] == ("ACCEPTED_FOR_EXACT_ARM280_ONE_ATTEMPT_AUTHORIZATION")
    assert result["launch_admitted"] is True
    assert result["attempt_consumed"] is False
    assert result["isaac_started"] is False
    assert all(result["static_review"].values())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("automatic_retry", True),
        ("runtime_execution_admitted", True),
        ("attempt_claimed", True),
        ("hardware_access", True),
    ],
)
def test_arm282_rejects_claimant_drift(tmp_path: Path, key: str, value: object) -> None:
    review, definition, source = _definition(tmp_path)
    changed = copy.deepcopy(definition)
    changed[key] = value
    changed.pop("claimant_sha256")
    changed["claimant_sha256"] = review._sha(changed)

    with pytest.raises(review.RecoveryClaimantReviewError):
        review.review_claimant(
            changed,
            definition_file_sha256="7" * 64,
            claimant_source=source,
            review_source_sha256="8" * 64,
        )


def test_arm282_rejects_reordered_source(tmp_path: Path) -> None:
    review, definition, source = _definition(tmp_path)
    changed_source = tmp_path / "claimant.py"
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        "self._used = True\n        return self._worker_runner(",
        "return self._worker_runner(\n            # self._used = True",
    )
    changed_source.write_text(text, encoding="utf-8")
    definition["source_files_sha256"]["claimant_source"] = review._file_sha(
        changed_source
    )
    definition.pop("claimant_sha256")
    definition["claimant_sha256"] = review._sha(definition)

    with pytest.raises((review.RecoveryClaimantReviewError, SyntaxError)):
        review.review_claimant(
            definition,
            definition_file_sha256="7" * 64,
            claimant_source=changed_source,
            review_source_sha256="8" * 64,
        )
