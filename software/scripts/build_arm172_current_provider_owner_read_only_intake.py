"""Build ARM-172 from retained records only; performs no hardware I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application.native_t102_current_provider_owner_ai_review_acceptance_v1 import (
    NativeT102CurrentProviderOwnerAIReviewAcceptanceError,
    parse_current_provider_owner_ai_review_acceptance_v1,
)
from rocell.application.native_t102_current_provider_owner_read_only_intake_v1 import (
    NativeT102CurrentProviderOwnerReadOnlyIntakeError,
    build_native_t102_current_provider_owner_read_only_intake_v1,
)
from rocell.application.native_t102_production_transport_v1 import (
    PinnedNativeT102EndpointV1,
)


MAX_INPUT_BYTES = 256 * 1024
EXPECTED_ACCEPTANCE_SHA256 = (
    "29bf06b863b3f9a5124a25c57e7aac5ffd4ed1ef41f4cf0b17bb28a9971a0b0a")


def _strict_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.resolve(strict=True).is_file():
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "input must be one regular non-symlink file")
    raw = path.read_bytes()
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "input size is invalid")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
                    f"input contains duplicate field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                NativeT102CurrentProviderOwnerReadOnlyIntakeError(
                    f"input contains {item}")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "input is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "input root must be a JSON object")
    return value


def _checkpoint(document: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if document.get("schema") != "rocell.issue190_operational_checkpoint.v1":
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "checkpoint schema differs")
    expected = document.get("checkpoint_sha256")
    unsigned = {key: value for key, value in document.items()
                if key != "checkpoint_sha256"}
    actual = hashlib.sha256(json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    if expected != actual:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "checkpoint hash differs")
    metadata = document.get("controller_metadata")
    if type(metadata) is not dict:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "checkpoint controller metadata is missing")
    required = {
        "port_name", "vid", "pid", "unit_serial", "persistent_instance_id",
        "session_id", "source_sha256", "log_head_sha256", "device_open_count",
        "serial_write_count", "motion_command_count",
    }
    if not required.issubset(metadata):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "checkpoint controller metadata is incomplete")
    if any(type(metadata[name]) is not int or metadata[name] != 0 for name in (
        "device_open_count", "serial_write_count", "motion_command_count"
    )):
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "checkpoint is not a zero-I/O identity observation")
    expected_instance = (
        f"USB\\VID_{str(metadata['vid']).upper()}&PID_{str(metadata['pid']).upper()}\\"
        f"{str(metadata['unit_serial']).lower()}"
    )
    if str(metadata["persistent_instance_id"]).lower() != expected_instance.lower():
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "checkpoint persistent identity differs")
    return actual, metadata


def build(acceptance_path: Path, checkpoint_path: Path, output: Path) -> dict:
    """Create the exact retained proposal without opening or enumerating a port."""

    try:
        acceptance = parse_current_provider_owner_ai_review_acceptance_v1(
            _strict_json(Path(acceptance_path)))
    except NativeT102CurrentProviderOwnerAIReviewAcceptanceError as exc:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "owner acceptance is invalid") from exc
    if acceptance.acceptance_sha256 != EXPECTED_ACCEPTANCE_SHA256:
        raise NativeT102CurrentProviderOwnerReadOnlyIntakeError(
            "owner acceptance is not the exact ARM-171 acceptance")
    checkpoint_sha256, metadata = _checkpoint(_strict_json(Path(checkpoint_path)))
    endpoint = PinnedNativeT102EndpointV1(
        port_name=metadata["port_name"],
        usb_vid=metadata["vid"].upper(),
        usb_pid=metadata["pid"].upper(),
        usb_serial_number=metadata["unit_serial"],
    )
    intake = build_native_t102_current_provider_owner_read_only_intake_v1(
        acceptance,
        endpoint,
        intake_id="arm-172-current-provider-owner-read-only-intake",
        host_id=(
            "windows-host-sha256-"
            "e56132c821d6f85ebf7eb4b49584d5547d92765f96bfd7deb29796b3a1056e0b"
        ),
        created_utc="2026-10-31T22:20:00Z",
        operational_checkpoint_sha256=checkpoint_sha256,
        controller_metadata_session_id=metadata["session_id"],
        controller_metadata_source_sha256=metadata["source_sha256"],
        controller_metadata_log_head_sha256=metadata["log_head_sha256"],
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(intake.to_dict(), indent=2) + "\n")
    return intake.to_dict()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("acceptance", type=Path)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.acceptance, args.checkpoint, args.output), indent=2))
