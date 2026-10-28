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
