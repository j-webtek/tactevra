"""Build an offline exchange directory for an external ARM-054 review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.native_t102_adapter_review_packet_v1 import (
    build_native_t102_adapter_review_packet_v1,
)


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def build(root: Path, output_dir: Path) -> dict:
    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(
            "review exchange output already exists; refusing to overwrite")
    members = {
        "source/native_t102_serial_transport_v1.py": (
            root / "software/native/review/arm054-candidate/source/"
            "native_t102_serial_transport_v1.py").read_bytes(),
        "tests/test_windows_native_t102_serial_transport_v1.py": (
            root / "software/native/review/arm054-candidate/tests/"
            "test_windows_native_t102_serial_transport_v1.py").read_bytes(),
        "docs/WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md": (
            root / "software/native/review/arm054-candidate/docs/"
            "WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md"
        ).read_bytes(),
    }
    packet = build_native_t102_adapter_review_packet_v1(
        candidate_members=members,
        verification_record=(
            root / "software/native/review/arm054-offline-verification.json"
        ).read_bytes(),
    )
    files = {
        "arm054-adapter-review-packet.zip": packet.packet_bytes,
        "native_t102_adapter_review_decision_v1.schema.json": (
            root / "software/ai/schemas/"
            "native_t102_adapter_review_decision_v1.schema.json"
        ).read_bytes(),
        "native_t102_adapter_review_decision_report_v1.schema.json": (
            root / "software/ai/schemas/"
            "native_t102_adapter_review_decision_report_v1.schema.json"
        ).read_bytes(),
        "REVIEWER_PROCEDURE.md": (
            root / "software/docs/NATIVE_T102_ADAPTER_REVIEW_DECISION.md"
        ).read_bytes(),
    }
    manifest = {
        "schema": "rocell.native_t102_adapter_review_exchange.v1",
        "status": "AWAITING_EXTERNAL_INDEPENDENT_REVIEW",
        "packet_sha256": packet.packet_sha256,
        "packet_manifest_sha256": packet.manifest_sha256,
        "candidate_commit": packet.candidate_commit,
        "members": [
            {"path": name, "bytes": len(data),
             "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in sorted(files.items())
        ],
        "external_decision_present": False,
        "independent_review_complete": False,
        "endpoint_open_authorized": False,
        "controller_start_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    files["exchange-manifest.json"] = _canonical(manifest)
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, data in sorted(files.items()):
        _write(output_dir / name, data)
    return {
        **manifest,
        "exchange_manifest_sha256": hashlib.sha256(
            files["exchange-manifest.json"]).hexdigest(),
        "output_dir": str(output_dir),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(
        Path(__file__).resolve().parents[2], args.output_dir,
    ), indent=2, sort_keys=True))
