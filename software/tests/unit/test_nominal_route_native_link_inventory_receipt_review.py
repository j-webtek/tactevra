from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
INTEGRATION = ROOT / "software" / "integrations" / "isaac_sim"
if str(INTEGRATION) not in sys.path:
    sys.path.insert(0, str(INTEGRATION))


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, INTEGRATION / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DIAGNOSTIC = load(
    "native_link_inventory_diagnostic_for_receipt_review",
    "nominal_route_native_link_inventory_diagnostic.py",
)
ARM293 = load(
    "native_link_inventory_review_for_receipt_review",
    "nominal_route_native_link_inventory_review.py",
)
RECEIPT_REVIEW = load(
    "native_link_inventory_receipt_review",
    "nominal_route_native_link_inventory_receipt_review.py",
)


class Articulation:
    link_names = list(DIAGNOSTIC.EXPECTED_LINK_NAMES)

    def get_link_transforms(self):
        return [[[0.0] * 7 for _ in self.link_names]]


class Session:
    physics_steps = 0

    def start_headless(self):
        pass

    def load_scene(self):
        pass

    def initialize_physics(self):
        pass

    def native_objects(self):
        return {
            "articulation": Articulation(),
            "scene_query": object(),
            "key_view": object(),
            "root_view": object(),
        }

    def shutdown(self):
        pass


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def evidence(tmp_path: Path):
    output = tmp_path / "arm294-native-link-inventory-diagnostic-001"
    future = tmp_path / "arm295-nominal-route-physics-attempt-001"
    diagnostic_source = (
        INTEGRATION / "nominal_route_native_link_inventory_diagnostic.py"
    )
    request = DIAGNOSTIC.build_request(
        diagnostic_source_sha256=DIAGNOSTIC._file_sha(diagnostic_source),
        session_source_sha256="b" * 64,
        proposed_output_directory=output,
    )
    request_path = tmp_path / "arm292" / "request.json"
    _write(request_path, request)
    request_file_sha = DIAGNOSTIC._file_sha(request_path)
    arm293_review = ARM293.review_request(
        request,
        request_file_sha256=request_file_sha,
        diagnostic_source=diagnostic_source,
        review_source_sha256="d" * 64,
    )
    arm293_path = tmp_path / "arm293" / "review.json"
    _write(arm293_path, arm293_review)
    receipt = DIAGNOSTIC.run_diagnostic(
        Session(),
        request,
        arm293_review,
        authorization_statement=DIAGNOSTIC.EXACT_AUTHORIZATION,
        output_directory=output,
        governed_attempt_directory=future,
        current_source_files_sha256=dict(request["source_files_sha256"]),
    )
    receipt_path = output / "receipt.json"
    return {
        "request": request,
        "request_path": request_path,
        "arm293_review": arm293_review,
        "arm293_path": arm293_path,
        "receipt": receipt,
        "receipt_path": receipt_path,
        "future": future,
    }


def review(data):
    return RECEIPT_REVIEW.review_receipt(
        data["receipt"],
        data["request"],
        data["arm293_review"],
        receipt_file_sha256=RECEIPT_REVIEW._file_sha(data["receipt_path"]),
        request_file_sha256=RECEIPT_REVIEW._file_sha(data["request_path"]),
        arm293_review_file_sha256=RECEIPT_REVIEW._file_sha(data["arm293_path"]),
        receipt_path=data["receipt_path"],
        governed_attempt_directory=data["future"],
        reviewer_source_sha256="e" * 64,
    )


def test_accepts_exact_retained_zero_motion_receipt(tmp_path):
    result = review(evidence(tmp_path))
    assert result["status"] == "ACCEPTED_NATIVE_LINK_INVENTORY_ZERO_MOTION_EVIDENCE"
    assert result["verified_link_names"] == list(DIAGNOSTIC.EXPECTED_LINK_NAMES)
    assert result["source_physics_steps"] == 0
    assert result["route_attempt_admitted"] is False
    assert result["isaac_started"] is False
    assert result["next_required_stage"].startswith("REBUILD_NEWLY_NUMBERED")
    assert RECEIPT_REVIEW._require_hash(
        result, "receipt_review_sha256", "receipt review"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "FAIL_NATIVE_LINK_INVENTORY_ZERO_MOTION_NO_RETRY", "boundary"),
        ("link_names", ["base_link"], "boundary"),
        ("transform_count", 6, "boundary"),
        ("physics_steps", 1, "boundary"),
        ("joint_targets_submitted", True, "boundary"),
        ("unexpected_motion_authority", True, "boundary"),
    ],
)
def test_rejects_failed_or_drifted_receipt(tmp_path, field, value, message):
    data = evidence(tmp_path)
    data["receipt"][field] = value
    _write(data["receipt_path"], data["receipt"])
    with pytest.raises(
        RECEIPT_REVIEW.NativeLinkInventoryReceiptReviewError, match=message
    ):
        review(data)


def test_rejects_receipt_file_hash_mismatch(tmp_path):
    data = evidence(tmp_path)
    with pytest.raises(
        RECEIPT_REVIEW.NativeLinkInventoryReceiptReviewError,
        match="receipt file hash",
    ):
        RECEIPT_REVIEW.review_receipt(
            data["receipt"],
            data["request"],
            data["arm293_review"],
            receipt_file_sha256="f" * 64,
            request_file_sha256=RECEIPT_REVIEW._file_sha(data["request_path"]),
            arm293_review_file_sha256=RECEIPT_REVIEW._file_sha(data["arm293_path"]),
            receipt_path=data["receipt_path"],
            governed_attempt_directory=data["future"],
            reviewer_source_sha256="e" * 64,
        )


def test_rejects_existing_governed_attempt_directory(tmp_path):
    data = evidence(tmp_path)
    data["future"].mkdir()
    with pytest.raises(
        RECEIPT_REVIEW.NativeLinkInventoryReceiptReviewError,
        match="already exists",
    ):
        review(data)


def test_reviewer_has_no_isaac_or_transport_import(tmp_path):
    source = (
        INTEGRATION / "nominal_route_native_link_inventory_receipt_review.py"
    ).read_text(encoding="utf-8")
    import_lines = [line.strip() for line in source.splitlines() if "import " in line]
    assert all("isaac" not in line.lower() for line in import_lines)
    assert all("serial" not in line.lower() for line in import_lines)
    assert all("socket" not in line.lower() for line in import_lines)
    assert not (tmp_path / "arm295-nominal-route-physics-attempt-001").exists()
