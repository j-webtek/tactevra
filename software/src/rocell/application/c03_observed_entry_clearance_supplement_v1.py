"""Seal numeric clearance already derived by the ICQ-7 entry sweep.

The supplement is a compatibility bridge for retained ICQ-7 v1 receipts.  It
does not accept caller-provided margins: every value is reconstructed from the
sealed continuous-sweep evidence nested in that receipt.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Mapping

from .c03_observed_route_entry_qualification_v1 import (
    CLEAR_STATUS,
    parse_c03_observed_route_entry_qualification_v1,
)


SCHEMA = "tactevra.c03_observed_entry_clearance_supplement.v1"
STATUS = "NUMERIC_ENTRY_CLEARANCE_AVAILABLE_ZERO_AUTHORITY"
METHOD = (
    "minimum Euclidean separation between uncertainty-inflated conservative "
    "sweep AABBs for every adjacent observed-entry sample pair"
)
_FIELDS = {
    "schema", "status", "source_entry_qualification_sha256",
    "entry_segment_count", "segment_clearances",
    "minimum_clearance_lower_bound_mm", "limiting_body_pair",
    "clearance_measurement", "controller_commands", "wire_commands",
    "hardware_commands_generated", "hardware_access", "hardware_writes",
    "physical_movements", "physical_authority",
    "c03_observed_entry_clearance_supplement_sha256",
}
_ROW_FIELDS = {
    "segment_sequence", "start_sample_sha256", "end_sample_sha256",
    "source_segment_report_sha256", "minimum_clearance_lower_bound_mm",
    "limiting_body_pair",
}


class C03ObservedEntryClearanceSupplementV1Error(ValueError):
    """The sealed entry receipt lacks exact numeric clearance evidence."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry clearance evidence is not canonical JSON"
        ) from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _zero_authority(value: Mapping[str, Any]) -> None:
    if (
        value.get("controller_commands") != []
        or value.get("wire_commands") != []
        or value.get("hardware_commands_generated") != 0
        or value.get("hardware_access") is not False
        or value.get("hardware_writes") != 0
        or value.get("physical_movements") != 0
        or value.get("physical_authority") is not False
    ):
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry clearance supplement carries authority"
        )


def build_c03_observed_entry_clearance_supplement_v1(
    entry_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive a numeric entry margin only from a sealed clear ICQ-7 receipt."""

    try:
        entry = parse_c03_observed_route_entry_qualification_v1(entry_receipt)
    except ValueError as exc:
        raise C03ObservedEntryClearanceSupplementV1Error(
            f"observed entry receipt differs: {exc}"
        ) from exc
    if entry["status"] != CLEAR_STATUS:
        raise C03ObservedEntryClearanceSupplementV1Error(
            "numeric clearance requires a clear observed-entry receipt"
        )
    sweep = entry.get("continuous_sweep_qualification")
    reports = sweep.get("segment_reports") if isinstance(sweep, Mapping) else None
    plan = entry.get("sample_plan")
    if (
        not isinstance(plan, list)
        or not isinstance(reports, list)
        or entry.get("segment_count") != len(reports)
        or len(plan) != len(reports) + 1
        or not reports
    ):
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry segment clearance coverage differs"
        )

    rows: list[dict[str, Any]] = []
    for sequence, (start, end, report) in enumerate(
        zip(plan[:-1], plan[1:], reports, strict=True)
    ):
        value = report.get("minimum_clearance_lower_bound_mm") \
            if isinstance(report, Mapping) else None
        pair = report.get("limiting_body_pair") \
            if isinstance(report, Mapping) else None
        if (
            not isinstance(report, Mapping)
            or report.get("segment_sequence") != sequence
            or report.get("start_sample_sha256") != start.get("sample_sha256")
            or report.get("end_sample_sha256") != end.get("sample_sha256")
            or report.get("collision_free_diagnostic") is not True
            or report.get("collisions") != []
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
            or not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(item, str) or not item for item in pair)
        ):
            raise C03ObservedEntryClearanceSupplementV1Error(
                "entry segment numeric clearance differs"
            )
        rows.append({
            "segment_sequence": sequence,
            "start_sample_sha256": start["sample_sha256"],
            "end_sample_sha256": end["sample_sha256"],
            "source_segment_report_sha256": _sha(report),
            "minimum_clearance_lower_bound_mm": float(value),
            "limiting_body_pair": list(pair),
        })
    limiting = min(rows, key=lambda item: (
        item["minimum_clearance_lower_bound_mm"], item["limiting_body_pair"]
    ))
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "source_entry_qualification_sha256": entry[
            "c03_observed_route_entry_qualification_sha256"
        ],
        "entry_segment_count": len(rows),
        "segment_clearances": rows,
        "minimum_clearance_lower_bound_mm": limiting[
            "minimum_clearance_lower_bound_mm"
        ],
        "limiting_body_pair": limiting["limiting_body_pair"],
        "clearance_measurement": METHOD,
        "controller_commands": [],
        "wire_commands": [],
        "hardware_commands_generated": 0,
        "hardware_access": False,
        "hardware_writes": 0,
        "physical_movements": 0,
        "physical_authority": False,
    }
    return {
        **core,
        "c03_observed_entry_clearance_supplement_sha256": _sha(core),
    }


def parse_c03_observed_entry_clearance_supplement_v1(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry clearance supplement fields differ"
        )
    document = dict(value)
    claimed = document.pop(
        "c03_observed_entry_clearance_supplement_sha256", None
    )
    if (
        value.get("schema") != SCHEMA
        or value.get("status") != STATUS
        or claimed != _sha(document)
    ):
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry clearance supplement schema or hash differs"
        )
    _zero_authority(value)
    rows = value.get("segment_clearances")
    if (
        not isinstance(rows, list)
        or not rows
        or value.get("entry_segment_count") != len(rows)
    ):
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry clearance supplement segment accounting differs"
        )
    for sequence, row in enumerate(rows):
        clearance = row.get("minimum_clearance_lower_bound_mm") \
            if isinstance(row, Mapping) else None
        pair = row.get("limiting_body_pair") \
            if isinstance(row, Mapping) else None
        if (
            not isinstance(row, Mapping)
            or set(row) != _ROW_FIELDS
            or row.get("segment_sequence") != sequence
            or not _is_sha256(row.get("start_sample_sha256"))
            or not _is_sha256(row.get("end_sample_sha256"))
            or not _is_sha256(row.get("source_segment_report_sha256"))
            or isinstance(clearance, bool)
            or not isinstance(clearance, (int, float))
            or not math.isfinite(float(clearance))
            or float(clearance) < 0.0
            or not isinstance(pair, list)
            or len(pair) != 2
            or any(not isinstance(item, str) or not item for item in pair)
        ):
            raise C03ObservedEntryClearanceSupplementV1Error(
                "entry clearance supplement segment accounting differs"
            )
    limiting = min(rows, key=lambda item: (
        float(item["minimum_clearance_lower_bound_mm"]),
        item["limiting_body_pair"],
    ))
    if (
        value.get("clearance_measurement") != METHOD
        or not _is_sha256(value.get("source_entry_qualification_sha256"))
        or value.get("minimum_clearance_lower_bound_mm")
        != limiting["minimum_clearance_lower_bound_mm"]
        or value.get("limiting_body_pair") != limiting["limiting_body_pair"]
    ):
        raise C03ObservedEntryClearanceSupplementV1Error(
            "entry clearance supplement limiting evidence differs"
        )
    return dict(value)


__all__ = [
    "SCHEMA", "STATUS", "C03ObservedEntryClearanceSupplementV1Error",
    "build_c03_observed_entry_clearance_supplement_v1",
    "parse_c03_observed_entry_clearance_supplement_v1",
]
