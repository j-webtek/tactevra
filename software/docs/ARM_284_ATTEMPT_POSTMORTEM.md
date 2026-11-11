# ARM-284 retained attempt postmortem

## Outcome

The single authorized ARM-284 attempt was consumed at
`2026-11-11T02:53:18Z`. Both launch gates passed and Isaac Sim started on GPU
0, opened the pinned robot USD, and created the PhysX simulation views. The
attempt did not produce a route result. Its claimed directory remains unchanged
with only the original nonterminal `status.json`:

```json
{"attempt_count":1,"automatic_retry":false,"hardware_access":false,"physical_authority":false,"status":"ATTEMPT_CLAIMED_BACKEND_PENDING"}
```

This is a consumed, incomplete attempt. It must not be retried or interpreted
as a passing simulation.

## Retained evidence

| Evidence | SHA-256 |
| --- | --- |
| `arm284-nominal-route-physics-attempt-001/status.json` | `888e31f169a178ecff5ee75685222c8a31c90d5589a0460896e24a69bc22cc49` |
| `arm287-eula-preflight-001/receipt.json` | `a1d1b4b1f7755b87436bcaf525a83eaa90966a3225f68eb2eaceb5f91061e79e` |
| `arm287-memory-preflight-001/receipt.json` | `d936a357d3bbc36d29470b69209c157e4a632b27a5d50d1850d58e82cc29c338` |
| Isaac Kit log `kit_20261110_215320.log` | `2aca471190b94c4a1572abaf5f6c5cbff76a8897a0acebb20ce48394312cbd6c` |

The EULA receipt observed `OMNI_KIT_ACCEPT_EULA=YES` without accepting terms
itself. The memory receipt reported 75,956,498,432 available physical bytes,
173,948,747,776 available commit bytes, and 0.2950 commit utilization. Neither
gate claimed an attempt or granted hardware or physical authority.

The Kit log records successful application startup, successful opening of the
pinned USD, CUDA device 0 selection, and creation of PhysX simulation views.
It then records a clean `SimulationApp.close()` sequence, with no traceback in
the Kit log and no remaining Isaac process.

## Root cause

`OneAttemptNativeBackend` originally called `session.shutdown()` in a `finally`
block. An exception after Isaac startup entered that `finally` block before the
outer worker could replace the pending claim with terminal failure evidence.
Isaac's `SimulationApp.close()` can terminate the host process during shutdown,
so control never returned to the worker. This left the attempt directory in the
claimed-pending state and concealed the precise failing phase.

## Correction and next gate

ARM-287 updates the native backend to record an atomic
`FAILED_RETAINED_NO_RETRY` status,
including the failing lifecycle phase and exception, before it invokes session
shutdown. A regression test models a shutdown that never returns normally and
proves that the terminal failure already exists when shutdown begins.

ARM-288 independently checks the corrected source without importing or starting
Isaac. It requires the failure receipt's atomic replacement to precede the
finally-guarded shutdown and continues to reject attempt-claim, joint-command,
physics-step, simulator-import, and hardware surfaces.

This correction and review do not authorize another launch. Because ARM-287
changes a reviewed runtime source, all affected hashes and review lineage must
be rebuilt.
A future attempt requires a new identifier, a fresh output directory, fresh
EULA and memory receipts, an independent review of the corrected source, and a
new exact one-attempt authorization. ARM-284 remains immutable and consumed.

