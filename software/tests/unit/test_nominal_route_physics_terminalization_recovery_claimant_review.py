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
    claimant = importlib.import_module(
        "nominal_route_physics_terminalization_recovery_claimant"
    )
    review = importlib.import_module(
        "nominal_route_physics_terminalization_recovery_claimant_review"
    )
    return claimant, review


def _signed(module, core, key):
    return {**core, key: module._sha(core)}


def _definition(tmp_path: Path, claimant_source: Path):
    claimant, _ = _modules()
    integration_source = "7" * 64
    review_source = "8" * 64
    integration = _signed(
        claimant,
        {
            "schema": claimant.INTEGRATION_SCHEMA,
            "integration_id": (
                "arm287-terminalizing-native-runtime-worker-integration-001"
            ),
            "source_files_sha256": {
                "arm274_integration_source": integration_source
            },
            "lifecycle": ["terminalize_failure_before_shutdown"],
            "launch_admitted": False,
        },
        "integration_sha256",
    )
    integration_review = _signed(
        claimant,
        {
            "schema": claimant.INTEGRATION_REVIEW_SCHEMA,
            "source_integration_sha256": integration["integration_sha256"],
            "source_integration_source_sha256": integration_source,
            "review_source_sha256": review_source,
            "failure_terminalization_precedes_shutdown": True,
            "launch_admitted": False,
        },
        "integration_review_sha256",
    )
    output = str(tmp_path / "attempt-001")
    worker = _signed(
        claimant,
        {
            "schema": claimant.WORKER_SCHEMA,
            "status": "READY_FOR_INDEPENDENT_WORKER_ENVELOPE_REVIEW",
            "source_request_sha256": "a" * 64,
            "proposed_output_directory": output,
            "required_authorization_statement": claimant.WORKER_AUTHORIZATION,
            "attempt_ledger": {
                "maximum_attempt_count": 1,
                "attempts_consumed_by_preparation": 0,
                "automatic_retry": False,
            },
            "isaac_execution_authorized": False,
            "isaac_started": False,
            "hardware_access": False,
            "physical_authority": False,
        },
        "worker_sha256",
    )
    request = _signed(
        claimant,
        {
            "schema": claimant.RECOVERY_REQUEST_SCHEMA,
            "status": (
                "READY_FOR_INDEPENDENT_TERMINALIZED_RECOVERY_CLAIMANT_REVIEW"
            ),
            "required_authorization_statement": claimant.EXACT_AUTHORIZATION,
            "old_authorization_reusable": False,
            "attempt_claimed": False,
            "isaac_started": False,
            "request_source_file_sha256": "6" * 64,
            "source_worker_request_sha256": "a" * 64,
            "source_integration_sha256": integration["integration_sha256"],
            "source_integration_file_sha256": "3" * 64,
            "source_integration_review_sha256": integration_review[
                "integration_review_sha256"
            ],
            "source_integration_review_file_sha256": "4" * 64,
            "proposed_output_directory": output,
            "attempt_contract": {
                "maximum_attempt_count": 1,
                "automatic_retry": False,
                "claim_only_after_fresh_memory_preflight": True,
                "claim_only_after_fresh_eula_preflight": True,
                "terminalize_before_simulator_shutdown": True,
                "trajectory_playback": False,
                "hardware_or_physical_authority": False,
            },
        },
        "request_sha256",
    )
    return claimant.build_claimant_definition(
        request,
        worker,
        integration,
        integration_review,
        recovery_request_file_sha256="1" * 64,
        worker_preparation_file_sha256="2" * 64,
        integration_file_sha256="3" * 64,
        integration_review_file_sha256="4" * 64,
        claimant_source_sha256=claimant._file_sha(claimant_source),
        recovery_request_source_sha256="6" * 64,
        integration_source_sha256=integration_source,
        integration_review_source_sha256=review_source,
        memory_preflight_source_sha256="9" * 64,
        eula_preflight_source_sha256="b" * 64,
        worker_source_sha256="c" * 64,
    )


def test_arm291_accepts_exact_inert_claimant(tmp_path: Path) -> None:
    _, review = _modules()
    source = (
        INTEGRATION
        / "nominal_route_physics_terminalization_recovery_claimant.py"
    )
    definition = _definition(tmp_path, source)

    result = review.review_claimant(
        definition,
        definition_file_sha256="d" * 64,
        claimant_source=source,
        review_source_sha256="e" * 64,
    )

    assert result["status"] == "ACCEPTED_FOR_EXACT_ARM289_ONE_ATTEMPT_AUTHORIZATION"
    assert result["failure_terminalization_precedes_shutdown"] is True
    assert result["attempt_consumed"] is False
    assert result["isaac_started"] is False
    assert result["hardware_access"] is False
    assert result["physical_authority"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("automatic_retry", True),
        ("trajectory_playback", True),
        ("hardware_access", True),
        ("physical_authority", True),
    ],
)
def test_arm291_rejects_authority_or_retry_drift(
    tmp_path: Path, field: str, value: bool
) -> None:
    claimant, review = _modules()
    source = (
        INTEGRATION
        / "nominal_route_physics_terminalization_recovery_claimant.py"
    )
    drifted = copy.deepcopy(_definition(tmp_path, source))
    drifted[field] = value
    drifted.pop("claimant_sha256")
    drifted["claimant_sha256"] = claimant._sha(drifted)

    with pytest.raises(
        review.TerminalizationRecoveryClaimantReviewError, match="boundary"
    ):
        review.review_claimant(
            drifted,
            definition_file_sha256="d" * 64,
            claimant_source=source,
            review_source_sha256="e" * 64,
        )


def test_arm291_rejects_terminalization_contract_drift(tmp_path: Path) -> None:
    claimant, review = _modules()
    source = (
        INTEGRATION
        / "nominal_route_physics_terminalization_recovery_claimant.py"
    )
    drifted = copy.deepcopy(_definition(tmp_path, source))
    drifted["failure_terminalization"][
        "required_before_simulator_shutdown"
    ] = False
    drifted.pop("claimant_sha256")
    drifted["claimant_sha256"] = claimant._sha(drifted)

    with pytest.raises(
        review.TerminalizationRecoveryClaimantReviewError, match="boundary"
    ):
        review.review_claimant(
            drifted,
            definition_file_sha256="d" * 64,
            claimant_source=source,
            review_source_sha256="e" * 64,
        )


def test_arm291_rejects_gate_order_drift(tmp_path: Path) -> None:
    _, review = _modules()
    source = (
        INTEGRATION
        / "nominal_route_physics_terminalization_recovery_claimant.py"
    )
    changed = source.read_text(encoding="utf-8").replace(
        "eula = dict(self._eula_evaluator(self._eula_collector()))",
        "eula = dict(self._eula_evaluator(dict()))",
    )
    drifted_source = tmp_path / source.name
    drifted_source.write_text(changed, encoding="utf-8")
    definition = _definition(tmp_path, drifted_source)

    with pytest.raises(
        review.TerminalizationRecoveryClaimantReviewError, match="order"
    ):
        review.review_claimant(
            definition,
            definition_file_sha256="d" * 64,
            claimant_source=drifted_source,
            review_source_sha256="e" * 64,
        )
