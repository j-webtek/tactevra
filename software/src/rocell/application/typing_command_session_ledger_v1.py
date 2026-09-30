"""Bounded, hash-chained lifecycle records for supervised typing requests."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from .typing_shadow_service_v1 import parse_typing_shadow_service_receipt_v1
from .typing_supervised_command_gateway_v1 import (
    ADMITTED,
    TypingSupervisedCommandGatewayV1,
    parse_typing_supervised_command_admission_v1,
)

RECEIPT_SCHEMA = "rocell.typing_command_session_receipt.v1"
SNAPSHOT_SCHEMA = "rocell.typing_command_session_ledger_snapshot.v1"
QUEUED = "QUEUED"
ADMISSION_REJECTED = "ADMISSION_REJECTED"
LEDGER_CAPACITY_REJECTED = "LEDGER_CAPACITY_REJECTED"
TERMINAL_STATUSES = frozenset({
    ADMISSION_REJECTED,
    LEDGER_CAPACITY_REJECTED,
    "SHADOW_COMPLETED",
    "CANCELED_BEFORE_ADMISSION",
    "STALE_GENERATION_REJECTED",
    "SHADOW_REJECTED",
})
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingCommandSessionLedgerV1Error(ValueError):
    """Session identity, transition, receipt, or snapshot is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identifier(value: object, label: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 128
            or value != value.strip() or ":\\" in value or "://" in value
            or value.startswith(("/", "\\"))):
        raise TypingCommandSessionLedgerV1Error(f"{label} is invalid")
    return value


def _fingerprint(
    mission_id: str, request_id: str, pipeline_inputs: Mapping[str, Any],
) -> str:
    if not isinstance(pipeline_inputs, Mapping):
        raise TypeError("pipeline_inputs must be a mapping")
    payload = pipeline_inputs.get("payload")
    plan_hash = getattr(pipeline_inputs.get("intent_plan"), "plan_hash", None)
    if not isinstance(payload, bytes) or not payload or not isinstance(
        plan_hash, str
    ) or _HASH.fullmatch(plan_hash) is None:
        raise TypingCommandSessionLedgerV1Error(
            "submission fingerprint inputs differ"
        )
    return _sha({
        "mission_id": mission_id,
        "request_id": request_id,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "intent_plan_sha256": plan_hash,
    })


def _receipt(
    *, mission_id: str, request_id: str, status: str, terminal: bool,
    revision: int, ingress_fingerprint_sha256: str,
    request_sha256: str | None, admission_receipt_sha256: str | None,
    service_receipt_sha256: str | None, shadow_receipt_sha256: str | None,
    blocker: str | None, previous_session_receipt_sha256: str | None,
) -> dict[str, object]:
    core = {
        "schema": RECEIPT_SCHEMA,
        "mission_id": mission_id,
        "request_id": request_id,
        "status": status,
        "terminal": terminal,
        "revision": revision,
        "ingress_fingerprint_sha256": ingress_fingerprint_sha256,
        "request_sha256": request_sha256,
        "admission_receipt_sha256": admission_receipt_sha256,
        "service_receipt_sha256": service_receipt_sha256,
        "shadow_receipt_sha256": shadow_receipt_sha256,
        "blocker": blocker,
        "previous_session_receipt_sha256": previous_session_receipt_sha256,
        "automatic_retry_allowed": False,
        "executor_attached": False,
        "controller_opened": False,
        "transport_opened": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "session_receipt_sha256": _sha(core)}


class TypingCommandSessionLedgerV1:
    """Correlate admission and terminal shadow outcomes without dispatch."""

    def __init__(
        self, gateway: TypingSupervisedCommandGatewayV1, *,
        maximum_sessions: int = 4096,
    ) -> None:
        if not isinstance(gateway, TypingSupervisedCommandGatewayV1):
            raise TypeError("gateway must be TypingSupervisedCommandGatewayV1")
        if (isinstance(maximum_sessions, bool)
                or not isinstance(maximum_sessions, int)
                or not 1 <= maximum_sessions <= 4096):
            raise TypingCommandSessionLedgerV1Error(
                "maximum_sessions must be in [1, 4096]"
            )
        self._lock = RLock()
        self._gateway = gateway
        self._maximum_sessions = maximum_sessions
        self._records: OrderedDict[str, dict[str, object]] = OrderedDict()
        self._admission_receipts: dict[str, dict[str, object]] = {}
        self._service_receipts: dict[str, dict[str, Any]] = {}
        self._fingerprints: dict[str, str] = {}
        self._missions: dict[str, str] = {}
        self._duplicate_replays = 0
        self._conflicting_duplicates = 0
        self._capacity_rejections = 0

    @property
    def context(self):
        return self._gateway.context

    def submit(
        self, mission_id: str, request_id: str,
        pipeline_inputs: Mapping[str, Any],
    ) -> dict[str, object]:
        mission_id = _identifier(mission_id, "mission_id")
        request_id = _identifier(request_id, "request_id")
        fingerprint = _fingerprint(mission_id, request_id, pipeline_inputs)
        with self._lock:
            existing = self._records.get(request_id)
            if existing is not None:
                if (self._fingerprints[request_id] != fingerprint
                        or self._missions[request_id] != mission_id):
                    self._conflicting_duplicates += 1
                    raise TypingCommandSessionLedgerV1Error(
                        "request identity was reused with different input"
                    )
                self._duplicate_replays += 1
                return dict(existing)
            if len(self._records) >= self._maximum_sessions:
                self._capacity_rejections += 1
                return _receipt(
                    mission_id=mission_id, request_id=request_id,
                    status=LEDGER_CAPACITY_REJECTED, terminal=True, revision=0,
                    ingress_fingerprint_sha256=fingerprint,
                    request_sha256=None, admission_receipt_sha256=None,
                    service_receipt_sha256=None, shadow_receipt_sha256=None,
                    blocker="LEDGER_CAPACITY_EXHAUSTED",
                    previous_session_receipt_sha256=None,
                )
            admission = self._gateway.admit(request_id, pipeline_inputs)
            parse_typing_supervised_command_admission_v1(admission)
            admitted = admission["status"] == ADMITTED
            record = _receipt(
                mission_id=mission_id, request_id=request_id,
                status=QUEUED if admitted else ADMISSION_REJECTED,
                terminal=not admitted, revision=0,
                ingress_fingerprint_sha256=fingerprint,
                request_sha256=admission["request_sha256"],
                admission_receipt_sha256=admission["admission_receipt_sha256"],
                service_receipt_sha256=None, shadow_receipt_sha256=None,
                blocker=admission["blocker"],
                previous_session_receipt_sha256=None,
            )
            self._records[request_id] = record
            self._admission_receipts[request_id] = dict(admission)
            self._fingerprints[request_id] = fingerprint
            self._missions[request_id] = mission_id
            return dict(record)

    def _terminalize(self, service: Mapping[str, Any]) -> dict[str, object]:
        parse_typing_shadow_service_receipt_v1(service)
        request_id = service["request_id"]
        prior = self._records.get(request_id)
        if prior is None or prior["status"] != QUEUED:
            raise TypingCommandSessionLedgerV1Error(
                "terminal receipt has no unique queued session"
            )
        if service["request_sha256"] != prior["request_sha256"]:
            raise TypingCommandSessionLedgerV1Error(
                "terminal request identity differs"
            )
        record = _receipt(
            mission_id=prior["mission_id"], request_id=request_id,
            status=service["status"], terminal=True, revision=1,
            ingress_fingerprint_sha256=prior["ingress_fingerprint_sha256"],
            request_sha256=prior["request_sha256"],
            admission_receipt_sha256=prior["admission_receipt_sha256"],
            service_receipt_sha256=service["service_receipt_sha256"],
            shadow_receipt_sha256=service["shadow_receipt_sha256"],
            blocker=service["blocker"],
            previous_session_receipt_sha256=prior["session_receipt_sha256"],
        )
        self._records[request_id] = record
        self._service_receipts[request_id] = dict(service)
        return dict(record)

    def run_next_shadow(self) -> dict[str, object]:
        with self._lock:
            return self._terminalize(self._gateway.run_next_shadow())

    def cancel(self, request_id: str) -> dict[str, object]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            prior = self._records.get(request_id)
            if prior is None or prior["status"] != QUEUED:
                raise TypingCommandSessionLedgerV1Error(
                    "request has no unique queued session to cancel"
                )
            return self._terminalize(self._gateway.cancel(request_id))

    def get(self, request_id: str) -> dict[str, object]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            record = self._records.get(request_id)
            if record is None:
                raise TypingCommandSessionLedgerV1Error("session is unknown")
            return dict(record)

    def terminal_service_receipt(self, request_id: str) -> dict[str, Any]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            receipt = self._service_receipts.get(request_id)
            if receipt is None:
                raise TypingCommandSessionLedgerV1Error(
                    "terminal service receipt is unavailable"
                )
            return dict(receipt)

    def admission_receipt(self, request_id: str) -> dict[str, object]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            receipt = self._admission_receipts.get(request_id)
            if receipt is None:
                raise TypingCommandSessionLedgerV1Error(
                    "admission receipt is unavailable"
                )
            return dict(receipt)

    def shadow_artifact(self, request_id: str) -> dict[str, Any]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            record = self._records.get(request_id)
            if (record is None or record["status"] != "SHADOW_COMPLETED"
                    or record["shadow_receipt_sha256"] is None):
                raise TypingCommandSessionLedgerV1Error(
                    "completed shadow artifact is unavailable"
                )
            return self._gateway.shadow_artifact(
                request_id, record["shadow_receipt_sha256"])

    def artifact_store_snapshot(self) -> dict[str, object]:
        with self._lock:
            return self._gateway.artifact_store_snapshot()

    def shadow_materialization(self, request_id: str) -> dict[str, Any]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            record = self._records.get(request_id)
            if (record is None or record["status"] != "SHADOW_COMPLETED"
                    or record["shadow_receipt_sha256"] is None):
                raise TypingCommandSessionLedgerV1Error(
                    "completed shadow materialization is unavailable"
                )
            return self._gateway.shadow_materialization(
                request_id, record["shadow_receipt_sha256"])

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            queued = sum(item["status"] == QUEUED for item in self._records.values())
            terminal = len(self._records) - queued
            gateway = self._gateway.snapshot()
            core = {
                "schema": SNAPSHOT_SCHEMA,
                "maximum_sessions": self._maximum_sessions,
                "retained_sessions": len(self._records),
                "queued_sessions": queued,
                "terminal_sessions": terminal,
                "duplicate_replays": self._duplicate_replays,
                "conflicting_duplicates": self._conflicting_duplicates,
                "capacity_rejections": self._capacity_rejections,
                "request_ids": list(self._records),
                "gateway_snapshot_sha256": gateway["gateway_snapshot_sha256"],
                "automatic_retry_allowed": False,
                "executor_attached": False,
                "controller_opened": False,
                "transport_opened": False,
                "controller_commands": [],
                "hardware_commands_generated": 0,
                "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "ledger_snapshot_sha256": _sha(core)}


def parse_typing_command_session_receipt_v1(value: Mapping[str, object]):
    fields = {
        "schema", "mission_id", "request_id", "status", "terminal",
        "revision", "ingress_fingerprint_sha256", "request_sha256",
        "admission_receipt_sha256", "service_receipt_sha256",
        "shadow_receipt_sha256", "blocker",
        "previous_session_receipt_sha256", "automatic_retry_allowed",
        "executor_attached", "controller_opened", "transport_opened",
        "controller_commands", "hardware_commands_generated",
        "hardware_access", "physical_authority", "session_receipt_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingCommandSessionLedgerV1Error("session receipt fields differ")
    unsigned = dict(value); supplied = unsigned.pop("session_receipt_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingCommandSessionLedgerV1Error("session receipt hash differs")
    _identifier(value["mission_id"], "mission_id")
    _identifier(value["request_id"], "request_id")
    for field in ("ingress_fingerprint_sha256",):
        if _HASH.fullmatch(value[field] or "") is None:
            raise TypingCommandSessionLedgerV1Error("session identity differs")
    status = value["status"]
    if status not in TERMINAL_STATUSES | {QUEUED}:
        raise TypingCommandSessionLedgerV1Error("session status differs")
    terminal = status in TERMINAL_STATUSES
    if value["terminal"] is not terminal:
        raise TypingCommandSessionLedgerV1Error("session terminal state differs")
    expected_revision = 0 if status in {QUEUED, ADMISSION_REJECTED,
                                        LEDGER_CAPACITY_REJECTED} else 1
    if value["revision"] != expected_revision:
        raise TypingCommandSessionLedgerV1Error("session revision differs")
    digests = ("request_sha256", "admission_receipt_sha256",
               "service_receipt_sha256", "shadow_receipt_sha256",
               "previous_session_receipt_sha256")
    for field in digests:
        item = value[field]
        if item is not None and _HASH.fullmatch(item) is None:
            raise TypingCommandSessionLedgerV1Error("session digest differs")
    if status == LEDGER_CAPACITY_REJECTED:
        if any(value[field] is not None for field in digests):
            raise TypingCommandSessionLedgerV1Error("capacity evidence differs")
        if value["blocker"] != "LEDGER_CAPACITY_EXHAUSTED":
            raise TypingCommandSessionLedgerV1Error("capacity blocker differs")
    elif status in {QUEUED, ADMISSION_REJECTED}:
        if value["admission_receipt_sha256"] is None:
            raise TypingCommandSessionLedgerV1Error("admission evidence differs")
        if any(value[field] is not None for field in
               ("service_receipt_sha256", "shadow_receipt_sha256",
                "previous_session_receipt_sha256")):
            raise TypingCommandSessionLedgerV1Error("queued evidence differs")
        queued_evidence = (value["request_sha256"] is not None
                           and value["blocker"] is None)
        rejected_evidence = (value["request_sha256"] is None
                             and isinstance(value["blocker"], str)
                             and bool(value["blocker"]))
        if ((status == QUEUED and not queued_evidence)
                or (status == ADMISSION_REJECTED and not rejected_evidence)):
            raise TypingCommandSessionLedgerV1Error("admission outcome differs")
    else:
        if any(value[field] is None for field in
               ("request_sha256", "admission_receipt_sha256",
                "service_receipt_sha256", "previous_session_receipt_sha256")):
            raise TypingCommandSessionLedgerV1Error("terminal evidence differs")
        completed = status == "SHADOW_COMPLETED"
        if completed is not (value["shadow_receipt_sha256"] is not None
                             and value["blocker"] is None):
            raise TypingCommandSessionLedgerV1Error("terminal outcome differs")
        if (not completed and (value["shadow_receipt_sha256"] is not None
                               or not isinstance(value["blocker"], str)
                               or not value["blocker"])):
            raise TypingCommandSessionLedgerV1Error("terminal blocker differs")
    if (value["automatic_retry_allowed"] is not False
            or value["executor_attached"] is not False
            or value["controller_opened"] is not False
            or value["transport_opened"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingCommandSessionLedgerV1Error("session authority differs")
    return value


def parse_typing_command_session_ledger_snapshot_v1(
    value: Mapping[str, object],
):
    fields = {
        "schema", "maximum_sessions", "retained_sessions", "queued_sessions",
        "terminal_sessions", "duplicate_replays", "conflicting_duplicates",
        "capacity_rejections", "request_ids", "gateway_snapshot_sha256",
        "automatic_retry_allowed", "executor_attached", "controller_opened",
        "transport_opened", "controller_commands", "hardware_commands_generated",
        "hardware_access", "physical_authority", "ledger_snapshot_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingCommandSessionLedgerV1Error("ledger snapshot fields differ")
    unsigned = dict(value); supplied = unsigned.pop("ledger_snapshot_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingCommandSessionLedgerV1Error("ledger snapshot hash differs")
    counters = ("maximum_sessions", "retained_sessions", "queued_sessions",
                "terminal_sessions", "duplicate_replays",
                "conflicting_duplicates", "capacity_rejections",
                "hardware_commands_generated")
    if any(isinstance(value[field], bool) or not isinstance(value[field], int)
           or value[field] < 0 for field in counters):
        raise TypingCommandSessionLedgerV1Error("ledger counters differ")
    ids = value["request_ids"]
    if (value["schema"] != SNAPSHOT_SCHEMA or not isinstance(ids, list)
            or not 1 <= value["maximum_sessions"] <= 4096
            or value["retained_sessions"] > value["maximum_sessions"]
            or value["retained_sessions"] != len(ids)
            or value["retained_sessions"] != value["queued_sessions"]
            + value["terminal_sessions"]
            or len(set(ids)) != len(ids)
            or _HASH.fullmatch(value["gateway_snapshot_sha256"] or "") is None):
        raise TypingCommandSessionLedgerV1Error("ledger accounting differs")
    for request_id in ids:
        _identifier(request_id, "request_id")
    if (value["automatic_retry_allowed"] is not False
            or value["executor_attached"] is not False
            or value["controller_opened"] is not False
            or value["transport_opened"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingCommandSessionLedgerV1Error("ledger authority differs")
    return value


__all__ = [
    "ADMISSION_REJECTED", "LEDGER_CAPACITY_REJECTED", "QUEUED",
    "RECEIPT_SCHEMA", "SNAPSHOT_SCHEMA", "TERMINAL_STATUSES",
    "TypingCommandSessionLedgerV1", "TypingCommandSessionLedgerV1Error",
    "parse_typing_command_session_ledger_snapshot_v1",
    "parse_typing_command_session_receipt_v1",
]
