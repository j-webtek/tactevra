"""Deterministic model-command admission into the supervised shadow runtime."""

from __future__ import annotations

import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from .typing_runtime_supervisor_v1 import (
    TypingRuntimeSupervisorV1,
    TypingRuntimeSupervisorV1Error,
)
from .typing_shadow_service_v1 import TypingShadowServiceV1Error

RECEIPT_SCHEMA = "rocell.typing_supervised_command_admission.v1"
SNAPSHOT_SCHEMA = "rocell.typing_supervised_command_gateway_snapshot.v1"
ADMITTED = "ADMITTED"
REJECTED = "REJECTED"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingSupervisedCommandGatewayV1Error(ValueError):
    """Gateway input, receipt, or snapshot is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _receipt(
    *, status: str, request_id: str, disposition: str,
    request_sha256: str | None, blocker: str | None,
    supervisor_snapshot_sha256: str,
) -> dict[str, object]:
    core = {
        "schema": RECEIPT_SCHEMA, "status": status,
        "request_id": request_id, "disposition": disposition,
        "request_sha256": request_sha256, "blocker": blocker,
        "supervisor_snapshot_sha256": supervisor_snapshot_sha256,
        "automatic_retry_allowed": False,
        "executor_attached": False, "controller_opened": False,
        "transport_opened": False, "controller_commands": [],
        "hardware_commands_generated": 0, "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "admission_receipt_sha256": _sha(core)}


class TypingSupervisedCommandGatewayV1:
    """Translate supervisor outcomes into bounded machine-readable receipts."""

    def __init__(self, supervisor: TypingRuntimeSupervisorV1) -> None:
        if not isinstance(supervisor, TypingRuntimeSupervisorV1):
            raise TypeError("supervisor must be TypingRuntimeSupervisorV1")
        self._lock = RLock()
        self._supervisor = supervisor
        self._admitted = 0
        self._rejected = 0
        self._backpressure_rejections = 0
        self._state_rejections = 0
        self._input_rejections = 0

    @property
    def context(self):
        return self._supervisor.context

    @property
    def supervisor_state(self) -> str:
        return self._supervisor.state

    def admit(
        self, request_id: str, pipeline_inputs: Mapping[str, Any],
    ) -> dict[str, object]:
        if not isinstance(request_id, str) or not request_id:
            raise TypingSupervisedCommandGatewayV1Error("request id is invalid")
        if not isinstance(pipeline_inputs, Mapping):
            raise TypeError("pipeline_inputs must be a mapping")
        with self._lock:
            before = self._supervisor.snapshot()
            state = before["state"]
            try:
                request_sha256 = self._supervisor.submit(
                    request_id, pipeline_inputs
                )
            except TypingRuntimeSupervisorV1Error as exc:
                message = str(exc)
                if message == "requalification required before submission":
                    blocker = "REQUALIFICATION_REQUIRED"
                    self._state_rejections += 1
                elif message == "supervisor is invalidated":
                    blocker = "SUPERVISOR_INVALIDATED"
                    self._state_rejections += 1
                else:
                    raise
                self._rejected += 1
                after = self._supervisor.snapshot()
                return _receipt(
                    status=REJECTED, request_id=request_id,
                    disposition=after["state"], request_sha256=None,
                    blocker=blocker,
                    supervisor_snapshot_sha256=after[
                        "supervisor_snapshot_sha256"
                    ],
                )
            except TypingShadowServiceV1Error as exc:
                message = str(exc)
                if message == "shadow service queue is full":
                    blocker = "BACKPRESSURE_QUEUE_FULL"
                    self._backpressure_rejections += 1
                elif message == "shadow service lifetime request bound is exhausted":
                    blocker = "BACKPRESSURE_REQUEST_BOUND"
                    self._backpressure_rejections += 1
                else:
                    blocker = "INPUT_REJECTED"
                    self._input_rejections += 1
                self._rejected += 1
                after = self._supervisor.snapshot()
                return _receipt(
                    status=REJECTED, request_id=request_id,
                    disposition=after["state"], request_sha256=None,
                    blocker=blocker,
                    supervisor_snapshot_sha256=after[
                        "supervisor_snapshot_sha256"
                    ],
                )
            self._admitted += 1
            after = self._supervisor.snapshot()
            if after["state"] != state:
                raise TypingSupervisedCommandGatewayV1Error(
                    "supervisor state changed during admission"
                )
            return _receipt(
                status=ADMITTED, request_id=request_id,
                disposition=after["state"], request_sha256=request_sha256,
                blocker=None,
                supervisor_snapshot_sha256=after[
                    "supervisor_snapshot_sha256"
                ],
            )

    def run_next_shadow(self) -> dict[str, Any]:
        with self._lock:
            return self._supervisor.execute_next()

    def cancel(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            return self._supervisor.cancel(request_id)

    def shadow_artifact(self, request_id: str, expected_sha256: str):
        with self._lock:
            return self._supervisor.shadow_artifact(
                request_id, expected_sha256)

    def artifact_store_snapshot(self):
        with self._lock:
            return self._supervisor.artifact_store_snapshot()

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            supervisor = self._supervisor.snapshot()
            core = {
                "schema": SNAPSHOT_SCHEMA,
                "supervisor_state": supervisor["state"],
                "supervisor_snapshot_sha256": supervisor[
                    "supervisor_snapshot_sha256"
                ],
                "admitted": self._admitted, "rejected": self._rejected,
                "backpressure_rejections": self._backpressure_rejections,
                "state_rejections": self._state_rejections,
                "input_rejections": self._input_rejections,
                "automatic_retry_allowed": False,
                "executor_attached": False, "controller_opened": False,
                "transport_opened": False, "controller_commands": [],
                "hardware_commands_generated": 0, "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "gateway_snapshot_sha256": _sha(core)}


def parse_typing_supervised_command_admission_v1(value: Mapping[str, object]):
    fields = {"schema", "status", "request_id", "disposition",
              "request_sha256", "blocker", "supervisor_snapshot_sha256",
              "automatic_retry_allowed", "executor_attached",
              "controller_opened", "transport_opened", "controller_commands",
              "hardware_commands_generated", "hardware_access",
              "physical_authority", "admission_receipt_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingSupervisedCommandGatewayV1Error("admission fields differ")
    unsigned = dict(value); supplied = unsigned.pop("admission_receipt_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingSupervisedCommandGatewayV1Error("admission hash differs")
    if (value["schema"] != RECEIPT_SCHEMA or value["status"] not in {ADMITTED, REJECTED}
            or not isinstance(value["request_id"], str) or not value["request_id"]
            or not isinstance(value["disposition"], str)
            or _HASH.fullmatch(value["supervisor_snapshot_sha256"] or "") is None):
        raise TypingSupervisedCommandGatewayV1Error("admission identity differs")
    admitted = value["status"] == ADMITTED
    if admitted is not (_HASH.fullmatch(value["request_sha256"] or "") is not None):
        raise TypingSupervisedCommandGatewayV1Error("admission request hash differs")
    if admitted is not (value["blocker"] is None):
        raise TypingSupervisedCommandGatewayV1Error("admission blocker differs")
    if (value["automatic_retry_allowed"] is not False
            or value["executor_attached"] is not False
            or value["controller_opened"] is not False
            or value["transport_opened"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingSupervisedCommandGatewayV1Error("admission authority differs")
    return value


def parse_typing_supervised_command_gateway_snapshot_v1(value: Mapping[str, object]):
    fields = {"schema", "supervisor_state", "supervisor_snapshot_sha256",
              "admitted", "rejected", "backpressure_rejections",
              "state_rejections", "input_rejections",
              "automatic_retry_allowed", "executor_attached",
              "controller_opened", "transport_opened", "controller_commands",
              "hardware_commands_generated", "hardware_access",
              "physical_authority", "gateway_snapshot_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingSupervisedCommandGatewayV1Error("gateway snapshot fields differ")
    unsigned = dict(value); supplied = unsigned.pop("gateway_snapshot_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingSupervisedCommandGatewayV1Error("gateway snapshot hash differs")
    for field in ("admitted", "rejected", "backpressure_rejections",
                  "state_rejections", "input_rejections",
                  "hardware_commands_generated"):
        item = value[field]
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingSupervisedCommandGatewayV1Error("gateway counters differ")
    if value["rejected"] != (value["backpressure_rejections"]
                              + value["state_rejections"]
                              + value["input_rejections"]):
        raise TypingSupervisedCommandGatewayV1Error("gateway rejection counters differ")
    if (value["automatic_retry_allowed"] is not False
            or value["executor_attached"] is not False
            or value["controller_opened"] is not False
            or value["transport_opened"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingSupervisedCommandGatewayV1Error("gateway authority differs")
    return value


__all__ = ["ADMITTED", "REJECTED", "RECEIPT_SCHEMA", "SNAPSHOT_SCHEMA",
           "TypingSupervisedCommandGatewayV1",
           "TypingSupervisedCommandGatewayV1Error",
           "parse_typing_supervised_command_admission_v1",
           "parse_typing_supervised_command_gateway_snapshot_v1"]
