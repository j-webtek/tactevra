"""Audit retained sources for the static-overhead collision body roster."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rocell.application.static_overhead_collision_source_audit_v1 import (
    audit_static_overhead_collision_sources_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract-workspace", type=Path, required=True)
    parser.add_argument("--source-workspace", type=Path, required=True)
    parser.add_argument("--measurement-manifest", type=Path, required=True)
    parser.add_argument("--measurement-manifest-sha256", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = audit_static_overhead_collision_sources_v1(
        args.contract_workspace,
        args.source_workspace,
        args.measurement_manifest,
        args.measurement_manifest_sha256,
        source_revision=args.source_revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
