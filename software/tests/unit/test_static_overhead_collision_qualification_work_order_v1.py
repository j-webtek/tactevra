from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.static_overhead_collision_qualification_work_order_v1 import (
    build_static_overhead_collision_qualification_work_order_v1,
)


WORKSPACE = Path(__file__).resolve().parents[3]
AUDIT = WORKSPACE / "software/ai/eval/static_overhead_collision_source_audit_20261017.json"


def _audit_sha256() -> str:
    return hashlib.sha256(AUDIT.read_bytes()).hexdigest()


def test_work_order_preserves_all_bodies_and_reuses_retained_dimensions() -> None:
    first = build_static_overhead_collision_qualification_work_order_v1(
        AUDIT,
        _audit_sha256(),
    )
    second = build_static_overhead_collision_qualification_work_order_v1(
        AUDIT,
        _audit_sha256(),
    )

    rows = {row["body_id"]: row for row in first["body_qualification_work"]}
    assert first == second
    assert first["required_body_count"] == 19
    assert len(rows) == 19
    assert first["retained_dimension_body_ids"] == [
        "workcell:board_solid",
        "workcell:keyboard",
        "workcell:phone",
    ]
    assert first["repeat_dimension_measurement_body_ids"] == []
    assert all(not row["repeat_dimension_measurement_requested"] for row in rows.values())
    assert rows["workcell:keyboard"]["retained_dimensions_reused"] is True
    assert rows["workcell:phone"]["retained_dimensions_reused"] is True
    assert rows["installation:static_camera_cable"]["qualification_action_class"] == (
        "QUALIFY_FIXED_FLEXIBLE_ENVELOPE"
    )
    assert rows["attachment:contact_tool"]["qualification_action_class"] == (
        "REVIEW_BARE_JAW_ABSENCE_DECLARATION"
    )
    assert rows["robot:link5"]["qualification_action_class"] == (
        "REVIEW_CONSERVATIVE_LINK_ENVELOPE"
    )
    assert all(row["measurement_status_after_work_order"] == "PENDING" for row in rows.values())
    assert first["profile_generated"] is False
    assert first["collision_screening_executed"] is False
    assert first["controller_commands"] == []
    assert first["hardware_access"] is False
    assert first["physical_movements"] == 0
    assert first["physical_authority"] is False

    staged = [body for stage in first["execution_order"] for body in stage["body_ids"]]
    assert set(staged) == set(rows)
    assert len(staged) == len(set(staged))


def test_work_order_rejects_file_hash_and_canonical_hash_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file hash mismatch"):
        build_static_overhead_collision_qualification_work_order_v1(AUDIT, "0" * 64)

    document = json.loads(AUDIT.read_text(encoding="utf-8"))
    document["candidate_body_count"] = 18
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        build_static_overhead_collision_qualification_work_order_v1(
            changed,
            hashlib.sha256(changed.read_bytes()).hexdigest(),
        )


def test_work_order_rejects_missing_or_duplicate_body_rows(tmp_path: Path) -> None:
    document = json.loads(AUDIT.read_text(encoding="utf-8"))
    document["body_source_coverage"] = document["body_source_coverage"][:-1]
    core = {key: value for key, value in document.items() if key != "report_sha256"}
    canonical = json.dumps(
        core,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    document["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    incomplete = tmp_path / "incomplete.json"
    incomplete.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 19"):
        build_static_overhead_collision_qualification_work_order_v1(
            incomplete,
            hashlib.sha256(incomplete.read_bytes()).hexdigest(),
        )
