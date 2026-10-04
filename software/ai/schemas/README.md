# Schemas

Version the AI task proposal and adapter result here. A schema must distinguish
`type_text`, `clarify`, and `unsupported`, preserve exact text when supported,
and bind a source observation. The semantic task proposal contains no robot
coordinates or raw controller command. The separate model-motion proposal may
contain device-local or board coordinates but never joints, wire commands, or
transport authority. RoCell's existing `ActionPlan` remains authoritative for
semantic typing actions.

The first implementation work package is in [the roadmap](../docs/ROADMAP.md).
The initial proposal shape is [`task_proposal_v0.schema.json`](task_proposal_v0.schema.json).
The read-only compiler inspection response is
[`plan_result_v0.schema.json`](plan_result_v0.schema.json). An accepted result
contains RoCell's own semantic `ActionPlan`; it is not an execution receipt.
The [synthetic visual target schema](visual_targets_v0.schema.json) is a
separate board-coordinate observation contract. It has no motion authority.
The [synthetic image-model prediction schema](visual_targets_v1.schema.json)
binds pixel and checkpoint hashes to predicted keyboard target coordinates;
its model scores are uncalibrated and it also has no motion authority.
The [held-out localization evaluation bundle](localization_evaluation_bundle_v1.schema.json)
records exact model, target-catalog, disjoint calibration/evaluation dataset,
domain, coverage, error, per-target failure, and adapter-abstention evidence.
Its scope is fixed to `SYNTHETIC_OFFLINE_ONLY`; its qualification candidate may
be absent when declared held-out coverage fails, and any retained candidate is
still uninstalled. This schema is not a deployment-qualification schema.
The [scene-observation schema](scene_observation_v0.schema.json) binds a strict
multimodal scene assessment to exact image bytes. It describes visibility and
image quality and cannot contain coordinates or controller commands.
The [shadow-preview schema](shadow_preview_v0.schema.json) binds one request,
image, scene observation, precision observation, and guarded preview into a
replayable offline record with zero hardware writes and no permit.
The [model-motion proposal schema](model_motion_proposal_v1.schema.json) lets a
model propose a named keyboard or phone coordinate in a declared frame. The
proposal still has no transport authority; deterministic code must resolve,
plan, screen, and admit it before any controller command can exist.
The [ordered model-motion batch schema](model_motion_batch_v1.schema.json) binds
one semantic plan to same-frame, same-image proposals in action order. The
[v2 proposal](model_motion_proposal_v2.schema.json) and
[v2 batch](model_motion_batch_v2.schema.json) add a bounded scene lease,
independent placement and board-frame evidence, camera/clock/lease identity,
integer epoch-millisecond freshness, capability identity, ordered semantic action
indexes, qualified planar uncertainty, and per-observation confidence. V2
deliberately removes model-owned speed and clearance choices and initially accepts
only `board_mm_xy_plane_v2`. The arm consumer composes producer localization error
with independent placement error, while surface-normal evidence is checked
separately. It remains zero-authority and is additive beside the frozen v1
compatibility contract. The
[model-motion ingress report](model_motion_ingress_v1.schema.json) records
RoCell's deterministic admission of that batch while retaining zero hardware
authority.
The [model-motion sequence snapshot](model_motion_sequence_snapshot_v1.schema.json)
tracks that admitted batch one action at a time. It requires a new observed arm
state for every proposal, forbids lookahead and automatic retry, and advances
only after exact, independently verified completion evidence.
The [durable sequence-journal snapshot](model_motion_sequence_journal_snapshot_v1.schema.json)
records the append-only, hash-chained lifecycle and its conservative restart
disposition. A committed dispatch boundary with no verified result explicitly
forbids replay and requires outcome reconciliation.
The [trajectory execution envelope](trajectory_execution_envelope_v1.schema.json)
is the sealed, controller-independent input to the future sole writer. It binds
the current model action and planner/collision evidence to timed five-joint
waypoints, measured position/velocity/acceleration/jerk limits, settling policy,
deadline, controller session, build, calibration, and configuration epochs. It
contains no wire command or execution authority.
The [translation-assurance schema](translation_assurance_v0.schema.json)
records the ordered stage disposition and proves that no downstream stage can
pass after the first blocker in the current offline path.
The [model-motion assurance bundle](model_motion_assurance_bundle_v0.schema.json)
binds a strict coordinate proposal to its deterministic nominal candidate and
forces every physical stage after missing calibration to remain `not_run`.
The [model-motion planner gate schema](model_motion_planner_gate_v1.schema.json)
binds that candidate to the frozen build, frame contract, configuration epochs,
and calibration graph. It remains zero-write and emits neither IK nor a route
while measured calibration, strict payload decoding, or target reprojection is
unavailable.
The [planner calibration snapshot schema](planner_calibration_snapshot_v1.schema.json)
records the exact hash-matched measured transforms, robot reference, controller
correlation, device placement, and tool/TCP geometry accepted by the strict
decoder. It carries no physical authority.
The [model-motion simulation report](model_motion_simulation_v0.schema.json)
binds a nominal coordinate rehearsal to its proposal and static source hashes.
The Python validator also checks hashes and zero physical authority. Even
`SAMPLES_PASS_NOT_EXECUTABLE` does not permit controller execution.
The [measured target reprojection schema](measured_target_reprojection_v1.schema.json)
validates a model point in the measured device frame, binds it to its named target,
and transforms its surface/clearance points into calibrated board frame `B`. It is
Cartesian planner input only and contains no IK result or controller command.
The original [measured trajectory screening v1 schema](measured_trajectory_screening_v1.schema.json)
binds that target to a fresh observed start state, deterministic sampled IK and
joint-continuity evidence, plus the current nominal full-body
collision-readiness audit. The additive
[v2 screening schema](measured_trajectory_screening_v2.schema.json) identifies
whether geometry came from that nominal audit or a strict installed measured
profile and binds the selected collision contract, installed-profile content,
and measured clearance-policy hashes. Missing start telemetry, incomplete
geometry, or the still-unimplemented continuous sweep remains an explicit
blocker. V1 remains published for frozen evidence; new screening reports use v2.
The [observed planner start-state schema](observed_planner_start_state_v1.schema.json)
binds one authenticated, fresh T=1051 receipt to the measured robot reference.
It requires all six feedback joints, applies the calibrated sign/offset projection,
and exposes a time-limited five-joint IK start state with no commands or authority.
The [installed collision-geometry profile schema](installed_collision_geometry_profile_v1.schema.json)
defines the measured, content-addressed body envelopes, source bindings,
engineering exclusions, and clearance policy required before route screening may
rely on the installed arm rather than diagnostic placeholders.

The S4 zero-write controller boundary publishes five strict, closed schemas:
the [T=102 encoding profile](zero_write_waveshare_t102_profile_v1.schema.json),
[single-use preview permit](zero_write_waveshare_preview_permit_v1.schema.json),
[wire preview receipt](zero_write_waveshare_preview_receipt_v1.schema.json),
[sole-writer journal](zero_write_sole_writer_journal_v1.schema.json), and
[sole-writer rehearsal report](zero_write_sole_writer_report_v1.schema.json).
They make the model-to-arm handoff reviewable without granting transport or
physical authority. The profile's joint mapping remains a content-addressed
claim only; these schemas and their synthetic golden bytes do not qualify the
mapping against installed firmware or hardware.
The [installed-controller evidence schema](installed_controller_qualification_evidence_v1.schema.json)
and [assessment schema](installed_controller_qualification_report_v1.schema.json)
close that gap at the software boundary: a profile becomes eligible only for
zero-write profile binding when independently reviewed, current physical
evidence matches its controller session, configuration epoch, mapping hash,
protocol-source hash, T=102 fields, T=1051 fields, planner order, and fixed
gripper field. Even a passing assessment grants no transport or execution
authority; evidence collection and physical qualification remain separate.
The [installed-controller surface evidence schema](installed_controller_surface_evidence_v1.schema.json)
and [surface compatibility report](installed_controller_surface_compatibility_report_v1.schema.json)
add a prior fail-closed check that the exact installed app actually exposes the
generic `T=102` command and `T=105`/`T=1051` feedback paths. The check prevents a
finite diagnostic image such as r96 from being mistaken for a production
runtime. A compatible result still grants no transport, execution, or physical
authority.
The [production runtime manifest](production_controller_runtime_manifest_v1.schema.json)
and [zero-I/O rehearsal report](production_controller_runtime_rehearsal_v1.schema.json)
define the replacement runtime's executable acceptance contract: safe idle at
startup, one writer, exact ordered and expiring T=102 frames, exact T=105/T=1051
feedback framing, terminal closure on ambiguity, and no automatic retry. These
schemas also bind each r97 `T=1021` accepted-once ordinal before another command
or feedback exchange; that receipt explicitly does not prove physical arrival.
They describe an offline contract only and cannot authorize transport.
The [external r97 review decision](r97_independent_review_decision_v1.schema.json)
and its [assessment](r97_independent_review_decision_report_v1.schema.json)
define the separate, content-addressed record an independent reviewer must
publish. The decision binds the exact packet, manifest, and app hashes; records
the closed checklist, independence assertions, findings, and disposition; and
grants no deployment or physical authority. The software validates structure
and internal bindings but cannot authenticate the human identity or manufacture
independence; custody and identity evidence remain external.
For integration development, the same decision schema permits the explicit
`SYNTHETIC_TEST_ONLY` origin. Its assessment returns
`SYNTHETIC_REHEARSAL_ACCEPTED` and `synthetic_rehearsal_ready=true`, while
retaining `SYNTHETIC_EVIDENCE_NOT_INDEPENDENT`,
`ready_for_epoch_intake=false`, and every physical authority flag false. This
allows the workstreams to rehearse serialization and binding without confusing
synthetic success with production review.
The [owner AI-review acceptance](native_t102_owner_ai_review_acceptance_v1.schema.json)
records the project owner's explicit governance choice to accept the exact,
hash-bound internal ARM-054 AI technical review as the prerequisite for a later
read-only endpoint-qualification intake. It preserves that no human review or
external independence is claimed. Read-only intake eligibility is not endpoint
open authority: controller startup, transport writes, execution, hardware
access, and physical authority remain false.
The [read-only endpoint intake](native_t102_read_only_endpoint_intake_v1.schema.json)
binds that exact acceptance to one explicitly pinned serial identity and one
bounded passive observation plan. It is a hardware-incapable prerequisite
record only: it permits no endpoint open, startup, write, active request,
movement, torque action, retry, or fallback. A valid intake is merely ready for
a separate, explicit read-only authorization and cannot supply that authority
itself.
The [read-only endpoint qualification receipt](native_t102_read_only_endpoint_qualification_v1.schema.json)
records the separately authorized one-open passive observation against that
intake. It closes over the exact identity before and after open, bounded lines,
lifecycle counts, zero outbound activity, and retained non-authority flags. A
completed empty passive window proves only that the endpoint opened and closed
under the zero-write policy; it does not prove controller protocol or firmware
identity.
The [active-feedback intake](native_t105_active_feedback_intake_v1.schema.json)
binds that passive receipt and exact endpoint to the canonical ten bytes
`{"T":105}\n`, one response line, one open/write/read/close lifecycle, and
zero T=102, movement, torque, retry, purge, fallback, startup, or control-line
assertion. Its fake-only rehearsal checks the lifecycle and strict T=1051
parsing without accepting an arbitrary transport. The retained intake cannot
open COM7 or authorize its active write; that requires a later explicit
authorization naming its hash.
The [active-feedback qualification receipt](native_t105_active_feedback_qualification_v1.schema.json)
retains the separately authorized one-attempt lifecycle, exact raw response,
and zero-effect counters. ARM-064 received `FAULT:NOT_READY` rather than
T=1051, closed successfully, and made no retry. The source tree contains that
exact fault in the finite ghost-typing diagnostic, which makes the response
consistent with an installed diagnostic surface that does not expose generic
T=105 feedback. This source match is an inference, not installed-firmware
attestation.
The [measured configuration-epoch intake](controller_configuration_epoch_intake_v1.schema.json)
and [intake assessment](controller_configuration_epoch_intake_report_v1.schema.json)
require that full decision, rather than accepting only an arbitrary review hash
and disposition, and bind the reviewed release to all eight measured workcell
components. The candidate app digest is explicit but separate from the epoch
digest, avoiding a self-referential firmware build. A passing assessment makes
only an epoch-bound build proposal ready; installation, startup, transport,
execution, and physical authority remain false.
The epoch intake also has a strict JSON decoder and a synthetic builder covering
all eight ordered components. Its synthetic report is intentionally `BLOCKED`
by `FIRMWARE_REVIEW_DECISION_BLOCKED` and
`COMPONENT_NOT_PHYSICAL_ORIGINAL`; a separate rehearsal summary may record that
the integration exercise completed, but it cannot change the production report.
The [owner-governed epoch draft](owner_governed_configuration_epoch_draft_v1.schema.json)
and [assessment](owner_governed_configuration_epoch_assessment_v1.schema.json)
form the non-human-review successor path selected in ARM-067. They preserve the
historical contract unchanged, bind the exact owner acceptance, and support
partial evidence intake so every missing component and binding remains visible.
Only a complete, current, physical-original, owner-AI-accepted eight-component
draft receives a configuration-epoch hash. Even that result permits only an
epoch-bound build proposal and grants no hardware authority.
The [software-build evidence](software_build_epoch_evidence_v1.schema.json) and
[owner-AI review](software_build_owner_ai_review_v1.schema.json) close the
first owner-governed epoch component from tracked source and reviewed r97
release identities. They distinguish retained original software inputs from a
physical measurement, advance only `software_build`, and grant no controller
or physical authority.
The [camera/support/optics intake](camera_support_optics_epoch_intake_v1.schema.json)
and [readiness assessment](camera_support_optics_epoch_assessment_v1.schema.json)
provide the next component boundary. Catalog specifications and digital support
designs are retained as context but never promoted to physical originals. All
four bindings must carry current retained-original evidence and owner-AI review
before the adapter can construct a `camera_support_optics` epoch component.
The [retained-original owner-AI review](camera_support_original_owner_ai_review_v1.schema.json)
and [binding adapter receipt](camera_support_binding_adapter_receipt_v1.schema.json)
define the file-backed bridge into those four slots. The loader permits only
bounded regular files below one canonical root, rejects duplicate JSON fields,
verifies both content hashes, requires canonical binding order, and fixes all
hardware authority false. It authenticates an already completed review; it does
not collect evidence, open the camera, determine freshness, or advance an epoch.
The [synthetic epoch model-to-arm rehearsal](synthetic_epoch_model_arm_rehearsal_v1.schema.json)
then binds that exact blocked epoch to one model batch, its indexed proposal, a
sealed trajectory, the Waveshare encoding profile, and the zero-write receipt.
Success requires at least one reviewable encoded command while transport writes,
retry, execution authority, and production dispatch all remain disabled. This
is an interface-compatibility artifact, not evidence of planning accuracy,
installed-controller readiness, or physical safety.
The [AI-emitted epoch model-to-arm rehearsal](ai_emitted_epoch_model_arm_rehearsal_v1.schema.json)
adds the producer/consumer seam that the synthetic rehearsal alone cannot
prove. It requires canonical bytes produced by the real AI batch assembler,
their exact registry-ingress and freshness reports, and the real arm planner's
calibration-blocked result. A separate synthetic downstream preview may bind
the same batch and proposal to the epoch and encoder, but the schema fixes that
preview as synthetic and fixes installation, startup, execution, retry,
hardware access, physical authority, and production dispatch false. It is not
model qualification or evidence that the measured planner can produce a route.
The [model-to-arm conformance profile](model_arm_conformance_profile_v1.schema.json)
freezes the shared v2 producer/consumer boundary as executable expectations. It
distinguishes structural compatibility from operational readiness, preserves
the initial keyboard/contact-only scope, and makes arm-owned motion policy and
authority fields explicitly unavailable to model output. Its passing synthetic
cases prove only that canonical AI bytes reach the correct arm gate and that
unsafe or unsupported variants fail closed; they grant no hardware authority.
The [model/arm operational-readiness report](model_arm_operational_readiness_v1.schema.json)
composes that software boundary with the current owner-governed configuration
epoch, physical camera/support intake, owner AI-governance acceptance, measured
planner state, and installed-controller assessment. It removes the superseded
external-human-review blocker while retaining every technical blocker. A READY
result advances only to a separately reviewed single-action candidate; this
report never permits dispatch or emits controller commands.

[Precision observation v2](precision_observation_v2.schema.json) carries explicit
localization abstention or a reference to externally qualified uncertainty.
[Localization qualification v0](localization_qualification_v0.schema.json)
binds an offline synthetic error bound to a checkpoint, domain, target set,
and distinct calibration/evaluation datasets. No qualification is installed.
The producer constructs the existing shared ModelMotionBatch only after
precision and scene checks; scene confidence cannot fill a localization gap.

The [camera-arrival consumer handoff](camera_arrival_consumer_handoff_v1.schema.json)
binds each structurally valid arrival original to the exact consumer source,
downstream schema, and field binding in the current checkout. The companion
[consumer receipt](camera_arrival_consumer_validation_receipt_v1.schema.json)
and [aggregate assessment](camera_arrival_consumer_validation_assessment_v1.schema.json)
retain each consumer pass or blocker against those exact hashes. Completion is
only readiness for offline review; all epoch, registry, qualification, device,
write, movement, admission, and physical-authority fields remain false.
Domain adapters cover the camera/support assessment, localization campaign
preflight, held-out localization evaluation, typed planner snapshot, and typed
installed collision/cable profile. They preserve native blocked outcomes and
do not make the generic receipt gate responsible for domain-specific pass
criteria. Complete route coverage therefore remains distinct from 15 passing
receipts.
