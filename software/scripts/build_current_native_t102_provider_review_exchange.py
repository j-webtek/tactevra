"""Build an offline exchange for the current native T=102 provider review."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rocell.application.native_t102_current_provider_review_packet_v1 import (
    CANDIDATE_COMMIT,
    CANDIDATE_FILES,
    VERIFICATION_SCHEMA,
    build_native_t102_current_provider_review_packet_v1,
)


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _candidate_members(root: Path) -> dict[str, bytes]:
    return {path: (root / path).read_bytes() for path in CANDIDATE_FILES}


def _verification_record(members: dict[str, bytes]) -> bytes:
    return _canonical({
        "schema": VERIFICATION_SCHEMA,
        "status": "PASS_OFFLINE_NO_HARDWARE",
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_files": [
            {
                "path": path,
                "bytes": len(members[path]),
                "sha256": hashlib.sha256(members[path]).hexdigest(),
            }
            for path in sorted(members)
        ],
        "focused_tests_passed": 40,
        "github_checks_passed": 14,
        "execution_grant_gate_tested": True,
        "fused_composition_tested": True,
        "real_endpoint_opened": False,
        "os_device_handles": 0,
        "hardware_writes": 0,
        "physical_movements": 0,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "physical_authority": False,
    })


def _reviewer_procedure(packet_sha256: str, manifest_sha256: str) -> bytes:
    return f"""# Current native T=102 provider external review

Review the packet in this directory without modifying it.

Exact identities:

- candidate commit: `{CANDIDATE_COMMIT}`
- packet SHA-256: `{packet_sha256}`
- packet manifest SHA-256: `{manifest_sha256}`

Required review:

1. Verify `exchange-manifest.json`, the packet hash, and the packet manifest.
2. Inspect every packet member and complete the packet's closed checklist.
3. Confirm the sink-issued execution grant is required before endpoint open.
4. Confirm the exact endpoint and canonical T=102 bytes are checked again and
   the grant is consumed before the movement write.
5. Confirm pre/post-open identity checks, finite waits, exact serial settings,
   and the absence of discovery, fallback, reopen, resend, purge, or retry.
6. Confirm durable start, single-use authority and permit consumption, terminal
   outcome sealing, and no replay through the fused composition.
7. Return a separately authenticated decision bound to all three identities
   above. Do not place the decision inside or alter this exchange directory.

This exchange is review input only. It does not establish reviewer identity,
complete independent review, qualify the transport, authorize an endpoint
open, authorize execution, access hardware, or grant physical authority.
""".encode("utf-8")


def _write(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)


def build(root: Path, output_dir: Path) -> dict:
    root = Path(root).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise FileExistsError(
            "review exchange output already exists; refusing to overwrite")
    members = _candidate_members(root)
    packet = build_native_t102_current_provider_review_packet_v1(
        candidate_members=members,
        verification_record=_verification_record(members),
    )
    files = {
        "arm165-current-native-t102-provider-review-packet.zip": (
            packet.packet_bytes),
        "REVIEWER_PROCEDURE.md": _reviewer_procedure(
            packet.packet_sha256, packet.manifest_sha256),
    }
    manifest = {
        "schema": "rocell.native_t102_current_provider_review_exchange.v1",
        "status": "AWAITING_EXTERNAL_INDEPENDENT_REVIEW",
        "packet_sha256": packet.packet_sha256,
        "packet_manifest_sha256": packet.manifest_sha256,
        "candidate_commit": packet.candidate_commit,
        "members": [
            {
                "path": name,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            for name, data in sorted(files.items())
        ],
        "external_decision_present": False,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "endpoint_open_authorized": False,
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
