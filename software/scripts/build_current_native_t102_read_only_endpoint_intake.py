"""Build one zero-I/O read-only intake for the reviewed current T=102 provider."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rocell.application.native_t102_current_provider_review_decision_v1 import (
    NativeT102CurrentProviderReviewDecisionError,
    assess_native_t102_current_provider_review_decision_v1,
    parse_native_t102_current_provider_review_decision_v1,
)
from rocell.application.native_t102_current_provider_read_only_intake_v1 import (
    build_native_t102_current_provider_read_only_intake_v1,
)
from rocell.application.native_t102_production_transport_v1 import (
    PinnedNativeT102EndpointV1,
)


MAX_DECISION_BYTES = 128 * 1024


def _strict_json(data: bytes) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise NativeT102CurrentProviderReviewDecisionError(
                    f"decision contains duplicate field {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            data.decode("utf-8"), object_pairs_hook=pairs,
            parse_constant=lambda item: (_ for _ in ()).throw(
                NativeT102CurrentProviderReviewDecisionError(
                    f"decision contains {item}")),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NativeT102CurrentProviderReviewDecisionError(
            "decision is not strict UTF-8 JSON") from exc
    if type(value) is not dict:
        raise NativeT102CurrentProviderReviewDecisionError(
            "decision root must be a JSON object")
    return value


def _write(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def build(
    decision_path: Path,
    output_dir: Path,
    *,
    intake_id: str,
    host_id: str,
    created_utc: str,
    port_name: str,
    usb_vid: str,
    usb_pid: str,
    usb_serial_number: str,
    passive_read_timeout_s: float = 1.0,
    maximum_passive_lines: int = 4,
    maximum_line_bytes: int = 2048,
) -> dict[str, Any]:
    """Retain a decision-bound proposal without accessing the endpoint."""

    decision_path = Path(decision_path)
    if decision_path.is_symlink():
        raise NativeT102CurrentProviderReviewDecisionError(
            "decision input must be one regular non-symlink file")
    decision_path = decision_path.resolve(strict=True)
    output_dir = Path(output_dir).resolve()
    if not decision_path.is_file():
        raise NativeT102CurrentProviderReviewDecisionError(
            "decision input must be one regular non-symlink file")
    if output_dir.exists():
        raise FileExistsError(
            "read-only intake output already exists; refusing to overwrite")
    raw = decision_path.read_bytes()
    if not raw or len(raw) > MAX_DECISION_BYTES:
        raise NativeT102CurrentProviderReviewDecisionError(
            "decision input size is invalid")
    decision = parse_native_t102_current_provider_review_decision_v1(
        _strict_json(raw))
    endpoint = PinnedNativeT102EndpointV1(
        port_name=port_name,
        usb_vid=usb_vid,
        usb_pid=usb_pid,
        usb_serial_number=usb_serial_number,
    )
    report = assess_native_t102_current_provider_review_decision_v1(
        decision, assessment_utc=created_utc)
    intake = build_native_t102_current_provider_read_only_intake_v1(
        decision,
        endpoint,
        intake_id=intake_id,
        host_id=host_id,
        created_utc=created_utc,
        passive_read_timeout_s=passive_read_timeout_s,
        maximum_passive_lines=maximum_passive_lines,
        maximum_line_bytes=maximum_line_bytes,
    )
    summary = {
        "schema": "rocell.native_t102_current_provider_read_only_intake_build.v1",
        "status": intake.to_dict()["status"],
        "input_document_sha256": hashlib.sha256(raw).hexdigest(),
        "decision_sha256": decision.decision_sha256,
        "report_sha256": report.report_sha256,
        "endpoint_sha256": endpoint.endpoint_sha256,
        "intake_sha256": intake.intake_sha256,
        "endpoint_open_authorized": False,
        "transport_write_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    _write(output_dir / "normalized-decision.json", decision.to_dict())
    _write(output_dir / "assessment-report.json", report.to_dict())
    _write(output_dir / "read-only-endpoint-intake.json", intake.to_dict())
    _write(output_dir / "build-summary.json", summary)
    return {**summary, "output_dir": str(output_dir)}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decision", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--intake-id", required=True)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--created-utc", required=True)
    parser.add_argument("--port-name", required=True)
    parser.add_argument("--usb-vid", required=True)
    parser.add_argument("--usb-pid", required=True)
    parser.add_argument("--usb-serial-number", required=True)
    parser.add_argument("--passive-read-timeout-s", type=float, default=1.0)
    parser.add_argument("--maximum-passive-lines", type=int, default=4)
    parser.add_argument("--maximum-line-bytes", type=int, default=2048)
    args = parser.parse_args()
    result = build(
        args.decision,
        args.output_dir,
        intake_id=args.intake_id,
        host_id=args.host_id,
        created_utc=args.created_utc,
        port_name=args.port_name,
        usb_vid=args.usb_vid,
        usb_pid=args.usb_pid,
        usb_serial_number=args.usb_serial_number,
        passive_read_timeout_s=args.passive_read_timeout_s,
        maximum_passive_lines=args.maximum_passive_lines,
        maximum_line_bytes=args.maximum_line_bytes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
