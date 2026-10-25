# Powered feedback wizard rehearsal

Implemented and tested: 2026-09-12. This is **simulated connection testing**,
not a live connection to the received RoArm-M3 Pro.

## Developer and operator workflow

1. Start the existing wizard explicitly in rehearsal mode. Leave physical
   devices untouched; this action does not access them.
2. In Arm, choose **Rehearse powered feedback (no hardware)**.
3. Select one scenario, review its preview, then execute it.
4. Inspect the result and use **Export logs** to save evidence to the assigned
   workspace export folder. Export after each scenario if all runs are needed.
5. Repeat with another scenario. Only the latest complete powered-feedback
   rehearsal original is pinned in memory independently of rotating UI cards.
   Closing the wizard before exporting loses that full in-memory original.

The shared action definition supplies browser and terminal forms. This action is
disabled in physical mode; changing mode is not a way to activate native I/O.

| Scenario | Expected operation | Meaning |
| --- | --- | --- |
| nominal | SUCCEEDED | One synthetic T105 write, complete reply, confirmed cleanup |
| stale-input | FAILED | Input predates request; retained, no query written |
| incomplete-reply | FAILED | T1051 lacks required pose/voltage fields |
| short-write | FAILED | Partial write; no retry |
| cleanup-unknown | FAILED | Resource cleanup not confirmed |

Expected failure scenarios deliberately report FAILED, not a successful live
connection. All physical effect counters remain zero. Simulated write bytes and
cleanup are separately labeled. The displayed original SHA-256 identifies the
full retained JSON, not the exported wrapper file.

## How components connect

`wizard_actions.py` defines the closed scenario choices. The service dispatches
`wizard_powered_feedback_rehearsal.run_rehearsal`, which constructs synthetic
metadata and intent bound to the current session/source/operation. It calls
`powered_feedback_observation.observe_rehearsal` with the exact incapable API.
That function exercises the existing non-purging serial lifecycle and shared
feedback parser. The service keeps a compact result for display and pins original
bytes before final publication/source checks, preserving failed observations.

`attachment-powered-feedback-rehearsal.json` contains an `original_base64` wrapper
so export formatting does not change the original bytes. Decode it, hash the
decoded bytes, and compare with the displayed `original_sha256`. The decoded
document contains the intent, scenario, observation, raw received-byte records,
errors and lifecycle/resource accounting. Ordinary diagnostic exports still
include their manifest and integrity verification.

The synthetic review hashes are labeled test inputs; they are not installed
firmware evidence or approved physical runtime evidence. No native worker,
physical safety acceptance or motion permit is created by this action.

## Verification and remaining work

178 tests passed in 23.72 seconds in
`software/runs/pytest-powered-feedback-wizard-20260912-03`, covering this public
action/export, action catalog, powered setup, general wizard service, native
metadata integration and memory feedback lifecycle. Tests verify the five
scenarios, physical-mode rejection, export integrity, original-byte preservation
and retention after ten notes rotate result cards. Host device access is forbidden
in the new public-action tests. These are automated service-level tests; a manual
browser interaction test has not been performed for this increment.

Initial export verification caught JSON reformatting changing original hashes;
the explicit base64 wrapper fixed that without weakening hash verification.

Still needed: reviewed powered admission, durable one-use live attempt records,
supervised native feedback worker, its wizard action and received-unit test.
Firmware-change history is still awaiting operator response. Camera-to-board,
arm-to-board and tool calibration, bounded movement, keyboard contact and phone
tapping remain separate unfinished physical milestones.

## Durable powered attempt storage increment

`application/powered_feedback_attempt_store.py` now supplies the parent journal
for the upcoming supervised live-feedback coordinator. This is implemented
storage infrastructure, **not yet connected to a live wizard action**.

1. Construct `PoweredFeedbackAttemptJournal` from associated originals. It
   reopens the startup record and reconstructs the full metadata/review join;
   constructing a `PreparedPoweredFeedback` dataclass alone cannot bypass that
   validation. An immutable prepared file retains the exact intent and originals.
2. Call `consume` only after independent physical admission. It checks current
   source, original startup freshness and prepared-file integrity again. It then
   reserves the final consumed filename before writing, verifies readback and
   returns a diagnostic receipt. Any failure burns the instance. A partial
   consumed file stays occupied and cannot be overwritten for another attempt.
3. The future supervisor must retain raw process stdout/stderr through
   `retain_outcome`, including malformed output, cancellation and timeouts.
   Process success explicitly does not establish device cleanup. Outcome
   publication is one-use and bounded; a failed publication must not be retried
   as a successful device operation.
4. `collect_attempt` reads only the exact operation's prepared/consumed/outcome
   and child-claim names. It exports bounded original-byte chunks and distinguishes missing,
   unreadable and retained files. Malformed or partial bytes remain available.
   This is a non-atomic historical snapshot, not chain authentication or replay.

These records use `operation-<32 lowercase hex>-powered-feedback-<stage>.json`
inside the assigned diagnostic root. They cannot collide with passive USB-only
records. A second journal constructor for the same attempt cannot replace its
prepared record. There is no journal reload-to-resume API or device callback.

Verification: **63 tests passed in 8.27 seconds**, run
`software/runs/pytest-powered-feedback-journal-20260912-03`. Coverage includes
two concurrent consumers, existing/partial consumed records, changed source or
startup, expired evidence, forged associations, exact original recovery,
malformed process output, outcome limits and no retry after failure. Shared
passive journaling, filesystem durability and public rehearsal/export regression
tests also passed. Real filesystem operations used modeled hardware inputs;
no serial port or camera was accessed.

Remaining integration: source-reviewed firmware/runtime admission, a unique
child-side claim tied to the supervised worker, worker packaging/registration,
coordinator/public action, and export/history UI for these powered live-attempt
records. **A consumed journal receipt is not permission to open COM6.**

## Worker-side claim increment

`application/powered_feedback_child_claim.py` now implements the claim mechanism
needed by the future supervised powered worker. `verify_consumed_attempt` reads
the canonical prepared/consumed files, verifies their hash chain and exact intent,
checks current source/runtime-byte association and timing, reopens startup, and
rebuilds metadata plus full review originals. This verification does not claim
the attempt or touch hardware.

`claim_for_child` performs those checks, then exclusively reserves a `claimed`
record. Existing claimed or outcome files block it even if their content is
partial or malformed. Concurrent workers can have only one reservation winner;
the losing Windows CREATE_NEW call reports a durability error. No deletion,
takeover, retry or recovery-to-resume is provided.

The returned live object is registered by object identity within the process.
`consume_live_claim` accepts it once; reconstructed/copied objects are rejected.
Consumption occurs before subsequent intent/admission checks, so failure cannot
reuse that object. These checks are lifecycle controls, not a security boundary
against arbitrary Python code running in the process. Independent reviewed
runtime and firmware admission remain required.

The journal/export stage list now includes `claimed`. Raw claim bytes survive
historical collection; historical collection still does not claim authentication
or physical authority. This supersedes the earlier three-stage listing above.

**66 tests passed in 9.51s** in
`software/runs/pytest-powered-feedback-claim-20260912-02`, covering new claims,
powered journal/preparation, passive claim/journal regression and the public
powered rehearsal/export. Tests include concurrency, copied claims, already-used
claims, failed intent matching, altered/partial records, foreign source/runtime
and expired setup. All device data was modeled. Real filesystem reservations
were exercised, but no device access occurred.

Still unfinished: bind this claim to a source-pinned supervised native worker,
reviewed powered admission, packaging/registration, coordinator/public action and
live-attempt export/history UI. The implementation does **not** release native
feedback or movement. Operator firmware history is still unresolved.

## Isolated worker packaging increment

`providers/windows/powered_feedback_package.py` builds a deterministic closed
`powered-feedback.zip` from the existing arm worker dependency roster plus the
powered-feedback modules. It excludes the application/wizard bootstrap and
publishes immutably. `_powered_feedback_child.py` requires Python `-I -S`, an
absolute archive path with the fixed filename, and its SHA-256 before importing
archive code. Digest matching is not a signature or independent source approval;
the future supervisor still has to pin and validate the registered artifacts.

Two entry modes currently exist:

- `check-imports`: import deployed feedback/journal/claim dependencies and report
  readiness of imports only. It does not claim an attempt or enumerate devices.
- `rehearse`: accept a bounded closed handoff with session, operation, source and
  one of the five existing synthetic scenarios. Execute the same memory-only
  feedback lifecycle and return a compact completion plus exact original bytes
  in a base64 wrapper. Failed scenarios report FAILED inside the completion;
  a zero child exit code means the worker returned its result, not that the
  simulated connection succeeded.

`observe` and all other modes are rejected before archive imports. Native DLL
loading and further subprocess creation are guarded before importing the archive
in these rehearsal/import modes. The provider itself still requires the exact
hardware-incapable API; these guards are additional regression checks, not an OS
security sandbox. No command or endpoint field is accepted in the handoff.

**33 tests passed in 11.15s** in
`software/runs/pytest-powered-feedback-package-20260912-02`, including actual
isolated child processes, deterministic archive generation, all five scenarios,
original-byte hashes, wrong-digest/unisolated/live-mode rejection, and passive
package, powered claim and public wizard rehearsal regression tests. No serial
port or camera was accessed and no powered attempt was claimed by the child.

This packaged entry is not yet registered with the owned worker supervisor, and
the public rehearsal action still uses its existing in-process implementation.
Next: fixed supervisor registration/wire contract and coordinator integration,
then independently reviewed powered native admission. Live feedback, calibration
and contact work remain unfinished. Do not use a generic subprocess launch as a
substitute for supervised physical dispatch.

## Supervised public wizard integration

The public `rehearse_powered_arm_feedback` action now dispatches through
`wizard_powered_feedback_coordinator.py` and `OwnedWindowsWorker`, replacing its
in-process execution. This supersedes the in-process status above. The child has
a third, still memory-only entry mode: `supervised-rehearse`.

The fixed registration binds the current interpreter, child script, deterministic
archive, per-operation working directory and exact arguments. The process budget
is eight seconds plus two seconds for cleanup, one process, 256 KiB stdout and
8 KiB stderr. The shared supervisor owns cancellation and process cleanup. Source
is checked before dispatch and by the authorizer at the supervised entry checks.

`powered_feedback_process_codec.py` validates the closed request domain, scenario,
session/operation/source identifiers, digest and exact deadline. The returned
completion is tied to that request and to the hashed original observation. It
rejects physical effect claims, mismatched context and a success observation
without confirmed simulated cleanup. Native admission remains held: this
registration accepts only the incapable composition and rehearsal command.

Before dispatch, `prepared-rehearsal.json` records actual runtime/payload inputs
inside `<operation-id>-powered-feedback-child`. After the attempt,
`process-outcome.json` preserves process status, registration and exact stdout/
stderr. Failed outcome persistence fails the wizard operation while retaining
diagnostics in memory for export; process failure does not imply device cleanup.
These files are diagnostic-only, not a physical attempt journal or replay permit.

The assigned export now additionally includes
`attachment-powered-feedback-process.json`, with base64-wrapped original process
diagnostics. The original observation attachment remains byte-identical. Failed
or cancelled process attempts retain raw diagnostic evidence even when there is
no accepted observation. Latest in-memory originals stay pinned independently of
rotating UI results. Existing files do not restore live permissions after restart.

Verification: **75 tests passed in 18.17s** in
`software/runs/pytest-powered-feedback-supervised-20260912-03`, including actual
public wizard dispatch through the owned supervisor, all five scenarios, confirmed
process-tree exit, durable/exported byte equality, pre-dispatch cancellation,
altered response rejection, isolated package tests, shared process-supervisor and
passive native package regressions. No hardware was accessed.

The preceding broader run had 133 passes and two failures: the new cancellation
test omitted creating its fixture log directory (fixed), and the existing action
catalog expected-set test omits `physical_camera_operating_proposal`, which is
present in the current workspace. That unrelated camera/catalog mismatch was
left untouched and is **not** claimed resolved by the 75-test run.

Next required live work: reviewed firmware/runtime admission, the powered native
API and observation entry, physical child registration/coordinator, and live
attempt journal/claim plus export/history integration. Firmware-change history
still awaits the operator. This increment enables no live feedback, movement,
calibration or typing/tapping.

## Historical attempt recovery through the wizard

The shared Arm action **Inspect saved powered feedback attempt** now accepts one
saved operation ID and reads only its prepared, consumed, claimed and outcome
files from the assigned diagnostic root. It is available in physical and
rehearsal modes because it never opens a device or dispatches a worker.

Use this action after restarting the wizard to inspect a previous powered
attempt, then choose **Export logs**. The attachment
`attachment-powered-feedback-history.json` preserves collected original bytes in
base64 chunks with byte counts and SHA-256 digests. These historical chunks do not
pass through JSON reformatting. The most recently inspected collection remains
pinned even after ordinary result cards rotate out; export before closing if
you need that exact non-atomic snapshot.

The result distinguishes MISSING, UNREADABLE and BYTES_RETAINED per stage. An
inspection can succeed when a file is partial or malformed: success means bytes
were collected, **not** that the original operation succeeded or cleanup was
confirmed. All-missing attempts and unreadable stages fail the inspection while
preserving available evidence. No attempt is repaired, resumed, reconstructed as
live authority, or replayed. Hashes are not authentication and chain verification
is explicitly false.

Export enforces the existing one-MiB attachment budget. If a collected snapshot
exceeds it, export fails explicitly rather than claiming a complete export or
silently omitting original bytes. Chunked/multi-attachment export for unusually
large malformed histories remains an improvement; the original files are retained
in the diagnostic root.

Implementation: `wizard_powered_feedback_history.py`, shared action catalog and
`ArrivalWizardService` result/export retention. **75 tests passed in 18.09s** in
`software/runs/pytest-powered-feedback-history-20260912-02`, including public
history actions in both modes, exact partial-byte recovery after ten result-card
rotations, missing/unreadable records, traversal rejection, powered journal,
supervised rehearsal and general service regression. Hardware providers were
forbidden in the history tests; no hardware access occurred. This run did not
include or resolve the separately documented camera action-catalog mismatch.

This action reads powered physical-attempt journal files. It is not the recovery
UI for supervised rehearsal's per-operation `process-outcome.json` file. Live
powered query execution, reviewed firmware admission and physical calibration
remain incomplete.

## Native facade and shared observation loop

`powered_feedback_serial_api.py` now implements the one-query Windows facade.
Its ordinary constructor cannot load the serial API. `from_live_claim` consumes
the exact process-local claim, reopens and checks the prepared/consumed/claimed
chain, rejects an existing outcome, validates the firmware/protocol/startup
originals again, and requires fresh matching endpoint metadata. It binds one
endpoint and intent; wrong-path and failed-open attempts cannot be retried.

The facade permits only the existing fixed T105 payload. One write submission
consumes its write slot even if submission fails. Completion/cancellation of
writes must reference the same token. A expired setup or identity prevents a new
open, but cleanup remains available after a deadline when resources may already
be owned. This is a trusted process boundary, not a sandbox for arbitrary Python;
the parent must independently validate and supervise the registered runtime.

The shared backend now accepts this exact admitted facade, not ordinary native
construction or the passive API. Its lifecycle composition is explicitly
`WINDOWS_POWERED_FEEDBACK_ENGINEERING`. `observe_physical` and `observe_rehearsal`
use the same bounded read/query/cleanup loop but require distinct provider types
and provenance. A pre-cancelled physical-shaped test acquires no resources.

**135 tests passed in 9.91s** in
`software/runs/pytest-powered-feedback-native-api-20260912-02`. Coverage includes
the new facade, existing loop/backend/passive restrictions and isolated packaging.
The native open/cleanup test used a fake DLL, including cleanup after expiry.
Other facade tests forbid the serial DLL loader. This is not a received-unit
driver test, voltage measurement or verified live feedback.

Still next: physical worker payload/registration, fresh metadata collection in
that child, and the public coordinator connecting prepared originals, journal,
claim, observation and exports. The current packaged child still rejects live
operation modes. Firmware history has been confirmed unchanged since delivery;
it is no longer an unanswered question. No movement is enabled by this work.

## Physical child and supervisor integration

The native path now has its own `powered-feedback-native.zip` and fixed child,
separate from the rehearsal package. The archive adds the exact pySerial metadata
dependencies and native registration/wire modules. Import-check mode blocks DLL
loading and subprocesses; it does not claim an attempt or enumerate devices.

The physical handoff contains only an exact powered intent, assigned journal root,
consumption digest and source-pinned runtime registration. The registration fixes
interpreter, child, archive, arguments, directory, one process, 20-second runtime,
two-second cleanup and bounded streams. It allows no arbitrary command, endpoint
override or alternate executable. Runtime hash equality alone remains insufficient:
the supervisor compares current source-derived artifacts and verifies originals.

Before dispatch and immediately before the initial thread resumes, the supervisor
revalidates the prepared/consumed evidence. The child reserves its unique claim
before fresh USB metadata collection. Matching fresh metadata admits the exact
native facade, which performs the shared one-query observation. Returned data
includes the fresh metadata snapshot, raw receive-byte records, feedback and
resource cleanup. The parent validates request/result identity and compares the
returned claim digest against the actual retained claim file.

Success validation requires one complete typed response, the ten confirmed query
bytes, empty startup/late-cleanup buffers, no observation errors and confirmed
cleanup. Reported voltage remains controller telemetry, not an independent
measurement. Physical authority, persistent connection and motion authorization
remain false even when one query succeeds.

**90 tests passed in 14.46s**, run
`software/runs/pytest-powered-feedback-native-worker-20260912-03`. Coverage includes
isolated imports, malformed/raw-command/oversized handoffs, rehashed foreign wire
context, exact registration and changed argument/budget/pin rejection. Missing
consumed originals are verified to stop before even constructing the process
backend. Native facade, rehearsal package and shared supervisor regressions pass.
No valid physical handoff was executed in these tests and no hardware was accessed.

Remaining: public physical coordinator/action, its original report/runtime/journal
joins, durable outcome plus compact UI/export handling, and a controlled received-
unit query. This is implementation evidence, not a live connection qualification.
All calibration and contact/motion milestones remain unfinished.

## Public physical action and coordinator

**Run one supervised powered feedback query** is now exposed in physical mode.
It requires a powered-startup original less than five minutes old, current
correlated USB metadata and the operator's explicit unchanged-delivery firmware
confirmation. The preview binds setup/original/review hashes; a later setup or
selection change invalidates it. One attempt is allowed per wizard launch, even
if preparation fails. This is not automatic replay or reconnection after failure.

`wizard_powered_feedback_native_coordinator.py` assembles and verifies the fixed
runtime registration, actual requested serial profile, operator history, vendor
protocol review, startup and USB originals. The journal is prepared/consumed
before dispatch. The supervisor and child repeat their checks, and the outcome
is saved immutably before a successful operation can be published.

The compact result displays controller feedback, query-byte count and serial/
process closure without nesting full metadata in the UI. Unknown counts or
cleanup remain null/unknown rather than fabricated zeros. A successful query is
not a persistent command connection, power qualification or motion permit.

Exports add `attachment-powered-feedback-attempt-files.json` and
`attachment-powered-feedback-native-logs.json`, retaining original journal bytes
and raw process stdout/stderr. The service pins the attempt before preparation
and the outcome before final source/publication checks, so partial failures can
still be exported. Persistence failure prevents success; raw in-memory logs are
retained for export before closing.

**77 tests passed in 18.49s**, run
`software/runs/pytest-powered-feedback-live-join-20260912-02`. Tests use explicitly
simulated worker outcomes; an autouse guard prevents any live process dispatch.
They exercise the actual public service and coordinator joins, one-use attempt,
startup/firmware prerequisites, stale preview, raw export and success versus
outcome-save failure. Rehearsal, powered setup/history and shared supervisor
regressions also pass. These tests do not prove communication with the received arm.

The next step is one operator-present live query through this action after fresh
current setup confirmation. Opening serial can cause controller reset/startup
movement; keep the arm secured and the area clear. No deliberate motion command
is part of the query. Review actual feedback and closure evidence before deciding
on any subsequent bounded movement or calibration step.

## Received-unit response-profile finding (2026-10-21)

The operator-present live sequence was run once against the reviewed CP210x
controller identity after a zero-write observation received no bytes. The
active attempt wrote the single fixed 10-byte `T=105` request and received one
complete 142-byte newline-terminated `T=1051` JSON response. Serial cleanup and
owned-process exit were confirmed; no retry or motion command occurred.

The received response uses an installed position-vector profile:

```json
{"T":1051,"p":[2050,2147,1958,2550,2227,2041,2042],"pose":"KEYBOARD_FORWARD_CAL_1","motion_active":false,"trajectory_progress_permille":1000}
```

This differs from the full Waveshare field set required by the powered-feedback
qualification (`x,y,z,tit,b,s,e,t,r,g,v`). Transport therefore worked, while the
operation correctly remained failed and physically unqualified. The seven raw
counts and named-pose metadata are evidence of an installed response shape;
they are not calibrated joint or tool-tip measurements.

`feedback_profile.py` now names this exact bounded response shape as
`POSITION_VECTOR_NAMED_POSE`. The powered observation still rejects it, retains
the original response bytes, and reports
`INSTALLED_POSITION_VECTOR_FEEDBACK_PROFILE` instead of the generic incomplete
feedback label. Extra fields, malformed counts, invalid pose identifiers,
non-Boolean motion state, and out-of-range progress remain `UNKNOWN` and fail
closed. Supporting any operational use requires a separately reviewed profile
mapping and installed-controller qualification; this classifier grants none.

## Position-vector calibration contract (2026-10-21)

The retained controller history identifies the seven position slots as servo
IDs 11 through 17. This makes the raw vector structurally useful: indices 0,
1, 3, 4, 5, and 6 correspond to the primary base, shoulder, elbow, wrist-pitch,
wrist-roll, and gripper servos, while index 2 is the driven member of the mirrored
shoulder pair. The ordering is now explicit in a zero-I/O calibration boundary;
it is not inferred anew from each response.

`arm/position_vector_calibration.py` separates two outcomes:

1. An exact installed response can be described as `CALIBRATION_REQUIRED`, with
   its raw counts and known servo slots retained. This does not compute or claim
   canonical joint state.
2. Conversion is available only when the caller supplies a strict
   `rocell.position_vector_calibration.v1` artifact bound to the exact controller
   VID, PID, unit serial, and firmware SHA-256. The artifact must contain the
   fixed servo and canonical joint orders, one bounded affine count conversion
   for every logical joint, at least two training and one held-out observation
   per joint, passing held-out error limits, a validated mirrored-shoulder
   residual/tolerance, and distinct dataset, fit-report, and independent-review
   SHA-256 identities.

Runtime conversion rechecks controller identity, response shape, shoulder-pair
agreement, and each calibrated joint range. Any mismatch fails closed. Even a
valid converted result sets `motion_authorized` and `physical_authority` false;
it is an observation contract, not an execution permit.

The single retained `KEYBOARD_FORWARD_CAL_1` response cannot populate an
accepted artifact. It provides one stationary vector and no independently
measured canonical joint truth, per-joint span, held-out sample, or firmware
binary identity. The next physical calibration campaign must therefore be
planned separately and requires new explicit hardware authorization. No further
query, retry, motion, or device access was performed for this increment.

## Offline position-vector campaign workflow (2026-10-21)

`calibration/position_vector_campaign.py` now implements the offline campaign
that can produce the strict position-vector artifact described above. It
validates controller and attachment identity, stationary seven-count samples,
independent six-joint truth, disjoint training and held-out evidence, count
coverage, held-out error, and mirrored-shoulder agreement. Its default gates are
five training samples, three held-out samples, 128 counts of training span per
primary joint, 0.035 radians maximum held-out error, and 24 counts maximum
shoulder residual.

The workflow produces a deterministic fit report and requires an accepting
review from someone other than the dataset producer. Unique truth-evidence
hashes and exact dataset, fit-report, and review hashes prevent evidence reuse
or artifact crossing. The builder recomputes the fit before emitting the
runtime artifact. See
[`POSITION_VECTOR_CALIBRATION_CAMPAIGN.md`](POSITION_VECTOR_CALIBRATION_CAMPAIGN.md)
for the dataset contract, commands, attachment-profile separation, and physical
collection boundary.

This addition performed no hardware access. The retained observation remains
`CALIBRATION_REQUIRED`; a physical campaign still requires fresh authorization
and independent measurements.

## Calibrated position-vector execution seam (2026-10-25)

The qualified calibration campaign now reaches a bounded application execution
seam. The seam reproduces the exact offline execution approval, requires fresh
operator and physical prerequisites valid for no more than five minutes, checks
the installed calibration and controller binding, and invokes one injected
exchange with no retry branch. It accepts only one exact T=105 request, one
installed position-vector T=1051 response, zero motion commands, and confirmed
cleanup before converting the raw counts with the approved calibration.

The resulting receipt advances only to calibrated execution review and grants
no motion, contact, persistent connection, or physical authority. This resolves
the application-level response-profile mismatch that caused the original
full-Waveshare worker to reject the received unit's valid position vector. It
does not alter that worker or broaden its qualification contract.

No controller, camera, or hardware was accessed for this increment. The separate
native position-vector serial adapter now exists alongside this seam. It keeps
the full-Waveshare worker unchanged, journals intent before transport creation,
records every open/write/response/close stage, and emits the seam's exact
exchange evidence only after one installed-profile response and confirmed
cleanup. Partial or interrupted attempts remain terminal with retry forbidden.

The reviewed production composition is now implemented behind the private owned
process boundary. The parent pins the interpreter, deterministic child archive,
exact controller and firmware binding, request, runtime, PID, and original
deadline. It supervises one request/result exchange, verifies the returned
immutable journal export byte-for-byte, and retains the no-retry and no-motion
claims. There is still no public live CLI. A later physical attempt requires
newly confirmed physical state; the earlier unplugged or powered state is not
reused.

## Calibrated native child composition (2026-10-25)

The calibrated adapter is now joined to the non-purging Windows connection at a
private child-side boundary. Admission requires the exact reviewed controller,
a fresh identical identity, the installed calibration controller/firmware
binding, closed request, pinned runtime, current child PID, and original
deadline. Construction and status are inert; the admitted facade has one open
attempt and preserves the adapter's fixed T105/no-retry lifecycle.

The same boundary verifies and retains terminal or interrupted journals as an
immutable evidence export with hashes for every original byte stream. It does
not provide a CLI, invoke hardware in tests, authorize motion, or treat an
interrupted attempt as retryable. Parent-side source-pinned package,
registration, wire, supervision, and result/export association are now present.
The next increment is parent application orchestration that consumes the
existing approved request and fresh prerequisites, invokes this private worker
once, and submits the verified exchange evidence to the calibrated execution
review seam. Route execution continues to require separately qualified
`no_attachment` or `stylus_attachment` geometry.
