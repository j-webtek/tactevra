"""Build a deterministic index over already retained parked-pose evidence."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator


AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from eval.evaluate_parked_pose_qualification import (  # noqa: E402
    CAMPAIGN_SCHEMA,
    canonical_hash,
    load_strict_json,
)
from eval.preflight_parked_pose_campaign import (  # noqa: E402
    INDEX_SCHEMA,
    TYPE_CUSTODY,
    _sha256_and_size,
    required_artifacts,
)


DECLARATIONS_SCHEMA = AI_ROOT / "schemas" / "parked_pose_custody_declarations_v1.schema.json"


def _validate(document: dict[str, Any], schema_path: Path, label: str) -> None:
    errors = sorted(
        Draft202012Validator(load_strict_json(schema_path)).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        first = errors[0]
        where = ".".join(str(item) for item in first.absolute_path) or "$"
        raise ValueError(f"{label} schema validation failed at {where}: {first.message}")


def _regular_input(path: Path, label: str) -> Path:
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} must be a regular file")
    return resolved


def _contained_files(root: Path) -> tuple[Path, list[Path]]:
    if root.is_symlink():
        raise ValueError("evidence root cannot be a symlink")
    resolved_root = root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise ValueError("evidence root must be a directory")
    files: list[Path] = []
    for directory, names, filenames in os.walk(resolved_root, followlinks=False):
        directory_path = Path(directory)
        for name in names:
            if (directory_path / name).is_symlink():
                raise ValueError(f"evidence root cannot contain a symlink: {name}")
        for name in filenames:
            path = directory_path / name
            if path.is_symlink():
                raise ValueError(f"evidence root cannot contain a symlink: {name}")
            if not path.is_file():
                raise ValueError(f"evidence root contains a non-regular file: {name}")
            files.append(path)
    return resolved_root, sorted(files, key=lambda path: path.relative_to(resolved_root).as_posix())


def _inventory(root: Path) -> tuple[Path, dict[str, tuple[str, int]]]:
    resolved_root, before = _contained_files(root)
    by_digest: dict[str, tuple[str, int]] = {}
    for path in before:
        digest, size = _sha256_and_size(path)
        relative = path.relative_to(resolved_root).as_posix()
        if size == 0:
            raise ValueError(f"retained artifact cannot be empty: {relative}")
        if digest in by_digest:
            raise ValueError(
                f"one retained digest appears at multiple paths: "
                f"{by_digest[digest][0]}/{relative}"
            )
        by_digest[digest] = (relative, size)
    _, after = _contained_files(resolved_root)
    before_names = [path.relative_to(resolved_root).as_posix() for path in before]
    after_names = [path.relative_to(resolved_root).as_posix() for path in after]
    if before_names != after_names:
        raise ValueError("evidence root changed during inventory")
    return resolved_root, by_digest


def build_index(
    campaign_path: Path,
    declarations_path: Path,
    evidence_root: Path,
) -> dict[str, Any]:
    campaign = load_strict_json(_regular_input(campaign_path, "campaign"))
    declarations = load_strict_json(
        _regular_input(declarations_path, "custody declarations")
    )
    _validate(campaign, CAMPAIGN_SCHEMA, "campaign")
    _validate(declarations, DECLARATIONS_SCHEMA, "custody declarations")
    campaign_core = {
        key: value for key, value in campaign.items() if key != "campaign_sha256"
    }
    if canonical_hash(campaign_core) != campaign["campaign_sha256"]:
        raise ValueError("campaign SHA-256 mismatch")
    declarations_core = {
        key: value
        for key, value in declarations.items()
        if key != "declarations_sha256"
    }
    if canonical_hash(declarations_core) != declarations["declarations_sha256"]:
        raise ValueError("custody declarations SHA-256 mismatch")
    if declarations["campaign_sha256"] != campaign["campaign_sha256"]:
        raise ValueError("custody declarations campaign identity mismatch")
    if campaign["physical_cycles"] and (
        campaign["collection_effects"]["authorization_evidence_sha256"] is None
    ):
        raise ValueError("physical campaign requires collection authorization evidence")

    required = required_artifacts(campaign, declarations["custody_review_sha256"])
    declared: dict[str, str] = {}
    for declaration in declarations["declarations"]:
        digest = declaration["sha256"]
        if digest in declared:
            raise ValueError(f"duplicate custody declaration: {digest}")
        declared[digest] = declaration["custody"]
    missing_declarations = sorted(set(required) - set(declared))
    extra_declarations = sorted(set(declared) - set(required))
    if missing_declarations or extra_declarations:
        raise ValueError(
            "custody declaration coverage mismatch; "
            f"missing={missing_declarations}; extra={extra_declarations}"
        )
    for digest, artifact_type in required.items():
        if declared[digest] != TYPE_CUSTODY[artifact_type]:
            raise ValueError(f"artifact custody mismatch: {digest}")

    _, retained = _inventory(evidence_root)
    missing_files = sorted(set(required) - set(retained))
    extra_files = sorted(set(retained) - set(required))
    if missing_files or extra_files:
        raise ValueError(
            f"retained file coverage mismatch; missing={missing_files}; extra={extra_files}"
        )
    entries = [
        {
            "sha256": digest,
            "relative_path": retained[digest][0],
            "size_bytes": retained[digest][1],
            "artifact_type": required[digest],
            "custody": declared[digest],
        }
        for digest in sorted(required)
    ]
    core = {
        "schema": "rocell.ai_parked_pose_evidence_index.v1",
        "scope": "READ_ONLY_RETAINED_EVIDENCE_INDEX",
        "campaign_sha256": campaign["campaign_sha256"],
        "custody_review_sha256": declarations["custody_review_sha256"],
        "entries": entries,
    }
    index = {**core, "index_sha256": canonical_hash(core)}
    _validate(index, INDEX_SCHEMA, "evidence index")
    return index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--custody-declarations", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    resolved_root = args.evidence_root.resolve(strict=True)
    resolved_output = args.output.resolve(strict=False)
    if resolved_output == resolved_root or resolved_root in resolved_output.parents:
        parser.error("--output must be outside --evidence-root")
    index = build_index(args.campaign, args.custody_declarations, args.evidence_root)
    rendered = json.dumps(index, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.name}.tmp")
    temporary.write_bytes(rendered.encode("utf-8"))
    temporary.replace(args.output)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
