"""Isolated one-query position-vector child; import audit is hardware-incapable."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys


def main() -> int:
    if not sys.flags.isolated or not sys.flags.no_site or len(sys.argv) != 4:
        return 2
    archive = Path(sys.argv[1])
    if not archive.is_absolute() or archive.name != "calibrated-position-vector-native.zip":
        return 3
    if sys.argv[3] not in {"check-imports", "execute-one"}:
        return 5
    raw = archive.read_bytes()
    if len(raw) > 8 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != sys.argv[2]:
        return 4
    if sys.argv[3] == "check-imports":
        import ctypes
        import subprocess

        def forbidden(*args, **kwargs):
            raise RuntimeError("POSITION_VECTOR_IMPORT_AUDIT_HOST_ACCESS_FORBIDDEN")

        ctypes.WinDLL = forbidden
        subprocess.Popen = forbidden
        os.open = forbidden
    sys.path.insert(0, str(archive))
    from rocell.providers.windows.calibrated_position_vector_owned_protocol import (
        canonical,
        decode_request,
        encode_result,
        validate_payload,
    )
    from rocell.providers.windows.calibrated_position_vector_native_composition import (
        execute_owned_calibrated_position_vector_exchange,
        export_position_vector_serial_attempt,
    )
    from rocell.providers.windows.calibrated_position_vector_serial_adapter import (
        PositionVectorSerialAdapterError,
        load_position_vector_serial_attempt,
    )

    if sys.argv[3] == "check-imports":
        result = canonical({
            "schema": "rocell.calibrated_position_vector_import_check.v1",
            "status": "IMPORTS_OK_NOT_HARDWARE_TESTED",
            "physical_authority": False,
            "motion_authorized": False,
            "automatic_retry_allowed": False,
            "connected": False,
        })
    else:
        wire = decode_request(sys.stdin.buffer.read(65_537))
        payload, binding = validate_payload(wire["payload"])
        working = Path.cwd().resolve()
        expected = Path(payload["root"]).resolve() / (
            binding.request["attempt_id"] + "-position-vector-child"
        )
        if working != expected:
            raise ValueError("child working directory changed")
        status = "SUCCEEDED"
        error = None
        try:
            evidence = execute_owned_calibrated_position_vector_exchange(
                binding,
                journal_root=working / "journals",
                current_runtime_sha256=binding.runtime_sha256,
                owned_process_id=os.getpid(),
            )
            attempt = working / "journals" / (
                "position-vector-feedback-" + binding.request["attempt_id"]
            )
        except PositionVectorSerialAdapterError as failure:
            status = "FAILED_NO_RETRY"
            error = failure.code
            evidence = None
            attempt = failure.journal_directory
        retained = load_position_vector_serial_attempt(attempt)
        if retained["result"] is None:
            raise ValueError("terminal journal result required")
        exported = export_position_vector_serial_attempt(
            attempt, export_root=working / "exports"
        )
        child = {
            "schema": "rocell.calibrated_position_vector_native_child_result.v1",
            "status": status,
            "error": error,
            "binding_sha256": binding.binding_sha256,
            "exchange_evidence": evidence,
            "journal_export": exported,
            "physical_authority": False,
            "motion_authorized": False,
            "automatic_retry_allowed": False,
            "connected": False,
        }
        result = encode_result(child, wire=wire)
    sys.stdout.buffer.write(result)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
