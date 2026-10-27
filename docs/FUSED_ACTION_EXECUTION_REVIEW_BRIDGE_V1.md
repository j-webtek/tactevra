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
