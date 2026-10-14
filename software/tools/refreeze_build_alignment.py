#!/usr/bin/env python3
"""Prepare or apply one synchronized, fail-closed RC03 software re-freeze.

This tool deliberately updates only the software-side provenance records.  It
does not regenerate RC03, change geometry, release hardware, or turn any
physical gate into PASS.  Run the RC03 generators and validators first, review
the dry-run report, then use ``--apply`` once for the approved next freeze.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


DEFAULT_WORKSPACE = Path(__file__).resolve().parents[2]
FREEZE_ID_PATTERN = re.compile(
    r"^ROCELL-PHASE0-(?P<revision>.+)-FREEZE-(?P<number>[0-9]{3})$"
)
EXPECTED_FROZEN_STATUS = "FROZEN_DIGITAL_ENGINEERING_HOLDS_CONTACT_BLOCKED"
EXPECTED_PREHARDWARE_STATE = (
    "DIGITALLY_CONSISTENT_ENGINEERING_AND_PHYSICAL_RELEASE_BLOCKED"
)
PROSPECTIVE_EXTERNAL_VALIDATION_INPUTS = (
    "hardware/static_overhead_camera/config/support_design.json",
    "hardware/static_overhead_camera/config/commercial_tripod_candidate.json",
    "hardware/static_overhead_camera/hardware_intake_template.csv",
)


class RefreezeError(ValueError):
    """The requested re-freeze is unsafe or inconsistent."""


def _freeze_plan_value(value: Any) -> Any:
    """Return an immutable detached copy of one JSON-compatible plan value."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RefreezeError("Re-freeze summary keys must be strings")
            frozen[key] = _freeze_plan_value(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_plan_value(item) for item in value)
    raise RefreezeError(
        f"Re-freeze summary contains unsupported {type(value).__name__}"
    )


def _thaw_plan_value(value: Any) -> Any:
    """Convert an immutable plan summary back to ordinary JSON containers."""

    if isinstance(value, Mapping):
        return {key: _thaw_plan_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_plan_value(item) for item in value]
    return value


@dataclass(frozen=True)
class RefreezePlan:
    """Fully rendered files and an auditable summary for one re-freeze."""

    workspace: Path
    documents: Mapping[Path, bytes]
    input_digests: Mapping[Path, str]
    summary: Mapping[str, Any]

    def __post_init__(self) -> None:
        workspace = Path(self.workspace).resolve()
        _require(workspace.is_dir(), f"Workspace does not exist: {workspace}")

        documents: dict[Path, bytes] = {}
        for raw_path, raw_payload in self.documents.items():
            path = Path(raw_path).resolve()
            try:
                path.relative_to(workspace)
            except ValueError as exc:
                raise RefreezeError(f"Output escapes workspace: {path}") from exc
            if path in documents:
                raise RefreezeError(f"Duplicate resolved output path: {path}")
            if not isinstance(raw_payload, bytes):
                raise RefreezeError(f"Rendered output must be immutable bytes: {path}")
            documents[path] = bytes(raw_payload)

        input_digests: dict[Path, str] = {}
        for raw_path, raw_digest in self.input_digests.items():
            path = Path(raw_path).resolve()
            if path in input_digests:
                raise RefreezeError(f"Duplicate resolved input path: {path}")
            if (
                not isinstance(raw_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", raw_digest) is None
            ):
                raise RefreezeError(f"Invalid input SHA-256 for {path}")
            input_digests[path] = raw_digest

        if not isinstance(self.summary, Mapping):
            raise RefreezeError("Re-freeze summary must be a mapping")
        frozen_summary = _freeze_plan_value(dict(self.summary))
        assert isinstance(frozen_summary, Mapping)
        object.__setattr__(self, "workspace", workspace)
        object.__setattr__(
            self,
            "documents",
            MappingProxyType(
                dict(sorted(documents.items(), key=lambda item: str(item[0])))
            ),
        )
        object.__setattr__(
            self,
            "input_digests",
            MappingProxyType(
                dict(sorted(input_digests.items(), key=lambda item: str(item[0])))
            ),
        )
        object.__setattr__(self, "summary", frozen_summary)


def _load_json(
    path: Path,
    observed_inputs: dict[Path, str] | None = None,
) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        document = json.loads(
            payload.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                RefreezeError(f"Nonfinite JSON constant {value!r} in {path}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, RefreezeError) as exc:
        raise RefreezeError(f"Cannot load {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise RefreezeError(f"Expected a JSON object in {path}")
    if observed_inputs is not None:
        observed_inputs[path.resolve()] = _sha256_bytes(payload)
    return document


def _render_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RefreezeError(f"Cannot hash {path}: {exc}") from exc
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RefreezeError(message)


def _workspace_path(workspace: Path, relative: str) -> Path:
    candidate = (workspace / relative).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise RefreezeError(f"Path escapes the workspace: {relative}") from exc
    return candidate


def _artifact_digest(
    workspace: Path,
    relative: str,
    pending_documents: Mapping[Path, bytes],
    observed_inputs: dict[Path, str],
) -> str:
    path = _workspace_path(workspace, relative)
    payload = pending_documents.get(path)
    if payload is not None:
        return _sha256_bytes(payload)
    digest = _sha256_file(path)
    observed_inputs[path] = digest
    return digest


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _validate_prospective_documents(
    workspace: Path,
    *,
    pending_documents: Mapping[Path, bytes],
    snapshot_paths: list[Path],
) -> dict[str, Any]:
    """Run the production validator against an isolated prospective workspace."""

    validator = workspace / "software/tools/validate_build_alignment.py"
    _require(validator.is_file(), "Alignment validator is missing")
    with tempfile.TemporaryDirectory(prefix="rocell-refreeze-validation-") as name:
        prospective = Path(name).resolve()
        shutil.copytree(
            workspace / "software/src",
            prospective / "software/src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(workspace / "software/config", prospective / "software/config")
        shutil.copytree(
            workspace / "software/calibrations",
            prospective / "software/calibrations",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(workspace / "software/models", prospective / "software/models")
        _copy_file(
            validator, prospective / "software/tools/validate_build_alignment.py"
        )
        for source in snapshot_paths:
            _copy_file(source, prospective / source.relative_to(workspace))
        # The strict onboarding-foundation validator follows these source-bound
        # ICD references outside software/ and the frozen RC03 snapshot.  Stage
        # the exact dependencies rather than weakening validation in the
        # isolated prospective workspace.
        for relative in PROSPECTIVE_EXTERNAL_VALIDATION_INPUTS:
            source = _workspace_path(workspace, relative)
            _require(
                source.is_file(),
                f"Prospective validation input is missing: {relative}",
            )
            _copy_file(source, prospective / Path(relative))
        for destination, payload in pending_documents.items():
            staged = prospective / destination.relative_to(workspace)
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(payload)

        completed = subprocess.run(
            [sys.executable, "software/tools/validate_build_alignment.py"],
            cwd=prospective,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RefreezeError(
                "Prospective alignment validator did not emit valid JSON: "
                f"{completed.stdout[-500:]!r} {completed.stderr[-500:]!r}"
            ) from exc
        _require(isinstance(report, dict), "Prospective alignment report is malformed")
        _require(
            completed.returncode == 0
            and report.get("status") == "ALIGNED_CAMERA_HOLD_CONTACT_BLOCKED"
            and report.get("errors") == [],
            "Prospective Freeze validation failed: "
            + json.dumps(report, sort_keys=True),
        )
        return report


def _collect_input_digests(
    workspace: Path,
    *,
    snapshot_paths: list[Path],
    document_paths: Mapping[Path, bytes],
) -> dict[Path, str]:
    """Capture every file that can affect planning or prospective validation."""

    inputs = set(snapshot_paths)
    inputs.update(document_paths)
    inputs.update((workspace / "software/config").rglob("*.json"))
    inputs.update(
        _workspace_path(workspace, relative)
        for relative in PROSPECTIVE_EXTERNAL_VALIDATION_INPUTS
    )
    inputs.add(workspace / "software/calibrations/registry.json")
    inputs.add(workspace / "software/tools/validate_build_alignment.py")
    inputs.add(Path(__file__).resolve())
    inputs.update((workspace / "software/src/rocell").rglob("*.py"))
    inputs.update(
        path for path in (workspace / "software/models").rglob("*") if path.is_file()
    )
    return {
        path.resolve(): _sha256_file(path.resolve())
        for path in sorted(inputs)
        if path.is_file()
    }


def _set_digest(payloads: Mapping[Path, bytes], workspace: Path) -> str:
    """Hash a named set of rendered files without depending on dict order."""

    digest = hashlib.sha256()
    for path, payload in sorted(payloads.items(), key=lambda item: str(item[0])):
        digest.update(
            str(path.relative_to(workspace)).replace("\\", "/").encode("utf-8")
        )
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def _digest_input_set(input_digests: Mapping[Path, str], workspace: Path) -> str:
    digest = hashlib.sha256()
    for path, value in sorted(input_digests.items(), key=lambda item: str(item[0])):
        digest.update(
            str(path.relative_to(workspace)).replace("\\", "/").encode("utf-8")
        )
        digest.update(b"\0")
        digest.update(value.encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _merge_and_verify_inputs(
    observed: dict[Path, str],
    collected: Mapping[Path, str],
) -> None:
    for path, digest in collected.items():
        prior = observed.get(path)
        _require(
            prior is None or prior == digest,
            f"Re-freeze input changed while the plan was being rendered: {path}",
        )
        observed[path] = digest


def _verify_input_digests(
    input_digests: Mapping[Path, str],
    *,
    phase: str = "while the plan was being validated",
) -> None:
    for path, expected in input_digests.items():
        _require(path.is_file(), f"Re-freeze input disappeared: {path}")
        _require(
            _sha256_file(path) == expected,
            f"Re-freeze input changed {phase}: {path}",
        )


def acquire_refreeze_lock(workspace: Path, token: str) -> Path:
    """Acquire the one process-visible lock before an apply plan is built."""

    _require(
        isinstance(token, str) and re.fullmatch(r"[0-9a-f]{64}", token) is not None,
        "Re-freeze lock token must be the reviewed lowercase plan SHA-256",
    )
    lock_path = workspace.resolve() / "software/config/.refreeze.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RefreezeError(
            f"Re-freeze lock exists: {lock_path}; inspect the workspace before removing it"
        ) from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((token + "\n").encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    return lock_path


def release_refreeze_lock(lock_path: Path) -> None:
    lock_path.unlink(missing_ok=True)


def _verify_refreeze_lock(
    workspace: Path,
    held_lock_path: Path,
    expected_plan_sha256: str,
) -> None:
    """Require the exact workspace lock token for the reviewed plan."""

    expected_lock = workspace.resolve() / "software/config/.refreeze.lock"
    supplied_lock = Path(held_lock_path).resolve()
    _require(
        supplied_lock == expected_lock and supplied_lock.is_file(),
        "Apply requires the workspace re-freeze lock acquired before planning",
    )
    try:
        token_bytes = supplied_lock.read_bytes()
    except OSError as exc:
        raise RefreezeError(
            f"Cannot read re-freeze lock {supplied_lock}: {exc}"
        ) from exc
    _require(
        token_bytes == (expected_plan_sha256 + "\n").encode("ascii"),
        "Re-freeze lock token does not own the reviewed plan",
    )


def build_refreeze_plan(
    workspace: Path,
    *,
    expected_current_freeze_id: str,
    new_freeze_number: int,
    freeze_date: str,
    reason: str,
    approval_reference: str,
    companion_change_reason: str | None = None,
) -> RefreezePlan:
    """Build a deterministic re-freeze without changing the filesystem."""

    workspace = workspace.resolve()
    observed_inputs: dict[Path, str] = {}
    _require(workspace.is_dir(), f"Workspace does not exist: {workspace}")
    try:
        parsed_freeze_date = date.fromisoformat(freeze_date)
    except ValueError as exc:
        raise RefreezeError("freeze_date must be a valid YYYY-MM-DD date") from exc
    _require(1 <= new_freeze_number <= 999, "new freeze number must be 1..999")
    reason = reason.strip()
    approval_reference = approval_reference.strip()
    companion_change_reason = (
        companion_change_reason.strip() if companion_change_reason is not None else None
    )
    _require(
        len(reason) >= 12, "--reason must contain at least 12 non-space characters"
    )
    _require(
        len(approval_reference) >= 8,
        "--approval-reference must contain at least 8 non-space characters",
    )
    if companion_change_reason == "":
        companion_change_reason = None

    config_root = _workspace_path(workspace, "software/config")
    manifest_path = config_root / "system_manifest.json"
    camera_path = config_root / "camera_manifest.json"
    profile_path = config_root / "simulation_hardware_profile.json"
    virtual_profile_path = config_root / "virtual_commissioning_profile.json"
    gate_path = config_root / "gate_projection.json"
    bundle_path = config_root / "simulation_bundle_lock.json"
    registry_path = _workspace_path(workspace, "software/calibrations/registry.json")

    manifest = _load_json(manifest_path, observed_inputs)
    camera = _load_json(camera_path, observed_inputs)
    profile = _load_json(profile_path, observed_inputs)
    virtual_profile = _load_json(virtual_profile_path, observed_inputs)
    gate = _load_json(gate_path, observed_inputs)
    bundle = _load_json(bundle_path, observed_inputs)
    registry = _load_json(registry_path, observed_inputs)

    current_id = manifest.get("manifest_id")
    _require(
        current_id == expected_current_freeze_id,
        "Current manifest ID differs from --expected-current-freeze-id",
    )
    match = FREEZE_ID_PATTERN.fullmatch(str(current_id))
    _require(match is not None, f"Unsupported current freeze ID: {current_id!r}")
    assert match is not None
    current_number = int(match.group("number"))
    design_revision = str(manifest.get("rc03", {}).get("design_revision", ""))
    _require(
        match.group("revision") == design_revision,
        "Freeze ID and RC03 design revision disagree",
    )
    _require(
        new_freeze_number == current_number + 1,
        "The new freeze number must be exactly the next sequential number",
    )
    _require(manifest.get("status") == EXPECTED_FROZEN_STATUS, "Manifest is not frozen")
    try:
        current_freeze_date = date.fromisoformat(str(manifest.get("freeze_date")))
    except ValueError as exc:
        raise RefreezeError("Current manifest freeze_date is invalid") from exc
    _require(
        parsed_freeze_date >= current_freeze_date,
        "New freeze date cannot precede the current freeze date",
    )

    rc03 = manifest.get("rc03", {})
    _require(isinstance(rc03, dict), "Manifest rc03 section must be an object")
    rc03_relative = rc03.get("root")
    _require(isinstance(rc03_relative, str), "Manifest RC03 root is missing")
    rc03_root = _workspace_path(workspace, rc03_relative)
    _require(rc03_root.is_dir(), f"RC03 root does not exist: {rc03_root}")

    release = _load_json(rc03_root / "RELEASE_VALIDATION.json", observed_inputs)
    package = _load_json(
        rc03_root / "BUILD_BY_STEP/PACKAGE_VALIDATION.json", observed_inputs
    )
    active_build = _load_json(
        rc03_root / "BUILD_BY_STEP/ACTIVE_BUILD.json", observed_inputs
    )
    measurement = _load_json(
        rc03_root / "config/measurement_record.json", observed_inputs
    )
    readiness = _load_json(rc03_root / "PRINT_READINESS.json", observed_inputs)
    tracker = _load_json(rc03_root / "BUILD_TRACKER.json", observed_inputs)
    prehardware = _load_json(rc03_root / "PREHARDWARE_READINESS.json", observed_inputs)

    _require(
        release.get("status") == "PASS", "RC03 digital release validation is not PASS"
    )
    _require(
        package.get("status") == "PASS", "Build-step package validation is not PASS"
    )
    _require(
        package.get("physical_release") == "UNRELEASED",
        "This tool cannot migrate a physically released package",
    )
    _require(
        rc03.get("physical_release_status") == "UNRELEASED",
        "Manifest physical release must remain UNRELEASED",
    )
    _require(
        active_build.get("active_build_id") == rc03.get("active_build_id"),
        "Active build ID changed; reconcile it before re-freezing",
    )
    _require(
        prehardware.get("state") == EXPECTED_PREHARDWARE_STATE,
        "Unexpected prehardware readiness state",
    )
    for field in (
        "safe_to_start_production_printing",
        "safe_to_drill_final_anchor_bores",
        "safe_to_power_robot",
    ):
        _require(
            prehardware.get(field) is False,
            f"Prehardware unexpectedly sets {field}=true",
        )
    _require(
        manifest.get("current_build_state", {}).get("contact_enabled") is False,
        "Contact must remain disabled during a software-only re-freeze",
    )
    _require(
        registry.get("artifacts") == {},
        "Calibration registry is not empty; explicitly migrate or invalidate its artifacts",
    )

    snapshot = rc03.get("source_snapshot")
    _require(
        isinstance(snapshot, list) and bool(snapshot),
        "RC03 source snapshot is empty",
    )
    assert isinstance(snapshot, list)
    snapshot_updates: list[dict[str, str]] = []
    snapshot_source_paths: list[Path] = []
    old_snapshot = {
        str(entry.get("path")): str(entry.get("sha256"))
        for entry in snapshot
        if isinstance(entry, dict)
    }
    _require(
        len(old_snapshot) == len(snapshot), "Snapshot paths are duplicated or malformed"
    )
    for entry in snapshot:
        relative = entry.get("path")
        _require(
            isinstance(relative, str) and bool(relative),
            "Snapshot path is invalid",
        )
        assert isinstance(relative, str)
        source_path = (rc03_root / relative).resolve()
        try:
            source_path.relative_to(rc03_root.resolve())
        except ValueError as exc:
            raise RefreezeError(f"Snapshot path escapes RC03: {relative}") from exc
        _require(source_path.is_file(), f"Snapshot source is missing: {relative}")
        snapshot_source_paths.append(source_path)
        source_digest = _sha256_file(source_path)
        observed_inputs[source_path] = source_digest
        snapshot_updates.append({"path": relative, "sha256": source_digest})

    gate_counts = Counter(
        value.get("status")
        for value in measurement.get("gates", {}).values()
        if isinstance(value, dict)
    )
    print_summary = readiness.get("summary", {})
    tracker_summary = tracker.get("summary", {})
    prehardware_summary = prehardware.get("summary", {})
    selected_jobs = int(print_summary.get("total_jobs", 0)) - int(
        print_summary.get("not_selected", 0)
    )
    _require(
        tracker_summary.get("selected_jobs") == selected_jobs,
        "Print readiness and build tracker selected-job counts disagree",
    )
    _require(
        dict(gate_counts) == prehardware.get("measurement_gate_status_counts"),
        "Measurement gate counts and prehardware report disagree",
    )

    new_id = f"ROCELL-PHASE0-{design_revision}-FREEZE-{new_freeze_number:03d}"
    new_bundle_id = (
        f"ROCELL-SIM-BUNDLE-{design_revision}-FREEZE-"
        f"{new_freeze_number:03d}-{new_freeze_number:03d}"
    )
    new_projection_id = f"ROCELL-RC03-CAPABILITIES-FREEZE-{new_freeze_number:03d}"

    next_manifest = copy.deepcopy(manifest)
    next_manifest["manifest_id"] = new_id
    next_manifest["freeze_date"] = freeze_date
    next_manifest["rc03"]["source_snapshot"] = snapshot_updates
    current_state = next_manifest["current_build_state"]
    current_state.update(
        {
            "selected_jobs": selected_jobs,
            "ready_jobs": int(print_summary.get("ready", 0)),
            "waiting_jobs": int(print_summary.get("waiting", 0)),
            "not_selected_jobs": int(print_summary.get("not_selected", 0)),
            "physical_gate_pass_count": int(gate_counts.get("PASS", 0)),
            "physical_gate_not_tested_count": int(gate_counts.get("NOT_TESTED", 0)),
            "prehardware_readiness_state": prehardware.get("state"),
            "prehardware_digital_pass_count": int(
                prehardware_summary.get("digital_pass", 0)
            ),
            "prehardware_digital_fail_count": int(
                prehardware_summary.get("digital_fail", 0)
            ),
        }
    )
    # These safety fields are asserted rather than inferred from mutable input.
    current_state["safe_to_start_production_printing"] = False
    current_state["safe_to_drill_final_anchor_bores"] = False
    current_state["safe_to_power_robot"] = False
    current_state["contact_enabled"] = False

    next_camera = copy.deepcopy(camera)
    next_camera["system_freeze_id"] = new_id
    next_profile = copy.deepcopy(profile)
    next_profile["binding"]["system_manifest_id"] = new_id
    next_virtual_profile = copy.deepcopy(virtual_profile)
    next_virtual_profile["binding"]["system_manifest_id"] = new_id
    next_virtual_profile["binding"]["simulation_bundle_id"] = new_bundle_id
    next_gate = copy.deepcopy(gate)
    next_gate["projection_id"] = new_projection_id
    next_gate["system_manifest_id"] = new_id
    next_registry = copy.deepcopy(registry)
    next_registry["system_manifest_id"] = new_id

    pending: dict[Path, bytes] = {
        manifest_path.resolve(): _render_json(next_manifest),
        camera_path.resolve(): _render_json(next_camera),
        profile_path.resolve(): _render_json(next_profile),
        virtual_profile_path.resolve(): _render_json(next_virtual_profile),
        gate_path.resolve(): _render_json(next_gate),
        registry_path.resolve(): _render_json(next_registry),
    }
    next_bundle = copy.deepcopy(bundle)
    next_bundle["bundle_id"] = new_bundle_id
    next_bundle["system_manifest_id"] = new_id
    artifacts = next_bundle.get("artifacts")
    _require(
        isinstance(artifacts, dict) and bool(artifacts),
        "Simulation bundle artifacts are missing",
    )
    assert isinstance(artifacts, dict)
    for artifact in artifacts.values():
        _require(isinstance(artifact, dict), "Simulation bundle artifact is malformed")
        relative = artifact.get("path")
        _require(
            isinstance(relative, str), "Simulation bundle artifact path is invalid"
        )
        artifact["sha256"] = _artifact_digest(
            workspace,
            relative,
            pending,
            observed_inputs,
        )
    pending[bundle_path.resolve()] = _render_json(next_bundle)

    collected_inputs = _collect_input_digests(
        workspace,
        snapshot_paths=snapshot_source_paths,
        document_paths=pending,
    )
    _merge_and_verify_inputs(observed_inputs, collected_inputs)

    prospective_report = _validate_prospective_documents(
        workspace,
        pending_documents=pending,
        snapshot_paths=snapshot_source_paths,
    )
    _verify_input_digests(observed_inputs)
    input_set_sha256 = _digest_input_set(observed_inputs, workspace)

    changed_sources = [
        entry["path"]
        for entry in snapshot_updates
        if old_snapshot.get(entry["path"]) != entry["sha256"]
    ]
    _require(
        bool(changed_sources) or companion_change_reason is not None,
        "No RC03 source changed; provide --companion-change-reason for an explicit "
        "companion-only re-freeze",
    )

    active_output_digest = _set_digest(pending, workspace)
    archive_root = workspace / "software/freezes" / str(current_id)
    transaction_root = workspace / "software/freezes/transactions"
    prior_aliases = {
        "system_manifest": manifest_path.resolve(),
        "camera_manifest": camera_path.resolve(),
        "simulation_hardware_profile": profile_path.resolve(),
        "virtual_commissioning_profile": virtual_profile_path.resolve(),
        "gate_projection": gate_path.resolve(),
        "simulation_bundle_lock": bundle_path.resolve(),
        "calibration_registry": registry_path.resolve(),
    }
    archive_documents: dict[Path, bytes] = {}
    archive_hashes: dict[str, dict[str, str]] = {}
    for name, source in prior_aliases.items():
        payload = source.read_bytes()
        destination = archive_root / (
            "calibration_registry.json"
            if name == "calibration_registry"
            else source.name
        )
        if destination.exists():
            _require(
                destination.read_bytes() == payload,
                f"Immutable prior-freeze archive differs: {destination}",
            )
        archive_documents[destination.resolve()] = payload
        archive_hashes[name] = {
            "path": str(destination.relative_to(workspace)).replace("\\", "/"),
            "sha256": _sha256_bytes(payload),
        }

    new_alias_hashes = {
        name: {
            "path": str(path.relative_to(workspace)).replace("\\", "/"),
            "sha256": _sha256_bytes(pending[path]),
        }
        for name, path in prior_aliases.items()
    }
    transaction_id = f"ROCELL-REFREEZE-{current_number:03d}-TO-{new_freeze_number:03d}"
    transaction_path = transaction_root / f"{current_id}__{new_id}.json"
    transaction = {
        "schema": "rocell.refreeze_transaction.v1",
        "schema_version": 1,
        "transaction_id": transaction_id,
        "commit_state": "APPLIED_WHEN_ACTIVE_MANIFEST_MATCHES_NEW_MANIFEST_SHA256",
        "physical_release_effect": "NONE",
        "old_manifest_id": current_id,
        "new_manifest_id": new_id,
        "freeze_date": freeze_date,
        "reason": reason,
        "approval_reference": approval_reference,
        "companion_change_reason": companion_change_reason,
        "tool": {
            "path": "software/tools/refreeze_build_alignment.py",
            "sha256": _sha256_file(Path(__file__).resolve()),
        },
        "reviewed_active_output_set_sha256": active_output_digest,
        "planning_input_set_sha256": input_set_sha256,
        "old_alias_archive": archive_hashes,
        "new_active_aliases": new_alias_hashes,
        "source_changes": [
            {
                "path": entry["path"],
                "old_sha256": old_snapshot[entry["path"]],
                "new_sha256": entry["sha256"],
                "changed": old_snapshot[entry["path"]] != entry["sha256"],
            }
            for entry in snapshot_updates
        ],
        "preflight": {
            "rc03_release_status": release.get("status"),
            "build_step_package_status": package.get("status"),
            "physical_release": package.get("physical_release"),
            "active_build_id": active_build.get("active_build_id"),
            "print_readiness_summary": print_summary,
            "measurement_gate_status_counts": dict(sorted(gate_counts.items())),
            "prehardware_state": prehardware.get("state"),
            "prehardware_summary": prehardware_summary,
        },
        "prospective_alignment_validation": prospective_report,
    }
    transaction_payload = _render_json(transaction)
    if transaction_path.exists():
        _require(
            transaction_path.read_bytes() == transaction_payload,
            f"Immutable re-freeze transaction differs: {transaction_path}",
        )
    pending.update(archive_documents)
    pending[transaction_path.resolve()] = transaction_payload
    input_digests = dict(observed_inputs)
    _verify_input_digests(input_digests)
    plan_hash = _set_digest(pending, workspace)
    summary: dict[str, Any] = {
        "status": "READY_TO_APPLY_SOFTWARE_ONLY_REFREEZE",
        "physical_release_effect": "NONE",
        "old_manifest_id": current_id,
        "new_manifest_id": new_id,
        "new_simulation_bundle_id": new_bundle_id,
        "new_gate_projection_id": new_projection_id,
        "freeze_date": freeze_date,
        "active_build_id": rc03.get("active_build_id"),
        "changed_snapshot_sources": changed_sources,
        "changed_snapshot_source_count": len(changed_sources),
        "reason": reason,
        "approval_reference": approval_reference,
        "companion_change_reason": companion_change_reason,
        "prior_freeze_archive": str(archive_root.relative_to(workspace)).replace(
            "\\", "/"
        ),
        "transaction_record": str(transaction_path.relative_to(workspace)).replace(
            "\\", "/"
        ),
        "current_build_state": {
            key: current_state[key]
            for key in (
                "selected_jobs",
                "ready_jobs",
                "waiting_jobs",
                "not_selected_jobs",
                "physical_gate_pass_count",
                "physical_gate_not_tested_count",
                "safe_to_power_robot",
                "contact_enabled",
            )
        },
        "output_files": [
            str(path.relative_to(workspace)).replace("\\", "/")
            for path in sorted(pending)
        ],
        "plan_sha256": plan_hash,
        "planning_input_set_sha256": input_set_sha256,
        "prospective_validation_status": prospective_report.get("status"),
    }
    return RefreezePlan(
        workspace=workspace,
        documents=pending,
        input_digests=input_digests,
        summary=summary,
    )


def apply_refreeze_plan(
    plan: RefreezePlan,
    *,
    expected_plan_sha256: str,
    held_lock_path: Path,
) -> None:
    """Replace every planned JSON file with its reviewed rendered payload."""

    if not isinstance(plan, RefreezePlan):
        raise TypeError("plan must be a RefreezePlan")
    summary_plan_sha256 = str(plan.summary.get("plan_sha256", ""))
    _require(
        re.fullmatch(r"[0-9a-f]{64}", expected_plan_sha256) is not None,
        "--expected-plan-sha256 must be 64 lowercase hexadecimal characters",
    )
    rendered_plan_sha256 = _set_digest(plan.documents, plan.workspace)
    _require(
        expected_plan_sha256 == summary_plan_sha256 == rendered_plan_sha256,
        "The reviewed plan hash differs from the rendered re-freeze payloads",
    )
    _verify_refreeze_lock(
        plan.workspace,
        held_lock_path,
        expected_plan_sha256,
    )
    staged: list[tuple[Path, Path]] = []
    try:
        _verify_input_digests(plan.input_digests, phase="after planning")
        for destination, payload in plan.documents.items():
            relative = destination.relative_to(plan.workspace)
            is_archive = len(relative.parts) >= 3 and relative.parts[:2] == (
                "software",
                "freezes",
            )
            if is_archive and destination.exists():
                _require(
                    destination.read_bytes() == payload,
                    f"Refusing to overwrite immutable archive: {destination}",
                )
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".refreeze",
                dir=destination.parent,
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            staged.append((temporary, destination))

        # The process-visible lock serializes cooperating re-freeze writers,
        # but RC03 generators and editors do not take that lock. Recheck both
        # the exact token and every consumed input after staging and directly
        # before the first irreversible replacement.
        _verify_refreeze_lock(
            plan.workspace,
            held_lock_path,
            expected_plan_sha256,
        )
        _verify_input_digests(
            plan.input_digests,
            phase="during output staging",
        )

        # Commit append-only evidence first, dependency leaves next, their
        # bundle lock second, and the manifest last. Until the final replace,
        # every mixed state fails closed. If interrupted, restore the old leaf
        # aliases from the archived prior-freeze directory before replanning.
        def commit_order(item: tuple[Path, Path]) -> tuple[int, str]:
            destination = item[1]
            relative = destination.relative_to(plan.workspace)
            if len(relative.parts) >= 3 and relative.parts[:2] == (
                "software",
                "freezes",
            ):
                return (-1, str(destination))
            if destination.name == "system_manifest.json":
                return (2, str(destination))
            if destination.name == "simulation_bundle_lock.json":
                return (1, str(destination))
            return (0, str(destination))

        for temporary, destination in sorted(staged, key=commit_order):
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--expected-current-freeze-id", required=True)
    parser.add_argument("--new-freeze-number", required=True, type=int)
    parser.add_argument("--date", required=True, dest="freeze_date")
    parser.add_argument("--reason", required=True)
    parser.add_argument("--approval-reference", required=True)
    parser.add_argument(
        "--companion-change-reason",
        help="required only when no RC03 source hash changed",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the synchronized JSON records; default is a read-only dry run",
    )
    parser.add_argument(
        "--expected-plan-sha256",
        help="required with --apply; copy the exact hash from the reviewed dry run",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    lock_path: Path | None = None
    try:
        if args.apply:
            if args.expected_plan_sha256 is None:
                raise RefreezeError("--apply requires --expected-plan-sha256")
            lock_path = acquire_refreeze_lock(
                args.workspace,
                args.expected_plan_sha256,
            )
        plan = build_refreeze_plan(
            args.workspace,
            expected_current_freeze_id=args.expected_current_freeze_id,
            new_freeze_number=args.new_freeze_number,
            freeze_date=args.freeze_date,
            reason=args.reason,
            approval_reference=args.approval_reference,
            companion_change_reason=args.companion_change_reason,
        )
        if args.apply:
            assert args.expected_plan_sha256 is not None
            assert lock_path is not None
            apply_refreeze_plan(
                plan,
                expected_plan_sha256=args.expected_plan_sha256,
                held_lock_path=lock_path,
            )
        result = _thaw_plan_value(plan.summary)
        assert isinstance(result, dict)
        result["applied"] = bool(args.apply)
        print(json.dumps(result, indent=2))
        return 0
    except RefreezeError as exc:
        print(json.dumps({"status": "REFREEZE_REJECTED", "error": str(exc)}, indent=2))
        return 2
    finally:
        if lock_path is not None:
            release_refreeze_lock(lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
