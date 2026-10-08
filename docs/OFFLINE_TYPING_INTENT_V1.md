# Offline typing intent v1

`rocell.offline_typing_intent.v1` is the closed, offline input contract for the
typing planner. It has four variants: `TYPE_TEXT`, `PRESS_KEY`, `CLARIFY`, and
`REFUSE`. Additional fields are rejected.

The current motion adapter accepts only `TYPE_TEXT` with `device` set to
`KEYBOARD`. It preserves `text` exactly and passes it to the deterministic
keystroke compiler. `PHONE`, `PRESS_KEY`, `CLARIFY`, and `REFUSE` stop before
motion workspace creation.

The optional local classifier uses the internal
`rocell.offline_intent_classification.v1` schema to choose only the intent type,
device, or closed reason. It does not generate the `TYPE_TEXT` payload. The
public intent composer extracts exact text from the request with a closed,
fail-safe grammar and rejects any actionable classification it cannot compose.
The first classifier campaign remains rejected because its fresh unquoted-text
template was not admitted by that grammar, even though classification itself
was exact on its development cases. No classifier is promoted by that result.

## Compatibility

Compatibility: additive. Existing `ModelMotionBatchV2`, proposal, ingress,
trajectory, collision, freshness, and execution contracts are unchanged. The
intent object is an upstream input and adds no joint, PWM, serial, controller,
permit, transport, or authority fields to the model-to-arm boundary.

## Migration and rollback

Callers may migrate by emitting one of the four exact variants defined in
`software/ai/schemas/offline_typing_intent_v1.schema.json`. Only callers that
need keyboard text motion should invoke the ARM-521 adapter.

Rollback requires disabling the intent adapter and returning to the ARM-520
dynamic planner's explicit text argument. No stored batch, arm-runtime schema,
controller configuration, or physical state needs conversion. The installed
collision profile and fresh observed start state remain required in either
configuration.

The internal classification schema requires no migration because its rejected
candidate is disconnected from the runtime. Removing the classifier and its
offline evaluator restores the earlier deterministic composition path without
converting any public intent or motion artifact.

## Current evidence boundary

ARM-521 proves one structured keyboard intent reaches a fresh simulated v2
batch and complete canonical IK route. It does not prove language-model intent
accuracy, collision safety, key registration, transport, or physical movement.

Classifier corpus generation now admits every expected result through the
production deterministic composer before training. The first campaign with
this check remains rejected: 18 of 200 development classifications failed, and
a provenance audit found request wording reused from its predecessor. Future
campaigns must also prove zero historical request overlap before writing data.
These campaign checks do not alter the public intent or motion contracts.
