"""Compile and export evidence for named firmware targets. Never upload or open a port."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import re
from rocell.application.first_motion_contract import canonical
from rocell.application.wizard_diagnostic_export import WizardDiagnosticExporter,verify_export


BUILD_PROFILES = {
    'legacy-huge-app': 'esp32:esp32:esp32:PartitionScheme=huge_app,PSRAM=enabled',
    'default-4mb-no-psram': 'esp32:esp32:esp32:PartitionScheme=default,PSRAM=disabled',
}


def build_settings(tools, target, profile):
    """Keep compatibility-review binaries separate from earlier audited builds."""
    fqbn = BUILD_PROFILES[profile]
    suffix = '' if profile == 'legacy-huge-app' else '--' + profile
    return tools / ('build-' + target + suffix), fqbn


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target')
    parser.add_argument('--profile', choices=BUILD_PROFILES, default='legacy-huge-app')
    args=parser.parse_args()
    allowed=('probe','reference','owner-candidate','transport-candidate','transport-v2-candidate',
        'received-candidate','baseline-candidate','diagnostic-boot-candidate','configured-diagnostic-candidate')
    if args.target not in allowed and not re.fullmatch(r'configured-diagnostic-candidate-r[1-9][0-9]{0,3}',args.target):
        parser.error('Unknown compile target')
    root=Path(__file__).resolve().parents[1];tools=root/'.firmware-tools'
    cli=tools/'cli-1.5.1/arduino-cli.exe'
    local_config=tools/'arduino-cli.local.yaml'
    config=local_config if local_config.is_file() else root/'firmware/arduino-cli.yaml'
    sketch=root/'firmware/compile_probe' if args.target=='probe' else tools/args.target/'RoArm-M3_example'
    build,fqbn=build_settings(tools,args.target,args.profile)
    command=[str(cli),'compile','--fqbn',fqbn,'--config-file',str(config),
        '--build-path',str(build),'--jobs','2',str(sketch)]
    if args.target=='probe':
        # ESP32 3.0.7 puts -c in extra_flags: preserve it when adding an include.
        command.extend(['--build-property',
            'compiler.cpp.extra_flags=-MMD -c -I'+str(root/'firmware/diagnostics').replace('\\','/')])
    result=subprocess.run(command,capture_output=True,text=True,timeout=300)
    listing=subprocess.run([str(cli),'lib','list','--config-file',str(config)],
        capture_output=True,text=True,check=True,timeout=30)
    platforms=subprocess.run([str(cli),'core','list','--config-file',str(config)],
        capture_output=True,text=True,check=True,timeout=30)
    # Never inventory old binaries as successful outputs of a failed build.
    artifacts={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in build.glob('*.bin')} if result.returncode==0 else {}
    inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in (sketch,root/'firmware/diagnostics') for p in folder.iterdir()
        if p.suffix in ('.ino','.h','.cpp')}
    report=dict(schema='rocell.firmware_compile_review.v1',target=args.target,
        status='COMPILED' if result.returncode==0 else 'FAILED',exit_code=result.returncode,
        command=command,fqbn=fqbn,build_profile=args.profile,source_hashes=inputs,artifact_hashes=artifacts,
        installed_libraries=listing.stdout,installed_platforms=platforms.stdout,
        cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),
        reference_input_manifest_sha256=hashlib.sha256((tools/'reference-build-inputs.json').read_bytes()).hexdigest(),
        servo_read_source_sha256=hashlib.sha256((tools/'user/libraries/SCServo/SCS.cpp').read_bytes()).hexdigest(),
        toolchain_lock_sha256=hashlib.sha256((root/'firmware/toolchain.lock.json').read_bytes()).hexdigest(),
        hardware_access=False,firmware_uploaded=False,deployable=False)
    exporter=WizardDiagnosticExporter(root/'runs/wizard-exports');exporter.prepare(create=True)
    receipt=exporter.export({'mode':'compile-only-review'},[],attachments={
        'compile-review.json':canonical(report),
        'compile-output.txt':(result.stdout+'\n'+result.stderr).encode()})
    if not verify_export(Path(receipt['path']))['valid']:raise ValueError('Build evidence export failed')
    print(json.dumps(dict(status=report['status'],export=receipt['path'],verified=True,artifacts=artifacts)))


if __name__=='__main__':main()
