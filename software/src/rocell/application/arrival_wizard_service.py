"""Shared arrival workbench; construction and cached views are device-inert.

The console delegates original-store transactions and isolated rehearsal work.
Its one effectful USB baseline action delegates to the purpose-specific original
M1/coordinator owner, never to the zero-effect diagnostic subprocess runner.
Browser actions select only the closed catalog. Construction/status read
configuration and memory; only an explicitly executed ticket can create a log,
run a worker, query the admitted USB target, or export a report.
Original-bound camera probe/settings capture have parent-owned effectful paths.
Stage-6 capture, serial open, arm power and contact remain unavailable.

The UI revision includes progress; a separate state epoch binds action tickets.
Thus progress polling cannot invalidate an exact Stop ticket for the same
operation. State changes, source drift, expiry and session restart still do.
"""

from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import sys
from pathlib import Path
import re
import threading
import time
import unicodedata
from typing import Any, Callable
import uuid

from rocell import __version__
from rocell.application.arm_wizard_readiness import arm_wizard_readiness
from rocell.application.physical_onboarding import STAGE_ORDER
from rocell.application.physical_intake_notebook import PhysicalIntakeNotebook
from rocell.application.wizard_actions import (
    ACTIONS,
    ACTION_BY_ID,
    PHYSICAL_HOLD,
    ActionDefinition,
    WizardError,
    validate_action_input,
)
from rocell.application.wizard_diagnostic_coordinator import (
    DiagnosticProcessRunner,
    require_regular_path,
    source_fingerprint,
    validate_diagnostic_worker_result,
)
from rocell.application.wizard_diagnostic_export import (
    MAX_ATTACHMENTS,
    WizardDiagnosticExporter,
    WizardDiagnosticExportError,
    sanitize_diagnostic_record,
    verify_export,
)
from rocell.application.wizard_diagnostic_log import WizardDiagnosticLog
from rocell.application.wizard_device_selection import (
    DeviceSelectionError,
    WizardDeviceSelection,
)
from rocell.application.wizard_native_camera_enrollment import (
    NativeCameraEnrollmentError,
    WizardNativeCameraEnrollment,
)
from rocell.application.wizard_native_camera_metadata import (
    RehearsalNativeCameraMetadataProvider,
)
from rocell.application.wizard_native_arm_metadata import (
    correlate_native_arm_metadata,
    decode_controller_snapshot,
    summarize_native_arm_metadata,
)
from rocell.application.wizard_camera_helper_inspection import (
    CameraHelperInspectionError,
    create_metadata_provider,
    inspect_current_camera_helper as inspect_camera_helper,
)
from rocell.application.wizard_camera_helper_registration import (
    CameraHelperRegistrationError,
    WizardCameraHelperRegistration,
)
from .camera_configuration_wizard import CameraConfigurationWizard
from .camera_operating_assessment_wizard import (
    CameraOperatingAssessmentWizard,
    ACTION as OPERATING_ASSESSMENT,
)
from .camera_operating_proposal_wizard import (
    CameraOperatingProposalWizard,
    ACTION as OPERATING_PROPOSAL,
)
from .camera_operating_submission_wizard import (
    CameraOperatingSubmissionWizard,
    ACTION as OPERATING_SUBMISSION,
)
from .physical_camera_dispatch import PhysicalCameraDispatchError
from .camera_configuration_wizard_contract import (
    CAPTURE_ACTION_ID as CONFIGURATION_CAPTURE,
    EXPORT_ACTION_ID as CONFIGURATION_EXPORT,
)


MAX_TICKETS = 128
MAX_OPERATIONS = 32
MAX_FULL_RESULTS = 8
MAX_RESULT_BYTES = 1024 * 1024
TICKET_TTL_SECONDS = 120
_HOUSEKEEPING = frozenset(
    {
        "export_logs",
        "record_note",
        "stop_operation",
        "physical_received_camera_export",
        "physical_camera_identity_export",
        "physical_usb_identity_export",
        "physical_camera_probe_export",
        "physical_camera_probe_attempt_export",
        CONFIGURATION_EXPORT,
    }
)
_TERMINAL = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"})
_INVENTORY_ACTIONS = frozenset({"inventory_devices", "rehearse_device_inventory"})
_CANDIDATE_ACTIONS = {
    "review_camera_candidate": "CAMERA",
    "review_arm_candidate": "SERIAL",
}
_NATIVE_ACTIONS = frozenset(
    {"native_camera_inventory", "native_camera_identity", "native_camera_review"}
)
_NATIVE_CHOICES = frozenset({"native_camera_identity", "native_camera_review"})
_NATIVE_ARM_ACTIONS = frozenset(
    {"inspect_native_arm_metadata", "rehearse_native_arm_metadata"}
)
_POWERED_ACTIONS = frozenset({"run_powered_arm_feedback", "capture_powered_arm_telemetry"})
_HELPER_ACTIONS = frozenset({"camera_helper_inspect", "camera_helper_review"})
_CAMERA_CAMPAIGN_ACTIONS = frozenset(
    {"rehearsal_camera_campaign", "rehearsal_owned_camera_campaign"}
)
_PREVIEW_INVALIDATING_ACTIONS = _CAMERA_CAMPAIGN_ACTIONS | frozenset(
    {
        "rehearsal_collect",
        "rehearsal_arm_feedback_campaign",
        "rehearsal_owned_arm_feedback_campaign",
        "rehearsal_reopen",
        "rehearsal_camera_probe",
        "rehearsal_camera_configuration",
        "physical_camera_configuration",
        CONFIGURATION_CAPTURE,
        "physical_camera_plan",
    }
)
_CELL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_OMISSION_POLICY = (
    "Views include lightweight summaries only. Up to eight most recent full results "
    "are retained, each at most 1 MiB. Exports include those that fit a 6 MiB "
    "attachment budget; every omitted result is listed with its reason/hash when available. "
    "A complete last-published intake draft, retained noncontact readiness receipt, "
    "retained camera/runtime/metadata reports and owned-arm connection diagnostics, "
    "when present, each reserve one of the eight attachment slots before rotating full "
    "results. Raw camera media and operational ledgers are never copied."
)


@dataclass
class _Ticket:
    ticket_id: str
    action_id: str
    values: dict[str, Any]
    state_epoch: int
    source_sha256: str
    expires_at: float
    running_operation_id: str | None
    receipt: dict[str, Any] | None = None


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_payload(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode("ascii")


def _profile(workspace: Path, relative: str) -> dict[str, Any]:
    path = require_regular_path(workspace / relative, directory=False)
    if path.stat().st_size > 256 * 1024:
        raise WizardError(
            "PROFILE_LIMIT", "A configured profile exceeded its read budget."
        )
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise WizardError("INVALID_PROFILE", "Expected a configured profile object.")
    return sanitize_diagnostic_record(value)


def _nominal_board(workspace: Path) -> tuple[dict[str, Any], bytes]:
    """Render verified nominal scene geometry, never unverified layout JSON."""
    from PIL import Image, ImageDraw
    from rocell.application.context import load_simulation_context

    context = load_simulation_context(
        workspace, workspace / "software/config/system_manifest.json"
    )
    scene = context.scene
    width = scene.board.maximum.x - scene.board.minimum.x
    height = scene.board.maximum.y - scene.board.minimum.y
    geometry: dict[str, Any] = {
        "width_mm": width,
        "height_mm": height,
        "coordinate_state": "NOMINAL_UNMEASURED",
        "frame": scene.board_frame,
        "origin": "front-left board top; +X right, +Y toward arm, +Z up",
        "manifest_id": context.snapshot.manifest_id,
        "source_hashes": dict(scene.source_hashes),
        "devices": [
            {
                "name": name,
                "x_mm": device.envelope.minimum.x,
                "y_mm": device.envelope.minimum.y,
                "width_mm": device.envelope.maximum.x - device.envelope.minimum.x,
                "height_mm": device.envelope.maximum.y - device.envelope.minimum.y,
                "interaction_z_mm": device.interaction_plane_z_mm,
            }
            for name, device in scene.devices.items()
        ],
        "tags": [
            {"name": tag.name, "x_mm": tag.center.x, "y_mm": tag.center.y}
            for tag in scene.fiducials
        ],
    }
    image = Image.new("RGB", (1000, 820), "#0c1928")
    draw = ImageDraw.Draw(image)
    draw.text((35, 22), "NOMINAL SCHEMATIC - NOT A CAMERA FRAME", fill="#f9cb65")
    draw.text(
        (35, 44),
        "Source-bound dimensions; no hardware, calibration or physical accuracy verified.",
        fill="#d1dfec",
    )
    scale = min(880 / width, 650 / height)
    left, bottom = 60, 735

    def xy(x: float, y: float) -> tuple[float, float]:
        return left + x * scale, bottom - y * scale

    draw.rectangle(
        [xy(0, height), xy(width, 0)], fill="#e5dcc5", outline="#8eb9c7", width=3
    )
    for grid_x in range(0, int(width) + 1, 50):
        draw.line([xy(grid_x, 0), xy(grid_x, height)], fill="#c9c1ae")
    for grid_y in range(0, int(height) + 1, 50):
        draw.line([xy(0, grid_y), xy(width, grid_y)], fill="#c9c1ae")
    for device in geometry["devices"]:
        x, y, w, h = (device[key] for key in ("x_mm", "y_mm", "width_mm", "height_mm"))
        draw.rectangle(
            [xy(x, y + h), xy(x + w, y)], fill="#264b62", outline="#0e273b", width=2
        )
        label = f"{device['name'].upper()}  {w:g} x {h:g} mm"
        draw.text(xy(x + 4, y + h - 12), label, fill="#ffffff")
    for tag in geometry["tags"]:
        x, y = xy(tag["x_mm"], tag["y_mm"])
        draw.rectangle(
            (x - 9, y - 9, x + 9, y + 9), fill="#ffffff", outline="#222222", width=2
        )
        draw.text((x + 12, y - 5), tag["name"], fill="#111111")
    draw.text(
        (60, 752),
        f"Board {width:g} x {height:g} mm | origin front-left | +Y toward arm",
        fill="#d1dfec",
    )
    draw.text(
        (60, 774),
        "Target map is nominal. Never use this schematic as installed camera evidence.",
        fill="#f9cb65",
    )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return geometry, output.getvalue()


class ArrivalWizardService:
    """One local session; no device connection/resume or state writes on startup."""

    def __init__(
        self,
        workspace: Path,
        *,
        mode: str = "rehearsal",
        cell_id: str = "CELL-A",
        export_directory: Path | None = None,
        log_directory: Path | None = None,
        runner: Any = None,
        native_camera_provider: Any = None,
        helper_inspector: Any = None,
        helper_provider_factory: Any = None,
        endpoint_binding: Any = None,
        held_pair_binding: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if mode not in {"rehearsal", "physical"}:
            raise WizardError(
                "INVALID_MODE",
                "Select rehearsal or physical diagnostic mode explicitly.",
            )
        if type(cell_id) is not str or _CELL.fullmatch(cell_id) is None:
            raise WizardError("INVALID_CELL", "Use a bounded cell identifier.")
        self.workspace = require_regular_path(Path(workspace), directory=True)
        self.mode, self.cell_id = mode, cell_id
        self.session_id = "wizard-" + uuid.uuid4().hex
        self.source_sha256 = source_fingerprint(self.workspace)
        self._observed_source_sha256: str | None = self.source_sha256
        self._device_selection = WizardDeviceSelection(
            mode=mode, session_id=self.session_id, source_sha256=self.source_sha256
        )
        self._native_arm_report: dict[str, Any] | None = None
        self._native_arm_summary: dict[str, Any] | None = None
        self._native_arm_retained: dict[str, Any] | None = None
        self._passive_arm_retained: dict[str, Any] | None = None
        self._passive_arm_checkpoint: dict[str, Any] | None = None
        self._passive_arm_history: dict[str, Any] | None = None
        self._passive_arm_setup: dict[str, Any] | None = None
        self._passive_arm_outcome = None
        self._passive_arm_publication = None
        self._passive_arm_attempt_id = None
        self._physical_passive_history_files = None
        self._powered_arm_startup = None
        self._powered_feedback_rehearsal_original = None
        self._powered_feedback_process_original = None
        self._powered_feedback_history_files = None
        self._powered_feedback_attempt_id = None
        self._powered_feedback_outcome = None
        self._absolute_wrist_capture_choices = None
        self._powered_feedback_publication = None
        from .wizard_endpoint_coordinator import EndpointWizardBinding
        if endpoint_binding is not None and type(endpoint_binding) is not EndpointWizardBinding:
            raise WizardError('ENDPOINT_BINDING_INVALID','Trusted typed endpoint binding required.')
        self._endpoint_binding = endpoint_binding
        from .wizard_held_pair import HeldPairWizardBinding
        if held_pair_binding is not None and type(held_pair_binding) is not HeldPairWizardBinding:
            raise WizardError('PAIR_BINDING_INVALID','Trusted typed pair binding required.')
        self._held_pair_binding = held_pair_binding
        self._held_pair_attempted = False
        self._first_motion_attachment = None
        self._observational_request = None
        self._observational_configuration = None
        self._observational_sources = {}
        self._wrist_correction_configuration = None
        self._positional_campaign_configuration = None
        self._positional_campaign_confirmation = None
        self._positional_campaign_publication = None
        self._wrist_correction_confirmation = None
        self._wrist_correction_outcome = None
        self._wrist_correction_publication = None
        self._observational_confirmation = None
        self._observational_outcome = None
        self._observational_publication = None
        self._observational_operator_receipts = []
        self._first_motion_support_receipts = {}
        self._first_motion_observation_receipts = []
        self._first_motion_qualification_receipts = []
        self._first_motion_attempt_id = None
        self._first_motion_confirmation = None
        self._first_motion_outcome = None
        self._first_motion_publication = None
        self._endpoint_attempt_id = None
        self._endpoint_outcome = None
        self._endpoint_publication = None
        self._endpoint_confirmation = None
        self._native_arm_current = False
        self._native_arm_reason: str | None = None
        self._native_arm_review_sha256: str | None = None
        # File inspection and review are explicit actions. Neither these pure
        # registries nor the factory inspect files or invoke a helper at startup.
        self._helper_inspector = helper_inspector or inspect_camera_helper
        self._helper_provider_factory = (
            helper_provider_factory or create_metadata_provider
        )
        self._camera_helper = WizardCameraHelperRegistration(
            mode=mode, session_id=self.session_id, source_sha256=self.source_sha256
        )
        self._native_registration_managed = False
        # Preserve the incapable fixture/trusted injection test seam. Physical
        # launch defaults to no provider until the fixed-catalog review commits.
        self._native_fixture_provider = (
            native_camera_provider is None and mode == "rehearsal"
        )
        self._native_camera_provider = (
            RehearsalNativeCameraMetadataProvider()
            if self._native_fixture_provider
            else native_camera_provider
        )
        self._native_camera = WizardNativeCameraEnrollment(
            mode=mode,
            session_id=self.session_id,
            source_sha256=self.source_sha256,
            provider_descriptor=(
                None
                if self._native_camera_provider is None
                else dict(self._native_camera_provider.descriptor())
            ),
        )
        self.export_directory = (
            export_directory or self.workspace / "software/runs/wizard-exports"
        )
        self.log_directory = (
            log_directory or self.workspace / "software/runs/wizard-diagnostics"
        )
        self._exporter = WizardDiagnosticExporter(self.export_directory)
        self._log = WizardDiagnosticLog(
            self.log_directory,
            self.session_id,
            source_sha256=self.source_sha256,
            mode=mode,
        )
        self._runner = runner or DiagnosticProcessRunner(
            self.workspace, expected_source_sha256=self.source_sha256
        )
        self._clock = clock
        self._lock = threading.RLock()
        self._executor: ThreadPoolExecutor | None = None
        self._revision = 0
        self._state_epoch = 0
        self._state_revision_floor = 0
        self._tickets: dict[str, _Ticket] = {}
        self._operations: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._full_results: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._running: str | None = None
        self._cancel: threading.Event | None = None
        self._primary_operations = 0
        self._events: list[dict[str, Any]] = []
        self._exports: list[dict[str, Any]] = []
        # Created only after this launch logs a successful native review. An
        # imported enrollment/document never recreates this publication receipt.
        self._probe_metadata_publication: dict[str, Any] | None = None
        self._probe_dispatch_queue: dict[str, Any] | None = None
        self._probe_attempt_completion: dict[str, Any] | None = None
        self._configuration_wizard = CameraConfigurationWizard(self)
        self._operating_proposal = CameraOperatingProposalWizard(self)
        self._operating_assessment = CameraOperatingAssessmentWizard(self)
        self._operating_submission = CameraOperatingSubmissionWizard(self)
        self._images: dict[str, bytes] = {}
        self._source_changed = False
        self._log_error: dict[str, str] | None = None
        self._closed = False
        self._latest_by_section: dict[str, dict[str, Any]] = {}
        from rocell.application.commissioning_rehearsal_service import (
            CommissioningRehearsalService,
        )

        self._commissioning = CommissioningRehearsalService(
            self.workspace,
            self.log_directory.parent / "wizard-rehearsal" / self.session_id,
            source_sha256=self.source_sha256,
        )
        from rocell.application.physical_source_preflight_service import (
            PhysicalSourcePreflightService,
        )

        self._source_preflight = PhysicalSourcePreflightService(
            self.workspace, launch_id=self.session_id, source_sha256=self.source_sha256
        )
        from rocell.application.physical_camera_acquisition_service import (
            PhysicalCameraAcquisitionService,
        )

        self._physical_camera = PhysicalCameraAcquisitionService(
            self.workspace,
            launch_id=self.session_id,
            source_sha256=self.source_sha256,
            mode=mode,
        )
        from rocell.application.physical_camera_setup_service import (
            PhysicalCameraSetupService,
        )

        self._physical_camera_setup = PhysicalCameraSetupService(self._physical_camera)
        from rocell.application.physical_intake_evidence_service import (
            PhysicalIntakeEvidenceService,
        )

        self._physical_intake_evidence = PhysicalIntakeEvidenceService(
            self._physical_camera_setup
        )
        from rocell.application.physical_source_qualification_service import (
            PhysicalSourceQualificationService,
        )

        self._source_qualification = PhysicalSourceQualificationService(
            self._physical_camera_setup
        )
        from rocell.application.physical_static_camera_onboarding_service import (
            PhysicalStaticCameraOnboardingService,
        )

        self._static_camera_onboarding = PhysicalStaticCameraOnboardingService(
            self._physical_camera_setup
        )
        from rocell.application.physical_received_camera_service import (
            PhysicalReceivedCameraService,
        )

        self._received_camera = PhysicalReceivedCameraService(
            self._physical_camera_setup
        )
        from rocell.application.physical_camera_identity_service import (
            PhysicalCameraIdentityService,
        )

        self._camera_identity_records = PhysicalCameraIdentityService(
            self._physical_camera_setup
        )
        from rocell.application.physical_usb_identity_service import (
            PhysicalUsbIdentityService,
        )

        self._usb_identity = PhysicalUsbIdentityService(self._physical_camera_setup)
        # Immutable draft snapshots are separate from canonical stage evidence.
        # Only a successfully logged, unredacted action replaces this reference.
        self._physical_intake: PhysicalIntakeNotebook | None = None
        self._published_noncontact_sha256: str | None = None
        camera_profile = _profile(
            self.workspace,
            "software/config/camera_profiles/arducam_b0477_imx283_16mm.json",
        )
        arm_profile = _profile(self.workspace, "software/config/arm_connection.json")
        self._camera = {
            "status": "NOT_CONNECTED",
            "verification": "NOT_RUN",
            "description": "Static overhead Arducam B0477 / IMX283, purchased profile pending received-unit verification.",
            "profile_id": camera_profile.get("profile_id"),
            "identity": camera_profile.get("published_identity", {}),
            "interface": camera_profile.get("published_interface", {}),
            "optics": camera_profile.get("published_optics", {}),
            "image_id": None,
            "image_provenance": "NO_IMAGE",
            "physical_capture_available": False,
            "focus_warning": "Verify focus near the intended one-metre mounting height; the lens profile lists a 5 m-infinity default range.",
        }
        self._arm = {
            "status": "NOT_CONNECTED",
            "verification": "NOT_RUN",
            "description": "Waveshare RoArm-M3 Pro; metadata inspection is not a serial connection.",
            "profile": arm_profile,
            "physical_connection_available": False,
            "startup_warning": "Power-on/serial opening can cause controller reset or startup motion. This wizard cannot energize or initialize the arm.",
        }
        self._board: dict[str, Any] = {
            "status": "NOT_RENDERED",
            "coordinate_state": "NOMINAL_UNMEASURED",
            "geometry": None,
            "installed_calibration": "NOT_VERIFIED",
        }
        self._stages = [
            {
                "stage_id": stage.value,
                "title": stage.value.replace("_", " ").title(),
                "state": "PHYSICAL_PENDING",
                "description": "Rehearsal and notes cannot advance this physical stage.",
            }
            for stage in STAGE_ORDER
        ]

    def _changed(self, *, state: bool = False) -> None:
        self._revision += 1
        if state:
            self._state_epoch += 1
            self._state_revision_floor = self._revision

    def _invalidate_native_arm(self, reason: str) -> None:
        """Withdraw current correlation without altering retained observations."""
        self._native_arm_current = False
        self._native_arm_reason = reason

    def _arm_review_sha256(self) -> str | None:
        review = self._device_selection.reviewed_candidate("SERIAL")
        return (
            None
            if review is None
            else hashlib.sha256(_json_payload(review)).hexdigest()
        )

    def _native_arm_view(self) -> dict[str, Any]:
        # This is a cached/pure projection. It cannot query Windows or select a
        # port, even when the main app is in physical diagnostic mode.
        review_matches = self._native_arm_review_sha256 == self._arm_review_sha256()
        current = (
            self._native_arm_current
            and review_matches
            and not (self._source_changed or self._log_error or self._closed)
        )
        return {
            "schema": "rocell.wizard_native_arm_metadata_view.v1",
            "status": (
                "CURRENT"
                if current
                else (
                    "NOT_INSPECTED"
                    if self._native_arm_reason is None
                    and self._native_arm_report is None
                    and not self._closed
                    else "HISTORICAL_HELD"
                )
            ),
            "report": (deepcopy(self._native_arm_summary)),
            "invalidation_reason": (
                None
                if current
                else (
                    "APPLICATION_CLOSED"
                    if self._closed
                    else (
                        "ARM_METADATA_CONTEXT_CHANGED"
                        if self._native_arm_current and not review_matches
                        else self._native_arm_reason
                    )
                )
            ),
            "connected": False,
            "qualified": False,
            "physical_authority": False,
        }

    def _revoke_helper(self, reason: str, *, preserve_inspection: bool = False) -> None:
        """Retire callable metadata capability and dependent choices together."""
        if preserve_inspection:
            self._camera_helper.invalidate_review(reason)
        else:
            self._camera_helper.invalidate(reason)
        self._native_camera_provider = None
        self._native_camera.invalidate(reason)
        self._physical_camera.invalidate()
        self._physical_camera_setup.invalidate()
        self._source_qualification.invalidate()
        self._static_camera_onboarding.invalidate()
        self._received_camera.invalidate()
        self._camera_identity_records.invalidate()
        self._usb_identity.invalidate()

    def _append_event(self, kind: str, details: dict[str, Any]) -> bool:
        try:
            clean = sanitize_diagnostic_record(details, maximum_bytes=32 * 1024)
            record = self._log.append(kind, clean)
            self._events.append(record)
            self._changed()
            return True
        except Exception as exc:
            self._clear_camera_preview("DIAGNOSTIC_LOG_FAILED_NO_CURRENT_PREVIEW")
            self._device_selection.invalidate("DIAGNOSTIC_LOG_FAILED")
            self._invalidate_native_arm("DIAGNOSTIC_LOG_FAILED")
            self._revoke_helper("DIAGNOSTIC_LOG_FAILED")
            self._log_error = {
                "code": "DIAGNOSTIC_LOG_FAILED",
                "message": f"Diagnostic logging failed ({type(exc).__name__}); export available state and review the log folder. No automatic repair/resume.",
            }
            if self._cancel is not None:
                self._cancel.set()
            self._changed(state=True)
            return False

    def _clear_camera_preview(self, provenance: str) -> None:
        """Retire the served image and its association together under the lock."""
        self._images = {}
        self._camera["image_id"] = None
        self._camera["image_capture"] = None
        self._camera["image_provenance"] = provenance
        if provenance in {
            "SOURCE_CHANGED_NO_CURRENT_PREVIEW",
            "DIAGNOSTIC_LOG_FAILED_NO_CURRENT_PREVIEW",
            "REHEARSAL_HELD_NO_CURRENT_PREVIEW",
        }:
            self._commissioning.invalidate_camera_configuration()

    def _commissioning_view(self) -> dict[str, Any]:
        view = self._commissioning.view()
        noncontact_context = self._noncontact_publication_context(view)
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or noncontact_context is None
            or self._published_noncontact_sha256 != noncontact_context
        ):
            view["noncontact_evaluation"] = None
        if (
            self._running is not None
            and self._operations[self._running]["action_id"]
            in _PREVIEW_INVALIDATING_ACTIONS
        ):
            # A service can finish retention before Arrival logs completion.
            # Publish a new current readback only after that outer boundary.
            view["camera_configuration"] = None
            view["arm_feedback_process"] = None
        if self._source_changed or self._log_error or self._closed:
            # Historical raw evidence remains in the original M1 store and
            # operation result; a held launch cannot present it as current.
            view["arm_feedback_process"] = None
        if any(
            operation.get("completion_log_persisted") is not True
            and operation["action_id"] in _PREVIEW_INVALIDATING_ACTIONS
            for operation in self._operations.values()
        ):
            # Intent logging precedes `_running`, and `_finish` clears it before
            # the completion log. Neither gap may publish a current projection.
            view["arm_feedback_process"] = None
            view["camera_configuration"] = None
        latest_effect = next(
            (
                operation
                for operation in reversed(tuple(self._operations.values()))
                if operation["action_id"] in _PREVIEW_INVALIDATING_ACTIONS
            ),
            None,
        )
        if latest_effect is not None and latest_effect["status"] in {
            "FAILED",
            "CANCELLED",
            "TIMED_OUT",
        }:
            # Private M1 retention may have succeeded before an outer result or
            # publication failure. Keep its diagnostics, not a current success
            # card. A later explicit verified reopen can publish its own result.
            view["arm_feedback_process"] = None
        return view

    @staticmethod
    def _noncontact_publication_context(view: dict[str, Any]) -> str | None:
        value = view.get("noncontact_evaluation")
        if (
            value is None
            or view.get("status") in {"HELD", "REOPEN_HELD"}
            or view.get("quarantined")
            or view.get("unresolved_attempt_ids")
        ):
            return None
        return hashlib.sha256(
            _json_payload(
                {
                    "session_id": view["session_id"],
                    "challenge_sha256": view.get("challenge_sha256"),
                    "evaluation_sha256": value["evaluation_sha256"],
                    "stage": view["stage"],
                    "stage_state": view["stage_state"],
                }
            )
        ).hexdigest()

    def _physical_camera_view(self) -> dict[str, Any]:
        view = self._physical_camera.view()
        if view["publication"]["status"] == "PENDING":
            # Intent computation can finish before result logging. No new
            # current plan/frame is shown until the outer publication succeeds.
            view["plan"] = None
            view["reviewed_endpoint"] = None
            view["configuration"] = {
                "capabilities": None,
                "candidate": None,
                "readback": None,
            }
            view["last_frame"] = None
            view["status"] = "HELD"
        if self._source_changed or self._log_error or self._closed:
            view.update(
                status="HELD", plan=None, reviewed_endpoint=None, last_frame=None
            )
            view["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            view["configuration"] = {
                "capabilities": None,
                "candidate": None,
                "readback": None,
            }
            view["runtime_inspection"]["status"] = "HISTORICAL_HELD"
            view["runtime_inspection"]["publication"] = {
                "status": "HISTORICAL_HELD",
                "operation_id": None,
            }
        return view

    def _check_physical_camera_settings_identity(self) -> None:
        """Compare current reviewed metadata with the retained probe identity."""
        from .physical_camera_selection import selection_from_enrollment

        selected = selection_from_enrollment(
            self._native_camera,
            source_sha256=self.source_sha256,
            launch_session_id=self.session_id,
        )
        if selected.safe_summary() != self._physical_camera.view()["reviewed_endpoint"]:
            raise WizardError(
                "CAMERA_CONFIGURATION_IDENTITY",
                "The reviewed endpoint changed; the prior probe cannot supply settings for another camera.",
            )

    def _recheck_source(self, action_id: str) -> None:
        if action_id in _HOUSEKEEPING:
            return
        try:
            current = source_fingerprint(self.workspace)
            self._observed_source_sha256 = current
        except Exception as exc:
            current = None
            self._observed_source_sha256 = None
            self._source_changed = True
            self._clear_camera_preview("SOURCE_CHANGED_NO_CURRENT_PREVIEW")
            self._device_selection.invalidate("SOURCE_CHANGED")
            self._invalidate_native_arm("SOURCE_CHANGED")
            self._revoke_helper("SOURCE_CHANGED")
            self._changed(state=True)
            raise WizardError(
                "SOURCE_CHANGED",
                "Source verification failed. Export diagnostics and restart explicitly after review.",
            ) from exc
        if current != self.source_sha256:
            self._source_changed = True
            self._clear_camera_preview("SOURCE_CHANGED_NO_CURRENT_PREVIEW")
            self._device_selection.invalidate("SOURCE_CHANGED")
            self._invalidate_native_arm("SOURCE_CHANGED")
            self._revoke_helper("SOURCE_CHANGED")
            self._changed(state=True)
            raise WizardError(
                "SOURCE_CHANGED",
                "Source changed after launch. Export diagnostics and restart explicitly after review.",
            )

    def _trim_operations(self) -> None:
        """Rotate presentation history, never the separately pinned attempts."""
        while len(self._operations) > MAX_OPERATIONS:
            oldest = next(iter(self._operations))
            if oldest == self._running:
                break
            self._operations.pop(oldest)
            self._full_results.pop(oldest, None)

    def _load_bound_wrist_correction(self, operation_id):
        """Reconstruct a session-owned binding; caller holds the service lock.

        No cached success flag substitutes for the retained bytes and their
        underlying originals. This helper performs filesystem reads only.
        """
        from .first_motion_contract import canonical
        from .physical_onboarding_durability import contained_path,read_bounded_regular_file
        from .wrist_correction_assessment_binding import bind_saved_correction_assessment
        from rocell.providers.windows.endpoint_child_execution import decode_reviewed_controller_binding
        selected=self._operations.get(operation_id,{})
        if selected.get('action_id')!='bind_saved_wrist_correction' or selected.get('status')!='SUCCEEDED':
            raise WizardError('CORRECTION_BINDING_MISSING','Select a completed correction binding from this session.')
        report=deepcopy(selected['result']['steps'][0]['report'])
        def read(name):
            return read_bounded_regular_file(contained_path(self._log.root,name,label='correction setup original'),maximum_bytes=128*1024)
        if read(operation_id+'-bound-wrist-correction.json')!=canonical(report):
            raise WizardError('CORRECTION_BINDING_CHANGED','Retained correction binding changed.')
        source=self._observational_sources.get(report['source_id'])
        assessed=self._operations.get(report['assessment_operation_id'],{})
        if (source is None or source['session_id']!=self.session_id or source['source_sha256']!=self.source_sha256
                or assessed.get('action_id')!='assess_saved_wrist_correction' or assessed.get('status')!='SUCCEEDED'):
            raise WizardError('CORRECTION_SOURCE_CHANGED','Correction source or assessment changed.')
        controller_raw=read(source['source_id']+'-controller.json')
        protocol_raw=read(source['source_id']+'-protocol.json')
        if hashlib.sha256(protocol_raw).hexdigest()!=source['original_sha256']['protocol']:
            raise WizardError('CORRECTION_PROTOCOL_CHANGED','Reviewed correction protocol changed.')
        controller=decode_reviewed_controller_binding(controller_raw,expected_sha256=source['original_sha256']['controller'])
        assessment=read(report['assessment_operation_id']+'-saved-wrist-correction-assessment.json')
        bound=bind_saved_correction_assessment(assessment,
            expected_sha256=hashlib.sha256(canonical(assessed['result']['steps'][0]['report'])).hexdigest(),
            export_root=self.export_directory,controller=controller)
        if (bound.to_dict()!=report['binding'] or hashlib.sha256(bound.canonical_bytes).hexdigest()!=report['binding_sha256']):
            raise WizardError('CORRECTION_BINDING_CHANGED','Reconstructed correction binding differs.')
        return bound,controller_raw,protocol_raw,report

    def _bound_action(self, action: ActionDefinition) -> ActionDefinition:
        """Use the same cached closed choices for rendering and validation."""
        if action.action_id == 'stage_wrist_correction':
            options=tuple({'value':key,'label':key} for key,op in self._operations.items()
                if op.get('action_id')=='bind_saved_wrist_correction' and op.get('status')=='SUCCEEDED')
            return replace(action,fields=(dict(action.fields[0],options=options,default=None),))
        if action.action_id == 'bind_saved_wrist_correction':
            assessments=tuple({'value':key,'label':key} for key,op in self._operations.items()
                if op.get('action_id')=='assess_saved_wrist_correction' and op.get('status')=='SUCCEEDED')
            sources=tuple({'value':key,'label':receipt['label']} for key,receipt in self._observational_sources.items())
            return replace(action,fields=(dict(action.fields[0],options=assessments,default=None),
                dict(action.fields[1],options=sources,default=None)))
        absolute = (self._observational_configuration or {}).get('absolute_draft')
        if action.action_id == 'run_observational_movement' and absolute is not None:
            target = absolute.to_dict()['target_deg']
            return replace(action, label='Run one absolute wrist endpoint test',
                description=f'Move wrist pitch to absolute {target} degrees at spd 20, acc 1. Fresh baseline must match the reviewed start and bounded approach. No return or retry. Serial opening can cause startup movement; cancellation is not an emergency stop.',
                fields=tuple(dict(field, label=f'I accept only absolute wrist target {target} degrees, with no return or retry.')
                    if field['name'] == 'bounded_policy_accepted' else field for field in action.fields))
        if action.action_id == 'setup_observational_movement':
            options = tuple({'value':key, 'label':receipt['label']} for key,receipt in self._observational_sources.items())
            absolute_options = ({'value':'relative', 'label':'Relative increment (1 or 5 degrees)'},) + tuple(
                {'value':item['draft_sha256'], 'label':f'Absolute {item["draft"]["target_deg"]} degrees from retained telemetry'}
                for item in (self._absolute_wrist_capture_choices or {}).get('choices', []))
            return replace(action, fields=({**action.fields[0], 'options':options, 'default':None},)+tuple(
                dict(field, options=absolute_options) if field['name'] == 'absolute_draft' else field
                for field in action.fields[1:]))
        if action.action_id == 'review_first_motion_qualification':
            options = tuple({'value': key, 'label': key} for key, op in self._operations.items()
                if op.get('action_id') == 'assess_first_motion_qualification' and op.get('status') == 'SUCCEEDED')
            return replace(action, fields=tuple(dict(field, options=options, default=None)
                if field['name'] == 'assessment_operation_id' else field for field in action.fields))
        if action.action_id == 'assess_first_motion_qualification':
            options = tuple({'value': receipt['operation_id'], 'label': receipt['operation_id']+' / '+receipt['outcome']}
                for _, receipt in self._first_motion_observation_receipts
                if self._operations.get(receipt['operation_id'], {}).get('status') == 'SUCCEEDED')
            return replace(action, fields=(dict(action.fields[0], options=options, default=None),))
        if action.action_id == 'record_observational_movement':
            from .first_motion_contract import canonical
            outcome, request = self._observational_outcome, self._observational_request
            options = ()
            if absolute is None and request is not None and outcome is not None and type(outcome.report) is dict:
                attempt = request.to_dict()['attempt_id']
                options = ({'value':attempt+'@'+hashlib.sha256(canonical(outcome.report)).hexdigest(),
                            'label':attempt+' / '+outcome.report.get('status','UNKNOWN')},)
            return replace(action, fields=({**action.fields[0], 'options':options, 'default':None},)+action.fields[1:])
        if action.action_id == 'record_first_motion_observation':
            outcome = self._first_motion_outcome
            options = ()
            if self._first_motion_attempt_id is not None and outcome is not None and type(outcome.report) is dict:
                from .first_motion_contract import canonical
                options = ({'value': self._first_motion_attempt_id+'@'+hashlib.sha256(canonical(outcome.report)).hexdigest(),
                            'label': self._first_motion_attempt_id+' / '+outcome.report.get('status','UNKNOWN')},)
            return replace(action, fields=tuple(dict(field, options=options, default=None)
                if field['name'] == 'trial' else field for field in action.fields))
        if action.action_id in ('review_retained_first_motion_draft', 'attach_retained_first_motion'):
            options = tuple({'value': key, 'label': key} for key, op in self._operations.items()
                if op.get('action_id') == 'create_first_motion_draft' and op.get('status') == 'SUCCEEDED')
            fields = []
            for field in action.fields:
                if field['name'] == 'draft_operation_id':
                    fields.append(dict(field, options=options, default=None))
                elif action.action_id == 'attach_retained_first_motion':
                    approvals = []
                    for key, op in self._operations.items():
                        steps = (op.get('result') or {}).get('steps', [])
                        report = steps[0].get('report', {}) if len(steps) == 1 else {}
                        if (op.get('action_id') in ('review_retained_first_motion_draft','record_first_motion_engineering_review')
                                and op.get('status') == 'SUCCEEDED' and report.get('review', {}).get('decision') == 'APPROVED'
                                and report.get('review', {}).get('check') == field['name']):
                            approvals.append({'value': key, 'label': key+' / selection '+report.get('selection_sha256','')})
                    fields.append(dict(field, options=tuple(approvals), default=None))
                else:
                    fields.append(field)
            return replace(action, fields=tuple(fields))
        if action.action_id == 'create_first_motion_draft':
            choices = {
                'measurement_operation_id': tuple(key for key, op in self._operations.items()
                    if op.get('action_id') == 'record_first_motion_measurements' and op.get('status') == 'SUCCEEDED'),
                'support_record_id': tuple(self._first_motion_support_receipts),
            }
            return replace(action, fields=tuple(dict(field, options=tuple(
                {'value': key, 'label': key} for key in choices[field['name']]), default='')
                                                for field in action.fields))
        if action.worker == "physical_usb_identity":
            return replace(
                action, fields=tuple(self._usb_identity.fields(action.action_id))
            )
        if action.worker == "physical_camera_identity_records":
            return replace(
                action,
                fields=tuple(self._camera_identity_records.fields(action.action_id)),
            )
        if action.worker == "physical_received_camera":
            return replace(
                action, fields=tuple(self._received_camera.fields(action.action_id))
            )
        if action.worker == "physical_static_camera_onboarding":
            return replace(
                action,
                fields=tuple(self._static_camera_onboarding.fields(action.action_id)),
            )
        if action.worker == "physical_source_qualification":
            return replace(
                action,
                fields=tuple(self._source_qualification.fields(action.action_id)),
            )
        if action.action_id == "physical_intake_submit":
            return replace(
                action,
                fields=(
                    *self._physical_intake_evidence.submission_fields(
                        self._physical_intake
                    ),
                    *action.fields,
                ),
            )
        if action.action_id == "physical_intake_record":
            options = (
                self._physical_intake.choices()
                if self._physical_intake is not None and self._intake_is_current()
                else []
            )
            return replace(
                action,
                fields=({**action.fields[0], "options": options}, *action.fields[1:]),
            )
        if action.action_id == "rehearsal_camera_configuration":
            return replace(
                action, fields=self._commissioning.camera_configuration_fields()
            )
        if action.action_id == "physical_camera_configuration":
            return replace(action, fields=self._physical_camera.configuration_fields())
        if action.action_id == CONFIGURATION_EXPORT:
            return replace(action, fields=self._configuration_wizard.export_fields())
        if action.action_id == OPERATING_ASSESSMENT:
            return replace(action, fields=self._operating_assessment.fields())
        if action.action_id == OPERATING_SUBMISSION:
            return replace(action, fields=self._operating_submission.fields())
        if action.action_id == "camera_helper_inspect" and self.mode == "rehearsal":
            scenario = {
                "name": "scenario",
                "label": "Helper inspection fixture scenario",
                "type": "select",
                "required": True,
                "default": "nominal",
                "options": [
                    {"value": name, "label": name.replace("-", " ")}
                    for name in ("nominal", "missing-helper", "hash-drift")
                ],
            }
            return replace(action, fields=(scenario, *action.fields))
        if action.action_id in _NATIVE_CHOICES:
            field = {**action.fields[0], "options": self._native_camera.choices()}
            field.pop("default", None)
            return replace(action, fields=(field, *action.fields[1:]))
        if (
            action.action_id == "native_camera_inventory"
            and self._native_fixture_provider
        ):
            scenario = {
                "name": "scenario",
                "label": "Native metadata fixture scenario",
                "type": "select",
                "required": True,
                "default": "nominal",
                "options": [
                    {"value": name, "label": name.replace("-", " ")}
                    for name in (
                        "nominal",
                        "missing-mapping",
                        "wrong-device",
                        "duplicate-name",
                    )
                ],
            }
            return replace(action, fields=(scenario, *action.fields))
        if action.action_id in _CANDIDATE_ACTIONS:
            options = self._device_selection.choices(
                _CANDIDATE_ACTIONS[action.action_id]
            )
            field = {**action.fields[0], "options": options}
            field.pop("default", None)
            return replace(action, fields=(field, *action.fields[1:]))
        if action.action_id == "physical_camera_reopen":
            field = {
                **action.fields[0],
                "options": self._physical_camera_setup.reopen_choices(),
            }
            field.pop("default", None)
            return replace(action, fields=(field, *action.fields[1:]))
        if action.action_id != "rehearsal_reopen":
            return action
        choices = self._commissioning.reopen_choices()
        options = [
            {
                "value": item["choice_id"],
                "label": (
                    item["session_id"]
                    + " — "
                    + Path(item["directory"]).name
                    + (
                        " — source matches"
                        if item["source_matches"]
                        else " — SOURCE DIFFERS: inspection hold"
                    )
                ),
            }
            for item in choices
        ]
        field = {
            **action.fields[0],
            "options": options,
        }
        field.pop("default", None)  # An original store must be chosen explicitly.
        return replace(action, fields=(field,))

    def _passive_setup_context(self) -> dict[str, Any]:
        """Bind a current original setup, not a browser-supplied receipt."""
        saved = self._passive_arm_setup or {}
        steps = saved.get("steps", [])
        report = steps[0].get("report", {}) if steps else {}
        current = self._native_arm_view()
        age = time.monotonic_ns() - report.get("recorded_monotonic_ns", 0)
        if (
            saved.get("status") != "SUCCEEDED"
            or report.get("status") != "SETUP_RECORDED_NOT_CONNECTED"
            or not 0 <= age <= 300_000_000_000
            or current.get("status") != "CURRENT"
            or report.get("native_report_sha256")
            != (current.get("report") or {}).get("report_sha256")
        ):
            raise WizardError(
                "PASSIVE_SETUP_REQUIRED",
                "Record fresh USB-only setup against current correlated metadata first.",
            )
        return dict(
            setup_operation_id=Path(report["path"]).name.removesuffix(
                "-passive-setup-original.json"
            ),
            expected_setup_sha256=report["sha256"],
            arm_review_sha256=self._arm_review_sha256(),
        )

    def _powered_setup_context(self) -> dict[str, Any]:
        saved = self._powered_arm_startup or {}
        steps = saved.get("steps", [])
        report = steps[0].get("report", {}) if steps else {}
        current = self._native_arm_view()
        age = time.monotonic_ns() - report.get("recorded_monotonic_ns", 0)
        if (
            saved.get("status") != "SUCCEEDED"
            or report.get("status") != "POWERED_STARTUP_RECORDED_NOT_AUTHORIZED"
            or not 0 <= age <= 300_000_000_000
            or current.get("status") != "CURRENT"
            or (current.get("report") or {}).get("status") != "METADATA_CORRELATED"
        ):
            raise WizardError(
                "POWERED_SETUP_REQUIRED",
                "Record fresh powered startup and correlate current USB metadata before the feedback query.",
            )
        return {
            "startup_operation_id": Path(report["path"]).name.removesuffix(
                "-powered-startup-original.json"
            ),
            "expected_startup_sha256": report["sha256"],
            "arm_review_sha256": self._arm_review_sha256(),
            "native_report_sha256": current["report"]["report_sha256"],
        }

    def configure_observational_movement(self, *, controller_binding, protocol_original, direction=-1):
        """Trusted host staging, not a browser upload or movement authorization.

        Reuse reviewed controller/protocol originals. Staging is untimed; the
        subsequent final click creates a short-lived signed request once only.
        """
        return self._configure_observational_movement(controller_binding=controller_binding,
            protocol_original=protocol_original, direction=direction)

    def configure_positional_campaign(self, *, usb_identity, start_joints_rad, targets_rad, originals):
        """Trusted host intake only; not a browser evidence/command endpoint."""
        return self._configure_campaign(dict(usb_identity=usb_identity,start_joints_rad=start_joints_rad,
            targets_rad=targets_rad,originals=originals))

    def configure_model_corrected_campaign(self, *, usb_identity, start_joints_rad, originals,
            model_raw, expected_model_sha256, exports):
        """Stage one model experiment through the existing reviewed wizard slot."""
        return self._configure_campaign(dict(usb_identity=usb_identity,start_joints_rad=start_joints_rad,
            originals=originals,model_raw=model_raw,expected_model_sha256=expected_model_sha256,
            exports=exports),corrected=True)

    def configure_base_mapping_probe(self, *, usb_identity, start_joints_rad, delta_deg, originals, synchronize=False):
        """Trusted-host one-degree base probe, sharing the one-use wizard slot."""
        return self._configure_campaign(dict(usb_identity=usb_identity,start_joints_rad=start_joints_rad,
            delta_deg=delta_deg,originals=originals,synchronize=synchronize),base=True)

    def configure_base_midpoint_probe(self, *, usb_identity, start_joints_rad, target_name, originals):
        """Stage one fixed uncorrected held-out target in the ordinary wizard slot."""
        return self._configure_campaign(dict(usb_identity=usb_identity,start_joints_rad=start_joints_rad,
            target_name=target_name,originals=originals),midpoint=True)

    def configure_base_compensation_experiment(self, *, usb_identity, start_joints_rad,
            originals, model_raw, expected_model_sha256, training_exports, held_out, experiment_kind, direction='INCREASING'):
        """Evidence-backed local base pair through the existing one-use UI slot."""
        return self._configure_campaign(dict(usb_identity=usb_identity,start_joints_rad=start_joints_rad,
            originals=originals,model_raw=model_raw,expected_model_sha256=expected_model_sha256,
            training_exports=training_exports,held_out=held_out,experiment_kind=experiment_kind,direction=direction),base_experiment=True)

    def configure_base_alternating_sequence(self, **staging_arguments):
        """Trusted-host fixed route; browser review uses the existing one-use slot."""
        return self._configure_campaign(staging_arguments,base_sequence=True)

    def configure_base_speed_experiment(self, **staging_arguments):
        """Trusted-host speed-10 experiment in the existing one-use wizard slot."""
        return self._configure_campaign(staging_arguments,base_speed=True)

    def configure_roll_mapping_probe(self, **staging_arguments):
        """Trusted-host one-degree wrist-roll probe through the one-use UI slot."""
        return self._configure_campaign(staging_arguments,roll=True)

    def configure_roll_fixed_probe(self, **staging_arguments):
        """Fixed raw roll target, distinct from the relative one-degree profile."""
        return self._configure_campaign(staging_arguments,roll_fixed=True)

    def configure_roll_persistence_probe(self, **staging_arguments):
        """Stage one command with an explicitly previewed 35-second observation."""
        return self._configure_campaign(staging_arguments,roll_persistence=True)

    def configure_roll_long_fixed_probe(self, **staging_arguments):
        """Stage an enumerated fixed target and 35-second observation."""
        return self._configure_campaign(staging_arguments,roll_long_fixed=True)

    def configure_roll_target_variation(self, **staging_arguments):
        """Trusted-host named-case selection; existing wizard review starts it."""
        return self._configure_campaign(staging_arguments,roll_variation=True)

    def _configure_campaign(self, staging_arguments, *, corrected=False, base=False, midpoint=False, base_experiment=False, base_sequence=False, base_speed=False, roll=False, roll_fixed=False, roll_persistence=False, roll_long_fixed=False, roll_variation=False):
        from .wizard_positional_campaign_coordinator import stage_positional_campaign
        from .wizard_positional_campaign_coordinator import stage_model_corrected_campaign
        from .wizard_positional_campaign_coordinator import stage_base_mapping_probe
        from .wizard_positional_campaign_coordinator import stage_base_midpoint_probe
        from .wizard_positional_campaign_coordinator import stage_base_compensation_experiment
        from .wizard_positional_campaign_coordinator import stage_base_alternating_sequence
        from .wizard_positional_campaign_coordinator import stage_base_speed_experiment
        from .wizard_positional_campaign_coordinator import stage_roll_mapping_probe
        from .wizard_positional_campaign_coordinator import stage_roll_fixed_probe
        from .wizard_positional_campaign_coordinator import stage_roll_persistence_probe, stage_roll_long_fixed_probe
        from .wizard_positional_campaign_coordinator import stage_roll_target_variation
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running or self._log_error
                    or self._positional_campaign_configuration is not None
                    or self._observational_confirmation is not None
                    or self._wrist_correction_confirmation is not None
                    or self._first_motion_attempt_id is not None or self._endpoint_attempt_id is not None):
                raise WizardError('CAMPAIGN_SETUP_HELD','Use an idle physical session without a consumed motion attempt.')
            context = self._powered_setup_context()
            self._recheck_source('run_positional_campaign')
            if not self._append_event('positional_campaign_staging_started', dict(physical_authority=False)):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Cannot begin campaign staging.')
            self.export_directory.mkdir(parents=True, exist_ok=True)
            from .physical_onboarding_durability import safe_root
            safe_root(self.export_directory)
            stage = stage_roll_target_variation if roll_variation else stage_roll_long_fixed_probe if roll_long_fixed else stage_roll_persistence_probe if roll_persistence else stage_roll_fixed_probe if roll_fixed else stage_roll_mapping_probe if roll else stage_base_speed_experiment if base_speed else stage_base_alternating_sequence if base_sequence else stage_base_compensation_experiment if base_experiment else stage_base_midpoint_probe if midpoint else stage_base_mapping_probe if base else stage_model_corrected_campaign if corrected else stage_positional_campaign
            staged = stage(self.workspace, root=self._log.root,
                session_id=self.session_id, **staging_arguments)
            if self._powered_setup_context() != context:
                raise WizardError('CAMPAIGN_SETUP_CHANGED','Powered setup changed during staging.')
            preview = staged.preview()
            if not self._append_event('positional_campaign_staged', preview):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Cannot retain campaign staging event.')
            self._positional_campaign_configuration = dict(staged=staged, preview=preview, context=context)
            self._changed(state=True)
            return deepcopy(preview)

    def configure_absolute_wrist_movement(self, *, controller_binding, protocol_original, draft):
        """Trusted-host attachment of a typed endpoint draft; never browser JSON.

        Reuses the wizard's single-attempt slot, context checks and final click.
        The child still verifies a fresh six-joint baseline before dispatch.
        """
        from rocell.motion.absolute_wrist_diagnostic import AbsoluteWristDiagnosticDraft
        if type(draft) is not AbsoluteWristDiagnosticDraft:
            raise WizardError('ABSOLUTE_DRAFT_REQUIRED', 'An exact host-reviewed endpoint draft is required.')
        return self._configure_observational_movement(controller_binding=controller_binding,
            protocol_original=protocol_original, direction=draft.to_dict()['direction'], absolute_draft=draft)

    def retain_reviewed_observational_sources(self, *, controller_binding, protocol_original, label):
        """Trusted host intake of already reviewed sources; never a browser upload.

        This call asserts review provenance, not a fresh operator clearance or
        motion approval. File hashes establish association, not semantic truth.
        """
        return self._retain_reviewed_observational_sources(controller_binding=controller_binding,
            protocol_original=protocol_original, label=label)

    def _retain_reviewed_observational_sources(self, *, controller_binding, protocol_original, label, owner=None, onboarding=None):
        from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
        from .physical_connection_contracts import EvidenceOrigin
        from .physical_onboarding_durability import publish_reservation_bytes
        from .first_motion_contract import canonical
        from .wizard_diagnostic_coordinator import decode_diagnostic_json
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running != owner or self._log_error
                    or self._observational_configuration is not None or len(self._observational_sources) >= 8):
                raise WizardError('OBSERVATIONAL_SOURCE_HELD','Use an idle physical session before staging.')
            if (type(controller_binding) is not ReviewedControllerBinding
                    or controller_binding.origin is not EvidenceOrigin.PHYSICAL_OBSERVATION
                    or type(protocol_original) is not bytes or not 0 < len(protocol_original) <= 128*1024
                    or type(label) is not str or not 1 <= len(label.strip()) <= 128):
                raise WizardError('OBSERVATIONAL_SOURCE_INVALID','Typed reviewed controller, protocol original and label required.')
            protocol = decode_diagnostic_json(protocol_original, maximum=128*1024)
            if type(protocol) is not dict or not protocol or canonical(protocol) != protocol_original:
                raise WizardError('OBSERVATIONAL_SOURCE_INVALID','Canonical structured reviewed protocol required.')
            self._recheck_source('setup_observational_movement')
            source_id = 'observational-source-'+uuid.uuid4().hex
            if not self._append_event('observational_sources_intake', dict(source_id=source_id, physical_authority=False)):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Cannot retain reviewed sources.')
            hashes = {}
            for kind, raw in (('controller',canonical(controller_binding.to_dict())), ('protocol',protocol_original)):
                publish_reservation_bytes(self._log.root, source_id+'-'+kind+'.json', raw, maximum_bytes=128*1024)
                hashes[kind] = hashlib.sha256(raw).hexdigest()
            receipt = dict(source_id=source_id, label=label, session_id=self.session_id,
                source_sha256=self.source_sha256, original_sha256=hashes,
                provenance='TRUSTED_HOST_REVIEWED_INPUT', motion_authorized=False)
            if onboarding is not None:
                receipt['onboarding'] = deepcopy(onboarding)
            if not self._append_event('observational_sources_retained', receipt):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Sources were not committed as selectable.')
            self._observational_sources[source_id] = receipt
            self._changed(state=True)
            return deepcopy(receipt)

    def _configure_observational_movement(self, *, controller_binding, protocol_original, direction=-1, owner=None, degrees=1, absolute_draft=None):
        from rocell.providers.windows.arm_feedback_worker import ReviewedControllerBinding
        from .physical_connection_contracts import EvidenceOrigin
        from .observational_worker_preparation import stage_observational_runtime
        from .first_motion_contract import canonical
        from rocell.motion.observational_wrist_plan import ONE_DEGREE_POLICY, FIVE_DEGREE_POLICY
        if absolute_draft is not None:
            from rocell.motion.absolute_wrist_diagnostic import AbsoluteWristDiagnosticDraft
            from .absolute_wrist_worker_preparation import stage_absolute_wrist_runtime
            if type(absolute_draft) is not AbsoluteWristDiagnosticDraft:
                raise WizardError('ABSOLUTE_DRAFT_REQUIRED', 'Exact typed draft required.')
            stage_observational_runtime = stage_absolute_wrist_runtime
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running != owner
                    or self._log_error or self._observational_configuration is not None
                    or self._first_motion_attempt_id is not None or self._endpoint_attempt_id is not None):
                raise WizardError('OBSERVATIONAL_SETUP_HELD','Use an idle physical session with no prior motion attempt.')
            if (type(controller_binding) is not ReviewedControllerBinding
                    or controller_binding.origin is not EvidenceOrigin.PHYSICAL_OBSERVATION
                    or type(direction) is not int or direction not in (-1, 1)
                    or type(degrees) is not int or degrees not in (1, 5)):
                raise WizardError('OBSERVATIONAL_SETUP_INVALID','Reviewed physical controller and bounded direction required.')
            self._recheck_source('run_observational_movement')
            context = self._powered_setup_context()
            self._append_event('observational_staging_started', {'physical_authority':False})
            if self._log_error:
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Staging could not be logged.')
            staged = stage_observational_runtime(self.workspace, root=self._log.root,
                attempt_id='operation-'+uuid.uuid4().hex,
                controller_original=canonical(controller_binding.to_dict()), protocol_original=protocol_original)
            identity = controller_binding.identity
            config = dict(staged=staged, context=context, direction=direction, degrees=degrees,
                policy=ONE_DEGREE_POLICY if degrees == 1 else FIVE_DEGREE_POLICY,
                usb_identity=dict(vid=int(identity.vid,16), pid=int(identity.pid,16), serial_number=identity.unit_serial))
            if absolute_draft is not None:
                config['absolute_draft'] = absolute_draft
                config['policy'] = 'ABSOLUTE_WRIST_ENDPOINT_V1'
            if self._powered_setup_context() != context:
                raise WizardError('OBSERVATIONAL_SETUP_CHANGED','Setup changed during staging.')
            if not self._append_event('observational_staged', dict(attempt_id=staged.attempt_id,
                    direction=direction, degrees=degrees if absolute_draft is None else None, policy=config['policy'],
                    usb_identity=config['usb_identity'], physical_authority=False,
                    absolute_draft=absolute_draft.to_dict() if absolute_draft is not None else None)):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Staged runtime was not committed for use.')
            self._observational_configuration = config
            self._changed(state=True)
            return dict(attempt_id=staged.attempt_id, direction=direction,
                policy=(f'Absolute wrist target {absolute_draft.to_dict()["target_deg"]} degrees; spd 20, acc 1; no return or retry.'
                    if absolute_draft is not None else f'{degrees} degrees of wrist pitch from owned baseline; spd 20, acc 1; no return or retry.'),
                motion_authorized=False)

    def retain_first_motion_support(self, *, supporting_originals):
        """Trusted-host retention, not review or a browser upload endpoint.

        Preserve originals byte-for-byte. Only a completely published and logged
        set becomes selectable in this session. A failed publication leaves its
        files for diagnosis; it is never silently adopted on restart.
        """
        from .first_motion_reference_reader import ORIGINAL_REFERENCES
        from .physical_onboarding_durability import publish_reservation_bytes
        from .wizard_diagnostic_coordinator import decode_diagnostic_json
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running is not None
                    or self._log_error or self._first_motion_attempt_id is not None):
                raise WizardError('FIRST_MOTION_SUPPORT_HELD', 'Use an idle physical wizard before commissioning.')
            names = ORIGINAL_REFERENCES - {'independent_posture_review_sha256'}
            if type(supporting_originals) is not dict or set(supporting_originals) != names:
                raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Seven exact supporting originals required; posture is selected separately.')
            originals = dict(supporting_originals)
            # Validate the whole set before any write. JSON structure and hashes
            # demonstrate retention integrity, never semantic or physical truth.
            for raw in originals.values():
                if type(raw) is not bytes or not 0 < len(raw) <= 128 * 1024:
                    raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Bounded immutable original bytes required.')
                value = decode_diagnostic_json(raw, maximum=128 * 1024)
                if type(value) is not dict or not value:
                    raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Nonempty structured original required.')
            self._recheck_source('record_first_motion_measurements')
            record_id = 'support-' + uuid.uuid4().hex
            # The log owns creation of its session directory. Record intent
            # before publication, but do not make that intent selectable.
            if not self._append_event('first_motion_support_retention_started',
                                      dict(record_id=record_id, motion_authorized=False)):
                raise WizardError('DIAGNOSTIC_LOG_FAILED', 'Could not start supporting-original retention.')
            hashes = {}
            for name in sorted(originals):
                raw = originals[name]
                publish_reservation_bytes(self._log.root, record_id+'-'+name+'.json',
                                          raw, maximum_bytes=128 * 1024)
                hashes[name] = hashlib.sha256(raw).hexdigest()
            self._recheck_source('record_first_motion_measurements')
            receipt = dict(record_id=record_id, session_id=self.session_id,
                source_sha256=self.source_sha256, original_sha256=hashes,
                status='ORIGINALS_RETAINED_NOT_REVIEWED', motion_authorized=False,
                semantic_compatibility_verified=False)
            if not self._append_event('first_motion_support_retained', receipt):
                raise WizardError('DIAGNOSTIC_LOG_FAILED', 'Supporting originals were not committed as selectable evidence.')
            self._first_motion_support_receipts[record_id] = deepcopy(receipt)
            return deepcopy(receipt)

    def create_first_motion_draft_from_retained(self, *, measurement_operation_id, support_record_id):
        """Resolve a same-session receipt, not caller paths, hashes or raw posture.

        No latest-file search, implicit recovery, retiming, signing or device
        access. Subsequent engineering reviews must assess the actual originals.
        """
        return self._create_first_motion_draft_from_retained(measurement_operation_id=measurement_operation_id,
                                                            support_record_id=support_record_id)

    def _create_first_motion_draft_from_retained(self, *, measurement_operation_id, support_record_id, owner_operation=None):
        from .physical_onboarding_durability import contained_path, read_bounded_regular_file
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running != owner_operation
                    or self._log_error or self._first_motion_attempt_id is not None):
                raise WizardError('FIRST_MOTION_SUPPORT_HELD', 'Use an idle physical wizard before commissioning.')
            if type(support_record_id) is not str or support_record_id not in self._first_motion_support_receipts:
                raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Select this session\'s successfully retained supporting record.')
            receipt = self._first_motion_support_receipts[support_record_id]
            if receipt['session_id'] != self.session_id or receipt['source_sha256'] != self.source_sha256:
                raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Supporting record context changed.')
            originals = {}
            for name, digest in receipt['original_sha256'].items():
                raw = read_bounded_regular_file(contained_path(self._log.root,
                    support_record_id+'-'+name+'.json', label='supporting original'), maximum_bytes=128 * 1024)
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Retained supporting original changed.')
                originals[name] = raw
            if owner_operation is None:
                return self.create_first_motion_draft(measurement_operation_id=measurement_operation_id,
                                                      supporting_originals=originals)
            return self._create_first_motion_draft(measurement_operation_id=measurement_operation_id,
                supporting_originals=originals, owner_operation=owner_operation)

    def create_first_motion_draft(self, *, measurement_operation_id, supporting_originals):
        """Trusted host draft assembly from a successful local measurement receipt.

        Supporting originals exclude posture: the host resolves that original
        from its own operation log, never from a supplied file path or hash.
        This records a reviewable draft, not a configured or authorized run.
        """
        return self._create_first_motion_draft(measurement_operation_id=measurement_operation_id,
                                               supporting_originals=supporting_originals)

    def _create_first_motion_draft(self, *, measurement_operation_id, supporting_originals, owner_operation=None):
        from .first_motion_draft import draft_from_originals
        from .first_motion_reference_reader import ORIGINAL_REFERENCES
        from .physical_onboarding_durability import contained_path, read_bounded_regular_file
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running != owner_operation
                    or self._log_error or self._first_motion_attempt_id is not None):
                raise WizardError('FIRST_MOTION_DRAFT_HELD','Use an idle physical wizard before any commissioning attempt.')
            if (type(measurement_operation_id) is not str
                    or not re.fullmatch(r'operation-[a-f0-9]{32}', measurement_operation_id)
                    or type(supporting_originals) is not dict
                    or set(supporting_originals) != ORIGINAL_REFERENCES-{'independent_posture_review_sha256'}):
                raise WizardError('FIRST_MOTION_DRAFT_INVALID','Select one retained measurement operation and seven supporting originals.')
            operation = self._operations.get(measurement_operation_id, {})
            steps = (operation.get('result') or {}).get('steps', [])
            report = steps[0].get('report', {}) if len(steps) == 1 else {}
            if (operation.get('action_id') != 'record_first_motion_measurements'
                    or operation.get('status') != 'SUCCEEDED'):
                raise WizardError('FIRST_MOTION_DRAFT_INVALID','Measurement must be a successful operation in this session.')
            raw = read_bounded_regular_file(contained_path(self._log.root,
                measurement_operation_id+'-first-motion-measurement-original.json', label='selected measurement'), maximum_bytes=8192)
            if hashlib.sha256(raw).hexdigest() != report.get('original_sha256'):
                raise WizardError('FIRST_MOTION_DRAFT_INVALID','Retained measurement differs from its successful receipt.')
            originals = dict(supporting_originals)
            originals['independent_posture_review_sha256'] = raw
            def current():
                if (self._closed or self._running != owner_operation or self._log_error
                        or (owner_operation is not None and self._cancel is not None and self._cancel.is_set())):
                    raise WizardError('FIRST_MOTION_CONTEXT_CHANGED','Draft context unavailable.')
                self._recheck_source('record_first_motion_measurements')
            draft = draft_from_originals(self.workspace, reference_originals=originals,
                session_id=self.session_id, measurement_operation_id=measurement_operation_id,
                check_current=current)
            if not self._append_event('first_motion_draft_created', dict(
                    measurement_operation_id=measurement_operation_id,
                    selection_sha256=draft.selection_sha256, preview=draft.preview(), motion_authorized=False)):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Could not retain the generated draft.')
            return draft

    def select_first_motion_measurement(self, *, request, operation_id):
        """Trusted host selection of this session's original; no admission/signing.

        Receipt identity is resolved here, not accepted as browser-provided
        evidence. The loader re-reads the immutable file and recomputes bounds.
        """
        return self._select_first_motion_measurement(request=request, operation_id=operation_id)

    def _select_first_motion_measurement(self, *, request, operation_id, owner=None, check=None):
        from .first_motion_contract import FirstMotionRequest
        from .first_motion_measurements import load_measurement_for_request
        with self._lock:
            if check is not None: check()
            if self.mode!='physical' or self._closed or self._running != owner:
                raise WizardError('FIRST_MOTION_SELECTION_HELD','Use an idle physical wizard for original selection.')
            if type(request) is not FirstMotionRequest or type(operation_id) is not str:
                raise WizardError('FIRST_MOTION_SELECTION_INVALID','Typed request and retained operation required.')
            operation=self._operations.get(operation_id,{})
            steps=(operation.get('result') or {}).get('steps',[])
            report=steps[0].get('report',{}) if len(steps)==1 else {}
            if (operation.get('action_id')!='record_first_motion_measurements'
                    or operation.get('status')!='SUCCEEDED'
                    or report.get('original_sha256')!=request.to_dict()['references']['independent_posture_review_sha256']):
                raise WizardError('FIRST_MOTION_SELECTION_INVALID','Select this session\'s successful exact measurement receipt.')
            def current():
                if check is not None: check()
                if self._closed or self._running != owner or self._log_error:
                    raise WizardError('FIRST_MOTION_CONTEXT_CHANGED','Measurement context is unavailable.')
                self._recheck_source('record_first_motion_measurements')
            raw,association=load_measurement_for_request(request,root=self._log.root,
                session_id=self.session_id,operation_id=operation_id,check_current=current)
            if not self._append_event('first_motion_measurement_selected',association):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Could not retain measurement selection.')
            request.require_start_time(time.monotonic_ns())
            return raw,association

    def stage_first_motion_evidence(self, *, request, operation_id, reference_originals):
        """Trusted host staging of this session's measurement; not a browser route."""
        from .first_motion_staging import stage_first_motion_originals
        with self._lock:
            raw,_association=self.select_first_motion_measurement(request=request,operation_id=operation_id)
            def current():
                if self._closed or self._running is not None or self._log_error:
                    raise WizardError('FIRST_MOTION_CONTEXT_CHANGED','Staging context is unavailable.')
                self._recheck_source('record_first_motion_measurements')
            report=stage_first_motion_originals(self.workspace,request,root=self._log.root,
                reference_originals=reference_originals,measurement_raw=raw,
                session_id=self.session_id,operation_id=operation_id,check_current=current)
            if not self._append_event('first_motion_evidence_staged',report):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Staged evidence remains retained; logging failed.')
            request.require_start_time(time.monotonic_ns())
            return report

    def select_first_motion_reviews(self, *, draft, review_operation_ids):
        """Select this session's original approvals, without signing or launch."""
        return self._select_first_motion_reviews(draft=draft, review_operation_ids=review_operation_ids)

    def _select_first_motion_reviews(self, *, draft, review_operation_ids, owner=None, check=None):
        from .first_motion_draft import FirstMotionDraft
        from .first_motion_review_intake import load_selected_reviews
        with self._lock:
            if check is not None: check()
            if (self.mode != 'physical' or self._closed or self._running != owner
                    or self._log_error):
                raise WizardError('FIRST_MOTION_REVIEW_HELD','Use an idle physical wizard with working logs.')
            if (type(draft) is not FirstMotionDraft or type(review_operation_ids) is not tuple
                    or len(review_operation_ids) != 5
                    or any(type(value) is not str for value in review_operation_ids)
                    or len(set(review_operation_ids)) != 5):
                raise WizardError('FIRST_MOTION_REVIEW_INVALID','Select five distinct commissioning review operations.')
            receipts = []
            for operation_id in review_operation_ids:
                operation = self._operations.get(operation_id, {})
                steps = (operation.get('result') or {}).get('steps', [])
                report = steps[0].get('report', {}) if len(steps) == 1 else {}
                if (operation.get('action_id') not in ('record_first_motion_engineering_review', 'review_retained_first_motion_draft')
                        or operation.get('status') != 'SUCCEEDED'
                        or report.get('selection_sha256') != draft.selection_sha256
                        or report.get('review', {}).get('decision') != 'APPROVED'):
                    raise WizardError('FIRST_MOTION_REVIEW_INVALID','Selected operation is not this draft\'s successful approval.')
                receipts.append((operation_id, report.get('review_sha256')))
            def current():
                if check is not None: check()
                if self._closed or self._running != owner or self._log_error:
                    raise WizardError('FIRST_MOTION_CONTEXT_CHANGED','Review context unavailable.')
                self._recheck_source('record_first_motion_engineering_review')
            originals = load_selected_reviews(root=self._log.root, draft=draft,
                selections=tuple(receipts), source_sha256=self.source_sha256, check_current=current)
            if not self._append_event('first_motion_engineering_reviews_selected',
                    dict(selection_sha256=draft.selection_sha256, receipts=receipts, motion_authorized=False)):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Could not retain commissioning review selection.')
            return originals

    def configure_first_motion(self, *, draft, reference_originals,
                               review_operation_ids, measurement_operation_id):
        """Attach exact trusted host material once; not a browser motion route.

        A temporary validation envelope is never dispatched or authenticated.
        Actual execution must reconstruct a new timed request at final click.
        """
        return self._configure_first_motion(draft=draft, reference_originals=reference_originals,
            review_operation_ids=review_operation_ids, measurement_operation_id=measurement_operation_id)

    def _configure_first_motion(self, *, draft, reference_originals,
                                review_operation_ids, measurement_operation_id, owner=None, check=None):
        from .first_motion_draft import FirstMotionDraft
        from .first_motion_reference_reader import ORIGINAL_REFERENCES
        from .wizard_diagnostic_coordinator import decode_diagnostic_json
        with self._lock:
            if check is not None: check()
            if (self.mode != 'physical' or self._closed or self._running != owner
                    or self._log_error or self._first_motion_attachment is not None
                    or self._first_motion_attempt_id is not None or self._endpoint_binding is not None):
                raise WizardError('FIRST_MOTION_CONFIGURATION_HELD','Use an idle unbound physical wizard with working logs.')
            if (type(draft) is not FirstMotionDraft or type(reference_originals) is not dict
                    or set(reference_originals) != ORIGINAL_REFERENCES):
                raise WizardError('FIRST_MOTION_CONFIGURATION_INVALID','Exact draft and complete original bytes required.')
            references = dict(reference_originals)
            refs = draft.preview()['selection']['references']
            for name, raw in references.items():
                if (type(raw) is not bytes or not 0 < len(raw) <= 128*1024
                        or hashlib.sha256(raw).hexdigest() != refs[name]):
                    raise WizardError('FIRST_MOTION_CONFIGURATION_INVALID','Original bytes differ from selected references.')
                decoded = decode_diagnostic_json(raw, maximum=128*1024)
                if type(decoded) is not dict or not decoded:
                    raise WizardError('FIRST_MOTION_CONFIGURATION_INVALID','Structured reference original required.')
            # Reuse actual same-session measurement validation without consuming
            # a short-lived execution request or renewing its original timestamp.
            from rocell.providers.windows.bench_review_key import load_host_first_motion_review_authority
            try:
                # Read-only readiness check before accepting an attachment.
                # Do not store key material on the service or provision missing
                # storage; execution will independently load the current key.
                load_host_first_motion_review_authority(self.workspace)
            except (ValueError, OSError, RuntimeError) as error:
                raise WizardError('FIRST_MOTION_REVIEW_KEY_REQUIRED',
                    'Private review key is unavailable. Use Set up private bench review key to check or explicitly provision it before configuring this test.') from error
            now = time.monotonic_ns()
            validation = draft.create_request(expected_selection_sha256=draft.selection_sha256,
                attempt_id='operation-'+'0'*32, issued_monotonic_ns=now,
                deadline_monotonic_ns=now+30_000_000_000)
            raw, _association = self._select_first_motion_measurement(
                request=validation, operation_id=measurement_operation_id, owner=owner, check=check)
            if references['independent_posture_review_sha256'] != raw:
                raise WizardError('FIRST_MOTION_CONFIGURATION_INVALID','Selected measurement original mismatch.')
            self._select_first_motion_reviews(draft=draft, review_operation_ids=review_operation_ids, owner=owner, check=check)
            receipts = tuple((operation_id, self._operations[operation_id]['result']['steps'][0]['report']['review_sha256'])
                             for operation_id in review_operation_ids)
            candidate = dict(draft=draft, reference_originals=references,
                review_selections=receipts, measurement_operation_id=measurement_operation_id)
            report = dict(selection_sha256=draft.selection_sha256,
                measurement_operation_id=measurement_operation_id, review_operation_ids=review_operation_ids,
                status='HOST_ATTACHED_NOT_AUTHORIZED', physical_authority=False, motion_authorized=False)
            self._recheck_source('record_first_motion_engineering_review')
            if check is not None: check()
            if not self._append_event('first_motion_configured', report):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Could not retain commissioning configuration.')
            if check is not None: check()
            self._first_motion_attachment = candidate
            self._changed(state=True)
            return report

    def configure_first_motion_from_retained(self, *, draft_operation_id, review_operation_ids):
        """Trusted-host bridge from wizard selections to the guarded attachment.

        Derive support and measurement identities from the successful generated
        draft receipt. Callers cannot substitute paths, original bytes, hashes or
        measurement IDs. Attachment itself neither opens a device nor creates a
        motion permit; the existing final-click executor remains separate.
        """
        return self._configure_first_motion_from_retained(draft_operation_id=draft_operation_id,
                                                         review_operation_ids=review_operation_ids)

    def _configure_first_motion_from_retained(self, *, draft_operation_id, review_operation_ids, owner=None, check=None):
        from .first_motion_draft import FirstMotionDraft
        from .physical_onboarding_durability import contained_path, read_bounded_regular_file
        with self._lock:
            if check is not None: check()
            if (self.mode != 'physical' or self._closed or self._running != owner
                    or self._log_error or self._first_motion_attachment is not None
                    or self._first_motion_attempt_id is not None or self._endpoint_binding is not None):
                raise WizardError('FIRST_MOTION_CONFIGURATION_HELD', 'Use an idle unbound physical wizard.')
            if type(draft_operation_id) is not str or not re.fullmatch(r'operation-[a-f0-9]{32}', draft_operation_id):
                raise WizardError('FIRST_MOTION_DRAFT_INVALID', 'Select a retained draft operation.')
            operation = self._operations.get(draft_operation_id, {})
            steps = (operation.get('result') or {}).get('steps', [])
            report = steps[0].get('report', {}) if len(steps) == 1 else {}
            if operation.get('action_id') != 'create_first_motion_draft' or operation.get('status') != 'SUCCEEDED':
                raise WizardError('FIRST_MOTION_DRAFT_INVALID', 'Select this session\'s successful generated draft.')
            raw = read_bounded_regular_file(contained_path(self._log.root,
                draft_operation_id+'-first-motion-generated-draft.json', label='generated draft'), maximum_bytes=16384)
            if hashlib.sha256(raw).hexdigest() != report.get('draft_sha256'):
                raise WizardError('FIRST_MOTION_DRAFT_INVALID', 'Retained draft changed.')
            draft = FirstMotionDraft(raw)
            support_id = report.get('support_record_id')
            support = self._first_motion_support_receipts.get(support_id) if type(support_id) is str else None
            if (support is None or support['session_id'] != self.session_id
                    or support['source_sha256'] != self.source_sha256):
                raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'The draft\'s original supporting record is unavailable.')
            originals = {}
            for name, digest in support['original_sha256'].items():
                value = read_bounded_regular_file(contained_path(self._log.root,
                    support_id+'-'+name+'.json', label='supporting original'), maximum_bytes=128*1024)
                if hashlib.sha256(value).hexdigest() != digest:
                    raise WizardError('FIRST_MOTION_SUPPORT_INVALID', 'Retained supporting original changed.')
                originals[name] = value
            measurement_id = report.get('measurement_operation_id')
            if type(measurement_id) is not str or not re.fullmatch(r'operation-[a-f0-9]{32}', measurement_id):
                raise WizardError('FIRST_MOTION_DRAFT_INVALID', 'Original measurement association is missing.')
            originals['independent_posture_review_sha256'] = read_bounded_regular_file(contained_path(self._log.root,
                measurement_id+'-first-motion-measurement-original.json', label='measurement original'), maximum_bytes=8192)
            # Existing attachment revalidates original hashes against the draft,
            # measurement age/uncertainty/receipt, five reviews and private key.
            return self._configure_first_motion(draft=draft, reference_originals=originals,
                review_operation_ids=review_operation_ids, measurement_operation_id=measurement_id, owner=owner, check=check)

    def configure_endpoint_trial(self, *, draft, reference_originals, review_operation_ids):
        """Trusted host wiring, not a browser route or a motion approval.

        Review hashes come from this service's successful retained operations,
        not caller-supplied digest claims. Actual source/original validation is
        delegated to the existing assembler. Nothing opens a device here.
        """
        from .endpoint_trial_draft import EndpointTrialDraft
        from .endpoint_binding_assembly import assemble_endpoint_binding
        from .endpoint_supervised_metadata import SupervisedEndpointMetadataFactory
        with self._lock:
            if (self.mode != 'physical' or self._closed or self._running is not None
                    or self._endpoint_attempt_id is not None or self._endpoint_binding is not None
                    or self._first_motion_attachment is not None):
                raise WizardError('ENDPOINT_CONFIGURATION_HELD','Use an idle unbound physical wizard; attempted attachments cannot be replaced.')
            if (type(draft) is not EndpointTrialDraft or type(review_operation_ids) is not tuple
                    or len(review_operation_ids) != 5
                    or any(type(value) is not str for value in review_operation_ids)
                    or len(set(review_operation_ids)) != 5):
                raise WizardError('ENDPOINT_REVIEW_SELECTION_INVALID','Select five distinct recorded engineering operations.')
            self._recheck_source('run_endpoint_trial')
            receipts = []
            for operation_id in review_operation_ids:
                operation = self._operations.get(operation_id,{})
                result = operation.get('result') or {}
                steps = result.get('steps',[])
                report = steps[0].get('report',{}) if len(steps)==1 else {}
                if (operation.get('action_id') != 'record_endpoint_engineering_review'
                        or operation.get('status') != 'SUCCEEDED'
                        or report.get('draft_sha256') != draft.draft_sha256
                        or report.get('review',{}).get('decision') != 'APPROVED'):
                    raise WizardError('ENDPOINT_REVIEW_SELECTION_INVALID','A selected operation is not an approval of this exact draft.')
                receipts.append((operation_id,report.get('review_sha256')))
            installed = None
            def current():
                # Keep the post-snapshot guard in memory. Disk source/build
                # reconstruction already occurs before metadata in the existing
                # reference reader; repeating it here would age the snapshot.
                with self._lock:
                    if self._closed or self._source_changed or self._log_error:
                        raise WizardError('ENDPOINT_CONTEXT_CHANGED','Endpoint service context is unavailable.')
                    if installed is not None and self._endpoint_binding is not installed:
                        raise WizardError('ENDPOINT_CONTEXT_CHANGED','Endpoint attachment changed.')
                    if self._endpoint_attempt_id is not None and (
                        self._running != self._endpoint_attempt_id or self._endpoint_confirmation is None
                        or self._endpoint_confirmation[0] != self._endpoint_attempt_id):
                        raise WizardError('ENDPOINT_CONTEXT_CHANGED','Endpoint operation no longer owns this context.')
            def cancellation():
                current()
                return self._cancel
            def retain(record):
                with self._lock:
                    if not self._append_event('endpoint_supervised_metadata',record):
                        raise WizardError('DIAGNOSTIC_LOG_FAILED','Endpoint metadata could not be retained.')
            metadata = SupervisedEndpointMetadataFactory(workspace=self.workspace,
                source_sha256=self.source_sha256,cell_id=self.cell_id,
                cancellation_reader=cancellation,retain=retain,check_current=current)
            candidate = assemble_endpoint_binding(workspace=self.workspace,draft=draft,
                reference_originals=reference_originals,review_root=self._log.root,
                review_selections=tuple(receipts),check_current=current,metadata_factory=metadata)
            if not self._append_event('endpoint_host_binding_prepared',{
                'draft_sha256':draft.draft_sha256,'review_operation_ids':list(review_operation_ids),
                'physical_authority':False,'motion_authorized':False}):
                raise WizardError('DIAGNOSTIC_LOG_FAILED','Endpoint assembly could not be retained.')
            self._endpoint_binding = installed = candidate
            self._changed(state=True)
            return {'draft_sha256':draft.draft_sha256,'status':'HOST_BOUND_NOT_AUTHORIZED',
                    'physical_authority':False,'motion_authorized':False}

    def _action_view(self, action: ActionDefinition) -> dict[str, Any]:
        action = self._bound_action(action)
        value = action.view(mode=self.mode, busy=self._running is not None)
        reasons = value["blocked_reasons"]
        if action.action_id == 'run_held_pair':
            if self._held_pair_binding is None:
                reasons.append('No trusted host-bound pair and admission readers are attached.')
            else:
                try:
                    value['pair_preview'] = self._held_pair_binding.preview(self.export_directory)
                except Exception:
                    reasons.append('Host-bound pair preparation could not be replayed.')
            if self._held_pair_attempted:
                reasons.append('This pair action was consumed; no automatic retry.')
        if action.action_id == 'review_first_motion_qualification':
            value['qualification_previews'] = {}
            for option in action.fields[0]['options']:
                steps = (self._operations[option['value']].get('result') or {}).get('steps', [])
                if len(steps) != 1: continue
                report = steps[0].get('report', {})
                assessment = report.get('assessment', {})
                preview = {key:deepcopy(assessment.get(key)) for key in (
                    'status','holds','attempt_id','request_sha256','result_sha256','observation_sha256',
                    'reported_observation','limitations','physical_movement_verified','campaign_advance_allowed')}
                preview['assessment_sha256'] = report.get('assessment_sha256')
                value['qualification_previews'][option['value']] = preview
        if action.action_id == 'review_first_motion_qualification' and not action.fields[0]['options']:
            reasons.append('Complete a retained evidence assessment first; a HELD assessment may be rejected or left UNKNOWN, not accepted.')
        if action.action_id == 'review_first_motion_qualification' and len(self._first_motion_qualification_receipts) >= 16:
            reasons.append('Sixteen review records are retained; export and inspect them before further work.')
        if action.action_id == 'assess_first_motion_qualification' and not action.fields[0]['options']:
            reasons.append('Record an observation against a retained commissioning result first.')
        if action.action_id == 'record_observational_movement' and not action.fields[0]['options']:
            reasons.append('No retained observational movement trial is available in this session.')
        if action.action_id == 'record_observational_movement' and len(self._observational_operator_receipts) >= 16:
            reasons.append('Sixteen observations are retained; export and review this session before continuing.')
        if action.action_id == 'record_first_motion_observation' and not action.fields[0]['options']:
            reasons.append('No retained commissioning result is available in this session; export incomplete attempts for diagnosis.')
        if action.action_id == 'record_first_motion_observation' and len(self._first_motion_observation_receipts) >= 16:
            reasons.append('This session has retained sixteen observations; export and review them before further work.')
        if action.action_id in ('review_retained_first_motion_draft','attach_retained_first_motion'):
            if not action.fields[0]['options']:
                reasons.append('Create a successful commissioning draft in this session first.')
            # Cached display only. Execution re-reads the selected original and
            # validates its receipt; rendering does not scan files or approve it.
            value['retained_draft_previews'] = {}
            for option in action.fields[0]['options']:
                operation = self._operations[option['value']]
                steps = (operation.get('result') or {}).get('steps', [])
                if len(steps) == 1:
                    value['retained_draft_previews'][option['value']] = deepcopy(steps[0].get('report', {}).get('preview'))
            if action.action_id == 'attach_retained_first_motion':
                if any(not field['options'] for field in action.fields):
                    reasons.append('Select a retained draft and one approval for each of the five engineering checks.')
                if self._first_motion_attachment is not None or self._first_motion_attempt_id is not None or self._endpoint_binding is not None:
                    reasons.append('This wizard is already attached or has attempted commissioning.')
        if action.action_id == 'create_first_motion_draft':
            if any(not field['options'] for field in action.fields):
                reasons.append('A successful measurement and host-retained supporting record set are both required.')
            if self._first_motion_attempt_id is not None:
                reasons.append('Commissioning has already been attempted in this session.')
        if action.action_id == 'run_positional_campaign':
            config = self._positional_campaign_configuration
            if config is None:
                reasons.append('Stage host-reviewed campaign originals and exactly two targets first.')
            else:
                value['campaign_preview'] = deepcopy(config['preview'])
                try:
                    if self._powered_setup_context() != config['context']:
                        reasons.append('Powered setup changed since campaign staging.')
                except WizardError as exc:
                    reasons.append(str(exc))
            if (self._positional_campaign_confirmation is not None
                    or self._observational_confirmation is not None or self._wrist_correction_confirmation is not None
                    or self._first_motion_attempt_id is not None or self._endpoint_attempt_id is not None):
                reasons.append('A motion attempt was already accepted; export and review its outcome.')
        if (action.action_id in ('run_observational_movement','run_first_motion','run_endpoint_trial','run_wrist_correction')
                and self._positional_campaign_confirmation is not None):
            reasons.append('An attended campaign was accepted; export and review its outcome first.')
        if action.action_id == 'run_wrist_correction':
            config=self._wrist_correction_configuration
            if config is None:
                reasons.append('Prepare a matched correction runtime first.')
            else:
                value['correction_preview']=deepcopy(config['report'])
                value['correction_preview'].update(usb_identity=config['bound'].to_dict()['usb_identity'],
                    expected_start_contexts_rad=config['bound'].to_dict()['proposal']['expected_start_contexts_rad'],
                    spd=20,acc=1,return_motion=False,retry_allowed=False)
            if self._wrist_correction_confirmation is not None:
                reasons.append('This correction has already been accepted. Review its outcome; no retry.')
            if self._observational_confirmation is not None or self._first_motion_attempt_id is not None or self._endpoint_attempt_id is not None:
                reasons.append('Another motion profile has been attempted in this session; review its outcome first.')
            try:
                self._powered_setup_context()
            except WizardError as exc:
                reasons.append(str(exc))
        if action.action_id == 'stage_wrist_correction' and self._wrist_correction_confirmation is not None:
            reasons.append('A correction was already accepted in this session; export and review its outcome.')
        if action.action_id in ('run_observational_movement','run_first_motion','run_endpoint_trial') and self._wrist_correction_confirmation is not None:
            reasons.append('A correction was accepted in this session; export and review its outcome first.')
        if action.action_id == 'run_observational_movement':
            config = self._observational_configuration
            if self._first_motion_attempt_id is not None or self._endpoint_attempt_id is not None:
                reasons.append('Another motion profile has already been attempted; review that outcome first.')
            if config is None:
                reasons.append('Stage reviewed controller and protocol originals through the host setup first.')
            else:
                value['observational_preview'] = dict(usb_identity=config['usb_identity'],
                    joint='wrist pitch', delta_degrees=config['direction'] * config.get('degrees', 1), spd=20, acc=1,
                    absolute_target='Selected from fresh owned baseline at execution', return_motion=False)
                if config.get('absolute_draft') is not None:
                    value['observational_preview'] = dict(usb_identity=config['usb_identity'],
                        joint='wrist pitch', absolute_target_degrees=config['absolute_draft'].to_dict()['target_deg'],
                        reviewed_draft=config['absolute_draft'].to_dict(), spd=20, acc=1,
                        fresh_baseline_required=True, return_motion=False, retry_allowed=False)
            if self._observational_confirmation is not None:
                reasons.append('This observational test has already been accepted; review its retained outcome.')
            try:
                if config is not None and self._powered_setup_context() != config['context']:
                    reasons.append('Powered setup changed after staging.')
            except WizardError as exc:
                reasons.append(str(exc))
        if action.action_id == 'setup_observational_movement':
            if not action.fields[0]['options']:
                reasons.append('No host-reviewed arm/protocol records are retained in this session.')
            if self._observational_configuration is not None:
                reasons.append('An observational runtime is already staged; use its run control or review the outcome.')
            # Surface the same prerequisite enforced at staging; this reads
            # retained setup/metadata only and does not open the arm.
            try:
                self._powered_setup_context()
            except WizardError as exc:
                reasons.append(str(exc))
        if action.action_id == 'use_current_arm_for_observational_test':
            current = self._native_arm_view()
            if current.get('status') != 'CURRENT' or (current.get('report') or {}).get('status') != 'METADATA_CORRELATED':
                reasons.append('Review the arm USB selection and correlate its native metadata first.')
            if self._observational_configuration is not None or len(self._observational_sources) >= 8:
                reasons.append('An observational runtime is staged or the source-record limit has been reached.')
        if action.action_id == 'run_first_motion':
            if self._observational_confirmation is not None:
                reasons.append('An observational trial has been attempted; review its outcome before another motion profile.')
            if self._first_motion_attachment is None:
                reasons.append('No host-attached commissioning draft and originals.')
            else:
                value['commissioning_preview'] = self._first_motion_attachment['draft'].preview()
            if self._first_motion_attempt_id is not None:
                reasons.append('This commissioning attachment has already been attempted; export and review its outcome.')
            try:
                self._powered_setup_context()
            except WizardError as exc:
                reasons.append(str(exc))
        if action.action_id == 'run_endpoint_trial':
            if self._observational_confirmation is not None:
                reasons.append('An observational trial has been attempted; review its outcome before another motion profile.')
            if self._endpoint_binding is None:
                reasons.append('No host-bound endpoint trial and engineering review readers are attached.')
            else:
                value['endpoint_draft'] = json.loads(self._endpoint_binding.draft.canonical_bytes)
                value['endpoint_draft_sha256'] = self._endpoint_binding.draft.draft_sha256
            if self._endpoint_attempt_id is not None:
                reasons.append('This endpoint attachment has already been attempted; review retained evidence before a new launch.')
            try:
                self._powered_setup_context()
            except WizardError as exc:
                reasons.append(str(exc))
        if action.action_id in _POWERED_ACTIONS:
            try:
                self._powered_setup_context()
            except WizardError as exc:
                reasons.append(str(exc))
            if self._powered_feedback_attempt_id is not None:
                reasons.append(
                    "One powered feedback attempt per launch; export and review before any further connection."
                )
        if action.action_id == "run_passive_arm_connection":
            try:
                self._passive_setup_context()
            except WizardError as exc:
                reasons.append(str(exc))
            if any(
                item["action_id"] == action.action_id
                for item in self._operations.values()
            ):
                reasons.append(
                    "One passive attempt per launch; export diagnostics. No replay."
                )
        if action.action_id == "record_passive_arm_setup":
            current_arm = self._native_arm_view()
            if (
                current_arm["status"] != "CURRENT"
                or (current_arm.get("report") or {}).get("status")
                != "METADATA_CORRELATED"
            ):
                reasons.append(
                    "Inspect and correlate current arm USB metadata before recording setup."
                )
        if action.action_id == "rehearse_passive_arm_connection" and any(
            item["action_id"] == action.action_id for item in self._operations.values()
        ):
            reasons.append(
                "One passive rehearsal attempt per launch; export its diagnostics before closing. No automatic replay."
            )
        if self._closed:
            reasons.append("The session is shutting down; restart explicitly.")
        if action.action_id not in _HOUSEKEEPING:
            if self._source_changed:
                reasons.append(
                    "Source changed after launch; export diagnostics and restart after review."
                )
            if self._log_error:
                reasons.append(
                    "Diagnostic logging failed; export/stop/note remain available for review."
                )
            if self._primary_operations >= MAX_OPERATIONS:
                reasons.append(
                    "This launch reached its 32-operation budget. Export, restart the application, then explicitly discover and reopen the same rehearsal store; do not initialize a replacement to continue it."
                )
        if action.action_id == "stop_operation" and self._running is None:
            reasons.append("No diagnostic operation is running.")
        if (
            action.action_id == "camera_helper_review"
            and self._camera_helper.view()["inspection"] is None
        ):
            reasons.append(
                "Explicitly inspect the fixed helper files before reviewing them."
            )
        if action.action_id in _CANDIDATE_ACTIONS and not action.fields[0]["options"]:
            reasons.append(
                "No current metadata candidate is available. Explicitly inspect metadata "
                "(or load a rehearsal fixture), then review a candidate from that snapshot."
            )
        if action.action_id in _NATIVE_ARM_ACTIONS:
            if self._device_selection.reviewed_candidate("SERIAL") is None:
                reasons.append(
                    "Explicitly review a current generic arm SERIAL candidate first."
                )
            if (
                action.action_id == "inspect_native_arm_metadata"
                # sys.platform is process-local; platform.system() may invoke
                # Windows 'ver' when its OS-version cache is cold.
                and sys.platform != "win32"
            ):
                reasons.append(
                    "Native COM-interface identity inspection is available on Windows only."
                )
        if action.action_id in _NATIVE_ACTIONS:
            if self._native_camera_provider is None:
                reasons.append(
                    "No reviewed native metadata provider is registered. The local development "
                    "build is not runtime registration; physical endpoint lookup remains unavailable."
                )
            if self._device_selection.view()["devices"]["CAMERA"]["review"] is None:
                reasons.append(
                    "Explicitly review a current generic camera metadata candidate first."
                )
            if action.action_id in _NATIVE_CHOICES and not action.fields[0]["options"]:
                reasons.append(
                    "Discover native endpoint metadata, then explicitly choose an endpoint."
                )
            if (
                action.action_id == "native_camera_review"
                and self._native_camera.view()["identity"] is None
            ):
                reasons.append(
                    "Resolve one exact native endpoint identity before reviewing it."
                )
        if action.worker == "commissioning":
            reason = self._commissioning.blocked_reason(action.action_id)
            if reason:
                reasons.append(reason)
        if action.worker == "physical_preflight":
            reason = self._source_preflight.blocked_reason()
            if reason:
                reasons.append(reason)
        if action.worker == "physical_camera_setup":
            reason = self._physical_camera_setup.blocked_reason(action.action_id)
            if reason:
                reasons.append(reason)
            if (
                action.action_id
                in {"physical_camera_probe_prepare", "physical_camera_probe_review"}
                and not self._probe_metadata_current()
            ):
                reasons.append(
                    "Complete and log current camera metadata collection and endpoint review in this launch; saved enrollment is not a current connection."
                )
        if (
            action.action_id == "physical_camera_probe_export"
            and not self._physical_camera_setup.probe_record_view()["export_available"]
        ):
            reasons.append(
                "No camera probe preparation or queued attempt is retained for export."
            )
        if action.worker == "physical_intake_evidence":
            reason = self._physical_intake_evidence.blocked_reason(
                action.action_id, self._physical_intake
            )
            if reason:
                reasons.append(reason)
        if action.worker == "physical_source_qualification":
            reason = self._source_qualification.blocked_reason(action.action_id)
            if reason:
                reasons.append(reason)
        if action.worker == "physical_static_camera_onboarding":
            reason = self._static_camera_onboarding.blocked_reason(action.action_id)
            if reason:
                reasons.append(reason)
        if action.worker == "physical_received_camera":
            reason = self._received_camera.blocked_reason(action.action_id)
            if reason:
                reasons.append(reason)
        if action.worker == "physical_camera_identity_records":
            reason = self._camera_identity_records.blocked_reason(
                action.action_id,
                native_camera=self._native_camera,
                helper=self._camera_helper,
            )
            if reason:
                reasons.append(reason)
        if action.worker == "physical_usb_identity":
            reason = self._usb_identity.blocked_reason(
                action.action_id,
                native_camera=self._native_camera,
                helper=self._camera_helper,
            )
            if reason:
                reasons.append(reason)
        if action.worker == "physical_camera_runtime":
            reason = self._physical_camera.runtime_blocked_reason(action.action_id)
            if reason:
                reasons.append(reason)
        if action.worker == "physical_camera_configuration":
            reason = self._physical_camera.configuration_blocked_reason()
            if reason:
                reasons.append(reason)
        if action.worker == "physical_intake":
            setup = self._physical_camera_setup_view()
            if (
                setup["publication"]["status"] != "CURRENT"
                or not setup["prerequisites"]
            ):
                reasons.append(
                    "Collect or reopen and verify original camera requirements before starting a passive intake draft."
                )
            if (
                action.action_id == "physical_intake_start"
                and self._physical_intake is not None
            ):
                reasons.append(
                    "This launch already has a draft. Explicitly revise its entries or export it; starting over cannot erase its history."
                )
            if (
                action.action_id == "physical_intake_record"
                and not self._intake_is_current()
            ):
                reasons.append(
                    "Start a draft bound to the currently verified camera requirements first."
                )
        if action.action_id == "physical_camera_plan":
            reason = self._physical_camera_setup.planning_blocked_reason()
            if reason:
                reasons.append(reason)
        if action.action_id == "physical_camera_probe":
            if self._probe_dispatch_queue is not None:
                reasons.append(
                    "This camera probe was queued once. Inspect/export its original outcome; do not replay it."
                )
            else:
                try:
                    self._original_probe_context()
                except WizardError as exc:
                    reasons.append(str(exc))
        if (
            action.action_id == "physical_camera_probe_attempt_export"
            and not self._probe_attempt_view()["export_available"]
        ):
            reasons.append(
                "No queued camera probe or admission attempt is retained in this launch."
            )
        if action.action_id == CONFIGURATION_CAPTURE:
            try:
                self._configuration_wizard.preview_context()
            except (WizardError, ValueError) as exc:
                reasons.append(str(exc))
        if action.action_id == OPERATING_PROPOSAL:
            try:
                self._operating_proposal.preview_context()
            except (WizardError, ValueError) as exc:
                reasons.append(str(exc))
        if action.action_id == OPERATING_ASSESSMENT:
            try:
                self._operating_assessment.preview_context()
            except (WizardError, ValueError) as exc:
                reasons.append(str(exc))
        if action.action_id == OPERATING_SUBMISSION:
            try:
                self._operating_submission.preview_context()
            except (WizardError, ValueError) as exc:
                reasons.append(str(exc))
        if (
            action.action_id == CONFIGURATION_EXPORT
            and not self._configuration_wizard.view()["export_available"]
        ):
            reasons.append("No settings-capture attempt is retained in this launch.")
        value["enabled"] = not reasons
        return value

    def _original_probe_context(self) -> dict[str, Any]:
        """Cached UI/log owner binding; full original authentication is later."""
        if self._closed or not self._probe_metadata_current():
            raise WizardError(
                "CAMERA_PROBE_METADATA_REQUIRED",
                "Complete and log current camera metadata collection and endpoint review in this launch. Imported enrollment is not a current connection.",
            )
        return self._physical_camera_setup.original_probe_context(self._native_camera)

    def _probe_attempt_view(self) -> dict[str, Any]:
        """Bounded inert display, distinct from the full private export packet."""
        progress = self._physical_camera.original_probe_progress()
        queue = self._probe_dispatch_queue
        return dict(
            schema="rocell.wizard_camera_probe_attempt.v1",
            source_sha256=self.source_sha256,
            launch_session_id=self.session_id,
            status=progress["status"],
            failed_phase=progress["failed_phase"],
            queued=queue is not None,
            claimed=False if queue is None else queue["claimed"],
            operation_id=None if queue is None else queue["operation_id"],
            outcome=(self._probe_attempt_completion or {}).get("status"),
            export_available=queue is not None or progress["attempted"],
            export_action="physical_camera_probe_attempt_export",
            physical_authority=False,
            hardware_qualified=False,
            connected=False,
            meaning="A capability observation is not a connected camera, image stream, physical-stage acceptance or arm authorization. A queued attempt is one-use; export its outcome without automatic retry.",
        )

    def _probe_attempt_packet(self) -> dict[str, Any] | None:
        """Private cached export, independent of rotating ordinary results."""
        from .camera_probe_attempt_export import DIAGNOSTICS_SCHEMA

        data = self._physical_camera.retained_probe_diagnostics()
        if self._probe_dispatch_queue is None and data["admission"] is None:
            return None
        return dict(
            schema=DIAGNOSTICS_SCHEMA,
            source_sha256=self.source_sha256,
            launch_session_id=self.session_id,
            queue=deepcopy(self._probe_dispatch_queue),
            admission=data["admission"],
            dispatch=data["dispatch"],
            completion=deepcopy(self._probe_attempt_completion),
            physical_authority=False,
            hardware_qualified=False,
            meaning="Cached original-probe attempt and completion, including failure and unknown outcomes. No current readiness or replay can be restored.",
        )

    def _probe_attempt_export_context(self) -> str:
        packet = self._probe_attempt_packet()
        if packet is None:
            raise WizardError(
                "CAMERA_PROBE_ATTEMPT_EXPORT_EMPTY", "No retained camera probe attempt."
            )
        return hashlib.sha256(_json_payload(packet)).hexdigest()

    def _probe_metadata_current(self) -> bool:
        """Cached current-owner/log provenance only; never query the camera."""
        publication = self._probe_metadata_publication
        if publication is None or self._source_changed or self._log_error:
            return False
        snapshot = self._native_camera.export_snapshot()
        if (
            hashlib.sha256(_json_payload(snapshot)).hexdigest()
            != publication["enrollment_sha256"]
        ):
            return False
        for operation_id, action_id in publication["operations"].items():
            operation = self._operations.get(operation_id)
            if (
                operation is None
                or operation["action_id"] != action_id
                or operation["status"] != "SUCCEEDED"
                or operation.get("completion_log_persisted") is not True
            ):
                return False
        return True

    def _probe_export_context(self) -> str:
        packet = self._physical_camera_setup.probe_record_diagnostics()
        if packet is None:
            raise WizardError(
                "CAMERA_PROBE_EXPORT_EMPTY",
                "No retained probe records or queued attempts to export.",
            )
        # Source checking may withdraw CURRENT publication. It must not alter
        # the previewed original/attempt/queue bytes or hide historical records.
        packet.pop("publication")
        return hashlib.sha256(_json_payload(packet)).hexdigest()

    def _physical_camera_setup_view(self) -> dict[str, Any]:
        view = self._physical_camera_setup.view()
        if self._source_changed or self._log_error or self._closed:
            view["prerequisites"] = None
            view["requirements_provenance"] = "NONE"
            view["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            if view["source_workflow"]["status"] != "NOT_STARTED":
                view["source_workflow"]["status"] = "HISTORICAL_HELD"
            if view["configuration_records"]["status"] != "NOT_RETAINED":
                view["configuration_records"]["status"] = "HISTORICAL_HELD"
        return view

    def _physical_intake_evidence_view(self) -> dict[str, Any]:
        value = self._physical_intake_evidence.view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker == "physical_intake_evidence"
        ):
            # Presentation withdrawal must not mutate the exact admission
            # context or invalidate setup before its transaction is entered.
            value["publication"] = {
                "status": "PENDING",
                "operation_id": running["operation_id"],
            }
            value["status"] = (
                "HISTORICAL_HELD" if value["collection_count"] else "NOT_STARTED"
            )
            value["collection"] = None
            value["discovery"].update(
                status="NOT_DISCOVERED", discovery_sha256=None, files=[], issues=[]
            )
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
        return value

    def _source_reassessment_view(self) -> dict[str, Any]:
        value = self._source_qualification.view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker
            == "physical_source_qualification"
        ):
            # Withdraw display without changing the setup context required by
            # the service's original transaction entry. Never admit from GET.
            value["publication"] = {
                "status": "PENDING",
                "operation_id": running["operation_id"],
            }
            value["status"] = (
                "HISTORICAL_HELD"
                if value["qualification"] is not None
                else "NOT_STARTED"
            )
            value["qualification"] = None
            value["next_action"] = None
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            value["next_action"] = None
        return value

    def _static_camera_onboarding_view(self) -> dict[str, Any]:
        value = self._static_camera_onboarding.view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker
            == "physical_static_camera_onboarding"
        ):
            value["publication"] = {
                "status": "PENDING",
                "operation_id": running["operation_id"],
            }
            value["status"] = (
                "HISTORICAL_HELD" if value["contract"] is not None else "NOT_STARTED"
            )
            value["contract"] = None
            value["camera_receipt_entry"] = None
            value["next_action"] = None
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            value["next_action"] = None
        return value

    def _camera_setup_source_report(self) -> Any:
        return self._physical_camera_setup.source_report_from_retained(
            self._source_preflight.retained_report()
        )

    def _camera_identity_records_view(self) -> dict[str, Any]:
        value = self._camera_identity_records.view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker
            == "physical_camera_identity_records"
        ):
            value["publication"] = {
                "status": "PENDING",
                "operation_id": running["operation_id"],
            }
            value["status"] = "HISTORICAL_HELD" if value["cycles"] else "NOT_STARTED"
            value["cycles"], value["identity_entry"], value["next_action"] = (
                [],
                None,
                None,
            )
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            value["next_action"] = None
        return value

    def _usb_identity_view(self) -> dict[str, Any]:
        """Cached original USB observations; no inspection or device I/O."""
        value = self._usb_identity.view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker == "physical_usb_identity"
        ):
            value["publication"] = {
                "status": "PENDING",
                "operation_id": running["operation_id"],
            }
            value["status"] = (
                "HISTORICAL_HELD" if value["usb_id"] is not None else "NOT_STARTED"
            )
            for key in (
                "inspection",
                "review",
                "execution",
                "observation",
                "next_action",
            ):
                value[key] = None
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            value["next_action"] = None
        return value

    def _usb_identity_export_pointer(self) -> dict[str, Any]:
        value = self._usb_identity_view()
        receipt = value["export_receipt"]
        return {
            "schema": "rocell.wizard_usb_identity_export_pointer.v1",
            **{
                key: deepcopy(value[key])
                for key in (
                    "source_sha256",
                    "launch_session_id",
                    "original_context",
                    "publication",
                    "status",
                    "usb_id",
                )
            },
            "coverage": {
                key: deepcopy(value[key])
                for key in ("inspection", "review", "execution", "observation")
            },
            "export_receipt": (
                None
                if receipt is None
                else {
                    key: receipt[key]
                    for key in ("path", "export_id", "manifest_sha256")
                }
            ),
            "separate_metadata_export_required": True,
            "original_documents_included": False,
            "physical_authority": False,
            "meaning": "Compact USB baseline coverage only. Export the separate original USB evidence bundle; this pointer does not preserve full original subjects or establish reconnect/reboot qualification, camera capture release or arm access.",
        }

    def _usb_qualification_export_pointer(self) -> dict[str, Any]:
        """Compact coverage only; full phase subjects use the existing USB export.

        A live four-phase card includes large repeated checks and observations.
        The general report must reference that domain bundle, not duplicate the
        whole card and exceed the fixed snapshot limit after camera entry.
        """
        value = self._usb_qualification_view()
        receipt = value["export_receipt"]
        complete = value.get("complete")
        return {
            "schema": "rocell.wizard_usb_qualification_export_pointer.v1",
            **{
                key: deepcopy(value[key])
                for key in (
                    "source_sha256",
                    "launch_session_id",
                    "original_context",
                    "publication",
                    "status",
                )
            },
            "plan_sha256": (value.get("plan") or {}).get("plan_sha256"),
            "phases": {
                key: (
                    None
                    if value.get(key) is None
                    else {
                        "phase_id": value[key]["phase_id"],
                        "state": value[key]["state"],
                        "phase_sha256": (value[key].get("phase_record") or {}).get(
                            "phase_sha256"
                        ),
                    }
                )
                for key in ("baseline", "absence", "reconnect", "reboot")
            },
            "complete": (
                None
                if complete is None
                else {
                    key: complete[key]
                    for key in (
                        "series_id",
                        "state",
                        "series_sha256",
                        "assessment_sha256",
                        "review_sha256",
                    )
                }
            ),
            "export_receipt": (
                None
                if receipt is None
                else {
                    key: receipt[key]
                    for key in ("path", "export_id", "manifest_sha256")
                }
            ),
            "separate_metadata_export_required": True,
            "required_action": "physical_usb_identity_export",
            "original_documents_included": False,
            "physical_authority": False,
            "meaning": "Compact original USB trial coverage only. Full phase, assessment, review and attempted records require the separate USB evidence export. This is not a live UI projection or connection permission.",
        }

    def _usb_qualification_view(self) -> dict[str, Any]:
        """Cached declared trial only; no acquisition or original-store reads."""
        value = self._usb_identity.qualification_view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker == "physical_usb_identity"
        ):
            value["publication"] = dict(
                status="PENDING", operation_id=running["operation_id"]
            )
            value["status"] = "NOT_DECLARED"
            value["plan"] = value["next_action"] = None
            for key in ("baseline", "absence", "reconnect", "reboot", "complete"):
                if key in value:
                    value[key] = None
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = dict(status="HISTORICAL_HELD", operation_id=None)
            value["next_action"] = None
        return value

    def _camera_identity_export_pointer(self) -> dict[str, Any]:
        value = self._camera_identity_records_view()
        receipt = value["export_receipt"]
        return {
            "schema": "rocell.wizard_camera_identity_export_pointer.v1",
            **{
                key: deepcopy(value[key])
                for key in (
                    "source_sha256",
                    "launch_session_id",
                    "original_context",
                    "publication",
                    "status",
                )
            },
            "cycles": [
                {
                    "identity_id": cycle["identity_id"],
                    "sequence": cycle["sequence"],
                    "state": cycle["state"],
                    **{
                        role
                        + "_sha256": (
                            None if cycle[role] is None else cycle[role]["sha256"]
                        )
                        for role in (
                            "metadata",
                            "helper",
                            "receipt",
                            "assessment",
                            "review",
                        )
                    },
                }
                for cycle in value["cycles"]
            ],
            "export_receipt": (
                None
                if receipt is None
                else {
                    key: receipt[key]
                    for key in ("path", "export_id", "manifest_sha256")
                }
            ),
            "separate_metadata_export_required": True,
            "original_documents_included": False,
            "physical_authority": False,
            "meaning": "Compact original identity coverage only. Use the separate identity metadata export for full retained subjects; this pointer is not persistent identity qualification or current connection evidence.",
        }

    def _received_camera_view(self) -> dict[str, Any]:
        value = self._received_camera.view()
        running = self._operations.get(self._running) if self._running else None
        if (
            running is not None
            and ACTION_BY_ID[running["action_id"]].worker == "physical_received_camera"
        ):
            value["publication"] = {
                "status": "PENDING",
                "operation_id": running["operation_id"],
            }
            value["status"] = (
                "HISTORICAL_HELD" if value["collection"] is not None else "NOT_STARTED"
            )
            value["draft"] = value["collection"] = value["identity_entry"] = None
            value["draft_origin_notebook_sha256"] = value["next_action"] = None
            value["inbox"]["choices"] = []
            discovery = value["inbox"]["discovery"]
            discovery.update(
                status="NOT_DISCOVERED", files=[], issues=[], discovery_sha256=None
            )
        if (
            self._source_changed
            or self._log_error
            or self._closed
            or (
                value["publication"]["status"] == "CURRENT"
                and self._physical_camera_setup_view()["publication"]["status"]
                != "CURRENT"
            )
        ):
            value["status"] = "HISTORICAL_HELD"
            value["publication"] = {"status": "HISTORICAL_HELD", "operation_id": None}
            value["next_action"] = None
            value["inbox"]["choices"] = []
        return value

    def _received_camera_export_pointer(self) -> dict[str, Any]:
        """Explicit small diagnostic coverage, never a substitute original."""
        value = self._received_camera_view()
        collection, draft, receipt = (
            value["collection"],
            value["draft"],
            value["metadata_export"],
        )
        subjects = None
        if collection is not None:
            subjects = {
                "receipt_id": collection["receipt_id"],
                "sequence": collection["sequence"],
                "state": collection["state"],
                "notebook_sha256": (
                    None
                    if collection["notebook"] is None
                    else collection["notebook"]["evidence_sha256"]
                ),
                **{
                    role
                    + "_sha256": (
                        None
                        if collection[role] is None
                        else collection[role][role + "_sha256"]
                    )
                    for role in ("submission", "assessment", "review")
                },
            }
        return {
            "schema": "rocell.wizard_received_camera_export_pointer.v1",
            "source_sha256": value["source_sha256"],
            "launch_session_id": value["launch_session_id"],
            "original_context": deepcopy(value["original_context"]),
            "publication": deepcopy(value["publication"]),
            "status": value["status"],
            "latest_subjects": subjects,
            "draft_sha256": None if draft is None else draft["snapshot_sha256"],
            "metadata_export": (
                None
                if receipt is None
                else {
                    key: receipt[key]
                    for key in ("path", "export_id", "manifest_sha256")
                }
            ),
            "separate_metadata_export_required": True,
            "original_received_documents_included": False,
            "private_original_media_included": False,
            "physical_authority": False,
            "hardware_qualified": False,
            "meaning": "General diagnostics contain coverage and hashes only. Use the explicit received-camera metadata export for all original cycle/draft/attempt documents; private original media remains excluded. This pointer cannot restore evidence, acceptance or native release.",
        }

    def _intake_is_current(self) -> bool:
        if self.mode != "physical" or self._physical_intake is None:
            return False
        setup = self._physical_camera_setup_view()
        requirements = setup["prerequisites"]
        if setup["publication"]["status"] != "CURRENT" or requirements is None:
            return False
        binding = self._physical_intake.to_dict()["binding"]
        return binding == {
            "source_sha256": self.source_sha256,
            "session_id": requirements["binding"]["session_id"],
            "origin_launch_id": setup["origin_launch_id"],
            "launch_session_id": self.session_id,
            "prerequisites_sha256": requirements["evidence_sha256"],
        }

    def _physical_intake_view(self) -> dict[str, Any]:
        current = self._intake_is_current()
        return {
            "schema": "rocell.wizard_physical_intake.v1",
            "status": (
                "CURRENT_DRAFT"
                if current
                else (
                    "NOT_STARTED"
                    if self._physical_intake is None
                    else "HISTORICAL_HELD"
                )
            ),
            "notebook": (
                self._physical_intake.view()
                if current and self._physical_intake is not None
                else None
            ),
            "physical_authority": False,
            "hardware_qualified": False,
            "meaning": "Unreviewed passive intake drafts only. Evidence notes are not attached bytes. Export before closing; draft restoration is not yet available. No canonical stage, power state or connection is accepted.",
        }

    def _intake_context_sha256(self) -> str:
        setup = self._physical_camera_setup_view()
        if (
            setup["publication"]["status"] != "CURRENT"
            or setup["prerequisites"] is None
        ):
            raise WizardError(
                "INTAKE_REQUIREMENTS_UNAVAILABLE",
                "Original current camera requirements are unavailable.",
            )
        return hashlib.sha256(
            _json_payload(
                {
                    "source_sha256": self.source_sha256,
                    "launch_session_id": self.session_id,
                    "requirements": setup["prerequisites"]["binding"],
                    "prerequisites_sha256": setup["prerequisites"]["evidence_sha256"],
                    "notebook_sha256": (
                        None
                        if self._physical_intake is None
                        else self._physical_intake.sha256
                    ),
                }
            )
        ).hexdigest()

    def _source_preflight_view(self) -> dict[str, Any]:
        view = self._source_preflight.view()
        latest = next(
            (
                operation
                for operation in reversed(self._operations.values())
                if operation["action_id"] == "physical_source_preflight"
            ),
            None,
        )
        current = bool(
            latest
            and latest["status"] == "SUCCEEDED"
            and latest.get("completion_log_persisted") is True
            and self._running is None
            and not self._source_changed
            and not self._log_error
            and not self._closed
        )
        view["source_observation_current"] = current
        if view["status"] == "FILE_CHECKS_COHERENT" and not current:
            view["status"] = (
                "PUBLICATION_PENDING" if self._running else "PUBLICATION_HELD"
            )
            view["next_step"] = (
                "Historical source report retained; current publication is not confirmed. Inspect operation status and export diagnostics."
            )
        return view

    def view(self) -> dict[str, Any]:
        """Cached projection only; no source reread, device enumeration or writes."""
        with self._lock:
            status = (
                "SHUTTING_DOWN"
                if self._closed
                else (
                    "DIAGNOSTIC_HOLD"
                    if self._source_changed or self._log_error
                    else (
                        "DIAGNOSTIC_RUNNING"
                        if self._running
                        else "READY_FOR_DIAGNOSTICS"
                    )
                )
            )
            summaries = [self._summary(value) for value in self._operations.values()]
            projection = deepcopy(
                {
                    "schema": "rocell.arrival_wizard_view.v1",
                    "revision": self._revision,
                    "state_epoch": self._state_epoch,
                    "mode": self.mode,
                    "session_id": self.session_id,
                    "cell_id": self.cell_id,
                    "title": "RoCell arrival workbench",
                    "status": status,
                    "authority": "NO_PHYSICAL_AUTHORITY",
                    "physical_authority": False,
                    "verification": "DIAGNOSTIC_ONLY_NOT_RECEIVED_UNIT_VERIFIED",
                    "source_binding_sha256": self.source_sha256,
                    "software_version": __version__,
                    "next_step": (
                        "Export diagnostics and review the hold before restarting."
                        if self._source_changed or self._log_error
                        else "Run setup baselines, rehearse camera and arm connections, then inspect results and export logs."
                    ),
                    "actions": [self._action_view(action) for action in ACTIONS],
                    "camera": self._camera,
                    "arm": self._arm,
                    "device_selection": self._device_selection.view(),
                    "native_arm_metadata": self._native_arm_view(),
                    "passive_arm_rehearsal": self._passive_arm_view(),
                    "passive_arm_history": self._passive_arm_history,
                    "camera_helper_registration": self._camera_helper.view(),
                    "native_camera_enrollment": self._native_camera.view(),
                    "physical_camera": self._physical_camera_view(),
                    "physical_camera_setup": self._physical_camera_setup_view(),
                    "camera_mode_entry": self._physical_camera_setup.mode_entry_view(),
                    "camera_probe_setup": self._physical_camera_setup.probe_record_view(),
                    "camera_probe_attempt": self._probe_attempt_view(),
                    "camera_configuration_attempt": self._configuration_wizard.view(),
                    "camera_operating_proposal": self._operating_proposal.view(),
                    "camera_operating_submission": self._operating_submission.view(),
                    "source_reassessment": self._source_reassessment_view(),
                    "static_camera_onboarding": self._static_camera_onboarding_view(),
                    "received_camera_onboarding": self._received_camera_view(),
                    "camera_identity_onboarding": self._camera_identity_records_view(),
                    "usb_identity": self._usb_identity_view(),
                    "usb_qualification": self._usb_qualification_view(),
                    "physical_intake": self._physical_intake_view(),
                    "physical_intake_evidence": self._physical_intake_evidence_view(),
                    "board": self._board,
                    "stages": self._stages,
                    "commissioning_rehearsal": self._commissioning_view(),
                    "physical_source_preflight": self._source_preflight_view(),
                    "blockers": [PHYSICAL_HOLD],
                    "baselines": self._latest_by_section.get("overview", {}),
                    "tasks": self._latest_by_section.get("tasks", {}),
                    "diagnostics": {
                        "log_directory": str(self._log.directory),
                        "log_state": (
                            "HELD"
                            if self._log_error
                            else (
                                "NOT_STARTED"
                                if not self._events
                                else "APPEND_ONLY_DIAGNOSTIC"
                            )
                        ),
                        "log_error": self._log_error,
                        "source_changed": self._source_changed,
                        "event_count": len(self._events),
                        "retention_policy": _OMISSION_POLICY,
                        "replay_allowed": False,
                        "stop_is_robot_estop": False,
                    },
                    "operations": summaries,
                    "latest": summaries[-1] if summaries else None,
                    "events": self._events[-30:],
                    "exports": {
                        "directory": str(self.export_directory),
                        "items": self._exports[-8:],
                    },
                }
            )

            projection["arm_readiness"] = arm_wizard_readiness(projection)
            return projection

    def _passive_arm_view(self) -> dict[str, Any] | None:
        if self._passive_arm_retained is None:
            return None
        retained = self._passive_arm_retained
        operation = self._operations.get(retained["operation_id"], {})
        result = retained["result"]
        steps = result.get("steps", [])
        report = steps[0].get("report", {}) if steps else {}
        process = report.get("process", {})
        return {
            "schema": "rocell.wizard_passive_arm_rehearsal_view.v1",
            "operation_id": retained["operation_id"],
            "provenance": "REHEARSAL_ONLY_NOT_RECEIVED_DEVICE_EVIDENCE",
            "operation_status": operation.get("status", "HISTORICAL"),
            "durable_checkpoint": deepcopy(self._passive_arm_checkpoint),
            "completion_log_confirmed": operation.get("completion_log_persisted")
            is True,
            "source_invalidation_observed": self._source_changed,
            "process_status": process.get("status", "NOT_RETAINED"),
            "process_tree_exit_reported": process.get("tree_exit_confirmed"),
            "passive_summary": deepcopy(report.get("passive_summary")),
            "export_attachment": "passive-arm-rehearsal.json",
            "physical_authority": False,
            "connected": False,
        }

    def prepare_action(
        self, action_id: str, input: dict[str, Any], expected_revision: int
    ) -> dict[str, Any]:
        with self._lock:
            # Stop can be prepared from a view made stale only by progress in
            # this exact state epoch. A completed/replaced operation advances
            # the floor, so an old Stop view cannot target a different worker.
            valid_revision = (
                type(expected_revision) is int
                and 0 <= expected_revision <= self._revision
            )
            progress_only_stop = (
                valid_revision
                and action_id == "stop_operation"
                and self._running is not None
                and expected_revision >= self._state_revision_floor
            )
            if not valid_revision or (
                expected_revision != self._revision and not progress_only_stop
            ):
                raise WizardError(
                    "STALE_REVISION",
                    "The displayed view changed; refresh before preparing an action.",
                )
            if type(action_id) is not str or action_id not in ACTION_BY_ID:
                raise WizardError("UNKNOWN_ACTION", "This action is not registered.")
            action = self._bound_action(ACTION_BY_ID[action_id])
            values = validate_action_input(action, input)
            available = self._action_view(action)
            if not available["enabled"]:
                raise WizardError(
                    "ACTION_BLOCKED", " ".join(available["blocked_reasons"])
                )
            self._recheck_source(action_id)
            if action_id == 'run_held_pair' and values['acknowledge'] is not True:
                raise WizardError('PAIR_ACK_REQUIRED','Acknowledge the exact host-bound pair.')
            if action_id == 'run_positional_campaign':
                config = self._positional_campaign_configuration
                values['_campaign_id'] = config['preview']['campaign_id']
                values['_campaign_context'] = self._powered_setup_context()
            if action_id == 'run_wrist_correction':
                config=self._wrist_correction_configuration
                bound,_,_,_=self._load_bound_wrist_correction(config['binding_operation_id'])
                if bound!=config['bound']:
                    raise WizardError('CORRECTION_SETUP_CHANGED','Prepared correction evidence changed.')
                values['_correction_setup_context']=self._powered_setup_context()
                values['_correction_runtime_sha256']=config['report']['runtime_sha256']
                values['_correction_attempt_id']=config['staged'].attempt_id
            if action_id == 'run_observational_movement':
                values['_observational_setup_context'] = self._powered_setup_context()
            if action_id == 'run_first_motion':
                from rocell.safety.first_motion_review_authority import OPERATOR_CHECKS
                attachment = self._first_motion_attachment
                if (attachment is None or values['selection_sha256'] != attachment['draft'].selection_sha256
                        or any(values[name] is not True for name in OPERATOR_CHECKS)):
                    raise WizardError('FIRST_MOTION_CONFIRMATION_INVALID','Confirm the exact attached selection and every operator check.')
                values['_first_motion_setup_context'] = self._powered_setup_context()
            if action_id == 'run_endpoint_trial':
                if (self._endpoint_binding is None or values['acknowledge'] is not True
                        or values['draft_sha256']!=self._endpoint_binding.draft.draft_sha256):
                    raise WizardError('ENDPOINT_DRAFT_CHANGED','Review the exact host-bound trial before preparing.')
                values['_endpoint_setup_context'] = self._powered_setup_context()
            if action_id == "run_passive_arm_connection":
                values["_passive_setup_context"] = self._passive_setup_context()
            if action_id in _POWERED_ACTIONS:
                values["_powered_setup_context"] = self._powered_setup_context()
            if action_id in _NATIVE_ARM_ACTIONS:
                values["_arm_review_sha256"] = self._arm_review_sha256()
            if action_id == "record_passive_arm_setup":
                values["_arm_review_sha256"] = self._arm_review_sha256()
                values["_setup_native_report_sha256"] = self._native_arm_report[
                    "report_sha256"
                ]
            if action.worker == "commissioning":
                values = self._commissioning.bind(action_id, values)
            if action_id == "physical_camera_plan":
                from rocell.providers.windows.native_camera_protocol import (
                    canonical,
                    digest,
                )

                planned = self._physical_camera.preview_plan(
                    values["operation"], self._native_camera
                )
                values["planning_context_sha256"] = digest(canonical(planned))
            if action_id == "physical_camera_probe":
                values["_original_probe_context"] = self._original_probe_context()
                values["_original_probe_context_sha256"] = hashlib.sha256(
                    _json_payload(values["_original_probe_context"])
                ).hexdigest()
            if action_id == "physical_camera_probe_attempt_export":
                values["_probe_attempt_export_context_sha256"] = (
                    self._probe_attempt_export_context()
                )
            if action_id == CONFIGURATION_CAPTURE:
                values["_configuration_capture_context"] = (
                    self._configuration_wizard.preview_context()
                )
            if action_id == OPERATING_PROPOSAL:
                self._operating_proposal.validate_values(values)
                values["_operating_proposal_context"] = (
                    self._operating_proposal.preview_context()
                )
            if action_id == OPERATING_ASSESSMENT:
                values["_operating_assessment_context"] = self._operating_assessment.preview_context(values)
            if action_id == OPERATING_SUBMISSION:
                values["_operating_submission_context"] = self._operating_submission.preview_context(values)
            if action_id == CONFIGURATION_EXPORT:
                values["_configuration_export_context_sha256"] = (
                    self._configuration_wizard.export_context(
                        values["attempt_choice_id"]
                    )
                )
            if action_id == "physical_camera_configuration":
                self._check_physical_camera_settings_identity()
                values["_configuration_context_sha256"] = (
                    self._physical_camera.configuration_context_sha256()
                )
            if action.worker == "physical_camera_setup":
                values["setup_context_sha256"] = (
                    self._physical_camera_setup.context_sha256(
                        action_id,
                        self._native_camera,
                        self._camera_setup_source_report(),
                        values.get("choice_id"),
                    )
                )
            if action_id == "physical_camera_probe_export":
                values["_probe_export_context_sha256"] = self._probe_export_context()
            if action.worker == "physical_intake":
                values["intake_context_sha256"] = self._intake_context_sha256()
            if action.worker == "physical_usb_identity":
                values["_usb_identity_context_sha256"] = (
                    self._usb_identity.context_sha256(
                        native_camera=self._native_camera, helper=self._camera_helper
                    )
                )
                actor = values.get("operator_id", values.get("reviewer_id"))
                if actor is not None and (
                    type(actor) is not str
                    or not 1 <= len(actor) <= 64
                    or actor != actor.strip()
                    or any(not 32 <= ord(c) < 127 for c in actor)
                ):
                    raise WizardError(
                        "USB_IDENTITY_ACTOR",
                        "Use a trimmed printable-ASCII operator/reviewer label of at most 64 characters.",
                    )
                if action_id == "physical_usb_complete_review":
                    from .physical_usb_complete_service import distinct_review_label

                    if not distinct_review_label(
                        self._physical_camera_setup.original_source_workflow(), actor
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Use a procedural reviewer label distinct from the plan author and all four phase operators; labels do not authenticate independent people.",
                        )
                if action_id == "physical_usb_identity_review":
                    inspection = self._usb_identity.view()["inspection"]
                    if (
                        type(actor) is not str
                        or inspection is None
                        or actor.casefold() == inspection["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review the exact USB policy/runtime subject with a distinct procedural label; labels are not authenticated independent people.",
                        )
                if action_id in {
                    "physical_usb_qualification_review",
                    "physical_usb_reconnect_review",
                    "physical_usb_reboot_review",
                }:
                    baseline = self._usb_identity.qualification_view().get(
                        {
                            "physical_usb_qualification_review": "baseline",
                            "physical_usb_reconnect_review": "reconnect",
                            "physical_usb_reboot_review": "reboot",
                        }[action_id]
                    )
                    preparation = (
                        None if baseline is None else baseline.get("preparation")
                    )
                    if (
                        preparation is None
                        or type(actor) is not str
                        or actor.casefold() == preparation["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review the original preparation with a distinct procedural label.",
                        )
                if action_id in {
                    "physical_usb_absence_boot_review",
                    "physical_usb_absence_runtime_review",
                }:
                    absence = self._usb_identity.qualification_view().get("absence")
                    reported = (
                        None if absence is None else absence.get("operator_event")
                    )
                    if (
                        reported is None
                        or type(actor) is not str
                        or actor.casefold() == reported["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review the exact absence scope with a distinct procedural label; labels do not authenticate independent people.",
                        )
                if action_id == "physical_usb_qualification_declare":
                    for key in ("cable_label", "port_label"):
                        label = values[key]
                        if (
                            type(label) is not str
                            or not 0 < len(label.encode("utf-8")) <= 128
                            or label != label.strip()
                            or any(ord(c) < 32 or ord(c) == 127 for c in label)
                        ):
                            raise WizardError(
                                "USB_PLAN_LABEL_INVALID",
                                "Enter a nonempty trimmed single-line cable/port label of at most 128 UTF-8 bytes.",
                            )
            if action.worker == "physical_camera_identity_records":
                values["_camera_identity_context_sha256"] = (
                    self._camera_identity_records.context_sha256(
                        native_camera=self._native_camera, helper=self._camera_helper
                    )
                )
                actor = values.get("operator_id", values.get("reviewer_id"))
                if actor is not None and (
                    type(actor) is not str or _CELL.fullmatch(actor) is None
                ):
                    raise WizardError(
                        "CAMERA_IDENTITY_ACTOR",
                        "Use a bounded portable operator/reviewer label.",
                    )
            if action.worker == "physical_received_camera":
                values["_received_camera_context_sha256"] = (
                    self._received_camera.context_sha256()
                )
                actor = values.get("operator_id", values.get("reviewer_id"))
                if (
                    action_id
                    in {
                        "physical_received_camera_submit",
                        "physical_received_camera_review",
                    }
                    and actor is not None
                    and (type(actor) is not str or _CELL.fullmatch(actor) is None)
                ):
                    raise WizardError(
                        "RECEIVED_CAMERA_ACTOR",
                        "Use a bounded portable operator/reviewer label.",
                    )
                if action_id == "physical_received_camera_review":
                    collection = self._received_camera.view()["collection"]
                    if (
                        type(actor) is not str
                        or collection is None
                        or collection["submission"] is None
                        or actor.casefold()
                        == collection["submission"]["binding"]["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review the exact received-camera subject with a distinct procedural label; labels are not authenticated people.",
                        )
            if action.worker == "physical_static_camera_onboarding":
                values["_static_camera_onboarding_context_sha256"] = (
                    self._static_camera_onboarding.context_sha256()
                )
                actor = values.get("operator_id", values.get("reviewer_id"))
                if actor is not None and (
                    type(actor) is not str or _CELL.fullmatch(actor) is None
                ):
                    raise WizardError(
                        "STATIC_CAMERA_ACTOR",
                        "Use a bounded portable operator/reviewer label.",
                    )
                if action_id == "physical_static_contract_review":
                    contract = self._static_camera_onboarding.view()["contract"]
                    if (
                        type(actor) is not str
                        or contract is None
                        or contract["receipt"] is None
                        or actor.casefold()
                        == contract["receipt"]["binding"]["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review the exact retained design assessment with a distinct procedural label; labels do not authenticate independent people.",
                        )
            if action.worker == "physical_source_qualification":
                values["_source_qualification_context_sha256"] = (
                    self._source_qualification.context_sha256()
                )
                actor = values.get("operator_id", values.get("reviewer_id"))
                if actor is not None and (
                    type(actor) is not str or _CELL.fullmatch(actor) is None
                ):
                    raise WizardError(
                        "SOURCE_QUALIFICATION_ACTOR",
                        "Use a bounded portable operator/reviewer label.",
                    )
                if action_id == "physical_source_qualify":
                    statement = values["isolation_statement"]
                    if (
                        type(statement) is not str
                        or statement.strip() != statement
                        or any(
                            unicodedata.category(char).startswith("C")
                            for char in statement
                        )
                        or len(statement.encode("utf-8")) > 512
                    ):
                        raise WizardError(
                            "ISOLATION_STATEMENT_INVALID",
                            "Use at most 512 UTF-8 bytes of trimmed, control-free isolation text.",
                        )
                    if values["isolation_state"] == "OBSERVED_DISCONNECTED" and (
                        len(statement) < 12 or not values["isolation_choice"]
                    ):
                        raise WizardError(
                            "ISOLATION_ORIGINAL_REQUIRED",
                            "Observed disconnected power requires an explicit statement and an exact discovered original; a checkbox is not an observation.",
                        )
                if action_id == "physical_source_qualification_review":
                    subject = self._source_qualification.view()["qualification"]
                    if (
                        type(actor) is not str
                        or subject is None
                        or actor.casefold() == subject["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review the exact retained qualification with a distinct procedural label; labels do not authenticate independent people.",
                        )
            if action.worker == "physical_intake_evidence":
                values["_intake_evidence_context_sha256"] = (
                    self._physical_intake_evidence.context_sha256(self._physical_intake)
                )
                actor = values.get("operator_id", values.get("reviewer_id"))
                if actor is not None and (
                    type(actor) is not str or _CELL.fullmatch(actor) is None
                ):
                    raise WizardError(
                        "INTAKE_ACTOR_INVALID",
                        "Use a portable bounded operator/reviewer label.",
                    )
                if action_id == "physical_intake_review":
                    collection = self._physical_intake_evidence.view()["collection"]
                    if (
                        type(actor) is not str
                        or collection is None
                        or collection["submission"] is None
                        or actor.casefold()
                        == collection["submission"]["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Review requires the exact retained submission and a distinct label; labels do not authenticate independent people.",
                        )
            if action.worker == "physical_camera_runtime":
                actor = values.get("operator_id", values.get("reviewer_id"))
                if type(actor) is not str or _CELL.fullmatch(actor) is None:
                    raise WizardError(
                        "CAMERA_RUNTIME_ACTOR", "Use a bounded operator/reviewer label."
                    )
                if action_id == "physical_camera_runtime_review":
                    summary = self._physical_camera.runtime_view()["inspection"]
                    if actor.casefold() == summary["operator_id"].casefold():
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Use a distinct reviewer label; labels do not authenticate different people.",
                        )
                values["runtime_context_sha256"] = (
                    self._physical_camera.runtime_context_sha256()
                )
            if len(self._tickets) >= MAX_TICKETS:
                raise WizardError(
                    "TICKET_LIMIT",
                    "Ticket budget reached; export the log folder and start a new session.",
                )
            ticket_id = "ticket-" + uuid.uuid4().hex
            ticket = _Ticket(
                ticket_id,
                action_id,
                deepcopy(values),
                self._state_epoch,
                self.source_sha256,
                self._clock() + TICKET_TTL_SECONDS,
                self._running,
            )
            self._tickets[ticket_id] = ticket
            effects = [
                "Run one registered non-actuating diagnostic worker; no camera/serial open, power change or motion."
            ]
            if action_id == 'review_first_motion_qualification':
                effects = ['Re-read the assessment and reconstruct its native/observation evidence before and after saving the explicit decision.',
                    'No hold override, hardware access, calibrated-accuracy assertion or permission for another move.']
            elif action_id == 'assess_first_motion_qualification':
                effects = ['Re-read native streams and observation originals, recompute telemetry and check the host-owned process association.',
                    'Retain an assessment only; HELD or review-ready is not physical qualification or motion permission.']
            elif action_id == 'use_current_arm_for_observational_test':
                effects = ['Associate the current USB metadata with your model/history report and fixed vendor protocol review.',
                    'No device access, firmware verification, measurements, key creation or movement.']
            elif action_id == 'setup_observational_movement':
                effects = ['Read selected host-reviewed originals and stage the source-pinned runtime.',
                    'No hardware access, key creation or motion. Operator clearance is confirmed separately before running.']
            elif action_id == 'run_observational_movement':
                effects = ['May open the staged arm controller and send one wrist-pitch command.',
                    'Relative increment: '+str(self._observational_configuration['direction'] * self._observational_configuration.get('degrees', 1))+' degrees; spd 20, acc 1.',
                    'Absolute target is derived from the owned baseline. No return or retry. Power shutdown must be reachable.']
                if self._observational_configuration.get('absolute_draft') is not None:
                    draft = self._observational_configuration['absolute_draft'].to_dict()
                    effects = ['May open the arm and move wrist pitch to absolute '+str(draft['target_deg'])+' degrees; spd 20, acc 1.',
                        'Fresh six-joint baseline must match the reviewed start and direction. No return or retry.',
                        'Power shutdown must be reachable; cancellation is not a physical stop.']
            elif action_id == 'record_observational_movement':
                effects = ['Retain your observation against this session\'s exact observational trial.',
                    'No measurement requirement, hardware access, automatic retry or new motion permission.']
            elif action_id == 'record_first_motion_observation':
                effects = ['Re-read this session\'s exact retained result and final request; record the observer\'s report separately.',
                    'No hardware access, physical qualification, automatic retry or campaign advancement.']
            elif action_id == 'attach_retained_first_motion':
                effects = ['Re-read the selected draft, originals and five explicit approvals; check the existing private review key.',
                    'Attach records only. No key provisioning, device open, motion command or final operator confirmation.']
            elif action_id == 'create_first_motion_draft':
                effects = ['Read the selected same-session originals and retain an untimed commissioning draft.',
                    'This does not approve evidence, attach a run, create a key or access hardware.']
            elif action_id == 'record_first_motion_measurements':
                effects = [
                    'Retain self-reported measurements and uncertainty, not verified physical approval.',
                    'No device access or movement. Recording time does not establish measurement time.',
                    'Out-of-proposal measurements remain in the record; they do not enable a trial.',
                ]
            elif action_id in ('record_endpoint_engineering_review', 'record_first_motion_engineering_review', 'review_retained_first_motion_draft'):
                effects = [
                    'Retain the exact draft and this explicit engineering decision in the workspace session log.',
                    'The reviewer identity is self-reported; recording does not independently verify the evidence or enable motion.',
                    'No device open, command, settings change or automatic approval. Export logs retains the decision and draft.',
                ]
            elif action_id == 'run_positional_campaign':
                from math import degrees
                preview = self._positional_campaign_configuration['preview']
                effects = [f"{leg['leg_id']}: expected start {degrees(leg['expected_start_rad']):.3f} degrees -> intended endpoint {degrees(leg['target_rad']):.3f} degrees; transmitted command {degrees(leg['command']['rad']):.6f} degrees."
                    for leg in self._positional_campaign_configuration['preview']['legs']]
                count=self._positional_campaign_configuration['preview']['limits']['maximum_writes']
                axis = 'wrist roll' if preview.get('selected_joint') == 'r' else 'base' if preview.get('selected_joint') == 'b' else 'wrist'
                if preview.get('experiment_kind')=='SPEED_CANDIDATE':
                    effects += ['Speed comparison candidate: transmitted target is frozen from the speed-20 model; that model is not validated at speed 10.']
                if 'synchronization_maximum_ms' in preview['limits']:
                    effects += ['Retain the first line as startup synchronization (maximum 250 ms / 4096 bytes), then require at least one second of clean baseline; no later malformed line is skipped.']
                effects += [f"At most {count} {axis} commands; spd {preview['limits']['spd']}, acc {preview['limits']['acc']}. Fresh six-joint baseline; verification against each intended endpoint.",
                    'No next command after a failed endpoint, timeout or cancellation; no retry or recovery return.',
                    'Opening USB serial may cause startup motion. Software cancellation cannot guarantee physical stopping.',
                    'Retain and verify command/telemetry originals in '+str(self.export_directory)+'.']
            elif action_id == 'run_wrist_correction':
                proposal=self._wrist_correction_configuration['bound'].to_dict()['proposal']
                effects=[f"Nominal endpoint {proposal['nominal_target_deg']} degrees; experimental motor target {proposal['experimental_motor_target_deg']} degrees, spd 20, acc 1.",
                    'One command only after current identity and fresh matching baseline checks. No return or retry.',
                    'Opening serial can cause startup movement. Stay clear; cancellation is not a physical emergency stop.',
                    'Endpoint failure remains failure even if process cleanup and export succeed.']
            elif action_id == 'stage_wrist_correction':
                effects=['Revalidate matched assessment, controller, protocol and saved trial originals.',
                    'Retain a pinned runtime package. No device open, signed movement review or command.']
            elif action_id == 'bind_saved_wrist_correction':
                effects=['Re-read the selected assessment and controller originals; match historical device identity.',
                    'No device open or motion. Current connection, pose and final movement review remain required.']
            elif action_id == 'assess_saved_wrist_correction':
                effects = ['Read selected absolute trial originals from '+str(self.export_directory),
                    'Assess a historical correction hypothesis; no device opens, commands or settings changes.']
            elif action_id == 'read_arm_wifi_feedback':
                effects = ['One HTTP T=105 feedback request to 192.168.0.225 after a local MAC check.',
                    'No movement, configuration changes, USB access or automatic retry. Not a motion baseline.']
            elif action_id == 'sample_arm_wifi_feedback':
                effects = ['Up to eight sequential HTTP T=105 requests with identity checks at 192.168.0.225.',
                    'Stop on the first fault. Retain timing and joint spans; no motion or retry. Not movement qualification.']
            elif action_id == 'observe_arm_wifi_feedback':
                effects = ['Up to 35 seconds of feedback-only observation, at most 200 requests, paced to at most five starts per second.',
                    'Retain exact numeric feedback bodies and stop on the first fault. Cooperative transport lock; no movement or retry.']
            elif action_id in ('run_wifi_roll_sweep_low_trial','run_wifi_roll_sweep_center_trial','run_wifi_roll_sweep_high_trial'):
                command={'run_wifi_roll_sweep_low_trial':.85,'run_wifi_roll_sweep_center_trial':.95,'run_wifi_roll_sweep_high_trial':1.05}[action_id]
                effects=[f'LIVE descending characterization: command {command} degrees, desired 1.25 degrees.',
                    'Fresh delta >0.5 and <=1.5 degrees; speed 20/acc 1. No retry, model update or held-out validation.']
            elif action_id == 'run_wifi_roll_adjacent_lookup_trial':
                effects=['LIVE frozen descending lookup validation: desired roll 1.50 degrees, exact command 1.25 degrees.',
                    'Fresh delta >0.5 and <=1.5 degrees; speed 20/acc 1. No retry or global enablement. Secure and clear arm required.']
            elif action_id in ('run_wifi_roll_adjacent_low_trial','run_wifi_roll_adjacent_high_trial'):
                effects=['LIVE descending probe: desired roll 1.50 degrees; exact command '+
                    ('1.25 degrees.' if action_id=='run_wifi_roll_adjacent_low_trial' else '1.35 degrees.'),
                    'Fresh delta >0.5 and <=1.5 degrees; speed 20/acc 1. No retry or model update. Secure and clear arm required.']
            elif action_id == 'run_wifi_roll_adjacent_trial':
                effects=['LIVE uncorrected descending characterization: desired and commanded roll 1.50 degrees.',
                    'Fresh commanded delta >0.5 and <=1.5 degrees; speed 20/acc 1. One command, no retry or compensation. Secure and clear arm required.']
            elif action_id == 'run_wifi_roll_lookup_trial':
                effects=['LIVE frozen descending lookup validation: desired roll 1.25 degrees, exact command 0.95 degrees.',
                    'Fresh commanded delta >0.5 and <=1.5 degrees; speed 20/acc 1. One command, no retry or global enablement. Secure and clear arm required.']
            elif action_id in ('run_wifi_roll_probe_low_trial','run_wifi_roll_probe_high_trial'):
                effects=['LIVE descending characterization: desired roll 1.25 degrees; command '+
                    ('0.95 degrees.' if action_id=='run_wifi_roll_probe_low_trial' else '1.15 degrees.'),
                    'Fresh commanded delta >0.5 and <=1.5 degrees; speed 20/acc 1. One command, no retry or model update. Secure and clear arm required.']
            elif action_id in ('run_wifi_roll_corrected_up_trial','run_wifi_roll_corrected_down_trial'):
                effects=['LIVE frozen correction experiment: desired roll endpoint 1.25 degrees; command '+
                    ('1.3134765703183617 degrees from below.' if action_id=='run_wifi_roll_corrected_up_trial' else '1.049804687506479 degrees from above.'),
                    'Fresh commanded delta >0.5 and <=1.5 degrees, speed 20/acc 1; one command, no retry or automatic return. Secure and clear arm required.']
            elif action_id in ('run_wifi_roll_zero_trial','run_wifi_roll_center_up_trial','run_wifi_roll_center_down_trial'):
                labels={'run_wifi_roll_zero_trial':'0 degrees from above', 'run_wifi_roll_center_up_trial':'1.25 degrees from below','run_wifi_roll_center_down_trial':'1.25 degrees from above'}
                effects=['LIVE single roll leg to '+labels[action_id]+'.',
                    'Fresh delta >0.5 and <=1.5 degrees; speed 20/acc 1. Arm must be secure and clear. No retry or automatic next movement.']
            elif action_id in ('run_wifi_roll_low_trial','run_wifi_roll_high_trial'):
                effects = ['LIVE fixed target: '+('roll 1 degree approached from above.' if action_id=='run_wifi_roll_low_trial' else 'roll 2.5 degrees approached from below.'),
                    'Fresh delta must be >0.5 and <=1.5 degrees; speed 20/acc 1. One command, ten-second deadline; no retry or automatic return. Arm must be secure and clear.']
            elif action_id == 'run_wifi_roll_negative_trial':
                effects = ['LIVE: fresh-baseline roll -1 degree, absolute target within +/-3 degrees, speed 20/acceleration 1.',
                    'One distinct trial, one-second feedback-gap allowance, ten-second completion budget. No retry or automatic return.',
                    'Arm must be secured, powered and clear. A lost response may mean motion occurred.']
            elif action_id == 'run_wifi_roll_trial':
                effects = ['LIVE: fresh-baseline roll +1 degree, absolute target within +/-3 degrees, speed 20/acceleration 1.',
                    'One dispatch, one-second feedback-gap allowance, ten-second completion budget. No retry, initialization or return.',
                    'Arm must be secured, powered and clear. A lost response may mean motion occurred.']
            elif action_id == 'observe_arm_wifi_bounded':
                effects = ['Feedback-only native HTTP observation: shared absolute 800 ms I/O deadline and 150 ms cooldown.',
                    'Fixed T105 requests, identity checks and transport lock. No movement or retry.']
            elif action_id == 'rehearse_static_task':
                effects = ['Run static-camera nominal geometry and dense sequential IK; no USB, network, camera capture or arm commands.',
                    'The selected park is a simulation overlay, not an installed measurement. A pass cannot enable hardware motion or contact.']
            elif action_id == 'simulate_micro_correction':
                effects=['Run seventeen synthetic micro-correction policy and command-strategy checks.',
                    'No hardware access or movement. Retain results for export; this simulation grants no live authority.']
            elif action_id == 'run_micro_commissioning':
                effects=['LIVE: at most one descending 0.95-degree predecessor and one conditional 0.90-degree micro-command; joint 5, speed 20, acceleration 1.',
                    'Requires an already admissible starting pose, secured powered arm, clear workspace, and no other controller. No automatic positioning, retry or return.',
                    'Verify predecessor and passive hold, export, then stop if already in band. Micro command requires reported roll 1.35–1.45 degrees and fresh matching feedback.',
                    'Up to two 35-second passive holds. Results export automatically to the assigned folder. Cancellation stops progression; it is not a physical emergency stop.']
            elif action_id == 'run_held_pair':
                effects=['LIVE: execute only the host-bound forward target, then return only after exported verified forward arrival.',
                    'Fresh trusted host admission is required; the checkbox does not grant firmware or movement approval.',
                    'No retry or recovery motion. Stop prevents subsequent operations, not commands already delivered.']
                effects.append(str(self._held_pair_binding.preview(self.export_directory)))
            elif action_id == 'review_observed_pair':
                effects=['Replay saved forward/return evidence, source authorization and delivery links.',
                    'Offline servo-count review only. No network, USB, command, retry or physical-tip qualification.']
            elif action_id in ('review_collected_hold', 'review_observed_hold'):
                effects=['Replay saved hold evidence, consumed request and raw transport exports in the assigned folder.',
                    'Display servo-count evidence only. No network, USB, retry, firmware change or hardware qualification.']
            elif action_id in ('review_planned_servo_run','review_started_servo_run','review_startup_servo_run','review_started_startup_run'):
                effects=['Verify saved plan, capture and assessment exports in the assigned folder; linked-start review also checks the consumed claim and delivery record.',
                    'Offline replay only; no network, USB, firmware change or movement.']
            elif action_id == 'simulate_servo_diagnostics':
                effects=['Generate one named synthetic diagnostic trace; no network, USB or movement.',
                    'Export exact trace bytes and assessment to the assigned folder and verify offline replay. A simulated failure is not a hardware diagnosis.']
            elif action_id == 'simulate_discrete_transaction':
                effects = ['Run seven finite in-memory transaction scenarios. No hardware access or commands.',
                    'Retain simulation results for diagnostic export; no movement qualification.']
            elif action_id == 'observe_arm_wifi_feedback_intermediate':
                effects = ['35-second feedback-only diagnostic, at most 234 requests; 150 ms quiet after completion.',
                    'First-fault stop, original retention and cooperative lock; no movement or retry.']
            elif action_id == 'observe_arm_wifi_feedback_spaced':
                effects = ['35-second feedback-only diagnostic, at most 70 requests; 500 ms quiet after completion.',
                    'First-fault stop, original retention and cooperative lock; no movement or retry.']
            elif action_id == 'observe_arm_wifi_feedback_fast':
                effects = ['Up to 35 seconds of feedback-only observation, at most 400 requests, at most ten starts per second.',
                    'Same identity checks and original retention. First-fault stop, cooperative lock; no movement or retry.']
            elif action_id == 'review_endpoint_campaign':
                effects = [
                    'Read only selected endpoint exports from the assigned folder: '+str(self.export_directory),
                    'Reconstruct original-byte comparisons; no port opens, motion, retries or settings changes.',
                    'The result is historical descriptive evidence, not fresh approval or physical qualification.',
                ]
            elif action_id == 'run_first_motion':
                effects = ['May open the reviewed controller and send one fixed T101 joint-4 command after admission.',
                    'Exact selection SHA-256: '+values['selection_sha256'],
                    'No return or retry; cancellation and process cleanup do not prove physical stopping.']
            elif action_id == 'run_endpoint_trial':
                effects = [
                    'May open the reviewed serial controller and send one bounded noncontact motion command after current admission checks.',
                    'Exact draft SHA-256: '+values['draft_sha256'],
                    'Retain baseline, endpoint telemetry and cleanup evidence in the assigned export folder. No automatic return or retry.',
                    'Opening serial may reset the controller. Cancellation is not an emergency stop or proof that the arm has stopped.',
                ]
            elif action.worker == 'positional_campaign_rehearsal':
                from rocell.motion.positional_campaign import compile_wrist_campaign
                campaign = compile_wrist_campaign(values['pattern'],int(values['leg_count']))
                from math import degrees
                campaign_body = campaign.to_dict()
                effects = ['Simulation only: no device access or live campaign admission.',
                    'Exact plan SHA-256: '+campaign.sha256,
                    'Absolute wrist targets; fixed modeled speed fields spd 20 / acc 1.',
                    f"At most {len(campaign_body['legs'])} simulated commands; "
                    f"{len(campaign_body['legs']) * campaign_body['limits']['maximum_leg_s']} modeled seconds for these legs; "
                    'physical commands: 0.',
                    *[f"{leg['leg_id']}: expected start {degrees(leg['expected_start_rad']):.3f} degrees "
                      f"-> absolute target {degrees(leg['target_rad']):.3f} degrees."
                      for leg in campaign_body['legs']],
                    'Each leg: 1-second modeled baseline, 5-second observation; '
                    'target tolerance 0.5 degrees, settling span 0.1 degrees over 200 ms.',
                    'Verify each endpoint and withhold all later simulated writes after any failure.',
                    'Fault: '+values['fault']+' on leg '+values['fault_leg']+'. Export retains synthetic originals.']
            elif action.worker == 'pose_policy_review':
                effects = [
                    'Offline replay of saved pose and installed-settings receipts; no hardware access.',
                    'Identify joint-window mismatches without changing settings or proposing a movement.',
                    'Base placement and full-path clearance remain unknown; sampled stability is historical.',
                    'No startup, hold, recovery, motion or torque changes. Export logs retains the review.',
                ]
            elif action.worker == "movement_campaign":
                from .wizard_movement_campaign import parse_plan
                campaign = parse_plan(values["plan_json"])
                effects = [
                    "Simulation only; no device opens, writes, calibration or movement authority.",
                    "Exact campaign SHA-256: " + campaign.sha256,
                    "Model: synthetic 0.5-second linear travel, 0.05-second samples; speed coefficients do not predict travel time.",
                    "IK, full-link and cable clearance are UNKNOWN. Export logs retains the frozen plan and results.",
                    *[f"Trial {t['trial_id']}: {t['start']} -> {t['target']}; spd coefficient {t['spd']}; timeout {t['timeout_s']} s."
                      for t in campaign.to_dict()["trials"]],
                ]
            elif action.worker == "physical_camera_runtime":
                effects = [
                    (
                        "Inspect only the fixed camera runtime files: at most 40 native paths / 32 MiB, with separate bounded source-fingerprint checks and a 30-second deadline. No helper execution, metadata inventory, M1 store or device access."
                        if action_id == "physical_camera_runtime_inspect"
                        else "Acknowledge the exact retained file report without reinspection. HELD gaps stay HELD; distinct labels are not authenticated identities."
                    ),
                    "Exact runtime/report context SHA-256: "
                    + values["runtime_context_sha256"],
                    "Logging, Stop or source/context changes prevent current publication. No runtime registration, hardware qualification, connection or motion is enabled.",
                ]
            elif action_id == OPERATING_SUBMISSION:
                effects = [
                    "Read saved original setup, the logged proposal and both explicitly selected capture attempts; no device is opened.",
                    "Proposal SHA-256: " + values["_operating_submission_context"]["proposal_sha256"],
                    "Capture requests: " + ", ".join(values["_operating_submission_context"]["capture_requests"]),
                    "Save one immutable proposal/assessment package and move stage 5 to REVIEW_PENDING after readback. This is not review, stage approval, calibration or a connection.",
                    "Stop, changed context or failed logs withhold publication. Bytes already written remain historical; uncertain or partial operations are never automatically retried.",
                ]
            elif action_id == OPERATING_ASSESSMENT:
                effects = [
                    "Acquire existing camera-session storage leases and read saved original setup, probe, settings and the explicitly selected capture records; no device is opened.",
                    "Proposal SHA-256: " + values["_operating_assessment_context"]["proposal_sha256"],
                    "Retain a diagnostic assessment. No original stage record, approval, settings write, new capture or arm action is performed.",
                    "Missing captures, USB/reopen/pixel/freshness evidence and separate review remain unresolved. Stop or changed context prevents a successful result; no automatic retry.",
                ]
            elif action_id == OPERATING_PROPOSAL:
                effects = [
                    "Read only the fixed, bounded purchase-profile file and record a draft for the exact currently logged settings; no device or original store is opened.",
                    "Settings epoch: "
                    + values["_operating_proposal_context"]["settings_epoch"],
                    "Log the rationale without changing the 9-fps reference, applying settings, running a capture or approving a physical stage.",
                    "Source/settings/owner changes, Stop, redaction or failed logs withhold current publication. Export drafts before closing; they are not restored as current on restart.",
                ]
            elif action_id == "physical_camera_configuration":
                effects = [
                    "Stage only the explicitly selected reported mode and electronic-control intent. No camera is opened and no setting is applied.",
                    "Retained probe/settings context SHA-256: "
                    + values["_configuration_context_sha256"],
                    "Withdraw the previous image and readback; a later separately admitted capture is required to observe these settings. Stop/source/log failures prevent current publication.",
                ]
            elif action_id == "physical_camera_probe":
                effects = [
                    "Authenticate the complete original setup and recheck the exact selected camera, installed runtimes and storage headroom before device access.",
                    "Exact reviewed probe plan SHA-256: "
                    + values["_original_probe_context"]["expected_plan_sha256"],
                    "May open only the selected camera for one finite capability probe. No camera control writes, images, serial access, arm startup, motion or contact.",
                    "The disconnected arm supply is your current report, not an electrical measurement. Stop is software cancellation, not an emergency stop.",
                    "Consume this intent once before dispatch. On any failure export the attempt to "
                    + str(self.export_directory)
                    + "; do not automatically retry.",
                ]
            elif action_id == CONFIGURATION_CAPTURE:
                context = values["_configuration_capture_context"]
                effects = [
                    "Authenticate original setup, current logged settings, selected camera, installed runtimes and storage before camera access.",
                    "Apply only the selected reported mode and electronic controls, read back and capture one frame within 5,000 ms native capture and "
                    + str(context["intent"]["capture_budget"]["max_frame_bytes"])
                    + " bytes. No continuous streaming.",
                    "Exact settings-capture plan SHA-256: "
                    + context["expected_capture_plan_sha256"],
                    "Manual lens focus/aperture remain physical adjustments. This test grants no calibration, stage PASS, arm access or motion authority.",
                    "Disconnect the arm actuator supply. Stop cancels software; it is not an emergency stop. Any uncertain attempt must be exported and inspected, not automatically retried.",
                ]
            elif action_id in {
                "physical_camera_probe_attempt_export",
                CONFIGURATION_EXPORT,
            }:
                effects = [
                    "Export complete cached queue/admission/native readback/completion diagnostics beneath "
                    + str(self.export_directory),
                    "Redact credentials before encoding; preserve hashes and label changed bytes. No live store/device read, reconnection or replay.",
                ]
            elif action_id == "physical_camera_plan":
                effects = [
                    "Retain an exact camera acquisition intent in the diagnostic result; no device lookup, file inspection, M1 permit, settings application or camera opening occurs.",
                    "Planning context SHA-256: " + values["planning_context_sha256"],
                    "Missing physical prerequisites remain blocking; neither confirmation nor export approves acquisition.",
                ]
            elif action.worker == "physical_intake":
                effects = [
                    "Retain a complete draft notebook in this diagnostic result; do not write canonical physical-stage evidence or read attachment paths.",
                    "Exact draft / original requirements context SHA-256: "
                    + values["intake_context_sha256"],
                    "Revisions replace the current draft entry only after successful logging. Unknowns stay unknown; measured entries remain unaccepted.",
                    "Export to the assigned diagnostics folder before closing. Drafts are not automatically restored on another launch.",
                ]
            elif action.worker == "physical_intake_evidence":
                effects = [
                    "Only the selected explicit file workflow runs. No device metadata query, camera/serial open, power event, motion or physical acceptance occurs.",
                    "Exact notebook, original-store and discovery context SHA-256: "
                    + values["_intake_evidence_context_sha256"],
                    "Discovery is limited to 32 immediate files / 2 MiB each / 16 MiB total in the assigned inbox. Selected original-store retention stays within its existing 32-reference / 4 MiB total including metadata.",
                    "All sixteen draft rows must be explicit. OBSERVED requires an attachment; UNKNOWN may omit one. Retained originals and exact-subject reviews are append-only; Stop cannot undo committed bytes and never authorizes automatic retry.",
                    "Original source assessment remains BLOCKED. Completeness, byte integrity and distinct labels do not establish measurement truth, independent people or later-stage acceptance.",
                ]
                if action_id == "physical_intake_export_originals":
                    effects.append(
                        "PRIVATE ORIGINALS: copy exact unredacted original media to a fresh folder beneath "
                        + str(self.export_directory)
                        + ". Do not proceed unless exporting potentially private files is intended. Diagnostics-only export does not include these bytes."
                    )
            elif action.worker == "physical_usb_identity":
                effects = [
                    "Exact original USB baseline context SHA-256: "
                    + values["_usb_identity_context_sha256"],
                    "Stop, source/context drift, uncertain cleanup or completion-log failure withdraw current publication. Original evidence remains historical; no automatic retry, capture release or arm authority.",
                ]
                if action_id in {
                    "physical_usb_complete_assess",
                    "physical_usb_complete_review",
                }:
                    effects.insert(
                        0,
                        "File-only: reread the four original USB phases under the current session lease. Retain assessment/review evidence; no USB query, host-boot observation, camera capture, arm access, power, motion or contact. Acceptance is identity-only.",
                    )
                    if action_id == "physical_usb_complete_review":
                        exact = (
                            self._usb_identity.qualification_view().get("complete")
                            or {}
                        )
                        effects.append(
                            "Exact assessment SHA-256: "
                            + str(exact.get("assessment_sha256"))
                        )
                elif action_id == "physical_usb_reboot_boot_collect":
                    effects.insert(
                        0,
                        "Collect the separately reviewed local host-boot observation once for this after-reboot interval. Require the same original host, a different boot after reconnect completion and no later than Begin. A new app launch or operator report is not reboot proof. No Windows restart is performed, no attestation is claimed and no USB query follows automatically.",
                    )
                elif action_id == "physical_usb_reboot_begin":
                    effects.insert(
                        0,
                        "File-only: record your manual Windows Restart report in a distinct launch after complete original reconnect evidence. Then collect and review three fresh generic/native metadata acquisitions and explicitly refresh the original session. Reopening an attempted reboot phase permits history/export only; no acquisition is replayed.",
                    )
                elif action_id in {
                    "physical_usb_reboot_prepare",
                    "physical_usb_reboot_review",
                }:
                    effects.insert(
                        0,
                        "File-only: bind freshly logged after-reboot metadata, exact original predecessors, fixed runtime and separately reviewed query/boot scope. No descriptor query, camera capture, serial access, robot power, motion, contact or restart command.",
                    )
                elif action_id == "physical_usb_reconnect_boot_collect":
                    effects.insert(
                        0,
                        "Collect the separately reviewed local host-boot observation once for this reconnect. Compare with the exact retained absence host/boot; changed or unknown boot evidence is held. No USB query follows automatically and no Windows restart is performed.",
                    )
                elif action_id == "physical_usb_reconnect_begin":
                    effects.insert(
                        0,
                        "File-only: record your reconnect report after complete original physical USB absence. Then collect and review three fresh generic/native metadata acquisitions in this launch. The report is not mechanical proof; reopening this phase permits historical inspection/export only.",
                    )
                elif action_id in {
                    "physical_usb_reconnect_prepare",
                    "physical_usb_reconnect_review",
                }:
                    effects.insert(
                        0,
                        "File-only: bind freshly logged reconnect metadata, exact original predecessor, fixed runtime and independently reviewed query/boot scope. No descriptor query, camera capture, serial access, robot power, motion or contact.",
                    )
                elif action_id == "physical_usb_absence_collect":
                    effects.insert(
                        0,
                        "Run one independently admitted physical USB-node presence query for the literal original BASELINE target. Two bounded Configuration Manager samples; at most four API calls, zero device-handle opens, configuration writes and frames. Unknown observed counts remain null. Up to 25 seconds clipped by the original 30-second permit expiry; the fixed prepared minimum must fit. No replay or endpoint selection.",
                    )
                    effects.append(
                        "Stop is software cancellation, not a robot emergency stop. ABSENT is not mechanical unplug proof, continuous absence or completed reconnect/reboot qualification."
                    )
                elif action_id == "physical_usb_absence_boot_collect":
                    effects.insert(
                        0,
                        "Run the separately reviewed local host-boot observation once under its original intent. The admission window and owned-process lifecycle remain bounded. No USB query follows automatically; only clean same-host/same-boot evidence prepares a later file-only review. A new application launch is not a Windows reboot.",
                    )
                elif action_id.startswith("physical_usb_absence_"):
                    effects.insert(
                        0,
                        "File-only original absence report or exact-subject review. The physical USB target is reconstructed from complete original BASELINE evidence; no live endpoint selection, boot observation, USB query, automatic disconnect/reboot, capture or arm action.",
                    )
                elif action_id == "physical_usb_qualification_declare":
                    effects.insert(
                        0,
                        "File-only: retain one original qualification-trial plan, bound to the received camera's reviewed label and the declared cable/port. No USB query, host-boot observation, physical disconnect, restart, camera capture or arm activity. The earlier baseline is historical, never a newly acquired trial phase.",
                    )
                elif action_id in {
                    "physical_usb_identity_collect",
                    "physical_usb_qualification_collect",
                    "physical_usb_reconnect_collect",
                    "physical_usb_reboot_collect",
                }:
                    effects.insert(
                        0,
                        "Run one explicitly admitted USB descriptor query for the original reviewed target: up to 25 seconds bounded by the original permit expiry; the full prepared 20-second lifecycle must still fit. Native query at most 10 seconds, at most 32 hub opens / 128 reads / 32 closes and 128 KiB retained evidence. No configuration writes, camera frames, serial access, power, motion or contact.",
                    )
                    effects.append(
                        "Hub queries are device effects. Stop cannot undo completed queries or committed bytes; await both owned-process and USB cleanup observations. Unknown counts remain unknown, never zero by inference. Baseline alone is not reconnect/reboot identity qualification."
                    )
                    if action_id == "physical_usb_qualification_collect":
                        effects.insert(
                            0,
                            "First retain one independently owned local host/LastBootUpTime observation under its original request. Only a clean retained boot permits the separate USB admission. No Windows restart, automatic disconnect, or reuse/renewal of a USB permit.",
                        )
                elif action_id == "physical_usb_qualification_begin":
                    effects.insert(
                        0,
                        "File-only: commit the new BASELINE phase boundary. Then explicitly collect and review fresh generic/native metadata in this launch and refresh the original session. Starting the phase does not collect metadata, boot facts or USB descriptors.",
                    )
                elif action_id == "physical_usb_identity_export":
                    effects.insert(
                        0,
                        "Copy retained original USB evidence into a separate bounded metadata bundle under the assigned export folder. No live query, replay or original-store mutation; source/log holds do not prevent historical diagnostic export.",
                    )
                else:
                    effects.insert(
                        0,
                        "File-only inspection or exact-subject policy/runtime review in the original camera store. No USB helper execution, hub open, camera capture, serial access or device activity.",
                    )
                    effects.append(
                        "Procedural operator/reviewer labels are not authenticated independent people. Acknowledging files does not remove observed gaps or select a different target."
                    )
            elif action.worker == "physical_camera_identity_records":
                effects = [
                    "Exact original identity context: "
                    + values["_camera_identity_context_sha256"],
                    "Retain or review server-owned metadata in the original camera store only. No metadata collection, device opening, camera activation, power, motion or stage-5 entry occurs.",
                    "Missing unit-serial provenance, negotiated USB and reconnect/reboot qualification remain specific BLOCKED evidence gaps.",
                ]
                if action_id == "physical_camera_identity_review":
                    effects.append(
                        "Review the exact retained identity subject; procedural labels do not authenticate independent people and cannot upgrade a blocked assessment."
                    )
                elif action_id == "physical_camera_identity_export":
                    effects.append(
                        "Write a separate complete metadata bundle to the assigned export folder, including historical diagnostic coverage. Source/log holds do not make copied evidence current or authorize replay."
                    )
            elif action.worker == "physical_received_camera":
                effects = [
                    "Exact retained received-camera context: "
                    + values["_received_camera_context_sha256"],
                    "No device is opened, no OS inventory or native helper is run, and no power, motion or contact event is authorized.",
                    "Source and static design records remain immutable. Drafts are not acceptance; selected originals must be retained under camera_receipt ownership. Fixed stage-3 PASS does not accept installation, flatness limits, runtime or calibration.",
                    "Stop may withdraw publication but cannot undo original records or exports. No replay, automatic selection or next-stage entry.",
                ]
                if action_id == "physical_received_camera_draft_start":
                    remaining = max(0, MAX_OPERATIONS - self._primary_operations)
                    effects.extend(
                        [
                            f"This launch has {remaining} of {MAX_OPERATIONS} primary actions remaining. Plan about 21 actions for draft start, sixteen explicit row records, one file discovery, submission, exact review and identity-stage entry; corrections or additional discovery need more.",
                            "If that headroom is insufficient, explicitly restart and reopen the original store BEFORE starting the draft. This advisory does not execute, select or reopen anything. Metadata export remains available at the limit, but exporting an unsubmitted draft does not automatically restore it on restart.",
                        ]
                    )
                if action_id == "physical_received_camera_review":
                    collection = self._received_camera.view()["collection"]
                    effects.append(
                        "Exact submission / assessment: "
                        + collection["submission"]["submission_sha256"]
                        + " / "
                        + collection["assessment"]["assessment_sha256"]
                    )
                elif action_id == "physical_camera_identity_begin":
                    effects.append(
                        "Request camera_identity WAITING_OPERATOR only; no metadata enumeration or connection."
                    )
                elif action_id == "physical_received_camera_export":
                    effects.append(
                        "Separate received-stage metadata bundle beneath "
                        + str(self.export_directory)
                        + "; private original media is not copied. Historical export cannot restore current readiness."
                    )
            elif action.worker == "physical_static_camera_onboarding":
                effects = [
                    "Exact original design context: "
                    + values["_static_camera_onboarding_context_sha256"],
                    "No device is opened, no native helper is launched, and no power, motion, contact or installation is released.",
                    "Design-only PASS is distinct from received identity, measurements and installed qualification. Review never enters stage 3 automatically.",
                    "Stop withdraws publication but cannot undo retained original records; no automatic retry or replay.",
                ]
                if action_id == "physical_static_contract_review":
                    contract = self._static_camera_onboarding.view()["contract"]
                    effects.append(
                        "Exact receipt / assessment: "
                        + contract["receipt"]["receipt_sha256"]
                        + " / "
                        + contract["assessment"]["assessment_sha256"]
                    )
                elif action_id == "physical_camera_receipt_begin":
                    effects.append(
                        "Request camera_receipt WAITING_OPERATOR only; no received hardware fact is generated."
                    )
            elif action.worker == "physical_source_qualification":
                effects = [
                    "Use the same original camera store and server-resolved evidence subjects; never replace or replay an uncertain attempt.",
                    "Exact source qualification context SHA-256: "
                    + values["_source_qualification_context_sha256"],
                    "Source-stage acceptance is separate from native camera release, received-device qualification, arm power, motion and contact. No device is opened.",
                    "Stop withdraws current publication but cannot undo committed original evidence. Inspect and export retained diagnostics without automatic retry.",
                ]
                if action_id == "physical_source_isolation_files_discover":
                    effects.append(
                        "Discover bounded original-file metadata in the assigned guarded inbox only. No original bytes are submitted and no isolation observation is inferred."
                    )
                elif action_id == "physical_source_qualify":
                    effects.append(
                        "Collect fresh controlled software facts and run one fixed incapable ownership experiment; retain the explicit isolation statement and selected original if supplied. UNKNOWN remains blocked. Save a deterministic assessment, not a manual PASS."
                    )
                elif action_id == "physical_source_qualification_review":
                    subject = self._source_qualification.view()["qualification"]
                    effects.extend(
                        [
                            "Exact receipt SHA-256: " + subject["receipt_sha256"],
                            "Exact assessment SHA-256: " + subject["assessment_sha256"],
                            "Record a distinct-label procedural review of this exact verdict. It cannot upgrade missing requirements; any source-stage PASS grants no native release.",
                        ]
                    )
                else:
                    effects.append(
                        "Request static-camera contract WAITING_OPERATOR only after committed source-stage PASS. No camera action or stage-2 acceptance follows."
                    )
            elif action_id == "physical_camera_probe_export":
                effects = [
                    "Create a separate hash-verified preparation/review bundle beneath "
                    + str(self.export_directory),
                    "Include complete retained attempts, including uncertain writes. Redact credentials before splitting bounded readable JSON parts. Existing bundles are not overwritten.",
                    "Exact diagnostic body SHA-256: "
                    + values["_probe_export_context_sha256"],
                    "A diagnostic copy cannot restore current enrollment, authorize devices or replay an operation.",
                ]
            elif action.worker == "physical_camera_setup":
                effects = [
                    "Operate only on assigned camera diagnostic storage: "
                    + self._physical_camera_setup.target_directory(),
                    "Initialize pending records, audit the original store, or retain the fixed build requirements according to this selected action. No device is enumerated or opened; no stage is accepted.",
                    "Exact setup context SHA-256: " + values["setup_context_sha256"],
                    "Stop cannot undo committed storage. Inspect original records and export diagnostics without replay or replacement.",
                ]
                if action_id == "physical_camera_discover":
                    effects = [
                        "Read bounded metadata only beneath the assigned camera setup folder. No M1 store, camera, serial endpoint or native helper is opened.",
                        "Retain source-mismatch/partial-store issues; no store is selected or initialized automatically.",
                        "Exact setup context SHA-256: "
                        + values["setup_context_sha256"],
                    ]
                elif action_id == "physical_camera_prerequisites":
                    effects.append(
                        "Retain one initial eight-domain configuration record in the same original store. Missing predecessors and later outputs stay explicit; no hardware observation or acceptance is invented. The record is not regenerated on refresh or restart."
                    )
                elif action_id == "physical_camera_mode_enter":
                    effects[1] = (
                        "Reread the complete accepted identity review, retain one entry record and set camera mode/controls to WAITING_OPERATOR. No camera is opened and no stage is passed."
                    )
                    effects.append(
                        "A partial entry remains diagnostic-only. Probe, settings, images, arm connection and movement require separate later steps."
                    )
                elif action_id in {
                    "physical_camera_probe_prepare",
                    "physical_camera_probe_review",
                }:
                    effects[1] = (
                        "Reread original setup and installed runtime files; retain a preparation or exact-preparation review. No camera is opened, settings applied, frame captured, arm powered or stage passed."
                    )
                    if action_id == "physical_camera_probe_review":
                        effects.append(
                            "Exact preparation SHA-256: "
                            + str(
                                self._physical_camera_setup.probe_record_view()[
                                    "preparation_sha256"
                                ]
                            )
                        )
                    effects.append(
                        "This action is consumed before intent logging; a partial or stopped attempt is not automatically retried."
                    )
                elif action_id == "physical_camera_reopen":
                    original = self._physical_camera_setup.reopen_preview(
                        values["choice_id"]
                    )
                    effects = [
                        "Verify this exact original camera store; never create a replacement or replay a device action.",
                        "Selected original: " + json.dumps(original, sort_keys=True),
                        "Storage qualification/lease metadata may change; original stage evidence and journal are inspected, not rewritten.",
                        "Old requirements remain original-context history, not current endpoint qualification. Current metadata, settings, frames and approvals are not restored.",
                    ]
                elif action_id in {
                    "physical_camera_assess_sources",
                    "physical_camera_review_sources",
                }:
                    effects[1] = (
                        "Save actual file-only receipt and a BLOCKED assessment, then commit REVIEW_PENDING in the original workspace-sources stage."
                        if action_id == "physical_camera_assess_sources"
                        else "A different reviewer label acknowledges the exact original receipt and assessment; save the review and commit workspace-sources BLOCKED."
                    )
                    effects.append(
                        "No PASS override. Power remains UNKNOWN; no device, serial, camera, motion or contact operation is performed. Labels do not authenticate independent people."
                    )
            elif action.worker == "physical_preflight":
                effects = [
                    "Create a new source-only PHYSICAL_DIAGNOSTIC M1 session at "
                    + str(self._source_preflight.directory),
                    "Acquire storage leases, consume one file-check permit and retain/read back actual bounded source/build observations. No device is enumerated or opened; power remains UNKNOWN.",
                    "A coherent report is not canonical stage completion or hardware qualification. Export evidence to the assigned folder; this launch never retries or reopens this attempt.",
                ]
            elif action_id in _NATIVE_ARM_ACTIONS:
                effects = [
                    "Compare fresh bounded serial/Windows metadata with the exact reviewed SERIAL candidate. No COM port is opened, initialized or written.",
                    "The fixed child has a 20-second parent execution budget and bounded cleanup; the Windows collector has a 10-second deadline. Stop withdraws publication, not electrical power.",
                    "Rehearsal uses incapable metadata only. Correlation is not model, firmware, boot, power or physical qualification evidence.",
                ]
            elif action.worker == "inventory":
                effects = [
                    "Read OS camera/serial metadata only; endpoints are not opened or qualified."
                ]
            elif action_id == "rehearse_device_inventory":
                effects = [
                    "Replace the current metadata snapshot and invalidate both candidate reviews using a fixed injected scenario. No host metadata or device endpoint is accessed."
                ]
            elif action_id in _CANDIDATE_ACTIONS:
                try:
                    candidate = self._device_selection.preview(
                        values["choice_id"], _CANDIDATE_ACTIONS[action_id]
                    )
                except DeviceSelectionError as exc:
                    raise WizardError(exc.code, str(exc)) from exc
                effects = [
                    "Record only an acknowledgement of this exact retained metadata candidate. It remains disconnected, unqualified and not a persistent endpoint binding.",
                    "Exact metadata selection: "
                    + json.dumps(candidate, sort_keys=True),
                    "A new inventory or source change invalidates this selection; no automatic reconnect or hardware activation follows.",
                ]
            elif action_id in _HELPER_ACTIONS:
                effects = [
                    "Retire any previous helper registration and native endpoint choices before dispatch. Failure never restores them.",
                    "Inspect only the fixed catalogued files, or review a retained inspection. No helper execution, OS metadata lookup, device activation or arm action.",
                    "Registration permits only explicit inventory/identity metadata queries with file revalidation. It is not a trusted release, physical process qualification, camera connection or capture permission.",
                ]
                if action_id == "camera_helper_review":
                    try:
                        helper_preview = self._camera_helper.preview()
                    except CameraHelperRegistrationError as exc:
                        raise WizardError(exc.code, str(exc)) from exc
                    if (
                        values["reviewer_id"].casefold()
                        == helper_preview["inspection"]["operator_id"].casefold()
                    ):
                        raise WizardError(
                            "REVIEWER_MUST_DIFFER",
                            "Use a reviewer label distinct from the inspection operator. Labels do not authenticate different people.",
                        )
                    effects.append(
                        "Exact retained helper inspection: "
                        + json.dumps(helper_preview, sort_keys=True)
                    )
            elif action_id in _NATIVE_ACTIONS:
                try:
                    native_preview = (
                        self._native_camera.preview(values["choice_id"])
                        if action_id in _NATIVE_CHOICES
                        else {
                            "generic_review": self._device_selection.reviewed_candidate(
                                "CAMERA"
                            ),
                            "provider": self._native_camera.view()["provenance"],
                            "scenario": values.get("scenario"),
                        }
                    )
                except NativeCameraEnrollmentError as exc:
                    raise WizardError(exc.code, str(exc)) from exc
                effects = [
                    "Retain exact native endpoint metadata only. No camera activation, mode probe, control write, arm action or physical qualification.",
                    "Rehearsal uses incapable fixtures; a registered physical provider queries Windows metadata only. Cancellation prevents publication and waits for the bounded lookup to end; it is not a robot emergency stop.",
                    "Exact native metadata request: "
                    + json.dumps(native_preview, sort_keys=True),
                    "This action retires the previous affected review before dispatch; failure never restores an old endpoint binding.",
                ]
            elif action.worker == "export":
                effects = [
                    f"Create one fresh diagnostic export beneath {self.export_directory}; verify its manifest. Existing exports are not overwritten."
                ]
            elif action.worker == "note":
                effects = [
                    "Append a redacted diagnostic note. No test, stage or physical hold is changed."
                ]
            elif action.worker == "stop":
                effects = [
                    "Request cancellation of this diagnostic child process. This is not a robot emergency stop or proof of de-energization."
                ]
            elif action.worker == "commissioning":
                if action_id == "rehearsal_discover":
                    effects = [
                        "Read bounded saved-session metadata beneath the assigned rehearsal folder. No storage qualification, session creation, device access or automatic reopening."
                    ]
                elif action_id == "rehearsal_reopen":
                    selected = values["_selected_store"]
                    effects = [
                        "Explicitly requalify the existing storage volume and acquire/release original session leases. Qualification probes and lease metadata may change; stage evidence/journals are not rewritten.",
                        "Original selected session: "
                        + selected["session_id"]
                        + "; cell: "
                        + selected["cell_id"]
                        + "; directory: "
                        + selected["directory"],
                        "Restore verified evidence only. No previous permit, review acceptance, camera campaign or arm command is replayed. Any pending assessment requires a fresh exact review.",
                    ]
                elif (
                    action_id == "rehearsal_collect"
                    and self._commissioning.view().get("stage")
                    in {"optics_intrinsics", "static_registration"}
                ):
                    effects = [
                        "Open the due synthetic optics stage under original-session storage leases and retain its operator record.",
                        "Verify the retained stage-six camera dependency, then run the fixed intrinsics parser/assessment or normal plus tag-loss nominal JPEG pixel probes. No physical camera is opened; the binary dataset is not the evaluated pixels.",
                        "Retain the complete bounded technical report before assessment. Stop before publication leaves a held stage; reopening never reruns a missing evaluation. No physical calibration or stage PASS is inferred from collection.",
                    ]
                elif (
                    action_id == "rehearsal_collect"
                    and self._commissioning.view().get("stage") == "arm_identity"
                ):
                    effects = [
                        "Open the due arm-identity rehearsal stage and bind its operator to the exact reviewed static-registration receipt, assessment and review.",
                        "Load the configured arm profile and run the existing inventory/composition code using closed injected serial metadata fixtures. This neither enumerates the host nor opens a serial endpoint; USB or COM metadata cannot establish received Pro, driver or firmware identity.",
                        "Verify retained camera dependencies and retain the complete bounded report. Nominal acceptance and expected-fault checks are separate. A missing result holds on reopening; collection does not grant physical qualification or motion authority.",
                    ]
                elif (
                    action_id == "rehearsal_collect"
                    and self._commissioning.view().get("stage")
                    in {"power_safety", "power_on_observation"}
                ):
                    effects = [
                        "Open the due power-procedure rehearsal stage and bind it to its exact reviewed predecessor and arm-identity report.",
                        "Run the existing typed power-safety or first-power assessor on fixed synthetic procedure observations, including abnormal and uncertain cases. Do not energize the arm for this action. No startup trajectory is predicted, E-stop is tested, or final power state is observed.",
                        "Verify retained dependencies and save the complete bounded assessor report. Stop before publication leaves a hold; reopening never reruns missing evidence. Successful fault handling is not nominal acceptance or permission for physical power, serial access, motion or contact.",
                    ]
                elif (
                    action_id == "rehearsal_collect"
                    and self._commissioning.view().get("stage")
                    == "reference_frame_calibration"
                ):
                    effects = [
                        "Open the nominal reference-frame rehearsal and verify exact reviewed optics, static registration and retained feedback-campaign dependencies, including its separate synthetic final-power observation.",
                        "Evaluate the source-pinned calibration graph, nominal URDF frame chain and rigid point-correspondence fit with untouched held-out points. Camera records are dependencies, not measured point inputs; serial feedback is not calibrated joint data. Two target coordinate round trips do not establish whole-board reachability.",
                        "Retain complete numerical and graph evidence before assessment. A missing result holds on reopening; no fitter, worker or motion is replayed. Eight physical reference components remain pending, with no installed calibration, energy, motion or contact authority.",
                    ]
                elif (
                    action_id == "rehearsal_collect"
                    and self._commissioning.view().get("stage")
                    == "noncontact_acceptance"
                ):
                    effects = [
                        "Open the due readiness gap diagnostic under original-session leases and verify the complete reviewed stage-thirteen reference and its exact camera/feedback dependencies.",
                        "Audit actual historical collision sources, inventory separate static-camera requirements, and run fixed typed accuracy-budget controls. No IK search, route campaign, virtual contact, camera, serial or physical motion is run.",
                        "Retain complete inputs/results. Missing installed geometry and unmeasured real-build terms remain BLOCKED/UNBOUNDED even when synthetic fault checks pass. Exact review cannot advance to physical handoff.",
                    ]
                elif action_id == "rehearsal_owned_camera_campaign":
                    effects = [
                        "Bind the due camera-stage operator, selected synthetic identity and exact settings epoch to a one-use coordinator permit. Retire the prior preview before dispatch; this action cannot run in physical mode.",
                        "Launch one owned, contained incapable child using a fixed source-derived native-format fixture plan. Capture 1–4 frames with the selected closed fault; reserve about 85 MB per frame plus a storage margin. No physical camera, arbitrary executable, endpoint or command is selected.",
                        "Retain actual child creation/resume/tree-exit and cleanup observations separately from the synthetic native receipt and dataset. Verify retained bytes before deriving a synthetic preview. Failure, Stop, source drift or log loss does not promote a new image or authorize replay; no driver, USB3 link, device cleanup or camera qualification is granted.",
                    ]
                elif action_id == "rehearsal_camera_probe":
                    effects = [
                        "Retain one exact consumed-permit capability probe through the fixed contained incapable process. No frames or electronic control writes are requested.",
                        "Display reported modeled modes, control ranges and current flags only after complete retained evidence. Do not infer purchased-camera support or qualification; Stop or failure is not permission to replay.",
                    ]
                elif action_id == "rehearsal_camera_configuration":
                    effects = [
                        "Validate all selected reported mode/control fields against the exact retained probe before any camera operation.",
                        "Save immutable source/identity/probe-bound intent and its settings epoch. No camera is opened and no controls are applied. The later contained capture must supply independent readback.",
                    ]
                elif action_id == "rehearsal_arm_feedback_campaign":
                    effects = [
                        "Bind one in-memory controller to the exact reviewed identity and power-stage evidence, a fresh synthetic energy envelope and a one-use coordinator permit.",
                        "Exercise the actual feedback worker with the sealed incapable serial backend: one open, at most one fixed feedback write, bounded reads and one close attempt. Never open a physical COM port, energize the arm or send motion/contact commands.",
                        "Retain complete bounded serial evidence before known sealing. Evaluate technical response, serial cleanup and a separate synthetic post-campaign power observation independently. Missing evidence, Stop or uncertainty holds the cell; do not retry it.",
                    ]
                elif action_id == "rehearsal_owned_arm_feedback_campaign":
                    effects = [
                        "Bind the reviewed stage-12 source, controller identity and synthetic power dependencies to one exact consumed coordinator permit. Prepare one fixed source-bound incapable child package before issuing its energy envelope; no physical port or power event is available.",
                        "Launch at most one owned child with a 20-second parent budget and one fixed feedback transaction, a 2048-byte line limit, bounded reads and one close attempt. The selected closed scenario is not an arbitrary command, endpoint or executable.",
                        "Retain actual process creation, resume and tree-exit observations separately from modeled non-purging serial cleanup, feedback validity and an independent synthetic final-power observation. Stop, timeout, malformed output or uncertain cleanup holds without replay or fallback to the memory-only action. Process exit and serial close never prove physical de-energization.",
                    ]
                elif (
                    action_id == "rehearsal_collect"
                    and self._commissioning.view().get("stage")
                    == "feedback_only_connection"
                ):
                    effects = [
                        "Retain the due feedback-stage operator and verify exact reviewed identity/power/board dependencies. No serial worker is dispatched by collection.",
                        "Choose one separate feedback campaign: the existing memory-only action or the contained incapable child action. Then assess and review retained evidence. There is no automatic fallback, replay, physical port or power-state access.",
                    ]
                else:
                    effects = [
                        "Mutate only the separate immutable REHEARSAL session using qualified storage leases. No physical device operation occurs.",
                        "Current rehearsal assessment: "
                        + json.dumps(
                            self._commissioning.view().get("assessment"), sort_keys=True
                        ),
                    ]
            return {
                "ticket_id": ticket_id,
                "action_id": action_id,
                "label": action.label,
                "effects": effects,
                "warnings": [
                    "No physical hardware authority is granted.",
                    "A timeout is not permission to replay an operation.",
                ],
                "expires_in_s": TICKET_TTL_SECONDS,
                "source_binding_sha256": self.source_sha256,
                "state_epoch": ticket.state_epoch,
                "input": sanitize_diagnostic_record(
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    }
                ),
                "physical_authority": False,
            }

    def execute_action(self, ticket_id: str) -> dict[str, Any]:
        with self._lock:
            ticket = self._tickets.get(ticket_id) if type(ticket_id) is str else None
            if ticket is None:
                raise WizardError(
                    "UNKNOWN_TICKET",
                    "No ticket exists in this launch; nothing was executed.",
                )
            if ticket.receipt is not None:
                operation = self._operations.get(ticket.receipt["operation_id"])
                return {
                    **ticket.receipt,
                    "status": (
                        operation["status"] if operation else ticket.receipt["status"]
                    ),
                }
            if self._clock() >= ticket.expires_at:
                raise WizardError(
                    "TICKET_EXPIRED",
                    "The action ticket expired; preview the current state again.",
                )
            if (
                ticket.state_epoch != self._state_epoch
                or ticket.source_sha256 != self.source_sha256
                or ticket.running_operation_id != self._running
            ):
                raise WizardError(
                    "STALE_TICKET",
                    "The operation state changed; this ticket cannot execute.",
                )
            action = ACTION_BY_ID[ticket.action_id]
            available = self._action_view(action)
            if not available["enabled"]:
                raise WizardError(
                    "ACTION_BLOCKED", " ".join(available["blocked_reasons"])
                )
            self._recheck_source(ticket.action_id)
            if ticket.action_id == 'run_first_motion' and (
                self._first_motion_attachment is None
                or ticket.values['selection_sha256'] != self._first_motion_attachment['draft'].selection_sha256
                or ticket.values['_first_motion_setup_context'] != self._powered_setup_context()
            ):
                raise WizardError('FIRST_MOTION_CONTEXT_CHANGED','Commissioning selection or powered setup changed.')
            if ticket.action_id == 'run_endpoint_trial' and (
                self._endpoint_binding is None
                or ticket.values['draft_sha256']!=self._endpoint_binding.draft.draft_sha256
                or ticket.values['_endpoint_setup_context']!=self._powered_setup_context()
            ):
                raise WizardError('ENDPOINT_CONTEXT_CHANGED','Trial or powered setup changed after preview.')
            if ticket.action_id == "physical_camera_probe" and (
                self._original_probe_context()
                != ticket.values["_original_probe_context"]
            ):
                raise WizardError(
                    "CAMERA_PROBE_CONTEXT_CHANGED",
                    "The exact original setup changed after preview. Nothing was queued or dispatched.",
                )
            if (
                ticket.action_id == CONFIGURATION_CAPTURE
                and self._configuration_wizard.preview_context()
                != ticket.values["_configuration_capture_context"]
            ):
                raise WizardError(
                    "CONFIGURATION_CONTEXT_CHANGED",
                    "Settings-capture context changed after preview; nothing was queued.",
                )
            if (
                action.worker == "physical_usb_identity"
                and ticket.action_id != "physical_usb_identity_export"
                and ticket.values["_usb_identity_context_sha256"]
                != self._usb_identity.context_sha256(
                    native_camera=self._native_camera, helper=self._camera_helper
                )
            ):
                raise WizardError(
                    "USB_IDENTITY_CONTEXT_CHANGED",
                    "Original USB baseline context changed after preview; nothing was dispatched.",
                )
            if ticket.action_id == "run_passive_arm_connection" and (
                ticket.values["_passive_setup_context"] != self._passive_setup_context()
            ):
                raise WizardError(
                    "PASSIVE_SETUP_CHANGED",
                    "Setup changed after preview; nothing dispatched.",
                )
            if ticket.action_id == "record_passive_arm_setup" and (
                ticket.values["_setup_native_report_sha256"]
                != (self._native_arm_report or {}).get("report_sha256")
            ):
                raise WizardError(
                    "PASSIVE_SETUP_METADATA_CHANGED",
                    "Arm metadata changed after setup preview; nothing was recorded.",
                )
            if (
                ticket.action_id in _NATIVE_ARM_ACTIONS
                or ticket.action_id == "record_passive_arm_setup"
            ) and (ticket.values["_arm_review_sha256"] != self._arm_review_sha256()):
                raise WizardError(
                    "ARM_REVIEW_CHANGED",
                    "The original arm metadata review changed; preview the current selection again.",
                )
            if action.worker == "physical_camera_runtime":
                self._physical_camera.begin_runtime_action(
                    ticket.action_id, ticket.values["runtime_context_sha256"]
                )
            if (
                action.worker == "physical_camera_configuration"
                and ticket.values["_configuration_context_sha256"]
                != self._physical_camera.configuration_context_sha256()
            ):
                raise WizardError(
                    "CAMERA_CONFIGURATION_CONTEXT",
                    "The retained native probe/settings changed after preview.",
                )
            if ticket.action_id == OPERATING_PROPOSAL:
                if (
                    self._operating_proposal.preview_context()
                    != ticket.values["_operating_proposal_context"]
                ):
                    raise WizardError(
                        "MODE_PROPOSAL_CONTEXT_CHANGED",
                        "The logged settings or entry changed after preview; no draft was queued.",
                    )
            if ticket.action_id == OPERATING_ASSESSMENT:
                if self._operating_assessment.preview_context(ticket.values) != ticket.values["_operating_assessment_context"]:
                    raise WizardError("OPERATING_ASSESSMENT_STALE", "Proposal, settings or selected captures changed after preview.")
            if ticket.action_id == OPERATING_SUBMISSION:
                if self._operating_submission.preview_context(ticket.values) != ticket.values["_operating_submission_context"]:
                    raise WizardError("OPERATING_SUBMIT_STALE", "Proposal, setup or selected originals changed after preview.")
            if (
                ticket.action_id in _POWERED_ACTIONS
                and ticket.values["_powered_setup_context"]
                != self._powered_setup_context()
            ):
                raise WizardError(
                    "POWERED_SETUP_CHANGED",
                    "Powered setup or USB selection changed after preview.",
                )
            operation_id = "operation-" + uuid.uuid4().hex
            if ticket.action_id == 'run_positional_campaign':
                config = self._positional_campaign_configuration
                if (config is None or self._positional_campaign_confirmation is not None
                        or ticket.values['_campaign_id'] != config['preview']['campaign_id']
                        or ticket.values['_campaign_context'] != self._powered_setup_context()
                        or config['context'] != self._powered_setup_context()):
                    raise WizardError('CAMPAIGN_SETUP_CHANGED','Campaign setup changed or acceptance was consumed.')
                self._positional_campaign_confirmation = (operation_id, config, time.monotonic_ns())
            if ticket.action_id == 'run_wrist_correction':
                config=self._wrist_correction_configuration
                if (config is None or self._wrist_correction_confirmation is not None
                        or ticket.values['_correction_runtime_sha256']!=config['report']['runtime_sha256']
                        or ticket.values['_correction_attempt_id']!=config['staged'].attempt_id
                        or ticket.values['_correction_setup_context']!=self._powered_setup_context()):
                    raise WizardError('CORRECTION_SETUP_CHANGED','Correction setup changed or acceptance already consumed.')
                if self._load_bound_wrist_correction(config['binding_operation_id'])[0]!=config['bound']:
                    raise WizardError('CORRECTION_SETUP_CHANGED','Correction originals changed after preview.')
                operation_id=config['staged'].attempt_id
                self._wrist_correction_confirmation=(operation_id,config,time.monotonic_ns())
            if ticket.action_id == 'run_observational_movement':
                config = self._observational_configuration
                if (config is None or self._observational_confirmation is not None
                        or self._powered_setup_context() != config['context']
                        or ticket.values['_observational_setup_context'] != config['context']):
                    raise WizardError('OBSERVATIONAL_SETUP_CHANGED','Staged setup changed or attempt already consumed.')
                operation_id = config['staged'].attempt_id
                self._observational_confirmation = (operation_id, config, time.monotonic_ns())
            operation = {
                "operation_id": operation_id,
                "action_id": ticket.action_id,
                "label": action.label,
                "status": "QUEUED",
                "created_at": _now_text(),
                "message": "Queued for explicit diagnostic execution.",
                "progress_count": 0,
                "physical_authority": False,
                "mode": self.mode,
                "result": None,
                "result_retention": "NOT_FINISHED",
                "error": None,
            }
            self._operations[operation_id] = operation
            ticket.receipt = {"operation_id": operation_id, "status": "QUEUED"}
            if ticket.action_id == 'run_first_motion':
                from rocell.safety.first_motion_review_authority import OPERATOR_CHECKS
                # Burn the attachment at acceptance, before logging or queueing.
                # Queue delay never renews this host-owned final-click timestamp.
                self._first_motion_attempt_id = operation_id
                accepted_ns = time.monotonic_ns()
                self._first_motion_confirmation = (operation_id, self._first_motion_attachment, accepted_ns)
                if not self._append_event('first_motion_final_click_accepted', dict(
                        operation_id=operation_id, accepted_ns=accepted_ns,
                        selection_sha256=ticket.values['selection_sha256'],
                        operator_id=ticket.values['operator_id'],
                        answers={name:ticket.values[name] for name in OPERATOR_CHECKS},
                        physical_authority=False)):
                    self._finish(operation_id,'FAILED',{'code':'DIAGNOSTIC_LOG_FAILED',
                        'message':'Final confirmation could not be retained; attempt consumed.', 'physical_authority':False})
                    return dict(ticket.receipt)
            if ticket.action_id == 'run_endpoint_trial':
                from .endpoint_operator_confirmation import record_final_confirmation
                from rocell.safety.bench_review_authority import OPERATOR_CHECKS
                # Accept the explicit final click under the existing action
                # lock. Compile/record now, not later after queue delay. Consume
                # this attachment before any publication that might fail.
                binding = self._endpoint_binding
                self._endpoint_attempt_id = operation_id
                def confirmation_current():
                    self._recheck_source(ticket.action_id)
                    if (self._endpoint_binding is not binding or binding is None
                            or ticket.values['_endpoint_setup_context'] != self._powered_setup_context()):
                        raise WizardError('ENDPOINT_CONTEXT_CHANGED','Final confirmation setup changed.')
                try:
                    if not self._append_event('endpoint_final_confirmation_accepted',{
                        'operation_id':operation_id,'draft_sha256':ticket.values['draft_sha256'],
                        'operator_id':ticket.values['operator_id'],
                        'answers':{name:ticket.values[name] for name in OPERATOR_CHECKS},
                        'physical_authority':False}):
                        raise WizardError('DIAGNOSTIC_LOG_FAILED','Final confirmation could not be retained.')
                    confirmed = record_final_confirmation(draft=binding.draft,
                        expected_draft_sha256=ticket.values['draft_sha256'],attempt_id=operation_id,
                        actor_id=ticket.values['operator_id'],
                        answers={name:ticket.values[name] for name in OPERATOR_CHECKS},
                        root=self._log.root,deadline_ns=time.monotonic_ns()+int(action.timeout_s*1_000_000_000),
                        check_current=confirmation_current)
                    if not self._append_event('endpoint_final_confirmation_recorded',{
                        'operation_id':operation_id,'request':confirmed.request.to_dict(),
                        'request_sha256':confirmed.request.request_sha256,
                        'operator_reviews':[json.loads(raw) for raw in confirmed.operator_originals],
                        'physical_authority':False}):
                        raise WizardError('DIAGNOSTIC_LOG_FAILED','Recorded confirmation could not be logged.')
                    self._endpoint_confirmation = (operation_id,binding,confirmed)
                except Exception as error:
                    self._finish(operation_id,'FAILED',{
                        'code':'ENDPOINT_CONFIRMATION_FAILED','message':str(error),
                        'physical_authority':False})
                    return dict(ticket.receipt)
            if ticket.action_id == CONFIGURATION_CAPTURE:
                try:
                    self._configuration_wizard.queue(
                        operation_id,
                        ticket.values["_configuration_capture_context"],
                        ticket.values,
                    )
                except (WizardError, ValueError) as error:
                    self._clear_camera_preview("PHYSICAL_CAMERA_QUEUE_WITHDRAWN")
                    self._trim_operations()
                    self._finish(
                        operation_id,
                        "FAILED",
                        {
                            "code": getattr(
                                error, "code", "CONFIGURATION_QUEUE_FAILED"
                            ),
                            "message": str(error),
                            "physical_authority": False,
                        },
                    )
                    return dict(ticket.receipt)
            # Bind the capture queue before rotating older metadata operations.
            # If rotation retires a required owner, the active guard fails with
            # a retained queued outcome instead of leaving an orphaned QUEUED op.
            self._trim_operations()
            if ticket.action_id == "physical_camera_probe":
                # Consume before intent logging: an uncertain queue/log outcome
                # must remain inspectable, never become an automatic retry.
                self._probe_dispatch_queue = dict(
                    operation_id=operation_id,
                    context_sha256=ticket.values["_original_probe_context_sha256"],
                    claimed=False,
                )
            if ticket.action_id in _NATIVE_ARM_ACTIONS | _INVENTORY_ACTIONS | {
                "review_arm_candidate"
            }:
                # Retire before intent logging as well as before child dispatch.
                self._invalidate_native_arm("ARM_METADATA_CONTEXT_CHANGED")
                if ticket.action_id in _NATIVE_ARM_ACTIONS:
                    self._native_arm_report = None
                    self._native_arm_summary = None
            if action.worker == "physical_camera_setup":
                if ticket.action_id == "physical_camera_mode_enter":
                    self._physical_camera_setup.begin_mode_entry(
                        ticket.values["setup_context_sha256"], operation_id
                    )
                elif ticket.action_id in {
                    "physical_camera_probe_prepare",
                    "physical_camera_probe_review",
                }:
                    self._physical_camera_setup.begin_probe_record(
                        ticket.action_id,
                        ticket.values["setup_context_sha256"],
                        operation_id,
                    )
                self._physical_camera_setup.invalidate()
                if ticket.action_id == "physical_camera_reopen":
                    self._physical_camera.invalidate()
            if action.worker == "physical_camera_configuration":
                self._configuration_wizard.withdraw_settings()
                self._physical_camera.begin_configuration_action(
                    ticket.values["_configuration_context_sha256"]
                )
            if action.worker == "commissioning":
                # A refreshed stage challenge is a new publication boundary,
                # even when the original numerical bytes have not changed.
                self._published_noncontact_sha256 = None
            if (
                ticket.action_id in _INVENTORY_ACTIONS
                or ticket.action_id in _HELPER_ACTIONS
                or ticket.action_id in _NATIVE_ACTIONS
                or ticket.action_id in {"review_camera_candidate"}
            ):
                self._physical_camera.invalidate()
                self._physical_camera_setup.invalidate()
                self._camera_identity_records.invalidate()
                self._usb_identity.invalidate()
            if ticket.action_id == "physical_camera_plan":
                self._physical_camera.withdraw_plan_publication()
            if ticket.action_id in _PREVIEW_INVALIDATING_ACTIONS:
                # Admission is explicit; view/prepare never retire an image.
                # Clear before intent logging, including a failed log attempt.
                self._clear_camera_preview("NO_CURRENT_STAGE_CAPTURE")
            logged = self._append_event(
                "ACTION_EXECUTED",
                {
                    "operation_id": operation_id,
                    "action_id": ticket.action_id,
                    "state_epoch": self._state_epoch,
                },
            )
            if (
                not logged
                and action.worker not in {"export", "stop", "note"}
                and ticket.action_id
                not in {
                    "physical_received_camera_export",
                    "physical_camera_identity_export",
                    "physical_usb_identity_export",
                    "physical_camera_probe_export",
                    "physical_camera_probe_attempt_export",
                    CONFIGURATION_EXPORT,
                }
            ):
                self._finish(
                    operation_id,
                    "FAILED",
                    {
                        "code": "DIAGNOSTIC_LOG_FAILED",
                        "message": "Worker was not dispatched because intent logging failed.",
                        "physical_authority": False,
                    },
                )
                return {"operation_id": operation_id, "status": "FAILED"}
            if action.worker in {"export", "stop", "note"}:
                self._housekeeping(operation_id, ticket)
                ticket.receipt["status"] = operation["status"]
                return dict(ticket.receipt)
            if ticket.action_id in _INVENTORY_ACTIONS:
                # Retire old choices before dispatch, even if the new query is
                # cancelled, malformed or incomplete. Never reuse stale identity.
                self._device_selection.invalidate("INVENTORY_REFRESH_STARTED")
            if ticket.action_id in _HELPER_ACTIONS:
                self._native_registration_managed = True
                self._revoke_helper(
                    (
                        "HELPER_REVIEW_STARTED"
                        if ticket.action_id == "camera_helper_review"
                        else "HELPER_INSPECTION_STARTED"
                    ),
                    preserve_inspection=ticket.action_id == "camera_helper_review",
                )
            if (
                ticket.action_id in _INVENTORY_ACTIONS
                or ticket.action_id == "review_camera_candidate"
            ):
                self._native_camera.invalidate("GENERIC_CAMERA_REVIEW_CHANGED")
            elif ticket.action_id == "native_camera_inventory":
                self._native_camera.invalidate("NATIVE_INVENTORY_REFRESH_STARTED")
            elif ticket.action_id == "native_camera_identity":
                self._native_camera.invalidate_identity(
                    "NATIVE_IDENTITY_REFRESH_STARTED"
                )
            elif ticket.action_id == "native_camera_review":
                self._native_camera.invalidate_review("NATIVE_REVIEW_STARTED")
            if ticket.action_id not in _HOUSEKEEPING:
                self._primary_operations += 1
            self._running = operation_id
            self._cancel = threading.Event()
            self._changed(state=True)
            if self._executor is None:
                self._executor = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="rocell-diagnostic"
                )
            self._executor.submit(
                self._run,
                operation_id,
                ticket.action_id,
                deepcopy(ticket.values),
                self._cancel,
            )
            return dict(ticket.receipt)

    def _housekeeping(self, operation_id: str, ticket: _Ticket) -> None:
        try:
            if ticket.action_id == "stop_operation":
                assert self._cancel is not None
                self._cancel.set()
                self._camera_identity_records.invalidate()
                self._usb_identity.invalidate()
                result = {
                    "status": "CANCEL_REQUESTED",
                    "target_operation_id": self._running,
                    "message": "Diagnostic cancellation requested; await the target operation's cleanup outcome. Not a robot emergency stop.",
                    "physical_authority": False,
                }
            elif ticket.action_id == "record_note":
                if not self._append_event(
                    "OPERATOR_NOTE",
                    {"note": ticket.values["note"], "physical_stage_change": "NONE"},
                ):
                    raise WizardError(
                        "DIAGNOSTIC_LOG_FAILED",
                        "The note could not be persisted; no resolution was recorded.",
                    )
                result = {
                    "message": "Diagnostic note recorded. Test outcomes and physical holds are unchanged.",
                    "physical_authority": False,
                }
            else:
                result = self._export()
            self._finish(operation_id, "SUCCEEDED", result)
        except Exception as exc:
            self._finish(
                operation_id,
                "FAILED",
                {
                    "code": getattr(exc, "code", "DIAGNOSTIC_ACTION_FAILED"),
                    "message": str(exc)[:1500],
                    "physical_authority": False,
                },
            )

    def _run(
        self,
        operation_id: str,
        action_id: str,
        values: dict[str, Any],
        cancel: threading.Event,
    ) -> None:
        # The mode-entry owner receives this original outer deadline; progress
        # logging and its inner readbacks cannot renew the action's time budget.
        operation_deadline_ns = (
            time.monotonic_ns() + ACTION_BY_ID[action_id].timeout_s * 1_000_000_000
        )
        with self._lock:
            metadata_started_at_ns = time.time_ns()
            metadata_token = self._usb_identity.acquisition_started(
                action_id, operation_id, metadata_started_at_ns
            )
            self._operations[operation_id]["status"] = "RUNNING"
            self._operations[operation_id]["message"] = (
                "One exact physical USB-node presence query is running; await original counts and cleanup. Stop is software cancellation, not an emergency stop."
                if action_id == "physical_usb_absence_collect"
                else (
                    "One independently reviewed local host-boot observation is running. No USB query follows automatically."
                    if action_id
                    in {
                        "physical_usb_absence_boot_collect",
                        "physical_usb_reconnect_boot_collect",
                        "physical_usb_reboot_boot_collect",
                    }
                    else (
                        "The bounded original host-boot observation comes first; a USB query may follow only after separate admission. No capture or arm access."
                        if action_id == "physical_usb_qualification_collect"
                        else (
                            "One explicitly admitted USB descriptor query is running; await retained counts and cleanup. No capture or arm access."
                            if action_id
                            in {
                                "physical_usb_identity_collect",
                                "physical_usb_reconnect_collect",
                                "physical_usb_reboot_collect",
                            }
                            else (
                                "Authenticating the original setup before one bounded selected-camera probe. No arm access; await original counts and cleanup."
                                if action_id == "physical_camera_probe"
                                else (
                                    "Authenticating original logged settings for one bounded camera frame. Camera settings may be applied; no arm access. Await readback and cleanup."
                                    if action_id == CONFIGURATION_CAPTURE
                                    else (
                                        "One admitted wrist test is running and may open the arm and move it. Stay clear; software cancellation is not a physical stop. Await telemetry and cleanup."
                                        if action_id in ('run_observational_movement','run_wrist_correction')
                                        else "Registered operation is running. Follow its reviewed effects; await the retained result for device activity and cleanup."
                                    )
                                )
                            )
                        )
                    )
                )
            )
            self._changed()

        def progress(message: str) -> None:
            with self._lock:
                operation = self._operations[operation_id]
                operation["message"] = sanitize_diagnostic_record(str(message)[:500])
                operation["progress_count"] += 1
                if operation["progress_count"] <= 20 and not (
                    action_id
                    in {
                        "physical_received_camera_export",
                        "physical_camera_identity_export",
                        "physical_usb_identity_export",
                        "physical_camera_probe_export",
                        "physical_camera_probe_attempt_export",
                        CONFIGURATION_EXPORT,
                    }
                    and self._log_error
                ):
                    self._append_event(
                        "DIAGNOSTIC_PROGRESS",
                        {"operation_id": operation_id, "message": operation["message"]},
                    )
                self._changed()

        native_retained_result: dict[str, Any] | None = None
        staged_intake: PhysicalIntakeNotebook | None = None
        staged_arm: dict[str, Any] | None = None
        staged_arm_summary: dict[str, Any] | None = None
        try:
            staged_selection = None
            staged_native = None
            staged_native_provider = None
            staged_helper = None
            result: dict[str, Any]
            if action_id == "record_passive_arm_setup":
                from .wizard_passive_arm_setup import record_setup

                with self._lock:
                    self._recheck_source(action_id)
                    current_arm = self._native_arm_view()
                    if (
                        current_arm["status"] != "CURRENT"
                        or (current_arm.get("report") or {}).get("status")
                        != "METADATA_CORRELATED"
                    ):
                        raise WizardError(
                            "PASSIVE_SETUP_METADATA_HELD",
                            "Current correlated arm metadata is required.",
                        )
                    setup_generic = deepcopy(
                        self._device_selection.reviewed_candidate("SERIAL")
                    )
                    setup_native = deepcopy(self._native_arm_report)
                    if (
                        values["_arm_review_sha256"] != self._arm_review_sha256()
                        or values["_setup_native_report_sha256"]
                        != setup_native["report_sha256"]
                    ):
                        raise WizardError(
                            "PASSIVE_SETUP_METADATA_CHANGED",
                            "Setup metadata changed before publication.",
                        )
                if cancel.is_set():
                    raise WizardError(
                        "CANCELLED", "Setup recording cancelled before publication."
                    )
                result = record_setup(
                    workspace=self.workspace,
                    root=self._log.root,
                    session_id=self.session_id,
                    operation_id=operation_id,
                    source_sha256=self.source_sha256,
                    generic_review=setup_generic,
                    native_report=setup_native,
                    operator_id=values["operator_id"],
                    power_disconnected=values["power_disconnected"],
                    secured_and_clear=values["secured_and_clear"],
                    now_monotonic_ns=time.monotonic_ns(),
                )
                native_retained_result = deepcopy(result)
                with self._lock:
                    self._recheck_source(action_id)
            elif action_id == "record_powered_arm_startup":
                from .wizard_powered_arm_setup import record_startup

                # Invalidate before file publication, including a failed write.
                # A reported power transition cannot leave USB-only approval live.
                with self._lock:
                    self._passive_arm_setup = None
                    self._recheck_source(action_id)
                if cancel.is_set():
                    raise WizardError("CANCELLED", "Powered setup recording cancelled.")
                result = record_startup(
                    root=self._log.root,
                    session_id=self.session_id,
                    operation_id=operation_id,
                    source_sha256=self.source_sha256,
                    now_monotonic_ns=time.monotonic_ns(),
                    **values,
                )
                native_retained_result = deepcopy(result)
                with self._lock:
                    self._powered_arm_startup = deepcopy(result)
                    self._recheck_source(action_id)
            elif action_id == 'review_first_motion_qualification':
                from .first_motion_qualification import assess_first_motion_evidence
                from .first_motion_qualification_decision import record_qualification_decision
                from .first_motion_contract import canonical
                from .physical_onboarding_durability import contained_path, read_bounded_regular_file
                with self._lock:
                    if len(self._first_motion_qualification_receipts) >= 16:
                        raise WizardError('QUALIFICATION_REVIEW_LIMIT','Bounded review record limit reached.')
                    selected_id = values['assessment_operation_id']
                    selected_op = self._operations.get(selected_id, {})
                    steps = (selected_op.get('result') or {}).get('steps', [])
                    saved = steps[0].get('report', {}) if len(steps) == 1 else {}
                    if selected_op.get('action_id') != 'assess_first_motion_qualification' or selected_op.get('status') != 'SUCCEEDED':
                        raise WizardError('QUALIFICATION_REVIEW_HELD','Select a successful assessment in this session.')
                    raw = read_bounded_regular_file(contained_path(self._log.root,
                        selected_id+'-first-motion-assessment.json', label='selected assessment'), maximum_bytes=128*1024)
                    if hashlib.sha256(raw).hexdigest() != saved.get('assessment_sha256'):
                        raise WizardError('QUALIFICATION_REVIEW_HELD','Retained assessment changed.')
                    selected = [item for item in self._first_motion_observation_receipts
                        if item[1]['operation_id'] == saved.get('observation_operation_id')]
                    if len(selected) != 1:
                        raise WizardError('QUALIFICATION_REVIEW_HELD','Original observation receipt unavailable.')
                    request, receipt = selected[0]
                    def revalidate():
                        if (cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns
                                or self._closed or self._log_error or self._running != operation_id):
                            raise WizardError('QUALIFICATION_REVIEW_INTERRUPTED','Review no longer owns a current operation.')
                        self._recheck_source(action_id)
                        outcome = self._first_motion_outcome
                        if (outcome is None or type(outcome.report) is not dict
                                or request.to_dict()['attempt_id'] != self._first_motion_attempt_id
                                or hashlib.sha256(canonical(outcome.report)).hexdigest() != receipt['result_sha256']):
                            raise WizardError('QUALIFICATION_REVIEW_HELD','Owned outcome changed.')
                        return canonical(assess_first_motion_evidence(request, result_root=self.export_directory,
                            observation_root=self._log.root, observation_receipt=receipt, owned_result=outcome.owned))
                    report = record_qualification_decision(raw,
                        {key:value for key,value in values.items() if key != 'assessment_operation_id'},
                        root=self._log.root, operation_id=operation_id, recorded_ns=time.monotonic_ns(), revalidate=revalidate)
                    report['assessment_operation_id'] = selected_id
                    self._first_motion_qualification_receipts.append((operation_id, deepcopy(report)))
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'first_motion_qualification_review','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'assess_first_motion_qualification':
                from .first_motion_qualification import assess_first_motion_evidence
                from .first_motion_contract import canonical
                from .physical_onboarding_durability import publish_reservation_bytes
                with self._lock:
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Assessment interrupted.')
                    selected = [item for item in self._first_motion_observation_receipts
                        if item[1]['operation_id'] == values['observation_operation_id']]
                    if (len(selected) != 1 or self._operations.get(values['observation_operation_id'], {}).get('status') != 'SUCCEEDED'):
                        raise WizardError('FIRST_MOTION_ASSESSMENT_HELD','Select this session\'s successful observation receipt.')
                    request, receipt = selected[0]
                    outcome = self._first_motion_outcome
                    if (outcome is None or type(outcome.report) is not dict
                            or request.to_dict()['attempt_id'] != self._first_motion_attempt_id
                            or hashlib.sha256(canonical(outcome.report)).hexdigest() != receipt['result_sha256']):
                        raise WizardError('FIRST_MOTION_ASSESSMENT_HELD','Observation does not match the current retained outcome.')
                    assessment = assess_first_motion_evidence(request, result_root=self.export_directory,
                        observation_root=self._log.root, observation_receipt=receipt, owned_result=outcome.owned)
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Assessment interrupted.')
                    raw = canonical(assessment)
                    publish_reservation_bytes(self._log.root, operation_id+'-first-motion-assessment.json', raw, maximum_bytes=128*1024)
                    report = dict(assessment=assessment, assessment_sha256=hashlib.sha256(raw).hexdigest(),
                                  observation_operation_id=values['observation_operation_id'])
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'first_motion_assessment','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'use_current_arm_for_observational_test':
                from .first_motion_contract import canonical
                from .observational_onboarding_sources import sources_from_onboarding, reviewed_vendor_protocol_original
                from .physical_onboarding_durability import publish_reservation_bytes
                with self._lock:
                    if self._native_arm_view().get('status') != 'CURRENT':
                        raise WizardError('OBSERVATIONAL_IDENTITY_CHANGED','Native arm metadata is no longer current.')
                    native = canonical(self._native_arm_report)
                    generic = deepcopy(self._device_selection.reviewed_candidate('SERIAL'))
                    if values['confirm_model'] is not True or values['firmware_unchanged'] is not True:
                        raise WizardError('OBSERVATIONAL_HISTORY_REQUIRED','Explicit model and unchanged-history report required.')
                    unit = canonical(dict(schema='rocell.observational_received_unit.v1',
                        session_id=self.session_id, source_sha256=self.source_sha256,
                        native_report_sha256=hashlib.sha256(native).hexdigest(), operator_id=values['operator_id'],
                        model='RoArm-M3-Pro', firmware_unchanged_since_delivery=True,
                        basis='OPERATOR_REPORTED', installed_binary_verified=False))
                    binding, originals, summary = sources_from_onboarding(native_original=native,
                        generic_review=generic, received_unit_original=unit,
                        protocol_original=reviewed_vendor_protocol_original(),
                        session_id=self.session_id, source_sha256=self.source_sha256)
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Onboarding source association interrupted.')
                    for name, raw in originals.items():
                        publish_reservation_bytes(self._log.root, operation_id+'-observational-onboarding-'+name+'.json',
                            raw, maximum_bytes=256*1024)
                    receipt = self._retain_reviewed_observational_sources(controller_binding=binding,
                        protocol_original=originals['protocol'], label='RoArm-M3 Pro / '+binding.identity.port_name,
                        owner=operation_id, onboarding=dict(operation_id=operation_id,
                            original_sha256=summary['original_sha256']))
                result = dict(schema='rocell.wizard_worker_result.v1', action_id=action_id,
                    status='SUCCEEDED', physical_authority=False,
                    steps=[dict(name='observational onboarding sources', exit_code=0, report=dict(receipt=receipt, summary=summary))],
                    device_open_count=0, serial_write_count=0, power_event_count=0,
                    motion_command_count=0, contact_command_count=0, metadata_inventory_performed=False)
                native_retained_result = deepcopy(result)
            elif action_id == 'setup_observational_movement':
                from .physical_onboarding_durability import contained_path, read_bounded_regular_file
                from rocell.providers.windows.endpoint_child_execution import decode_reviewed_controller_binding
                with self._lock:
                    receipt = self._observational_sources.get(values['source_id'])
                    if (receipt is None or receipt['session_id'] != self.session_id
                            or receipt['source_sha256'] != self.source_sha256):
                        raise WizardError('OBSERVATIONAL_SOURCE_CHANGED','Selected reviewed sources are no longer current.')
                    originals = {}
                    for kind, digest in receipt['original_sha256'].items():
                        raw = read_bounded_regular_file(contained_path(self._log.root,
                            receipt['source_id']+'-'+kind+'.json', label='reviewed observational source'), maximum_bytes=128*1024)
                        if hashlib.sha256(raw).hexdigest() != digest:
                            raise WizardError('OBSERVATIONAL_SOURCE_CHANGED','Retained source bytes changed.')
                        originals[kind] = raw
                    binding = decode_reviewed_controller_binding(originals['controller'],
                        expected_sha256=receipt['original_sha256']['controller'])
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Observational setup interrupted.')
                    absolute_draft = None
                    if values.get('absolute_draft', 'relative') != 'relative':
                        from .absolute_wrist_telemetry_source import choices_from_retained_telemetry
                        from .first_motion_contract import canonical
                        from rocell.motion.absolute_wrist_diagnostic import AbsoluteWristDiagnosticDraft
                        current_choices = choices_from_retained_telemetry(self._log.root,
                            self._powered_feedback_outcome, session_id=self.session_id,
                            source_sha256=self.source_sha256,
                            native_identity_sha256=hashlib.sha256(canonical(self._native_arm_report)).hexdigest())
                        onboarding = receipt.get('onboarding') or {}
                        if (onboarding.get('original_sha256') or {}).get('native_identity') != current_choices['native_identity_sha256']:
                            raise WizardError('ABSOLUTE_UNIT_CHANGED', 'Select controller records associated with this telemetry device.')
                        if current_choices != self._absolute_wrist_capture_choices:
                            raise WizardError('ABSOLUTE_CAPTURE_CHANGED', 'Retained telemetry changed after selection.')
                        selected = [item for item in current_choices['choices'] if item['draft_sha256'] == values['absolute_draft']]
                        if len(selected) != 1:
                            raise WizardError('ABSOLUTE_DRAFT_CHANGED', 'Selected absolute draft is unavailable.')
                        absolute_draft = AbsoluteWristDiagnosticDraft(canonical(selected[0]['draft']))
                        if not self._append_event('absolute_capture_draft_selected', dict(
                                source_attempt_id=current_choices.get('source_attempt_id'),
                                outcome_sha256=current_choices.get('outcome_sha256'),
                                capture_sha256=current_choices.get('capture_sha256'),
                                draft_sha256=absolute_draft.sha256, historical_only=True,
                                motion_authorized=False)):
                            raise WizardError('DIAGNOSTIC_LOG_FAILED', 'Draft source could not be retained.')
                    report = self._configure_observational_movement(controller_binding=binding,
                        protocol_original=originals['protocol'], direction=(absolute_draft.to_dict()['direction']
                            if absolute_draft is not None else int(values['direction'])),
                        degrees=int(values.get('degrees', '1')), owner=operation_id, absolute_draft=absolute_draft)
                result = dict(schema='rocell.wizard_worker_result.v1', action_id=action_id,
                    status='SUCCEEDED', physical_authority=False,
                    steps=[dict(name='observational setup', exit_code=0, report=report)],
                    device_open_count=0, serial_write_count=0, power_event_count=0,
                    motion_command_count=0, contact_command_count=0, metadata_inventory_performed=False)
                native_retained_result = deepcopy(result)
            elif action_id == 'run_observational_movement':
                from .wizard_observational_coordinator import confirm_observational_run, run_reviewed_observational
                from rocell.safety.observational_review_authority import CHECKS
                with self._lock:
                    confirmation = self._observational_confirmation
                    if confirmation is None or confirmation[0] != operation_id:
                        raise WizardError('OBSERVATIONAL_CONFIRMATION_MISSING','No accepted confirmation for this attempt.')
                    config = confirmation[1]
                def current_observational():
                    with self._lock:
                        if (self._closed or self._log_error or self._source_changed
                                or self._running != operation_id
                                or self._observational_confirmation is not confirmation
                                or self._powered_setup_context() != config['context']):
                            raise WizardError('OBSERVATIONAL_CONTEXT_CHANGED','Current observational setup changed.')
                current_observational()
                absolute = config.get('absolute_draft')
                if absolute is not None:
                    from .wizard_absolute_wrist_coordinator import confirm_absolute_wrist_run, run_reviewed_absolute_wrist
                    confirm_observational_run = confirm_absolute_wrist_run
                    run_reviewed_observational = run_reviewed_absolute_wrist
                selection = (dict(draft=absolute) if absolute is not None else
                    dict(direction=config['direction'], policy=config['policy']))
                request, signed = confirm_observational_run(self.workspace, config['staged'],
                    session_id=self.session_id, usb_identity=config['usb_identity'], **selection,
                    operator_id=values['operator_id'], checks={name:values[name] for name in CHECKS},
                    accepted_ns=confirmation[2], now_ns=time.monotonic_ns())
                with self._lock:
                    self._observational_request = request
                outcome = run_reviewed_observational(self.workspace, config['staged'], request,
                    review_original=signed, export_root=self.export_directory, cancellation=cancel,
                    check_current=current_observational)
                with self._lock:
                    self._observational_outcome = outcome
                result = dict(action_id=action_id, physical_authority=False,
                    status='SUCCEEDED' if outcome.stage == 'RETAINED' and
                        (outcome.report or {}).get('status') == 'RESULT_RETAINED' else 'FAILED',
                    message='Attempt ended at '+outcome.stage+'; review telemetry and record what you observed.',
                    steps=[dict(name='observational trial', report=outcome.report or {}, stage=outcome.stage)],
                    error_type=outcome.error_type, replay_allowed=False)
                if absolute is not None:
                    report = outcome.report or {}
                    result['status'] = ('SUCCEEDED' if outcome.stage == 'RETAINED'
                        and report.get('endpoint_reported_settled') is True else 'FAILED')
                    result['message'] = ('Absolute endpoint: '+str(report.get('endpoint_status') or 'UNVERIFIED')+
                        '; retention: '+outcome.stage+'. No automatic next movement.')
                    result['motion_mode'] = 'ABSOLUTE_WRIST'
                with self._lock:
                    self._observational_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'record_observational_movement':
                from .first_motion_contract import canonical
                from .observational_operator_report import record_operator_report, FIELDS
                from .physical_onboarding_durability import contained_path, read_bounded_regular_file
                with self._lock:
                    request, outcome = self._observational_request, self._observational_outcome
                    if request is None or outcome is None or type(outcome.report) is not dict:
                        raise WizardError('OBSERVATIONAL_RESULT_MISSING','No retained observational trial.')
                    if len(self._observational_operator_receipts) >= 16:
                        raise WizardError('OBSERVATION_LIMIT','Export and review the sixteen retained observations.')
                    if request.to_dict()['session_id'] != self.session_id:
                        raise WizardError('OBSERVATIONAL_SESSION_CHANGED','Trial belongs to another session.')
                    attempt = request.to_dict()['attempt_id']
                    expected = canonical(outcome.report)
                    if values['trial'] != attempt+'@'+hashlib.sha256(expected).hexdigest():
                        raise WizardError('OBSERVATIONAL_RESULT_CHANGED','Selected trial result changed.')
                    raw = read_bounded_regular_file(contained_path(self.export_directory,
                        attempt+'-observational-report.json', label='observational result'), maximum_bytes=256*1024)
                    if raw != expected:
                        raise WizardError('OBSERVATIONAL_RESULT_CHANGED','Retained trial bytes changed.')
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Observation recording interrupted.')
                    report = record_operator_report(request, raw, {name:values[name] for name in FIELDS},
                        root=self._log.root, operation_id=operation_id, recorded_ns=time.monotonic_ns())
                    self._observational_operator_receipts.append(deepcopy(report))
                    from .observational_functional_assessment import assess_retained_observational_trial
                    from .physical_onboarding_durability import publish_reservation_bytes
                    assessment = assess_retained_observational_trial(request, outcome, report,
                        review_root=self._log.root, export_root=self.export_directory)
                    assessment_raw = canonical(assessment)
                    publish_reservation_bytes(self._log.root, operation_id+'-observational-assessment.json',
                        assessment_raw, maximum_bytes=128*1024)
                    report = dict(report, functional_assessment_pending=False, assessment=assessment,
                        assessment_sha256=hashlib.sha256(assessment_raw).hexdigest())
                    self._observational_operator_receipts[-1] = deepcopy(report)
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'observational_operator_report','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'record_first_motion_observation':
                from .first_motion_contract import FirstMotionRequest, canonical
                from .first_motion_observation import record_observation, FIELDS, MAX_OBSERVATIONS
                from .physical_onboarding_durability import contained_path, read_bounded_regular_file
                from .wizard_diagnostic_coordinator import decode_diagnostic_json
                with self._lock:
                    if len(self._first_motion_observation_receipts) >= MAX_OBSERVATIONS:
                        raise WizardError('OBSERVATION_LIMIT','The bounded observation record limit has been reached.')
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Observation recording interrupted.')
                    outcome = self._first_motion_outcome
                    attempt = self._first_motion_attempt_id
                    if outcome is None or type(outcome.report) is not dict or attempt is None:
                        raise WizardError('FIRST_MOTION_OBSERVATION_HELD','No retained trial result.')
                    expected = canonical(outcome.report)
                    if values['trial'] != attempt+'@'+hashlib.sha256(expected).hexdigest():
                        raise WizardError('FIRST_MOTION_OBSERVATION_HELD','Selected result changed.')
                    result_raw = read_bounded_regular_file(contained_path(self.export_directory,
                        attempt+'-first_motion-report.json', label='retained trial result'), maximum_bytes=256*1024)
                    if result_raw != expected:
                        raise WizardError('FIRST_MOTION_OBSERVATION_HELD','Retained result differs from the owned outcome.')
                    click_raw = read_bounded_regular_file(contained_path(self._log.root,
                        attempt+'-first-motion-final-click.json', label='final request'), maximum_bytes=32768)
                    click = decode_diagnostic_json(click_raw, maximum=32768)
                    request = FirstMotionRequest(canonical(click['request']))
                    if request.to_dict()['attempt_id'] != attempt:
                        raise WizardError('FIRST_MOTION_OBSERVATION_HELD','Final request belongs to another attempt.')
                    if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                        raise WizardError('CANCELLED','Observation recording interrupted.')
                    report = record_observation(request, result_raw, {name:values[name] for name in FIELDS},
                        root=self._log.root, operation_id=operation_id, recorded_ns=time.monotonic_ns())
                    self._first_motion_observation_receipts.append((request, deepcopy(report)))
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'first_motion_observation','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'attach_retained_first_motion':
                from rocell.safety.first_motion_review_authority import ENGINEERING_CHECKS
                def check_attachment():
                    if (cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns
                            or self._running != operation_id or self._closed or self._log_error
                            or self._operations.get(operation_id, {}).get('action_id') != action_id):
                        raise WizardError('FIRST_MOTION_ATTACHMENT_INTERRUPTED', 'Attachment operation no longer owns a current context.')
                with self._lock:
                    check_attachment()
                    report = self._configure_first_motion_from_retained(
                        draft_operation_id=values['draft_operation_id'],
                        review_operation_ids=tuple(values[name] for name in sorted(ENGINEERING_CHECKS)),
                        owner=operation_id, check=check_attachment)
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'first_motion_attachment','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'create_first_motion_draft':
                if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                    raise WizardError('CANCELLED', 'Draft creation interrupted.')
                draft = self._create_first_motion_draft_from_retained(**values, owner_operation=operation_id)
                from .physical_onboarding_durability import publish_reservation_bytes
                # A separate immutable original lets later review re-read and
                # verify the successful operation's exact bytes, not a UI copy.
                publish_reservation_bytes(self._log.root, operation_id+'-first-motion-generated-draft.json',
                                          draft.canonical_bytes, maximum_bytes=16384)
                if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                    raise WizardError('CANCELLED', 'Draft creation interrupted; any retained draft is not an approval.')
                report = dict(status='DRAFT_CREATED_NOT_AUTHORIZED', draft_json=draft.canonical_bytes.decode('ascii'),
                              draft_sha256=hashlib.sha256(draft.canonical_bytes).hexdigest(),
                              preview=draft.preview(), **values)
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'first_motion_draft','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'record_first_motion_measurements':
                from .first_motion_measurements import record_measurements
                if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                    raise WizardError('CANCELLED','Measurement recording interrupted.')
                with self._lock:
                    self._recheck_source(action_id)
                    report = record_measurements(values,root=self._log.root,
                        session_id=self.session_id,operation_id=operation_id,
                        source_sha256=self.source_sha256,now_ns=time.monotonic_ns())
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'first_motion_measurement_original','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id in ('record_endpoint_engineering_review', 'record_first_motion_engineering_review', 'review_retained_first_motion_draft'):
                selected_draft_operation = None
                if action_id == 'review_retained_first_motion_draft':
                    from .physical_onboarding_durability import contained_path, read_bounded_regular_file
                    from .first_motion_draft import FirstMotionDraft
                    selected_draft_operation = values['draft_operation_id']
                    with self._lock:
                        selected_op = self._operations.get(selected_draft_operation, {})
                        steps = (selected_op.get('result') or {}).get('steps', [])
                        selected_report = steps[0].get('report', {}) if len(steps) == 1 else {}
                        if selected_op.get('action_id') != 'create_first_motion_draft' or selected_op.get('status') != 'SUCCEEDED':
                            raise WizardError('FIRST_MOTION_DRAFT_INVALID', 'Select a successful draft in this session.')
                        raw = read_bounded_regular_file(contained_path(self._log.root,
                            selected_draft_operation+'-first-motion-generated-draft.json', label='selected generated draft'), maximum_bytes=16384)
                        if hashlib.sha256(raw).hexdigest() != selected_report.get('draft_sha256'):
                            raise WizardError('FIRST_MOTION_DRAFT_INVALID', 'Retained draft differs from its successful receipt.')
                        draft = FirstMotionDraft(raw)
                        values = dict(values)
                        del values['draft_operation_id']
                        values['draft_json'] = draft.canonical_bytes.decode('ascii')
                if action_id in ('record_first_motion_engineering_review', 'review_retained_first_motion_draft'):
                    from .first_motion_review_intake import record_decision
                else:
                    from .wizard_engineering_review_intake import record_decision
                if cancel.is_set() or time.monotonic_ns() >= operation_deadline_ns:
                    raise WizardError('CANCELLED','Engineering decision recording interrupted.')
                with self._lock:
                    self._recheck_source(action_id)
                    report = record_decision(values,root=self._log.root,operation_id=operation_id,
                        source_sha256=self.source_sha256,now_ns=time.monotonic_ns())
                    if selected_draft_operation is not None:
                        report['draft_operation_id'] = selected_draft_operation
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'engineering_decision','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id in ('run_wifi_roll_sweep_low_trial','run_wifi_roll_sweep_center_trial','run_wifi_roll_sweep_high_trial','run_wifi_roll_trial','run_wifi_roll_negative_trial','run_wifi_roll_low_trial','run_wifi_roll_high_trial','run_wifi_roll_zero_trial','run_wifi_roll_center_up_trial','run_wifi_roll_center_down_trial','run_wifi_roll_corrected_up_trial','run_wifi_roll_corrected_down_trial','run_wifi_roll_probe_low_trial','run_wifi_roll_probe_high_trial','run_wifi_roll_lookup_trial','run_wifi_roll_adjacent_trial','run_wifi_roll_adjacent_low_trial','run_wifi_roll_adjacent_high_trial','run_wifi_roll_adjacent_lookup_trial'):
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_adjacent_lookup_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_sweep_low_trial, run_native_roll_sweep_center_trial, run_native_roll_sweep_high_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_adjacent_low_trial, run_native_roll_adjacent_high_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_adjacent_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_lookup_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_probe_low_trial, run_native_roll_probe_high_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_corrected_up_trial, run_native_roll_corrected_down_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_trial, run_native_roll_negative_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_low_trial, run_native_roll_high_trial
                from rocell.providers.windows.wifi_discrete_native import run_native_roll_zero_trial, run_native_roll_center_up_trial, run_native_roll_center_down_trial
                self._recheck_source(action_id)
                self.export_directory.mkdir(parents=True,exist_ok=True)
                run_trial={'run_wifi_roll_trial':run_native_roll_trial,'run_wifi_roll_negative_trial':run_native_roll_negative_trial,
                    'run_wifi_roll_low_trial':run_native_roll_low_trial,'run_wifi_roll_high_trial':run_native_roll_high_trial,
                    'run_wifi_roll_zero_trial':run_native_roll_zero_trial,'run_wifi_roll_center_up_trial':run_native_roll_center_up_trial,
                    'run_wifi_roll_center_down_trial':run_native_roll_center_down_trial,
                    'run_wifi_roll_corrected_up_trial':run_native_roll_corrected_up_trial,
                    'run_wifi_roll_corrected_down_trial':run_native_roll_corrected_down_trial,
                    'run_wifi_roll_probe_low_trial':run_native_roll_probe_low_trial,
                    'run_wifi_roll_probe_high_trial':run_native_roll_probe_high_trial,
                    'run_wifi_roll_lookup_trial':run_native_roll_lookup_trial,
                    'run_wifi_roll_adjacent_trial':run_native_roll_adjacent_trial,
                    'run_wifi_roll_adjacent_low_trial':run_native_roll_adjacent_low_trial,
                    'run_wifi_roll_sweep_low_trial':run_native_roll_sweep_low_trial,
                    'run_wifi_roll_sweep_center_trial':run_native_roll_sweep_center_trial,
                    'run_wifi_roll_sweep_high_trial':run_native_roll_sweep_high_trial,
                    'run_wifi_roll_adjacent_high_trial':run_native_roll_adjacent_high_trial,
                    'run_wifi_roll_adjacent_lookup_trial':run_native_roll_adjacent_lookup_trial}[action_id]
                report=run_trial(root=self.export_directory,cancelled=cancel.is_set)
                result=dict(action_id=action_id,status=report['status'],physical_authority=False,
                    steps=[dict(name='bounded_native_wifi_roll',report=report)],
                    message='Single roll trial; inspect retained endpoint result. No automatic next command.')
                from rocell.application.move_result import summarize_move
                result['move_result'] = summarize_move(
                    report, request_id=operation_id, action_id=action_id)
                self._wifi_roll_publication=deepcopy(result)
                native_retained_result=deepcopy(result)
            elif action_id == 'run_micro_commissioning':
                from rocell.providers.windows.micro_commissioning_native import run_native_micro_commissioning
                self._recheck_source(action_id)
                if values.get('exclusive_controller_declared') is not True:
                    raise WizardError('MICRO_CONTROLLER_DECLARATION_REQUIRED','Exclusive-controller declaration required.')
                def check_micro_current():
                    with self._lock:
                        self._recheck_source(action_id)
                report=run_native_micro_commissioning(root=self.export_directory,export_root=self.export_directory,
                    exclusive_controller_declared=True,
                    cancelled=lambda:cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns,
                    check_current=check_micro_current)
                result=dict(action_id=action_id,
                    status='SUCCEEDED' if report['status'] in ('NO_CORRECTION_NEEDED','EXPERIMENT_VERIFIED') else 'FAILED',
                    physical_authority=False,steps=[dict(name='single_micro_commissioning',report=report)],
                    message='Bounded live experiment. Inspect classification and exports; completion is not proof of improved physical accuracy.')
                self._micro_commissioning_publication=deepcopy(result)
                native_retained_result=deepcopy(result)
            elif action_id == 'rehearse_static_task':
                from .static_simulation_context import load_static_simulation_context
                from .static_task_rehearsal import run_static_task_rehearsal
                self._recheck_source(action_id)
                if cancel.is_set():
                    raise WizardError('CANCELLED', 'Static rehearsal cancelled before calculation.')
                report = run_static_task_rehearsal(load_static_simulation_context(self.workspace),
                    device=values['device'], text=values['text'], dense=True,
                    park_xy_board_mm=(290.,40.) if values['park']=='overlay_290_40' else None)
                self._recheck_source(action_id)
                result = dict(action_id=action_id,
                    status='SUCCEEDED' if report['status']=='DENSE_SAMPLES_PASS_NOT_EXECUTABLE' else 'FAILED',
                    physical_authority=False, steps=[dict(name='static_task_rehearsal', report=report)],
                    message='Simulation only. Inspect route checks; no installed calibration or physical clearance established.')
                self._static_task_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'simulate_micro_correction':
                from .micro_diagnostic_suite import run_suite
                self._recheck_source(action_id)
                report=run_suite()
                result=dict(action_id=action_id,status=report['status'],physical_authority=False,
                    steps=[dict(name='synthetic_micro_policy_suite',report=report)],
                    message='Simulation only: no hardware access or live motion authority.')
                self._micro_simulation_publication=deepcopy(result)
                native_retained_result=deepcopy(result)
            elif action_id == 'simulate_discrete_transaction':
                from rocell.arm.discrete_transaction import simulate_transactions
                report = simulate_transactions()
                result = dict(action_id=action_id,status=report['status'],physical_authority=False,
                    steps=[dict(name='in_memory_transaction_suite',report=report)],
                    message='Simulation only: no network, USB, or physical movement.')
                self._discrete_simulation_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'run_held_pair':
                from .wizard_held_pair import run_wizard_held_pair
                self._recheck_source(action_id)
                if self._held_pair_attempted or values.get('acknowledge') is not True:
                    raise WizardError('PAIR_CONSUMED','Pair unavailable or acknowledgement missing.')
                self._held_pair_attempted = True
                try:
                    outcome = run_wizard_held_pair(self._held_pair_binding,self.export_directory,
                        cancelled=cancel.is_set,deadline_ns=operation_deadline_ns)
                except Exception:
                    raise WizardError('PAIR_STOPPED','Pair admission or execution failed; attempt consumed. Inspect retained exports; no retry.') from None
                report = outcome['report']
                result = dict(action_id=action_id,
                    status='SUCCEEDED' if report['phase']=='CONTROLLER_REPORTED_PAIR_ARRIVAL' else 'FAILED',
                    physical_authority=False,steps=[dict(name='held_pair_trial',report=report)],
                    export_path=outcome['export_path'],admission_export_id=outcome['admission_export_id'],
                    message='Controller-count trial result; not measured stylus-tip accuracy. No retry.')
                self._held_pair_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'review_observed_pair':
                from .held_pair_observed_return import replay_observed_pair_return
                self._recheck_source(action_id)
                replay = replay_observed_pair_return(self.export_directory, values['export_id'])
                report = dict(schema='rocell.wizard_pair_review.v1', export_id=values['export_id'],
                    origin='HOST_HTTP_OBSERVATION', replay_verified=replay['replay_verified'],
                    export_sha256=replay['export_sha256'], review=replay['review'],
                    hardware_access=False, progression_authority=False, retry_allowed=False)
                result = dict(action_id=action_id, status='SUCCEEDED', physical_authority=False,
                    steps=[dict(name='offline_pair_review', report=report)],
                    message='Saved paired evidence replayed. No hardware access or physical-tip qualification.')
                self._pair_review_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id in ('review_collected_hold', 'review_observed_hold'):
                from .hold_collected_review import replay_collected_hold_simulation
                from .hold_observed_review import replay_hold_observation
                self._recheck_source(action_id)
                observed = action_id == 'review_observed_hold'
                reviewer = replay_hold_observation if observed else replay_collected_hold_simulation
                replay = reviewer(self.export_directory, values['export_id'])
                report = dict(schema='rocell.wizard_hold_review.v1', export_id=values['export_id'],
                    origin='HOST_HTTP_OBSERVATION' if observed else 'SIMULATION',
                    replay_verified=replay['matches'], hardware_access=False,
                    progression_authority=False, retry_allowed=False, assessment=replay['assessment'],
                    endpoint_review=replay['assessment'] if observed else replay['endpoint_review'],
                    delivery=replay['delivery'])
                if observed:
                    report.update(controller_status=replay['controller_status'],
                                  stable_status_observed=replay['stable_status_observed'])
                result = dict(action_id=action_id, status='SUCCEEDED', physical_authority=False,
                    steps=[dict(name='offline_hold_review', report=report)],
                    message='Saved evidence replayed. No hardware connection or movement qualification.')
                self._hold_review_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id in ('review_planned_servo_run','review_started_servo_run','review_startup_servo_run','review_started_startup_run'):
                from .servo_planned_run import replay_planned_run
                from .servo_started_run import replay_started_run
                from .startup_planned_run import replay_startup_run
                from .startup_started_run import replay_started_startup
                self._recheck_source(action_id)
                started=action_id in ('review_started_servo_run','review_started_startup_run')
                startup=action_id in ('review_startup_servo_run','review_started_startup_run')
                replay=(replay_started_startup if startup and started else replay_startup_run if startup else replay_started_run if started else replay_planned_run)(self.export_directory,values['export_id'])
                report=dict(schema='rocell.started_startup_review.v1' if startup and started else 'rocell.startup_run_review.v1' if startup else 'rocell.started_run_review.v1' if started else 'rocell.planned_run_review.v1',export_id=values['export_id'],
                    replay_verified=replay['matches'],outcome=replay['outcome'],hardware_access=False,
                    progression_authority=False)
                if started:report.update(delivery=replay['delivery'],prepared_export_id=replay['prepared_export_id'],retry_allowed=False)
                result=dict(action_id=action_id,status='SUCCEEDED',physical_authority=False,
                    steps=[dict(name='offline_planned_run_review',report=report)],
                    message='Saved evidence replayed; review completion does not qualify hardware movement.')
                self._planned_servo_review_publication=deepcopy(result)
                native_retained_result=deepcopy(result)
            elif action_id == 'simulate_servo_diagnostics':
                from .servo_diagnostic_rehearsal import run_rehearsal
                self._recheck_source(action_id)
                report=run_rehearsal(self.export_directory,values['scenario'])
                result=dict(action_id=action_id,status='SUCCEEDED',physical_authority=False,
                    steps=[dict(name='synthetic_servo_diagnostics',report=report)],
                    message='Simulation completed and export replay verified; this does not qualify hardware. Inspect the diagnostic outcome separately.')
                self._servo_diagnostic_publication=deepcopy(result)
                native_retained_result=deepcopy(result)
            elif action_id in ('read_arm_wifi_feedback','sample_arm_wifi_feedback','observe_arm_wifi_feedback','observe_arm_wifi_feedback_fast','observe_arm_wifi_feedback_spaced','observe_arm_wifi_feedback_intermediate','observe_arm_wifi_bounded'):
                from rocell.providers.windows.arm_wifi_feedback import probe, sample_feedback
                from rocell.providers.windows.arm_wifi_observation import observe, observe_fast, observe_spaced, observe_intermediate
                from rocell.providers.windows.arm_wifi_deadline import observe_bounded
                from rocell.providers.windows.arm_transport_lock import arm_transport_lock
                self._recheck_source(action_id)
                with arm_transport_lock():
                    report = (observe_bounded if action_id=='observe_arm_wifi_bounded' else observe_intermediate if action_id=='observe_arm_wifi_feedback_intermediate' else observe_spaced if action_id=='observe_arm_wifi_feedback_spaced' else observe_fast if action_id=='observe_arm_wifi_feedback_fast' else observe if action_id=='observe_arm_wifi_feedback' else sample_feedback if action_id=='sample_arm_wifi_feedback' else probe)(cancelled=cancel.is_set)
                result = dict(action_id=action_id,status=report['status'],physical_authority=False,
                    steps=[dict(name='read_only_wifi_feedback',report=report)],
                    message='Wi-Fi feedback diagnostic only; no movement readiness granted.')
                self._wifi_feedback_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'review_endpoint_campaign':
                from .endpoint_campaign_import import parse_campaign_review_input, summarize_saved_endpoint_campaign
                plan,attempts = parse_campaign_review_input(values)
                def check_review_current():
                    if cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns:
                        raise WizardError('ENDPOINT_REVIEW_INTERRUPTED','Saved endpoint review cancelled or timed out.')
                    with self._lock:
                        self._recheck_source(action_id)
                report = summarize_saved_endpoint_campaign(self.export_directory,plan,attempts,
                    check_current=check_review_current)
                result = {'schema':'rocell.wizard_worker_result.v1','action_id':action_id,
                    'status':'SUCCEEDED','physical_authority':False,
                    'steps':[{'name':'saved_endpoint_campaign','exit_code':0,'report':report}],
                    'device_open_count':0,'serial_write_count':0,'power_event_count':0,
                    'motion_command_count':0,'contact_command_count':0,'metadata_inventory_performed':False}
                native_retained_result = deepcopy(result)
            elif action_id == 'assess_saved_wrist_correction':
                from .wrist_correction_saved_sources import assess_saved_correction_sources
                from .first_motion_contract import canonical
                from .physical_onboarding_durability import publish_reservation_bytes
                attempts=[line.strip() for line in values['attempt_ids'].splitlines() if line.strip()]
                if cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns:
                    raise WizardError('CANCELLED','Saved correction assessment interrupted.')
                self._recheck_source(action_id)
                report=assess_saved_correction_sources(self.export_directory,attempts)
                if cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns:
                    raise WizardError('CANCELLED','Saved correction assessment interrupted.')
                publish_reservation_bytes(self._log.root,operation_id+'-saved-wrist-correction-assessment.json',
                    canonical(report),maximum_bytes=128*1024)
                result=dict(schema='rocell.wizard_worker_result.v1',action_id=action_id,status='SUCCEEDED',physical_authority=False,
                    steps=[dict(name='saved wrist correction assessment',exit_code=0,report=report)],
                    device_open_count=0,serial_write_count=0,power_event_count=0,motion_command_count=0,
                    contact_command_count=0,metadata_inventory_performed=False)
                native_retained_result=deepcopy(result)
            elif action_id == 'bind_saved_wrist_correction':
                from .wrist_correction_assessment_binding import bind_saved_correction_assessment
                from .first_motion_contract import canonical
                from .physical_onboarding_durability import contained_path,read_bounded_regular_file,publish_reservation_bytes
                from rocell.providers.windows.endpoint_child_execution import decode_reviewed_controller_binding
                with self._lock:
                    self._recheck_source(action_id)
                    selected=self._operations.get(values['assessment_operation_id'],{})
                    source=self._observational_sources.get(values['source_id'])
                    if (selected.get('action_id')!='assess_saved_wrist_correction' or selected.get('status')!='SUCCEEDED'
                            or source is None or source['session_id']!=self.session_id or source['source_sha256']!=self.source_sha256):
                        raise WizardError('CORRECTION_SELECTION_CHANGED','Selected assessment or controller source changed.')
                    expected=canonical(selected['result']['steps'][0]['report'])
                    assessment=read_bounded_regular_file(contained_path(self._log.root,
                        values['assessment_operation_id']+'-saved-wrist-correction-assessment.json',label='correction assessment'),maximum_bytes=128*1024)
                    controller_raw=read_bounded_regular_file(contained_path(self._log.root,source['source_id']+'-controller.json',
                        label='correction controller'),maximum_bytes=128*1024)
                    controller=decode_reviewed_controller_binding(controller_raw,expected_sha256=source['original_sha256']['controller'])
                    bound=bind_saved_correction_assessment(assessment,expected_sha256=hashlib.sha256(expected).hexdigest(),
                        export_root=self.export_directory,controller=controller)
                    if cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns:
                        raise WizardError('CANCELLED','Correction controller matching interrupted.')
                    report=dict(binding=bound.to_dict(),binding_sha256=hashlib.sha256(bound.canonical_bytes).hexdigest(),
                        assessment_operation_id=values['assessment_operation_id'],source_id=source['source_id'])
                    publish_reservation_bytes(self._log.root,operation_id+'-bound-wrist-correction.json',canonical(report),maximum_bytes=128*1024)
                result=dict(schema='rocell.wizard_worker_result.v1',action_id=action_id,status='SUCCEEDED',physical_authority=False,
                    steps=[dict(name='correction controller matching',exit_code=0,report=report)],device_open_count=0,
                    serial_write_count=0,power_event_count=0,motion_command_count=0,contact_command_count=0,metadata_inventory_performed=False)
                native_retained_result=deepcopy(result)
            elif action_id == 'stage_wrist_correction':
                from .wrist_correction_worker_preparation import stage_correction_runtime
                from .first_motion_contract import canonical
                from .physical_onboarding_durability import publish_reservation_bytes
                from rocell.providers.windows.owned_worker_process import owned_registration_document
                with self._lock:
                    self._recheck_source(action_id)
                    # Invalidate any prior setup before attempting replacement. A failed
                    # restaging must not leave an older experiment looking ready.
                    self._wrist_correction_configuration=None
                    bound,controller_raw,protocol_raw,binding_report=self._load_bound_wrist_correction(values['binding_operation_id'])
                    if cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns:
                        raise WizardError('CANCELLED','Correction staging interrupted.')
                    staged=stage_correction_runtime(self.workspace,root=self._log.root,attempt_id='operation-'+uuid.uuid4().hex,
                        controller_original=controller_raw,protocol_original=protocol_raw)
                    # Re-read after package creation; staging cannot hide a changed
                    # source or trial set behind a previously cached assessment.
                    rechecked=self._load_bound_wrist_correction(values['binding_operation_id'])
                    self._recheck_source(action_id)
                    if (rechecked!=(bound,controller_raw,protocol_raw,binding_report)
                            or cancel.is_set() or time.monotonic_ns()>=operation_deadline_ns):
                        raise WizardError('CORRECTION_STAGING_CHANGED','Correction inputs changed or staging interrupted.')
                    report=dict(schema='rocell.wizard_wrist_correction_runtime.v1',
                        binding_operation_id=values['binding_operation_id'],binding_sha256=binding_report['binding_sha256'],
                        attempt_id=staged.attempt_id,source_sha256=staged.source_sha256,
                        runtime_sha256=hashlib.sha256(canonical(owned_registration_document(staged.registration))).hexdigest(),
                        nominal_target_deg=bound.to_dict()['proposal']['nominal_target_deg'],
                        experimental_motor_target_deg=bound.to_dict()['proposal']['experimental_motor_target_deg'],
                        motion_authorized=False,current_connection_verified=False,fresh_baseline_required=True,
                        final_review_required=True,execution_enabled=False)
                    publish_reservation_bytes(self._log.root,operation_id+'-wrist-correction-runtime-setup.json',canonical(report),maximum_bytes=128*1024)
                    self._wrist_correction_configuration=dict(staged=staged,bound=bound,
                        binding_operation_id=values['binding_operation_id'],report=report,session_id=self.session_id)
                result=dict(schema='rocell.wizard_worker_result.v1',action_id=action_id,status='SUCCEEDED',physical_authority=False,
                    steps=[dict(name='correction runtime preparation',exit_code=0,report=report)],device_open_count=0,
                    serial_write_count=0,power_event_count=0,motion_command_count=0,contact_command_count=0,metadata_inventory_performed=False)
                native_retained_result=deepcopy(result)
            elif action_id == 'run_positional_campaign':
                from .wizard_positional_campaign_coordinator import run_staged_positional_campaign
                from rocell.safety.positional_campaign_authority import BOUNDED_CHECKS
                with self._lock:
                    confirmation = self._positional_campaign_confirmation
                    if confirmation is None or confirmation[0] != operation_id:
                        raise WizardError('CAMPAIGN_CONFIRMATION_MISSING','No accepted campaign Start.')
                    config = confirmation[1]
                def current_campaign():
                    with self._lock:
                        if (self._closed or self._log_error or self._source_changed or cancel.is_set()
                                or self._running != operation_id
                                or self._positional_campaign_confirmation is not confirmation
                                or self._positional_campaign_configuration is not config
                                or self._powered_setup_context() != config['context']):
                            raise WizardError('CAMPAIGN_CONTEXT_CHANGED','Campaign wizard context changed.')
                current_campaign()
                outcome = run_staged_positional_campaign(self.workspace, config['staged'],
                    operator_id=values['operator_id'], checks={name:values[name] for name in BOUNDED_CHECKS},
                    accepted_ns=confirmation[2], cancellation=cancel, export_root=self.export_directory,
                    check_current=current_campaign)
                result = dict(action_id=action_id, physical_authority=False,
                    status='SUCCEEDED' if outcome['status']=='ENDPOINTS_REPORTED_COMPLETE' else 'FAILED',
                    message='Attended campaign: '+outcome['status']+'. No automatic further movement.',
                    steps=[dict(name='two-endpoint campaign', report=outcome)],
                    replay_allowed=False, physical_accuracy_verified=False)
                with self._lock:
                    self._positional_campaign_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'run_wrist_correction':
                from .wizard_wrist_correction_coordinator import confirm_correction_run,run_reviewed_correction
                from rocell.safety.observational_review_authority import CHECKS
                with self._lock:
                    confirmation=self._wrist_correction_confirmation
                    if confirmation is None or confirmation[0]!=operation_id:
                        raise WizardError('CORRECTION_CONFIRMATION_MISSING','No accepted review for this correction attempt.')
                    config=confirmation[1]
                def current_correction():
                    with self._lock:
                        if (self._closed or self._log_error or self._source_changed or cancel.is_set()
                                or self._running!=operation_id or self._wrist_correction_confirmation is not confirmation
                                or self._wrist_correction_configuration is not config
                                or self._powered_setup_context()!=values['_correction_setup_context']):
                            raise WizardError('CORRECTION_CONTEXT_CHANGED','Current correction setup or ownership changed.')
                current_correction()
                # The retained binding stays immutable. Coordinator contracts
                # accept a bounded list; pass a local copy of the same pairs.
                originals=list(config['bound'].originals)
                request,signed=confirm_correction_run(self.workspace,config['staged'],session_id=self.session_id,
                    usb_identity=config['bound'].to_dict()['usb_identity'],originals=originals,
                    operator_id=values['operator_id'],checks={name:values[name] for name in CHECKS},
                    accepted_ns=confirmation[2],now_ns=time.monotonic_ns())
                outcome=run_reviewed_correction(self.workspace,config['staged'],request,plan_original=signed,
                    originals=originals,export_root=self.export_directory,
                    cancellation=cancel,check_current=current_correction)
                # Process success and export success are not endpoint success. Only
                # the parent's reconstructed endpoint verdict can report settling.
                verdict=(outcome.owned.parsed_result if outcome.owned is not None else None)
                verified=(isinstance(verdict,dict) and verdict.get('schema')=='rocell.wrist_correction_process_finalization.v1')
                endpoint=verdict.get('status') if verified else 'UNVERIFIED'
                result=dict(action_id=action_id,physical_authority=False,
                    status='SUCCEEDED' if outcome.stage=='EXPORTED' and endpoint=='REPORTED_SETTLED' else 'FAILED',
                    message='Correction endpoint: '+str(endpoint)+'; retention: '+outcome.stage+'. No automatic next movement.',
                    steps=[dict(name='correction trial',stage=outcome.stage,report=outcome.report or {},
                        parent_verdict=verdict if verified else None)],
                    error_type=outcome.error_type,replay_allowed=False,physical_accuracy_verified=False)
                with self._lock:
                    self._wrist_correction_outcome=outcome
                    self._wrist_correction_publication=deepcopy(result)
                native_retained_result=deepcopy(result)
            elif action_id == 'run_first_motion':
                from .wizard_first_motion_coordinator import run_confirmed_first_motion
                from rocell.safety.first_motion_review_authority import OPERATOR_CHECKS
                with self._lock:
                    attachment = self._first_motion_attachment
                    confirmation = self._first_motion_confirmation
                    if (attachment is None or confirmation is None or confirmation[0] != operation_id
                            or confirmation[1] is not attachment):
                        raise WizardError('FIRST_MOTION_CONFIRMATION_MISSING','No accepted final click for this operation.')
                def check_first_motion_current():
                    with self._lock:
                        # This is an ownership/cancellation-context callback,
                        # invoked repeatedly by receipt and measurement loaders.
                        # Full source reconstruction belongs at operation entry,
                        # staging, snapshot preparation and native prelaunch; do
                        # not rescan the entire tree for every receipt field.
                        if (self._closed or self._log_error or self._source_changed
                                or self._running != operation_id
                                or self._first_motion_attachment is not attachment
                                or self._first_motion_confirmation is not confirmation
                                or self._powered_setup_context() != values['_first_motion_setup_context']):
                            raise WizardError('FIRST_MOTION_CONTEXT_CHANGED','Commissioning operation context changed.')
                inputs = {name:values[name] for name in OPERATOR_CHECKS}
                inputs.update(operator_id=values['operator_id'], selection_sha256=values['selection_sha256'])
                self._recheck_source(action_id)
                check_first_motion_current()
                outcome = run_confirmed_first_motion(self.workspace, attachment['draft'], inputs,
                    attempt_id=operation_id, reference_originals=dict(attachment['reference_originals']),
                    review_selections=attachment['review_selections'], review_root=self._log.root,
                    export_root=self.export_directory, session_id=self.session_id,
                    measurement_operation_id=attachment['measurement_operation_id'], cancellation=cancel,
                    check_current=check_first_motion_current, accepted_ns=confirmation[2])
                result = {'action_id':action_id,'physical_authority':False,
                    'status':'SUCCEEDED' if outcome.stage=='RETAINED' and
                        (outcome.report or {}).get('status')=='RESULT_RETAINED' else 'FAILED',
                    'message':'Commissioning ended at '+outcome.stage+'. Physical response still requires independent review.',
                    'steps':[{'name':'first motion','report':outcome.report or {},'stage':outcome.stage}],
                    'report_path':str(outcome.report_path) if outcome.report_path else None,
                    'error_type':outcome.error_type,'replay_allowed':False}
                with self._lock:
                    self._first_motion_outcome = outcome
                    self._first_motion_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id == 'run_endpoint_trial':
                from .wizard_endpoint_coordinator import run_endpoint_draft
                with self._lock:
                    binding = self._endpoint_binding
                    self._endpoint_attempt_id = operation_id
                    confirmation = self._endpoint_confirmation
                    if (confirmation is None or confirmation[0] != operation_id
                            or confirmation[1] is not binding):
                        raise WizardError('ENDPOINT_CONFIRMATION_MISSING','No accepted final confirmation for this attempt.')
                    confirmed = confirmation[2]
                def check_endpoint_current():
                    with self._lock:
                        self._recheck_source(action_id)
                        if (self._endpoint_binding is not binding or binding is None
                                or self._endpoint_confirmation is not confirmation
                                or binding.draft.draft_sha256!=values['draft_sha256']
                                or self._powered_setup_context()!=values['_endpoint_setup_context']):
                            raise WizardError('ENDPOINT_CONTEXT_CHANGED','Current endpoint setup changed.')
                check_endpoint_current()
                outcome = run_endpoint_draft(self.workspace,binding.draft,
                    expected_draft_sha256=values['draft_sha256'],attempt_id=operation_id,
                    reference_originals=dict(binding.reference_originals),review_root=self._log.root,
                    export_root=self.export_directory,session_id=self.session_id,
                    connection_id=operation_id,operator_reader=confirmed.intake.operator_reader,
                    engineering_reader=binding.engineering_reader,context_factory=binding.context_factory,
                    cancellation=cancel,check_current=check_endpoint_current,
                    deadline_ns=operation_deadline_ns,prepared_request=confirmed.request)
                result = {'action_id':action_id,'physical_authority':False,
                    'status':'SUCCEEDED' if outcome.stage=='RETAINED' and
                        (outcome.report or {}).get('status')=='RESULT_RETAINED' else 'FAILED',
                    'message':'Endpoint attempt finished at '+outcome.stage+'. Review telemetry; this is not continuous-motion qualification.',
                    'steps':[{'name':'endpoint trial','report':outcome.report or {},'stage':outcome.stage}],
                    'report_path':str(outcome.report_path) if outcome.report_path else None,
                    'error_type':outcome.error_type,'replay_allowed':False}
                with self._lock:
                    self._endpoint_outcome = outcome
                    self._endpoint_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
            elif action_id in _POWERED_ACTIONS:
                from .wizard_powered_feedback_native_coordinator import run_feedback
                from .physical_onboarding_durability import read_bounded_regular_file
                from .arm_bench_qualification_contract import _canonical

                context = values["_powered_setup_context"]
                with self._lock:
                    self._powered_feedback_attempt_id = operation_id
                    native_original = _canonical(self._native_arm_report)
                    generic_review = deepcopy(
                        self._device_selection.reviewed_candidate("SERIAL")
                    )

                def check_powered_current():
                    with self._lock:
                        self._recheck_source(action_id)
                        if self._powered_setup_context() != context:
                            raise WizardError(
                                "POWERED_SETUP_CHANGED",
                                "Powered setup or reviewed endpoint changed before dispatch.",
                            )

                check_powered_current()
                docs = Path(__file__).resolve().parents[3] / "docs"
                installed_firmware_evidence = None
                if values.get("installed_r120_verified") is True:
                    from .installed_r120_evidence import verified_installed_r120_evidence
                    installed_firmware_evidence = verified_installed_r120_evidence(
                        self.workspace)
                outcome = run_feedback(
                    root=self._log.root,
                    session_id=self.session_id,
                    operation_id=operation_id,
                    source_sha256=self.source_sha256,
                    startup_operation_id=context["startup_operation_id"],
                    expected_startup_sha256=context["expected_startup_sha256"],
                    native_original=native_original,
                    generic_review=generic_review,
                    history_original=read_bounded_regular_file(
                        docs / "ARM_RECEIVED_FIRMWARE_HISTORY.md", maximum_bytes=2048
                    ),
                    protocol_original=read_bounded_regular_file(
                        docs / "POWERED_FEEDBACK_PROTOCOL_REVIEW.md",
                        maximum_bytes=65536,
                    ),
                    installed_firmware_evidence_original=installed_firmware_evidence,
                    deadline_ns=operation_deadline_ns,
                    cancellation=cancel,
                    check_current=check_powered_current,
                    action_id=action_id,
                )
                result = outcome.publication()
                with self._lock:
                    self._powered_feedback_outcome = outcome
                    self._powered_feedback_publication = deepcopy(result)
                    self._absolute_wrist_capture_choices = None
                    if action_id == 'capture_powered_arm_telemetry' and result.get('status') == 'SUCCEEDED':
                        from .absolute_wrist_telemetry_source import choices_from_retained_telemetry
                        try:
                            self._absolute_wrist_capture_choices = choices_from_retained_telemetry(
                                self._log.root, outcome, session_id=self.session_id,
                                source_sha256=self.source_sha256,
                                native_identity_sha256=hashlib.sha256(native_original).hexdigest())
                        except (ValueError, KeyError, TypeError, OSError, RuntimeError):
                            # Preserve the capture even if it cannot support a draft.
                            self._absolute_wrist_capture_choices = None
                native_retained_result = deepcopy(result)
                check_powered_current()
            elif action_id == "run_passive_arm_connection":
                from .wizard_passive_arm_coordinator import PassiveArmCoordinator

                context = values["_passive_setup_context"]
                # Pin before preparation so even a preparation/dispatch failure
                # without a returned process result can export its partial files.
                with self._lock:
                    self._passive_arm_attempt_id = operation_id

                def check_passive_current():
                    with self._lock:
                        self._recheck_source(action_id)
                        if self._passive_setup_context() != context:
                            raise WizardError(
                                "PASSIVE_SETUP_CHANGED",
                                "Current setup changed before dispatch.",
                            )

                outcome = PassiveArmCoordinator().run(
                    root=self._log.root,
                    setup_operation_id=context["setup_operation_id"],
                    expected_setup_sha256=context["expected_setup_sha256"],
                    session_id=self.session_id,
                    source_sha256=self.source_sha256,
                    attempt_id=operation_id,
                    deadline_ns=operation_deadline_ns,
                    cancellation=cancel,
                    check_current=check_passive_current,
                )
                result = outcome.wizard_publication()
                # Keep bounded raw bytes outside recent-result rotation, even
                # when durable publication failed. Never invent zero effects.
                with self._lock:
                    self._passive_arm_outcome = outcome
                    self._passive_arm_publication = deepcopy(result)
                native_retained_result = deepcopy(result)
                check_passive_current()
            elif action_id == "inspect_powered_feedback_history":
                from .wizard_powered_feedback_history import inspect_history

                result, collected = inspect_history(
                    self._log.root, values["attempt_id"]
                )
                with self._lock:
                    self._powered_feedback_history_files = collected
                native_retained_result = deepcopy(result)
            elif action_id == "inspect_physical_passive_history":
                from .passive_arm_attempt_export import collect_attempt

                history_files = collect_attempt(self._log.root, values["attempt_id"])
                summary_stages = {
                    stage: {
                        key: value
                        for key, value in record.items()
                        if key != "base64_chunks"
                    }
                    for stage, record in history_files["stages"].items()
                }
                found = any(
                    record["status"] == "BYTES_COLLECTED_NOT_VALIDATED"
                    for record in summary_stages.values()
                )
                readable = not any(
                    record["status"] == "READ_FAILED"
                    for record in summary_stages.values()
                )
                status = "SUCCEEDED" if found and readable else "FAILED"
                result = {
                    "schema": "rocell.wizard_worker_result.v1",
                    "action_id": action_id,
                    "status": status,
                    "steps": [
                        {
                            "name": "physical_passive_history",
                            "exit_code": 0 if status == "SUCCEEDED" else 1,
                            "report": {
                                "attempt_id": values["attempt_id"],
                                "stages": summary_stages,
                                "historical_only": True,
                                "authenticated": False,
                                "replay_allowed": False,
                                "physical_authority": False,
                                "message": "File diagnostics only; no original validity, current connection or cleanup is established. Export to inspect exact bytes.",
                            },
                        }
                    ],
                    "device_open_count": 0,
                    "serial_write_count": 0,
                    "power_event_count": 0,
                    "motion_command_count": 0,
                    "contact_command_count": 0,
                    "metadata_inventory_performed": False,
                    "physical_authority": False,
                }
                with self._lock:
                    self._physical_passive_history_files = history_files
                native_retained_result = deepcopy(result)
            elif action_id == "inspect_passive_arm_history":
                from .passive_arm_history import inspect_history

                result = inspect_history(
                    self._log.root, values["session_id"], self.source_sha256
                )
            elif action_id == "rehearse_powered_arm_feedback":
                from .wizard_powered_feedback_coordinator import (
                    run_supervised_rehearsal,
                )

                def check_powered_source():
                    with self._lock:
                        self._recheck_source(action_id)

                check_powered_source()
                result, original, process_original = run_supervised_rehearsal(
                    root=self._log.root,
                    session_id=self.session_id,
                    operation_id=operation_id,
                    source_sha256=self.source_sha256,
                    scenario=values["scenario"],
                    cancellation=cancel,
                    deadline_ns=operation_deadline_ns,
                    recheck_source=check_powered_source,
                )
                # Preserve full failed results before final publication checks.
                with self._lock:
                    self._powered_feedback_rehearsal_original = original
                    self._powered_feedback_process_original = process_original
                    self._recheck_source(action_id)
                native_retained_result = deepcopy(result)
            elif action_id == "rehearse_passive_arm_connection":
                from .passive_arm_rehearsal import run_passive_rehearsal

                def check_passive_source():
                    with self._lock:
                        self._recheck_source(action_id)

                check_passive_source()
                result = run_passive_rehearsal(
                    parent_directory=self._log.root,
                    launch_id=self.session_id,
                    operation_id=operation_id,
                    source_sha256=self.source_sha256,
                    scenario=values["scenario"],
                    deadline_ns=operation_deadline_ns,
                    cancellation=cancel,
                    recheck_source=check_passive_source,
                )
                native_retained_result = deepcopy(result)
                check_passive_source()
            elif action_id in _NATIVE_ARM_ACTIONS:
                with self._lock:
                    self._recheck_source(action_id)
                    generic_arm = self._device_selection.reviewed_candidate("SERIAL")
                    if (
                        generic_arm is None
                        or values["_arm_review_sha256"] != self._arm_review_sha256()
                    ):
                        raise WizardError(
                            "ARM_REVIEW_CHANGED",
                            "Original reviewed serial metadata is no longer current.",
                        )
                raw_arm = self._runner.run(
                    action_id,
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    cell_id=self.cell_id,
                    cancel=cancel,
                    progress=progress,
                )
                result = self._validated_result(action_id, raw_arm)
                # Retain even a failed/cancelled diagnostic after validation,
                # independently of the rotating generic result cards.
                with self._lock:
                    self._native_arm_retained = deepcopy(result)
                native_retained_result = deepcopy(result)
                if result != raw_arm and result["status"] == "SUCCEEDED":
                    raise WizardError(
                        "BOUND_METADATA_REDACTED",
                        "Native arm metadata required redaction; no exact identity correlation was published.",
                    )
                elif result["status"] == "SUCCEEDED":
                    steps = result["steps"]
                    if (
                        len(steps) != 1
                        or steps[0]["name"] != "native_arm_metadata_snapshot"
                    ):
                        raise WizardError(
                            "INVALID_ARM_METADATA",
                            "Expected one exact native arm metadata snapshot.",
                        )
                    snapshot = decode_controller_snapshot(steps[0]["report"], self.mode)
                    staged_arm = correlate_native_arm_metadata(
                        snapshot,
                        generic_arm,
                        mode=self.mode,
                        session_id=self.session_id,
                        source_sha256=self.source_sha256,
                        operation_id=operation_id,
                    )
                    staged_arm_summary = summarize_native_arm_metadata(staged_arm)
                    result["steps"] = [
                        {
                            "name": "native_arm_metadata_correlation",
                            "exit_code": 0,
                            "report": staged_arm,
                        }
                    ]
                native_retained_result = deepcopy(result)
            elif action_id in _HELPER_ACTIONS:
                with self._lock:
                    self._recheck_source(action_id)
                    staged_helper = self._camera_helper.staged_copy()
                if cancel.is_set():
                    raise WizardError(
                        "HELPER_CANCELLED",
                        "Stop was requested before helper file inspection/review. Nothing was registered.",
                    )
                if action_id == "camera_helper_inspect":
                    inspection = self._helper_inspector(
                        self.workspace,
                        mode=self.mode,
                        source_sha256=self.source_sha256,
                        scenario=values.get("scenario"),
                    )
                    report = staged_helper.ingest(
                        inspection,
                        operation_id=operation_id,
                        operator_id=values["operator_id"],
                    )
                else:
                    report = staged_helper.review(
                        values["reviewer_id"], operation_id=operation_id
                    )
                    registration = staged_helper.registration()
                    if registration is not None:
                        # Factory construction is inert. The returned wrapper
                        # rechecks this exact inspection before each explicit
                        # metadata lookup; it exposes no probe/capture API.
                        staged_native_provider = self._helper_provider_factory(
                            self.workspace,
                            registration,
                            mode=self.mode,
                            source_sha256=self.source_sha256,
                        )
                        descriptor = dict(staged_native_provider.descriptor())
                        if descriptor.get("helper_sha256") != registration.inspection[
                            "helper_sha256"
                        ] or descriptor.get("provenance") != (
                            "INCAPABLE_FIXTURE"
                            if self.mode == "rehearsal"
                            else "WINDOWS_NATIVE_METADATA"
                        ):
                            raise WizardError(
                                "HELPER_PROVIDER_MISMATCH",
                                "Metadata provider differs from the reviewed helper and mode.",
                            )
                        staged_native = WizardNativeCameraEnrollment(
                            mode=self.mode,
                            session_id=self.session_id,
                            source_sha256=self.source_sha256,
                            provider_descriptor=descriptor,
                        )
                result = {
                    "schema": "rocell.wizard_worker_result.v1",
                    "action_id": action_id,
                    "status": "SUCCEEDED",
                    "steps": [{"name": action_id, "exit_code": 0, "report": report}],
                    "device_open_count": 0,
                    "serial_write_count": 0,
                    "power_event_count": 0,
                    "motion_command_count": 0,
                    "contact_command_count": 0,
                    "metadata_inventory_performed": False,
                    "physical_authority": False,
                }
            elif action_id in _NATIVE_ACTIONS:
                with self._lock:
                    self._recheck_source(action_id)
                    staged_native = self._native_camera.staged_copy()
                    staged_native_provider = self._native_camera_provider
                    generic_review = self._device_selection.reviewed_candidate("CAMERA")
                if staged_native_provider is None or generic_review is None:
                    raise WizardError(
                        "NATIVE_METADATA_UNAVAILABLE",
                        "Native metadata requires a registered provider and current generic camera review.",
                    )
                # The fixture scenario belongs to this explicit inventory only.
                # Keep its provider with the staged registry, never publish a
                # new scenario after a failed or cancelled inventory.
                packet = None
                try:
                    if cancel.is_set():
                        raise NativeCameraEnrollmentError(
                            "NATIVE_METADATA_CANCELLED",
                            "Stop was requested before metadata dispatch; no lookup was attempted.",
                        )
                    if action_id == "native_camera_inventory":
                        if self._native_fixture_provider:
                            if self._native_registration_managed:
                                staged_native_provider = self._helper_provider_factory(
                                    self.workspace,
                                    self._camera_helper.registration(),
                                    mode=self.mode,
                                    source_sha256=self.source_sha256,
                                    scenario=values["scenario"],
                                )
                            else:
                                staged_native_provider = (
                                    RehearsalNativeCameraMetadataProvider(
                                        values["scenario"]
                                    )
                                )
                        packet = staged_native_provider.inventory()
                        report = staged_native.ingest_inventory(
                            packet,
                            operation_id=operation_id,
                            generic_review=generic_review,
                        )
                    elif action_id == "native_camera_identity":
                        packet = staged_native_provider.identity(
                            staged_native.candidate(values["choice_id"])
                        )
                        report = staged_native.retain_identity(
                            values["choice_id"], packet, operation_id=operation_id
                        )
                    else:
                        report = staged_native.review(
                            values["choice_id"], values["reviewer_id"]
                        )
                    native_status = "SUCCEEDED"
                    native_exit = 0
                except (
                    NativeCameraEnrollmentError,
                    CameraHelperInspectionError,
                ) as exc:
                    # Retain a bounded malformed/held receipt for investigation,
                    # but never publish its staged choices or prospective binding.
                    report = {
                        "code": exc.code,
                        "message": str(exc),
                        "packet": packet,
                        "physical_authority": False,
                    }
                    if isinstance(exc, CameraHelperInspectionError):
                        report["inspection_report"] = exc.inspection_report
                        with self._lock:
                            self._revoke_helper(exc.code)
                            self._changed(state=True)
                    staged_native = None
                    native_status = "FAILED"
                    native_exit = 1
                result = {
                    "schema": "rocell.wizard_worker_result.v1",
                    "action_id": action_id,
                    "status": native_status,
                    "steps": [
                        {"name": action_id, "exit_code": native_exit, "report": report}
                    ],
                    "device_open_count": 0,
                    "serial_write_count": 0,
                    "power_event_count": 0,
                    "motion_command_count": 0,
                    "contact_command_count": 0,
                    "metadata_inventory_performed": self.mode == "physical"
                    and action_id != "native_camera_review"
                    and packet is not None,
                    "physical_authority": False,
                }
                if report.get("code") == "NATIVE_METADATA_CANCELLED":
                    result = {
                        "schema": "rocell.wizard_diagnostic_completion.v1",
                        "action_id": action_id,
                        "status": "CANCELLED",
                        "message": report["message"],
                        "elapsed_s": 0.0,
                        "output_limit_exceeded": False,
                        "physical_authority": False,
                    }
            elif action_id in _CANDIDATE_ACTIONS:
                with self._lock:
                    self._recheck_source(action_id)
                    staged_selection = self._device_selection.staged_copy()
                    reviewed = staged_selection.review(
                        values["choice_id"],
                        _CANDIDATE_ACTIONS[action_id],
                        values["reviewer_id"],
                    )
                result = {
                    "schema": "rocell.wizard_worker_result.v1",
                    "action_id": action_id,
                    "status": "SUCCEEDED",
                    "steps": [
                        {
                            "name": "metadata_candidate_review",
                            "exit_code": 0,
                            "report": reviewed,
                        }
                    ],
                    "device_open_count": 0,
                    "serial_write_count": 0,
                    "power_event_count": 0,
                    "motion_command_count": 0,
                    "contact_command_count": 0,
                    "metadata_inventory_performed": False,
                    "physical_authority": False,
                }
            elif ACTION_BY_ID[action_id].worker == "physical_intake":
                with self._lock:
                    self._recheck_source(action_id)
                    if values["intake_context_sha256"] != self._intake_context_sha256():
                        raise WizardError(
                            "INTAKE_CONTEXT_CHANGED",
                            "The original requirements or draft changed; prepare a new explicit action.",
                        )
                    if cancel.is_set():
                        raise WizardError(
                            "INTAKE_CANCELLED",
                            "Draft recording was cancelled before staging.",
                        )
                    if action_id == "physical_intake_start":
                        if self._physical_intake is not None:
                            raise WizardError(
                                "INTAKE_ALREADY_STARTED",
                                "An existing draft cannot be replaced by starting over.",
                            )
                        staged_intake = PhysicalIntakeNotebook.start(
                            self._physical_camera_setup.current_prerequisite_artifact(),
                            launch_session_id=self.session_id,
                        )
                    else:
                        if (
                            self._physical_intake is None
                            or not self._intake_is_current()
                        ):
                            raise WizardError(
                                "INTAKE_NOT_CURRENT",
                                "The current draft is unavailable.",
                            )
                        staged_intake = self._physical_intake.record(
                            **{
                                key: value
                                for key, value in values.items()
                                if key != "intake_context_sha256"
                            },
                            recorded_at_ns=time.time_ns(),
                        )
                    result = {
                        "schema": "rocell.wizard_worker_result.v1",
                        "action_id": action_id,
                        "status": "SUCCEEDED",
                        "steps": [
                            {
                                "name": "physical_intake_draft",
                                "exit_code": 0,
                                "report": {
                                    "notebook": staged_intake.view(),
                                    "meaning": "Candidate draft snapshot; current publication requires successful completion logging and no Stop.",
                                },
                            }
                        ],
                        "device_open_count": 0,
                        "serial_write_count": 0,
                        "power_event_count": 0,
                        "motion_command_count": 0,
                        "contact_command_count": 0,
                        "metadata_inventory_performed": False,
                        "physical_authority": False,
                    }
                    native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_intake_evidence":
                with self._lock:
                    self._recheck_source(action_id)
                    intake_notebook = self._physical_intake
                # The bounded original-byte transaction runs outside Arrival's
                # lock. GET and Stop stay responsive; the setup owner acquires
                # its own exact current context before withdrawing publication.
                result = self._physical_intake_evidence.perform(
                    action_id,
                    expected_context_sha256=values["_intake_evidence_context_sha256"],
                    notebook=intake_notebook,
                    values={
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    cancellation=cancel,
                    progress=progress,
                    export_parent=self.export_directory,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_usb_identity":
                with self._lock:
                    if action_id == "physical_usb_identity_export":
                        try:
                            self._recheck_source("physical_usb_identity_collect")
                        except WizardError as exc:
                            if exc.code != "SOURCE_CHANGED":
                                raise
                    else:
                        self._recheck_source(action_id)
                    usb_native = self._native_camera.staged_copy()
                    usb_helper = self._camera_helper.staged_copy()
                # The service owns the exact original target and coordinator.
                # Never send this action through the generic diagnostic child.
                result = self._usb_identity.perform(
                    action_id,
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    expected_context_sha256=values["_usb_identity_context_sha256"],
                    cancellation=cancel,
                    progress=progress,
                    export_parent=self.export_directory,
                    native_camera=usb_native,
                    helper=usb_helper,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_camera_identity_records":
                with self._lock:
                    if action_id == "physical_camera_identity_export":
                        try:
                            self._recheck_source("physical_camera_identity_submit")
                        except WizardError as exc:
                            if exc.code != "SOURCE_CHANGED":
                                raise
                    else:
                        self._recheck_source(action_id)
                    identity_native = self._native_camera.staged_copy()
                    identity_helper = self._camera_helper.staged_copy()
                result = self._camera_identity_records.perform(
                    action_id,
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    native_camera=identity_native,
                    helper=identity_helper,
                    expected_context_sha256=values["_camera_identity_context_sha256"],
                    cancellation=cancel,
                    progress=progress,
                    export_parent=self.export_directory,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_received_camera":
                with self._lock:
                    if action_id == "physical_received_camera_export":
                        try:
                            self._recheck_source("physical_received_camera_submit")
                        except WizardError as exc:
                            if exc.code != "SOURCE_CHANGED":
                                raise
                    else:
                        self._recheck_source(action_id)
                result = self._received_camera.perform(
                    action_id,
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    expected_context_sha256=values["_received_camera_context_sha256"],
                    cancellation=cancel,
                    progress=progress,
                    export_parent=self.export_directory,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_static_camera_onboarding":
                with self._lock:
                    self._recheck_source(action_id)
                result = self._static_camera_onboarding.perform(
                    action_id,
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    expected_context_sha256=values[
                        "_static_camera_onboarding_context_sha256"
                    ],
                    cancellation=cancel,
                    progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_source_qualification":
                with self._lock:
                    self._recheck_source(action_id)
                result = self._source_qualification.perform(
                    action_id,
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    expected_context_sha256=values[
                        "_source_qualification_context_sha256"
                    ],
                    cancellation=cancel,
                    progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif action_id in {
                "physical_camera_probe_attempt_export",
                CONFIGURATION_EXPORT,
            }:
                from .camera_probe_attempt_export import export_probe_attempt
                from .camera_configuration_attempt_export import (
                    export_configuration_attempt,
                )

                with self._lock:
                    configuration_export = action_id == CONFIGURATION_EXPORT
                    current = (
                        self._configuration_wizard.export_context(
                            values["attempt_choice_id"]
                        )
                        if configuration_export
                        else self._probe_attempt_export_context()
                    )
                    expected = values[
                        (
                            "_configuration_export_context_sha256"
                            if configuration_export
                            else "_probe_attempt_export_context_sha256"
                        )
                    ]
                    if current != expected:
                        raise WizardError(
                            (
                                "CAMERA_CONFIGURATION_ATTEMPT_EXPORT_CHANGED"
                                if configuration_export
                                else "CAMERA_PROBE_ATTEMPT_EXPORT_CHANGED"
                            ),
                            "The retained attempt changed after preview; preview the exact export again.",
                        )
                    attempt_packet = (
                        self._configuration_wizard.packet(values["attempt_choice_id"])
                        if configuration_export
                        else self._probe_attempt_packet()
                    )
                export_attempt = (
                    export_configuration_attempt
                    if configuration_export
                    else export_probe_attempt
                )
                receipt = export_attempt(
                    attempt_packet,
                    export_parent=self.export_directory,
                    cancellation=cancel,
                    deadline_ns=operation_deadline_ns,
                )
                with self._lock:
                    self._exports.append(receipt)
                    self._exports = self._exports[-8:]
                    self._changed()
                result = dict(
                    schema="rocell.wizard_worker_result.v1",
                    action_id=action_id,
                    status="SUCCEEDED",
                    steps=[
                        dict(
                            name=action_id,
                            exit_code=0,
                            report=dict(receipt=receipt, physical_authority=False),
                        )
                    ],
                    device_open_count=0,
                    serial_write_count=0,
                    power_event_count=0,
                    motion_command_count=0,
                    contact_command_count=0,
                    metadata_inventory_performed=False,
                    physical_authority=False,
                )
                native_retained_result = deepcopy(result)
            elif action_id == "physical_camera_probe_export":
                from .camera_probe_setup_export import export_probe_setup

                with self._lock:
                    try:
                        self._recheck_source("physical_camera_probe_prepare")
                    except WizardError as exc:
                        if exc.code != "SOURCE_CHANGED":
                            raise
                    if (
                        self._probe_export_context()
                        != values["_probe_export_context_sha256"]
                    ):
                        raise WizardError(
                            "CAMERA_PROBE_EXPORT_CHANGED",
                            "Retained probe records changed since preview; preview the exact export again.",
                        )
                    probe_packet = (
                        self._physical_camera_setup.probe_record_diagnostics()
                    )
                receipt = export_probe_setup(
                    probe_packet,
                    export_parent=self.export_directory,
                    cancellation=cancel,
                    deadline_ns=operation_deadline_ns,
                )
                # A completed export survives late Stop/log failure. Keep the
                # receipt before any fallible result publication, as elsewhere.
                with self._lock:
                    self._exports.append(receipt)
                    self._exports = self._exports[-8:]
                    self._changed()
                result = dict(
                    schema="rocell.wizard_worker_result.v1",
                    action_id=action_id,
                    status="SUCCEEDED",
                    steps=[
                        dict(
                            name=action_id,
                            exit_code=0,
                            report=dict(receipt=receipt, physical_authority=False),
                        )
                    ],
                    device_open_count=0,
                    serial_write_count=0,
                    power_event_count=0,
                    motion_command_count=0,
                    contact_command_count=0,
                    metadata_inventory_performed=False,
                    physical_authority=False,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_camera_setup":
                with self._lock:
                    self._recheck_source(action_id)
                    setup_enrollment = self._native_camera.staged_copy()
                    setup_source_report = self._camera_setup_source_report()
                    setup_enrollment_bytes = _json_payload(
                        setup_enrollment.export_snapshot()
                    )

                def validate_setup_enrollment() -> None:
                    with self._lock:
                        if (
                            self._running != operation_id
                            or self._closed
                            or cancel.is_set()
                            or not self._probe_metadata_current()
                            or _json_payload(self._native_camera.export_snapshot())
                            != setup_enrollment_bytes
                        ):
                            raise WizardError(
                                "CAMERA_PROBE_CURRENT_ENROLLMENT",
                                "Current logged wizard enrollment or operation ownership changed; retain diagnostics without replay.",
                            )

                # Keep long filesystem qualification outside the Arrival lock
                # so progress polling and Stop remain responsive.
                setup_options: dict[str, Any] = {}
                if action_id in {
                    "physical_camera_mode_enter",
                    "physical_camera_probe_prepare",
                    "physical_camera_probe_review",
                }:
                    setup_options["deadline_ns"] = operation_deadline_ns
                if action_id in {
                    "physical_camera_probe_prepare",
                    "physical_camera_probe_review",
                }:
                    setup_options["validate_current_enrollment"] = (
                        validate_setup_enrollment
                    )
                result = self._physical_camera_setup.perform(
                    action_id,
                    expected_context_sha256=values["setup_context_sha256"],
                    operator_id=(
                        values["reviewer_id"]
                        if action_id == "physical_camera_review_sources"
                        else values["operator_id"]
                    ),
                    enrollment=setup_enrollment,
                    source_report=setup_source_report,
                    cancellation=cancel,
                    progress=progress,
                    choice_id=values.get("choice_id"),
                    **setup_options,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_camera_runtime":
                with self._lock:
                    self._recheck_source(action_id)
                # File I/O stays outside the UI lock. The inspector is bounded,
                # purpose-specific and incapable of opening a device.
                result = self._physical_camera.perform_runtime_action(
                    action_id,
                    expected_context_sha256=values["runtime_context_sha256"],
                    actor_id=values[
                        (
                            "operator_id"
                            if action_id == "physical_camera_runtime_inspect"
                            else "reviewer_id"
                        )
                    ],
                    operation_id=operation_id,
                    cancellation=cancel,
                    progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif action_id == OPERATING_SUBMISSION:
                result = self._operating_submission.run(
                    operation_id, values, cancellation=cancel,
                    deadline_ns=operation_deadline_ns, progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif action_id == OPERATING_ASSESSMENT:
                result = self._operating_assessment.run(
                    operation_id, values, cancellation=cancel,
                    deadline_ns=operation_deadline_ns, progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif action_id == OPERATING_PROPOSAL:
                result = self._operating_proposal.run(
                    operation_id,
                    values,
                    cancellation=cancel,
                    deadline_ns=operation_deadline_ns,
                    progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_camera_configuration":
                with self._lock:
                    self._recheck_source(action_id)
                    self._check_physical_camera_settings_identity()
                result = self._physical_camera.stage_configuration(
                    {
                        key: value
                        for key, value in values.items()
                        if not key.startswith("_")
                    },
                    expected_context_sha256=values["_configuration_context_sha256"],
                    cancellation=cancel,
                )
                native_retained_result = deepcopy(result)
            elif action_id == "physical_camera_probe":
                with self._lock:
                    self._recheck_source(action_id)
                    queue = self._probe_dispatch_queue
                    if (
                        queue is None
                        or queue["operation_id"] != operation_id
                        or queue["claimed"]
                    ):
                        raise WizardError(
                            "CAMERA_PROBE_QUEUE_REQUIRED",
                            "The original one-use logged queue is required.",
                        )
                    queue["claimed"] = True
                    original_session = self._physical_camera_setup.session
                    original_enrollment = self._native_camera
                    original_context = values["_original_probe_context"]

                def validate_original_probe_context() -> None:
                    with self._lock:
                        self._recheck_source(action_id)
                        if (
                            self._running != operation_id
                            or self._closed
                            or self._log_error
                            or cancel.is_set()
                            or self._probe_dispatch_queue is not queue
                            or queue["operation_id"] != operation_id
                            or queue["claimed"] is not True
                            or self._physical_camera_setup.session
                            is not original_session
                            or self._native_camera is not original_enrollment
                            or self._original_probe_context() != original_context
                            or hashlib.sha256(
                                _json_payload(original_context)
                            ).hexdigest()
                            != queue["context_sha256"]
                        ):
                            raise WizardError(
                                "CAMERA_PROBE_CURRENT_OWNER_CHANGED",
                                "Original setup, current logged enrollment, Stop or operation ownership changed. Retain diagnostics without replay.",
                            )

                validate_original_probe_context()
                result = self._physical_camera.run_original_probe(
                    original_session,
                    original_enrollment,
                    request_key=operation_id,
                    **{
                        key: original_context[key]
                        for key in (
                            "expected_header_sha256",
                            "expected_preparation_sha256",
                            "expected_review_sha256",
                            "expected_plan_sha256",
                        )
                    },
                    operator_id=values["operator_id"],
                    arm_actuator_supply_disconnected=values[
                        "arm_actuator_supply_disconnected"
                    ],
                    bounded_probe_consent=values["bounded_probe_consent"],
                    cancellation=cancel,
                    deadline_ns=operation_deadline_ns,
                    progress=progress,
                    validate_current_context=validate_original_probe_context,
                )
                native_retained_result = deepcopy(result)
                validate_original_probe_context()
            elif action_id == CONFIGURATION_CAPTURE:
                result = self._configuration_wizard.run(
                    operation_id,
                    values,
                    cancellation=cancel,
                    deadline_ns=operation_deadline_ns,
                    progress=progress,
                )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_camera":
                if action_id != "physical_camera_plan":
                    raise WizardError(
                        "PHYSICAL_CAMERA_RELEASE_HELD",
                        "Native acquisition is not released.",
                    )
                with self._lock:
                    self._recheck_source(action_id)
                    result = self._physical_camera.record_plan(
                        values["operation"],
                        self._native_camera,
                        expected_plan_sha256=values["planning_context_sha256"],
                        operator_id=values["operator_id"],
                        cancellation=cancel,
                    )
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "physical_preflight":
                with self._lock:
                    self._recheck_source(action_id)
                result = self._source_preflight.perform(
                    values["operator_id"], cancellation=cancel, progress=progress
                )
                # Preserve the returned complete report even if the later
                # service publication/source check refuses current readiness.
                native_retained_result = deepcopy(result)
            elif ACTION_BY_ID[action_id].worker == "commissioning":
                with self._lock:
                    self._recheck_source(action_id)
                    if action_id in _PREVIEW_INVALIDATING_ACTIONS:
                        self._clear_camera_preview("NO_CURRENT_STAGE_CAPTURE")
                result = self._commissioning.perform(
                    action_id, values, cancellation=cancel, progress=progress
                )
            else:
                result = self._runner.run(
                    action_id,
                    values,
                    cell_id=self.cell_id,
                    cancel=cancel,
                    progress=progress,
                )
            metadata_finished_at_ns = time.time_ns()
            original_result = result
            result = self._validated_result(action_id, result)
            if (
                staged_native is not None
                or staged_arm is not None
                or staged_helper is not None
                or action_id == "physical_camera_plan"
                or action_id == "physical_camera_probe"
                or action_id == CONFIGURATION_CAPTURE
                or action_id == "physical_camera_configuration"
                or action_id == OPERATING_PROPOSAL
                or action_id == OPERATING_ASSESSMENT
                or ACTION_BY_ID[action_id].worker == "physical_camera_setup"
                or ACTION_BY_ID[action_id].worker == "physical_camera_runtime"
                or ACTION_BY_ID[action_id].worker == "physical_intake"
                or ACTION_BY_ID[action_id].worker == "physical_intake_evidence"
                or ACTION_BY_ID[action_id].worker == "physical_source_qualification"
                or ACTION_BY_ID[action_id].worker == "physical_static_camera_onboarding"
                or ACTION_BY_ID[action_id].worker == "physical_received_camera"
                or ACTION_BY_ID[action_id].worker == "physical_usb_identity"
                or (
                    ACTION_BY_ID[action_id].worker == "physical_camera_identity_records"
                )
                or (
                    ACTION_BY_ID[action_id].worker == "commissioning"
                    and self._commissioning.view().get("noncontact_evaluation")
                    is not None
                )
            ) and original_result != result:
                # Redaction must not silently replace the exact wire bytes that
                # a prospective endpoint artifact hashes. Retain the redacted
                # diagnostic for investigation, but discard all staged readiness.
                # A successful registry report is already bounded before hashing.
                staged_native = None
                staged_helper = None
                staged_intake = None
                staged_arm = None
                result["status"] = "FAILED"
                result["steps"][0]["exit_code"] = 1
                if ACTION_BY_ID[action_id].worker == "commissioning":
                    result["code"] = "BOUND_NONCONTACT_REDACTED"
                    result["message"] = (
                        "Retained readiness diagnostics required redaction. Exported text is not the exact original evidence; no current gap report was published."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_intake":
                    result["code"] = "BOUND_INTAKE_REDACTED"
                    result["message"] = (
                        "Draft text required redaction. The retained result is redacted, not the exact hashed notebook; no new current draft was published."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_intake_evidence":
                    result["code"] = "BOUND_INTAKE_EVIDENCE_REDACTED"
                    result["message"] = (
                        "Retained intake diagnostics required redaction. Exported text is not the exact original subject named by its hashes; no current intake review is published. Original M1 bytes remain historical."
                    )
                elif (
                    ACTION_BY_ID[action_id].worker == "physical_camera_identity_records"
                ):
                    result["code"] = "BOUND_CAMERA_IDENTITY_REDACTED"
                    result["message"] = (
                        "Identity diagnostics required redaction. No current original identity review is published; exact source records remain historical and distinct from sanitized text."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_usb_identity":
                    result["code"] = "BOUND_USB_IDENTITY_REDACTED"
                    result["message"] = (
                        "USB diagnostics required redaction. Current publication is withheld; sanitized text is not the original evidence named by its hashes. Export retained originals separately."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_received_camera":
                    result["code"] = "BOUND_RECEIVED_CAMERA_REDACTED"
                    result["message"] = (
                        "Received-camera diagnostics required redaction. No current receipt or stage acceptance is published; original subjects remain separate from sanitized text."
                    )
                elif (
                    ACTION_BY_ID[action_id].worker
                    == "physical_static_camera_onboarding"
                ):
                    result["code"] = "BOUND_STATIC_CAMERA_REDACTED"
                    result["message"] = (
                        "Static design diagnostics required redaction; exported text is not the original subject. No current design acceptance is published; original evidence remains historical."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_source_qualification":
                    result["code"] = "BOUND_SOURCE_QUALIFICATION_REDACTED"
                    result["message"] = (
                        "Source qualification diagnostics required redaction; exported text is not the exact original subject. No current source-stage acceptance is published; original evidence remains historical."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_camera_runtime":
                    result["code"] = "BOUND_CAMERA_RUNTIME_REDACTED"
                    result["message"] = (
                        "Runtime diagnostics required redaction; the exported text is not the exact original inspection. No current file review was published."
                    )
                elif ACTION_BY_ID[action_id].worker == "physical_camera_setup":
                    result["code"] = "BOUND_CAMERA_SETUP_REDACTED"
                    result["message"] = (
                        "Camera setup diagnostics required redaction; exported text is not the exact original M1 bytes. No current setup report was published."
                    )
                elif action_id == OPERATING_ASSESSMENT:
                    result["code"] = "BOUND_CAMERA_ASSESSMENT_REDACTED"
                    result["message"] = "Assessment required redaction. Retain diagnostics; no successful original check or approval is inferred."
                elif action_id == OPERATING_PROPOSAL:
                    result["code"] = "BOUND_CAMERA_PROPOSAL_REDACTED"
                    result["message"] = (
                        "Draft diagnostics required redaction. Sanitized text is not the original proposal; current publication is withheld."
                    )
                elif action_id == "physical_camera_configuration":
                    result["code"] = "BOUND_CAMERA_CONFIGURATION_REDACTED"
                    result["message"] = (
                        "Native settings intent required diagnostic redaction; the exact candidate was not published or applied."
                    )
                elif action_id == CONFIGURATION_CAPTURE:
                    result["code"] = "BOUND_CAMERA_CAPTURE_REDACTED"
                    result["message"] = (
                        "Capture diagnostics required redaction. No current image was published; inspect the retained attempt without replay."
                    )
                elif action_id == "physical_camera_plan":
                    result["code"] = "BOUND_CAMERA_INTENT_REDACTED"
                    result["message"] = (
                        "Camera intent required diagnostic redaction. The retained report is "
                        "redacted, not the exact original intent named by its hash. "
                        "No current camera plan was published; acquisition remains held."
                    )
                else:
                    result["code"] = "BOUND_METADATA_REDACTED"
                    result["message"] = (
                        "Metadata required diagnostic redaction. The retained result is redacted, "
                        "not exact endpoint evidence; no native selection or binding was published."
                    )
                result["original_result_sha256"] = hashlib.sha256(
                    _json_payload(original_result)
                ).hexdigest()
            if (
                action_id in _NATIVE_ACTIONS
                or action_id in _NATIVE_ARM_ACTIONS
                or action_id in _HELPER_ACTIONS
                or action_id == "physical_camera_plan"
                or action_id == "physical_camera_probe"
                or action_id == CONFIGURATION_CAPTURE
                or action_id == "physical_camera_configuration"
                or ACTION_BY_ID[action_id].worker == "physical_camera_setup"
                or ACTION_BY_ID[action_id].worker == "physical_camera_runtime"
                or ACTION_BY_ID[action_id].worker == "physical_intake"
                or ACTION_BY_ID[action_id].worker == "physical_intake_evidence"
                or ACTION_BY_ID[action_id].worker == "physical_source_qualification"
                or ACTION_BY_ID[action_id].worker == "physical_static_camera_onboarding"
                or ACTION_BY_ID[action_id].worker == "physical_received_camera"
                or ACTION_BY_ID[action_id].worker == "physical_camera_identity_records"
                or ACTION_BY_ID[action_id].worker == "physical_usb_identity"
            ):
                # Keep the validated bounded metadata even if a final source
                # check rejects publication after the provider has returned.
                native_retained_result = deepcopy(result)
            if action_id in _NATIVE_ARM_ACTIONS:
                with self._lock:
                    self._native_arm_retained = deepcopy(result)
            status = result["status"]
            if status == "SUCCEEDED" and action_id in _INVENTORY_ACTIONS:
                try:
                    steps = result["steps"]
                    if len(steps) != 1 or steps[0]["name"] != "metadata_inventory":
                        raise WizardError(
                            "INVALID_DEVICE_INVENTORY",
                            "Expected one exact metadata inventory report.",
                        )
                    staged_selection = WizardDeviceSelection(
                        mode=self.mode,
                        session_id=self.session_id,
                        source_sha256=self.source_sha256,
                    )
                    staged_selection.ingest(
                        steps[0]["report"], operation_id=operation_id
                    )
                except (DeviceSelectionError, WizardError) as exc:
                    # Preserve the actual failed/partial report for investigation
                    # instead of replacing it with a success-looking empty list.
                    staged_selection = None
                    status = result["status"] = "FAILED"
                    result["code"] = exc.code
                    result["message"] = str(exc)
            geometry = pixels = None
            if status == "SUCCEEDED" and action_id == "board_preview":
                geometry, pixels = _nominal_board(self.workspace)
            with self._lock:
                self._recheck_source(action_id)
                if (
                    ACTION_BY_ID[action_id].worker == "physical_usb_identity"
                    and status == "SUCCEEDED"
                ):
                    self._usb_identity.validate_publication(result)
                if (
                    ACTION_BY_ID[action_id].worker == "physical_camera_identity_records"
                    and status == "SUCCEEDED"
                ):
                    self._camera_identity_records.validate_publication(result)
                if (
                    ACTION_BY_ID[action_id].worker == "physical_received_camera"
                    and status == "SUCCEEDED"
                ):
                    self._received_camera.validate_publication(result)
                if (
                    ACTION_BY_ID[action_id].worker
                    == "physical_static_camera_onboarding"
                    and status == "SUCCEEDED"
                ):
                    self._static_camera_onboarding.validate_publication(result)
                if (
                    ACTION_BY_ID[action_id].worker == "physical_source_qualification"
                    and status == "SUCCEEDED"
                ):
                    # Compare the exact returned subject before appending any
                    # derived Stop explanation to the retained operation result.
                    self._source_qualification.validate_publication(result)
                if (
                    staged_arm is not None
                    and values["_arm_review_sha256"] != self._arm_review_sha256()
                ):
                    raise WizardError(
                        "ARM_REVIEW_CHANGED",
                        "The reviewed serial candidate changed before publication; retained metadata is historical only.",
                    )
                if (
                    staged_intake is not None
                    and values["intake_context_sha256"] != self._intake_context_sha256()
                ):
                    raise WizardError(
                        "INTAKE_CONTEXT_CHANGED",
                        "The original requirements or draft changed before publication; retained candidate is historical only.",
                    )
                if cancel.is_set() and status == "SUCCEEDED":
                    if ACTION_BY_ID[action_id].worker in {
                        "commissioning",
                        "physical_preflight",
                        "physical_camera_setup",
                        "physical_intake_evidence",
                        "physical_source_qualification",
                        "physical_static_camera_onboarding",
                        "physical_received_camera",
                        "physical_camera_identity_records",
                        "physical_usb_identity",
                    }:
                        result["message"] = (
                            "Stop was requested, but this durable diagnostic operation had completed. "
                            "Inspect its committed result; cancellation cannot undo evidence or authorize replay."
                        )
                    else:
                        status = "CANCELLED"
                        result["message"] = (
                            "Cancellation was requested; no diagnostic readiness was promoted."
                        )
                if (
                    geometry is not None
                    and pixels is not None
                    and status == "SUCCEEDED"
                ):
                    image_id = "image-" + uuid.uuid4().hex
                    self._images = {image_id: pixels}
                    self._camera["image_id"] = image_id
                    self._camera["image_capture"] = None
                    self._camera["image_provenance"] = (
                        "NOMINAL_SCHEMATIC_NOT_CAMERA_CAPTURE"
                    )
                    self._board.update(
                        {"status": "NOMINAL_SCHEMATIC_AVAILABLE", "geometry": geometry}
                    )
                campaign_preview = None
                campaign_capture = None
                if (
                    status == "SUCCEEDED"
                    and action_id in _CAMERA_CAMPAIGN_ACTIONS
                    and not cancel.is_set()
                ):
                    preview = self._commissioning.latest_preview()
                    if preview is not None:
                        capture = self._commissioning.view()["capture_dataset"]
                        binding = capture["verification"]["plan"]["binding"]
                        campaign_preview = preview
                        campaign_capture = {
                            "meaning": "LAST_SUCCESSFUL_REHEARSAL_CAPTURE_NOT_LIVE",
                            "campaign_id": binding["campaign_id"],
                            "settings_epoch": binding["settings_epoch"],
                            "manifest_sha256": capture["dataset"]["manifest_sha256"],
                        }
                if (
                    ACTION_BY_ID[action_id].worker == "physical_camera_runtime"
                    and status == "SUCCEEDED"
                ):
                    self._physical_camera.validate_runtime_publication(
                        operation_id, result
                    )
                if (
                    action_id == "physical_camera_configuration"
                    and status == "SUCCEEDED"
                ):
                    self._check_physical_camera_settings_identity()
                    self._physical_camera.validate_configuration_publication(result)
                self._finish(operation_id, status, result)
                if action_id == OPERATING_SUBMISSION:
                    if self._operations[operation_id]["status"] == "SUCCEEDED" and not cancel.is_set():
                        self._operating_submission.publish(operation_id, result, cancel)
                    else:
                        self._operating_submission.withhold(operation_id)
                        if cancel.is_set():
                            raise WizardError("OPERATING_SUBMIT_INTERRUPTED", "Stop withheld publication; any committed original submission remains historical and is not replayed.")
                if action_id == OPERATING_PROPOSAL:
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._operating_proposal.publish(operation_id, result, cancel)
                    else:
                        self._operating_proposal.withhold(operation_id)
                        if cancel.is_set():
                            raise WizardError("MODE_PROPOSAL_INTERRUPTED", "Stop withheld the logged draft; no current proposal was published.")
                if action_id in {"physical_camera_probe", CONFIGURATION_CAPTURE}:
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._publish_physical_camera_observation(
                            operation_id, result, cancellation=cancel
                        )
                        if action_id == CONFIGURATION_CAPTURE:
                            self._configuration_wizard.record_publication(operation_id)
                    else:
                        self._physical_camera.invalidate()
                        if action_id == CONFIGURATION_CAPTURE and cancel.is_set():
                            raise WizardError(
                                "CONFIGURATION_PUBLICATION_CANCELLED",
                                "Stop withheld the settings-capture image; preserve its original attempt.",
                            )
                if action_id == "physical_camera_configuration":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera.publish_configuration(
                            operation_id, result
                        )
                        # Legacy/internal staging remains usable, but cannot
                        # manufacture an original-bound public capture receipt.
                        if self._probe_attempt_completion is not None:
                            self._configuration_wizard.publish_settings(
                                operation_id, result
                            )
                        self._changed(state=True)
                    else:
                        self._physical_camera.invalidate()
                if action_id in _NATIVE_ARM_ACTIONS:
                    if (
                        staged_arm is not None
                        and self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._native_arm_report = staged_arm
                        self._native_arm_summary = staged_arm_summary
                        self._native_arm_review_sha256 = values["_arm_review_sha256"]
                        self._native_arm_current = True
                        self._native_arm_reason = None
                        self._changed(state=True)
                    else:
                        self._invalidate_native_arm("ARM_METADATA_NOT_PUBLISHED")
                if ACTION_BY_ID[action_id].worker == "physical_camera_runtime":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera.publish_runtime_action(operation_id)
                    else:
                        self._physical_camera.invalidate_runtime()
                if ACTION_BY_ID[action_id].worker == "commissioning":
                    self._published_noncontact_sha256 = (
                        self._noncontact_publication_context(self._commissioning.view())
                        if self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                        else None
                    )
                if (
                    staged_intake is not None
                    and self._operations[operation_id]["status"] == "SUCCEEDED"
                    and not cancel.is_set()
                ):
                    self._physical_intake = staged_intake
                    self._changed(state=True)
                if ACTION_BY_ID[action_id].worker == "physical_camera_setup":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera_setup.publication_completed(operation_id)
                        self._physical_intake_evidence.observe_setup()
                        self._source_qualification.observe_setup()
                        self._static_camera_onboarding.observe_setup()
                        self._received_camera.observe_setup()
                    else:
                        self._physical_camera_setup.invalidate()
                        self._physical_intake_evidence.invalidate()
                        self._source_qualification.invalidate()
                        self._static_camera_onboarding.invalidate()
                        self._received_camera.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_source_qualification":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera_setup.publication_completed(operation_id)
                        self._source_qualification.publication_completed(operation_id)
                        self._static_camera_onboarding.observe_setup()
                        self._received_camera.observe_setup()
                        self._physical_intake_evidence.observe_setup()
                        self._changed(state=True)
                    else:
                        self._physical_camera_setup.invalidate()
                        self._source_qualification.invalidate()
                        self._physical_intake_evidence.invalidate()
                        self._static_camera_onboarding.invalidate()
                        self._received_camera.invalidate()
                if (
                    ACTION_BY_ID[action_id].worker
                    == "physical_static_camera_onboarding"
                ):
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera_setup.publication_completed(operation_id)
                        self._static_camera_onboarding.publication_completed(
                            operation_id
                        )
                        self._received_camera.observe_setup()
                        self._source_qualification.observe_setup()
                        self._physical_intake_evidence.observe_setup()
                        self._changed(state=True)
                    else:
                        self._physical_camera_setup.invalidate()
                        self._static_camera_onboarding.invalidate()
                        self._received_camera.invalidate()
                        self._source_qualification.invalidate()
                        self._physical_intake_evidence.invalidate()
                if ACTION_BY_ID[action_id].worker in {
                    "physical_camera_setup",
                    "physical_source_qualification",
                    "physical_static_camera_onboarding",
                }:
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._camera_identity_records.observe_setup()
                    else:
                        self._camera_identity_records.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_camera_identity_records":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        if (
                            action_id != "physical_camera_identity_export"
                            and self._physical_camera_setup.view()["publication"][
                                "status"
                            ]
                            == "PENDING"
                        ):
                            self._physical_camera_setup.publication_completed(
                                operation_id
                            )
                        self._camera_identity_records.publication_completed(
                            operation_id
                        )
                        if action_id != "physical_camera_identity_export":
                            self._received_camera.observe_setup()
                            self._static_camera_onboarding.observe_setup()
                            self._source_qualification.observe_setup()
                            self._physical_intake_evidence.observe_setup()
                        self._changed(state=True)
                    else:
                        self._physical_camera_setup.invalidate()
                        self._camera_identity_records.invalidate()
                        self._received_camera.invalidate()
                        self._static_camera_onboarding.invalidate()
                        self._source_qualification.invalidate()
                        self._physical_intake_evidence.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_received_camera":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        # A metadata export is not a new original-store commit.
                        if action_id != "physical_received_camera_export":
                            if (
                                self._physical_camera_setup.view()["publication"][
                                    "status"
                                ]
                                == "PENDING"
                            ):
                                self._physical_camera_setup.publication_completed(
                                    operation_id
                                )
                        self._received_camera.publication_completed(operation_id)
                        if action_id != "physical_received_camera_export":
                            self._static_camera_onboarding.observe_setup()
                            self._source_qualification.observe_setup()
                            self._physical_intake_evidence.observe_setup()
                            self._camera_identity_records.observe_setup()
                        self._changed(state=True)
                    else:
                        self._physical_camera_setup.invalidate()
                        self._received_camera.invalidate()
                        self._camera_identity_records.invalidate()
                        self._static_camera_onboarding.invalidate()
                        self._source_qualification.invalidate()
                        self._physical_intake_evidence.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_intake_evidence":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera_setup.publication_completed(operation_id)
                        self._physical_intake_evidence.publication_completed(
                            operation_id
                        )
                        self._changed(state=True)
                    else:
                        self._physical_intake_evidence.invalidate()
                        if action_id != "physical_intake_files_discover":
                            self._physical_camera_setup.invalidate()
                if ACTION_BY_ID[action_id].worker in {
                    "physical_camera_setup",
                    "physical_source_qualification",
                    "physical_static_camera_onboarding",
                    "physical_received_camera",
                    "physical_camera_identity_records",
                    "physical_intake_evidence",
                } and action_id not in {
                    "physical_received_camera_export",
                    "physical_camera_identity_export",
                }:
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._usb_identity.observe_setup()
                    else:
                        self._usb_identity.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_usb_identity":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        if (
                            action_id != "physical_usb_identity_export"
                            and self._physical_camera_setup.view()["publication"][
                                "status"
                            ]
                            == "PENDING"
                        ):
                            self._physical_camera_setup.publication_completed(
                                operation_id
                            )
                        self._usb_identity.publication_completed(operation_id)
                        if action_id != "physical_usb_identity_export":
                            self._camera_identity_records.observe_setup()
                            self._received_camera.observe_setup()
                            self._static_camera_onboarding.observe_setup()
                            self._source_qualification.observe_setup()
                            self._physical_intake_evidence.observe_setup()
                        self._changed(state=True)
                    else:
                        self._physical_camera_setup.invalidate()
                        self._usb_identity.invalidate()
                        self._camera_identity_records.invalidate()
                        self._received_camera.invalidate()
                        self._static_camera_onboarding.invalidate()
                        self._source_qualification.invalidate()
                        self._physical_intake_evidence.invalidate()
                if action_id == "physical_camera_plan":
                    if (
                        self._operations[operation_id]["status"] == "SUCCEEDED"
                        and not cancel.is_set()
                    ):
                        self._physical_camera.publication_completed(operation_id)
                    else:
                        self._physical_camera.invalidate()
                if (
                    campaign_preview is not None
                    and self._operations[operation_id]["status"] == "SUCCEEDED"
                    and not cancel.is_set()
                ):
                    # A preview is published only after full result retention
                    # and completion logging. A committed result remains
                    # inspectable if Stop arrived late, without promoting media.
                    image_id = "image-" + uuid.uuid4().hex
                    self._images = {image_id: campaign_preview}
                    self._camera["image_id"] = image_id
                    self._camera["image_provenance"] = (
                        "SYNTHETIC_DATASET_DERIVED_PREVIEW_NOT_PHYSICAL"
                    )
                    self._camera["image_capture"] = campaign_capture
                if (
                    staged_helper is not None
                    and self._operations[operation_id]["status"] == "SUCCEEDED"
                ):
                    self._camera_helper = staged_helper
                    self._changed(state=True)
                if (
                    staged_selection is not None
                    and self._operations[operation_id]["status"] == "SUCCEEDED"
                ):
                    # Publish only after full-result retention and completion log
                    # succeed. A failed log/export cannot mint a reviewed choice.
                    self._device_selection = staged_selection
                    self._changed(state=True)
                if (
                    staged_native is not None
                    and self._operations[operation_id]["status"] == "SUCCEEDED"
                ):
                    self._native_camera = staged_native
                    self._native_camera_provider = staged_native_provider
                    self._probe_metadata_publication = None
                    if action_id == "native_camera_review" and not cancel.is_set():
                        owned_snapshot = staged_native.export_snapshot()
                        binding = owned_snapshot.get("binding_artifact")
                        if binding is not None:
                            payload = binding["payload"]
                            self._probe_metadata_publication = dict(
                                enrollment_sha256=hashlib.sha256(
                                    _json_payload(owned_snapshot)
                                ).hexdigest(),
                                operations={
                                    payload[
                                        "generic_operation_id"
                                    ]: "inventory_devices",
                                    payload[
                                        "inventory_operation_id"
                                    ]: "native_camera_inventory",
                                    payload[
                                        "identity_operation_id"
                                    ]: "native_camera_identity",
                                    operation_id: "native_camera_review",
                                },
                            )
                    self._changed(state=True)
                if (
                    metadata_token is not None
                    and self._operations[operation_id]["status"] == "SUCCEEDED"
                    and self._operations[operation_id].get("completion_log_persisted")
                    is True
                    and not cancel.is_set()
                    and not self._source_changed
                    and original_result == result
                ):
                    if action_id == "inventory_devices":
                        document = result["steps"][0]["report"]
                    else:
                        phase_native_snapshot = self._native_camera.export_snapshot()
                        document = phase_native_snapshot[
                            (
                                "inventory_packet"
                                if action_id == "native_camera_inventory"
                                else "identity_packet"
                            )
                        ]
                    self._usb_identity.acquisition_published(
                        metadata_token,
                        finished_at_ns=metadata_finished_at_ns,
                        document=document,
                        result_sha256=self._operations[operation_id]["result_sha256"],
                    )
        except Exception as exc:
            with self._lock:
                if action_id in _HELPER_ACTIONS or isinstance(
                    exc, CameraHelperInspectionError
                ):
                    self._revoke_helper(
                        getattr(exc, "code", "HELPER_ACTION_FAILED"),
                        preserve_inspection=action_id == "camera_helper_review",
                    )
                    self._changed(state=True)
                if ACTION_BY_ID[action_id].worker == "commissioning":
                    self._clear_camera_preview("REHEARSAL_HELD_NO_CURRENT_PREVIEW")
                    self._published_noncontact_sha256 = None
                failure = native_retained_result or {"physical_authority": False}
                if ACTION_BY_ID[action_id].worker in {
                    "physical_camera_setup",
                    "physical_source_qualification",
                    "physical_static_camera_onboarding",
                    "physical_received_camera",
                    "physical_camera_identity_records",
                    "physical_intake_evidence",
                    "physical_usb_identity",
                }:
                    self._usb_identity.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_usb_identity":
                    self._physical_camera_setup.invalidate()
                    self._camera_identity_records.invalidate()
                    self._received_camera.invalidate()
                    self._static_camera_onboarding.invalidate()
                    self._source_qualification.invalidate()
                    self._physical_intake_evidence.invalidate()
                    failure["retained_usb_identity"] = (
                        self._usb_identity_export_pointer()
                    )
                if action_id in _NATIVE_ARM_ACTIONS:
                    self._invalidate_native_arm("ARM_METADATA_ACTION_FAILED")
                if ACTION_BY_ID[action_id].worker == "physical_camera_runtime":
                    self._physical_camera.invalidate_runtime()
                    failure["retained_camera_runtime"] = (
                        self._physical_camera.retained_runtime_diagnostics()
                    )
                if ACTION_BY_ID[action_id].worker == "commissioning":
                    noncontact = self._commissioning.retained_noncontact_diagnostics()
                    if noncontact is not None:
                        failure["retained_noncontact_receipt"] = noncontact
                if ACTION_BY_ID[action_id].worker == "physical_camera_setup":
                    self._physical_camera_setup.invalidate()
                    self._physical_intake_evidence.invalidate()
                    self._source_qualification.invalidate()
                    self._static_camera_onboarding.invalidate()
                    self._received_camera.invalidate()
                    failure["retained_camera_setup"] = (
                        self._physical_camera_setup.retained_diagnostics()
                    )
                if ACTION_BY_ID[action_id].worker == "physical_source_qualification":
                    self._physical_camera_setup.invalidate()
                    self._source_qualification.invalidate()
                    self._physical_intake_evidence.invalidate()
                    self._static_camera_onboarding.invalidate()
                    self._received_camera.invalidate()
                    failure["retained_source_reassessment"] = (
                        self._source_reassessment_view()
                    )
                if (
                    ACTION_BY_ID[action_id].worker
                    == "physical_static_camera_onboarding"
                ):
                    self._physical_camera_setup.invalidate()
                    self._static_camera_onboarding.invalidate()
                    self._received_camera.invalidate()
                    self._source_qualification.invalidate()
                    self._physical_intake_evidence.invalidate()
                    failure["retained_static_camera_onboarding"] = (
                        self._static_camera_onboarding_view()
                    )
                if ACTION_BY_ID[action_id].worker == "physical_received_camera":
                    self._physical_camera_setup.invalidate()
                    self._received_camera.invalidate()
                    self._static_camera_onboarding.invalidate()
                    self._source_qualification.invalidate()
                    self._physical_intake_evidence.invalidate()
                    failure["retained_received_camera"] = (
                        self._received_camera_export_pointer()
                    )
                if ACTION_BY_ID[action_id].worker in {
                    "physical_camera_setup",
                    "physical_source_qualification",
                    "physical_static_camera_onboarding",
                    "physical_received_camera",
                }:
                    self._camera_identity_records.invalidate()
                if ACTION_BY_ID[action_id].worker == "physical_camera_identity_records":
                    self._physical_camera_setup.invalidate()
                    self._camera_identity_records.invalidate()
                    self._received_camera.invalidate()
                    self._static_camera_onboarding.invalidate()
                    self._source_qualification.invalidate()
                    self._physical_intake_evidence.invalidate()
                    failure["retained_camera_identity"] = (
                        self._camera_identity_export_pointer()
                    )
                if ACTION_BY_ID[action_id].worker == "physical_intake_evidence":
                    self._physical_intake_evidence.invalidate()
                    if action_id != "physical_intake_files_discover":
                        self._physical_camera_setup.invalidate()
                    # Full immutable subjects survive in the dedicated export;
                    # a nested error card carries bounded historical metadata.
                    failure["retained_intake_evidence"] = (
                        self._physical_intake_evidence_view()
                    )
                if ACTION_BY_ID[action_id].worker in {
                    "physical_camera",
                    "physical_camera_configuration",
                }:
                    self._physical_camera.invalidate()
                    failure["retained_camera_intent"] = (
                        self._physical_camera.retained_intent()
                    )
                if ACTION_BY_ID[action_id].worker == "physical_preflight":
                    failure["source_preflight"] = self._source_preflight.view()
                    failure["retained_source_evidence"] = (
                        self._source_preflight.retained_report()
                    )
                if action_id == "rehearsal_owned_arm_feedback_campaign":
                    # Retention can complete before a later Stop, source check
                    # or stage publication fails. Export cached diagnostics as
                    # historical data, never as current accepted evidence.
                    failure["retained_feedback_diagnostics"] = (
                        self._commissioning.retained_feedback_diagnostics()
                    )
                if action_id == "rehearsal_owned_camera_campaign":
                    failure["retained_camera_diagnostics"] = (
                        self._commissioning.retained_camera_diagnostics()
                    )
                if native_retained_result is not None:
                    failure["status"] = "FAILED"
                    failure["retention_meaning"] = (
                        "RETURNED_SOURCE_REPORT_RETAINED_PUBLICATION_REJECTED"
                        if ACTION_BY_ID[action_id].worker == "physical_preflight"
                        else (
                            "RETURNED_CAMERA_INTENT_RETAINED_PUBLICATION_REJECTED"
                            if ACTION_BY_ID[action_id].worker
                            in {
                                "physical_camera",
                                "physical_camera_setup",
                                "physical_camera_runtime",
                            }
                            else (
                                "RETURNED_INTAKE_DRAFT_RETAINED_PUBLICATION_REJECTED"
                                if ACTION_BY_ID[action_id].worker == "physical_intake"
                                else "RETURNED_METADATA_RETAINED_PUBLICATION_REJECTED"
                            )
                        )
                    )
                    failure["source_at_dispatch_sha256"] = self.source_sha256
                    failure["source_after_lookup_sha256"] = self._observed_source_sha256
                failure.update(
                    {
                        "code": getattr(exc, "code", "DIAGNOSTIC_FAILED"),
                        "message": str(exc)[:1500],
                        "error_type": type(exc).__name__,
                        "physical_authority": False,
                    }
                )
                if isinstance(exc, CameraHelperInspectionError):
                    failure["inspection_report"] = exc.inspection_report
                if (
                    type(exc) is PhysicalCameraDispatchError
                    and action_id
                    in {
                        "physical_camera_probe",
                        "physical_camera_capture",
                        CONFIGURATION_CAPTURE,
                    }
                    and exc.diagnostic is not None
                ):
                    # Small original-readback summary only. Full pipe/admission
                    # records remain in the dedicated exact-attempt export.
                    failure["camera_attempt_failure"] = exc.diagnostic
                terminal_status = (
                    "CANCELLED"
                    if getattr(exc, "code", None)
                    in {
                        "HELPER_CANCELLED",
                        "PREFLIGHT_CANCELLED",
                        "INTAKE_CANCELLED",
                        "INTAKE_INTERRUPTED",
                        "INTAKE_INBOX_CANCELLED",
                        "CAMERA_RUNTIME_CANCELLED",
                        "RUNTIME_INSPECTION_CANCELLED",
                    }
                    else "FAILED"
                )
                if ACTION_BY_ID[action_id].worker == "physical_camera_runtime":
                    if getattr(exc, "code", None) == "CANCELLED":
                        terminal_status = "CANCELLED"
                    elif getattr(exc, "code", None) == "TIMED_OUT":
                        terminal_status = "TIMED_OUT"
                self._finish(operation_id, terminal_status, failure)
                if action_id in _NATIVE_ARM_ACTIONS:
                    # _finish has already sanitized this failure. A codec or
                    # source failure must not discard its bounded raw snapshot.
                    retained = self._full_results.get(operation_id)
                    if retained is not None:
                        self._native_arm_retained = deepcopy(retained)

    @staticmethod
    def _validate_usb_identity_result(action_id: str, result: Any) -> None:
        """Parent-only effectful result; the diagnostic child keeps its zero-I/O schema."""
        keys = {
            "schema",
            "action_id",
            "status",
            "steps",
            "device_open_count",
            "serial_write_count",
            "power_event_count",
            "motion_command_count",
            "contact_command_count",
            "counter_coverage",
            "physical_authority",
            "hardware_qualified",
        }
        valid = (
            type(result) is dict
            and set(result) == keys
            and result["schema"] == "rocell.wizard_usb_identity_action_result.v1"
            and result["action_id"] == action_id
            and result["status"] == "SUCCEEDED"
            and result["physical_authority"] is False
            and result["hardware_qualified"] is False
            and all(
                type(result[k]) is int and result[k] == 0
                for k in (
                    "serial_write_count",
                    "power_event_count",
                    "motion_command_count",
                    "contact_command_count",
                )
            )
            and type(result["steps"]) is list
            and len(result["steps"]) == 1
        )
        if not valid:
            raise WizardError(
                "INVALID_USB_ACTION_RESULT",
                "USB service returned an unsupported result envelope.",
            )
        step = result["steps"][0]
        if (
            type(step) is not dict
            or set(step) != {"name", "exit_code", "report"}
            or step["name"] != action_id
            or type(step["exit_code"]) is not int
            or step["exit_code"] != 0
            or type(step["report"]) is not dict
            or step["report"].get("pending_completion_log") is not True
        ):
            raise WizardError(
                "INVALID_USB_ACTION_RESULT",
                "Expected one original pending USB action report.",
            )
        opens, coverage = result["device_open_count"], result["counter_coverage"]
        if action_id in {
            "physical_usb_complete_assess",
            "physical_usb_complete_review",
        }:
            from .physical_usb_complete_projection import complete_projection_valid

            report = step["report"]
            projection = report.get("qualification")
            if (
                report.get("usb_query_attempted") is not False
                or report.get("execution") is not None
                or type(projection) is not dict
                or projection.get("schema") != "rocell.wizard_usb_qualification.v6"
                or projection.get("publication", {}).get("status") != "PENDING"
                or any(
                    projection.get(key) is not False
                    for key in (
                        "physical_authority",
                        "hardware_qualified",
                        "camera_capture_authorized",
                        "arm_access_authorized",
                    )
                )
                or not complete_projection_valid(projection)
            ):
                raise WizardError(
                    "INVALID_USB_ACTION_RESULT",
                    "Expected a withheld, file-only final identity review publication.",
                )
        no_query = (
            action_id == "physical_usb_qualification_collect"
            and step["report"].get("usb_query_attempted") is False
        )
        if no_query:
            boot = step["report"].get("host_boot")
            valid = (
                type(opens) is int
                and opens == 0
                and coverage == "NO_DEVICE_IO"
                and step["report"].get("execution") is None
                and type(boot) is dict
                and boot.get("original_state") in {"BOOT_HELD", "BOOT_UNCERTAIN"}
                and boot.get("device_io_performed") is False
            )
        elif action_id not in {
            "physical_usb_identity_collect",
            "physical_usb_qualification_collect",
            "physical_usb_reconnect_collect",
            "physical_usb_reboot_collect",
        }:
            valid = type(opens) is int and opens == 0 and coverage == "NO_DEVICE_IO"
            if action_id.startswith(
                ("physical_usb_reconnect_", "physical_usb_reboot_")
            ):
                valid = (
                    valid
                    and step["report"].get("usb_query_attempted") is False
                    and step["report"].get("execution") is None
                )
                if action_id in {
                    "physical_usb_reconnect_boot_collect",
                    "physical_usb_reboot_boot_collect",
                }:
                    boot = step["report"].get("host_boot")
                    valid = (
                        valid
                        and type(boot) is dict
                        and boot.get("schema")
                        == (
                            "rocell.wizard_usb_reboot_boot_summary.v1"
                            if action_id == "physical_usb_reboot_boot_collect"
                            else "rocell.wizard_usb_reconnect_boot_summary.v1"
                        )
                        and boot.get("original_state")
                        in {"BOOT_RETAINED", "BOOT_HELD", "BOOT_UNCERTAIN"}
                        and boot.get("device_io_performed") is False
                    )
                    if action_id == "physical_usb_reboot_boot_collect":
                        valid = (
                            valid
                            and isinstance(boot, dict)
                            and boot.get("restart_status")
                            in {
                                "BOOT_RETAINED",
                                "BOOT_HELD",
                                "BOOT_UNCERTAIN",
                                "NOT_EVALUATED",
                            }
                            and boot.get("physical_authority") is False
                            and boot.get("hardware_qualified") is False
                        )
        else:
            execution = step["report"].get("execution")
            valid = (
                type(execution) is dict
                and execution.get("schema")
                == "rocell.owned_usb_identity_run_summary.v1"
                and execution.get("physical_authority") is False
                and execution.get("hardware_qualified") is False
                and coverage == execution.get("counter_coverage")
            )
            if action_id in {
                "physical_usb_qualification_collect",
                "physical_usb_reconnect_collect",
                "physical_usb_reboot_collect",
            }:
                valid = valid and step["report"].get("usb_query_attempted") is True
            if valid:
                assert isinstance(execution, dict)
                counts = execution.get("actual_counts")
                if coverage == "NOT_REPORTED":
                    valid = (
                        opens is None
                        and counts is None
                        and execution.get("no_attempt") is False
                    )
                elif coverage in {"NATIVE_RECEIPT", "NO_PROCESS_CREATED"}:
                    valid = (
                        type(opens) is int
                        and 0 <= opens <= 32
                        and type(counts) is dict
                        and type(counts.get("hub_open_attempts")) is int
                        and opens == counts["hub_open_attempts"]
                    )
                    if coverage == "NO_PROCESS_CREATED":
                        valid = (
                            valid
                            and execution.get("no_attempt") is True
                            and isinstance(counts, dict)
                            and all(type(n) is int and n == 0 for n in counts.values())
                        )
                    else:
                        valid = valid and execution.get("no_attempt") is False
                else:
                    valid = False
        if not valid:
            raise WizardError(
                "USB_ACTION_COUNTER_MISMATCH",
                "USB effect counts are absent or inconsistent with the retained execution summary; unknown is not zero.",
            )

    @staticmethod
    def _validate_usb_absence_result(action_id: str, result: Any) -> None:
        """Purpose-specific parent result; CM calls are not descriptor hub opens."""
        keys = {
            "schema",
            "action_id",
            "status",
            "steps",
            "device_open_count",
            "presence_api_call_count",
            "presence_query_attempted",
            "counter_coverage",
            "serial_write_count",
            "power_event_count",
            "motion_command_count",
            "contact_command_count",
            "physical_authority",
            "hardware_qualified",
        }
        valid = (
            type(result) is dict
            and set(result) == keys
            and result["schema"] == "rocell.wizard_usb_absence_action_result.v1"
            and result["action_id"] == action_id
            and result["status"] == "SUCCEEDED"
            and result["physical_authority"] is False
            and result["hardware_qualified"] is False
            and type(result["presence_query_attempted"]) is bool
            and all(
                type(result[k]) is int and result[k] == 0
                for k in (
                    "serial_write_count",
                    "power_event_count",
                    "motion_command_count",
                    "contact_command_count",
                )
            )
            and type(result["steps"]) is list
            and len(result["steps"]) == 1
        )
        step = result["steps"][0] if valid else None
        valid = (
            valid
            and type(step) is dict
            and set(step) == {"name", "exit_code", "report"}
            and step["name"] == action_id
            and type(step["exit_code"]) is int
            and step["exit_code"] == 0
            and type(step["report"]) is dict
            and step["report"].get("pending_completion_log") is True
            and all(
                step["report"].get(k) is False
                for k in (
                    "physical_authority",
                    "hardware_qualified",
                    "camera_capture_authorized",
                    "arm_access_authorized",
                )
            )
        )
        if not valid:
            raise WizardError(
                "INVALID_USB_ABSENCE_RESULT",
                "Expected an exact original pending absence action result.",
            )
        assert isinstance(step, dict)
        opens, calls, coverage = (
            result["device_open_count"],
            result["presence_api_call_count"],
            result["counter_coverage"],
        )
        if action_id != "physical_usb_absence_collect":
            valid = (
                result["presence_query_attempted"] is False
                and coverage == "NO_DEVICE_IO"
                and type(opens) is int
                and opens == 0
                and type(calls) is int
                and calls == 0
            )
        else:
            execution = step["report"].get("execution")
            valid = result["presence_query_attempted"] is True
            if execution is None:
                valid = (
                    valid
                    and opens is None
                    and calls is None
                    and coverage == "NOT_REPORTED"
                )
            else:
                valid = (
                    valid
                    and type(execution) is dict
                    and execution.get("schema")
                    == "rocell.owned_usb_presence_run_summary.v1"
                    and execution.get("physical_authority") is False
                    and execution.get("hardware_qualified") is False
                    and coverage == execution.get("counter_coverage")
                )
                counts = execution.get("actual_counts") if valid else None
                if coverage == "NOT_REPORTED":
                    valid = (
                        valid
                        and counts is None
                        and opens is None
                        and calls is None
                        and execution.get("no_attempt") is False
                    )
                elif coverage in {"NATIVE_RECEIPT", "NO_PROCESS_CREATED"}:
                    valid = (
                        valid
                        and type(counts) is dict
                        and set(counts)
                        == {
                            "api_calls",
                            "device_handle_opens",
                            "configuration_writes",
                            "frames",
                        }
                        and type(calls) is int
                        and type(counts["api_calls"]) is int
                        and 0 <= calls <= 4
                        and calls == counts["api_calls"]
                        and type(opens) is int
                        and opens == 0
                        and opens == counts["device_handle_opens"]
                        and all(
                            type(counts[k]) is int and counts[k] == 0
                            for k in (
                                "device_handle_opens",
                                "configuration_writes",
                                "frames",
                            )
                        )
                    )
                    if coverage == "NO_PROCESS_CREATED":
                        valid = (
                            valid and calls == 0 and execution.get("no_attempt") is True
                        )
                    else:
                        valid = valid and execution.get("no_attempt") is False
                else:
                    valid = False
        if not valid:
            raise WizardError(
                "USB_ABSENCE_COUNTER_MISMATCH",
                "Presence API/device counts must match retained originals; unknown is not zero.",
            )

    def _validated_result(self, action_id: str, result: Any) -> dict[str, Any]:
        if type(result) is not dict or result.get("physical_authority") is not False:
            raise WizardError(
                "INVALID_WORKER_RESULT",
                "Worker result is malformed or claims physical authority.",
            )
        if action_id == 'run_positional_campaign':
            if self._positional_campaign_publication is None or result != self._positional_campaign_publication:
                raise WizardError('INVALID_CAMPAIGN_RESULT','Result is not the service-owned campaign outcome.')
        elif action_id in ('run_wifi_roll_sweep_low_trial','run_wifi_roll_sweep_center_trial','run_wifi_roll_sweep_high_trial','run_wifi_roll_trial','run_wifi_roll_negative_trial','run_wifi_roll_low_trial','run_wifi_roll_high_trial','run_wifi_roll_zero_trial','run_wifi_roll_center_up_trial','run_wifi_roll_center_down_trial','run_wifi_roll_corrected_up_trial','run_wifi_roll_corrected_down_trial','run_wifi_roll_probe_low_trial','run_wifi_roll_probe_high_trial','run_wifi_roll_lookup_trial','run_wifi_roll_adjacent_trial','run_wifi_roll_adjacent_low_trial','run_wifi_roll_adjacent_high_trial','run_wifi_roll_adjacent_lookup_trial'):
            if result != getattr(self, '_wifi_roll_publication', None):
                raise WizardError('INVALID_WIFI_ROLL_RESULT','Result is not the service-owned live trial outcome.')
        elif action_id == 'run_micro_commissioning':
            if result != getattr(self, '_micro_commissioning_publication', None):
                raise WizardError('INVALID_MICRO_RESULT','Result is not the service-owned commissioning outcome.')
        elif action_id == 'rehearse_static_task':
            if result != getattr(self, '_static_task_publication', None):
                raise WizardError('INVALID_SIMULATION_RESULT', 'Static task result is not service-owned.')
        elif action_id == 'simulate_micro_correction':
            if result != getattr(self, '_micro_simulation_publication', None):
                raise WizardError('INVALID_SIMULATION_RESULT','Result is not the service-owned micro simulation outcome.')
        elif action_id == 'simulate_discrete_transaction':
            if result != getattr(self, '_discrete_simulation_publication', None):
                raise WizardError('INVALID_SIMULATION_RESULT','Result is not the service-owned simulation outcome.')
        elif action_id == 'run_held_pair':
            if result != getattr(self, '_held_pair_publication', None):
                raise WizardError('INVALID_PAIR_RESULT','Result is not the service-owned pair trial.')
        elif action_id == 'review_observed_pair':
            if result != getattr(self, '_pair_review_publication', None):
                raise WizardError('INVALID_REVIEW_RESULT','Result is not the service-owned pair review.')
        elif action_id in ('review_collected_hold', 'review_observed_hold'):
            if result != getattr(self, '_hold_review_publication', None):
                raise WizardError('INVALID_REVIEW_RESULT','Result is not the service-owned hold review.')
        elif action_id in ('review_planned_servo_run','review_started_servo_run','review_startup_servo_run','review_started_startup_run'):
            if result != getattr(self, '_planned_servo_review_publication', None):
                raise WizardError('INVALID_REVIEW_RESULT','Result is not the service-owned planned-run review.')
        elif action_id == 'simulate_servo_diagnostics':
            if result != getattr(self, '_servo_diagnostic_publication', None):
                raise WizardError('INVALID_SIMULATION_RESULT','Result is not the service-owned diagnostic rehearsal.')
        elif action_id in ('read_arm_wifi_feedback','sample_arm_wifi_feedback','observe_arm_wifi_feedback','observe_arm_wifi_feedback_fast','observe_arm_wifi_feedback_spaced','observe_arm_wifi_feedback_intermediate','observe_arm_wifi_bounded'):
            if result != getattr(self, '_wifi_feedback_publication', None):
                raise WizardError('INVALID_WIFI_RESULT','Result is not the service-owned Wi-Fi observation.')
        elif action_id == 'run_wrist_correction':
            if result!=self._wrist_correction_publication or self._wrist_correction_outcome is None:
                raise WizardError('INVALID_CORRECTION_RESULT','Result is not the service-owned correction outcome.')
        elif action_id == 'run_observational_movement':
            if result != self._observational_publication or self._observational_outcome is None:
                raise WizardError('INVALID_OBSERVATIONAL_RESULT','Result is not the service-owned observational outcome.')
        elif action_id == 'run_first_motion':
            if result != self._first_motion_publication or self._first_motion_outcome is None:
                raise WizardError('INVALID_FIRST_MOTION_RESULT','Result is not the service-owned commissioning outcome.')
        elif action_id == 'run_endpoint_trial':
            if result!=self._endpoint_publication or self._endpoint_outcome is None:
                raise WizardError('INVALID_ENDPOINT_RESULT','Endpoint result is not the service-owned observation.')
        elif action_id in _POWERED_ACTIONS:
            if (
                result != self._powered_feedback_publication
                or self._powered_feedback_outcome is None
            ):
                raise WizardError(
                    "INVALID_POWERED_RESULT",
                    "Powered result is not the service-owned observation.",
                )
        elif action_id == "run_passive_arm_connection":
            if (
                result != self._passive_arm_publication
                or self._passive_arm_outcome is None
            ):
                raise WizardError(
                    "INVALID_PASSIVE_RESULT",
                    "Passive result is not the service-owned observation.",
                )
        elif action_id in {
            "physical_usb_absence_begin",
            "physical_usb_absence_boot_review",
            "physical_usb_absence_boot_collect",
            "physical_usb_absence_runtime_review",
            "physical_usb_absence_collect",
        }:
            self._validate_usb_absence_result(action_id, result)
        elif action_id in {"physical_camera_probe", CONFIGURATION_CAPTURE}:
            # Effectful parent results do not use the incapable subprocess's
            # zero-I/O schema. Match data already backed by original M1 readback.
            self._physical_camera.validate_observation_publication(action_id, result)
        elif ACTION_BY_ID[action_id].worker == "physical_usb_identity":
            self._validate_usb_identity_result(action_id, result)
        elif result.get("schema") == "rocell.wizard_diagnostic_completion.v1":
            required = {
                "schema",
                "action_id",
                "status",
                "message",
                "elapsed_s",
                "output_limit_exceeded",
                "physical_authority",
            }
            if (
                set(result) != required
                or result["action_id"] != action_id
                or result["status"] not in {"CANCELLED", "TIMED_OUT", "FAILED"}
                or type(result["message"]) is not str
                or not 1 <= len(result["message"]) <= 2000
                or type(result["elapsed_s"]) not in {int, float}
                or not math.isfinite(result["elapsed_s"])
                or result["elapsed_s"] < 0
                or type(result["output_limit_exceeded"]) is not bool
                or (
                    result["status"] == "FAILED" and not result["output_limit_exceeded"]
                )
            ):
                raise WizardError(
                    "INVALID_WORKER_RESULT",
                    "Local diagnostic cancellation/timeout envelope is invalid.",
                )
        else:
            # The process runner and service share one strict worker schema.
            # Only these known transport observations are added after parsing.
            returncode = result.get("worker_exit_code", 0)
            elapsed = result.get("elapsed_s", 0)
            stderr = result.get("worker_stderr", "")
            if (
                type(returncode) is not int
                or type(elapsed) not in {int, float}
                or not math.isfinite(elapsed)
                or elapsed < 0
                or type(stderr) is not str
                or len(stderr) > 128 * 1024
            ):
                raise WizardError(
                    "INVALID_WORKER_RESULT",
                    "Diagnostic transport observations are malformed.",
                )
            worker_result = {
                key: value
                for key, value in result.items()
                if key not in {"worker_exit_code", "elapsed_s", "worker_stderr"}
            }
            validate_diagnostic_worker_result(
                worker_result, action_id=action_id, returncode=returncode
            )
        try:
            return sanitize_diagnostic_record(result, maximum_bytes=MAX_RESULT_BYTES)
        except WizardDiagnosticExportError as exc:
            raise WizardError(
                "RESULT_RETENTION_LIMIT",
                "The full worker result could not be retained within the JSON/nesting/string/1 MiB budgets; no full-result export or readiness claim was created.",
            ) from exc

    def _finish(self, operation_id: str, status: str, result: dict[str, Any]) -> None:
        operation = self._operations[operation_id]
        try:
            clean = sanitize_diagnostic_record(result, maximum_bytes=MAX_RESULT_BYTES)
        except WizardDiagnosticExportError:
            clean = {
                "code": "RESULT_RETENTION_LIMIT",
                "message": "Full diagnostic result exceeded retention bounds and was not retained.",
                "physical_authority": False,
            }
            status = "FAILED"
        operation.update(
            {
                "status": status,
                "finished_at": _now_text(),
                "result": clean,
                "result_retention": "FULL_JSON_RETAINED",
                "result_sha256": hashlib.sha256(_json_payload(clean)).hexdigest(),
            }
        )
        for ticket in self._tickets.values():
            if ticket.receipt and ticket.receipt["operation_id"] == operation_id:
                ticket.receipt["status"] = status
        operation["message"] = clean.get("message") or (
            "Diagnostic completed; physical hardware remains unqualified."
            if status == "SUCCEEDED"
            else "Diagnostic did not complete successfully. Inspect details, record investigation and export logs before retrying explicitly."
        )
        if status in {"FAILED", "TIMED_OUT"}:
            operation["error"] = {
                "code": clean.get("code", "DIAGNOSTIC_FAILED"),
                "message": operation["message"],
                "remediation": "Inspect the structured steps and worker error; export logs, resolve the cause, and prepare a new explicit diagnostic. Do not bypass physical holds.",
            }
            if operation["action_id"] == "physical_camera_probe":
                operation["error"][
                    "remediation"
                ] = "Use Export camera probe attempt to preserve original admission/native readback and completion. Inspect the same store; do not replay or replace an uncertain probe. Arm access remains held."
            if operation["action_id"] == CONFIGURATION_CAPTURE:
                operation["error"][
                    "remediation"
                ] = "Export this settings-capture attempt with its original admission, settings/readback, cleanup and logs. Inspect uncertain outcomes without replay; arm access remains held."
        self._full_results[operation_id] = clean
        if operation["action_id"] == "record_passive_arm_setup":
            self._passive_arm_setup = deepcopy(clean)
        if operation["action_id"] == "inspect_passive_arm_history":
            steps = clean.get("steps", [])
            report = steps[0].get("report", {}) if steps else {}
            self._passive_arm_history = (
                deepcopy(
                    {
                        key: value
                        for key, value in report.items()
                        if key not in {"raw_stdout_base64", "raw_stderr_base64"}
                    }
                )
                if report
                else {
                    "schema": "rocell.passive_arm_history_view.v1",
                    "pair_status": "UNVERIFIED_NO_REPLAY",
                    "historical_only": True,
                    "physical_authority": False,
                    "connected": False,
                    "replay_allowed": False,
                    "message": "Historical files could not be verified. Inspect this operation's error and export logs; no replay.",
                }
            )
        if operation["action_id"] == "rehearse_passive_arm_connection":
            self._passive_arm_retained = {
                "operation_id": operation_id,
                "source_sha256": self.source_sha256,
                "result": deepcopy(clean),
                "physical_authority": False,
            }
            # Keep the in-memory raw result even if publication fails. A failed
            # persistence attempt is never converted into a successful receipt.
            from .passive_arm_diagnostic_checkpoint import publish

            try:
                self._passive_arm_checkpoint = publish(
                    self._log.root, self.session_id, self._passive_arm_retained
                )
            except Exception as exc:
                self._passive_arm_checkpoint = {
                    "status": "PERSISTENCE_UNCONFIRMED",
                    "error_type": type(exc).__name__,
                    "physical_authority": False,
                }
                operation["action_outcome_before_checkpoint_failure"] = status
                status = "FAILED"
                operation["status"] = status
                operation["message"] = (
                    "Passive result persistence is unconfirmed; export retained diagnostics. Do not replay."
                )
                operation["error"] = {
                    "code": "PASSIVE_CHECKPOINT_UNCONFIRMED",
                    "message": operation["message"],
                }
                for ticket in self._tickets.values():
                    if (
                        ticket.receipt
                        and ticket.receipt["operation_id"] == operation_id
                    ):
                        ticket.receipt["status"] = status
        while len(self._full_results) > MAX_FULL_RESULTS:
            omitted_id, _ = self._full_results.popitem(last=False)
            if omitted_id in self._operations:
                self._operations[omitted_id]["result"] = None
                self._operations[omitted_id][
                    "result_retention"
                ] = "OMITTED_OLDER_THAN_LAST_EIGHT_RESULTS"
        if self._running == operation_id:
            self._running = None
            self._cancel = None
        logged = self._append_event(
            "ACTION_FINISHED",
            {
                "operation_id": operation_id,
                "action_id": operation["action_id"],
                "status": status,
                "result_sha256": operation["result_sha256"],
                "result_retention": operation["result_retention"],
            },
        )
        operation["completion_log_persisted"] = logged
        if not logged:
            # Preserve the underlying test/export result, but do not present a
            # successfully persisted diagnostic completion that does not exist.
            operation["action_outcome_before_log_failure"] = status
            operation["status"] = "FAILED"
            operation["result_retention"] = "FULL_JSON_RETAINED_COMPLETION_LOG_FAILED"
            operation["message"] = (
                "The action returned an outcome, but its completion could not be logged. "
                "Inspect the retained result/any verified export receipt and review the diagnostic log hold."
            )
            operation["error"] = {
                "code": "DIAGNOSTIC_LOG_FAILED",
                "message": operation["message"],
                "remediation": "Export available in-memory diagnostics and resolve the log-folder issue; do not assume the action was not performed or automatically replay it.",
            }
            for ticket in self._tickets.values():
                if ticket.receipt and ticket.receipt["operation_id"] == operation_id:
                    ticket.receipt["status"] = operation["status"]
        if (
            ACTION_BY_ID[operation["action_id"]].worker == "commissioning"
            and operation["status"] != "SUCCEEDED"
        ):
            self._clear_camera_preview("REHEARSAL_HELD_NO_CURRENT_PREVIEW")
        summary = self._summary(operation)
        self._latest_by_section[ACTION_BY_ID[operation["action_id"]].section] = summary
        if operation["action_id"] in {
            "camera_rehearsal",
            "camera_stack",
            "prebuild_vision_checks",
        }:
            self._camera["last_test"] = summary
        if operation["action_id"] in {"arm_rehearsal", "inventory_devices"}:
            self._arm["last_test"] = summary
        if operation["action_id"] == "physical_camera_probe":
            # Pin one bounded completion independently of rotating notes/results.
            self._probe_attempt_completion = deepcopy(operation)
        if operation["action_id"] == CONFIGURATION_CAPTURE:
            self._configuration_wizard.record_completion(operation)
        if operation["action_id"] == OPERATING_PROPOSAL:
            self._operating_proposal.record_completion(operation)
        if operation["action_id"] == OPERATING_ASSESSMENT:
            self._operating_assessment.record_completion(operation)
        if operation["action_id"] == OPERATING_SUBMISSION:
            self._operating_submission.record_completion(operation)
        self._changed(state=True)

    @staticmethod
    def _summary(operation: dict[str, Any]) -> dict[str, Any]:
        summary = {key: value for key, value in operation.items() if key != "result"}
        result = operation.get("result") or {}
        steps = result.get("steps", [])
        if isinstance(steps, list):
            summary["steps"] = [
                {
                    "name": step.get("name"),
                    "exit_code": step.get("exit_code"),
                    "report_status": (
                        step.get("report", {}).get("status")
                        if type(step.get("report")) is dict
                        else None
                    ),
                }
                for step in steps[:16]
                if type(step) is dict
            ]
        return deepcopy(summary)

    def operation(self, operation_id: str) -> dict[str, Any]:
        with self._lock:
            if type(operation_id) is not str or operation_id not in self._operations:
                raise WizardError(
                    "UNKNOWN_OPERATION",
                    "Operation is unavailable in this launch's bounded history.",
                )
            return deepcopy(self._operations[operation_id])

    def image(self, image_id: str) -> tuple[bytes, str]:
        with self._lock:
            if type(image_id) is not str or image_id not in self._images:
                raise WizardError(
                    "UNKNOWN_IMAGE",
                    "No retained nominal schematic has this ID; no camera was opened.",
                )
            return self._images[image_id], "image/png"

    def _publish_physical_camera_observation(
        self,
        operation_id: str,
        result: dict[str, Any],
        *,
        cancellation: threading.Event,
    ) -> None:
        """Logged data handoff for the admitted probe or bounded settings frame.

        This is intentionally not an HTTP endpoint and cannot dispatch hardware.
        Exact result/log ownership is required. The browser receives no evidence
        upload, runtime-release switch, automatic capture or arm authorization.
        """
        from .physical_camera_selection import selection_from_enrollment

        with self._lock:
            operation = self._operations.get(operation_id)
            action_id = None if operation is None else operation["action_id"]
            try:
                if (
                    action_id
                    not in {
                        "physical_camera_probe",
                        "physical_camera_capture",
                        CONFIGURATION_CAPTURE,
                    }
                    or operation is None
                    or operation["status"] != "SUCCEEDED"
                    or operation.get("completion_log_persisted") is not True
                    or operation.get("result_retention") != "FULL_JSON_RETAINED"
                    or self._full_results.get(operation_id) != result
                    or operation.get("result_sha256")
                    != hashlib.sha256(_json_payload(result)).hexdigest()
                    or self._closed
                    or self._log_error
                    or cancellation.is_set()
                ):
                    raise WizardError(
                        "CAMERA_OBSERVATION_NOT_LOGGED",
                        "Current exact result and completion log required before image publication.",
                    )
                self._recheck_source(action_id)
                selected = selection_from_enrollment(
                    self._native_camera,
                    source_sha256=self.source_sha256,
                    launch_session_id=self.session_id,
                )
                if (
                    selected.safe_summary()
                    != self._physical_camera.view()["reviewed_endpoint"]
                ):
                    raise WizardError(
                        "CAMERA_OBSERVATION_IDENTITY",
                        "The current reviewed endpoint differs from the captured identity.",
                    )
                self._physical_camera.validate_observation_publication(
                    action_id, result
                )
                if cancellation.is_set():
                    raise WizardError(
                        "CAMERA_OBSERVATION_CANCELLED",
                        "Stop arrived before retained image publication.",
                    )
                self._physical_camera.publish_retained_observation(operation_id)
                image_id = "image-" + uuid.uuid4().hex
                png = self._physical_camera.cache_published_preview(image_id)
                self._recheck_source(action_id)
                if cancellation.is_set():
                    raise WizardError(
                        "CAMERA_OBSERVATION_CANCELLED",
                        "Stop arrived during final image validation.",
                    )
                if png is not None:
                    frame = self._physical_camera.view()["last_frame"]
                    self._images = {image_id: png}
                    self._camera.update(
                        image_id=image_id,
                        image_provenance=frame["provenance"],
                        image_capture=deepcopy(frame),
                    )
                self._changed(state=True)
            except Exception:
                self._clear_camera_preview("PHYSICAL_CAMERA_PUBLICATION_WITHDRAWN")
                self._physical_camera.invalidate()
                raise

    def _export(self) -> dict[str, Any]:
        attachments: dict[str, bytes] = {}
        omitted: list[dict[str, Any]] = []
        total = 0
        dedicated = []
        if self._first_motion_qualification_receipts:
            from .first_motion_qualification_decision import export_qualification_decisions
            payload = export_qualification_decisions(self._log.root, tuple(self._first_motion_qualification_receipts))
            attachments['first-motion-qualification.json'] = payload
            dedicated.append('first-motion-qualification.json')
            total += len(payload)
        if self._observational_sources:
            from .observational_onboarding_sources import export_source_originals
            payload = export_source_originals(root=self._log.root,
                receipts=tuple(self._observational_sources.values()), session_id=self.session_id,
                source_sha256=self.source_sha256)
            attachments['observational-source-originals.json'] = payload
            dedicated.append('observational-source-originals.json')
            total += len(payload)
        if self._observational_operator_receipts:
            from .observational_operator_report import export_operator_reports
            payload = export_operator_reports(root=self._log.root, receipts=tuple(self._observational_operator_receipts))
            attachments['observational-operator-reports.json'] = payload
            dedicated.append('observational-operator-reports.json')
            total += len(payload)
        if self._first_motion_observation_receipts:
            from .first_motion_observation import export_observations
            payload = export_observations(root=self._log.root, records=tuple(self._first_motion_observation_receipts))
            attachments['first-motion-observations.json'] = payload
            dedicated.append('first-motion-observations.json')
            total += len(payload)
        if self._observational_outcome is not None and self._observational_outcome.owned is not None:
            import base64
            from .wizard_absolute_wrist_coordinator import AbsoluteWristRunOutcome
            from rocell.providers.windows.owned_worker_process import OwnedWorkerResult
            process = self._observational_outcome.owned
            absolute_logs = type(self._observational_outcome) is AbsoluteWristRunOutcome
            log_name = 'absolute-wrist-native-logs.json' if absolute_logs else 'observational-native-logs.json'
            if (type(process) is not OwnedWorkerResult or len(process.stdout) > 256*1024
                    or len(process.stderr) > 8192):
                raise WizardError('OBSERVATIONAL_EXPORT_INVALID','Owned observational log bytes are unavailable or exceed bounds.')
            payload = _json_payload(dict(schema=('rocell.absolute_wrist_native_logs.v1' if absolute_logs
                else 'rocell.observational_native_logs.v1'),
                stage=self._observational_outcome.stage,
                process={key:value for key,value in process.to_dict().items() if key!='parsed_result'},
                stdout_base64_chunks=[base64.b64encode(process.stdout[i:i+32768]).decode('ascii')
                                      for i in range(0,len(process.stdout),32768)],
                stderr_base64_chunks=[base64.b64encode(process.stderr[i:i+32768]).decode('ascii')
                                      for i in range(0,len(process.stderr),32768)],
                physical_authority=False, physical_movement_verified=False, replay_allowed=False))
            attachments[log_name] = payload
            dedicated.append(log_name)
            total += len(payload)
        if self._first_motion_outcome is not None and self._first_motion_outcome.owned is not None:
            import base64
            from rocell.providers.windows.owned_worker_process import OwnedWorkerResult
            process = self._first_motion_outcome.owned
            if (type(process) is not OwnedWorkerResult or len(process.stdout) > 256*1024
                    or len(process.stderr) > 8192):
                raise WizardError('FIRST_MOTION_EXPORT_INVALID','Commissioning process originals are unavailable or exceed bounds.')
            # Reserve original child streams before ordinary result rotation.
            # This also works when native result publication failed; do not rerun
            # motion to recover logs. Decoded child claims are deliberately absent.
            payload = _json_payload(dict(schema='rocell.first_motion_native_logs.v1',
                stage=self._first_motion_outcome.stage,
                process={key:value for key,value in process.to_dict().items() if key!='parsed_result'},
                stdout_base64_chunks=[base64.b64encode(process.stdout[i:i+32768]).decode('ascii')
                                      for i in range(0,len(process.stdout),32768)],
                stderr_base64_chunks=[base64.b64encode(process.stderr[i:i+32768]).decode('ascii')
                                      for i in range(0,len(process.stderr),32768)],
                physical_authority=False, physical_movement_verified=False, replay_allowed=False))
            attachments['first-motion-native-logs.json'] = payload
            dedicated.append('first-motion-native-logs.json')
            total += len(payload)
        if self._powered_feedback_attempt_id is not None:
            from .powered_feedback_attempt_store import collect_attempt

            payload = _json_payload(
                collect_attempt(self._log.root, self._powered_feedback_attempt_id)
            )
            attachments["powered-feedback-attempt-files.json"] = payload
            dedicated.append("powered-feedback-attempt-files.json")
            total += len(payload)
        if self._powered_feedback_outcome is not None:
            import base64

            process = self._powered_feedback_outcome.process
            summary = {
                key: value
                for key, value in process.to_dict().items()
                if key != "parsed_result"
            }
            payload = _json_payload(
                {
                    "schema": "rocell.powered_feedback_native_logs.v1",
                    "process": summary,
                    "stdout_base64_chunks": [
                        base64.b64encode(process.stdout[i : i + 32768]).decode("ascii")
                        for i in range(0, len(process.stdout), 32768)
                    ],
                    "stderr_base64_chunks": [
                        base64.b64encode(process.stderr[i : i + 32768]).decode("ascii")
                        for i in range(0, len(process.stderr), 32768)
                    ],
                    "physical_authority": False,
                }
            )
            attachments["powered-feedback-native-logs.json"] = payload
            dedicated.append("powered-feedback-native-logs.json")
            total += len(payload)
        if self._powered_feedback_history_files is not None:
            payload = _json_payload(self._powered_feedback_history_files)
            if len(payload) > MAX_RESULT_BYTES:
                raise WizardError(
                    "POWERED_HISTORY_EXPORT_LIMIT",
                    "Historical powered records exceed this export's attachment budget; no complete export was produced.",
                )
            attachments["powered-feedback-history.json"] = payload
            dedicated.append("powered-feedback-history.json")
            total += len(payload)
        if self._powered_feedback_process_original is not None:
            import base64

            payload = _json_payload(
                {
                    "schema": "rocell.powered_feedback_process_export.v1",
                    "original_base64": base64.b64encode(
                        self._powered_feedback_process_original
                    ).decode("ascii"),
                    "physical_authority": False,
                }
            )
            attachments["powered-feedback-process.json"] = payload
            dedicated.append("powered-feedback-process.json")
            total += len(payload)
        if self._powered_feedback_rehearsal_original is not None:
            import base64

            raw = self._powered_feedback_rehearsal_original
            # Wrapper formatting may change during export; original bytes must not.
            payload = _json_payload(
                {
                    "schema": "rocell.powered_feedback_rehearsal_export.v1",
                    "origin": "SYNTHETIC_REHEARSAL",
                    "original_base64": base64.b64encode(raw).decode("ascii"),
                    "physical_authority": False,
                }
            )
            attachments["powered-feedback-rehearsal.json"] = payload
            dedicated.append("powered-feedback-rehearsal.json")
            total += len(payload)
        if self._passive_arm_retained is not None:
            payload = _json_payload(self._passive_arm_retained)
            if len(payload) > MAX_RESULT_BYTES:
                raise WizardError(
                    "PASSIVE_ARM_EXPORT_LIMIT",
                    "Retained passive diagnostic exceeds export budget.",
                )
            attachments["passive-arm-rehearsal.json"] = payload
            dedicated.append("passive-arm-rehearsal.json")
            total += len(payload)
        if self._physical_intake is not None:
            # Housekeeping stays available after faults. Observe source here
            # without requiring a successful check to export historical notes;
            # otherwise a direct export after an edit could mislabel old drafts.
            try:
                self._recheck_source("physical_intake_record")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            # Reserve this bounded complete snapshot before the rotating last-
            # eight result budget, so ordinary notes cannot evict draft work.
            payload = _json_payload(
                {
                    "schema": "rocell.physical_intake_export.v1",
                    "status": (
                        "CURRENT_DRAFT"
                        if self._intake_is_current()
                        else "HISTORICAL_HELD"
                    ),
                    "notebook": self._physical_intake.view(),
                    "physical_authority": False,
                    "hardware_qualified": False,
                    "meaning": "Original last published draft snapshot; not an accepted receipt, verified attachment or restored physical readiness.",
                }
            )
            attachments["physical-intake-notebook.json"] = payload
            dedicated.append("physical-intake-notebook.json")
            total += len(payload)
        noncontact = self._commissioning.retained_noncontact_diagnostics()
        if noncontact is not None:
            try:
                self._recheck_source("rehearsal_collect")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            clean_receipt = sanitize_diagnostic_record(
                noncontact, maximum_bytes=MAX_RESULT_BYTES
            )
            exact = clean_receipt == noncontact
            current = self._commissioning_view().get("noncontact_evaluation")
            payload = _json_payload(
                {
                    "schema": "rocell.noncontact_diagnostic_export.v1",
                    "publication": (
                        "CURRENT_GAP_REPORT"
                        if exact and current is not None
                        else "HISTORICAL_HELD"
                    ),
                    "original_bytes_preserved": exact,
                    "receipt": clean_receipt,
                    "physical_authority": False,
                    "meaning": "Original readiness gap diagnostics, not noncontact acceptance or physical handoff. Redacted content, when indicated, is not the original evidence named by its hashes.",
                }
            )
            attachments["noncontact-readiness.json"] = payload
            dedicated.append("noncontact-readiness.json")
            total += len(payload)
        runtime = self._physical_camera.retained_runtime_diagnostics()
        if runtime is not None:
            try:
                self._recheck_source("physical_camera_runtime_inspect")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            clean_runtime = sanitize_diagnostic_record(
                runtime, maximum_bytes=MAX_RESULT_BYTES
            )
            exact = clean_runtime == runtime
            current = self._physical_camera_view()["runtime_inspection"]
            payload = _json_payload(
                {
                    "schema": "rocell.physical_camera_runtime_inspection_export.v1",
                    "publication": (
                        "CURRENT_FILE_REPORT"
                        if exact
                        and current["publication"]["status"] == "CURRENT"
                        and current["inspection"]["report_sha256"]
                        == runtime["inspection_sha256"]
                        else "HISTORICAL_HELD"
                    ),
                    "original_bytes_preserved": exact,
                    **clean_runtime,
                    "physical_authority": False,
                    "meaning": "Original file diagnostics only, never runtime registration or hardware qualification. Redacted content, when indicated, is not original evidence named by its hashes.",
                }
            )
            attachments["camera-runtime-inspection.json"] = payload
            dedicated.append("camera-runtime-inspection.json")
            total += len(payload)
        if self._powered_arm_startup is not None:
            import base64
            from .physical_onboarding_durability import read_bounded_regular_file

            receipt = self._powered_arm_startup["steps"][0]["report"]
            original_path = Path(receipt["path"])
            if original_path.parent != self._log.root:
                raise WizardError(
                    "POWERED_STARTUP_EXPORT_PATH",
                    "Powered startup original is outside the assigned folder.",
                )
            raw = read_bounded_regular_file(original_path, maximum_bytes=32768)
            if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
                raise WizardError(
                    "POWERED_STARTUP_EXPORT_CHANGED",
                    "Powered startup original changed; export not certified.",
                )
            payload = _json_payload(
                {
                    "schema": "rocell.powered_arm_startup_export.v1",
                    "original_base64": base64.b64encode(raw).decode("ascii"),
                    "original_sha256": receipt["sha256"],
                    "physical_authority": False,
                }
            )
            if total + len(payload) > 6 * MAX_RESULT_BYTES:
                raise WizardError(
                    "POWERED_STARTUP_EXPORT_BUDGET",
                    "Powered startup original exceeds the remaining export budget.",
                )
            attachments["powered-arm-startup-original.json"] = payload
            dedicated.append("powered-arm-startup-original.json")
            total += len(payload)
        if self._physical_passive_history_files is not None:
            history_attachment = _json_payload(self._physical_passive_history_files)
            if (
                len(history_attachment) > MAX_RESULT_BYTES
                or total + len(history_attachment) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "PASSIVE_HISTORY_EXPORT_BUDGET",
                    "Historical files exceed the remaining export budget; originals remain in the assigned log folder.",
                )
            attachments["physical-passive-history.json"] = history_attachment
            dedicated.append("physical-passive-history.json")
            total += len(history_attachment)
        if self._passive_arm_attempt_id is not None:
            from .passive_arm_attempt_export import collect_attempt

            attempt_files = _json_payload(
                collect_attempt(self._log.root, self._passive_arm_attempt_id)
            )
            if (
                len(attempt_files) > MAX_RESULT_BYTES
                or total + len(attempt_files) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "PASSIVE_HISTORY_EXPORT_BUDGET",
                    "Attempt files exceed the remaining export budget; original files remain in the assigned diagnostic folder.",
                )
            attachments["passive-arm-attempt-files.json"] = attempt_files
            dedicated.append("passive-arm-attempt-files.json")
            total += len(attempt_files)
        if self._passive_arm_outcome is not None:
            import base64

            passive_process = self._passive_arm_outcome.process
            # Chunk exact binary logs below the exporter's per-string bound.
            # These are explicit diagnostic exports, not replayable requests.
            streams = {}
            for stream_name in ("stdout", "stderr"):
                stream = getattr(passive_process, stream_name)
                streams[stream_name] = {
                    "bytes": len(stream),
                    "sha256": hashlib.sha256(stream).hexdigest(),
                    "base64_chunks": [
                        base64.b64encode(stream[start : start + 32768]).decode("ascii")
                        for start in range(0, len(stream), 32768)
                    ],
                }
            passive_attachment = _json_payload(
                {
                    "schema": "rocell.passive_arm_process_logs_export.v1",
                    "attempt_id": passive_process.attempt_id,
                    "summary": self._passive_arm_outcome.summary(),
                    "streams": streams,
                    "physical_authority": False,
                    "replay_allowed": False,
                    "privacy": "Exact process diagnostics; review before sharing. Binary logs are not text-redacted.",
                }
            )
            if (
                len(passive_attachment) > MAX_RESULT_BYTES
                or total + len(passive_attachment) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "PASSIVE_LOG_EXPORT_BUDGET",
                    "Passive logs exceed the remaining export budget.",
                )
            attachments["passive-arm-process-logs.json"] = passive_attachment
            dedicated.append("passive-arm-process-logs.json")
            total += len(passive_attachment)
        if self._passive_arm_setup is not None:
            from .physical_onboarding_durability import read_bounded_regular_file

            setup_steps = self._passive_arm_setup.get("steps", [])
            if (
                setup_steps
                and setup_steps[0].get("name") == "passive_arm_setup_original"
            ):
                setup_receipt = setup_steps[0]["report"]
                setup_path = Path(setup_receipt["path"])
                if setup_path.parent != self._log.root:
                    raise WizardError(
                        "PASSIVE_SETUP_EXPORT_PATH",
                        "Setup original is outside the diagnostic folder.",
                    )
                setup_bytes = read_bounded_regular_file(
                    setup_path, maximum_bytes=MAX_RESULT_BYTES
                )
                if hashlib.sha256(setup_bytes).hexdigest() != setup_receipt["sha256"]:
                    raise WizardError(
                        "PASSIVE_SETUP_EXPORT_CHANGED",
                        "Setup original changed; export not certified.",
                    )
                # The general exporter normalizes JSON formatting. Encode the
                # original bytes so its recorded hash remains independently
                # verifiable after that presentation transformation.
                import base64

                setup_attachment = _json_payload(
                    {
                        "schema": "rocell.passive_arm_setup_original_export.v1",
                        "original_base64": base64.b64encode(setup_bytes).decode(
                            "ascii"
                        ),
                        "original_sha256": setup_receipt["sha256"],
                        "physical_authority": False,
                        "connected": False,
                    }
                )
                if (
                    len(setup_attachment) > MAX_RESULT_BYTES
                    or total + len(setup_attachment) > 6 * MAX_RESULT_BYTES
                ):
                    raise WizardError(
                        "PASSIVE_SETUP_EXPORT_BUDGET",
                        "Setup original exceeds the remaining export budget.",
                    )
                attachments["passive-arm-setup-original.json"] = setup_attachment
                dedicated.append("passive-arm-setup-original.json")
                total += len(setup_attachment)
        if self._native_arm_retained is not None:
            try:
                self._recheck_source("inspect_native_arm_metadata")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            # Keep the most recent bounded arm metadata attempt even after
            # ordinary notes rotate its result card. This is not a stage store.
            payload = _json_payload(
                {
                    "schema": "rocell.wizard_native_arm_metadata_export.v1",
                    "publication": self._native_arm_view()["status"],
                    "source_sha256": self.source_sha256,
                    "session_id": self.session_id,
                    "result": self._native_arm_retained,
                    "physical_authority": False,
                    "meaning": "Latest retained metadata diagnostic only. Failed or redacted results are not exact identity evidence; no port connection or physical qualification is granted.",
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "ARM_METADATA_EXPORT_BUDGET",
                    "The full retained arm diagnostic exceeds the export budget; it was not truncated or marked exported.",
                )
            attachments["native-arm-metadata.json"] = payload
            dedicated.append("native-arm-metadata.json")
            total += len(payload)
        qualification = self._source_qualification.retained_diagnostics()
        static_onboarding = self._static_camera_onboarding.retained_diagnostics()
        if qualification is not None or static_onboarding is not None:
            try:
                self._recheck_source("physical_source_qualify")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            # The service returns a closed flattened collection of metadata
            # documents/references. Private isolation originals are not embedded.
            clean = sanitize_diagnostic_record(
                qualification or {}, maximum_bytes=MAX_RESULT_BYTES
            )
            exact = clean == (qualification or {})
            packet = {
                **clean,
                "schema": "rocell.wizard_source_qualification_export.v1",
                "publication": (
                    self._source_reassessment_view()["publication"]
                    if exact
                    else {"status": "HISTORICAL_HELD", "operation_id": None}
                ),
                "original_bytes_preserved": exact,
                "physical_authority": False,
                "hardware_qualified": False,
                "meaning": "Original source qualification metadata and references only, not private isolation bytes or native release. Redacted documents are not the original subjects named by their hashes; no automatic restoration or replay.",
            }
            if static_onboarding is not None:
                static_clean = sanitize_diagnostic_record(
                    static_onboarding, maximum_bytes=MAX_RESULT_BYTES
                )
                static_exact = static_clean == static_onboarding
                static_publication = (
                    self._static_camera_onboarding_view()["publication"]
                    if static_exact
                    else {"status": "HISTORICAL_HELD", "operation_id": None}
                )
                packet.update(
                    schema="rocell.wizard_source_qualification_export.v2",
                    source_qualification_present=qualification is not None,
                    source_qualification_publication=deepcopy(packet["publication"]),
                    source_qualification_original_bytes_preserved=exact,
                    static_camera_onboarding={
                        **static_clean,
                        "publication": static_publication,
                        "original_bytes_preserved": static_exact,
                    },
                    original_bytes_preserved=exact and static_exact,
                    meaning="Separate original source qualification and static-camera design metadata families. Design PASS is not received or installed qualification; no private isolation originals or native release are included. Redacted documents are not original evidence.",
                )
                if not (exact and static_exact):
                    packet["publication"] = {
                        "status": "HISTORICAL_HELD",
                        "operation_id": None,
                    }
            # Validate the complete composed depth/node budget as well as each
            # family. No extra attachment slot, silent truncation or quota raise.
            checked_packet = sanitize_diagnostic_record(
                packet, maximum_bytes=MAX_RESULT_BYTES
            )
            if checked_packet != packet:
                raise WizardError(
                    "SOURCE_QUALIFICATION_EXPORT_REDACTION",
                    "Combined source/design metadata changed under final sanitization; no complete original export is claimed.",
                )
            payload = _json_payload(packet)
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
                or len(attachments) >= MAX_ATTACHMENTS
            ):
                raise WizardError(
                    "SOURCE_QUALIFICATION_EXPORT_BUDGET",
                    "Full source qualification metadata exceeds export bounds; no truncation or complete export claimed.",
                )
            attachments["source-qualification-data.json"] = payload
            dedicated.append("source-qualification-data.json")
            total += len(payload)
        intake_evidence = self._physical_intake_evidence.retained_diagnostics()
        if intake_evidence is not None:
            try:
                self._recheck_source("physical_intake_submit")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            clean = sanitize_diagnostic_record(
                intake_evidence, maximum_bytes=MAX_RESULT_BYTES
            )
            exact = clean == intake_evidence
            payload = _json_payload(
                {
                    **clean,
                    "schema": "rocell.wizard_physical_intake_evidence_export.v1",
                    "publication": (
                        self._physical_intake_evidence_view()["publication"]
                        if exact
                        else {"status": "HISTORICAL_HELD", "operation_id": None}
                    ),
                    "original_bytes_preserved": exact,
                    "meaning": "Original submission/assessment/review metadata only, not private attachment media or physical acceptance. Redacted documents are not original subjects named by their hashes. Original media require a separate explicit private-originals export.",
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "INTAKE_EVIDENCE_EXPORT_BUDGET",
                    "Full retained intake metadata exceeds the export budget; no truncation or complete export is claimed.",
                )
            attachments["intake-evidence.json"] = payload
            dedicated.append("intake-evidence.json")
            total += len(payload)
        configuration = self._physical_camera_setup.retained_configuration_diagnostics()
        if configuration is not None:
            try:
                self._recheck_source("physical_camera_refresh")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            # The complete initial dependency vector has its own reserved slot.
            # Ordinary nested result cards carry only a compact summary, and
            # later notes cannot evict these original configuration records.
            document = configuration["record"].pop("document")
            original = {**configuration, "document": document}
            clean = sanitize_diagnostic_record(original, maximum_bytes=MAX_RESULT_BYTES)
            exact = clean == original
            payload = _json_payload(
                {
                    **clean,
                    "schema": "rocell.wizard_physical_configuration_export.v1",
                    "publication": (
                        "CURRENT"
                        if exact
                        and self._physical_camera_setup_view()["configuration_records"][
                            "status"
                        ]
                        == "CURRENT"
                        else "HISTORICAL_HELD"
                    ),
                    "original_bytes_preserved": exact,
                    "meaning": "Original configuration dependency record, not accepted measurements, camera admission or hardware qualification. Redacted documents are not the original bytes named by their hashes.",
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "CONFIGURATION_RECORD_EXPORT_BUDGET",
                    "Full configuration diagnostics exceed the export budget; no record was truncated.",
                )
            attachments["configuration-records.json"] = payload
            dedicated.append("configuration-records.json")
            total += len(payload)
        source_workflow = self._physical_camera_setup.retained_source_diagnostics()
        if source_workflow is not None:
            try:
                self._recheck_source("physical_camera_refresh")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            clean = sanitize_diagnostic_record(
                source_workflow, maximum_bytes=MAX_RESULT_BYTES
            )
            exact = clean == source_workflow
            payload = _json_payload(
                {
                    "publication": (
                        self._physical_camera_setup_view()["source_workflow"]["status"]
                        if exact
                        else "HISTORICAL_HELD"
                    ),
                    "original_bytes_preserved": exact,
                    **clean,
                    "schema": "rocell.wizard_workspace_source_export.v1",
                    "meaning": "Original source-stage evidence and last attempted records. BLOCKED is not hardware qualification; redacted documents are not the original evidence named by their hashes.",
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "SOURCE_WORKFLOW_EXPORT_BUDGET",
                    "Full source-workflow diagnostics exceed the export budget; no truncation or success claimed.",
                )
            attachments["workspace-source-workflow.json"] = payload
            dedicated.append("workspace-source-workflow.json")
            total += len(payload)
        mode_entry = self._physical_camera_setup.mode_entry_diagnostics()
        if mode_entry is not None:
            clean_entry = sanitize_diagnostic_record(
                mode_entry, maximum_bytes=64 * 1024
            )
            payload = _json_payload(
                {
                    **clean_entry,
                    "original_bytes_preserved": clean_entry == mode_entry,
                }
            )
            if len(payload) > 64 * 1024 or total + len(payload) > 6 * MAX_RESULT_BYTES:
                raise WizardError(
                    "CAMERA_MODE_EXPORT_BUDGET",
                    "Full camera-entry diagnostics exceed the export budget; no truncation or success claimed.",
                )
            attachments["camera-mode-entry.json"] = payload
            dedicated.append("camera-mode-entry.json")
            total += len(payload)
        proposal_data = self._operating_proposal.packet()
        if proposal_data["attempts"]:
            clean_proposal = sanitize_diagnostic_record(
                proposal_data, maximum_bytes=MAX_RESULT_BYTES
            )
            payload = _json_payload(
                {
                    "diagnostics": clean_proposal,
                    "original_bytes_preserved": clean_proposal == proposal_data,
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
            ):
                raise WizardError(
                    "CAMERA_PROPOSAL_EXPORT_BUDGET",
                    "Complete draft proposal diagnostics exceed the export budget; no truncation is accepted.",
                )
            attachments["camera-operating-proposals.json"] = payload
            dedicated.append("camera-operating-proposals.json")
            total += len(payload)
        assessment_data = self._operating_assessment.packet()
        if assessment_data["attempts"]:
            clean = sanitize_diagnostic_record(assessment_data, maximum_bytes=MAX_RESULT_BYTES)
            payload = _json_payload(dict(diagnostics=clean, original_bytes_preserved=clean == assessment_data))
            if len(payload) > MAX_RESULT_BYTES or total + len(payload) > 6 * MAX_RESULT_BYTES:
                raise WizardError("OPERATING_ASSESSMENT_EXPORT_BUDGET", "Complete assessment history exceeds the export budget; nothing was truncated.")
            attachments["camera-operating-assessments.json"] = payload
            dedicated.append("camera-operating-assessments.json")
            total += len(payload)
        submission_data = self._operating_submission.packet()
        if submission_data["attempts"] or submission_data["original_readback"] is not None:
            clean = sanitize_diagnostic_record(submission_data, maximum_bytes=MAX_RESULT_BYTES)
            payload = _json_payload(dict(diagnostics=clean, original_bytes_preserved=clean == submission_data))
            if len(payload) > MAX_RESULT_BYTES or total + len(payload) > 6 * MAX_RESULT_BYTES:
                raise WizardError("OPERATING_SUBMISSION_EXPORT_BUDGET", "Complete submission history exceeds the export budget; nothing was truncated.")
            attachments["camera-operating-submissions.json"] = payload
            dedicated.append("camera-operating-submissions.json")
            total += len(payload)
        camera_data = self._physical_camera.retained_capture_diagnostics()
        if camera_data is not None:
            try:
                self._recheck_source("physical_camera_configuration")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            # Flatten documents instead of nesting full native packets another
            # few levels. Export keeps metadata only, never raw camera media.
            original_probe = "original_probe" in camera_data
            if original_probe:
                # The dedicated exporter decodes/redacts native pipe buffers
                # before bounded reconstruction. Never pass opaque base64 or
                # oversized compound originals through this general exporter.
                documents = dict(
                    probe_attempt=self._probe_attempt_view(),
                    complete_native_diagnostics_included=False,
                    separate_export_action="physical_camera_probe_attempt_export",
                    configuration_attempt=self._configuration_wizard.view(),
                    configuration_export_action=CONFIGURATION_EXPORT,
                )
            else:
                documents = {
                    f"{phase}_{name}": document
                    for phase, workflow in camera_data.items()
                    if workflow is not None
                    for name, document in workflow.items()
                }
            clean = sanitize_diagnostic_record(
                documents, maximum_bytes=MAX_RESULT_BYTES
            )
            exact = clean == documents and not original_probe
            payload = _json_payload(
                {
                    "schema": "rocell.wizard_native_camera_data_export.v1",
                    "publication": (
                        self._physical_camera_view()["publication"]["status"]
                        if exact
                        else "HISTORICAL_HELD"
                    ),
                    "original_bytes_preserved": exact,
                    **clean,
                    "meaning": (
                        "Summary only. Use Export camera probe attempt for complete decoded/redacted admission and native run/supervision diagnostics. This general bundle cannot restore a connection or authorize replay."
                        if original_probe
                        else "Native data handoff diagnostics and saved dataset references, not current connection, device release or physical stage acceptance. Media remains in its assigned dataset folder."
                    ),
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
                or len(attachments) >= MAX_ATTACHMENTS
            ):
                raise WizardError(
                    "CAMERA_DATA_EXPORT_BUDGET",
                    "Complete native camera diagnostics exceed export bounds; no truncation or successful export claimed.",
                )
            attachments["native-camera-data.json"] = payload
            dedicated.append("native-camera-data.json")
            total += len(payload)
        feedback = self._commissioning.retained_feedback_diagnostics()
        if feedback is not None and feedback.get("arm_feedback_process") is not None:
            try:
                self._recheck_source("rehearsal_owned_arm_feedback_campaign")
            except WizardError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
            # Reserve current-launch complete identity traces (or explicitly
            # summary-only reopened diagnostics) before ordinary result rotation.
            clean = sanitize_diagnostic_record(feedback, maximum_bytes=MAX_RESULT_BYTES)
            exact = clean == feedback
            current = self._commissioning_view().get("arm_feedback_process")
            payload = _json_payload(
                {
                    "schema": "rocell.wizard_owned_arm_connection_export.v1",
                    "publication": (
                        "CURRENT_REHEARSAL_DIAGNOSTIC"
                        if exact and current == feedback["arm_feedback_process"]
                        else "HISTORICAL_HELD"
                    ),
                    "original_bytes_preserved": exact,
                    "diagnostics": clean,
                    "physical_authority": False,
                    "meaning": "Modeled controller resolution and retained process diagnostics, not a physical connection. Full serial/process bytes remain in the original M1 store; after reopening only the verified summary is restored here. Redacted data is not original evidence named by its hashes.",
                }
            )
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
                or len(attachments) >= MAX_ATTACHMENTS
            ):
                raise WizardError(
                    "ARM_CONNECTION_EXPORT_BUDGET",
                    "Complete retained connection diagnostics exceed export bounds; no truncation or successful export claimed.",
                )
            attachments["owned-arm-connection.json"] = payload
            dedicated.append("owned-arm-connection.json")
            total += len(payload)
        movement_index = []
        for operation_id, result in reversed(self._full_results.items()):
            payload = _json_payload(result)
            action_id = self._operations.get(operation_id, {}).get("action_id")
            if action_id in ACTION_BY_ID and ACTION_BY_ID[action_id].worker in {
                "physical_received_camera",
                "physical_camera_identity_records",
                "physical_usb_identity",
            }:
                omitted.append(
                    {
                        "operation_id": operation_id,
                        "reason": (
                            "USB_IDENTITY_SEPARATE_METADATA_BUNDLE_REQUIRED"
                            if ACTION_BY_ID[action_id].worker == "physical_usb_identity"
                            else (
                                "CAMERA_IDENTITY_SEPARATE_METADATA_BUNDLE_REQUIRED"
                                if ACTION_BY_ID[action_id].worker
                                == "physical_camera_identity_records"
                                else "RECEIVED_CAMERA_SEPARATE_METADATA_BUNDLE_REQUIRED"
                            )
                        ),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                    }
                )
                continue
            if (
                len(payload) > MAX_RESULT_BYTES
                or total + len(payload) > 6 * MAX_RESULT_BYTES
                or len(attachments) >= MAX_ATTACHMENTS
            ):
                omitted.append(
                    {
                        "operation_id": operation_id,
                        "reason": (
                            "ATTACHMENT_COUNT_BUDGET"
                            if len(attachments) >= MAX_ATTACHMENTS
                            else "ATTACHMENT_BYTE_BUDGET"
                        ),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "bytes": len(payload),
                    }
                )
                continue
            attachments[f"result-{operation_id.removeprefix('operation-')}.json"] = (
                payload
            )
            if isinstance(result.get('move_result'), dict):
                movement_index.append(dict(
                    operation_id=operation_id,
                    attachment=f"attachment-result-{operation_id.removeprefix('operation-')}.json",
                    result_pointer='/move_result', evidence_pointer='/steps/0/report',
                    status=result['move_result']['status'],
                    native_request_id=result['move_result'].get('native_request_id'),
                    configuration_id=result['move_result'].get('configuration_id')))
            total += len(payload)
        for operation_id, operation in self._operations.items():
            if operation["result_retention"].startswith("OMITTED"):
                omitted.append(
                    {
                        "operation_id": operation_id,
                        "reason": operation["result_retention"],
                        "sha256": operation.get("result_sha256"),
                    }
                )
        snapshot = self.view()
        # Index only retained attachments; omitted results remain in the existing
        # omission inventory. Manifest hashes cover the final redacted bytes.
        snapshot['movement_export_index'] = movement_index
        # Received originals have an explicit separate bundle. Do not duplicate
        # large notebooks/inspection histories or repeated attachment choices
        # into the 256 KiB general diagnostic snapshot or its eight attachments.
        snapshot["received_camera_onboarding"] = self._received_camera_export_pointer()
        snapshot["camera_identity_onboarding"] = self._camera_identity_export_pointer()
        snapshot["usb_identity"] = self._usb_identity_export_pointer()
        snapshot["usb_qualification"] = self._usb_qualification_export_pointer()
        for action in snapshot["actions"]:
            if ACTION_BY_ID[action["action_id"]].worker in {
                "physical_received_camera",
                "physical_camera_identity_records",
                "physical_usb_identity",
            }:
                action.pop("fields", None)
        snapshot["usb_identity_export_policy"] = {
            "schema": "rocell.wizard_usb_identity_export_policy.v1",
            "live_ui_projection": False,
            "original_documents_included": False,
            "action_form_fields": "OMITTED_UI_DEFINITIONS_NOT_EVIDENCE",
            "required_action": "physical_usb_identity_export",
            "physical_authority": False,
            "meaning": "General diagnostics retain compact USB baseline and four-phase review coverage only. The separate explicit USB evidence bundle retains original policy/runtime/operation, phase, assessment, review and owned execution bytes with redaction distinctions. No query or replay is part of export.",
        }
        snapshot["camera_identity_export_policy"] = {
            "schema": "rocell.wizard_camera_identity_export_policy.v1",
            "live_ui_projection": False,
            "original_documents_included": False,
            "action_form_fields": "OMITTED_UI_DEFINITIONS_NOT_EVIDENCE",
            "required_action": "physical_camera_identity_export",
            "physical_authority": False,
            "meaning": "General diagnostics contain compact identity coverage only. The separate explicit identity metadata bundle retains full subjects, with original hashes and redaction distinctions; no domain is silently treated as fully exported.",
        }
        snapshot["received_camera_export_policy"] = {
            "schema": "rocell.wizard_received_camera_export_policy.v1",
            "live_ui_projection": False,
            "original_documents_included": False,
            "action_form_fields": "OMITTED_UI_DEFINITIONS_NOT_EVIDENCE",
            "required_action": "physical_received_camera_export",
            "physical_authority": False,
            "meaning": "A general diagnostic export is not the complete received-stage evidence bundle; invoke the separate explicit metadata export. No original domain is silently dropped or marked fully exported.",
        }
        if snapshot["actions"]:
            # Form definitions grow with the registry even without intake data.
            # Live forms also repeat the same 32-file choice roster in sixteen
            # selects. They are UI definitions, not evidence. Keep the live UI
            # complete, but make this explicitly identified export projection
            # refer to the reserved full notebook rather than duplicating it.
            # Do not raise the shared snapshot cap or truncate original records.
            for action in snapshot["actions"]:
                action.pop("fields", None)
            notebook_reference = None
            if self._physical_intake is not None:
                notebook_reference = {
                    "attachment": "attachment-physical-intake-notebook.json",
                    "original_notebook_sha256": self._physical_intake.sha256,
                    "meaning": "Complete notebook is in the reserved attachment; exported text may be sanitized and is not authority to restore readiness.",
                }
                snapshot["physical_intake"]["notebook"] = None
            snapshot["snapshot_projection"] = {
                "schema": "rocell.wizard_export_projection.v1",
                "live_ui_snapshot": False,
                "action_form_fields": "OMITTED_UI_DEFINITIONS_NOT_EVIDENCE",
                "notebook_reference": notebook_reference,
                "meaning": "Bounded diagnostic projection. Action labels and blocking reasons remain; complete original intake metadata has reserved attachments, not abbreviated evidence.",
            }
        # The report includes only receipt summaries, not recursive older export
        # manifests or full test payloads. Full results use bounded attachments.
        snapshot["exports"] = {
            "directory": str(self.export_directory),
            "export_count": len(self._exports),
        }
        snapshot["events"] = []
        snapshot["result_export_policy"] = {
            "description": _OMISSION_POLICY,
            "omitted": omitted,
            "included_full_results": len(attachments) - len(dedicated),
            "dedicated_attachments": dedicated,
        }
        self._exporter.prepare(create=True)
        receipt = self._exporter.export(snapshot, self._events, attachments=attachments)
        verification = verify_export(Path(receipt["path"]))
        if not verification["valid"]:
            raise WizardError(
                "EXPORT_VERIFICATION_FAILED",
                "Export integrity verification failed; inspect the retained directory.",
            )
        self._exports.append(receipt)
        self._exports = self._exports[-8:]
        return {
            "message": "Diagnostic export written and verified. It does not commission hardware.",
            "receipt": receipt,
            "verification": verification,
            "physical_authority": False,
        }

    def shutdown(self) -> None:
        """Cancel the diagnostic child; never claim a physical emergency stop."""
        with self._lock:
            self._closed = True
            if self._cancel is not None:
                self._cancel.set()
            self._changed(state=True)
            executor = self._executor
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
