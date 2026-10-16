"""Offline wrapper tests: never acquire a port or send a robot command."""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

from rocell.application.wizard_diagnostic_export import WizardDiagnosticExporter, verify_export

SPEC = importlib.util.spec_from_file_location(
    'bench_usb_http_capture', Path(__file__).resolve().parents[2] / 'scripts/bench_usb_http_capture.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Service:
    def __init__(self, status='SUCCEEDED'):
        self.status = status
        self.dispatches = 0
        self.handles = []

    def view(self):
        return {'revision': 1}

    def prepare_action(self, *args):
        return {'ticket_id': 'ticket'}

    def execute_action(self, ticket):
        self.dispatches += 1
        return {'operation_id': 'same-operation'}

    def operation(self, handle):
        self.handles.append(handle)
        return {'status': self.status, 'result': {'large': list(range(20000))}}


def test_large_native_result_not_duplicated_in_wrapper(tmp_path):
    record = {}
    action = MODULE.ActionTracker(Service(), record)
    result = action('capture', {})
    assert len(result['result']['large']) == 20000
    assert record['actions'] == [dict(name='capture', operation_id='same-operation', status='SUCCEEDED')]
    exporter = WizardDiagnosticExporter(tmp_path.resolve())
    exporter.prepare(create=True)
    receipt = exporter.export({'mode': 'offline-test'}, [], attachments={
        'usb-http-capture.json': json.dumps(record).encode()})
    assert verify_export(Path(receipt['path']).resolve())['valid']
    assert action.pending_id is None


def test_terminal_failure_is_retained_without_raw_result():
    record = {}
    action = MODULE.ActionTracker(Service('FAILED'), record)
    with pytest.raises(RuntimeError, match='FAILED'):
        action('capture', {})
    assert action.pending_id is None
    assert record['actions'][0]['status'] == 'FAILED'
    assert 'result' not in record['actions'][0]


def test_timeout_preserves_handle_and_blocks_new_action():
    ticks = iter([0, 0, 61])
    service = Service('RUNNING')
    action = MODULE.ActionTracker(service, {}, clock=lambda: next(ticks), sleep=lambda _: None)
    with pytest.raises(RuntimeError, match='Pending operation'):
        action('capture', {})
    assert action.pending_id == 'same-operation'
    with pytest.raises(RuntimeError, match='Unresolved operation'):
        action('export_logs', {})
    assert service.dispatches == 1
    assert service.handles == ['same-operation']


def test_poll_error_does_not_infer_completion():
    service = Service()
    def fail(_):
        raise OSError('poll unavailable')
    service.operation = fail
    action = MODULE.ActionTracker(service, {})
    with pytest.raises(OSError):
        action('capture', {})
    assert action.pending_id == 'same-operation'


def test_dispatch_exception_remains_uncertain():
    service = Service()
    def fail(_):
        raise OSError('dispatch unavailable')
    service.execute_action = fail
    action = MODULE.ActionTracker(service, {})
    with pytest.raises(OSError):
        action('capture', {})
    assert action.pending_id == 'DISPATCH_UNCERTAIN'


def test_http_has_explicit_serial_clock_bracket(monkeypatch):
    ticks = iter([100, 200])
    monkeypatch.setattr(MODULE.time, 'monotonic_ns', lambda: next(ticks))
    monkeypatch.setattr(MODULE, 'bounded_probe', lambda **kw: {
        'status': 'SUCCEEDED', 'request_started_monotonic_s': 999.0})
    result = MODULE.timed_probe()
    assert result['host_monotonic_started_ns'] == 100
    assert result['host_monotonic_finished_ns'] == 200
    assert result['request_started_monotonic_s'] == 999.0


def write_r120_evidence(root, monkeypatch, *, source_suffix=b''):
    image = b'pinned-r120-test-image'
    digest = hashlib.sha256(image).hexdigest()
    monkeypatch.setattr(MODULE, 'R120_APP_SHA256', digest)
    session = {'arm_baseline': {'installed_firmware': {
        'candidate': 'r120', 'app_sha256': digest, 'startup_motion_commands': 0}}}
    paths = {
        MODULE.R120_SESSION: json.dumps(session).encode(),
        MODULE.R120_JOURNAL: (json.dumps({'stage': 'FLASH_VERIFIED',
            'app_sha256': digest, 'protected_regions_unchanged': True}) + '\n').encode(),
        MODULE.R120_IMAGE: image,
        MODULE.R120_SOURCE / 'RoArm-M3_example.ino': (
            b'Serial.begin(115200); Serial1.begin(1000000,mode,18,19); '
            b'if(strcmp(line_,"{\\"T\\":105}")==0){emitFeedback();return;}' + source_suffix),
    }
    for relative, data in paths.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return digest


def test_installed_r120_serial_only_evidence_is_explicit(tmp_path, monkeypatch):
    digest = write_r120_evidence(tmp_path, monkeypatch)
    result = MODULE.verify_installed_r120_serial_only(tmp_path)
    assert result['app_sha256'] == digest
    assert result['network_transport'] == 'NOT_IMPLEMENTED_IN_APPLICATION'
    assert result['usb_capture_policy'] == 'ZERO_WRITE_UNSOLICITED_ONLY'


def test_installed_r120_evidence_rejects_network_enabled_source(tmp_path, monkeypatch):
    write_r120_evidence(tmp_path, monkeypatch, source_suffix=b' WiFi.begin();')
    with pytest.raises(RuntimeError, match='not the reviewed serial-only'):
        MODULE.verify_installed_r120_serial_only(tmp_path)
