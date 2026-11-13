# ARM-298 attempt postmortem

## Terminal outcome

ARM-298 was executed exactly once on 2026-11-13 under its separately supplied
one-attempt authorization. The fresh EULA and memory gates passed, Isaac Sim
6.1 started successfully, and the pinned scene reached backend execution. The
attempt then failed closed before producing a route-physics result because the
restricted articulation wrapper did not expose the wrapped Isaac
`set_dof_positions` method required by conservative native sweep evaluation.

The retained terminal status is `FAILED_RETAINED_NO_RETRY` at
`execute_backend`, with an `AttributeError` reporting that
`IsaacArticulationLinkView` has no `set_dof_positions`. No automatic retry
occurred. The attempt granted no trajectory playback, hardware access, or
physical authority. Its authorization is consumed and ARM-298 must not be
rerun.

## Retained evidence

| Artifact | SHA-256 |
| --- | --- |
| `arm298-nominal-route-physics-attempt-001/status.json` | `959e0a7c840f1b742ea479abe7cc65944d0aaa630724b7346e13a3a21d240a2c` |
| `arm298-nominal-route-physics-eula-preflight-001/receipt.json` | `a1d1b4b1f7755b87436bcaf525a83eaa90966a3225f68eb2eaceb5f91061e79e` |
| `arm298-nominal-route-physics-memory-preflight-001/receipt.json` | `5d23aadc19a190e6315245c76840cc455f2a1fe0c91788a2336f3db92ce1dd3b` |

The EULA receipt records observed acceptance and admitted launch. The memory
receipt records passing physical-memory, commit-availability, and commit-ratio
checks. The attempt status records exactly one attempt, no automatic retry,
and both hardware and physical authority as false. No matching Isaac process
remained after shutdown.

## Root cause and correction

`IsaacInertSmokeDriver` intentionally returns an
`IsaacArticulationLinkView` rather than exposing the full experimental Isaac
articulation to downstream runtime composition. The wrapper forwarded DOF and
link names and native link transforms, but omitted the one mutation required
by `NativeIsaacConservativeSweepBinding`: teleporting a candidate joint row
before reading its link transforms. The wrapped Isaac 6.1 experimental
`Articulation` does provide `set_dof_positions`; the failure was therefore in
our capability-restricted adapter rather than in Isaac itself.

The correction adds an explicit `set_dof_positions` delegation to that
wrapper. It does not broaden the wrapper to arbitrary Isaac methods. Unit
coverage proves the exact row is forwarded and that a missing native setter
fails closed with a typed integration error.

## Forward boundary

The correction does not authorize another simulation and does not establish a
successful route, contact, key activation, typing, or real-arm safety result.
Any later route-physics attempt must use a newly numbered lineage that pins and
independently reviews the corrected adapter, uses fresh output and preflight
directories, and requires its own exact one-attempt authorization. ARM-298 and
the retained evidence above remain immutable.
