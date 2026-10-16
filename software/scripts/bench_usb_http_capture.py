"""One wizard-owned zero-write USB capture with an explicit transport policy.

Requires explicit standing-setup acknowledgement. Does not retry an attempt,
send motion/configuration commands, or substitute a raw serial implementation.
The installed r120 application is serial-only, so its reviewed mode verifies the
deployment/source evidence and does not require an inapplicable HTTP baseline.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from rocell.application.arrival_wizard_service import ArrivalWizardService
from rocell.application.wizard_diagnostic_export import WizardDiagnosticExporter,verify_export
from rocell.providers.windows.arm_transport_lock import arm_transport_lock
from rocell.providers.windows.arm_wifi_deadline import bounded_probe


R120_APP_SHA256 = '1b0589fa323a2714777f5c70453eeec6daa94bd8c92a481701689da82ce93fdc'
R120_SOURCE = Path('software/.firmware-tools/configured-diagnostic-candidate-r120/RoArm-M3_example')
R120_IMAGE = Path('software/.firmware-tools/build-configured-diagnostic-candidate-r120--default-4mb-no-psram/RoArm-M3_example.ino.bin')
R120_SESSION = Path('software/config/live_camera_feedback_session_20261015.json')
R120_JOURNAL = Path('software/runs/live-controller/app-r120-deployment-events.jsonl')


def verify_installed_r120_serial_only(workspace):
    """Verify the recorded installed app and that its source has no network path."""
    workspace = Path(workspace).resolve()
    session_raw = (workspace / R120_SESSION).read_bytes()
    session = json.loads(session_raw)
    installed = session['arm_baseline']['installed_firmware']
    if (installed.get('candidate'), installed.get('app_sha256'),
            installed.get('startup_motion_commands')) != ('r120', R120_APP_SHA256, 0):
        raise RuntimeError('Installed r120 session evidence differs')

    journal_raw = (workspace / R120_JOURNAL).read_bytes()
    events = [json.loads(line) for line in journal_raw.splitlines() if line.strip()]
    verified = [event for event in events if event.get('stage') == 'FLASH_VERIFIED']
    if len(verified) != 1 or verified[0].get('app_sha256') != R120_APP_SHA256 or \
            verified[0].get('protected_regions_unchanged') is not True:
        raise RuntimeError('Installed r120 deployment evidence differs')

    image = (workspace / R120_IMAGE).read_bytes()
    if hashlib.sha256(image).hexdigest() != R120_APP_SHA256:
        raise RuntimeError('Pinned r120 application image differs')
    source_paths = sorted((workspace / R120_SOURCE).glob('*'))
    sources = b'\n'.join(path.read_bytes() for path in source_paths if path.is_file())
    required = (b'Serial.begin(115200)', b'Serial1.begin(1000000',
                b'if(strcmp(line_,"{\\"T\\":105}")==0){emitFeedback();return;}')
    network_tokens = (b'#include <WiFi', b'WiFi.', b'WebServer', b'softAP', b'HTTPServer')
    if any(token not in sources for token in required) or any(token in sources for token in network_tokens):
        raise RuntimeError('Pinned r120 source is not the reviewed serial-only application')
    return {
        'candidate': 'r120',
        'app_sha256': R120_APP_SHA256,
        'deployment_journal_sha256': hashlib.sha256(journal_raw).hexdigest(),
        'session_record_sha256': hashlib.sha256(session_raw).hexdigest(),
        'network_transport': 'NOT_IMPLEMENTED_IN_APPLICATION',
        'usb_capture_policy': 'ZERO_WRITE_UNSOLICITED_ONLY',
    }


class ActionTracker:
    """Keep only references in the wrapper; raw evidence belongs to wizard exports.

    A polling timeout is not completion. Retain the exact operation handle so
    callers cannot start another action while the owner may still be running.
    """
    def __init__(self, service, record, *, clock=time.monotonic, sleep=time.sleep):
        self.service, self.record = service, record
        self.clock, self.sleep = clock, sleep
        self.pending_id = None

    def __call__(self, name, values):
        if self.pending_id is not None:
            raise RuntimeError('Unresolved operation; do not start another action')
        ticket = self.service.prepare_action(name, values, self.service.view()['revision'])
        # If dispatch raises, delivery is uncertain; keep a sentinel, not a false
        # idle state. Shutdown remains the owner's responsibility.
        self.pending_id = 'DISPATCH_UNCERTAIN'
        receipt = self.service.execute_action(ticket['ticket_id'])
        self.pending_id = receipt['operation_id']
        entry = dict(name=name, operation_id=self.pending_id, status='PENDING')
        self.record.setdefault('actions', []).append(entry)
        deadline = self.clock() + 60
        while self.clock() < deadline:
            operation = self.service.operation(self.pending_id)
            entry['status'] = operation['status']
            if operation['status'] not in ('QUEUED', 'RUNNING'):
                self.pending_id = None
                if operation['status'] != 'SUCCEEDED':
                    raise RuntimeError(name + ': ' + operation['status'])
                return operation
            self.sleep(.05)
        raise RuntimeError('Pending operation; do not retry')


def timed_probe():
    """Bracket HTTP in the USB collector's monotonic clock domain.

    Python 3.10 on Windows can use different clocks for perf_counter and
    monotonic. Keep the original transport timing, but never compare it directly
    to serial monotonic timestamps without an explicit common-clock bracket.
    """
    started = time.monotonic_ns()
    result = bounded_probe(retain_response=True)
    finished = time.monotonic_ns()
    result['host_monotonic_started_ns'] = started
    result['host_monotonic_finished_ns'] = finished
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standing-powered-clear-setup',action='store_true',required=True)
    parser.add_argument('--installed-r120-usb-only', action='store_true',
        help='Verify the installed serial-only r120 evidence and omit HTTP probes')
    args=parser.parse_args()
    workspace=Path(__file__).resolve().parents[2]
    service=ArrivalWizardService(workspace,mode='physical')
    record=dict(schema='rocell.usb_transport_capture.v2',setup_basis='USER_STANDING_POWERED_SECURED_CLEAR_ASSUMPTION',
                motion_commands=0,serial_command_writes_requested=0,
                transport_mode=('INSTALLED_R120_USB_ONLY' if args.installed_r120_usb_only
                                else 'LEGACY_USB_WITH_HTTP_BRACKET'))
    action = ActionTracker(service, record)
    try:
        with arm_transport_lock():
            if args.installed_r120_usb_only:
                record['installed_transport_evidence'] = verify_installed_r120_serial_only(workspace)
            else:
                record['http_before']=timed_probe()
                if record['http_before']['status']!='SUCCEEDED':raise RuntimeError('HTTP baseline unavailable')
            action('inventory_devices',dict(metadata_only=True))
            candidates=service.view()['device_selection']['devices']['SERIAL']['candidates']
            matches=[c for c in candidates if (c.get('vid'),c.get('pid'),c.get('unit_serial'))==
                ('10c4','ea60','52E4E1E8337FEF119E92181CEDD322A4')]
            if len(matches)!=1 or matches[0].get('identity_blockers'):raise RuntimeError('Exact USB unit unavailable')
            action('review_arm_candidate',dict(choice_id=matches[0]['choice_id'],reviewer_id='bench-identity-review',metadata_only=True))
            action('inspect_native_arm_metadata',dict(metadata_only=True))
            action('record_powered_arm_startup',dict(operator_id='user-standing-setup',adapter_on=True,
                usb_connected=True,secured_and_clear=True,stationary=True,startup_motion='unknown'))
            record['capture_started_ns']=time.perf_counter_ns()
            action('capture_powered_arm_telemetry',dict(firmware_unchanged=True))
            record['capture_finished_ns']=time.perf_counter_ns()
            if not args.installed_r120_usb_only:
                record['http_after']=timed_probe()
    except Exception as exc:
        record['error']=str(exc)
    finally:
        # Shutdown the owner before any further operation if capture is pending.
        pending = action.pending_id is not None
        record['unresolved_operation_id'] = action.pending_id
        if not pending:
            try:
                exported=action('export_logs',{})
                record['wizard_export']=exported['result']['receipt']['path']
            except Exception as exc:record['export_error']=str(exc)
        service.shutdown()
        exporter=WizardDiagnosticExporter((workspace/'software/runs/wizard-exports').resolve())
        exporter.prepare(create=True)
        receipt=exporter.export(dict(mode='usb-transport-diagnostic'),[],attachments={
            'usb-http-capture.json':json.dumps(record,allow_nan=False).encode()})
        assert verify_export(Path(receipt['path']).resolve())['valid']
        print(json.dumps(dict(export=receipt['path'],error=record.get('error'),wizard_export=record.get('wizard_export'),
            http_after_status=(record.get('http_after') or {}).get('status'))))


if __name__=='__main__':main()
