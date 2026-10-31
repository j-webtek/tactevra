"""Build the hash-bound ARM-171 owner acceptance; performs no hardware I/O."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.native_t102_current_provider_owner_ai_review_acceptance_v1 import (
    accept_current_provider_internal_ai_review_v1,
    build_current_provider_internal_ai_review_v1,
)


def build(output: Path) -> dict:
    """Create the exact retained owner acceptance without overwriting output."""

    decision, report = build_current_provider_internal_ai_review_v1(
        review_id="arm-171-current-provider-ai-review",
        review_started_utc="2026-10-31T21:34:00Z",
        review_completed_utc="2026-10-31T21:35:00Z",
        decision_valid_until_utc="2027-01-31T21:35:00Z",
    )
    acceptance = accept_current_provider_internal_ai_review_v1(
        decision,
        report,
        acceptance_id="arm-171-current-provider-owner-ai-acceptance",
        owner_id="project-owner",
        accepted_utc="2026-10-31T21:36:00Z",
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(acceptance.to_dict(), indent=2) + "\n")
    return acceptance.to_dict()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))
