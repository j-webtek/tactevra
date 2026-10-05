# Stage F hardware session script

> **NOT AUTHORIZED FOR EXECUTION**
>
> Objective: type one reviewed short string. This script prepares and reviews one future attended
> attempt. It provides no physical controller command and cannot open a hardware
> transport. See [`SAFETY_PROCEDURES.md`](../SAFETY_PROCEDURES.md).

## Configuration and approval

- Consolidated configuration section SHA-256:
  `9e02b723b40637d04aa4c069216a031965416357b9ac358bb1468847f046d7fc`.
- Consolidated result receipt:
  `80a5d6ccb6af3555dc55f74473d5b8992b71bf6d056316a9559b6bb0e1f22041`.
- Table mode: **commissioned keyboard and stations installed**. Phone, tray, touch pad, and unrelated fixtures removed.
- Initial caps: speed no more than **2%** and verified torque/current no more
  than **5%**, further reduced by installed controller and manufacturer limits.
- Prior-stage rule: Passing A-E plus reviewed bounded string and recovery qualification required.
- Jack signs one attempt, the exact stage-F command-package hash, envelope
  hash, limits, operator, observer, E-stop receipt, and expiration time.
- Approval is void after any configuration/hardware change or failed/aborted prior stage.

## Setup and preconditions

- [ ] Operator and safety observer are named; exclusion zone is marked and clear.
- [ ] Safety glasses, secured clothing/hair, stable base, and gravity support are confirmed.
- [ ] The stage-F table configuration above matches photographs and hashes.
- [ ] The passive stylus is 110 mm overall with the measured 3 mm tip and no cable.
- [ ] The pre-session hardwired E-stop test passed and its receipt is attached.
- [ ] Installed collision profile, controller identity, firmware, limits, camera,
      measurements, and configuration epoch match the approval.
- [ ] Required prior-stage receipts are passing and unexpired.
- [ ] Logging destinations exist before any actuator power is considered.
- [ ] Jack's stage-F sign-off is present for exactly one attempt.

## Exact CPU and emulator commands

Run from the repository root in PowerShell. These commands are hardware read-only
and must finish before the physical-command slot is reviewed.

```powershell
$Stage = 'F'
$SessionRoot = Join-Path $PWD ('software/runs/first-motion-stage-' + $Stage.ToLower() + '-' + (Get-Date -Format 'yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Force -Path $SessionRoot | Out-Null
$env:PYTHONPATH = 'software/src;software/ai'
python -m pytest -q software/ai/tests/test_first_motion_consolidated.py
python -m rocell_ai.first_motion_consolidated `
  --fixture software/ai/sim/evidence/first_motion_consolidated_v1.json `
  --workspace . `
  --output (Join-Path $SessionRoot 'consolidated-result.json')
Get-FileHash -Algorithm SHA256 software/ai/sim/evidence/first_motion_consolidated_v1.json |
  Format-List | Out-File (Join-Path $SessionRoot 'fixture-hash.txt')
Get-FileHash -Algorithm SHA256 (Join-Path $SessionRoot 'consolidated-result.json') |
  Format-List | Out-File (Join-Path $SessionRoot 'result-hash.txt')
python -c "import json,pathlib,sys; d=json.loads(pathlib.Path(sys.argv[2]).read_text()); e=next(x for x in d['telemetry_envelopes'] if x['stage']==sys.argv[1]); pathlib.Path(sys.argv[3]).write_text(json.dumps(e,indent=2,sort_keys=True)+'\n'); print(e['envelope_sha256'])" $Stage (Join-Path $SessionRoot 'consolidated-result.json') (Join-Path $SessionRoot ('stage-' + $Stage + '-predicted-envelope.json'))
```

## Predicted envelope review

Compare every measured sample with `stage-F-predicted-envelope.json`. The
file contains 33 ordered samples and bounds derived from 14 synthetic plant
profiles. It is a review aid, not a physical tolerance. Before execution, replace
synthetic bounds with the measured plant envelope and bind it to Jack's approval.

Compare capture time and freshness; all six measured joints; direction,
monotonic progress, settling, and terminal state; independent observation; and
this planned action: one verified character at a time; stop between characters.

## Physical-command slot

`BLOCKED_NO_APPROVED_INSTALLED_STAGE_F_COMMAND_PACKAGE`

The existing first-motion staging/review pipeline must produce a single-action,
hash-bound package after physical measurements. This document intentionally does
not name a transport invocation or provide command bytes. A package may run only
through the reviewed host workflow after Jack's sign-off. Emulator bytes must
never be copied into a hardware transport.

## Pass and no-go decision

Pass only if the exact approved action completes once, every measured sample is
inside the separately accepted physical envelope, independent observation
agrees, and every log closes cleanly. Specific abort trigger: **first text/readback disagreement or recovery ambiguity**.

No-go on a missing checkbox, hash mismatch, stale evidence, failed E-stop test,
limit uncertainty, transport uncertainty, absent observer, unexpected contact,
or any common abort trigger. There is no automatic retry.

## Logged evidence

- signed approval and void-condition check;
- fixture, configuration, command-package, software commit, and envelope hashes;
- operator, observer, timestamps, E-stop receipt, table photographs, and limits;
- exact admitted command bytes when a future package exists;
- full measured telemetry with capture times and controller status;
- camera frames/video and independent observation result;
- stage-specific device/host events and partial output;
- pass, no-go, or abort decision with reason and final power-isolation state.
