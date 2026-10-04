r"""Read-only, loopback UI design preview with FICTIONAL camera records.

This is not the wizard service. It constructs no hardware/application providers,
accepts no POST actions, writes no diagnostics, and cannot create approvals.
Run from the workspace: .venv\Scripts\python.exe software/scripts/camera_ui_preview.py
Then open the printed URL and choose Camera. Ctrl+C stops this preview only.
"""

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets


ACTION = "physical_camera_operating_assessment"
OPERATION = "operation-" + "a" * 32
CHECKS = (
    "REQUIRED_CONTROLS_SELECTED_MANUAL",
    "TWO_CAPTURE_REPORTS_PRESENT",
    "DISTINCT_PROBE_AND_CAPTURE_ATTEMPTS",
    "BOTH_READBACKS_MATCH_AND_CLEANUP_CONFIRMED",
    "REPEATED_OBSERVED_FORMAT_AND_LAYOUT",
    "SAME_CAPTURE_RUNTIME",
)
HOLDS = (
    "USB_SPEED_AND_IDENTITY_CONTINUITY_NOT_ASSESSED",
    "ORDERED_CLOSE_REOPEN_NOT_AUTHENTICATED",
    "PIXEL_FILES_NOT_VERIFIED",
    "FRAME_FRESHNESS_NOT_ASSESSED",
    "SEPARATE_OPERATOR_REVIEW_NOT_RECORDED",
    "INSTALLED_OPTICS_AND_CALIBRATION_DEFERRED",
    "PROPOSAL_AND_ASSESSMENT_ORIGINAL_STAGE_RETENTION_NOT_IMPLEMENTED",
)
FALSE_FIELDS = (
    "approved_operating_policy",
    "original_store_authenticated",
    "authenticated_operator_identity",
    "stage_passed",
    "physical_authority",
    "hardware_qualified",
    "camera_capture_authorized",
    "arm_access_authorized",
    "device_io_performed",
    "automatic_fallback",
)


def example_operation(*, complete=False):
    """Presentation specimen only; dummy references are not original evidence."""
    failed = [] if complete else list(CHECKS[1:])
    preflight = dict(
        schema="rocell.camera_operating_evidence_preflight.v1",
        status=(
            "BLOCKED_METADATA"
            if failed
            else "CONSISTENT_METADATA_PENDING_ORIGINAL_REVIEW"
        ),
        proposal_sha256="b" * 64,
        checks=[dict(id=key, satisfied=key not in failed) for key in CHECKS],
        failed_checks=failed,
        **dict.fromkeys(FALSE_FIELDS, False),
    )
    report = dict(
        schema="rocell.camera_original_operating_assessment.v1",
        status="ORIGINAL_INPUTS_CHECKED_APPROVAL_HELD",
        original_inputs_authenticated_at_read=True,
        currentness_requires_revalidation=True,
        original_stage_record_retained=False,
        approved_operating_policy=False,
        physical_authority=False,
        hardware_qualified=False,
        connected=False,
        proposal_sha256="b" * 64,
        preflight=preflight,
        unresolved_checks=list(HOLDS),
        fixture_notice="FICTIONAL UI SPECIMEN. No original evidence was read.",
    )
    worker = dict(
        schema="rocell.wizard_worker_result.v1",
        action_id=ACTION,
        status="SUCCEEDED",
        steps=[dict(name="original_operating_assessment", exit_code=0, report=report)],
        device_open_count=0,
        serial_write_count=0,
        power_event_count=0,
        motion_command_count=0,
        contact_command_count=0,
        metadata_inventory_performed=False,
        physical_authority=False,
    )
    return dict(
        operation_id=OPERATION,
        action_id=ACTION,
        status="SUCCEEDED",
        label="Example camera assessment — fictional data",
        message="UI DESIGN PREVIEW ONLY. No camera or original evidence was accessed.",
        completion_log_persisted=True,
        result_retention="FULL_JSON_RETAINED",
        result=worker,
    )


def example_view(scenario="incomplete"):
    """Fictional view; only the drafts scenario permits editing, never dispatch."""
    operation = example_operation(complete=scenario == "consistent")
    if scenario == "held":
        operation["status"] = "FAILED"
        operation["completion_log_persisted"] = False
    view = dict(
        revision=1,
        state_epoch=0,
        source_binding_sha256="0" * 64,
        mode="rehearsal",
        cell_id="UI-PREVIEW-NO-HARDWARE",
        session_id="fictional-ui-preview",
        status="UI_DESIGN_PREVIEW_ONLY",
        verification="FICTIONAL_DATA_NOT_HARDWARE_EVIDENCE",
        authority="NO_PHYSICAL_AUTHORITY",
        physical_authority=False,
        camera={},
        arm={},
        stages=[],
        diagnostics=dict(log_state="NO_LOGS_WRITTEN_UI_PREVIEW"),
        exports=dict(directory="UI preview only — exports disabled", items=[]),
        actions=[
            dict(
                action_id=ACTION,
                section="camera",
                label="Check proposal against saved original evidence",
                description="This design preview cannot run assessments or open devices.",
                enabled=False,
                fields=[],
                blocked_reasons=["Read-only UI specimen: all actions disabled."],
            )
        ],
        operations=(
            []
            if scenario == "empty"
            else [{key: value for key, value in operation.items() if key != "result"}]
        ),
    )
    if scenario in {"catalog", "activity", "drafts"}:
        # Declarative definitions only: never construct ArrivalWizardService or
        # invoke its workers. Forms start disabled; drafts opts into editing only.
        from rocell.application.wizard_actions import ACTIONS

        view["actions"] = []
        for action in ACTIONS:
            item = action.view(mode="rehearsal", busy=False)
            item["enabled"] = False
            item["blocked_reasons"].append(
                "Read-only UI preview: actions cannot run here."
            )
            view["actions"].append(item)
        if scenario == "drafts":
            # Editable browser-only specimens. POST still returns 405: neither
            # a ticket nor a worker exists here, even for a harmless note.
            for item in view["actions"]:
                if item["action_id"] in {
                    "record_note",
                    "plan_task",
                    "simulate_task",
                    "rehearsal_camera_settings",
                    "movement_campaign_preview",
                    "movement_campaign_simulate",
                }:
                    item["enabled"] = True
                    item["blocked_reasons"] = []
                    item[
                        "description"
                    ] += " EDITING PREVIEW ONLY: type and refresh to review draft behavior. Preview action returns 405; no action can run."
        view["operations"] = []
        if scenario == "activity":
            view["operations"] = [
                {key: value for key, value in record.items() if key != "result"}
                for record in example_activity().values()
            ]
    return view, operation


def example_activity():
    """Bounded fictional history for paging, recovery and explicit result reads."""
    records = {}
    for index in range(16):
        operation_id = f"operation-preview-{index:02}"
        status = ("SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED")[index % 4]
        record = dict(
            operation_id=operation_id,
            action_id=(
                "camera_rehearsal" if index % 2 else "rehearse_passive_arm_connection"
            ),
            label=f"Fictional {'camera' if index % 2 else 'arm'} diagnostic {index + 1}",
            status=status,
            started_at=f"2026-09-12T15:{index:02}:00Z",
            finished_at=f"2026-09-12T15:{index:02}:01Z",
            completion_log_persisted=index != 15,
            result_retention=(
                "OMITTED_OLDER_THAN_LAST_EIGHT_RESULTS"
                if index < 9
                else (
                    "FULL_JSON_RETAINED_COMPLETION_LOG_FAILED"
                    if index == 15
                    else "FULL_JSON_RETAINED"
                )
            ),
            message="FICTIONAL UI specimen. No device was opened or command sent.",
            result=(
                None
                if index < 9
                else dict(
                    fixture_notice="Fictional saved result; not hardware evidence.",
                    physical_authority=False,
                )
            ),
        )
        if index == 15:
            record.update(
                status="FAILED", action_outcome_before_log_failure="SUCCEEDED"
            )
        if record["status"] != "SUCCEEDED":
            record["error"] = dict(
                code="FICTIONAL_REVIEW_REQUIRED",
                message="Example outcome for reviewing the interface only.",
                remediation="Inspect the saved record and export workflow. No automatic replay.",
            )
        records[operation_id] = record
    records[OPERATION] = example_operation()
    return records


def handler(scenario, *, saved_preview=None):
    token = secrets.token_urlsafe(32)
    static = Path(__file__).resolve().parents[1] / "src/rocell/ui/static"
    view, operation = example_view(scenario)
    records = example_activity() if scenario == "activity" else {OPERATION: operation}
    if saved_preview is not None:
        view, operation = saved_preview
        records = {operation['operation_id']: operation}
    record_routes = {"/api/operations/" + key: value for key, value in records.items()}

    class PreviewHandler(BaseHTTPRequestHandler):
        session_token = token

        def do_GET(self):
            host = self.headers.get_all("Host")
            expected_origin = f"http://127.0.0.1:{self.server.server_port}"
            if host != [f"127.0.0.1:{self.server.server_port}"]:
                self.send_error(403, "Invalid local host")
                return
            origins = self.headers.get_all("Origin")
            if (origins and origins != [expected_origin]) or self.headers.get("Sec-Fetch-Site") == "cross-site":
                self.send_error(403, "Invalid local origin")
                return
            if self.path.startswith("/api/"):
                supplied = self.headers.get_all("X-RoCell-Token")
                if (not supplied or len(supplied) != 1
                        or not hmac.compare_digest(supplied[0], token)):
                    self.send_error(401, "Preview session required")
                    return
            routes = {
                "/": (static / "index.html", "text/html; charset=utf-8"),
                "/assets/app.js": (static / "app.js", "text/javascript; charset=utf-8"),
                "/assets/app.css": (static / "app.css", "text/css; charset=utf-8"),
            }
            if self.path in routes:
                path, content_type = routes[self.path]
                payload = path.read_bytes()
                if self.path == "/":
                    payload = payload.replace(
                        b"<body>",
                        b'<body><div role="status" style="padding:12px;background:#fff3df;text-align:center;font-weight:bold">UI DESIGN PREVIEW - FICTIONAL DATA - NO HARDWARE ACCESS</div>',
                    )
                    if saved_preview is not None:
                        payload = payload.replace(b'UI DESIGN PREVIEW - FICTIONAL DATA - NO HARDWARE ACCESS',
                            b'HISTORICAL REPORT PREVIEW - NOT A NEW RUN - NO HARDWARE ACCESS')
            elif self.path == "/api/view" or self.path in record_routes:
                content_type = "application/json"
                payload = json.dumps(
                    view if self.path == "/api/view" else record_routes[self.path]
                ).encode()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            self.send_error(405, "UI preview is read-only; no actions exist")

        def log_message(self, *_args):
            pass

    return PreviewHandler


def saved_micro_preview(folder):
    """Read a verified coordinator export; never import a native motion provider."""
    from rocell.application.wizard_diagnostic_export import verify_export
    from rocell.application.micro_result_summary import summarize_micro_result
    folder = Path(folder).resolve()
    verified = verify_export(folder)
    name = 'attachment-result-commissioning.json'
    if not verified['valid'] or name not in {item['name'] for item in verified.get('files', [])}:
        raise ValueError('Verified coordinator attachment required')
    report = json.loads((folder / name).read_text(encoding='utf-8'))
    if report.get('schema') != 'rocell.micro_commissioning.v1':
        raise ValueError('Coordinator schema required')
    # This projection is new; never overwrite or restamp the historical original.
    report['summary'] = summarize_micro_result(report)
    view, _ = example_view('empty')
    view.update(session_id='historical-preview', verification='HISTORICAL_NOT_CURRENT', actions=[])
    operation = dict(operation_id='historical-micro', action_id='run_micro_commissioning',
        label='Historical micro-commissioning report (not a new run)',
        status='SUCCEEDED' if report['status'] in ('NO_CORRECTION_NEEDED','EXPERIMENT_VERIFIED') else 'FAILED',
        result_retention='FULL_JSON_RETAINED', completion_log_persisted=False,
        message='Read-only historical export; summary recomputed for display. No device access. The coordinator attachment was serialized before its own export completed; its final_export_succeeded=false is not proof of export failure. This preview verified its manifest, but has no enclosing operation completion log.',
        result=dict(steps=[dict(report=report)]))
    view['operations'] = [{key:value for key,value in operation.items() if key != 'result'}]
    return view, operation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "empty",
            "incomplete",
            "consistent",
            "held",
            "catalog",
            "activity",
            "drafts",
        ),
        default="incomplete",
    )
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument('--micro-export', type=Path, help='Read-only historical coordinator export preview')
    args = parser.parse_args()
    preview_handler = handler(args.scenario,
        saved_preview=saved_micro_preview(args.micro_export) if args.micro_export else None)
    with ThreadingHTTPServer(
        ("127.0.0.1", args.port), preview_handler
    ) as server:
        print(
            f"Read-only UI preview: http://127.0.0.1:{server.server_port}/#session={preview_handler.session_token}&csrf=ui-preview",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
