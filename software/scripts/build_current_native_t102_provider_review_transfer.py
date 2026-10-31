"""Build or verify the deterministic ARM-166 review-transfer archive."""

from __future__ import annotations

from io import BytesIO
import hashlib
import json
from pathlib import Path
import zipfile

from verify_current_native_t102_provider_review_exchange import (
    MEMBERS,
    CurrentNativeT102ProviderReviewExchangeError,
    _read_closed_directory,
    verify_payloads,
)


PREFIX = "arm166-current-provider-review-exchange/"
ARCHIVE_MEMBERS = tuple(PREFIX + name for name in MEMBERS)
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024
EXPECTED_TRANSFER_SHA256 = (
    "be2b4aa1c30ea94d84f84b05fbf90aed6639c6507e8a25dbd1e597bbd49b397d"
)


class CurrentNativeT102ProviderReviewTransferError(ValueError):
    """The outer transfer archive is unsafe, incomplete, or changed."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _entry(name: str) -> zipfile.ZipInfo:
    entry = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    entry.compress_type = zipfile.ZIP_STORED
    entry.create_system = 3
    entry.external_attr = 0o100644 << 16
    entry.flag_bits = 0
    return entry


def _archive_bytes(payloads: dict[str, bytes]) -> bytes:
    stream = BytesIO()
    with zipfile.ZipFile(stream, "w", allowZip64=False) as archive:
        for name in MEMBERS:
            archive.writestr(_entry(PREFIX + name), payloads[name])
    return stream.getvalue()


def build(exchange_dir: Path, output_zip: Path) -> dict[str, object]:
    """Verify one exchange and create its deterministic outer transfer ZIP."""

    exchange_dir = Path(exchange_dir)
    output_zip = Path(output_zip)
    if output_zip.exists() or output_zip.is_symlink():
        raise FileExistsError(
            "review transfer output already exists; refusing to overwrite")
    payloads = _read_closed_directory(exchange_dir)
    exchange = verify_payloads(payloads)
    archive_bytes = _archive_bytes(payloads)
    transfer_sha256 = _sha(archive_bytes)
    if transfer_sha256 != EXPECTED_TRANSFER_SHA256:
        raise CurrentNativeT102ProviderReviewTransferError(
            "built review transfer identity differs")
    with output_zip.open("xb") as stream:
        stream.write(archive_bytes)
    return {
        "schema": "rocell.native_t102_current_provider_review_transfer.v1",
        "status": "AWAITING_EXTERNAL_INDEPENDENT_REVIEW",
        "transfer_sha256": transfer_sha256,
        "transfer_bytes": len(archive_bytes),
        "exchange_manifest_sha256": exchange["exchange_manifest_sha256"],
        "external_decision_present": False,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "endpoint_open_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
        "output_zip": str(output_zip.resolve()),
    }


def verify_transfer(transfer_zip: Path) -> dict[str, object]:
    """Verify the exact outer ZIP and its nested exchange without extraction."""

    transfer_zip = Path(transfer_zip)
    if transfer_zip.is_symlink():
        raise CurrentNativeT102ProviderReviewTransferError(
            "review transfer must be one regular non-symlink file")
    transfer_zip = transfer_zip.resolve(strict=True)
    if not transfer_zip.is_file():
        raise CurrentNativeT102ProviderReviewTransferError(
            "review transfer must be one regular non-symlink file")
    archive_bytes = transfer_zip.read_bytes()
    if not archive_bytes or len(archive_bytes) > MAX_ARCHIVE_BYTES:
        raise CurrentNativeT102ProviderReviewTransferError(
            "review transfer size is invalid")
    transfer_sha256 = _sha(archive_bytes)
    if transfer_sha256 != EXPECTED_TRANSFER_SHA256:
        raise CurrentNativeT102ProviderReviewTransferError(
            "review transfer identity differs")
    try:
        with zipfile.ZipFile(BytesIO(archive_bytes)) as archive:
            entries = archive.infolist()
            if tuple(entry.filename for entry in entries) != ARCHIVE_MEMBERS:
                raise CurrentNativeT102ProviderReviewTransferError(
                    "review transfer membership or order differs")
            if archive.comment or archive.testzip() is not None:
                raise CurrentNativeT102ProviderReviewTransferError(
                    "review transfer integrity differs")
            for entry in entries:
                if (
                    entry.date_time != FIXED_TIMESTAMP
                    or entry.compress_type != zipfile.ZIP_STORED
                    or entry.create_system != 3
                    or entry.external_attr != 0o100644 << 16
                    or entry.flag_bits & 0x1
                    or entry.is_dir()
                ):
                    raise CurrentNativeT102ProviderReviewTransferError(
                        "review transfer metadata differs")
            payloads = {
                entry.filename.removeprefix(PREFIX): archive.read(entry)
                for entry in entries
            }
    except (OSError, zipfile.BadZipFile) as exc:
        raise CurrentNativeT102ProviderReviewTransferError(
            "review transfer is not one valid closed ZIP") from exc
    try:
        exchange = verify_payloads(payloads)
    except CurrentNativeT102ProviderReviewExchangeError as exc:
        raise CurrentNativeT102ProviderReviewTransferError(
            "nested review exchange is invalid") from exc
    return {
        "schema": "rocell.native_t102_current_provider_review_transfer_verification.v1",
        "status": "PASS_UNCHANGED_REVIEW_TRANSFER",
        "transfer_sha256": transfer_sha256,
        "transfer_bytes": len(archive_bytes),
        "exchange_manifest_sha256": exchange["exchange_manifest_sha256"],
        "packet_sha256": exchange["packet_sha256"],
        "packet_manifest_sha256": exchange["packet_manifest_sha256"],
        "candidate_commit": exchange["candidate_commit"],
        "external_decision_present": False,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "endpoint_open_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("exchange_dir", type=Path)
    build_parser.add_argument("output_zip", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("transfer_zip", type=Path)
    args = parser.parse_args()
    result = (
        build(args.exchange_dir, args.output_zip)
        if args.command == "build"
        else verify_transfer(args.transfer_zip)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
