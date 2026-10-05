"""Bounded in-memory content store for canonical typing shadow receipts."""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
from threading import RLock
from typing import Any, Mapping

from .typing_shadow_pipeline_v1 import parse_typing_shadow_pipeline_v1

SCHEMA = "rocell.typing_shadow_artifact_store_snapshot.v1"
_HASH = re.compile(r"^[0-9a-f]{64}$")


class TypingShadowArtifactStoreV1Error(ValueError):
    """Artifact identity, capacity, content, or retrieval differs."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class TypingShadowArtifactStoreV1:
    """Retain each verified receipt exactly once without replacement."""

    def __init__(
        self, *, maximum_entries: int = 4096,
        maximum_artifact_bytes: int = 65_536,
    ) -> None:
        if (isinstance(maximum_entries, bool)
                or not isinstance(maximum_entries, int)
                or not 1 <= maximum_entries <= 4096):
            raise TypingShadowArtifactStoreV1Error(
                "maximum_entries must be in [1, 4096]"
            )
        if (isinstance(maximum_artifact_bytes, bool)
                or not isinstance(maximum_artifact_bytes, int)
                or not 1024 <= maximum_artifact_bytes <= 1_048_576):
            raise TypingShadowArtifactStoreV1Error(
                "maximum_artifact_bytes must be in [1024, 1048576]"
            )
        self._lock = RLock()
        self._maximum_entries = maximum_entries
        self._maximum_artifact_bytes = maximum_artifact_bytes
        self._artifacts: OrderedDict[str, bytes] = OrderedDict()
        self._hashes: dict[str, str] = {}
        self._total_bytes = 0
        self._idempotent_puts = 0
        self._retrievals = 0
        self._misses = 0

    def put(self, request_id: str, artifact: Mapping[str, Any]) -> str:
        if not isinstance(request_id, str) or not request_id:
            raise TypingShadowArtifactStoreV1Error("request_id is invalid")
        try:
            parsed = dict(parse_typing_shadow_pipeline_v1(artifact))
        except ValueError as exc:
            raise TypingShadowArtifactStoreV1Error(
                f"shadow artifact differs: {exc}"
            ) from exc
        if parsed["request_id"] != request_id:
            raise TypingShadowArtifactStoreV1Error(
                "artifact request identity differs"
            )
        payload = _canonical(artifact)
        if len(payload) > self._maximum_artifact_bytes:
            raise TypingShadowArtifactStoreV1Error("artifact exceeds byte bound")
        digest = parsed["typing_shadow_pipeline_sha256"]
        with self._lock:
            existing = self._artifacts.get(request_id)
            if existing is not None:
                if existing != payload or self._hashes[request_id] != digest:
                    raise TypingShadowArtifactStoreV1Error(
                        "artifact request identity cannot be replaced"
                    )
                self._idempotent_puts += 1
                return digest
            if len(self._artifacts) >= self._maximum_entries:
                raise TypingShadowArtifactStoreV1Error(
                    "artifact store capacity is exhausted"
                )
            self._artifacts[request_id] = payload
            self._hashes[request_id] = digest
            self._total_bytes += len(payload)
            return digest

    def get(self, request_id: str, expected_sha256: str) -> dict[str, Any]:
        if (not isinstance(request_id, str) or not request_id
                or not isinstance(expected_sha256, str)
                or _HASH.fullmatch(expected_sha256) is None):
            raise TypingShadowArtifactStoreV1Error(
                "artifact retrieval identity differs"
            )
        with self._lock:
            payload = self._artifacts.get(request_id)
            if payload is None:
                self._misses += 1
                raise TypingShadowArtifactStoreV1Error("artifact is unavailable")
            if self._hashes[request_id] != expected_sha256:
                self._misses += 1
                raise TypingShadowArtifactStoreV1Error(
                    "artifact content address differs"
                )
            self._retrievals += 1
            value = json.loads(payload)
            parse_typing_shadow_pipeline_v1(value)
            return value

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            core = {
                "schema": SCHEMA,
                "maximum_entries": self._maximum_entries,
                "maximum_artifact_bytes": self._maximum_artifact_bytes,
                "retained_entries": len(self._artifacts),
                "total_bytes": self._total_bytes,
                "idempotent_puts": self._idempotent_puts,
                "retrievals": self._retrievals,
                "misses": self._misses,
                "request_ids": list(self._artifacts),
                "content_sha256": [self._hashes[item]
                                   for item in self._artifacts],
                "mutable_replacement_allowed": False,
                "automatic_retry_allowed": False,
                "controller_commands": [],
                "hardware_commands_generated": 0,
                "hardware_access": False,
                "physical_authority": False,
            }
            return {**core, "artifact_store_snapshot_sha256": _sha(core)}


def parse_typing_shadow_artifact_store_snapshot_v1(value: Mapping[str, object]):
    fields = {"schema", "maximum_entries", "maximum_artifact_bytes",
              "retained_entries", "total_bytes", "idempotent_puts",
              "retrievals", "misses", "request_ids", "content_sha256",
              "mutable_replacement_allowed", "automatic_retry_allowed",
              "controller_commands", "hardware_commands_generated",
              "hardware_access", "physical_authority",
              "artifact_store_snapshot_sha256"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise TypingShadowArtifactStoreV1Error("artifact snapshot fields differ")
    unsigned = dict(value); supplied = unsigned.pop("artifact_store_snapshot_sha256")
    if not isinstance(supplied, str) or supplied != _sha(unsigned):
        raise TypingShadowArtifactStoreV1Error("artifact snapshot hash differs")
    counters = ("maximum_entries", "maximum_artifact_bytes", "retained_entries",
                "total_bytes", "idempotent_puts", "retrievals", "misses",
                "hardware_commands_generated")
    if any(isinstance(value[field], bool) or not isinstance(value[field], int)
           or value[field] < 0 for field in counters):
        raise TypingShadowArtifactStoreV1Error("artifact counters differ")
    ids, hashes = value["request_ids"], value["content_sha256"]
    if (value["schema"] != SCHEMA or not isinstance(ids, list)
            or not isinstance(hashes, list) or len(ids) != len(hashes)
            or len(ids) != value["retained_entries"]
            or len(set(ids)) != len(ids)
            or len(set(hashes)) != len(hashes)
            or not 1 <= value["maximum_entries"] <= 4096
            or not 1024 <= value["maximum_artifact_bytes"] <= 1_048_576
            or value["retained_entries"] > value["maximum_entries"]
            or value["total_bytes"] > (
                value["retained_entries"] * value["maximum_artifact_bytes"]
            )
            or any(not isinstance(item, str) or not item for item in ids)
            or any(not isinstance(item, str) or _HASH.fullmatch(item) is None
                   for item in hashes)):
        raise TypingShadowArtifactStoreV1Error("artifact accounting differs")
    if (value["mutable_replacement_allowed"] is not False
            or value["automatic_retry_allowed"] is not False
            or value["controller_commands"] != []
            or value["hardware_commands_generated"] != 0
            or value["hardware_access"] is not False
            or value["physical_authority"] is not False):
        raise TypingShadowArtifactStoreV1Error("artifact authority differs")
    return value


__all__ = ["SCHEMA", "TypingShadowArtifactStoreV1",
           "TypingShadowArtifactStoreV1Error",
           "parse_typing_shadow_artifact_store_snapshot_v1"]
