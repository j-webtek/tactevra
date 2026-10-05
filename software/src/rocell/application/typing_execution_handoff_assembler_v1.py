"""Assemble one blocked execution handoff from a canonical session ledger."""

from __future__ import annotations

from typing import Any

from .typing_command_session_ledger_v1 import (
    TypingCommandSessionLedgerV1,
    TypingCommandSessionLedgerV1Error,
)
from .typing_execution_handoff_candidate_v1 import (
    TypingExecutionHandoffCandidateV1Error,
    build_typing_execution_handoff_candidate_v1,
)


class TypingExecutionHandoffAssemblerV1Error(ValueError):
    """The canonical ledger cannot supply one completed evidence chain."""


def assemble_typing_execution_handoff_candidate_v1(
    ledger: TypingCommandSessionLedgerV1, request_id: str,
) -> dict[str, Any]:
    """Build the exact blocked candidate without re-running any planner."""

    if not isinstance(ledger, TypingCommandSessionLedgerV1):
        raise TypingExecutionHandoffAssemblerV1Error(
            "canonical command session ledger is required"
        )
    try:
        session = ledger.get(request_id)
        admission = ledger.admission_receipt(request_id)
        service = ledger.terminal_service_receipt(request_id)
        shadow = ledger.shadow_artifact(request_id)
        return build_typing_execution_handoff_candidate_v1(
            session, admission, service, shadow
        )
    except (TypingCommandSessionLedgerV1Error,
            TypingExecutionHandoffCandidateV1Error) as exc:
        raise TypingExecutionHandoffAssemblerV1Error(
            f"execution handoff is unavailable: {exc}"
        ) from exc


__all__ = [
    "TypingExecutionHandoffAssemblerV1Error",
    "assemble_typing_execution_handoff_candidate_v1",
]
