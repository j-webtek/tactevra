"""Bounded zero-authority service for generation-bound typing shadow requests."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from .context import SimulationContext
from .typing_exact_ik_cache_owner_v1 import TypingExactIkCacheOwnerV1


RECEIPT_SCHEMA = "rocell.typing_shadow_service_receipt.v1"
SNAPSHOT_SCHEMA = "rocell.typing_shadow_service_snapshot.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL = frozenset({
    "SHADOW_COMPLETED",
    "CANCELED_BEFORE_ADMISSION",
    "STALE_GENERATION_REJECTED",
    "SHADOW_REJECTED",
})
_FORBIDDEN_INPUTS = frozenset({
    "context_lifecycle", "prepared_planner", "exact_ik_result_cache",
})


class TypingShadowServiceV1Error(ValueError):
    """A service request, transition, receipt, or diagnostic is invalid."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise TypingShadowServiceV1Error(f"{label} is not a SHA-256 digest")
    return value


def _identifier(value: object, label: str, *, maximum: int = 128) -> str:
    if (
        not isinstance(value, str) or not value or len(value) > maximum
        or value != value.strip() or ":\\" in value or "://" in value
        or value.startswith(("/", "\\"))
    ):
        raise TypingShadowServiceV1Error(f"{label} is invalid or path-like")
    return value


@dataclass(frozen=True, slots=True)
class _QueuedRequest:
    request_id: str
    request_sha256: str
    context_epoch_sha256: str
    service_instance_id: str
    generation: int
    pipeline_inputs: dict[str, Any]


def _request_identity(
    request_id: str, pipeline_inputs: Mapping[str, Any], *,
    context_epoch_sha256: str, service_instance_id: str, generation: int,
) -> str:
    payload = pipeline_inputs.get("payload")
    if not isinstance(payload, bytes) or not payload:
        raise TypingShadowServiceV1Error("payload must be nonempty bytes")
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TypingShadowServiceV1Error("payload is not canonical JSON") from exc
    if not isinstance(document, Mapping) or document.get("request_id") != request_id:
        raise TypingShadowServiceV1Error(
            "service request identity differs from payload"
        )
    if _canonical(document) != payload:
        raise TypingShadowServiceV1Error("payload is not canonical JSON")
    intent = pipeline_inputs.get("intent_plan")
    plan_hash = getattr(intent, "plan_hash", None)
    _digest(plan_hash, "intent plan")
    return _sha({
        "request_id": request_id,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "intent_plan_sha256": plan_hash,
        "context_epoch_sha256": context_epoch_sha256,
        "service_instance_id": service_instance_id,
        "generation": generation,
    })


def _receipt(
    queued: _QueuedRequest, *, status: str,
    active_context_epoch_sha256: str,
    active_service_instance_id: str,
    active_generation: int,
    shadow_receipt_sha256: str | None,
    blocker: str | None,
) -> dict[str, Any]:
    if status not in _TERMINAL:
        raise TypingShadowServiceV1Error("terminal status differs")
    if status == "SHADOW_COMPLETED":
        shadow_receipt_sha256 = _digest(
            shadow_receipt_sha256, "shadow receipt"
        )
        if blocker is not None:
            raise TypingShadowServiceV1Error(
                "completed service receipt cannot contain a blocker"
            )
    elif shadow_receipt_sha256 is not None:
        raise TypingShadowServiceV1Error(
            "blocked service receipt cannot contain a shadow receipt"
        )
    core = {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "request_id": queued.request_id,
        "request_sha256": queued.request_sha256,
        "submitted_context_epoch_sha256": queued.context_epoch_sha256,
        "submitted_service_instance_id": queued.service_instance_id,
        "submitted_generation": queued.generation,
        "active_context_epoch_sha256": active_context_epoch_sha256,
        "active_service_instance_id": active_service_instance_id,
        "active_generation": active_generation,
        "shadow_receipt_sha256": shadow_receipt_sha256,
        "blocker": blocker,
        "automatic_retry_allowed": False,
        "controller_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "physical_authority": False,
    }
    return {**core, "service_receipt_sha256": _sha(core)}


class TypingShadowServiceV1:
    """Serialize bounded shadow work without acquiring execution capability."""

    def __init__(
        self, owner: TypingExactIkCacheOwnerV1, *, maximum_queued: int = 32,
        maximum_requests: int = 4096,
    ) -> None:
        if not isinstance(owner, TypingExactIkCacheOwnerV1):
            raise TypeError("owner must be TypingExactIkCacheOwnerV1")
        for value, label, lower, upper in (
            (maximum_queued, "maximum_queued", 1, 64),
            (maximum_requests, "maximum_requests", 1, 4096),
        ):
            if (
                isinstance(value, bool) or not isinstance(value, int)
                or not lower <= value <= upper
            ):
                raise TypingShadowServiceV1Error(
                    f"{label} must be in [{lower}, {upper}]"
                )
        if maximum_requests < maximum_queued:
            raise TypingShadowServiceV1Error(
                "maximum_requests cannot be smaller than maximum_queued"
            )
        self._lock = RLock()
        self._owner = owner
        self._maximum_queued = maximum_queued
        self._maximum_requests = maximum_requests
        self._queue: OrderedDict[str, _QueuedRequest] = OrderedDict()
        self._used_request_ids: set[str] = set()
        self._submitted = 0
        self._completed = 0
        self._canceled = 0
        self._stale_rejected = 0
        self._shadow_rejected = 0
        self._invalidated_queued = 0
        self._reloads = 0
        self._restarts = 0
        self._invalidations = 0
        self._active = True

    @property
    def context(self) -> SimulationContext:
        with self._lock:
            self._require_active()
            return self._owner.context

    def _require_active(self) -> None:
        if not self._active:
            raise TypingShadowServiceV1Error("shadow service is invalidated")

    def submit(
        self, request_id: str, pipeline_inputs: Mapping[str, Any],
    ) -> str:
        request_id = _identifier(request_id, "request_id")
        if not isinstance(pipeline_inputs, Mapping):
            raise TypeError("pipeline_inputs must be a mapping")
        if _FORBIDDEN_INPUTS.intersection(pipeline_inputs):
            raise TypingShadowServiceV1Error(
                "owner-managed pipeline inputs cannot be submitted"
            )
        with self._lock:
            self._require_active()
            if len(self._queue) >= self._maximum_queued:
                raise TypingShadowServiceV1Error("shadow service queue is full")
            if len(self._used_request_ids) >= self._maximum_requests:
                raise TypingShadowServiceV1Error(
                    "shadow service lifetime request bound is exhausted"
                )
            if request_id in self._used_request_ids:
                raise TypingShadowServiceV1Error("request_id cannot be reused")
            binding = self._owner.binding()
            inputs = dict(pipeline_inputs)
            if inputs.get("context") is not binding.context:
                raise TypingShadowServiceV1Error(
                    "request context is not the service's active context"
                )
            request_sha256 = _request_identity(
                request_id,
                inputs,
                context_epoch_sha256=binding.context_epoch_sha256,
                service_instance_id=binding.service_instance_id,
                generation=binding.generation,
            )
            queued = _QueuedRequest(
                request_id=request_id,
                request_sha256=request_sha256,
                context_epoch_sha256=binding.context_epoch_sha256,
                service_instance_id=binding.service_instance_id,
                generation=binding.generation,
                pipeline_inputs=inputs,
            )
            self._queue[request_id] = queued
            self._used_request_ids.add(request_id)
            self._submitted += 1
            return request_sha256

    def _active_identity(self) -> tuple[str, str, int]:
        binding = self._owner.binding()
        return (
            binding.context_epoch_sha256,
            binding.service_instance_id,
            binding.generation,
        )

    def cancel(self, request_id: str) -> dict[str, Any]:
        request_id = _identifier(request_id, "request_id")
        with self._lock:
            self._require_active()
            queued = self._queue.pop(request_id, None)
            if queued is None:
                raise TypingShadowServiceV1Error(
                    "request is not queued for pre-admission cancellation"
                )
            active = self._active_identity()
            self._canceled += 1
            return _receipt(
                queued,
                status="CANCELED_BEFORE_ADMISSION",
                active_context_epoch_sha256=active[0],
                active_service_instance_id=active[1],
                active_generation=active[2],
                shadow_receipt_sha256=None,
                blocker="CANCELED_BEFORE_ADMISSION",
            )

    def execute_next(self) -> dict[str, Any]:
        with self._lock:
            self._require_active()
            if not self._queue:
                raise TypingShadowServiceV1Error("shadow service queue is empty")
            _, queued = self._queue.popitem(last=False)
            active = self._active_identity()
            submitted = (
                queued.context_epoch_sha256,
                queued.service_instance_id,
                queued.generation,
            )
            if submitted != active:
                self._stale_rejected += 1
                return _receipt(
                    queued,
                    status="STALE_GENERATION_REJECTED",
                    active_context_epoch_sha256=active[0],
                    active_service_instance_id=active[1],
                    active_generation=active[2],
                    shadow_receipt_sha256=None,
                    blocker="SUBMITTED_LIFECYCLE_IS_STALE",
                )
            try:
                shadow = self._owner.run_shadow_pipeline(**queued.pipeline_inputs)
                completed_receipt = _receipt(
                    queued,
                    status="SHADOW_COMPLETED",
                    active_context_epoch_sha256=active[0],
                    active_service_instance_id=active[1],
                    active_generation=active[2],
                    shadow_receipt_sha256=shadow.get(
                        "typing_shadow_pipeline_sha256"
                    ),
                    blocker=None,
                )
            except Exception:
                self._shadow_rejected += 1
                return _receipt(
                    queued,
                    status="SHADOW_REJECTED",
                    active_context_epoch_sha256=active[0],
                    active_service_instance_id=active[1],
                    active_generation=active[2],
                    shadow_receipt_sha256=None,
                    blocker="SHADOW_PIPELINE_REJECTED",
                )
            self._completed += 1
            return completed_receipt

    def reload_sources(self, *, issued_monotonic_ns: int) -> None:
        with self._lock:
            self._require_active()
            self._owner.reload_sources(issued_monotonic_ns=issued_monotonic_ns)
            self._reloads += 1

    def restart(
        self, *, service_instance_id: str, issued_monotonic_ns: int,
    ) -> None:
        with self._lock:
            self._require_active()
            self._owner.restart(
                service_instance_id=service_instance_id,
                issued_monotonic_ns=issued_monotonic_ns,
            )
            self._restarts += 1

    def invalidate(self) -> None:
        with self._lock:
            if self._active:
                self._owner.invalidate()
                self._active = False
                self._invalidations += 1
                self._invalidated_queued += len(self._queue)
                self._queue.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            owner = self._owner.snapshot()
            core = {
                "schema": SNAPSHOT_SCHEMA,
                "active": self._active,
                "maximum_queued": self._maximum_queued,
                "maximum_requests": self._maximum_requests,
                "queued": len(self._queue),
                "submitted": self._submitted,
                "completed": self._completed,
                "canceled": self._canceled,
                "stale_rejected": self._stale_rejected,
                "shadow_rejected": self._shadow_rejected,
                "invalidated_queued": self._invalidated_queued,
                "reloads": self._reloads,
                "restarts": self._restarts,
                "invalidations": self._invalidations,
                "queued_request_ids": list(self._queue),
                "owner_snapshot_sha256": owner["owner_snapshot_sha256"],
                "automatic_retry_allowed": False,
                "executor_attached": False,
                "sole_writer_attached": False,
                "controller_commands": [],
                "hardware_commands_generated": 0,
                "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "service_snapshot_sha256": _sha(core)}


def parse_typing_shadow_service_receipt_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    fields = {
        "schema", "status", "request_id", "request_sha256",
        "submitted_context_epoch_sha256", "submitted_service_instance_id",
        "submitted_generation", "active_context_epoch_sha256",
        "active_service_instance_id", "active_generation",
        "shadow_receipt_sha256", "blocker", "automatic_retry_allowed",
        "controller_commands", "hardware_commands_generated", "hardware_access",
        "physical_authority", "service_receipt_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingShadowServiceV1Error("service receipt fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("service_receipt_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingShadowServiceV1Error("service receipt hash differs")
    if value.get("schema") != RECEIPT_SCHEMA or value.get("status") not in _TERMINAL:
        raise TypingShadowServiceV1Error("service receipt schema or status differs")
    _identifier(value.get("request_id"), "request_id")
    for field in (
        "request_sha256", "submitted_context_epoch_sha256",
        "active_context_epoch_sha256",
    ):
        _digest(value.get(field), field)
    for field in ("submitted_service_instance_id", "active_service_instance_id"):
        _identifier(value.get(field), field, maximum=192)
    for field in ("submitted_generation", "active_generation"):
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingShadowServiceV1Error(f"{field} differs")
    shadow = value.get("shadow_receipt_sha256")
    blocker = value.get("blocker")
    if value["status"] == "SHADOW_COMPLETED":
        _digest(shadow, "shadow receipt")
        if blocker is not None:
            raise TypingShadowServiceV1Error("completed receipt blocker differs")
    elif shadow is not None or not isinstance(blocker, str) or not blocker:
        raise TypingShadowServiceV1Error("blocked receipt evidence differs")
    expected_blockers = {
        "CANCELED_BEFORE_ADMISSION": "CANCELED_BEFORE_ADMISSION",
        "STALE_GENERATION_REJECTED": "SUBMITTED_LIFECYCLE_IS_STALE",
        "SHADOW_REJECTED": "SHADOW_PIPELINE_REJECTED",
    }
    if value["status"] in expected_blockers and blocker != expected_blockers[
        value["status"]
    ]:
        raise TypingShadowServiceV1Error("service receipt blocker differs")
    submitted_identity = (
        value["submitted_context_epoch_sha256"],
        value["submitted_service_instance_id"],
        value["submitted_generation"],
    )
    active_identity = (
        value["active_context_epoch_sha256"],
        value["active_service_instance_id"],
        value["active_generation"],
    )
    if value["status"] == "STALE_GENERATION_REJECTED" and (
        submitted_identity == active_identity
    ):
        raise TypingShadowServiceV1Error("service receipt lifecycle differs")
    if value["status"] in {"SHADOW_COMPLETED", "SHADOW_REJECTED"} and (
        submitted_identity != active_identity
    ):
        raise TypingShadowServiceV1Error("service receipt lifecycle differs")
    if (
        value.get("automatic_retry_allowed") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingShadowServiceV1Error("service receipt violates zero authority")
    return value


def parse_typing_shadow_service_snapshot_v1(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    fields = {
        "schema", "active", "maximum_queued", "maximum_requests", "queued",
        "submitted", "completed", "canceled", "stale_rejected",
        "shadow_rejected", "invalidated_queued", "reloads", "restarts",
        "invalidations",
        "queued_request_ids", "owner_snapshot_sha256", "automatic_retry_allowed",
        "executor_attached", "sole_writer_attached", "controller_commands",
        "hardware_commands_generated", "hardware_access", "physical_authority",
        "service_snapshot_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingShadowServiceV1Error("service snapshot fields differ")
    unsigned = dict(value)
    supplied = unsigned.pop("service_snapshot_sha256")
    if not isinstance(supplied, str) or _sha(unsigned) != supplied:
        raise TypingShadowServiceV1Error("service snapshot hash differs")
    if value.get("schema") != SNAPSHOT_SCHEMA or not isinstance(
        value.get("active"), bool
    ):
        raise TypingShadowServiceV1Error("service snapshot identity differs")
    for field in (
        "maximum_queued", "maximum_requests", "queued", "submitted",
        "completed", "canceled", "stale_rejected", "shadow_rejected",
        "invalidated_queued", "reloads", "restarts", "invalidations",
    ):
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, int) or item < 0:
            raise TypingShadowServiceV1Error(f"{field} differs")
    ids = value.get("queued_request_ids")
    if (
        not isinstance(ids, list) or len(ids) != value["queued"]
        or len(ids) > value["maximum_queued"] or len(set(ids)) != len(ids)
    ):
        raise TypingShadowServiceV1Error("queued request identities differ")
    for request_id in ids:
        _identifier(request_id, "queued request_id")
    if (
        not 1 <= value["maximum_queued"] <= 64
        or not 1 <= value["maximum_requests"] <= 4096
        or value["maximum_requests"] < value["maximum_queued"]
        or value["submitted"] > value["maximum_requests"]
        or value["submitted"]
        != (
            value["queued"] + value["completed"] + value["canceled"]
            + value["stale_rejected"] + value["shadow_rejected"]
            + value["invalidated_queued"]
        )
        or value["invalidations"] not in (0, 1)
    ):
        raise TypingShadowServiceV1Error("service counters differ")
    _digest(value.get("owner_snapshot_sha256"), "owner snapshot")
    if (
        value.get("automatic_retry_allowed") is not False
        or value.get("executor_attached") is not False
        or value.get("sole_writer_attached") is not False
        or value.get("controller_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("physical_authority") is not False
    ):
        raise TypingShadowServiceV1Error("service snapshot violates zero authority")
    return value


__all__ = [
    "RECEIPT_SCHEMA", "SNAPSHOT_SCHEMA", "TypingShadowServiceV1",
    "TypingShadowServiceV1Error", "parse_typing_shadow_service_receipt_v1",
    "parse_typing_shadow_service_snapshot_v1",
]
