"""Build the deterministic, review-only ARM-054 adapter handoff archive."""

from __future__ import annotations

import json
from pathlib import Path

from rocell.application.native_t102_adapter_review_packet_v1 import (
    build_native_t102_adapter_review_packet_v1,
)


def build(root: Path, output: Path | None = None) -> dict:
    root = Path(root).resolve()
    result = build_native_t102_adapter_review_packet_v1(
        candidate_members={
            "source/native_t102_serial_transport_v1.py": (
                root / "software/native/review/arm054-candidate/source/"
                "native_t102_serial_transport_v1.py"
            ).read_bytes(),
            "tests/test_windows_native_t102_serial_transport_v1.py": (
                root / "software/native/review/arm054-candidate/tests/"
                "test_windows_native_t102_serial_transport_v1.py"
            ).read_bytes(),
            "docs/WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md": (
                root / "software/native/review/arm054-candidate/docs/"
                "WINDOWS_NATIVE_T102_SERIAL_ADAPTER.md"
            ).read_bytes(),
        },
        verification_record=(
            root / "software/native/review/arm054-offline-verification.json"
        ).read_bytes(),
    )
    destination = (
        root / "software/runs/review-packets" /
        f"arm054-adapter-{result.packet_sha256}.zip"
        if output is None else Path(output).resolve()
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() != result.packet_bytes:
        raise ValueError(
            "existing ARM-054 review packet differs; refusing to overwrite")
    if not destination.exists():
        with destination.open("xb") as stream:
            stream.write(result.packet_bytes)
    return {
        **result.to_dict(),
        "path": str(destination.relative_to(root)),
        "serial_endpoint_opened": False,
        "controller_started": False,
        "movement_command_sent": False,
    }


if __name__ == "__main__":
    print(json.dumps(build(Path(__file__).resolve().parents[2]), indent=2))
