"""Generate separate, source-verified owner-handoff candidate; never upload it."""
import hashlib
import argparse
import json
from pathlib import Path


def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Candidate patch anchor mismatch')
    return text.replace(old,new,1)


def integrate_baseline_scan(outputs):
    """Patch only a separate candidate; leave approved r2 source untouched."""
    owner = outputs['configured_native_owner.h'].decode()
    owner += '''
#include "baseline_only_owner.h"
rocell_diag::DiagnosticSessionClaim rocellSessionClaim;
using RocellBaselineOwner=rocell_diag::BaselineOnlyOwner<SMS_STS,RocellConfiguredClock>;
RocellBaselineOwner* rocellBaselineOwner=nullptr;
void initializeBaselineOwner(){
  static RocellBaselineOwner owner(st,rocellConfiguredClock,rocellSessionClaim,rocellDiagnosticInstance);
  rocellBaselineOwner=&owner;
}
void pollBaselineOwner(){if(rocellBaselineOwner)rocellBaselineOwner->poll();}
'''
    outputs['configured_native_owner.h'] = owner.encode()
    routes = outputs['configured_diagnostic_routes.h'].decode()
    routes = replace_once(routes,
        '  if(rocellChallengeAttempted)return rocellChallengeJson[0]!=0;',
        '  if(rocellChallengeAttempted)return rocellChallengeJson[0]!=0;\n'
        '  if(!rocellSessionClaim.claim(rocell_diag::DiagnosticClaim::Motion))return false;')
    outputs['configured_diagnostic_routes.h'] = routes.encode()
    http = outputs['diagnostic_http.h'].decode()
    http = replace_once(http, '#include "diagnostic_session.h"',
        '#include "diagnostic_session.h"\n#include "baseline_only_routes.h"')
    http = replace_once(http, '  registerConfiguredChallengeRoute();',
        '  initializeBaselineOwner();\n'
        '  rocell_diag::register_baseline_only_routes(server,*rocellBaselineOwner);\n'
        '  registerConfiguredChallengeRoute();')
    outputs['diagnostic_http.h'] = http.encode()
    boot = outputs['diagnostic_boot.h'].decode()
    boot = replace_once(boot, '    rocellConfiguredRuntime.poll();',
        '    pollBaselineOwner();\n    rocellConfiguredRuntime.poll();')
    outputs['diagnostic_boot.h'] = boot.encode()


def integrate_startup_mode(outputs):
    """Separate startup-only candidate; no implicit normal-policy fallback."""
    owner=outputs['configured_native_owner.h'].decode()
    owner=replace_once(owner, '#include "configured_diagnostic_runtime.h"',
                       '#include "configured_startup_runtime.h"')
    owner=replace_once(owner, 'rocell_diag::ConfiguredDiagnosticRuntime<',
                       'rocell_diag::ConfiguredStartupRuntime<')
    outputs['configured_native_owner.h']=owner.encode()
    routes=outputs['configured_diagnostic_routes.h'].decode()
    routes=replace_once(routes, '"/rocell-diagnostics.json"', '"/rocell-startup.json"')
    routes=replace_once(routes, '"/rocell-diagnostics.key"', '"/rocell-startup.key"')
    outputs['configured_diagnostic_routes.h']=routes.encode()


def integrate_pair_mode(outputs):
    """Hold-first finite pair candidate; no changes to installed hold-only r7."""
    owner=outputs['configured_native_owner.h'].decode()
    owner=replace_once(owner,'bool rocellRejectDiagnosticInterference(){',
        '#include "configured_pair_board.h"\nbool rocellRejectDiagnosticInterference(){')
    owner=replace_once(owner,'  rocellConfiguredRuntime.interference();return true;',
        '  rocellConfiguredRuntime.interference();rocellPairRuntime.interference();return true;')
    outputs['configured_native_owner.h']=owner.encode()
    routes=outputs['diagnostic_http.h'].decode()
    routes=replace_once(routes,'void registerDiagnosticRoutes(){','void registerHoldDiagnosticRoutes(){')
    outputs['diagnostic_http.h']=(routes+'\n#include "configured_pair_board_routes.h"\n').encode()
    boot=outputs['diagnostic_boot.h'].decode()
    boot=replace_once(boot,
        '    rocellConfiguredRuntime.poll();\n    // A slow read-only HTTP client must not hold up finite bus acquisition.\n'
        '    if(!rocellConfiguredRuntime.exclusive_work())server.handleClient();',
        '    rocell_diag::poll_hold_pair_diagnostics(rocellConfiguredRuntime,rocellPairRuntime,server);')
    outputs['diagnostic_boot.h']=boot.encode()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport',action='store_true',help='Separate read-only diagnostic transport candidate')
    parser.add_argument('--received',action='store_true',help='Integrated internal receipt/session candidate; no start route')
    parser.add_argument('--diagnostic-boot',action='store_true',help='Separate diagnostic-only startup; no legacy command ingress')
    parser.add_argument('--configured',action='store_true',help='Separate configured/authenticated runtime candidate; never upload')
    parser.add_argument('--configured-revision',type=int,default=0,help='New immutable configured candidate revision (1–9999)')
    parser.add_argument('--baseline-scan',action='store_true',help='Integrate exclusive baseline scan into a new configured revision')
    parser.add_argument('--startup-mode',action='store_true',help='Separate startup-only runtime and configuration paths; never upload')
    parser.add_argument('--hold-mode',action='store_true',help='Separate hold-only board composition; never upload')
    parser.add_argument('--pair-mode',action='store_true',help='Explicit hold-first pair composition; requires hold-mode; never upload')
    args=parser.parse_args()
    if args.pair_mode and not args.hold_mode:
        parser.error('Pair mode requires hold-mode in a new configured revision')
    if args.hold_mode and (not args.configured or not args.configured_revision or args.baseline_scan or args.startup_mode):
        parser.error('Hold mode requires a configured revision without baseline or startup mode')
    if args.startup_mode and not args.baseline_scan:
        parser.error('Startup mode requires exclusive baseline-scan composition')
    if args.baseline_scan and (not args.configured or not args.configured_revision):
        parser.error('Baseline scan requires a separate configured revision')
    if args.configured_revision and (not args.configured or not 1<=args.configured_revision<=9999):
        parser.error('A revision from 1 to 9999 requires --configured')
    if args.configured:args.diagnostic_boot=True
    if args.diagnostic_boot:args.received=True
    if args.received:args.transport=True
    root=Path(__file__).resolve().parents[1];tools=root/'.firmware-tools'
    manifest=json.loads((tools/'reference-build-inputs.json').read_text())
    source=tools/'reference/RoArm-M3_example'
    target='baseline-candidate' if args.received else 'transport-v2-candidate' if args.transport else 'owner-candidate'
    if args.diagnostic_boot:target='diagnostic-boot-candidate'
    if args.configured:target='configured-diagnostic-candidate'
    if args.configured_revision:target+=f'-r{args.configured_revision}'
    destination=tools/target/'RoArm-M3_example'
    outputs={}
    for path in source.iterdir():
        if path.suffix not in ('.h','.ino'):continue
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=manifest['files'][str(path.relative_to(tools))]:
            raise ValueError('Reference source changed')
        text=raw.decode('utf-8-sig').replace('\r\r\n','\n').replace('\r\n','\n')
        if path.name=='esp_now_ctrl.h':
            start=text.index('void OnDataRecv(')
            end=text.index('void initEspNow()',start)
            text=text[:start]+'#include "espnow_owner.h"\n\n'+text[end:]
        elif path.name=='uart_ctrl.h':
            anchor='int cmdType = jsonCmdReceive["T"].as<int>();'
            text=replace_once(text,anchor,anchor+'''
    if (rocellOwnerFault() && cmdType!=CMD_EMERGENCY_STOP) {
      jsonInfoHttp.clear();
      jsonInfoHttp["error"]="ROCELL_OWNER_FAULT";
      return;
    }''')
            if args.received:
                text=replace_once(text,anchor,anchor+'''
    if (rocellRejectDiagnosticInterference() && cmdType!=CMD_EMERGENCY_STOP) {
      jsonInfoHttp.clear();jsonInfoHttp["error"]="ROCELL_DIAGNOSTIC_OWNED";
      return;
    }''')
        elif path.name=='http_server.h' and args.transport:
            text=replace_once(text,'WebServer server(80);','WebServer server(80);\n#include "diagnostic_http.h"')
            text=replace_once(text,'void webCtrlServer(){','void webCtrlServer(){\n  registerDiagnosticRoutes();')
        elif path.suffix=='.ino':
            text=replace_once(text,'void loop() {','void loop() {\n  processEspNowOwner();')
            text=replace_once(text,'  unsigned long curr_time = millis();',
                '  if (rocellOwnerFault()) return;\n  unsigned long curr_time = millis();')
            if args.received:
                text=replace_once(text,'#include "RoArm-M3_module.h"',
                    '#include "RoArm-M3_module.h"\n#include "native_diagnostic_owner.h"')
                text=replace_once(text,'  if (rocellOwnerFault()) return;',
                    '  if (rocellDiagnosticOwned) { pollReceivedDiagnostic(); return; }\n  if (rocellOwnerFault()) return;')
        if args.diagnostic_boot and path.suffix=='.ino':
            text=text[:text.index('void setup() {')]+'#include "diagnostic_boot.h"\n'
        outputs[path.name]=text.encode()
    for name in ('callback_handoff.h','espnow_owner.h'):
        outputs[name]=(root/'firmware/diagnostics'/name).read_bytes()
    if args.transport:
        for name in ('diagnostic_http.h','diagnostic_status_json.h','diagnostic_session.h','evidence_store.h',
                     'reference_write_capture.h','reference_read_adapter.h',
                     'command_capture.h','servo_evidence.h','servo_evidence_json.h'):
            outputs[name]=(root/'firmware/diagnostics'/name).read_bytes()
    if args.received:
        for name in ('native_diagnostic_owner.h','reference_elbow_admission.h','received_session.h','diagnostic_receipt.h','fresh_elbow_baseline.h'):
            outputs[name]=(root/'firmware/diagnostics'/name).read_bytes()
    if args.diagnostic_boot:
        outputs['diagnostic_boot.h']=(root/'firmware/diagnostics/diagnostic_boot.h').read_bytes()
    if args.configured:
        for header in (root/'firmware/diagnostics').glob('*.h'):
            outputs[header.name]=header.read_bytes()
        name='RoArm-M3_example.ino'
        outputs[name]=replace_once(outputs[name].decode(),'#include "native_diagnostic_owner.h"',
            '#include "configured_native_owner.h"').encode()
    if args.baseline_scan:integrate_baseline_scan(outputs)
    if args.startup_mode:integrate_startup_mode(outputs)
    if args.hold_mode:
        # Replace the selected composition, not the existing runtime sources.
        # The diagnostic-only setup/loop never initializes legacy ingress.
        outputs['configured_native_owner.h']=outputs['configured_hold_owner.h']
        outputs['diagnostic_http.h']=outputs['configured_hold_routes.h']
    if args.pair_mode:integrate_pair_mode(outputs)
    destination.mkdir(parents=True,exist_ok=True)
    # Regeneration never destroys hand edits. Use a distinct directory for revisions.
    for name,raw in outputs.items():
        path=destination/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('Candidate file differs; refusing overwrite')
    for name,raw in outputs.items():
        path=destination/name
        if not path.exists():
            with path.open('xb') as stream:stream.write(raw)
    print(json.dumps(dict(candidate=str(destination),files=len(outputs),
        hashes={name:hashlib.sha256(raw).hexdigest() for name,raw in outputs.items()},deployable=False)))


if __name__=='__main__':main()
