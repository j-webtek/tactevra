# Fused action admission to execution review bridge v1

## Scope

The fused camera state action admission can enter the existing single action
execution review while retaining the exact route, target, action, interaction,
runtime session, collision profile, operator confirmation, verifier, and
freshness lineage that authorized review.

The bridge is an application adapter with zero execution authority. It does not
consume a review, create a permit, encode a controller command, access hardware,
or move the arm.

## Contract

The producer seals `valid_until` as the earliest expiry of the consumed route
entry, operator confirmation, and effect verifier. The bridge validates the
admission's exact field set and digest, checks that the requested review remains
inside that lifetime, binds the admitted target and action to the exact motion
proposal, and binds the runtime session and installed collision profile to the
supporting evidence.

After those checks pass, the bridge delegates to the existing single action
execution review builder. Controller readiness, collision qualification,
contact envelope, T102, configuration, and trajectory checks therefore remain
authoritative.

The resulting `rocell.single_action_execution_review.v1` document may include
`fused_camera_state_action_review_admission_sha256`. When present, that digest
is covered by the review's own content hash.

## Permit orchestration

`FusedCameraStateReviewedMotionPermitSessionV1` owns the next transition for a
fused review. It accepts only reviews that carry the fused action-admission
digest, derives the required safety capability from the reviewed interaction,
and uses one monotonic timestamp for review consumption and supervisor
evaluation. The requested permit lifetime must end no later than the review
deadline.

The session consumes its in-memory gate once and delegates permit issuance to
the existing `SafetySupervisor` bridge. The returned permit admission retains
the fused action-admission digest, so camera, route, operator, verifier,
trajectory, review, and exact-goal permit lineage remain connected. A global
machine-ledger reservation keyed by the review digest prevents a reconstructed
gate from consuming the same review again with a different receipt timestamp.
The reservation is fail closed and is not released after failed preflight.

This boundary creates a short-lived, single-use physical capability only when
the safety supervisor approves the current conditions. It does not access a
transport, encode or write a command, move the arm, retry an action, or verify
an effect. Dispatch, settling, and independent effect verification remain
downstream requirements.

## Sole-writer and settlement rehearsal

The typed fused permit result can enter the existing production-shaped T=102
runtime rehearsal without callers separating or replacing its permit,
admission, and lifecycle. The exact decoded target, sole writer, controller
session, configuration epoch, and encoding profile are rechecked at the final
boundary, and the dispatch timestamp is also used to consume the permit.

The terminal execution report explicitly carries the fused action-admission
digest and review-consumption digest alongside the permit binding. A modeled
accepted-once acknowledgment and consecutive fresh T=1051 joint samples may
close the lifecycle as settled. Crossed identities reject before the write
boundary; zero, partial, ambiguous, unacknowledged, stale, or unsettled results
are terminal and cannot retry or authorize a successor action.

The rehearsal sink has no serial, socket, callback, or device API. It records
zero physical writes, does not claim an authentic controller receipt, and does
not verify the keyboard effect. Native transport, independently acquired
feedback, physical settling, and effect verification remain downstream gates.

## Durable native handoff preparation

The accepted fused permit result can now prepare the existing durable native
T=102 handoff without callers separating its permit and admission. Preparation
rechecks the exact T=102 goal and requires the runtime frame and preparation
instant to remain inside the permit lifetime. The immutable prepared record and
its snapshot carry the fused action-admission digest and review-consumption
digest alongside the permit, frame, writer, controller-session, configuration,
encoding-profile, and adapter-candidate bindings.

Preparation deliberately stops before the writer claim. The permit remains
unspent, the lifecycle remains `ACCEPTED`, recovery remains cancellation and
fresh replanning, and transport-open and physical-write counts remain zero.
External native authority, exclusive writer claim, native transport, authentic
feedback, observed settling, and independent effect verification are still
required downstream.

## Durable native writer claim

The prepared fused handoff can now cross the exclusive-writer ambiguity
boundary without callers reconstructing its authority objects. The claim path
requires the lifecycle to remain `ACCEPTED`, the permit to retain its one use,
the fused action-admission and review-consumption lineage to match, and the
claim instant to remain inside both the command frame and permit lifetimes.

The immutable claim is committed before any future transport open. From that
point recovery is `RETRY_FORBIDDEN_DISPATCH_UNCERTAIN`; cancellation and blind
resend are no longer safe. The claim itself grants no physical authority,
authorizes no transport open, performs no command write, and does not consume
the permit. External signed authority must bind to this exact claim before the
existing production transport boundary can be considered.

## External native authority admission

A machine-verified external authority record can now be admitted through the
fused path only when it binds the exact claimed handoff, reviewed action,
runtime frame, pinned endpoint, writer, controller session, configuration, and
encoding profile. Its signed lifetime must fit inside both the frame lifetime
and the fused motion-permit lifetime.

Admission does not consume the external authority or motion permit. It creates
no production-attempt journal, opens no transport, writes no controller bytes,
and claims no physical result. The existing production boundary remains
responsible for durably starting an attempt before it atomically consumes the
authority and permit and invokes any native transport.

## Durable production candidate composition

The fused path can now delegate one exact claimed handoff and admitted external
authority to the existing durable production-candidate lifecycle. Before that
delegation, it rechecks the accepted fused lifecycle, unspent permit, fused
action-admission and review-consumption digests, claimed handoff, command frame,
wire bytes, pinned endpoint, writer, controller session, configuration epoch,
encoding profile, signed authority lifetime, and exact approval decision.

The production lifecycle remains the sole owner of the irreversible ordering:
it spends the machine-ledger execution reservation, flushes the durable start,
consumes the external authority and motion permit once, binds the transport
grant, makes at most one open/write/capture/close attempt, and commits a terminal
receipt that forbids replay. The fused wrapper then verifies that the permit is
spent and the terminal receipt preserves the complete claim lineage.

This API accepts an abstract transport supplied by its caller; it neither
discovers nor constructs a serial provider. Repository tests use a scripted
implementation with no device handle. Their success status is explicitly
`CONTROLLER_EVIDENCE_CAPTURED_SETTLED_UNQUALIFIED`: it does not authenticate a
controller, prove physical movement, qualify the installed setup, or verify a
keyboard effect. The existing reviewed lifecycle remains `ACCEPTED` because its
event contract accepts rehearsal dispatch receipts, not native production
receipts; the durable native terminal snapshot is authoritative for this path.

## Windows provider composition evidence

The repository now exercises this fused wrapper through the actual
`WindowsNativeT102SerialTransportV1` class. The test supplies an in-memory
pyserial-shaped connection and exact pinned inventory, so the provider runs its
normal endpoint verification, execution-grant, canonical T=102, quiescent
buffer, bounded read, T=105 request, and one-shot counter logic without loading
pyserial or reaching an OS device.

The composed fixture observes one open, one exact T=102 write, two exact T=105
requests, two settled T=1051 samples, and one close. It also verifies durable
terminal/no-replay state and single-use permit consumption. This is source-level
composition evidence only: the resulting receipt keeps
`transport_implementation_qualified`, `authentic_controller_receipt_claimed`,
and `physical_movement_verified` false. Installed transport qualification and
independently acquired controller and keyboard-effect evidence remain required.

## Compatibility and migration

The schema addition is optional. Existing callers may continue to build single
action execution reviews directly, and reviews without the fused admission
digest retain their previous serialized form and digest.

Callers that require fused camera lineage should use
`build_fused_camera_state_single_action_execution_review_v1` and provide a
review wall clock time plus the corresponding monotonic interval. The adapter
rejects expired admissions and review intervals that outlive the admission.

## Rollback

Runtime orchestration can return to the direct review builder without changing
the legacy review contract. Removing the adapter and optional schema property
restores the earlier producer surface; no hardware state or firmware migration
is involved.

The permit orchestrator is an explicit module import and does not replace the
legacy permit bridge. Rolling it back removes the fused-only entry point; the
machine ledger remains append-only, so already reserved reviews stay spent.

The runtime wrapper is also an explicit call. Removing it returns callers to
the generic hardware-incapable T=102 rehearsal. The optional fused lineage
fields preserve the legacy report shape and hash when the admission did not
originate from the fused camera path.

The native handoff additions are optional. Legacy admissions retain their prior
prepared-record and snapshot shapes and hashes. Rolling back the fused handoff
entry point leaves existing immutable journals readable and returns fused
callers to the hardware-incapable runtime rehearsal.

Removing the fused claim entry point leaves already claimed journals readable.
Those claims remain retry-forbidden ambiguity records and must not be converted
back into cancellation-safe prepared handoffs.

Removing the fused authority-admission adapter returns callers to the generic
machine-verification boundary. It does not revoke or consume authority records
that were already admitted in memory, and it changes no durable journal format.

Removing the fused production-candidate wrapper leaves the generic production
boundary and every existing durable attempt readable. Any attempt whose durable
start exists remains retry-forbidden even if this optional composition entry
point is rolled back.
