"""Immutable materialization of the five arm-facing shadow planning stages."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from .typing_execution_plan_v1 import TypingExecutionPlanV1
from .typing_joint_schedule_v1 import TypingJointScheduleV1
from .typing_shadow_pipeline_v1 import parse_typing_shadow_pipeline_v1
from .typing_trajectory_plan_v1 import TypingTrajectoryPlanV1

SCHEMA = "rocell.typing_shadow_materialization.v1"
STAGES = (
    "typing_execution_plan", "typing_trajectory_plan",
    "typing_trajectory_ik_screen", "typing_joint_schedule",
    "typing_collision_intake",
)
ARTIFACT_HASH_FIELDS = {
    "typing_execution_plan": "plan_sha256",
    "typing_trajectory_plan": "trajectory_plan_sha256",
    "typing_trajectory_ik_screen": "typing_trajectory_ik_screen_sha256",
    "typing_joint_schedule": "schedule_sha256",
    "typing_collision_intake": "typing_collision_intake_sha256",
}
STAGE_HASH_FIELDS = {
    "typing_execution_plan": "typing_execution_plan_sha256",
    "typing_trajectory_plan": "typing_trajectory_plan_sha256",
    "typing_trajectory_ik_screen": "typing_trajectory_ik_screen_sha256",
    "typing_joint_schedule": "typing_joint_schedule_sha256",
    "typing_collision_intake": "typing_collision_intake_sha256",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")


class TypingShadowMaterializationV1Error(ValueError):
    """Materialized stage content, lineage, capacity, or authority differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _artifact(value: object, hash_field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypingShadowMaterializationV1Error("stage artifact is not an object")
    result = json.loads(_canonical(value))
    claimed = result.get(hash_field)
    unsigned = {key: item for key, item in result.items() if key != hash_field}
    if (not isinstance(claimed, str) or _SHA.fullmatch(claimed) is None
            or _sha(unsigned) != claimed):
        raise TypingShadowMaterializationV1Error(
            f"{hash_field} content hash differs"
        )
    if (result.get("controller_commands") != []
            or result.get("hardware_commands_generated") != 0
            or result.get("hardware_access") is not False
            or result.get("physical_authority") is not False):
        raise TypingShadowMaterializationV1Error(
            f"{hash_field} authority differs"
        )
    return result


class TypingShadowMaterializationRecorderV1:
    """Capture one pipeline's stage bodies, then bind its terminal receipt."""

    def __init__(self) -> None:
        self._captured: dict[str, Any] | None = None
        self._bundle: dict[str, Any] | None = None

    def capture(
        self, *, request_id: str, execution: TypingExecutionPlanV1,
        trajectory: TypingTrajectoryPlanV1, ik: Mapping[str, Any],
        schedule: TypingJointScheduleV1, collision: Mapping[str, Any],
    ) -> None:
        if self._captured is not None:
            raise TypingShadowMaterializationV1Error(
                "materialization recorder is single use"
            )
        if (not isinstance(request_id, str) or not request_id
                or not isinstance(execution, TypingExecutionPlanV1)
                or not isinstance(trajectory, TypingTrajectoryPlanV1)
                or not isinstance(schedule, TypingJointScheduleV1)):
            raise TypingShadowMaterializationV1Error(
                "materialization inputs differ"
            )
        artifacts = {
            "typing_execution_plan": execution.to_dict(),
            "typing_trajectory_plan": trajectory.to_dict(),
            "typing_trajectory_ik_screen": json.loads(_canonical(ik)),
            "typing_joint_schedule": schedule.to_dict(),
            "typing_collision_intake": json.loads(_canonical(collision)),
        }
        validated = {
            stage: _artifact(artifacts[stage], ARTIFACT_HASH_FIELDS[stage])
            for stage in STAGES
        }
        if validated["typing_execution_plan"]["request_id"] != request_id:
            raise TypingShadowMaterializationV1Error(
                "materialization request identity differs"
            )
        self._captured = {"request_id": request_id, "artifacts": validated}

    def finalize(self, shadow_receipt: Mapping[str, Any]) -> dict[str, Any]:
        if self._captured is None or self._bundle is not None:
            raise TypingShadowMaterializationV1Error(
                "materialization recorder is not finalizable"
            )
        shadow = parse_typing_shadow_pipeline_v1(shadow_receipt)
        if shadow["request_id"] != self._captured["request_id"]:
            raise TypingShadowMaterializationV1Error(
                "shadow and materialization request identities differ"
            )
        artifacts = self._captured["artifacts"]
        stage_hashes = {
            STAGE_HASH_FIELDS[stage]: artifacts[stage][ARTIFACT_HASH_FIELDS[stage]]
            for stage in STAGES
        }
        for field, digest in stage_hashes.items():
            if shadow["stage_hashes"][field] != digest:
                raise TypingShadowMaterializationV1Error(
                    f"materialized {field} differs from shadow receipt"
                )
        core = {
            "schema": SCHEMA,
            "request_id": shadow["request_id"],
            "shadow_pipeline_sha256": shadow["typing_shadow_pipeline_sha256"],
            "stage_hashes": stage_hashes,
            "stage_artifacts": artifacts,
            "materialization_class": "SYNTHETIC_OFFLINE_SHADOW_ONLY",
            "permit_review_ready": False,
            "required_next_evidence": [
                "INSTALLED_COLLISION_EVIDENCE",
                "FRESH_OBSERVED_START_STATE",
                "FRESH_CONTROLLER_STATE",
                "INDEPENDENT_EFFECT_VERIFIER",
            ],
            "automatic_retry_allowed": False,
            "eligible_for_executor": False,
            "permit_issued": False,
            "controller_commands": [],
            "hardware_commands_generated": 0,
            "hardware_access": False,
            "physical_authority": False,
        }
        self._bundle = {**core, "materialization_sha256": _sha(core)}
        return json.loads(_canonical(self._bundle))


def parse_typing_shadow_materialization_v1(value: Mapping[str, Any]):
    fields = {
        "schema", "request_id", "shadow_pipeline_sha256", "stage_hashes",
        "stage_artifacts", "materialization_class", "permit_review_ready",
        "required_next_evidence", "automatic_retry_allowed",
        "eligible_for_executor", "permit_issued", "controller_commands",
        "hardware_commands_generated", "hardware_access", "physical_authority",
        "materialization_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingShadowMaterializationV1Error(
            "materialization fields differ"
        )
    unsigned = dict(value)
    supplied = unsigned.pop("materialization_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingShadowMaterializationV1Error("materialization hash differs")
    artifacts = value["stage_artifacts"]
    hashes = value["stage_hashes"]
    if (value["schema"] != SCHEMA or not isinstance(artifacts, Mapping)
            or set(artifacts) != set(STAGES) or not isinstance(hashes, Mapping)
            or set(hashes) != set(STAGE_HASH_FIELDS.values())):
        raise TypingShadowMaterializationV1Error(
            "materialization stage inventory differs"
        )
    for stage in STAGES:
        parsed = _artifact(artifacts[stage], ARTIFACT_HASH_FIELDS[stage])
        if (parsed[ARTIFACT_HASH_FIELDS[stage]]
                != hashes[STAGE_HASH_FIELDS[stage]]):
            raise TypingShadowMaterializationV1Error(
                "materialization stage lineage differs"
            )
    if (not isinstance(value["request_id"], str) or not value["request_id"]
            or _SHA.fullmatch(value["shadow_pipeline_sha256"] or "") is None
            or value["materialization_class"]
            != "SYNTHETIC_OFFLINE_SHADOW_ONLY"
            or value["permit_review_ready"] is not False
            or value["automatic_retry_allowed"] is not False
            or value["eligible_for_executor"] is not False
            or value["permit_issued"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingShadowMaterializationV1Error(
            "materialization identity or authority differs"
        )
    return value


class TypingShadowMaterializationStoreV1:
    """Bounded immutable storage keyed by request and shadow receipt hash."""

    def __init__(self, *, maximum_entries: int = 4096) -> None:
        if (isinstance(maximum_entries, bool) or not isinstance(maximum_entries, int)
                or not 1 <= maximum_entries <= 4096):
            raise TypingShadowMaterializationV1Error(
                "maximum_entries must be in [1, 4096]"
            )
        self._lock = RLock()
        self._maximum_entries = maximum_entries
        self._items: OrderedDict[str, bytes] = OrderedDict()

    def put(self, request_id: str, bundle: Mapping[str, Any]) -> str:
        parse_typing_shadow_materialization_v1(bundle)
        if bundle["request_id"] != request_id:
            raise TypingShadowMaterializationV1Error(
                "materialization store identity differs"
            )
        payload = _canonical(bundle)
        with self._lock:
            if request_id in self._items:
                if self._items[request_id] != payload:
                    raise TypingShadowMaterializationV1Error(
                        "materialization cannot be replaced"
                    )
                return bundle["materialization_sha256"]
            if len(self._items) >= self._maximum_entries:
                raise TypingShadowMaterializationV1Error(
                    "materialization store capacity is exhausted"
                )
            self._items[request_id] = payload
            return bundle["materialization_sha256"]

    def get(self, request_id: str, shadow_pipeline_sha256: str) -> dict[str, Any]:
        with self._lock:
            payload = self._items.get(request_id)
            if payload is None:
                raise TypingShadowMaterializationV1Error(
                    "materialization is unavailable"
                )
            value = json.loads(payload)
            if value["shadow_pipeline_sha256"] != shadow_pipeline_sha256:
                raise TypingShadowMaterializationV1Error(
                    "materialization content address differs"
                )
            parse_typing_shadow_materialization_v1(value)
            return value


__all__ = [
    "ARTIFACT_HASH_FIELDS", "SCHEMA", "STAGES", "STAGE_HASH_FIELDS",
    "TypingShadowMaterializationRecorderV1",
    "TypingShadowMaterializationStoreV1",
    "TypingShadowMaterializationV1Error",
    "parse_typing_shadow_materialization_v1",
]
