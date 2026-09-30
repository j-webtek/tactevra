# Tactevra project status

Reviewed September 29, 2026 through the ARM-132 shadow-service reuse campaign,
the ARM-128 retained endpoint-atlas campaign,
the ARM-126 retained service fault campaign,
ARM-125 bounded shadow service,
ARM-124 retained owner fault campaign,
ARM-123 single-owner cache integration, the ARM-122 retained exact-result cache
benchmark and invalidation matrix,
ARM-121 lifecycle-bound cache experiment,
ARM-120 retained multi-sequence IK effort campaign, ARM-119
decision-neutral IK effort telemetry, ARM-118 retained
typing preparation benchmark, and ARM-117 typing planner preparation,
ARM-077 PC0 pre-camera qualification basis, ARM-076 typing collision-evidence
intake, ARM-075 exact-sample offline IK screen, AI-403 precision-adapter
integration, and merged physical-camera
campaign/evaluator work through PR #152. PR #151 subsequently updated the AI
test dependency to Torch 2.13; that dependency merge does not change physical
qualification or execution authority.
Unmerged workstream branches are not included in this summary.
This is a capability summary for readers; the
[shared workplan](software/ai/docs/SHARED_AI_ARM_WORKPLAN.md) retains current
stage ownership, while the [evidence ledger](software/ai/docs/EVIDENCE_LEDGER.md)
preserves detailed test records as development continues.

Protected `main` also carries the shared model/arm conformance profile,
operational-readiness gate, retained camera/support binding adapter, and the
mainline precision adapter from PRs #115, #119, #120, and #126. PRs #147,
#148, and #152 add the physical-camera campaign, AI evidence ownership, and
strict localization evaluator. These controls
formalize software compatibility and evidence requirements but add no physical
observation or movement authority.

The final-camera dependency is tracked as a targeted physical-integration hold
in [the camera integration hold](docs/CAMERA_INTEGRATION_HOLD.md). Preparatory
software, evidence, documentation, and distribution work may continue, but
measured calibration and physical perception claims must wait for the fixed
camera installation.

Tactevra (formerly RoCell) is an experimental robot workcell intended to carry out keyboard and phone
tasks from a person's text request. You can explore the software and run offline
examples today. A reliable physical typing or phone-operation product is still
being developed.

## At a glance

- **Try now:** the [hardware-free walkthrough](docs/GETTING_STARTED.md) turns
  a supported text request into proposed key actions and nominal coordinates.
  No model download or robot is needed.
- **Research progress:** AI/arm contracts, simulated planning, and command
  previews have software evidence. Specific supervised noncontact movements
  also have historical lab records; they are not a general typing qualification.
- **Not demonstrated:** reliable camera-guided physical typing or phone operation.
  Merged firmware and clear simulated waypoints do not authorize movement.
- **Distribution:** no source release is published at this checkpoint. The
  earlier preview effort was [deferred, not completed](https://github.com/j-webtek/tactevra/issues/25).
  [Issue #45](https://github.com/j-webtek/tactevra/issues/45) was closed by
  removing the tracked vendor file and retaining a link-only boundary. The
  broader [Waveshare model license disposition](docs/decisions/0001-waveshare-model-license-disposition.md)
  now records the upstream declaration, owner decision, and remaining caveat.

The sections below explain the evidence behind this summary. For setup help,
use [support](SUPPORT.md); for implementation ownership and newer increments,
use the shared workplan linked above. The [public roadmap](ROADMAP.md) describes
the evidence required to advance from this checkpoint without treating plans as
completed capabilities.

## What works today

| Area | Available now | What this establishes |
| --- | --- | --- |
| Local interface | Browser and terminal rehearsal, task planning, diagnostic exports | Software workflows can be explored without connecting a robot |
| Text interpretation | Grounded parser and deterministic compiler for supported requests | Supported text can become an ordered list of named actions; arbitrary language is not guaranteed |
| Scene assessment | Local vision adapters and experimental Gemma scene checks | Saved images can be assessed for device visibility and quality; results remain provisional |
| Keyboard localization | KeyboardPoseNet trained on synthetic images | Candidate keyboard poses and key coordinates can be evaluated offline; real-camera accuracy remains unqualified |
| AI-to-arm interface | V2 batch assembler, strict decoder, registry snapshot, and freshness checks | Actual assembler output passes shared software tests with synthetic evidence, preserving action order and rejecting tested invalid inputs |
| Model/arm compatibility | Shared conformance profile and operational-readiness gate | Software can reject tested incompatibilities and incomplete evidence before execution; a pass does not authorize movement or qualify a physical setup |
| Precision evidence | Pose-output adapter, deterministic V2 batch producer, identity/capture bindings, and compact held-out synthetic evaluation | The adapter preserves repeated targets and fails closed on invalid qualification, domain, freshness, confidence, identity, or containment; its 14.400834977 mm synthetic bound crosses ordinary key safe regions, so deployment qualification remains uninstalled |
| Arm planning adapter | Admitted v2 proposals enter the arm-owned measured planning policy | The tested valid input reaches the planner but stops for missing or stale calibration; no trajectory or controller command is produced |
| Installed collision evidence | Strict measured profiles bind body geometry and clearance policy to the manifest, build, model, and base collision contract | The measured trajectory screener can consume this profile without falling back to nominal geometry, but continuous full-body sweep remains unimplemented and release stays blocked |
| Conservative route collision evaluation | Robot poses are FK-derived at bounded samples; rigid motion is enclosed by URDF-derived margins, each adjacent pair requires a profile-bound cable envelope, and one exact contact allowance can be bound to a sealed no-write envelope | Synthetic fixtures test clear, collision, crossed-identity, contact-policy, and resource cases; installed engineering evidence and physical qualification still block release |
| Controller-command preview | Sealed synthetic trajectories can be encoded into Waveshare T=102 bytes and a proposed dispatch schedule | Offline encoding and published schemas are tested; the preview has no transport and sends nothing to the arm |
| Execution lifecycle rehearsal | Ownership, single-use reservations, fault handling, and restart reconciliation are modeled | Tests exercise no-retry and fault rules without device I/O; this is not an installed live execution service |
| Reviewed permit bridge | A consumed single-action review can be bound to the existing safety supervisor and an exact-goal motion permit with hash-chained lifecycle acknowledgments | Portable tests cover accepted, started, completed, failed, and uncertain records; there is still no controller transport, physical execution, or independent outcome evidence |
| Sole-writer dispatch rehearsal | One-use permit consumption, an exact encoded-write attempt, receipt hashing, and ordered settling checks | The passing fixture is hardware-incapable and in-memory; it does not establish native transport, independently acquired feedback, physical movement, or task outcome |
| Controller evidence gate | Required controller identity, mapping, protocol, freshness, and review fields are checked | Modeled records test rejection behavior; even a passing record grants no transport or execution authority, and no physical originals were qualified |
| Installed-controller compatibility | A passive r96 observation is recorded; an offline assessment checks the installed application's command surface | r96 lacks the required generic production command/feedback interface and remains blocked; its identity evidence is not independently qualified |
| Production runtime contract | A host-side executable specification rehearses safe-idle startup, one writer, ordered commands, deadlines, and feedback checks | Software rules are testable without I/O; this is not replacement firmware or an installed execution service |
| Production firmware candidate | r97 controller-side implementation compiled offline; source, integration, sealed review handoff, typed review-decision, full synthetic review-to-epoch rehearsal, and owner-governed measured-epoch intake contracts are merged | The owner accepted a clearly labeled non-independent AI review and the reproducible `software_build` component is ready, but seven required physical components remain missing and the epoch identity is null; installed qualification and all physical use remain blocked |
| Synthetic model-to-controller lineage | Exact synthetic review and epoch identities now bind through actual AI-assembler bytes, arm ingress and freshness checks, the measured planner blocker, a sealed synthetic trajectory, T=102 profile, and zero-write preview receipt | Crossed identities reject and one encoded command is reviewable, but the real planner stops for missing calibration, production dispatch remains explicitly blocked, and no bytes are sent |
| Arm control research | Documented supervised noncontact movement and joint-feedback checks | Specific lab sequences were completed; controller feedback does not measure key-contact accuracy |
| Hardware | RC03 workcell design and step-by-step assembly package | Design and print resources exist, with their own measurement and print-readiness requirements |

### Recent progress, in plain language

The latest collision increments derive robot and attachment poses from exact
accepted joint solutions, insert bounded joint-space samples, and build
conservative rigid envelopes between each adjacent pair. Every pair also
requires a hash-bound measured cable envelope. Collisions, missing evidence,
crossed identities, unsupported joints, or resource overflow block the route.
An additive gate now accepts only reviewed global exclusions and, for a contact
proposal, one exact installed tool/device pair at one target-bound `CONTACT`
waypoint. It binds that policy and the conservative-sweep hash to the same v2
proposal and no-write trajectory envelope. Clear fixture checks still cannot
release motion because no independently measured installed profile, engineering
contact evidence, or physical qualification has been supplied.

The arm lane can now inspect what controller-command bytes a synthetic movement
would produce, without sending them. It also rehearses how one command owner
would reserve work, stop on faults, and reconcile a restart without automatic
retries. Published schemas and an exact-byte fixture let the workstreams check
the same boundary. These developments do not remove the real planning path's
calibration block or qualify an installed controller mapping.

The latest integration check begins with canonical bytes from the actual AI
batch assembler, rather than a hand-built substitute. The arm decoder, registry,
freshness gate, and measured planner all consume that same payload. The measured
planner then correctly stops because commissioned calibration is absent. A
separate synthetic copy carries the same batch/proposal identity through the
synthetic r97 review decision, eight-component epoch, sealed trajectory,
encoding profile, and zero-write receipt. This closes the software wire-format
and lineage gap between the workstreams without claiming that the synthetic
observation fixture, learned model, physical route, or controller is qualified.
It opens no transport and sends no bytes.

The newer controller-evidence gate checks whether a supplied record matches the
encoding profile and its declared session, mapping, and protocol. Its success
cases use modeled records, not independently authenticated physical evidence.
See ARM-021/023 in the
[evidence ledger](software/ai/docs/EVIDENCE_LEDGER.md); the gate does not collect
that evidence.

Since that checkpoint, the arm lane recorded one passive controller observation
without a restart or movement (ARM-024). The subsequent offline assessment found
that the installed r96 diagnostic application cannot accept the generic command
and feedback interface needed for production use (ARM-026). This is a design
boundary, not a failed movement test: r96 remains useful diagnostic history, but
cannot simply be connected to the new planner as its execution service.

A separate [production runtime contract](software/docs/PRODUCTION_CONTROLLER_RUNTIME_CONTRACT.md)
now defines the required behavior in a host-side, zero-I/O rehearsal (ARM-028/029).
It models one command owner, strict ordering and deadlines, and stopping on
ambiguous feedback or restart. The subsequent
[r97 firmware candidate](software/docs/PRODUCTION_RUNTIME_FIRMWARE_R97.md)
implements a narrow controller-side command and feedback surface (ARM-030/031).
The ledger records a 314,640-byte offline build, 30 focused tests and 107 selected
integration tests passing. These are overlapping software checks, not physical
trials. Its configuration epoch remains explicitly unset. Independent source/image
review, configuration binding and installed qualification are still open. The
epoch intake now requires and validates the full content-addressed external
decision rather than trusting a hash and approval label alone, but no reviewer
decision has been supplied and software cannot authenticate reviewer identity.
No controller was installed, started, queried or moved in that work. The passive record and
compatibility assessment reference local evidence not included in a fresh clone;
this public summary reports the ledger, not an independent physical revalidation.

The merged host acknowledgment update (ARM-032) also checks that each command's
acceptance receipt matches its pending sequence before allowing further work.
It remains a zero-I/O rehearsal: command acceptance is not proof of arrival, and
missing or ambiguous receipts must not trigger an automatic retry. Its selected
integration run records 115 passing tests; independent r97 review remains open.

The AI lane has a translation-focused training candidate that improved mean key
position error from about 0.937 to 0.907 mm on reused synthetic development data.
That is a development-selection result, not independent generalization or real
camera accuracy. At this merged checkpoint, a fresh held-out comparison remains
the next dependency; no runtime checkpoint was replaced by this experiment.
The earlier confidence-head experiment **failed its synthetic research criteria**
and accepted no evaluation targets. Better pose estimates do not establish usable
confidence or erase that failure.

Detailed evidence is in AI-035/036 and ARM-018/020 of the
[evidence ledger](software/ai/docs/EVIDENCE_LEDGER.md). ARM-020 records 229
passing tests in its selected integration run, with zero hardware writes and
zero physical movements. Test selections overlap and are not a model-accuracy
score, full-suite qualification, or physical typing success rate.

The merged ARM-046/047 boundary now consumes one reviewed action at most once,
rechecks the existing safety supervisor, derives capability from the frozen
device and interaction semantics, and binds an exact-goal permit to
hash-chained lifecycle acknowledgments. Terminal results prohibit automatic
retry and follow-on movement. This makes the offline handoff more explicit; it
does not add a native controller writer, authenticated feedback, settling,
contact qualification, or independent device-input verification.

The merged ARM-048 increment replaces caller-authored lifecycle start records
with a hash-bound dispatch receipt at one exact encoded-write boundary. It also
models conservative terminal outcomes for zero, partial, ambiguous, or unsettled
writes and denies retry after every dispatch outcome. Its writer fixture cannot
open a port or reach hardware, so the result qualifies the state machine and
evidence contract only—not native transport, controller feedback, movement, or
typing.

The later ARM-064 one-shot active feedback request reached the installed
diagnostic surface but received `FAULT:NOT_READY`; no retry or movement followed.
ARM-065 therefore kept the r97 runtime transition blocked. ARM-066 added a
strict external-decision intake, and ARM-067 records the owner's decision to
accept a non-independent AI technical review without mislabeling it as human or
external evidence. ARM-068 adds the parallel owner-governed configuration-epoch
contract. Its retained draft is intentionally incomplete: all eight physical
components and all 32 required bindings are missing, the epoch identity is null,
and installation, transport, execution, and physical authority remain false.

ARM-069 then closed the four reproducible `software_build` bindings with exact
source, dependency, provider, and build-snapshot evidence plus a separate
owner-AI review. This advances software provenance only: the other seven
components remain missing, the configuration-epoch identity remains null, and
no installed-controller or physical authority was created.

ARM-070 adds the deterministic `camera_support_optics` intake and readiness
assessment. It records the current gap instead of manufacturing evidence: the
camera receipt, persistent identity, commissioned mode and controls, and support
witnesses are all missing. The component remains blocked, the ARM-069 partial
epoch is unchanged, and no camera or hardware authority was granted.

ARM-073 adds the strict file-backed bridge that those four missing originals
will use after collection and owner-AI review. It verifies bounded regular-file
reads, safe relative paths, exact content hashes, closed review fields, and
canonical binding order before constructing ARM-070 inputs. It eliminates
manual transcription but does not create any missing observation, decide model
accuracy, advance the epoch, or grant hardware authority.

ARM-074 adds a zero-authority T2A compiler from ordered typing actions to
semantic Cartesian endpoints, bounded-step IK/collision screening samples, and
analytically jerk-bounded quintic timing estimates. It preserves repeated keys
and compares direct hover-to-hover travel with the park-between-key baseline.
It does not yet run IK, joint-dynamics, installed-geometry, or continuous
collision screening and grants no physical authority.

ARM-075 passes those exact T2A samples through the pinned numerical IK,
calibrated joint bounds, joint-margin, task-Jacobian-rank, and adjacent-joint
continuity gates. Its passing fixture is explicitly synthetic and local.
Installed collision geometry, cable evidence, conservative segment sweeps,
controller timing, and physical qualification remain required; the new receipt
creates no controller commands or physical authority.

ARM-076 connects that receipt to the collision-evidence workflow without
claiming that the synthetic seed is measured feedback. It deterministically
builds the bounded joint sample plan and enumerates the exact installed-profile
attachment, cable-geometry, and adjacent-sweep evidence slots. It fails closed
when the measured installed profile is absent and still performs no collision
screening, controller access, or physical movement.

ARM-077 freezes the offline PC0 qualification basis for the remaining
pre-camera arm integration work. It content-binds the canonical typing
fixtures, source files, synthetic-only calibration/dynamics/controller
identities, outcome vocabulary, and benchmark/resource ceilings. Strict tests
reject authority promotion, reordered fixtures, crossed identities, and source
drift. This creates a repeatable basis for joint-space timing work; it does not
qualify installed dynamics, controller timing, camera evidence, collision
geometry, or physical movement.

ARM-078 adds the first PC1 deterministic joint-schedule boundary. Exact ordered
offline IK samples are lineage-checked, mapped from the frozen semantic joint
order to canonical URDF joints, timestamped, and time-scaled against the
synthetic PC0 velocity, acceleration, and jerk ceilings. The canonical receipt
reports schedule-wide demand and margin and retains explicit blockers for
measured installed dynamics, controller tracking, collision evidence, and a
fresh observed start. PC1 remains in progress; this checkpoint emits no
controller command and establishes no physical typing speed or authority.

ARM-079 completes that synthetic offline PC1 gate with per-segment duration,
velocity, acceleration, jerk, margin, and limiting-constraint diagnostics plus
strict schedule reconstruction. The retained tests exercise all three dynamic
limits, just-inside/just-outside rescale bounds, stationary samples, direction
reversal, and crossed lineage. This makes the zero-I/O PC2 shadow composition
ready to begin; measured dynamics, tracking, collision evidence, fresh state,
and physical authority remain blocked.

ARM-080 composes the actual strict V2 decoder and existing T1/T2/PC1/collision-
intake boundaries behind one zero-I/O API. Retained `robot` and
`H,H,1,PERIOD` receipts preserve order and repetition, bind nine stage hashes,
and stop at the honest installed-collision-profile and fresh-state blockers.
PC2 remains in progress; the new boundary has no writer, transport, or physical
authority.

ARM-081 completes PC2 with a canonical receipt parser/schema and stage-owner
mutation matrix. Rehashed receipt tampering and mutations at the decoder,
semantic ingress, freshness, IK lineage, and dynamics boundaries fail closed
while the retained golden traces remain deterministic. PC3 rolling-horizon and
restart-safety work is now ready; physical evidence and authority remain
unchanged.

ARM-082 completes PC3. The runtime now retains one current typing action and at
most one non-authoritative preview, both bound to exact observed-state and
configuration identities. Drift or expiry invalidates the horizon;
pre-dispatch restart reconstructs without replay, while a restart after durable
dispatch intent is terminal `OUTCOME_UNCERTAIN` with retry forbidden. PC4 is
ready; no controller bytes, transport access, movement, or physical authority
were added.

ARM-083 completes PC4. The current action's exact timed joint samples now map
deterministically to pinned Waveshare T=102 bytes behind a zero-write boundary.
Joint ordering, timing, firmware speed/acceleration, gripper policy, deadlines,
and feedback requirements remain arm-owned. Exact execution lineages are
sealed into one dispatch-intent identity; no transport, permit consumption,
automatic retry, movement, or physical authority was added. PC5 is ready.

ARM-084 begins PC5. The repository now has one canonical synthetic-offline
campaign receipt covering 35 stable dispositions across model input,
identity/order, planning, transport/feedback, process-crash, and
runtime/resource fault families. AI ingress, rolling horizons, and controller
preview reconstruction also enforce explicit depth, action-count, command-count,
and payload limits. The affected 86-test suite passes with zero I/O. PC5 is not
complete until the remaining planner, transport, crash, and cache observations
are produced by their actual owner boundaries.

ARM-085 completes PC5. All 35 required fault dispositions now have direct
zero-hardware owner-boundary coverage spanning strict model decoding,
identity/order validation, IK and dynamics screening, collision/clearance
admission, transaction and protocol-emulator uncertainty, sequence handling,
restart reconciliation, deadline/cancellation behavior, and a bounded
hash-bound observation cache. The affected 145-test suite passes with no
physical transport, command authority, movement, or automatic retry. PC6
unified trace journaling and deterministic replay is ready.

ARM-086 begins PC6. A zero-authority trace manifest now binds 14 ordered stages
from request and AI batch through controller/feedback rehearsal and an explicit
effect-verification placeholder. Only bounded sizes and hashes are retained.
Replay deterministically rejects missing, changed, truncated, extra, reordered,
or identity-crossed artifacts and cannot execute their contents. The affected
99-test journal/planning suite passes. Actual retained PC2-PC5 adapters and a
clean-checkout replay command remain before PC6 can complete.

ARM-087 connects the PC6 manifest to the actual strict PC2-PC5 contracts. The
adapter validates and cross-binds the batch, shadow receipt, rolling horizon,
controller preview, and fault campaign, then derives the 14 replay artifacts
and an explicit not-observed effect placeholder. Crossed request, action order,
horizon, or schedule lineage rejects before sealing. The combined 103-test
suite passes with no hardware access. PC6 still needs the contained
clean-checkout replay command and path/redaction qualification.

ARM-088 adds a contained trace package and `replay-typing-trace` command.
Packages stay beneath an explicit nonsymlink evidence root and contain only
bounded canonical files with fixed names and verified hashes. Replay rejects
path escape, symlinks, sensitive keys, absolute paths, mutation, deletion, and
unexpected entries while explicitly reporting zero hardware authority. The
affected 117-test suite passes. PC6 now needs one actual adapter-produced golden
package retained and replayed from a clean checkout.

ARM-089 completes PC6. The repository now retains one bounded package produced
through the actual ARM-087 PC2-PC5 adapter. A regeneration test proves all 16
package files are byte-identical, and an isolated-workspace CLI test replays the
checked-in package as `IDENTICAL` with no hardware imports, commands, or
physical authority. The expanded affected suite passes 119 tests. PC7 safe
transition-cache work may now begin; measured-workcell and camera gates remain
unchanged.

ARM-090 begins PC7 with a bounded zero-authority cache for directional typing
transitions. Keys bind every geometry, calibration, model, dynamics, policy,
tool, and device-pose identity. Values contain only a joint planning seed,
timing estimates, and the prior schedule hash. Every hit revalidates start
state, IK, collision evidence, dynamics, and permit policy and still requires a
fresh plan; it cannot emit commands or reuse admission. Deterministic FIFO
eviction, invalidation, corruption handling, and metrics are covered. Fourteen
focused tests and the 133-test affected suite pass. Broader pair and randomized
equivalence coverage remains before PC7 completion.

ARM-091 completes PC7. Cached-versus-uncached equivalence now covers all eight
canonical PC0 fixtures plus explicit reverse travel, repeated keys,
number/punctuation, and single-key routes. All seven cache identity dimensions
are exercised for invalidation, and a seeded 128-operation campaign proves
bounded deterministic capacity behavior. Thirty-one focused tests and the
150-test affected PC2-PC7 suite pass with identical planning receipts and joint
schedule hashes. PC8 performance benchmarking is now unblocked.

ARM-092 begins PC8 with a strict synthetic performance-report contract. It
requires nine named scenario classes with at least 50 samples each, exact CPU
stage accounting, cache results, resource maxima, predicted route duration,
and deterministic p50/p95/p99 summaries. All retained PC0 ceilings are enforced
and simulation timing is explicitly prohibited from being reported as physical
typing speed. Eight focused tests and the 158-test affected suite pass. An
instrumented runner and retained measured report remain before PC8 completion.

ARM-093 instruments the actual zero-I/O PC2 route. The runner measures process
CPU across decode, static validation, planning, IK, time scaling, collision
intake, and receipt creation, plus peak working-set memory, screening samples,
serialized bytes, predicted schedule duration, and declared cache estimates.
It preserves the ordinary receipt exactly and records zero for preview and
encoding because the honest collision-evidence blocker precedes those stages.
Ten focused tests and the 160-test affected suite pass. The bounded retained
campaign and bottleneck/readiness report remain outstanding.

ARM-094 completes PC8 with a retained 450-observation campaign. Every one of
the nine required scenarios has 50 iterations; all configured CPU/resource
ceilings pass, 50/50 malformed inputs reject, and the exact evidence file and
embedded content hashes are regression-bound. IK is the dominant measured
software bottleneck at 8.953 seconds p95 CPU. The matched synthetic `ROBOT`
comparison predicts an 8.98 percent shorter direct-hover route than the park
baseline, but explicitly makes no physical speed claim. Twelve focused and 162
affected tests pass with zero hardware access, commands, or physical authority.
PC9 camera-arrival evidence tooling is next; installed geometry, calibration,
observed state, tracking, contact, and outcome verification remain blocked.

ARM-095 begins PC9 with one canonical, fail-closed camera-arrival kit. Its 15
slots map camera/support originals, calibrations, installed geometry, cable
envelope, keyboard/tool profiles, and localization evidence to exact external
destinations, schema, review fields, units/uncertainty, and downstream
consumers. The retained synthetic dry run cannot populate measured hashes,
advance an epoch, update a registry, install qualification, open the camera,
start a controller, write hardware, or move the arm. Thirty-three combined
tests pass. The operator checklist now defines collection order and mandatory
stop conditions; PC9 remains in progress while remaining calibration and
installed-geometry consumer dry runs are consolidated.

ARM-096 completes PC9 by binding every arrival slot to the current real
camera-support, planner-calibration, installed-collision, campaign-preflight,
or localization-evaluator source and aggregate schema. The retained map
SHA-256-binds every dependency, and the consolidated 225-test arrival matrix
passes across capture files, checksums, receipts, profiles, calibration,
geometry, support intake, campaign preflight, and evaluation. It consumes zero
measured originals and grants no physical admission or authority. PC10 clean-
checkout pre-camera closure is next; the physical-camera hold remains active.

ARM-097 completes PC10 against detached clean-checkout implementation commit
`baa5745a966284bb94204307f1d37994e4e5bf3c`. The FREEZE-013 lineage rebind
preserves robot numerics and physical-authority flags while regenerating the
dependent shadow, trace, and performance evidence. The clean Windows/Python
3.10.10 checkout passes 507 governed portable tests, 194 explicit PC0-PC9
tests, 115 repository-policy tests, and all maintained policy audits. No
camera, controller, transport, torque, or movement authority was exercised.
The pre-camera software backbone is therefore ready for separately authorized
camera commissioning; the physical-camera hold remains active.

ARM-098 adds the first post-PC10 operational handoff: a read-only preflight for
the external camera-arrival evidence root. It inventories all 15 canonical
slots, verifies strict sidecar structure, exact artifact identity/class/units,
source-file containment, byte count, SHA-256, accepted review, and one shared
configuration epoch. Complete input becomes only
`READY_FOR_OFFLINE_QUALIFICATION_REVIEW`; the tool cannot open the camera or
controller, promote evidence, advance an epoch, install qualification, write
hardware, or move the arm. The governed offline matrix now passes 514 tests.

ARM-099 makes that handoff consumable by the installed base package through
`python -m rocell.application.camera_arrival_evidence_preflight_v1`, freezes a
strict JSON output schema, and adds a hash-verifying parser for downstream
offline consumers. Rehashed authority or slot mutations fail closed. An actual
installed-package smoke test returned the expected blocked 15-slot report with
zero authority, and the governed offline matrix now passes 518 tests. Package
metadata remained unchanged, preserving the frozen software-build evidence.

ARM-100 binds each verified arrival slot to its exact repository consumer
source, downstream schema, and field binding in one canonical, hash-bound
routing receipt. A complete 15-slot epoch becomes only
`READY_FOR_OFFLINE_CONSUMER_VALIDATION`; no consumer is invoked and every
consumer-validation, qualification, physical-admission, device-access, write,
and movement flag remains false. Source corruption, altered maps, rehashed
authority claims, and route-admission mutations fail closed. The governed
offline matrix now passes 527 tests.

ARM-101 adds the matching downstream receipt and aggregate-assessment
contracts. Each consumer result must bind the exact handoff, original hashes,
consumer source/schema hashes, validator identity/version, and output hash.
Missing results remain `PENDING`, failures remain `BLOCKED`, duplicates and
cross-route substitutions reject, and only 15 exact passes produce
`CONSUMER_VALIDATION_COMPLETE_FOR_OFFLINE_REVIEW`. That status still installs
nothing and grants no physical admission or execution authority. The governed
offline matrix now passes 534 tests.

ARM-102 connects three existing domain consumers to that receipt gate. The
camera/support assessment emits four route-local receipts, campaign preflight
emits two, and held-out localization evaluation emits two. Native blockers and
native output hashes are retained; validator identity is bound to the mapped
consumer source. Eight exact passes leave seven routes pending, so this partial
coverage cannot complete offline review or grant authority. The governed
offline matrix now passes 540 tests.

ARM-103 completes emitter coverage with five typed planner-snapshot routes and
two typed installed-collision/cable routes. A full synthetic assembly now
accounts for all 15 route identities, but the current incomplete geometry and
configuration-sampled moving cable correctly remain blocked: 13 passes, 2
blockers, and 0 pending is not completion. This makes route coverage distinct
from qualification readiness. The governed offline matrix now passes 543
tests.

ARM-104 composes the 15-slot structural preflight, repository-bound consumer
handoff, strict canonical receipt loading, and aggregate assessment behind one
offline command. Empty, pending, blocked-consumer, and all-pass states remain
distinct, and canonical receipt-directory rules reject extra, symlinked,
oversized, malformed, crossed, or authority-bearing inputs. Its strongest
result is only `COMPLETE_FOR_OFFLINE_REVIEW`; it opens no camera or transport,
starts no controller, emits no command, and grants no physical authority. The
governed offline matrix now passes 554 tests.

ARM-105 freezes 18 synthetic camera-arrival cases spanning normal, partial,
blocked, corrupted, mixed-epoch, malformed, crossed, unsafe, and bounded-size
inputs. All cases reached their expected owning boundary. The campaign also
fixed strict duplicate/size handling for external sidecars and a mixed-epoch
handoff-parser inconsistency. It remains synthetic and zero-authority. The
governed offline matrix now passes 560 tests.

ARM-106 gives all five native consumer families one operator-facing dispatch
and exclusive receipt-write boundary. Mapping consumers use a uniform CLI;
planner and collision consumers preserve their typed objects through the same
Python API. All 15 route filenames and hashes are covered, overwrites reject,
and the two installed geometry/cable blockers remain intact. The governed
offline matrix now passes 564 tests.

ARM-107 makes a camera-arrival evidence session resumable without weakening the
hold. One hash-sealed manifest binds the 15 originals, routes, receipts,
candidate epoch, camera profile, tool profile, and derived state. Exclusive
creation prevents overwrite; bounded duplicate-safe restart verification
reruns the commissioning orchestrator and requires an exact rebuilt manifest.
The five states keep structural completion separate from validation progress,
and even the strongest state leaves measured commissioning held. The governed
offline matrix now passes 575 tests.

ARM-108 begins PC15 with a typed, bounded cable-envelope contract. It binds
ordered synthetic posture samples and every adjacent swept envelope to one
installed-collision profile and retained source hash. Its evidence is labeled
`SYNTHETIC_OFFLINE_ONLY`; missing or crossed evidence rejects, and the type can
satisfy only the cable receipt route. It cannot install physical collision
qualification. The governed offline matrix now passes 579 tests.

ARM-109 completes PC15 with a retained, hash-sealed eight-case campaign through
the real collision receipt boundary. Complete synthetic templates pass only as
offline rehearsal; missing or unknown camera-holder geometry blocks with exact
body-specific diagnostics. The 64-posture resource boundary passes, and broken
sweeps, crossed lineage, unknown source bindings, and route misuse reject. The
campaign parser and schema preserve zero physical authority. The governed
offline matrix now passes 586 tests.

ARM-110 completes PC16 with an immutable camera replay boundary. It binds frozen
image and metadata bytes, camera/support profiles, model and calibration
identities, the PC11 handoff, retained campaign/localization outputs, and exact
consumer receipt decisions. Identical inputs reproduce identical decisions;
byte, identity, expectation, handoff, or authority drift rejects. Original and
synthetic source provenance remain distinct from `IMMUTABLE_REPLAY`, and no
replay is presented as a fresh capture. The governed offline matrix now passes
597 tests. The arm-side runner revalidates retained outputs through the real
consumers; it does not execute the AI vision model.

ARM-111 starts PC17 with a strict observability contract for PC11-PC16. It
requires bounded monotonic samples, cold/warm and pass/block/pending coverage,
stable codes, safe correlations, and unchanged decision hashes before and
after instrumentation. p50/p95/p99 are withheld until their declared sample
counts are met. Timing cannot feed admission or claim physical performance,
and the report carries zero camera, transport, controller, write, movement,
and physical authority. The governed offline matrix now passes 608 tests.
That increment established the contract; ARM-112 supplies the retained
host-measured benchmark through the existing stage workflows.

ARM-112 completes PC17 with 120 measurements through the real offline
PC11-PC16 boundaries: 20 per stage, split evenly between freshly materialized
and retained artifact trees. The report records 61 pass, 33 blocked, and 26
pending outcomes; every timed result exactly matches its verification hash.
The dominant measured software work is the complete PC12 fault campaign
(1,333.4719 ms p95) and PC15 collision/cable campaign (256.4344 ms p95) on
this Windows/Python 3.10 host. These are diagnostic host measurements, not
admission thresholds or physical-speed claims. The governed offline matrix now
passes 610 tests.

ARM-113 completes PC18 with one retained, content-addressed corpus spanning the
actual shared emitter, the actual precision-adapter contract fixture, and the
current localization-abstention output. H,H,I preserves repetition and order
through arm admission and offline trajectory compilation. H,H,1,PERIOD also
preserves exact order, but arm admission correctly blocks it because the
14.400834977 mm synthetic localization bound does not fit measured key-safe
regions. Unsupported phone input, uncalibrated localization, exact expiry,
crossed image identity, and low confidence stop at their declared owner. All
seven cases carry zero commands and zero physical authority. The governed
offline matrix now passes 616 tests. This establishes software compatibility,
not camera accuracy, IK/collision qualification, or physical typing.

ARM-114 refines that boundary with two more retained outputs from the actual
shared emitter: a 15-action mixed typing sequence (`robot book 10.` plus Enter)
and a 46-action catalog sweep containing every named keyboard target. Both
preserve exact order through zero-authority trajectory compilation. Four
derived attacks against the real H,H,I payload—authority injection, duplicate
JSON, a non-finite coordinate, and reordered actions—now have exact strict-
decoder outcomes. The report also records the existing 64-proposal and 1 MiB
input ceilings; its largest retained batch is 46 proposals and 15,022 bytes.
The governed offline matrix now passes 619 tests. This remains structural
coverage and does not make the 46 routes physically qualified.

ARM-115 begins the operational-efficiency implementation without weakening
admission. A retained clean-commit benchmark compares full locked-context
source revalidation with an immutable epoch-bound validation lease. Across 20
samples per path, both produced the exact same accepted ingress hash; median
host validation fell from 37.185 ms to 0.115 ms. Changed context epoch,
restarted service identity, changed generation, replaced context object, and
mutated lease all blocked. This is bounded offline host evidence, not a runtime
service, admission threshold, controller benchmark, or physical-speed claim.
The governed offline matrix now passes 655 tests.

ARM-116 connects that lease to a runtime-owned in-process lifecycle. The
lifecycle owns the active context, service identity, and generation, and locks
the complete trusted-registry admission against concurrent reload or
invalidation. Successful reload advances the generation atomically; failed
reload preserves the prior valid state; restart and invalidation revoke stale
bindings. This remains hardware-free application scaffolding rather than a
deployed daemon or physical-performance qualification.

ARM-117 places immutable pinned-model parsing behind that lifecycle for the
typing shadow path. Reload, restart, crossed context, mutation, or unmanaged
reuse rejects, while the full-source and prepared paths emit identical IK,
collision-intake, and end-to-end receipts. Request-specific solver creation,
IK work, dynamic collision evidence, and every physical gate remain uncached.
ARM-118 supplies that clean retained benchmark. Across 20 complete offline
shadow runs per path, immutable preparation reduced p50 from 1.667267 s to
1.590753 s and p95 from 1.705646 s to 1.604661 s; cold preparation itself was
1.190 ms. Every terminal receipt and every stage hash remained identical, and
reload, restart, forged preparation, and unmanaged preparation all rejected.
The result is host-measured optimization evidence only: it does not set an
admission threshold or grant controller, transport, or physical authority.

ARM-119 begins E2 by exposing bounded solver-effort telemetry as a separate
diagnostic output. Enabling it leaves every canonical planning and terminal
receipt hash unchanged. An initial non-retained `ROBOT` run observed 57
waypoints, 228 attempts, and 660 iterations. The first seed converged at every
waypoint but was the selected minimum-residual solution at only 4 waypoints, so
first-convergence early exit is explicitly unsafe for exact equivalence. A
representative retained solver campaign is the next dependency.

ARM-120 completes that retained campaign across five synthetic typing
sequences. It measured 186 waypoints, 744 attempts, and 2,393 iterations. Exact
solver inputs were bound to the active solver source and every relevant
configuration identity: only 48 were unique, leaving 138 repeat observations
across 35 identities and a maximum recurrence of 11. This establishes a strong
candidate for an exact content-addressed result-cache experiment. It does not
authorize caching, relaxed checking, controller access, or physical motion.

ARM-121 adds the resulting exact-result cache as an opt-in offline experiment.
It is bounded in memory, tied to one precise context lifecycle generation, and
uses the complete reference solver on every miss. Each hit revalidates cached
result integrity. Cold, warm, capacity-limited, and cache-disabled governed
tests preserve identical canonical receipts; stale, invalidated, unmanaged,
cross-context, or corrupt reuse rejects. Its counters are non-authoritative and
it creates no controller commands or hardware access. No retained performance
claim has been made yet; the next dependency is a clean cold/warm/capacity
benchmark plus an explicit lifecycle invalidation matrix.

ARM-122 completes that dependency with 40 interleaved clean-commit samples.
For the prepared `ROBOT` path, cache-disabled p50 was 2.919988 s and warm-cache
p50 was 0.301630 s, a 2.618358 s reduction (about 89.7%). Warm p95 improved by
2.639824 s. All receipts and stage hashes remained identical. The cold cache
also reused 110 of 570 inputs inside the measured sequences, while the warm
cache served all 570 lookups without a miss. Explicit invalidation, reload,
restart, crossed context, corruption, and unmanaged use all blocked. This is
strong host-side evidence for bounded integration, but it is not physical
typing throughput, a deployment qualification, or authority to skip safety,
freshness, collision, or verification gates.

ARM-123 adds one explicit owner for the lifecycle, prepared planner, and exact
IK cache. Shadow callers can no longer substitute owner-managed resources.
Reload and restart automatically retire the previous cache and provision an
empty generation-bound replacement; explicit invalidation retires both cache
and lifecycle. A replacement preparation failure leaves the owner unready and
closed. Hashed diagnostics expose only lifecycle and cache counters and remain
outside admission. Governed tests preserve cold/warm canonical equivalence,
prove old-cache retirement, reject old-context inputs and caller overrides,
and verify zero controller, hardware, and physical authority.

ARM-124 retains a clean-commit six-case owner campaign. Normal cold/warm reuse,
reload retirement, restart retirement, and explicit invalidation passed.
Forced preparation failure during both reload and restart also retired the old
cache and left the owner unready, with later execution blocked. All successful
cases preserved one identical terminal receipt. The retained evidence grants
no controller, transport, hardware, movement, or physical authority. The next
dependency is service wiring plus bounded cancellation and generation-race
coverage without weakening the sole-writer boundary.

ARM-125 supplies that zero-authority service boundary. Each request is bound at
submission to its canonical payload, intent plan, context epoch, service
instance, and lifecycle generation. The bounded FIFO admits only one shadow
request at a time, never permits request-ID reuse or automatic retry, and has no
executor, transport, or sole-writer capability. Cancellation is terminal only
before admission. Reload and restart make older queued work stale; it is
rejected without running the owner. A concurrency test proves a transition
cannot split an admitted request across generations. Explicit invalidation
accounts for every discarded queued request. Hashed receipts and snapshots
remain diagnostic and report zero controller commands, hardware access, and
physical authority. This closes the planned service-wiring and generation-race
dependency; endpoint-atlas and warm-start experiments remain next.

ARM-126 retains the corresponding clean-commit eight-case fault campaign.
Normal FIFO completion, pre-admission cancellation, reload and restart stale
rejection, queue saturation, explicit invalidation, unexpected shadow failure,
and admitted-request/reload serialization all passed. The two completed cases
preserved the same shadow decision hash. Cancellation, stale rejection, queue
saturation, invalidation, and forced failure performed zero owner runs. The
race transition demonstrably waited for the admitted request. The retained
artifact reports zero controller, transport, hardware, movement, and physical
authority. Service wiring is now evidenced rather than only unit-tested; the
next E2 dependency is endpoint-atlas analysis before any warm-start proposal.

ARM-127 adds a bounded, decision-neutral endpoint-atlas observer to the exact
typing IK screen. It records accepted semantic PARK, HOVER, CONTACT, and
RETRACT endpoints only after the canonical solver and continuity decision. An
endpoint identity binds phase, target, and exact board point; separate hashes
bind incoming and solved joint states. Per-route reports expose repeated
endpoint and transition counts plus observed joint-solution stability, but
explicitly forbid atlas use in planning or admission. Governed tests prove the
canonical shadow receipt remains byte-identical with observation enabled and
that capacity, integrity, aggregate, transition, and authority mutations fail
closed. A retained representative-corpus atlas study is still required before
proposing any warm-start behavior.

ARM-128 runs that observer from clean source across the five established
representative sequences: home transition, `ROBOT`, repeated
letter/number/punctuation, alphabetic extremes, and number/space/enter. The
retained campaign preserves the reference shadow receipt for every route and
records 186 screened samples, 58 semantic endpoints, and 53 transitions. It
finds 40 unique endpoint identities; seven recur, and every recurring identity
has one observed solved joint-state hash. All 40 endpoints are stable in this
bounded corpus, with zero variable-solution endpoint observations. This is a
useful exact-reuse candidate map, not a general proof of path independence:
atlas use and warm starts remain explicitly unauthorized until a separate
equivalence-preserving experiment covers invalidation and hostile contexts.

ARM-129 adds the next decision-neutral experiment rather than enabling endpoint
reuse. A lifecycle-bound verifier stores a bounded candidate solved state for
each exact semantic endpoint, then compares every recurrence with the complete
canonical solver result. Its decision context binds build, model, calibration,
joint bounds, gripper configuration, IK options, algorithm, implementation,
and solver-source identity. In the repeated `ROBOT` test, two complete runs
preserve the reference receipt while 21 candidate hits match the canonical
solution and zero conflict. Capacity, lifetime sample bounds, entry corruption,
deliberate solution conflict, decision-context mismatch, reload, restart,
crossed context, and unmanaged use all reject or remain bounded. Candidates
remain excluded from decisions and admission; warm starts remain unauthorized.

ARM-130 retains that verifier's clean-commit qualification across the same five
representative sequence families used by the atlas. Every instrumented receipt
is byte-identical to its reference. The cumulative verifier records 186
samples, 58 endpoint observations, 40 stores, 18 repeat matches, and zero
conflicts, exactly reconciling with ARM-128. A ten-case fault matrix bounds
capacity and rejects sample exhaustion, invalidation, corruption, deliberate
solution conflict, changed decision context, reload, restart, crossed context,
and unmanaged use. This closes the evidence prerequisite for considering a
separate substitution experiment; it does not authorize substitution, warm
starts, controller access, or physical motion.

ARM-131 resolves the substitution choice without introducing a second cache.
Endpoint-only substitution remains forbidden because it omits the incoming
joint state. The existing exact-input cache includes that state and every other
solver identity, rechecks entry integrity, and performs a complete solve on
each miss. A clean-commit five-pattern campaign preserved every canonical
receipt and stage hash across 186 lookups. Cold per-route caches safely reused
26 exact inputs; warm caches served all 186. Aggregate host time was 10.645 s
without reuse, 8.835 s cold, and 1.040 s warm. This is experimental shadow
timing, not physical throughput or permission to relax safety gates.

ARM-132 qualifies that exact-input cache at the bounded shadow-service request
boundary. Five mixed requests executed in FIFO order through one owner and
produced 186 lookups, 48 full-solve misses, and 138 exact hits. Cancellation
performed zero owner runs and zero cache work. Reload and restart rejected the
queued stale request, retired the previous cache, and completed one new
current-generation request from a cold cache with 23 misses and one safe
within-route hit. No automatic retry occurred. Request-level timing remains
diagnostic, and the service remains detached from any executor or sole writer.

AI-403 then integrates the pose-output precision adapter and actual V2 batch
producer on current `main`. The retained contract fixture deterministically
preserves `H,H,1,PERIOD`, while invalid qualification, domain, freshness,
identity, confidence, and containment paths abstain. Its disjoint 2,000-case
calibration and 2,000-case held-out synthetic evaluation measured 0.9975
coverage at a declared 0.99. The conservative planar bound is nevertheless
14.400834977 mm, which crosses ordinary key safe regions. The candidate remains
`SYNTHETIC_OFFLINE_ONLY`, is not installed for deployment, and grants no
controller or physical authority.

Repository improvements include protected-main CI, support and private security
reporting, contributor handoff templates, reviewed dependency updates, and an
experimental source-release checklist. CI now exposes resolved package versions
and coverage limits in each job summary. No source release has been published at
this checkpoint. The snapshot audit now
uses [exact reviewed synthetic-fixture exceptions](docs/AUDIT_FIXTURE_REVIEW.md);
historical failed audit records remain intact. An audit pass is not security
certification. See [test tiers](docs/CI.md) for clean-checkout limits.

## What still needs work

The main gap is connecting trustworthy perception to physical execution. The
current v2 assembler can consume output from the merged precision adapter, but
the retained qualification is synthetic and intentionally uninstalled. The
system does not yet produce a deployment-qualified batch from a final-camera
capture. The trusted registry is an in-process snapshot; creating it does not
establish the provenance of the measurements it contains.

Before physical typing can be demonstrated, the system needs measured camera,
board, device, robot and tool relationships; qualified localization and confidence;
validated movement and contact behavior; and independent confirmation that the
intended character actually appeared. The phone workflow also needs fresh screen
state observations between actions. Phone contracts and simulations do not yet
demonstrate an operating dialer or completed call.

## Current development direction

The highest-value next test is a fixed final-camera measurement campaign, not
another broad ghost-motion routine. It must retain the four camera/support
originals, measure camera-to-board, board-to-robot, keyboard-to-board, and
tool-to-joint transforms, and evaluate the merged adapter on disjoint real
captures. Deployment can advance only when the combined perception,
calibration, tracking, and tool uncertainty fits inside each applicable target's
safe-region margin. The arm lane
has merged the offline r97 firmware candidate and the owner's explicitly
non-independent AI-review decision. The reproducible `software_build` evidence
is now ready, and the `camera_support_optics` intake is implemented but blocked
on four retained physical originals and their owner-AI review. Six additional
configuration components also remain missing. Configuration binding and installed-controller
qualification remain unresolved. A merge is not deployment approval or evidence
that the device is running r97.
The existing r96 application remains incompatible with that production interface;
closing paperwork alone will not add the missing command handlers. Both use the same
[AI/arm workplan](software/ai/docs/SHARED_AI_ARM_WORKPLAN.md).
The next shared milestone is a measured final-camera observation that survives
the existing model-to-arm gates and reaches checked planning without synthetic
promotion. Further physical qualification is tracked separately. Stylus loading
and additional ghost routines are retained as specific lab procedures, rather
than the general next step for every reader.

On the arm-efficiency lane, ARM-133 now freezes exact-input IK reuse behind an
explicit shadow-only eligibility profile. It matches the active lifecycle,
build/model/calibration identities and four retained qualification files, and
requires the qualified 256-entry bound, complete-solve fallback, and no retry.
Mismatches cannot silently use cached results: they fall back to the complete
solver or reject stale/unsafe configuration. This improves readiness for a
warm command service but does not enable execution or claim physical speed.
ARM-134 now applies that profile at the shadow-service composition boundary.
The qualified path uses the existing exact-input cache, while calibration or
evidence mismatch and lifecycle transitions use the unchanged complete solver.
The five retained cases preserve the reference result and show zero cache
activity on every fallback. This is operational scaffolding only: no executor,
controller transport, retry, or physical authority is attached.
ARM-135 now sends canonical bytes from the actual shared AI batch assembler
through that composition using a declared synthetic integration fixture. The
retained `robot` sequence preserves `R,O,B,O,T`; its second request is a 57/57
exact-cache hit, while calibration/evidence mismatch and lifecycle transitions
remain complete-solve-only. One host observation improved from 2.3158146 s cold
to 0.3004444 s warm, but this is diagnostic software timing—not final-camera,
controller, device-effect, or physical typing evidence.
ARM-136 broadens the same integration to five mixed actual-emitter sequences in
one FIFO service generation. Both cold and warm rounds completed all requests in
order. The cold round reused 138 of 186 exact solver inputs and fully solved 48;
the warm round reused 186 of 186. Recorded cold p50/p95 were
0.2685515/1.3913187 seconds, versus 0.1982934/0.2997009 seconds warm. Those are
five-sample host diagnostics only. They do not establish stable tails,
controller throughput, physical typing speed, or deployment authority; the
campaign opened no transport and produced zero hardware writes and movements.
ARM-137 repeats that workload across 20 isolated cold/prewarmed service pairs.
All 200 measured requests retained FIFO order and exact cold/warm shadow-receipt
equivalence. The 100-sample cold p50/p95/p99 were
0.2736679/1.4014767/1.4241501 seconds; warm values were
0.1959784/0.3044458/0.3157095 seconds. Each replacement paid the expected cold
solve cost, each measured warm lane hit 186/186 exact inputs, and the bounded
cache reported no capacity skips. This strengthens the software case for a
long-lived qualified service, but it remains synthetic host evidence with no
controller, physical motion, key contact, or independent device effect.
ARM-138 now covers the long-lived warm service under bounded disturbances. It
preserves FIFO completion at the eight-request queue limit, rejects overflow,
cancels selected work before planning, and rejects three malformed or duplicate
submissions with zero cache activity. Reload and restart reject stale queued
requests and retire cache eligibility; no request is automatically retried.
Only a new explicitly qualified service restores the warm path, and its output
matches the retained reference receipt. The seven-case result remains synthetic
and zero-authority, with no controller, transport, hardware write, or movement.
ARM-139 adds a runtime supervisor so cache eligibility is no longer an implicit
service detail. Qualified startup is `WARM`; known mismatch is
`FULL_SOLVE_ONLY`; reload, restart, and invalidation are
`REQUALIFICATION_REQUIRED`. New submissions are blocked in the latter state,
stale work is not retried, and explicit fallback cannot retain exact reuse. A
separately qualified replacement restores `WARM` and reproduces the reference
plan. This remains shadow-only software scaffolding with no controller or
physical authority.
ARM-140 places the canonical model-command bytes behind that supervisor. The
gateway returns signed `ADMITTED` or `REJECTED` receipts, distinguishes queue
pressure, request bounds, malformed input, and requalification blockers, and
never permits an automatic retry. Its retained eight-case campaign preserves
the exact reference shadow result through warm admission, complete-solve
fallback, and qualified replacement. The gateway remains deliberately detached
from every executor, controller, and transport: it proves safe model-to-planner
admission, not physical dispatch or typing.
ARM-141 adds the bounded command-session ledger above that gateway. Every
retained request now has one mission identity, ingress fingerprint, admission
receipt, and hash-chained terminal shadow outcome. Identical resubmission is an
idempotent lookup; changed reuse of the same request ID fails closed. Completion,
cancellation, stale-generation rejection, admission rejection, capacity
exhaustion, and terminal lookup are all retained in an eight-case campaign.
This resolves caller-side outcome ambiguity only; the ledger remains detached
from execution, transport, controller writes, and physical movement.
ARM-142 seals the completed session, original admission, terminal service
receipt, and detailed shadow-planning receipt into one deterministic execution-
handoff candidate. It preserves the exact execution-plan, trajectory, IK,
schedule, and collision-intake hashes but explicitly remains blocked on
installed collision evidence, fresh observed/controller state, a one-use
permit, and independent effect verification. Cross-request lineage swaps,
noncompleted sessions, and authority tampering fail closed. The candidate is
not eligible for an executor and creates no permit or controller command.
ARM-143 retains the exact full shadow-planning receipt inside the bounded
runtime before `SHADOW_COMPLETED` can be reported. Retrieval requires both the
request identity and terminal content hash; repeat reads return the same
canonical artifact without re-planning, while changed replacement, wrong hash,
unknown request, and capacity overflow fail closed. Canceled and stale requests
retain no artifact. This closes the caller-side reconstruction gap used by
ARM-142 but remains an in-memory, zero-authority store with no executor,
controller, transport, automatic retry, hardware write, or movement.
The retained eight-case campaign was generated from clean framework commit
`69ef09bab0b62cceb2ab78b35e4f3c733137fd8d`; the governed offline matrix passes
863 tests after its evidence pin is enabled.
ARM-144 adds one canonical ledger-owned assembly API above ARM-143. A caller
provides only the completed request ID; the assembler retrieves the signed
session, admission, terminal service receipt, and exact retained shadow
artifact, then returns the existing blocked ARM-142 candidate without running
the planner again. Queued, canceled, stale, rejected, and unknown requests fail
closed. Candidate reconstruction remains available after supervisor
invalidation for audit, but never becomes permit- or executor-eligible.

## How to interpret results

- **Simulation:** a result under modeled geometry and assumptions.
- **Controller feedback:** the joint positions reported by the device.
- **Visual observation:** what a person or camera saw during a particular test.
- **External measurement:** a position or clearance measured independently.
- **Verified device input:** confirmation that the intended key or screen action occurred.

A successful result at one level does not establish the next. For example, the
[r91 five-leg record](software/docs/R91_HOVER_RECOVERY_AND_A_CYCLE_PLAN.md#live-five-leg-result-2026-09-25)
is historical noncontact movement evidence, not a reading of the current arm pose
or a physical typing result. Older plans preserve their original failures and
successes; their proposed next steps may have been superseded.

## What a clone includes

The repository contains source, documentation, tests, contracts, hardware design
packages, and selected research records. It is not a copy of the lab workstation.
Private credentials, raw run exports, device backups, local toolchains, and some
measurement/model artifacts are excluded. A link to a lab export may identify
evidence that is unavailable in a fresh clone.

Use [getting started](docs/GETTING_STARTED.md) for a first run,
[the documentation guide](docs/README.md) to find a topic, and
[contributing](CONTRIBUTING.md) for development and sanitized evidence sharing.
