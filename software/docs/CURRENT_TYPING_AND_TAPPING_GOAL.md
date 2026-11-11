# Current goal and execution plan

> **Current durable objective:**
> [SIM_TO_REAL_TYPING_GOAL.md](SIM_TO_REAL_TYPING_GOAL.md) supersedes the
> historical immediate execution priority below. The active path is now
> simulation-first, camera-informed, attachment-separated robotic typing with
> physics qualification and separately authorized sim-to-real validation.
> The remainder of this file is retained as command/servo diagnostic history
> and evidence; statements deferring camera, stylus registration, contact, or
> Isaac Sim are no longer the current plan.

Updated: 2026-09-17. This document supersedes historical immediate-next-action
instructions in the movement logs. The practical path document remains the
overall roadmap; FIRST_COORDINATED_GHOST_STEP.md retains detailed trial evidence.

## Rewritten goal

Build a reliable command-to-motion workflow for ghost-keyboard typing and eventual
physical typing and Android tapping. First resolve reverse-motion ambiguity with
command-correlated controller/servo diagnostics: distinguish requested targets,
transmitted bus commands, supported target readback and freshly acquired positions.
Implement capability discovery, diagnostic contracts, simulation, wizard reporting
and reproducible exports before deploying supported instrumentation. Use evidence
to correct the demonstrated cause, then validate bounded bidirectional movements,
repeatable cycles, coordinated approach/press/retract and short ghost-key sequences.
Validate any compensation prospectively within explicit operating limits. Work
autonomously on software and read-only investigations under the standing setup
assumptions; stop affected sequences on uncertain delivery, invalid acquisition,
unexpected motion or export failure. Do not require routine visual confirmation,
infer missing telemetry, or treat joint feedback as physical tip metrology. Defer
camera, contact and real stylus accuracy until mounting and registration are ready.
Firmware deployment and configuration changes require a separate reviewed decision.

## Current execution priority — supersedes historical next actions

Follow [COMMAND_TO_SERVO_DIAGNOSTICS_PLAN.md](COMMAND_TO_SERVO_DIAGNOSTICS_PLAN.md).
The user selected instrumented diagnosis instead of requiring video confirmation.
Software work is not blocked waiting for a recording. Begin capability verification
and the evidence contract, then simulation, wizard/export integration and reviewed
deployment. The existing export labels are not full servo instrumentation.
No new movement, firmware upload or configuration change is implied by this plan
update. Preserve the native T104 hold and original forward/reverse trial verdicts.

## Working phases and completion gates

These motion phases follow the diagnostic plan above. Updating this plan does not
itself dispatch motion or release a held command path.

1. **Qualify the command family offline.** Verify the official all-joint command
   identifier, units, ranges and state effects; distinguish reference source from
   installed firmware. Preserve non-test joint targets from fresh reported state.
   Test explicit speed/acceleration, exact payload binding, single dispatch,
   independent joint-progress stress, invalid/stale feedback, cancellation and
   diagnostic export failure. Gate: tests pass and a bounded trial preview exists.
2. **Identify one live response.** Acquire fresh baseline feedback, issue one
   screened command through the reviewed runner, then record trajectory and a
   post-arrival settling window. Compare both the desired endpoint and transmitted
   endpoint with reported state. Gate: interpretable response, valid settled
   endpoint and verified export; otherwise diagnose without automatic retry.
3. **Establish repeatability and return behavior.** Qualify the reverse leg
   independently before chaining it. Repeat a finite set of paired endpoints at
   fixed settings, then vary one factor at a time. Gate: every leg satisfies its
   declared endpoint, settling and response-envelope criteria with durable records.
4. **Validate compensation only if needed.** Separate training and held-out trials;
   compare corrected results with the uncorrected baseline. Record valid posture,
   direction, amplitude and speed ranges. Gate: prospective improvement without
   worse path excursions; do not reuse the invalidated affine candidate.
5. **Execute a local ghost press cycle.** Preview approach, modeled 2 mm press and
   retract using the hypothetical tool. Qualify segments individually before a
   finite sequence, monitoring intermediate joint progress as well as endpoints.
   Gate: all segments and settled endpoints pass; this is not contact validation.
6. **Practice ghost typing.** Qualify approach to the virtual keyboard separately,
   then one key and a short adjacent-key sequence. Export per-key target, modeled
   tip response, timing and residual summary. Gate: repeatable noncontact execution;
   camera registration, actual stylus dimensions and contact tests remain later.

For every phase, freeze numeric tolerances, deadlines and the finite trial count
in the trial definition before dispatch. Record failures unchanged. Stop software
progression when a gate fails; this is not a claim that the controller cancels a
movement already in flight. No firmware, torque or PID changes are included.

### Previous goal wording (historical)

Implement and validate a reliable, telemetry-driven command-to-motion path toward
keyboard typing and Android tapping. Build on operator-confirmed movement and
the verified local elbow/wrist cycles; do not repeat larger demonstration moves
merely to prove motion. Next validate an offline coordinated 2 mm hypothetical
tip press/retract preview, then qualify bounded live coordinated segments from
fresh reported poses. Separately qualify the approach to the existing ghost
keyboard, then one noncontact ghost-key approach/press/retract and a short finite
sequence. Preserve separate desired-target and transmitted-command verdicts.
Capture and export each leg's baseline,
desired endpoint, transmitted command, reported trajectory, residuals, timing,
candidate identity and outcome before progressing. Validate corrections on
held-out trials within explicit posture, direction, speed and range limits.
Work autonomously without routine confirmation prompts under the standing
powered, secured and clear-workspace assumption, unless evidence contradicts it.
Stop affected sequences on uncertain commands, invalid feedback or unexpected
motion; do not automatically replay them. Favor useful repeatable performance
over perfect residuals. Defer camera integration, physical contact and calibrated
tip-accuracy claims until the supports, stylus mount and coordinate registration
are ready. Treat the 100 mm stylus offset and keyboard placement as hypothetical.

## What is established

- The operator has visibly observed commanded movement. This does not independently
  measure its magnitude or establish a successful endpoint for a specific export.
- Two local elbow cycles completed with clean per-leg reported-endpoint verification
  and exports; their modeled desired errors were approximately 0.298 and 0.288 mm.
- The descending wrist candidate reached the same reported endpoint from two starts,
  with approximately 0.401 mm desired error in the controller model. A later error
  in the second diagnostic prevents using that run as clean progression authority.
- A first coordinated 5 mm approach did not verify: its retained modeled error was
  approximately 6.11 mm, followed by a feedback timeout. Individual-joint success
  therefore does not establish coordinated Cartesian accuracy.
- The full-size ghost keyboard and hypothetical tool have offline route checks.
  These are not physical board registration, clearance measurement or tip metrology.

## Ordered implementation and testing

### Active next steps — supersedes historical checkpoints below

#### Planning refresh following operator confirmation

The operator reports seeing the demonstration move. Record this as qualitative
motion confirmation, not a measured angle, endpoint pass or proof of a particular
trial's success without an associated command/export record. Do not repeat a
larger demonstration just to establish that the arm can move.

Current evidence and immediate work:

1. **Preserve established results.** Local wrist paired trials passed reported
   endpoint checks and exports. The two latest increasing-elbow identification
   trials moved but failed their desired endpoints. Keep those failures intact.
   Wrist corrections remain scoped to their tested posture, not the new elbow pose.
2. **Finish the local elbow candidate integration offline.** The frozen additive
   bias is 0.005695130938801918 rad. Verify exact candidate/start/payload binding,
   single dispatch, and separate desired-target versus transmitted-target scoring.
   Test that reaching only the compensated wire target cannot falsely pass the
   desired endpoint. Integration is not live validation.
3. **Perform one held-out elbow trial after offline checks.** Acquire fresh state
   and screen the frozen start/trajectory. Use the existing declared limits and
   settling checks; do not loosen them after seeing results. A mismatched start
   requires a new reviewed preview, not automatic repositioning. Export raw
   feedback, command receipt, desired/wire residuals and verdict. No automatic
   retry, refit or return. The frozen candidate remains unvalidated until this passes.
4. **Qualify reverse motion and repeatability.** Review the return independently,
   then define a finite paired trial set. Keep correction scope explicit: joint,
   direction, posture, amplitude and speed. An increasing-direction success does
   not qualify descending motion or other joints.
5. **Build a local noncontact press/retract.** Qualify the remaining shoulder and
   wrist demands at the relevant posture, then screen and test coordinated legs.
   T102 is not qualified by the earlier attempts; native T104 remains held. Do not
   reuse the failed coordinated affine model or infer coordinated success from
   independent joint passes.
6. **Advance to ghost typing.** Separately qualify the virtual-keyboard approach,
   one key's approach/press/retract, then a short finite adjacent-key sequence.
   Report modeled errors and timing per leg. Camera, physical stylus mounting,
   board registration and contact tests remain deferred.

Practical objective: repeatable, explainable command-to-reported-position behavior
with useful exports, not perfect residuals or a physical accuracy claim. This
documentation update sends no hardware commands. The detailed checkpoints below
retain the evidence supporting this execution order.

#### Latest operator confirmation and execution order

Separately timed target/feedback acquisition contract added. Validates pinned
profile, command/boot/servo identity, per-read device errors and raw bytes,
post-dispatch chronology, nonoverlap, sequence and correlation-window budget.
Retains raw goal word separately from signed feedback; no simultaneous-read or
hardware provenance claim. 18 new tests plus register/v1 export regressions:
52 passed. No arm access. Next connect these records to a complete versioned
diagnostic trace and simulation/export/UI path; current v1 replay is preserved.

Reference register decoder implemented: immutable named map, unsigned-word/raw
retention, sign-magnitude position/speed/load/current decoding, explicit byte order
and exact 15-byte feedback bounds. Read failure is distinct from legitimate -1;
cached data after failed reads is rejected. Out-of-buffer mode/goal fields excluded.
22 new tests, 57 combined contract/decoder tests passed. No bus I/O, hardware
configuration or firmware deployment. Next add separately timed target/position
acquisition records and profile binding, retaining the already-exported v1 behavior.

Read-only vendor source investigation: identified goal-position registers and
generic readWord plus a 15-byte position/health feedback block in a pinned vendor
SCServo archive. Recorded address/width/sign semantics and an unsafe cached mode
helper (negative buffer index) in SERVO_READBACK_REFERENCE_REVIEW.md. No installed
library match or causal connection to reversal is claimed. This changes the next
implementation: use separate acquisition intervals and a reviewed signed-register
profile, not a single timestamp/unsigned-only synthetic assumption. No hardware
access, uploads, servo writes or vendor example execution occurred. Next implement
and test that producer-facing contract extension, retaining v1 replay compatibility.

Servo diagnostic UI increment: dedicated result card distinguishes simulation
completion, trace rejection/assessment, synthetic readback/fresh samples/residual,
export integrity and replay. Hardware remains explicitly NOT QUALIFIED. Invalid
authority/origin/schema combinations produce an unavailable summary. Six UI tests
execute actual app.js rendering with real service outputs in the existing inert
DOM harness; arm-page navigation exposes the action, no hardware runner calls.
This is not a real-browser visual inspection. Next complete diagnostic capability/
health semantics and the remaining failure scenarios, while investigating the
installed-compatible producer; do not confuse the now-connected synthetic wizard
workflow with live instrumentation or resolved reverse motion.

Wizard service integration: registered `simulate_servo_diagnostics` in the arm
action catalog with nine bounded scenario choices and explicit simulation-only
label/effects. Preview is inert; service execution uses assigned export_directory,
retains the service-owned result, verifies replay and supports normal Export Logs.
Arrival, stationary and reboot service tests prove no hardware runner calls or
arm connection qualification. Invalid selection rejected before dispatch.
76 focused wizard-action/service/export tests passed. Also corrected a pre-existing
missing `review_product_ghost_case` entry in the registry test's expected list.
Next verify browser rendering/navigation and give the action a dedicated evidence
summary rather than relying on generic result details. No actual browser workflow
or live servo instrumentation is claimed verified by the service tests.

2026-09-18 00:28 UTC: synthetic diagnostic runner now exports exact trace bytes
(base64 plus SHA256), assessment and explicit simulation provenance through the
existing wizard exporter. Offline replay verifies manifests/hashes, regenerates
the named fixture and recomputes the verdict, including rejected traces. It never
opens hardware or grants progression. 58 focused tests passed, including tampering,
export verification failure, invalid scenario and all nine scenario round trips.
All nine scenarios also exported/replayed in the workspace at 00:28:58 UTC.
Arrival export: `wizard-20260918T002858477671Z-913c2069b3e54f3592faf3d204cb0a61`;
stale-sequence rejection: `wizard-20260918T002858795555Z-5a574e4c2c8d49ebbbf3847e25aba229`.
CLI: `software/scripts/rehearse_servo_diagnostics.py <scenario>`.
Next wire this tested synthetic workflow into wizard action/service/UI and cover
the UI-to-export path. Additional health/capability semantics and installed
instrumentation remain pending. These simulations do not resolve live reversal.

Diagnostic decoder/simulation increment: bounded exact-schema ingestion now retains
raw-byte hash and rejects malformed/oversized/duplicate/nonfinite inputs. Nine
deterministic synthetic scenarios run through that decoder and assessor, including
stationary-but-fresh, read failure, unsupported readback, reboot and stale sequence.
46 focused tests passed. No hardware I/O or firmware change. Next wire these cases
to a bounded diagnostic runner with verified raw-trace exports/offline replay,
then wizard service/UI; add remaining health/controller-rejection cases explicitly.
Installed capability and telemetry-producer gaps remain unchanged, not solved by
these synthetic tests.

Diagnostics implementation resumed under the revised goal: added an evidence-scoped
capability inventory and offline servo_diagnostic_contract v1 assessor. Initial
contract and existing assessment tests: 24 passed. Command/payload/settings/boot
correlation, sequence ordering, read validity, separate goal readback and settling
are checked; no diagnostic verdict grants motion authority. No Python process was
found during the interrupted-turn check; no hardware accessed. Next implement the
bounded raw decoder and injected simulation scenarios, then actual wizard/export
wiring. Capability investigation and installed producer remain incomplete; see
SERVO_DIAGNOSTIC_CAPABILITIES.md for explicit limitations.

21:40 UTC: added export-only joint_diagnostic_assessment to the shared trial
runner. Labels distinguish no send, uncertain delivery/observation, missing
feedback, reported non-arrival and reported endpoint pass. Identical packets are
NOT labeled stale acquisition; servo acceptance and encoder freshness remain
UNAVAILABLE with this interface. Assessments never grant progression or retries.
35 focused diagnostic/runner/native tests passed, including verifying the actual
export attachment contains the assessment. Offline assessments of the forward
pass and both reverse failures exported and verified:
`wizard-20260917T214016707813Z-f523297aef9a45b9a1d1bd7bb260c852`.
No device I/O. Original trial verdicts unchanged. This improves diagnostics, not
the physical reverse response; no simulated bus-level evidence was fabricated.
Further software contract work must stay bounded: obtaining additional actuator
evidence or a separately reviewed physical characterization is still necessary
to qualify return motion. Firmware modification remains separately authorized.

Diagnostic review following 21:35: see
[ELBOW_REVERSE_DIAGNOSTIC_DECISION.md](ELBOW_REVERSE_DIAGNOSTIC_DECISION.md).
Reverified official reference archive hash and command definitions/handlers.
No exposed goal-register/PID/per-read-status getter found in that reference;
installed firmware remains unidentified. T108/109/112/501/502/503 are mutators,
not read-only diagnostics. Reviewed existing USB/HTTP comparison instead of
reopening serial or repeating stationary capture. Instrumentation gaps and an
additive simulated diagnostic contract are the next software work; firmware or
bus changes require separate compatibility review and authorization. No motion,
configuration writes or firmware changes were made in this review.

21:35 UTC: named reverse-speed40 experiment implemented with exact-start binding,
same T101 joint3 target 1.79168956, acceleration 1 and unchanged path/endpoint
limits. Speed is included in the reserved exact command. 49 focused native,
transaction and runner tests passed, including exact speed40 payload and wrong
start rejection. Fresh preview verified:
`wizard-20260917T213455433255Z-92f1cf279619450a8abf7a97ad159d4d`.
Executed once; 30 feedback samples, unchanged elbow 1.807029368 and other joints,
modeled endpoint error 5.164664 mm. FAILED completion window, exported/verified:
`wizard-20260917T213514249166Z-619a4a1004cd42a9a78f67f24018de83`.
No retry or larger command. Same-start/target 20-versus-40 comparison exported:
`wizard-20260917T213545010729Z-d776091dd02344ed982ae903ed3b1d82`.
Both responses unchanged; speed increase did not resolve this target. Sequential
command history differs, so this is not randomized causal evidence.

Next inspect available read-only servo acquisition/installed command-path evidence
and existing USB-versus-HTTP captures before selecting any further motion. Do not
repeat already completed transport comparisons or equate HTTP receipt with servo
bus execution. No more speed/amplitude staircase. If installed acquisition lacks
target/error/status readback, state that instrumentation gap explicitly and choose
a separately reviewed identification method rather than fabricating confirmation.

21:33 UTC: offline reverse audit exported and verified:
`wizard-20260917T213305904916Z-3a6dea14a66e45e4b92119cf8f6ad5f8`.
New reusable elbow_reverse_review validates payload/receipt hashes, raw trial
feedback against retained rows and a chronologically subsequent feedback-only
observation. Six audit tests plus eleven comparison tests passed (17 total).
Command conversion predicts -10 encoder counts, reported change is zero; ordinary
single-count rounding cannot explain the entire discrepancy under the reference
conversion. HTTP receipt is not proof of installed servo-bus target delivery.
Passive elbow raw load remained 45 (not calibrated force); physical cause remains
unproven. Historical reverse-offset reuse would command 1.7443065984 rad and
produce a sampled one-count hypothetical-tip envelope of 21.630695 mm, exceeding
the current 6 mm experiment scope. No such command was sent or enabled.

Next prepare a named SAME-TARGET reverse speed comparison (T101 joint3 target
1.79168956, speed 40 instead of 20, acceleration unchanged at 1), bound to fresh
exact current pose 1.807029368 and the existing other joint values. This changes
one input without increasing requested travel. Before execution, bind speed into
reservation/payload identity, test wrong-start/settings rejection, preview the
same path and retain existing observed-motion/endpoint/deadline limits. Execute
at most once, export before any next action. A response would support sensitivity
to this setting/history, not prove friction or solve global compensation; no
response should trigger command-path/servo diagnostics, not blind repetitions.
This is a future trial definition, not an executed result or relaxed endpoint gate.

21:31 UTC: independently prepared an UNCOMPENSATED reverse-elbow identification
from reconstructed successful forward endpoint 1.807029368 to prior starting
angle 1.79168956 (T101 joint3, 20/1). New exact-start probe has no forward-bias
reuse; 53 focused tests passed including wrong-start/no-send and no-compensation
regressions. Fresh preview export
`wizard-20260917T212959412583Z-b23820cb2c53494cac5a0568753c5637`:
one-count sampled modeled displacement 5.681119 mm within 6 mm.
One dispatch FAILED desired endpoint, exported and verified:
`wizard-20260917T213018314567Z-ebaacbf5eb60410ba58e880c6809b165`.
29 samples ended at unchanged elbow 1.807029368; modeled desired error 5.164664 mm;
reason FEEDBACK_OR_COMPLETION_WINDOW_EXHAUSTED. No retry/escalation/return.
Read-only bounded follow-up exported:
`wizard-20260917T213104814701Z-86eef1254d414e90bcb09785af62cc32`.
113 successful observations over ~35 seconds, zero reported span on all joints.
Thus no delayed reported response was observed; hardware fault or physical
deadband is NOT established by this alone.

Historical reverse exports 163506/164028 are valid when inspected with absolute
paths. An initial review used a relative path and failed verification; that was
a review invocation error, not evidence corruption. Both historical trials at
elbow 1.563126423 commanded 1.4758599604002836 and reported 1.523242922,
residual +0.047382962 rad (31 counts). They demonstrate older reverse undershoot,
not a transferable correction at the current shoulder/elbow/wrist posture.
Next review the command/receipt and reverse-direction response history together
to define a separately screened identification range. Do not auto-apply the
historical ~0.047 rad offset: its commanded path exceeds this trial's reviewed
scope. Return repeatability, coordinated press/retract and ghost typing remain
unqualified; forward local success is retained unchanged.

21:27 UTC: frozen local increasing-elbow correction integrated and tested: 52
focused transaction, native-adapter, runner and candidate tests passed. Added
regressions for wrong-start/no-send, exact T101 joint3 payload, verified export,
and wire-only arrival failing desired-endpoint verification. Fresh live preview
matched all six required starting joints and exported without motion:
`wizard-20260917T212726832691Z-cb3f120853fd4f0a8e21e8bb43472fb8`.
One prospective live dispatch then VERIFIED_AND_EXPORTED:
`wizard-20260917T212741969917Z-84e87697a9404f2a95a3a321374800bd`.
Nine feedback samples; elbow start 1.79168956, desired 1.80568956, wire
1.799994429061198, reported settled endpoint 1.807029368 rad. Desired residual
+0.001339808 rad, modeled desired-tip error 0.451096 mm (within predeclared
0.5 mm), wire-tip error 2.368568 mm, modeled displacement 5.164664 mm (within
6 mm). Other reported joints unchanged. No refitting, retry or return. This is
one successful held-out local increasing trial, not physical tip metrology or a
global correction. Original frozen training artifact remains immutable; this
separate live export supplies its prospective evidence.
Next independently preview and qualify reverse elbow behavior from fresh state,
using retained direction-specific history where applicable without assuming the
increasing correction transfers. Then test finite repeatability before combining
press-relevant joints. Prior exact-start wrist profiles are not valid unchanged
at this new elbow posture. This checkpoint supersedes the pending elbow-trial
wording in the planning refresh above.

21:20 UTC: local increasing-elbow constant-bias candidate frozen OFFLINE from
the two nearby T101 samples, mean residual 0.005695130938801918 rad. Raw response
integrity and >=2-second unchanged identification tails checked; original endpoint
failures remain failures. Desired new response +0.014 rad is strictly between
the observed +0.012272/+0.016874 rad responses; wire step +0.008304869 rad is
strictly between sampled +0.006/+0.011755 rad commands. This is amplitude support,
not proof of posture invariance. Start elbow 1.79168956, desired 1.80568956,
wire 1.799994429061198, T101 joint3 at 20/1. Wire/desired one-count modeled
envelopes 3.312600/5.230038 mm against 6 mm. No hardware accessed.
Verified candidate export `wizard-20260917T212020172869Z-06f35d9099a14ce8843f0fc62d89bede`;
candidate SHA256 2094c8e20d62dff40e2c29b7fd1f51c8be86b33f6bf2887821186e8866aa8fd9.
Next bind this immutable candidate and exact fresh start to separate desired/wire
verification, test failed desired endpoints, then attempt one prospective trial.
No runtime refitting, no descending application and no global enablement.

21:18 UTC: second local uncompensated T101 elbow identification, fixed target
1.785417714 from exact fresh start 1.779417714 (+0.006 rad). 33 tests passed.
Preview export `wizard-20260917T211811457082Z-fa0bb4e881894579bbd465c3c1b691a0`,
sampled one-count model excursion 2.536588 mm. Executed once, no retry/return.
Verified live export `wizard-20260917T211830530621Z-37561f57a5134b439898e3cc7fcc7bbb`.
30 feedback samples, final elbow 1.79168956 (delta +0.012271846), residual
+0.006271846 rad (~4 counts past predicted target), modeled desired-tip error
2.111646 mm, tip displacement 4.131746 mm. Other joints unchanged. Endpoint FAILED.
Together with preceding local trial (+0.005118416 rad / +3 counts), this supports
a narrow same-direction bias hypothesis, not a global correction. Next freeze a
constant local residual using both points and screen a held-out request whose
wire delta and desired response remain between these observed sample ranges.
Keep desired/wire scoring separate and original failures intact. No further
uncompensated staircase, no reuse of the older +5/+6-count posture correction.

21:16 UTC: isolated T101 elbow-history comparison exported and verified:
`wizard-20260917T211627982582Z-b7527b61e2d448c88c8af27b70a38cb4`.
Reused/generalized the receipt/payload-hash audit to elbow without mixing T102 or
T104. Earlier three distinct/repeated starts near elbow 1.53 rad gave +5 count
wire-target residual (0.008056958 rad); original 3-degree training gave +6 counts
(0.008999354 rad). Current similar-size request at elbow 1.762543925 gives +3
counts (0.005118416 rad). Identical sign is evidence of recurring bias, but the
amount changes with posture/history; old correction is not qualified unchanged.
No fitted model and no hardware movement. Next define one additional bounded,
uncompensated increasing-elbow identification target from the retained current
posture to test response consistency, before freezing a candidate for a separate
held-out destination. Do not call duplicated older trials independent posture
coverage, and do not relabel the current failed endpoint as corrected success.

21:14 UTC: isolated press-relevant elbow target qualified in software and attempted
once, without compensation. 39 transaction/native/pair tests passed. Exact reviewed
start/target binding, T101 joint3 only, 20/1. Preview export
`wizard-20260917T211357562578Z-005fa2e1ca974a2bb81f500076639f0e`.
Live verified export `wizard-20260917T211417782591Z-7a6acfc727ba4e6395a14ae328c02760`.
31 samples over 8.878663 seconds: elbow 1.762543925 -> 1.779417714, requested
1.7742992981223962. Requested +0.673533°, reported +0.966797°; predicted count
change +8, reported +11, residual +3 counts / +0.005118416 rad. Other joints
unchanged. Modeled desired-tip error 1.723303 mm; displacement 5.681119 mm within
the 6 mm progression guard. FAILED endpoint, no retry or return. Source SHA256
48235102ddbea8ad9836952711a318ac0551f7f1c3d6312acf260b2dec229f5b.
Next compare this isolated T101 elbow residual with prior direction-specific T101
elbow evidence, keeping T104/T102 results separate, before a frozen held-out
correction or independently screened return. Do not fit/deploy a correction from
this one sample, and do not issue the combined press yet. The current wrist-pair
exact-start profiles are no longer executable at the changed elbow posture.

21:11 UTC: recomputed the typing-relevant local press from the final repeated
wrist-pair export. Independently reconstructed raw feedback/model consistency and
2.255095-second stable desired-endpoint tail before using its posture. Added
identification_endpoint review; a success label alone is insufficient.
Verified offline export `wizard-20260917T211153372030Z-d80ef059e17f4471bd51de3afbf9850a`.
Model 2 mm press/retract IK passes. Full press joint demands: shoulder +0.110662°,
elbow +0.673533°, wrist -0.784089° (base/roll numerical changes negligible).
Isolated elbow desired target 1.7742992981223962 from 1.762543925; one-count
sampled hypothetical tip excursion 4.474321 mm. Combined independent-progress
screen samples 1,331 combinations, maximum 5.379359 mm versus 6 mm bound.
No hardware movement and no new compensation. Next qualify that exact isolated
elbow demand through a T101-only experiment with preserved other joints, fresh
start admission and endpoint export. The small shoulder adjustment also needs
qualification before claiming coordinated press readiness; wrist success alone
does not authorize the combined route. Camera/tool/board remain hypothetical.

21:10 UTC: TWO fixed wrist pairs completed, all four legs verified and exported.
Added explicit +/-one nominal count (+1e-8 serialization allowance) wrist-start
intervals, other joints fixed within 1e-8. Both interval extremes are screened;
targets/corrections remain unchanged. Four-leg maximum, stop on any leg/export
failure, with fresh native baseline and durable record comparison before each
next leg. 37 relevant tests passed. No T104 release or cross-joint scope change.
Campaign export `wizard-20260917T211015015242Z-6b5d2d2fcfec4023929dc40f990c5aab`.
Legs (all VERIFIED_AND_EXPORTED):
- Up `wizard-20260917T211005437930Z-80bfb9c76a1e41e7b620c69c88f42440`:
  wrist -0.046019424, modeled desired error 0.208530 mm.
- Down `wizard-20260917T211008507816Z-2739cccf734b480499f32878c4a954ee`:
  wrist -0.053689328, error 0.313785 mm.
- Up `wizard-20260917T211011601875Z-f67ad7b3ed4041dbae20e146305c339a`:
  wrist -0.046019424, error 0.208530 mm.
- Down `wizard-20260917T211014935627Z-2274705df5384aa79452b858c4f7ddb7`:
  wrist -0.053689328, error 0.313785 mm.
Other joints unchanged; elbow 1.762543925. Together with the preceding pair,
this is scoped repeated wrist control at one posture, not a coordinated vertical
press or physical metrology result. Next use this verified wrist behavior as a
component in a local multi-joint press preview; separately qualify elbow response
at this posture before live coordinated composition. Do not substitute continued
wrist-only repetitions for the unfinished ghost-keyboard objective.

21:07 UTC: descending posture-transfer trial PASSED desired endpoint and stable
tail with its unchanged historical correction. Added exact frozen-candidate/start
binding and a descending-only 1.5-degree observed/command bound; 6 mm modeled-tip
guard, other-joint drift guard, endpoint tolerances and ascending scope unchanged.
35 native/transaction/candidate tests passed. Preview export
`wizard-20260917T210721176332Z-3843fd1d78f241439711c3b9174094a4`.
One T101 wrist command -0.06913140077991495 at 20/1, desired -0.055223308.
Verified live export `wizard-20260917T210735607195Z-5daf20bbca82445e9a7ebb73580682bb`.
Seven samples: initial response -0.053689328, final -0.056757289; modeled desired
tip error 0.313786 mm versus wire error 2.531188 mm. Other joints unchanged.
This completes ONE local ascending/descending pair, with direction-specific
corrections; final wrist is one nominal count below the original reported start.
No extra return or retry. Repeated fixed-pair cycles are not yet established.
Next acquire fresh settled feedback, explicitly screen the one-count start
variation for the same fixed ascending/descending targets, then run a finite
repeatability campaign with per-leg desired checks and export-before-progression.
Do not silently relax exact-start binding or broaden this to elbow/Cartesian
typing. Physical tip accuracy and board registration remain deferred.

21:05 UTC: prepared descending return candidate OFFLINE, retaining the previously
frozen decreasing correction +0.013908092779914949 rad (wire = desired minus
residual). Parent identity 7aff3b4ac17b7c6d24843192a57426fab456508c74d2328e442a989e3134c834
verified; no fit uses the new posture or latest failed descending commands.
Rechecks the successful ascending export's desired endpoint and retained stable
tail, not just its status. Proposed start wrist -0.046019424, desired -0.055223308,
wire -0.06913140077991495 at 20/1; other targets unchanged, T101 wrist-only.
One-count sampled model envelope 5.041362 mm against 6 mm. Candidate hash
956ef6b3571719a1ab2ff1c7fea37ff51f84f1ed5f02f749cdf2f48cc8953373.
Initial verified preview export `wizard-20260917T210505241462Z-b8237c9ec63d44e2adc37043e27f179a`.
Eight candidate tests passed. No native admission or motion. Next bind this
immutable candidate to its exact fresh start and separate desired/wire scoring;
review its distinct <=1.5-degree command/observed bound (ascending remains
unchanged) before one live attempt. This posture transfer is not yet validated.

21:03 UTC: FIRST prospective reference-count-normalized ascending trial PASSED
the unchanged desired endpoint and stable-tail criteria. Exact frozen candidate
hash binding and fresh exact-start admission added; report/export now separates
desired and transmitted joints, joint residuals and modeled-tip errors. Desired
endpoint governs success. 37 transaction/runner/native tests passed, including
wire-in-band/desired-out-of-band rejection. Preview export
`wizard-20260917T210313098884Z-d2789c010113428b92eec752eb6b4c6e`.
One live command T101/joint4/rad -0.043466019212114355/spd20/acc1; desired -0.045.
Verified export `wizard-20260917T210328946326Z-0b32d64591154cb688d0f406a57ee317`.
Eight samples, wrist -0.055223308 -> -0.046019424; other five joints unchanged;
two-second stable tail satisfied. Desired residual -0.001019424 rad; modeled
desired-tip error 0.208530 mm, wire-tip error 0.522315 mm. The distinct metrics
matter: transmitted target is intentionally offset and is not the task endpoint.
This is one successful ascending transfer at one posture, not repeatability,
physical accuracy, a qualified descending return or ghost typing. No return sent.
Next qualify a separate finite descending leg from fresh feedback using existing
direction-specific evidence, then repeat a fixed endpoint pair with per-leg
desired verification and durable exports. Do not reuse the ascending offset for
descending motion without its own evidence and reviewed path.

21:00 UTC: froze an OFFLINE ascending candidate from the reference midpoint
difference, not a regression fit: command wrist = desired wrist +2*pi/4096 rad.
Compared against two independent ascending records without fitting either.
Counterfactual constant-response tip errors are 0.029640 and 0.345563 mm; these
are NOT measured corrected endpoints or held-out prospective validation.
Candidate desired wrist -0.045, wire -0.043466019212114355, retained start
-0.055223308 at elbow 1.762543925. Sampled one-count envelope 2.718795 mm.
Verified export `wizard-20260917T210045168003Z-73665e7b0aba485fb85dc2953869ad48`.
No motion. Next integrate this frozen candidate with independently scored desired
and transmitted endpoints, exact-start admission and export identity binding;
test failed-desired/successful-wire cases before one prospective live trial.
Do not broaden this source-derived wrist mapping to other joints or directions.

20:58 UTC: opposite-direction T101 wrist identification target -0.052 rad,
20/1, attempted ONCE after preview. Preview export
`wizard-20260917T205817945610Z-bd96c16be0ac4497a7791dd6bf3807a8`, sampled
one-count envelope 3.169602 mm. 26 native/transaction tests passed.
Live verified export `wizard-20260917T205837977415Z-3631210aa331486cb598544e23ccd9e2`.
Thirty samples: wrist -0.065961174 -> -0.055223308 (+0.010737866 rad), first
changed sample 0.578385 seconds after dispatch; unchanged tail 8.523183 seconds.
Other five joints unchanged. Desired wrist residual -0.003223308 rad; modeled
tip error 0.659348 mm, above unchanged 0.5 mm criterion. Directional progress
verified but endpoint trial FAILED; no relabeling or automatic return. Source
attachment SHA256 538d9b9b253f017375f2a8fe278736bbd2998fbefa9fec7c2736144d10f8088a.
This provides direction-sensitive response evidence at the current elbow posture,
not physical stylus accuracy or proof of a mechanical cause. Include it in the
historical count comparison. Next assess ascending count residuals against the
earlier independent ascending evidence before a frozen held-out correction trial;
qualify descending/return separately, since current descending nonresponses remain.

20:56 UTC: compared two earlier responsive T101 wrist trials with two current
nonresponses. Reproducible export:
`wizard-20260917T205655475374Z-7d4208839547479bb5422e71de5da9f7`.
All four payload hashes and receipt-body hashes verify. Same T101/joint4/spd20/
acc1 fields and numeric-feedback HTTP receipt kind. Earlier descending predicted
-17 counts yielded -6 by its endpoint-verification sample (later settling is
separate evidence); earlier ascending predicted +15 yielded +15. Current -5 and
-10 count targets yielded zero. Earlier elbow 1.691980809 differs from current
1.762543925: not a matched-start A/B trial or a measured deadband threshold.
Raw receipt wrist load differs 45 vs25, but is not calibrated force or a causal
diagnosis. No fitted correction, authority or new movement. Added dual-format
comparison code retaining original verdicts and explicit count-domain residuals.
Next prioritize a bounded opposite-direction T101 identification at this posture
to distinguish directional response from universal wrist nonresponse; preview
first and keep the same endpoint criteria. Do not automatically replay the old
descending correction or increase descending commands as a staircase.

20:55 UTC: distinct T101 wrist target -0.080 rad screened and attempted once.
Named scope allows <=0.016 rad only for this fixed wrist target from baseline
-0.065961174 +/- one nominal count; T102 scope and endpoint tolerances unchanged.
25 transaction/native tests passed. Preview sampled one-count tip maximum
3.185486 mm, export `wizard-20260917T205456723356Z-4e5715d0544a470ba1488e8ffe2af7d4`.
Live export: `wizard-20260917T205516533663Z-8c9403ebd3714b3db411695db12db21a`.
Thirty samples: wrist unchanged -0.065961174, elbow unchanged 1.762543925,
all other reported joints unchanged. Wrist desired residual +0.014038826 rad,
modeled tip error 2.871709 mm; no directional progress; completion-window failure.
Export verified. No return or second motion. This extends observed nonresponse
to the larger target, but does not establish deadband as cause. Do not continue
an automatic amplitude staircase. Next compare exact payload/receipt/reference
count targets with historical successful T101 wrist records and inspect available
read-only controller information before defining another experiment. Retain the
unchanged-feedback ambiguity; no compensation can be learned from this result.

20:53 UTC: implemented and tested a named T101 wrist comparison in the same
bounded transaction/export runner (32 tests passed). Exact payload is T101,
joint 4, rad -0.071961174, spd 20, acc 1; no other joint targets on the wire.
Preview export `wizard-20260917T205306243603Z-824bf2871a894bca89e7586e3df16ad1`.
Fresh elbow was 1.762543925, one nominal count beyond the last prior T102 sample;
do not call this a matched-start A/B comparison. Executed one T101 attempt:
`wizard-20260917T205330864210Z-209fca03b0be4574a070160548049c1b` (verified export).
Thirty immediate feedback samples: ALL joints unchanged, wrist -0.065961174,
desired wrist residual +0.006 rad, modeled desired-tip error 1.227337 mm.
No directional progress; completion-window failure. No retry or return.
The small wrist nonresponse is present under both command families; the T101
trial did not reproduce elbow drift. This does not identify deadband or prove
encoder freshness. Next screen a distinct wrist-only target outside the observed
small-step nonresponse interval against earlier T101 response evidence, with
explicit range review and unchanged acceptance criteria. Do not fit compensation
from unchanged feedback or expand T102 coordinated testing from these failures.

20:51 UTC: isolated wrist T102 experiment (-0.006 rad at 20/1) preview passed
with 1.541121 mm sampled one-count hypothetical tip envelope. Preview export
`wizard-20260917T205104175393Z-98ccaaafede2444d8612dcf11e04bb1a`.
Executed ONCE from fresh baseline. Immediate telemetry now works: 30 samples,
wrist unchanged -0.065961174; elbow moved 1.753340041 -> 1.761009944 despite its
unchanged angle target. Final modeled desired-tip error 3.795181 mm; observed
tip displacement 2.586584 mm. Completion-window failure export verified:
`wizard-20260917T205124547880Z-14721dd0f93e42229fcbcc6e88a1b17e`.
No retry, return or compensation. This is evidence of non-test-joint drift under
T102, not proof of a physical cause. Added explicit >0.004 rad non-test-joint
drift fault for future transactions; retained failure is not relabeled.
Next compare a separately reviewed single-joint wrist command against the same
absolute target, with fresh feedback and preserved one-use/export checks. Do not
escalate T102 amplitude or proceed to coordinated typing from this result.

20:49 UTC: offline T102 count review exported and verified:
`wizard-20260917T204927316884Z-7b7a3ee0cb00485eac83caf03c68a334`.
Source artifacts/hash integrity and passive feedback originals are checked by
review_t102_response.py and all_joint_response_review.py. Reference predicted
elbow count change +2 versus reported +6 (target residual +4 counts); wrist
predicted -3 versus reported 0 (target residual +3). Rounding alone does not
match the reference count targets. Base/shoulder/roll unchanged angle commands
predict a -1 count target shift because command midpoint 2047 differs from
feedback midpoint 2048; their reported counts stayed unchanged. Thus numerical
non-test angle preservation is NOT a servo-count hold guarantee. No correction
applied; installed source and actual bus writes remain unverified. Passive
capture began 28.6373 seconds after dispatch, so it cannot prove the path taken.
Next use these count-domain distinctions to design a bounded direction-specific
identification trial with working immediate feedback; do not claim that explicit
T102 settings alone solved coordinated control. No motion in this review.

20:46–20:47 UTC: first native T102 identification attempted once. HTTP receipt
received; no runner feedback samples because send time plus quiet period left
less than the required 800 ms read budget inside the first one-second window.
Failed trial export verified:
`wizard-20260917T204600889945Z-29fa41ba84364dc7b7d39464ec5ce3a9`.
No resend or return. A separate 35-second read-only capture exported as
`wizard-20260917T204704544754Z-55f811903612428d8ec31d37e89a2421` contains 116
successful samples over 34.915942 seconds, all six joint spans zero. Elbow is
1.753340041 (change +0.009203885 versus requested +0.003 rad); wrist remains
-0.065961174 (requested -0.003 rad). Other joints unchanged. This is a retained
post-command response, NOT a captured trajectory or passing endpoint trial.
T102 explicit settings therefore have not resolved the response discrepancy.

Fixed initial feedback scheduling: timely command receipt starts the first
one-second observation window; the ten-second completion deadline still starts
at dispatch. Receipt timing is exported. Late/duplicate receipt is rejected.
Runner tests now use the real 800 ms feedback budget and a 300 ms simulated send
instead of unrealistically short timing. 46 focused tests passed. No second
motion was sent. Next review quantization, requested versus returned servo-domain
targets and small-step deadband using retained evidence before selecting a
different identification trial. Do not fit a correction or retry this failed
relative move blindly; fresh baseline is required for any later experiment.

20:45 UTC: native T102 adapter added with read-only default, transport lock,
fresh baseline, existing exact native-send latch and real WizardDiagnosticExporter
verification. Named experiment is elbow +0.003/wrist -0.003 rad at 20/1; this is
an uncompensated identification point, not a keypress. Receipt is retained inside
the exported run. 44 focused tests passed, including native composition with fake
I/O and real verified exports. Real read-only preview succeeded and exported to
`wizard-20260917T204518908310Z-94106bd70a53486180e133c8b71a69ed`.
Fresh feedback retained elbow 1.744136156/wrist -0.065961174. The 121-sample
independent-progress/one-count stress maximum is 1.529034 mm against the 6 mm
model bound. Zero motion commands sent. Next one explicit execution of this named
identification experiment, acquiring a new baseline rather than replaying this
preview; review raw joint progress, settling and signed error before any return.
This preview neither validates installed T102 behavior nor establishes physical
clearance or tip accuracy. Native T104 hold remains unchanged.

T102 reservation/runner integration: WifiAllJointReservation now reuses the
existing durable exact-command consume and native-send latches. Baseline admission
checks pinned identity, cleanup, monotonic timing, retained response integrity and
age. The injected all_joint_runner enforces one send attempt, bounded observation
windows, cancellation, per-sample response reconstruction and export-before-
progression. Simulated integration exercises actual reservation files, including
the native-send latch, and records the settled-pending-export report before marking
progression ready. Nine integration cases cover success, wrong identity, cancel
before/after dispatch, lost receipt, corrupt feedback, unchanged feedback and
invalid/failed exports. First focused run: 41 tests passed. No sockets or hardware
used. Next supply the native locked adapter and real WizardDiagnosticExporter
verification callback, test that composition with substituted I/O, then preview
one named live identification trial. T104 is still held; T102 is not yet exposed
as a live wizard action. Callback simulation is not proof of a real exported run.

T102 transaction update: added offline AllJointTransaction with one dispatch
attempt, <=1 second baseline age/feedback gap, fixed 20/1 settings, <=0.5 degree
elbow/wrist deltas, sampled one-count response screening and observed 6 mm
hypothetical-tip/1 degree joint excursion guards. Endpoint qualification requires
<=0.5 mm modeled-tip error, <=0.004 rad per-joint residual, at least half the
requested signed progress on each changed joint, and a two-second stable tail
within one nominal encoder count. Directional progress prevents unchanged feedback
from passing merely because a small target lies within endpoint tolerance.
Reports retain raw feedback, signed residuals, command, target, timing and preview.
Progression stays pending until the adapter confirms durable verified export;
uncertain delivery cannot replay. 41 transaction/protocol/envelope/history tests
passed, including no-response deadline, excursion, dwell reset and export failure.
No hardware accessed. This state machine is not yet a native runner: next bind
fresh identity-matched feedback, exact one-use payload reservation, transport lock,
deadline/cancel handling and actual export verification in the adapter. Preserve
T104 hold. Criteria above are provisional identification tests, not physical
clearance, synchronized actuator motion or contact accuracy certification.

Protocol qualification update: verified the official reference archive SHA256
`a28247fee0bbb65cc034ff206031b8700d2b1ec8e3a1fa4b1a5a7365c55f1a57`.
json_cmd.h identifies CMD_JOINTS_RAD_CTRL as 102; uart_ctrl.h:23-33 maps
base/shoulder/elbow/wrist/roll/hand plus spd/acc to allJointAbsCtrl.
Added offline arm/all_joint_command.py and tests: exact packet/roundtrip,
non-test-target preservation, finite angles and explicit integer settings.
49 protocol/history tests passed. Argument-width limits are not safe rate limits;
the builder grants no motion admission and is not connected to native execution.
No hardware access or movement. Next integrate bounded trial policy, measured
baseline freshness, per-joint and modeled-tip trajectory/settling checks and
export-before-progression into a separately tested T102 transaction. Reference
source is still not identification of installed firmware. T104 hold remains.

20:30 UTC: finite response-domain scan exported as
`wizard-20260917T203052579967Z-e99007d151a44a23bb0469b54b25e9e2`.
At retained stable posture elbow 1.744136156/wrist -0.065961174, 25 interior
response combinations were evaluated without refitting. Five pass the sampled
one-count independent-progress stress, zero meet vertical press geometry; best
sampled desired tip error relative to [0,0,-2] mm is 1.686908 mm. Finite scan is
not a proof of continuous infeasibility, and the underlying response model remains
prospectively invalidated. No candidate selected and no hardware movement.

Next discriminating branch: qualify explicit all-joint control separately from
Cartesian interpolation rather than recursively tuning this narrow affine model.
Pinned reference module.h:825–840 shows allJointAbsCtrl applies explicit speed/
acceleration to a synchronous servo write then clears shared arrays; Cartesian
control uses shared arrays. This is a command-family/state difference, not proven
cause. Before any native trial:
1. Verify exact all-joint protocol fields and conversions against official source;
   preserve every non-test joint target and model command-state side effects.
2. Build simulation/transaction tests for explicit settings, single dispatch,
   telemetry verification, cancellation, response-skew envelope and durable export.
3. Define one bounded identification endpoint from fresh feedback, not an eight-leg
   ghost route or an unqualified return. No changed firmware/torque/PID settings.
4. Treat it as a different experiment, not a direct A/B comparison unless start,
   desired target and other settings are matched. Keep T104 hold in place.
5. Require reproducible direction-specific response and return behavior before
   coordinated press/retract and ghost-key progression. Do not claim that sending
   all joints in one packet guarantees synchronized physical motion.

20:28 UTC: asynchronous joint-progress stress review identifies insufficient margin
in the rejected affine trial, without claiming a physical root cause. Export
`wizard-20260917T202857256416Z-9092d966e9a6463ba11bc671277d03ec` samples 121
independent elbow/wrist progress combinations. Nominal response maximum tip
displacement is 5.792718 mm (elbow advanced, wrist unchanged); one additional
nominal encoder step yields 6.309910 mm, beyond the existing 6 mm limit. This
scenario is consistent with the type of intermediate state seen in the live fault,
but does not prove continuous bounds, encoder freshness or actuator dynamics.
Added reusable asynchronous_response_review and integrated the one-step stress
screen into offline affine candidate generation. The old candidate is now rejected
by that builder; its immutable export and failed hardware verdict remain unchanged.
41 response/candidate tests passed. No hardware access or motion in this update.

Next: evaluate whether any within-domain coordinated candidate retains response
margin under independent joint progress, before considering live qualification.
Do not reduce the original typing objective to this diagnostic, silently expand
the model range, or infer that a passing sampled screen guarantees physical clearance.
The separate endpoint-response failure still requires prospective validation even
if a better-screened path is found. Native T104 hold remains in force.

IMPORTANT correction: full reference assignment scan found the feedback path
updates stored XYZ/pitch too. Module.h:614–619 assigns lastX/Y/Z/T from FK;
getPosByServoFeedback invokes FK at 642, and T105 calls it at uart_ctrl.h:60–62.
Our native runner queries T105 before each command. The prior-goal-only replay
therefore omits a relevant event and does NOT prove the actual preview origin
was wrong. Withdraw that causal interpretation; preserve replay as counterfactual.
ReferenceCommandHistory now models explicit feedback acquisition, preserving
stored roll (not assigned by that FK path) and invalidating unknown acquisition
values. Ten simulator/history tests passed. Documentation corrected, no motion.
Native hold remains due to the failed prospective model and observed tip-bound
excursion, not a proven stale-origin issue. Next examine joint timing/servo response
with this feedback path represented; do not build further fixes on the superseded
claim below. Installed firmware/acquisition behavior remains unverified.

Command-history distinction implemented in simulation, with native commissioning
T104 hold enforced before hardware I/O. `ReferenceCommandHistory` preserves stored
commanded goals independently of feedback; previewing does not mutate state,
T105 does not synchronize it, unknown/interrupted histories fail explicitly, and
unmodeled intervening command families invalidate the hypothesis. Dual traces
remain reference hypotheses, never installed-state attestation. The
`run_native_vertical_trial` T104 path now returns
T104_INTERPOLATION_START_STATE_UNQUALIFIED without acquiring a connection or
sending anything; T101 commissioning remains separate. This hold is scoped to
that commissioning adapter, not a claim that every possible external control
surface is disabled. 34 command-history, simulator and Cartesian tests passed.
No physical motion sent. Next integrate history-aware retrospective analysis and
establish installed-controller behavior before replacing this hold with a reviewed
admission contract; there is no override switch or synchronization move.

20:23 UTC: identified a concrete reference-model mismatch. T104 reference firmware
interpolates from stored previous goal, while recent previews began at reported
feedback. Replay of the affine trial from these two hypotheses yields 4 versus
102 reference samples and 0.829 versus 5.834 mm maximum modeled tip displacement.
Prior commanded goal and actual reported start differ by 5.078 model mm.
See [COORDINATED_INTERPOLATION_HISTORY_REVIEW.md](COORDINATED_INTERPOLATION_HISTORY_REVIEW.md)
and export `wizard-20260917T202307336985Z-3ff118fe9ec04eb7909c22a31c761069`.
Official archive hash verified; installed implementation remains unverified.
No motion sent. Suspend additional T104 candidate trials until admission represents
this start-state uncertainty; do not reset/synchronize by sending the measured pose.
Next track/replay command-state history separately and reassess response fitting
against that history, then design a discriminating bounded test.

20:20 UTC: prospective affine-interior trial STOPPED on observed model-tip bound.
Live export `wizard-20260917T202005073864Z-4a7bed0ff01649c3b16e0e62452abdc7`.
First feedback sample: elbow 1.744136156, wrist still -0.064427193; modeled tip
displacement 6.206472318 mm exceeds 6 mm. No further movement command, no retry,
no retract. This progression guard is not a hardware emergency stop and does not
prove the actuators halted immediately. Subsequent read-only observation export
`wizard-20260917T202055447509Z-0997b263015e431e838d73b237b36d0e` retained 115
successful samples across 34.8358 s with zero joint spans: elbow 1.744136156,
wrist -0.065961174; other joints unchanged. Thus wrist changed after the fault
sample but the later plateau still does not match the predicted joint response.
The affine mapping is NOT validated for command deployment despite retrospective
prediction success. Candidate remains experimental; never widen the bound or
relabel this fault as success based on later samples. 68 tests passed before live
execution; 26 candidate tests passed afterward including a retained intermediate
joint-timing-skew regression that cannot be overwritten by later desired arrival.

Next: diagnose state/history dependence and intermediate joint response separately
from endpoint fitting using retained evidence. No further forward candidate presses
or automatic parameter escalation. A new experiment must discriminate competing
response explanations; mere recursive refitting has now failed prospective tests.

20:18 UTC: prospective inverse-model domain review completed offline. A 2 mm
vertical press from the current pose would require elbow wire delta +0.043425
degrees (training range +0.400752..+0.732414) and wrist -1.698464 degrees (training
range -1.478006..-0.783273). Both extrapolate; no vertical press promoted.
Prepared instead an explicitly nonvertical, bounded coordinated model-validation
trial using fixed 60%-interior response points in both training domains, without
refitting. Export `wizard-20260917T201815261974Z-ed05b78c956046cca2f21cdad0c14675`,
candidate SHA256 `c322d3db96a664f86cab305180ba99917154aa4d9c7df75dabcd6da13e121075`.
Desired elbow/wrist deltas +0.984375/-0.298828 degrees; wire +0.599749/-1.061166.
Model wire tip sweep 0.829007 mm; predicted actual response tip delta approximately
[-2.115438,-0.003237,-4.262892] mm, within the existing 6 mm displacement bound.
This is NOT a vertical keypress and does not replace the original ghost-typing
objective. Starting posture/history transfer remains prospective. No hardware
access; candidate not yet connected to a native command mode. Next test the frozen
interior candidate with desired-endpoint and response-envelope checks before using
the model to justify any extension toward coordinated press/retract.

20:16 UTC: offline chronological response comparison favors command-size-dependent
prediction over constant bias on two newer observations. Export
`wizard-20260917T201603834704Z-6d84f5b22d7d46829d1471bf7867c04c`
contains readable Markdown and source-hashed JSON. `analyze_coordinated_response.py`
fits older two coordinated presses, scores latest two without refitting, and flags
out-of-training-range predictions. Elbow affine slope 0.530001/intercept +0.666507
degrees: held-out max reported-angle prediction error 0.028563 degrees versus
0.131834 constant-offset error. Wrist slope 0.759059/intercept +0.506660 degrees:
0.001155 versus 0.084851 degrees. Four regression tests passed, including no
held-out fitting leakage and explicit extrapolation labels. No device access.

This is reported-response prediction, NOT proof an inverse command correction
will achieve its target. Four observations, changing postures and prior motion
history confound causality; two-point training fit is exact by construction.
Latest elbow prediction and latest uncorrected wrist prediction are outside the
older training ranges. No model deployed and no reverse-direction inference.
Next prepare a bounded prospective inverse-model trial only where desired response
and wire delta are inside the empirically supported same-direction range; screen
the resulting multi-joint path and preserve a held-out physical trial. If that
cannot satisfy the bounds, do not extrapolate merely to produce a command.

20:14 UTC: frozen coordinated held-out candidate tested once and FAILED desired
endpoint: 1.108414491 controller-model mm; wire error 5.078156106 mm remains
separate. Live export `wizard-20260917T201423927986Z-2d8334fcc06a430eb158652560d12a63`.
29 observations, no runner error; no retry/retract. Candidate was hash-bound to
the prior export, exact-start screened, and monitored with the 6 mm modeled tip
bound. 67 related tests passed; new mode requires desired endpoint verification.
Final reported joints [.001533981,.033747577,1.725728386,-.064427193,.018407769,3.138524692].
Desired elbow/wrist residuals +0.182425/+0.167023 degrees; wire residuals
+0.532048/+0.861250 degrees. The scalar correction does not qualify this coordinated
path even though the held-out model error is smaller than the prior uncorrected
trial's error at a different target. Do not claim controlled A/B improvement.

Next: review command-size/direction dependence across retained coordinated samples
before choosing another model or command; no more recursive one-sample additive
refits followed by forward presses. Hold further coordinated progression until a
specific discriminating experiment or better-supported scoped mapping is prepared.
Retraction/ghost sequence remains unqualified; all prior failed verdicts retained.

20:11 UTC offline comparison and frozen coordinated candidate completed. Earlier
uncompensated press export `wizard-20260917T182619277841Z-90592a21fcd14c78be0a319d0bdc6038`
had elbow/wrist signed residuals +0.322274/+0.695382 degrees; latest uncompensated
press has +0.349622/+0.694226 degrees. Earlier corrected trial
`wizard-20260917T183047269334Z-94f355c5112a48cfae9ac624121a1637` differed at
+0.478155/+0.862772 degrees relative to its wire targets: not evidence of a global
constant bias. Preserve desired-versus-wire distinction when comparing these.

Candidate export `wizard-20260917T201134178702Z-e0e999596ce14686be89309aa4918729`;
SHA256 `563d49058fd7497f46b7441434981e8bc27ae1538055d99cfdb443b7ee4ebd56`.
Separate post-transfer scope estimates elbow/wrist additive residuals from the
latest settled coordinated trial, then screens a distinct 2 mm hypothetical tip
endpoint from its final pose. Maximum wire tip sweep 3.092714 mm, controller sweep
2.089872 mm and joint excursion 1.476484 degrees; retains a 6 mm tip bound.
No hardware access, no global enablement, held-out validation still required.
23 candidate tests passed. Next bind this exact artifact/hash to one separately
admitted held-out command with desired-endpoint verification and no automatic
retract. The candidate is not currently selected by any native dispatch mode.

20:10 UTC: one direct coordinated 2 mm hypothetical press executed and FAILED
reported endpoint, with no retry or retract. Scoped `--post-transfer-tip` requires
the verified starting pose, screens direct T104 interpolation and monitors a
6 mm hypothetical-tip displacement bound. 43 related tests passed before dispatch.
Live export `wizard-20260917T201014338834Z-fe2b6eb0afe14b93901dfbaedc4e1ccf`;
trace review `wizard-20260917T201023036517Z-cd4fd517cfec4247824765bd6db63140`.
Thirty observations, no feedback failures. Model endpoint error 3.615386713 mm;
elbow requested +0.705065 degrees/reported +1.054687 degrees, wrist requested
-0.782117/reported -0.087891 degrees. Shoulder requested +0.077163 degrees and
reported no change (reference conversion predicted zero count change). Payload
and reserved command hashes match, IK expectations match; this is not explained
by reference quantization alone. Both changing joints reached the retained plateau
by the first observation at 0.3788 s and remained unchanged for 8.9097 s.
Final reported joints [.001533981,.033747577,1.710388578,-.053689328,.018407769,3.138524692].

Next: compare this coordinated response with retained single-joint and coordinated
evidence and freeze a scoped correction hypothesis before any further command.
Do not directly reuse successful wrist-only compensation as a Cartesian offset,
resume a full ghost sequence, or issue the unqualified decreasing-elbow retract.
The successful wrist cycles remain valid only in their recorded start scope.

20:08 UTC: coordinated 2 mm press/retract simulated from the verified final hold
pose, not an earlier completion sample. Controller-reference export:
`wizard-20260917T200832068764Z-2195fd95cacf4df8ac543603873af2aa`.
Eight segments pass reference IK/interpolation screening; maximum joint excursion
0.782117 degrees and lateral drift 0.00081543 model mm. These numerical geometry
results are not actuator accuracy. Press demands shoulder +0.07716 degrees
(0.878 nominal encoder steps), elbow +0.70507 degrees (8.022 steps), wrist
-0.78212 degrees (-8.899 steps); retraction reverses those directions. Nominal
step estimates explicitly do not predict firmware quantization or servo response.
The decreasing-elbow part overlaps the unresolved no-response direction, so a full
physical press/retract sequence remains unqualified. No motion sent in this update.
20 local-tip tests passed. Preview exports now select verified post-completion hold
poses when present and reject failed holds rather than silently using older poses.

Next: review the response evidence against these coupled joint demands and qualify
one bounded coordinated leg (not an automatic eight-segment sequence), retaining
signed per-joint errors and post-completion hold evidence. Do not transfer the
wrist scalar correction into Cartesian XYZ or treat ideal IK as measured accuracy.

20:06 UTC: TWO new-posture finite wrist cycles completed, all six legs passed
endpoint and mandatory hold review with per-leg verified exports. Cycle indexes:
`wizard-20260917T200622003481Z-305c15023c26445fa8426f9cbb6ced7e` and
`wizard-20260917T200643214039Z-9fd3bf0acc87480e9dd4216c20df8213`.
Both retained identical final reported wrist endpoints per leg:
-0.064427193, -0.075165059, -0.052155347; elbow 1.691980809 unchanged.
Post-hold desired model errors respectively approximately 0, 0.028425426 and
0.489891869 mm. Each cycle closed at its starting six-joint reported pose.
First cycle final leg changed during hold, then stabilized; second cycle had no
post-completion changes. All hold checks retained 10-11 samples with over two
seconds unchanged tail. No physical tip accuracy inferred. 48 related software
tests passed before execution. New `--transfer-cycle` always requires hold review;
its three exact-start scopes remain separate from the historical mapping cycle.

Next is coordinated local noncontact geometry/command qualification, not further
wrist-only repeats. Re-evaluate the elbow response requirement and small coupled
approach/press/retract from this verified local starting posture. Wrist cycle
success does not resolve the earlier decreasing-elbow no-response or authorize
physical contact/full keyboard traversal. Preserve per-leg export and hold checks.

Cycle hold integration implemented (software-only): `bench_compensated_wrist_cycle.py
--require-hold` collects a bounded three-second feedback-only observation after
each successful compensated leg. The cycle independently reviews the raw hold
evidence before proceeding, exports the full observation with the leg, and passes
the verified final hold pose to the next exact-start check. Missing/invalid hold
evidence stops progression; no retry or recovery return. Existing historical
cycles retain their original behavior unless this explicit option is selected.
Other-joint changes during a hold are rejected. 31 cycle/hold regression tests
passed, including missing hold evidence at every leg and a complete synthetic
three-leg cycle. No physical cycle executed in this update. Next implement the
separately scoped three-leg cycle for elbow 1.691980809 with hold required by
default; do not execute the old elbow-1.67357304 mapping cycle at this posture.

20:02 UTC: increasing transfer endpoint held in subsequent read-only observation.
Observation export `wizard-20260917T200131279398Z-5549ad5dbf1a4430bf2a888d20ef7965`:
116 samples across 34.9308 s, no reported joint changes. Verified-source review
`wizard-20260917T200221780415Z-904be2dc901344a88a69f313e4955e56` reports
REPORTED_HOLD_VERIFIED: desired error stayed 0.489891869 model mm; final wrist
-0.052155347, elbow 1.691980809, unchanged since completion. No movement sent.
Added `review_endpoint_hold.py` and pure endpoint_hold_review: requires clean
compensated completion, identity/model-consistent observations after the trial in
the same host clock, bounded observation gaps, desired-band retention and a stable
reported tail. Six unit tests passed. Review is evidence, never motion admission
or independent sensor freshness. Next integrate this evidence distinction into
the new-posture finite cycle; historical exact-start cycle is still not admissible
at the changed elbow. Do not rerun the uncorrected wrist diagnostic just to prepare
the cycle: its known reported endpoint should be an explicit preparation hypothesis.

19:59 UTC: increasing wrist posture-transfer trial passed desired reported endpoint.
Initial reverse preflight correctly rejected the early completion pose: wrist had
advanced from -0.073631078 to -0.075165059 after the previous trial completed.
Read-only observation export
`wizard-20260917T195919619596Z-1342b0bc659d46cca036adfef6f227fc`
retained 110 successful observations over 35 seconds, zero reported joint spans,
zero movement commands. This is reported stability, not encoder freshness proof.
The transfer's exact start was explicitly updated to that observed stable pose;
regression rejects the earlier pose. Original interpolation coefficients unchanged.
48 related tests passed, then four focused tests passed after the start update.
Preflight/candidate export:
`wizard-20260917T195950574802Z-23cdff0bc1b34b7bb5b72576b1b6352c`.
Live result:
`wizard-20260917T195958969852Z-3ac3e0c83e9d496eaf7ec3676d51460f`.
Desired wrist -0.055, wire -0.050766266637881065 rad, speed 20/acceleration 1;
reported endpoint -0.052155347, state COMPENSATED_REPORTED_ENDPOINT_VERIFIED.
Elbow stayed 1.691980809; other joints unchanged. One command, no automatic next leg.

Next: verify post-completion stability before treating that endpoint as cycle start,
then qualify a finite repeated cycle at this elbow posture. Keep endpoint-in-band
completion distinct from stable-start admission: the previous one-count settling
change must not trigger blind continuation or be mislabeled as a communication fault.
Coordinated ghost typing and physical accuracy remain unqualified.

19:56 UTC: first held-out wrist posture transfer PASSED desired reported endpoint.
The original decreasing scalar correction was retained without refitting; only
elbow posture and derived geometry changed. Frozen candidate export:
`wizard-20260917T195616082312Z-188f940f96574e8c82222b106be27d0d`,
candidate SHA256 `21c0a15d7dca8626cf8caae774c570785aea45142fcc0b3739e892aba6cbf797`.
Related candidate/transaction/runner tests: 59 passed. Preflight matched exact start,
predicted hypothetical tip sweep 5.007600914 mm, with feedback-time 6 mm bound.
Live export:
`wizard-20260917T195626116113Z-de37dc78d4a04d82b6753701b8b387c0`.
Desired wrist -0.075 rad; transmitted -0.088908092779915 rad, speed 20/acceleration 1;
reported final -0.073631078 rad. Four observations, no runner error, acknowledged.
Desired error 0.235748997 controller-model mm / +0.078433453 degrees; state
COMPENSATED_REPORTED_ENDPOINT_VERIFIED. Wire-target error remains 2.630905581 mm
and is NOT relabeled as a wire-target pass. Observed modeled tip displacement
1.882707401 mm; other joints unchanged, elbow 1.691980809.

This is one successful held-out transfer, not repeatability or physical accuracy.
Next qualify an increasing-direction leg from the newly reported wrist posture
without using the old exact-start increasing map indiscriminately, then return to
a reviewed starting state and repeat the same frozen decreasing candidate. Only
after that cycle evidence should coordinated ghost-key segments resume. No
automatic return or follow-up command was sent after this trial.

19:53 UTC: completed one separately scoped, uncompensated wrist response trial at
the post-overshoot elbow posture, using `--post-overshoot-wrist`. Exact six-joint
start enforced; no earlier correction reused. Preview predicted 5.355122416 mm
hypothetical tip sweep; feedback-time 6 mm model guard retained. Related tests:
59 passed. Live export:
`wizard-20260917T195349139361Z-b4961d687f4b4680b9c6afa24adbcc9e`.
Trace review:
`wizard-20260917T195358328182Z-8bce167f47ea4748ae47ae100d81e28b`.
One T101 wrist command, speed 20/acceleration 1, requested -1.5 degrees; reported
change -0.703124983 degrees across 30 samples. Other joints unchanged; no feedback
failures. Endpoint failed: 2.395162901 controller-model mm, +0.013908092779915 rad
wrist residual. Last reported change at 0.6063 s, unchanged tail 8.4842 s. No return
or retry sent. Final reported wrist is -0.064427193, elbow remains 1.691980809.

The wrist-angle residual exactly matches the earlier uncompensated trial at elbow
1.67357304. This supports a separately scoped held-out test of the existing wrist
correction at the new elbow posture, not automatic transfer of its qualification.
Next freeze that transfer hypothesis, screen its new-posture geometry, and test
one desired endpoint before any cycle. Preserve the failed uncorrected verdict;
do not resume the unresolved decreasing-elbow sweep. This trial demonstrates
changing wrist feedback, not verified freshness of every servo or physical tip accuracy.

Follow-up verification: read-only preflight export
`wizard-20260917T195020355228Z-823e312a8ed04041b8845090f294ade5`
matched the expected network identity and returned the retained six-joint pose
[.001533981,.033747577,1.691980809,-.052155347,.018407769,3.138524692].
Zero motion commands; successful HTTP response does not establish encoder freshness.
No newer motion export was found to bind the operator observation unambiguously.
Expanded ghost endpoint regression coverage to inject seven fault types at each
of all eleven dispatched legs (77 cases), including press/retract boundaries and
the final leg. Each verifies stopped progression, no automatic retry and zero
physical device access. Combined ghost rehearsal, product/controller bridge and
joint diagnosis test run: 99 passed. This verifies simulation fault handling, not
live endpoint accuracy or completion of the ghost-typing goal.

The operator now reports: "i did see it! looks like it works i saw it move."
Record this as visible movement during the latest demonstration, not a measured
angle, verified elbow endpoint, or proof that earlier unchanged-feedback trials
actually moved. The observation is not yet bound here to a specific exported trial.
Do not manufacture that association or assume the historical reported pose is current.

1. Reconcile the latest demonstration with available command/export records. Attach
   the operator observation if the trial can be identified unambiguously; otherwise
   retain it as an unlinked observation. Inspect fresh feedback before planning motion.
2. Preview one bounded single-joint trial from that current pose using the existing
   command path. Capture baseline, exact transmitted target, acknowledgement, feedback
   progression and settled endpoint. Compare desired and transmitted targets separately.
   A visible move alone is not an endpoint pass. No further large demonstration is needed.
3. If the trial is interpretable and passes predeclared checks, perform a finite
   out-and-back cycle, then repeat it to assess directional residuals and repeatability.
   Each return is a separately checked leg, never automatic recovery after a failure.
4. Retain successful posture/direction/speed-specific corrections; fit new corrections
   only from responsive data and test on held-out movements. Do not reuse the earlier
   wrist cycle if its exact-start elbow/posture requirements do not match.
5. Qualify coordinated local noncontact approach/press/retract, then one ghost key
   and a short adjacent-key sequence. Stop progression if an endpoint or feedback
   check fails; export the failure and diagnose before scheduling another leg.
6. Summarize results in readable exports: success rate, signed reported/model residuals,
   repeatability, settling time, failures and compensation scope. Keep camera mounting,
   actual stylus transform, board registration and physical contact explicitly deferred.

Packaging repair and the reproducible evidence bundle are already completed; they
are not prerequisites to redo. The old small-decreasing-elbow parameter sweep stays
closed. The new observation supports a separately reviewed, bounded correlation
trial, not blind speed/amplitude escalation or erasure of earlier failures.
No new hardware command was sent as part of this plan update.

#### Retained diagnostic history (not current next-action instructions)

19:45 UTC reproducible elbow evidence bundle assembled and verified offline:
`wizard-20260917T194508596472Z-92bdec945071487699aab40e2ec4b4ee`.
It contains all four complete trial reports, source hashes, compact JSON diagnosis
and a readable elbow-summary.md. No device access or external upload. Classification
is respectively no reported response / same-direction reported response / no
reported response / no reported response. Added joint_response_diagnosis to trace
review, keeping response classification distinct from endpoint success and all
freshness/physical-cause/training-authority claims false. 32 related tests passed.

An optional question asks whether the operator actually observed the last two
small decreasing trials, because that could distinguish physical nonresponse from
unchanged acquisition. Do not treat silence, prior broad visual confirmations or
uncertainty as confirmation of either physical outcome. Live parameter branch
remains stopped; use this bundle for targeted non-mutating diagnosis and preserve
the working wrist regression rather than inventing a root cause.

19:42 UTC speed comparison completed without reported elbow response. Added
`--post-overshoot-elbow-speed40`; same goal 1.683980809, exact starting elbow
1.691980809, acceleration 1, unchanged path and 6 mm observation bound. Reservation
speed metadata now derives from the exact admitted command rather than hardcoded
20. 55 related tests passed; fresh preflight matched. Verified live export:
`wizard-20260917T194218360472Z-ab9990310e9141fe8cdef162b3bac6d0`.
Endpoint failed with elbow unchanged and 2.533397018 modeled mm residual. Export
confirms wire/configuration both speed 40, acceleration 1; no runner error.

Speed 20 versus 40 did not discriminate the small decreasing no-response. STOP
this live parameter-testing branch: do not continue higher speeds, larger moves,
gain/torque changes or correction fitting from these zero-response points.
Current reported posture remains
[.001533981,.033747577,1.691980809,-.052155347,.018407769,3.138524692].
Next meaningful work is an evidence bundle and non-mutating diagnosis that can
distinguish actual elbow motion/servo acquisition from command acceptance. Existing
interface lacks verified per-servo acquisition status. If independent evidence
requires an operator observation or additional diagnostic interface, state that
specific dependency rather than rerun the same unsupported experiment. Continue
software/simulation regression work without claiming live ghost typing qualified.

Official-source review completed: see
[ELBOW_DIRECTION_RESPONSE_REVIEW.md](ELBOW_DIRECTION_RESPONSE_REVIEW.md).
Reference T101 forwards explicit steps/second speed and acceleration to the
selected servo; no read-only deadband query or installed deadband value was
established. 501/502/503 are settings writes, not diagnostics. Nothing flashed,
no registers/torque changed, no new movement during this review.
Next selected experiment keeps the exact last target and geometric bounds but
uses explicit speed 40 instead of 20 (acceleration 1 unchanged). Before dispatch,
fix single-joint reservation speed metadata to reflect the actual admitted
command and test it. This isolates speed, not amplitude or compensation. If this
also has no response, stop that branch and seek independent evidence rather than
continue parameter escalation.

19:37 UTC smaller decreasing-elbow diagnostic completed with no reported movement.
Added `--post-overshoot-elbow`: exact elbow start 1.691980809, goal 1.683980809
(-.008 rad / -.458366236 degrees), other joints fixed, 20/1 settings. Commanded
hypothetical-tip sweep under 3 mm, retained 6 mm live observation bound. 43 tests
passed; fresh preflight matched. Live export:
`wizard-20260917T193723231482Z-4f2c92274eb740ea8b8007d588c8a64b`.
Final elbow stayed 1.691980809 and other joints unchanged; endpoint failed at
2.533397018 modeled mm. No repeat, amplitude escalation, correction fit or return.

Now two small decreasing-elbow trials at different nearby starts showed no reported
response, whereas the intervening increasing trial responded with overshoot.
This supports direction/history-dependent behavior, not a globally reversed sign
or a proven physical cause. Do not train an inverse map from the zero-response
points or keep firing smaller commands. Next inspect supported servo/firmware
deadband, load and explicit speed semantics against retained evidence, and select
one discriminating experiment only after that review. Hardware/register/torque
configuration must not be changed implicitly. The wrist cycle remains unavailable
at this changed elbow posture; its original evidence is retained unchanged.

19:35 UTC elbow sweep review found a preview/live guard gap. Retained maximum
sampled controller displacement was 5.829206463 mm; the hypothetical 100 mm tip
displacement was 6.196284411 mm, exceeding the 6 mm preview bound. This is modeled
displacement, not physical metrology, and sparse samples cannot bound all travel.
No further hardware motion was sent.

The two named local elbow diagnostics now also check hypothetical tip displacement
during feedback processing. Exceeding 6 mm ends progression with
OBSERVED_HYPOTHETICAL_TIP_BOUND_EXCEEDED, preserving the triggering sample and
bound in the export. This does NOT interrupt an already-issued servo move and is
not an emergency stop. No automatic return/recovery is generated. 53 related
tests passed, preserving wrist-cycle regressions.
Offline replay of the complete verified source stopped on sample 2 of 31:
`wizard-20260917T193525777522Z-a521ce789a684651b9885fcece7ddaa4`.
Original hardware export remains unchanged. Current reported posture is still
the 19:33 elbow endpoint; a fresh observation is required before any new trial.

Next design a smaller, separately screened decreasing-elbow experiment from that
endpoint with command-path headroom for the observed response error. Do not expand
the monitored envelope merely to accept the overshoot. Evaluate actual response
before fitting correction or restoring the exact wrist-cycle posture. Existing
wrist cycle is a useful regression baseline, not authority at the shifted elbow.

19:33 UTC elbow opposite-direction discriminator executed once. Separate
`--post-tip-elbow-increasing` selects +.012 rad (not an 8-degree move; legacy
internal selector -8). Exact old posture, explicit 20/1 settings, 41-point arc
screen within 6 mm and hypothetical 100 mm tip bound. 41 relevant tests passed.
Preflight `wizard-20260917T193257408785Z-7ad4c705175244448f51c56b286d41b6`.
Live `wizard-20260917T193314387752Z-d975fcaf16c34888a2ab6f69bce92c81`.

Requested elbow 1.68557304 from 1.67357304 (+.687549354 degrees), final reported
1.691980809 (+1.054687474 degrees). Other five joints unchanged. Endpoint failed:
+.006407769 rad / +.367138120 degrees residual, 2.029180 controller-model mm.
This is a responding elbow with overshoot, not global no-response. Do not infer
the earlier decreasing nonresponse has been resolved. No retry/return followed.
The wrist cycle's exact-start prerequisite is now invalid until elbow posture
is separately restored and verified; do not bypass it.
Next review retained trajectory and actual modeled sweep, then prepare a bounded
direction-specific elbow correction/return experiment. Keep increasing overshoot
and decreasing no-response as separate observations; do not fit a single global
bias or transfer the wrist map. Coordinated ghost typing remains unqualified.

19:31 UTC milestone: TWO finite three-leg wrist cycles passed automatic per-leg
desired-endpoint verification and publish-before-progression. Implemented
`bench_compensated_wrist_cycle.py --mapping-cycle` (read-only preflight by default;
`--execute` sends at most three admitted legs). Reuses the existing one-use finite
cycle coordinator; no automatic recovery/retry, fresh exact-start/continuity checks
before each send, verified export before next leg. First-leg desired endpoint is
explicitly -.064427193, distinct from raw wire target; old diagnostic failures are
unchanged. Simulation/fault coverage: 49 tests passed, including interruption at
each leg, candidate mismatch, export failure, cancellation and replay prevention.

Cycle 1 index: `wizard-20260917T193053328134Z-35e1fc373cb641a5a9906a9b1b8a8020`.
Cycle 2 index: `wizard-20260917T193117289197Z-a15a070106e14c74b9a107aedbb8b01b`.
Both indices and all referenced leg exports verified. All six leg runner errors
null. Both cycles closed at exactly their initial reported six-joint posture:
[.001533981,.033747577,1.67357304,-.052155347,.018407769,3.138524692].
Desired model-space errors per leg were approximately 0, .499923216423 and
.489891759016 mm in both runs. This is repeatable local reported-state closure,
not measured physical stylus accuracy or validation of the elbow/ghost keyboard.

Next prioritize the unresolved elbow response at this posture before coordinated
typing. Review whether a similarly bounded direction-specific elbow trial can
discriminate its earlier no-response without reusing wrist corrections or raising
amplitude merely to force movement. Preserve this working wrist cycle as a
regression baseline. Camera/contact remain deferred; no keyboard sequence is yet
qualified by this wrist-only milestone.

19:27 UTC interpolation held-out trial passed locally, with limited margin.
Added exclusive one-leg `--wrist-map-trial prepare|held-out`, fresh exact-start
checking, 41-point 6 mm controller/hypothetical-tool arc screen and separate desired
endpoint verification. 58 focused tests passed before hardware work.
Preparation 1: `wizard-20260917T192645886663Z-48b97a66092f4eb9b949f46fb7b8a429`
reached wrist -.064427193 exactly in reported joints; no runner error.
Preparation 2 (unchanged decreasing candidate):
`wizard-20260917T192702949795Z-4d9c391c31c64c709c85700349e78bce`
again reached -.072097097, desired modeled error .499923216423 mm; no runner error.
Each leg was separately reviewed before progressing; map start matched exactly.
Held-out interpolation:
`wizard-20260917T192720932626Z-195a3ebe5a634c2ba5e3a6fabda8b3b8`.
Desired -.055 rad, wire -.050766266637881065 rad, final reported -.052155347 rad.
Five samples, no runner error, desired error .489891759016 modeled mm and
+.162986611079 degrees; COMPENSATED_REPORTED_ENDPOINT_VERIFIED. Model unchanged.

This is one interior-target pass, not proof of a linear actuator response: the
reported final coincides with an earlier training endpoint despite a different
wire command. Keep the limited margin and possible quantization/nonlinearity in
view; do not extend the model beyond the tested interval or posture.
Current posture [.001533981,.033747577,1.67357304,-.052155347,.018407769,3.138524692].
Next define a finite three-leg reported-endpoint cycle at this posture: original
decreasing wire command targeting the repeat-observed -.064427193 endpoint;
unchanged decreasing candidate; unchanged interpolation return. Each leg must
retain its intended task endpoint and wire endpoint separately, require fresh
start matching and stop on failure. The first leg needs a distinct explicit
desired-endpoint contract; do not retroactively relabel the earlier raw diagnostic
failures as passes. After a clean cycle, review closure and repeat once before
considering coordinated ghost motions; elbow qualification is still outstanding.

19:24 UTC local increasing response map prepared offline. Pinned verified source
trials share all six starting joints and 20/1 settings. Their command/report pairs:
(-.053761811220085054, -.056757289), (-.045917158220085054, -.052155347) rad.
The two-point slope is .586634233535; inverse interpolation proposes wire
-.050766266637881065 rad for held-out desired -.055 rad. This target lies strictly
between measured outputs. No extrapolation, changed-start application or global
joint compensation is supported. A perfect fit to two points is tautological,
not validation. Map SHA256:
`cd8e129c18486cf95cadd7799e6a77ed4b1901ab1f630bff4a804e78fa9d73f0`.
Verified export `wizard-20260917T192424925702Z-fd715d4709104bbeb4e274d0d6e83eb1`.
33 focused tests passed, including incompatible starts/settings, uncertain runs,
cross-joint changes, duplicate points, altered maps and extrapolation rejection.
No hardware command sent during this offline analysis.

Next screen a separate preparation route from current reported wrist -.056757289
back to the model's exact -.072097097 starting wrist; all other joints must match.
Do not assume an open-loop preparation reaches that start or weaken the map's
start scope. Each preparation leg needs its own preview, fresh baseline and
reported endpoint review. Then screen and execute the frozen interior held-out
target once. Preserve its result regardless of pass/fail; do not refit and count
the same target as a fresh validation. Camera/contact work remains deferred.

19:22 UTC increasing candidate held-out test completed, not verified. Frozen
candidate export `wizard-20260917T192045698291Z-b3689dd2a3af49e6aadbd7a37bf8febf`,
SHA256 `376e3e9352a23da6e447d2d4850ff7411a9d5fdffe9d7c7125661bdbfdea8dbf`.
Training reverse residual -.006238188779914944 rad; distinct desired wrist -.060,
wire -.053761811220085054 from -.072097097. Screened hypothetical tip sweep
3.750548 mm. Separate increasing artifact; decreasing artifact unchanged.
63 relevant tests passed; fresh preflight matched.
Live export `wizard-20260917T192154079024Z-5a6776c530fc4b3e9833aa453c8c3777`.
Review `wizard-20260917T192212558961Z-889059fd09f5474d9fa6a6887c8f99b0`.

Final wrist -.056757289 rad, other joints unchanged. Desired residual +.185793654
degrees / .558443157 modeled mm; wire residual -.171628234 degrees / .515866065
modeled mm. Both fail the unchanged .5 mm criterion. Thirty-two samples, no
runner error or feedback failures, last change .757114 s and stable tail 8.504641 s.
No retry/return, no successful-cycle claim. Current posture:
[.001533981,.033747577,1.67357304,-.056757289,.018407769,3.138524692].

The two increasing trials share the same start and 20/1 settings but show different
wire residuals at different commands. A constant directional bias is therefore
not sufficiently accurate for this local .5 mm criterion. Next compare these
points offline and assess a bounded command-response interpolation hypothesis,
keeping both original outcomes. It requires another held-out target and separately
screened starting-pose preparation, not silently retuning this failed result.
Do not chase submillimeter perfection as an end in itself: distinguish provisional
controller-model acceptance from eventual key-size/tool/registration requirements.

19:19 UTC same-command repeats completed and compared without refitting:
- Original decreasing diagnostic repeat:
  `wizard-20260917T191811242033Z-75c9bf99e8294b9287d32720dee50d13`.
  Same six-joint baseline, command and final reported joints as 19:09; endpoint
  still fails with the same +.013908092779914949 rad wrist residual.
  Comparison: `wizard-20260917T191844680352Z-97a90363e07d491a8a62265e011dd43d`.
- Frozen corrected held-out repeat:
  `wizard-20260917T191904213991Z-02005a7dec72428d800d7461efa1b12e`.
  Same baseline/command/candidate and final reported joints as 19:14; both pass
  desired-endpoint verification at .499923216423 modeled mm, with no runner error.
  Comparison: `wizard-20260917T191916524484Z-38690a3a17364c88992d56e785f92da1`.
  The corrected wrist ended at -.072097097 rad; other joints unchanged.

These are two-trial local reported-state repeats, not statistical reliability,
physical repeatability or a global correction. The pass remains threshold-adjacent.
The offline `compare_repeated_joint_trials.py` preserves source hashes and checks
command/start/candidate equality while keeping desired and wire verdicts separate.
Next prepare an increasing-direction candidate from the retained reverse trace,
validate it on a distinct nearby endpoint, and then define shared bidirectional
endpoints for a finite verified cycle. Do not overwrite or broaden the decreasing
candidate merely because the repeated endpoint is consistent.

19:17 UTC persistence and reverse-direction evidence:
112 successful read-only observations over the bounded 35-second observation
retained the same six-joint posture (wrist -.072097097). Verified persistence
export `wizard-20260917T191550505583Z-ad2f2686088047b5916bf284e783f897`.
Added a separate uncompensated `--post-tip-wrist-reverse`, exact posture matching,
same 41-point arc screen and 20/1 settings; 52 focused tests passed.
Preview `wizard-20260917T191638766727Z-cc5514285d524648953cab0f4cd397e0`.
Executed once: `wizard-20260917T191656675614Z-0b1fef1e816a4c11abc7ff289f2a78b1`.
Verified review `wizard-20260917T191710400615Z-4b9faca8b44a46978eb6fbe4c3bdcc35`.

Increasing wrist requested +1.5 degrees to -.045917158220085054 rad; reported
+1.142578111 degrees to -.052155347 rad. Other joints unchanged. Thirty-one
packets, no feedback failures, last change .892589 s and unchanged tail 8.389645 s.
Endpoint failed with -0.357421889-degree wrist residual and 1.074308 modeled mm.
No return/retry followed. Direction-dependent behavior is supported; the cause
is not established. The decreasing correction must not be used in reverse.

The final reported posture equals the original post-tip diagnostic starting
posture. Next, after reviewing this terminal result and acquiring a fresh matching
baseline, use a separately admitted repeat of the original decreasing diagnostic
to measure same-command endpoint repeatability. Preserve both trials rather than
refitting or overwriting. If it reproduces the prior final, the frozen held-out
candidate can be evaluated again under a new exact-start admission. Reverse
correction qualification and coordinated ghost motions still remain incomplete.

19:14 UTC held-out wrist candidate executed once and passed the existing desired
endpoint check, narrowly. Preview:
`wizard-20260917T191408153852Z-0536dd3a13d14da1900f5308f046f9d5`.
Verified live export:
`wizard-20260917T191415807610Z-3ffde72df33546fb84b9ba172c869e00`.
Candidate SHA unchanged: 7aff3b4ac17b7c6d24843192a57426fab456508c74d2328e442a989e3134c834.
Fresh baseline matched; T101 wrist command -.08890809277991495 rad, desired -.075.
Final reported wrist -.072097097 rad; other joints unchanged. Four observations,
no runner error, COMPENSATED_REPORTED_ENDPOINT_VERIFIED. Desired model error
.499923216423 mm and wrist residual +.166324090236 degrees. Wire-target error
2.895071450031 mm remains a separate failed verdict, as expected for compensation.
Thresholds were not changed. This result is only .0000768 mm inside the provisional
.5 mm model-space limit; do not claim robustness or independently measured accuracy.
Sixty-one focused transaction/runner/candidate tests passed before dispatch.
No automatic return/retry. Current reported six-joint posture:
[.001533981,.033747577,1.67357304,-.072097097,.018407769,3.138524692].

Next: check post-trial reported-state persistence without movement, then prepare
a separate bounded reverse-direction characterization and fixed-endpoint repeat.
Do not reuse the decreasing correction for increasing motion or silently refit
it to make this same held-out result pass. Repeatability, elbow response and
coordinated ghost-key progression remain incomplete.

19:11 UTC offline candidate prepared, not executed. Verified frozen candidate:
`wizard-20260917T191119271010Z-1adad8f0b95e46e995f3c89967081e06`, SHA256
`7aff3b4ac17b7c6d24843192a57426fab456508c74d2328e442a989e3134c834`.
Pinned training attachment hash is checked before fitting. Model: local decreasing
wrist additive residual, +.013908092779914949 rad. Distinct desired target -.075
rad; proposed wire target -.08890809277991495 rad, from final wrist -.064427193.
Other five joints unchanged. A 41-point arc has hypothetical tip sweep 5.007601 mm.
This is a hypothesis from one local trial, NOT validated compensation or evidence
of repeatability. No new physical command sent. Sixty relevant tests passed,
including rejection of uncertain, unsettled, wrong-direction, cross-joint and
changed-command training evidence.

Next integrate only this pinned artifact into a separate named held-out trial:
fresh exact-start match; desired endpoint verdict distinct from wire endpoint;
same 20/1 speed/acceleration; one command, no automatic return/retry. Keep the
existing local candidate and ordinary wrist checks unchanged. Passing this trial
would support one local transfer only; repetition and reverse direction remain
separate work before coordinated motions.

19:09 UTC wrist response discriminator executed once. Added exclusive
`--post-tip-wrist` with exact fresh-start matching, no compensation, 41-point
controller/hypothetical-tool arc screen (maximum tip sweep 5.355123 mm), and
unchanged non-wrist targets. Relevant transaction/runner/wrist tests: 53 passed.
Preview: `wizard-20260917T190810066370Z-39f2e6db177b41e086434e54cf9aa8e0`.
Live: `wizard-20260917T190917013883Z-949dfe33aefa475c83a6103de6fff839`.
Verified trace review: `wizard-20260917T190935790376Z-9a4b8149192b404f82476d46de939198`.

T101 joint 4, target -.07833528577991494 rad, speed 20, acceleration 1.
Reported wrist changed from -.052155347 to -.064427193 rad: requested -1.5
degrees, reported -.703124983 degrees. Other joints remained unchanged. Thirty
retained packets, two distinct packet values, no feedback failures; last wrist
change at .589709 s followed by an 8.498396 s unchanged tail. Endpoint verification
failed (2.395163 modeled mm, +.01390809278 rad wrist residual); no retry or return.
This disproves completely frozen reported state for this interval, not per-servo
encoder freshness or physical accuracy. Elbow-specific ambiguity remains.

Next: review the stable, correct-direction wrist residual against earlier local
evidence; prepare a frozen, posture-specific correction and held-out endpoint
preview before any new command. Keep the original failed result intact. Qualify
repeatability and reverse response separately; do not transfer wrist corrections
to elbow or resume coordinated typing from this single undershoot measurement.

19:05 UTC transport comparison complete for diagnostic purposes. Verified wrapper
`wizard-20260917T190523902642Z-c31fae47d2b94860845fbea2bcba58f7` and comparison
`wizard-20260917T190529522444Z-1eaf9e70d2a0476f9456361ba618fa6b` retain matching
six-joint values. The common-clock gap to the after-HTTP sample is 1.062 seconds;
the comparison honestly labels it CAPTURES_TOO_FAR_APART under its 1-second rule.
Do not optimize around that arbitrary classification or repeat stationary
captures to gain a pass: even simultaneous agreement cannot prove encoder
freshness. `compare_usb_http_capture.py` now reproduces this comparison from
verified exports using the serial packet's byte-associated read windows.

Next useful discriminator: prepare a separate, uncompensated wrist-only probe at
the latest exact posture (b=.001533981, s=.033747577, e=1.67357304,
t=-.052155347, r=.018407769, g=3.138524692). A small decreasing wrist-pitch
move with explicit speed/acceleration can test whether reported state responds
outside the elbow. This is not a retry of the failed elbow command and not an
accuracy/compensation trial. Existing wrist previews require older fixed elbow
postures; do not weaken those checks or reuse their offsets. Add a named preview
and tests, screen the entire controller/tool arc, and bind one fresh command.
Retain response/no-response and desired/wire residuals separately. No automatic
return or escalation. If response remains absent, stop motion and seek direct
actuator/observation evidence instead of more stationary polls or offset fitting.

19:02 UTC physical feedback-only checkpoint: repaired wrapper completed with no
error. Combined export `wizard-20260917T190219356146Z-a4c27e91a3e04658841154516451379c`
and native export `wizard-20260917T190219204901Z-f62788c320fd46e2977b6c2be1c2791c`
both verify. Native capture closed cleanly, retained 255 pose samples, wrote zero
serial bytes, and has no unresolved I/O. Both HTTP brackets succeeded; all six
joint values exactly equal the latest retained USB pose. This rules out a
different reported pose unique to HTTP in these captures, not a shared stale
controller state or actuator problem. No movement command was sent.

Timing limitation discovered during review: USB uses time.monotonic_ns while
HTTP's internal timestamps use perf_counter. Do not directly subtract these on
this Python/Windows runtime. The wrapper now adds explicit monotonic_ns brackets
around HTTP probes while preserving original transport timestamps (13 focused
tests passed). Existing captures remain descriptive, not certified time-paired.
Next use the corrected timestamps for a bounded comparison and review whether
feedback can discriminate movement before resuming an endpoint campaign. Do not
fit additional compensation from unchanged/contradictory responses.

19:01 UTC software progress: supplementary capture wrapper now retains compact
operation references, not nested native results. It tracks the exact pending
operation and blocks a new action after timeout, polling failure or uncertain
dispatch. Offline wrapper/feedback/serial regression suite: 119 passed. No live
capture or movement was repeated. Recovered summary from the verified original:
`wizard-20260917T190129353978Z-e5e74c21c74640d9923a90253466b1db` (verified).
The recovery script is `software/scripts/recover_usb_capture_summary.py`.
HTTP brackets were not recovered; do not infer a paired transport comparison.
Next: retain and compare timestamped packets through the existing bounded capture
workflow before deciding whether another single-joint trial is interpretable.

Updated checkpoint: the operator confirms seeing movement. This establishes
observed actuation, not a measured displacement or a pass for an unidentified
trial. Do not repeat larger demonstrations just to prove motion.

The 18:54 UTC native USB capture is retained in
`wizard-20260917T185403429261Z-0abafeb328724b08863a8c11fdb0e8b7`:
255 pose samples, zero confirmed write bytes, cleanup confirmed and no unresolved
I/O. Its terminal status is CAPTURED_CLOSED, not a persistent connection failure.
It explicitly does not verify encoder freshness or query/response correlation.
The last USB joint pose matches the earlier HTTP-reported pose, but that is not
a time-paired comparison. The supplementary combined export failed its nesting/
item budget; do not claim the surrounding HTTP captures were durably retained.

Immediate order:
1. Repair supplementary export packaging using compact operation references;
   regression-test success, failure and pending-operation cleanup offline.
   Recover a summary from existing native evidence without repeating capture.
2. Preserve bounded, timestamped HTTP/USB packets in a small diagnostic artifact.
   Treat distant samples as inconclusive and transport agreement as agreement,
   not proof of fresh encoders or physical accuracy.
3. From a fresh baseline, prepare one bounded single-joint diagnostic with explicit
   speed, acceleration and desired endpoint. Correlate observation and telemetry;
   stop if feedback remains unchanged or contradicts motion. No amplitude escalation.
4. Once interpretable, repeat a finite out-and-back trial and review signed errors
   and settling. Qualify compensation on held-out moves, not the fit samples.
5. Resume coordinated local ghost approach/press/retract and then a short sequence.
   Require an exported verdict per leg before proceeding; no physical contact.

Completion for this phase: reproducible exports, interpretable per-leg feedback,
and a finite noncontact sequence meeting predeclared application tolerances.
This does not certify real stylus placement, key contact or millimeter accuracy.

### Historical checkpoints (superseded where noted)

USB restored checkpoint 18:52 UTC: COM7 now enumerates VID 10C4/PID EA60, serial
52E4E1E8337FEF119E92181CEDD322A4, matching the historically observed arm endpoint.
Public wizard metadata-only inventory/review/native correlation succeeded with
one matching device and no metadata blockers. Verified export:
`wizard-20260917T185219832056Z-db55d7a8f18947f9903adf317ad0c36a`.
No serial port opened, no power-off report invented, no command sent. The missing
USB prerequisite is resolved; this is identity metadata, not fresh telemetry.
Existing bounded zero-write capture `capture_powered_arm_telemetry` is the next
reader to use, with current powered setup and fresh session correlation. Review
reset/open behavior and preserve its one-use admission; do not use bare pyserial
or the old query action on a controller known to stream unsolicited telemetry.
Then compare temporally adjacent HTTP and serial samples without promoting
agreement into proof of fresh encoders or physical accuracy.

USB-preparation checkpoint: inventory still shows only Bluetooth COM3/4/9/10;
no port opened. Added offline `feedback_channel_comparison.py`: verifies original
packet hashes, requires labeled HTTP/serial captures with host time intervals,
preserves signed joint differences and marks distant captures inconclusive.
Agreement grants neither freshness nor physical/motion authority. HTTP body and
serial newline framing are handled separately. Comparator plus existing powered
serial/nonpurging lifecycle regressions: 114 tests passed. The existing serial
path has explicit endpoint/reset admission; do not bypass it with bare pyserial.
Next live prerequisite remains the requested USB data connection. Then acquire
nearby stationary read-only samples through existing admitted readers and export
their comparison; the comparator alone does not acquire or authenticate hardware.

Read-only interface checkpoint 18:45 UTC: served-page export
`wizard-20260917T184526089377Z-37a82dfd581a4032bd90927e00bec210` verified.
Its getData function explicitly sends T105 and parses HTTP telemetry, matching
observed behavior. The page's getDevInfo route returns 404; firmware version
remains unknown. This is not authority to replace the installed interface with
the newer reference WebSocket path. Current official SDK docs recommend serial
for feedback; investigate an independent read path, inventorying ports without
opening them first because serial opening can reset the controller. No scripts,
motion commands, configuration writes or firmware changes during inspection.
Port inventory lists only Bluetooth COM3/COM4/COM9/COM10, with no USB VID/PID.
No arm USB serial port is currently available and none was opened. Request USB
data connection for an independently acquired telemetry comparison; preserve
power and settings, keep clear during connection, then inspect the serial-opening
reset behavior before using the existing bounded reader. HTTP observations alone
currently cannot settle the encoder-freshness question.

Read-only checkpoint 18:43 UTC: packet review export
`wizard-20260917T184345852055Z-3b065b49a62d4f378c11242cc4e546e8` verified.
All 31 original T101 feedback packets are identical, elbow load raw 45, with no
torque-state or voltage fields. This neither proves caching nor proves health.
Twenty-six focused tests pass. Reference HTTP handler returns ok and publishes
telemetry on WebSocket, unlike this arm's HTTP numeric telemetry. Thus exact
installed behavior differs from the pinned reference interface. Next inspect
served interface/version clues read-only; keep motion paused and do not assume
reference acquisition/servo-setting behavior matches the installed build.

Live checkpoint 18:41 UTC: separate `--post-tip-elbow` diagnostic implemented,
screened with 41 samples and a 6 mm controller/hypothetical-tip sweep cap, tested
(38 focused tests) and admitted from fresh matching feedback. One T101 joint 3
command targeted 1.6579063063032675 rad, speed 20, acceleration 1. Verified export
`wizard-20260917T184148463017Z-fc3474830b1d4836b6df550bad581717`:
COMPLETION_DEADLINE_EXCEEDED, 31 samples, no runner error, all reported joints
unchanged. Elbow remained 1.67357304 (reconstructed count 2115) against predicted
goal count 2105; modeled controller miss 4.961219 mm. No retry/return sent.
Trace review `wizard-20260917T184212853332Z-021ac6430ceb4791ac90e67ac023f098`
verified. This localizes the issue beyond T104 interpolation alone: the same
elbow target did not produce reported movement through explicit T101 settings.
It does not identify deadband, load, actuator configuration or stale acquisition.
Next inspect retained servo-related fields and supported read-only diagnostics;
keep movement paused, do not escalate target magnitude or fit zero response.

Source-review checkpoint: see `TIP_REVERSE_FIRMWARE_DIAGNOSIS.md`. The official
archive SHA256 was reverified; reference elbow conversion has no sign reversal.
T104 shared servo speed/acceleration settings are history-dependent, unlike the
explicit 20/1 used by our T101 trials. Correct prior shorthand: T104 bus
acceleration is not unconditionally zero (initial array value is 20). Installed
firmware/settings and encoder-read freshness remain unverified. Earlier verified
T101 exports show decreasing elbow motion at a different posture, with residual
error; this does not justify globally reversing the mapping or importing offsets.
Next prepare a separate screened T101 elbow-only diagnostic toward the prior
reverse elbow goal, preserving other joints, with no automatic retry/return.
This is a new diagnostic after review, not resumption of the failed tip cycle.

Read-only checkpoint 18:36 UTC: command-mapping audit export
`wizard-20260917T183627147274Z-f83dcea14aa8439f8c38b87d55f66f49` verified.
Reserved command equals transaction command; transmitted payload SHA256 matches;
recomputed reference inverse equals expected joints exactly. Predicted elbow
counts 2113 -> 2105 versus reported 2115 (10-count target residual). Wrist target
and reported count both 2014. Rounding alone does not explain the elbow result.
This audits host records/reference math, not installed firmware or actual bus
writes. Fresh read-only export
`wizard-20260917T183627954433Z-41f98e00b0c848e29b5697f68f32658d` reports SUCCEEDED
feedback, cleanup confirmed, and exactly the prior final six joints. Named
retract admission correctly rejects this changed start. No movement was sent.
Twenty-six audit/trace/candidate tests passed. Next inspect available firmware
command/feedback paths and compare earlier isolated elbow evidence at similar
postures before designing another motion experiment. The cause remains unknown;
do not attribute it solely to host sign conversion or fit away opposite motion.

Live checkpoint 18:34 UTC: the separately scoped uncompensated upward diagnostic
was screened, tested and sent once after fresh matching preflight. Thirty-six
focused tests passed before dispatch. Live export
`wizard-20260917T183418258680Z-39080a782e1d4bfdb5273d6b85bd4d9d` verified:
COMPLETION_DEADLINE_EXCEEDED, 30 observations, runner error null, 5.069348 mm
controller endpoint miss. Elbow requested -.721856 degrees but reported +.175781;
wrist requested +.782655 and reported +.703125. This opposite-sign elbow response
stops further motion tests pending diagnosis; no return/retry/correction followed.
Trace review `wizard-20260917T183434474368Z-2d485127a1974c12bb196baf4f106c1b`
verified: elbow/wrist stopped changing at .449482 seconds, followed by 8.903226
seconds unchanged. Counterfactual ideal elbow alone reduces modeled error to
.276904 mm; this localizes the reported discrepancy but does not establish its
physical cause. Final joints [.001533981,.033747577,1.67357304,-.052155347,
.018407769,3.138524692]. Fitter now rejects opposite/zero observed elbow or wrist
response rather than converting it into another additive correction.
Next perform read-only evidence/command/firmware-mapping diagnosis. Do not fit
or send a reverse correction based solely on this opposite-sign response.

Offline checkpoint 18:32 UTC: two-tip-trial comparison exported and verified as
`wizard-20260917T183137147087Z-578cdf2a7eb7440e8117fde374365fa7`.
Elbow wire residual changed +.155881 degrees and wrist +.167390 degrees. Shoulder
reported no movement for requested .050975/.059713-degree changes. These are
changed operating points, not a controlled repeat or proof of a specific cause.
No global additive correction is qualified.
The local-tip preview now supports a separately labeled upward/retract reference.
From final retained joints, a 2 mm-up reference passes the eight-leg controller
model: maximum joint excursion .782655 degrees, lateral drift .000858 mm.
Verified export `wizard-20260917T183226443418Z-6e2e08653f384b7e8bb28ac538501793`.
Its source remains COMPLETION_DEADLINE_EXCEEDED; retaining its settled feedback
for offline geometry does not promote the failed endpoint. Thirty-one focused
tests passed. No hardware command this step.
Next freeze the upward target and separately screen its direct single-command
path from fresh matching feedback, then run one uncompensated reverse diagnostic.
Do not transfer the descending offsets. Use reverse evidence to design a finite
paired experiment with fixed desired endpoints, capped legs and export-before-
progression, rather than accumulating additional downward trials.

Live checkpoint 18:30 UTC: pinned local-tip candidate is integrated via
`bench_cartesian_vertical.py --local-tip-candidate` (read-only default; explicit
`--execute` sends one). Candidate artifact/hash, exact baseline and distinct
desired/wire verdicts are bound to the existing reservation. Thirty-nine focused
tests passed, including tampering rejection and desired-arrival simulation.
Fresh preflight admitted the pose. Live export
`wizard-20260917T183047269334Z-94f355c5112a48cfae9ac624121a1637` verified:
COMPLETION_DEADLINE_EXCEEDED, 30 samples, runner error null. Desired controller
position miss 1.060005 mm (NOT verified); wire-target miss 4.906312 mm. Desired
joint errors: shoulder -.059713 degrees, elbow +.155881, wrist +.167390.
Final joints [.001533981,.033747577,1.670505078,-.064427193,.018407769,3.138524692].
No return/retry occurred. The smaller desired miss than the previous 3.589844 mm
trial is not a controlled repeatability result: both target and start changed.
Next compare the two tip-command traces, including shoulder quantization and
changing elbow/wrist residuals, before selecting another correction. Do not
indefinitely walk the tip downward and refit every miss; bound any further
identification and plan separately qualified return-direction evidence.

Offline checkpoint 18:28 UTC: latest press trace has an unchanged elbow/wrist tail
of 8.903481 seconds after the last reported change at .391108 seconds; no failed
feedback requests. Trace review export
`wizard-20260917T182720601907Z-679230e64d96448a95fb7161276e6e5e` verified.
The existing coordinated-candidate fitter now supports this named tip experiment:
it derives a distinct 2 mm-down desired target from the final reported pose,
subtracts the source residual only from elbow/wrist, preserves roll/gripper, and
screens the corrected direct T104 path. Candidate export
`wizard-20260917T182802972330Z-29b98ce47f894c32ac40b1b5c66bc0cc` verified;
candidate SHA256 `5ea61cae132f37e8e424fc137362a64e4e3840db7701a4c0c25725f95ae5712b`.
Residuals: elbow +.005624738315 rad, wrist +.012136710386 rad. Corrected wire
path: 38 samples, maximum joint excursion 1.478006 degrees, hypothetical tip
sweep 2.864902 mm. Thirty-one focused tests passed. No live movement this step.
Next bind this frozen candidate to a distinct named native trial with desired
endpoint termination and validate it once from fresh matching feedback. This is
a one-trace additive hypothesis, not an established general correction; the new
target/start are held out, and no reverse-direction transfer is qualified.

Live checkpoint 18:26 UTC: named `--local-tip-press` integration is implemented
through the existing one-use Cartesian reservation/runner. Twenty-five focused
tests passed. Read-only preflight admitted the exact reviewed start; a single
uncompensated T104 command then attempted the full 2 mm local hypothetical press,
with its direct interpolation separately screened (not assumed from eight legs).
Export `wizard-20260917T182619277841Z-90592a21fcd14c78be0a319d0bdc6038`
verified. Outcome COMPLETION_DEADLINE_EXCEEDED, 30 observations, runner error null,
controller endpoint miss 3.589844 mm. Elbow requested +0.732414 degrees, reported
+1.054687; wrist requested -0.783273 degrees, reported -0.087891. Shoulder stayed
at its starting reported value; roll/gripper unchanged. No return or retry sent.
The hypothetical tip projected from reported joints moved [-2.388555,-0.003655,
-5.385524] mm, versus the desired [0,0,-2] mm. This is model-derived, not physical
tip measurement. Final joints: [.001533981,.033747577,1.65516527,-.053689328,
.018407769,3.138524692]. Original-start admission now intentionally rejects a
repeat from this new posture. Next analyze this trial's plateau and directional
residuals, freeze a bounded coordinated correction, screen its wire trajectory,
and validate on a distinct target from fresh feedback. Do not dispatch a return
or ghost sequence merely because the ideal reference simulation passed.

Offline checkpoint 18:23 UTC: the local preview now projects solved joints into
firmware end-edge coordinates and screens all eight T104 reference interpolations
at speed coefficient .05. It preserves gripper state, checks inverse-branch
agreement, provisional/URDF joint limits and the hypothetical tip path. Result:
CONTROLLER_REFERENCE_PASS_NOT_EXECUTABLE, maximum lateral drift 0.000822 mm,
maximum joint excursion 0.783273 degrees. Verified export:
`wizard-20260917T182339455535Z-be6764567ff04c50a55c22152b11366a`.
Run with `preview_local_tip_cycle.py <successful-leg-export> --controller-path`.
No compensation or native commands were generated; actual installed firmware,
physical clearance and physical tip accuracy are not verified by this report.
Next integrate a named single-leg experiment into the existing native transaction
path: fresh-pose admission, exact target binding, desired-versus-wire metrics,
bounded command, endpoint verification and export. Start with one useful bounded
press segment, not the full eight-leg route, then characterize its observed
response before admitting return or repeated sequences.

Offline checkpoint 18:22 UTC: local tip preview v2 passed with nine waypoints and
168 interpolated samples. For the hypothetical 100 mm stylus, requested depth is
2 mm, maximum lateral drift 0.000822 mm, vertical tracking error 0.000131 mm,
maximum joint excursion 0.783273 degrees, and modeled return error zero.
These are numerical reference-path results, NOT hardware accuracy. Eighteen
focused preview/wrist-review/cycle tests passed, including invalid inputs and IK
failure. The hash-linked diagnostic export verified:
`wizard-20260917T182200103616Z-12d8c587c8af479c900409f0481f81f0`.
No commands were generated or sent. Next translate the desired reference into
the supported controller command representation and screen its actual firmware
interpolation model before any bounded live leg. Linear joint interpolation is
not evidence of the controller's intermediate trajectory. Step 1's local preview
is complete; controller-path admission and step 2 remain pending.

The user's latest visual confirmation establishes that motion was seen. It is
not a measured displacement or a new endpoint-verification export. This plan
update sends no commands to the arm.

1. **Finish the offline local tip preview.** Review and test
   `application/local_tip_cycle.py` and its preview script. They currently model
   a 2 mm vendor-base vertical down/up path with the hypothetical 100 mm tool,
   retaining the starting tool axis. Validate IK, interpolation, lateral drift,
   joint bounds and exact modeled return; publish a reproducible report. Code
   presence is not a test pass. The local synthetic frame does not relocate the
   keyboard or establish tool perpendicularity, physical clearance or accuracy.
2. **Prepare one bounded coordinated trial.** From fresh feedback, screen the
   desired path AND any compensated wire path. Keep other-joint behavior,
   posture/direction/speed limits and command identity explicit. Existing local
   wrist biases are not automatically valid for coordinated motion. If screening
   fails, revise offline instead of dispatching an unchecked trajectory.
3. **Execute, verify and export one leg at a time.** Record baseline, desired and
   wire targets, timestamped feedback, settling, joint and modeled-tip residuals,
   faults and candidate identity. Require fresh stable endpoint evidence and a
   verified export before the next leg. Stop on invalid feedback, unexpected
   motion or uncertain execution; no automatic replay or blind return.
4. **Validate a small finite press/retract cycle.** Test the reverse direction
   separately, then combine qualified legs. Use held-out targets/repeats to
   distinguish a useful correction from a fitted single result. Keep the current
   0.5 mm modeled endpoint band for comparable trials; it is not physical tip
   accuracy. Do not chase zero residual or generalize beyond the tested domain.
5. **Connect to the ghost keyboard.** Screen the approach to PARK and the first
   A-key HOVER separately, preserving the saved keyboard placement. Advance to
   one simulated key and then a finite A-S-D sequence only after the relevant
   coordinated legs qualify. Simulated contact is free-space motion, not an
   actual keypress. Full approach and typing remain incomplete.
6. **Package the usable workflow.** Expose qualified finite trials, preview,
   progress, outcomes and diagnostic export through the wizard. Keep exports in
   the workspace export folder. Later, when supports and the stylus are ready,
   register the actual board/tool/camera and validate physical key and screen
   contact separately.

Completion for this phase means a reproducibly exported noncontact single-key
cycle and short ghost sequence with per-leg reported endpoint verification and
no unresolved execution faults. It does not mean camera calibration, physical
typing, screen tapping, or independently measured stylus accuracy is complete.

Checkpoint at 18:14 UTC: hypothetical -100 mm hand-TCP stylus review of the live
cycle finds 2.267767 mm vertical travel with 1.682998 mm lateral travel per leg.
This is an arc, not a straight keypress. In unregistered vendor-base coordinates,
the final tip is 167.44 mm from the route's PARK entry and 248.12 mm from the first
A-key HOVER. These are distinct waypoints; prior 'first hover' wording for PARK
was incorrect. No route relocation or live motion occurred. Review export
`wizard-20260917T181402014692Z-6bffea7204b44ec6b4285dc45986fc1b`.
Next screen coordinated task-space tip trajectories and the approach separately;
do not treat repeated local wrist motion as completion of the keyboard route.

Checkpoint at 18:10 UTC: the finite automatic wrist pair passed both legs and
reproduced the manually reviewed endpoints. Cycle export
`wizard-20260917T181042068964Z-89bbdac5740d43f681aec56bc04041d5`.
Per-leg publication/verification precedes progression; fresh-pose continuity,
candidate/command binding, cancellation and fault stops are implemented. Fifty
focused tests passed. Down .351116 modeled mm error, up exact reported high;
no runner errors. Next assess this local arc in the hypothetical stylus/ghost-key
geometry and plan task-space approach/press/retract without relabeling the wrist
cycle as a keyboard task. Full objective remains incomplete.

Checkpoint at 18:07 UTC: one separately admitted shared-endpoint wrist pair
completed. Down desired -.068 rad reported -.065961174 (.351116 modeled mm
error); up desired -.052155347 returned exactly that reported angle. Both clean
compensated completions, no runner errors, other joints unchanged. Follow-up
read-only preflight admits the high endpoint. Next automate the finite pair with
export-before-progression and fault tests, then repeat. This is a local wrist
pair, not yet a ghost-keyboard task or calibrated stylus press/retract.

Checkpoint at 18:04 UTC: ascending correction passed a new desired -.055 rad
target with .489892 modeled mm error, four observations and no runner error.
Final reported wrist -.052155347 rad; a later read-only check matched it. The
margin to .5 mm is narrow. Export
`wizard-20260917T180403867312Z-7320da0a89d14d3aadaf652c0926bd11`.
Next qualify shared endpoints for a finite bidirectional pair; the separate
one-way successes do not yet establish return-cycle repeatability. Keep full
ghost keyboard approach/press/retract pending and preserve physical-accuracy limits.

Checkpoint at 18:02 UTC: separate ascending wrist diagnostic requested +1.5
degrees and reported +1.230469 degrees, other joints unchanged. Modeled target
miss .810134 mm, so strict verification failed. This is substantially different
from descending undershoot; preserve separate directional models. Export
`wizard-20260917T180217981403Z-efa28b4ae1f64b19b7a1382dbcc48c75`.
Next freeze the ascending residual (-.004704207779914954 rad) and validate it on
a separate small target from fresh pose. No automatic return or retry occurred.

Checkpoint at 18:00 UTC: the new fixed-posture descending wrist candidate passed
at desired -.085 rad, then the unchanged bias passed at a nearby held-out desired
-.094203884 rad. Both errors .108677 modeled mm, four samples, no runner errors,
all other joints unchanged. Latest export
`wizard-20260917T180002142128Z-741792e95c244d34b015e0533a4252bb`.
Next separately characterize ascending wrist response before building a finite
bidirectional sequence; do not assume the descending offset works in reverse.

Checkpoint at 17:56 UTC: pinned source review found an explicit T104 final write
and feedback refresh of stored Cartesian pose. A new wrist-only T101 test at the
current shoulder/elbow posture requested -1.5 degrees and reported -.527344 degrees,
with other joints unchanged and no feedback failures. Export
`wizard-20260917T175637612429Z-34ef0ef0e9484ef7810967bb31445882`.
This rules out T104 interpolation as the sole explanation, not all firmware or
mechanical causes. Next use the isolated residual to freeze and validate a small
local wrist endpoint correction; keep posture fixed and avoid automatic retries.

Checkpoint at 17:53 UTC: the hybrid proposal is rejected for live use. An offline
grid of 2,010 approach targets (1-10 mm translation, pitch offsets -.020..+.020
rad) found no inverse command pair inside both models' training ranges and the
3-degree joint envelope. Export
`wizard-20260917T175346648813Z-8f5fe928fafa4f39b9e7a73bedf10c07`.
This is a finite-grid result, not proof that every possible route is infeasible.
Next isolate wrist command response and review coordinated-command semantics;
do not widen model ranges to force the hybrid into use. No live motion sent.

Checkpoint at 17:50 UTC: offline chronological model comparison trained on the
first two nearby coordinated trials and evaluated the third without fitting to
it. Elbow affine-delta prediction error was .061922 degrees; wrist proportional-
gain error was .097218 degrees, versus .299280 degrees for averaged additive
wrist bias. Export `wizard-20260917T175047625832Z-94203ba8bc614fbcba48c69bf5b48551`.
This is exploratory model selection on a tiny changed-posture sample, not
qualification. Next screen a frozen hybrid candidate using these existing
coefficients, with a new independent live validation. No motion at this checkpoint.

Checkpoint at 17:48 UTC: v2 completed its bounded observation window without a
runner error. Desired residual .881280 modeled mm (still failed at .5 mm).
Elbow desired residual .064338 degrees; wrist .201745 degrees. Thirty feedback
samples retained; a final read was intentionally not started with less than its
normal .8 s budget remaining. No return or next movement. Continue wrist-focused
local refinement and held-out validation; do not claim independent tip accuracy.

Checkpoint at 17:45 UTC: native feedback admission now reserves the normal .8 s
I/O budget within the unchanged transaction deadline. If insufficient, the runner
records a skipped-read scheduling reason and ends at the deadline without claiming
arrival. Real transport faults are not suppressed. 58 runner/regression tests and
16 candidate/comparison tests passed. No live movement during this checkpoint.
Cross-trial comparison export `wizard-20260917T174530932266Z-a70210a8fc824850aadabd26f1235941`
shows +0.195 degree bias changes at both elbow and wrist, but starts/commands differ.
Next screen a v2 local bias candidate using the latest reported residual, preserving
v1 and requiring new held-out evidence. Keep direction, scope and sweep checks.

Checkpoint at 17:42 UTC: a frozen coordinated elbow/wrist additive-offset candidate
was implemented, screened, and tested on a held-out next target. Desired error was
1.725343 modeled mm; elbow and wrist desired residuals were each about +0.195 degrees.
The trial failed desired verification and retained a late feedback timeout. Fresh
read-only recovery succeeded; no subsequent motion. Review residual variation and
the late request's remaining deadline before another candidate. Step 3 remains
incomplete; smaller error on a different target is not a controlled accuracy claim.

Checkpoint at 17:37 UTC: step 3 has a new coordinated diagnostic, not a pass.
Export `wizard-20260917T173649895803Z-4dd31f63a6874991aaec1828fb30aaf1` contains
32 samples without transport failures and a 3.694687 modeled mm endpoint miss.
Saved analysis identifies +0.331902 degree elbow residual and +0.686408 degree
wrist residual, unchanged after 0.467 seconds. Next design a correction bounded
to the observed posture/directions and validate on new evidence; do not dispatch
the next ghost route leg from this failed result.

Checkpoint at 17:33 UTC: steps 1 and 2 below are complete for the specifically
bound extended-start descending wrist candidate. 62 focused tests and 17 adjacent
regressions passed. Live export
`wizard-20260917T173331734047Z-db11da2e2b81417dbedb5f0c4affab62` verified desired
arrival with five samples, no runner error and 0.401277 modeled mm residual.
Preparation's failed endpoint is preserved separately. Step 3 is next; this does
not qualify arbitrary wrist targets, ascending compensation or physical accuracy.

### 1. Finish clean wrist endpoint handling

Reuse the existing clean compensated-completion mechanism only for explicitly
bound wrist candidates. Stop normally once fresh desired-position samples meet
the existing tolerance and dwell rules. Preserve the independent wire-target
verdict, rather than waiting unnecessarily for an intentionally offset target.

Test candidate binding, wrong posture, stale/incoherent feedback, missing receipt,
other-joint changes, timeout and cancellation. Historical failed runs stay failed;
do not whitelist generic timeouts. Exit: focused regression tests pass and the
new opt-in path cannot authorize unrelated commands.

### 2. Validate one clean wrist trial

Read the actual current pose; saved final positions are not a current baseline.
If preparation is necessary, screen and export it as its own trial. A failed
preparation must not automatically dispatch the next command. Review the resulting
pose separately and use only a candidate whose declared start range admits it.

Run one frozen-candidate validation, export it and assess clean termination,
desired endpoint, dwell, timing and other-joint stability. Exit: a new clean
reported-state pass, not retrospective promotion of an earlier diagnostic.

### 3. Qualify a bounded coordinated segment

Use the current posture to select a short noncontact segment and screen joint
limits and modeled sweep. Do not transplant the old elbow-only correction into
a changed shoulder/wrist posture without validation. Compare requested versus
reported changes joint by joint, separating transport failures from residuals.
If needed, collect a small posture-specific mapping, freeze it, then test it on
new data. Exit: useful repeatable desired-endpoint arrival within the declared
local scope, without widening tolerances simply to turn failures into passes.

### 4. Perform one ghost-key cycle

Preview approach, hover, simulated press and retract with the hypothetical 100 mm
tool. Keep the entire swept volume free of real contact; the simulated key plane
is not the real board. Admit each leg from fresh feedback and the preceding clean
result. Export before advancing. Stop without automatic retry or return on an
uncertain result. Exit: one complete finite noncontact cycle with traceable results.

### 5. Expand to a short ghost sequence

Use a few adjacent virtual keys before expanding travel or speed. Change one
variable at a time and retain held-out repeats. Summarize success rate, desired
endpoint residuals, repeatability, duration and transport failures. Prefer the
simplest configuration meeting the declared task tolerance; do not claim typing
success from controller telemetry alone.

### 6. Prepare the hardware handoff

Keep measured keyboard geometry, board registration, actual stylus tip transform,
camera calibration and contact-depth/compliance testing explicitly pending.
When ready, verify these before any physical keypress or phone-screen contact.
Only independent physical measurements can establish absolute tip accuracy or
support a claim of improving on a manufacturer's millimeter specification.

## Evidence and operating rules

Exports remain in `software/runs/wizard-exports`. Each leg must distinguish desired
target, compensated wire command, reported endpoint, modeled Cartesian endpoint
and any independent operator observation. Include timestamps, candidate/version,
start scope, speed, acceleration, receipt/transport outcome and final verdict.
Do not infer independent feedback acquisition timestamps where firmware supplies
none. Unchanged reports alone do not prove new sensor acquisition.

No additional broad scaffolding or repeated visibility demonstrations are needed.
No new live motion is authorized by editing this document alone; execution uses
the existing bounded command admission and fault-stop checks. Standing user
authorization avoids routine prompts, not fresh software checks. Camera absence
does not block noncontact local testing, but does block camera-based validation.

## Completion boundary

This phase is complete when a bounded ghost-key cycle and short sequence execute
with automatic per-leg checks and reproducible exports, and the remaining physical
registration/contact work is clearly documented. It does not mean unrestricted
motion, camera readiness, calibrated physical accuracy or successful real typing.
