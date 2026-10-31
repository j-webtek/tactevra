"""Verify one ARM-166 current-provider review exchange without extracting it."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application.native_t102_current_provider_review_decision_v1 import (
    CANDIDATE_COMMIT,
    MANIFEST_SHA256,
    PACKET_SHA256,
)
from rocell.application.native_t102_current_provider_review_packet_v1 import (
    NativeT102CurrentProviderReviewPacketError,
    inspect_native_t102_current_provider_review_packet_v1,
)


SCHEMA = "rocell.native_t102_current_provider_review_exchange.v1"
STATUS = "AWAITING_EXTERNAL_INDEPENDENT_REVIEW"
EXPECTED_EXCHANGE_MANIFEST_SHA256 = (
    "146dc2135cdb97c8bb04602f09a0de9f8d24a96551c52e64ca9fd20cceafdb54"
)
PACKET_NAME = "arm165-current-native-t102-provider-review-packet.zip"
PROCEDURE_NAME = "REVIEWER_PROCEDURE.md"
MANIFEST_NAME = "exchange-manifest.json"
MEMBERS = (PROCEDURE_NAME, PACKET_NAME, MANIFEST_NAME)
MAX_MEMBER_BYTES = 1024 * 1024


class CurrentNativeT102ProviderReviewExchangeError(ValueError):
    """The transferred review exchange is incomplete or has changed."""


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _strict_json(payload: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise CurrentNativeT102ProviderReviewExchangeError(
                    f"exchange manifest repeats {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                CurrentNativeT102ProviderReviewExchangeError(
                    f"exchange manifest contains {item}")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange manifest is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange manifest root must be a JSON object")
    return value


def _canonical(value: object) -> bytes:
    return (json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode("utf-8")


def _read_closed_directory(exchange_dir: Path) -> dict[str, bytes]:
    exchange_dir = Path(exchange_dir)
    if exchange_dir.is_symlink():
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange directory must be one non-symlink directory")
    exchange_dir = exchange_dir.resolve(strict=True)
    if not exchange_dir.is_dir():
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange path must be one non-symlink directory")
    children = tuple(exchange_dir.iterdir())
    if {item.name for item in children} != set(MEMBERS):
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange directory membership differs")
    payloads: dict[str, bytes] = {}
    for path in children:
        if path.is_symlink() or not path.is_file():
            raise CurrentNativeT102ProviderReviewExchangeError(
                "exchange members must be regular non-symlink files")
        payload = path.read_bytes()
        if not payload or len(payload) > MAX_MEMBER_BYTES:
            raise CurrentNativeT102ProviderReviewExchangeError(
                f"exchange member size is invalid: {path.name}")
        payloads[path.name] = payload
    return payloads


def verify(exchange_dir: Path) -> dict[str, Any]:
    """Verify the closed exchange and packet without extracting or executing."""

    payloads = _read_closed_directory(exchange_dir)
    manifest_bytes = payloads[MANIFEST_NAME]
    manifest = _strict_json(manifest_bytes)
    if manifest_bytes != _canonical(manifest):
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange manifest must use canonical JSON bytes")
    if _sha(manifest_bytes) != EXPECTED_EXCHANGE_MANIFEST_SHA256:
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange manifest identity differs")
    expected_members = [
        {
            "path": name,
            "bytes": len(payloads[name]),
            "sha256": _sha(payloads[name]),
        }
        for name in sorted((PROCEDURE_NAME, PACKET_NAME))
    ]
    expected_manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "packet_sha256": PACKET_SHA256,
        "packet_manifest_sha256": MANIFEST_SHA256,
        "candidate_commit": CANDIDATE_COMMIT,
        "members": expected_members,
        "external_decision_present": False,
        "independent_review_complete": False,
        "transport_implementation_qualified": False,
        "endpoint_open_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    if manifest != expected_manifest:
        raise CurrentNativeT102ProviderReviewExchangeError(
            "exchange member identity or review-only manifest differs")
    try:
        packet = inspect_native_t102_current_provider_review_packet_v1(
            payloads[PACKET_NAME])
    except NativeT102CurrentProviderReviewPacketError as exc:
        raise CurrentNativeT102ProviderReviewExchangeError(
            "embedded current-provider review packet is invalid") from exc
    if (
        packet.packet_sha256 != PACKET_SHA256
        or packet.manifest_sha256 != MANIFEST_SHA256
        or packet.candidate_commit != CANDIDATE_COMMIT
    ):
        raise CurrentNativeT102ProviderReviewExchangeError(
            "embedded current-provider review packet identity differs")
    return {
        "schema": "rocell.native_t102_current_provider_review_exchange_verification.v1",
        "status": "PASS_UNCHANGED_REVIEW_INPUT",
        "exchange_manifest_sha256": _sha(manifest_bytes),
        "packet_sha256": packet.packet_sha256,
        "packet_manifest_sha256": packet.manifest_sha256,
        "candidate_commit": packet.candidate_commit,
        "packet_member_count": packet.member_count,
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
    parser.add_argument("exchange_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.exchange_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
