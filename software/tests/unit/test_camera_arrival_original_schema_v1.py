from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((
    ROOT / "software/ai/schemas/camera_arrival_original_v1.schema.json"
).read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
H = "a" * 64


def _original() -> dict[str, object]:
    return {
        "schema": "rocell.camera_arrival_original.v1",
        "artifact_id": "camera_to_board_transform",
        "artifact_class": "CALIBRATION_ORIGINAL",
        "captured_at_utc": "2026-09-28T12:00:00Z",
        "source_relative_path": "calibration/camera-to-board-result.json",
        "source_size_bytes": 1024,
        "source_sha256": H,
        "units": ["mm", "rad"],
        "uncertainty": {
            "value": 0.5,
            "unit": "mm",
            "method": "held-out fiducial residual bound",
            "evidence_sha256": H,
        },
        "configuration_epoch_id": "physical-camera-epoch-001",
        "review": {
            "reviewer_id": "owner-ai-review",
            "reviewed_at_utc": "2026-09-28T13:00:00Z",
            "disposition": "ACCEPTED",
            "review_sha256": H,
        },
    }


def test_physical_original_sidecar_schema_accepts_bound_measurement():
    assert list(VALIDATOR.iter_errors(_original())) == []


@pytest.mark.parametrize(("path", "value"), (
    (("source_relative_path",), "../escape.json"),
    (("source_sha256",), "A" * 64),
    (("source_size_bytes",), 0),
    (("review", "disposition"), "PENDING"),
    (("uncertainty",), None),
))
def test_physical_original_sidecar_schema_rejects_unbound_or_unsafe_values(
    path: tuple[str, ...], value: object,
):
    document = deepcopy(_original())
    target = document
    for key in path[:-1]:
        target = target[key]  # type: ignore[index,assignment]
    target[path[-1]] = value  # type: ignore[index]
    assert list(VALIDATOR.iter_errors(document))
