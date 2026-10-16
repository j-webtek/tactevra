# Tactevra project status

Reviewed September 28, 2026 through the ARM-076 typing collision-evidence
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

The final camera is now installed for the October 2026 keyboard campaign. A
read-only B0477 capture at 1920 by 1080 YUY2 binds the fixed workcell epoch, and
the measured six-tag board now supplies a reproducible image-to-board planar
mapping. Its independent interior-tag checks reach 7.4937 mm maximum error, so
keyboard overlays may proceed while camera-guided motion remains blocked. Full
intrinsics, board-to-robot registration, tool offsets, contact, and physical
typing qualification remain open.

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
| Fixed camera board-plane mapping | The installed 610 by 457 mm board and six measured 40 mm AprilTags produce a reproducible B0477 image-to-board homography | Saved-frame overlays can use measured board XY with a current 7.4937 mm held-out maximum; this does not establish lens intrinsics, Z, robot registration, or motion authority |
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
