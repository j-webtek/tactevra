#!/usr/bin/env python3
"""Generate the non-destructive operator-facing BUILD_BY_STEP package.

Canonical CAD, configuration, ledgers, drawings, and print controls remain in their
original locations.  Step folders contain instructions, direct links, hashes, and
operator-writable evidence templates.  This prevents controlled files from
silently diverging while still giving a builder one complete folder per step.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "assembly_steps.json"
TARGET = ROOT / "BUILD_BY_STEP"
STAGING = ROOT / "BUILD_BY_STEP.__staging__"
PREVIOUS = ROOT / "BUILD_BY_STEP.__previous__"
SENTINEL = ".generated_by_build_step_packages"
ACTIVE_BUILD_FILE = "ACTIVE_BUILD.json"
LAYOUT_VERSION = 6
BUILD_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\Z")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{value}" for value in range(1, 10)),
    *(f"LPT{value}" for value in range(1, 10)),
}
STEP_START_FILE = "00 - START HERE.md"
STEP_BEFORE_FILE = "01 - BEFORE YOU START.md"
STEP_PARTS_FILE = "02 - PARTS AND TOOLS CHECKLIST.md"
STEP_STL_DIRECTORY = "03 - STL MODELS"
STEP_STL_README = "READ ME - HOW TO USE THESE MODELS.md"
STEP_STL_CATALOG = "STL MODEL LIST.csv"
STEP_DRILL_GUIDE_FILE = "03A - PRINT AND ASSEMBLE THE BOARD DRILL GUIDE.md"
STEP_PRINT_SETTINGS_FILE = "03B - PRINT SETTINGS FOR THIS STEP.md"
STEP_INSTRUCTIONS_FILE = "04 - STEP-BY-STEP INSTRUCTIONS.md"
STEP_CHECK_FILE = "05 - CHECK YOUR WORK.md"
STEP_EVIDENCE_DIRECTORY = "06 - SAVE MEASUREMENTS AND PHOTOS"
STEP_EVIDENCE_README = "READ ME - WHAT TO RECORD.md"
STEP_FINISH_FILE = "07 - FINISH THIS STEP AND CONTINUE.md"
STEP_TECHNICAL_DIRECTORY = "99 - TECHNICAL RECORDS - DO NOT EDIT"
STEP_MANIFEST_FILE = f"{STEP_TECHNICAL_DIRECTORY}/STEP_MANIFEST.json"
STEP_OPEN_FILES = f"{STEP_TECHNICAL_DIRECTORY}/OPEN CONTROLLED FILES.md"
STEP_FILE_INDEX = f"{STEP_TECHNICAL_DIRECTORY}/FILE INDEX.csv"
STEP_FILE_MANIFEST = f"{STEP_TECHNICAL_DIRECTORY}/FILE MANIFEST.json"
STEP_FILE_HASHES = f"{STEP_TECHNICAL_DIRECTORY}/SHA256SUMS.txt"
STEP_HARDWARE_CSV = f"{STEP_TECHNICAL_DIRECTORY}/HARDWARE AND TOOLS.csv"
EVIDENCE_TEMPLATE_DIRECTORY = "BUILD_ID_TEMPLATE"
MEASUREMENT_RECORD_FILE = "measurement_record.json"
SIGNOFF_RECORD_FILE = "signoff.json"
MEASUREMENTS_CHECKLIST_FILE = "Measurements Checklist.md"
FINISH_SIGNOFF_FILE = "Finish and Sign Off.md"
LEGACY_EVIDENCE_DIRECTORY = "06_EVIDENCE"

ROOT_DASHBOARD_FILE = "00 - START HERE.md"
ROOT_SEQUENCE_FILE = "01 - COMPLETE BUILD ORDER.md"
ROOT_EVIDENCE_FILE = "02 - HOW TO SAVE MEASUREMENTS AND PHOTOS.md"
ROOT_GLOSSARY_FILE = "03 - PART NAMES AND TECHNICAL TERMS.md"

REQUIRED_GEOMETRY_OVERRIDE_KEYS = {
    "camera_hex_ac",
    "compliant_tool_m3_insert_pocket_d",
    "keyboard_locator_slot_w",
    "keyboard_locator_socket_d",
    "m3_head_recess_d",
    "m4_washer_od",
    "m5_nut_ac",
    "m5_washer_od",
    "mast_socket_size",
    "phone_locator_slot_w",
    "phone_locator_socket_d",
    "phone_m4_nut_ac",
    "phone_station_m3_insert_pocket_d",
    "seam_radial_slot_w",
    "seam_round_socket_d",
    "zip_tie_slot_w",
    "zip_tie_tunnel_h",
}
LEGACY_GENERATED_STL_COPIES = {"m3_insert_fit_gauge.stl"}
STEP_00_CANONICAL_REFERENCE_STLS = {
    "hardware_fit_gauge.stl",
    "keyboard_station_left.stl",
    "m3_head_fit_gauge.stl",
    "m4_washer_fit_gauge.stl",
    "m5_nut_trap_fit_gauge.stl",
    "mast_socket_fit_test.stl",
    "phone_clamp_rail.stl",
    "phone_m3_insert_fit_gauge.stl",
    "phone_tcp_station.stl",
    "setup_hardware_fit_gauge.stl",
    "station_locator_fit_gauge.stl",
    "stylus_diameter_gauge.stl",
    "tool_m3_insert_fit_gauge.stl",
}

REQUIRED_STEP_FILES = (
    STEP_START_FILE,
    STEP_BEFORE_FILE,
    STEP_PARTS_FILE,
    f"{STEP_STL_DIRECTORY}/{STEP_STL_README}",
    f"{STEP_STL_DIRECTORY}/{STEP_STL_CATALOG}",
    STEP_PRINT_SETTINGS_FILE,
    STEP_INSTRUCTIONS_FILE,
    STEP_CHECK_FILE,
    f"{STEP_EVIDENCE_DIRECTORY}/{STEP_EVIDENCE_README}",
    f"{STEP_EVIDENCE_DIRECTORY}/{EVIDENCE_TEMPLATE_DIRECTORY}/{MEASUREMENT_RECORD_FILE}",
    f"{STEP_EVIDENCE_DIRECTORY}/{EVIDENCE_TEMPLATE_DIRECTORY}/{SIGNOFF_RECORD_FILE}",
    f"{STEP_EVIDENCE_DIRECTORY}/{EVIDENCE_TEMPLATE_DIRECTORY}/{MEASUREMENTS_CHECKLIST_FILE}",
    f"{STEP_EVIDENCE_DIRECTORY}/{EVIDENCE_TEMPLATE_DIRECTORY}/{FINISH_SIGNOFF_FILE}",
    STEP_FINISH_FILE,
    STEP_MANIFEST_FILE,
    STEP_OPEN_FILES,
    STEP_FILE_INDEX,
    STEP_FILE_MANIFEST,
    STEP_FILE_HASHES,
    STEP_HARDWARE_CSV,
)
ROOT_CONTROL_FILES = (
    "README.md",
    ROOT_DASHBOARD_FILE,
    ROOT_SEQUENCE_FILE,
    ROOT_EVIDENCE_FILE,
    ROOT_GLOSSARY_FILE,
    "PRINT_JOB_OWNERSHIP.csv",
)

CORE_REFERENCES = (
    ("README_FIRST.md", "release entry point", "read"),
    ("output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf", "complete illustrated guide", "read"),
    ("ASSEMBLY_MANUAL.pdf", "controlled detailed manual", "read"),
    ("ASSEMBLY_MANUAL.md", "controlled detailed-manual source", "reference_only"),
    ("BOM.csv", "purchasing source", "reference_only"),
    ("JOB_KITS.csv", "kitting source", "reference_only"),
    ("FASTENER_MAP.csv", "board fastener source", "edit_only_in_step_01_after_cutoff_tests"),
    ("PRINT_READINESS.md", "current print readiness", "verify"),
    ("PRINT_READINESS.json", "machine-readable print readiness", "reference_only"),
    ("BUILD_TRACKER.md", "lifecycle tracker", "verify"),
    ("BUILD_TRACKER.json", "machine-readable lifecycle tracker", "reference_only"),
    ("config/measurement_record.json", "canonical measurement and gate record", "edit_only_with_recording_script"),
    ("config/job_build_record.json", "canonical job lifecycle record", "edit_only_with_controlled_workflow"),
    ("config/parameters.json", "canonical CAD parameter set", "reference_only"),
    ("config/print_jobs.json", "canonical print-job definitions", "reference_only"),
    ("config/print_profiles.json", "canonical print-profile definitions", "reference_only"),
    ("config/workcell_layout.json", "generated geometry/layout source", "reference_only"),
    ("config/assembly_steps.json", "canonical step-to-file relationship map", "reference_only"),
    (
        "config/tripod_camera_installation_intake_v1.json",
        "hash-bound tripod receipt, measurement, pose, stability, and qualification intake",
        "complete",
    ),
    ("TRIPOD_CAMERA_INSTALLATION.md", "tripod installation and qualification procedure", "read"),
    ("slicer_profiles/QIDI_PLUS4/README.md", "QIDI process-preset import guide", "read"),
    ("scripts/build_step_packages.py", "step-package generator and validator", "run_from_project_root"),
    (
        "scripts/stage_hash_bound_artifacts.py",
        "hash-bound canonical artifact staging and offline verification",
        "run_for_standalone_export",
    ),
    ("scripts/validate_print_readiness.py", "typed gate and print-readiness validator", "run_from_project_root"),
    ("scripts/validate_release_package.py", "whole-package release validator", "run_from_project_root"),
    (
        "scripts/validate_tripod_camera_intake.py",
        "tripod intake hash and zero-authority validator",
        "run_from_project_root",
    ),
    ("scripts/generate_build_tracker.py", "job-lifecycle validator and tracker generator", "run_from_project_root"),
    ("scripts/generate_job_cards.py", "controlled print-traveler instruction generator", "reference_only"),
    ("scripts/build_manual_pdf.py", "controlled detailed-manual PDF renderer", "reference_only"),
    ("scripts/render_assembly_guide.py", "assembly-panel source renderer", "reference_only"),
    ("scripts/build_illustrated_assembly_guide.py", "illustrated-guide PDF generator", "reference_only"),
    ("scripts/set_active_build.py", "active physical-build selector", "run_before_recording_evidence"),
    ("scripts/initialize_step_evidence.py", "non-overwriting active-build evidence initializer", "run_before_each_step"),
    ("scripts/record_step_result.py", "non-destructive step-result recorder", "run_for_each_step_test"),
    ("scripts/sign_off_step.py", "validated step signoff recorder", "run_after_step_tests"),
    ("scripts/step_evidence_common.py", "shared step-evidence containment and schema controls", "reference_only"),
    ("scripts/record_job_lifecycle.py", "sequential print-job lifecycle recorder", "run_after_each_completed_state"),
    ("scripts/record_print_measurement.py", "canonical gate and route recorder", "run_after_reviewing_raw_evidence"),
)

OPERATIONAL_PATHS = {
    "ASSEMBLY_MANUAL.pdf",
    "BUILD_TRACKER.md",
    "BUILD_TRACKER.json",
    "JOB_CARDS.pdf",
    "JOB_KITS.csv",
    "PRINT_READINESS.md",
    "PRINT_READINESS.json",
    "RELEASE_VALIDATION.json",
    "FASTENER_MAP.csv",
    "config/job_build_record.json",
    "config/measurement_record.json",
    "drawings/documentation_sync.json",
    "fiducials/apriltag_map.json",
}
OPERATIONAL_PREFIXES = ("job_cards/", "output/")

DIRECT_FILE_REQUIREMENTS = {
    "00": (
        "PRINT_READINESS.md",
        "JOB_CARDS.pdf",
        "JOB_KITS.csv",
    ),
    "01": (
        "output/pdf/RC03_BOARD_DRILL_GUIDE_LETTER_1TO1.pdf",
        "output/pdf/RC03_BOARD_DRILL_GUIDE_24X36_FULL_SIZE_1TO1.pdf",
        "drawings/board_hole_coordinates.csv",
        "FASTENER_MAP.csv",
    ),
    "13": (
        "config/tripod_camera_installation_intake_v1.json",
        "TRIPOD_CAMERA_INSTALLATION.md",
    ),
}
NON_ACTIONABLE_DIRECT_FILE_ACTIONS = {"reference_only", "DO_NOT_PRINT"}
DIRECT_ACTION_LABELS = {
    "complete": "Complete this controlled record",
    "inspect": "Inspect",
    "install_in_isolated_environment": "Install in an isolated environment",
    "print_actual_size": "Print at Actual Size / 100%",
    "print_or_verify": "Print or verify",
    "read": "Read",
    "reference_only": "Reference only",
    "run_from_project_root": "Run from the project root",
    "use": "Use",
    "use_with_helper": "Use with the named helper",
    "verify": "Verify",
    "verify_not_physical_release": "Verify digital record; not physical release",
    "view": "View",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def required_step_files(step: dict[str, Any]) -> tuple[str, ...]:
    """Return the exact generated file set for a step's visible layout."""
    if step["id"] == "01":
        return (*REQUIRED_STEP_FILES, STEP_DRILL_GUIDE_FILE)
    return REQUIRED_STEP_FILES


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generated_control_hashes(base: Path, relative_paths: Iterable[str]) -> dict[str, str]:
    return {
        relative: sha256(base / relative)
        for relative in relative_paths
        if (base / relative).is_file()
    }


def safe_generated_path(path: Path, expected_name: str) -> Path:
    resolved = path.resolve()
    if resolved.parent != ROOT.resolve() or resolved.name != expected_name:
        raise RuntimeError(f"Refusing generated-folder operation outside the exact target: {resolved}")
    return resolved


def remove_generated(path: Path, expected_name: str, require_sentinel: bool) -> None:
    resolved = safe_generated_path(path, expected_name)
    if not resolved.exists():
        return
    if require_sentinel and not (resolved / SENTINEL).is_file():
        raise RuntimeError(f"Refusing to remove unrecognized directory without {SENTINEL}: {resolved}")
    shutil.rmtree(resolved)


def remove_known_legacy_stl_copies(base: Path) -> None:
    """Remove only explicitly retired generated STL copies during an in-place overlay."""
    resolved_base = safe_generated_path(base, TARGET.name)
    if not (resolved_base / SENTINEL).is_file():
        raise RuntimeError(f"Refusing legacy cleanup without {SENTINEL}: {resolved_base}")
    for step_dir in resolved_base.iterdir():
        if not step_dir.is_dir() or not re.match(r"^\d{2}(?:_| - )", step_dir.name):
            continue
        stl_dir = step_dir / STEP_STL_DIRECTORY
        if not stl_dir.is_dir():
            continue
        resolved_stl_dir = stl_dir.resolve()
        for filename in LEGACY_GENERATED_STL_COPIES:
            candidate = stl_dir / filename
            if not candidate.exists():
                continue
            if candidate.is_dir() and not candidate.is_symlink():
                raise RuntimeError(f"Refusing to remove unexpected legacy directory: {candidate}")
            if candidate.resolve().parent != resolved_stl_dir:
                raise RuntimeError(f"Refusing legacy STL cleanup outside the exact step directory: {candidate}")
            candidate.unlink()


def markdown_link(label: str, from_dir: Path, target: Path) -> str:
    relative = Path(os.path.relpath(target, from_dir)).as_posix()
    return f"[{label}](<{relative}>)"


def step_stl_is_local_copy(step_id: str, filename: str) -> bool:
    """Return whether the tracked step package intentionally embeds this STL."""
    return step_id == "00" and filename not in STEP_00_CANONICAL_REFERENCE_STLS


def csv_write(path: Path, headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(list(headers))
        writer.writerows(rows)


def load_sources() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    config = read_json(CONFIG_PATH)
    jobs_doc = read_json(ROOT / "config" / "print_jobs.json")
    measurement = read_json(ROOT / "config" / "measurement_record.json")
    readiness = read_json(ROOT / "PRINT_READINESS.json")
    return config, jobs_doc, measurement, readiness


def resolve_pattern(pattern: str) -> list[Path]:
    matches = sorted(path for path in ROOT.glob(pattern) if path.is_file())
    if not matches:
        raise FileNotFoundError(f"Assembly-step mapping did not resolve any file: {pattern}")
    for path in matches:
        try:
            relative = path.resolve().relative_to(ROOT.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Mapped file escapes the project root: {path}") from exc
        if relative.parts and relative.parts[0] in {"BUILD_BY_STEP", "tmp"}:
            raise RuntimeError(f"Mapped file is generated/scratch, not canonical: {relative}")
    return matches


def add_file(
    records: dict[str, dict[str, Any]],
    path: Path,
    role: str,
    action: str,
    job_id: str | None = None,
) -> None:
    relative = path.relative_to(ROOT).as_posix()
    record = records.setdefault(
        relative,
        {
            "canonical_path": relative,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "roles": [],
            "actions": [],
            "job_ids": [],
        },
    )
    if role not in record["roles"]:
        record["roles"].append(role)
    if action not in record["actions"]:
        record["actions"].append(action)
    if job_id and job_id not in record["job_ids"]:
        record["job_ids"].append(job_id)


def files_for_step(step: dict[str, Any], jobs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for source, role, action in CORE_REFERENCES:
        path = ROOT / source
        if not path.is_file():
            raise FileNotFoundError(path)
        add_file(records, path, role, action)

    panel = step.get("panel")
    if panel:
        add_file(records, ROOT / panel, "assembly-step illustration", "view")

    print_action = step.get("print_action", "consume_accepted_output")
    for job_id in step.get("print_jobs", []):
        if job_id not in jobs:
            raise KeyError(f"Step {step['id']} references unknown print job {job_id}")
        job = jobs[job_id]
        plate = ROOT / "print_plates_3mf" / job["plate_file"]
        sidecar = plate.with_suffix(".print.json")
        settings = plate.with_name(f"{plate.stem}.PRINT_SETTINGS.md")
        sidecar_data = read_json(sidecar)
        process_preset = ROOT / sidecar_data["preset_contract"]["qidi_process_profile_file"]
        card = ROOT / "job_cards" / f"JOB-{job_id}.md"
        for path, role in (
            (plate, "geometry-only QIDI plate"),
            (sidecar, "controlled plate/profile/hash sidecar"),
            (settings, "exact operator print-settings sheet"),
            (process_preset, "importable QIDI Studio process preset"),
            (card, "controlled print traveler"),
        ):
            if not path.is_file():
                raise FileNotFoundError(path)
            add_file(records, path, role, print_action, job_id)
        for part in job["parts"]:
            stl = ROOT / "stl" / part
            step_path = ROOT / "cad" / "step" / f"{Path(part).stem}.step"
            if not stl.is_file() or not step_path.is_file():
                raise FileNotFoundError(f"Job {job_id} is missing its STL/STEP pair for {part}")
            add_file(records, stl, "canonical slicing mesh", "reference_only", job_id)
            add_file(records, step_path, "neutral CAD companion", "reference_only", job_id)

    for mapping in step.get("extra_files", []):
        for path in resolve_pattern(mapping["path"]):
            add_file(records, path, mapping["role"], mapping["action"])

    for record in records.values():
        record["roles"].sort()
        record["actions"].sort()
        record["job_ids"].sort()
    return [records[key] for key in sorted(records)]


def unique_required_inputs(step: dict[str, Any]) -> list[str]:
    """Return every configured physical-input statement once, in source order."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in step.get("required_inputs", []):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Step {step['id']} has an invalid required physical input")
        normalized = " ".join(value.split()).casefold()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(value.strip())
    return unique


def unique_hardware_rows(step: dict[str, Any]) -> list[dict[str, Any]]:
    """Return structured hardware/tool rows once without hiding distinct conditions."""
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in step.get("hardware", []):
        key = tuple(" ".join(str(row[field]).split()).casefold() for field in ("type", "qty", "item", "condition"))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def actionable_file_records(step: dict[str, Any], files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select concise, operator-actionable canonical records and fail on mapping gaps."""
    by_path = {record["canonical_path"]: record for record in files}
    selected_paths: set[str] = set()

    panel = step.get("panel")
    if panel:
        selected_paths.add(panel)

    for mapping in step.get("extra_files", []):
        if mapping["action"] in NON_ACTIONABLE_DIRECT_FILE_ACTIONS:
            continue
        selected_paths.update(path.relative_to(ROOT).as_posix() for path in resolve_pattern(mapping["path"]))

    if step["id"] != "00" and step.get("print_jobs"):
        selected_paths.add("JOB_KITS.csv")

    required_paths = set(DIRECT_FILE_REQUIREMENTS.get(step["id"], ()))
    selected_paths.update(required_paths)
    missing = sorted(path for path in selected_paths if path not in by_path)
    if missing:
        raise ValueError(
            f"Step {step['id']} cannot render direct operator links because its canonical file records "
            f"do not include: {missing}. Add a verified CORE_REFERENCES or extra_files mapping; do not invent a path."
        )
    return [by_path[path] for path in sorted(selected_paths)]


def compact_mm(value: str) -> str:
    """Render generated coordinate values without binary-float noise."""
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def render_step_print_settings_file(
    folder: Path,
    step: dict[str, Any],
    jobs: dict[str, dict[str, Any]],
) -> None:
    """Create one plain-language print-control index inside every step folder."""
    readiness_doc = read_json(ROOT / "PRINT_READINESS.json")
    readiness = {row["job_id"]: row["status"] for row in readiness_doc["jobs"]}
    job_ids = step.get("print_jobs", [])
    lines = [
        f"# Step {step['id']} — Print Settings for This Step",
        "",
        "**Generated control — do not edit. The linked canonical files and their hashes define the print setup.**",
        "",
    ]
    if not job_ids:
        lines.extend(
            [
                "## No printing in this step",
                "",
                "This step has no associated print job. Use only the accepted parts and assemblies named in the parts checklist and instructions.",
                "",
                "Do not substitute an STL from another step or create an untracked print.",
            ]
        )
        (folder / STEP_PRINT_SETTINGS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    if step["id"] == "00":
        lines.extend(
            [
                "## Print authority",
                "",
                "This is the only step that produces printed parts. Print a job only when its readiness below is **READY**. `WAITING` and `NOT_SELECTED` are STOP conditions.",
                "",
                "For each job: open the readable settings sheet, import its QIDI process JSON, select the separate exact filament preset, import the geometry-only 3MF at 100%, inspect the layer preview, and save a native QIDI Studio project in the active build evidence folder.",
            ]
        )
    else:
        lines.extend(
            [
                "## Traceability only — do not print here",
                "",
                "The jobs below identify the accepted Step-00 parts consumed by this assembly step. Do not print the convenience STL copies during assembly. A failed or missing part returns to Step 00 and its controlled job workflow.",
            ]
        )

    lines.extend(
        [
            "",
            "| Job | Authority | Material | Preset status | Plate | Exact readable settings | Machine sidecar | QIDI process import | Traveler |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for job_id in job_ids:
        job = jobs[job_id]
        plate = ROOT / "print_plates_3mf" / job["plate_file"]
        sidecar_path = plate.with_suffix(".print.json")
        sidecar = read_json(sidecar_path)
        contract = sidecar["preset_contract"]
        settings_path = plate.parent / contract["human_settings_file"]
        process_path = ROOT / contract["qidi_process_profile_file"]
        card = ROOT / "job_cards" / f"JOB-{job_id}.md"
        lines.append(
            f"| `{job_id}` | **{readiness.get(job_id, 'UNKNOWN')}** | "
            f"{sidecar['process_profile']['material']} | `{contract['preset_data_status']}` | "
            f"{markdown_link(plate.name, folder, plate)} | "
            f"{markdown_link(settings_path.name, folder, settings_path)} | "
            f"{markdown_link(sidecar_path.name, folder, sidecar_path)} | "
            f"{markdown_link(process_path.name, folder, process_path)} | "
            f"{markdown_link(card.name, folder, card)} |"
        )

    lines.extend(
        [
            "",
            "## Material rules",
            "",
            "- QIDI ABS Rapido jobs use the confirmed `QIDI ABS Rapido @Qidi X-Plus 4 0.4 nozzle` filament preset and the exact job-specific imported process profile.",
            "- PETG, TPU 95A, and ASA settings sheets intentionally show `EXACT_SPOOL_PRESET_REQUIRED` until the exact physical spool, drying record, calibrated flow, pressure advance, temperature, cooling, and volumetric limits are recorded. Do not guess these values.",
            "- Never compensate for ABS shrink or a failed fit by globally scaling an STL. Measure the matching coupon, update the controlled CAD parameter if required, regenerate, and revalidate.",
            "- The process JSON controls process settings only. The filament preset remains a separate QIDI Studio selection.",
        ]
    )
    (folder / STEP_PRINT_SETTINGS_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_board_drill_guide_file(folder: Path) -> None:
    """Write the Step-01 operator guide from the controlled coordinate schedule."""
    coordinate_path = ROOT / "drawings" / "board_hole_coordinates.csv"
    with coordinate_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required_fields = {
        "release_revision", "layout_sha256", "id", "type", "station", "x", "y",
        "right_edge_mm", "rear_edge_mm", "template_action",
    }
    if len(rows) != 13 or not rows or not required_fields.issubset(rows[0]):
        raise ValueError("board_hole_coordinates.csv must contain the controlled thirteen-feature schedule")
    if len({row["id"] for row in rows}) != 13:
        raise ValueError("board_hole_coordinates.csv contains duplicate or blank feature IDs")
    locator_count = sum(row["type"] == "locator_pin_blind" for row in rows)
    anchor_count = sum(row["type"] == "m4_retention_through" for row in rows)
    if (locator_count, anchor_count) != (4, 9):
        raise ValueError("board_hole_coordinates.csv must contain four locators and nine anchors")

    letter_path = ROOT / "output" / "pdf" / "RC03_BOARD_DRILL_GUIDE_LETTER_1TO1.pdf"
    full_path = ROOT / "output" / "pdf" / "RC03_BOARD_DRILL_GUIDE_24X36_FULL_SIZE_1TO1.pdf"
    layout_hashes = {row["layout_sha256"] for row in rows}
    revisions = {row["release_revision"] for row in rows}
    if len(layout_hashes) != 1 or len(revisions) != 1:
        raise ValueError("board_hole_coordinates.csv mixes layout hashes or release revisions")

    lines = [
        "# Step 01 — Print and Assemble the Board Drill Guide",
        "",
        "**Generated reference — do not edit this file. Use only the exact guide accepted in Step 00.**",
        "",
        "> **STOP:** The guide authorizes four locator bores and nine anchor center punches. It does not authorize drilling a tag, station outline, registration mark, dimension, or clamp no-drill area. The nine anchor bore sizes come only from the completed, qualified `FASTENER_MAP.csv`.",
        "",
        "## 1 — Choose exactly one physical guide",
        "",
        "| Choice | Open this controlled file | Use when |",
        "| --- | --- | --- |",
        f"| Tiled Letter guide | {markdown_link('RC03 Board Drill Guide — Letter 1:1', folder, letter_path)} | A normal Letter-size printer will produce the drilling field. |",
        f"| Single-sheet guide | {markdown_link('RC03 Board Drill Guide — 24 x 36 Full Size 1:1', folder, full_path)} | A print shop can produce one true 24 x 36 inch sheet without scaling. |",
        "",
        "Do not mix pages from these choices. Record the selected path, its SHA-256, the source-layout SHA-256, and the print settings in Step 00 before using it on the board.",
        "",
        "## 2A — Assemble the Letter guide",
        "",
        "1. Print one-sided at **Actual Size / 100 percent**. Disable Fit, Shrink, Crop, borderless enlargement, and duplex printing.",
        "2. Pages 1-3 are the overview, controlled schedule, and tile-assembly map. They are reference pages marked not for drilling.",
        "3. Pages 4-12 are the nine 1:1 drilling tiles. Arrange them in the printed 3 x 3 map on a clean, flat surface.",
        "4. Overlap every adjacent pair by the printed **12 mm** zones. Align the duplicated registration crosses and matching IDs before taping the seam.",
        "5. **Never butt paper edges or unprinted printer margins.** One butted seam introduces 12 mm of error; two can introduce 24 mm cumulatively.",
        "6. Tape without pulling or stretching the paper. Reject a wrinkled, damp, torn, distorted, or mismatched tile.",
        "",
        "## 2B — Prepare the full-size guide",
        "",
        "1. Print the single PDF page on true 24 x 36 inch media at **Actual Size / 100 percent**.",
        "2. Disable Fit, Shrink, Crop, and borderless enlargement. Confirm the print shop did not rescale to a different roll width or printable area.",
        "3. Keep the complete board outline, FRONT/origin labels, orientation arrow, and both independent scale controls visible.",
        "",
        "## 3 — Accept the physical print before transfer",
        "",
        "1. With a steel rule, measure the independent X and Y 100 mm controls on **every physical drilling sheet**. Both directions on every sheet must read **100.0 +/- 0.2 mm**.",
        "2. For a Letter guide, verify every matching registration cross and ID through both seams in both axes. For the full-size guide, verify the board-edge and orientation controls.",
        "3. Photograph every ruler check and the completed registration/edge check. A passed scale control proves print scale only; it is not a released hand-transfer position tolerance.",
        "4. If any control fails, discard the physical print and repeat Step 00 acceptance. Do not compensate by stretching paper or moving individual marks.",
        "",
        "## 4 — Register the guide to the board",
        "",
        "1. Confirm the cured board top, front-left origin, FRONT edge, +X/right, and +Y/rear.",
        "2. Align the printed 610 x 457 mm board outline with the physical board without stretching the guide. Confirm both opposite edges, the orientation arrow, the clamp no-drill area, and every TAG ONLY / NO DRILL symbol.",
        f"3. Open {markdown_link('the controlled thirteen-feature coordinate schedule', folder, coordinate_path)}. Cross-check each center from four directions: X from the left, X remainder from the right, Y from the front, and Y remainder from the rear.",
        "4. Do not average conflicting marks. If the paper center and edge measurements disagree, stop and correct registration before punching.",
        "5. Transfer exactly four **blue round locator centers** and nine **orange square anchor centers**. Photograph the registered guide and transferred centers before removing the paper.",
        "",
        "## 5 — Independent thirteen-center audit",
        "",
        f"Controlled revision: `{next(iter(revisions))}`  ",
        f"Coordinate-layout SHA-256: `{next(iter(layout_hashes))}`",
        "",
        "| ID | Station | X from left (mm) | Y from front (mm) | From right (mm) | From rear (mm) | Authorized operation |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        if row["type"] == "locator_pin_blind":
            operation = "Drill Ø6 mm blind, 15 mm nominal; never deeper than local thickness minus 2.0 mm"
        else:
            operation = "CENTER-PUNCH ONLY; final bore comes from the completed qualified FASTENER_MAP.csv"
        lines.append(
            f"| `{row['id']}` | {row['station']} | {compact_mm(row['x'])} | {compact_mm(row['y'])} | "
            f"{compact_mm(row['right_edge_mm'])} | {compact_mm(row['rear_edge_mm'])} | {operation} |"
        )
    lines.extend(
        [
            "",
            "`PT-HOLD-R1` and `PT-HOLD-R2` are each only 21.2 mm center-to-right-edge. Before drilling, physically prove that the selected anchor bore, flange, install face, and tool access preserve the board edge.",
            "",
            "## 6 — Drill in two controlled stages",
            "",
            "1. Remove all paper, then repeat the thirteen-center audit before a bit touches the board.",
            "2. Pilot and drill only the four locator bores. Use a square guide and positive stop; 15.0 mm is nominal, and the measured depth must never exceed local board thickness minus 2.0 mm. Inspect the underside after every bore.",
            "3. Complete and qualify all nine `FASTENER_MAP.csv` rows with the actual anchor manufacturer/part and scrap-board proof. The printed anchor target is a center reference, not a universal final bit diameter.",
            "4. Drill the nine anchor bores only with the recorded pilot/final bits and depth/through controls. Protect the two right-edge locations from breakout and veneer splitting.",
            "5. Temporarily install pins and anchors and perform the complete three-station, nine-retainer dry fit. Epoxy locator pins only after that full dry fit passes.",
            "",
            "> **Accuracy rule:** No numeric hand-transfer hole-position tolerance has been released. Scale bars, registration marks, and edge measurements are independent error checks; final physical compatibility still requires the complete station dry fit before epoxy or handoff.",
        ]
    )
    (folder / STEP_DRILL_GUIDE_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def canonical_input_hash(config: dict[str, Any], step_files: dict[str, list[dict[str, Any]]]) -> str:
    digest = hashlib.sha256()
    digest.update(CONFIG_PATH.relative_to(ROOT).as_posix().encode("utf-8"))
    digest.update(sha256(CONFIG_PATH).encode("ascii"))
    unique: dict[str, str] = {}
    for records in step_files.values():
        for record in records:
            unique[record["canonical_path"]] = record["sha256"]
    for relative, file_hash in sorted(unique.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(file_hash.encode("ascii"))
    digest.update(config["design_revision"].encode("utf-8"))
    return digest.hexdigest()


def package_definition_hash(
    config: dict[str, Any],
    jobs_doc: dict[str, Any],
    measurement: dict[str, Any],
    step_files: dict[str, list[dict[str, Any]]],
) -> str:
    """Hash design/package definitions while excluding mutable build evidence/state."""
    digest = hashlib.sha256()
    procedure_assets = {
        step.get("panel") for step in config.get("steps", []) if step.get("panel")
    }
    unique: dict[str, str] = {}
    for records in step_files.values():
        for record in records:
            relative = record["canonical_path"]
            if (
                relative not in procedure_assets
                and (relative in OPERATIONAL_PATHS or relative.startswith(OPERATIONAL_PREFIXES))
            ):
                continue
            unique[relative] = record["sha256"]
    for relative, file_hash in sorted(unique.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(file_hash.encode("ascii"))

    measurement_schema = {
        "schema_version": measurement.get("schema_version"),
        "design_revision": measurement.get("design_revision"),
        "printer": measurement.get("printer"),
        "test_context_fields": sorted(measurement.get("test_context", {})),
        # Route selection changes the required files, gates, and test rows, so it
        # is a build-definition decision rather than mutable test evidence.
        "selected_routes": measurement.get("selected_routes"),
        "gates": {
            gate_id: {
                "category": gate.get("category"),
                "scope": gate.get("scope"),
                "recorded_value_fields": sorted(gate.get("recorded_values", {})),
                "nominal_values": gate.get("nominal_values"),
                "evidence": gate.get("evidence"),
            }
            for gate_id, gate in sorted(measurement.get("gates", {}).items())
        },
    }
    lifecycle_schema = read_json(ROOT / "config" / "job_build_record.json")
    lifecycle_definition = {
        "schema_version": lifecycle_schema.get("schema_version"),
        "design_revision": lifecycle_schema.get("design_revision"),
        "lifecycle_states": lifecycle_schema.get("lifecycle_states"),
        "jobs": [
            {
                "job_id": row.get("job_id"),
                "kit_id": row.get("kit_id"),
                "postprint_gate_ids": row.get("postprint_gate_ids"),
                "assembly_gate_ids": row.get("assembly_gate_ids"),
            }
            for row in lifecycle_schema.get("jobs", [])
        ],
    }
    immutable_kit_columns = (
        "kit_id",
        "module",
        "route_requirement",
        "job_id",
        "job_stage",
        "printed_contents",
        "hardware_and_consumables",
        "acceptance_signoff",
        "storage_label",
    )
    with (ROOT / "JOB_KITS.csv").open(encoding="utf-8", newline="") as stream:
        kit_rows = list(csv.DictReader(stream))
    kit_definition = [
        {column: row.get(column) for column in immutable_kit_columns}
        for row in kit_rows
    ]
    immutable_fastener_columns = (
        "feature_id",
        "station",
        "world_x_mm",
        "world_y_mm",
        "fastener_role",
        "printed_stack_mm",
        "washer_qty",
        "board_anchor_qty",
        "hardware_class",
        "candidate_length",
        "acceptance",
    )
    with (ROOT / "FASTENER_MAP.csv").open(encoding="utf-8", newline="") as stream:
        fastener_rows = list(csv.DictReader(stream))
    fastener_definition = [
        {column: row.get(column) for column in immutable_fastener_columns}
        for row in fastener_rows
    ]
    for label, value in (
        ("assembly_config", config),
        ("print_jobs", jobs_doc),
        ("measurement_schema", measurement_schema),
        ("lifecycle_schema", lifecycle_definition),
        ("kit_definition", kit_definition),
        ("fastener_definition", fastener_definition),
    ):
        digest.update(label.encode("utf-8"))
        digest.update(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()


def gate_rows(gate_ids: list[str], measurement: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    gates = measurement["gates"]
    for gate_id in gate_ids:
        gate = gates[gate_id]
        rows.append((gate_id, gate["status"], gate.get("evidence", "")))
    return rows


def effective_gate_ids(step: dict[str, Any], key: str, measurement: dict[str, Any]) -> list[str]:
    """Return unconditional plus selected-route conditional gate IDs."""
    result = list(step.get(key, []))
    conditional = step.get(f"conditional_{key}", {})
    for route, gate_ids in conditional.items():
        if measurement["selected_routes"].get(route, False):
            result.extend(gate_ids)
    return list(dict.fromkeys(result))


def effective_acceptance(step: dict[str, Any], measurement: dict[str, Any]) -> list[dict[str, Any]]:
    """Return common acceptance rows plus rows for every selected route."""
    result = list(step.get("acceptance", []))
    for route, rows in step.get("conditional_acceptance", {}).items():
        if measurement["selected_routes"].get(route, False):
            result.extend(rows)
    return result


def blocker_description(gate_id: str, measurement: dict[str, Any]) -> str:
    if gate_id.startswith("prerequisite_step:"):
        step_id = gate_id.split(":", 1)[1]
        return f"Complete and sign Step {step_id} for the active build ID before this step can start."
    if gate_id.startswith("evidence_error:"):
        return "Active-build evidence is invalid or stale: " + gate_id.split(":", 1)[1]
    if gate_id.startswith("completion_gate:"):
        completion_id = gate_id.split(":", 1)[1]
        return (
            f"Previously signed work has been reopened because completion gate `{completion_id}` "
            "is no longer PASS. Correct/retest it before continuing."
        )
    if gate_id.startswith("select_one_route:"):
        routes = gate_id.split(":", 1)[1].replace("|", " or ")
        return f"Select at least one tool route in the canonical measurement record ({routes})."
    gate = measurement["gates"].get(gate_id, {})
    evidence = str(gate.get("evidence", "Complete and record the required physical verification.")).strip()
    return f"{evidence} (gate `{gate_id}`)"


def display_state(state: str) -> str:
    return state.replace("_", " ")


def route_selection_guidance(heading: str) -> list[str]:
    """Render three explicit route decisions as valid, copyable commands."""
    rows = [
        ("Phone stylus tool", "phone_stylus_route"),
        ("Keyboard rod tool", "keyboard_rod_route"),
        ("Fixed-mast camera fallback only (not the arm-camera route)", "camera_mast_optional"),
    ]
    lines = [
        heading,
        "",
        "Record an explicit `yes` or `no` for all three routes before releasing route-dependent jobs. Run exactly one command from each row; do not rely on a default value.",
        "",
        "| Decision | Select this route | Do not select this route |",
        "| --- | --- | --- |",
    ]
    for label, route in rows:
        lines.append(
            f"| {label} | `python scripts/record_print_measurement.py --route {route} --selected yes` | "
            f"`python scripts/record_print_measurement.py --route {route} --selected no` |"
        )
    lines.extend(
        [
            "",
            "At least one tool route—`phone_stylus_route` or `keyboard_rod_route`—must be `yes`. `camera_mast_optional` refers only to the independent fixed eye-to-hand fallback, never the intended arm-mounted camera. Its `yes` value records qualification scope only; it does not authorize printing. Jobs 03C3, 06, 07A, and 07B remain blocked until `fixed_camera_fallback_architecture_released` is PASS against the exact controlled camera-decision hash.",
        ]
    )
    return lines


def evidence_value_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, dict):
        return not value or any(evidence_value_blank(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return not value or any(evidence_value_blank(item) for item in value)
    return False


def valid_build_id(value: Any) -> bool:
    if not isinstance(value, str) or BUILD_ID_PATTERN.fullmatch(value) is None:
        return False
    if value.endswith(".") or value.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        return False
    return value != "BUILD_ID_TEMPLATE"


def load_active_build(base: Path | None) -> dict[str, Any]:
    default = {"schema_version": 1, "active_build_id": None}
    if base is None:
        return default
    path = base / ACTIVE_BUILD_FILE
    if not path.is_file():
        return default
    try:
        value = read_json(path)
    except (OSError, json.JSONDecodeError):
        return {**default, "configuration_error": f"{ACTIVE_BUILD_FILE} is unreadable"}
    if not isinstance(value, dict):
        return {**default, "configuration_error": f"{ACTIVE_BUILD_FILE} root must be an object"}
    build_id = value.get("active_build_id")
    if value.get("schema_version") != 1:
        return {**default, "configuration_error": f"{ACTIVE_BUILD_FILE} schema_version must be 1"}
    if build_id is not None and not valid_build_id(build_id):
        return {
            **default,
            "configuration_error": (
                "active_build_id must start with a letter/digit, use only letters, digits, dot, "
                "underscore, or hyphen, be 1-80 characters, and not be a reserved Windows name"
            ),
        }
    return {"schema_version": 1, "active_build_id": build_id}


def read_active_signoff(
    step_dir: Path | None,
    step: dict[str, Any],
    measurement: dict[str, Any],
    active_build_id: str | None,
    definition_hash: str,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Load and validate only this step's exact active-build evidence."""
    if step_dir is None or not active_build_id:
        return None, []
    evidence_root, evidence_root_errors = locate_evidence_root(step_dir)
    if evidence_root_errors:
        return None, evidence_root_errors
    if evidence_root is None:
        return None, []
    build_dir = evidence_root / active_build_id
    if not build_dir.is_dir():
        return None, []
    signoff_path = build_dir / "signoff.json"
    measurement_path = build_dir / "measurement_record.json"
    if not signoff_path.is_file() or not measurement_path.is_file():
        return None, ["active build folder is missing measurement_record.json or signoff.json"]
    try:
        signoff = read_json(signoff_path)
        local_measurement = read_json(measurement_path)
    except (OSError, json.JSONDecodeError):
        return None, ["active build evidence JSON is unreadable"]
    if not isinstance(signoff, dict) or not isinstance(local_measurement, dict):
        return None, ["active build evidence JSON roots must be objects"]

    errors: list[str] = []
    expected_ids = [item["test_id"] for item in effective_acceptance(step, measurement)]
    snapshots: list[str] = []
    for label, value in (("signoff", signoff), ("measurement record", local_measurement)):
        if value.get("schema_version") != 1:
            errors.append(f"{label} schema_version is not 1")
        if value.get("build_id") != active_build_id:
            errors.append(f"{label} build_id does not match ACTIVE_BUILD.json")
        if value.get("step_id") != step["id"]:
            errors.append(f"{label} step_id is not {step['id']}")
        if value.get("design_revision") != measurement.get("design_revision"):
            errors.append(f"{label} revision is stale")
        if value.get("package_definition_hash") != definition_hash:
            errors.append(f"{label} package definition hash is stale")
        snapshot = value.get("canonical_snapshot_hash")
        if not isinstance(snapshot, str) or re.fullmatch(r"[0-9a-f]{64}", snapshot) is None:
            errors.append(f"{label} canonical snapshot hash is missing or malformed")
        else:
            snapshots.append(snapshot)
        if value.get("canonical_input_hash") != snapshot:
            errors.append(f"{label} legacy canonical input hash alias does not match its snapshot")
    if len(snapshots) == 2 and snapshots[0] != snapshots[1]:
        errors.append("signoff and measurement record originate from different canonical snapshots")

    status = signoff.get("status")
    if not isinstance(status, str) or status not in {"NOT_STARTED", "IN_PROGRESS", "HOLD", "PASS"}:
        errors.append("signoff status is invalid")
    if signoff.get("required_test_ids") != expected_ids:
        errors.append("signoff required_test_ids do not match the current route/step")
    accepted_value = signoff.get("accepted_test_ids")
    accepted = accepted_value if isinstance(accepted_value, list) else []
    if (
        not isinstance(accepted_value, list)
        or any(not isinstance(item, str) for item in accepted)
        or not set(accepted).issubset(expected_ids)
        or len(accepted) != len(set(accepted))
    ):
        errors.append("signoff accepted_test_ids contain invalid IDs")
    holds_value = signoff.get("open_holds")
    holds = holds_value if isinstance(holds_value, list) else []
    if (
        not isinstance(holds_value, list)
        or any(not isinstance(item, str) or evidence_value_blank(item) for item in holds)
    ):
        errors.append("signoff open_holds must be a list of non-blank strings")

    rows_value = local_measurement.get("measurements")
    rows = rows_value if isinstance(rows_value, list) and all(isinstance(row, dict) for row in rows_value) else []
    if not isinstance(rows_value, list) or len(rows) != len(rows_value) or [row.get("test_id") for row in rows] != expected_ids:
        errors.append("measurement rows do not match the current required test IDs")
        rows = []
    for row in rows:
        row_result = row.get("result")
        if not isinstance(row_result, str) or row_result not in {"NOT_TESTED", "PASS", "FAIL"}:
            errors.append(f"test {row.get('test_id')} has an invalid result")
        if not isinstance(row.get("evidence_files"), list):
            errors.append(f"test {row.get('test_id')} evidence_files must be a list")

    started_identity_valid = (
        isinstance(local_measurement.get("operator"), str)
        and not evidence_value_blank(local_measurement.get("operator"))
        and isinstance(local_measurement.get("started_at"), str)
        and not evidence_value_blank(local_measurement.get("started_at"))
    )
    if isinstance(status, str) and status in {"IN_PROGRESS", "HOLD", "PASS"} and not started_identity_valid:
        errors.append(f"{status} measurement record lacks operator or started_at")

    if status == "PASS":
        if set(accepted) != set(expected_ids) or len(accepted) != len(expected_ids):
            errors.append("PASS does not accept every required test ID exactly once")
        if holds:
            errors.append("PASS has unresolved open_holds")
        if (
            not isinstance(signoff.get("operator"), str)
            or evidence_value_blank(signoff.get("operator"))
            or not isinstance(signoff.get("signed_at"), str)
            or evidence_value_blank(signoff.get("signed_at"))
        ):
            errors.append("PASS lacks operator or signed_at")
        for row in rows:
            if row.get("result") != "PASS":
                errors.append(f"test {row.get('test_id')} is not PASS")
                continue
            if (
                evidence_value_blank(row.get("value_or_observation"))
                or not isinstance(row.get("unit"), str)
                or evidence_value_blank(row.get("unit"))
                or not isinstance(row.get("instrument_id"), str)
                or evidence_value_blank(row.get("instrument_id"))
            ):
                errors.append(f"test {row.get('test_id')} lacks value/unit/instrument")
            evidence_files = row.get("evidence_files")
            if not isinstance(evidence_files, list) or not evidence_files:
                errors.append(f"test {row.get('test_id')} lacks linked evidence")
                continue
            for evidence_file in evidence_files:
                if not isinstance(evidence_file, str) or not evidence_file.strip():
                    errors.append(f"test {row.get('test_id')} has an invalid evidence path")
                    continue
                try:
                    candidate = Path(evidence_file)
                    if candidate.is_absolute():
                        errors.append(f"test {row.get('test_id')} evidence must be relative to its build-ID folder")
                        continue
                    resolved = (build_dir / candidate).resolve()
                    resolved_build_dir = build_dir.resolve()
                except (OSError, ValueError):
                    errors.append(f"test {row.get('test_id')} has an invalid evidence path")
                    continue
                try:
                    resolved.relative_to(resolved_build_dir)
                except ValueError:
                    errors.append(f"test {row.get('test_id')} evidence path escapes its build-ID folder")
                    continue
                try:
                    exists = resolved.is_file()
                except (OSError, ValueError):
                    errors.append(f"test {row.get('test_id')} has an invalid evidence path")
                    continue
                if not exists:
                    errors.append(f"test {row.get('test_id')} linked evidence file does not exist: {evidence_file}")
    elif status == "IN_PROGRESS" and holds:
        errors.append("IN_PROGRESS has open holds; use HOLD status")
    elif status == "HOLD" and not holds:
        errors.append("HOLD requires at least one non-blank open_holds entry")
    elif status == "NOT_STARTED":
        if holds or accepted:
            errors.append("NOT_STARTED must have no accepted tests or open holds")
        if not evidence_value_blank(local_measurement.get("operator")) or not evidence_value_blank(
            local_measurement.get("started_at")
        ):
            errors.append("NOT_STARTED measurement record may not contain operator/start time")
        if any(
            not evidence_value_blank(signoff.get(field))
            for field in ("operator", "witness", "signed_at")
        ):
            errors.append("NOT_STARTED signoff signature fields must be blank")
        for row in rows:
            if (
                row.get("result") != "NOT_TESTED"
                or not evidence_value_blank(row.get("value_or_observation"))
                or not evidence_value_blank(row.get("unit"))
                or not evidence_value_blank(row.get("instrument_id"))
                or bool(row.get("evidence_files"))
            ):
                errors.append(f"NOT_STARTED contains populated test row {row.get('test_id')}")

    return (signoff if not errors else None), errors


def compute_state(
    step: dict[str, Any],
    measurement: dict[str, Any],
    preserved_dir: Path | None,
    prerequisite_states: dict[str, tuple[str, list[str]]],
    active_build_id: str | None,
    definition_hash: str,
) -> tuple[str, list[str]]:
    gates = measurement["gates"]
    required_routes = step.get("requires_any_route", [])
    route_block = []
    if required_routes and not any(measurement["selected_routes"].get(route, False) for route in required_routes):
        route_block = ["select_one_route:" + "|".join(required_routes)]
    input_gates = effective_gate_ids(step, "input_gates", measurement)
    signoff, evidence_errors = read_active_signoff(
        preserved_dir, step, measurement, active_build_id, definition_hash
    )
    if evidence_errors:
        return "HOLD", [f"evidence_error:{error}" for error in evidence_errors]
    prerequisite_block = [
        f"prerequisite_step:{step_id}"
        for step_id in step.get("prerequisite_steps", [])
        if prerequisite_states.get(step_id, ("LOCKED", []))[0] != "COMPLETE"
    ]
    blocked = prerequisite_block + route_block + [
        gate_id for gate_id in input_gates if gates[gate_id]["status"] != "PASS"
    ]
    if blocked:
        started = signoff and signoff.get("status") in {"IN_PROGRESS", "HOLD", "PASS"}
        return ("HOLD" if started else "LOCKED"), blocked
    if signoff and signoff["status"] == "HOLD":
        return "HOLD", []
    if signoff and signoff["status"] == "IN_PROGRESS":
        return "IN_PROGRESS", []
    completion = effective_gate_ids(step, "completion_gates", measurement)
    completion_routes = step.get("completion_requires_any_route", [])
    completion_route_selected = not completion_routes or any(
        measurement["selected_routes"].get(route, False) for route in completion_routes
    )
    complete = completion_route_selected and all(
        gates[gate_id]["status"] == "PASS" for gate_id in completion
    )
    if complete and signoff and signoff["status"] == "PASS":
        return "COMPLETE", []
    if signoff and signoff["status"] == "PASS":
        reopened = [
            f"completion_gate:{gate_id}"
            for gate_id in completion
            if gates[gate_id]["status"] != "PASS"
        ]
        if not completion_route_selected:
            reopened.append("select_one_route:" + "|".join(completion_routes))
        return "HOLD", reopened
    return "READY_TO_START", []


def ensure_evidence_template(
    evidence_dir: Path,
    step: dict[str, Any],
    measurement: dict[str, Any],
    canonical_hash: str,
    definition_hash: str,
    active_build_id: str | None,
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    acceptance_rows = effective_acceptance(step, measurement)
    example_test_id = acceptance_rows[0]["test_id"] if acceptance_rows else f"{step['id']}-A"
    readme = evidence_dir / STEP_EVIDENCE_README
    readme.write_text(
        "# Save measurements and photos here\n\n"
        "This is the only operator-writable area in this generated step package. Step-local records are the raw source record; they do **not** automatically update the reviewed project gates or print-job lifecycle.\n\n"
        "1. At Step 00, choose one unique build ID such as `2026-08-31_CELL-A`; use exactly that folder name throughout the build.\n"
        f"2. Do not initialize this folder while the step is locked. When `{STEP_START_FILE}` reports `READY TO START`, follow the root `{ROOT_EVIDENCE_FILE}` workflow exactly; the controlled initializer refuses to overwrite evidence.\n"
        f"3. Save each original photo, native QIDI project, calibration output, or report inside the copied build-ID folder before recording it. Every `--evidence` value must be relative to that build-ID folder, remain contained within it, and name a file that already exists. Neither `{MEASUREMENT_RECORD_FILE}` nor `{SIGNOFF_RECORD_FILE}` may cite itself as physical evidence.\n"
        f"4. From the project root, record each pre-populated test with the controlled helper. Example: `python scripts/record_step_result.py --step {step['id']} --test {example_test_id} --value \"REPLACE_WITH_VALUE_OR_OBSERVATION\" --unit \"REPLACE_WITH_UNIT_OR_NA\" --instrument \"REPLACE_WITH_TOOL_ID_OR_METHOD\" --evidence \"photos/{example_test_id}.jpg\" --result PASS --operator \"REPLACE_WITH_NAME\"`. Repeat `--evidence` for additional files; use `--notes` for useful context.\n"
        f"5. Use `{MEASUREMENTS_CHECKLIST_FILE}` to confirm that every required test ID was recorded. Then copy supported reviewed gate results into `config/measurement_record.json` with `scripts/record_print_measurement.py`; cite this build-ID evidence path. Do not mark a canonical gate PASS while any required value is blank.\n"
        "6. For Step 00 print jobs, advance `config/job_build_record.json` only in lifecycle order and only after the matching state evidence exists; then regenerate the tracker and job cards.\n"
        f"7. Follow `{FINISH_SIGNOFF_FILE}`. For PASS, run `python scripts/sign_off_step.py --step {step['id']} --status PASS --operator \"REPLACE_WITH_NAME\"`; add `--witness \"REPLACE_WITH_NAME\"` when required. The helper derives accepted test IDs and refuses incomplete or invalid rows.\n"
        f"8. To stop with a documented hold, run `python scripts/sign_off_step.py --step {step['id']} --status HOLD --operator \"REPLACE_WITH_NAME\" --hold \"REPLACE_WITH_REASON\"`; repeat `--hold` for separate reasons.\n"
        f"9. Raw edits to `{MEASUREMENT_RECORD_FILE}` or `{SIGNOFF_RECORD_FILE}` are an advanced recovery fallback only. Normal recording and signoff use the helpers above so containment, schema, and completeness checks cannot be skipped.\n"
        "10. Regeneration preserves actual build-ID folders but refreshes `BUILD_ID_TEMPLATE/` to the current package-definition and canonical-snapshot hashes.\n\n"
        f"See the root `{ROOT_EVIDENCE_FILE}` for the exact synchronization sequence.\n",
        encoding="utf-8",
    )
    template = evidence_dir / EVIDENCE_TEMPLATE_DIRECTORY
    template.mkdir(exist_ok=True)
    measurement_path = template / MEASUREMENT_RECORD_FILE
    write_json(
        measurement_path,
        {
            "schema_version": 1,
            "design_revision": "RC03-INT-R1",
            "package_definition_hash": definition_hash,
            "canonical_snapshot_hash": canonical_hash,
            "canonical_input_hash": canonical_hash,
            "step_id": step["id"],
            "build_id": active_build_id or "REPLACE_WITH_UNIQUE_BUILD_ID",
            "operator": None,
            "started_at": None,
            "instrument_ids": [],
            "measurements": [
                {
                    "test_id": item["test_id"],
                    "criterion": item["criterion"],
                    "value_or_observation": None,
                    "unit": None,
                    "instrument_id": None,
                    "evidence_files": [],
                    "result": "NOT_TESTED",
                    "notes": None,
                }
                for item in acceptance_rows
            ],
            "evidence_files": [],
            "corrections_and_retests": [],
        },
    )
    signoff_path = template / SIGNOFF_RECORD_FILE
    write_json(
        signoff_path,
        {
            "schema_version": 1,
            "design_revision": "RC03-INT-R1",
            "package_definition_hash": definition_hash,
            "canonical_snapshot_hash": canonical_hash,
            "canonical_input_hash": canonical_hash,
            "step_id": step["id"],
            "build_id": active_build_id or "REPLACE_WITH_UNIQUE_BUILD_ID",
            "status": "NOT_STARTED",
            "required_test_ids": [item["test_id"] for item in acceptance_rows],
            "accepted_test_ids": [],
            "open_holds": [],
            "operator": None,
            "witness": None,
            "signed_at": None,
        },
    )
    for directory, purpose in (
        ("photos", "Place original, uncropped evidence photos here."),
        ("qidi", "Place native QIDI Studio project files and layer-preview captures here."),
        ("reports", "Place calibration, force, motion, and exported measurement reports here."),
    ):
        target = template / directory
        target.mkdir(exist_ok=True)
        note = target / "README.md"
        if not note.exists():
            note.write_text(f"# {directory.title()}\n\n{purpose}\n", encoding="utf-8")
    if step["id"] == "13":
        for relative, purpose in (
            ("photos/charuco", "Store 20-30 accepted full-resolution ChArUco calibration captures here."),
            ("photos/fov", "Store at least 20 named full-resolution field-of-view acceptance poses here."),
        ):
            target = template / relative
            target.mkdir(parents=True, exist_ok=True)
            (target / "README.md").write_text(f"# {target.name.title()}\n\n{purpose}\n", encoding="utf-8")

    checklist_lines = [
        f"# Step {step['id']} — Measurements Checklist",
        "",
        "Use the copy inside your active build-ID folder as a work aid; never edit this generated template.",
        "",
        f"Record authoritative results with `scripts/record_step_result.py`; it safely updates `{MEASUREMENT_RECORD_FILE}`. Raw JSON editing is an advanced recovery fallback only.",
        "",
        f"Every `--evidence` path must be relative to the build-ID folder, remain contained within that folder, and point to an existing regular file. Neither `{MEASUREMENT_RECORD_FILE}` nor `{SIGNOFF_RECORD_FILE}` is physical evidence. Repeat `--evidence` when one test has multiple files.",
        "",
        "Command form:",
        "",
        f"`python scripts/record_step_result.py --step {step['id']} --test TEST_ID --value \"VALUE_OR_OBSERVATION\" --unit \"UNIT_OR_NA\" --instrument \"TOOL_ID_OR_METHOD\" --evidence \"photos/EXISTING_FILE.jpg\" --result PASS --operator \"OPERATOR_NAME\"`",
        "",
    ]
    for item in acceptance_rows:
        checklist_lines.extend(
            [
                f"## {item['test_id']} — {item['criterion']}",
                "",
                f"- Method: {item['method']}",
                f"- Pass limit: {item['limit']}",
                f"- Required evidence: {item['evidence']}",
                "- Required record: value or observation",
                "- Required record: unit and instrument ID",
                "- Required record: original evidence file path",
                "- Required record: PASS or FAIL result",
                "",
            ]
        )
    (template / MEASUREMENTS_CHECKLIST_FILE).write_text("\n".join(checklist_lines) + "\n", encoding="utf-8")

    signoff_lines = [
        f"# Step {step['id']} — Finish and Sign Off",
        "",
        "Use the copy inside your active build-ID folder as a work aid; never edit this generated template.",
        "",
        f"Use `scripts/sign_off_step.py` to update the authoritative `{SIGNOFF_RECORD_FILE}`. Raw JSON editing is an advanced recovery fallback only.",
        "",
        "- Required result: every required test row is complete and PASS",
        "- Required result: every original measurement/photo/report path is recorded",
        "- Required result: applicable reviewed project gates are PASS",
        "- Required result: corrections and retests are preserved",
        "- Required result: `open_holds` is empty",
        "- Required result: operator, witness when required, and signed time are recorded",
        "",
        f"PASS command: `python scripts/sign_off_step.py --step {step['id']} --status PASS --operator \"OPERATOR_NAME\"` (add `--witness \"WITNESS_NAME\"` when required).",
        "",
        f"HOLD command: `python scripts/sign_off_step.py --step {step['id']} --status HOLD --operator \"OPERATOR_NAME\" --hold \"REASON\"` (repeat `--hold` for separate reasons).",
        "",
        "The PASS helper derives accepted test IDs and refuses incomplete or invalid rows. If any item is incomplete, record HOLD and do not continue to the next step.",
    ]
    (template / FINISH_SIGNOFF_FILE).write_text("\n".join(signoff_lines) + "\n", encoding="utf-8")


def step_folder_name(step: dict[str, Any]) -> str:
    """Return the explicit, stable operator-facing folder name for one step."""
    value = step.get("operator_folder")
    if not isinstance(value, str) or not value.startswith(f"{step['id']} - "):
        raise ValueError(f"Step {step['id']} has an invalid operator_folder")
    if any(character in value for character in '<>:"/\\|?*') or value.endswith((" ", ".")):
        raise ValueError(f"Step {step['id']} operator_folder is not Windows-safe: {value!r}")
    return value


def plain_model_name(filename: str) -> str:
    """Make a mesh basename readable without changing the controlled filename."""
    words = Path(filename).stem.replace("_", " ").replace("-", " ").split()
    replacements = {
        "tcp": "TCP",
        "tpu": "TPU",
        "usb": "USB",
        "m3": "M3",
        "m4": "M4",
        "m5": "M5",
        "2020": "2020",
    }
    return " ".join(replacements.get(word.lower(), word.capitalize()) for word in words)


def direct_action_label(action: str) -> str:
    return DIRECT_ACTION_LABELS.get(action, action.replace("_", " ").capitalize())


def locate_evidence_root(step_dir: Path) -> tuple[Path | None, list[str]]:
    """Find a v2 or legacy evidence root without ever merging two histories."""
    candidates = [step_dir / STEP_EVIDENCE_DIRECTORY, step_dir / LEGACY_EVIDENCE_DIRECTORY]
    existing = [path for path in candidates if path.is_dir()]
    if len(existing) > 1:
        return None, [
            f"step folder contains both {STEP_EVIDENCE_DIRECTORY!r} and legacy "
            f"{LEGACY_EVIDENCE_DIRECTORY!r}; refuse to merge evidence histories"
        ]
    return (existing[0] if existing else None), []


def copy_preserved_evidence(preserved_step_dir: Path | None, destination: Path) -> None:
    """Copy one evidence history exactly while removing only the v1 generated read-me."""
    if preserved_step_dir is None:
        return
    source, errors = locate_evidence_root(preserved_step_dir)
    if errors:
        raise RuntimeError("; ".join(errors))
    if source is None:
        return
    if destination.exists():
        raise RuntimeError(f"Refusing to merge preserved evidence into existing destination: {destination}")
    shutil.copytree(source, destination)
    generated_template = destination / EVIDENCE_TEMPLATE_DIRECTORY
    if generated_template.is_dir():
        shutil.rmtree(generated_template)
    elif generated_template.exists():
        raise RuntimeError(f"Preserved evidence template path is not a directory: {generated_template}")
    if source.name == LEGACY_EVIDENCE_DIRECTORY:
        legacy_generated_readme = destination / "README.md"
        if legacy_generated_readme.is_file():
            legacy_generated_readme.unlink()


def step_manifest_path(step_dir: Path) -> Path | None:
    """Locate a current or v1 manifest in an existing generated step folder."""
    candidates = [step_dir / STEP_MANIFEST_FILE, step_dir / "STEP_MANIFEST.json"]
    existing = [path for path in candidates if path.is_file()]
    if len(existing) > 1:
        raise RuntimeError(f"Ambiguous manifests in preserved step folder: {step_dir}")
    return existing[0] if existing else None


def preserved_steps_by_id(base: Path | None) -> dict[str, Path]:
    """Resolve preserved folders by immutable step_id, independent of display names."""
    if base is None or not base.is_dir():
        return {}
    result: dict[str, Path] = {}
    for directory in sorted((path for path in base.iterdir() if path.is_dir()), key=lambda path: path.name):
        manifest_path = step_manifest_path(directory)
        if manifest_path is None:
            if re.match(r"^\d{2}(?:_| - )", directory.name):
                raise RuntimeError(f"Cannot migrate generated step folder without a manifest: {directory}")
            continue
        try:
            manifest = read_json(manifest_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot migrate unreadable step manifest {manifest_path}: {exc}") from exc
        step_id = manifest.get("step_id") if isinstance(manifest, dict) else None
        if not isinstance(step_id, str) or re.fullmatch(r"\d{2}", step_id) is None:
            raise RuntimeError(f"Cannot migrate step folder with invalid step_id: {manifest_path}")
        if step_id in result:
            raise RuntimeError(
                f"Cannot migrate duplicate Step {step_id} folders: {result[step_id]} and {directory}"
            )
        result[step_id] = directory
    return result


def generated_layout_version(base: Path | None) -> int | None:
    """Read the generated layout version without trusting mutable display names."""
    if base is None or not base.is_dir():
        return None
    index_path = base / "INDEX.json"
    if index_path.is_file():
        try:
            value = read_json(index_path)
        except (OSError, UnicodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict) and isinstance(value.get("layout_version"), int):
            return value["layout_version"]
    sentinel_path = base / SENTINEL
    if sentinel_path.is_file():
        match = re.search(r"^layout_version=(\d+)$", sentinel_path.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return int(match.group(1))
    # Recognized packages created before layout versioning are layout v1.
    return 1 if sentinel_path.is_file() else None


def render_step(
    base: Path,
    step: dict[str, Any],
    files: list[dict[str, Any]],
    jobs: dict[str, dict[str, Any]],
    measurement: dict[str, Any],
    canonical_hash: str,
    definition_hash: str,
    state: str,
    blocked_gates: list[str],
    next_step: dict[str, Any] | None,
    preserved_step_dir: Path | None,
    generated_at: str,
    active_build_id: str | None,
) -> dict[str, Any]:
    folder = base / step_folder_name(step)
    folder.mkdir(parents=True)
    technical_dir = folder / STEP_TECHNICAL_DIRECTORY
    technical_dir.mkdir()
    stl_dir = folder / STEP_STL_DIRECTORY
    stl_dir.mkdir()

    copy_preserved_evidence(preserved_step_dir, folder / STEP_EVIDENCE_DIRECTORY)
    ensure_evidence_template(
        folder / STEP_EVIDENCE_DIRECTORY, step, measurement, canonical_hash, definition_hash, active_build_id
    )
    active_signoff, active_evidence_errors = read_active_signoff(
        folder, step, measurement, active_build_id, definition_hash
    )
    active_signoff_status = (
        active_signoff.get("status", "NOT_STARTED")
        if active_signoff
        else ("INVALID — HOLD" if active_evidence_errors else "NOT_STARTED")
    )
    active_open_holds = active_signoff.get("open_holds", []) if active_signoff else []

    job_rows = []
    for job_id in step.get("print_jobs", []):
        job = jobs[job_id]
        plate_path = ROOT / "print_plates_3mf" / job["plate_file"]
        sidecar = read_json(plate_path.with_suffix(".print.json"))
        contract = sidecar["preset_contract"]
        job_rows.append(
            {
                "job_id": job_id,
                "action": step["print_action"],
                "stage": job["stage"],
                "selection": job["selection"],
                "profile": job["profile"],
                "plate_file": job["plate_file"],
                "settings_file": contract["human_settings_file"],
                "settings_sha256": contract["human_settings_sha256"],
                "qidi_process_profile_file": contract["qidi_process_profile_file"],
                "qidi_process_profile_sha256": contract["qidi_process_profile_sha256"],
                "filament_preset": contract["filament_preset_name"],
                "preset_data_status": contract["preset_data_status"],
                "parts": job["parts"],
                "purpose": job["purpose"],
            }
        )

    stl_records: list[dict[str, Any]] = []
    for record in files:
        canonical_path = record["canonical_path"]
        if not canonical_path.startswith("stl/") or not canonical_path.lower().endswith(".stl"):
            continue
        source = ROOT / canonical_path
        if "DO_NOT_PRINT" in record["actions"] or "DO_NOT_PRINT" in source.name:
            usage = "DO_NOT_PRINT"
        elif step["id"] == "00":
            usage = "PRINT_VIA_READY_JOB_ONLY"
        else:
            usage = "TRACEABILITY_ONLY_DO_NOT_PRINT"
        record["local_copy_usage"] = usage
        if step_stl_is_local_copy(step["id"], source.name):
            destination = stl_dir / source.name
            shutil.copy2(source, destination)
            copied_hash = sha256(destination)
            if copied_hash != record["sha256"]:
                raise RuntimeError(f"STL copy hash mismatch for {canonical_path}")
            record["local_operator_copy"] = destination.relative_to(folder).as_posix()
            record["local_copy_sha256"] = copied_hash
            record["artifact_resolution"] = "local_hash_verified_copy"
        else:
            record["canonical_reference"] = Path(
                os.path.relpath(source, stl_dir)
            ).as_posix()
            record["artifact_resolution"] = "canonical_hash_bound_reference"
        stl_records.append(record)

    csv_write(
        stl_dir / STEP_STL_CATALOG,
        (
            "file",
            "plain_name",
            "use",
            "job_ids",
            "profiles",
            "quantity_by_job",
            "selections",
            "canonical_path",
            "sha256",
            "artifact_resolution",
        ),
        (
            (
                Path(row["canonical_path"]).name,
                plain_model_name(Path(row["canonical_path"]).name),
                row["local_copy_usage"],
                "; ".join(row["job_ids"]),
                "; ".join(dict.fromkeys(jobs[job_id]["profile"] for job_id in row["job_ids"])),
                "; ".join(
                    f"{job_id}:{jobs[job_id]['parts'].get(Path(row['canonical_path']).name, 0)}"
                    for job_id in row["job_ids"]
                ),
                "; ".join(dict.fromkeys(jobs[job_id]["selection"] for job_id in row["job_ids"])),
                row["canonical_path"],
                row["sha256"],
                row["artifact_resolution"],
            )
            for row in stl_records
        ),
    )
    if stl_records:
        stl_lines = [
            "# STL files for this step",
            "",
            (
                "Step 00 uses a governed mix of small generated convenience copies and hash-bound "
                "links to the authoritative project-level `stl/` files. Steps 01–15 use only "
                "hash-bound links and intentionally contain no duplicate STL bytes."
            ),
            "",
            "## Rules",
            "",
            "- Print only when the step and job card explicitly say to print. Assembly Steps 01-15 normally consume parts already accepted in Step 00.",
            "- Never globally scale or auto-repair a production STL without reopening the measurement, regeneration, and validation workflow.",
            "- A file marked `DO_NOT_PRINT` is a visualization/reference body only.",
            f"- Compare against `{STEP_STL_CATALOG}`; any hash mismatch is a STOP.",
            (
                "- For a complete no-repository Step 00 package, run "
                "`python scripts/stage_step_00_bundle.py --output <fresh-directory>` from the "
                "RC03 project root, then use the verifier copied into that bundle."
                if step["id"] == "00"
                else "- Return to Step 00 and its qualified ready-job workflow if an accepted part is missing."
            ),
            "",
            "| STL | Usage | Job reference | SHA-256 |",
            "| --- | --- | --- | --- |",
        ]
        for row in stl_records:
            filename = Path(row["canonical_path"]).name
            if row.get("local_operator_copy"):
                link = f"[{filename}](<{filename}>)"
            else:
                link = markdown_link(filename, stl_dir, ROOT / row["canonical_path"])
            stl_lines.append(
                f"| {link} | **{row['local_copy_usage']}** | "
                f"{', '.join(row['job_ids']) or 'reference only'} | `{row['sha256']}` |"
            )
    else:
        stl_lines = [
            "# No STL is required in this step",
            "",
            "This folder is intentionally present so every build step has the same layout.",
            "",
            f"This step does not create or consume a unique printable model. Use accepted physical assemblies from earlier steps and the controlled reference files listed in `../{STEP_TECHNICAL_DIRECTORY}/OPEN CONTROLLED FILES.md`.",
            "",
            "Do not substitute an unrelated STL or fabricate a schematic object from an illustration.",
        ]
    (stl_dir / STEP_STL_README).write_text("\n".join(stl_lines) + "\n", encoding="utf-8")
    render_step_print_settings_file(folder, step, jobs)

    manifest = {
        "schema_version": 1,
        "layout_version": LAYOUT_VERSION,
        "design_revision": "RC03-INT-R1",
        "package_definition_hash": definition_hash,
        "canonical_snapshot_hash": canonical_hash,
        "canonical_input_hash": canonical_hash,
        "step_id": step["id"],
        "slug": step["slug"],
        "title": step["title"],
        "operator_folder": step["operator_folder"],
        "operator_title": step["operator_title"],
        "state_at_generation": state,
        "active_build_id": active_build_id,
        "blocked_input_gates": blocked_gates,
        "prerequisite_steps": step.get("prerequisite_steps", []),
        "input_gate_ids": effective_gate_ids(step, "input_gates", measurement),
        "completion_gate_ids": effective_gate_ids(step, "completion_gates", measurement),
        "conditional_input_gates": step.get("conditional_input_gates", {}),
        "conditional_completion_gates": step.get("conditional_completion_gates", {}),
        "completion_requires_any_route": step.get("completion_requires_any_route", []),
        "conditional_acceptance": step.get("conditional_acceptance", {}),
        "effective_test_ids": [item["test_id"] for item in effective_acceptance(step, measurement)],
        "panel": step.get("panel"),
        "print_jobs": job_rows,
        "canonical_files": files,
        "local_stl_copy_count": sum(bool(row.get("local_operator_copy")) for row in stl_records),
        "hash_bound_stl_reference_count": sum(
            row.get("artifact_resolution") == "canonical_hash_bound_reference" for row in stl_records
        ),
        "next_step": next_step["id"] if next_step else None,
        "operator_writable_directory": STEP_EVIDENCE_DIRECTORY,
    }
    write_json(folder / STEP_MANIFEST_FILE, manifest)
    write_json(folder / STEP_FILE_MANIFEST, {"schema_version": 1, "files": files})

    csv_write(
        folder / STEP_FILE_INDEX,
        ("canonical_path", "sha256", "size_bytes", "roles", "actions", "job_ids"),
        (
            (
                row["canonical_path"],
                row["sha256"],
                row["size_bytes"],
                "; ".join(row["roles"]),
                "; ".join(row["actions"]),
                "; ".join(row["job_ids"]),
            )
            for row in files
        ),
    )
    (folder / STEP_FILE_HASHES).write_text(
        "".join(f"{row['sha256']}  ../../../{row['canonical_path']}\n" for row in files),
        encoding="utf-8",
    )

    open_lines = [
        "# Controlled files for this step\n",
        "These are direct links to the single canonical files. They are intentionally not copied here.\n",
        "| Action | Job | File | Role | SHA-256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in files:
        path = ROOT / row["canonical_path"]
        label = row["canonical_path"]
        open_lines.append(
            "| "
            + ", ".join(row["actions"])
            + " | "
            + (", ".join(row["job_ids"]) or "—")
            + " | "
            + markdown_link(label, technical_dir, path)
            + " | "
            + ", ".join(row["roles"])
            + " | `"
            + row["sha256"][:12]
            + "…` |"
        )
    open_lines.extend(
        [
            "",
            "## Control rules",
            "",
            "- A `.3mf` is a geometry-only plate. Use its paired `.PRINT_SETTINGS.md`, `.print.json`, imported QIDI process preset, separate filament preset, and job card; then save a native QIDI Studio project in the build-ID evidence folder.",
            "- STL is the canonical slicing mesh; STEP is its neutral CAD companion. Neither is edited inside this package.",
            "- Files marked `DO_NOT_PRINT` or `reference_only` are never manufacturing masters.",
            f"- If any hash differs from `{Path(STEP_FILE_INDEX).name}`, stop and regenerate this package before continuing.",
        ]
    )
    (folder / STEP_OPEN_FILES).write_text("\n".join(open_lines) + "\n", encoding="utf-8")

    config_steps = {item["id"]: item for item in read_json(CONFIG_PATH)["steps"]}
    previous_id = step.get("prerequisite_steps", [])[-1] if step.get("prerequisite_steps") else None
    previous_step = config_steps.get(previous_id) if previous_id else None

    before_lines = [
        f"# Step {step['id']} — Before You Start",
        "",
        "**Generated reference — do not edit this file. Save actual results in the active build record.**",
        "",
        f"**Current result:** **{display_state(state)}**",
        "",
    ]
    before_lines.extend(
        [
        "## Required earlier steps",
        "",
        ]
    )
    if step.get("prerequisite_steps"):
        for step_id in step["prerequisite_steps"]:
            previous = config_steps[step_id]
            prerequisite_status = (
                "NOT COMPLETE" if f"prerequisite_step:{step_id}" in blocked_gates else "COMPLETE"
            )
            before_lines.append(
                f"- Current result: **{prerequisite_status}**. Required result: Step {step_id} — "
                + markdown_link(previous["operator_title"], folder, base / step_folder_name(previous) / STEP_START_FILE)
                + " is `COMPLETE` for this build ID."
            )
    else:
        before_lines.append("- No earlier assembly step is required; this is the controlled starting step.")
    before_lines.extend(
        ["", "## Required reviewed inputs", "", "| Input | Current result | Evidence needed |", "| --- | --- | --- |"]
    )
    input_gate_ids = effective_gate_ids(step, "input_gates", measurement)
    for gate_id, status, evidence in gate_rows(input_gate_ids, measurement):
        before_lines.append(f"| `{gate_id}` | **{status}** | {evidence} |")
    required_routes = step.get("requires_any_route", [])
    if required_routes:
        selected_routes = [route for route in required_routes if measurement["selected_routes"].get(route, False)]
        route_result = "PASS: " + ", ".join(selected_routes) if selected_routes else "NOT SELECTED"
        before_lines.append(
            f"| Tool route: {' or '.join(required_routes)} | **{route_result}** | "
            "Record explicit route decisions in Step 00; at least one listed tool route must be `yes`. |"
        )
    if not input_gate_ids and not required_routes:
        before_lines.append("| — | — | No additional reviewed input gates |")
    before_lines.extend(
        [
            "",
            "## Gather checklist",
            "",
            f"Open [{STEP_PARTS_FILE}](<{STEP_PARTS_FILE}>). It contains every configured physical input plus the deduplicated parts, hardware, materials, and tools register.",
        ]
    )
    if state == "READY_TO_START":
        before_lines.extend(["", "## Create this step's build record", ""])
        if active_build_id:
            before_lines.append(
                f"The selected build ID is `{active_build_id}`. Before taking the first measurement or photo, run `python scripts/initialize_step_evidence.py --step {step['id']}` exactly once."
            )
        elif step["id"] == "00":
            before_lines.append(
                "Select a unique build ID with `python scripts/set_active_build.py --build-id YYYY-MM-DD_CELL-A`, regenerate this package, then run `python scripts/initialize_step_evidence.py --step 00` exactly once."
            )
    elif state == "LOCKED":
        before_lines.extend(
            [
                "",
                "> **STOP:** This step is locked. Resolve the non-PASS prerequisite and reviewed-input rows above; do not begin work or initialize evidence.",
            ]
        )
    elif state == "HOLD":
        before_lines.extend(["", "## Stop and resolve the hold", ""])
        before_lines.extend(f"- {blocker_description(gate, measurement)}" for gate in blocked_gates)
        before_lines.extend(f"- Open hold: {hold}" for hold in active_open_holds)
    before_lines.extend(
        [
            "",
            "## Always stop when",
            "",
            "- A required measurement is missing or out of limit.",
            "- A part is damaged, unlabeled, or does not match its accepted kit.",
            "- A file hash changed or an unresolved HOLD exists.",
            "- Digital validation is mistaken for physical permission to continue.",
        ]
    )
    (folder / STEP_BEFORE_FILE).write_text("\n".join(before_lines) + "\n", encoding="utf-8")

    required_inputs = unique_required_inputs(step)
    hardware_rows = unique_hardware_rows(step)
    csv_write(
        folder / STEP_HARDWARE_CSV,
        ("source", "type", "qty", "item", "critical_condition", "status"),
        [
            *(
                ("required_physical_input", "Required input", "As specified", item, "Present and accepted before work", "NOT_VERIFIED")
                for item in required_inputs
            ),
            *(
                ("structured_register", item["type"], item["qty"], item["item"], item["condition"], "NOT_VERIFIED")
                for item in hardware_rows
            ),
        ],
    )
    parts_lines = [
        f"# Step {step['id']} — Parts and Tools Checklist",
        "",
        "**Generated reference — do not edit this file. Confirm each required result physically before work.**",
        "",
        "Each configured physical-input requirement and each distinct structured register row appears once. If both rows describe the same object, treat them as complementary context and quantity/condition constraints—not as two objects to gather.",
        "",
        "## Required physical inputs",
        "",
        "| Quantity | Required input | Required condition |",
        "| --- | --- | --- |",
    ]
    for item in required_inputs:
        parts_lines.append(f"| As specified | {item} | Present, identified, and accepted before work |")
    parts_lines.extend(
        [
        "",
        "## Structured parts, hardware, materials, and tools",
        "",
        "| Type | Quantity | Item | Required condition |",
        "| --- | --- | --- | --- |",
        ]
    )
    for item in hardware_rows:
        parts_lines.append(f"| {item['type']} | {item['qty']} | {item['item']} | {item['condition']} |")
    parts_lines.extend(["", "## Printed-part traceability", ""])
    if step.get("print_jobs"):
        job_mode = (
            "Produce only a job whose current print readiness is `READY`; follow its controlled job card."
            if step["id"] == "00"
            else "Use the accepted, labeled Step-00 kit parts. Do not print the traceability copies during this assembly step."
        )
        parts_lines.extend(
            [
                f"- {job_mode}",
                f"- Relevant job IDs: `{', '.join(step['print_jobs'])}`.",
                "- Open " + markdown_link(STEP_PRINT_SETTINGS_FILE, folder, folder / STEP_PRINT_SETTINGS_FILE) + " for the exact per-job preset files and current authority.",
            ]
        )
    else:
        parts_lines.extend(
            [
                "- This step has no associated print job.",
                "- The standard " + markdown_link(STEP_PRINT_SETTINGS_FILE, folder, folder / STEP_PRINT_SETTINGS_FILE) + " explicitly records that no printing is allowed here.",
            ]
        )
    if stl_records:
        model_description = (
            "local model file(s)"
            if step["id"] == "00"
            else "hash-bound canonical model reference(s)"
        )
        parts_lines.append(
            f"- Review the {len(stl_records)} {model_description} and their exact usage labels in "
            + markdown_link("03 - STL MODELS", folder, stl_dir / STEP_STL_README)
            + "."
        )
    else:
        parts_lines.append("- No STL model is required for this step; the standard model folder explains why.")
    parts_lines.extend(
        [
            "",
            "The machine-readable source list is in "
            + markdown_link("99 - TECHNICAL RECORDS - DO NOT EDIT", folder, folder / STEP_HARDWARE_CSV)
            + ".",
        ]
    )
    (folder / STEP_PARTS_FILE).write_text("\n".join(parts_lines) + "\n", encoding="utf-8")

    if step["id"] == "01":
        render_board_drill_guide_file(folder)

    procedure_lines = [
        f"# Step {step['id']} — Step-by-Step Instructions",
        "",
        "**Generated reference — do not edit this file.**",
        "",
        "## Orientation",
        "",
        "- Origin: front-left corner of the finished board top.",
        "- +X: right. +Y: rear/toward the arm. +Z: up.",
        "- Confirm FRONT and +Y/rear before placing a part, device, template, or tag.",
        "",
    ]
    if step.get("panel"):
        panel_path = ROOT / step["panel"]
        procedure_lines.extend(
            [
                "## Assembly image",
                "",
                f"![Step {step['id']} — {step['operator_title']}]({Path(os.path.relpath(panel_path, folder)).as_posix()})",
                "",
                "The image explains order and orientation. Verify all schematic dimensions and hardware against the measured controls below.",
                "",
            ]
        )
    if step["id"] == "00":
        procedure_lines.extend(route_selection_guidance("## Record all three route decisions before printing"))
        procedure_lines.append("")
    direct_files = actionable_file_records(step, files)
    procedure_lines.extend(
        [
            "## Files used in this step",
            "",
            "Open these canonical project files for the actions below. The links point to the controlled originals; do not copy or rename them.",
            "",
            "| Canonical file | Use in this step | Purpose |",
            "| --- | --- | --- |",
        ]
    )
    for record in direct_files:
        canonical_path = record["canonical_path"]
        procedure_lines.append(
            f"| {markdown_link(canonical_path, folder, ROOT / canonical_path)} | "
            f"{', '.join(direct_action_label(action) for action in record['actions'])} | "
            f"{', '.join(record['roles'])} |"
        )
    procedure_lines.append("")
    if step["id"] == "00":
        action_number = 0
        for instruction in step["procedure"]:
            phase = re.match(r"^(Phase 00\.\d+)\s+—\s+([^:]+):\s*(.*)$", instruction)
            if phase:
                body = phase.group(3)
                body = body[:1].upper() + body[1:]
                if procedure_lines[-1] != "":
                    procedure_lines.append("")
                procedure_lines.extend([f"## {phase.group(1)} — {phase.group(2)}", "", body, ""])
            else:
                action_number += 1
                procedure_lines.append(f"{action_number}. {instruction}")
    else:
        procedure_lines.extend(["## Numbered actions", ""])
        procedure_lines.extend(f"{number}. {instruction}" for number, instruction in enumerate(step["procedure"], 1))
    procedure_lines.extend(["", "## STOP", "", f"> {step['stop_gate']}"])
    (folder / STEP_INSTRUCTIONS_FILE).write_text("\n".join(procedure_lines) + "\n", encoding="utf-8")

    acceptance_lines = [
        f"# Step {step['id']} — Check Your Work",
        "",
        f"Save original files under `{STEP_EVIDENCE_DIRECTORY}/<BUILD_ID>/`, then record every test with `python scripts/record_step_result.py --step {step['id']} ...`. Each `--evidence` path must be relative to that build-ID folder, remain contained within it, and name an existing regular file; `{MEASUREMENT_RECORD_FILE}` and `{SIGNOFF_RECORD_FILE}` cannot cite themselves. A visual check alone is not evidence when a measured value is required.",
        "",
        f"Command form: `python scripts/record_step_result.py --step {step['id']} --test TEST_ID --value \"VALUE_OR_OBSERVATION\" --unit \"UNIT_OR_NA\" --instrument \"TOOL_ID_OR_METHOD\" --evidence \"photos/EXISTING_FILE.jpg\" --result PASS --operator \"OPERATOR_NAME\"`. Repeat `--evidence` as needed. Raw JSON editing is an advanced recovery fallback only.",
        "",
        "| Test | What must be true | How to check | Pass limit | Reviewed gate | Evidence to save | Record result in |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in effective_acceptance(step, measurement):
        gate_label = f"`{item['gate_id']}`" if item.get("gate_id") else "local signoff"
        acceptance_lines.append(
            f"| `{item['test_id']}` | {item['criterion']} | {item['method']} | {item['limit']} | "
            f"{gate_label} | {item['evidence']} | `scripts/record_step_result.py` |"
        )
    acceptance_lines.extend(["", "## Completion status", "", "| Requirement | Current result |", "| --- | --- |"])
    for gate_id, status, _ in gate_rows(effective_gate_ids(step, "completion_gates", measurement), measurement):
        acceptance_lines.append(f"| `{gate_id}` | **{status}** |")
    acceptance_lines.append(f"| active-build step signoff | **{active_signoff_status}** |")
    if step.get("completion_requires_any_route"):
        routes = step["completion_requires_any_route"]
        selected = [route for route in routes if measurement["selected_routes"].get(route, False)]
        acceptance_lines.append(
            f"| select at least one of `{', '.join(routes)}` | **{'PASS: ' + ', '.join(selected) if selected else 'NOT_SELECTED'}** |"
        )
    acceptance_lines.extend(["", "## If a check fails", ""])
    if step.get("failure_recovery"):
        acceptance_lines.append(step["failure_recovery"])
    elif previous_step:
        acceptance_lines.append(
            f"Set this step to `HOLD`; do not continue. Keep reversible local rework in Step {step['id']}. Return to Step 00 for a failed printed part, hardware-fit coupon, or source measurement; return to Step 01 for a failed board locator/anchor; or return to Step {previous_step['id']} — {previous_step['operator_title']} when its installed handoff caused the failure. Reopen every affected downstream signoff."
        )
    else:
        acceptance_lines.append("Set Step 00 to `HOLD`; correct the measurement, profile, CAD parameter, slice, or print, then repeat every affected diagnostic and downstream release check.")
    acceptance_lines.extend(
        [
            "",
            f"The step is PASS only when every test is in limit, all required reviewed gates are PASS, and `{SIGNOFF_RECORD_FILE}` is signed PASS.",
        ]
    )
    (folder / STEP_CHECK_FILE).write_text("\n".join(acceptance_lines) + "\n", encoding="utf-8")

    finish_lines = [
        f"# Step {step['id']} — Finish This Step and Continue",
        "",
        "Do not continue unless every mandatory acceptance item is PASS and there is no unresolved HOLD.",
        "",
        "## Required handoff results",
        "",
    ]
    finish_lines.extend(f"- Required result: {item}" for item in step["handoff"])
    finish_lines.extend(
        [
            "- Required result: Installed items, returned tools, accepted spares, quarantined parts, and affected downstream datums are recorded in the build-ID folder.",
            f"- Required result: The responsible operator ran `python scripts/sign_off_step.py --step {step['id']} --status PASS --operator \"OPERATOR_NAME\"`; the helper validated and completed `{SIGNOFF_RECORD_FILE}`.",
            "",
            "Raw signoff JSON editing is an advanced recovery fallback only. Use `--status HOLD --hold \"REASON\"` instead of forcing PASS when any requirement is incomplete.",
            "",
            f"After PASS, follow [{ROOT_EVIDENCE_FILE}](<../{ROOT_EVIDENCE_FILE}>) section 8: regenerate, run `python scripts/build_step_packages.py --check`, reopen the refreshed state, and confirm this step is `COMPLETE` before any handoff.",
            "",
        ]
    )
    if next_step and state == "COMPLETE":
        finish_lines.extend(
            [
                "## Continue",
                "",
                f"Confirm Step {next_step['id']} is `READY TO START`; only then run `python scripts/initialize_step_evidence.py --step {next_step['id']}`.",
                "",
                f"Next: Step {next_step['id']} — "
                + markdown_link(next_step["operator_title"], folder, base / step_folder_name(next_step) / STEP_START_FILE),
            ]
        )
    elif next_step:
        finish_lines.extend(
            [
                "## Next step remains locked",
                "",
                f"Step {next_step['id']} cannot be opened from this handoff until Step {step['id']} is computed `COMPLETE`.",
            ]
        )
    else:
        finish_lines.extend(["## End state", "", "Archive the signed release record and service baseline. Any controlled change reopens affected steps."])
    (folder / STEP_FINISH_FILE).write_text("\n".join(finish_lines) + "\n", encoding="utf-8")

    nav_parts = []
    if previous_step:
        nav_parts.append(markdown_link(f"← Step {previous_step['id']}", folder, base / step_folder_name(previous_step) / STEP_START_FILE))
    nav_parts.append(markdown_link("Build dashboard", folder, base / ROOT_DASHBOARD_FILE))
    if next_step and state == "COMPLETE":
        nav_parts.append(markdown_link(f"Step {next_step['id']} →", folder, base / step_folder_name(next_step) / STEP_START_FILE))
    elif next_step:
        nav_parts.append("Next step locked")
    top_nav = " | ".join(nav_parts)

    before_link = f"[{STEP_BEFORE_FILE}](<{STEP_BEFORE_FILE}>)"
    if state == "LOCKED":
        next_safe_action = f"Open {before_link} for the single prerequisite/gate table; do not begin or initialize evidence."
    elif state == "HOLD":
        next_safe_action = f"Stop work and open {before_link}; correct and retest every recorded hold before continuing."
    elif state == "IN_PROGRESS":
        next_safe_action = f"Review {before_link}, then continue only in the existing active-build record."
    elif state == "COMPLETE":
        next_safe_action = "Use the signed handoff. The next-step link is now enabled below."
    else:
        next_safe_action = f"Open {before_link}, physically confirm every requirement, and create the build record exactly once."
    start_lines = [
        f"# Step {step['id']} — {step['operator_title']}",
        "",
        top_nav,
        "",
        f"**Current result:** **{display_state(state)}**",
        f"**Next safe action:** {next_safe_action}  ",
        f"**Engineering name:** {step['title']}",
        "",
        "## Goal",
        "",
        step["purpose"],
        "",
        "## Finished when",
        "",
        step["expected_result"],
    ]
    if step.get("panel"):
        start_lines.extend(
            [
                "",
                "## Assembly image",
                "",
                f"![Step {step['id']} — {step['operator_title']}]({Path(os.path.relpath(ROOT / step['panel'], folder)).as_posix()})",
            ]
        )
    start_lines.extend(["", "## Open these files in order", ""])
    if step["id"] == "01":
        start_lines.extend(
            [
                f"1. [{STEP_BEFORE_FILE}](<{STEP_BEFORE_FILE}>)",
                f"2. [{STEP_PARTS_FILE}](<{STEP_PARTS_FILE}>)",
                f"3. [{STEP_DRILL_GUIDE_FILE}](<{STEP_DRILL_GUIDE_FILE}>)",
                f"4. [{STEP_PRINT_SETTINGS_FILE}](<{STEP_PRINT_SETTINGS_FILE}>)",
                f"5. [{STEP_INSTRUCTIONS_FILE}](<{STEP_INSTRUCTIONS_FILE}>)",
                f"6. [{STEP_CHECK_FILE}](<{STEP_CHECK_FILE}>)",
                f"7. [{STEP_EVIDENCE_README}](<{STEP_EVIDENCE_DIRECTORY}/{STEP_EVIDENCE_README}>)",
                f"8. [{STEP_FINISH_FILE}](<{STEP_FINISH_FILE}>)",
            ]
        )
    else:
        start_lines.extend(
            [
                f"1. [{STEP_BEFORE_FILE}](<{STEP_BEFORE_FILE}>)",
                f"2. [{STEP_PARTS_FILE}](<{STEP_PARTS_FILE}>)",
                f"3. [{STEP_PRINT_SETTINGS_FILE}](<{STEP_PRINT_SETTINGS_FILE}>)",
                f"4. [{STEP_INSTRUCTIONS_FILE}](<{STEP_INSTRUCTIONS_FILE}>)",
                f"5. [{STEP_CHECK_FILE}](<{STEP_CHECK_FILE}>)",
                f"6. [{STEP_EVIDENCE_README}](<{STEP_EVIDENCE_DIRECTORY}/{STEP_EVIDENCE_README}>)",
                f"7. [{STEP_FINISH_FILE}](<{STEP_FINISH_FILE}>)",
            ]
        )
    start_lines.extend(
        [
            "",
            f"Model files: [{STEP_STL_DIRECTORY}](<{STEP_STL_DIRECTORY}/{STEP_STL_README}>)  ",
            f"Advanced records: [{STEP_TECHNICAL_DIRECTORY}](<{STEP_TECHNICAL_DIRECTORY}/{Path(STEP_OPEN_FILES).name}>)",
            "",
            f"> **STOP:** {step['stop_gate']}",
        ]
    )
    (folder / STEP_START_FILE).write_text("\n".join(start_lines) + "\n", encoding="utf-8")

    controlled_paths = [relative for relative in required_step_files(step) if relative != STEP_MANIFEST_FILE]
    manifest["generated_control_hashes"] = generated_control_hashes(folder, controlled_paths)
    write_json(folder / STEP_MANIFEST_FILE, manifest)
    return manifest


def build() -> dict[str, Any]:
    config, jobs_doc, measurement, readiness = load_sources()
    generated_at = datetime.now(timezone.utc).isoformat()
    if config["design_revision"] != measurement["design_revision"]:
        raise ValueError("assembly_steps.json and measurement_record.json revisions differ")
    jobs = {job["job_id"]: job for job in jobs_doc["jobs"]}
    steps = config["steps"]
    step_ids = [step["id"] for step in steps]
    if step_ids != [f"{value:02d}" for value in range(16)]:
        raise ValueError(f"Expected exactly ordered steps 00-15, received {step_ids}")

    step_files = {step["id"]: files_for_step(step, jobs) for step in steps}
    canonical_hash = canonical_input_hash(config, step_files)
    definition_hash = package_definition_hash(config, jobs_doc, measurement, step_files)
    preserved_target = TARGET if TARGET.is_dir() else None
    preserved_steps = preserved_steps_by_id(preserved_target)
    previous_layout_version = generated_layout_version(preserved_target)
    expected_step_folder_names = {step_folder_name(step) for step in steps}
    preserved_step_folder_names = {path.name for path in preserved_steps.values()}
    structural_migration_required = bool(
        preserved_target
        and (
            previous_layout_version != LAYOUT_VERSION
            or preserved_step_folder_names != expected_step_folder_names
        )
    )
    active_build = load_active_build(preserved_target)
    if active_build.get("configuration_error"):
        raise ValueError(active_build["configuration_error"])
    active_build_id = active_build.get("active_build_id")
    states: dict[str, tuple[str, list[str]]] = {}
    for step in steps:
        preserved_step = preserved_steps.get(step["id"])
        states[step["id"]] = compute_state(
            step,
            measurement,
            preserved_step,
            states,
            active_build_id,
            definition_hash,
        )

    remove_generated(STAGING, STAGING.name, require_sentinel=False)
    STAGING.mkdir()
    (STAGING / SENTINEL).write_text(
        f"layout_version={LAYOUT_VERSION}\n"
        f"Generated by scripts/build_step_packages.py. Only ACTIVE_BUILD.json and each step's "
        f"{STEP_EVIDENCE_DIRECTORY} area are operator-writable.\n",
        encoding="utf-8",
    )
    write_json(STAGING / ACTIVE_BUILD_FILE, {"schema_version": 1, "active_build_id": active_build_id})

    manifests = []
    for index, step in enumerate(steps):
        next_step = steps[index + 1] if index + 1 < len(steps) else None
        preserved_step = preserved_steps.get(step["id"])
        state, blocked_gates = states[step["id"]]
        manifests.append(
            render_step(
                STAGING,
                step,
                step_files[step["id"]],
                jobs,
                measurement,
                canonical_hash,
                definition_hash,
                state,
                blocked_gates,
                next_step,
                preserved_step,
                generated_at,
                active_build_id,
            )
        )

    ownership: defaultdict[str, list[str]] = defaultdict(list)
    for step in steps:
        if step.get("print_action") == "produce_here":
            for job_id in step.get("print_jobs", []):
                ownership[job_id].append(step["id"])
    csv_write(
        STAGING / "PRINT_JOB_OWNERSHIP.csv",
        ("job_id", "produce_in_step", "assembly_consumers"),
        (
            (
                job_id,
                ";".join(ownership.get(job_id, [])),
                ";".join(step["id"] for step in steps if job_id in step.get("print_jobs", []) and step["id"] != "00"),
            )
            for job_id in jobs
        ),
    )

    selected_routes = measurement["selected_routes"]
    readiness_summary = readiness["summary"]
    first_locked = next((step["id"] for step in steps if states[step["id"]][0] == "LOCKED"), None)
    first_blocked = next(
        (step["id"] for step in steps if states[step["id"]][0] in {"HOLD", "LOCKED"}),
        None,
    )
    first_attention = next(
        (step["id"] for step in steps if states[step["id"]][0] != "COMPLETE"),
        None,
    )
    index_doc = {
        "schema_version": 1,
        "layout_version": LAYOUT_VERSION,
        "design_revision": "RC03-INT-R1",
        "package_definition_hash": definition_hash,
        "canonical_snapshot_hash": canonical_hash,
        "canonical_input_hash": canonical_hash,
        "generated_at": generated_at,
        "physical_release": "UNRELEASED",
        "active_build_id": active_build_id,
        "print_readiness": readiness_summary,
        "selected_routes": selected_routes,
        "first_locked_step": first_locked,
        "first_blocked_step": first_blocked,
        "first_attention_step": first_attention,
        "steps": [
            {
                "id": step["id"],
                "folder": step_folder_name(step),
                "title": step["title"],
                "operator_title": step["operator_title"],
                "state": states[step["id"]][0],
                "blocked_input_gates": states[step["id"]][1],
                "prerequisite_steps": step.get("prerequisite_steps", []),
                "print_jobs": step.get("print_jobs", []),
                "next_step": steps[index + 1]["id"] if index + 1 < len(steps) else None,
            }
            for index, step in enumerate(steps)
        ],
    }
    write_json(STAGING / "INDEX.json", index_doc)

    entry_instruction = (
        f"open Step {first_attention} as the first non-complete step"
        if first_attention
        else "review the completed final-step archive; no build step remains open"
    )
    known_decisions: list[str] = []
    if not any(selected_routes.get(route, False) for route in ("phone_stylus_route", "keyboard_rod_route")):
        known_decisions.append("- Choose at least one compliant-tool route before Step 00 can complete and Step 14 can begin.")
    if measurement["gates"]["camera_mount_interface_measured"]["status"] != "PASS":
        known_decisions.append("- Supply and measure the exact arm-mounted camera/interface specification before Step 13; the separate fixed mast is a selected but unqualified fallback only.")
    with (ROOT / "FASTENER_MAP.csv").open(encoding="utf-8", newline="") as stream:
        package_fastener_rows = list(csv.DictReader(stream))
    if any(
        not row["selected_length_mm"].strip()
        or not row["anchor_type"].strip()
        or not row["final_board_bore_mm"].strip()
        for row in package_fastener_rows
    ):
        known_decisions.append("- Complete the blank selected-length, anchor-type, and final-board-bore fields in FASTENER_MAP.csv from physical cutoff tests before final board drilling.")
    if measurement["gates"]["workcell_commissioning_pass"]["status"] != "PASS":
        known_decisions.append("- Select and document a rated E-stop implementation and board-to-bench anti-shift method before Step 15 commissioning.")
    known_decisions.extend(
        [
            "- Transfer every accepted coupon value through its dedicated key in `user_overrides.example.json`, then regenerate and prove the geometry-parameter mapping before production.",
            "- Store diagnostic native QIDI projects in the build-ID evidence folder; the canonical `--qidi-job` gate records non-diagnostic release jobs only.",
        ]
    )
    root_lines = [
        "# RoCell RC03 — Start Here",
        "",
        "This is the operator-facing sequence for `RC03-INT-R1`. The CAD, configuration, ledgers, drawings, and print controls remain canonical in their original project folders. Each step contains direct links/hashes plus hash-verified STL convenience copies so operators can work by step without creating a second manufacturing master.",
        "",
        f"**Physical state:** `UNRELEASED`  ",
        f"**Active build ID:** `{active_build_id or 'NOT SET'}`  ",
        f"**Print readiness:** {readiness_summary['ready']} READY / {readiness_summary['waiting']} WAITING / {readiness_summary['not_selected']} NOT_SELECTED  ",
        f"**Package definition hash:** `{definition_hash}`  ",
        f"**Canonical snapshot hash:** `{canonical_hash}`  ",
        f"**Selected routes:** phone stylus={selected_routes['phone_stylus_route']}, keyboard rod={selected_routes['keyboard_rod_route']}, fixed-mast camera fallback={selected_routes['camera_mast_optional']} (selection is not release)",
        "",
        "## How to use this folder",
        "",
        f"1. Read [the complete build order](<{ROOT_SEQUENCE_FILE}>), then {entry_instruction} (a new build starts at Step 00).",
        f"2. In each step, open `{STEP_START_FILE}` and follow its numbered file map.",
        f"3. Follow [how to save measurements and photos](<{ROOT_EVIDENCE_FILE}>), set one active build ID, and initialize only a step that is `READY TO START`.",
        f"4. Use the exact usage label in each step's `{STEP_STL_DIRECTORY}` folder. Canonical project-level `stl/` files remain authoritative.",
        f"5. Open manufacturing controls only through `{STEP_TECHNICAL_DIRECTORY}/{Path(STEP_OPEN_FILES).name}`; do not create editable forks.",
        "6. Print jobs are produced only in Step 00. Later assembly steps consume accepted, labeled parts and include STL/job files for recovery and traceability.",
        "7. Record raw measurements and original evidence. A checkmark without an in-limit value is not PASS.",
        f"8. Use [part names and technical terms](<{ROOT_GLOSSARY_FILE}>) whenever a term is unfamiliar.",
        "9. If a source or local STL hash changes, regenerate and revalidate before continuing.",
        "",
        "## Persistent orientation",
        "",
        "- Origin: front-left corner of the finished board top.",
        "- +X is right, +Y is rear/toward the arm, and +Z is up.",
        "- Blue denotes locators/controlled geometry, orange denotes hardware/action, and red denotes STOP/no-go conditions.",
        "",
        "## Sequence dashboard",
        "",
        "| Step | State | Title | Prerequisites | Print-job references | Next |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, step in enumerate(steps):
        next_id = steps[index + 1]["id"] if index + 1 < len(steps) else "archive"
        root_lines.append(
            f"| [{step['id']}](<{step_folder_name(step)}/{STEP_START_FILE}>) | **{display_state(states[step['id']][0])}** | {step['operator_title']} | "
            f"{', '.join(step.get('prerequisite_steps', [])) or '—'} | {', '.join(step.get('print_jobs', [])) or '—'} | {next_id} |"
        )
    root_lines.extend(
        [
            "",
            "## Canonical controls",
            "",
            f"- {markdown_link('Illustrated assembly guide', STAGING, ROOT / 'output/pdf/RC03_ILLUSTRATED_ASSEMBLY_GUIDE.pdf')}",
            f"- {markdown_link('Detailed assembly manual', STAGING, ROOT / 'ASSEMBLY_MANUAL.pdf')}",
            f"- {markdown_link('Print readiness', STAGING, ROOT / 'PRINT_READINESS.md')}",
            f"- {markdown_link('Build tracker', STAGING, ROOT / 'BUILD_TRACKER.md')}",
            f"- {markdown_link('BOM', STAGING, ROOT / 'BOM.csv')}",
            f"- {markdown_link('Fastener map', STAGING, ROOT / 'FASTENER_MAP.csv')}",
            f"- {markdown_link('Job kits', STAGING, ROOT / 'JOB_KITS.csv')}",
            "",
            "## Open decisions and controlled change triggers",
            "",
            *known_decisions,
            "",
            "`tmp/` is scratch/QA output and is never build evidence.",
        ]
    )
    (STAGING / ROOT_DASHBOARD_FILE).write_text("\n".join(root_lines) + "\n", encoding="utf-8")
    (STAGING / "README.md").write_text(
        "# Start here\n\n"
        f"Open [{ROOT_DASHBOARD_FILE}](<{ROOT_DASHBOARD_FILE}>). It is the single operator dashboard for this build package.\n",
        encoding="utf-8",
    )

    complete_count = sum(state == "COMPLETE" for state, _ in states.values())
    if first_attention:
        attention_state = display_state(states[first_attention][0])
        sequence_status = (
            f"**Current sequence status:** {complete_count}/16 steps COMPLETE; "
            f"Step {first_attention} is the first non-complete step and is **{attention_state}**."
        )
    else:
        sequence_status = "**Current sequence status:** all 16 steps are COMPLETE for the active build."
    simple_root_lines = [
        "# RoCell RC03 — Complete Build Order",
        "",
        "Follow these folders in numeric order. Step 00 produces and accepts the printed parts; Steps 01-15 assemble and prove the cell. Never skip a LOCKED state, HOLD, or STOP condition.",
        "",
        "**Current physical state:** UNRELEASED. Digital completion does not itself authorize physical release.",
        "",
        sequence_status,
        "",
        f"**Active build ID:** `{active_build_id or 'NOT SET'}`. Set it before recording any evidence.",
        "",
        "Safe path: choose routes and one build ID → measure real hardware → print diagnostics → record results → regenerate and validate → print only READY jobs → inspect and kit → assemble Steps 01-15 in order.",
        "",
        f"Read [how to save measurements and photos](<{ROOT_EVIDENCE_FILE}>) and [part names and technical terms](<{ROOT_GLOSSARY_FILE}>) before beginning.",
        "",
    ]
    for step in steps:
        local_stl_count = sum(
            1
            for record in step_files[step["id"]]
            if record["canonical_path"].startswith("stl/") and record["canonical_path"].lower().endswith(".stl")
        )
        if step["id"] == "00":
            stl_summary = f"**Step-00 qualification/production STL copies:** {local_stl_count}; use only through a READY job."
        elif local_stl_count:
            stl_summary = f"**Traceability-only STL copies:** {local_stl_count}; do not print during this assembly step."
        else:
            stl_summary = "**STL requirement:** none for this step."
        simple_root_lines.extend(
            [
                f"## Step {step['id']} — {step['operator_title']}",
                "",
                f"**Goal:** {step['purpose']}",
                "",
                f"**Done when:** {step['expected_result']}",
                "",
                stl_summary,
                "",
                f"Open: [{step['id']} — Start Here](<{step_folder_name(step)}/{STEP_START_FILE}>)",
                "",
                f"> **STOP:** {step['stop_gate']}",
                "",
            ]
        )
    (STAGING / ROOT_SEQUENCE_FILE).write_text("\n".join(simple_root_lines) + "\n", encoding="utf-8")

    evidence_lines = [
        "# Evidence and canonical-record workflow",
        "",
        "Use one build ID from Step 00 through Step 15. The step folders hold raw evidence; the canonical configuration files hold reviewed gate and lifecycle state. They do not synchronize automatically.",
        "",
        "## Two hashes with different jobs",
        "",
        f"- **Package definition hash:** `{definition_hash}`. This binds build evidence to the procedure, models, gate schema, job definitions, and acceptance logic. If it changes, affected evidence is stale and must be reviewed/repeated.",
        f"- **Canonical snapshot hash:** `{canonical_hash}`. This fingerprints the current complete canonical snapshot, including mutable reviewed gate and lifecycle values. It normally changes as valid evidence is synchronized; that change alone does not invalidate earlier evidence whose package definition hash still matches.",
        "- Never rewrite immutable raw evidence merely to replace an older canonical snapshot hash. Preserve the original snapshot field and regenerate the package so dashboards show the current snapshot.",
        "",
    ]
    evidence_lines.extend(route_selection_guidance("## 1. Record all three route decisions"))
    evidence_lines.extend(
        [
            "",
            "After recording all three decisions, regenerate and run `python scripts/build_step_packages.py --check` before initializing Step 00. If a route selection changes after evidence work begins, place the build on HOLD and start a new build ID after regeneration so conditional test rows cannot be lost.",
            "",
            "## 2. Initialize the same build ID in every step",
            "",
            "At Step 00, choose a unique name such as `2026-08-31_CELL-A`, select it explicitly, regenerate, verify the package, and then copy Step 00's refreshed template once:",
            "",
            "```powershell",
            "python scripts/set_active_build.py --build-id 2026-08-31_CELL-A",
            "python scripts/build_step_packages.py",
            "python scripts/build_step_packages.py --check",
            "python scripts/initialize_step_evidence.py --step 00",
            "```",
            "",
            "For each later step, initialize only after the preceding signed step has been regenerated as `COMPLETE` and the next step is shown as `READY TO START`. The initializer uses the same active build ID, accepts only `READY_TO_START`, and refuses to overwrite an existing folder. Never pre-initialize route-dependent templates, reuse a build ID, or edit `BUILD_ID_TEMPLATE/`.",
            "",
            "## 3. Capture and record raw evidence",
            "",
            f"Save photos, native QIDI projects, calibration outputs, and reports below the current build-ID folder before recording them. Every `--evidence` value must be relative to that build-ID folder, remain contained within it, and identify a regular file that already exists. Neither `{MEASUREMENT_RECORD_FILE}` nor `{SIGNOFF_RECORD_FILE}` may cite itself. Repeat `--evidence` for multiple files; record corrections and retests without erasing a failed first result.",
            "",
            "Use the controlled result helper once for every pre-populated test ID. Example:",
            "",
            "```powershell",
            "python scripts/record_step_result.py --step 03 --test 03-A --value \"seats by hand; no rocking\" --unit \"N/A\" --instrument \"visual inspection\" --evidence \"photos/03-A.jpg\" --result PASS --operator \"NAME\"",
            "```",
            "",
            "The helper safely updates the active build's `measurement_record.json`. Raw JSON editing is an advanced recovery fallback only and must never bypass containment, schema, or completeness validation.",
            "",
            "## 4. Review before changing a canonical gate",
            "",
            "Compare every result with the corresponding step limit. A canonical gate may be set to PASS only when all required values and context are populated, its evidence identifies this build ID, and no applicable row failed.",
            "",
            "From the project root, use the controlled recorder for supported gate fields:",
            "",
            "```powershell",
            "python scripts/record_print_measurement.py --help",
            "python scripts/record_print_measurement.py --context operator=NAME --context date=YYYY-MM-DD --context printer_serial=SERIAL --context measurement_tool_id=TOOL_ID --context evidence_directory=BUILD_ID_PATH --context qidi_studio_version=VERSION",
            "python scripts/record_print_measurement.py --gate GATE_ID --status PASS --value FIELD=VALUE --evidence-note \"BUILD_ID evidence path and summary\"",
            "```",
            "",
            "Repeat `--value` for every field required by that gate. The recorder rejects PASS while required values or test context are blank. Diagnostic native QIDI projects stay in Step 00 evidence; `--qidi-job` is for non-diagnostic release jobs only.",
            "",
            "## 5. Advance print-job and kit state only in order",
            "",
            "For Step 00, validators derive `READY_TO_SLICE` automatically when a selected job's prerequisites pass; operators do not set it and there is no evidence slot for it. After a job is reported READY_TO_SLICE, advance exactly one manual state at a time with the controlled recorder:",
            "",
            "```powershell",
            f"python scripts/record_job_lifecycle.py --job 00A --state SLICE_REVIEWED --operator \"NAME\" --evidence \"BUILD_BY_STEP/{steps[0]['operator_folder']}/{STEP_EVIDENCE_DIRECTORY}/BUILD_ID/...\"",
            "```",
            "",
            "Then advance sequentially through `PRINTED` → `POSTPRINT_PASS` → `KITTED` → `ASSEMBLY_PASS` → `IN_SERVICE`, running the command once per completed state. The recorder rejects skips, unselected jobs, unresolved prerequisites, and missing mapped gates. Reconcile `JOB_KITS.csv` counts, QA fields, evidence reference, and storage label before KITTED; never infer KITTED from a successful print alone.",
            "",
            "## 6. Regenerate and verify after canonical updates",
            "",
            "Run the applicable commands from the project root:",
            "",
            "```powershell",
            "python scripts/validate_print_readiness.py",
            "python scripts/generate_build_tracker.py",
            "python scripts/generate_job_cards.py",
            "python scripts/sync_documentation.py",
            "python scripts/validate_release_package.py",
            "python scripts/build_step_packages.py",
            "python scripts/build_step_packages.py --check",
            "python scripts/update_checksums.py",
            "```",
            "",
            "If installed tag metrology changes, run `python scripts/generate_fiducials.py --map-only` before documentation sync and release validation.",
            "",
            "## 7. Sign the step with the controlled helper",
            "",
            "When all required test rows and reviewed gates pass, run:",
            "",
            "```powershell",
            "python scripts/sign_off_step.py --step 03 --status PASS --operator \"NAME\"",
            "```",
            "",
            "Add `--witness \"NAME\"` when required. The PASS helper derives accepted test IDs and refuses incomplete or invalid rows. To stop, use `python scripts/sign_off_step.py --step 03 --status HOLD --operator \"NAME\" --hold \"reason\"`; repeat `--hold` for multiple reasons. Raw `signoff.json` editing is an advanced recovery fallback only.",
            "",
            "## 8. Regenerate, verify the handoff, then initialize the next step",
            "",
            "Immediately after signoff, regenerate and check the package:",
            "",
            "```powershell",
            "python scripts/build_step_packages.py",
            "python scripts/build_step_packages.py --check",
            "```",
            "",
            f"Reopen `{ROOT_DASHBOARD_FILE}` or inspect `INDEX.json`. Confirm that the step just signed is `COMPLETE` and its immediate next step is `READY TO START` for the same active build ID. Only after both results are visible may you run:",
            "",
            "```powershell",
            "python scripts/initialize_step_evidence.py --step NN",
            "```",
            "",
            "Do not initialize on `LOCKED`, `HOLD`, `IN PROGRESS`, `COMPLETE`, or stale package state. Step 15 has no next-step initialization; archive its signed release record after final validation.",
        ]
    )
    (STAGING / ROOT_EVIDENCE_FILE).write_text("\n".join(evidence_lines) + "\n", encoding="utf-8")

    glossary_lines = [
        "# Plain-language build glossary",
        "",
        "- **Datum:** A trusted surface, edge, point, or feature from which another position is measured.",
        "- **Build ID:** A unique name tying all raw measurements, files, and signoffs to one physical cell build.",
        "- **Active build:** The single build ID selected in `ACTIVE_BUILD.json`; only that build's evidence may affect computed step state.",
        "- **Canonical gate / record:** The reviewed project-level status and values used by validators; step-local evidence does not update it automatically.",
        "- **Package definition hash:** The stable evidence-binding fingerprint of the models, procedures, gate schema, job definitions, and acceptance logic.",
        "- **Canonical snapshot hash:** The fingerprint of the complete current project snapshot; it changes as reviewed measurements and lifecycle state are synchronized.",
        "- **Raw evidence:** Original measurements, observations, images, projects, and reports saved before a reviewer marks a canonical gate PASS.",
        "- **Route:** One selected hardware/configuration branch. Phone stylus and keyboard rod/TPU are tool routes. `camera_mast_optional` is only the independent fixed-camera fallback; selecting it records scope and never releases its print jobs or substitutes for the intended arm-mounted route.",
        "- **Signoff:** The step-level decision recording required tests, open holds, operator, date, and final status for the active build.",
        "- **Reopen / downstream:** Invalidate and repeat the changed source step plus every later acceptance that depended on it.",
        "- **Master / slave:** The keyboard master owns the location; the slave joins to the master seam and must not create a competing locator system.",
        "- **Locator:** A pin/socket or keyed feature that establishes position. It is not tightened to create clamp force.",
        "- **Clamp or retainer screw:** A screw that holds seated parts against their support; the locator still owns position.",
        "- **Radial slot:** An elongated locator socket that constrains one direction while allowing harmless expansion or tolerance in the other.",
        "- **Shared stack:** One fastener passing through a removable component and a station into the board, retaining both.",
        "- **TCP (tool center point):** The robot-coordinate point representing the active tip/contact location of a tool.",
        "- **Coupon:** A small diagnostic print used with the real hardware to select a fit before production parts are released.",
        "- **First article:** The first full part printed and measured before dependent or batch parts are authorized.",
        "- **Native QIDI project:** The QIDI Studio project saved after profile, object count, orientation, and layer preview are verified; a geometry-only 3MF is not equivalent.",
        "- **Proof load:** A controlled test load applied for a stated duration to demonstrate retention without damage or permanent movement.",
        "- **Yaw:** Rotation in the board plane about +Z.",
        "- **Optical-plane Z:** Height of the visible tag surface above the finished board top, including tag stock and compressed adhesive.",
        "- **HOLD:** Work has started or been reviewed but cannot proceed until a documented issue is corrected and retested.",
        "- **Quarantine:** Physically label and separate a failed, suspect, or unselected part so it cannot enter the build accidentally.",
        "- **READY TO START:** Required canonical inputs are PASS; the step itself has not yet been completed.",
        "- **READY (print readiness):** A selected print job is eligible to slice/print; this is not an assembly-step state.",
        "- **READY_TO_SLICE (job lifecycle):** A validator-derived lifecycle state; operators begin manual lifecycle evidence at SLICE_REVIEWED.",
        "- **LOCKED:** At least one prerequisite gate or route decision is incomplete; do not start the step.",
        "- **COMPLETE:** Required acceptance evidence, canonical completion gates, and the step signoff are all PASS.",
    ]
    (STAGING / ROOT_GLOSSARY_FILE).write_text("\n".join(glossary_lines) + "\n", encoding="utf-8")
    index_doc["generated_root_control_hashes"] = generated_control_hashes(STAGING, ROOT_CONTROL_FILES)
    write_json(STAGING / "INDEX.json", index_doc)

    validation = validate_tree(
        STAGING,
        config,
        jobs_doc,
        measurement,
        readiness,
        expected_snapshot_hash=canonical_hash,
        expected_definition_hash=definition_hash,
    )
    write_json(STAGING / "PACKAGE_VALIDATION.json", validation)
    if validation["status"] != "PASS":
        raise RuntimeError(json.dumps(validation, indent=2))

    if TARGET.exists():
        if not (TARGET / SENTINEL).is_file():
            raise RuntimeError(f"Refusing to replace unrecognized {TARGET}")
        remove_generated(PREVIOUS, PREVIOUS.name, require_sentinel=True)
        try:
            TARGET.rename(PREVIOUS)
        except PermissionError:
            if structural_migration_required:
                raise RuntimeError(
                    "Layout migration requires an atomic folder swap, but Windows has a file open in BUILD_BY_STEP. "
                    "Close every BUILD_BY_STEP file or preview and run scripts/build_step_packages.py again; "
                    "the generator refused an unsafe in-place overlay."
                )
            # Windows may hold the dashboard open in the desktop app.  The staged
            # tree already contains preserved evidence; update managed content in
            # place, remove only explicitly retired generated copies, validate it,
            # and remove only the exact generated staging tree.
            remove_known_legacy_stl_copies(TARGET)
            shutil.copytree(STAGING, TARGET, dirs_exist_ok=True)
            remove_generated(STAGING, STAGING.name, require_sentinel=True)
            in_place_validation = validate_existing(write_report=True)
            if in_place_validation["status"] != "PASS":
                raise RuntimeError(json.dumps(in_place_validation, indent=2))
            return in_place_validation
    STAGING.rename(TARGET)
    remove_generated(PREVIOUS, PREVIOUS.name, require_sentinel=True)
    return validation


def read_generated_json_object(
    path: Path,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    """Read a generated JSON control without allowing corruption to escape validation."""
    try:
        value = read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is unreadable JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} root must be an object")
        return None
    return value


def validate_tree(
    base: Path,
    config: dict[str, Any],
    jobs_doc: dict[str, Any],
    measurement: dict[str, Any],
    readiness: dict[str, Any],
    expected_snapshot_hash: str | None = None,
    expected_definition_hash: str | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    jobs = {job["job_id"]: job for job in jobs_doc["jobs"]}
    steps = config["steps"]
    gate_ids = set(measurement["gates"])
    step_ids = [step["id"] for step in steps]
    referenced_paths: set[str] = set()
    local_stl_copy_total = 0
    hash_bound_stl_reference_total = 0

    if not (base / SENTINEL).is_file():
        errors.append(f"missing {SENTINEL}")
    elif f"layout_version={LAYOUT_VERSION}" not in (base / SENTINEL).read_text(encoding="utf-8"):
        errors.append(f"{SENTINEL} layout version is not {LAYOUT_VERSION}")
    for required_root_file in (
        "README.md",
        ROOT_DASHBOARD_FILE,
        ROOT_SEQUENCE_FILE,
        ROOT_EVIDENCE_FILE,
        ROOT_GLOSSARY_FILE,
        ACTIVE_BUILD_FILE,
        "INDEX.json",
        "PRINT_JOB_OWNERSHIP.csv",
    ):
        if not (base / required_root_file).is_file():
            errors.append(f"missing root package file {required_root_file}")
    active_build = load_active_build(base)
    if active_build.get("configuration_error"):
        errors.append(active_build["configuration_error"])
    active_build_id = active_build.get("active_build_id")
    if step_ids != [f"{value:02d}" for value in range(16)]:
        errors.append("step IDs are not exactly 00 through 15")
    operator_folders = [step.get("operator_folder") for step in steps]
    operator_titles = [step.get("operator_title") for step in steps]
    if len(set(operator_folders)) != len(steps) or any(not isinstance(value, str) for value in operator_folders):
        errors.append("operator folder names are missing or duplicated")
    if any(not isinstance(value, str) or not value.strip() for value in operator_titles):
        errors.append("operator titles are missing or blank")
    expected_step_folders = {step_folder_name(step) for step in steps}
    actual_step_folders = {
        path.name
        for path in base.iterdir()
        if path.is_dir() and re.match(r"^\d{2}(?:_| - )", path.name)
    } if base.is_dir() else set()
    unexpected_step_folders = sorted(actual_step_folders - expected_step_folders)
    if unexpected_step_folders:
        errors.append(f"unexpected generated step folders are present: {unexpected_step_folders}")
    if base.is_dir():
        allowed_root_entries = expected_step_folders | {
            SENTINEL,
            "README.md",
            ROOT_DASHBOARD_FILE,
            ROOT_SEQUENCE_FILE,
            ROOT_EVIDENCE_FILE,
            ROOT_GLOSSARY_FILE,
            ACTIVE_BUILD_FILE,
            "INDEX.json",
            "PRINT_JOB_OWNERSHIP.csv",
            "PACKAGE_VALIDATION.json",
        }
        unexpected_root_entries = sorted(path.name for path in base.iterdir() if path.name not in allowed_root_entries)
        if unexpected_root_entries:
            errors.append(f"unexpected generated package-root paths are present: {unexpected_root_entries}")
    computed_states: dict[str, tuple[str, list[str]]] = {}
    for step in steps:
        step_dir = base / step_folder_name(step)
        computed_states[step["id"]] = compute_state(
            step,
            measurement,
            step_dir if step_dir.is_dir() else None,
            computed_states,
            active_build_id,
            expected_definition_hash or "",
        )
    for step in steps:
        conditional = []
        for mapping in (step.get("conditional_input_gates", {}), step.get("conditional_completion_gates", {})):
            for mapped_gates in mapping.values():
                conditional.extend(mapped_gates)
        acceptance_rows = list(step.get("acceptance", []))
        for rows in step.get("conditional_acceptance", {}).values():
            acceptance_rows.extend(rows)
        acceptance_gate_ids = [item["gate_id"] for item in acceptance_rows if item.get("gate_id")]
        unknown_gates = sorted(
            set(step.get("input_gates", []) + step.get("completion_gates", []) + conditional + acceptance_gate_ids)
            - gate_ids
        )
        if unknown_gates:
            errors.append(f"step {step['id']} has unknown gates: {unknown_gates}")
        test_ids = [item["test_id"] for item in acceptance_rows]
        if len(test_ids) != len(set(test_ids)):
            errors.append(f"step {step['id']} has duplicate acceptance test IDs")
        for prerequisite in step.get("prerequisite_steps", []):
            if prerequisite not in step_ids or step_ids.index(prerequisite) >= step_ids.index(step["id"]):
                errors.append(f"step {step['id']} has invalid prerequisite {prerequisite}")
        folder = base / step_folder_name(step)
        if not folder.is_dir():
            errors.append(f"missing step folder {folder.name}")
            continue
        exact_required_files = required_step_files(step)
        for relative in exact_required_files:
            if not (folder / relative).is_file():
                errors.append(f"{folder.name} missing {relative}")
        expected_top_entries = {Path(relative).parts[0] for relative in exact_required_files}
        actual_top_entries = {path.name for path in folder.iterdir()}
        unexpected_top_entries = sorted(actual_top_entries - expected_top_entries)
        if unexpected_top_entries:
            errors.append(f"{folder.name} has unexpected generated top-level paths: {unexpected_top_entries}")
        technical_dir = folder / STEP_TECHNICAL_DIRECTORY
        expected_technical_entries = {
            Path(STEP_MANIFEST_FILE).name,
            Path(STEP_OPEN_FILES).name,
            Path(STEP_FILE_INDEX).name,
            Path(STEP_FILE_MANIFEST).name,
            Path(STEP_FILE_HASHES).name,
            Path(STEP_HARDWARE_CSV).name,
        }
        technical_entries = {path.name for path in technical_dir.iterdir()} if technical_dir.is_dir() else set()
        if technical_entries != expected_technical_entries:
            errors.append(f"{folder.name} technical-record folder contains unexpected or missing paths")
        evidence_root = folder / STEP_EVIDENCE_DIRECTORY
        if evidence_root.is_dir():
            for entry in evidence_root.iterdir():
                if entry.is_file() and entry.name != STEP_EVIDENCE_README:
                    errors.append(f"{folder.name} has unexpected evidence-root file: {entry.name}")
                elif entry.is_dir() and entry.name != EVIDENCE_TEMPLATE_DIRECTORY and not valid_build_id(entry.name):
                    errors.append(f"{folder.name} has invalid evidence build-ID directory: {entry.name}")
        manifest_path = folder / STEP_MANIFEST_FILE
        if not manifest_path.is_file():
            continue
        manifest = read_generated_json_object(
            manifest_path,
            f"{folder.name} STEP_MANIFEST.json",
            errors,
        )
        if manifest is None:
            continue
        if manifest.get("layout_version") != LAYOUT_VERSION:
            errors.append(f"{folder.name} manifest layout version is stale")
        if manifest.get("step_id") != step["id"]:
            errors.append(f"{folder.name} manifest step ID mismatch")
        if manifest.get("operator_folder") != step["operator_folder"]:
            errors.append(f"{folder.name} manifest operator folder is stale")
        if manifest.get("operator_title") != step["operator_title"]:
            errors.append(f"{folder.name} manifest operator title is stale")
        if expected_definition_hash and manifest.get("package_definition_hash") != expected_definition_hash:
            errors.append(f"{folder.name} package definition hash is stale")
        if expected_snapshot_hash and manifest.get("canonical_snapshot_hash") != expected_snapshot_hash:
            errors.append(f"{folder.name} canonical snapshot hash is stale")
        if expected_snapshot_hash and manifest.get("canonical_input_hash") != expected_snapshot_hash:
            errors.append(f"{folder.name} legacy canonical input hash alias is stale")
        if manifest.get("active_build_id") != active_build_id:
            errors.append(f"{folder.name} active build ID is stale")
        controlled_paths = [relative for relative in exact_required_files if relative != STEP_MANIFEST_FILE]
        recorded_control_hashes = manifest.get("generated_control_hashes")
        if not isinstance(recorded_control_hashes, dict) or set(recorded_control_hashes) != set(controlled_paths):
            errors.append(f"{folder.name} generated-control hash manifest is incomplete")
        else:
            for relative in controlled_paths:
                path = folder / relative
                if path.is_file() and recorded_control_hashes.get(relative) != sha256(path):
                    errors.append(f"{folder.name} generated control file was edited or is stale: {relative}")
        current_state, current_blockers = computed_states[step["id"]]
        if manifest.get("state_at_generation") != current_state:
            errors.append(
                f"{folder.name} computed state is stale; expected {current_state}, "
                f"found {manifest.get('state_at_generation')}"
            )
        if manifest.get("blocked_input_gates") != current_blockers:
            errors.append(f"{folder.name} blocker list is stale")
        guide_path = folder / STEP_START_FILE
        before_path = folder / STEP_BEFORE_FILE
        parts_path = folder / STEP_PARTS_FILE
        instructions_path = folder / STEP_INSTRUCTIONS_FILE
        acceptance_path = folder / STEP_CHECK_FILE
        if guide_path.is_file():
            guide_text = guide_path.read_text(encoding="utf-8")
            expected_state_text = f"**Current result:** **{display_state(current_state)}**"
            if expected_state_text not in guide_text:
                errors.append(f"{folder.name} plain-language guide state text is stale")
            next_step_id = manifest.get("next_step")
            if current_state != "COMPLETE" and next_step_id:
                next_config = next((item for item in steps if item["id"] == next_step_id), None)
                if next_config:
                    forbidden_target = f"../{step_folder_name(next_config)}/{STEP_START_FILE}"
                    finish_text = (folder / STEP_FINISH_FILE).read_text(encoding="utf-8")
                    if forbidden_target in guide_text or forbidden_target in finish_text:
                        errors.append(f"{folder.name} exposes a clickable next-step link before COMPLETE")
            if "## Why this step cannot start or continue" in guide_text:
                errors.append(f"{folder.name} START HERE duplicates detailed blockers")
            if f"[{STEP_BEFORE_FILE}]" not in guide_text:
                errors.append(f"{folder.name} START HERE does not link to its prerequisite details")
        if current_state == "LOCKED" and before_path.is_file():
            before_text = before_path.read_text(encoding="utf-8")
            if "## Do not begin" in before_text:
                errors.append(f"{folder.name} repeats a locked blocker list below its gate table")
            if before_text.count("**STOP:** This step is locked.") != 1:
                errors.append(f"{folder.name} must contain exactly one concise locked-step stop rule")
        if parts_path.is_file():
            parts_text = parts_path.read_text(encoding="utf-8")
            for item in unique_required_inputs(step):
                expected_row = f"| As specified | {item} | Present, identified, and accepted before work |"
                if parts_text.count(expected_row) != 1:
                    errors.append(f"{folder.name} parts checklist does not contain required input exactly once: {item}")
            for item in unique_hardware_rows(step):
                expected_row = f"| {item['type']} | {item['qty']} | {item['item']} | {item['condition']} |"
                if parts_text.count(expected_row) != 1:
                    errors.append(f"{folder.name} parts checklist does not contain structured row exactly once: {item['item']}")
        hardware_csv_path = folder / STEP_HARDWARE_CSV
        if hardware_csv_path.is_file():
            with hardware_csv_path.open(encoding="utf-8", newline="") as stream:
                gather_rows = list(csv.DictReader(stream))
            expected_required = unique_required_inputs(step)
            actual_required = [row.get("item") for row in gather_rows if row.get("source") == "required_physical_input"]
            if actual_required != expected_required:
                errors.append(f"{folder.name} hardware CSV required-input rows are stale or duplicated")
            expected_structured = [
                (str(item["type"]), str(item["qty"]), str(item["item"]), str(item["condition"]))
                for item in unique_hardware_rows(step)
            ]
            actual_structured = [
                (row.get("type"), row.get("qty"), row.get("item"), row.get("critical_condition"))
                for row in gather_rows
                if row.get("source") == "structured_register"
            ]
            if actual_structured != expected_structured:
                errors.append(f"{folder.name} hardware CSV structured rows are stale or duplicated")
        if acceptance_path.is_file():
            signoff, signoff_errors = read_active_signoff(
                folder, step, measurement, active_build_id, expected_definition_hash or ""
            )
            signoff_status = (
                signoff.get("status", "NOT_STARTED")
                if signoff
                else ("INVALID — HOLD" if signoff_errors else "NOT_STARTED")
            )
            expected_signoff_row = f"| active-build step signoff | **{signoff_status}** |"
            if expected_signoff_row not in acceptance_path.read_text(encoding="utf-8"):
                errors.append(f"{folder.name} acceptance signoff status is stale")
        expected_local_stls: set[str] = set()
        canonical_file_rows = manifest.get("canonical_files")
        if not isinstance(canonical_file_rows, list) or not all(
            isinstance(record, dict) for record in canonical_file_rows
        ):
            errors.append(f"{folder.name} manifest canonical_files must be a list of objects")
            canonical_file_rows = []
        for record in canonical_file_rows:
            canonical_path = record.get("canonical_path")
            recorded_hash = record.get("sha256")
            if not isinstance(canonical_path, str) or not canonical_path or not isinstance(recorded_hash, str):
                errors.append(f"{folder.name} manifest has an invalid canonical file record")
                continue
            referenced_paths.add(canonical_path)
            path = ROOT / canonical_path
            if not path.is_file():
                errors.append(f"{folder.name} missing canonical source {canonical_path}")
            elif sha256(path) != recorded_hash:
                errors.append(f"{folder.name} source hash changed: {canonical_path}")
            if canonical_path.startswith("stl/") and canonical_path.lower().endswith(".stl"):
                expected_usage = (
                    "DO_NOT_PRINT"
                    if "DO_NOT_PRINT" in record.get("actions", []) or "DO_NOT_PRINT" in Path(canonical_path).name
                    else ("PRINT_VIA_READY_JOB_ONLY" if step["id"] == "00" else "TRACEABILITY_ONLY_DO_NOT_PRINT")
                )
                if record.get("local_copy_usage") != expected_usage:
                    errors.append(f"{folder.name} has wrong STL usage label for {canonical_path}")
                if step_stl_is_local_copy(step["id"], Path(canonical_path).name):
                    local_copy = record.get("local_operator_copy")
                    if not isinstance(local_copy, str) or not local_copy:
                        errors.append(f"{folder.name} lacks a local STL copy for {canonical_path}")
                        continue
                    local_path = folder / local_copy
                    expected_local_stls.add(local_path.name)
                    if record.get("artifact_resolution") != "local_hash_verified_copy":
                        errors.append(f"{folder.name} has wrong STL resolution for {canonical_path}")
                    if record.get("local_copy_sha256") != recorded_hash:
                        errors.append(f"{folder.name} local copy record hash mismatch: {local_copy}")
                    if not local_path.is_file():
                        errors.append(f"{folder.name} missing local STL {local_copy}")
                    elif sha256(local_path) != recorded_hash:
                        errors.append(f"{folder.name} local STL hash mismatch: {local_copy}")
                    else:
                        local_stl_copy_total += 1
                else:
                    expected_reference = Path(os.path.relpath(path, folder / STEP_STL_DIRECTORY)).as_posix()
                    if record.get("artifact_resolution") != "canonical_hash_bound_reference":
                        errors.append(f"{folder.name} has wrong canonical STL resolution for {canonical_path}")
                    if record.get("canonical_reference") != expected_reference:
                        errors.append(f"{folder.name} has stale canonical STL reference for {canonical_path}")
                    if any(
                        key in record
                        for key in ("local_operator_copy", "local_copy_sha256")
                    ):
                        errors.append(f"{folder.name} retains local-copy fields for {canonical_path}")
                    hash_bound_stl_reference_total += 1
        if instructions_path.is_file():
            instructions_text = instructions_path.read_text(encoding="utf-8")
            try:
                direct_records = actionable_file_records(step, canonical_file_rows)
            except ValueError as exc:
                errors.append(str(exc))
                direct_records = []
            action_heading = "## Phase 00.1" if step["id"] == "00" else "## Numbered actions"
            if "## Files used in this step" not in instructions_text:
                errors.append(f"{folder.name} instructions lack the direct files-used section")
            elif action_heading not in instructions_text or instructions_text.index(
                "## Files used in this step"
            ) > instructions_text.index(action_heading):
                errors.append(f"{folder.name} direct files-used section is not before its actions")
            for record in direct_records:
                canonical_path = record["canonical_path"]
                expected_link = markdown_link(canonical_path, folder, ROOT / canonical_path)
                if expected_link not in instructions_text:
                    errors.append(f"{folder.name} instructions lack canonical action link {canonical_path}")
            if step["id"] == "00":
                for route in ("phone_stylus_route", "keyboard_rod_route", "camera_mast_optional"):
                    for selected in ("yes", "no"):
                        command = (
                            "python scripts/record_print_measurement.py "
                            f"--route {route} --selected {selected}"
                        )
                        if command not in instructions_text:
                            errors.append(f"Step 00 instructions lack explicit route command: {route}={selected}")
        drill_guide_path = folder / STEP_DRILL_GUIDE_FILE
        if step["id"] == "01" and drill_guide_path.is_file():
            drill_guide_text = drill_guide_path.read_text(encoding="utf-8")
            required_drill_guide_phrases = (
                "RC03 Board Drill Guide — Letter 1:1",
                "RC03 Board Drill Guide — 24 x 36 Full Size 1:1",
                "Pages 4-12",
                "12 mm",
                "Never butt paper edges",
                "100.0 +/- 0.2 mm",
                "CENTER-PUNCH ONLY",
                "local thickness minus 2.0 mm",
                "complete three-station, nine-retainer dry fit",
            )
            for phrase in required_drill_guide_phrases:
                if phrase not in drill_guide_text:
                    errors.append(f"{folder.name} drill-guide helper lacks required safety text: {phrase}")
            with (ROOT / "drawings" / "board_hole_coordinates.csv").open(encoding="utf-8", newline="") as stream:
                coordinate_rows = list(csv.DictReader(stream))
            for row in coordinate_rows:
                if drill_guide_text.count(f"`{row['id']}`") < 1:
                    errors.append(f"{folder.name} drill-guide helper omits coordinate ID {row['id']}")
        actual_local_stls = {path.name for path in (folder / STEP_STL_DIRECTORY).glob("*.stl")}
        if actual_local_stls != expected_local_stls:
            errors.append(
                f"{folder.name} local STL set mismatch; expected {sorted(expected_local_stls)}, found {sorted(actual_local_stls)}"
            )
        if manifest.get("local_stl_copy_count") != len(expected_local_stls):
            errors.append(f"{folder.name} local_stl_copy_count is wrong")
        expected_reference_count = sum(
            record.get("artifact_resolution") == "canonical_hash_bound_reference"
            for record in canonical_file_rows
        )
        if manifest.get("hash_bound_stl_reference_count") != expected_reference_count:
            errors.append(f"{folder.name} hash_bound_stl_reference_count is wrong")
        stl_directory = folder / STEP_STL_DIRECTORY
        actual_stl_entries = {path.name for path in stl_directory.iterdir()} if stl_directory.is_dir() else set()
        expected_stl_entries = expected_local_stls | {STEP_STL_README, STEP_STL_CATALOG}
        if actual_stl_entries != expected_stl_entries:
            errors.append(f"{folder.name} STL directory contains unexpected or missing paths")
        template_values: dict[str, dict[str, Any]] = {}
        for template_name in (MEASUREMENT_RECORD_FILE, SIGNOFF_RECORD_FILE):
            template_path = folder / STEP_EVIDENCE_DIRECTORY / EVIDENCE_TEMPLATE_DIRECTORY / template_name
            if template_path.is_file():
                template_value = read_generated_json_object(
                    template_path,
                    f"{folder.name} {template_name}",
                    errors,
                )
                if template_value is None:
                    continue
                template_values[template_name] = template_value
                if template_value.get("design_revision") != "RC03-INT-R1":
                    errors.append(f"{folder.name} {template_name} revision is stale")
                if expected_definition_hash and template_value.get("package_definition_hash") != expected_definition_hash:
                    errors.append(f"{folder.name} {template_name} package definition hash is stale")
                if expected_snapshot_hash and template_value.get("canonical_snapshot_hash") != expected_snapshot_hash:
                    errors.append(f"{folder.name} {template_name} canonical snapshot hash is stale")
                if expected_snapshot_hash and template_value.get("canonical_input_hash") != expected_snapshot_hash:
                    errors.append(f"{folder.name} {template_name} legacy canonical input hash alias is stale")
                if template_value.get("step_id") != step["id"]:
                    errors.append(f"{folder.name} {template_name} step ID is wrong")
        expected_test_ids = [item["test_id"] for item in effective_acceptance(step, measurement)]
        measurement_template = folder / STEP_EVIDENCE_DIRECTORY / EVIDENCE_TEMPLATE_DIRECTORY / MEASUREMENT_RECORD_FILE
        measurement_template_value = template_values.get(MEASUREMENT_RECORD_FILE)
        if measurement_template.is_file() and measurement_template_value is not None:
            template_rows_value = measurement_template_value.get("measurements")
            valid_template_rows = isinstance(template_rows_value, list) and all(
                isinstance(row, dict) for row in template_rows_value
            )
            template_rows = template_rows_value if valid_template_rows else []
            if not valid_template_rows:
                errors.append(f"{folder.name} measurement template rows must be a list of objects")
            elif [row.get("test_id") for row in template_rows] != expected_test_ids:
                errors.append(f"{folder.name} measurement template test rows are stale or out of order")
            required_row_fields = {
                "test_id", "criterion", "value_or_observation", "unit", "instrument_id",
                "evidence_files", "result", "notes",
            }
            for row in template_rows:
                if set(row) != required_row_fields or row.get("result") != "NOT_TESTED":
                    errors.append(f"{folder.name} measurement template row schema is invalid")
                    break
        signoff_template = folder / STEP_EVIDENCE_DIRECTORY / EVIDENCE_TEMPLATE_DIRECTORY / SIGNOFF_RECORD_FILE
        signoff_value = template_values.get(SIGNOFF_RECORD_FILE)
        if signoff_template.is_file() and signoff_value is not None:
            if signoff_value.get("required_test_ids") != expected_test_ids:
                errors.append(f"{folder.name} signoff required_test_ids are stale")
            if signoff_value.get("accepted_test_ids") != [] or signoff_value.get("status") != "NOT_STARTED":
                errors.append(f"{folder.name} signoff template must start unaccepted")
        result_help_paths = (
            folder / STEP_EVIDENCE_DIRECTORY / STEP_EVIDENCE_README,
            folder / STEP_EVIDENCE_DIRECTORY / EVIDENCE_TEMPLATE_DIRECTORY / MEASUREMENTS_CHECKLIST_FILE,
            folder / STEP_CHECK_FILE,
        )
        for help_path in result_help_paths:
            if not help_path.is_file():
                continue
            help_text = help_path.read_text(encoding="utf-8")
            if f"record_step_result.py --step {step['id']}" not in help_text:
                errors.append(f"{folder.name} {help_path.name} lacks the step-aware result helper")
            if any(token not in help_text for token in ("relative", "contained", "exist", "advanced recovery fallback only")):
                errors.append(f"{folder.name} {help_path.name} lacks complete evidence-path/fallback rules")
        signoff_help_paths = (
            folder / STEP_EVIDENCE_DIRECTORY / STEP_EVIDENCE_README,
            folder / STEP_EVIDENCE_DIRECTORY / EVIDENCE_TEMPLATE_DIRECTORY / FINISH_SIGNOFF_FILE,
            folder / STEP_FINISH_FILE,
        )
        for help_path in signoff_help_paths:
            if not help_path.is_file():
                continue
            help_text = help_path.read_text(encoding="utf-8")
            if f"sign_off_step.py --step {step['id']}" not in help_text:
                errors.append(f"{folder.name} {help_path.name} lacks the step-aware signoff helper")
            if "advanced recovery fallback only" not in help_text:
                errors.append(f"{folder.name} {help_path.name} lacks the raw-JSON fallback warning")
        canonical_path_set = {
            record.get("canonical_path")
            for record in canonical_file_rows
            if isinstance(record.get("canonical_path"), str)
        }
        for helper_path in ("scripts/record_step_result.py", "scripts/sign_off_step.py"):
            if helper_path not in canonical_path_set:
                errors.append(f"{folder.name} manifest omits controlled evidence helper {helper_path}")
        read_only_markdown = [
            folder / STEP_START_FILE,
            folder / STEP_BEFORE_FILE,
            folder / STEP_PARTS_FILE,
            folder / STEP_INSTRUCTIONS_FILE,
            folder / STEP_CHECK_FILE,
            folder / STEP_FINISH_FILE,
            folder / STEP_STL_DIRECTORY / STEP_STL_README,
            folder / STEP_EVIDENCE_DIRECTORY / STEP_EVIDENCE_README,
            folder / STEP_OPEN_FILES,
        ]
        if step["id"] == "01":
            read_only_markdown.append(folder / STEP_DRILL_GUIDE_FILE)
        for markdown_path in read_only_markdown:
            if markdown_path.is_file() and re.search(r"\[[ xX]\]", markdown_path.read_text(encoding="utf-8")):
                errors.append(f"{folder.name} read-only document contains a misleading checkbox: {markdown_path.name}")

    ownership: defaultdict[str, list[str]] = defaultdict(list)
    for step in steps:
        if step.get("print_action") == "produce_here":
            for job_id in step.get("print_jobs", []):
                ownership[job_id].append(step["id"])
        unknown_jobs = sorted(set(step.get("print_jobs", [])) - set(jobs))
        if unknown_jobs:
            errors.append(f"step {step['id']} has unknown print jobs: {unknown_jobs}")
    for job_id in jobs:
        if ownership[job_id] != ["00"]:
            errors.append(f"print job {job_id} must have Step 00 as its only producer; found {ownership[job_id]}")

    panels = [step.get("panel") for step in steps if step.get("panel")]
    if len(panels) != 15 or len(set(panels)) != 15:
        errors.append("the package must own exactly 15 unique assembly panels")

    index_path = base / "INDEX.json"
    if index_path.is_file():
        index_value = read_generated_json_object(index_path, "INDEX.json", errors)
    else:
        index_value = None
    if index_value is not None:
        if index_value.get("layout_version") != LAYOUT_VERSION:
            errors.append("INDEX.json layout version is stale")
        if expected_definition_hash and index_value.get("package_definition_hash") != expected_definition_hash:
            errors.append("INDEX.json package definition hash is stale")
        if expected_snapshot_hash and index_value.get("canonical_snapshot_hash") != expected_snapshot_hash:
            errors.append("INDEX.json canonical snapshot hash is stale")
        if expected_snapshot_hash and index_value.get("canonical_input_hash") != expected_snapshot_hash:
            errors.append("INDEX.json legacy canonical input hash alias is stale")
        if index_value.get("active_build_id") != active_build_id:
            errors.append("INDEX.json active build ID is stale")
        root_control_hashes = index_value.get("generated_root_control_hashes")
        if not isinstance(root_control_hashes, dict) or set(root_control_hashes) != set(ROOT_CONTROL_FILES):
            errors.append("INDEX.json generated-root-control hashes are incomplete")
        else:
            for relative in ROOT_CONTROL_FILES:
                path = base / relative
                if path.is_file() and root_control_hashes.get(relative) != sha256(path):
                    errors.append(f"generated root control file was edited or is stale: {relative}")
        expected_first_locked = next(
            (step_id for step_id in step_ids if computed_states[step_id][0] == "LOCKED"), None
        )
        expected_first_blocked = next(
            (step_id for step_id in step_ids if computed_states[step_id][0] in {"HOLD", "LOCKED"}), None
        )
        expected_first_attention = next(
            (step_id for step_id in step_ids if computed_states[step_id][0] != "COMPLETE"), None
        )
        for field, expected in (
            ("first_locked_step", expected_first_locked),
            ("first_blocked_step", expected_first_blocked),
            ("first_attention_step", expected_first_attention),
        ):
            if index_value.get(field) != expected:
                errors.append(f"INDEX.json {field} is stale")
        index_rows = index_value.get("steps")
        if (
            not isinstance(index_rows, list)
            or not all(isinstance(row, dict) for row in index_rows)
            or [row.get("id") for row in index_rows] != step_ids
        ):
            errors.append("INDEX.json step rows are missing, duplicated, or out of order")
        else:
            for row in index_rows:
                current_state, current_blockers = computed_states[row["id"]]
                if row.get("state") != current_state or row.get("blocked_input_gates") != current_blockers:
                    errors.append(f"INDEX.json state/blockers are stale for Step {row['id']}")
                source_step = next(item for item in steps if item["id"] == row["id"])
                if row.get("folder") != step_folder_name(source_step):
                    errors.append(f"INDEX.json folder is stale for Step {row['id']}")
                if row.get("operator_title") != source_step["operator_title"]:
                    errors.append(f"INDEX.json operator title is stale for Step {row['id']}")

    simple_sequence_path = base / ROOT_SEQUENCE_FILE
    if simple_sequence_path.is_file():
        complete_count = sum(state == "COMPLETE" for state, _ in computed_states.values())
        first_attention = next(
            (step_id for step_id in step_ids if computed_states[step_id][0] != "COMPLETE"), None
        )
        if first_attention:
            expected_sequence_text = (
                f"**Current sequence status:** {complete_count}/16 steps COMPLETE; "
                f"Step {first_attention} is the first non-complete step and is "
                f"**{display_state(computed_states[first_attention][0])}**."
            )
        else:
            expected_sequence_text = "**Current sequence status:** all 16 steps are COMPLETE for the active build."
        if expected_sequence_text not in simple_sequence_path.read_text(encoding="utf-8"):
            errors.append(f"{ROOT_SEQUENCE_FILE} current-state summary is stale")

    root_evidence_path = base / ROOT_EVIDENCE_FILE
    if root_evidence_path.is_file():
        root_evidence_text = root_evidence_path.read_text(encoding="utf-8")
        for route in ("phone_stylus_route", "keyboard_rod_route", "camera_mast_optional"):
            for selected in ("yes", "no"):
                command = f"python scripts/record_print_measurement.py --route {route} --selected {selected}"
                if command not in root_evidence_text:
                    errors.append(f"{ROOT_EVIDENCE_FILE} lacks explicit route command: {route}={selected}")
        if "record_step_result.py --step 03" not in root_evidence_text:
            errors.append(f"{ROOT_EVIDENCE_FILE} lacks the controlled result-helper example")
        if "sign_off_step.py --step 03" not in root_evidence_text:
            errors.append(f"{ROOT_EVIDENCE_FILE} lacks the controlled signoff-helper example")
        if any(
            token not in root_evidence_text
            for token in ("relative", "contained", "already exists", "advanced recovery fallback only")
        ):
            errors.append(f"{ROOT_EVIDENCE_FILE} lacks complete evidence-path/fallback rules")
        handoff_heading = "## 8. Regenerate, verify the handoff, then initialize the next step"
        if handoff_heading not in root_evidence_text:
            errors.append(f"{ROOT_EVIDENCE_FILE} lacks the final regeneration handoff")
        else:
            handoff = root_evidence_text[root_evidence_text.index(handoff_heading) :]
            ordered_terms = (
                "python scripts/build_step_packages.py",
                "python scripts/build_step_packages.py --check",
                "`COMPLETE`",
                "`READY TO START`",
                "python scripts/initialize_step_evidence.py --step NN",
            )
            positions = [handoff.find(term) for term in ordered_terms]
            if any(position < 0 for position in positions) or positions != sorted(positions):
                errors.append(f"{ROOT_EVIDENCE_FILE} final handoff order is incomplete or unsafe")

    coverage_groups = {
        "stl": {path.relative_to(ROOT).as_posix() for path in (ROOT / "stl").glob("*.stl")},
        "step": {path.relative_to(ROOT).as_posix() for path in (ROOT / "cad" / "step").glob("*.step")},
        "print_plate": {path.relative_to(ROOT).as_posix() for path in (ROOT / "print_plates_3mf").glob("*.3mf")},
        "print_sidecar": {path.relative_to(ROOT).as_posix() for path in (ROOT / "print_plates_3mf").glob("*.print.json")},
        "print_settings": {path.relative_to(ROOT).as_posix() for path in (ROOT / "print_plates_3mf").glob("*.PRINT_SETTINGS.md")},
        "qidi_process_profile": {path.relative_to(ROOT).as_posix() for path in (ROOT / "slicer_profiles" / "QIDI_PLUS4").glob("*.process.json")},
        "job_card": {path.relative_to(ROOT).as_posix() for path in (ROOT / "job_cards").glob("JOB-*.md")},
        "drawing": {path.relative_to(ROOT).as_posix() for path in (ROOT / "drawings").glob("*") if path.is_file()},
        "fiducial": {path.relative_to(ROOT).as_posix() for path in (ROOT / "fiducials").glob("*") if path.is_file()},
        "assembly_panel": {path.relative_to(ROOT).as_posix() for path in (ROOT / "output" / "assembly_guide" / "images").glob("*.png")},
    }
    coverage_counts: dict[str, dict[str, int]] = {}
    for name, expected in coverage_groups.items():
        missing = sorted(expected - referenced_paths)
        coverage_counts[name] = {"expected": len(expected), "referenced": len(expected & referenced_paths)}
        if missing:
            errors.append(f"{name} coverage is incomplete: {missing}")

    if not any(
        measurement["selected_routes"].get(route, False)
        for route in ("phone_stylus_route", "keyboard_rod_route")
    ):
        warnings.append("No tool route is selected; route-dependent Step 00 and Step 14 work cannot be completed.")
    if not measurement["selected_routes"].get("camera_mast_optional"):
        warnings.append("The legacy fixed-mast route is correctly unselected. Step 13 uses the selected commercial tripod, which remains unqualified until its hash-bound intake and collision evidence are complete.")
    if readiness["summary"]["ready"] == 0:
        warnings.append("No print job is currently READY; do not start a production print from any step package.")
    override_example = read_json(ROOT / "config" / "user_overrides.example.json")
    parameters = read_json(ROOT / "config" / "parameters.json")
    missing_override_keys = sorted(REQUIRED_GEOMETRY_OVERRIDE_KEYS - set(override_example))
    unknown_override_keys = sorted(set(override_example) - set(parameters))
    if missing_override_keys:
        errors.append(
            "user_overrides.example.json is missing mapped geometry keys: "
            + ", ".join(missing_override_keys)
        )
    if unknown_override_keys:
        errors.append(
            "user_overrides.example.json contains keys absent from parameters.json: "
            + ", ".join(unknown_override_keys)
        )

    with (ROOT / "FASTENER_MAP.csv").open(encoding="utf-8", newline="") as stream:
        fastener_rows = list(csv.DictReader(stream))
    unresolved_fasteners = [
        row["feature_id"]
        for row in fastener_rows
        if not row["selected_length_mm"].strip() or not row["anchor_type"].strip() or not row["final_board_bore_mm"].strip()
    ]
    if unresolved_fasteners:
        warnings.append(
            "Board fastener selections remain physically unresolved for: " + ", ".join(unresolved_fasteners)
        )

    return {
        "schema_version": 1,
        "design_revision": "RC03-INT-R1",
        "status": "PASS" if not errors else "FAIL",
        "physical_release": "UNRELEASED",
        "package_definition_hash": expected_definition_hash,
        "canonical_snapshot_hash": expected_snapshot_hash,
        "canonical_input_hash": expected_snapshot_hash,
        "step_count": len(steps),
        "assembly_panel_count": len(panels),
        "print_job_count": len(jobs),
        "print_job_single_owner": not any(ownership[job_id] != ["00"] for job_id in jobs),
        "canonical_artifact_coverage": coverage_counts,
        "canonical_files_are_links_not_copies": True,
        "local_stl_copies_verified": local_stl_copy_total,
        "hash_bound_stl_references_verified": hash_bound_stl_reference_total,
        "operator_evidence_preserved_on_regeneration": True,
        "readiness_summary": readiness["summary"],
        "errors": errors,
        "warnings": warnings,
    }


def validate_existing(write_report: bool = True) -> dict[str, Any]:
    config, jobs_doc, measurement, readiness = load_sources()
    jobs = {job["job_id"]: job for job in jobs_doc["jobs"]}
    step_files = {step["id"]: files_for_step(step, jobs) for step in config["steps"]}
    expected_snapshot_hash = canonical_input_hash(config, step_files)
    expected_definition_hash = package_definition_hash(config, jobs_doc, measurement, step_files)
    result = validate_tree(
        TARGET,
        config,
        jobs_doc,
        measurement,
        readiness,
        expected_snapshot_hash=expected_snapshot_hash,
        expected_definition_hash=expected_definition_hash,
    )
    if write_report and TARGET.is_dir():
        write_json(TARGET / "PACKAGE_VALIDATION.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Validate the existing BUILD_BY_STEP package without regenerating it")
    args = parser.parse_args()
    result = validate_existing(write_report=True) if args.check else build()
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
