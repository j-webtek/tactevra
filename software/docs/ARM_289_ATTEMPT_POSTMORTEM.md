# ARM-289 retained attempt postmortem

## Outcome

The single authorized ARM-289 attempt was consumed on `2026-11-11` at
`C:\IsaacSim\artifacts\issue190\arm289-nominal-route-physics-attempt-001`.
Both fresh launch gates passed, Isaac Sim 6.1 started on GPU 0, loaded the
pinned workcell, initialized physics, and reached native runtime construction.
The attempt then failed closed before route execution with this terminal
status:

```json
{"attempt_count":1,"automatic_retry":false,"error_message":"native articulation link inventory changed","error_stage":"construct_runtime","error_type":"NativeSweepBindingError","hardware_access":false,"physical_authority":false,"status":"FAILED_RETAINED_NO_RETRY"}
```

No route result, joint targets, trajectory playback, key contact, hardware
access, or physical movement occurred. ARM-289 is consumed and must never be
retried.

## Retained evidence

| Evidence | SHA-256 |
| --- | --- |
| `arm289-nominal-route-physics-attempt-001/status.json` | `6b95004208e946df5417ef617a3b09b6ea858399ebd05102f72785df1931494c` |
| `arm289-eula-preflight-001/receipt.json` | `a1d1b4b1f7755b87436bcaf525a83eaa90966a3225f68eb2eaceb5f91061e79e` |
| `arm289-memory-preflight-001/receipt.json` | `df6e9cf9eaddf3b27c3690dbbfc8b2c27ce93e8257cbe1f199331305571eb1a` |
| `arm289-launch-console-003.log` | `7f23aa342655e95a058186f683751eae7c9ce17963f5f9261a86224c495660ef` |
| Isaac Kit log `kit_20261111_072404.log` | `ffba673d003c42bb347f3843d5819bb946372a53ac3d556755a117f1790fa9b4` |

The EULA receipt observed the operator-provided acceptance without accepting
terms itself. The memory receipt retained 107,045,990,400 available physical
bytes, 114,133,450,752 available commit bytes, and 0.2168 commit utilization.
Neither gate claimed an attempt or granted hardware or physical authority.

The ARM-287 terminalization correction worked as intended: the exact failure
stage and exception were atomically retained before Isaac shutdown. The Kit
log records successful application startup and clean shutdown, and the worker
status is terminal rather than pending.

## Root cause

`NativeIsaacConservativeSweepBinding` requires the articulation adapter to
expose both `dof_names` and `link_names`. The real Isaac experimental
`Articulation` provides both properties, but `IsaacArticulationLinkView`
forwarded only `dof_names` and `get_link_transforms`. Consequently,
`getattr(articulation, "link_names", ())` produced an empty inventory during
runtime construction even though the native articulation contained the
expected links.

The retained concrete-attempt binding also still loaded the superseded
ARM-274 integration document. The corrected runtime class expects the ARM-287
v2 terminalization schema, so launch required external redirection to the
already reviewed ARM-287 document. This did not consume an attempt during
preflight, but it must be corrected before another governed lineage is built.

## Correction and next gate

The correction forwards `link_names` from the native Isaac articulation and
adds a regression assertion beside the existing DOF and transform-view
assertions. The concrete attempt binding now pins and loads the reviewed
ARM-287 integration directly, eliminating launch-time redirection.

These changes do not authorize another route attempt. The corrected sources
must pass tests, be independently reviewed, and be used to rebuild all affected
source hashes and binding evidence. A future attempt requires a new identifier,
a new output directory, fresh EULA and memory receipts, and a new exact
one-attempt authorization. ARM-289 and its retained evidence remain immutable.

The correction subsequently merged after the full local and cross-platform
suite. ARM-292 now binds the corrected source to an exact seven-link inventory,
and ARM-293 independently verifies that its runtime contains no physics step,
settle, joint/trajectory, route-worker, retry, hardware, or physical-authority
surface. Their retained request and review are inert. The next runtime gate is
one separately authorized ARM-294 zero-motion observation; only a passing
receipt can justify rebuilding a newly numbered route-physics attempt.
