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
receipt can justify rebuilding a newly numbered route-physics attempt. The
post-runtime receipt reviewer independently rebinds that receipt to ARM-292 and
ARM-293, verifies the exact seven-link/transform evidence and zero-authority
fields, and refuses review if the ARM-295 directory already exists. It imports
no Isaac or transport library and grants no attempt authority.

The next inert layer is also implemented: an ARM-295 lineage-plan builder binds
an accepted ARM-294 receipt review to the immutable ARM-289 terminal failure,
the corrected runtime-source inventory, and three distinct still-absent output
locations (attempt, EULA receipt, and memory receipt). A separate reviewer
re-hashes every input and source, statically rejects runtime/transport surfaces,
and grants only permission to construct a fresh-preflight-bound claimant. These
modules cannot run Isaac, accept authorization, claim an attempt, invoke a
backend, or authorize physical motion. No ARM-295 artifact can be materialized
until ARM-294 actually passes and its retained receipt is independently
accepted.

The claimant layer is now also implemented without materializing an ARM-295
artifact. It clones the proven fail-closed worker envelope to the new governed
output, pins the accepted plan/review and gate sources, and makes the legacy
ARM-253 worker statement an internal compatibility token rather than external
authority. Its independent reviewer verifies that exact ARM-295 authorization
and current-source checks precede EULA collection, memory collection, exclusive
receipt retention, single-use consumption, and one worker delegation. Runtime
construction still depends on real accepted ARM-294 evidence; the source alone
does not authorize or claim ARM-295.

## ARM-294 correction validation and ARM-295 handoff

On `2026-11-11`, the operator separately authorized exactly one ARM-294
zero-motion native link-inventory diagnostic. The diagnostic started Isaac Sim
6.1 once, initialized the pinned scene, observed the native articulation, and
shut down successfully. It retained
`PASS_NATIVE_LINK_INVENTORY_ZERO_MOTION` with the exact ordered links
`base_link`, `link1` through `link5`, and `gripper_link`, plus one transform
batch containing seven transforms. The receipt records zero physics steps,
zero timeline playback, zero joint positions or targets, zero trajectory
playback, zero key contact, and no hardware or physical authority. ARM-294 is
consumed and must not be rerun.

The non-starting receipt reviewer accepted that evidence and confirmed that the
future ARM-295 output remained absent. The plan, plan review, claimant, and
claimant review were then built from the accepted receipt without starting
Isaac or collecting live gates. Their retained raw file hashes are:

| Evidence | SHA-256 |
| --- | --- |
| `arm294-native-link-inventory-diagnostic-001/receipt.json` | `6f1fdd432f78a8bc138b6d1cd6930bcfd549ecbf934fc5dbfc7daf0261d06480` |
| `arm294-native-link-inventory-receipt-review-001/review.json` | `ce317154d7531c14e32f8decde0f0e66533bea39ba7e60e6c20f40582c8618c5` |
| `arm295-native-inventory-recovery-plan-001/plan.json` | `18d16e73086cfdd394b4c76ef55b395e1aa5ab9b009f2bf1f77122a5dd0a5dc5` |
| `arm295-native-inventory-recovery-plan-review-001/review.json` | `e56e3a175d8ee4a0e88c26bcf32e93fc35aa8d4fa9af6f25d926621f7b49eff9` |
| `arm295-native-inventory-recovery-claimant-001/claimant.json` | `25962ed86f9402e3072d0b6a7347aa0dea99dfe9b732705ad4145d134b546267` |
| `arm295-native-inventory-recovery-claimant-review-001/review.json` | `def24e590a0c240340bd7de410cc3fed854e240cd07e28ea4505b85477e84327` |

The accepted claimant review stops at
`SEPARATE_EXACT_ARM295_ONE_ATTEMPT_AUTHORIZATION`. The ARM-295 attempt,
fresh EULA receipt, and fresh memory receipt are still absent. Therefore this
evidence proves the native link correction and establishes a reproducible
fresh lineage, but it does not prove route physics, contact, key activation,
typing, or real-arm safety.
