from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software/integrations/isaac_sim"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def _modules():
    claimant = importlib.import_module("nominal_route_physics_eula_recovery_claimant")
    review = importlib.import_module(
        "nominal_route_physics_eula_recovery_claimant_review"
    )
    return claimant, review


def _definition(tmp_path: Path, claimant_source: Path):
    claimant, _ = _modules()
    worker_core = {
        "schema": claimant.WORKER_SCHEMA,
        "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
        "source_request_sha256": "1" * 64,
        "proposed_output_directory": str(tmp_path / "attempt-001"),
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
        "status": "READY_FOR_INDEPENDENT_EULA_RECOVERY_CLAIMANT_REVIEW",
        "source_worker_request_sha256": "1" * 64,
        "required_authorization_statement": claimant.EXACT_AUTHORIZATION,
        "old_authorization_reusable": False,
        "attempt_claimed": False,
        "isaac_started": False,
        "attempt_contract": {
            "maximum_attempt_count": 1,
            "automatic_retry": False,
            "claim_only_after_fresh_memory_preflight": True,
            "claim_only_after_fresh_eula_preflight": True,
            "trajectory_playback": False,
            "hardware_or_physical_authority": False,
        },
        "proposed_output_directory": str(tmp_path / "attempt-001"),
    }
    request = {**request_core, "request_sha256": claimant._sha(request_core)}
    return claimant.build_claimant_definition(
        request,
        worker,
        recovery_request_file_sha256="2" * 64,
        worker_preparation_file_sha256="3" * 64,
        claimant_source_sha256=claimant._file_sha(claimant_source),
        memory_preflight_source_sha256="4" * 64,
        eula_preflight_source_sha256="5" * 64,
        worker_source_sha256="6" * 64,
    )


def test_arm286_accepts_exact_inert_claimant(tmp_path: Path) -> None:
    _, review = _modules()
    source = INTEGRATION / "nominal_route_physics_eula_recovery_claimant.py"
    definition = _definition(tmp_path, source)

    result = review.review_claimant(
        definition,
        definition_file_sha256="7" * 64,
        claimant_source=source,
        review_source_sha256="8" * 64,
    )

    assert result["status"] == "ACCEPTED_FOR_EXACT_ARM284_ONE_ATTEMPT_AUTHORIZATION"
    assert result["launch_admitted"] is True
    assert result["attempt_consumed"] is False
    assert result["isaac_started"] is False
    assert result["fresh_eula_gate_precedes_memory_and_attempt_claim"] is True
    assert result["both_receipts_precede_attempt_claim"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("automatic_retry", True),
        ("trajectory_playback", True),
        ("hardware_access", True),
        ("physical_authority", True),
    ],
)
def test_arm286_rejects_authority_or_retry_drift(
    tmp_path: Path, field: str, value: bool
) -> None:
    claimant, review = _modules()
    source = INTEGRATION / "nominal_route_physics_eula_recovery_claimant.py"
    definition = _definition(tmp_path, source)
    drifted = dict(definition)
    drifted[field] = value
    core = dict(drifted)
    core.pop("claimant_sha256")
    drifted["claimant_sha256"] = claimant._sha(core)

    with pytest.raises(review.EulaRecoveryClaimantReviewError, match="boundary"):
        review.review_claimant(
            drifted,
            definition_file_sha256="7" * 64,
            claimant_source=source,
            review_source_sha256="8" * 64,
        )


def test_arm286_rejects_gate_order_drift(tmp_path: Path) -> None:
    claimant, review = _modules()
    source = INTEGRATION / "nominal_route_physics_eula_recovery_claimant.py"
    text = source.read_text(encoding="utf-8")
    changed = text.replace(
        "eula = dict(self._eula_evaluator(self._eula_collector()))",
        "eula = dict(self._eula_evaluator(dict()))",
    )
    drifted_source = tmp_path / source.name
    drifted_source.write_text(changed, encoding="utf-8")
    definition = _definition(tmp_path, drifted_source)

    with pytest.raises(review.EulaRecoveryClaimantReviewError, match="order"):
        review.review_claimant(
            definition,
            definition_file_sha256="7" * 64,
            claimant_source=drifted_source,
            review_source_sha256="8" * 64,
        )


def test_arm286_rejects_claimant_source_hash_drift(tmp_path: Path) -> None:
    _, review = _modules()
    source = INTEGRATION / "nominal_route_physics_eula_recovery_claimant.py"
    definition = _definition(tmp_path, source)
    copied = tmp_path / source.name
    copied.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(review.EulaRecoveryClaimantReviewError, match="boundary"):
        review.review_claimant(
            definition,
            definition_file_sha256="7" * 64,
            claimant_source=copied,
            review_source_sha256="8" * 64,
        )
