"""Simulation-first RoCell command-line interface.

No live motion command is registered here.  Hardware adapters are imported only
inside a handler after its immutable capability gate has passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Callable, Mapping, Sequence

from rocell import __version__
from rocell.application.first_power_on_onboarding import (
    first_power_on_scenario_names,
    first_power_on_stage_names,
)
from rocell.errors import (
    CapabilityDeniedError,
    CliError,
    ConfigurationError,
    ExitCode,
    HardwareError,
    UsageError,
)
from rocell.models.actions import ActionPlan
from rocell.motion import DryRunEngine, DryRunError
from rocell.rc03 import (
    BuildImportError,
    BuildIntegrityError,
    Capability,
    CapabilityAssessment,
    BuildSnapshot,
    assess_capability,
    import_build_snapshot,
    project_capabilities,
)
from rocell.typing import compile_development_text
from rocell.typing.unicode_support import UnsupportedCharacterError


JSON_INDENT = 2
DEFAULT_MANIFEST_RELATIVE = Path("software/config/system_manifest.json")
DEFAULT_B0477_PROFILE_RELATIVE = Path(
    "software/config/camera_profiles/arducam_b0477_imx283_16mm.json"
)
DEFAULT_B0477_UVC_INVENTORY_RELATIVE = Path(
    "software/tests/fixtures/camera/b0477_nominal_uvc_inventory.json"
)
DEFAULT_B0477_INTRINSICS_REHEARSAL_RELATIVE = Path(
    "software/tests/fixtures/camera/b0477_synthetic_intrinsics_rehearsal.json"
)
# Freezes 006 through 009 change controlled RC03 evidence state, not the documented
# reach-study selection. Keep the original Freeze-005 report identity visible
# and bind every explicitly compatible manifest to that immutable provenance.
_FREEZE005_DOCUMENTED_REACH_SELECTION: Mapping[str, Any] = {
    "study_input_id": "reach-00ed8c5820df03c7",
    "rank": 1,
    "reach_report_hash": "335275e2a68aa2cda82163fedfe93c17daccdd65d87e07ab03359fafc738fc00",
    "reach_status": "CONTACT_AND_PARK_DIAGNOSTIC_NO_COMPLETE_FINALIST",
    "reach_mission_complete": False,
}
_DOCUMENTED_REACH_SELECTIONS: Mapping[str, Mapping[str, Any]] = {
    "ROCELL-PHASE0-RC03-INT-R1-FREEZE-005": _FREEZE005_DOCUMENTED_REACH_SELECTION,
    "ROCELL-PHASE0-RC03-INT-R1-FREEZE-006": _FREEZE005_DOCUMENTED_REACH_SELECTION,
    "ROCELL-PHASE0-RC03-INT-R1-FREEZE-007": _FREEZE005_DOCUMENTED_REACH_SELECTION,
    "ROCELL-PHASE0-RC03-INT-R1-FREEZE-008": _FREEZE005_DOCUMENTED_REACH_SELECTION,
    "ROCELL-PHASE0-RC03-INT-R1-FREEZE-009": _FREEZE005_DOCUMENTED_REACH_SELECTION,
}
_VIRTUAL_FAULT_PROFILES = (
    "none",
    "arm-connect",
    "arm-reference",
    "arm-stall",
    "camera-unavailable",
    "camera-tag-loss",
    "contact-missed",
    "keyboard-double",
    "phone-wrong-ui",
    "focus-lost",
)
_FIRST_POWER_ON_SCENARIOS = first_power_on_scenario_names()
_FIRST_POWER_ON_STAGES = first_power_on_stage_names()
_PHYSICAL_CONNECTION_REHEARSAL_FAULTS = (
    "none",
    "wrong-camera-identity",
    "wrong-camera-mode",
    "stale-camera-frame",
    "camera-identity-drift",
    "camera-close-failure",
    "wrong-arm-identity",
    "dirty-arm-buffer",
    "malformed-t1051-response",
    "retry-prohibition",
)


def _json_dump(document: Mapping[str, Any], stream: Any | None = None) -> None:
    # Resolve stdout at call time so embedding/tests can redirect it reliably.
    selected_stream = sys.stdout if stream is None else stream
    print(
        json.dumps(
            document,
            indent=JSON_INDENT,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        ),
        file=selected_stream,
    )


def _canonical_report_hash(document: Mapping[str, Any]) -> str:
    """Hash one CLI report wrapper without accepting NaN or unstable key order."""

    return hashlib.sha256(
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _finite_float_argument(value: str) -> float:
    """Parse one finite CLI float before it reaches a simulation boundary."""

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("must be finite")
    return parsed


def _sha256_argument(value: str) -> str:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise argparse.ArgumentTypeError("must be a lowercase SHA-256 digest")
    return value


def _positive_nanoseconds_argument(value: str) -> int:
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be integer nanoseconds") from exc
    if parsed <= 0 or parsed > 2**63 - 1:
        raise argparse.ArgumentTypeError("must be bounded positive nanoseconds")
    return parsed


def _find_workspace(requested: Path | None) -> Path:
    if requested is not None:
        workspace = requested.expanduser().resolve()
        if not workspace.is_dir():
            raise ConfigurationError(
                "WORKSPACE_NOT_FOUND",
                f"Workspace directory does not exist: {workspace}",
            )
        return workspace

    environment_value = os.environ.get("ROCELL_WORKSPACE")
    if environment_value:
        workspace = Path(environment_value).expanduser().resolve()
        if not workspace.is_dir():
            raise ConfigurationError(
                "WORKSPACE_NOT_FOUND",
                f"ROCELL_WORKSPACE does not exist: {workspace}",
            )
        return workspace

    starts = [Path.cwd().resolve(), Path(__file__).resolve().parents[3]]
    checked: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in checked:
                continue
            checked.add(candidate)
            if (candidate / DEFAULT_MANIFEST_RELATIVE).is_file():
                return candidate
    raise ConfigurationError(
        "WORKSPACE_NOT_FOUND",
        "Could not find software/config/system_manifest.json; use --workspace",
    )


def _manifest_path(workspace: Path, requested: Path | None) -> Path:
    if requested is None:
        return workspace / DEFAULT_MANIFEST_RELATIVE
    expanded = requested.expanduser()
    return (expanded if expanded.is_absolute() else workspace / expanded).resolve()


def _contained_workspace_file(
    workspace: Path,
    requested: Path | None,
    default_relative: Path,
    *,
    label: str,
) -> Path:
    """Resolve one existing regular file without allowing workspace escape."""

    selected = default_relative if requested is None else requested.expanduser()
    candidate = selected if selected.is_absolute() else workspace / selected
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ConfigurationError(
            "WORKSPACE_FILE_UNAVAILABLE",
            f"{label} is unavailable: {candidate}",
        ) from exc
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise ConfigurationError(
            "WORKSPACE_FILE_OUTSIDE_ROOT",
            f"{label} must remain beneath the selected workspace",
        ) from exc
    if not resolved.is_file():
        raise ConfigurationError(
            "WORKSPACE_FILE_NOT_REGULAR",
            f"{label} must be a regular file: {resolved}",
        )
    return resolved


def _load_snapshot(args: argparse.Namespace) -> BuildSnapshot:
    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    try:
        return import_build_snapshot(workspace, manifest_path)
    except (BuildImportError, BuildIntegrityError, OSError, ValueError) as exc:
        details: dict[str, Any] = {"manifest": str(manifest_path)}
        source_errors = getattr(exc, "errors", None)
        if source_errors:
            details["source_errors"] = list(source_errors)
        raise ConfigurationError(
            "BUILD_SNAPSHOT_INVALID",
            f"Could not import a verified build snapshot: {exc}",
            details=details,
        ) from exc


def _load_virtual_bootstrap(args: argparse.Namespace) -> Any:
    """Build the complete zero-I/O virtual startup state for a CLI command."""

    workspace = _find_workspace(args.workspace)
    runtime_path = getattr(args, "runtime", None)
    from rocell.application import (
        BootstrapConfigurationError,
        bootstrap_virtual_workcell,
    )

    try:
        bootstrap = bootstrap_virtual_workcell(workspace, runtime_path)
    except (BootstrapConfigurationError, OSError, TypeError, ValueError) as exc:
        details: dict[str, Any] = {
            "runtime": str(
                runtime_path
                if runtime_path is not None
                else workspace / "software/config/runtime.json"
            )
        }
        raise ConfigurationError(
            "VIRTUAL_BOOTSTRAP_INVALID",
            f"Could not initialize the hardware-independent virtual workcell: {exc}",
            details=details,
        ) from exc

    if args.manifest is not None:
        requested_manifest = _manifest_path(workspace, args.manifest).resolve()
        if requested_manifest != bootstrap.runtime.system_manifest_path:
            raise ConfigurationError(
                "VIRTUAL_BOOTSTRAP_MANIFEST_MISMATCH",
                "The requested manifest differs from the strict runtime policy",
                details={
                    "requested_manifest": str(requested_manifest),
                    "runtime_manifest": str(bootstrap.runtime.system_manifest_path),
                },
            )
    return bootstrap


def _assessment_dict(assessment: CapabilityAssessment) -> dict[str, Any]:
    return {
        "allowed": assessment.allowed,
        "reasons": list(assessment.reasons),
        "snapshot_hash": assessment.snapshot_hash,
    }


def _status_document(snapshot: BuildSnapshot) -> dict[str, Any]:
    capabilities = project_capabilities(snapshot)
    return {
        "schema": "rocell.status.v1",
        "runtime_version": __version__,
        "manifest_id": snapshot.manifest_id,
        "design_revision": snapshot.design_revision,
        "active_build_id": snapshot.active_build_id,
        "snapshot_hash": snapshot.snapshot_hash,
        "integrity_verified": snapshot.integrity_verified,
        "physical_release_status": snapshot.physical_release_status,
        "safe_to_power_robot": snapshot.safe_to_power_robot,
        "contact_enabled": snapshot.contact_enabled,
        "camera": {
            "exact_model": snapshot.camera_exact_model,
            "state": snapshot.camera_state,
        },
        "hard_blockers": list(snapshot.hard_blockers),
        "capabilities": {
            capability.value: _assessment_dict(assessment)
            for capability, assessment in sorted(
                capabilities.items(), key=lambda item: item[0].value
            )
        },
    }


def _emit(
    document: Mapping[str, Any], json_output: bool, human_lines: Sequence[str]
) -> None:
    if json_output:
        _json_dump(document)
    else:
        for line in human_lines:
            print(line)


def _command_status(args: argparse.Namespace) -> int:
    snapshot = _load_snapshot(args)
    document = _status_document(snapshot)
    _emit(
        document,
        args.json,
        (
            f"RoCell {__version__} - {snapshot.manifest_id}",
            f"build: {snapshot.active_build_id or 'UNASSIGNED'}; revision: {snapshot.design_revision}",
            f"physical release: {snapshot.physical_release_status}",
            f"safe to power robot: {snapshot.safe_to_power_robot}",
            f"contact enabled: {snapshot.contact_enabled}",
            f"blockers: {len(snapshot.hard_blockers)}",
        ),
    )
    return int(ExitCode.OK)


def _command_integration_readiness(args: argparse.Namespace) -> int:
    """Report the retained AI-to-arm gate without touching hardware."""

    workspace = _find_workspace(args.workspace)
    from rocell.application.model_arm_operational_readiness_v1 import (
        ModelArmOperationalReadinessError,
        build_model_arm_operational_readiness_v1,
    )

    try:
        document = build_model_arm_operational_readiness_v1(workspace)
    except (ModelArmOperationalReadinessError, OSError, ValueError) as exc:
        raise ConfigurationError(
            "INTEGRATION_READINESS_INVALID",
            f"Could not build the retained AI-to-arm readiness report: {exc}",
            details={"workspace": str(workspace)},
        ) from exc

    stages = document["stage_assessments"]
    _emit(
        document,
        args.json,
        (
            f"AI-to-arm integration readiness: {document['status']}",
            f"ready stages: {len(document['ready_stage_ids'])}/{len(stages)}",
            "blocked stages: " + (
                ", ".join(document["blocked_stage_ids"])
                if document["blocked_stage_ids"] else "none"
            ),
            "hardware access: not attempted; physical authority: false",
        ),
    )
    if args.require_ready and not document["single_action_review_ready"]:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_doctor(args: argparse.Namespace) -> int:
    bootstrap = _load_virtual_bootstrap(args)
    snapshot = bootstrap.context.snapshot
    digital = assess_capability(snapshot, Capability.DIGITAL_PLAN)
    simulated = assess_capability(snapshot, Capability.SIMULATED_DRY_RUN)
    feedback = assess_capability(snapshot, Capability.ARM_FEEDBACK)
    declared_gaps = tuple(
        check for check in bootstrap.checks if check.status == "DECLARED_GAP"
    )
    checks = [
        {
            "id": "build_snapshot_integrity",
            "status": "PASS",
            "detail": f"verified snapshot {snapshot.snapshot_hash}",
        },
        {
            "id": "virtual_workcell_bootstrap",
            "status": "PASS" if bootstrap.simulation_ready else "FAIL",
            "detail": (
                f"verified bootstrap {bootstrap.bootstrap_hash}; "
                f"declared gaps={len(declared_gaps)}"
            ),
        },
        {
            "id": "digital_plan",
            "status": "PASS" if digital.allowed else "FAIL",
            "reasons": list(digital.reasons),
        },
        {
            "id": "semantic_simulated_dry_run",
            "status": "PASS" if simulated.allowed else "FAIL",
            "reasons": list(simulated.reasons),
        },
        {
            "id": "live_arm_feedback",
            "status": (
                "NOT_RUN_BLOCKED" if not feedback.allowed else "NOT_RUN_AVAILABLE"
            ),
            "reasons": list(feedback.reasons),
            "detail": "No COM port was enumerated or opened.",
        },
        {
            "id": "optional_hardware_imports",
            "status": "NOT_IMPORTED",
            "detail": "Simulation mode does not import pyserial or OpenCV.",
        },
    ]
    simulation_pass = (
        bootstrap.simulation_ready and digital.allowed and simulated.allowed
    )
    document = {
        "schema": "rocell.doctor.v1",
        "mode": args.mode,
        "status": "PASS_WITH_HARDWARE_HOLDS" if simulation_pass else "FAIL",
        "snapshot_hash": snapshot.snapshot_hash,
        "virtual_bootstrap": {
            "status": bootstrap.status,
            "bootstrap_hash": bootstrap.bootstrap_hash,
            "simulation_ready": bootstrap.simulation_ready,
            "declared_gaps": [
                {"id": check.check_id, "detail": check.detail}
                for check in declared_gaps
            ],
            "collision_readiness_status": bootstrap.collision_readiness.status,
            "missing_calibration_count": len(
                bootstrap.calibration_inventory.missing_requirement_ids
            ),
            "authority": {
                "simulation_only": True,
                "hardware_accessed": False,
                "hardware_commands_generated": 0,
            },
        },
        "checks": checks,
    }
    _emit(
        document,
        args.json,
        (
            f"doctor ({args.mode}): {document['status']}",
            f"snapshot: {snapshot.snapshot_hash}",
            f"bootstrap: {bootstrap.bootstrap_hash}; declared gaps: {len(declared_gaps)}",
            "hardware access: not attempted",
        ),
    )
    return int(ExitCode.OK if simulation_pass else ExitCode.CONFIGURATION_ERROR)


def _command_camera_profile(args: argparse.Namespace) -> int:
    """Inspect the strict purchase-time B0477 profile without opening a camera."""

    workspace = _find_workspace(args.workspace)
    profile_path = _contained_workspace_file(
        workspace,
        args.profile_file,
        DEFAULT_B0477_PROFILE_RELATIVE,
        label="purchased camera profile",
    )
    from rocell.vision import CameraProfileError, load_camera_profile

    try:
        profile = load_camera_profile(profile_path)
    except (CameraProfileError, OSError, ValueError) as exc:
        raise ConfigurationError(
            "CAMERA_PROFILE_INVALID",
            f"Could not validate the purchased camera profile: {exc}",
            details={"profile": str(profile_path)},
        ) from exc
    native = profile.published_mode("USB_3_2_GEN_1", 5472, 3648)
    if native is None:
        raise ConfigurationError(
            "CAMERA_PROFILE_NATIVE_MODE_MISSING",
            "The B0477 purchase profile does not contain its full USB3 mode",
        )
    proxy = profile.simulation_proxy
    recovered_h, recovered_v = proxy.recovered_field_of_view_deg()
    document = {
        "schema": "rocell.camera_profile_cli.v1",
        "profile": {
            "id": profile.profile_id,
            "record_state": profile.record_state,
            "source_file_sha256": profile.source_file_sha256,
            "canonical_sha256": profile.canonical_sha256,
            "reported_product_title": profile.reported_product_title,
            "published_identity": {
                "manufacturer": profile.manufacturer,
                "model": profile.model,
                "sensor": profile.sensor,
                "lens_mount": profile.lens_mount,
                "focal_length_mm": profile.focal_length_mm,
            },
            "intended_physical_mode": {
                "evidence_state": native.evidence_state,
                "host_bus": native.host_bus,
                "width_px": native.width_px,
                "height_px": native.height_px,
                "maximum_fps": native.maximum_fps,
                "pixel_format": native.pixel_format,
                "verified_on_received_hardware": False,
            },
            "simulation_proxy": {
                "state": proxy.state,
                "calibration_state": proxy.calibration_state,
                "width_px": proxy.width_px,
                "height_px": proxy.height_px,
                "pixel_count": proxy.pixel_count,
                "scale_numerator": proxy.scale_numerator,
                "scale_denominator": proxy.scale_denominator,
                "nominal_intrinsics_px": {
                    "fx": proxy.fx_px,
                    "fy": proxy.fy_px,
                    "cx": proxy.cx_px,
                    "cy": proxy.cy_px,
                },
                "published_fov_recovered_deg": {
                    "horizontal": recovered_h,
                    "vertical": recovered_v,
                },
                "within_current_resource_limits": proxy.within_current_raster_limits,
                "physical_calibration_evidence": False,
            },
            "evidence_state": {
                "physical_observation": profile.physical_observation_state,
                "usb_observation": profile.usb_observation_state,
                "commissioning": profile.commissioning_state,
            },
            "open_blockers": list(profile.open_blockers),
        },
        "authority": {
            **dict(profile.authority),
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
        },
    }
    _emit(
        document,
        args.json,
        (
            f"camera profile: {profile.manufacturer} {profile.model} / {profile.sensor}",
            f"state: {profile.record_state}",
            "intended physical mode: 5472x3648 YUY2 at up to 9 fps over USB3 (published, not received-unit verified)",
            f"synthetic proxy: {proxy.width_px}x{proxy.height_px}; physical calibration evidence: false",
            "hardware access: not attempted; robot motion/contact authority: false",
        ),
    )
    return int(ExitCode.OK)


def _command_host_doctor(args: argparse.Namespace) -> int:
    """Inspect the controlled arrival environment without touching a device."""

    from importlib import metadata
    import subprocess

    from rocell.application.physical_host_readiness import (
        PhysicalHostReadinessError,
        assess_physical_host_readiness,
    )

    snapshot = _load_snapshot(args)
    workspace = _find_workspace(args.workspace)
    try:
        report = assess_physical_host_readiness(workspace, snapshot)
    except (PhysicalHostReadinessError, OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "PHYSICAL_HOST_READINESS_INVALID",
            f"Could not assess the physical-onboarding host: {exc}",
        ) from exc

    dependency_by_name = {item.import_name: item for item in report.dependencies}
    if args.profile == "runtime":
        profile_ready = report.base_software_ready
    elif args.profile == "hardware":
        profile_ready = (
            report.camera_diagnostics_dependencies_ready
            and report.arm_diagnostics_dependencies_ready
        )
    else:
        profile_ready = report.development_dependencies_ready

    # Multiple OpenCV wheels in one environment can silently change which cv2
    # binary is imported. Metadata inspection is safe and imports no backend.
    conflicting_opencv_distributions: list[str] = []
    for distribution_name in (
        "opencv-python",
        "opencv-python-headless",
        "opencv-contrib-python-headless",
    ):
        try:
            metadata.version(distribution_name)
        except metadata.PackageNotFoundError:
            continue
        conflicting_opencv_distributions.append(distribution_name)
    if args.profile in {"hardware", "development"} and conflicting_opencv_distributions:
        profile_ready = False

    pip_check: dict[str, object] = {
        "attempted": False,
        "passed": False,
        "exit_code": None,
        "output": "NOT_RUN_OUTSIDE_CONTROLLED_WORKSPACE_VENV",
    }
    if report.running_from_workspace_venv:
        pip_check["attempted"] = True
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-m", "pip", "check"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            pip_check["output"] = f"PIP_CHECK_FAILED_TO_RUN:{type(exc).__name__}"
            profile_ready = False
        else:
            output = (completed.stdout + completed.stderr).strip()
            pip_check.update(
                {
                    "passed": completed.returncode == 0,
                    "exit_code": completed.returncode,
                    "output": output[:4096] or "NO_OUTPUT",
                }
            )
            if completed.returncode != 0:
                profile_ready = False

    expected_physical_holds = tuple(
        blocker
        for blocker in report.blockers
        if blocker == "SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED"
    )
    environment_blockers = tuple(
        blocker for blocker in report.blockers if blocker not in expected_physical_holds
    )
    status = (
        "READY_WITH_PHYSICAL_HOLDS"
        if profile_ready and expected_physical_holds
        else "READY" if profile_ready else "BLOCKED"
    )
    document = {
        "schema": "rocell.host_doctor_cli.v1",
        "profile": args.profile,
        "profile_ready": profile_ready,
        "status": status,
        "report": report.to_dict(),
        "dependency_summary": {
            name: dependency_by_name[name].to_dict()
            for name in sorted(dependency_by_name)
        },
        "conflicting_opencv_distributions": conflicting_opencv_distributions,
        "pip_check": pip_check,
        "environment_blockers": list(environment_blockers),
        "physical_holds": list(expected_physical_holds),
        "authority": {
            "hardware_accessed": False,
            "camera_opens": 0,
            "arm_port_opens": 0,
            "robot_commands_sent": 0,
            "motion_authorized": False,
            "contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    _emit(
        document,
        args.json,
        (
            f"physical-onboarding host: {status}",
            f"profile: {args.profile}; ready: {profile_ready}",
            f"environment blockers: {len(environment_blockers)}",
            f"physical holds: {len(expected_physical_holds)}",
        ),
    )
    if args.require_pass and not profile_ready:
        denial_reasons = [
            *environment_blockers,
            *(
                f"CONFLICTING_OPENCV_DISTRIBUTION:{name}"
                for name in conflicting_opencv_distributions
            ),
        ]
        if pip_check["attempted"] and not pip_check["passed"]:
            denial_reasons.append("PIP_CHECK_FAILED")
        if not denial_reasons:
            denial_reasons.append("SELECTED_HOST_PROFILE_NOT_READY")
        raise CapabilityDeniedError(
            f"physical_host_{args.profile}",
            denial_reasons,
        )
    return int(ExitCode.OK)


def _command_rehearse_physical_connections(args: argparse.Namespace) -> int:
    """Exercise the exact connection lifecycle with incapable fake providers."""

    from rocell.application.physical_connection_rehearsal import (
        PhysicalConnectionRehearsalError,
        RehearsalFault,
        run_physical_connection_rehearsal,
    )

    try:
        selected_fault = RehearsalFault(args.fault.upper().replace("-", "_"))
        report = run_physical_connection_rehearsal(
            run_id=args.run_id,
            fault=selected_fault,
        )
    except (PhysicalConnectionRehearsalError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "PHYSICAL_CONNECTION_REHEARSAL_FAILED",
            f"The zero-hardware connection rehearsal failed: {exc}",
        ) from exc

    expected_outcome = (
        report.rehearsal_passed
        if selected_fault is RehearsalFault.NONE
        else report.expected_fault_blocked
    )
    document = {
        **report.to_dict(),
        "report_sha256": report.report_sha256,
        "expected_outcome_observed": expected_outcome,
    }
    _emit(
        document,
        args.json,
        (
            f"physical connection rehearsal: {report.outcome.value}",
            f"scenario: {args.fault}; expected outcome: {expected_outcome}",
            f"synthetic steps: {len(report.steps)}; physical effects: 0",
            "T=104/motion/contact/torque commands: 0",
        ),
    )
    if args.require_expected and not expected_outcome:
        raise CapabilityDeniedError(
            "physical_connection_rehearsal_expected_outcome",
            ["CONNECTION_REHEARSAL_EXPECTATION_NOT_MET"],
        )
    return int(ExitCode.OK)


def _open_physical_controller(args: argparse.Namespace) -> Any:
    """Open one policy-rooted onboarding session without importing a backend."""

    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingController,
        PhysicalOnboardingControllerError,
    )
    from rocell.application.physical_onboarding import PhysicalOnboardingError
    from rocell.application.physical_onboarding_policy import (
        PhysicalOnboardingPolicyError,
    )

    workspace = _find_workspace(args.workspace)
    snapshot = _load_snapshot(args)
    try:
        return PhysicalOnboardingController.open(
            workspace,
            snapshot,
            session_id=args.session_id,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalOnboardingControllerError,
        PhysicalOnboardingError,
        PhysicalOnboardingPolicyError,
    ) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_SESSION_INVALID",
            f"Could not open and verify the physical onboarding session: {exc}",
        ) from exc


def _physical_cli_document(
    operation: str,
    *,
    status: Mapping[str, object] | None = None,
    result: Mapping[str, object] | None = None,
    operation_effect: Mapping[str, object] | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema": "rocell.physical_onboard_cli.v1",
        "operation": operation,
        "operation_effect": dict(
            operation_effect
            or {
                "os_device_metadata_reads": 0,
                "device_opens": 0,
                "camera_frames_captured": 0,
                "serial_transactions": 0,
                "robot_power_operations": 0,
                "robot_commands_sent": 0,
            }
        ),
        "authority": {
            "diagnostic_only": True,
            "robot_power_authorized": False,
            "motion_authorized": False,
            "contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    if status is not None:
        document["status"] = dict(status)
    if result is not None:
        document["result"] = dict(result)
    return document


def _command_physical_onboard_new(args: argparse.Namespace) -> int:
    from datetime import datetime, timezone
    import secrets

    from rocell.application.physical_onboarding import PhysicalOnboardingError
    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingController,
        PhysicalOnboardingControllerError,
    )
    from rocell.application.physical_onboarding_policy import (
        PhysicalOnboardingPolicyError,
    )

    workspace = _find_workspace(args.workspace)
    snapshot = _load_snapshot(args)
    session_id = args.session_id
    if session_id is None:
        utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        session_id = f"arrival-{utc}-{secrets.token_hex(4)}"
    try:
        controller = PhysicalOnboardingController.create(
            workspace,
            snapshot,
            session_id=session_id,
            cell_id=args.cell_id,
        )
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalOnboardingControllerError,
        PhysicalOnboardingError,
        PhysicalOnboardingPolicyError,
    ) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_CREATE_FAILED",
            f"Could not create the physical onboarding session: {exc}",
            details={"session_id": session_id, "session_published": False},
        ) from exc

    # Creation publishes an immutable journal before optional safe preparation.
    # Keep that boundary visible so a later verification failure cannot strand
    # an autogenerated session ID or encourage a duplicate-create retry.
    try:
        executed: list[dict[str, object]] = []
        if args.prepare_safe:
            for _ in range(2):
                preview = controller.preview_next()
                if (
                    not preview.executable
                    or preview.operation != "VERIFY_ZERO_IO_STAGE"
                ):
                    break
                execution = controller.execute_next(
                    expected_challenge_sha256=(preview.challenge.challenge_sha256)
                )
                executed.append(execution.to_dict())
        status = controller.status()
        preview = controller.preview_next()
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalOnboardingControllerError,
        PhysicalOnboardingError,
        PhysicalOnboardingPolicyError,
    ) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_PREPARATION_FAILED",
            (
                f"Physical onboarding session {session_id!r} was published, "
                f"but safe preparation could not finish: {exc}. Resume with "
                f"'.\\rocell.ps1 physical-onboard status --session-id {session_id} --json'."
            ),
            details={
                "session_id": session_id,
                "session_published": True,
                "session_directory": str(controller.session_directory),
                "recovery_operation": "status",
            },
        ) from exc
    document = _physical_cli_document(
        "new",
        status=status.to_dict(),
        result={
            "session_id": session_id,
            "safe_zero_io_executions": executed,
            "next": preview.to_dict(),
        },
    )
    _emit(
        document,
        args.json,
        (
            f"physical onboarding session: {session_id}",
            f"source binding current: {status.source_binding_current}",
            f"safe checks executed: {len(executed)}",
            f"next: {preview.operation}",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_status(args: argparse.Namespace) -> int:
    controller = _open_physical_controller(args)
    try:
        status = controller.status()
        preview = controller.preview_next()
    except (OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_STATUS_INVALID",
            f"Could not verify onboarding status: {exc}",
        ) from exc
    document = _physical_cli_document(
        "status",
        status=status.to_dict(),
        result={"next": preview.to_dict()},
    )
    _emit(
        document,
        args.json,
        (
            f"session: {status.snapshot.header.session_id}",
            f"source binding current: {status.source_binding_current}",
            f"diagnostic complete: {status.snapshot.diagnostic_complete}",
            f"next: {preview.operation}",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_next(args: argparse.Namespace) -> int:
    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingControllerError,
    )

    controller = _open_physical_controller(args)
    try:
        preview = controller.preview_next()
        status_before = controller.status()
        if not args.execute:
            document = _physical_cli_document(
                "next",
                status=status_before.to_dict(),
                result={"preview": preview.to_dict(), "executed": False},
            )
            _emit(
                document,
                args.json,
                (
                    f"next: {preview.operation}",
                    f"stage: {preview.stage.value if preview.stage else 'NONE'}",
                    f"executable by non-device controller: {preview.executable}",
                    f"challenge: {preview.challenge.challenge_sha256}",
                ),
            )
            return int(ExitCode.OK)

        missing = tuple(
            name
            for name, value in (
                ("--expected-stage", args.expected_stage),
                ("--expected-head-sha256", args.expected_head_sha256),
                ("--expected-challenge-sha256", args.expected_challenge_sha256),
            )
            if value is None
        )
        if missing:
            raise UsageError(
                "PHYSICAL_ONBOARDING_PRECONDITION_REQUIRED",
                f"--execute requires {', '.join(missing)}",
            )
        actual_stage = None if preview.stage is None else preview.stage.value
        if args.expected_stage != actual_stage:
            raise ConfigurationError(
                "PHYSICAL_ONBOARDING_STAGE_STALE",
                "The expected stage differs from the verified next stage",
                details={"expected": args.expected_stage, "actual": actual_stage},
            )
        if args.expected_head_sha256 != status_before.journal_head_sha256:
            raise ConfigurationError(
                "PHYSICAL_ONBOARDING_HEAD_STALE",
                "The expected journal head differs from the verified head",
                details={
                    "expected": args.expected_head_sha256,
                    "actual": status_before.journal_head_sha256,
                },
            )
        execution = controller.execute_next(
            expected_challenge_sha256=args.expected_challenge_sha256
        )
    except (UsageError, ConfigurationError):
        raise
    except (OSError, TypeError, ValueError, PhysicalOnboardingControllerError) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_NEXT_FAILED",
            f"Could not execute the bounded next onboarding action: {exc}",
        ) from exc
    document = _physical_cli_document(
        "next",
        status=execution.status.to_dict(),
        result={"executed": True, "execution": execution.to_dict()},
    )
    _emit(
        document,
        args.json,
        (
            f"executed: {execution.operation}",
            f"session: {execution.status.snapshot.header.session_id}",
            f"next: {execution.status.snapshot.next_action.code}",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_record(args: argparse.Namespace) -> int:
    from rocell.application.physical_onboarding import PhysicalOnboardingStage
    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingControllerError,
    )

    controller = _open_physical_controller(args)
    try:
        evidence = controller.record_evidence_file(
            stage=PhysicalOnboardingStage(args.stage),
            source_path=args.file,
            expected_payload_sha256=args.file_sha256,
            captured_at_ns=args.captured_at_ns,
            label=args.label,
            media_type=args.media_type,
            expected_challenge_sha256=args.expected_challenge_sha256,
        )
        status = controller.status()
    except (OSError, TypeError, ValueError, PhysicalOnboardingControllerError) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_EVIDENCE_REJECTED",
            f"Could not retain onboarding evidence: {exc}",
        ) from exc
    document = _physical_cli_document(
        "record",
        status=status.to_dict(),
        result={"evidence": evidence.to_dict(), "stage_passed": False},
    )
    _emit(
        document,
        args.json,
        (
            f"retained evidence: {evidence.evidence_id}",
            f"stage: {evidence.stage.value}; stage passed: false",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_verify(args: argparse.Namespace) -> int:
    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingControllerError,
    )

    controller = _open_physical_controller(args)
    try:
        status = controller.verify()
    except (OSError, TypeError, ValueError, PhysicalOnboardingControllerError) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_VERIFY_FAILED",
            f"Onboarding integrity verification failed: {exc}",
        ) from exc
    document = _physical_cli_document(
        "verify",
        status=status.to_dict(),
        result={
            "integrity_verified": True,
            "source_binding_current": True,
            "diagnostic_complete": status.snapshot.diagnostic_complete,
        },
    )
    _emit(
        document,
        args.json,
        (
            "onboarding integrity: VERIFIED",
            f"diagnostic complete: {status.snapshot.diagnostic_complete}",
        ),
    )
    if args.require_complete and not status.snapshot.diagnostic_complete:
        raise CapabilityDeniedError(
            "physical_onboarding_diagnostic_complete",
            ["PHYSICAL_ONBOARDING_INCOMPLETE"],
        )
    return int(ExitCode.OK)


def _command_physical_onboard_verify_foundation(args: argparse.Namespace) -> int:
    """Validate the additive v2 design graph without touching a device."""

    from rocell.application.physical_onboarding_foundation import (
        PhysicalOnboardingFoundationError,
        load_physical_onboarding_foundation,
    )

    workspace = _find_workspace(args.workspace)
    try:
        foundation = load_physical_onboarding_foundation(workspace)
    except (OSError, TypeError, ValueError, PhysicalOnboardingFoundationError) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_FOUNDATION_INVALID",
            f"Physical-onboarding foundation validation failed: {exc}",
        ) from exc
    result = {
        "foundation_id": foundation.foundation_id,
        "foundation_sha256": foundation.source_sha256,
        "validated_contract_count": len(foundation.contracts),
        "runtime_activation": foundation.runtime_activation,
        "zero_physical_authority": foundation.zero_physical_authority,
        "open_implementation_gates": list(foundation.open_implementation_gates),
        "result": "VALID_ZERO_AUTHORITY_FOUNDATION",
    }
    document = _physical_cli_document(
        "verify-foundation",
        result=result,
    )
    _emit(
        document,
        args.json,
        (
            f"foundation: {foundation.foundation_id}",
            f"contracts verified: {len(foundation.contracts)}",
            f"open implementation gates: {len(foundation.open_implementation_gates)}",
            "physical authority: false",
        ),
    )
    return int(ExitCode.OK)


def _open_physical_m1_runtime(
    args: argparse.Namespace,
    *,
    initialize: bool,
) -> Any:
    """Bind and open the qualified M1 store without importing a device backend.

    Initialization is deliberately separate from session creation. This makes
    the on-volume durability qualification and its persistent anchor an
    operator-visible step, while ordinary V2 commands fail closed when that
    step has not happened.
    """

    from rocell.application.physical_onboarding_durability import (
        PhysicalOnboardingDurabilityError,
    )
    from rocell.application.physical_onboarding_leases import (
        PhysicalOnboardingLeaseError,
    )
    from rocell.application.physical_onboarding_m1 import (
        PhysicalOnboardingM1Error,
        PhysicalOnboardingM1Runtime,
    )
    from rocell.application.physical_onboarding_policy import (
        PhysicalOnboardingPolicyError,
        bind_physical_onboarding_sources,
    )
    from rocell.application.physical_onboarding_storage import (
        PhysicalOnboardingStorageError,
    )

    workspace = _find_workspace(args.workspace)
    snapshot = _load_snapshot(args)
    try:
        policy, binding = bind_physical_onboarding_sources(workspace, snapshot)
        deployment_root = policy.session_root(workspace)
        if initialize:
            # The M1 runtime itself validates every existing path component and
            # rejects symlinks/reparse points. mkdir only establishes the
            # policy-selected container required by its qualification probe.
            deployment_root.mkdir(parents=True, exist_ok=True)
            runtime = PhysicalOnboardingM1Runtime.initialize(
                deployment_root,
                source_binding_sha256=binding.source_binding_sha256,
                cell_id=args.cell_id,
            )
        else:
            runtime = PhysicalOnboardingM1Runtime.open(
                deployment_root,
                source_binding_sha256=binding.source_binding_sha256,
                cell_id=args.cell_id,
            )
        return runtime
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalOnboardingDurabilityError,
        PhysicalOnboardingLeaseError,
        PhysicalOnboardingM1Error,
        PhysicalOnboardingPolicyError,
        PhysicalOnboardingStorageError,
    ) as exc:
        operation = "initialize" if initialize else "open"
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_M1_STORAGE_INVALID",
            f"Could not {operation} the qualified zero-hardware M1 store: {exc}",
            details={
                "cell_id": args.cell_id,
                "hardware_access_attempted": False,
            },
        ) from exc


def _command_physical_onboard_init_v2_storage(args: argparse.Namespace) -> int:
    """Qualify and initialize crash-aware M1 storage with zero device I/O."""

    runtime = _open_physical_m1_runtime(args, initialize=True)
    verification = runtime.verify()
    status = verification.to_dict()
    document = _physical_cli_document(
        "init-v2-storage",
        status=status,
        result={
            "qualified_storage_ready": True,
            "cell_id": runtime.cell.cell_id,
            "deployment_root": str(runtime.deployment_root),
            "source_binding_sha256": runtime.source_binding_sha256,
            "durability_qualification_sha256": (
                runtime.qualification_anchor.report_sha256
            ),
            "challenge_sha256": verification.challenge_sha256,
            "session_created": False,
        },
    )
    _emit(
        document,
        args.json,
        (
            f"qualified M1 storage: READY for cell {runtime.cell.cell_id}",
            f"deployment root: {runtime.deployment_root}",
            "session created: false; hardware accessed: false",
            "robot power, motion, descent, and contact authority: false",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_new_v2(args: argparse.Namespace) -> int:
    """Create one qualified V2 session without advancing a stage."""

    from datetime import datetime, timezone
    import secrets

    from rocell.application.physical_onboarding_attempts import (
        PhysicalOnboardingAttemptError,
    )
    from rocell.application.physical_onboarding_leases import (
        PhysicalOnboardingLeaseError,
    )
    from rocell.application.physical_onboarding_m1 import (
        PhysicalOnboardingM1Error,
    )
    from rocell.application.physical_onboarding_quarantine import (
        PhysicalOnboardingQuarantineError,
    )
    from rocell.application.physical_onboarding_storage import (
        PhysicalOnboardingStorageError,
    )
    from rocell.application.physical_onboarding_v2 import (
        PhysicalOnboardingV2Error,
    )

    runtime = _open_physical_m1_runtime(args, initialize=False)
    session_id = args.session_id
    if session_id is None:
        utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        session_id = f"arrival-v2-{utc}-{secrets.token_hex(4)}"
    try:
        verification = runtime.create_session(session_id)
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalOnboardingAttemptError,
        PhysicalOnboardingLeaseError,
        PhysicalOnboardingM1Error,
        PhysicalOnboardingQuarantineError,
        PhysicalOnboardingStorageError,
        PhysicalOnboardingV2Error,
    ) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_M1_SESSION_CREATE_FAILED",
            f"Could not create qualified V2 onboarding session {session_id!r}: {exc}",
            details={
                "cell_id": args.cell_id,
                "session_id": session_id,
                # A qualified directory publication is atomic, but a failure
                # after that boundary must not be reported as "not published".
                # Verification is the only safe retry decision.
                "session_publication_outcome": "VERIFY_REQUIRED",
                "recovery_operation": "verify-v2-runtime",
                "hardware_access_attempted": False,
            },
        ) from exc
    status = verification.to_dict()
    document = _physical_cli_document(
        "new-v2",
        status=status,
        result={
            "session_id": session_id,
            "session_published": True,
            "stage_advanced": False,
            "challenge_sha256": verification.challenge_sha256,
            "effects_allowed_by_m1_storage": verification.effects_allowed,
        },
    )
    _emit(
        document,
        args.json,
        (
            f"qualified V2 session: {session_id}",
            f"cell: {runtime.cell.cell_id}; stage advanced: false",
            "hardware accessed: false; physical authority: false",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_verify_v2_runtime(args: argparse.Namespace) -> int:
    """Verify M1 global state and, optionally, one V2 session."""

    from rocell.application.physical_onboarding_attempts import (
        PhysicalOnboardingAttemptError,
    )
    from rocell.application.physical_onboarding_m1 import PhysicalOnboardingM1Error
    from rocell.application.physical_onboarding_quarantine import (
        PhysicalOnboardingQuarantineError,
    )
    from rocell.application.physical_onboarding_storage import (
        PhysicalOnboardingStorageError,
    )
    from rocell.application.physical_onboarding_v2 import (
        PhysicalOnboardingV2Error,
    )

    runtime = _open_physical_m1_runtime(args, initialize=False)
    try:
        verification = runtime.verify(args.session_id)
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalOnboardingAttemptError,
        PhysicalOnboardingM1Error,
        PhysicalOnboardingQuarantineError,
        PhysicalOnboardingStorageError,
        PhysicalOnboardingV2Error,
    ) as exc:
        raise ConfigurationError(
            "PHYSICAL_ONBOARDING_M1_VERIFY_FAILED",
            f"Could not verify the zero-hardware M1 runtime: {exc}",
            details={
                "cell_id": args.cell_id,
                "session_id": args.session_id,
                "hardware_access_attempted": False,
            },
        ) from exc
    status = verification.to_dict()
    document = _physical_cli_document(
        "verify-v2-runtime",
        status=status,
        result={
            "integrity_verified": True,
            "cell_id": runtime.cell.cell_id,
            "session_id": verification.session_id,
            "challenge_sha256": verification.challenge_sha256,
            "effects_allowed_by_m1_storage": verification.effects_allowed,
            "physical_authority_granted": False,
        },
    )
    _emit(
        document,
        args.json,
        (
            f"M1 runtime integrity: VERIFIED for cell {runtime.cell.cell_id}",
            f"session: {verification.session_id or 'NONE'}",
            f"status: {status['status']}",
            "hardware accessed: false; physical authority: false",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_intake(args: argparse.Namespace) -> int:
    from rocell.application.hardware_intake import (
        HardwareIntakeError,
        assess_hardware_intake,
    )
    from rocell.application.physical_onboarding import PhysicalOnboardingStage
    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingControllerError,
    )

    workspace = _find_workspace(args.workspace)
    try:
        assessment = assess_hardware_intake(workspace, args.file)
        if args.require_review_ready and not assessment.ready_for_human_review:
            raise CapabilityDeniedError(
                "physical_hardware_intake_review_ready",
                ["HARDWARE_INTAKE_INCOMPLETE_OR_ON_HOLD"],
            )
        evidence = None
        status_document = None
        if args.session_id is not None:
            if args.expected_challenge_sha256 is None:
                raise UsageError(
                    "PHYSICAL_ONBOARDING_PRECONDITION_REQUIRED",
                    "Recording intake evidence requires --expected-challenge-sha256",
                )
            controller = _open_physical_controller(args)
            evidence = controller.record_generated_evidence_document(
                stage=PhysicalOnboardingStage.CAMERA_RECEIPT,
                document=assessment.to_dict(),
                label="physical-hardware-intake-assessment",
                expected_challenge_sha256=args.expected_challenge_sha256,
            )
            status_document = controller.status().to_dict()
    except (UsageError, CapabilityDeniedError):
        raise
    except (
        OSError,
        TypeError,
        ValueError,
        HardwareIntakeError,
        PhysicalOnboardingControllerError,
    ) as exc:
        raise ConfigurationError(
            "PHYSICAL_HARDWARE_INTAKE_INVALID",
            f"Hardware intake validation failed: {exc}",
        ) from exc
    document = _physical_cli_document(
        "intake",
        status=status_document,
        result={
            "assessment": assessment.to_dict(),
            "retained_evidence": None if evidence is None else evidence.to_dict(),
            "stage_passed": False,
        },
    )
    _emit(
        document,
        args.json,
        (
            f"intake records: {assessment.record_count}",
            f"review ready: {assessment.ready_for_human_review}",
            f"holds: {len(assessment.hold_record_ids)}",
            f"retained: {evidence is not None}; stage passed: false",
        ),
    )
    return int(ExitCode.OK)


def _command_physical_onboard_inventory(args: argparse.Namespace) -> int:
    """Read OS device metadata only; never open, select, or qualify a device."""

    import platform
    import time

    from rocell.application.physical_host_readiness import (
        PhysicalHostReadinessError,
        assess_physical_host_readiness,
    )
    from rocell.application.physical_onboarding import (
        PhysicalOnboardingStage,
        StageState,
    )
    from rocell.application.physical_onboarding_controller import (
        PhysicalOnboardingControllerError,
    )

    workspace = _find_workspace(args.workspace)
    snapshot = _load_snapshot(args)
    try:
        host = assess_physical_host_readiness(workspace, snapshot)
    except (OSError, TypeError, ValueError, PhysicalHostReadinessError) as exc:
        raise ConfigurationError(
            "PHYSICAL_HOST_READINESS_INVALID",
            f"Could not validate the inventory environment: {exc}",
        ) from exc
    if not (
        host.device_access_environment_ready and host.arm_diagnostics_dependencies_ready
    ):
        raise CapabilityDeniedError(
            "read_only_physical_device_inventory",
            [
                blocker
                for blocker in host.blockers
                if blocker != "SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED"
            ]
            or ["CONTROLLED_HARDWARE_ENVIRONMENT_NOT_READY"],
        )

    # Validate the selected session and every mutation precondition before the
    # first OS device-metadata read. An invalid or stale invocation must not
    # enumerate even though enumeration itself never opens a device.
    controller = _open_physical_controller(args)
    try:
        controller.verify()
        record_stage = (
            None
            if args.record_stage is None
            else PhysicalOnboardingStage(args.record_stage)
        )
        if record_stage is not None:
            if record_stage not in {
                PhysicalOnboardingStage.CAMERA_IDENTITY,
                PhysicalOnboardingStage.ARM_IDENTITY,
            }:
                raise UsageError(
                    "PHYSICAL_INVENTORY_STAGE_INVALID",
                    "Inventory may be retained only for camera_identity or arm_identity",
                )
            if args.expected_challenge_sha256 is None:
                raise UsageError(
                    "PHYSICAL_ONBOARDING_PRECONDITION_REQUIRED",
                    "--record-stage requires --expected-challenge-sha256",
                )
            preview = controller.preview_next()
            if (
                preview.stage is not record_stage
                or preview.stage_state is not StageState.WAITING_OPERATOR
            ):
                raise ConfigurationError(
                    "PHYSICAL_INVENTORY_STAGE_NOT_ACTIVE",
                    "Inventory can be retained only for the active WAITING_OPERATOR identity stage",
                )
            if preview.challenge.challenge_sha256 != args.expected_challenge_sha256:
                raise ConfigurationError(
                    "PHYSICAL_ONBOARDING_CHALLENGE_STALE",
                    "The inventory evidence challenge is stale or belongs to another state",
                )
    except (UsageError, ConfigurationError):
        raise
    except (OSError, TypeError, ValueError, PhysicalOnboardingControllerError) as exc:
        raise ConfigurationError(
            "PHYSICAL_DEVICE_INVENTORY_PREFLIGHT_FAILED",
            f"Could not verify inventory preconditions without device access: {exc}",
        ) from exc

    # Import the inventory boundary only after the controlled environment gate.
    from rocell.application.physical_device_inventory import (
        PhysicalDeviceInventoryError,
        SubprocessArgvCommandRunner,
        compose_physical_device_inventory_report,
        inventory_linux_video_cameras_from_sysfs,
        inventory_serial_ports_with_pyserial,
        inventory_windows_pnp_cameras,
    )

    selected_platform = platform.system()
    try:
        if selected_platform == "Windows":
            camera_inventory = inventory_windows_pnp_cameras(
                SubprocessArgvCommandRunner()
            )
        elif selected_platform == "Linux":
            camera_inventory = inventory_linux_video_cameras_from_sysfs()
        else:
            raise PhysicalDeviceInventoryError(
                f"unsupported inventory platform {selected_platform!r}"
            )
        serial_inventory = inventory_serial_ports_with_pyserial()
        report = compose_physical_device_inventory_report(
            platform_system=selected_platform,
            captured_at_unix_ns=time.time_ns(),
            camera_inventory=camera_inventory,
            serial_inventory=serial_inventory,
        )
        if args.require_candidates and (
            not camera_inventory.candidates or not serial_inventory.candidates
        ):
            raise CapabilityDeniedError(
                "physical_device_candidates_observed",
                ["CAMERA_OR_SERIAL_CANDIDATE_NOT_OBSERVED"],
            )
        evidence = None
        if record_stage is not None:
            evidence = controller.record_generated_evidence_document(
                stage=record_stage,
                document=report.to_dict(),
                label="read-only-physical-device-inventory",
                expected_challenge_sha256=args.expected_challenge_sha256,
            )
        status = controller.status()
    except (UsageError, CapabilityDeniedError):
        raise
    except (
        OSError,
        TypeError,
        ValueError,
        PhysicalDeviceInventoryError,
        PhysicalOnboardingControllerError,
    ) as exc:
        raise HardwareError(
            "PHYSICAL_DEVICE_INVENTORY_FAILED",
            f"Read-only device inventory failed: {exc}",
        ) from exc
    document = _physical_cli_document(
        "inventory",
        status=status.to_dict(),
        result={
            "inventory": report.to_dict(),
            "retained_evidence": None if evidence is None else evidence.to_dict(),
            "qualified": False,
        },
        operation_effect={
            "os_device_metadata_reads": 2,
            "device_opens": 0,
            "camera_frames_captured": 0,
            "serial_transactions": 0,
            "robot_power_operations": 0,
            "robot_commands_sent": 0,
        },
    )
    _emit(
        document,
        args.json,
        (
            f"camera candidates: {len(camera_inventory.candidates)}",
            f"serial candidates: {len(serial_inventory.candidates)}",
            "devices opened: 0; devices qualified: false",
        ),
    )
    return int(ExitCode.OK)


def _command_rehearse_camera_commissioning(args: argparse.Namespace) -> int:
    """Exercise B0477 identity/mode/reopen gates using synthetic JSON only."""

    workspace = _find_workspace(args.workspace)
    profile_path = _contained_workspace_file(
        workspace,
        args.profile_file,
        DEFAULT_B0477_PROFILE_RELATIVE,
        label="purchased camera profile",
    )
    fixture_path = _contained_workspace_file(
        workspace,
        args.fixture,
        Path("software/tests/fixtures/camera/b0477_nominal_rehearsal.json"),
        label="camera commissioning rehearsal fixture",
    )
    from rocell.vision import (
        CameraCommissioningRehearsalError,
        CameraProfileError,
        assess_camera_commissioning_rehearsal,
        load_camera_commissioning_rehearsal,
        load_camera_profile,
    )

    try:
        profile = load_camera_profile(profile_path)
        rehearsal = load_camera_commissioning_rehearsal(
            fixture_path,
            fixture_root=workspace,
        )
        assessment = assess_camera_commissioning_rehearsal(
            rehearsal,
            purchased_profile=profile,
        )
    except (
        CameraCommissioningRehearsalError,
        CameraProfileError,
        OSError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "CAMERA_COMMISSIONING_REHEARSAL_INVALID",
            f"Could not complete the synthetic B0477 commissioning rehearsal: {exc}",
            details={
                "profile": str(profile_path),
                "fixture": str(fixture_path),
            },
        ) from exc

    assessment_document = assessment.to_dict()
    document = {
        "schema": "rocell.camera_commissioning_rehearsal_cli.v1",
        "profile": {
            "id": profile.profile_id,
            "source_file_sha256": profile.source_file_sha256,
            "canonical_sha256": profile.canonical_sha256,
            "record_state": profile.record_state,
            "commissioning_state": profile.commissioning_state,
        },
        "fixture": {
            "path": fixture_path.relative_to(workspace).as_posix(),
            "source_file_sha256": rehearsal.source_file_sha256,
            "canonical_sha256": rehearsal.canonical_sha256,
            "class": rehearsal.fixture_class,
            "evidence_origin": rehearsal.evidence_origin,
        },
        "assessment": assessment_document,
        "assessment_sha256": assessment.canonical_sha256,
        "interpretation": (
            "PASS validates the synthetic parser and gate logic only; it does "
            "not show that a camera is present, received, calibrated, or ready."
        ),
        "authority": {
            "simulation_only": True,
            "commissioned": assessment.commissioned,
            "hardware_accessed": assessment.hardware_accessed,
            "camera_frames_requested": assessment.camera_frames_requested,
            "hardware_commands_generated": assessment.arm_commands,
            "physical_release_effect": assessment.physical_release_effect,
            "robot_motion_authorized": False,
            "contact_authorized": False,
        },
    }
    _emit(
        document,
        args.json,
        (
            f"B0477 commissioning rehearsal: {assessment.status}",
            f"synthetic reopen snapshots: {assessment.reopen_snapshot_count}; settings stable: true",
            "commissioned: false; hardware/camera frames/arm commands: 0/0/0",
            "physical receipt, USB enumeration, focus, calibration, motion, and contact remain blocked",
        ),
    )
    return int(ExitCode.OK)


def _command_rehearse_b0477_uvc_inventory(args: argparse.Namespace) -> int:
    """Exercise provider-neutral UVC selection gates using fake evidence only."""

    workspace = _find_workspace(args.workspace)
    profile_path = _contained_workspace_file(
        workspace,
        args.profile_file,
        DEFAULT_B0477_PROFILE_RELATIVE,
        label="purchased camera profile",
    )
    fixture_path = _contained_workspace_file(
        workspace,
        args.fixture,
        DEFAULT_B0477_UVC_INVENTORY_RELATIVE,
        label="synthetic B0477 UVC inventory fixture",
    )
    from rocell.vision import (
        CameraProfileError,
        DeterministicFakeUvcInventoryProvider,
        UvcInventoryError,
        assess_uvc_inventory,
        collect_uvc_inventory,
        load_camera_profile,
        parse_uvc_inventory_json,
    )

    try:
        profile = load_camera_profile(profile_path)
        parsed_inventory = parse_uvc_inventory_json(fixture_path.read_bytes())
        inventory = collect_uvc_inventory(
            DeterministicFakeUvcInventoryProvider(parsed_inventory)
        )
        assessment = assess_uvc_inventory(profile, inventory)
    except (CameraProfileError, UvcInventoryError, OSError, ValueError) as exc:
        raise ConfigurationError(
            "B0477_UVC_INVENTORY_REHEARSAL_INVALID",
            f"Could not complete the synthetic B0477 UVC inventory rehearsal: {exc}",
            details={
                "profile": str(profile_path),
                "fixture": str(fixture_path),
            },
        ) from exc

    # These digests let later synthetic calibration fixtures bind to exactly the
    # rehearsed identity and read-back settings without treating either as live
    # device evidence. A blocked selector intentionally yields no identity hash.
    selected_identity_sha256 = None
    selected = tuple(
        device
        for device in inventory.reopen_snapshots[0].devices
        if device.identity.persistent_path == inventory.selector_value
    )
    if len(selected) == 1:
        selected_identity_sha256 = selected[0].identity.canonical_sha256
    settings_sha256 = [
        snapshot.settings_sha256 for snapshot in inventory.reopen_snapshots
    ]
    assessment_document = assessment.to_dict()
    document = {
        "schema": "rocell.b0477_uvc_inventory_rehearsal_cli.v1",
        "profile": {
            "id": profile.profile_id,
            "source_file_sha256": profile.source_file_sha256,
            "canonical_sha256": profile.canonical_sha256,
            "record_state": profile.record_state,
            "commissioning_state": profile.commissioning_state,
        },
        "fixture": {
            "path": fixture_path.relative_to(workspace).as_posix(),
            "source_file_sha256": inventory.source_file_sha256,
            "canonical_sha256": inventory.canonical_sha256,
            "provider_id": inventory.provider_id,
            "purpose": inventory.purpose,
        },
        "synthetic_binding": {
            "persistent_selector": inventory.selector_value,
            "selected_identity_sha256": selected_identity_sha256,
            "reopen_settings_sha256": settings_sha256,
        },
        "assessment": assessment_document,
        "assessment_sha256": assessment.canonical_sha256,
        "interpretation": (
            "PASS validates only the deterministic UVC inventory parser and "
            "selection gates. Synthetic VID, PID, serial, path, modes, and "
            "controls are not observations of the purchased camera."
        ),
        "authority": {
            "simulation_only": True,
            "commissioned": assessment.commissioned,
            "hardware_accessed": assessment.hardware_accessed,
            "live_capture_performed": assessment.live_capture_performed,
            "camera_frames_requested": assessment.camera_frames_requested,
            "hardware_commands_generated": assessment.arm_commands,
            "live_capture_authority": assessment.live_capture_authority,
            "robot_motion_authority": assessment.robot_motion_authority,
            "contact_authority": assessment.contact_authority,
            "physical_release_effect": assessment.physical_release_effect,
        },
    }
    _emit(
        document,
        args.json,
        (
            f"B0477 UVC inventory rehearsal: {assessment.status}",
            f"synthetic provider: {inventory.provider_id}; reopen snapshots: {len(inventory.reopen_snapshots)}",
            "hardware/camera frames/arm commands: 0/0/0; commissioned: false",
            "real USB identity, mode negotiation, reconnect stability, motion, and contact remain blocked",
        ),
    )
    return int(
        ExitCode.OK
        if assessment.passed or not args.require_pass
        else ExitCode.CONFIGURATION_ERROR
    )


def _command_rehearse_b0477_intrinsics(args: argparse.Namespace) -> int:
    """Validate the sealed B0477 intrinsics workflow without camera access."""

    workspace = _find_workspace(args.workspace)
    profile_path = _contained_workspace_file(
        workspace,
        args.profile_file,
        DEFAULT_B0477_PROFILE_RELATIVE,
        label="purchased camera profile",
    )
    fixture_path = _contained_workspace_file(
        workspace,
        args.fixture,
        DEFAULT_B0477_INTRINSICS_REHEARSAL_RELATIVE,
        label="synthetic B0477 intrinsics rehearsal fixture",
    )
    from rocell.calibration import (
        StaticCameraIntrinsicsError,
        assess_static_camera_intrinsics_rehearsal,
        load_static_camera_intrinsics_rehearsal,
    )
    from rocell.vision import CameraProfileError, load_camera_profile

    try:
        profile = load_camera_profile(profile_path)
        artifact = load_static_camera_intrinsics_rehearsal(
            fixture_path,
            fixture_root=workspace,
        )
        assessment = assess_static_camera_intrinsics_rehearsal(
            artifact,
            purchased_profile=profile,
        )
    except (
        CameraProfileError,
        StaticCameraIntrinsicsError,
        OSError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "B0477_INTRINSICS_REHEARSAL_INVALID",
            f"Could not validate the synthetic B0477 intrinsics rehearsal: {exc}",
            details={
                "profile": str(profile_path),
                "fixture": str(fixture_path),
            },
        ) from exc

    aggregate = dict(artifact.aggregate_residuals)
    assessment_document = assessment.to_dict()
    document = {
        "schema": "rocell.b0477_intrinsics_rehearsal_cli.v1",
        "profile": {
            "id": profile.profile_id,
            "source_file_sha256": profile.source_file_sha256,
            "canonical_sha256": profile.canonical_sha256,
            "record_state": profile.record_state,
        },
        "fixture": {
            "path": fixture_path.relative_to(workspace).as_posix(),
            "artifact_id": artifact.artifact_id,
            "artifact_class": artifact.artifact_class,
            "source_file_sha256": artifact.source_file_sha256,
            "canonical_sha256": artifact.canonical_sha256,
            "integrity_sha256": artifact.integrity_sha256,
        },
        "bindings": {
            "profile_source_file_sha256": artifact.profile_source_file_sha256,
            "persistent_camera_identity_sha256": (
                artifact.persistent_camera_identity_sha256
            ),
            "focus_lock_evidence_sha256": artifact.focus_lock_evidence_sha256,
            "aperture_lock_evidence_sha256": artifact.aperture_lock_evidence_sha256,
            "controls_snapshot_sha256": artifact.controls_snapshot_sha256,
            "settings_binding_sha256": artifact.settings_binding_sha256,
            "input_bindings_sha256": artifact.input_bindings_sha256,
            "images_manifest_sha256": artifact.images_manifest_sha256,
            "split_commitment_sha256": artifact.split_commitment_sha256,
            "undistortion_map_sha256": artifact.undistortion_map_sha256,
        },
        "target_mode": artifact.mode.to_dict(),
        "dataset": {
            "training_views": len(artifact.training_image_ids),
            "held_out_views": len(artifact.held_out_image_ids),
            "charuco_maximum_corner_count": artifact.board.maximum_corner_count,
        },
        "synthetic_solution": {
            "distortion_model": artifact.distortion_model,
            "distortion_coefficient_count": len(artifact.distortion_coefficients),
            "valid_pixel_roi": list(artifact.valid_pixel_roi),
            "output_crop": list(artifact.output_crop),
            "aggregate_residuals_px": aggregate,
        },
        "assessment": assessment_document,
        "assessment_sha256": assessment.canonical_sha256,
        "interpretation": (
            "The pass validates a sealed synthetic calibration-data contract and "
            "held-out gate logic only. The numeric solution and evidence hashes "
            "are rehearsal data, not measurements from the purchased camera."
        ),
        "authority": {
            "simulation_only": True,
            "physical_calibration_valid": assessment.physical_calibration_valid,
            "commissioned": assessment.commissioned,
            "hardware_accessed": assessment.hardware_accessed,
            "camera_frames_requested": assessment.camera_frames_requested,
            "hardware_commands_generated": assessment.arm_motion_commands,
            "contact_commands": assessment.contact_commands,
            "robot_motion_authority": assessment.robot_motion_authority,
            "contact_authority": assessment.contact_authority,
            "physical_release_effect": assessment.physical_release_effect,
        },
    }
    _emit(
        document,
        args.json,
        (
            f"B0477 intrinsics rehearsal: {assessment.status}",
            f"synthetic ChArUco views: {assessment.training_view_count} training / {assessment.held_out_view_count} held out",
            f"target mode: {artifact.mode.width_px}x{artifact.mode.height_px} @ {artifact.mode.fps:g} fps {artifact.mode.pixel_format}",
            "physical calibration/camera frames/robot motion/contact authority: false",
        ),
    )
    return int(ExitCode.OK)


def _command_rehearse_b0477_stack(args: argparse.Namespace) -> int:
    """Cross-check every selected B0477 component and optional pixel evidence."""

    workspace = _find_workspace(args.workspace)
    from rocell.application import (
        B0477StackCoherenceError,
        B0477StaticVisionError,
        B0477StaticVisionMode,
        load_and_assess_b0477_stack_coherence,
        run_b0477_static_vision_rehearsal,
    )

    normal_report = None
    tag_loss_report = None
    try:
        if not args.skip_pixel_vision:
            normal_report = run_b0477_static_vision_rehearsal(
                workspace,
                sequence=args.sequence,
                mode=B0477StaticVisionMode.NORMAL,
                camera_profile_path=args.profile_file,
                support_design_path=args.support_file,
            )
            tag_loss_report = run_b0477_static_vision_rehearsal(
                workspace,
                sequence=args.sequence,
                mode=B0477StaticVisionMode.TAG_LOSS,
                camera_profile_path=args.profile_file,
                support_design_path=args.support_file,
            )
        report = load_and_assess_b0477_stack_coherence(
            workspace,
            camera_profile_path=args.profile_file,
            support_design_path=args.support_file,
            commissioning_fixture_path=args.commissioning_fixture,
            uvc_inventory_fixture_path=args.uvc_fixture,
            intrinsics_fixture_path=args.intrinsics_fixture,
            normal_vision_report=normal_report,
            tag_loss_vision_report=tag_loss_report,
        )
    except (
        B0477StackCoherenceError,
        B0477StaticVisionError,
        OSError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "B0477_STACK_REHEARSAL_INVALID",
            f"Could not complete the B0477 stack coherence rehearsal: {exc}",
        ) from exc

    report_document = report.to_dict()
    pixel_summary: dict[str, object]
    if normal_report is None or tag_loss_report is None:
        pixel_summary = {
            "executed": False,
            "reason": "SKIPPED_BY_EXPLICIT_CLI_OPTION",
        }
    else:
        pixel_summary = {
            "executed": True,
            "sequence": args.sequence,
            "normal": {
                "status": normal_report.status,
                "detail_code": normal_report.detail_code,
                "detected_tag_ids": list(normal_report.detected_tag_ids),
                "inlier_tag_ids": list(normal_report.inlier_tag_ids),
                "report_sha256": normal_report.content_sha256,
            },
            "tag_loss": {
                "status": tag_loss_report.status,
                "detail_code": tag_loss_report.detail_code,
                "detected_tag_ids": list(tag_loss_report.detected_tag_ids),
                "inlier_tag_ids": list(tag_loss_report.inlier_tag_ids),
                "report_sha256": tag_loss_report.content_sha256,
            },
        }
    document = {
        "schema": "rocell.b0477_stack_rehearsal_cli.v1",
        "status": report.status,
        "passed": report.passed,
        "report": report_document,
        "report_sha256": report.canonical_sha256,
        "pixel_vision": pixel_summary,
        "interpretation": (
            "A pass proves that the selected purchase profile, support screen, "
            "fake UVC evidence, commissioning rehearsal, intrinsics rehearsal, "
            "and any included pixel reports are internally coherent. It does "
            "not prove receipt, calibration, installation, or physical safety."
        ),
        "authority": report_document["authority"],
    }
    _emit(
        document,
        args.json,
        (
            f"B0477 stack rehearsal: {report.status}",
            f"coherence checks: {sum(check.passed for check in report.checks)}/{len(report.checks)}",
            f"pixel vision pair: {'executed' if pixel_summary['executed'] else 'explicitly skipped'}",
            "physical camera/calibration/robot motion/contact authority: false",
        ),
    )
    return int(
        ExitCode.OK
        if report.passed or not args.require_pass
        else ExitCode.CONFIGURATION_ERROR
    )


def _command_simulate_b0477_vision(args: argparse.Namespace) -> int:
    """Run the purchased-camera static JPEG/tag/pose path in simulation."""

    workspace = _find_workspace(args.workspace)
    from rocell.application import (
        B0477StaticVisionError,
        B0477StaticVisionMode,
        run_b0477_static_vision_rehearsal,
    )
    from rocell.simulation.synthetic_raster import SyntheticRasterError

    mode = {
        "normal": B0477StaticVisionMode.NORMAL,
        "tag-loss": B0477StaticVisionMode.TAG_LOSS,
    }[args.mode]
    try:
        report = run_b0477_static_vision_rehearsal(
            workspace,
            sequence=args.sequence,
            mode=mode,
        )
    except (B0477StaticVisionError, SyntheticRasterError, OSError, ValueError) as exc:
        raise ConfigurationError(
            "B0477_STATIC_VISION_REHEARSAL_INVALID",
            f"Could not run the B0477 static-overhead vision rehearsal: {exc}",
        ) from exc
    expected = (
        report.status == "PASS"
        if mode is B0477StaticVisionMode.NORMAL
        else (
            report.status == "REJECTED"
            and report.detail_code == "B0477_STATIC_TAG_LOSS_NATURALLY_REJECTED"
        )
    )
    report_document = report.to_dict()
    document = {
        "schema": "rocell.b0477_static_vision_cli.v1",
        "scenario_behaved_as_expected": expected,
        "report": report_document,
        "report_sha256": report.content_sha256,
        "interpretation": (
            "The result crosses a real synthetic JPEG/pixel detector/pose "
            "boundary using nominal published-FOV-derived geometry. It is not "
            "physical camera, calibration, accuracy, or release evidence."
        ),
        "authority": report_document["authority"],
    }
    _emit(
        document,
        args.json,
        (
            f"B0477 static vision ({args.mode}): {report.status} / {report.detail_code}",
            f"tags visible/detected/inlier: {len(report.visible_tag_ids)}/{len(report.detected_tag_ids)}/{len(report.inlier_tag_ids)}",
            f"synthetic proxy: {report.pixel_statistics.width_px}x{report.pixel_statistics.height_px}; expected behavior: {str(expected).lower()}",
            "physical camera/calibration/motion/contact authority: false",
        ),
    )
    return int(
        ExitCode.OK
        if expected or not args.require_expected
        else ExitCode.CONFIGURATION_ERROR
    )


def _command_rehearse_first_power_on(args: argparse.Namespace) -> int:
    """Run the ordered first-power-on process against fake providers only."""

    workspace = _find_workspace(args.workspace)
    from rocell.application.first_power_on_onboarding import (
        FirstPowerOnError,
        load_first_power_on_checkpoint,
        run_first_power_on_rehearsal,
        save_first_power_on_checkpoint,
    )

    try:
        checkpoint = (
            load_first_power_on_checkpoint(workspace, args.resume)
            if args.resume is not None
            else None
        )
        report = run_first_power_on_rehearsal(
            workspace,
            scenario=args.scenario,
            stop_after=args.stop_after,
            checkpoint=checkpoint,
        )
        saved_path = (
            save_first_power_on_checkpoint(workspace, args.checkpoint, report)
            if args.checkpoint is not None
            else None
        )
    except (FirstPowerOnError, OSError, ValueError, RuntimeError) as exc:
        raise ConfigurationError(
            "FIRST_POWER_ON_REHEARSAL_INVALID",
            f"Could not complete the zero-hardware first-power-on rehearsal: {exc}",
        ) from exc

    document: dict[str, Any] = {
        "schema": "rocell.first_power_on_rehearsal_cli.v2",
        "rehearsal": report.to_dict(),
        "rehearsal_report_sha256": report.report_sha256,
        "checkpoint": (
            {
                "path": saved_path.relative_to(workspace).as_posix(),
                "created": True,
            }
            if saved_path is not None
            else None
        ),
        "interpretation": (
            "A nominal completion proves the onboarding state machine and fake "
            "boundaries only. It does not prove camera receipt, connectivity, "
            "physical calibration, robot power safety, motion, or contact."
        ),
    }
    blocked = report.first_blocked_stage
    _emit(
        document,
        args.json,
        (
            f"first-power-on rehearsal: {report.status}",
            f"scenario: {report.scenario.value}; expected outcome: {str(report.expected_outcome_observed).lower()}",
            (
                f"stages recorded: {len(report.records)}/{len(_FIRST_POWER_ON_STAGES)}; "
                f"blocked: {blocked.value if blocked is not None else 'none'}"
            ),
            (
                f"synthetic frames/T=105 queries: {report.emulated_camera_frames}/"
                f"{report.emulated_feedback_queries}; real hardware operations: 0"
            ),
            "physical onboarding/calibration/motion/contact authority: false",
            f"next safe action: {report.to_dict()['next_safe_action']}",
        ),
    )
    return int(
        ExitCode.OK
        if report.expected_outcome_observed or not args.require_expected
        else ExitCode.CONFIGURATION_ERROR
    )


def _command_bootstrap_sim(args: argparse.Namespace) -> int:
    """Emit the complete deterministic virtual-workcell startup report."""

    bootstrap = _load_virtual_bootstrap(args)
    document = bootstrap.to_dict()
    declared_gap_count = sum(
        check.status == "DECLARED_GAP" for check in bootstrap.checks
    )
    _emit(
        document,
        args.json,
        (
            f"virtual bootstrap: {bootstrap.status}",
            f"bootstrap hash: {bootstrap.bootstrap_hash}",
            f"checks: {len(bootstrap.checks)}; declared gaps: {declared_gap_count}",
            "hardware access: not attempted; hardware commands generated: 0",
        ),
    )
    return int(
        ExitCode.OK if bootstrap.simulation_ready else ExitCode.CONFIGURATION_ERROR
    )


def _compile_plan(device: str, text: str) -> ActionPlan:
    try:
        return compile_development_text(device, text)
    except (UnsupportedCharacterError, ValueError, TypeError) as exc:
        if device not in {"keyboard", "phone"}:
            raise UsageError(
                "UNKNOWN_DEVICE", f"Unsupported device {device!r}"
            ) from exc
        raise UsageError(
            "TEXT_NOT_SUPPORTED_BY_DEVELOPMENT_PROFILE",
            str(exc),
            details={"device": device},
        ) from exc


def _virtual_fault_script(profile: str, device: str) -> Any:
    """Translate one bounded CLI fault profile into an immutable script."""

    from rocell.simulation import (
        VirtualFaultKind,
        VirtualFaultScript,
        VirtualFaultTrigger,
    )

    if profile == "none":
        return VirtualFaultScript("cli-none")
    if device not in {"keyboard", "phone"}:
        raise UsageError("UNKNOWN_DEVICE", f"Unsupported device {device!r}")
    if profile == "keyboard-double" and device != "keyboard":
        raise UsageError(
            "FAULT_PROFILE_DEVICE_MISMATCH",
            "--fault-profile keyboard-double requires --device keyboard",
        )
    if profile == "phone-wrong-ui" and device != "phone":
        raise UsageError(
            "FAULT_PROFILE_DEVICE_MISMATCH",
            "--fault-profile phone-wrong-ui requires --device phone",
        )

    component = "keyboard" if device == "keyboard" else "android"
    definitions: dict[str, tuple[Any, str, str]] = {
        "arm-connect": (VirtualFaultKind.ARM_CONNECT_FAILURE, "arm", "connect"),
        "arm-reference": (
            VirtualFaultKind.ARM_REFERENCE_FAILURE,
            "arm",
            "reference",
        ),
        "arm-stall": (VirtualFaultKind.ARM_STALL, "arm", "execute_waypoint"),
        "camera-unavailable": (
            VirtualFaultKind.CAMERA_UNAVAILABLE,
            "camera",
            "observe",
        ),
        # Keep tag loss distinct from camera unavailability: this mode renders
        # and decodes a real JPEG, then fails naturally at the minimum-tag
        # pose gate after the four world-reference tags disappear.
        "camera-tag-loss": (
            VirtualFaultKind.CAMERA_TAG_LOSS,
            "camera",
            "observe",
        ),
        "contact-missed": (
            (
                VirtualFaultKind.KEYBOARD_MISSED_CONTACT
                if device == "keyboard"
                else VirtualFaultKind.ANDROID_MISSED_CONTACT
            ),
            component,
            "contact",
        ),
        "keyboard-double": (
            VirtualFaultKind.KEYBOARD_DOUBLE_CONTACT,
            "keyboard",
            "contact",
        ),
        "phone-wrong-ui": (
            VirtualFaultKind.ANDROID_WRONG_UI_STATE,
            "android",
            "verify_state",
        ),
        "focus-lost": (
            VirtualFaultKind.DEVICE_FOCUS_LOST,
            component,
            "contact",
        ),
    }
    try:
        kind, selected_component, operation = definitions[profile]
    except KeyError as exc:
        raise UsageError(
            "UNKNOWN_VIRTUAL_FAULT_PROFILE",
            f"Unsupported virtual fault profile {profile!r}",
        ) from exc
    trigger = VirtualFaultTrigger(
        trigger_id=f"cli-{profile}",
        kind=kind,
        component=selected_component,
        operation=operation,
    )
    return VirtualFaultScript(f"cli-{profile}-{device}", (trigger,))


def _command_simulate_integrated_v2(args: argparse.Namespace) -> int:
    """Run the dense camera/collision/authorization-bound V2 rehearsal."""

    bootstrap = _load_virtual_bootstrap(args)
    workspace = bootstrap.runtime.workspace
    selected_journal_root = args.journal_root.expanduser()
    journal_root = (
        selected_journal_root
        if selected_journal_root.is_absolute()
        else workspace / selected_journal_root
    )
    # Keep the final path component unresolved so the journal layer can reject
    # a caller-supplied symlink instead of silently following it.
    journal_root = Path(os.path.abspath(journal_root))
    if args.fault_kind == "none":
        if args.fault_command_ordinal is not None:
            raise UsageError(
                "INTEGRATED_V2_FAULT_KIND_REQUIRED",
                "--fault-command-ordinal requires a non-none --fault-kind",
            )
        fault_injections: tuple[Any, ...] = ()
    else:
        if args.fault_command_ordinal is None:
            raise UsageError(
                "INTEGRATED_V2_FAULT_ORDINAL_REQUIRED",
                "a non-none --fault-kind requires --fault-command-ordinal",
            )
        from rocell.simulation.t104_runtime import (
            MAX_RUNTIME_COMMANDS,
            T104FaultInjection,
        )

        if not 0 <= args.fault_command_ordinal < MAX_RUNTIME_COMMANDS:
            raise UsageError(
                "INTEGRATED_V2_FAULT_ORDINAL_INVALID",
                "--fault-command-ordinal is outside the bounded runtime range",
            )

        fault_injections = (
            T104FaultInjection(
                sequence_ordinal=args.fault_command_ordinal,
                fault_kind=args.fault_kind.upper(),
            ),
        )

    if args.camera_fault_kind == "none":
        if args.camera_fault_contact_ordinal is not None:
            raise UsageError(
                "INTEGRATED_V2_CAMERA_FAULT_KIND_REQUIRED",
                (
                    "--camera-fault-contact-ordinal requires a non-none "
                    "--camera-fault-kind"
                ),
            )
        camera_fault_injection: Any = None
    else:
        if args.camera_fault_contact_ordinal is None:
            raise UsageError(
                "INTEGRATED_V2_CAMERA_FAULT_ORDINAL_REQUIRED",
                (
                    "a non-none --camera-fault-kind requires "
                    "--camera-fault-contact-ordinal"
                ),
            )
        from rocell.simulation.b0477_replay_camera import (
            MAX_REPLAY_CONTACTS,
            B0477ReplayFaultInjection,
            B0477ReplayFaultKind,
        )

        if not 0 <= args.camera_fault_contact_ordinal < MAX_REPLAY_CONTACTS:
            raise UsageError(
                "INTEGRATED_V2_CAMERA_FAULT_ORDINAL_INVALID",
                "--camera-fault-contact-ordinal is outside the bounded range",
            )
        camera_fault_injection = B0477ReplayFaultInjection(
            contact_occurrence_ordinal=args.camera_fault_contact_ordinal,
            fault_kind=B0477ReplayFaultKind(
                args.camera_fault_kind.upper().replace("-", "_")
            ),
        )

    if args.fault_kind != "none" and args.camera_fault_kind != "none":
        raise UsageError(
            "INTEGRATED_V2_MULTIPLE_FAULTS_UNSUPPORTED",
            "select either one controller fault or one camera fault, not both",
        )

    from rocell.application.integrated_zero_hardware_mission import (
        IntegratedZeroHardwareMissionError,
        assemble_default_zero_hardware_mission_v2,
        open_zero_hardware_mission_v2,
        prepare_zero_hardware_mission_v2,
        run_zero_hardware_mission_v2,
    )
    from rocell.safety.authorization_v2 import AuthorizationV2Error
    from rocell.simulation.t104_runtime import T104RuntimeError

    try:
        assembly = assemble_default_zero_hardware_mission_v2(
            workspace,
            args.device,
            args.text,
            t104_fault_injections=fault_injections,
            camera_fault_injection=camera_fault_injection,
        )
        if (
            camera_fault_injection is not None
            and camera_fault_injection.contact_occurrence_ordinal
            >= assembly.contact_count
        ):
            raise UsageError(
                "INTEGRATED_V2_CAMERA_FAULT_ORDINAL_INVALID",
                (
                    "--camera-fault-contact-ordinal is outside this mission's "
                    "contact range"
                ),
            )
        prepared = (
            open_zero_hardware_mission_v2(assembly, journal_root)
            if args.open_existing
            else prepare_zero_hardware_mission_v2(assembly, journal_root)
        )
        report = run_zero_hardware_mission_v2(prepared)
    except (
        AuthorizationV2Error,
        IntegratedZeroHardwareMissionError,
        T104RuntimeError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "INTEGRATED_V2_REHEARSAL_INVALID",
            f"Could not complete the integrated V2 rehearsal: {exc}",
            details={
                "journal_root": str(journal_root),
                "open_existing": bool(args.open_existing),
                "fault_kind": args.fault_kind,
                "fault_command_ordinal": args.fault_command_ordinal,
                "camera_fault_kind": args.camera_fault_kind,
                "camera_fault_contact_ordinal": (args.camera_fault_contact_ordinal),
            },
        ) from exc

    report_document = report.to_dict()
    document = {
        "schema": "rocell.integrated_zero_hardware_mission_cli.v1",
        "status": report.status,
        "completed": report.completed,
        "assembly": {
            "assembly_sha256": assembly.assembly_sha256,
            "source_action_plan_sha256": assembly.plan.plan_hash,
            "semantic_step_count": len(assembly.semantic_schedule.steps),
            "observation_only_step_count": assembly.observation_only_step_count,
            "contact_count": assembly.contact_count,
            "route_waypoint_count": assembly.dense_route.route_waypoint_count,
            "command_count": assembly.command_count,
            "physical_clearance_established": False,
        },
        "journal_root": str(journal_root),
        "opened_existing_journals": bool(args.open_existing),
        "fault_injection": {
            "controller": {
                "kind": args.fault_kind,
                "command_ordinal": args.fault_command_ordinal,
            },
            "camera": {
                "kind": args.camera_fault_kind,
                "contact_occurrence_ordinal": (args.camera_fault_contact_ordinal),
            },
        },
        "report": report_document,
        "report_sha256": report.report_sha256,
        "authority": {
            "simulation_only": True,
            "physical_authority": "ZERO",
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "wire_messages_generated": 0,
            "power_authorized": False,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    _emit(
        document,
        args.json,
        (
            f"integrated V2 rehearsal: {report.status}",
            (
                f"semantic steps/contacts: {len(assembly.semantic_schedule.steps)}"
                f"/{assembly.contact_count}; observation-only: "
                f"{assembly.observation_only_step_count}"
            ),
            (
                f"route waypoints/controller commands: "
                f"{assembly.dense_route.route_waypoint_count}/{assembly.command_count}"
            ),
            (
                f"camera/contact receipts: "
                f"{len(report.camera_observation_sha256s)}"
                f"/{len(report.contact_receipts)}; output verified: "
                f"{report.outcome_matches}"
            ),
            f"journal root: {journal_root}",
            "physical camera/calibration/clearance/motion/contact authority: false",
        ),
    )
    return int(
        ExitCode.OK
        if report.completed or not args.require_pass
        else ExitCode.CONFIGURATION_ERROR
    )


def _command_simulate_session(args: argparse.Namespace) -> int:
    """Run the locked end-to-end virtual typing/tapping pipeline."""

    bootstrap = _load_virtual_bootstrap(args)
    plan = _compile_plan(args.device, args.text)
    fault_script = _virtual_fault_script(args.fault_profile, args.device)
    from rocell.application import (
        BootstrapConfigurationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualSessionError,
        VirtualSessionScenarioBinding,
        run_virtual_session,
    )
    from rocell.simulation import (
        VirtualCommissioningProfileError,
        VirtualWorkcellError,
        load_virtual_commissioning_profile,
    )

    try:
        profile = load_virtual_commissioning_profile(bootstrap.context)
        park = profile.park_point_board
        scenario = VirtualSessionScenarioBinding(
            scenario_id=profile.profile_id,
            scenario_hash=profile.source_sha256,
            park_point_board_mm=(park.x, park.y, park.z),
        )
        report = run_virtual_session(
            bootstrap,
            plan,
            args.text,
            profile.study_input,
            scenario,
            fault_script=fault_script,
        )
    except (
        BootstrapConfigurationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualCommissioningProfileError,
        VirtualSessionError,
        VirtualWorkcellError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "VIRTUAL_SESSION_FAILED",
            f"Could not run the locked virtual session: {exc}",
            details={"fault_profile": args.fault_profile},
        ) from exc

    evidence_record: Mapping[str, Any] | None = None
    if args.record:
        from rocell.evidence.virtual_session import (
            VirtualSessionEvidenceError,
            record_virtual_session,
        )

        try:
            evidence_record = record_virtual_session(
                report,
                bootstrap.runtime.evidence_root_path,
            ).to_dict()
        except (VirtualSessionEvidenceError, OSError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                "VIRTUAL_SESSION_RECORD_FAILED",
                f"Could not write immutable virtual-session evidence: {exc}",
                details={
                    "evidence_root": str(bootstrap.runtime.evidence_root_path),
                    "session_report_hash": report.report_hash,
                },
            ) from exc

    document: dict[str, Any] = {
        "schema": "rocell.simulate_session_cli.v1",
        "status": report.status,
        "pipeline_completed": report.pipeline_completed,
        "session_report_hash": report.report_hash,
        "fault_profile": args.fault_profile,
        "record_requested": bool(args.record),
        "evidence_record": evidence_record,
        "virtual_session": report.to_dict(),
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    human_lines = [
        f"virtual session: {report.status}",
        f"session report hash: {report.report_hash}",
        f"fault profile: {args.fault_profile}; completed: {report.pipeline_completed}",
        "hardware access: not attempted; hardware commands generated: 0",
    ]
    if evidence_record is not None:
        human_lines.append(f"evidence manifest: {evidence_record['manifest']}")
    _emit(document, args.json, tuple(human_lines))
    if args.require_pass and not report.pipeline_completed:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_simulate_adaptive_session(args: argparse.Namespace) -> int:
    """Run the arm-camera correction rehearsal without any hardware adapter."""

    bootstrap = _load_virtual_bootstrap(args)
    # Validate unsupported text as a usage error before the comparatively
    # expensive raster/trajectory rehearsal.
    plan = _compile_plan(args.device, args.text)

    from rocell.application import (
        AdaptiveVirtualSessionError,
        BootstrapConfigurationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualSessionScenarioBinding,
        make_hidden_virtual_board_truth,
        run_adaptive_virtual_session,
    )
    from rocell.geometry import Vec3
    from rocell.simulation import (
        VirtualCommissioningProfileError,
        VirtualWorkcellError,
        load_virtual_commissioning_profile,
    )

    try:
        profile = load_virtual_commissioning_profile(bootstrap.context)
        park = profile.park_point_board
        scenario = VirtualSessionScenarioBinding(
            scenario_id=profile.profile_id,
            scenario_hash=profile.source_sha256,
            park_point_board_mm=(park.x, park.y, park.z),
        )
        truth = make_hidden_virtual_board_truth(
            profile.study_input,
            translation_Wv_mm=Vec3(
                args.truth_offset_x_mm,
                args.truth_offset_y_mm,
                args.truth_offset_z_mm,
            ),
            yaw_board_rad=math.radians(args.truth_yaw_deg),
        )
        report = run_adaptive_virtual_session(
            bootstrap,
            plan,
            args.text,
            profile.study_input,
            scenario,
            truth=truth,
        )
    except (
        AdaptiveVirtualSessionError,
        BootstrapConfigurationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualCommissioningProfileError,
        VirtualWorkcellError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "ADAPTIVE_VIRTUAL_SESSION_FAILED",
            f"Could not run the adaptive arm-camera simulation: {exc}",
            details={
                "device": args.device,
                "truth_controls": "HIDDEN_VIRTUAL_PLANT_SIMULATION_ONLY",
            },
        ) from exc

    document: dict[str, Any] = {
        "schema": "rocell.simulate_adaptive_session_cli.v1",
        "status": report.status,
        "pipeline_completed": report.pipeline_completed,
        "adaptive_session_report_hash": report.report_hash,
        # Deliberately do not echo the injected transform: the adaptive report
        # treats plant truth as opaque and exposes only its content hash.
        "synthetic_truth_injection": {
            "scope": "HIDDEN_VIRTUAL_PLANT_SIMULATION_ONLY",
            "transform_serialized": False,
            "can_update_calibration_registry": False,
        },
        "adaptive_virtual_session": report.to_dict(),
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"adaptive virtual session: {report.status}",
            f"adaptive report hash: {report.report_hash}",
            f"correction revisions installed: {len(report.correction_installations)}",
            "hardware access: not attempted; hardware commands generated: 0",
        ),
    )
    if args.require_pass and not report.pipeline_completed:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_qualify_prehardware(args: argparse.Namespace) -> int:
    """Run a locked aggregate software qualification without hardware I/O."""

    workspace = _find_workspace(args.workspace)
    from rocell.application import (
        AdaptiveVirtualSessionError,
        BootstrapConfigurationError,
        MissionRouteCoverageError,
        PrehardwareQualificationError,
        PrehardwareQualificationPolicy,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualSessionError,
        run_prehardware_qualification,
    )
    from rocell.simulation import (
        VirtualCommissioningProfileError,
        VirtualWorkcellError,
    )

    try:
        policy = PrehardwareQualificationPolicy(profile=args.profile)
        report = run_prehardware_qualification(
            workspace,
            runtime_path=args.runtime,
            policy=policy,
        )
    except (
        AdaptiveVirtualSessionError,
        BootstrapConfigurationError,
        MissionRouteCoverageError,
        PrehardwareQualificationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualCommissioningProfileError,
        VirtualSessionError,
        VirtualWorkcellError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "PREHARDWARE_QUALIFICATION_FAILED",
            f"Could not run the locked prehardware qualification: {exc}",
            details={"profile": args.profile, "hardware_accessed": False},
        ) from exc

    evidence_record: Mapping[str, Any] | None = None
    if args.record:
        from rocell.application import load_runtime_policy
        from rocell.evidence import (
            PrehardwareQualificationEvidenceError,
            record_prehardware_qualification,
        )

        try:
            runtime = load_runtime_policy(workspace, args.runtime)
            evidence_record = record_prehardware_qualification(
                report,
                runtime.evidence_root_path,
            ).to_dict()
        except (
            BootstrapConfigurationError,
            PrehardwareQualificationEvidenceError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise ConfigurationError(
                "PREHARDWARE_QUALIFICATION_RECORD_FAILED",
                "Could not write immutable prehardware qualification evidence: "
                f"{exc}",
                details={
                    "profile": args.profile,
                    "qualification_report_hash": report.report_hash,
                    "hardware_accessed": False,
                },
            ) from exc

    report_document = report.to_dict()
    coverage_state = report_document.get("coverage_state", "UNKNOWN")
    document: dict[str, Any] = {
        "schema": "rocell.qualify_prehardware_cli.v1",
        "status": report.status,
        "profile": args.profile,
        "campaign_passed": report.campaign_passed,
        "coverage_state": coverage_state,
        "all_mission_routes_accepted": report.all_mission_routes_accepted,
        "physical_ready": report.physical_ready,
        "qualification_report_hash": report.report_hash,
        "record_requested": bool(args.record),
        "evidence_record": evidence_record,
        "prehardware_qualification": report_document,
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    case_summary = report_document.get("case_summary", {})
    human_lines = [
        f"prehardware qualification: {report.status}",
        f"profile: {args.profile}; case summary: {case_summary}",
        f"campaign passed: {str(report.campaign_passed).lower()}",
        (
            "all mission routes accepted: "
            f"{str(report.all_mission_routes_accepted).lower()} "
            f"(coverage state: {coverage_state})"
        ),
        f"physical ready: {str(report.physical_ready).lower()}",
        "hardware commands generated: 0",
        f"qualification report hash: {report.report_hash}",
    ]
    if evidence_record is not None:
        human_lines.append(f"evidence manifest: {evidence_record['manifest']}")
    _emit(document, args.json, tuple(human_lines))
    if args.require_pass and not report.campaign_passed:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _resolve_virtual_session_manifest(
    bootstrap: Any,
    requested: Path,
) -> Path:
    """Resolve a replay manifest and reject any escape from the evidence root."""

    workspace = bootstrap.runtime.workspace
    evidence_root = bootstrap.runtime.evidence_root_path.resolve()
    expanded = requested.expanduser()
    selected = (expanded if expanded.is_absolute() else workspace / expanded).resolve()
    try:
        selected.relative_to(evidence_root)
    except ValueError as exc:
        raise UsageError(
            "SESSION_MANIFEST_OUTSIDE_EVIDENCE_ROOT",
            "The replay manifest must be contained by the runtime evidence root",
            details={
                "manifest": str(selected),
                "evidence_root": str(evidence_root),
            },
        ) from exc
    if selected.name != "manifest.json" or not selected.is_file():
        raise UsageError(
            "SESSION_MANIFEST_NOT_FOUND",
            "--manifest must name an existing virtual-session manifest.json",
            details={"manifest": str(selected)},
        )
    return selected


def _resolve_prehardware_qualification_manifest(
    runtime: Any,
    requested: Path,
) -> Path:
    """Resolve a qualification manifest within the configured evidence root."""

    workspace = runtime.workspace
    evidence_root = runtime.evidence_root_path.resolve()
    expanded = requested.expanduser()
    candidate = expanded if expanded.is_absolute() else workspace / expanded
    if candidate.is_symlink() or candidate.parent.is_symlink():
        raise UsageError(
            "QUALIFICATION_MANIFEST_SYMLINK_REJECTED",
            "The qualification manifest and record directory must not be symlinks",
            details={"manifest": str(candidate)},
        )
    selected = candidate.resolve()
    try:
        selected.relative_to(evidence_root)
    except ValueError as exc:
        raise UsageError(
            "QUALIFICATION_MANIFEST_OUTSIDE_EVIDENCE_ROOT",
            "The qualification replay manifest must be contained by the runtime "
            "evidence root",
            details={
                "manifest": str(selected),
                "evidence_root": str(evidence_root),
            },
        ) from exc
    if selected.name != "manifest.json" or not selected.is_file():
        raise UsageError(
            "QUALIFICATION_MANIFEST_NOT_FOUND",
            "--manifest must name an existing prehardware qualification manifest.json",
            details={"manifest": str(selected)},
        )
    return selected


def _command_replay_prehardware_qualification(args: argparse.Namespace) -> int:
    """Verify and fully recompute a qualification evidence package."""

    workspace = _find_workspace(args.workspace)
    from rocell.application import (
        AdaptiveVirtualSessionError,
        BootstrapConfigurationError,
        MissionRouteCoverageError,
        PrehardwareQualificationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualSessionError,
        load_runtime_policy,
    )
    from rocell.evidence import (
        PrehardwareQualificationEvidenceError,
        replay_prehardware_qualification,
    )
    from rocell.simulation import (
        VirtualCommissioningProfileError,
        VirtualWorkcellError,
    )

    try:
        runtime = load_runtime_policy(workspace, args.runtime)
    except (BootstrapConfigurationError, OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "PREHARDWARE_QUALIFICATION_REPLAY_RUNTIME_INVALID",
            f"Could not load the zero-authority replay runtime: {exc}",
            details={"hardware_accessed": False},
        ) from exc
    manifest_path = _resolve_prehardware_qualification_manifest(
        runtime,
        args.qualification_manifest,
    )
    try:
        replay = replay_prehardware_qualification(
            workspace,
            manifest_path,
            runtime_path=runtime.source_path,
        )
    except (
        AdaptiveVirtualSessionError,
        BootstrapConfigurationError,
        MissionRouteCoverageError,
        PrehardwareQualificationError,
        PrehardwareQualificationEvidenceError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualCommissioningProfileError,
        VirtualSessionError,
        VirtualWorkcellError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "PREHARDWARE_QUALIFICATION_REPLAY_FAILED",
            "Could not verify and recompute prehardware qualification evidence: "
            f"{exc}",
            details={
                "manifest": str(manifest_path),
                "hardware_accessed": False,
            },
        ) from exc

    replay_document = replay.to_dict()
    document: dict[str, Any] = {
        "schema": "rocell.replay_prehardware_qualification_cli.v1",
        "status": replay.status,
        "profile": replay.profile,
        "identical": replay.identical,
        "evidence_manifest": manifest_path.relative_to(
            runtime.evidence_root_path
        ).as_posix(),
        "replay": replay_document,
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "execution_authorized": False,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"prehardware qualification replay: {replay.status}",
            f"profile: {replay.profile}; identical: {str(replay.identical).lower()}",
            f"recorded report: {replay.recorded_report_sha256}",
            f"recomputed report: {replay.recomputed_report_sha256}",
            "hardware access: not attempted; hardware commands generated: 0",
        ),
    )
    if args.require_identical and not replay.identical:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_replay_typing_trace(args: argparse.Namespace) -> int:
    """Verify one contained PC6 trace package without interpreting artifacts."""

    from rocell.application.typing_trace_package_v1 import (
        TypingTracePackageV1Error,
        replay_typing_trace_package_v1,
    )

    try:
        report = replay_typing_trace_package_v1(
            args.evidence_root,
            args.package_id,
            expected_correlation_id=args.expected_correlation_id,
            expected_request_id=args.expected_request_id,
        )
    except (OSError, TypeError, ValueError, TypingTracePackageV1Error) as exc:
        raise ConfigurationError(
            "TYPING_TRACE_REPLAY_FAILED",
            f"Could not verify the contained typing trace package: {exc}",
            details={
                "package_id": args.package_id,
                "hardware_accessed": False,
                "hardware_commands_generated": 0,
            },
        ) from exc
    document: dict[str, Any] = {
        "schema": "rocell.replay_typing_trace_cli.v1",
        "status": report["status"],
        "identical": report["replay"]["identical"],
        "package_id": report["package_id"],
        "package_sha256": report["package_sha256"],
        "typing_trace_replay_sha256": report["replay"][
            "typing_trace_replay_sha256"],
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "execution_authorized": False,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"typing trace replay: {report['status']}",
            f"package: {report['package_id']}",
            f"identical: {str(report['replay']['identical']).lower()}",
            "hardware access: not attempted; hardware commands generated: 0",
        ),
    )
    if args.require_identical and report["replay"]["identical"] is not True:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_replay_session(args: argparse.Namespace) -> int:
    """Strictly verify and fully recompute an immutable virtual session."""

    bootstrap = _load_virtual_bootstrap(args)
    manifest_path = _resolve_virtual_session_manifest(
        bootstrap,
        args.session_manifest,
    )
    from rocell.application import (
        BootstrapConfigurationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualSessionError,
    )
    from rocell.evidence.virtual_session import (
        VirtualSessionEvidenceError,
        replay_virtual_session,
    )
    from rocell.simulation import (
        VirtualCommissioningProfileError,
        VirtualWorkcellError,
    )

    try:
        replay = replay_virtual_session(
            bootstrap.runtime.workspace,
            manifest_path,
            runtime_path=bootstrap.runtime.source_path,
        )
    except (
        BootstrapConfigurationError,
        TrajectorySimulationError,
        VirtualCalibrationError,
        VirtualCommissioningProfileError,
        VirtualSessionError,
        VirtualSessionEvidenceError,
        VirtualWorkcellError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "VIRTUAL_SESSION_REPLAY_FAILED",
            f"Could not verify and recompute virtual-session evidence: {exc}",
            details={"manifest": str(manifest_path)},
        ) from exc

    replay_document = replay.to_dict()
    document: dict[str, Any] = {
        "schema": "rocell.replay_session_cli.v1",
        "status": replay.status,
        "identical": replay.identical,
        "bootstrap_hash": bootstrap.bootstrap_hash,
        "evidence_manifest": manifest_path.relative_to(
            bootstrap.runtime.evidence_root_path
        ).as_posix(),
        "replay": replay_document,
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"virtual replay: {replay.status}",
            f"recorded report: {replay.recorded_report_hash}",
            f"recomputed report: {replay.recomputed_report_hash}",
            "hardware access: not attempted; hardware commands generated: 0",
        ),
    )
    if args.require_identical and not replay.identical:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _plan_document(
    snapshot: BuildSnapshot, plan: ActionPlan, mode: str
) -> dict[str, Any]:
    capability = (
        Capability.DIGITAL_PLAN if mode == "plan" else Capability.SIMULATED_DRY_RUN
    )
    assessment = assess_capability(snapshot, capability)
    if not assessment.allowed:
        raise CapabilityDeniedError(capability.value, assessment.reasons)
    document: dict[str, Any] = {
        "schema": "rocell.plan_result.v1",
        "mode": mode,
        "snapshot_hash": snapshot.snapshot_hash,
        "capability": _assessment_dict(assessment),
        "execution_authorized": False,
        "action_plan": plan.to_dict(),
        "plan_hash": plan.plan_hash,
    }
    if mode == "dry-run":
        try:
            report = DryRunEngine().run(plan, snapshot)
        except DryRunError as exc:
            raise CapabilityDeniedError(
                Capability.SIMULATED_DRY_RUN.value, [str(exc)]
            ) from exc
        document["simulation"] = {
            **report.to_dict(),
            "report_hash": report.report_hash,
            "scope": "SEMANTIC_ACTIONS_ONLY_NO_GEOMETRY",
            "hardware_access": False,
            "arm_commands_generated": 0,
            "camera_frames_requested": 0,
            "geometric_path_checks_performed": False,
            "collision_checks_performed": False,
            "calibration_resolution_performed": False,
        }
    return document


def _command_plan(args: argparse.Namespace) -> int:
    snapshot = _load_snapshot(args)
    plan = _compile_plan(args.device, args.text)
    document = _plan_document(snapshot, plan, "plan")
    _emit(
        document,
        args.json,
        (
            f"semantic plan: {plan.plan_hash}",
            f"device/profile: {plan.device.value} / {plan.profile_id}",
            f"actions: {len(plan.actions)}; live execution authorized: no",
        ),
    )
    return int(ExitCode.OK)


def _command_dry_run(args: argparse.Namespace) -> int:
    snapshot = _load_snapshot(args)
    plan = _compile_plan(args.device, args.text)
    document = _plan_document(snapshot, plan, "dry-run")
    _emit(
        document,
        args.json,
        (
            f"semantic dry-run: {plan.plan_hash}",
            f"actions traced: {len(plan.actions)}",
            "hardware/geometry/collision/calibration execution: not performed",
        ),
    )
    return int(ExitCode.OK)


def _command_simulate(args: argparse.Namespace) -> int:
    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    plan = _compile_plan(args.device, args.text)
    from rocell.application import (
        SimulationContextError,
        load_simulation_context,
        run_simulation,
    )
    from rocell.application.simulate import SimulationRunError
    from rocell.motion import GeometricSimulationError

    try:
        context = load_simulation_context(workspace, manifest_path)
        report = run_simulation(context, plan)
    except SimulationRunError as exc:
        raise CapabilityDeniedError(
            Capability.SIMULATED_DRY_RUN.value, [str(exc)]
        ) from exc
    except (
        SimulationContextError,
        GeometricSimulationError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "SIMULATION_SOURCE_INVALID",
            f"Could not build the frozen simulation scenario: {exc}",
        ) from exc
    document = {**report.to_dict(), "report_hash": report.report_hash}
    geometry = report.geometry
    ik = report.ik
    vision = report.vision
    _emit(
        document,
        args.json,
        (
            f"simulation: {report.status.value}",
            (
                f"placemat alignment: {context.alignment.status}; "
                f"{len(context.alignment.checks)} checks"
            ),
            f"plan: {plan.plan_hash}; geometric checks: {len(geometry.checks)}",
            (
                "provisional IK: "
                f"{ik.converged_count}/{len(ik.samples)} sampled points converged"
            ),
            (
                "synthetic overview vision: "
                f"{vision.visible_count}/{len(vision.observations)} tags visible"
            ),
            "eye-on-arm vision and outcome verification: not yet performed",
            "physical execution/readiness: not authorized and unchanged",
        ),
    )
    return int(
        ExitCode.OK
        if report.required_simulation_checks_pass
        else ExitCode.CONFIGURATION_ERROR
    )


def _command_workcell(args: argparse.Namespace) -> int:
    """Inspect placemat/software alignment without compiling or simulating text."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import SimulationContextError, load_simulation_context

    try:
        context = load_simulation_context(workspace, manifest_path)
    except (SimulationContextError, OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "WORKCELL_ALIGNMENT_SOURCE_INVALID",
            f"Could not validate the frozen placemat: {exc}",
        ) from exc
    report = context.alignment
    document = {
        **report.to_dict(),
        "report_hash": report.report_hash,
        "simulation_bundle": {
            "bundle_id": context.bundle_lock.bundle_id,
            "lock_sha256": context.bundle_lock.source_lock_sha256,
            "physical_release_effect": "NONE",
        },
    }
    _emit(
        document,
        args.json,
        (
            f"workcell: {report.status}",
            f"revision: {report.design_revision}; checks: {len(report.checks)}",
            "physical execution/readiness: not authorized and unchanged",
        ),
    )
    return int(ExitCode.OK if report.all_checks_pass else ExitCode.CONFIGURATION_ERROR)


def _target_sweep_exit_code(
    *,
    alignment_passed: bool,
    all_accepted: bool,
    require_all: bool,
) -> int:
    """Map sweep evidence to process status without weakening alignment failures."""

    if not alignment_passed:
        return int(ExitCode.CONFIGURATION_ERROR)
    if require_all and not all_accepted:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_sweep_targets(args: argparse.Namespace) -> int:
    """Run exhaustive nominal target IK screening with zero hardware access."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        SimulationContextError,
        SweepPhase,
        load_simulation_context,
        run_target_sweep,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        devices = ("keyboard", "phone") if args.device == "all" else (args.device,)
        tool_cases: tuple[str, ...]
        if args.tool_case == "default":
            tool_cases = (context.scenario.tool_case_id,)
        elif args.tool_case == "all":
            tool_cases = tuple(case.case_id for case in context.scenario.tool_cases)
        else:
            tool_cases = (args.tool_case,)
        phases = tuple(SweepPhase) if args.phase == "all" else (SweepPhase(args.phase),)
        report = run_target_sweep(
            context,
            devices=devices,
            tool_case_ids=tool_cases,
            phases=phases,
        )
    except (SimulationContextError, OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "TARGET_SWEEP_SOURCE_INVALID",
            f"Could not run target feasibility sweep: {exc}",
        ) from exc
    document = {**report.to_dict(), "report_hash": report.report_hash}
    _emit(
        document,
        args.json,
        (
            f"target sweep: {document['status']}",
            f"target points accepted: {report.accepted_count}/{len(report.results)}",
            (
                "required park poses accepted: "
                f"{sum(result.accepted for result in report.park_results)}/"
                f"{len(report.park_results)}"
            ),
            f"devices: {', '.join(report.devices)}; tool cases: {', '.join(report.tool_cases)}",
            (
                "requested matrix only; screening has no trajectory continuity, "
                "hardware access, or command generation"
            ),
        ),
    )
    # A failed placemat contract is a configuration error, not an optional IK
    # screening gap.  ``--require-all`` remains the stricter policy for
    # otherwise valid matrices containing unreachable targets or park poses.
    return _target_sweep_exit_code(
        alignment_passed=report.alignment_passed,
        all_accepted=report.all_accepted,
        require_all=args.require_all,
    )


def _command_optimize_layout(args: argparse.Namespace) -> int:
    """Run the bounded RC03 contact/park placement study without hardware."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        ReachOptimizationError,
        SimulationContextError,
        load_simulation_context,
        run_reach_optimization,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        report = run_reach_optimization(context)
    except (
        ReachOptimizationError,
        SimulationContextError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "REACH_LAYOUT_STUDY_FAILED",
            f"Could not run the bounded RC03 reach-layout study: {exc}",
        ) from exc

    document = {**report.to_dict(), "report_hash": report.report_hash}
    best = report.ranked_candidates[0]
    _emit(
        document,
        args.json,
        (
            f"reach-layout diagnostic: {report.status}",
            (
                f"coarse hypotheses/IK solves: {report.coarse_candidate_count}/"
                f"{report.coarse_ik_solve_count}"
            ),
            (
                f"full finalists/IK solves: {len(report.finalist_ids)}/"
                f"{report.full_ik_solve_count}"
            ),
            (
                f"best contacts keyboard {best.keyboard_accepted}/{best.keyboard_total}; "
                f"phone {best.phone_accepted}/{best.phone_total}; "
                f"route parks {best.park_routes_accepted}/2"
            ),
            "scope: independent contact and park IK only; hardware authority: none",
        ),
    )
    if args.require_complete and not best.mission_complete:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_optimize_park(args: argparse.Namespace) -> int:
    """Find a geometry-screened park overlay without changing the build."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        ParkOptimizationError,
        SimulationContextError,
        load_simulation_context,
        run_park_optimization,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        report = run_park_optimization(context)
    except (
        ParkOptimizationError,
        SimulationContextError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "PARK_POSE_STUDY_FAILED",
            f"Could not run the bounded Freeze005 park-pose study: {exc}",
        ) from exc

    document = {**report.to_dict(), "report_hash": report.report_hash}
    best = report.best_candidate
    if best is None:
        best_summary = "best park: none"
    else:
        point = best.geometry.point_board
        best_summary = (
            f"best park: {best.geometry.candidate_id} at "
            f"({point.x}, {point.y}, {point.z}) mm; "
            f"routes accepted: {best.accepted_route_count}/2"
        )
    _emit(
        document,
        args.json,
        (
            f"park-pose diagnostic: {report.status}",
            best_summary,
            (
                f"ranked candidates/IK solves: {len(report.ranked_candidates)}/"
                f"{report.actual_ik_solve_count}"
            ),
            (
                "scope: independent geometry-filtered park IK only; "
                "canonical context and hardware authority: unchanged/none"
            ),
        ),
    )
    if args.require_both_routes and (best is None or not best.all_routes_accepted):
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_study_layout_hypotheses(args: argparse.Namespace) -> int:
    """Run the wider staged layout sensitivity study without hardware."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        PrehardwareLayoutStudyError,
        SimulationContextError,
        load_simulation_context,
        run_prehardware_layout_study,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        report = run_prehardware_layout_study(context)
    except (
        PrehardwareLayoutStudyError,
        SimulationContextError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "PREHARDWARE_LAYOUT_STUDY_FAILED",
            f"Could not run the bounded prehardware layout study: {exc}",
        ) from exc

    document = {**report.to_dict(), "report_hash": report.report_hash}
    regression_screens = (*report.coarse_screens, *report.refinement_screens)
    _emit(
        document,
        args.json,
        (
            f"prehardware layout diagnostic: {report.status}",
            (
                "coarse/refinement hypotheses: "
                f"{len(report.coarse_screens)}/{len(report.refinement_screens)}; "
                f"regression passes: "
                f"{sum(row.regression_passed for row in regression_screens)}"
            ),
            (
                "screened-shortlist 46-key + 29-phone contact screens/promotions: "
                f"{len(report.full_catalog_screens)}/"
                f"{len(report.promoted_candidates)}"
            ),
            (
                f"layout/park-source IK solves: "
                f"{report.actual_layout_ik_solve_count}/"
                f"{report.park_optimizer_actual_ik_solve_count}"
            ),
            (
                "scope: bounded unmeasured hypotheses and independent poses; "
                "full routes, collision, and hardware authority: not claimed/none"
            ),
        ),
    )
    if args.require_promotable and not report.promoted_candidates:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_stress_placemat_geometry(args: argparse.Namespace) -> int:
    """Expose assumed placemat/device error before hardware measurements exist."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        PlacematUncertaintyBounds,
        PlacematUncertaintyError,
        SimulationContextError,
        load_simulation_context,
        run_placemat_uncertainty_simulation,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        bounds = (
            PlacematUncertaintyBounds.zero()
            if args.zero_bounds
            else PlacematUncertaintyBounds()
        )
        report = run_placemat_uncertainty_simulation(context, bounds)
    except (
        PlacematUncertaintyError,
        SimulationContextError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "PLACEMAT_GEOMETRY_SENSITIVITY_FAILED",
            f"Could not run the placemat geometry sensitivity study: {exc}",
            details={"hardware_accessed": False},
        ) from exc

    keyboard = tuple(target for target in report.targets if target.device == "keyboard")
    phone = tuple(target for target in report.targets if target.device == "phone")
    keyboard_gap_count = sum(target.sensitivity_gap_observed for target in keyboard)
    phone_gap_count = sum(target.sensitivity_gap_observed for target in phone)
    minimum_keyboard_margin = min(target.worst_xy_margin_mm for target in keyboard)
    minimum_phone_margin = min(target.worst_xy_margin_mm for target in phone)
    document = report.to_dict()
    _emit(
        document,
        args.json,
        (
            f"placemat geometry sensitivity: {report.status}",
            (
                f"targets/cases/observations: {len(report.targets)}/"
                f"{len(report.cases)}/{len(report.targets) * len(report.cases)}"
            ),
            (
                "sampled targets with XY sensitivity gaps, keyboard/phone: "
                f"{keyboard_gap_count}/{phone_gap_count}"
            ),
            (
                "worst sampled XY safe-region margin, keyboard/phone: "
                f"{minimum_keyboard_margin:.4f}/{minimum_phone_margin:.4f} mm"
            ),
            (
                "inputs: frozen nominal RC03 geometry plus assumed unmeasured "
                "bounds; these are not tolerances or physical acceptance data"
            ),
            (
                "selected vision binding: static overhead Arducam B0477; "
                "received identity, installation, and calibration remain unverified"
            ),
            "hardware access/commands/physical authority: 0/0/none",
            f"report SHA-256: {report.report_sha256}",
        ),
    )
    if args.require_no_gaps and report.sensitivity_gap_count:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_screen_mission_routes(args: argparse.Namespace) -> int:
    """Screen all locked targets as independent park-to-park routes."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        MissionRouteCoverageError,
        ParkOptimizationError,
        PrehardwareLayoutStudyError,
        SimulationContextError,
        TrajectorySimulationError,
        default_reach_study_inputs,
        load_simulation_context,
        run_mission_route_coverage,
        run_park_optimization,
        run_prehardware_layout_study,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        layout_report = None
        park_report = None
        if args.from_layout_study_rank is not None:
            layout_report = run_prehardware_layout_study(context)
            rank_index = args.from_layout_study_rank - 1
            if rank_index >= len(layout_report.promoted_candidates):
                raise MissionRouteCoverageError(
                    "requested prehardware layout rank is not available; only "
                    f"{len(layout_report.promoted_candidates)} candidates were "
                    "eligible for full-route screening"
                )
            promotion = layout_report.promoted_candidates[rank_index]
            if promotion.rank != args.from_layout_study_rank:
                raise MissionRouteCoverageError(
                    "prehardware promotion rank does not match its ordered position"
                )
            study_input = promotion.study_input
            park = promotion.full_catalog_screen.selected_park_probe
            park_xy = (park.point_board.x, park.point_board.y)
            selection: dict[str, Any] = {
                "source": "PROMOTED_PREHARDWARE_LAYOUT_STUDY",
                "rank": promotion.rank,
                "layout_report_hash": layout_report.report_hash,
                "study_input_id": study_input.study_input_id,
                "eligible_for_full_route_screen": True,
                "park_probe_id": park.park_id,
                "park_xy_board_mm": list(park_xy),
                "canonical_context_modified": False,
            }
        else:
            documented = _DOCUMENTED_REACH_SELECTIONS.get(context.snapshot.manifest_id)
            if documented is None:
                raise MissionRouteCoverageError(
                    "no documented placement is available for this freeze"
                )
            selected_id = str(documented["study_input_id"])
            matches = tuple(
                study
                for study in default_reach_study_inputs(context)
                if study.study_input_id == selected_id
            )
            if len(matches) != 1:
                raise MissionRouteCoverageError(
                    "documented placement did not resolve exactly once"
                )
            study_input = matches[0]
            park_report = run_park_optimization(context)
            best_park = park_report.best_candidate
            if best_park is None or not best_park.all_routes_accepted:
                raise MissionRouteCoverageError(
                    "bounded park source did not produce a both-route probe"
                )
            if (
                park_report.selected_study_input.study_input_id
                != study_input.study_input_id
            ):
                raise MissionRouteCoverageError(
                    "documented placement and bounded park source identities differ"
                )
            point = best_park.geometry.point_board
            park_xy = (point.x, point.y)
            selection = {
                "source": "DOCUMENTED_FREEZE_PLACEMENT_AND_BOUNDED_PARK",
                **dict(documented),
                "study_input_id": study_input.study_input_id,
                "park_report_hash": park_report.report_hash,
                "park_candidate_id": best_park.geometry.candidate_id,
                "park_xy_board_mm": list(park_xy),
                "canonical_context_modified": False,
            }
        coverage = run_mission_route_coverage(
            context,
            study_input,
            park_xy,
        )
        if coverage.study_input != study_input:
            raise MissionRouteCoverageError(
                "mission coverage returned a different layout input than selected"
            )
        if coverage.park_xy_board_mm != park_xy:
            raise MissionRouteCoverageError(
                "mission coverage returned a different park than selected"
            )
    except (
        MissionRouteCoverageError,
        ParkOptimizationError,
        PrehardwareLayoutStudyError,
        SimulationContextError,
        TrajectorySimulationError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "MISSION_ROUTE_COVERAGE_FAILED",
            f"Could not run complete mission-route coverage: {exc}",
        ) from exc

    coverage_document = {**coverage.to_dict(), "report_hash": coverage.report_hash}
    document: dict[str, Any] = {
        "schema": "rocell.mission_route_coverage_cli.v1",
        "status": coverage.status,
        "simulation_only": True,
        "execution_authorized": False,
        "hardware_accessed": False,
        "hardware_commands_generated": 0,
        "contact_authorized": False,
        "physical_release_effect": "NONE",
        "selection": selection,
        "coverage": coverage_document,
    }
    document["report_hash"] = _canonical_report_hash(document)
    device_summary = coverage_document["device_summary"]
    _emit(
        document,
        args.json,
        (
            f"mission-route coverage: {coverage.status}",
            (
                "independent routes accepted: "
                f"{sum(route.accepted for route in coverage.routes)}/"
                f"{len(coverage.routes)}"
            ),
            (
                "keyboard/phone accepted: "
                f"{device_summary['keyboard']['accepted_route_count']}/46; "
                f"{device_summary['phone']['accepted_route_count']}/29"
            ),
            (
                f"IK solves/Jacobian FK evaluations: {coverage.total_ik_solves}/"
                f"{coverage.total_task_jacobian_fk_evaluations}"
            ),
            (
                "scope: one independent park-to-target-to-park route per target; "
                "arbitrary sequences, collision, and hardware authority: not claimed/none"
            ),
        ),
    )
    if args.require_all and not coverage.all_routes_accepted:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_screen_adaptive_mission_routes(args: argparse.Namespace) -> int:
    """Run every target through a fresh adaptive camera/contact session."""

    workspace = _find_workspace(args.workspace)
    from rocell.application import (
        AdaptiveMissionCoverageError,
        AdaptiveMissionCoveragePolicy,
        run_adaptive_mission_coverage,
    )

    try:
        policy = AdaptiveMissionCoveragePolicy(
            orchestration_chunk_size=args.chunk_size,
        )
        report = run_adaptive_mission_coverage(
            workspace,
            policy=policy,
            runtime_path=args.runtime,
        )
    except (AdaptiveMissionCoverageError, OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "ADAPTIVE_MISSION_COVERAGE_FAILED",
            f"Could not run complete adaptive mission coverage: {exc}",
            details={"hardware_accessed": False},
        ) from exc

    report_document = report.to_dict()
    summary_value = report_document.get("summary")
    if not isinstance(summary_value, Mapping):
        raise ConfigurationError(
            "ADAPTIVE_MISSION_COVERAGE_REPORT_INVALID",
            "Adaptive mission coverage returned no summary object",
        )
    summary: Mapping[str, Any] = summary_value
    failed_route_observations: list[str] = []
    chunk_values = report_document.get("chunks")
    if isinstance(chunk_values, list):
        for chunk_value in chunk_values:
            if not isinstance(chunk_value, Mapping):
                continue
            route_values = chunk_value.get("routes")
            if not isinstance(route_values, list):
                continue
            for route_value in route_values:
                if (
                    not isinstance(route_value, Mapping)
                    or route_value.get("accepted") is not False
                ):
                    continue
                target_id = route_value.get("target_id")
                device = route_value.get("device")
                fault_reason = route_value.get("fault_reason")
                child_status = route_value.get("child_status")
                if isinstance(target_id, str) and target_id:
                    target_label = (
                        f"{device}:{target_id}"
                        if isinstance(device, str) and device
                        else target_id
                    )
                    failed_route_observations.append(
                        f"{target_label} [status={child_status}, fault={fault_reason}]"
                    )
    rejected_count = summary.get("rejected_route_count")
    failed_route_text = (
        ", ".join(
            observation.split(" [", maxsplit=1)[0]
            for observation in failed_route_observations
        )
        if failed_route_observations
        else "none" if rejected_count == 0 else "not exposed by report"
    )
    document: dict[str, Any] = {
        "schema": "rocell.adaptive_mission_coverage_cli.v1",
        "status": report.status,
        "all_routes_accepted": report.all_routes_accepted,
        "adaptive_mission_coverage": report_document,
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "execution_authorized": False,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"adaptive mission coverage: {report.status}",
            (
                "adaptive target sessions accepted: "
                f"{summary['accepted_route_count']}/{summary['route_count']}"
            ),
            (
                "executions/captures/contacts: "
                f"{summary['execution_count']}/{summary['capture_count']}/"
                f"{summary['contact_count']}"
            ),
            f"failed routes: {failed_route_text}",
            *(f"  {observation}" for observation in failed_route_observations),
            "scope: synthetic nominal board truth; physical readiness and authority: none",
            f"adaptive coverage report hash: {report.report_hash}",
        ),
    )
    if args.require_all and not report.all_routes_accepted:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_stress_adaptive_session(args: argparse.Namespace) -> int:
    """Run signed, boundary, and seeded arm-camera perturbation cases."""

    workspace = _find_workspace(args.workspace)
    from rocell.application import (
        AdaptivePerturbationCampaignError,
        AdaptivePerturbationPolicy,
        run_adaptive_perturbation_campaign,
    )

    try:
        policy = AdaptivePerturbationPolicy(
            seed=args.seed,
            generated_case_count=args.generated_cases,
        )
        report = run_adaptive_perturbation_campaign(
            workspace,
            policy=policy,
            runtime_path=args.runtime,
        )
    except (
        AdaptivePerturbationCampaignError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "ADAPTIVE_PERTURBATION_CAMPAIGN_FAILED",
            f"Could not run the adaptive perturbation campaign: {exc}",
            details={"seed": args.seed, "hardware_accessed": False},
        ) from exc

    report_document = report.to_dict()
    summary_value = report_document.get("summary")
    if not isinstance(summary_value, Mapping):
        raise ConfigurationError(
            "ADAPTIVE_PERTURBATION_REPORT_INVALID",
            "Adaptive perturbation campaign returned no summary object",
        )
    summary: Mapping[str, Any] = summary_value
    # Read diagnostic identifiers from the public report document instead of
    # coupling the CLI to the concrete in-process report implementation.  This
    # keeps alternate/report-replay implementations usable at this boundary.
    result_values = report_document.get("results")
    failed_case_ids: tuple[str, ...] = ()
    failed_case_observations: tuple[str, ...] = ()
    if isinstance(result_values, list):
        collected_ids: list[str] = []
        collected_observations: list[str] = []
        for result_value in result_values:
            if (
                not isinstance(result_value, Mapping)
                or result_value.get("passed") is not False
            ):
                continue
            case_value = result_value.get("case")
            if not isinstance(case_value, Mapping):
                continue
            case_id = case_value.get("case_id")
            if isinstance(case_id, str) and case_id:
                collected_ids.append(case_id)
                decision_value = result_value.get("decision_statuses")
                decisions = (
                    ">".join(
                        status for status in decision_value if isinstance(status, str)
                    )
                    if isinstance(decision_value, list)
                    else "unknown"
                )
                fault_value = result_value.get("fault_reason")
                fault = fault_value if isinstance(fault_value, str) else "none"
                completed = result_value.get("pipeline_completed")
                collected_observations.append(
                    f"{case_id} [decisions={decisions or 'none'}, "
                    f"completed={str(completed).lower()}, fault={fault}]"
                )
        failed_case_ids = tuple(collected_ids)
        failed_case_observations = tuple(collected_observations)
    failed_count = summary.get("failed_count")
    failed_case_text = (
        ", ".join(failed_case_ids)
        if failed_case_ids
        else "none" if failed_count == 0 else "not exposed by report"
    )
    document: dict[str, Any] = {
        "schema": "rocell.adaptive_perturbation_campaign_cli.v1",
        "status": report.status,
        "campaign_passed": report.campaign_passed,
        "seed": args.seed,
        "adaptive_perturbation_campaign": report_document,
        "authority": {
            "simulation_only": True,
            "hardware_accessed": False,
            "hardware_commands_generated": 0,
            "execution_authorized": False,
            "live_motion_authorized": False,
            "physical_contact_authorized": False,
            "physical_release_effect": "NONE",
        },
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"adaptive perturbation campaign: {report.status}",
            (
                f"cases passed: {summary['passed_count']}/"
                f"{summary['case_count']}; expected safe rejections: "
                f"{summary['expected_rejection_count']}"
            ),
            (
                f"seed: {args.seed}; executions/captures: "
                f"{summary['total_executions']}/{summary['total_captures']}"
            ),
            f"failed cases: {failed_case_text}",
            *(f"  {observation}" for observation in failed_case_observations),
            "hidden transforms are hash-bound but not serialized; physical authority: none",
            f"perturbation report hash: {report.report_hash}",
        ),
    )
    if args.require_pass and not report.campaign_passed:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_collision_status(args: argparse.Namespace) -> int:
    """Report exact current full-body collision-model gaps without motion."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        SimulationContextError,
        assess_current_collision_readiness,
        load_simulation_context,
    )
    from rocell.simulation import CollisionContractError

    try:
        context = load_simulation_context(workspace, manifest_path)
        report = assess_current_collision_readiness(context)
    except (
        CollisionContractError,
        SimulationContextError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "COLLISION_READINESS_AUDIT_FAILED",
            f"Could not assess current collision-model readiness: {exc}",
        ) from exc

    document = {**report.to_dict(), "report_hash": report.report_hash}
    readiness_summary = (
        "current full-body pose/sweep queries may proceed only as "
        "simulation diagnostics"
        if report.geometry_audit.diagnostic_ready
        else "current full-body pose/sweep queries remain blocked"
    )
    _emit(
        document,
        args.json,
        (
            f"collision-model readiness: {report.status}",
            (
                "required/bound bodies: "
                f"{report.geometry_audit.required_body_count}/"
                f"{report.geometry_audit.bound_body_count}"
            ),
            (
                f"missing/unknown complete bodies: "
                f"{len(report.missing_required_body_ids)}/"
                f"{len(report.unknown_required_body_ids)}"
            ),
            (
                "scope: exact required-body contract/source audit only; no "
                "collision pose or sweep query was run"
            ),
            readiness_summary,
            "hardware motion, contact, and physical-gate authority: none",
        ),
    )
    if args.require_diagnostic_ready and not report.geometry_audit.diagnostic_ready:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _resolve_reach_study_input(
    context: Any,
    *,
    placement_rank: int,
    refresh_placement_ranking: bool,
    study_input_id: str | None,
) -> tuple[Any, dict[str, Any]]:
    """Resolve one explicit placement overlay without changing the context."""

    from rocell.application import (
        default_reach_study_inputs,
        TrajectorySimulationError,
        run_reach_optimization,
    )

    selection: dict[str, Any]
    if refresh_placement_ranking:
        reach_report = run_reach_optimization(context)
        rank_index = placement_rank - 1
        if rank_index >= len(reach_report.ranked_candidates):
            raise TrajectorySimulationError(
                f"placement rank {placement_rank} is unavailable"
            )
        ranked = reach_report.ranked_candidates[rank_index]
        selected_id = ranked.study_input_id
        candidate_inputs = tuple(
            evaluation.study_input for evaluation in reach_report.full_evaluations
        )
        selection = {
            "source": "FRESH_BOUNDED_REACH_OPTIMIZATION",
            "rank": ranked.rank,
            "reach_report_hash": reach_report.report_hash,
            "reach_status": reach_report.status,
            "reach_mission_complete": ranked.mission_complete,
            "park_id_from_reach_study": ranked.park_id,
        }
    else:
        if placement_rank != 1:
            raise UsageError(
                "PLACEMENT_RANK_REQUIRES_REFRESH",
                "--placement-rank other than 1 requires --refresh-placement-ranking",
            )
        documented = _DOCUMENTED_REACH_SELECTIONS.get(context.snapshot.manifest_id)
        if study_input_id is not None:
            selected_id = study_input_id
            selection = {
                "source": "EXPLICIT_DEFAULT_GRID_STUDY_INPUT_ID",
                "rank": None,
                "reach_report_hash": None,
                "reach_status": None,
                "reach_mission_complete": False,
                "park_id_from_reach_study": None,
            }
        elif documented is not None:
            selected_id = str(documented["study_input_id"])
            selection = {
                "source": "DOCUMENTED_FREEZE_BOUND_REACH_RESULT",
                **dict(documented),
                "park_id_from_reach_study": "park-00",
            }
        else:
            raise UsageError(
                "PLACEMENT_SELECTION_REQUIRED",
                "No documented placement exists for this freeze; provide "
                "--study-input-id or --refresh-placement-ranking",
            )
        candidate_inputs = default_reach_study_inputs(context)

    matching_inputs = tuple(
        study for study in candidate_inputs if study.study_input_id == selected_id
    )
    if len(matching_inputs) != 1:
        raise TrajectorySimulationError(
            f"study input {selected_id!r} does not resolve exactly once"
        )
    selection["study_input_id"] = selected_id
    return matching_inputs[0], selection


def _command_simulate_trajectory(args: argparse.Namespace) -> int:
    """Run ranked-placement discrete waypoint screening without hardware."""

    if (args.park_x_mm is None) != (args.park_y_mm is None):
        raise UsageError(
            "TRAJECTORY_PARK_PAIR_REQUIRED",
            "--park-x-mm and --park-y-mm must be supplied together",
        )
    if args.use_optimized_park and args.park_x_mm is not None:
        raise UsageError(
            "TRAJECTORY_PARK_SOURCE_CONFLICT",
            "--use-optimized-park cannot be combined with manual park coordinates",
        )
    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    plan = _compile_plan(args.device, args.text)
    from rocell.application import (
        ParkOptimizationError,
        ReachOptimizationError,
        SimulationContextError,
        TrajectorySimulationError,
        TrajectorySimulationPolicy,
        load_simulation_context,
        run_park_optimization,
        run_trajectory_simulation,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        study_input, selection = _resolve_reach_study_input(
            context,
            placement_rank=args.placement_rank,
            refresh_placement_ranking=args.refresh_placement_ranking,
            study_input_id=args.study_input_id,
        )
        study_input_id = study_input.study_input_id
        park_report = None
        park_selection: dict[str, Any]
        if args.use_optimized_park:
            park_report = run_park_optimization(context)
            best_park = park_report.best_candidate
            if best_park is None or not best_park.all_routes_accepted:
                raise TrajectorySimulationError(
                    "park optimizer did not produce a candidate accepted for both routes"
                )
            if park_report.selected_study_input.study_input_id != study_input_id:
                raise TrajectorySimulationError(
                    "optimized park and trajectory placement study identities differ"
                )
            point = best_park.geometry.point_board
            park_xy = (point.x, point.y)
            park_selection = {
                "source": "FREEZE_BOUND_BOUNDED_PARK_OPTIMIZATION",
                "automatic_overlay_used": True,
                "manual_override_used": False,
                "park_report_hash": park_report.report_hash,
                "park_status": park_report.status,
                "candidate_id": best_park.geometry.candidate_id,
                "point_board_mm": [point.x, point.y, point.z],
                "accepted_route_count": best_park.accepted_route_count,
                "all_required_route_parks_accepted": (best_park.all_routes_accepted),
                "minimum_normalized_arm_joint_margin": (
                    best_park.minimum_normalized_arm_joint_margin
                ),
                "canonical_context_modified": False,
            }
        elif args.park_x_mm is not None:
            park_xy = (float(args.park_x_mm), float(args.park_y_mm))
            park_selection = {
                "source": "MANUAL_CLI_OVERLAY",
                "automatic_overlay_used": False,
                "manual_override_used": True,
                "point_board_xy_mm": list(park_xy),
                "independent_park_screening_verified": False,
                "canonical_context_modified": False,
            }
        else:
            park_xy = None
            park_selection = {
                "source": "SELECTED_REACH_STUDY_NOMINAL_PARK",
                "automatic_overlay_used": False,
                "manual_override_used": False,
                "canonical_context_modified": False,
            }
        policy = TrajectorySimulationPolicy(
            maximum_cartesian_step_mm=args.maximum_cartesian_step_mm,
            maximum_joint_step_rad=args.maximum_joint_step_rad,
            minimum_normalized_arm_joint_margin=args.minimum_arm_joint_margin,
            maximum_refinement_rounds=args.maximum_refinement_rounds,
            maximum_route_targets=args.maximum_route_targets,
            park_xy_board_mm=park_xy,
        )
        trajectory = run_trajectory_simulation(
            context,
            plan,
            study_input,
            policy,
        )
    except (
        ParkOptimizationError,
        ReachOptimizationError,
        SimulationContextError,
        TrajectorySimulationError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise ConfigurationError(
            "TRAJECTORY_STUDY_FAILED",
            f"Could not run the bounded discrete waypoint route study: {exc}",
        ) from exc

    trajectory_document = {
        **trajectory.to_dict(),
        "report_hash": trajectory.report_hash,
    }
    document: dict[str, Any] = {
        "schema": "rocell.rank_selected_trajectory_study.v1",
        "status": trajectory.status,
        "simulation_only": True,
        "execution_authorized": False,
        "hardware_accessed": False,
        "hardware_commands_generated": 0,
        "physical_release_effect": "NONE",
        "placement_selection": {
            **selection,
            "park_override_used": park_xy is not None,
        },
        "park_selection": park_selection,
        "trajectory": trajectory_document,
    }
    document["report_hash"] = _canonical_report_hash(document)
    final_round = trajectory.final_round
    accepted = 0 if final_round is None else len(final_round.joint_results)
    total = 0 if final_round is None else len(final_round.waypoints)
    _emit(
        document,
        args.json,
        (
            f"trajectory diagnostic: {trajectory.status}",
            (
                f"placement source/input: {selection['source']}/"
                f"{study_input_id}; reach complete: "
                f"{selection['reach_mission_complete']}"
            ),
            f"park source: {park_selection['source']}",
            (
                f"final evaluated/required waypoints: {accepted}/{total}; "
                f"IK solves: {trajectory.total_ik_solves}"
            ),
            f"termination: {trajectory.termination_reason}",
            (
                "scope: nominal tool-tip centreline and sequential IK only; "
                "link/self/camera/cable collision and hardware authority: none"
            ),
        ),
    )
    if args.require_pass and (
        final_round is None or not final_round.all_waypoints_accepted
    ):
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_calibration_status(args: argparse.Namespace) -> int:
    """Report ordered missing/stale calibration evidence without capturing data."""

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    from rocell.application import (
        SimulationContextError,
        assess_calibration_status,
        load_simulation_context,
    )

    try:
        context = load_simulation_context(workspace, manifest_path)
        report = assess_calibration_status(context, args.device)
    except (SimulationContextError, OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "CALIBRATION_STATUS_SOURCE_INVALID",
            f"Could not assess calibration readiness: {exc}",
        ) from exc
    document = {**report.to_dict(), "report_hash": report.report_hash}
    valid_count = sum(item.valid for item in report.assessments)
    _emit(
        document,
        args.json,
        (
            f"calibration ({report.device}): {document['status']}",
            f"valid: {valid_count}/{len(report.assessments)}",
            "read-only assessment; no camera, arm, or calibration capture was attempted",
        ),
    )
    if args.require_ready and not report.all_valid:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_solve_eye_on_arm_offline(args: argparse.Namespace) -> int:
    """Solve one pinned JSON dataset without importing any hardware adapter."""

    from rocell.calibration import (
        EyeOnArmDatasetError,
        EyeOnArmSolveError,
        EyeOnArmSolverUnavailable,
        load_eye_on_arm_dataset,
        solve_eye_on_arm,
    )

    try:
        dataset = load_eye_on_arm_dataset(
            args.dataset,
            expected_file_sha256=args.expected_sha256,
        )
        report = solve_eye_on_arm(
            dataset,
        )
    except (
        EyeOnArmDatasetError,
        EyeOnArmSolveError,
        EyeOnArmSolverUnavailable,
        OSError,
    ) as exc:
        raise ConfigurationError(
            "EYE_ON_ARM_OFFLINE_SOLVE_FAILED",
            f"Could not solve the offline eye-on-arm dataset: {exc}",
            details={"dataset": str(args.dataset)},
        ) from exc
    document = {
        **report.to_dict(),
        "report_hash": report.report_hash,
        "hardware_access": False,
        "arm_commands_generated": 0,
        "camera_frames_requested": 0,
        "artifact_created": False,
        "artifact_installed": False,
    }
    _emit(
        document,
        args.json,
        (
            f"eye-on-arm offline solve: {report.status}",
            f"dataset: {report.dataset_id}; report: {report.report_hash}",
            (
                "training/held-out poses: "
                f"{report.training_summary.count}/{report.held_out_summary.count}"
            ),
            "hardware access, artifact installation, and physical authority: none",
        ),
    )
    if args.require_diagnostic_pass and not report.diagnostic_pass:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _load_verified_eye_on_arm_inputs(args: argparse.Namespace) -> tuple[Any, Any, Any]:
    """Load dataset/evidence against the canonical active software context."""

    from rocell.application import load_simulation_context
    from rocell.calibration import (
        EyeOnArmEvidenceError,
        load_eye_on_arm_capture_evidence,
        load_eye_on_arm_dataset,
    )

    workspace = _find_workspace(args.workspace)
    manifest_path = _manifest_path(workspace, args.manifest)
    context = load_simulation_context(workspace, manifest_path)
    dataset = load_eye_on_arm_dataset(
        args.dataset,
        expected_file_sha256=args.dataset_sha256,
    )
    evidence = load_eye_on_arm_capture_evidence(
        args.evidence,
        expected_file_sha256=args.evidence_sha256,
    )
    if evidence.manifest_id != context.snapshot.manifest_id:
        raise EyeOnArmEvidenceError(
            "Capture evidence manifest differs from the verified active context"
        )
    if evidence.active_build_id != context.snapshot.active_build_id:
        raise EyeOnArmEvidenceError(
            "Capture evidence build differs from the verified active context"
        )
    if evidence.kinematic_model_sha256 != context.scenario.model_sha256:
        raise EyeOnArmEvidenceError(
            "Capture evidence model differs from the verified simulation bundle"
        )
    return context, dataset, evidence


def _command_verify_eye_on_arm_fk_offline(args: argparse.Namespace) -> int:
    """Recompute carrier poses from raw feedback without touching hardware."""

    from rocell.application import SimulationContextError
    from rocell.calibration import (
        EyeOnArmDatasetError,
        EyeOnArmEvidenceError,
        verify_eye_on_arm_fk,
    )

    try:
        context, dataset, evidence = _load_verified_eye_on_arm_inputs(args)
        report = verify_eye_on_arm_fk(
            dataset,
            evidence,
            context.scenario.model_path,
        )
    except (
        EyeOnArmDatasetError,
        EyeOnArmEvidenceError,
        SimulationContextError,
        OSError,
    ) as exc:
        raise ConfigurationError(
            "EYE_ON_ARM_OFFLINE_FK_VERIFICATION_FAILED",
            f"Could not verify offline eye-on-arm FK evidence: {exc}",
            details={
                "dataset": str(args.dataset),
                "evidence": str(args.evidence),
            },
        ) from exc

    fk_document = {
        **report.to_dict(),
        "report_hash": report.report_hash,
    }
    document: dict[str, Any] = {
        "schema": "rocell.eye_on_arm_fk_offline_cli.v1",
        "status": report.status,
        "verified_context": {
            "manifest_id": context.snapshot.manifest_id,
            "active_build_id": context.snapshot.active_build_id,
            "snapshot_hash": context.snapshot.snapshot_hash,
            "simulation_bundle_id": context.bundle_lock.bundle_id,
            "model_sha256": context.scenario.model_sha256,
            "identity_match_checked": True,
        },
        "verified_input_file_sha256": {
            "dataset": args.dataset_sha256,
            "evidence": args.evidence_sha256,
        },
        "fk_verification": fk_document,
        "hardware_access": False,
        "arm_commands_generated": 0,
        "camera_frames_requested": 0,
        "artifact_created": False,
        "artifact_installed": False,
        "commissioning_assessment_performed": False,
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"eye-on-arm offline FK verification: {report.status}",
            (
                f"dataset/evidence: {report.dataset_id}/{report.evidence_id}; "
                f"samples: {len(report.samples)}"
            ),
            f"pinned model: {report.kinematic_model_sha256}",
            "hardware access, artifact installation, commissioning, and motion authority: none",
        ),
    )
    if args.require_pass and not report.all_passed:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_verify_eye_on_arm_capture_bundle_offline(
    args: argparse.Namespace,
) -> int:
    """Verify hash-pinned capture bytes and stop-and-look brackets offline."""

    from rocell.application import SimulationContextError
    from rocell.calibration import (
        EyeOnArmCaptureBundleError,
        EyeOnArmDatasetError,
        EyeOnArmEvidenceError,
        load_eye_on_arm_capture_bundle,
        verify_eye_on_arm_capture_bundle,
    )

    try:
        context, dataset, evidence = _load_verified_eye_on_arm_inputs(args)
        bundle = load_eye_on_arm_capture_bundle(
            args.bundle,
            expected_file_sha256=args.bundle_sha256,
        )
        report = verify_eye_on_arm_capture_bundle(dataset, evidence, bundle)
    except (
        EyeOnArmCaptureBundleError,
        EyeOnArmDatasetError,
        EyeOnArmEvidenceError,
        SimulationContextError,
        OSError,
    ) as exc:
        raise ConfigurationError(
            "EYE_ON_ARM_CAPTURE_BUNDLE_VERIFICATION_FAILED",
            f"Could not verify the offline eye-on-arm capture bundle: {exc}",
            details={
                "dataset": str(args.dataset),
                "evidence": str(args.evidence),
                "bundle": str(args.bundle),
            },
        ) from exc

    verification_document = {
        **report.to_dict(),
        "report_hash": report.report_hash,
    }
    document: dict[str, Any] = {
        "schema": "rocell.eye_on_arm_capture_bundle_offline_cli.v1",
        "status": report.status,
        "verified_context": {
            "manifest_id": context.snapshot.manifest_id,
            "active_build_id": context.snapshot.active_build_id,
            "snapshot_hash": context.snapshot.snapshot_hash,
            "simulation_bundle_id": context.bundle_lock.bundle_id,
            "model_sha256": context.scenario.model_sha256,
            "identity_match_checked": True,
        },
        "verified_input_file_sha256": {
            "dataset": args.dataset_sha256,
            "evidence": args.evidence_sha256,
            "capture_bundle": args.bundle_sha256,
        },
        "capture_bundle_verification": verification_document,
        "hardware_access": False,
        "arm_commands_generated": 0,
        "camera_frames_requested": 0,
        "artifact_created": False,
        "artifact_installed": False,
        "commissioning_assessment_performed": False,
        "physical_timing_qualified": False,
    }
    document["report_hash"] = _canonical_report_hash(document)
    _emit(
        document,
        args.json,
        (
            f"eye-on-arm capture-bundle verification: {report.status}",
            f"bundle: {report.bundle_id}; samples: {len(report.samples)}",
            (
                "structural byte/bracket check only; physical timing remains "
                "unqualified"
            ),
            "hardware access, commissioning, artifact installation, and motion authority: none",
        ),
    )
    if args.require_pass and not report.structural_passed:
        return int(ExitCode.CONFIGURATION_ERROR)
    return int(ExitCode.OK)


def _command_arm_feedback(args: argparse.Namespace) -> int:
    snapshot = _load_snapshot(args)
    assessment = assess_capability(snapshot, Capability.ARM_FEEDBACK)
    if not assessment.allowed:
        # This branch is deliberately before importing rocell.arm, constructing
        # SerialTransport, importing pyserial, or touching the requested port.
        raise CapabilityDeniedError(Capability.ARM_FEEDBACK.value, assessment.reasons)

    # A future build may release feedback while motion remains blocked.  Even
    # then, direct ``python -m rocell`` use must not bypass the checkout-bound
    # environment required by physical onboarding.  This assessment reads
    # software/configuration metadata only and imports no device backend.
    from rocell.application.physical_host_readiness import (
        PhysicalHostReadinessError,
        assess_physical_host_readiness,
    )

    workspace = _find_workspace(args.workspace)
    try:
        host = assess_physical_host_readiness(workspace, snapshot)
    except (OSError, TypeError, ValueError, PhysicalHostReadinessError) as exc:
        raise ConfigurationError(
            "PHYSICAL_HOST_READINESS_INVALID",
            f"Could not validate the feedback-only environment: {exc}",
        ) from exc
    if not (
        host.device_access_environment_ready and host.arm_diagnostics_dependencies_ready
    ):
        raise CapabilityDeniedError(
            Capability.ARM_FEEDBACK.value,
            [
                blocker
                for blocker in host.blockers
                if blocker != "SUPERSEDING_STATIC_CAMERA_FREEZE_NOT_PROMOTED"
            ]
            or ["CONTROLLED_ARM_DIAGNOSTICS_ENVIRONMENT_NOT_READY"],
        )

    from rocell.arm import (
        ArmConnectionConfigurationError,
        FeedbackError,
        FeedbackNotPermittedError,
        RoArmM3,
        SerialTransport,
        TransportError,
        load_arm_connection_profile,
    )
    from rocell.safety import AuthorizationError, SafetySupervisor

    try:
        connection_profile = load_arm_connection_profile(workspace)
        connection_profile.require_commissioned_port(args.port)
    except ArmConnectionConfigurationError as exc:
        raise ConfigurationError(
            "ARM_CONNECTION_NOT_COMMISSIONED",
            str(exc),
        ) from exc
    if args.timeout is not None and args.timeout != connection_profile.read_timeout_s:
        raise UsageError(
            "ARM_TIMEOUT_NOT_CONTROLLED",
            "Requested timeout must match the commissioned arm connection profile",
        )

    # Reassess and mint a one-use T=105 capability immediately before creating
    # the live transport. This keeps build-power authorization at the final
    # outbound boundary rather than trusting the CLI's earlier display gate.
    try:
        feedback_permit = SafetySupervisor(snapshot).authorize_feedback(ttl_s=5.0)
    except AuthorizationError as exc:
        raise CapabilityDeniedError(
            Capability.ARM_FEEDBACK.value,
            [str(exc)],
        ) from exc

    transport = SerialTransport(
        args.port,
        baudrate=connection_profile.baudrate,
        read_timeout_s=connection_profile.read_timeout_s,
        write_timeout_s=connection_profile.write_timeout_s,
    )
    client = RoArmM3(transport, permit_feedback=feedback_permit)
    try:
        client.connect()
        feedback = client.request_feedback()
    except (FeedbackError, FeedbackNotPermittedError, TransportError, OSError) as exc:
        raise HardwareError(
            "ARM_FEEDBACK_FAILED",
            f"Live arm feedback failed without retry: {exc}",
            details={"port": args.port},
        ) from exc
    finally:
        if client.is_connected:
            client.close()

    document = {
        "schema": "rocell.arm_feedback.v1",
        "snapshot_hash": snapshot.snapshot_hash,
        "feedback": feedback.raw_fields,
    }
    _emit(document, args.json, (f"T=1051 feedback received from {args.port}",))
    return int(ExitCode.OK)


def _command_arrival_wizard(args: argparse.Namespace) -> int:
    """Launch a local diagnostic workbench, never a physical action at startup."""
    from rocell.application.arrival_wizard_service import ArrivalWizardService
    from rocell.application.wizard_actions import WizardError

    # Match other CLI workflows: explicit path, environment, then project
    # discovery. The parser deliberately leaves an omitted workspace as None.
    workspace = _find_workspace(args.workspace)
    if not 0 <= args.port <= 65535:
        raise UsageError(
            "INVALID_WIZARD_PORT", "Wizard port must be between 0 and 65535."
        )
    if args.json and not args.check:
        raise UsageError(
            "WIZARD_JSON_REQUIRES_CHECK",
            "Use --json with --check; interactive mode uses the local UI.",
        )
    try:
        service = ArrivalWizardService(
            workspace,
            mode=args.mode,
            cell_id=args.cell_id,
            export_directory=args.export_dir,
        )
    except (WizardError, OSError, ValueError) as exc:
        raise ConfigurationError("WIZARD_STARTUP_BLOCKED", str(exc)) from exc
    if args.check:
        try:
            _emit(
                service.view(),
                args.json,
                ("Wizard diagnostic preflight: no server or device opened.",),
            )
            return int(ExitCode.OK)
        finally:
            service.shutdown()
    if args.ui == "terminal":
        from rocell.ui.terminal import run_terminal_wizard

        try:
            return run_terminal_wizard(service)
        finally:
            service.shutdown()
    from rocell.ui.server import create_wizard_server

    try:
        server = create_wizard_server(service, port=args.port)
    except (OSError, ValueError):
        service.shutdown()
        raise
    try:
        print("RoCell local onboarding workbench")
        print(
            f"Mode: {args.mode}; physical camera/arm activation and contact remain blocked."
        )
        print(f"Export folder: {service.view()['exports']['directory']}")
        # Launch credentials stay in this local terminal/URL fragment; the
        # service and diagnostic export never receive or retain them.
        print(f"Open locally: {server.launch_url}")
        print(
            "Press Ctrl+C here to close the workbench. Diagnostic Stop is not a robot E-stop.",
            # Pipe-backed launchers must receive the local URL before the
            # server loop begins, not only after Python eventually exits.
            flush=True,
        )
        if args.open_browser:
            import webbrowser

            webbrowser.open(server.launch_url, new=2)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.close()
    return int(ExitCode.OK)


def _add_json_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit stable JSON output")


def _add_text_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", choices=("keyboard", "phone"), required=True)
    parser.add_argument(
        "--text", required=True, help="Text to compile; output retains only its hash"
    )
    _add_json_argument(parser)


def _add_placement_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the shared, explicit source controls for a reach-study overlay."""

    parser.add_argument(
        "--placement-rank",
        type=int,
        choices=(1, 2),
        default=1,
        help="Fully screened reach-study finalist rank to evaluate",
    )
    placement_source = parser.add_mutually_exclusive_group()
    placement_source.add_argument(
        "--study-input-id",
        default=None,
        help="Replay an exact content-derived input from the locked default grid",
    )
    placement_source.add_argument(
        "--refresh-placement-ranking",
        action="store_true",
        help="Rerun the bounded reach optimizer before selecting --placement-rank",
    )


def _add_eye_dataset_evidence_arguments(parser: argparse.ArgumentParser) -> None:
    """Require exact file identities for a physical-capture-shaped input set."""

    parser.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Strict rocell.eye_on_arm_dataset.v1 JSON input",
    )
    parser.add_argument(
        "--dataset-sha256",
        required=True,
        help="Lowercase SHA-256 of the exact dataset file bytes",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        required=True,
        help="Strict rocell.eye_on_arm_capture_evidence.v1 JSON input",
    )
    parser.add_argument(
        "--evidence-sha256",
        required=True,
        help="Lowercase SHA-256 of the exact raw-feedback evidence file bytes",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rocell",
        description="Simulation-first RoCell workcell control boundary",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="Workspace containing software/config/system_manifest.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional manifest path, absolute or relative to the workspace",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    bootstrap_sim = commands.add_parser(
        "bootstrap-sim",
        help="Validate and initialize the complete hardware-independent virtual workcell",
        description=(
            "Strictly load every virtual-workcell startup source, verify its "
            "cross-links, and report declared fidelity/physical gaps without "
            "importing hardware backends or creating a session."
        ),
    )
    bootstrap_sim.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    _add_json_argument(bootstrap_sim)
    bootstrap_sim.set_defaults(handler=_command_bootstrap_sim)

    qualification = commands.add_parser(
        "qualify-prehardware",
        help="Run the locked aggregate software-only qualification campaign",
        description=(
            "Exercise the real virtual startup, arm-camera correction, contact, "
            "outcome, determinism, and fail-stop paths. The standard profile "
            "also recomputes all 75 independent target routes and can take "
            "several minutes. No profile can authorize hardware motion/contact."
        ),
    )
    qualification.add_argument(
        "--profile",
        choices=("quick", "standard"),
        default="standard",
        help=(
            "quick runs bounded correction/fault/determinism cases; standard "
            "adds the full fault matrix and 75-route screen; default: standard"
        ),
    )
    qualification.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    qualification.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero unless every selected diagnostic behaves as expected",
    )
    qualification.add_argument(
        "--record",
        action="store_true",
        help=(
            "Atomically record a bounded qualification evidence package beneath "
            "the configured runtime evidence root"
        ),
    )
    _add_json_argument(qualification)
    qualification.set_defaults(handler=_command_qualify_prehardware)

    simulate_session = commands.add_parser(
        "simulate-session",
        help="Run a locked end-to-end virtual keyboard or Android session",
        description=(
            "Bootstrap the strict virtual workcell, load the hash-locked rank-1 "
            "commissioning overlay, execute accepted joint waypoints in virtual "
            "plants, and verify the text outcome without hardware access."
        ),
    )
    _add_text_arguments(simulate_session)
    simulate_session.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    simulate_session.add_argument(
        "--fault-profile",
        choices=_VIRTUAL_FAULT_PROFILES,
        default="none",
        help="Inject one deterministic fail-stop fault; default: none",
    )
    simulate_session.add_argument(
        "--record",
        action="store_true",
        help="Write an immutable evidence package beneath the runtime evidence root",
    )
    simulate_session.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero unless the virtual pipeline completes and verifies",
    )
    simulate_session.set_defaults(handler=_command_simulate_session)

    integrated_v2 = commands.add_parser(
        "simulate-integrated-v2",
        help="Run the dense zero-hardware keyboard/Android V2 mission",
        description=(
            "Assemble and execute the additive V2 mission across semantic steps, "
            "the accepted dense trajectory, synthetic B0477 observations, isolated "
            "26-body endpoint/midpoint collision queries, authorization-v2, an "
            "in-memory non-wire T104 runtime, virtual contacts, independent output "
            "observation, and crash-safe journals. It cannot access or authorize "
            "physical hardware."
        ),
    )
    _add_text_arguments(integrated_v2)
    integrated_v2.add_argument(
        "--journal-root",
        type=Path,
        required=True,
        help=(
            "New empty directory for an initial run, or the exact existing "
            "journal directory when --open-existing is selected"
        ),
    )
    integrated_v2.add_argument(
        "--open-existing",
        action="store_true",
        help=(
            "Open the exact assembly-bound journal set; execution still refuses "
            "automatic retry after any state beyond INTENT_COMMITTED"
        ),
    )
    integrated_v2.add_argument(
        "--fault-kind",
        choices=("none", "stall", "reset", "disconnect", "timeout", "nonsettle"),
        default="none",
        help="Inject one deterministic non-wire controller fault; default: none",
    )
    integrated_v2.add_argument(
        "--fault-command-ordinal",
        type=int,
        default=None,
        metavar="N",
        help="Zero-based dense command ordinal at which to inject --fault-kind",
    )
    integrated_v2.add_argument(
        "--camera-fault-kind",
        choices=("none", "capture-failure", "timeout", "stale-frame"),
        default="none",
        help=(
            "Inject one deterministic B0477 replay-camera fault after a settled "
            "final hover; default: none"
        ),
    )
    integrated_v2.add_argument(
        "--camera-fault-contact-ordinal",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Zero-based physical contact occurrence at which to inject "
            "--camera-fault-kind"
        ),
    )
    integrated_v2.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero unless the integrated rehearsal completes and verifies",
    )
    integrated_v2.set_defaults(handler=_command_simulate_integrated_v2)

    adaptive_session = commands.add_parser(
        "simulate-adaptive-session",
        help="Rehearse arm-camera board correction and truth-derived contact",
        description=(
            "Run a bounded, hardware-independent arm-camera rehearsal. Hidden-"
            "truth offset options perturb only the synthetic virtual plant; they "
            "cannot update calibration, release a physical gate, or reach a "
            "hardware transport."
        ),
    )
    _add_text_arguments(adaptive_session)
    adaptive_session.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    adaptive_session.add_argument(
        "--truth-offset-x-mm",
        type=_finite_float_argument,
        default=0.0,
        metavar="MM",
        help="Simulation-only hidden board-truth X offset in Wv; default: 0",
    )
    adaptive_session.add_argument(
        "--truth-offset-y-mm",
        type=_finite_float_argument,
        default=0.0,
        metavar="MM",
        help="Simulation-only hidden board-truth Y offset in Wv; default: 0",
    )
    adaptive_session.add_argument(
        "--truth-offset-z-mm",
        type=_finite_float_argument,
        default=0.0,
        metavar="MM",
        help="Simulation-only hidden board-truth Z offset in Wv; default: 0",
    )
    adaptive_session.add_argument(
        "--truth-yaw-deg",
        type=_finite_float_argument,
        default=0.0,
        metavar="DEG",
        help="Simulation-only hidden board-truth yaw about board Z; default: 0",
    )
    adaptive_session.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero unless correction, contact, outcome, and park pass",
    )
    adaptive_session.set_defaults(handler=_command_simulate_adaptive_session)

    replay_session = commands.add_parser(
        "replay-session",
        help="Strictly verify and fully recompute virtual-session evidence",
        description=(
            "Require an immutable manifest beneath the configured evidence root, "
            "verify every package byte/hash, and rerun the complete locked session."
        ),
    )
    replay_session.add_argument(
        "--manifest",
        dest="session_manifest",
        type=Path,
        required=True,
        help=(
            "Evidence manifest path beneath the runtime evidence root, absolute "
            "or relative to the selected workspace"
        ),
    )
    replay_session.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    replay_session.add_argument(
        "--require-identical",
        action="store_true",
        help="Return nonzero unless full recomputation is byte-for-byte identical",
    )
    _add_json_argument(replay_session)
    replay_session.set_defaults(handler=_command_replay_session)

    replay_qualification = commands.add_parser(
        "replay-prehardware-qualification",
        help="Strictly verify and fully recompute qualification evidence",
        description=(
            "Require an immutable qualification manifest beneath the configured "
            "evidence root, verify every compact artifact and child-report hash, "
            "then rerun the locked quick or standard campaign. Standard replay "
            "can take several minutes. No hardware adapter is opened."
        ),
    )
    replay_qualification.add_argument(
        "--manifest",
        dest="qualification_manifest",
        type=Path,
        required=True,
        help=(
            "Qualification evidence manifest beneath the runtime evidence root, "
            "absolute or relative to the selected workspace"
        ),
    )
    replay_qualification.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    replay_qualification.add_argument(
        "--require-identical",
        action="store_true",
        help="Return nonzero unless every recomputed artifact is identical",
    )
    _add_json_argument(replay_qualification)
    replay_qualification.set_defaults(handler=_command_replay_prehardware_qualification)

    replay_typing_trace = commands.add_parser(
        "replay-typing-trace",
        help="Verify one contained PC6 typing trace package without hardware",
        description=(
            "Read one exact package beneath an explicit evidence root, verify "
            "canonical manifests, stage hashes, containment, and redaction, then "
            "compare retained bytes without decoding them into executable commands."
        ),
    )
    replay_typing_trace.add_argument(
        "--evidence-root", type=Path, required=True,
        help="Existing nonsymlink directory containing the trace package",
    )
    replay_typing_trace.add_argument(
        "--package-id", required=True,
        help="Exact typing-trace-<24 lowercase hex> package identifier",
    )
    replay_typing_trace.add_argument("--expected-correlation-id", required=True)
    replay_typing_trace.add_argument("--expected-request-id", required=True)
    replay_typing_trace.add_argument(
        "--require-identical", action="store_true",
        help="Return nonzero unless every retained stage is byte-identical",
    )
    _add_json_argument(replay_typing_trace)
    replay_typing_trace.set_defaults(handler=_command_replay_typing_trace)

    status = commands.add_parser(
        "status", help="Inspect verified build state and capabilities"
    )
    _add_json_argument(status)
    status.set_defaults(handler=_command_status)

    integration_readiness = commands.add_parser(
        "integration-readiness",
        help="Report retained AI-to-arm readiness without hardware access",
        description=(
            "Compose the content-bound AI/arm evidence already retained in the "
            "repository. This command never opens a camera or controller, emits "
            "commands, or grants physical authority."
        ),
    )
    integration_readiness.add_argument(
        "--require-ready",
        action="store_true",
        help="Return nonzero unless every single-action review gate is ready",
    )
    _add_json_argument(integration_readiness)
    integration_readiness.set_defaults(handler=_command_integration_readiness)

    doctor = commands.add_parser(
        "doctor", help="Run side-effect-free runtime diagnostics"
    )
    doctor.add_argument("--mode", choices=("sim",), required=True)
    _add_json_argument(doctor)
    doctor.set_defaults(handler=_command_doctor)

    host_doctor = commands.add_parser(
        "host-doctor",
        help="Verify the controlled environment for physical onboarding",
        description=(
            "Inspect the selected source tree, workspace virtual environment, "
            "optional hardware dependencies, and dependency consistency without "
            "enumerating, opening, or commanding a physical device."
        ),
    )
    host_doctor.add_argument(
        "--profile",
        choices=("runtime", "hardware", "development"),
        default="hardware",
        help="Dependency profile to require; default: hardware",
    )
    host_doctor.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero when the selected environment profile is not ready",
    )
    _add_json_argument(host_doctor)
    host_doctor.set_defaults(handler=_command_host_doctor)

    connection_rehearsal = commands.add_parser(
        "rehearse-physical-connections",
        help="Rehearse exact B0477 and RoArm connection contracts with fakes",
        description=(
            "Run an incapable-provider rehearsal of host dependencies, exact B0477 "
            "identity/open/configure/flush/fresh-frame/reopen/close, unpowered arm "
            "identity, and one synthetic T=105/T=1051 exchange. It never enumerates "
            "or opens physical hardware and cannot authorize power, motion, or contact."
        ),
    )
    connection_rehearsal.add_argument(
        "--run-id",
        default="physical-connection-rehearsal-001",
        help="Portable synthetic run identifier",
    )
    connection_rehearsal.add_argument(
        "--fault",
        choices=_PHYSICAL_CONNECTION_REHEARSAL_FAULTS,
        default="none",
        help="Deterministic synthetic fault to require; default: none",
    )
    connection_rehearsal.add_argument(
        "--require-expected",
        action="store_true",
        help="Return nonzero unless nominal completes or the selected fault blocks",
    )
    _add_json_argument(connection_rehearsal)
    connection_rehearsal.set_defaults(handler=_command_rehearse_physical_connections)

    physical = commands.add_parser(
        "physical-onboard",
        help="Create and advance a persistent, diagnostic-only arrival session",
        description=(
            "Manage the separate physical commissioning journal. The initial "
            "release can automate controlled-file checks and read-only device "
            "inventory; it cannot power, initialize, move, or contact with the arm."
        ),
    )
    physical_commands = physical.add_subparsers(
        dest="physical_operation", required=True
    )

    physical_new = physical_commands.add_parser(
        "new",
        help="Create a source-bound immutable onboarding session",
    )
    physical_new.add_argument("--cell-id", required=True)
    physical_new.add_argument(
        "--session-id",
        default=None,
        help="Portable unique session ID; generated when omitted",
    )
    physical_new.add_argument(
        "--prepare-safe",
        action="store_true",
        help="Run both controlled-file-only stages; never enumerate a device",
    )
    _add_json_argument(physical_new)
    physical_new.set_defaults(handler=_command_physical_onboard_new)

    physical_status = physical_commands.add_parser(
        "status",
        help="Verify and display one session without performing an action",
    )
    physical_status.add_argument("--session-id", required=True)
    _add_json_argument(physical_status)
    physical_status.set_defaults(handler=_command_physical_onboard_status)

    physical_next = physical_commands.add_parser(
        "next",
        help="Preview or execute exactly one stale-state-protected safe action",
    )
    physical_next.add_argument("--session-id", required=True)
    physical_next.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Execute one action. Only the first two stages may pass; a later "
            "stage can only be marked WAITING_OPERATOR."
        ),
    )
    physical_next.add_argument(
        "--expected-stage",
        choices=_FIRST_POWER_ON_STAGES,
        default=None,
    )
    physical_next.add_argument(
        "--expected-head-sha256",
        type=_sha256_argument,
        default=None,
    )
    physical_next.add_argument(
        "--expected-challenge-sha256",
        type=_sha256_argument,
        default=None,
    )
    _add_json_argument(physical_next)
    physical_next.set_defaults(handler=_command_physical_onboard_next)

    physical_record = physical_commands.add_parser(
        "record",
        help="Hash and retain one evidence file without passing its stage",
    )
    physical_record.add_argument("--session-id", required=True)
    physical_record.add_argument(
        "--stage", choices=_FIRST_POWER_ON_STAGES, required=True
    )
    physical_record.add_argument("--file", type=Path, required=True)
    physical_record.add_argument("--file-sha256", type=_sha256_argument, required=True)
    physical_record.add_argument(
        "--captured-at-ns", type=_positive_nanoseconds_argument, required=True
    )
    physical_record.add_argument("--label", required=True)
    physical_record.add_argument("--media-type", required=True)
    physical_record.add_argument(
        "--expected-challenge-sha256",
        type=_sha256_argument,
        required=True,
    )
    _add_json_argument(physical_record)
    physical_record.set_defaults(handler=_command_physical_onboard_record)

    physical_verify = physical_commands.add_parser(
        "verify",
        help="Verify source binding, journal, high-water mark, and all evidence",
    )
    physical_verify.add_argument("--session-id", required=True)
    physical_verify.add_argument(
        "--require-complete",
        action="store_true",
        help="Return nonzero until the diagnostic handoff is complete",
    )
    _add_json_argument(physical_verify)
    physical_verify.set_defaults(handler=_command_physical_onboard_verify)

    physical_foundation = physical_commands.add_parser(
        "verify-foundation",
        help="Validate the runtime-inactive v2 contract graph with zero device I/O",
    )
    _add_json_argument(physical_foundation)
    physical_foundation.set_defaults(
        handler=_command_physical_onboard_verify_foundation
    )

    physical_init_v2 = physical_commands.add_parser(
        "init-v2-storage",
        help="Qualify and initialize crash-aware M1 storage with zero device I/O",
        description=(
            "Run the controlled on-volume Windows/NTFS durability checks, anchor "
            "the result, and initialize one cell-global M1 store. This command "
            "does not enumerate or open a camera or arm and grants no physical "
            "authority."
        ),
    )
    physical_init_v2.add_argument("--cell-id", required=True)
    _add_json_argument(physical_init_v2)
    physical_init_v2.set_defaults(handler=_command_physical_onboard_init_v2_storage)

    physical_new_v2 = physical_commands.add_parser(
        "new-v2",
        help="Create a qualified V2 session without advancing any stage",
        description=(
            "Open an explicitly initialized M1 store and create one source-bound "
            "V2 session under cell/session leases. No device is enumerated or "
            "opened and no onboarding stage is advanced."
        ),
    )
    physical_new_v2.add_argument("--cell-id", required=True)
    physical_new_v2.add_argument(
        "--session-id",
        default=None,
        help="Portable unique V2 session ID; generated when omitted",
    )
    _add_json_argument(physical_new_v2)
    physical_new_v2.set_defaults(handler=_command_physical_onboard_new_v2)

    physical_verify_v2 = physical_commands.add_parser(
        "verify-v2-runtime",
        help="Verify M1 global state and optionally one V2 session",
        description=(
            "Freshly requalify the M1 store and verify its cell-global ledgers. "
            "When --session-id is supplied, also verify that complete V2 session. "
            "This is a zero-device-I/O integrity check, not a physical release."
        ),
    )
    physical_verify_v2.add_argument("--cell-id", required=True)
    physical_verify_v2.add_argument(
        "--session-id",
        default=None,
        help="Optional V2 session to include in the integrity check",
    )
    _add_json_argument(physical_verify_v2)
    physical_verify_v2.set_defaults(handler=_command_physical_onboard_verify_v2_runtime)

    wizard = physical_commands.add_parser(
        "wizard",
        help="Open the local diagnostic/rehearsal workbench; startup opens no hardware",
        description=(
            "Service-backed loopback UI for baselines, camera/arm rehearsals, "
            "semantic task planning, and verified diagnostic exports. Physical mode "
            "offers explicit source-only durable preflight and OS metadata inspection; capture, serial-open, "
            "power, motion and contact remain unavailable until qualified."
        ),
    )
    wizard.add_argument(
        "--mode", choices=("rehearsal", "physical"), default="rehearsal"
    )
    wizard.add_argument("--ui", choices=("browser", "terminal"), default="browser")
    wizard.add_argument(
        "--cell-id",
        default="CELL-A",
        help="Diagnostic cell label; does not create an M1 deployment",
    )
    wizard.add_argument(
        "--export-dir",
        type=Path,
        default=None,
        help="Assigned export directory; defaults to workspace software/runs/wizard-exports",
    )
    wizard.add_argument(
        "--port", type=int, default=0, help="Loopback port; 0 selects a free port"
    )
    wizard.add_argument(
        "--open-browser",
        action="store_true",
        help="Explicitly open the local workbench in the default browser",
    )
    wizard.add_argument(
        "--check",
        action="store_true",
        help="Return startup view without binding a server, running tests, or opening devices",
    )
    _add_json_argument(wizard)
    wizard.set_defaults(handler=_command_arrival_wizard)

    physical_intake = physical_commands.add_parser(
        "intake",
        help="Validate the locked 55-row hardware intake and evidence hashes",
    )
    physical_intake.add_argument("--file", type=Path, required=True)
    physical_intake.add_argument(
        "--session-id",
        default=None,
        help="Optional session whose active camera_receipt stage receives the report",
    )
    physical_intake.add_argument(
        "--expected-challenge-sha256",
        type=_sha256_argument,
        default=None,
    )
    physical_intake.add_argument(
        "--require-review-ready",
        action="store_true",
        help="Return nonzero unless all 55 controlled records are PASS or NA",
    )
    _add_json_argument(physical_intake)
    physical_intake.set_defaults(handler=_command_physical_onboard_intake)

    physical_inventory = physical_commands.add_parser(
        "inventory",
        help="Inventory camera and serial metadata without opening either device",
    )
    physical_inventory.add_argument("--session-id", required=True)
    physical_inventory.add_argument(
        "--record-stage",
        choices=("camera_identity", "arm_identity"),
        default=None,
        help="Optionally retain the inventory under the active matching stage",
    )
    physical_inventory.add_argument(
        "--expected-challenge-sha256",
        type=_sha256_argument,
        default=None,
    )
    physical_inventory.add_argument(
        "--require-candidates",
        action="store_true",
        help="Return nonzero unless at least one camera and serial candidate are observed",
    )
    _add_json_argument(physical_inventory)
    physical_inventory.set_defaults(handler=_command_physical_onboard_inventory)

    camera_profile = commands.add_parser(
        "camera-profile",
        help="Inspect the selected B0477 purchase profile without hardware access",
        description=(
            "Validate the exact purchased-camera record, published USB3 mode, "
            "and bounded synthetic projection. This command does not enumerate "
            "or open a camera and cannot commission hardware."
        ),
    )
    camera_profile.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help=(
            "Optional profile path beneath the workspace; defaults to the "
            "controlled Arducam B0477 profile"
        ),
    )
    _add_json_argument(camera_profile)
    camera_profile.set_defaults(handler=_command_camera_profile)

    camera_rehearsal = commands.add_parser(
        "rehearse-camera-commissioning",
        help="Exercise the B0477 commissioning gates with synthetic evidence",
        description=(
            "Validate a bounded synthetic persistent-identity, USB3 native-mode, "
            "manual-controls, and close/reopen fixture. No camera is enumerated "
            "or opened, and a pass never commissions physical hardware."
        ),
    )
    camera_rehearsal.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help=(
            "Synthetic rehearsal JSON beneath the workspace; defaults to the "
            "controlled nominal B0477 test fixture"
        ),
    )
    camera_rehearsal.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help=(
            "Optional profile path beneath the workspace; defaults to the "
            "controlled Arducam B0477 purchase profile"
        ),
    )
    _add_json_argument(camera_rehearsal)
    camera_rehearsal.set_defaults(handler=_command_rehearse_camera_commissioning)

    uvc_rehearsal = commands.add_parser(
        "rehearse-b0477-uvc-inventory",
        help="Exercise B0477 UVC identity and mode gates with a fake provider",
        description=(
            "Parse a bounded synthetic UVC inventory, collect it through the "
            "provider seam, and assess persistent identity, exact native YUY2 "
            "mode, USB3 negotiation, manual controls, and reopen stability. "
            "No camera is enumerated or opened."
        ),
    )
    uvc_rehearsal.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help=(
            "Synthetic inventory JSON beneath the workspace; defaults to the "
            "controlled nominal B0477 UVC fixture"
        ),
    )
    uvc_rehearsal.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help=(
            "Optional profile path beneath the workspace; defaults to the "
            "controlled Arducam B0477 purchase profile"
        ),
    )
    uvc_rehearsal.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero when any synthetic UVC inventory gate is blocked",
    )
    _add_json_argument(uvc_rehearsal)
    uvc_rehearsal.set_defaults(handler=_command_rehearse_b0477_uvc_inventory)

    intrinsics_rehearsal = commands.add_parser(
        "rehearse-b0477-intrinsics",
        help="Validate the sealed B0477 intrinsics workflow using synthetic data",
        description=(
            "Validate the exact native mode, camera/settings bindings, ChArUco "
            "definition, source-image manifest, precommitted training/held-out "
            "split, distortion solution, crop, residuals, and undistortion-map "
            "hash in a synthetic fixture. No camera or robot is accessed."
        ),
    )
    intrinsics_rehearsal.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help=(
            "Synthetic intrinsics JSON beneath the workspace; defaults to the "
            "controlled B0477 ChArUco rehearsal fixture"
        ),
    )
    intrinsics_rehearsal.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help=(
            "Optional profile path beneath the workspace; defaults to the "
            "controlled Arducam B0477 purchase profile"
        ),
    )
    _add_json_argument(intrinsics_rehearsal)
    intrinsics_rehearsal.set_defaults(handler=_command_rehearse_b0477_intrinsics)

    stack_rehearsal = commands.add_parser(
        "rehearse-b0477-stack",
        help="Cross-check the complete selected B0477 static-camera stack",
        description=(
            "Bind the purchase profile, support geometry, commissioning fixture, "
            "fake UVC inventory, sealed intrinsics rehearsal, and (by default) "
            "normal plus tag-loss JPEG vision runs into one zero-authority report."
        ),
    )
    stack_rehearsal.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help="Optional purchased-profile path beneath the workspace",
    )
    stack_rehearsal.add_argument(
        "--support-file",
        type=Path,
        default=None,
        help="Optional static-support design path beneath the workspace",
    )
    stack_rehearsal.add_argument(
        "--commissioning-fixture",
        type=Path,
        default=None,
        help="Optional synthetic commissioning fixture beneath the workspace",
    )
    stack_rehearsal.add_argument(
        "--uvc-fixture",
        type=Path,
        default=None,
        help="Optional synthetic UVC inventory fixture beneath the workspace",
    )
    stack_rehearsal.add_argument(
        "--intrinsics-fixture",
        type=Path,
        default=None,
        help="Optional synthetic intrinsics fixture beneath the workspace",
    )
    stack_rehearsal.add_argument(
        "--sequence",
        type=int,
        default=0,
        help="Bounded sequence shared by the normal and tag-loss pixel runs",
    )
    stack_rehearsal.add_argument(
        "--skip-pixel-vision",
        action="store_true",
        help="Run the fast five-artifact coherence check without rendering images",
    )
    stack_rehearsal.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero when any stack coherence gate is blocked",
    )
    _add_json_argument(stack_rehearsal)
    stack_rehearsal.set_defaults(handler=_command_rehearse_b0477_stack)

    b0477_vision = commands.add_parser(
        "simulate-b0477-vision",
        help="Run the static B0477 synthetic JPEG-to-board-pose path",
        description=(
            "Render the RC03 placemat using the exact B0477 half-scale synthetic "
            "projection, recover AprilTags from JPEG pixels, and estimate board "
            "pose. This is nominal zero-hardware evidence only."
        ),
    )
    b0477_vision.add_argument(
        "--mode",
        choices=("normal", "tag-loss"),
        default="normal",
        help="Normal six-tag image or an expected natural tag-loss rejection",
    )
    b0477_vision.add_argument(
        "--sequence",
        type=int,
        default=0,
        help="Bounded synthetic capture sequence; default: 0",
    )
    b0477_vision.add_argument(
        "--require-expected",
        action="store_true",
        help="Return nonzero unless normal passes or tag-loss safely rejects",
    )
    _add_json_argument(b0477_vision)
    b0477_vision.set_defaults(handler=_command_simulate_b0477_vision)

    first_power_on = commands.add_parser(
        "rehearse-first-power-on",
        help="Rehearse camera-first connection and calibration onboarding",
        description=(
            "Run the complete first-power-on state machine using only controlled "
            "files, synthetic camera images, a fake UVC provider, and an injected "
            "RoArm protocol controller. Power application is modeled as a possible "
            "automatic-motion event. No OS device is enumerated, no physical port "
            "is opened, and no initialization or motion command is available."
        ),
    )
    first_power_on.add_argument(
        "--scenario",
        choices=_FIRST_POWER_ON_SCENARIOS,
        default="nominal",
        help="Nominal workflow or one deterministic fail-stop scenario",
    )
    first_power_on.add_argument(
        "--stop-after",
        choices=_FIRST_POWER_ON_STAGES,
        default=None,
        help="Stop after one passing stage and emit a resumable rehearsal prefix",
    )
    first_power_on.add_argument(
        "--resume",
        type=Path,
        default=None,
        help="Strict checkpoint beneath the workspace to verify before resuming",
    )
    first_power_on.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="New immutable checkpoint path beneath the workspace; never overwrites",
    )
    first_power_on.add_argument(
        "--require-expected",
        action="store_true",
        help="Return nonzero unless nominal completes or the injected fault blocks at its declared stage",
    )
    _add_json_argument(first_power_on)
    first_power_on.set_defaults(handler=_command_rehearse_first_power_on)

    plan = commands.add_parser("plan", help="Compile text into semantic actions only")
    _add_text_arguments(plan)
    plan.set_defaults(handler=_command_plan)

    dry_run = commands.add_parser(
        "dry-run",
        help="Trace semantic actions without geometry or hardware access",
    )
    _add_text_arguments(dry_run)
    dry_run.set_defaults(handler=_command_dry_run)

    workcell = commands.add_parser(
        "workcell",
        help="Validate placemat geometry, target bindings, frames, and physical holds",
    )
    _add_json_argument(workcell)
    workcell.set_defaults(handler=_command_workcell)

    sweep = commands.add_parser(
        "sweep-targets",
        help="Screen requested nominal targets plus required park through diagnostic IK",
    )
    sweep.add_argument(
        "--device",
        choices=("keyboard", "phone", "all"),
        default="all",
    )
    sweep.add_argument(
        "--tool-case",
        default="default",
        help="default, all, or an exact virtual tool case ID",
    )
    sweep.add_argument(
        "--phase",
        choices=("contact", "approach", "hover", "transit", "all"),
        default="contact",
    )
    sweep.add_argument(
        "--require-all",
        action="store_true",
        help="Return a nonzero exit code when any screened point is rejected",
    )
    _add_json_argument(sweep)
    sweep.set_defaults(handler=_command_sweep_targets)

    reach_layout = commands.add_parser(
        "optimize-layout",
        help="Run a bounded RC03 clamp/tool contact-and-park reach diagnostic",
        description=(
            "Run the bounded RC03 contact-and-park placement diagnostic; "
            "this never authorizes motion or contact."
        ),
    )
    reach_layout.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "Return nonzero unless one finalist accepts every locked contact "
            "and both route parks"
        ),
    )
    _add_json_argument(reach_layout)
    reach_layout.set_defaults(handler=_command_optimize_layout)

    park = commands.add_parser(
        "optimize-park",
        help="Find a bounded geometry-screened Freeze005 park-pose overlay",
        description=(
            "Search the revalidated placemat board for a park point accepted by "
            "both selected route tools. This is independent pose IK only and "
            "never authorizes motion or changes the canonical build."
        ),
    )
    park.add_argument(
        "--require-both-routes",
        action="store_true",
        help="Return nonzero unless the best candidate accepts both route tools",
    )
    _add_json_argument(park)
    park.set_defaults(handler=_command_optimize_park)

    layout_hypotheses = commands.add_parser(
        "study-layout-hypotheses",
        help="Run a staged broader base/yaw/tool sensitivity study",
        description=(
            "Screen a bounded, unmeasured base/yaw/tool envelope through a "
            "fixed verified park probe, named phone key_a regressions, spatial "
            "sentinels, and then all 46 keyboard plus 29 phone contacts. "
            "This is independent-pose simulation only and never authorizes motion."
        ),
    )
    layout_hypotheses.add_argument(
        "--require-promotable",
        action="store_true",
        help=(
            "Return nonzero unless at least one candidate in the screened "
            "full-catalog shortlist is eligible for the separate full-route screen"
        ),
    )
    _add_json_argument(layout_hypotheses)
    layout_hypotheses.set_defaults(handler=_command_study_layout_hypotheses)

    placemat_geometry = commands.add_parser(
        "stress-placemat-geometry",
        help="Stress nominal placemat targets with assumed geometry error",
        description=(
            "Evaluate all 46 keyboard and 29 phone target regions under a "
            "deterministic matrix of assumed board-registration, device-placement, "
            "target-map, surface-height, and TCP offsets. The default bounds are "
            "unmeasured sensitivity inputs, not tolerances or release criteria, "
            "and the report is bound to the selected static B0477 support/profile."
        ),
    )
    placemat_geometry.add_argument(
        "--zero-bounds",
        action="store_true",
        help=(
            "Run the one-case nominal control instead of the default 59-case "
            "assumed sensitivity matrix"
        ),
    )
    placemat_geometry.add_argument(
        "--require-no-gaps",
        action="store_true",
        help=(
            "Return nonzero for any sampled non-inside classification, including "
            "safe-region, adjacent-target, device-boundary, or board-boundary "
            "findings; default assumptions are expected to expose phone gaps"
        ),
    )
    _add_json_argument(placemat_geometry)
    placemat_geometry.set_defaults(handler=_command_stress_placemat_geometry)

    mission_routes = commands.add_parser(
        "screen-mission-routes",
        help="Screen every locked target as an independent complete route",
        description=(
            "Run all 46 keyboard and 29 phone targets as separate bounded "
            "park/transit/hover/approach/contact/retract/park trajectory "
            "diagnostics. This does not prove arbitrary typing sequences, "
            "collision freedom, physical contact, or hardware readiness."
        ),
    )
    mission_routes.add_argument(
        "--from-layout-study-rank",
        type=int,
        choices=tuple(range(1, 9)),
        default=None,
        help=(
            "Rerun the staged layout study and use this promoted rank; by "
            "default use the documented Freeze005 placement and bounded park"
        ),
    )
    mission_routes.add_argument(
        "--require-all",
        action="store_true",
        help="Return nonzero unless all 75 independent target routes pass",
    )
    _add_json_argument(mission_routes)
    mission_routes.set_defaults(handler=_command_screen_mission_routes)

    adaptive_routes = commands.add_parser(
        "screen-adaptive-mission-routes",
        help="Run all 75 targets through independent adaptive camera sessions",
        description=(
            "Execute one fresh synthetic arm-camera/contact/outcome/park cycle "
            "for each of the locked 46 keyboard and 29 phone targets. This is "
            "a multi-minute, zero-authority simulation and is separate from the "
            "trajectory-only mission route screen."
        ),
    )
    adaptive_routes.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    adaptive_routes.add_argument(
        "--chunk-size",
        type=int,
        choices=tuple(range(1, 16)),
        default=5,
        help="Bound report/orchestration chunks; each target remains independent",
    )
    adaptive_routes.add_argument(
        "--require-all",
        action="store_true",
        help="Return nonzero unless all 75 adaptive target sessions pass",
    )
    _add_json_argument(adaptive_routes)
    adaptive_routes.set_defaults(handler=_command_screen_adaptive_mission_routes)

    adaptive_stress = commands.add_parser(
        "stress-adaptive-session",
        help="Run deterministic signed and boundary arm-camera perturbations",
        description=(
            "Exercise nominal, signed X/Y, signed yaw, over-limit rejection, "
            "and SHA-256-seeded combined perturbations. Hidden transforms are "
            "hash-bound but never serialized, and no hardware adapter is opened."
        ),
    )
    adaptive_stress.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help=(
            "Optional runtime configuration path, absolute or relative to the "
            "selected workspace"
        ),
    )
    adaptive_stress.add_argument(
        "--seed",
        type=int,
        default=20_260_903,
        help="Signed 64-bit deterministic generator seed; default: 20260903",
    )
    adaptive_stress.add_argument(
        "--generated-cases",
        type=int,
        choices=tuple(range(0, 17)),
        default=8,
        help="Additional deterministic combined perturbations; default: 8",
    )
    adaptive_stress.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero unless every expected completion/rejection matches",
    )
    _add_json_argument(adaptive_stress)
    adaptive_stress.set_defaults(handler=_command_stress_adaptive_session)

    collision_status = commands.add_parser(
        "collision-status",
        help="Audit required full-body collision geometry and exact blockers",
        description=(
            "Revalidate the locked model and workcell, enumerate every required "
            "robot/holder/camera/cable/tool/environment collision body, and "
            "fail closed when complete geometry or bindings are absent. No pose "
            "or sweep is labeled collision-free while this audit is blocked."
        ),
    )
    collision_status.add_argument(
        "--require-diagnostic-ready",
        action="store_true",
        help=(
            "Return nonzero unless every required body has geometry sufficient "
            "for a simulation-only collision diagnostic"
        ),
    )
    _add_json_argument(collision_status)
    collision_status.set_defaults(handler=_command_collision_status)

    trajectory = commands.add_parser(
        "simulate-trajectory",
        help="Run bounded sequential IK over a complete nominal typing/tapping route",
        description=(
            "Select a finalist from the bounded reach study, expand text through "
            "park/transit/hover/approach/contact/retract phases, and check joint "
            "deltas between sampled IK waypoints. This never authorizes hardware."
        ),
    )
    _add_text_arguments(trajectory)
    _add_placement_arguments(trajectory)
    trajectory.add_argument(
        "--use-optimized-park",
        action="store_true",
        help=(
            "Use the best Freeze005 bounded park diagnostic as a simulation-only "
            "overlay; conflicts with manual park coordinates"
        ),
    )
    trajectory.add_argument("--park-x-mm", type=float, default=None)
    trajectory.add_argument("--park-y-mm", type=float, default=None)
    trajectory.add_argument(
        "--maximum-cartesian-step-mm",
        type=float,
        default=30.0,
    )
    trajectory.add_argument(
        "--maximum-joint-step-rad",
        type=float,
        default=0.35,
    )
    trajectory.add_argument(
        "--minimum-arm-joint-margin",
        type=float,
        default=0.01,
    )
    trajectory.add_argument(
        "--maximum-refinement-rounds",
        type=int,
        choices=(0, 1, 2, 3),
        default=2,
    )
    trajectory.add_argument(
        "--maximum-route-targets",
        type=int,
        choices=tuple(range(1, 17)),
        default=8,
    )
    trajectory.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero unless every densified waypoint passes",
    )
    trajectory.set_defaults(handler=_command_simulate_trajectory)

    calibration_status = commands.add_parser(
        "calibration-status",
        help="Inspect ordered calibration/qualification dependencies for a mission",
    )
    calibration_status.add_argument(
        "--device",
        choices=("keyboard", "phone"),
        required=True,
    )
    calibration_status.add_argument(
        "--require-ready",
        action="store_true",
        help="Return a nonzero exit code unless every required artifact is valid",
    )
    _add_json_argument(calibration_status)
    calibration_status.set_defaults(handler=_command_calibration_status)

    eye_on_arm = commands.add_parser(
        "solve-eye-on-arm-offline",
        help="Solve a pinned eye-on-arm JSON dataset with no hardware or artifact writes",
    )
    eye_on_arm.add_argument(
        "--dataset",
        type=Path,
        required=True,
        help="Strict rocell.eye_on_arm_dataset.v1 JSON input",
    )
    eye_on_arm.add_argument(
        "--expected-sha256",
        default=None,
        help="Optional lowercase SHA-256 pin for the exact input file bytes",
    )
    eye_on_arm.add_argument(
        "--require-diagnostic-pass",
        action="store_true",
        help="Return nonzero after emitting the report when diagnostic limits fail",
    )
    _add_json_argument(eye_on_arm)
    eye_on_arm.set_defaults(handler=_command_solve_eye_on_arm_offline)

    eye_on_arm_fk = commands.add_parser(
        "verify-eye-on-arm-fk-offline",
        help=(
            "Recompute carrier poses from hash-pinned raw T=1051 evidence "
            "with no hardware or artifact writes"
        ),
        description=(
            "Recompute carrier poses from hash-pinned raw T=1051 evidence "
            "with no hardware or artifact writes. This is an offline evidence "
            "check, not a commissioning or motion-authority operation."
        ),
    )
    _add_eye_dataset_evidence_arguments(eye_on_arm_fk)
    eye_on_arm_fk.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero after emitting the report unless every sample passes",
    )
    _add_json_argument(eye_on_arm_fk)
    eye_on_arm_fk.set_defaults(handler=_command_verify_eye_on_arm_fk_offline)

    eye_on_arm_bundle = commands.add_parser(
        "verify-eye-on-arm-capture-bundle-offline",
        help="Verify hash-pinned T=1051, JPEG, detection, and bracket bytes offline",
        description=(
            "Verify an exact dataset, decoded-feedback evidence file, and raw "
            "capture bundle containing T=1051 wire bytes, JPEG bytes, normalized "
            "detections, and pre/exposure/post brackets. This performs no hardware "
            "or artifact writes and does not qualify physical timing."
        ),
    )
    _add_eye_dataset_evidence_arguments(eye_on_arm_bundle)
    eye_on_arm_bundle.add_argument(
        "--bundle",
        type=Path,
        required=True,
        help="Strict rocell.eye_on_arm_capture_bundle.v1 JSON input",
    )
    eye_on_arm_bundle.add_argument(
        "--bundle-sha256",
        required=True,
        help="Lowercase SHA-256 of the exact capture-bundle file bytes",
    )
    eye_on_arm_bundle.add_argument(
        "--require-pass",
        action="store_true",
        help="Return nonzero after reporting unless every structural sample passes",
    )
    _add_json_argument(eye_on_arm_bundle)
    eye_on_arm_bundle.set_defaults(
        handler=_command_verify_eye_on_arm_capture_bundle_offline
    )

    simulate = commands.add_parser(
        "simulate",
        help="Run frozen nominal geometry, diagnostic IK, and synthetic vision",
    )
    _add_text_arguments(simulate)
    simulate.set_defaults(handler=_command_simulate)

    feedback = commands.add_parser(
        "arm-feedback",
        help="Request one T=105 snapshot only if the build permits robot power",
    )
    feedback.add_argument("--port", required=True, help="Explicit serial port identity")
    feedback.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Optional assertion that must equal the commissioned read timeout",
    )
    _add_json_argument(feedback)
    feedback.set_defaults(handler=_command_arm_feedback)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    json_requested = "--json" in arguments
    parser = build_parser()
    args = parser.parse_args(arguments)
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except CliError as exc:
        if json_requested:
            _json_dump(exc.to_dict(), stream=sys.stderr)
        else:
            print(f"error [{exc.code}]: {exc.message}", file=sys.stderr)
            reasons = exc.details.get("reasons")
            if isinstance(reasons, list):
                for reason in reasons:
                    print(f"  - {reason}", file=sys.stderr)
        return int(exc.exit_code)
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        error = CliError(
            "INTERNAL_ERROR",
            f"Unexpected runtime error: {type(exc).__name__}: {exc}",
            exit_code=ExitCode.INTERNAL_ERROR,
        )
        if json_requested:
            _json_dump(error.to_dict(), stream=sys.stderr)
        else:
            print(f"error [{error.code}]: {error.message}", file=sys.stderr)
        return int(error.exit_code)
