from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "software/ai"))

from rocell.application.typing_shadow_artifact_store_v1 import (
    TypingShadowArtifactStoreV1,
    TypingShadowArtifactStoreV1Error,
    parse_typing_shadow_artifact_store_snapshot_v1,
)
from software.scripts import run_typing_command_session_ledger_campaign_v1 as runner


def _artifact(request_id="artifact"):
    ledger, supervisor = runner._ledger()
    inputs = runner._inputs(ledger, request_id)
    from rocell.application.typing_shadow_pipeline_v1 import run_typing_shadow_pipeline_v1
    artifact = run_typing_shadow_pipeline_v1(**inputs)
    supervisor.invalidate()
    return artifact


def test_store_is_content_addressed_idempotent_and_bounded():
    store = TypingShadowArtifactStoreV1(maximum_entries=1)
    artifact = _artifact()
    digest = store.put("artifact", artifact)
    assert store.put("artifact", artifact) == digest
    assert store.get("artifact", digest) == artifact
    with pytest.raises(TypingShadowArtifactStoreV1Error, match="capacity"):
        store.put("other", _artifact("other"))
    snapshot = store.snapshot()
    assert parse_typing_shadow_artifact_store_snapshot_v1(snapshot) == snapshot
    assert snapshot["retained_entries"] == 1
    assert snapshot["idempotent_puts"] == 1


def test_store_rejects_replacement_wrong_hash_and_tamper():
    store = TypingShadowArtifactStoreV1()
    artifact = _artifact(); digest = store.put("artifact", artifact)
    changed = copy.deepcopy(artifact); changed["request_id"] = "different"
    with pytest.raises(TypingShadowArtifactStoreV1Error):
        store.put("artifact", changed)
    with pytest.raises(TypingShadowArtifactStoreV1Error, match="content address"):
        store.get("artifact", "f" * 64)
    snapshot = store.snapshot(); changed = dict(snapshot)
    changed["physical_authority"] = True
    with pytest.raises(TypingShadowArtifactStoreV1Error):
        parse_typing_shadow_artifact_store_snapshot_v1(changed)


def test_runtime_retains_artifact_without_replanning():
    ledger, supervisor = runner._ledger()
    inputs = runner._inputs(ledger, "runtime")
    ledger.submit("mission-runtime", "runtime", inputs)
    terminal = ledger.run_next_shadow()
    artifact = ledger.shadow_artifact("runtime")
    assert artifact["typing_shadow_pipeline_sha256"] == terminal[
        "shadow_receipt_sha256"]
    assert ledger.shadow_artifact("runtime") == artifact
    snapshot = ledger.artifact_store_snapshot()
    assert snapshot["retained_entries"] == 1
    assert snapshot["retrievals"] == 2
    supervisor.invalidate()
