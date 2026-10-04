from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.audit_ai_work_registry import (  # noqa: E402
    DEFAULT_REGISTRY,
    SCHEMA,
    RECEIPT_SCHEMA,
    audit_registry,
    canonical_hash,
    load_strict_json,
)


def _write_registry(path: Path, registry: dict) -> Path:
    registry = deepcopy(registry)
    registry.pop("registry_sha256", None)
    registry["registry_sha256"] = canonical_hash(registry)
    path.write_text(json.dumps(registry), encoding="utf-8")
    return path


def test_registry_schema_is_valid():
    Draft202012Validator.check_schema(load_strict_json(SCHEMA))
    Draft202012Validator.check_schema(load_strict_json(RECEIPT_SCHEMA))


def test_registry_covers_every_tracked_ai_test_once():
    receipt = audit_registry()
    assert receipt["status"] == "PASS"
    assert receipt["workstream_count"] == 7
    assert receipt["tracked_ai_test_count"] == 82
    assert receipt["documented_ai_test_count"] == 82
    assert receipt["unowned_test_paths"] == []
    assert receipt["multiply_owned_test_paths"] == []
    assert receipt["controller_authority"] is False
    assert receipt["hardware_writes"] == 0
    assert receipt["physical_movements"] == 0


def test_unowned_test_is_rejected(tmp_path):
    registry = load_strict_json(DEFAULT_REGISTRY)
    registry["workstreams"][1]["test_paths"].pop()
    path = _write_registry(tmp_path / "missing.json", registry)
    with pytest.raises(ValueError, match="AI test ownership mismatch"):
        audit_registry(path)


def test_multiply_owned_test_is_rejected(tmp_path):
    registry = load_strict_json(DEFAULT_REGISTRY)
    duplicate = registry["workstreams"][0]["test_paths"][0]
    registry["workstreams"][1]["test_paths"].append(duplicate)
    path = _write_registry(tmp_path / "duplicate-owner.json", registry)
    with pytest.raises(ValueError, match="multiple workstream owners"):
        audit_registry(path)


def test_missing_referenced_path_is_rejected(tmp_path):
    registry = load_strict_json(DEFAULT_REGISTRY)
    registry["workstreams"][0]["source_paths"][0] = "software/ai/rocell_ai/not_present.py"
    path = _write_registry(tmp_path / "missing-path.json", registry)
    with pytest.raises(FileNotFoundError):
        audit_registry(path)


def test_duplicate_json_fields_are_rejected(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema":"one","schema":"two"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_strict_json(path)
