"""Strictly assess one returned ARM-165 review decision without hardware I/O."""

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


def assess(
    decision_path: Path, output_dir: Path, *, assessment_utc: str,
) -> dict:
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
            "decision assessment output already exists; refusing to overwrite")
    data = decision_path.read_bytes()
    if not data or len(data) > MAX_DECISION_BYTES:
        raise NativeT102CurrentProviderReviewDecisionError(
            "decision input size is invalid")
    decision = parse_native_t102_current_provider_review_decision_v1(_strict_json(data))
    report = assess_native_t102_current_provider_review_decision_v1(
        decision, assessment_utc=assessment_utc)
    summary = {
        "schema": "rocell.native_t102_current_provider_review_decision_intake.v1",
        "status": report.status,
        "input_document_sha256": hashlib.sha256(data).hexdigest(),
        "decision_sha256": decision.decision_sha256,
        "report_sha256": report.report_sha256,
        "assessment_utc": assessment_utc,
        "ready_for_read_only_endpoint_qualification_intake": report.to_dict()[
            "ready_for_read_only_endpoint_qualification_intake"],
        "endpoint_open_authorized": False,
        "controller_start_authorized": False,
        "execution_authorized": False,
        "hardware_access": False,
        "physical_authority": False,
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    _write(output_dir / "normalized-decision.json", decision.to_dict())
    _write(output_dir / "assessment-report.json", report.to_dict())
    _write(output_dir / "intake-summary.json", summary)
    return {**summary, "output_dir": str(output_dir)}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decision", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--assessment-utc", required=True)
    args = parser.parse_args()
    result = assess(
        args.decision, args.output_dir, assessment_utc=args.assessment_utc)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result[
        "ready_for_read_only_endpoint_qualification_intake"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
