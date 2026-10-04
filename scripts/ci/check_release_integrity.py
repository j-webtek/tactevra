"""Check tracked source-preview contents against the reviewed release policy.

Policy mode runs in ordinary CI and rejects unexpected private, executable,
firmware, model-weight, key, and archive paths. It also validates the offline
release-readiness registry. Candidate mode additionally fails while a recorded
path or readiness blocker remains open.

This path check complements the content-oriented snapshot audit. Neither check
establishes redistribution rights or certifies that a snapshot is secret-free.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / ".github" / "release-integrity-policy.json"
READINESS_PATH = ROOT / ".github" / "release-readiness.json"
ISSUE_PREFIX = "https://github.com/j-webtek/tactevra/issues/"
TOP_LEVEL_FIELDS = {
    "version",
    "archive_scope",
    "forbidden_tracked_files",
    "forbidden_tracked_prefixes",
    "forbidden_tracked_basenames",
    "forbidden_tracked_basename_prefixes",
    "forbidden_tracked_suffixes",
    "allowed_tracked_files",
    "candidate_blockers",
}
READINESS_FIELDS = {
    "version", "release_scope", "authority", "tracker", "candidate", "blockers",
}
READINESS_TRACKER_FIELDS = {"issue", "expected_state", "milestone", "milestone_state"}
READINESS_CANDIDATE_FIELDS = {
    "status", "sha", "record", "ai_disposition", "arm_disposition",
    "audit_status", "maintainer_review_status", "publication_status",
}
READINESS_BLOCKER_FIELDS = {
    "id", "issue", "owner", "requirement", "status", "resolution",
}
RESOLUTION_FIELDS = {"summary", "evidence"}


def normalize(value: str) -> str:
    normalized = PurePosixPath(value.replace("\\", "/")).as_posix()
    if (not normalized or normalized.startswith("/")
            or normalized == ".." or normalized.startswith("../")
            or "/../" in f"/{normalized}/"):
        raise ValueError(f"invalid repository-relative path: {value!r}")
    return normalized


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _string_list(policy: dict, field: str, *, paths: bool = False) -> list[str]:
    values = policy.get(field)
    if not isinstance(values, list) or any(not isinstance(value, str) or not value
                                           for value in values):
        raise ValueError(f"{field} must be a list of non-empty strings")
    result = [normalize(value) if paths else value.lower() for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{field} contains duplicates")
    return result


def load_policy(path: Path = POLICY_PATH) -> dict:
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or set(policy) != TOP_LEVEL_FIELDS:
        raise ValueError(f"policy must contain exactly {sorted(TOP_LEVEL_FIELDS)}")
    if policy["version"] != 1:
        raise ValueError("policy version must be 1")
    if policy["archive_scope"] != "github-generated-source-archives":
        raise ValueError("archive_scope must be github-generated-source-archives")

    for field in ("forbidden_tracked_files", "forbidden_tracked_prefixes"):
        _string_list(policy, field, paths=True)
    for field in ("forbidden_tracked_basenames",
                  "forbidden_tracked_basename_prefixes",
                  "forbidden_tracked_suffixes"):
        _string_list(policy, field)

    allowed = policy["allowed_tracked_files"]
    blockers = policy["candidate_blockers"]
    if not isinstance(allowed, list) or not isinstance(blockers, list):
        raise ValueError("allowed_tracked_files and candidate_blockers must be lists")

    seen: set[str] = set()
    for index, entry in enumerate(allowed):
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "rationale"}:
            raise ValueError(f"allowed_tracked_files[{index}] has invalid fields")
        entry["path"] = normalize(entry["path"])
        digest = entry["sha256"].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"invalid SHA-256 for allowed file {entry['path']}")
        entry["sha256"] = digest
        if not isinstance(entry["rationale"], str) or not entry["rationale"].strip():
            raise ValueError(f"empty rationale for allowed file {entry['path']}")
        if entry["path"] in seen:
            raise ValueError(f"duplicate governed path: {entry['path']}")
        seen.add(entry["path"])

    for index, entry in enumerate(blockers):
        if not isinstance(entry, dict) or set(entry) != {"path", "issue", "rationale"}:
            raise ValueError(f"candidate_blockers[{index}] has invalid fields")
        entry["path"] = normalize(entry["path"])
        if (not isinstance(entry["issue"], str)
                or not entry["issue"].startswith(ISSUE_PREFIX)):
            raise ValueError(f"invalid issue for candidate blocker {entry['path']}")
        if not isinstance(entry["rationale"], str) or not entry["rationale"].strip():
            raise ValueError(f"empty rationale for candidate blocker {entry['path']}")
        if entry["path"] in seen:
            raise ValueError(f"duplicate governed path: {entry['path']}")
        seen.add(entry["path"])
    return policy


def load_readiness(path: Path = READINESS_PATH) -> dict:
    readiness = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(readiness, dict) or set(readiness) != READINESS_FIELDS:
        raise ValueError(
            f"readiness registry must contain exactly {sorted(READINESS_FIELDS)}")
    if readiness["version"] != 1:
        raise ValueError("readiness registry version must be 1")
    if readiness["release_scope"] != "source-only-experimental-preview":
        raise ValueError(
            "release_scope must be source-only-experimental-preview")
    if (not isinstance(readiness["authority"], str)
            or not readiness["authority"].strip()):
        raise ValueError("readiness authority must be a non-empty string")
    tracker = readiness["tracker"]
    if not isinstance(tracker, dict) or set(tracker) != READINESS_TRACKER_FIELDS:
        raise ValueError(
            f"readiness tracker must contain exactly {sorted(READINESS_TRACKER_FIELDS)}")
    if not isinstance(tracker["issue"], int) or tracker["issue"] < 1:
        raise ValueError("readiness tracker issue must be a positive integer")
    if tracker["expected_state"] not in {"open", "closed"}:
        raise ValueError("readiness tracker expected_state must be open or closed")
    if tracker["milestone_state"] not in {"open", "closed"}:
        raise ValueError("readiness tracker milestone_state must be open or closed")
    if not isinstance(tracker["milestone"], str) or not tracker["milestone"].strip():
        raise ValueError("readiness tracker milestone must be a non-empty string")
    candidate = readiness["candidate"]
    if not isinstance(candidate, dict) or set(candidate) != READINESS_CANDIDATE_FIELDS:
        raise ValueError(
            f"readiness candidate must contain exactly {sorted(READINESS_CANDIDATE_FIELDS)}")
    if candidate["status"] not in {"unselected", "qualified"}:
        raise ValueError("readiness candidate status must be unselected or qualified")
    if candidate["status"] == "qualified":
        if not isinstance(candidate["sha"], str) or not re.fullmatch(
                r"[0-9a-f]{40}", candidate["sha"]):
            raise ValueError("qualified readiness candidate needs a full lowercase SHA")
        candidate["record"] = normalize(candidate["record"])
        if candidate["ai_disposition"] != "compatible-offline-with-limitations":
            raise ValueError("qualified candidate needs the bounded AI disposition")
        if candidate["arm_disposition"] != "compatible-offline-with-limitations":
            raise ValueError("qualified candidate needs the bounded arm disposition")
        if candidate["audit_status"] != "pass":
            raise ValueError("qualified candidate needs a passing audit")
    elif any(candidate[field] is not None for field in READINESS_CANDIDATE_FIELDS - {"status"}):
        raise ValueError("unselected candidate fields must be null")
    if candidate["maintainer_review_status"] not in {None, "pending", "complete"}:
        raise ValueError("invalid maintainer review status")
    if candidate["publication_status"] not in {None, "not-approved", "approved", "published"}:
        raise ValueError("invalid publication status")
    blockers = readiness["blockers"]
    if not isinstance(blockers, list):
        raise ValueError("readiness blockers must be a list")

    seen_ids: set[str] = set()
    seen_issues: set[str] = set()
    for index, entry in enumerate(blockers):
        if not isinstance(entry, dict) or set(entry) != READINESS_BLOCKER_FIELDS:
            raise ValueError(f"readiness blockers[{index}] has invalid fields")
        blocker_id = entry["id"]
        if (not isinstance(blocker_id, str)
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", blocker_id)):
            raise ValueError(f"invalid readiness blocker id: {blocker_id!r}")
        if blocker_id in seen_ids:
            raise ValueError(f"duplicate readiness blocker id: {blocker_id}")
        seen_ids.add(blocker_id)
        issue = entry["issue"]
        if not isinstance(issue, str) or not issue.startswith(ISSUE_PREFIX):
            raise ValueError(f"invalid issue for readiness blocker {blocker_id}")
        if issue in seen_issues:
            raise ValueError(f"duplicate readiness blocker issue: {issue}")
        seen_issues.add(issue)
        for field in ("owner", "requirement"):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ValueError(
                    f"empty {field} for readiness blocker {blocker_id}")
        status = entry["status"]
        resolution = entry["resolution"]
        if status == "open":
            if resolution is not None:
                raise ValueError(
                    f"open readiness blocker {blocker_id} must have null resolution")
        elif status == "cleared":
            if (not isinstance(resolution, dict)
                    or set(resolution) != RESOLUTION_FIELDS):
                raise ValueError(
                    f"cleared readiness blocker {blocker_id} needs a resolution")
            if (not isinstance(resolution["summary"], str)
                    or not resolution["summary"].strip()):
                raise ValueError(
                    f"cleared readiness blocker {blocker_id} needs a summary")
            evidence = resolution["evidence"]
            if (not isinstance(evidence, list) or not evidence
                    or any(not isinstance(item, str) or not item.strip()
                           for item in evidence)):
                raise ValueError(
                    f"cleared readiness blocker {blocker_id} needs evidence")
        else:
            raise ValueError(
                f"invalid status for readiness blocker {blocker_id}: {status!r}")
    if candidate["status"] == "qualified" and any(
            entry["status"] == "open" for entry in blockers):
        raise ValueError("readiness candidate cannot be qualified while blockers are open")
    return readiness


def readiness_errors(root: Path, readiness: dict, tracked: list[str] | None = None,
                     *, candidate: bool = False) -> list[str]:
    errors: list[str] = []
    tracked_set = set(tracked) if tracked is not None else None
    candidate_record = readiness["candidate"].get("record")
    if candidate_record:
        if not (root / candidate_record).is_file():
            errors.append(f"missing candidate record: {candidate_record}")
        elif tracked_set is not None and candidate_record not in tracked_set:
            errors.append(f"untracked candidate record: {candidate_record}")
    for entry in readiness["blockers"]:
        if entry["status"] == "cleared":
            for evidence in entry["resolution"]["evidence"]:
                if evidence.startswith(("https://", "http://")):
                    continue
                try:
                    evidence_path = normalize(evidence)
                except ValueError as exc:
                    errors.append(
                        f"invalid readiness evidence for {entry['id']}: {exc}")
                    continue
                if not (root / Path(evidence_path)).is_file():
                    errors.append(
                        f"missing readiness evidence for {entry['id']}: {evidence_path}")
                elif tracked_set is not None and evidence_path not in tracked_set:
                    errors.append(
                        f"untracked readiness evidence for {entry['id']}: {evidence_path}")
        elif candidate:
            errors.append(
                f"release-readiness blocker is open: {entry['id']} ({entry['issue']})")
    return errors


def tracked_paths(root: Path = ROOT) -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root,
    )
    return sorted(normalize(raw.decode("utf-8"))
                  for raw in output.split(b"\0") if raw)


def policy_errors(root: Path, policy: dict, tracked: list[str],
                  *, candidate: bool = False) -> list[str]:
    tracked_set = set(tracked)
    allowed = {entry["path"]: entry for entry in policy["allowed_tracked_files"]}
    errors: list[str] = []

    for path, entry in allowed.items():
        disk_path = root / Path(path)
        if path not in tracked_set or not disk_path.is_file():
            errors.append(f"allowed-file record is stale or untracked: {path}")
        elif sha256(disk_path) != entry["sha256"]:
            errors.append(f"allowed-file digest changed: {path}")

    forbidden_files = set(
        value.lower() for value in policy["forbidden_tracked_files"])
    prefixes = tuple(value.lower() for value in policy["forbidden_tracked_prefixes"])
    basenames = set(value.lower() for value in policy["forbidden_tracked_basenames"])
    basename_prefixes = tuple(
        value.lower() for value in policy["forbidden_tracked_basename_prefixes"])
    suffixes = tuple(value.lower() for value in policy["forbidden_tracked_suffixes"])
    for path in tracked:
        if path in allowed:
            continue
        lower = path.lower()
        basename = PurePosixPath(lower).name
        reasons = []
        if lower in forbidden_files:
            reasons.append("forbidden file")
        if lower.startswith(prefixes):
            reasons.append("forbidden directory")
        if basename in basenames or basename.startswith(basename_prefixes):
            reasons.append("credential/private filename")
        if lower.endswith(suffixes):
            reasons.append("forbidden binary/model/key/archive suffix")
        if reasons:
            errors.append(f"{', '.join(reasons)}: {path}")

    if candidate:
        for entry in policy["candidate_blockers"]:
            if entry["path"] in tracked_set:
                errors.append(
                    f"candidate blocker remains tracked: {entry['path']} ({entry['issue']})")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("policy", "candidate"), default="policy")
    args = parser.parse_args()
    try:
        policy = load_policy()
        readiness = load_readiness()
        tracked = tracked_paths()
        errors = policy_errors(ROOT, policy, tracked, candidate=args.mode == "candidate")
        errors.extend(readiness_errors(
            ROOT, readiness, tracked, candidate=args.mode == "candidate"))
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"release-integrity check could not run: {exc}") from exc
    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise SystemExit(
            f"Release-integrity {args.mode} check failed:\n{details}\n"
            "Review .github/release-integrity-policy.json, "
            ".github/release-readiness.json, and docs/RELEASING.md."
        )
    blockers = (sum(entry["path"] in set(tracked)
                    for entry in policy["candidate_blockers"])
                + sum(entry["status"] == "open"
                      for entry in readiness["blockers"]))
    print(
        f"PASS: release-integrity {args.mode} check covers {len(tracked)} tracked paths; "
        f"{blockers} recorded candidate blocker(s) remain"
    )


if __name__ == "__main__":
    main()
