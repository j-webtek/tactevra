from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.c03_aggregate_qualification_receipt_v1 import (
    PASS,
    C03AggregateQualificationReceiptV1Error,
    build_c03_aggregate_qualification_receipt_v1,
)
from rocell.application.c03_observed_entry_clearance_supplement_v1 import (
    C03ObservedEntryClearanceSupplementV1Error,
    build_c03_observed_entry_clearance_supplement_v1,
    parse_c03_observed_entry_clearance_supplement_v1,
)
from rocell.application.context import load_simulation_context

from test_c03_aggregate_qualification_receipt_v1 import _bundle
from test_c03_observed_route_entry_qualification_v1 import _qualify


WORKSPACE = Path(__file__).resolve().parents[3]
MANIFEST = WORKSPACE / "software/config/system_manifest.json"


@pytest.fixture(scope="module")
def context():
    return load_simulation_context(WORKSPACE, MANIFEST)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _rehash(value: dict[str, object]) -> None:
    unsigned = dict(value)
    unsigned.pop("c03_observed_entry_clearance_supplement_sha256")
    value["c03_observed_entry_clearance_supplement_sha256"] = hashlib.sha256(
        _canonical(unsigned)
    ).hexdigest()


def test_clear_entry_derives_exact_segment_clearance_and_zero_authority(
    context, monkeypatch
):
    entry = _qualify(context, monkeypatch)
    result = build_c03_observed_entry_clearance_supplement_v1(entry)
    assert parse_c03_observed_entry_clearance_supplement_v1(result) == result
    assert result["entry_segment_count"] == entry["segment_count"] == 2
    assert len(result["segment_clearances"]) == 2
    assert result["minimum_clearance_lower_bound_mm"] >= 0.0
    assert len(result["limiting_body_pair"]) == 2
    assert result["hardware_writes"] == result["physical_movements"] == 0
    assert result["physical_authority"] is False


def test_exact_clear_chain_with_numeric_entry_margin_can_pass(
    context, monkeypatch
):
    bundle = _bundle(context, monkeypatch)
    supplement = build_c03_observed_entry_clearance_supplement_v1(bundle[0])
    result = build_c03_aggregate_qualification_receipt_v1(
        *bundle, entry_clearance_supplement=supplement
    )
    assert result["disposition"] == PASS
    assert result["clearance_summary"]["entry_numeric_clearance_available"] is True
    assert result["clearance_summary"][
        "entry_clearance_supplement_sha256"
    ] == supplement["c03_observed_entry_clearance_supplement_sha256"]
    assert "ICQ7_V1_CLEAR_ENTRY_HAS_NO_NUMERIC_CLEARANCE_MARGIN" not in result[
        "limitations"
    ]
    assert result["eligible_for_executor"] is False
    assert result["physical_authority"] is False


def test_changed_or_crossed_supplement_fails_closed(context, monkeypatch):
    bundle = _bundle(context, monkeypatch)
    supplement = build_c03_observed_entry_clearance_supplement_v1(bundle[0])

    changed = copy.deepcopy(supplement)
    changed["minimum_clearance_lower_bound_mm"] += 1.0
    with pytest.raises(
        C03AggregateQualificationReceiptV1Error, match="supplement differs"
    ):
        build_c03_aggregate_qualification_receipt_v1(
            *bundle, entry_clearance_supplement=changed
        )

    changed["c03_observed_entry_clearance_supplement_sha256"] = supplement[
        "c03_observed_entry_clearance_supplement_sha256"
    ]
    _rehash(changed)
    with pytest.raises(
        C03AggregateQualificationReceiptV1Error, match="supplement differs"
    ):
        build_c03_aggregate_qualification_receipt_v1(
            *bundle, entry_clearance_supplement=changed
        )

    crossed = copy.deepcopy(supplement)
    crossed["source_entry_qualification_sha256"] = "f" * 64
    _rehash(crossed)
    with pytest.raises(
        C03AggregateQualificationReceiptV1Error, match="lineage differs"
    ):
        build_c03_aggregate_qualification_receipt_v1(
            *bundle, entry_clearance_supplement=crossed
        )


def test_missing_or_reordered_entry_segments_fail_closed(context, monkeypatch):
    entry = _qualify(context, monkeypatch)
    supplement = build_c03_observed_entry_clearance_supplement_v1(entry)

    reordered = copy.deepcopy(supplement)
    reordered["segment_clearances"].reverse()
    _rehash(reordered)
    with pytest.raises(
        C03ObservedEntryClearanceSupplementV1Error,
        match="segment accounting differs",
    ):
        parse_c03_observed_entry_clearance_supplement_v1(reordered)

    missing = copy.deepcopy(supplement)
    missing["segment_clearances"].pop()
    missing["entry_segment_count"] -= 1
    _rehash(missing)
    with pytest.raises(
        C03AggregateQualificationReceiptV1Error, match="lineage differs"
    ):
        build_c03_aggregate_qualification_receipt_v1(
            *_bundle(context, monkeypatch), entry_clearance_supplement=missing
        )
